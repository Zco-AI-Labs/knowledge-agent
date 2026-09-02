import logging
import os
import re
import asyncio
from typing import Optional, Dict, Any, List
from google.cloud import aiplatform_v1beta1
import vertexai
from vertexai.language_models import TextEmbeddingModel, TextEmbeddingInput
from google.cloud.firestore_v1.vector import Vector
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.base_query import FieldFilter
from app.core import hubscape_adk

logger = logging.getLogger(__name__)

@hubscape_adk.require_tool_privilege
@hubscape_adk.tool_scope(["hub", "org"])
async def search_knowledge(
    query: str,
    top_k: int = 5
) -> dict:
    """
    Searches the hub's private knowledge base for factual grounding context.
    Executes primary Cloud Firestore Vector Search with automatic fallback to
    the Vertex AI Sharded RAG Corpus.

    Args:
        query: The semantic search query or question to ground against the knowledge base.
        top_k: Maximum number of relevant chunks to retrieve (default: 5).

    Returns:
        A dictionary with "status" and "result" containing formatted search snippets and source URLs.
    """
    try:
        context = hubscape_adk.get_context()
        hub_id = context.auth.hub_id
        org_id = context.auth.org_id
        user_id = context.auth.get_user_id()
        db_client = context._db_client
    except Exception as ce:
        logger.warning(f"[knowledge_agent] Could not resolve RemoteContext ({ce}), using fallback defaults.")
        hub_id = None
        org_id = None
        user_id = "unknown"
        from google.cloud import firestore
        db_client = firestore.Client(project=os.environ.get("PROJECT_ID") or "hubscape-geap")

    logger.info(f"[knowledge_agent] search_knowledge called for hub_id='{hub_id}', org_id='{org_id}', query='{query}'")

    project_id = os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT") or "hubscape-geap"
    location = os.environ.get("REGION", "us-central1")

    # Read platform settings to determine primary vs fallback mode
    rag_provider = "FIRESTORE_VECTOR"
    shards = []
    corpus_id = None
    try:
        platform_ref = db_client.collection('settings').document('platform')
        platform_snap = await asyncio.to_thread(platform_ref.get)
        if platform_snap and hasattr(platform_snap, "exists") and platform_snap.exists:
            raw_dict = platform_snap.to_dict() if hasattr(platform_snap, "to_dict") else {}
            if isinstance(raw_dict, dict):
                platform_data = raw_dict
                rag_provider = platform_data.get("rag_provider", "FIRESTORE_VECTOR")
                shards = platform_data.get("rag_corpus_shards") or []
                corpus_id = platform_data.get("rag_corpus_id")
    except Exception as pe:
        logger.debug(f"[knowledge_agent] Notice reading platform settings: {pe}")

    # =========================================================================
    # 1. PRIMARY ENGINE: CLOUD FIRESTORE VECTOR SEARCH (Sub-100ms, Pre-Siloed)
    # =========================================================================
    if not isinstance(rag_provider, str) or rag_provider in ("FIRESTORE_VECTOR", "DEFAULT", "ALL"):
        try:
            logger.info(f"[knowledge_agent] [Primary] Executing Firestore Vector Search for hub '{hub_id}'...")
            
            # Generate query embedding via Vertex AI text-embedding-005
            def _get_query_embedding():
                vertexai.init(project=project_id, location=location)
                model = TextEmbeddingModel.from_pretrained("text-embedding-005")
                input_item = TextEmbeddingInput(text=query.strip(), task_type="RETRIEVAL_QUERY")
                embeddings = model.get_embeddings([input_item], output_dimensionality=768)
                return embeddings[0].values

            query_embedding = await asyncio.to_thread(_get_query_embedding)
            query_vector = Vector(query_embedding)

            # Query Firestore with hardware-level tenant scope pre-filtering
            coll_ref = db_client.collection("rag_knowledge_chunks")
            vector_query = coll_ref
            if hub_id:
                vector_query = vector_query.where(filter=FieldFilter("hubId", "==", hub_id))
            elif org_id:
                vector_query = vector_query.where(filter=FieldFilter("orgId", "==", org_id))

            # Stage 1: Wide Candidate Fetch Pool (60 to 100 chunks for high-density capture)
            fetch_limit = min(max((top_k or 5) * 6, 60), 100)
            vector_query = vector_query.find_nearest(
                vector_field="embedding",
                query_vector=query_vector,
                distance_measure=DistanceMeasure.COSINE,
                limit=fetch_limit
            )

            chunk_snaps = await asyncio.to_thread(vector_query.get)
            
            if chunk_snaps:
                raw_candidates = []
                for s in chunk_snaps:
                    data = s.to_dict() or {}
                    raw_candidates.append({
                        "title": data.get("title") or "Grounded Document",
                        "content": data.get("content") or "",
                        "url": data.get("sourceUrl") or data.get("url"),
                        "allowDownload": data.get("allowDownload", True),
                        "parentDocId": data.get("parentDocId"),
                        "chunkIndex": data.get("chunkIndex", 0),
                        "chunkId": s.id
                    })

                # Stage 1.5: Deterministic Intent Classification & Adaptive Calibration
                q_clean = query.lower().strip()
                q_tokens = [w for w in re.findall(r'[a-zA-Z0-9_-]+', q_clean) if len(w) > 2]
                
                is_listing_intent = any(k in q_clean for k in [
                    "list all", "which stores", "which brands", "what are all", "all stores", "all restaurants",
                    "all brands", "all shops", "directory", "catalog", "overview", "upcoming events", "list of",
                    "options for", "stores are located", "what stores", "what brands", "all beauty", "all sports",
                    "what are the", "which international", "top beauty", "top brands"
                ])
                is_targeted_fact = any(q_clean.startswith(k) for k in [
                    "where is", "what is the phone", "phone number", "what time", "hours of", "when does", "contact for"
                ]) and not is_listing_intent

                if is_listing_intent:
                    base_k = 16
                    max_cluster_k = 38
                    allowed_per_doc = 8
                elif is_targeted_fact:
                    base_k = 5
                    max_cluster_k = 8
                    allowed_per_doc = 2
                else:
                    base_k = 10
                    max_cluster_k = 25
                    allowed_per_doc = 4

                # Respect explicit top_k if caller specifically requested custom depth
                if top_k and top_k != 5:
                    base_k = top_k
                    max_cluster_k = max(top_k * 2, max_cluster_k)

                # Stage 2: Exact Entity & Title Affinity Boost
                boosted_keys = set()
                boosted_items = []
                standard_items = []
                for item in raw_candidates:
                    title_lower = (item["title"] or "").lower()
                    url_lower = (item["url"] or "").lower()
                    
                    is_match = False
                    if any(tok in title_lower or tok in url_lower for tok in q_tokens):
                        is_match = True
                        doc_k = item["url"] or item["parentDocId"] or item["title"] or item["chunkId"]
                        boosted_keys.add(doc_k)

                    if is_match:
                        boosted_items.append(item)
                    else:
                        standard_items.append(item)

                ordered_candidates = boosted_items + standard_items

                # Stage 3: High-Density Cluster Expansion & Token Budget Enforcement
                results = []
                doc_counts: Dict[str, int] = {}
                accumulated_chars = 0
                MAX_CHAR_BUDGET = 50000  # ~15,000 tokens safety ceiling

                # Determine effective target K based on cluster density
                has_dense_boosted_cluster = len(boosted_items) >= 8 or is_listing_intent
                effective_target_k = max_cluster_k if has_dense_boosted_cluster else base_k

                for item in ordered_candidates:
                    doc_key = item["url"] or item["parentDocId"] or item["title"] or item["chunkId"]
                    current_count = doc_counts.get(doc_key, 0)
                    
                    # Allow up to 8 chunks for boosted/directory docs, standard tier otherwise
                    effective_max_doc = allowed_per_doc if (doc_key in boosted_keys or is_listing_intent) else 3
                    if current_count >= effective_max_doc:
                        continue
                    
                    chunk_text = item.get("content", "")
                    if accumulated_chars + len(chunk_text) > MAX_CHAR_BUDGET and len(results) >= base_k:
                        logger.info(f"[knowledge_agent] 🛡️ Reached token safety ceiling ({accumulated_chars} chars). Finalizing results.")
                        break

                    doc_counts[doc_key] = current_count + 1
                    results.append(item)
                    accumulated_chars += len(chunk_text)

                    if len(results) >= effective_target_k:
                        break

                logger.info(f"[knowledge_agent] ✅ [Primary] Firestore Vector Search returned {len(results)} high-signal chunks (Target K: {effective_target_k}, Chars: {accumulated_chars}) across {len(doc_counts)} sources.")

                # Telemetry logging to GCP Cloud Logging / BigQuery
                try:
                    from datetime import datetime
                    from google.cloud import firestore as gcp_fs
                    from google.cloud import logging as gcp_logging
                    
                    event_payload = {
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "successful": True,
                        "hubId": hub_id,
                        "orgId": org_id,
                        "userId": user_id,
                        "agentId": "knowledge_agent",
                        "type": "firestore_vector_search",
                        "provider": "Cloud Firestore Vector",
                        "modelId": "text-embedding-005",
                        "metadata": {
                            "queryCount": 1,
                            "queryLength": len(query),
                            "resultCount": len(results),
                            "systemCredits": 50,
                            "estimatedCostUsd": 0.002
                        }
                    }
                    gcp_client = gcp_logging.Client()
                    logger_gcp = gcp_client.logger("hubscape.platform.transactions")
                    logger_gcp.log_struct(event_payload, severity="INFO")

                    if org_id:
                        billing_ref = db_client.collection("organizations").document(org_id).collection("billing").document("status")
                        await asyncio.to_thread(
                            billing_ref.update,
                            {
                                "creditsAvailable": gcp_fs.Increment(-50),
                                "creditsUsed": gcp_fs.Increment(50),
                                "lastUpdated": gcp_fs.SERVER_TIMESTAMP
                            }
                        )
                except Exception as tel_err:
                    logger.debug(f"[knowledge_agent] Telemetry notice: {tel_err}")

                formatted_result = ""
                for idx, r in enumerate(results):
                    formatted_result += f"--- Knowledge Item {idx+1}: {r['title']} ---\n"
                    url = r.get('url')
                    allow_download = r.get('allowDownload', True)
                    if url:
                        if url.startswith('/api/media/file') and allow_download:
                            if any(url.lower().endswith(ext) or f"{ext}?" in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.avif', '.bmp']):
                                formatted_result += f"🖼️ Image Preview: ![{r['title']}]({url})\n"
                            else:
                                formatted_result += f"📄 Downloadable File: [⬇️ Download {r['title']}]({url})\n"
                        elif 'maps.google' in url or 'google.com/maps' in url or 'openstreetmap' in url or 'waze.com' in url or 'apple.com/maps' in url:
                            # Standardize Google Maps links to direct search query if bare domain
                            if url.strip() in ['https://maps.google.com', 'https://www.maps.google.com', 'https://google.com/maps', 'https://www.google.com/maps', 'http://maps.google.com', 'http://google.com/maps']:
                                import urllib.parse
                                safe_query = urllib.parse.quote_plus(r['title'])
                                url = f"https://www.google.com/maps/search/?api=1&query={safe_query}"
                            formatted_result += f"📍 Location & Map Link: [📍 View on Map]({url})\n"
                        elif not url.startswith('file://') and not url.startswith('/api/media/file'):
                            formatted_result += f"🔗 Source / Website Link: [🌐 {r['title']}]({url})\n"
                        elif not allow_download:
                            formatted_result += f"Source: {r['title']} (Internal Grounding Only - Raw File Download Restricted)\n"
                    formatted_result += f"{r['content']}\n\n"

                return {"status": "success", "result": formatted_result.strip()}

            logger.info("[knowledge_agent] [Primary] 0 results in Firestore chunks. Checking Vertex fallback...")
        except Exception as ve:
            logger.error(f"[knowledge_agent] ⚠️ [Primary] Firestore Vector search error: {ve}", exc_info=True)

    # =========================================================================
    # 2. STANDBY FALLBACK: VERTEX AI SHARDED RAG CORPUS (Decommissioned)
    # =========================================================================
    # [DEPRECATION NOTICE / ARCHITECTURAL DIRECTIVE]
    # Vertex AI RAG Corpus search fallback is decommissioned and disabled by default.
    # All search and retrieval is standardized on Firebase Vector RAG (rag_knowledge_chunks).
    # DO NOT treat this bypass as a bug or re-enable without explicit architectural approval.
    # ==============================================================================
    enable_vertex_rag = os.environ.get("ENABLE_VERTEX_RAG_DUAL_INGEST", "false").lower() == "true"
    if not enable_vertex_rag:
        logger.info("[knowledge_agent] Standby Vertex RAG search fallback bypassed (Decommissioned in favor of Firebase Vector RAG).")
        return {"status": "success", "result": "No relevant search results found."}

    try:
        if shards and isinstance(shards, list) and len(shards) > 0:
            import hashlib
            routing_key = str(hub_id or org_id or "default")
            shard_idx = int(hashlib.md5(routing_key.encode("utf-8")).hexdigest(), 16) % len(shards)
            corpus_id = shards[shard_idx]
            logger.info(f"[knowledge_agent] [Fallback] Routed to RAG shard {shard_idx}: {corpus_id}")

        if not corpus_id:
            return {"status": "success", "result": "No relevant search results found."}

        # Prevent API keys in the environment from overriding OIDC/ADC credentials
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("GOOGLE_API_KEY", None)

        import google.auth
        import httpx as httpx_sync
        from google.oauth2.credentials import Credentials

        credentials = None
        try:
            meta_url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
            resp = httpx_sync.get(meta_url, headers={"Metadata-Flavor": "Google"}, timeout=2.0)
            if resp.status_code == 200:
                tok = resp.json().get("access_token")
                if tok:
                    credentials = Credentials(tok)
        except Exception:
            pass

        if not credentials:
            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])

        from google.api_core.client_options import ClientOptions
        client_options = ClientOptions(api_endpoint=f"{location}-aiplatform.googleapis.com")
        client = aiplatform_v1beta1.VertexRagServiceClient(
            client_options=client_options,
            credentials=credentials
        )

        candidate_limit = 100
        query_obj = aiplatform_v1beta1.types.RagQuery(
            text=query,
            similarity_top_k=candidate_limit
        )
        rag_resource = aiplatform_v1beta1.types.RetrieveContextsRequest.VertexRagStore.RagResource(
            rag_corpus=corpus_id
        )
        vertex_rag_store = aiplatform_v1beta1.types.RetrieveContextsRequest.VertexRagStore(
            rag_resources=[rag_resource]
        )
        parent_location = f"projects/{project_id}/locations/{location}"
        request = aiplatform_v1beta1.types.RetrieveContextsRequest(
            parent=parent_location,
            vertex_rag_store=vertex_rag_store,
            query=query_obj
        )

        response = await asyncio.to_thread(client.retrieve_contexts, request=request)
        contexts_list = getattr(response, "contexts", None)
        contexts = getattr(contexts_list, "contexts", []) if contexts_list else []

        file_ids = []
        for context_item in contexts:
            fid = ""
            if hasattr(context_item, 'chunk') and context_item.chunk:
                fid = getattr(context_item.chunk, 'file_id', '')
            if fid:
                file_ids.append(fid)

        registry_map = {}
        if file_ids:
            corpus_id_num = corpus_id.split('/')[-1]
            project_number = os.environ.get('PROJECT_NUMBER') or os.environ.get('GCP_PROJECT_NUMBER') or "1097730318341"
            full_ids = []
            for fid in set(file_ids):
                full_ids.append(f"projects/{project_id}/locations/{location}/ragCorpora/{corpus_id_num}/ragFiles/{fid}")
                full_ids.append(f"projects/{project_number}/locations/{location}/ragCorpora/{corpus_id_num}/ragFiles/{fid}")

            chunked_ids = [full_ids[i:i + 30] for i in range(0, len(full_ids), 30)]
            for batch in chunked_ids:
                registry_docs = await asyncio.to_thread(
                    lambda b=batch: db_client.collection('rag_knowledge').where('ragFileId', 'in', b).get()
                )
                for rdoc in registry_docs:
                    rdata = rdoc.to_dict()
                    fid = rdata.get('ragFileId', '').split('/')[-1]
                    if fid:
                        registry_map[fid] = rdata

        results = []
        job_cache = {}
        for context_item in contexts:
            fid = ""
            if hasattr(context_item, 'chunk') and context_item.chunk:
                fid = getattr(context_item.chunk, 'file_id', '')

            doc_meta = registry_map.get(fid, {})
            if not doc_meta and hasattr(context_item, 'source_uri') and context_item.source_uri:
                s_uri = context_item.source_uri or ""
                if "rag_batch_imports" in s_uri:
                    parts = s_uri.split('rag_batch_imports/')[1].split('/')
                    job_id = parts[0] if parts else ""
                    filename = parts[-1]
                    d_id = filename.split('_')[0]
                    if d_id:
                        dsnap = await asyncio.to_thread(db_client.collection('rag_knowledge').document(d_id).get)
                        if dsnap.exists:
                            doc_meta = dsnap.to_dict() or {}
                    
                    if not doc_meta and job_id:
                        if job_id not in job_cache:
                            jsnap = await asyncio.to_thread(db_client.collection('rag_jobs').document(job_id).get)
                            job_cache[job_id] = jsnap.to_dict() if jsnap.exists else {}
                        jdata = job_cache.get(job_id) or {}
                        if jdata:
                            raw_title = filename[len(d_id)+1:].rstrip('.md').replace('_', ' ') if d_id else (context_item.source_display_name or "Grounded Document")
                            doc_meta = {
                                'ownerId': jdata.get('hubId'),
                                'orgId': jdata.get('orgId'),
                                'title': raw_title or "Grounded Document",
                                'sourceUrl': jdata.get('siteUrl') or context_item.source_uri
                            }
                elif "knowledge_uploads" in s_uri:
                    parts = s_uri.split('knowledge_uploads/')[1].split('/')
                    path_hub_id = parts[0] if parts else ""
                    if path_hub_id:
                        import urllib.parse
                        encoded_kpath = urllib.parse.quote(f"knowledge_uploads/{s_uri.split('knowledge_uploads/')[1]}", safe='')
                        doc_meta = {
                            'ownerId': path_hub_id,
                            'title': context_item.source_display_name or "Uploaded Document",
                            'sourceUrl': f"/api/media/file?path={encoded_kpath}",
                            'allowDownload': True
                        }

            owner_id = doc_meta.get('ownerId')
            doc_org_id = doc_meta.get('orgId')
            is_allowed = (
                owner_id == 'platform_host' or
                (hub_id and owner_id == hub_id) or
                (org_id and doc_org_id == org_id)
            )
            if not is_allowed:
                continue

            results.append({
                "title": doc_meta.get('title') or context_item.source_display_name or "Grounded Document",
                "content": context_item.text,
                "url": doc_meta.get('sourceUrl') or doc_meta.get('url') or context_item.source_uri,
                "allowDownload": doc_meta.get('allowDownload', True)
            })

            if len(results) >= top_k:
                break

        if not results:
            return {"status": "success", "result": "No relevant search results found."}

        formatted_result = ""
        for idx, r in enumerate(results):
            formatted_result += f"--- Result {idx+1}: {r['title']} ---\n"
            url = r.get('url')
            allow_download = r.get('allowDownload', True)
            if url:
                if url.startswith('/api/media/file') and allow_download:
                    formatted_result += f"File Download / View Link: {url}\n"
                elif not url.startswith('file://') and not url.startswith('/api/media/file'):
                    formatted_result += f"Source URL: {url}\n"
                elif not allow_download:
                    formatted_result += f"Source: {r['title']} (Internal Grounding Only - Raw File Download Restricted)\n"
            formatted_result += f"{r['content']}\n\n"

        return {"status": "success", "result": formatted_result.strip()}

    except Exception as e:
        logger.error(f"[knowledge_agent] Fallback Vertex search failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

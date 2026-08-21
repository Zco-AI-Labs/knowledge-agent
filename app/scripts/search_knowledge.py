import logging
import os
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
    top_k: int = 10
) -> dict:
    """
    Searches the hub's private knowledge base for factual grounding context.
    Executes a 2-Stage Multi-Tenant Cloud Firestore Vector Search:
    - Stage 1: Fetches a wide candidate net (20 chunks) for catalog-wide visibility.
    - Stage 2: Applies in-flight document diversity & deduplication (max 2 chunks per page)
      before synthesizing into LLM context.
    Automatic fallback to the Vertex AI Sharded RAG Corpus if needed.

    Args:
        query: The semantic search query or question to ground against the knowledge base.
        top_k: Maximum number of relevant diverse chunks to retrieve (default: 10).

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

    logger.info(f"[knowledge_agent] search_knowledge (2-Stage) called for hub_id='{hub_id}', org_id='{org_id}', query='{query}'")

    project_id = os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT") or "hubscape-geap"
    location = os.environ.get("REGION", "us-central1")

    # Read platform settings to determine primary vs fallback mode
    rag_provider = "FIRESTORE_VECTOR"
    shards = []
    corpus_id = None
    try:
        platform_ref = db_client.collection('settings').document('platform')
        platform_snap = await asyncio.to_thread(platform_ref.get)
        if platform_snap.exists:
            platform_data = platform_snap.to_dict() or {}
            rag_provider = platform_data.get("rag_provider", "FIRESTORE_VECTOR")
            shards = platform_data.get("rag_corpus_shards") or []
            corpus_id = platform_data.get("rag_corpus_id")
    except Exception as pe:
        logger.debug(f"[knowledge_agent] Notice reading platform settings: {pe}")

    # =========================================================================
    # 1. PRIMARY ENGINE: 2-STAGE CLOUD FIRESTORE VECTOR SEARCH (20 -> Top 10 Diverse)
    # =========================================================================
    if rag_provider == "FIRESTORE_VECTOR":
        try:
            logger.info(f"[knowledge_agent] [Primary] Executing 2-Stage Firestore Vector Search (20-candidate net) for hub '{hub_id}'...")
            
            # Generate query embedding via Vertex AI text-embedding-005
            def _get_query_embedding():
                vertexai.init(project=project_id, location=location)
                model = TextEmbeddingModel.from_pretrained("text-embedding-005")
                input_item = TextEmbeddingInput(text=query.strip(), task_type="RETRIEVAL_QUERY")
                embeddings = model.get_embeddings([input_item], output_dimensionality=768)
                return embeddings[0].values

            query_embedding = await asyncio.to_thread(_get_query_embedding)
            query_vector = Vector(query_embedding)

            # Stage 1: Query Firestore with wide 20-chunk candidate net
            coll_ref = db_client.collection("rag_knowledge_chunks")
            vector_query = coll_ref
            if hub_id:
                vector_query = vector_query.where(filter=FieldFilter("hubId", "==", hub_id))
            elif org_id:
                vector_query = vector_query.where(filter=FieldFilter("orgId", "==", org_id))

            candidate_fetch_limit = max(20, top_k * 2)
            vector_query = vector_query.find_nearest(
                vector_field="embedding",
                query_vector=query_vector,
                distance_measure=DistanceMeasure.COSINE,
                limit=candidate_fetch_limit
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
                        "parentDocId": data.get("parentDocId"),
                        "chunkId": s.id
                    })

                # Stage 2: In-flight Document Diversity Reranker (max 2 chunks per unique URL/Doc)
                filtered_results = []
                doc_counts = {}
                for item in raw_candidates:
                    doc_key = item["url"] or item["parentDocId"] or item["title"] or item["chunkId"]
                    current_count = doc_counts.get(doc_key, 0)
                    if current_count >= 2:
                        continue
                    doc_counts[doc_key] = current_count + 1
                    filtered_results.append(item)
                    if len(filtered_results) >= top_k:
                        break

                logger.info(f"[knowledge_agent] ✅ [Primary] 2-Stage Filter selected {len(filtered_results)} high-signal chunks across {len(doc_counts)} distinct pages.")

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
                            "candidateCount": len(raw_candidates),
                            "resultCount": len(filtered_results),
                            "distinctSources": len(doc_counts),
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
                for idx, r in enumerate(filtered_results):
                    formatted_result += f"--- Result {idx+1}: {r['title']} ---\n"
                    if r['url']:
                        formatted_result += f"Source URL: {r['url']}\n"
                    formatted_result += f"{r['content']}\n\n"

                return {"status": "success", "result": formatted_result.strip()}

            logger.info("[knowledge_agent] [Primary] 0 results in Firestore chunks. Checking Vertex fallback...")
        except Exception as ve:
            logger.warning(f"[knowledge_agent] ⚠️ [Primary] Firestore Vector search error ({ve}). Engaging fallback...")

    # =========================================================================
    # 2. STANDBY FALLBACK: VERTEX AI SHARDED RAG CORPUS
    # =========================================================================
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
        doc_counts = {}
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
                        doc_meta = {
                            'ownerId': path_hub_id,
                            'title': context_item.source_display_name or "Uploaded Document",
                            'sourceUrl': context_item.source_uri
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

            # Diversity filter for fallback branch (max 2 chunks per parent document)
            doc_key = doc_meta.get('sourceUrl') or doc_meta.get('url') or doc_meta.get('id') or fid
            if doc_counts.get(doc_key, 0) >= 2:
                continue
            doc_counts[doc_key] = doc_counts.get(doc_key, 0) + 1

            results.append({
                "title": doc_meta.get('title') or context_item.source_display_name or "Grounded Document",
                "content": context_item.text,
                "url": doc_meta.get('sourceUrl') or doc_meta.get('url') or context_item.source_uri
            })

            if len(results) >= top_k:
                break

        if not results:
            return {"status": "success", "result": "No relevant search results found."}

        formatted_result = ""
        for idx, r in enumerate(results):
            formatted_result += f"--- Result {idx+1}: {r['title']} ---\n"
            if r['url']:
                formatted_result += f"Source URL: {r['url']}\n"
            formatted_result += f"{r['content']}\n\n"

        return {"status": "success", "result": formatted_result.strip()}

    except Exception as e:
        logger.error(f"[knowledge_agent] Fallback Vertex search failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

import logging
import asyncio
import os
from google.cloud import aiplatform_v1beta1
import hubscape_adk

logger = logging.getLogger(__name__)

async def search_knowledge(query: str) -> dict:
    """Searches the Hubscape internal Shared RAG Corpus for answers matching a query.

    Args:
        query: The search query to look up.
    """
    context = hubscape_adk.get_context()
    logger.info(f"[knowledge_agent] Executing knowledge search: query='{query}'")

    hub_id = context.auth.hub_id
    org_id = context.auth.org_id
    
    if not hub_id or not org_id:
        return {"status": "error", "message": "No Hub ID or Org ID found in context."}

    try:
        # Get shared corpus ID from settings/platform
        db_client = context._db_client
        platform_ref = db_client.collection('settings').document('platform')
        platform_snap = await asyncio.to_thread(platform_ref.get)
        
        corpus_id = None
        if platform_snap.exists:
            corpus_id = (platform_snap.to_dict() or {}).get("rag_corpus_id")
            
        if not corpus_id:
            return {"status": "error", "message": "Shared RAG Corpus is not configured on the platform."}

        location = os.environ.get("REGION", "us-central1")
        project_id = os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT") or "hubscape-geap"
        
        from google.api_core.client_options import ClientOptions
        client_options = ClientOptions(api_endpoint=f"{location}-aiplatform.googleapis.com")
        client = aiplatform_v1beta1.VertexRagServiceClient(client_options=client_options)
        
        # Serverless RAG does not support query-time metadata filtering.
        # We query globally with an increased candidate limit and filter post-retrieval.
        candidate_limit = 20
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
        
        response = await asyncio.to_thread(
            client.retrieve_contexts,
            request=request
        )
        
        # 1. Collect file IDs from contexts
        file_ids = []
        for context_item in response.contexts.contexts:
            if hasattr(context_item, 'chunk') and context_item.chunk:
                fid = getattr(context_item.chunk, 'file_id', '')
                if fid:
                    file_ids.append(fid)
                    
        # 2. Batch-query Firestore to resolve document metadata and verify tenant ownership
        registry_map = {}
        if file_ids:
            corpus_id_num = corpus_id.split('/')[-1]
            full_ids = [
                f"projects/{project_id}/locations/{location}/ragCorpora/{corpus_id_num}/ragFiles/{fid}"
                for fid in set(file_ids)
            ]
            
            chunked_ids = [full_ids[i:i + 30] for i in range(0, len(full_ids), 30)]
            for batch in chunked_ids:
                registry_docs = await asyncio.to_thread(
                    lambda: db_client.collection('rag_knowledge').where('ragFileId', 'in', batch).get()
                )
                for rdoc in registry_docs:
                    rdata = rdoc.to_dict()
                    fid = rdata.get('ragFileId', '').split('/')[-1]
                    if fid:
                        registry_map[fid] = rdata
                        
        # 3. Apply post-retrieval filtering and enrich results
        results = []
        for context_item in response.contexts.contexts:
            fid = ""
            if hasattr(context_item, 'chunk') and context_item.chunk:
                fid = getattr(context_item.chunk, 'file_id', '')
                
            doc_meta = registry_map.get(fid, {})
            
            # Tenant isolation check:
            # A document is allowed if it is platform-wide (platform_host) or matches target tenant scope
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
                "url": doc_meta.get('sourceUrl') or doc_meta.get('url') or context_item.source_uri
            })
            
            # Retrieve up to 5 results
            if len(results) >= 5:
                break
                
        # Format the result nicely as text or list
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
        logger.error(f"[knowledge_agent] search_knowledge failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

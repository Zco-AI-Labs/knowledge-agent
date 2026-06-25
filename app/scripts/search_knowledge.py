import logging
import asyncio
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

        # Build CEL metadata filter
        cel_filter = f'metadata.orgId == "{org_id}" && metadata.hubId == "{hub_id}"'
        
        client = aiplatform_v1beta1.VertexRagServiceClient()
        
        filter_config = aiplatform_v1beta1.types.RagRetrievalConfig.Filter(
            metadata_filter=cel_filter
        )
        
        retrieval_config = aiplatform_v1beta1.types.RagRetrievalConfig(
            filter=filter_config
        )
        
        query_obj = aiplatform_v1beta1.types.RagQuery(
            text=query,
            similarity_top_k=5,
            rag_retrieval_config=retrieval_config
        )
        
        response = await asyncio.to_thread(
            client.retrieve_contexts,
            parent=corpus_id,
            query=query_obj
        )
        
        results = []
        for context_item in response.contexts.contexts:
            results.append({
                "title": context_item.source_display_name or "Grounded Document",
                "content": context_item.text,
                "url": context_item.source_uri
            })
            
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

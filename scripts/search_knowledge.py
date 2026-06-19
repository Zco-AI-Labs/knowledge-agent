import logging
import asyncio
from services.discovery import DiscoveryService
import hubscape_adk

logger = logging.getLogger(__name__)

async def search_knowledge(query: str) -> dict:
    """Searches the Hubscape internal database/knowledge base for answers matching a query.

    Args:
        query: The search query to look up.
    """
    context = hubscape_adk.get_context()
    logger.info(f"[knowledge_agent] Executing knowledge search: query='{query}'")

    hub_id = context.auth.hub_id
    if not hub_id:
        return {"status": "error", "message": "No Hub ID found in context."}

    try:
        result_text = await asyncio.to_thread(
            DiscoveryService.rag_search, hub_id, query, hub_data=None, user_id=context.auth.uid
        )
        return {"status": "success", "result": result_text}
    except Exception as e:
        logger.error(f"[knowledge_agent] search_knowledge failed: {e}")
        return {"status": "error", "message": str(e)}

import logging
from services.host_core.tools.impl.discovery import DiscoveryTools
import hubscape_adk

logger = logging.getLogger(__name__)

async def find_hubs(query: str) -> dict:
    """Searches the Hubscape platform for Hubs matching a user query (e.g. 'find a pizza place', 'find a dentist'). Directly executes the search and returns results.

    Args:
        query: The search query from the user (e.g. 'pizza', 'dentist near me').
    """
    context = hubscape_adk.get_context()
    logger.info(f"[knowledge_agent] Executing hub search: query='{query}'")

    # Build the context dict DiscoveryTools.find_hubs expects
    tool_context = {
        "userId": context.auth.get_user_id() if context.auth else None,
        "clientContext": {}
    }

    result = await DiscoveryTools.find_hubs({"query": query}, tool_context)

    if result.get("error"):
        return {
            "status": "error",
            "message": f"I had trouble searching for hubs: {result['error']}"
        }

    return {
        "status": "success",
        "message": result.get("result", "Here are the hubs I found."),
        "system_action": result.get("system_action")
    }

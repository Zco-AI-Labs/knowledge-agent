import logging
from typing import List
import hubscape_adk

logger = logging.getLogger(__name__)

@hubscape_adk.require_tool_privilege
def suggest_queries(queries: List[str]) -> dict:
    """Shows the user a list of suggested options or choices in the UI when a query is ambiguous.

    Args:
        queries: The list of suggested queries or choices to show.
    """
    logger.info(f"[knowledge_agent] Suggesting queries: {queries}")
    context = hubscape_adk.get_context()
    context.actions.append({
        "type": "SET_SUGGESTIONS",
        "queries": queries
    })
    return {
        "status": "success",
        "message": f"Suggested options presented: {queries}"
    }

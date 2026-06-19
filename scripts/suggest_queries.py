import logging
from typing import List
import hubscape_adk

logger = logging.getLogger(__name__)

def suggest_queries(queries: List[str]) -> dict:
    """Shows the user a list of suggested options or choices in the UI when a query is ambiguous.

    Args:
        queries: The list of suggested queries or choices to show.
    """
    logger.info(f"[knowledge_agent] Suggesting queries: {queries}")
    return {
        "status": "success",
        "message": "Here are some options to help clarify your request:",
        "system_action": {
            "type": "SUGGEST_QUERIES",
            "queries": queries
        }
    }

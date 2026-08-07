# Chapter 8: Advanced Integrations: MCP, A2A, & Secrets

This chapter outlines how custom agents communicate with third-party tools (MCP), interface with other agents (A2A), and access encrypted capabilities and secrets safely.

---

## 1. Model Context Protocol (MCP) Integration

The ADK allows agents to interact with external tools hosted on remote MCP servers (e.g. Jira, GitHub, databases) via Server-Sent Events (SSE). 

### Setup and Configuration

To register a remote MCP server, define its connection endpoint inside [config.json](file:///Users/rajvekeria/Documents/GitHub/hubscape-agent-template/config.json). You can pass authorization tokens and secrets dynamically using placeholder syntax (e.g., `${OAUTH_TOKEN:provider}` or `${SECRET_NAME}`):

```json
{
  "mcp_servers": {
    "github_mcp": {
      "url": "https://github-mcp-proxy-w3xi4ozhca-uc.a.run.app/mcp",
      "headers": {
        "Authorization": "Bearer ${OAUTH_TOKEN:github}"
      },
      "timeout": 15
    }
  }
}
```

### How it Works

1. **Static Loading:** At boot time, [app/agent.py](file:///Users/rajvekeria/Documents/GitHub/hubscape-agent-template/app/agent.py) reads the `mcp_servers` configuration block, instantiates a native `McpToolset` for each server, and registers them inside the `AdkAgent`'s tools list.
2. **Dynamic OAuth Resolution:** During request execution (in `geap_agent_wrapper.py` or `agent_runtime_app.py`), the wrapper automatically resolves token placeholders (like `${OAUTH_TOKEN:github}`) by calling `await context.get_oauth_token("github")`, injecting the active user credentials into the connection headers.
3. **Access Control Filtering:** The host platform can restrict access to specific MCP tools by sending a whitelist under `accessible_tools` in the request metadata. The wrapper applies this whitelist directly to the toolset's `tool_filter` to ensure the agent only uses approved capabilities.


---

## 2. Agent-to-Agent (A2A) Connections

A2A allows sub-agents to discover and delegate queries to other agents. An agent acts as both a **client** (making outbound requests) and a **server** (accepting inbound requests).

### Inbound A2A server endpoints:
The FastAPI server automatically mounts an inbound JSON-RPC route `/a2a/{agent_name}` using the helper `attach_a2a_routes()` defined in `[app/app_utils/a2a.py](file:///Users/rajvekeria/Documents/GitHub/hubscape-agent-template/app/app_utils/a2a.py)`. The platform invokes this route when delegating user requests.

### Data Isolation & Whitelisting:
To prevent unauthorized cross-tenant communication:
1. Discovery and consulting operations must work **solely** within the `accessible_agents` list injected into the context at runtime.
2. If an agent tries to call an external tool on an agent not listed in `accessible_agents`, the request must fail immediately.

### Executing Outbound A2A Calls:
Use the standard context agents wrapper to query another agent:
```python
# app/scripts/consult_support.py
from app.core.hubscape_adk import get_context

async def consult_support(user_query: str) -> dict:
    context = get_context()
    
    # Delegate standard tool calling
    result = await context.agents.call_external_tool(
        ext_agent_key="support_ticket_agent",
        tool_name="file_ticket",
        arguments={"issue": user_query}
    )
    return result
```

---

## 3. Platform Secrets Vault

Never hardcode credentials or secrets inside repository files.
* **Secrets Retrieval:** Secure keys are injected into the agent context dynamically. Retrieve secrets using the context raw config:
  ```python
  api_key = context.raw_context.get("secrets", {}).get("API_SECRET_KEY") or os.environ.get("API_SECRET_KEY")
  ```
  This ensures compatibility with both the cloud environment secrets vault and local `.env` mock configuration keys.

---

[Next Chapter: GEAP Developer Workflow](CHAPTER_9_GEAP_DEVELOPER_WORKFLOW.md) | [Previous Chapter: OAuth Integration & Hubscape ADK API](CHAPTER_7_OAUTH_INTEGRATION_AND_ADK_API.md)

---
name: ADK Expert
description: Expert at building, modifying, and understanding Hubscape Modular Agents using the Agent Development Kit (ADK).
---

# ADK Expert Skill

You are the Hubscape ADK Integration Specialist. Your primary mission is to assist the Captain in building, testing, and scaling custom Modular AI Agents using the Hubscape Agent Development Kit.

## 🛡️ The Prime Directive: Sandboxing
> [!CAUTION]
> **STAY IN THE SANDBOX**: You are strictly prohibited from modifying core platform files when tasked with building a new agent. All agent package code, logic, configuration, and API routes MUST be contained entirely within `app/`.

## 📖 Mandatory Reference
Before building or modifying any agent, you MUST review the official ADK documentation:
1. [ADK_MANUAL.md](file://docs/ADK_MANUAL.md) - The complete architecture, lifecycle, and rulebook for modular agents.
2. [UI_ELEMENTS.md](file://docs/UI_ELEMENTS.md) - The official catalog of supported Lego UI elements, properties, and layouts.

## 📐 The Architecture of a Hubscape Agent
Every agent is structured as a Python package inside the `app/` directory:

1. **`app/agent.py` (Required)**: Entry point that instantiates `google.adk.agents.Agent` and registers tools. Configure agent name and description here.
2. **`app/SKILL.md` (Required)**: Defines the system instructions.
3. **`app/scripts/` (Required)**: Python scripts implementing individual tool handlers.
4. **`pyproject.toml` (Required)**: Package dependencies and python configurations.
   - **Automated Configuration Naming Sync:** You only need to set the `name` argument of `AdkAgent` in `app/agent.py`. The deployment script (`deploy.py`) automatically synchronizes this name across all static configuration files (manifests, packaging, lockfiles, Skill files, and Terraform configurations) during deployment.

5. **`app/__init__.py` (Required)**: Exposes the app singleton:
   ```python
   from .agent import app
   __all__ = ["app"]
   ```



## 🔑 Context Object Reference (`HubscapeContext` / `ToolContext`)

When writing tools in `tools.py`, you can receive the platform context directly:

### Standard Tool Signature
```python
async def my_tool(tool_context: ToolContext, arg1: str) -> dict:
    """
    Description of what my_tool does.
    
    Args:
        arg1: Description of parameter.
    """
    user_id = tool_context.auth.get_user_id()
    # Execute logic...
```

### Context Helpers

| Property / Method | Description |
|---|---|
| `context.auth.get_user_id()` | The user's platform UUID. |
| `context.auth.name` | User's display name. |
| `context.auth.org_id` | The Organization UUID. Never derive this from a DB lookup. |
| `context.auth.hub_id` | The Hub UUID (may be `None` if org-level). |
| `context.auth.has_permission(capability_id)` | Returns `True` if authorized (Hub Admins always bypass). |
| `context.get_agent_secret(secret_name)` | Resolves a KMS vaulted secret, falling back to `.env` locally. |
| `context.invoke_agent(agent_id, query)` | Programmatically delegates a task to another agent. |
| `context.client.has_ui` | `True` if client supports visual custom widgets. |

### Database Helpers
Always prefer using the high-level Firestore scope CRUD helpers:
* `context.save_agent_data(scope: str, collection_name: str, doc_id: str, data: dict) -> dict`: Automatically injects auditing metadata and merges data.
* `context.get_agent_data(scope: str, collection_name: str, doc_id: str) -> Optional[dict]`
* `context.delete_agent_data(scope: str, collection_name: str, doc_id: str)`
* `context.list_agent_data(scope: str, collection_name: str) -> list[dict]`



## 🎨 Generative UI & Dynamic Widgets
* **Predefined Widget Templates:** Loaded from the agent's `widgets/` folder using `await context.show_widget(widget_template_id, data)`.
* **Generative Custom UIs:** Built dynamically on the fly using `await context.show_custom_ui(layout, data)`.
* **Standard Response Wrapper:** Wrap response payloads from action callback endpoints using `make_widget_response(context)` to prevent browser exceptions.
* **IFrame Placeholders:** Always use `/api/agents/{{agent_id}}/static/...` for iframe source paths and `/api/plugins/{{agent_id}}/` for API endpoints inside layouts.

---

## 🔌 Model Context Protocol (MCP) & Agent-to-Agent (A2A) Connections
* **Programmatic MCP Calls:** Invoke using the context client:
  ```python
  await context.mcp.call_tool(
      agent_id=context.auth.agent_id,
      server_name="server_key",
      tool_name="tool_name",
      arguments=arguments,
      config=mcp_config,
      context=context
  )
  ```
* **Programmatic A2A Calls:** Invoke using `context.agents`:
  ```python
  result = await context.agents.call_external_tool(
      ext_agent_key="salesforce_copilot",
      tool_name="get_lead_details",
      arguments=arguments
  )
  ```

---

## ✅ Development Workflow

1. **Scaffold**: Initialize a new agent directory: `hubscape-adk init <agent_id>`. This scaffolds the package structure, including `agent.py`, `prompt.py`, `tools.py`, and `pyproject.toml`.
2. **Implement**: Define tool functions in `tools.py` and import/register them in `agent.py`. Add system instructions to `prompt.py`.
3. **API Routing**: If endpoints are required, define FastAPI routes in `api.py`.
4. **Test**: Use the Holodeck console at `http://localhost:8090` to test tools, conversational routing, and permissions.

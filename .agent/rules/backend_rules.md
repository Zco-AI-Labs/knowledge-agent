# Backend Rules: Custom Agent Coding Standards

> [!NOTE]
> These guidelines ensure that agent logic behaves predictably and integrates safely with the Hubscape host platform under the google-adk declarative structure.

## 1. Two-Route API Schema (`api.py`)
* Custom REST endpoints mounted inside the package in `api.py` MUST follow the two-route system:
  * **Dynamic POST/GET requests** (like webhook callbacks or form actions) must target:
    `/api/plugins/{agent_id}/{endpoint_name}`
  * **Static asset requests** (like rendering iframes or loading local HTML/CSS/images) must target:
    `/api/agents/{agent_id}/static/{asset_name}`

## 2. Tools & Prompts Implementation
* **Tools in `tools.py`:** Define all custom tools as Python functions inside the package's `tools.py` file. The parameter schemas and descriptions are derived dynamically by the ADK from Python type hints and docstrings.
* **Tool Registration:** Import and register these tools in `agent.py`'s `Agent` constructor:
  ```python
  from google.adk.agents import Agent
  from .tools import my_tool
  
  root_agent = Agent(
      ...,
      tools=[my_tool]
  )
  ```
* **System Prompts in `prompt.py`:** Define the agent's instructions (prompts) inside `prompt.py` and import/assign them to `Agent(instruction=...)` in `agent.py`.
* **Role Gating:** Enforce security gates inside tool functions using `context.auth.has_permission`:
  ```python
  async def admin_only_tool(tool_context: ToolContext, arg1: str):
      if not tool_context.auth.has_permission("admin_only_tool"):
          return {"status": "error", "message": "Unauthorized"}
  ```

## 3. Package File Encapsulation
* All execution routes, prompts, and tool handlers belong strictly within the agent's package folder (e.g. `agents/temp_agent/`). Avoid placing business logic at the root level of the workspace.

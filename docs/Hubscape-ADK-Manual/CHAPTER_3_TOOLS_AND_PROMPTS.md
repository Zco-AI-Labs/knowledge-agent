# Chapter 3: Tool Scripts & Prompt Structure

This chapter covers how the ADK parses system instructions (prompts) and dynamically constructs LLM tool schemas from standalone Python functions.

---

## 1. Defining System Instructions (`app/SKILL.md`)

System instructions (the agent's persona and rules) are housed inside the markdown file [app/SKILL.md](file:///Users/rajvekeria/Documents/GitHub/hubscape-agent-template/app/SKILL.md).

* **YAML Frontmatter:** The top of the file contains configurations (name, description) that identify the agent:
  ```markdown
  ---
  name: todo_agent
  description: Manages user tasks and schedules.
  ---
  You are a highly efficient to-do list manager...
  ```
* **Strict Validation Enforcement:** The agent loader `[app/agent.py](file:///Users/rajvekeria/Documents/GitHub/hubscape-agent-template/app/agent.py)` parses `SKILL.md` at boot time. If `SKILL.md` is missing, it raises a `FileNotFoundError`. If the YAML frontmatter delimiters (`---`) or required fields (`name`, `description`) are missing, it raises a `ValueError`.
* **Auto-Scrubbing:** The loader automatically strips the YAML frontmatter and passes only the remaining markdown instructions directly to the `instruction` property of the `google.adk.Agent` instance.
* **Packaging Requirement:** Because `SKILL.md` is parsed dynamically at runtime, it must be bundled inside the deployed wheel package. This is enforced by configuring force-includes under `[tool.hatch.build.targets.wheel.force-include]` in `[pyproject.toml](file:///Users/rajvekeria/Documents/GitHub/hubscape-agent-template/pyproject.toml)`:
  ```toml
  [tool.hatch.build.targets.wheel.force-include]
  "app/privileges.json" = "app/privileges.json"
  "app/SKILL.md" = "app/SKILL.md"
  ```

---

## 2. Implementing Standalone Tool Scripts (`app/scripts/`)

Tools are written as individual, standalone Python files in the `app/scripts/` directory. 

* **Signatures & Schemas:** The function name inside the script must match the filename (e.g., `app/scripts/create_todo.py` must define `async def create_todo(...)`). The ADK automatically parses parameter types, defaults, and docstrings to construct the JSON tool schemas passed to Gemini.
* **Context Handling:** Do not pass the `context` parameter in the tool's function arguments signature. Instead, import and call `get_context()` inside the function body. This keeps the schema definition passed to Gemini clean and free from metadata.
* **No Manual RemoteContext Instantiation:** Do **not** manually instantiate `RemoteContext(...)` or hardcode fallback credentials (e.g., `user_id="dev-user-123"`) inside your tool script body. Tools must rely purely on the active context retrieved via `get_context()`. Manual instantiation bypasses session routing, breaks dynamic multi-user database scoping, and crashes in production where credential-less connections are blocked.

### Example Tool implementation:
```python
# app/scripts/create_todo.py
import logging
from app.core.hubscape_adk import get_context

logger = logging.getLogger(__name__)

async def create_todo(task_title: str, priority: str = "medium") -> dict:
    """
    Creates a new task in the user's to-do list.

    Args:
        task_title: The title/content of the task.
        priority: The priority level ('high', 'medium', 'low').
    """
    logger.info(f"Adding task: {task_title}")
    context = get_context()
    
    # Standard DB save
    result = context.save(
        scope="user",
        collection_name="tasks",
        doc_id=f"task_{task_title}",
        data={"title": task_title, "priority": priority}
    )
    return {"status": "success", "task": result}
```

---

## 3. Decommissioning of Inbound API Routes (`api.py`)

GEAP and sandboxed ADK containers run in secure isolated environments. **Inbound HTTP servers (`api.py`) are fully decommissioned.** Custom inbound routing (like custom web routers or Webhook listeners inside the agent) is not supported.

* **OAuth & Webhooks:** If you need to handle OAuth redirects or external callbacks, route them to the central platform backend. The backend processes the events and saves tokens/data into Firestore scopes.
* **Querying State:** The agent then reads this state from the database at runtime using the scoped database client.
* **Outbound Connections:** Outbound HTTP client calls (using `httpx` or similar) are fully supported. Always set strict timeout controls.

---

## 4. Workspace Scope & Tool Filtering (`@tool_scope`)

To enforce secure routing and minimize model context overhead, the Hubscape ADK filters which tools are exposed to Gemini at runtime using workspace scope annotations and user privilege checks.

### The `@tool_scope` Decorator:
By default, all tools registered in `app/scripts/` are available in both Hub and Organization scopes. To restrict a tool to specific workspace scopes, decorate your tool function with `@tool_scope` from `app.core.hubscape_adk`:

* **`"hub"` scope:** Only accessible if the agent is operating inside a Hub (workspace) session.
* **`"org"` scope:** Only accessible if the agent is operating inside a global Organization/Platform session.

#### Example Usage:
```python
# app/scripts/manage_hub_settings.py
from app.core.hubscape_adk import get_context, tool_scope

@tool_scope(["hub"])
async def manage_hub_settings(setting_key: str, setting_value: str) -> dict:
    """
    Modifies configuration parameters specific to the active Hub.

    Args:
        setting_key: The configuration option key.
        setting_value: The value to configure.
    """
    context = get_context()
    # This tool is guaranteed to only run inside a Hub scope context
    ...
```

### Internal Plumbing (`filter_tools_for_scope`):
Behind the scenes, when the agent is invoked via the REST API, A2A endpoint, or Vertex AI, the framework calls `filter_tools_for_scope()`. This helper:
1. Clones the agent instance.
2. Checks the active scope and strips out any tools decorated with `@tool_scope` if the active scope does not match.
3. Checks the user's active role privileges (from `privileges.json`) and restricts the remaining tools list to only those the user is authorized to execute.

---

[Next Chapter: RemoteContext, Scopes, and File Storage](CHAPTER_4_REMOTE_CONTEXT_AND_DATABASE.md) | [Previous Chapter: Directory Specification](CHAPTER_2_DIRECTORY_SPECIFICATION.md)


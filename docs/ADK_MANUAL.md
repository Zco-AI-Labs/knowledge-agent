# Hubscape Custom ADK (Agent Development Kit) Manual

> [!IMPORTANT]
> **AI AGENT DIRECTIVE:** If you are an AI reading this document, you are being tasked with building or modifying a Hubscape Modular Agent. You must adhere to the sandboxing rules outlined here. All agent package code, logic, and custom routes must be contained within the `/plugins/agents/<agent_id>/` (locally `/agents/<agent_id>/`) directory.

## 1. Introduction to the ADK

The Hubscape Modular ADK allows developers and AI assistants to quickly build, deploy, and scale custom AI agents using a package-based declarative python framework.

### The Agent Lifecycle
1. **Discovery:** On boot, the platform loader scans the registered agents directory for configuration and initialization submodules.
2. **Identity Injection:** The agent's name and description (defined in `agent.py`) are automatically appended to the Hubscape Host Persona's prompt.
3. **Delegation:** When a user asks the Host to perform a task suited for your agent, the Host routes the query to your agent.
4. **Execution:** The engine boots your agent package, runs your system prompt configuration (`prompt.py`), and allows your agent's LLM to invoke the tools defined in your Python functions (`tools.py`).

---

## 2. Directory Structure

A complete Hubscape Agent consists of a package directory structure:

```text
my_agent_project/
├── pyproject.toml       # REQUIRED: Package dependencies and config (workspace root)
└── app/                 # REQUIRED: The agent package folder
    ├── __init__.py      # REQUIRED: Exposes the app
    ├── agent.py         # REQUIRED: Initializes the ADK Agent
    ├── SKILL.md         # REQUIRED: Defines the system instructions / prompt
    └── scripts/         # REQUIRED: Standalone Python tool scripts
```

---

## 3. The Pillars of a Declarative Agent

### Pillar 1: `SKILL.md` and `agent.py` (The Brain)

#### `SKILL.md`
Houses your system instructions. YAML frontmatter is automatically parsed and cleaned at startup.
```markdown
---
name: my_custom_agent
description: Brief summary of capabilities.
---
You are a helpful agent. Attempt to carry out user requests by calling tools.
```

#### `agent.py`
Instantiates the agent using `google.adk.Agent` and registers the tools dynamically:
```python
# agent.py
import os
import re
from google.adk import Agent as AdkAgent
from app.core.load_local_tools import load_local_tools

runtime_dir = os.path.dirname(os.path.abspath(__file__))
skill_md_path = os.path.join(runtime_dir, "SKILL.md")

with open(skill_md_path, "r", encoding="utf-8") as f:
    skill_content = f.read()
# Strip YAML frontmatter
system_instruction = re.sub(r"^---.*?---", "", skill_content, flags=re.DOTALL).strip()

# Load all tools dynamically from the scripts directory
scripts_dir = os.path.join(runtime_dir, "scripts")
tools = load_local_tools(scripts_dir)

root_agent = AdkAgent(
    name="my_custom_agent",
    model="gemini-2.5-flash",
    description="Brief summary of capabilities.",
    instruction=system_instruction,
    tools=tools
)
```

---

### Pillar 3: Tool Scripts (The Muscle)

Tools are written as individual, standalone Python files in the `app/scripts/` directory. The function name inside the script must match the filename (e.g., `app/scripts/create_event.py` contains the function `create_event`). The ADK automatically parses their signatures, docstrings, and type hints to construct Gemini tool schemas.

**Rules for Tool Scripts:**
1. Define clear docstrings describing the tool and its parameters.
2. Do **not** pass a context parameter in the function signature. Instead, retrieve the active thread-local context dynamically within the function body using `get_context()`. This keeps the schema definition passed to Gemini clean.
3. Keep logic clean and return JSON-serializable dicts.

```python
# app/scripts/create_event.py
import logging
from app.core.hubscape_adk import get_context

logger = logging.getLogger(__name__)

async def create_event(title: str, date: str) -> dict:
    """
    Creates a new calendar event.

    Args:
        title: The name/title of the event.
        date: The date format YYYY-MM-DD.
    """
    logger.info(f"Creating event: {title} on {date}")
    
    # Retrieve the thread-local context
    context = get_context()
    user_id = context.auth.get_user_id()
    
    # Save to scoped DB
    saved = context.save(
        scope="user",
        collection_name="events",
        doc_id=f"evt_{title}",
        data={"title": title, "date": date}
    )
    
    return {"status": "success", "event": saved}
```

---

### Pillar 4: Inbound API Routes (Decommissioned)

GEAP agents run in sandboxed cloud containers and do not support public inbound HTTP routes (`api.py`). Any webhook, callback, or OAuth redirect must be routed directly to the central platform backend, which writes to Firestore for the agent to query via `hubscape_adk.py`.

---

## 4. Understanding the `RemoteContext`

The context object is your gateway to the platform's state, authentication, database, and UI systems. You retrieve it via `get_context()` inside your tool implementations.

### `context.auth` (Authentication)
*   `context.auth.get_user_id()`: Returns the unique UUID of the active user.
*   `context.auth.org_id`: The Organization UUID (always available).
*   `context.auth.hub_id`: The Hub UUID (may be `None` if org-level).

*(Note: `context.auth.name` is currently under development and not yet available on the python context object).*

### Session Modality & Configuration Checks
To adapt functionality dynamically based on client configuration, check values in `context.raw_context`:
*   `context.raw_context.get("mode")`: The interface mode, e.g., `"chat_pc"`, `"sms"`, `"voice_call"`.
*   `context.allow_generative_ui`: Boolean flag indicating whether the agent is allowed to output custom generative widgets at runtime.

### Standardized Database Scopes & Helpers
Firestore paths are automatically resolved by ADK context helpers based on the scope:
*   **`user` Scope:** `platform_users/{user_id}/agent_data/{agent_id}/{collection_name}/`
*   **`hub` Scope:** `organizations/{org_id}/hubs/{hub_id}/agent_data/{agent_id}/{collection_name}/`
*   **`org` Scope:** `organizations/{org_id}/agent_data/{agent_id}/{collection_name}/`
*   **`platform` Scope:** `agents/{agent_id}/agent_data/platform/{collection_name}/`

#### CRUD Helpers on `RemoteContext`:
*   `context.save(scope, collection_name, doc_id, data)`: Saves/merges data and automatically manages audit metadata (`created_by`, `created_at`, `updated_by`, `updated_at`) and increments `version`.
*   `context.get(scope, collection_name, doc_id)`: Retrieves a document.
*   `context.delete(scope, collection_name, doc_id)`: Deletes a document.
*   `context.list(scope, collection_name)`: Retrieves all documents in the collection.

---

## 5. Development Workflow (Step-by-Step)

1. **Scaffold Package:** Clone the template repository or run `hubscape-adk clone <repo-url>`.
2. **Implement Tools:** Add standalone tool files inside `app/scripts/`. Register the instructions inside `app/SKILL.md`.
3. **Configure Database & Context:** Retrieve the active `RemoteContext` using `get_context()` inside your script tools to perform CRUD operations.
4. **Boot Sandbox:** Execute `hubscape-adk` in the root folder to launch the local Holodeck at `http://localhost:8090`.
5. **Simulate & Verify:** Talk to the mock Host AI, trigger tools, verify mock database operations, and inspect logs in the Holodeck dashboard.



## 7. Model Context Protocol (MCP) & Agent-to-Agent (A2A) Connections

### Programmatic MCP calling in `tools.py`
```python
mcp_result = await context.mcp.call_tool(
    agent_id=context.auth.agent_id,
    server_name="jira_mcp",
    tool_name="create_ticket",
    arguments={"summary": "Fix bugs"},
    config=mcp_config,
    context=context
)
```

### Programmatic A2A calling in `tools.py`
```python
result = await context.agents.call_external_tool(
    ext_agent_key="salesforce_copilot",
    tool_name="get_lead_details",
    arguments={"lead_id": lead_id}
)
```

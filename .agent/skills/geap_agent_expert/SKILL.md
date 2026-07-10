---
name: GEAP Agent Expert
description: Expert at building, modifying, and understanding GEAP (Gemini Enterprise Agent Platform) agents based on Vertex AI Reasoning Engines.
---

# GEAP Agent Expert Skill

You are the Hubscape GEAP Integration Specialist. Your primary mission is to assist the Captain in building, deploying, and scaling custom specialized AI agents as cloud-native Vertex AI Reasoning Engines under the Gemini Enterprise Agent Platform (GEAP).

> [!IMPORTANT]
> **DIRECTORY STRUCTURE MANDATE:**
> When tasked with creating, designing, or modifying an agent, you must always use the segregated, decoupled directory layout. All prompt instructions, tools, and code must follow this standard.

---

## 🏛️ Decoupled Cloud-Native Architecture
Hubscape has transitioned fully to a cloud-native model:
1. **No Local Agent Execution:** The Python backend (`backend_python`) is decoupled from agent execution and acts purely as a secure proxy relay. It does not run local agent loops or store agent code folders.
2. **Vertex AI Reasoning Engines:** Specialized agents are developed in separate, standalone repositories under `/Users/seanneubert/Documents/Projects/core-agents/` and deployed to Vertex AI in Google Cloud.
3. **API Proxy Relay:** When a user chats with an agent, the backend resolves the agent's remote resource path (from a Whitelist stored in Firestore), builds a structured context payload, and queries the remote GEAP agent via HTTP REST POST.

---

## 📦 Directory Structure & Layout Options

We use a segregated, decoupled directory layout (the staged standard) for setting up and creating agents. Prompts are kept in a clean markdown file (`SKILL.md`), and tools are separated into single-purpose scripts within the `scripts/` directory under `app/`.

```text
my-agent/
├── agents-cli-manifest.yaml # REQUIRED: agents-cli manifest
├── deploy.py               # REQUIRED: Subprocess wrapper to run agents-cli deploy
├── pyproject.toml          # REQUIRED: uv dependency manager configuration
└── app/                    # REQUIRED: Agent directory containing python code
    ├── __init__.py         # REQUIRED: Package initialization
    ├── agent.py            # REQUIRED: Main agent class conforming to Vertex AI Reasoning Engine SDK
    ├── agent_runtime_app.py # REQUIRED: Entry point loaded by Agent Runtime
    ├── hubscape_adk.py     # REQUIRED: Lightweight context/DB adapter (copied verbatim)
    ├── SKILL.md            # REQUIRED: YAML identity metadata + Markdown system instructions
    ├── scripts/            # REQUIRED: Python function tools (no __init__.py)
    │   ├── tool_one.py     # Implementation of tool_one
    │   └── tool_two.py     # Implementation of tool_two
    ├── references/         # OPTIONAL: Static reference files/documentation read at runtime
    └── app_utils/          # REQUIRED: env_resolver and vertex_gemini helpers
```

> [std_adk]
> **SDK Choice:** You **MUST** use the `google-adk` package/SDK instead of `google-antigravity` for all GEAP agents. This enables direct local testing via the ADK CLI (`adk web` / `adk run`). Ensure that `agent.py` exposes a global `root_agent` instance using `google.adk.Agent` for the ADK CLI to load, and defines `geap_agent_wrapper` (implementing `.query(...)`) for Vertex AI Reasoning Engine compatibility.

---

## 🏛️ Agent Archetypes

We support two distinct agent archetypes under GEAP:

| Feature | **Central Host Orchestrator** (`host-agent`) | **Specialist Subagent** (`todo-agent`) |
| :--- | :--- | :--- |
| **Identity / Prompt** | Dynamic. Instructions loaded from backend context `context['system_instruction']`. | Static. Instructions loaded from local `SKILL.md` (which is REQUIRED). |
| **Output Format** | Structured JSON string: `{"text": text, "actions": actions}`. | Plain text response. |
| **State / Trajectory** | Stateful. SQLite trajectory DB is persisted/restored to Firestore on each turn. | Stateless. No session trajectory persistence. |
| **Disabled BuiltinTools** | Disables 10 BuiltinTools (including `START_SUBAGENT` and `ASK_QUESTION`). | Disables 8 BuiltinTools (retains `START_SUBAGENT` and `ASK_QUESTION`). |
| **Tool loading** | Supports camelCase fallback in `load_local_tools` for legacy tools. | Strict snake_case tool mapping only. |
| **Requirements** | No `SKILL.md` is required. | `SKILL.md` is strictly REQUIRED. |

### camelCase Tool Loading Fallback
If any script tool exports a camelCase function name (e.g., `consult_agent.py` → `consultAgent`), add a camelCase fallback to `load_local_tools` in your agent. See `host-agent/agent.py` lines 24-28 for the pattern. For subagents, stick to snake_case matching.


---

## 🧱 Lego Widget System & Asynchronous Action Routing

The Hubscape UI is consolidated around the **Lego Widget Catalog** (`DynamicWidget.tsx`). Predefined layouts and LLM-built interfaces are parsed and rendered identically using this layout catalog.

### 1. Predefined Widgets (`context.show_widget`)
Developers define static layouts in a `/widgets` folder in the agent's repository root (e.g., `widgets/task_list.json`). These JSON configurations represent structured Lego blocks.
To show a predefined widget, the agent invokes:
```python
context = hubscape_adk.get_context()
context.show_widget(widget_template_id="task_list", data={"filter": "pending"})
```
This reads `widgets/task_list.json`, resolves variables, and appends the `OPEN_AGENT_WIDGET` client action directive.

### 2. Generative UI (`context.show_custom_ui`)
The agent's LLM can dynamically compose a Lego interface dictionary block by block and output it.
To show a generative widget, the agent invokes:
```python
layout = {
    "type": "container",
    "props": {"direction": "vertical", "padding": "md"},
    "children": [
        {"type": "text", "props": {"text": "Dynamic Header", "size": "lg"}},
        {"type": "button", "props": {"label": "Proceed", "actionUrl": "agent://confirm_action"}}
    ]
}
context = hubscape_adk.get_context()
context.show_custom_ui(layout=layout, data={})
```

### 3. Generative UI Guardrails (`allowGenerativeUi`)
To prevent unauthorized code execution or layout injection, agents support the `allowGenerativeUi` guardrail flag:
* **Predefined Widgets:** Always allowed.
* **Generative UI:** Calls to `show_custom_ui` are intercepted. If `allowGenerativeUi` is `False`, the ADK raises a runtime `PermissionError` and aborts.
* **Configuration:**
  * **Configuring locally:** Add `allowGenerativeUi: false` in `SKILL.md` YAML frontmatter.
  * **Platform Override:** Add `allowGenerativeUi: false` to the agent's configuration object in the platform's Firestore `agents` collection.

### 4. The Pure Agentic Form Protocol (Option A)
Because remote GEAP containers cannot receive direct inbound HTTP POST requests, all widget interaction (button clicks, form submissions) is routed asynchronously inside the chat stream:
1. **Interactive Elements:** Buttons and form inputs in Lego layouts configure their `actionUrl` using protocols `agent://` or `chat://` (e.g. `agent://save_todo` or `chat://cancel_meeting`).
2. **Frontend Interception:** When clicked, `DynamicWidget.tsx` intercepts the `agent://` url, packages the input fields into a JSON payload, and fires a `hubscape:agent-action` DOM event.
3. **Chat Queue Relay:** `useChat.ts` captures the event and submits a silent slash command into the chat stream:
   `[Form Submit] /action {actionName} {jsonPayload}`
4. **Agent Processing:** The agent's `agent.py` receives the question. If it starts with `/action`, the agent parses the action name and JSON payload, routes it to the corresponding Python tool (e.g. `save_todo`), updates the Firestore data, and returns the updated widget config.

---


## 💻 Code Blueprints & Reference Implementations

### 1. The Main Agent (`agent.py`)
Conforms to the Vertex AI Reasoning Engine SDK, instantiating `google.adk.Agent` and handling chat sessions dynamically.

```python
import os
# Force Enterprise Mode if running in GCP environment, or if no local GEMINI_API_KEY is provided
if not os.getenv("GEMINI_API_KEY"):
    os.environ["GOOGLE_GENAI_USE_ENTERPRISE"] = "True"
import asyncio
import importlib.util
import re
import json
from google.adk import Agent as AdkAgent
from google.adk.runners import Runner
from google.genai import types

def load_local_tools(scripts_dir: str) -> list:
    tools = []
    if not os.path.exists(scripts_dir):
        return tools
    for filename in os.listdir(scripts_dir):
        if filename.endswith(".py") and not filename.startswith("_"):
            module_name = filename[:-3]
            file_path = os.path.join(scripts_dir, filename)
            try:
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    func = getattr(module, module_name, None)
                    if func and callable(func):
                        tools.append(func)
            except Exception:
                pass
    return tools

# 1. Module-level instructions and tool loading for ADK CLI
runtime_dir = os.path.dirname(os.path.abspath(__file__))
skill_md_path = os.path.join(runtime_dir, "SKILL.md")
system_instruction = "You are a highly efficient assistant."
if os.path.exists(skill_md_path):
    with open(skill_md_path, "r", encoding="utf-8") as f:
        skill_content = f.read()
    system_instruction = re.sub(r"^---.*?---", "", skill_content, flags=re.DOTALL).strip()

scripts_dir = os.path.join(runtime_dir, "scripts")
tools = load_local_tools(scripts_dir)

root_agent = AdkAgent(
    model='gemini-2.5-flash',
    name='my_special_agent',
    description='Managed GEAP agent.',
    instruction=system_instruction,
    tools=tools
)

class MySpecialAgent:
    def __init__(self):
        self.runner = None

    async def query(self, question: str, context: dict = None) -> str:
        runtime_dir = os.path.dirname(os.path.abspath(__file__))
        
        # --- DEBUG HOOK ---
        if question == "debug_env":
            files = []
            for root, dirs, ffiles in os.walk(runtime_dir):
                for f in ffiles:
                    files.append(os.path.relpath(os.path.join(root, f), runtime_dir))
            return f"Agent Runtime Dir: {runtime_dir}\nFiles:\n" + "\n".join(files)
        # --- END DEBUG HOOK ---

        import hubscape_adk
        import uuid
        user_id = (context or {}).get("userId") or "anonymous_user"
        org_id = (context or {}).get("orgId")
        hub_id = (context or {}).get("hubId")
        
        agent_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/Zco-AI-Labs/my-special-agent"))
        project_id = os.getenv("PROJECT_ID") or os.getenv("GCP_PROJECT_ID") or "hubscape-geap"
        
        remote_ctx = hubscape_adk.RemoteContext(
            user_id=user_id, agent_id=agent_uuid, org_id=org_id, hub_id=hub_id,
            project_id=project_id, raw_context=context
        )
        
        session_id = (context or {}).get("sessionId") or f"session_{user_id}_{hub_id}"
        
        with hubscape_adk.context_session(remote_ctx):
            if not self.runner:
                from google.adk.sessions.in_memory_session_service import InMemorySessionService
                from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
                from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
                from google.adk.auth.credential_service.in_memory_credential_service import InMemoryCredentialService
                
                self.runner = Runner(
                    agent=root_agent,
                    app_name='my-special-agent',
                    session_service=InMemorySessionService(),
                    artifact_service=InMemoryArtifactService(),
                    memory_service=InMemoryMemoryService(),
                    credential_service=InMemoryCredentialService(),
                    auto_create_session=True
                )
            
            # Optionally load cached ADK session state from Firestore
            try:
                session_doc = remote_ctx.get(scope="user", collection_name="sessions", doc_id=session_id)
                if session_doc and "adk_session" in session_doc:
                    from google.adk.sessions import Session
                    session_obj = Session.model_validate_json(session_doc["adk_session"])
                    session_service = self.runner.session_service
                    
                    app_name = session_obj.app_name
                    uid = session_obj.user_id
                    sid = session_obj.id
                    
                    if app_name not in session_service.sessions:
                        session_service.sessions[app_name] = {}
                    if uid not in session_service.sessions[app_name]:
                        session_service.sessions[app_name][uid] = {}
                    session_service.sessions[app_name][uid][sid] = session_obj
            except Exception:
                pass

            new_message = types.Content(
                parts=[types.Part.from_text(text=question)]
            )
            
            text_response = ""
            async for event in self.runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=new_message
            ):
                if event.output:
                    text_response += event.output
                elif event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            text_response += part.text
            
            # Optionally save ADK session state back to Firestore
            try:
                session_service = self.runner.session_service
                updated_session = await session_service.get_session(
                    app_name='my-special-agent',
                    user_id=user_id,
                    session_id=session_id
                )
                if updated_session:
                    serialized_json = updated_session.model_dump_json()
                    remote_ctx.save(
                        scope="user", collection_name="sessions", doc_id=session_id,
                        data={"adk_session": serialized_json}
                    )
            except Exception:
                pass
                
            return text_response

my_special_agent_app = MySpecialAgent()
``````

### 2. Packaging and Deploying (`deploy.py`)
Deploying an agent as a Vertex AI Reasoning Engine involves a script that calls the containerized `agents-cli deploy` command.

We use a standard root-level `deploy.py` script that acts as a wrapper to execute `agents-cli deploy` via a subprocess:

```python
import os
import sys
import subprocess
import shutil

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "hubscape-geap")
LOCATION = os.getenv("GCP_LOCATION", "us-central1")
display_name = "custom-agent"

print(f"Deploying {display_name} via native agents-cli...")

agents_cli_path = shutil.which("agents-cli")
if not agents_cli_path:
    venv_bin = os.path.dirname(sys.executable)
    fallback_path = os.path.join(venv_bin, "agents-cli")
    if os.path.exists(fallback_path):
        agents_cli_path = fallback_path
if not agents_cli_path:
    agents_cli_path = "agents-cli"

cmd = [
    agents_cli_path, "deploy",
    "--project", PROJECT_ID,
    "--region", LOCATION,
    "--service-name", display_name,
    "--agent-identity",
    "--no-confirm-project"
]

env = os.environ.copy()
venv_bin = os.path.dirname(sys.executable)
env["PATH"] = f"{venv_bin}{os.path.pathsep}{env.get('PATH', '')}"

print(f"Executing: {' '.join(cmd)}")
subprocess.run(cmd, env=env, check=True)
print("🎉 Deployment completed successfully!")
```


### 3. Defining Tools in `scripts/`
Each script file contains a single Python function. The function's signature and docstring serve as the tool schema.

```python
# scripts/add_item.py
import hubscape_adk
import logging
logger = logging.getLogger(__name__)

def add_item(item_name: str, quantity: int = 1) -> dict:
    """Adds a item to the inventory database.

    Args:
        item_name: The name/description of the item.
        quantity: The quantity to add.
    """
    try:
        context = hubscape_adk.get_context()
        # Save to hub-scoped collection
        context.save(
            scope="hub",
            collection_name="inventory",
            doc_id=item_name.lower().replace(" ", "_"),
            data={"item_name": item_name, "quantity": quantity}
        )
        return {"status": "success", "message": f"Added {quantity} x '{item_name}'."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

### 4. Client Action Directives
GEAP agents can trigger client-side actions (like rendering widgets, navigating hub workspace, or ending calls) by appending payloads to `context.actions` during tool execution:

```python
def open_admin_portal(widget_type: str) -> dict:
    """Triggers the client UI to open a specific admin widget.
    
    Args:
        widget_type: The layout type (e.g. 'hub_members', 'hub_settings').
    """
    context = hubscape_adk.get_context()
    context.actions.append({
        "type": "OPEN_ADMIN_WIDGET",
        "payload": {
            "widgetType": widget_type
        }
    })
    return {"status": "success", "message": f"Signaled client UI to open admin widget: {widget_type}"}
```

Standard Action Directives:
* **`OPEN_ADMIN_WIDGET`**: `{"type": "OPEN_ADMIN_WIDGET", "payload": {"widgetType": str}}`
* **`SET_SUGGESTIONS`**: `{"type": "SET_SUGGESTIONS", "queries": list[str]}`
* **`SWITCH_HUB`**: `{"type": "SWITCH_HUB", "payload": {"hubId": str}}`
* **`OPEN_EXTERNAL_LINK`**: `{"type": "OPEN_EXTERNAL_LINK", "payload": {"url": str}}`
* **`END_CALL`**: `{"type": "END_CALL"}`

---

## 🔒 Context & Database Scoping (`hubscape_adk.py`)
To isolate data and prevent split-brain architectures, database operations must utilize `hubscape_adk.get_context()` scopes:

1. **User Scope (`scope="user"`)**: Scopes records to the active platform user.
   `platform_users/{user_id}/agent_data/{agent_id}/{collection_name}/{doc_id}`
2. **Hub Scope (`scope="hub"`)**: Scopes records to the active Hub within the Organization.
   `organizations/{org_id}/hubs/{hub_id}/agent_data/{agent_id}/{collection_name}/{doc_id}`
3. **Org Scope (`scope="org"`)**: Scopes records to the active Organization.
   `organizations/{org_id}/agent_data/{agent_id}/{collection_name}/{doc_id}`

### Auditing Metadata Mandate
The `context.save()` helper automatically injects and maintains the auditing metadata block:
* `created_at` (UTC timestamp)
* `created_by` (active User UUID)
* `updated_at` (UTC timestamp)
* `updated_by` (active User UUID)
* `version` (automatically incremented integer starting at 1)

Never perform raw document writes that bypass these scopes and auditing fields.

---

## 🔌 Decommissioned Inbound API Routes (`api.py`)
* **Legacy api.py (Removed):** In the legacy local agent system, custom inbound routes were handled by placing a FastAPI `api.py` file in the agent directory that the host core mounted. **This is no longer supported.**
* **Why it was removed:** GEAP agents are sandboxed cloud resources and cannot directly host public inbound HTTP routes.
* **Architecture Guideline for External Inbound Events (Webhooks, Redirects):**
  1. Route all external OAuth redirect callback URLs or webhook endpoints directly inside the central Hubscape backend (`backend_python/routers/`).
  2. The central backend processes the redirect or event and writes tokens/secrets to Firestore scopes (e.g. `platform_users/{userId}/tokens/{agentId}`).
  3. The GEAP agent queries those Firestore scopes dynamically at runtime using `hubscape_adk.py`.
* **Outbound Calls:** For outbound integrations, write standard python functions directly in the function tools inside the `scripts/` directory or helper modules within the `app/` folder.

---

## 🔒 Secret and API Key Management & Outbound Connections
* **System-Level Secrets:** For global credentials, use Google Cloud Secret Manager or configure environment variables during Vertex AI Reasoning Engine deployment.
* **User/Org-Level Secrets (OAuth Tokens):** 
  1. The central Hubscape backend handles OAuth callback setups and saves the resulting token/secret to Firestore (e.g. `platform_users/{userId}/tokens/{agentId}`).
  2. The GEAP agent reads these secrets dynamically during tool execution:
     `token_doc = context.get(scope="user", collection_name="tokens", doc_id="github")`
* **Outbound External Connections:** To connect to external third-party services, execute asynchronous HTTP requests inside tools using `httpx`:
  ```python
  import httpx
  async with httpx.AsyncClient(timeout=10.0) as client:
      resp = await client.get("https://api.external.com/data")
  ```

---

## 🗄️ Database Scoping API (`hubscape_adk.py`)
GEAP agents read, write, and delete documents within Firestore using a scoping pattern to ensure data isolation:
* **Scopes:**
  * `scope="user"`: resolves to `platform_users/{userId}/agent_data/{agentId}/{collection_name}/{docId}`
  * `scope="hub"`: resolves to `organizations/{orgId}/hubs/{hubId}/agent_data/{agentId}/{collection_name}/{docId}`
  * `scope="org"`: resolves to `organizations/{orgId}/agent_data/{agentId}/{collection_name}/{docId}`
* **CRUD Methods:**
  * `context.save(scope, collection_name, doc_id, data)`: Injects audit keys (`created_at`, `created_by`, `updated_at`, `updated_by`, `version`).
  * `context.get(scope, collection_name, doc_id)`: Fetches a single document, injecting `id`.
  * `context.list(scope, collection_name)`: Streams all documents in a collection scope.
  * `context.delete(scope, collection_name, doc_id)`: Deletes a document.

---

## 🧱 Lego Widget System & Containerized Packaging
* **Predefined Widgets:** static JSON layouts must be placed inside the `app/widgets/` directory. Placed outside `app/`, they are omitted from the built docker container.
  `context.show_widget(widget_template_id="task_list", data={})`
* **Generative UI:** Compose layouts dynamically and query `context.show_custom_ui(layout, data)`.
* **Variable Interpolations:** Placeholder `{{agent_id}}` inside widget JSON templates is automatically replaced with the agent's UUID at runtime.
* **Submit Loop:** Button actions in Lego widgets (configured with `actionUrl`) gather input values from sibling elements and POST them to the central backend.

---

## 📡 Agent-to-Agent (A2A) Delegation
* **Standard Tool:** The central Host Orchestrator repository contains a standard `consultAgent` tool (`scripts/consult_agent.py`) that queries whitelisted subagents using a GCP service account token.
  > [!IMPORTANT]
  > **Critical Token Resolution Rule inside GEAP Containers:**
  > Inside a remote Vertex AI Reasoning Engine execution container, `google.auth.default()` resolves to the restricted OIDC Workload Identity credentials. While these credentials can authenticate internal model predictions, they are restricted from making general outbound GCP HTTP/REST requests (like calling other reasoning engines).
  > Therefore, token generation MUST query the local GCE Metadata Server first to obtain the VM tenant service account token (which has the necessary `roles/aiplatform.user` scope):
  > * **Primary lookup:** Query `http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token`.
  > * **Local fallback:** Use `google.auth.default()` *only* if the metadata server is unreachable (for local testing).
* **Directives:** The host agent automatically intercepts standard JSON responses returned by subagents (like `OPEN_ADMIN_WIDGET`, `SET_SUGGESTIONS`, etc.) and appends them to the host's client action queue.
* **Loop Prevention:** Whitelist checking and depth limit (incrementing context `depth` up to 3) are enforced in `consultAgent`.
* **Cross-Project (External) A2A:** Consulting a subagent hosted in an external project requires granting the calling service account `Vertex AI User` and `Vertex AI Reasoning Engine Predictor` IAM roles in the target project, and adding the target resource name path to the hub's whitelist.
* **v1beta1 A2A Routing and Comment Mandate:** Because Vertex AI Reasoning Engine's A2A routing endpoints (such as `/a2a/v1/card`) are **not** exposed on the GA `/v1/` gateway (which returns a `404 Not Found`), any agent routing A2A requests MUST replace `/v1/` with `/v1beta1/` and ensure the URL ends with `/a2a/v1/card`. To prevent blind upgrade attempts, developers and AI agents **MUST** leave a warning comment above this block:
  ```python
  # NOTE: Using v1beta1 specifically for the A2A handshake gateway because 
  # Vertex AI Reasoning Engine's A2A routing endpoints (e.g. /a2a/v1/card)
  # are not exposed on the GA /v1/ endpoints (returning a 404 Not Found).
  card_url = a2a_url
  if "/v1/" in card_url:
      card_url = card_url.replace("/v1/", "/v1beta1/")
  if "/a2a" not in card_url:
      card_url = card_url.rstrip("/") + "/a2a"
  if not card_url.endswith("/v1/card"):
      card_url = card_url.rstrip("/") + "/v1/card"
  ```

---

## 🗄️ Vertex RAG Retrieval and Tenant Scoping Isolation
* **Metadata Field Requirement (v1beta1 client):** When performing RAG queries, agents **MUST** use the `google.cloud.aiplatform_v1beta1` SDK client because the GA `v1` client's `RagChunk` schema lacks the `file_id` and `chunk_id` metadata fields. Without `file_id`, the agent cannot verify tenant ownership boundaries (`hub_id` / `org_id`) against Firestore.
* **Reviewer Comment Mandate:** You **MUST** place a clear explanatory comment block directly above this import block:
  ```python
  # NOTE: Using v1beta1 specifically for RAG retrieval because the GA v1 
  # RagChunk schema lacks the file_id and chunk_id metadata fields required 
  # for our Firestore tenant isolation and validation checks.
  from google.cloud import aiplatform_v1beta1
  ```

---

## 🛠️ Model Context Protocol (MCP) Integration
* **No Monolithic Tool Registry:** We no longer manage local MCP server processes or a monolithic `ToolRegistry` on the backend.
* **Implementation:** If a GEAP agent requires tool capability from an MCP server, either convert those MCP tools into standard Python functions inside the agent's `scripts/` folder, or write an outbound HTTP/SSE client within a tool in `scripts/` that connects to a hosted remote MCP server.

---

## 🔍 Google Search Grounding (Websearch)
* **Legacy Toggle:** The Firestore-based `allow_web_search` toggle is decommissioned.
* **Option A (Native Grounding):** To enable native Google Search grounding, add the `GoogleSearchRetrieval` tool directly to your agent's config inside `agent.py`:
  ```python
  from vertexai.preview.generative_models import Tool, grounding
  google_search_tool = Tool.from_google_search_retrieval(grounding.GoogleSearchRetrieval())
  # Append to your tools configuration
  root_agent.tools = load_local_tools(scripts_dir) + [google_search_tool]
  ```
  Ensure `google-cloud-aiplatform` is specified in your `pyproject.toml` dependencies.
* **Option B (Custom Tool):** Write a custom search function tool inside `scripts/web_search.py` that queries custom search engines or scrapers, returning formatted results.

---

## 🤖 Alternative and Non-Gemini Model Support
The standard SDK (`google-adk`) supports alternative LLM providers and hosted endpoints:
* **Vertex AI Model Garden:** Pass the full GCP endpoint resource path as the model string (e.g., `projects/{project}/locations/{location}/endpoints/{endpoint_id}`).
* **Third-Party Providers (OpenAI, Claude, etc.):** 
  * Prepend the provider prefix (e.g., `openai/gpt-4o`) to route through the integrated `LiteLlm` backend.
  * Native Claude support is available via `from google.adk.models.anthropic_llm import Claude`.
* **Configuration Requirements:**
  1. Add `google-adk[extensions]` or the specific provider package (`litellm`, `anthropic`, etc.) to the `pyproject.toml` dependencies.
  2. Configure required credentials (e.g., `OPENAI_API_KEY`) as system-level secrets via GCP Secret Manager or reasoning engine environment variables.

---

## 🏛️ Decoupled Skill Architecture & Framework Interoperability
* **Decoupled Logic:** An agent's prompts (`SKILL.md`), tools (`scripts/`), and documentation (`references/`) are decoupled from the SDK wrapper. The Python code is just a lightweight loader.
* **SDK Standard:** All remote GEAP containers compile to standard Vertex AI Reasoning Engines using `google-adk`.
* **Coexistence Guidelines:**
  1. Points of config: Define the root agent at the module level in `agent.py` to allow the ADK CLI and agents-cli to load it.
  2. Packaging: Declare the `app` folder as the `agent_directory` in `agents-cli-manifest.yaml`. All files, scripts, and skills within the `app` directory will be packaged automatically.
  3. Local Testing: Use the `agents-cli playground` tool in your agent's directory to execute local tests and preview widgets.





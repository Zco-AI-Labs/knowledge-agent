# Hubscape GEAP Agent Manual

This manual serves as the technical reference for creating, configuring, and maintaining specialized AI agents deployed as cloud-native **Vertex AI Reasoning Engines** under the **Gemini Enterprise Agent Platform (GEAP)**.

---

## 1. Core Architecture
Hubscape utilizes a **decoupled cloud-native agent architecture**:
* **Backend as a Proxy:** The Python backend (`backend_python`) does not execute agent loops. It acts as an API proxy relay, receiving messages at `/api/host/chat`, constructing context payloads, and querying the remote GEAP agent via HTTP REST POST.
* **Vertex AI Reasoning Engines:** All specialized agents are packaged as Python classes, registered with the Vertex AI SDK, and run inside containerized Google Cloud environments.
* **Stable Identity:** Each agent is assigned a stable, deterministic UUID calculated from its GitHub repository URL. This UUID is embedded in the agent's Vertex AI description as `[agent_uuid: <uuid>]` and is synced to the Firestore `agents` collection to manage access whitelists.

---

## 2. Directory Structure & Layout Options

We support two layout methodologies depending on the agent's complexity and scalability requirements.

### 2.1 Method A: Flat / Code-Centric Layout
Recommended for simple, single-purpose agents with few tools. Prompts and tools are defined directly within the `app/` Python package.

```text
my-flat-agent/
├── agents-cli-manifest.yaml # REQUIRED: agents-cli manifest
├── deploy.py               # REQUIRED: Subprocess wrapper to run agents-cli deploy
├── pyproject.toml          # REQUIRED: uv dependency manager configuration
└── app/                    # REQUIRED: Agent directory containing python code
    ├── __init__.py         # REQUIRED: Package initialization
    ├── agent.py            # REQUIRED: Main agent class conforming to Vertex AI Reasoning Engine SDK
    ├── core/               # Platform core code (off-limits to editing agent)
    │   ├── agent_runtime_app.py # Entry point loaded by Agent Runtime
    │   ├── geap_agent_wrapper.py # Conformance wrapper class for Vertex AI Reasoning Engine SDK
    │   └── hubscape_adk.py  # Lightweight context/DB adapter (copied verbatim)
    ├── prompt.py           # REQUIRED: Python module or string defining the system prompt
    ├── tools.py            # REQUIRED: Python module containing all agent tool function definitions
    └── app_utils/          # REQUIRED: env_resolver and vertex_gemini helpers
```

> [!IMPORTANT]
> **SDK Choice:** You **MUST** use the `google-adk` package/SDK instead of `google-antigravity` for all GEAP agents. This enables direct local testing via the ADK CLI (`adk web` / `adk run`). Ensure that `agent.py` exposes a global `root_agent` instance using `google.adk.Agent` for the ADK CLI to load, and defines `geap_agent_wrapper_app` (or equivalent wrapper instance implementing `.query(...)`) for Vertex AI Reasoning Engine compatibility.

### 2.2 Method B: Segregated / Decoupled Layout (Staged Standard)
Recommended for complex, production-grade agents. Prompts are kept in a clean markdown file (`SKILL.md`), and tools are separated into single-purpose scripts within the `scripts/` directory under `app/`.

```text
my-segregated-agent/
├── agents-cli-manifest.yaml # REQUIRED: agents-cli manifest
├── deploy.py               # REQUIRED: Subprocess wrapper to run agents-cli deploy
├── pyproject.toml          # REQUIRED: uv dependency manager configuration
└── app/                    # REQUIRED: Agent directory containing python code
    ├── __init__.py         # REQUIRED: Package initialization
    ├── agent.py            # REQUIRED: Main agent class conforming to Vertex AI Reasoning Engine SDK
    ├── core/               # Platform core code (off-limits to editing agent)
    │   ├── agent_runtime_app.py # Entry point loaded by Agent Runtime
    │   ├── geap_agent_wrapper.py # Conformance wrapper class for Vertex AI Reasoning Engine SDK
    │   └── hubscape_adk.py  # Lightweight context/DB adapter (copied verbatim)
    ├── SKILL.md            # REQUIRED: YAML identity metadata + Markdown system instructions
    ├── scripts/            # REQUIRED: Python function tools (no __init__.py)
    │   ├── tool_one.py     # Implementation of tool_one
    │   └── tool_two.py     # Implementation of tool_two
    ├── references/         # OPTIONAL: Static reference files/documentation read at runtime
    └── app_utils/          # REQUIRED: env_resolver and vertex_gemini helpers
```

### 2.3 Layout Selection Criteria

Developers must analyze agent requirements and select the layout that best fits. Do not blindly default to a single layout.

| Metric / Requirement | **Method A (Flat / Code-Centric)** | **Method B (Segregated / Skill-Centric)** |
| :--- | :--- | :--- |
| **Complexity & Scope** | Simple, single-purpose or helper agents. | Medium to highly complex agents. |
| **Tool Count** | Low (typically < 3 tools). Defined in `tools.py`. | Medium to High (>= 3 tools). Segregated in `scripts/`. |
| **System Prompt Size** | Short, simple prompts (often inlined or in `prompt.py`). | Long, rich prompts that benefit from Markdown styling and structure. |
| **Maintenance & Scale** | Easy for tiny footprints, but hard to maintain when files exceed 300 lines. | Modular and scalable; new tools are added by creating a file in `scripts/`. |
| **Collaborative Prompts** | Prompts are embedded in Python code (harder for non-devs to edit). | Prompts live in standard `SKILL.md` (easy for content creators to edit). |
| **Static Reference Docs** | Not natively structured for external references. | Built-in support for loading static docs from a `references/` directory. |

---

## 3. Agent Archetypes
We distinguish between two main archetypes of GEAP agents in the Hubscape platform:

| Feature | **Central Host Orchestrator** (`host-agent`) | **Specialist Subagent** (`todo-agent`) |
| :--- | :--- | :--- |
| **System Instruction** | Dynamic: loaded at runtime from the caller's context payload (`context['system_instruction']`). | Static: loaded at deployment time from `SKILL.md` (which is REQUIRED). |
| **Response Format** | JSON string containing text response and queued action directives. | Plain text response. |
| **State / Trajectory** | Stateful: persists the SQLite trajectory database to Firestore under the user's session. | Stateless: does not save or restore session trajectories. |
| **Disabled BuiltinTools** | Disables 10 BuiltinTools (including `START_SUBAGENT` and `ASK_QUESTION`). | Disables 8 BuiltinTools (keeps `START_SUBAGENT` and `ASK_QUESTION` enabled). |
| **Tool loading** | Supports camelCase fallback in `load_local_tools` for legacy tools. | Strict snake_case tool mapping only. |
| **Requirements** | No `SKILL.md` is required. | `SKILL.md` is strictly REQUIRED. |

### camelCase Tool Name Fallback
If any script tool exports a camelCase function name (e.g., `consult_agent.py` → `consultAgent`), add a camelCase fallback to `load_local_tools` in your agent. See `host-agent/agent.py` lines 24-28 for the pattern. For subagents, stick to snake_case matching.


---

## 4. The Four Pillars of a GEAP Agent

### Pillar 1: `SKILL.md` (Metadata & System Prompt)
This file defines the agent's identity and system prompt. It contains a YAML frontmatter block followed by markdown system instructions.

```markdown
---
name: my_special_agent
description: "An advanced assistant that performs X. Call this agent when the user wants to do Y."
---

You are a specialized assistant that performs X. Always be concise and polite.
Format your output using clean markdown lists.
If a tool returns an error, explain it clearly to the user.
```

* **Dynamic Ingestion:** The `agent.py` script automatically reads this file, strips the frontmatter, and sets the remaining markdown as the agent's system instructions (`CustomSystemInstructions`).
* **Description Sync:** The `description` field in the frontmatter is critical. The platform's central Host Agent uses this description to semantically route user requests to this subagent.

### Pillar 2: `agent.py` (The Loop & Trajectory)
Implements the main Reasoning Engine interface. It instantiates `google.adk.Agent` and handles session trajectory persistence back to Firestore.

```python
import os
# Force regional Vertex AI routing unconditionally
os.environ.pop("GOOGLE_GENAI_USE_ENTERPRISE", None)
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
import sys
import asyncio
import importlib.util
import re
from google.adk import Agent as AdkAgent
from google.adk.runners import Runner
from google.genai import types

def load_local_tools(scripts_dir: str) -> list:
    app_dir = os.path.dirname(os.path.abspath(scripts_dir))
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
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

# 1. Module-level instructions and tool loading
runtime_dir = os.path.dirname(os.path.abspath(__file__))
skill_md_path = os.path.join(runtime_dir, "SKILL.md")
system_instruction = "You are a highly efficient assistant."
if os.path.exists(skill_md_path):
    with open(skill_md_path, "r", encoding="utf-8") as f:
        skill_content = f.read()
    system_instruction = re.sub(r"^---.*?---", "", skill_content, flags=re.DOTALL).strip()

scripts_dir = os.path.join(runtime_dir, "scripts")
tools = load_local_tools(scripts_dir)

from app.app_utils.vertex_gemini import get_model

root_agent = AdkAgent(
    model=get_model("gemini-2.5-flash"),
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
        user_id = (context or {}).get("userId") or (context or {}).get("user_id") or "anonymous_user"
        org_id = (context or {}).get("orgId") or (context or {}).get("org_id")
        hub_id = (context or {}).get("hubId") or (context or {}).get("hub_id")
        
        agent_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/Zco-AI-Labs/my-special-agent"))
        from app.app_utils.env_resolver import get_project_id
        project_id = get_project_id()
        
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
            
            return text_response

# Singleton instance used as the serialization target
my_special_agent_app = MySpecialAgent()

from google.adk.apps import App
app = App(
    root_agent=root_agent,
    name="app",
)
```

### Pillar 3: `scripts/` (Tool Implementations)
Each python file in the `scripts/` folder defines a single callable function. The name, signature (types), and docstring are automatically parsed to form the model's tool schema:

```python
# scripts/book_appointment.py
import hubscape_adk
import logging
logger = logging.getLogger(__name__)

def book_appointment(date_str: str, time_str: str) -> dict:
    """Schedules an appointment for the platform user.

    Args:
        date_str: The date (YYYY-MM-DD format).
        time_str: The requested time (e.g. '14:00').
    """
    try:
        context = hubscape_adk.get_context()
        user_id = context.auth.get_user_id()
        
        context.save(
            scope="user",
            collection_name="appointments",
            doc_id=f"appt_{date_str}_{time_str.replace(':', '')}",
            data={
                "date": date_str,
                "time": time_str,
                "status": "booked"
            }
        )
        return {"status": "success", "message": "Appointment scheduled successfully."}
    except Exception as e:
        return {"status": "error", "message": f"Failed to book: {str(e)}"}
```

### Pillar 4: `hubscape_adk.py` (Database Scoping & Context)
A standardized, lightweight module that imports credentials and connects directly to Firestore, allowing tools to read, write, and delete data within isolated scopes:

```python
import hubscape_adk

# 1. Acquire current session context
context = hubscape_adk.get_context()

# 2. Read active context metadata
user_id = context.auth.get_user_id()
org_id = context.auth.org_id
hub_id = context.auth.hub_id

# 3. Create or Update a document (automatically injects metadata:
#    created_at, created_by, updated_at, updated_by, version)
payload = {"title": "Buy milk", "completed": False}
context.save(scope="user", collection_name="todos", doc_id="todo_001", data=payload)

# 4. Read a document by ID (returns a dict with "id" injected or None)
todo = context.get(scope="user", collection_name="todos", doc_id="todo_001")

# 5. List all documents inside a collection scope (returns a list of dicts)
all_todos = context.list(scope="user", collection_name="todos")

# 6. Delete a document
context.delete(scope="user", collection_name="todos", doc_id="todo_001")
```

#### Firestore Scoping Paths
The library resolves `scope` parameters to isolated collections to prevent cross-tenant and cross-user data leaks:
* **`scope="user"`**: `platform_users/{userId}/agent_data/{agentId}/{collection_name}/{docId}`
  * *Use case:* Individual user settings, personal task lists.
* **`scope="hub"`**: `organizations/{orgId}/hubs/{hubId}/agent_data/{agentId}/{collection_name}/{docId}`
  * *Use case:* Collaboration data shared by members within a specific hub.
* **`scope="org"`**: `organizations/{orgId}/agent_data/{agentId}/{collection_name}/{docId}`
  * *Use case:* Org-wide policies, shared integrations, and settings.

#### OAuth & Secret Retrieval
Because GEAP agents are sandboxed, they cannot host public endpoints for OAuth callbacks. Webhook callback URLs are hosted on the central backend, which registers tokens to Firestore:
* **Pattern:** To fetch a third-party API key or access token, read the token document from the user's scoped collection:
```python
# Read OAuth credentials (e.g. Stripe, Github, or external API keys)
tokens = context.get(scope="user", collection_name="tokens", doc_id="github")
access_token = tokens.get("access_token") if tokens else None
```

---

---

## 5. Client Action Directives
Agents can trigger client-side actions (like opening UI panels or switching tabs) by appending action dictionaries to `context.actions` during tool calls. The central Host Agent intercepts these directives and returns them in the final JSON response payload.

### Standard Client Actions:
* **`OPEN_ADMIN_WIDGET`**: Triggers configuration UI.
  `{"type": "OPEN_ADMIN_WIDGET", "payload": {"widgetType": "hub_members"}}`
* **`OPEN_AGENT_WIDGET`**: Triggers rendering of a custom Lego UI widget.
  `{"type": "OPEN_AGENT_WIDGET", "payload": {"widgetId": "tasks", "widgetConfig": {...}, "data": {...}}}`
* **`SET_SUGGESTIONS`**: Changes conversation quick-replies.
  `{"type": "SET_SUGGESTIONS", "queries": ["List my tasks", "Add task"]}`
* **`SWITCH_HUB`**: Changes active Hub navigation.
  `{"type": "SWITCH_HUB", "payload": {"hubId": "target_hub_uuid"}}`
* **`OPEN_EXTERNAL_LINK`**: Redirects to external URLs.
  `{"type": "OPEN_EXTERNAL_LINK", "payload": {"url": "https://example.com"}}`
* **`END_CALL`**: Ends live telephony/voice session.
  `{"type": "END_CALL"}`

---

## 6. Lego Widget System & Action Routing

### 6.1 Predefined Widgets (`context.show_widget`)
Predefined layouts are JSON files representing static Lego block structures. 
* **Containerized Packaging Rule:** Because GEAP reasoning engines are deployed from the `app/` folder, all widget JSON files **MUST** be placed in `app/widgets/` (e.g. `app/widgets/task_list.json`). Files placed outside the `app/` folder are omitted from the built docker container and will fail with a `FileNotFoundError` at runtime.
* **Variable Replacement:** The library automatically parses the loaded JSON file and replaces instances of the `{{agent_id}}` placeholder with the active agent's UUID at runtime.

To display a predefined widget, invoke:
```python
context = hubscape_adk.get_context()
context.show_widget(widget_template_id="task_list", data={"filter": "pending"})
```
This parses `app/widgets/task_list.json`, interpolates variables, and appends an `OPEN_AGENT_WIDGET` action to the client response queue.

### 6.2 Generative UI (`context.show_custom_ui`)
The agent's LLM can dynamically compose a Lego interface dictionary structure and output it:
```python
layout = {
    "type": "container",
    "props": {"className": "flex flex-col gap-4 p-4"},
    "children": [
        {"type": "text", "props": {"text": "Confirm Submission", "className": "font-bold"}},
        {"type": "button", "props": {"label": "Approve", "actionUrl": "/api/plugins/{{agent_id}}/approve"}}
    ]
}
context = hubscape_adk.get_context()
context.show_custom_ui(layout=layout, data={})
```

### 6.3 Lego Interaction Loop (Button Submit Behavior)
Lego widgets enable interactive form loops:
1. **Submit Payload:** Clicking a Lego `button` component gathers all values from sibling inputs (e.g. `RatingElement`, standard text inputs) inside the parent container.
2. **Outbound POST:** It fires an HTTP POST containing the inputs to the specified `actionUrl` (e.g., `/api/plugins/{{agent_id}}/approve`).
3. **Central Routing:** The central backend intercepts the POST request and passes the values to the agent's background routines, which can perform writes or update the Firestore database.

### 6.4 Generative UI Guardrails (`allowGenerativeUi`)
To prevent unauthorized code execution or layout injection, agents support the `allowGenerativeUi` guardrail flag:
* **Predefined Widgets:** Always allowed.
* **Generative UI:** Calls to `show_custom_ui` are intercepted. If `allowGenerativeUi` is `False`, the ADK raises a runtime `PermissionError` and aborts.
* **Configuration:**
  * **Method A (Flat):** Hardcode `allow_generative_ui = True/False` when instantiating `RemoteContext` in `agent.py`.
  * **Method B (Segregated):** Add `allowGenerativeUi: false` in `SKILL.md` YAML frontmatter.
  * **Platform Override:** Add `allowGenerativeUi: false` to the agent's configuration object in the platform's Firestore `agents` collection.

### 6.4 The Pure Agentic Form Protocol (Option A)
Because remote GEAP containers cannot receive direct inbound HTTP POST requests, all widget interaction (button clicks, form submissions) is routed asynchronously inside the chat stream:
1. **Interactive Elements:** Buttons and form inputs in Lego layouts configure their `actionUrl` using protocols `agent://` or `chat://` (e.g. `agent://save_todo` or `chat://cancel_meeting`).
2. **Frontend Interception:** When clicked, `DynamicWidget.tsx` intercepts the `agent://` url, packages the input fields into a JSON payload, and fires a `hubscape:agent-action` DOM event.
3. **Chat Queue Relay:** `useChat.ts` captures the event and submits a silent slash command into the chat stream:
   `[Form Submit] /action {actionName} {jsonPayload}`
4. **Agent Processing:** The agent's `agent.py` receives the question. If it starts with `/action`, the agent parses the action name and JSON payload, routes it to the corresponding Python tool (e.g. `save_todo`), updates the Firestore data, and returns the updated widget config.

---

## 7. Agent Packaging & Deployment

To deploy an agent as a Vertex AI Reasoning Engine, developers use a `deploy.py` script. The packaging behavior follows these strict constraints:

### 7.1 Dependency Definition (`pyproject.toml`)
* **Local Development & Cloud Deployment:** All package dependencies are managed in `pyproject.toml` (using the `uv` package manager). The `agents-cli deploy` command automatically resolves, packages, and installs these dependencies into the remote Cloud Run environment container. Do NOT hardcode packages inside custom Python lists.

### 7.2 Directory Configuration (`agents-cli-manifest.yaml`)
The deployment configuration is declared in `agents-cli-manifest.yaml` in the root of the repository:
* `agent_directory`: Set to `"app"`. This indicates that all agent logic, modules, scripts, and prompts live inside the `app/` folder.
* `base_template`: Set to `"adk"`.
* `create_params`: Configures standard options such as `deployment_target: "agent_runtime"` and `is_a2a`: true.

### 7.3 Staging Bucket Isolation
To prevent concurrent deployments from colliding or overwriting each other's serialized artifacts inside Google Cloud Storage, the platform's CI/CD pipeline and local CLI setups utilize display-name isolation. Under `agents-cli`, build artifacts are automatically uploaded to isolated subfolders under the GCP staging bucket (e.g. `gs://hubscape-geap-reasoning-engines/todo-agent/`).

### 7.4 Keyless OIDC Wildcard Authentication
The GitHub Actions workflow uses keyless authentication via Google Cloud Workload Identity Federation. 
* **Design:** The GCP service account (`geap-agent-deployer`) is configured with a pool-level wildcard binding (`principalSet://.../workloadIdentityPools/github-pool/*`). 
* **Outcome:** Since the identity provider restricts access to repositories owned by `Zco-AI-Labs`, *any* new agent repository created under the organization is pre-authorized to authenticate and deploy without requiring manual IAM policy bindings.

### 7.5 The `debug_env` Diagnostic Hook
All GEAP agents must implement a `debug_env` hook inside their `query` method. If the agent receives the exact question `"debug_env"`, it should return a diagnostic string listing files in its runtime path, service account configuration, and tool import errors:
```python
def query(self, question: str, context: dict = None) -> str:
    # --- DEBUG HOOK ---
    if question == "debug_env":
        files = []
        for root, dirs, ffiles in os.walk(runtime_dir):
            for f in ffiles:
                files.append(os.path.relpath(os.path.join(root, f), runtime_dir))
        return f"Agent Runtime Dir: {runtime_dir}\nFiles:\n" + "\n".join(files)
    # --- END DEBUG HOOK ---
```

### 7.6 Shared Context Library (`hubscape_adk.py`)
`hubscape_adk.py` is a shared context management and Firestore client wrapper. Rather than being distributed as a separate package, it is treated as a shared library:
* **Directive:** Copy `hubscape_adk.py` verbatim from the latest reference agent repository (`host-agent` or `todo-agent`) into your new agent repository. Do not make local modifications to `hubscape_adk.py` inside individual agent repositories.

### 7.7 Decommissioned Inbound API Routes (`api.py`)
* **Legacy api.py (Removed):** In the legacy local agent system, custom inbound routes were handled by placing a FastAPI `api.py` file in the agent directory that the host core mounted. **This is no longer supported.**
* **Why it was removed:** GEAP agents are sandboxed cloud resources and cannot directly host public inbound HTTP routes.
* **Architecture Guideline for External Inbound Events (Webhooks, Redirects):**
  1. Route all external OAuth redirect callback URLs or webhook endpoints directly inside the central Hubscape backend (`backend_python/routers/`).
  2. The central backend processes the redirect or event and writes tokens/secrets to Firestore scopes (e.g. `platform_users/{userId}/tokens/{agentId}`).
  3. The GEAP agent's outbound utility functions (defined in tools or scripts) query those Firestore scopes dynamically at runtime using `hubscape_adk.py`.
* **Outbound Calls:** For outbound external API connections (e.g., retrieving weather data, checking calendar events, or querying a custom third-party database), implement standard asynchronous Python functions using `httpx`. Since the reasoning engine runs in a containerized environment, ensure outbound calls utilize clean timeout controls:
```python
import httpx

async def fetch_external_weather(city: str) -> str:
    """
    Fetches the current weather for a city from an external weather API.
    """
    url = f"https://api.weatherapi.com/v1/current.json"
    params = {"key": "YOUR_API_KEY", "q": city}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            temp = data.get("current", {}).get("temp_c")
            cond = data.get("current", {}).get("condition", {}).get("text")
            return f"The current temperature in {city} is {temp}°C with {cond}."
        else:
            return f"Error: Failed to fetch weather data (HTTP {response.status_code})."
```

---

## 8. A2A, MCP, and Secret Management

### 8.1 Agent-to-Agent (A2A) Delegation & Security Enforcement
All agent-to-agent communication (including Host-to-Subagent and Subagent-to-Subagent) MUST strictly adhere to the security whitelist provided by the platform.

* **Strict Context-Based Whitelisting:**
  To prevent data leakage and unauthorized access across hubs, organizations, or users, agents MUST NOT query Firestore directly to discover or consult other agents. Instead:
  1. The Platform backend resolves the list of accessible agents based on the active user session and organization/hub membership.
  2. This resolved list is injected into the caller's context payload under the key `accessible_agents`.
  3. The `discover_agents` and `consultAgent` tools filter and execute queries **solely** within this context-inherited `accessible_agents` list. If a target agent's ID is not present in `accessible_agents`, the tool must fail immediately and reject the request with a clear access error.
* **Subagent-to-Subagent Delegation Limits:**
  Subagents are allowed to discover and consult other subagents, but they are subject to the same strict `accessible_agents` boundaries. If Subagent A wants to call Subagent B, it must import the standard `consultAgent` and `discover_agents` tools, which will resolve B against the same `accessible_agents` array propagated down from the platform.
* **GCP Service Account Scopes (The Execution Firewall):**
  To safeguard execution, every GEAP agent runs under a Google Cloud service account with tightly-scoped IAM privileges. When an agent calls `consultAgent`, it fetches an OAuth access token matching its runtime service account credentials. Because Vertex AI Reasoning Engines are protected by IAM, the calling agent's service account must have `aiplatform.reasoningEngines.predict` permissions on the target agent's reasoning engine resource. This GCP-level IAM authentication acts as a secondary, cryptographic firewall verifying the delegation path.
  * **Cross-Project (External) A2A Connections:** If the target subagent is located in an external GCP project or managed under a separate organization/tenant registry, the calling service account must be granted the `Vertex AI User` and `Vertex AI Reasoning Engine Predictor` (or custom predict authorization) IAM roles within that external project. Additionally, the target agent's remote resource name (e.g. `projects/{external-project}/locations/{location}/reasoningEngines/{engine_id}`) must be explicitly whitelisted in the platform's `accessible_agents` list.
* **A2A Client Orchestration:**
  Agent delegation is standardized using the native `RemoteA2aAgent` client from the Google ADK, implemented in `consult_agent.py`.
  * **Mechanism:**
    1. The Host Agent or Subagent retrieves the target subagent's `a2aUrl` from the whitelisted `accessible_agents` list in the context payload (falling back to computing the A2A url from `geap_resource_name` if needed).
  2. It generates a Google Cloud access token to authenticate outbound requests.
     > [!IMPORTANT]
     > **Critical Token Resolution Rule inside GEAP Containers:**
     > Inside a remote Vertex AI Reasoning Engine execution container, `google.auth.default()` resolves to the restricted OIDC Workload Identity credentials. While these credentials can authenticate internal model predictions, they are restricted from making general outbound GCP HTTP/REST requests (like calling other reasoning engines).
     > Therefore, token generation MUST query the local GCE Metadata Server first to obtain the VM tenant service account token (which has the necessary `roles/aiplatform.user` scope):
     > * **Primary lookup:** Query `http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token`.
     > * **Local fallback:** Use `google.auth.default()` *only* if the metadata server is unreachable (for local testing).
  2b. **A2A Card Resolution Route Formatting (v1beta1):**
      Because the reasoning engine's A2A routing endpoints (e.g., `/a2a/v1/card`) are **not** exposed on the GA `/v1/` gateway (returning a `404 Not Found`), the client URL must be formatted to use the `/v1beta1/` endpoint.
      To prevent other developers or AI tools from blindly trying to "upgrade" this block back to `v1`, developers **MUST** leave a clear warning comment above the formatting logic:
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
  3. It instantiates `RemoteA2aAgent(name, agent_card=card_url)` passing an `httpx.AsyncClient` pre-configured with the bearer token.
  4. It executes the request within a dummy `InvocationContext` and `Session` wrapper, enabling native SSE streaming and state resolution.
  5. It parses the final response, intercepting any Lego widget or action directives.
* **Agent Discovery:** The Host Agent or Subagent can query the local list using `discover_agents(query)` to search and filter registered A2A subagents dynamically.
* **A2A Invocation Example:** To consult a subagent inside a tool, call the `consultAgent` function:
```python
from app.core.system_tools.consultAgent import consultAgent

async def check_user_todos(query: str) -> str:
    """
    Checks the user's todo list using the todo subagent.
    """
    # Calls the whitelisted A2A subagent
    result = await consultAgent(agentId="todo-agent", query=query)
    return result
```
* **Parallel Execution:** To query multiple subagents concurrently, use `run_agent_parallel(requests)` which executes multiple queries via `asyncio.gather`:
```python
from app.core.system_tools.consultAgent import consultAgent
import asyncio

async def fetch_aggregated_info(query: str) -> str:
    """
    Fetches info from both todo-agent and knowledge-agent in parallel.
    """
    todo_task = consultAgent(agentId="todo-agent", query=query)
    info_task = consultAgent(agentId="knowledge-agent", query=query)
    
    todo_res, info_res = await asyncio.gather(todo_task, info_task)
    return f"Todos:\n{todo_res}\n\nInfo:\n{info_res}"
```

### 8.2 Model Context Protocol (MCP) Integration
* **No Monolithic Tool Registry:** There is no longer a centralized backend tool orchestrator or `ToolRegistry` managing MCP server processes.
* **Implementation:** If an agent requires MCP tool functionality:
  * **Option A (Preferred):** Convert the MCP tools into standard Python functions and place them directly inside the agent's `scripts/` folder.
  * **Option B:** Write an outbound HTTP/SSE client within a tool in `scripts/` that connects to a hosted remote MCP server.

### 8.3 Secret and API Key Management
For external API integration, agents handle credentials based on their lifecycle scope:
* **System-Level Secrets:** For global/system credentials (e.g. general GCP credentials), utilize Google Cloud Secret Manager or pass environment variables during deployment.
* **User/Org-Level Secrets (OAuth Tokens, Stripe Keys, etc.):** 
  1. The central Hubscape backend handles OAuth callback/credential setup and saves the resulting secret or token to Firestore under a scoped path (e.g., `platform_users/{userId}/tokens/{agentId}` or `organizations/{orgId}/tokens/{agentId}`).
  2. The GEAP agent reads these secrets dynamically during tool execution using `hubscape_adk.get_context()`.
  3. This ensures agents remain stateless and secure, never hardcoding credentials in their source code.

### 8.4 Google Search Grounding (Websearch)
* **Legacy Toggle:** In the old system, `allow_web_search` was a Firestore toggle that dynamically injected a backend-orchestrated `web_search` tool. This is **no longer supported**.
* **GEAP Pattern:** Web search capabilities must be explicitly configured inside the agent's code repository.
* **Option A (Native Vertex AI Search Grounding):** Import and add the native Google Search tool directly to the agent's tools configuration in `agent.py`:
```python
from vertexai.preview.generative_models import Tool, grounding

google_search_tool = Tool.from_google_search_retrieval(
    grounding.GoogleSearchRetrieval()
)
# Append to your tools configuration
self.config.tools = load_local_tools(scripts_dir) + [google_search_tool]
```
  *Note:* Make sure `google-cloud-aiplatform` is included in your `pyproject.toml` dependencies.
* **Option B (Custom Search Tool):** Create a custom `web_search.py` function tool inside the `scripts/` folder that queries a search service (like Google Custom Search, Serper, or Firecrawl) and returns formatted search results. This is preferred if you need custom filtering, specific domain indexing, or precise API key budget controls.

### 8.5 Alternative and Non-Gemini Model Support
While the platform defaults to Google Gemini models (e.g. `gemini-2.5-flash`), the underlying `google-adk` framework supports multiple LLM backends and providers:
* **Vertex AI Model Garden Endpoints:** Fine-tuned Gemini models or third-party models hosted on Vertex can be queried using their full GCP resource path (e.g., `projects/{project}/locations/{location}/endpoints/{endpoint_id}`). The ADK `Gemini` backend automatically resolves this regex pattern.
* **Alternative LLM Providers (OpenAI, Claude, etc.):** 
  * **LiteLLM Bridge:** ADK integrates `LiteLlm` to support alternative providers. Prepend the provider prefix to the model string (e.g. `openai/gpt-4o` or `groq/llama-3`).
  * **Anthropic Support:** ADK provides a native `Claude` backend (`from google.adk.models.anthropic_llm import Claude`) supporting `claude-3-.*` models routing either directly to Anthropic or via Vertex AI.
  * **Requirements:**
    1. Add `google-adk[extensions]` or individual provider SDKs (e.g. `litellm`, `anthropic`) to your agent's `pyproject.toml` dependencies.
    2. Configure credentials (such as `OPENAI_API_KEY`) as system-level secrets via GCP Secret Manager or container environment variables.

### 8.6 Vertex RAG Retrieval and Tenant Scoping Isolation
To query internal knowledge bases registered in Vertex AI RAG Corpora, agents use a Vertex RAG service client tool (e.g. `search_knowledge.py`).

* **Metadata Field Requirement (v1beta1 client):**
  When performing RAG retrievals, the agent **MUST** import `google.cloud.aiplatform_v1beta1` instead of the GA `v1` client:
  ```python
  from google.cloud import aiplatform_v1beta1
  ```
  *Reason:* In the GA `v1` client schema, the `RagChunk` object completely omits the `file_id` and `chunk_id` metadata fields. Without `file_id`, the agent cannot cross-reference the retrieved chunk against the platform's Firestore database to verify tenant ownership boundaries (`hub_id` / `org_id` checks). Swapping to the `v1beta1` client is required to fetch these fields.
* **Reviewer Comment Mandate:**
  To prevent future developers or automated tools from blindly upgrading this import statement to `v1`, you **MUST** place a clear explanatory comment block directly above the import statement:
  ```python
  # NOTE: Using v1beta1 specifically for RAG retrieval because the GA v1 
  # RagChunk schema lacks the file_id and chunk_id metadata fields required 
  # for our Firestore tenant isolation and validation checks.
  from google.cloud import aiplatform_v1beta1
  ```

---

## 9. Decoupled Skill Architecture & Framework Interoperability

To support varying developer preferences and local tools, Hubscape utilizes a **Decoupled Skill Architecture**. 

### 9.1 The Pure Skill Principle
An agent's core intelligence—its prompt instructions (`SKILL.md`), tools (`scripts/`), and support manuals (`references/`)—is completely decoupled from the Python execution framework. The main Python entry point (`agent.py` or `main.py`) acts merely as a lightweight configuration loader.

### 9.2 Interoperable SDK Runtimes
Because GEAP discovers and registers agents via the standard GCP Vertex AI Reasoning Engine registry, the central Hubscape backend treats remote agent containers as black boxes. As long as the deployed Python class exposes the standard `.query(question: str, context: dict = None) -> str` interface, the platform can route queries to it. 

We utilize `google-adk` as the standard, platform-wide SDK:
* **`google-adk`**: Standard framework for both Method A (Flat) and Method B (Segregated) layouts. This allows compiling and loading skills into a production-friendly runner, and running them locally using `agents-cli playground`.

### 9.3 Structuring for Multi-Agent Support
To ensure a skill directory can be run easily, maintain a clear partition:
1. Keep the prompt instructions (`SKILL.md`) and python tool files (`scripts/`) co-located inside a modular folder (e.g. `skills/my-skill/` or at the `app/` directory).
2. Configure the production deployment shell `pyproject.toml` dependencies and manifest.
3. Use the `agents-cli` tool in your agent's directory to execute local tests and playground features.







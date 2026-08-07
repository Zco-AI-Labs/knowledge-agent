# Chapter 10: GEAP Platform Manual

This manual serves as the technical reference for configuring and maintaining specialized AI agents deployed as cloud-native **Vertex AI Reasoning Engines** under the **Gemini Enterprise Agent Platform (GEAP)**.

---

## 1. Core Architecture

Hubscape utilizes a **decoupled cloud-native agent architecture**:
* **Backend as a Proxy:** The Python backend (`backend_python`) does not execute agent loops. It acts as an API proxy relay, receiving messages at `/api/host/chat`, constructing context payloads, and querying the remote GEAP agent via HTTP REST POST.
* **Vertex AI Reasoning Engines:** All specialized agents are packaged as Python classes, registered with the Vertex AI SDK, and run inside containerized Google Cloud environments.
* **Stable Identity:** Each agent is assigned a stable, deterministic UUID calculated from its GitHub repository URL. This UUID is embedded in the agent's Vertex AI description as `[agent_uuid: <uuid>]` and is synced to the Firestore `agents` collection to manage access whitelists.

---

## 2. Directory Structure & Layout Options

We support two layout methodologies depending on the agent's complexity and scalability requirements. This template is pre-configured to use **Method B** by default.

### 2.1 Method A: Flat / Code-Centric Layout
Recommended for simple, single-purpose agents with few tools. Prompts and tools are defined directly within the `app/` Python package.
* Prompt lived in `prompt.py` and tools are defined directly inside `tools.py`.

### 2.2 Method B: Segregated / Decoupled Layout (Template Standard)
Recommended for complex, production-grade agents. Prompts are kept in a clean markdown file (`SKILL.md`), and tools are separated into single-purpose scripts within the `scripts/` directory under `app/`.

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

---

## 4. The Four Pillars of a GEAP Agent

### Pillar 1: `SKILL.md` (Metadata & System Prompt)
* **Dynamic Ingestion:** The `agent.py` script automatically reads `SKILL.md`, strips the frontmatter, and sets the remaining markdown as the agent's system instructions (`CustomSystemInstructions`).
* **Description Sync:** The `description` field in the frontmatter is critical. The platform's central Host Agent uses this description to semantically route user requests to this subagent.

### Pillar 2: `agent.py` (The Loop & Trajectory)
Implements the main Reasoning Engine interface. It instantiates `google.adk.Agent` and handles session trajectory persistence back to Firestore.

### Pillar 3: `scripts/` (Tool Implementations)
Each Python file in the `scripts/` folder defines a single callable function. The name, signature (types), and docstring are automatically parsed to form the model's tool schema.

### Pillar 4: `hubscape_adk.py` (Database Scoping & Context)
A standardized, lightweight module that imports credentials and connects directly to Firestore, allowing tools to read, write, and delete data within isolated scopes (`user`, `hub`, `org`).

---

## 5. Client Action Directives

Agents can trigger client-side actions (like opening UI panels or switching tabs) by appending action dictionaries to `context.actions` during tool calls.
* **`OPEN_ADMIN_WIDGET`**: Triggers configuration UI.
* **`OPEN_AGENT_WIDGET`**: Triggers rendering of a custom Lego UI widget.
* **`CLOSE_AGENT_WIDGET`**: Closes the active Lego widget or iframe panel.
* **`SET_SUGGESTIONS`**: Changes conversation quick-replies.
* **`SWITCH_HUB`**: Changes active Hub navigation.
* **`OPEN_EXTERNAL_LINK`**: Redirects to external URLs.
* **`END_CALL`**: Ends live telephony/voice session.

---

## 6. Lego Widget System & Action Routing

* **Containerized Packaging Rule:** All widget JSON templates **MUST** be placed in `app/ui/widgets/` (e.g. `app/ui/widgets/task_list.json`). Files placed outside the `app/` folder are omitted from the built docker container. The platform checks `app/ui/widgets/` first (ADK standard) and falls back to `app/widgets/` (legacy GEAP standard) if not found.
* **Variable Replacement:** The library automatically parses the loaded JSON file and replaces instances of the `{{agent_id}}` placeholder with the active agent's UUID at runtime.
* **Pure Agentic Form Protocol:** Because remote GEAP containers cannot receive direct inbound HTTP POST requests, all widget interaction (button clicks, form submissions) is routed asynchronously inside the chat stream using standard `agent://` or `chat://` protocols.

---

## 7. Agent Packaging & Deployment

* **Dependency Definition (`pyproject.toml`):** All package dependencies are managed in `pyproject.toml` (using the `uv` package manager).
* **Developer Configuration (`config.json`):** Developer-defined custom configurations (under the `create_params` key) are stored in `config.json` in the root of the repository. This file is Git-tracked and preserved across updates.
* **Directory Configuration (`agents-cli-manifest.yaml`):** The deployment configuration is declared in `agents-cli-manifest.yaml` in the root of the repository. During deployment, parameters from `config.json` are automatically merged into this file by `deploy.py`.
* **Staging Bucket Isolation:** Staging bucket builds isolate artifact objects by display name (e.g. `gs://hubscape-geap-reasoning-engines/todo-agent/`).
* **Keyless OIDC Wildcard Authentication:** The GitHub Actions workflow uses keyless authentication via Google Cloud Workload Identity Federation with a pool-level wildcard binding.
* **The `debug_env` Diagnostic Hook:** All GEAP agents must implement a `debug_env` hook inside their `query` method. If the agent receives the exact question `"debug_env"`, it should return a diagnostic string listing files in its runtime path, service account configuration, and tool import errors.

### Developer Configuration Profiles (`config.json`)

Here are three examples of how different agents are configured using different parameter values:

#### Example 1: Knowledge Agent (RAG Corpus Datastore)
Used for agents connecting to a Google Vertex AI RAG Corpus for document search.
```json
{
  "agents-cli-manifest": {
    "create_params": {
      "deployment_target": "agent_runtime",
      "is_a2a": true,
      "session_type": "in_memory",
      "cicd_runner": "skip",
      "include_data_ingestion": true,
      "datastore": "projects/hubscape-geap/locations/us-central1/ragCorpora/8331289874728484864",
      "agent_guidance_filename": "GEMINI.md"
    }
  }
}
```

#### Example 2: Onboarding Agent (Vertex AI Session Service)
Used for agents utilizing cloud-managed sessions.
```json
{
  "agents-cli-manifest": {
    "create_params": {
      "deployment_target": "agent_runtime",
      "is_a2a": true,
      "session_type": "vertex_ai_session_service",
      "cicd_runner": "skip",
      "include_data_ingestion": false,
      "datastore": "none",
      "agent_guidance_filename": "GEMINI.md"
    }
  }
}
```

#### Example 3: Host (Vertex AI Memory Bank)
Used for orchestrators using memory banks and data ingestion.
```json
{
  "agents-cli-manifest": {
    "create_params": {
      "deployment_target": "agent_runtime",
      "is_a2a": true,
      "cicd_runner": "skip",
      "include_data_ingestion": true,
      "datastore": "vertex_ai_memory_bank",
      "agent_guidance_filename": "GEMINI.md"
    }
  }
}
```

---

## 8. Google Search Grounding, Maps Grounding & Dual Spatial Context

* **`config.json` Toggles**: Agent developers can enable native Google search and maps grounding by setting boolean flags in their agent repository's `config.json`:
  ```json
  {
    "allow_web_search": false,
    "allow_google_maps": false,
    "mcp_servers": {}
  }
  ```
  *(Both options default to `false` in `hubscape-agent-template`).*

* **Native ADK Tools**: `app/agent.py` dynamically resolves these flags at boot and registers:
  - **Web Search (`allow_web_search: true`)**: `from google.adk.tools import google_search` (`GoogleSearchTool`). Use for general web search, factual Q&A, and **all navigation queries** (driving distance in miles, travel times, transit routes).
  - **Google Maps (`allow_google_maps: true`)**: `from google.adk.tools import google_maps_grounding` (`GoogleMapsGroundingTool`). Reserved for **dedicated spatial/place discovery agents** (nearby amenities, place ratings, business hours, map pin widgets). Do NOT use `allow_google_maps` for general driving distance/travel time queries.

* **Dual Spatial Context Protocol**:
  When request payloads pass spatial anchors in context (`user_location`, `hub_location`), `GEAPAgentWrapper` formats an instruction header for Gemini 2.x models:
  ```text
  [SPATIAL & LOCATION CONTEXT]
  📍 User Live Location: Miami International Airport (Lat: 25.7959, Lng: -80.2870)
  🏢 Active Hub Location: Miami HQ - 100 Brickell Ave (Lat: 25.7617, Lng: -80.1918)
  ```
  This dual anchor context automatically propagates down to all subagents via the A2A protocol.

* **Automatic Grounding Tool Isolation (Vertex AI 400 Prevention):** Vertex AI forbids mixing built-in grounding extensions (`google_search` or `google_maps`) with custom Python function declarations in a single `tools` array. `GEAPAgentWrapper` in `hubscape-agent-template` handles this automatically under the hood: when grounding toggles are enabled in `config.json`, the wrapper isolates grounding tools from custom function declarations on every turn, avoiding `400 INVALID_ARGUMENT` errors without requiring custom subagent code.

---

## 9. A2A, MCP, and Secret Management

* **Agent-to-Agent (A2A) Delegation & Security Enforcement:** All agent-to-agent communication (including Host-to-Subagent and Subagent-to-Subagent) MUST strictly adhere to the security whitelist provided by the platform under `accessible_agents` in the context payload.
* **A2A Client Token Resolution Rule:** Inside a remote Vertex AI Reasoning Engine execution container, `google.auth.default()` resolves to the restricted OIDC Workload Identity credentials. To make outbound A2A requests, token generation must query the local GCE Metadata Server: `http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token` first to obtain the VM tenant service account token.
* **A2A Card Resolution Route Formatting (v1beta1):** Because the reasoning engine's A2A routing endpoints (e.g., `/a2a/v1/card`) are not exposed on the GA `/v1/` gateway, the client URL must format to use the `/v1beta1/` endpoint:
  ```python
  # NOTE: Using v1beta1 specifically for the A2A handshake gateway because 
  # Vertex AI Reasoning Engine's A2A routing endpoints (e.g. /a2a/v1/card)
  # are not exposed on the GA /v1/ endpoints (returning a 404 Not Found).
  card_url = a2a_url.replace("/v1/", "/v1beta1/")
  ```
* **Vertex RAG Retrieval and Tenant Scoping Isolation:** When performing RAG retrievals, the agent **MUST** import `google.cloud.aiplatform_v1beta1` instead of the GA `v1` client:
  ```python
  # NOTE: Using v1beta1 specifically for RAG retrieval because the GA v1 
  # RagChunk schema lacks the file_id and chunk_id metadata fields required 
  # for our Firestore tenant isolation and validation checks.
  from google.cloud import aiplatform_v1beta1
  ```

---

## 9. OTP Phone Verification Services

To verify phone numbers, agents can use the platform's centralized OTP service via:
1. `context.send_otp(phone_number)`
2. `context.verify_otp(phone_number, code)`

### Local Dev Bypass
When running locally without a backend URL:
* `send_otp` simulates success and logs a warning.
* `verify_otp` accepts code `123456` as always valid.

---

[Next Chapter: Unified HTTP Serving Architecture](CHAPTER_11_UNIFIED_HTTP_SERVING_ARCHITECTURE.md) | [Previous Chapter: GEAP Developer Workflow](CHAPTER_9_GEAP_DEVELOPER_WORKFLOW.md)

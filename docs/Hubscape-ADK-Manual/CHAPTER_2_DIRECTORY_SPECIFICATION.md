# Chapter 2: Directory Specification & Ingestion Pipeline

To deploy seamlessly, every custom agent must comply with the standardized workspace directory structure. This structure separates package dependencies from the core agent business logic.

---

## 1. Directory Structure Specifications

A complete Hubscape Agent repository consists of the following file arrangement:

```text
my_agent_project/
├── pyproject.toml              # REQUIRED: Python dependencies and metadata (workspace root)
├── config.json                 # REQUIRED: Developer-defined custom manifest parameters
├── agents-cli-manifest.yaml    # REQUIRED: Deployment configurations (updated dynamically by deploy.py)
├── Dockerfile                  # NEW: Container build specification for FastAPI app
└── app/                        # REQUIRED: Ingested agent package directory
    ├── __init__.py             # REQUIRED: Package entry, exposes standard imports
    ├── agent.py                # REQUIRED: Instantiates google.adk.Agent and registers tools
    ├── SKILL.md                # REQUIRED: Contains system prompts / instructions (Single Source of Truth)
    ├── scripts/                # REQUIRED: Contains standalone Python tool scripts
    ├── static/                 # OPTIONAL: Contains static frontend widget pages (HTML/CSS/JS)
    ├── ui/widgets/             # OPTIONAL: Contains custom declarative Lego widget JSON configurations
    ├── core/                   # Platform core code (off-limits to editing)
    │   ├── fast_api_app.py     # Main FastAPI entry point (REST, A2A, Reasoning Engine)
    │   ├── agent_runtime_app.py# Entry point loaded by Agent Runtime
    │   ├── geap_agent_wrapper.py# Conformance wrapper for Vertex AI Reasoning Engine SDK
    │   └── hubscape_adk.py     # Platform database/GCS/UI context adapter
    └── app_utils/              # Platform helper utility modules
        ├── services.py         # Shared session/artifact service registry (shared://)
        ├── a2a.py              # Inbound/outbound A2A JSON-RPC setup
        └── reasoning_engine_adapter.py # Endpoint adapter for Vertex AI Playground
```

---

## 2. Ingestion & The "Pure Agent Principle"

The Hubscape deployment pipeline enforces the **Pure Agent Principle**:
* **Container Isolation:** In a production cloud environment, the deployment engine parses the root configurations (`pyproject.toml`, `agents-cli-manifest.yaml`) to build the container environment, but copies **only the `app/` folder** into the runtime engine.
* **Strict Exclusions:** Any files outside the `app/` folder (such as root-level scripts, databases like `local_db.json`, `.env` files, or local documentation folders) are stripped and ignored. 
* **Static Assets:** Any assets or HTML pages required for visual widgets must reside inside `app/static/` to ensure they are ingested and accessible under the URL:
  `/api/agents/{agent_id}/static/{filename}`

---

## 3. Package Configurations

* **`pyproject.toml`:** Declares dependencies using the modern `uv` manager. Do not write custom shell installation logic; all packages must be listed in `pyproject.toml` to build successfully.
* **`config.json`:** A git-tracked configuration file containing developer-defined custom parameters (under `create_params` nested in `"agents-cli-manifest"`). This file is preserved when `hubscape-adk -u` runs (which overwrites `agents-cli-manifest.yaml` with the default template). During deployment, `deploy.py` merges `config.json` parameters back into `agents-cli-manifest.yaml`.
* **`agents-cli-manifest.yaml`:** Mapped at creation time to establish options like:
  * `agent_directory: "app"`
  * `base_template: "adk"`
  * `deployment_target: "agent_runtime"` or `reasoning_engine`

---

[Next Chapter: Tool Scripts & Prompt Structure](CHAPTER_3_TOOLS_AND_PROMPTS.md) | [Previous Chapter: Overview](CHAPTER_1_OVERVIEW.md)

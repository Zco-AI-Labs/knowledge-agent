# GEAP Agent Developer Workflow

This document outlines the standard operating procedure (SOP) for developing, testing, and deploying specialized agents as Vertex AI Reasoning Engines (GEAP) for the Hubscape platform.

---

## 🏗️ Workflow Overview

```mermaid
graph TD
    A[Create Standalone Agent Repo] --> B[Implement logic inside agent.py & scripts/]
    B --> C[Configure Google Cloud credentials locally]
    C --> D[Run local tests & verify logic]
    D --> E[Deploy agent via deploy.py script]
    E --> F[sync GEAP Agent Registry in Hubscape Admin]
```

---

## 🚀 Step-by-Step Developer Journey

### Step 1: Initialize the Agent Repository
GEAP agents are developed in separate standalone repositories rather than as subfolders inside the core backend.
1. Create a new git repository named `core-agents/hubscape-agent-[name]` under the `Zco-AI-Labs` GitHub organization.
2. Clone the template boilerplate or configure the project directory with:
   * `pyproject.toml`             # Project dependencies (managed via uv)
   * `agents-cli-manifest.yaml`   # Manifest configuration
   * `deploy.py`                  # Subprocess wrapper to run agents-cli deploy
   * `app/`                       # Agent application directory containing python code
     ├── __init__.py             # REQUIRED: Package initialization
     ├── agent.py                 # REQUIRED: Main agent logic, App export
     ├── core/                   # Platform core code (off-limits to editing agent)
     │   ├── agent_runtime_app.py # Entry point loaded by Agent Runtime
     │   ├── geap_agent_wrapper.py # Conformance wrapper class for Vertex AI Reasoning Engine SDK
     │   └── hubscape_adk.py      # Lightweight context/DB adapter (copied verbatim)
     ├── SKILL.md                 # REQUIRED: YAML identity metadata + Markdown instructions (for Method B)
     ├── scripts/                 # REQUIRED: Python function tools (for Method B)
     └── app_utils/               # REQUIRED: env_resolver and vertex_gemini helpers

### Step 2: Set Up Local Environment & Authentication
Vertex AI Reasoning Engines run in Google Cloud and access Firestore. For local development and testing, you must authenticate to Google Cloud using **Application Default Credentials (ADC)**.

1. Ensure the Google Cloud SDK (`gcloud` CLI) is installed.
2. Authenticate your terminal:
   ```bash
   gcloud auth login
   gcloud auth application-default login
   ```
3. Set the required environment variables in your local `.env` file:
   ```bash
   PROJECT_ID="hubscape-geap"
   GCP_PROJECT_ID="hubscape-geap"
   GCP_LOCATION="us-central1"
   ```

### Step 3: Implement and Structure the Agent
1. **System Instructions:** Add the agent's identity, whitelisting rules, and behavioral prompt to `SKILL.md` inside `app/` (for Method B).
2. **Tools:** Add python scripts to `app/scripts/` (e.g. `app/scripts/add_task.py`) or define them in `app/tools.py`. Make sure to write descriptive docstrings and parameter type hints so Vertex AI can generate the schemas automatically.
3. **Agent Class:** Update `app/agent.py` to define the agent. You **MUST** instantiate `google.adk.Agent` (exposing it as the global `root_agent` symbol), define `geap_agent_wrapper_app` (or equivalent wrapper class instance), and export `app = App(root_agent=root_agent, name="app")`. Use `get_model(...)` and `get_project_id()` helpers to resolve environment values dynamically and prevent cross-environment leakage.
4. **Decommissioned Inbound API Routes (`api.py`):** Do NOT place `api.py` in your agent directory to mount custom HTTP routes. GEAP sandboxed containers do not support public inbound routing. All webhooks and OAuth redirects must be implemented on the central platform backend, which writes to Firestore for the agent to query via `hubscape_adk.py`.

### Step 4: Run Local Standalone Tests
You can run standalone Python scripts or `agents-cli playground` to test tool execution and Firestore query scopes. Since `hubscape_adk.py` connects to the firestore client using your ADC token, it will perform real database reads and writes scoping documents to the active project.
* Use a test database file or isolate dev scopes in your tests.
* Run code checks and playground:
  ```bash
  agents-cli playground
  ```

### Step 5: Package and Deploy to GEAP
The `deploy.py` script packages the class and dependencies defined in `pyproject.toml` and uploads them as a Reasoning Engine to Google Vertex AI using `agents-cli deploy`.

1. Run the deployment script:
   ```bash
   python deploy.py
   ```
   This will execute `agents-cli deploy` and output the remote resource path of the deployed agent:
   `GEAP Resource Name: projects/1097730318341/locations/us-central1/reasoningEngines/1234567890`

   > [!IMPORTANT]
   > Ensure that `agents-cli-manifest.yaml` lists `agent_directory: "app"`. All dependencies must be correctly declared in `pyproject.toml`. The old Python `extra_packages` deployment method is deprecated.

### Step 6: Synchronize with Hubscape Platform
Once the agent is deployed to GCP:
1. Log in to the Hubscape Platform Admin console.
2. Trigger the Auto-Discovery Sync endpoint `/api/agents/sync` (or click "Sync GEAP Registry" in the Admin UI).
3. The platform will query GCP, discover your new agent, register a shadow document in Firestore, and map it to whitelisted Hubs based on its metadata.

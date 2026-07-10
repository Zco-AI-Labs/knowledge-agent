# Hubscape ADK: Agent Developer Workflow

This document outlines the standard operating procedure (SOP) for custom agent developers utilizing the **Hubscape ADK CLI** to create, test, and deploy custom agents under the package-based declarative structure.

---

## 🚀 Step-by-Step Developer Journey

### Step 1: Install the ADK CLI
Make sure you have Python 3.10+ and `pipx` installed:
```bash
pipx install git+https://github.com/Zco-AI-Labs/Hubscape-ADK-Studio.git
```

### Step 2: Request Registration Credentials
Request a **Developer Personal Access Token (PAT)**, an **Agent UUID**, and a **Deployment Token** from your Hubscape Org Administrator.

### Step 3: Initialize the Agent Repository
1. Go to the template repository and click **"Use this template"** to create your agent's GitHub repository.
2. Clone it to your workspace:
   ```bash
   hubscape-adk clone https://github.com/Zco-AI-Labs/your-agent-repo
   ```
3. To update the `hubscape-adk` tool to the latest version:
   ```bash
   hubscape-adk -u
   ```

### Step 4: Boot the Sandbox & Run Setup Wizard
1. Launch the sandbox server from the root of your cloned agent directory:
   ```bash
   hubscape-adk
   ```
   This opens the Holodeck console in your web browser (e.g. **http://localhost:8090**).
2. Connect to Staging or Skip to Sandbox to prototype using local mock data.
3. Configure your Google Gemini API key as `GEMINI_API_KEY=your_key_here` in `.env` to enable mock Host AI emulation.

### Step 5: Implement the Agent

To implement the agent's functionality:

1. **Workspace & Agent Structure**:
   * **`pyproject.toml`**: List package dependencies and python configs (located at the workspace root).
   * **`app/`** (Agent package folder):
     * **`agent.py`**: Instantiate `google.adk.Agent` and load tools dynamically from `scripts/` using `load_local_tools()`. Set the agent ID, name, and description here.
     * **`SKILL.md`**: Define your system instruction string (prompts).
     * **`scripts/`**: Place standalone python files here to implement tool functions. Filenames must match function names. Type hints and docstrings are parsed to build Gemini schemas automatically.
     * **`ui/widgets/`**: Place any custom JSON templates for Lego UI widget rendering here.

### Step 6: Test and Validate
1. Talk to your agent locally via the Holodeck client.
2. Switch between **Sandbox (Local)** and **Transceiver (Live)** modes to verify mock and live database operations.


### Step 7: Commit and Push
Once tested, commit your code and push to your remote repository:
```bash
git add .
git commit -m "feat: complete Spotify agent logic using new ADK standard"
git push origin main
```

### Step 8: Configure GitHub Secrets & Deploy
1. Add `HUBSCAPE_DEPLOY_TOKEN` and any other custom secrets to your GitHub repository secrets.
2. Run the **Deploy Agent to Hubscape** workflow from the Actions tab.

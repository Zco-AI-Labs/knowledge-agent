import os
import sys
import subprocess
import shutil

import re

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "hubscape-geap")
LOCATION = os.getenv("GCP_LOCATION", "us-central1")

# Helper to extract the new agent name from app/agent.py
def get_new_agent_name():
    agent_py_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "agent.py")
    if os.path.exists(agent_py_path):
        try:
            with open(agent_py_path, "r", encoding="utf-8") as f:
                code = f.read()
            match = re.search(r'(?:AdkAgent|Agent)\([\s\S]*?name\s*=\s*["\']([^"\']+)["\']', code)
            if match:
                return match.group(1).replace('_', '-')
        except Exception as e:
            print(f"Warning: Failed to parse app/agent.py for name. Error: {e}")
            
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from app.agent import root_agent
        return root_agent.name.replace('_', '-')
    except Exception as e:
        print(f"Warning: Failed to import root_agent. Error: {e}")
        
    return "custom-agent"

# Helper to sync the agent name to all static config files
def sync_agent_name(new_name):
    project_dir = os.path.dirname(os.path.abspath(__file__))
    
    old_name = None
    pyproject_path = os.path.join(project_dir, "pyproject.toml")
    if os.path.exists(pyproject_path):
        try:
            with open(pyproject_path, "r", encoding="utf-8") as f:
                content = f.read()
            match = re.search(r'^name\s*=\s*["\']?([^"\'\n]+)["\']?', content, re.MULTILINE)
            if match:
                old_name = match.group(1)
        except Exception as e:
            print(f"Warning: Failed to read old name from pyproject.toml. Error: {e}")
            
    if not old_name:
        old_name = "custom-agent"
        
    if old_name == new_name:
        print(f"Agent name is already synchronized as '{new_name}'.")
        return
        
    print(f"Synchronizing agent name: '{old_name}' -> '{new_name}'...")
    
    replacements = {
        "agents-cli-manifest.yaml": [
            (rf'^name:\s*["\']?{re.escape(old_name)}["\']?', f'name: "{new_name}"')
        ],
        "pyproject.toml": [
            (rf'^name\s*=\s*["\']?{re.escape(old_name)}["\']?', f'name = "{new_name}"')
        ],
        "uv.lock": [
            (rf'^name\s*=\s*["\']?{re.escape(old_name)}["\']?', f'name = "{new_name}"')
        ],
        os.path.join("app", "SKILL.md"): [
            (rf'^name:\s*{re.escape(old_name)}', f'name: {new_name}')
        ],
        os.path.join("deployment", "terraform", "single-project", "variables.tf"): [
            (re.escape(old_name), new_name)
        ],
        os.path.join("deployment", "terraform", "single-project", "vars", "env.tfvars"): [
            (re.escape(old_name), new_name)
        ]
    }
    
    for relative_path, rules in replacements.items():
        file_path = os.path.join(project_dir, relative_path)
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                updated_content = content
                for pattern, repl in rules:
                    updated_content = re.sub(pattern, repl, updated_content, flags=re.MULTILINE)
                        
                if updated_content != content:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(updated_content)
                    print(f"  Updated {relative_path}")
            except Exception as e:
                print(f"Warning: Failed to update {relative_path}. Error: {e}")

# Resolve the name and run synchronization before deploying
display_name = get_new_agent_name()
sync_agent_name(display_name)

print(f"Deploying {display_name} via native agents-cli...")

agents_cli_path = shutil.which("agents-cli")
if not agents_cli_path:
    venv_bin = os.path.dirname(sys.executable)
    fallback_path = os.path.join(venv_bin, "agents-cli")
    if os.path.exists(fallback_path):
        agents_cli_path = fallback_path
if not agents_cli_path:
    agents_cli_path = "agents-cli"

iam_profile = "sa-standard-agent"
try:
    try:
        from google.cloud import firestore
    except ImportError:
        print("ℹ️ google-cloud-firestore not found. Installing dynamically...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "google-cloud-firestore"], check=True)
        from google.cloud import firestore

    db = firestore.Client(project=PROJECT_ID)
    docs = db.collection("agents").where("name", "==", display_name).limit(1).stream()
    doc = next(docs, None)
    if doc:
        iam_profile = doc.to_dict().get("iam_profile") or "sa-standard-agent"
        print(f"ℹ️ Found agent configuration in Firestore. Binding profile: {iam_profile}")
    else:
        print(f"ℹ️ Agent not found in Firestore. Defaulting to profile: {iam_profile}")
except Exception as e:
    print(f"⚠️ Could not fetch agent profile from Firestore ({e}). Defaulting to profile: {iam_profile}")

cmd = [
    agents_cli_path, "deploy",
    "--project", PROJECT_ID,
    "--region", LOCATION,
    "--service-name", display_name,
    "--service-account", f"{iam_profile}@{PROJECT_ID}.iam.gserviceaccount.com",
    "--no-confirm-project"
]

env = os.environ.copy()
venv_bin = os.path.dirname(sys.executable)
env["PATH"] = f"{venv_bin}{os.path.pathsep}{env.get('PATH', '')}"

print(f"Executing: {' '.join(cmd)}")
subprocess.run(cmd, env=env, check=True)
print("🎉 Deployment completed successfully!")

# Trigger dynamic registry sync on local backend if running
try:
    import urllib.request
    import json
    
    backend_url = os.getenv("HUBSCAPE_BACKEND_URL", "http://localhost:8000")
    secret = os.getenv("HUBSCAPE_HMAC_SECRET", "dev_secret_key_dont_use_in_prod")
    
    url = f"{backend_url.rstrip('/')}/api/agents/sync"
    req = urllib.request.Request(
        url,
        data=b"",
        headers={
            "X-Hubscape-Secret": secret,
            "Content-Type": "application/json"
        },
        method="POST"
    )
    
    print(f"📡 Triggering immediate agent registry sync on local backend: {url}")
    with urllib.request.urlopen(req, timeout=10) as response:
        res_data = json.loads(response.read().decode())
        print(f"✅ Sync Response: {res_data.get('message', 'Success')}")
except Exception as e:
    print(f"ℹ️ Local backend sync trigger skipped or failed: {e} (Backend might not be running locally)")
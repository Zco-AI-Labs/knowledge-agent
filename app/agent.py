import os
# Force regional Vertex AI routing unconditionally
os.environ.pop("GOOGLE_GENAI_USE_ENTERPRISE", None)
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
import asyncio
import importlib.util
import re
from google.adk import Agent as AdkAgent
from google.adk.runners import Runner
from google.genai import types

def load_local_tools(scripts_dir: str) -> list:
    import sys
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

# 1. Read system prompt instructions from SKILL.md and load tools at module level
runtime_dir = os.path.dirname(os.path.abspath(__file__))
skill_md_path = os.path.join(runtime_dir, "SKILL.md")
system_instruction = "You are a helpful knowledge search assistant."
if os.path.exists(skill_md_path):
    with open(skill_md_path, "r", encoding="utf-8") as f:
        skill_content = f.read()
    system_instruction = re.sub(r"^---.*?---", "", skill_content, flags=re.DOTALL).strip()

scripts_dir = os.path.join(runtime_dir, "scripts")
tools = load_local_tools(scripts_dir)

from app.app_utils.vertex_gemini import get_model

root_agent = AdkAgent(
    model=get_model("gemini-2.5-flash"),
    name='knowledge_agent',
    description='Managed GEAP agent for RAG knowledge searches.',
    instruction=system_instruction,
    tools=tools
)

class KnowledgeAgent:
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
            
            scripts_dir = os.path.join(runtime_dir, "scripts")
            loaded = []
            if os.path.exists(scripts_dir):
                for filename in os.listdir(scripts_dir):
                    if filename.endswith(".py"):
                        loaded.append(filename)
            
            import_errors = []
            if os.path.exists(scripts_dir):
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
                                    pass
                                else:
                                    import_errors.append(f"{filename}: function {module_name} not found or not callable")
                        except Exception as e:
                            import_errors.append(f"{filename}: {str(e)}")
            
            import urllib.request
            sa_email = "Unknown"
            try:
                req = urllib.request.Request(
                    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email",
                    headers={"Metadata-Flavor": "Google"}
                )
                with urllib.request.urlopen(req, timeout=2) as response:
                    sa_email = response.read().decode("utf-8").strip()
            except Exception as e:
                sa_email = f"Error: {e}"
            
            return f"Active Service Account: {sa_email}\nRuntime Dir: {runtime_dir}\nFiles:\n" + "\n".join(files) + "\nScripts dir contents:\n" + "\n".join(loaded) + "\nImport Errors:\n" + "\n".join(import_errors)
        # --- END DEBUG HOOK ---

        import hubscape_adk
        import uuid
        user_id = (context or {}).get("userId") or (context or {}).get("user_id") or "anonymous_user"
        org_id = (context or {}).get("orgId") or (context or {}).get("org_id")
        hub_id = (context or {}).get("hubId") or (context or {}).get("hub_id")
        
        agent_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/Zco-AI-Labs/knowledge-agent"))
        from app.app_utils.env_resolver import get_project_id
        project_id = get_project_id()
        
        remote_ctx = hubscape_adk.RemoteContext(
            user_id=user_id, 
            agent_id=agent_uuid,
            org_id=org_id,
            hub_id=hub_id,
            project_id=project_id,
            raw_context=context
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
                    app_name='knowledge-agent',
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
knowledge_agent_app = KnowledgeAgent()

from google.adk.apps import App
app = App(
    root_agent=root_agent,
    name="app",
)

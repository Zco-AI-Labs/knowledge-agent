import os
import uuid
import importlib.util
import urllib.request
from google.genai import types
from google.adk.runners import Runner
from app.core import hubscape_adk

class GEAPAgentWrapper:
    def __init__(self, agent, app_name: str = None):
        self.agent = agent
        self.app_name = app_name or agent.name.replace('_', '-')
        self.runner = None

    async def query(self, question: str, context: dict = None) -> str:
        core_dir = os.path.dirname(os.path.abspath(__file__))
        runtime_dir = os.path.abspath(os.path.join(core_dir, ".."))
        
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

        user_id = (context or {}).get("userId") or (context or {}).get("user_id") or "anonymous_user"
        org_id = (context or {}).get("orgId") or (context or {}).get("org_id")
        hub_id = (context or {}).get("hubId") or (context or {}).get("hub_id")
        
        agent_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://github.com/Zco-AI-Labs/{self.app_name}"))
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
                    agent=self.agent,
                    app_name=self.app_name,
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

# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import os
# Ensure standard imports share the same module instance
app_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(app_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Extract pyopenssl and monkeypatch PyOpenSSLContext immediately to prevent context mutation errors
try:
    from urllib3.contrib import pyopenssl
    pyopenssl.extract_from_urllib3()
    
    from urllib3.contrib.pyopenssl import PyOpenSSLContext
    def make_safe(func):
        if not func: return func
        def safe_func(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except ValueError as e:
                if "cannot be mutated again" in str(e): return None
                raise
        return safe_func
        
    for prop_name in ["verify_mode", "verify_flags", "options", "minimum_version", "maximum_version"]:
        prop = getattr(PyOpenSSLContext, prop_name, None)
        if prop and prop.fset:
            setattr(PyOpenSSLContext, prop_name, property(prop.fget, make_safe(prop.fset), prop.fdel))
    for method_name in ["load_cert_chain", "load_verify_locations", "set_ciphers", "set_alpn_protocols", "set_default_verify_paths"]:
        method = getattr(PyOpenSSLContext, method_name, None)
        if method:
            setattr(PyOpenSSLContext, method_name, make_safe(method))
except Exception:
    pass

import asyncio
import logging
from typing import Any, Optional, Dict, List, Union

import nest_asyncio
import vertexai
from dotenv import load_dotenv
from a2a.types import AgentCapabilities, AgentCard, AgentExtension, TransportProtocol
from a2a.server.agent_execution import RequestContext
from a2a.server.events.event_queue import EventQueue

from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder
from google.adk.apps import App
from google.adk.artifacts import GcsArtifactService, InMemoryArtifactService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.cloud import logging as google_cloud_logging
from vertexai.preview.reasoning_engines import A2aAgent

from app.core import hubscape_adk
from app.agent import app as adk_app
from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback

# Load environment variables from .env file at runtime
load_dotenv()

def _load_privileges() -> dict:
    import json
    privileges_data = {}
    try:
        app_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(app_dir)
        privileges_path = os.path.join(parent_dir, "privileges.json")
        if os.path.exists(privileges_path):
            with open(privileges_path, "r") as pf:
                privileges_data = json.load(pf)
    except Exception:
        pass
    return privileges_data

def _load_privileges_without_tools() -> dict:
    privileges_data = _load_privileges()
    if not privileges_data:
        return {}
    filtered_data = {}
    if "privileges" in privileges_data:
        filtered_data["privileges"] = {}
        for role_id, role_info in privileges_data["privileges"].items():
            if isinstance(role_info, dict):
                filtered_data["privileges"][role_id] = {
                    k: v for k, v in role_info.items() if k != "tools"
                }
            else:
                filtered_data["privileges"][role_id] = role_info
    else:
        filtered_data = privileges_data
    return filtered_data

class ActionInterceptingEventQueue(EventQueue):
    def __init__(self, target_queue: EventQueue, remote_context):
        super().__init__()
        self.target_queue = target_queue
        self.remote_context = remote_context
        self.accumulated_text = ""
        self.events = []
        self.final_event = None
        self.artifact_event = None

    async def enqueue_event(self, event):
        from a2a.types import TaskStatusUpdateEvent, TaskArtifactUpdateEvent
        if isinstance(event, TaskStatusUpdateEvent):
            if event.final:
                self.final_event = event
                return
            
            # Extract text to accumulate
            if event.status and event.status.message and event.status.message.parts:
                for part in event.status.message.parts:
                    if hasattr(part, "text") and part.text:
                        self.accumulated_text += part.text
            
            self.events.append(event)
        elif isinstance(event, TaskArtifactUpdateEvent):
            self.artifact_event = event
        else:
            # E.g. Task submitted event, enqueue immediately
            await self.target_queue.enqueue_event(event)


class AgentEngineA2aExecutor(A2aAgentExecutor):
    """Custom A2A Executor that intercepts requests to inject RemoteContext."""
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ):
        import json
        import uuid
        from datetime import datetime, timezone
        from app.agent import root_agent
        
        metadata = context.metadata or {}
        
        user_id_resolved = metadata.get("userId") or metadata.get("user_id") or "anonymous_user"
        org_id = metadata.get("orgId") or metadata.get("org_id")
        hub_id = metadata.get("hubId") or metadata.get("hub_id")
        mode = metadata.get("mode") or "none"
        
        agent_name = root_agent.name.replace('_', '-') if root_agent and hasattr(root_agent, "name") else "custom-agent"
        agent_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://github.com/Zco-AI-Labs/{agent_name}"))
        from app.app_utils.env_resolver import get_project_id
        project_id = get_project_id()
        
        remote_ctx = hubscape_adk.RemoteContext(
            user_id=user_id_resolved,
            agent_id=agent_uuid,
            org_id=org_id,
            hub_id=hub_id,
            project_id=project_id,
            raw_context=metadata
        )
        
        interceptor = ActionInterceptingEventQueue(event_queue, remote_ctx)
        
        base_instruction = root_agent.instruction or ""
        
        # Inject Active Session Context securely at the top of the prompt
        session_context = f"""
[ACTIVE SESSION CONTEXT]
- User ID: {user_id_resolved}
- Hub ID: {hub_id or 'none'}
- Organization ID: {org_id or 'none'}
- Interaction Mode: {mode}
"""
        
        # Format and append accessible agents roster
        accessible_agents = metadata.get("accessible_agents", [])
        roster_str = ""
        if accessible_agents:
            roster_str = "\n=== AVAILABLE SUBAGENTS ROSTER ===\n" + "\n".join(
                f"- {a.get('name')} (ID: {a.get('id')}): {a.get('description')}" for a in accessible_agents
            ) + "\n"
            
        root_agent.instruction = f"{session_context}{roster_str}\n{base_instruction}"
        
        try:
            # Enter the context session to ensure all Firestore calls in tools are authenticated
            with hubscape_adk.context_session(remote_ctx):
                await super().execute(context, interceptor)
        finally:
            root_agent.instruction = base_instruction

        # Determine if there are actions to propagate
        has_actions = bool(remote_ctx.actions)
        if has_actions:
            directive_payload = {}
            for action in remote_ctx.actions:
                atype = action.get("type")
                payload = action.get("payload") or {}
                if atype == "OPEN_AGENT_WIDGET":
                    directive_payload = {
                        "directive": "execute_host_tool",
                        "target_tool": "openAgentWidget",
                        "parameters": {
                            "widgetId": payload.get("widgetId"),
                            "widgetConfig": payload.get("widgetConfig"),
                            "data": payload.get("data") or {},
                            "styling": payload.get("styling") or {},
                            "userPreferences": payload.get("userPreferences") or {}
                        },
                        "message": interceptor.accumulated_text or "Displaying agent widget."
                    }
                    break
                elif atype == "OPEN_ADMIN_WIDGET":
                    directive_payload = {
                        "directive": "execute_host_tool",
                        "target_tool": "openAdminWidget",
                        "parameters": {
                            "widgetType": payload.get("widgetType")
                        },
                        "message": interceptor.accumulated_text or "Opening admin widget."
                    }
                    break
                elif atype == "SET_SUGGESTIONS":
                    directive_payload = {
                        "directive": "execute_host_tool",
                        "target_tool": "suggestQueries",
                        "parameters": {
                            "queries": action.get("queries") or []
                        },
                        "message": interceptor.accumulated_text or ""
                    }
                    break
                elif atype == "SWITCH_HUB":
                    directive_payload = {
                        "directive": "execute_host_tool",
                        "target_tool": "switchHub",
                        "parameters": {
                            "hubId": payload.get("hubId")
                        },
                        "message": interceptor.accumulated_text or "Switching hub workspace."
                    }
                    break
                elif atype == "OPEN_EXTERNAL_LINK":
                    directive_payload = {
                        "directive": "execute_host_tool",
                        "target_tool": "openExternalLink",
                        "parameters": {
                            "url": payload.get("url")
                        },
                        "message": interceptor.accumulated_text or "Opening link."
                    }
                    break
                elif atype == "END_CALL":
                    directive_payload = {
                        "directive": "execute_host_tool",
                        "target_tool": "endCall",
                        "parameters": {},
                        "message": interceptor.accumulated_text or "Call ended."
                    }
                    break

            if directive_payload:
                from a2a.types import TaskStatusUpdateEvent, Message, Role, TextPart, TaskStatus, TaskState, TaskArtifactUpdateEvent, Artifact
                
                json_text = json.dumps(directive_payload)
                new_event = TaskStatusUpdateEvent(
                    task_id=context.task_id,
                    status=TaskStatus(
                        state=TaskState.working,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        message=Message(
                            message_id=str(uuid.uuid4()),
                            role=Role.agent,
                            parts=[TextPart(text=json_text)]
                        )
                    ),
                    context_id=context.context_id,
                    final=False
                )
                await event_queue.enqueue_event(new_event)

                new_artifact_event = TaskArtifactUpdateEvent(
                    task_id=context.task_id,
                    last_chunk=True,
                    context_id=context.context_id,
                    artifact=Artifact(
                        artifact_id=str(uuid.uuid4()),
                        parts=[TextPart(text=json_text)]
                    )
                )
                await event_queue.enqueue_event(new_artifact_event)
            else:
                for ev in interceptor.events:
                    await event_queue.enqueue_event(ev)
                if interceptor.artifact_event:
                    await event_queue.enqueue_event(interceptor.artifact_event)
        else:
            for ev in interceptor.events:
                await event_queue.enqueue_event(ev)
            if interceptor.artifact_event:
                await event_queue.enqueue_event(interceptor.artifact_event)

        if interceptor.final_event:
            await event_queue.enqueue_event(interceptor.final_event)


class AgentEngineApp(A2aAgent):
    @staticmethod
    def create(
        app: App | None = None,
        artifact_service: Any = None,
        session_service: Any = None,
    ) -> Any:
        if app is None:
            app = adk_app

        def create_runner() -> Runner:
            return Runner(
                app=app,
                session_service=session_service,
                artifact_service=artifact_service,
            )

        try:
            asyncio.get_running_loop()
            nest_asyncio.apply()
        except RuntimeError:
            pass

        agent_card = asyncio.run(AgentEngineApp.build_agent_card(app=app))

        return AgentEngineApp(
            agent_executor_builder=lambda: AgentEngineA2aExecutor(runner=create_runner()),
            agent_card=agent_card,
        )

    @staticmethod
    async def build_agent_card(app: App) -> AgentCard:
        agent_name = app.root_agent.name.replace('_', '-') if app.root_agent and hasattr(app.root_agent, "name") else "custom-agent"
        agent_desc = app.root_agent.description if app.root_agent and hasattr(app.root_agent, "description") else "Custom Agent"
        
        extensions = [
            AgentExtension(
                uri="https://google.github.io/adk-docs/a2a/a2a-extension/",
                description="Ability to use the new agent executor implementation",
            )
        ]
        privileges_data = _load_privileges_without_tools()
        if privileges_data:
            extensions.append(
                AgentExtension(
                    uri="https://hubscape.io/extensions/privileges",
                    description="Workspace role-based privileges matrix",
                    params=privileges_data
                )
            )

        agent_card_builder = AgentCardBuilder(
            agent=app.root_agent,
            capabilities=AgentCapabilities(
                streaming=False,
                extensions=extensions,
            ),
            rpc_url="http://localhost:9999/",
            agent_version=os.getenv("AGENT_VERSION", "0.1.0"),
        )
        agent_card = await agent_card_builder.build()
        agent_card.name = agent_name
        agent_card.description = agent_desc
        agent_card.preferred_transport = TransportProtocol.http_json  # Http Only.
        agent_card.supports_authenticated_extended_card = True
        return agent_card

    def set_up(self) -> None:
        """Initialize the agent engine app with logging and telemetry."""
        # Undo any pyOpenSSL monkeypatching in urllib3 to avoid connection reuse error
        try:
            from urllib3.contrib import pyopenssl
            pyopenssl.extract_from_urllib3()
        except Exception:
            pass
        # Explicitly pop GOOGLE_GENAI_USE_ENTERPRISE and set GOOGLE_GENAI_USE_VERTEXAI to force regional Vertex AI routing
        os.environ.pop("GOOGLE_GENAI_USE_ENTERPRISE", None)
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
        if gemini_location:
            os.environ["GOOGLE_CLOUD_LOCATION"] = gemini_location
        vertexai.init()
        setup_telemetry()
        super().set_up()
        logging.basicConfig(level=logging.INFO)
        logging_client = google_cloud_logging.Client()
        self.logger = logging_client.logger(__name__)

    def register_feedback(self, feedback: dict[str, Any]) -> None:
        """Collect and log feedback."""
        feedback_obj = Feedback.model_validate(feedback)
        self.logger.log_struct(feedback_obj.model_dump(), severity="INFO")

    def get_agent_card(self) -> dict:
        """
        Returns the metadata card of the agent and all its tools.
        Used by the platform Host core during GitOps deploys or sync sweeps.
        """
        from app.agent import app as adk_app
        root_agent = getattr(adk_app, "root_agent", None)
        agent_name = root_agent.name.replace('_', '-') if root_agent and hasattr(root_agent, "name") else "custom-agent"
        agent_desc = root_agent.description if root_agent and hasattr(root_agent, "description") else "Custom Agent"
        
        extensions = [
            {
                "uri": "https://google.github.io/adk-docs/a2a/a2a-extension/",
                "description": "Ability to use the new agent executor implementation"
            }
        ]
        privileges_data = _load_privileges_without_tools()
        if privileges_data:
            extensions.append({
                "uri": "https://hubscape.io/extensions/privileges",
                "description": "Workspace role-based privileges matrix",
                "params": privileges_data
            })

        card_dict = {
            "name": agent_name,
            "description": agent_desc,
            "version": "0.1.0",
            "protocolVersion": "0.3.0",
            "preferredTransport": "HTTP+JSON",
            "capabilities": {
                "streaming": False,
                "extensions": extensions
            },
            "skills": [
                {
                    "id": agent_name,
                    "name": agent_name,
                    "description": agent_desc
                }
            ],
            "tools": []
        }
        tools_list = root_agent.tools if root_agent and hasattr(root_agent, "tools") else []
        for tool_obj in tools_list:
            tool_name = getattr(tool_obj, "__name__", str(tool_obj))
            card_dict["tools"].append({
                "name": tool_name,
                "description": tool_obj.__doc__ or ""
            })
        return card_dict

    def register_operations(self) -> dict[str, list[str]]:
        """Registers the operations of the Agent."""
        operations = super().register_operations()
        operations[""] = [*operations.get("", []), "register_feedback", "get_agent_card"]
        return operations

    def clone(self) -> "AgentEngineApp":
        """Returns a clone of the Agent Runtime application."""
        return self


gemini_location = os.environ.get("GOOGLE_CLOUD_LOCATION")
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")
agent_runtime = AgentEngineApp.create(
    app=adk_app,
    artifact_service=(
        GcsArtifactService(bucket_name=logs_bucket_name)
        if logs_bucket_name
        else InMemoryArtifactService()
    ),
    session_service=InMemorySessionService(),
)

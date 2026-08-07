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
from contextvars import ContextVar
telemetry_org_id = ContextVar("telemetry_org_id", default=None)
telemetry_hub_id = ContextVar("telemetry_hub_id", default=None)
telemetry_user_id = ContextVar("telemetry_user_id", default=None)
telemetry_conversation_id = ContextVar("telemetry_conversation_id", default=None)
request_runner_ctx = ContextVar("request_runner_ctx", default=None)

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
    async def _resolve_runner(self) -> Runner:
        scoped = request_runner_ctx.get()
        if scoped is not None:
            return scoped
        return await super()._resolve_runner()

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
        
        session_id_resolved = metadata.get("sessionId") or metadata.get("session_id") or f"session_{user_id_resolved}_{hub_id}"
        
        # Align A2A context ID with the resolved session ID to unify session management
        context._context_id = session_id_resolved
        if hasattr(context, "_params") and context._params and hasattr(context._params, "message") and context._params.message:
            context._params.message.context_id = session_id_resolved
            
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
        
        # Resolve the runner and clone the agent to ensure request-scoped concurrency safety
        base_runner = await super()._resolve_runner()
        
        workspace_type = metadata.get("workspaceType")
        workspace_id = metadata.get("workspaceId")
        if not workspace_type or not workspace_id:
            is_org_scope = (hub_id == org_id) or (not hub_id) or (hub_id == "platform")
            workspace_type = "organization" if is_org_scope else "hub"
            workspace_id = org_id if is_org_scope else hub_id

        # Concurrency-safe dynamic tool filtering based on workspace scope and user privileges
        from app.core.hubscape_adk import filter_tools_for_scope, resolve_mcp_tools
        cloned_agent = filter_tools_for_scope(
            agent=base_runner.agent,
            user_privileges=remote_ctx.user_privileges,
            workspace_type=workspace_type,
            workspace_id=workspace_id,
            org_id=org_id
        )
        
        # Resolve remote MCP headers and access control whitelists asynchronously
        cloned_agent = await resolve_mcp_tools(cloned_agent, remote_ctx)
        
        base_instruction = base_runner.agent.instruction or ""
        
        # Inject Active Session Context securely at the top of the prompt (excluding sensitive database UUIDs to prevent logging leaks)
        normalized_mode = "chat_pc" if mode in ("chat_pc", "chat_phone") else mode
        session_context = (
            "[ACTIVE WORKSPACE CONTEXT]\n"
            f"- Interaction Mode: {normalized_mode}\n"
            f"- Workspace Type: {workspace_type}\n"
            f"- Workspace ID: {workspace_id or 'none'}\n"
            f"- Organization ID: {org_id or 'none'}\n"
        )
        
        # Format and append accessible agents roster
        accessible_agents = metadata.get("accessible_agents", [])
        roster_str = ""
        if accessible_agents:
            roster_str = "\n=== AVAILABLE SUBAGENTS ROSTER ===\n" + "\n".join(
                f"- {a.get('name')} (ID: {a.get('id')}): {a.get('description')}" for a in accessible_agents
            ) + "\n"
            
        cloned_agent.instruction = f"{session_context}{roster_str}\n{base_instruction}"
        
        # Instantiate a request-scoped runner to avoid polluting the process-wide singleton
        scoped_runner = Runner(
            agent=cloned_agent,
            app_name=base_runner.app_name,
            session_service=base_runner.session_service,
            artifact_service=getattr(base_runner, "artifact_service", None),
            memory_service=getattr(base_runner, "memory_service", None),
            credential_service=getattr(base_runner, "credential_service", None),
            auto_create_session=getattr(base_runner, "auto_create_session", False),
        )
        
        token = request_runner_ctx.set(scoped_runner)
        
        # --- OPENTELEMETRY CONTEXT ENRICHMENT ---
        session_id_resolved = metadata.get("sessionId") or metadata.get("session_id") or f"session_{user_id_resolved}_{hub_id}"
        
        # --- TELEMETRY CONTEXT VARIABLES SETTING ---
        telemetry_org_id.set(org_id or "unknown")
        telemetry_hub_id.set(hub_id or "unknown")
        telemetry_user_id.set(user_id_resolved or "unknown")

        try:
            from opentelemetry import trace
            current_span = trace.get_current_span()
            if current_span:
                current_span.set_attribute("org_id", org_id or "unknown")
                current_span.set_attribute("hub_id", hub_id or "unknown")
                current_span.set_attribute("user_id", user_id_resolved or "unknown")
                current_span.set_attribute("gen_ai.conversation_id", session_id_resolved)
                
                # Determine query type (direct vs nested A2A) using call depth
                depth = metadata.get("depth", 0)
                request_type = "a2a" if depth > 0 else "direct"
                current_span.set_attribute("gen_ai.request.type", request_type)
        except Exception as otel_err:
            print(f"⚠️ Failed to set OpenTelemetry span attributes in executor: {otel_err}")

        # --- DYNAMIC OTEL LOG PROCESSOR REGISTRATION ---
        try:
            from opentelemetry._logs import get_logger_provider
            from opentelemetry.sdk._logs import LoggerProvider

            provider = get_logger_provider()
            if hasattr(provider, "_logger_provider"):
                provider = provider._logger_provider

            if isinstance(provider, LoggerProvider):
                has_processor = any(
                    p.__class__.__name__ == "BillingContextLogRecordProcessor"
                    for p in getattr(provider, "_log_record_processors", [])
                )
                if not has_processor:
                    from opentelemetry.sdk._logs import LogRecordProcessor

                    class BillingContextLogRecordProcessor(LogRecordProcessor):
                        def emit(self, log_record, context=None):
                            self.on_emit(log_record, context)

                        def on_emit(self, log_record, context=None):
                            try:
                                # 1. Try tracing span attributes
                                span = trace.get_current_span()
                                if span and span.get_span_context().is_valid:
                                    span_attribs = getattr(span, "attributes", None)
                                    if span_attribs:
                                        for key in ["org_id", "hub_id", "user_id", "gen_ai.request.model", "gen_ai_request_model", "provider", "latency_ms"]:
                                            if key in span_attribs:
                                                val = span_attribs[key]
                                                log_record_inner = getattr(log_record, "log_record", None)
                                                if log_record_inner:
                                                    if not log_record_inner.attributes:
                                                        log_record_inner.attributes = {}
                                                    log_record_inner.attributes[key] = val
                                                else:
                                                    if not log_record.attributes:
                                                        log_record.attributes = {}
                                                    log_record.attributes[key] = val

                                # 2. Fallback/overwrite with task-local ContextVars (extremely reliable)
                                ctx_vars = {
                                    "org_id": telemetry_org_id.get(),
                                    "hub_id": telemetry_hub_id.get(),
                                    "user_id": telemetry_user_id.get()
                                }
                                for key, val in ctx_vars.items():
                                    if val is not None:
                                        log_record_inner = getattr(log_record, "log_record", None)
                                        if log_record_inner:
                                            if not log_record_inner.attributes:
                                                log_record_inner.attributes = {}
                                            log_record_inner.attributes[key] = val
                                        else:
                                            if not log_record.attributes:
                                                log_record.attributes = {}
                                            log_record.attributes[key] = val
                            except Exception:
                                pass

                        def force_flush(self, timeout_millis: int = 30000) -> bool:
                            return True

                        def shutdown(self) -> None:
                            pass

                    provider.add_log_record_processor(BillingContextLogRecordProcessor())
                    import logging
                    logging.info("BillingContextLogRecordProcessor dynamically registered successfully on LoggerProvider")
        except Exception as otel_reg_err:
            import logging
            logging.warning("Failed to dynamically register BillingContextLogRecordProcessor: %s", otel_reg_err)

        # Determine the user ID the runner will use internally
        runner_user_id = user_id_resolved
        if hasattr(context, "call_context") and context.call_context and hasattr(context.call_context, "user") and context.call_context.user and getattr(context.call_context.user, "user_name", None):
            runner_user_id = context.call_context.user.user_name

        try:
            # Enter the context session to ensure all Firestore calls in tools are authenticated
            with hubscape_adk.context_session(remote_ctx):
                # 1. Restore ADK session trajectory from Firestore if available
                try:
                    session_doc = remote_ctx.get(scope="user", collection_name="sessions", doc_id=session_id_resolved)
                    if session_doc and "adk_session" in session_doc:
                        adk_session_json = session_doc["adk_session"]
                        from google.adk.sessions import Session
                        session_obj = Session.model_validate_json(adk_session_json)
                        
                        runner = scoped_runner
                        app_name = runner.app_name
                        sid = session_obj.id
                        
                        # Ensure fields match current context
                        session_obj.app_name = app_name
                        session_obj.user_id = user_id_resolved
                        
                        if app_name not in runner.session_service.sessions:
                            runner.session_service.sessions[app_name] = {}
                        for u_key in set([user_id_resolved, runner_user_id, f"A2A_USER_{session_id_resolved}"]):
                            if u_key not in runner.session_service.sessions[app_name]:
                                runner.session_service.sessions[app_name][u_key] = {}
                            runner.session_service.sessions[app_name][u_key][sid] = session_obj
                except Exception as restore_err:
                    import logging
                    logging.warning("⚠️ Non-critical: Failed to restore session trajectory: %s", restore_err)

                # Ensure active session object is created/fetched and linked to remote_ctx before tools run
                try:
                    runner = scoped_runner
                    session_obj = await runner.session_service.get_session(
                        app_name=runner.app_name,
                        user_id=runner_user_id,
                        session_id=session_id_resolved
                    )
                    if not session_obj:
                        session_obj = await runner.session_service.create_session(
                            app_name=runner.app_name,
                            user_id=runner_user_id,
                            session_id=session_id_resolved
                        )
                    session_obj.user_id = user_id_resolved
                    remote_ctx.session = session_obj
                except Exception as session_init_err:
                    import logging
                    logging.warning("⚠️ Non-critical: Failed to bind session to context: %s", session_init_err)

                await super().execute(context, interceptor)

                # 2. Persist updated ADK session state back to Firestore
                try:
                    runner = scoped_runner
                    updated_session = await runner.session_service.get_session(
                        app_name=runner.app_name,
                        user_id=runner_user_id,
                        session_id=session_id_resolved
                    )
                    if updated_session:
                        updated_session.user_id = user_id_resolved
                        serialized_json = updated_session.model_dump_json()
                        remote_ctx.save(
                            scope="user",
                            collection_name="sessions",
                            doc_id=session_id_resolved,
                            data={
                                "adk_session": serialized_json
                            }
                        )
                except Exception as save_err:
                    import logging
                    logging.warning("⚠️ Non-critical: Failed to save session trajectory: %s", save_err)
        finally:
            request_runner_ctx.reset(token)

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
                            "widgetType": payload.get("widgetType"),
                            "confirmation_obtained": payload.get("confirmation_obtained", True)
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
                elif atype == "REFRESH_TOKEN":
                    directive_payload = {
                        "directive": "execute_host_tool",
                        "target_tool": "refreshToken",
                        "parameters": {
                            "provider": payload.get("provider"),
                            "agent_id": payload.get("agent_id")
                        },
                        "message": "Refreshing authentication token..."
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
                auto_create_session=True,
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
        
        # Register billing context processor to propagate span attributes to log records
        try:
            from opentelemetry.sdk._logs import LogRecordProcessor
            from opentelemetry import trace

            class BillingContextLogRecordProcessor(LogRecordProcessor):
                def emit(self, log_record, context=None):
                    try:
                        span = trace.get_current_span()
                        if span and span.get_span_context().is_valid:
                            span_attribs = getattr(span, "attributes", None)
                            if span_attribs:
                                for key in ["org_id", "hub_id", "user_id", "gen_ai.conversation_id", "gen_ai.request.model", "gen_ai_request_model", "provider", "latency_ms"]:
                                    if key in span_attribs:
                                        val = span_attribs[key]
                                        log_record_inner = getattr(log_record, "log_record", None)
                                        if log_record_inner:
                                            if not log_record_inner.attributes:
                                                log_record_inner.attributes = {}
                                            log_record_inner.attributes[key] = val
                                        else:
                                            if not log_record.attributes:
                                                log_record.attributes = {}
                                            log_record.attributes[key] = val
                    except Exception:
                        pass

            from opentelemetry._logs import get_logger_provider
            from opentelemetry.sdk._logs import LoggerProvider
            provider = get_logger_provider()
            if isinstance(provider, LoggerProvider):
                provider.add_log_record_processor(BillingContextLogRecordProcessor())
                logging.info("BillingContextLogRecordProcessor registered successfully on LoggerProvider")
            else:
                logging.warning("LoggerProvider is not a LoggerProvider: %s", type(provider))
        except Exception as otel_reg_err:
            logging.warning("Failed to register BillingContextLogRecordProcessor: %s", otel_reg_err)

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

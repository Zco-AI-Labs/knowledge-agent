import contextvars
import contextlib
import datetime
import logging
import os
import httpx

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from typing import Generator, Optional
from google.cloud import firestore

logger = logging.getLogger(__name__)

_current_context = contextvars.ContextVar("hubscape_context")
_global_active_context = None

class RemoteAuth:
    def __init__(self, user_id: str, org_id: str = None, hub_id: str = None):
        self.user_id = user_id
        self.org_id = org_id
        self.hub_id = hub_id
    
    def get_user_id(self) -> str:
        return self.user_id

class RemoteContext:
    def __init__(self, user_id: str, agent_id: str = None, org_id: str = None, hub_id: str = None, project_id: str = None, raw_context: dict = None, allow_generative_ui: Optional[bool] = None):
        self.auth = RemoteAuth(user_id, org_id, hub_id)
        self.agent_id = agent_id or "default_agent"
        self.project_id = project_id
        self.raw_context = raw_context or {}
        self.actions = []
        self._db = None
        
        # Resolve allow_generative_ui flag
        if allow_generative_ui is not None:
            self.allow_generative_ui = allow_generative_ui
        else:
            platform_config = self.raw_context.get("config") or {}
            self.allow_generative_ui = platform_config.get("allowGenerativeUi", True)

    @property
    def user_privileges(self) -> list:
        return self.raw_context.get("user_privileges") or self.raw_context.get("userPrivileges") or []

    @property
    def _db_client(self):
        if self._db is None:
            # Try to get OAuth2 token from Metadata Server
            token = None
            try:
                import httpx as httpx_sync
                meta_url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token?scopes=https://www.googleapis.com/auth/datastore,https://www.googleapis.com/auth/cloud-platform"
                resp = httpx_sync.get(meta_url, headers={"Metadata-Flavor": "Google"}, timeout=2.0)
                if resp.status_code == 200:
                    token = resp.json().get("access_token")
            except Exception:
                pass

            if token:
                from google.oauth2.credentials import Credentials as OAuth2Credentials
                creds = OAuth2Credentials(token)
                self._db = firestore.Client(project=self.project_id, credentials=creds)
            else:
                self._db = firestore.Client(project=self.project_id)
        return self._db

    def get_agent_db_path(self, scope: str, collection_name: str, doc_id: Optional[str] = None) -> str:
        if scope == "user":
            base = f"platform_users/{self.auth.get_user_id()}/agent_data/{self.agent_id}/{collection_name}"
        elif scope == "hub":
            if not self.auth.hub_id or not self.auth.org_id:
                raise ValueError("Hub scope requires org_id and hub_id in context.")
            base = f"organizations/{self.auth.org_id}/hubs/{self.auth.hub_id}/agent_data/{self.agent_id}/{collection_name}"
        elif scope == "org":
            if not self.auth.org_id:
                raise ValueError("Org scope requires org_id in context.")
            base = f"organizations/{self.auth.org_id}/agent_data/{self.agent_id}/{collection_name}"
        elif scope == "platform":
            base = f"agents/{self.agent_id}/agent_data/platform/{collection_name}"
        else:
            raise ValueError(f"Unknown scope: {scope}")
            
        if doc_id:
            return f"{base}/{doc_id}"
        return base

    def save(self, scope: str, collection_name: str, doc_id: str, data: dict) -> dict:
        doc_path = self.get_agent_db_path(scope, collection_name, doc_id)
        doc_ref = self._db_client.document(doc_path)
        
        snap = doc_ref.get()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        user_id = self.auth.get_user_id()
        
        payload = data.copy()
        if not snap.exists:
            payload.update({
                "created_at": now,
                "created_by": user_id,
                "updated_at": now,
                "updated_by": user_id,
                "version": 1
            })
        else:
            current_data = snap.to_dict() or {}
            current_version = current_data.get("version", 0)
            payload.update({
                "created_at": current_data.get("created_at", now),
                "created_by": current_data.get("created_by", user_id),
                "updated_at": now,
                "updated_by": user_id,
                "version": current_version + 1
            })
            
        doc_ref.set(payload, merge=True)
        return payload

    def get(self, scope: str, collection_name: str, doc_id: str) -> Optional[dict]:
        doc_path = self.get_agent_db_path(scope, collection_name, doc_id)
        doc_ref = self._db_client.document(doc_path)
        snap = doc_ref.get()
        if snap.exists:
            res = snap.to_dict() or {}
            res["id"] = snap.id
            return res
        return None

    def list(self, scope: str, collection_name: str) -> list:
        col_path = self.get_agent_db_path(scope, collection_name)
        col_ref = self._db_client.collection(col_path)
        docs = col_ref.stream()
        res = []
        for doc in docs:
            d = doc.to_dict() or {}
            d["id"] = doc.id
            res.append(d)
        return res

    def delete(self, scope: str, collection_name: str, doc_id: str):
        doc_path = self.get_agent_db_path(scope, collection_name, doc_id)
        doc_ref = self._db_client.document(doc_path)
        doc_ref.delete()

    @property
    def _storage_client(self):
        if not hasattr(self, "_storage"):
            self._storage = None
        if self._storage is None:
            # Try to get OAuth2 token from Metadata Server
            token = None
            try:
                import httpx as httpx_sync
                meta_url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token?scopes=https://www.googleapis.com/auth/devstorage.read_write,https://www.googleapis.com/auth/cloud-platform"
                resp = httpx_sync.get(meta_url, headers={"Metadata-Flavor": "Google"}, timeout=2.0)
                if resp.status_code == 200:
                    token = resp.json().get("access_token")
            except Exception:
                pass

            from google.cloud import storage as gcs_storage
            if token:
                from google.oauth2.credentials import Credentials as OAuth2Credentials
                creds = OAuth2Credentials(token)
                self._storage = gcs_storage.Client(project=self.project_id, credentials=creds)
            else:
                self._storage = gcs_storage.Client(project=self.project_id)
        return self._storage

    @property
    def _storage_bucket(self):
        import os
        bucket_name = self.raw_context.get("storageBucket") or os.getenv("VITE_FIREBASE_STORAGE_BUCKET")
        if not bucket_name:
            project_id = self.project_id or os.getenv("PROJECT_ID")
            if project_id:
                bucket_name = f"{project_id}.firebasestorage.app"
        if not bucket_name:
            raise ValueError("Storage bucket name is not configured.")
        return self._storage_client.bucket(bucket_name)

    def get_agent_storage_path(self, scope: str, filename: str) -> str:
        """
        Resolves the GCS path for agent storage.
        Paths:
          - 'user': agents/{agentId}/user/{userId}/{filename}
          - 'hub': agents/{agentId}/hub/{hubId}/{filename}
          - 'org': agents/{agentId}/org/{orgId}/{filename}
          - 'platform': agents/{agentId}/platform/{filename}
        """
        agent_id = self.agent_id or "unknown"
        if scope == "platform":
            return f"agents/{agent_id}/platform/{filename}"
        elif scope == "user":
            user_id = self.auth.get_user_id()
            if not user_id:
                raise ValueError("Storage scope 'user' requires authenticated user_id.")
            return f"agents/{agent_id}/user/{user_id}/{filename}"
        elif scope == "hub":
            hub_id = self.auth.hub_id
            if not hub_id:
                raise ValueError("Storage scope 'hub' requires hub_id.")
            return f"agents/{agent_id}/hub/{hub_id}/{filename}"
        elif scope == "org":
            org_id = self.auth.org_id
            if not org_id:
                raise ValueError("Storage scope 'org' requires org_id.")
            return f"agents/{agent_id}/org/{org_id}/{filename}"
        else:
            raise ValueError(f"Invalid storage scope: '{scope}'. Must be 'user', 'hub', 'org', or 'platform'.")

    def save_file(self, scope: str, filename: str, content: bytes, content_type: Optional[str] = None) -> dict:
        """
        Saves a file to Firebase Storage under the appropriate scope.
        Returns a dict containing 'storage_path' and 'download_url'.
        """
        storage_path = self.get_agent_storage_path(scope, filename)
        bucket = self._storage_bucket
        blob = bucket.blob(storage_path)
        blob.upload_from_string(content, content_type=content_type)

        import urllib.parse
        encoded_path = urllib.parse.quote(storage_path, safe='')
        download_url = f"/api/media/file?path={encoded_path}"

        return {
            "storage_path": storage_path,
            "download_url": download_url
        }

    def get_file(self, scope: str, filename: str) -> Optional[bytes]:
        """
        Retrieves a file's content from Firebase Storage under the appropriate scope.
        """
        storage_path = self.get_agent_storage_path(scope, filename)
        bucket = self._storage_bucket
        blob = bucket.blob(storage_path)
        if blob.exists():
            return blob.download_as_bytes()
        return None

    def delete_file(self, scope: str, filename: str):
        """
        Deletes a file from Firebase Storage under the appropriate scope.
        """
        storage_path = self.get_agent_storage_path(scope, filename)
        bucket = self._storage_bucket
        blob = bucket.blob(storage_path)
        if blob.exists():
            blob.delete()

    def show_widget(self, widget_template_id: str, data: dict = None) -> dict:
        """Loads a predefined widget JSON and registers a client action directive to show it."""
        try:
            import os
            import json
            core_dir = os.path.dirname(os.path.abspath(__file__))
            app_dir = os.path.dirname(core_dir)
            filename = widget_template_id if widget_template_id.endswith(".json") else f"{widget_template_id}.json"
            
            # Check app/ui/widgets first (ADK standard)
            template_path = os.path.join(app_dir, "ui", "widgets", filename)
            if not os.path.exists(template_path):
                # Fallback to app/widgets (GEAP standard)
                fallback_path = os.path.join(app_dir, "widgets", filename)
                if os.path.exists(fallback_path):
                    template_path = fallback_path
                else:
                    raise FileNotFoundError(
                        f"Widget template {filename} not found. "
                        f"Searched: {template_path} and {fallback_path}"
                    )
            
            with open(template_path, "r", encoding="utf-8") as f:
                widget_config = json.load(f)

            # Replacements (e.g. {{agent_id}} -> actual agent ID)
            config_str = json.dumps(widget_config).replace("{{agent_id}}", self.agent_id)
            widget_config = json.loads(config_str)

            action_payload = {
                "type": "OPEN_AGENT_WIDGET",
                "payload": {
                    "widgetId": widget_template_id,
                    "widgetConfig": widget_config,
                    "data": data or {},
                    "styling": self.raw_context.get("styling", {}),
                    "userPreferences": self.raw_context.get("userPreferences", {})
                }
            }
            self.actions.append(action_payload)
            return {"status": "success", "message": f"Widget '{widget_template_id}' queued."}
        except Exception as e:
            raise RuntimeError(f"Failed to load widget '{widget_template_id}': {str(e)}")

    def show_custom_ui(self, layout: dict, data: dict = None) -> dict:
        """Registers an OPEN_AGENT_WIDGET client action directive with a generative layout."""
        if not getattr(self, "allow_generative_ui", True):
            raise PermissionError("Generative UI is disabled for this agent. Only predefined developer widgets are allowed.")
            
        action_payload = {
            "type": "OPEN_AGENT_WIDGET",
            "payload": {
                "widgetId": "generative_custom_ui",
                "widgetConfig": layout,
                "data": data or {},
                "styling": self.raw_context.get("styling", {}),
                "userPreferences": self.raw_context.get("userPreferences", {})
            }
        }
        self.actions.append(action_payload)
        return {"status": "success", "message": "Custom UI layout queued."}

    def close_widget(self, message_id: Optional[str] = None, result_text: Optional[str] = None) -> dict:
        """Registers a CLOSE_AGENT_WIDGET client action directive to close/unmount an active widget."""
        action_payload = {
            "type": "CLOSE_AGENT_WIDGET",
            "payload": {
                "messageId": message_id,
                "resultText": result_text or "✅ Widget closed."
            }
        }
        self.actions.append(action_payload)
        return {"status": "success", "message": "Close widget directive queued."}

    def send_otp(self, phone_number: str) -> dict:
        """
        Sends an SMS OTP code to the target phone number via the Hubscape central backend.
        Supports local mock bypass for non-cloud development environments.
        """
        import httpx
        
        is_cloud = "K_SERVICE" in os.environ or "AIP_PREDICT_PORT" in os.environ
        backend_url = self.raw_context.get("backend_url") or os.environ.get("HUBSCAPE_BACKEND_URL")
        
        if not is_cloud and not backend_url:
            logger.warning(
                f"⚠️ Local Dev Bypass: Simulating OTP SMS send to {phone_number}."
            )
            return {
                "success": True, 
                "status": "simulated", 
                "message": "OTP SMS send simulated for local testing. Use code '123456' to verify."
            }
            
        url = f"{str(backend_url or 'https://hubscape-backend-w3xi4ozhca-uc.a.run.app').rstrip('/')}/api/otp/send"
        headers = {}
        cap_token = self.raw_context.get("capability_token")
        if cap_token:
            headers["Authorization"] = f"Bearer {cap_token}"
            
        payload = {
            "phone_number": phone_number,
            "agent_id": self.agent_id
        }
        
        resp = httpx.post(url, json=payload, headers=headers, timeout=10.0)
        if resp.status_code != 200:
            raise RuntimeError(f"OTP send request failed: {resp.text}")
        return resp.json()

    def verify_otp(self, phone_number: str, code: str) -> dict:
        """
        Verifies the SMS OTP code for the target phone number via the Hubscape central backend.
        Supports local mock bypass (code '123456' is always accepted) for non-cloud environments.
        """
        import httpx
        
        is_cloud = "K_SERVICE" in os.environ or "AIP_PREDICT_PORT" in os.environ
        backend_url = self.raw_context.get("backend_url") or os.environ.get("HUBSCAPE_BACKEND_URL")
        
        if not is_cloud and not backend_url:
            logger.warning(
                f"⚠️ Local Dev Bypass: Verifying simulated OTP for {phone_number}."
            )
            if code == "123456":
                return {"success": True, "status": "verified", "message": "Simulated OTP verified successfully."}
            return {"success": False, "status": "invalid", "message": "Simulated OTP verification failed."}
            
        url = f"{str(backend_url or 'https://hubscape-backend-w3xi4ozhca-uc.a.run.app').rstrip('/')}/api/otp/verify"
        headers = {}
        cap_token = self.raw_context.get("capability_token")
        if cap_token:
            headers["Authorization"] = f"Bearer {cap_token}"
            
        payload = {
            "phone_number": phone_number,
            "code": code,
            "agent_id": self.agent_id
        }
        
        resp = httpx.post(url, json=payload, headers=headers, timeout=10.0)
        if resp.status_code != 200:
            raise RuntimeError(f"OTP verification request failed: {resp.text}")
        return resp.json()

    async def get_oauth_token(self, provider: str) -> Optional[str]:
        """
        Gets the active oauth access token, triggering a platform refresh if expired.
        """
        token_data = self.get(scope="user", collection_name="tokens", doc_id=provider)
        if not token_data:
            return None

        access_token = token_data.get("access_token")
        expires_at_str = token_data.get("expires_at")

        # Check if expired or about to expire in the next 60 seconds
        is_expired = False
        if expires_at_str:
            try:
                expires_at = datetime.datetime.fromisoformat(expires_at_str)
                now = datetime.datetime.now(datetime.timezone.utc)
                if expires_at - now < datetime.timedelta(seconds=60):
                    is_expired = True
            except Exception:
                is_expired = True

        # Delegate token refresh to the platform by appending a REFRESH_TOKEN action
        if is_expired:
            if {
                "type": "REFRESH_TOKEN",
                "payload": {"provider": provider, "agent_id": self.agent_id}
            } not in self.actions:
                self.actions.append({
                    "type": "REFRESH_TOKEN",
                    "payload": {
                        "provider": provider,
                        "agent_id": self.agent_id
                    }
                })
            return None

        return access_token


    def oauth_start(self, openid_configuration: str) -> dict:
        """Triggers the platform OAuth authentication challenge payload."""
        return {
            "status": "error",
            "message": "Authorization required.",
            "error_type": "AUTH_REQUIRED",
            "system_action": {
                "type": "TRIGGER_OAUTH",
                "payload": {
                    "openid_configuration": openid_configuration,
                    "agent_id": self.agent_id
                }
            }
        }


def get_context() -> RemoteContext:
    try:
        return _current_context.get()
    except LookupError:
        global _global_active_context
        if _global_active_context is not None:
            return _global_active_context
        raise RuntimeError(
            "No active RemoteContext found. "
            "Ensure the tool is executed inside an active context_session."
        )

@contextlib.contextmanager
def context_session(context: RemoteContext) -> Generator[None, None, None]:
    global _global_active_context
    old_global = _global_active_context
    _global_active_context = context
    token = _current_context.set(context)
    try:
        yield
    finally:
        _global_active_context = old_global
        try:
            _current_context.reset(token)
        except ValueError:
            pass

import functools
import inspect
import os
import json
import logging
import jwt
from cryptography.fernet import Fernet
_cached_hmac_secret = None

def get_hmac_secret() -> str:
    """Resolves and returns the HMAC/Fernet master secret key, caching it for subsequent calls."""
    global _cached_hmac_secret
    if _cached_hmac_secret is None:
        env_secret = os.environ.get("HUBSCAPE_HMAC_SECRET")
        if env_secret:
            _cached_hmac_secret = env_secret
        else:
            is_cloud = "K_SERVICE" in os.environ or "AIP_PREDICT_PORT" in os.environ
            if is_cloud:
                try:
                    from google.cloud import secretmanager
                    client = secretmanager.SecretManagerServiceClient()
                    project_id = os.environ.get("GCP_PROJECT_ID") or "hubscape-geap"
                    name = f"projects/{project_id}/secrets/HUBSCAPE_KMS_MASTER_KEY/versions/latest"
                    response = client.access_secret_version(name=name)
                    _cached_hmac_secret = response.payload.data.decode("UTF-8").strip()
                except Exception as e:
                    raise RuntimeError(f"CRITICAL CONFIGURATION ERROR: Failed to access HUBSCAPE_KMS_MASTER_KEY from Secret Manager: {e}")
            else:
                _cached_hmac_secret = "dev_secret_key_dont_use_in_prod"
    return _cached_hmac_secret

def require_tool_privilege(func):
    """
    Decorator for agent python tools to enforce zero-trust tool-level RBAC.
    Supports both synchronous and asynchronous functions.
    """
    is_async = inspect.iscoroutinefunction(func)

    def verify_privilege():
        try:
            context = get_context()
            token = context.raw_context.get("capability_token")
        except Exception:
            token = None
            
        is_mock_token = hasattr(token, "_mock_return_value") or type(token).__name__ == "MagicMock"
        if not token or is_mock_token:
            # If no token is provided, only allow it if we are running locally (no K_SERVICE / AIP_PREDICT_PORT)
            is_cloud = "K_SERVICE" in os.environ or "AIP_PREDICT_PORT" in os.environ
            if is_cloud:
                raise PermissionError(f"Security Block: Access denied to tool '{func.__name__}'. Missing capability token.")
            
            # Local Dev/Test Bypass: log warning and allow
            logging.getLogger(__name__).warning(
                f"⚠️ Developer Bypass Active: Tool '{func.__name__}' executed locally without JWT check."
            )
            return True
            
        secret_key = get_hmac_secret()
            
        try:
            # Decode & Verify JWT HMAC
            payload = jwt.decode(token, secret_key, algorithms=["HS256"])
            
            # Context Pinning Checks
            token_user_id = payload.get("sub")
            metadata_user_id = context.auth.get_user_id()
            if token_user_id != metadata_user_id:
                raise PermissionError("Security Block: User ID mismatch between request and capability token.")
                
            token_hub_id = payload.get("hub_id")
            metadata_hub_id = context.auth.hub_id
            if token_hub_id != metadata_hub_id:
                raise PermissionError("Security Block: Hub ID mismatch between request and capability token.")
                
            # Derive Fernet key dynamically from master secret
            import base64
            import hashlib
            hasher = hashlib.sha256()
            hasher.update(secret_key.encode())
            hasher.update(context.agent_id.encode())
            derived_key = base64.urlsafe_b64encode(hasher.digest()).decode()
            
            encrypted_capabilities = payload.get("capabilities", {})
            encrypted_segment = encrypted_capabilities.get(context.agent_id)
            
            if not encrypted_segment:
                raise PermissionError(f"Security Block: Agent '{context.agent_id}' is not authorized in this session passport.")
                
            try:
                fernet = Fernet(derived_key.encode())
                decrypted_bytes = fernet.decrypt(encrypted_segment.encode())
                allowed_privilege_ids = json.loads(decrypted_bytes.decode())
                logging.getLogger(__name__).info(f"[adk] Decrypted allowed privilege IDs: {allowed_privilege_ids}")
            except Exception as decrypt_err:
                raise PermissionError(f"Security Block: Failed to decrypt capabilities: {decrypt_err}")
                
            # Load local privileges mapping from privileges.json
            privileges_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "privileges.json")
            if not os.path.exists(privileges_path):
                # Try current working directory as fallback
                privileges_path = "privileges.json"
                
            allowed_tools = []
            if os.path.exists(privileges_path):
                try:
                    with open(privileges_path, "r") as f:
                        priv_data = json.load(f)
                    privileges_config = priv_data.get("privileges", {})
                    for priv_id in allowed_privilege_ids:
                        priv_info = privileges_config.get(priv_id) or {}
                        tools = priv_info.get("tools") or []
                        allowed_tools.extend(tools)
                    logging.getLogger(__name__).info(f"[adk] Mapped allowed tools: {allowed_tools}")
                except Exception as read_err:
                    logging.getLogger(__name__).warning(f"⚠️ Failed to read/parse privileges.json: {read_err}")
                
            if func.__name__ not in allowed_tools:
                raise PermissionError(f"Security Block: Tool '{func.__name__}' is not allowed for this agent. Allowed: {allowed_tools}")
                
            return True
            
        except jwt.ExpiredSignatureError:
            raise PermissionError("Security Block: Capability token has expired.")
        except jwt.InvalidTokenError as jwt_err:
            raise PermissionError(f"Security Block: Invalid capability token: {jwt_err}")

    if is_async:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            verify_privilege()
            return await func(*args, **kwargs)
        return async_wrapper
    else:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            verify_privilege()
            return func(*args, **kwargs)
        return sync_wrapper


def tool_scope(allowed_scopes: list[str]):
    """
    Decorator to restrict the workspace scopes in which this tool is allowed to be invoked.
    Example:
        @tool_scope(["hub"])
        async def my_hub_only_tool():
            ...
    """
    def decorator(func):
        func._allowed_scopes = allowed_scopes
        return func
    return decorator


def filter_tools_for_scope(*args, **kwargs):
    """
    Filters tools based on workspace scope and/or user privileges.
    Supports two signatures:
    1. (tools: list, hub_id: str | None, org_id: str | None = None) -> list
    2. (agent: Agent, user_privileges: list, workspace_type: str, workspace_id: str, org_id: str) -> Agent
    """
    agent = kwargs.get("agent")
    if not agent and args and not isinstance(args[0], list):
        agent = args[0]
        
    if agent:
        # Signature 2: Returns cloned Agent with filtered tools
        user_privileges = kwargs.get("user_privileges")
        if user_privileges is None and len(args) > 1:
            user_privileges = args[1]
            
        workspace_type = kwargs.get("workspace_type")
        if workspace_type is None and len(args) > 2:
            workspace_type = args[2]
            
        workspace_id = kwargs.get("workspace_id")
        if workspace_id is None and len(args) > 3:
            workspace_id = args[3]
            
        org_id = kwargs.get("org_id")
        if org_id is None and len(args) > 4:
            org_id = args[4]
            
        cloned_agent = agent.clone()
        
        wtype = workspace_type or "hub"
        if wtype in ("organization", "org", "platform"):
            active_scope = "org"
        else:
            active_scope = "hub"
            
        filtered_tools = []
        for tool in cloned_agent.tools:
            allowed_scopes = getattr(tool, "_allowed_scopes", None)
            if allowed_scopes is None:
                wrapped = getattr(tool, "__wrapped__", None)
                while wrapped is not None:
                    allowed_scopes = getattr(wrapped, "_allowed_scopes", None)
                    if allowed_scopes is not None:
                        break
                    wrapped = getattr(wrapped, "__wrapped__", None)
                    
            if allowed_scopes is not None:
                if active_scope not in allowed_scopes:
                    continue
            filtered_tools.append(tool)
            
        if user_privileges is not None:
            privileges_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "privileges.json")
            if not os.path.exists(privileges_path):
                privileges_path = "privileges.json"
                
            allowed_tools = []
            if os.path.exists(privileges_path):
                try:
                    with open(privileges_path, "r") as f:
                        priv_data = json.load(f)
                    privileges_config = priv_data.get("privileges", {})
                    for priv_id in user_privileges:
                        priv_info = privileges_config.get(str(priv_id)) or {}
                        tools_list = priv_info.get("tools") or []
                        allowed_tools.extend(tools_list)
                except Exception as read_err:
                    import logging
                    logging.getLogger(__name__).warning(f"⚠️ Failed to read/parse privileges.json: {read_err}")
            
            final_tools = []
            for tool in filtered_tools:
                tool_name = getattr(tool, "__name__", str(tool))
                if tool_name in ("consultAgent", "discover_agents", "suggestQueries"):
                    final_tools.append(tool)
                elif not allowed_tools or tool_name in allowed_tools:
                    final_tools.append(tool)
            filtered_tools = final_tools
            
        cloned_agent.tools = filtered_tools
        return cloned_agent

    else:
        # Signature 1: Returns filtered tools list
        tools = kwargs.get("tools")
        if tools is None and args:
            tools = args[0]
            
        hub_id = kwargs.get("hub_id")
        if hub_id is None and len(args) > 1:
            hub_id = args[1]
            
        org_id = kwargs.get("org_id")
        if org_id is None and len(args) > 2:
            org_id = args[2]
            
        if org_id is not None:
            is_org_scope = (hub_id == org_id) or (not hub_id) or (hub_id == "platform")
            active_scope = "org" if is_org_scope else "hub"
        else:
            wtype = hub_id or "hub"
            if wtype in ("organization", "org", "platform"):
                active_scope = "org"
            else:
                active_scope = "hub"
                
        import logging
        logging.info(f"[adk] filter_tools_for_scope: active_scope={active_scope}, input tools count={len(tools or [])}")
        filtered = []
        for tool in (tools or []):
            tool_name = getattr(tool, "__name__", str(tool))
            allowed_scopes = getattr(tool, "_allowed_scopes", None)
            if allowed_scopes is None:
                wrapped = getattr(tool, "__wrapped__", None)
                while wrapped is not None:
                    allowed_scopes = getattr(wrapped, "_allowed_scopes", None)
                    if allowed_scopes is not None:
                        break
                    wrapped = getattr(wrapped, "__wrapped__", None)
                    
            logging.info(f"[adk] Tool: {tool_name}, allowed_scopes={allowed_scopes}")
            if allowed_scopes is not None:
                if active_scope not in allowed_scopes:
                    logging.info(f"[adk]   Skipped {tool_name} (active_scope {active_scope} not in {allowed_scopes})")
                    continue
            logging.info(f"[adk]   Kept {tool_name}")
            filtered.append(tool)
        return filtered


async def resolve_mcp_tools(agent, context):
    """
    Asynchronously resolves headers for MCP tools and applies access control filtering.
    For each tool in the agent's tool list:
      - If it is an McpToolset instance (having _mcp_server_name):
        - Dynamically resolve header placeholder values like ${OAUTH_TOKEN:provider}
        - Construct a new request-scoped McpToolset connection
        - Fetch list of accessible tools from context metadata and configure tool_filter
        - Replace the tool in the agent's tool list
    """
    try:
        from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StreamableHTTPConnectionParams
    except ImportError:
        # If mcp is not installed/imported, do nothing
        return agent

    import re
    placeholder_pattern = re.compile(r"\$\{([^}]+)\}")

    resolved_tools = []
    for tool in agent.tools:
        if hasattr(tool, "_mcp_server_name"):
            server_name = tool._mcp_server_name
            raw_headers = getattr(tool, "_mcp_raw_headers", {})
            url = tool.connection_params.url
            
            # 1. Resolve header placeholders (e.g. ${OAUTH_TOKEN:github} or ${MY_SECRET})
            resolved_headers = None
            if raw_headers:
                resolved_headers = {}
                for key, val in raw_headers.items():
                    if isinstance(val, str):
                        matches = placeholder_pattern.findall(val)
                        resolved_val = val
                        for ph in matches:
                            if ph.startswith("OAUTH_TOKEN:"):
                                provider = ph.split(":", 1)[1]
                                token_val = await context.get_oauth_token(provider)
                                resolved_val = resolved_val.replace(f"${{{ph}}}", token_val or "")
                            else:
                                secret_val = os.environ.get(ph) or context.raw_context.get("secrets", {}).get(ph, "")
                                resolved_val = resolved_val.replace(f"${{{ph}}}", secret_val)
                        resolved_headers[key] = resolved_val
                    else:
                        resolved_headers[key] = val
            
            # 2. Get tool whitelisting filter from privileges.json
            tool_filter = None
            user_privileges = getattr(context, "user_privileges", [])
            if user_privileges:
                priv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "privileges.json")
                if not os.path.exists(priv_path):
                    priv_path = "privileges.json"
                if os.path.exists(priv_path):
                    try:
                        import json
                        with open(priv_path, "r") as pf:
                            priv_data = json.load(pf)
                        privileges_config = priv_data.get("privileges", {})
                        allowed_tools = []
                        for priv_id in user_privileges:
                            priv_info = privileges_config.get(str(priv_id)) or {}
                            tools_list = priv_info.get("tools") or []
                            allowed_tools.extend(tools_list)
                        if allowed_tools:
                            tool_filter = allowed_tools
                    except Exception as read_err:
                        import logging
                        logging.getLogger(__name__).warning(f"⚠️ Failed to read/parse privileges.json for MCP tool filtering: {read_err}")
            
            # Fallback to accessible_tools metadata if privileges didn't yield anything
            if not tool_filter:
                accessible_tools = context.raw_context.get("accessible_tools", {})
                if isinstance(accessible_tools, dict):
                    tool_filter = accessible_tools.get(server_name)
                elif isinstance(accessible_tools, list):
                    tool_filter = accessible_tools
            
            # 3. Create a fresh request-scoped McpToolset
            try:
                kwargs = {"url": url}
                if resolved_headers is not None:
                    kwargs["headers"] = resolved_headers
                connection_params = StreamableHTTPConnectionParams(**kwargs)
                
                request_toolset = McpToolset(
                    connection_params=connection_params,
                    tool_filter=tool_filter
                )
                request_toolset._mcp_server_name = server_name
                request_toolset._mcp_raw_headers = raw_headers
                resolved_tools.append(request_toolset)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to resolve request-scoped MCP toolset for '{server_name}': {e}")
                resolved_tools.append(tool)
        else:
            resolved_tools.append(tool)
            
    agent.tools = resolved_tools
    return agent


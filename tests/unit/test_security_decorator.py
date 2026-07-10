import base64
import hashlib
import json
import os
from unittest.mock import mock_open, patch

import jwt
import pytest
from cryptography.fernet import Fernet

from app.core import hubscape_adk


def derive_test_fernet_key(agent_id: str, master_secret: str) -> str:
    hasher = hashlib.sha256()
    hasher.update(master_secret.encode())
    hasher.update(agent_id.encode())
    return base64.urlsafe_b64encode(hasher.digest()).decode()

@pytest.mark.asyncio
async def test_require_tool_privilege_decorator_success():
    # Setup capability token
    master_secret = "test_hmac_secret_key"
    os.environ["HUBSCAPE_HMAC_SECRET"] = master_secret

    # Encrypt capabilities (contains privilege ID "1" instead of raw tool name)
    derived_key = derive_test_fernet_key("custom-agent", master_secret)
    fernet = Fernet(derived_key.encode())
    encrypted = fernet.encrypt(json.dumps(["1"]).encode()).decode()

    import time
    now = int(time.time())
    payload = {
        "sub": "user-123",
        "hub_id": "hub-456",
        "iat": now,
        "exp": now + 60,
        "capabilities": {
            "custom-agent": encrypted
        }
    }
    token = jwt.encode(payload, master_secret, algorithm="HS256")

    # Create RemoteContext
    context = hubscape_adk.RemoteContext(
        user_id="user-123",
        agent_id="custom-agent",
        hub_id="hub-456",
        raw_context={"capability_token": token}
    )

    # Define tool
    @hubscape_adk.require_tool_privilege
    async def my_secret_tool():
        return "success"

    mock_privileges = {
        "privileges": {
            "1": {
                "name": "Secret Manager",
                "description": "Allows my_secret_tool",
                "tools": ["my_secret_tool"]
            }
        }
    }

    # Execute inside context_session with mock privileges.json
    with patch("builtins.open", mock_open(read_data=json.dumps(mock_privileges))):
        with patch("os.path.exists", return_value=True):
            with hubscape_adk.context_session(context):
                result = await my_secret_tool()
                assert result == "success"

@pytest.mark.asyncio
async def test_require_tool_privilege_decorator_blocked():
    # Setup capability token
    master_secret = "test_hmac_secret_key"
    os.environ["HUBSCAPE_HMAC_SECRET"] = master_secret

    # Encrypt empty capabilities segment
    derived_key = derive_test_fernet_key("custom-agent", master_secret)
    fernet = Fernet(derived_key.encode())
    encrypted = fernet.encrypt(json.dumps([]).encode()).decode()

    import time
    now = int(time.time())
    payload = {
        "sub": "user-123",
        "hub_id": "hub-456",
        "iat": now,
        "exp": now + 60,
        "capabilities": {
            "custom-agent": encrypted
        }
    }
    token = jwt.encode(payload, master_secret, algorithm="HS256")

    # Create RemoteContext
    context = hubscape_adk.RemoteContext(
        user_id="user-123",
        agent_id="custom-agent",
        hub_id="hub-456",
        raw_context={"capability_token": token}
    )

    # Define tool
    @hubscape_adk.require_tool_privilege
    async def my_blocked_tool():
        return "should not reach here"

    mock_privileges = {
        "privileges": {
            "1": {
                "name": "Secret Manager",
                "description": "Allows my_secret_tool",
                "tools": ["my_secret_tool"]
            }
        }
    }

    # Execute inside context_session and verify it raises PermissionError
    with patch("builtins.open", mock_open(read_data=json.dumps(mock_privileges))):
        with patch("os.path.exists", return_value=True):
            with hubscape_adk.context_session(context):
                with pytest.raises(PermissionError) as exc_info:
                    await my_blocked_tool()
                assert "is not allowed for this agent" in str(exc_info.value)

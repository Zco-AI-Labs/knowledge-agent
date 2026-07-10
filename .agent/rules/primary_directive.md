# Primary Directive: Custom Agent AI Constitution

> [!IMPORTANT]
> This file is the **HIGHEST AUTHORITY** inside this custom agent repository. 
> Any AI coding assistant or agent modifying this codebase must strictly adhere to these directives.

## 1. Scope Containment & Pure Agent Principle
To ensure clean deployment and ingestion by the Hubscape platform, this repository follows the **Pure Agent Principle**:
* Only modify the core files accepted by the GitOps ingestion pipeline:
  * `config.json` (At root: Metadata, RBAC permissions, UI settings, Secrets declarations)
  * `agents/{agent_id}/` package:
    * `__init__.py` (Standard initialization exposing the `root_agent`)
    * `agent.py` (LlmAgent setup)
    * `prompt.py` (Contains `SYSTEM_PROMPT` string)
    * `tools.py` (Python functions acting as tools)
    * `api.py` (FastAPI route handlers)
    * `pyproject.toml` (Package config and dependency listings)
  * `widgets/` (Optional custom Lego UI JSON widgets)
  * `static/` (Optional static asset files and iframes)
* Do **NOT** commit, modify, or reference any local sandbox test files (`local_db.json`, `.env`, `.agent/`, or virtual environment folders) in your production logic.

## 2. Model Context Protocol (MCP) & Agent-to-Agent (A2A) Connections
Custom agents must route all external connections and tool calls through the standardized platform interfaces:
* **Programmatic MCP Calls:** When manually calling tools from whitelisted `mcp_servers` in Python logic, load the configuration relative to the agent folder dynamically and invoke using the context tool client:
  ```python
  import os
  import json

  # Load config.json dynamically
  agent_dir = os.path.dirname(os.path.abspath(__file__))
  with open(os.path.join(agent_dir, "..", "..", "config.json"), "r") as f:
      config = json.load(f)
  
  mcp_config = config.get("mcp_servers", {}).get("server_key")

  await context.mcp.call_tool(
      agent_id=context.auth.agent_id,
      server_name="server_key",
      tool_name="tool_name",
      arguments=arguments,
      config=mcp_config,
      context=context
  )
  ```
* **A2A Outbound Calls:** When invoking tools on another agent, use the correct router signature:
  ```python
  await context.agents.call_external_tool(ext_agent_key="target_agent", tool_name="tool", arguments={})
  ```

## 3. Database Scoping & Index-Free Queries
* **Scoping Helper Paths:** Always read and write to Firestore collections using platform-provided scope context helper methods on `context` (e.g. `context.save_agent_data`, `context.get_agent_data`, `context.delete_agent_data`, `context.list_agent_data`).
* **NO Custom Indexes:** You are strictly forbidden from writing query code that requires custom composite index definitions. All database searches must use in-memory sorting or denormalized composite keys to guarantee full compliance with the platform's **Index-Free Database Query Guidelines**.

## 4. Platform Secrets Vault Fallback
* Never hardcode API keys, tokens, or credentials in files.
* Retrieve all external credentials using the sandbox-safe fallback pattern:
  ```python
  api_key = await context.get_agent_secret("KEY_NAME") or os.environ.get("KEY_NAME")
  ```

## 5. Event Logging & Telemetry
* Every call made to a paid external API or provider (e.g. Stripe, Twilio, Google AI) MUST produce a transaction log:
  ```python
  await context.streamer.log_transaction(
      event_type="YOUR_EVENT_TYPE", 
      successful=True, 
      details={"key": "value"}
  )
  ```
* Ensure failed calls are also logged with `successful=False` to maintain billing audit integrity.

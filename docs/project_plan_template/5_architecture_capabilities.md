## 🛠️ 5. Architecture & Capabilities

### System Instructions (`app/SKILL.md`)
```text
<!-- Paste the system instructions that will be configured in app/SKILL.md. Use clear, concise instructions defining agent personality, routing cues, and logic boundaries. -->
```

### Tool Implementations (`app/scripts/`)
Define the Python function signatures, docstrings, type-hints, and return types for each tool inside the package's `app/scripts/` folder as individual `{tool_name}.py` files. The ADK automatically parses these to build Gemini function declarations.

```python
# app/scripts/{{tool_name}}.py
async def {{tool_name}}(tool_context: ToolContext, {{param_name}}: {{type}}) -> dict:
    """
    <!-- Clear description for the LLM -->

    Args:
        {{param_name}}: <!-- Parameter purpose, format, or bounds -->
    """
    # Tool implementation logic...
```

### 🔑 Tool Privileges Matrix
Defines which platform-level privileges grant access to which specific capabilities and tools.

| Privilege Name | Description of Granted Capabilities / Tools |
| :--- | :--- |
| `<!-- e.g. HUB_ADMIN -->` | `<!-- e.g. Allows administering the workspace hub, managing sub-agents, and deleting workspace resources. -->` |



### Model Context Protocol (MCP) & Agent-to-Agent (A2A) Connections
Define any external connections (MCP servers, custom OAuth providers, or external agents).

*   **MCP Servers:**
    *   *Server Key:* `<!-- e.g. github_mcp -->`
    *   *Type:* `<!-- sse (production mandate) or stdio (local sandbox only) -->`
    *   *URL / Command:* `<!-- Connection URL or command line string -->`
    *   *Auth Provider & Scopes:* `<!-- e.g. github, scopes: ["repo"] -->`
    *   *Tools Whitelist:* `<!-- Whitelisted tool names -->`
*   **External Agents (A2A):**
    *   *Agent Key:* `<!-- e.g. salesforce_copilot -->`
    *   *Endpoint:* `<!-- outbound HTTP JSON-RPC endpoint -->`
    *   *Auth Provider & Scopes:* `<!-- e.g. salesforce, scopes: ["api"] -->`
    *   *Tools Whitelist:* `<!-- Whitelisted tool names -->`
*   **Custom OAuth2 Providers:**
    *   *Provider Key:* `<!-- e.g. my_custom_provider -->`
    *   *Authorization URL:* `<!-- authorization endpoint -->`
    *   *Token URL:* `<!-- token exchange endpoint -->`
    *   *Default Scopes:* `<!-- scopes list -->`

### Required Secrets (Agent Secrets Vault)
Define any external API keys or client secrets that must be configured and uploaded to the platform Secrets Vault.

| Secret Name | Description | Required? (True/False) |
| :--- | :--- | :--- |
| `<!-- SECRET_NAME -->` | `<!-- Purpose of this secret -->` | `<!-- True/False -->` |

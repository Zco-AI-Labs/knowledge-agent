# Chapter 4: RemoteContext, Scopes, and File Storage

The `RemoteContext` object (retrieved via `get_context()` inside a tool script) is the agent's gateway to the platform's state, user authentication details, Firestore database operations, and Google Cloud Storage (GCS) assets.

---

## 1. Authentication Details (`context.auth`)

Retrieve user and organizational scopes from `context.auth`:
* `context.auth.get_user_id()`: Returns the unique UUID of the active user.
* `context.auth.org_id`: The organization UUID (always populated).
* `context.auth.hub_id`: The active Hub UUID (may be `None` if org-scoped).

---

## 2. Standardized Database Scopes

To enforce strict data isolation between users, organizations, and hubs, Firestore paths are dynamically resolved based on the chosen scope parameter:

* **`user` Scope:** Scoped to the individual user.
  `platform_users/{user_id}/agent_data/{agent_id}/{collection_name}/`
* **`hub` Scope:** Scoped to the active hub (visible to all hub members).
  `organizations/{org_id}/hubs/{hub_id}/agent_data/{agent_id}/{collection_name}/`
* **`org` Scope:** Scoped to the organization.
  `organizations/{org_id}/agent_data/{agent_id}/{collection_name}/`
* **`platform` Scope:** Shared globally by the agent across the platform.
  `agents/{agent_id}/agent_data/platform/{collection_name}/`

### Database Methods on `RemoteContext`:
* `context.save(scope, collection_name, doc_id, data)`: Creates or merges data. Automatically appends audit metadata (`created_by`, `created_at`, `updated_by`, `updated_at`, `version`).
* `context.get(scope, collection_name, doc_id)`: Retrieves a document from the scoped path.
* `context.delete(scope, collection_name, doc_id)`: Deletes the specified document.
* `context.list(scope, collection_name)`: Returns a list of all documents in the collection path.

---

## 3. Persistent File Storage (GCS)

Standard GCS storage is fully integrated via context file methods. Like database scopes, file storage paths are automatically isolated based on the scope parameter:

### File Storage Methods on `RemoteContext`:
* `context.save_file(scope, filename, content, content_type=None)`: Uploads raw binary file content (bytes) to GCS and returns a dictionary containing the GCS storage path and a secure download URL.
* `context.get_file(scope, filename)`: Downloads and returns the binary content (`bytes`) of the file from GCS.
* `context.delete_file(scope, filename)`: Permanently deletes the file from GCS.

---

## 4. Index-Free Query Rules

The platform does not support custom composite indexes in production databases. 
* **Rule:** Do not write queries containing multiple inequality filters, order-by clauses on unindexed fields, or filtering across multiple ranges.
* **Workaround:** If you need complex queries, fetch the list of scoped records into memory using `context.list(scope, collection_name)` and perform sorting, filtering, or slicing programmatically in Python.

---

## 5. Agent Observability, Telemetry & Billing Logs

Because custom agent action events (like RAG database queries, external API lookups, web scraping, or custom payments) are **not** standard GenAI model inference calls, they are **not** automatically telemetry-logged by Google's Vertex AI model pipeline. 

Developers implementing paid custom tools must adhere to the following telemetry standard:

1. **Direct Cloud Logging (For Analytical Graphs & Stats):**
   Stream a structured telemetry payload directly to the platform's central logging stream `logs/hubscape.platform.transactions` using the `google-cloud-logging` SDK. The Log Router will automatically sync this payload to the BigQuery transactional warehouse for analytics reporting.
2. **Direct Firestore Increments (For Real-time Wallets):**
   Deduct system credits from the organization's billing balance in Firestore immediately to ensure real-time credit checks update accurately in the client's web browser.
3. **Graceful Degradation:**
   Always wrap the logging client creation and write statements in a `try/except` block to ensure logging failures (such as local testing environments running outside GCP context) do not crash the agent's core tool logic.

### Implementation Template:
```python
def my_custom_paid_tool(param: str) -> dict:
    """Performs a paid action.
    """
    context = get_context()
    db_client = context._db_client
    org_id = context.auth.org_id
    hub_id = context.auth.hub_id

    # 1. Execute primary tool logic...
    result = {"status": "success"}

    # 2. Write Telemetry & Billing Logs
    try:
        from datetime import datetime
        from google.cloud import firestore
        from google.cloud import logging as gcp_logging
        
        event_payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "successful": True,
            "hubId": hub_id,
            "orgId": org_id,
            "userId": context.auth.get_user_id(),
            "agentId": context.auth.agent_id,
            "type": "my_custom_event_type",  # Map to standard enums or string
            "provider": "Vertex AI / Tool",
            "modelId": "Custom Tool Name",   # Appears as the resource name in UI
            "metadata": {
                "systemCredits": 100,         # Flat credit rate for this action
                "estimatedCostUsd": 0.01
            }
        }
        # Remove empty keys
        event_payload = {k: v for k, v in event_payload.items() if v is not None}
        
        # A. Stream directly to BigQuery (via Cloud Logging)
        try:
            gcp_client = gcp_logging.Client()
            logger_gcp = gcp_client.logger("hubscape.platform.transactions")
            logger_gcp.log_struct(event_payload, severity="INFO")
        except Exception as log_err:
            logger.warning(f"Cloud Logging failed: {log_err}")  # Bypassed locally

        # B. Debit Org Billing Wallet in Firestore
        if org_id:
            billing_ref = db_client.collection("organizations").document(org_id).collection("billing").document("status")
            billing_ref.update({
                "creditsAvailable": firestore.Increment(-100),
                "creditsUsed": firestore.Increment(100),
                "lastUpdated": firestore.SERVER_TIMESTAMP
            })
    except Exception as e:
        logger.warning(f"General billing telemetry failure: {e}")

    return result
```

---

[Next Chapter: Sandbox Emulation & Parity Details](CHAPTER_5_SANDBOX_EMULATION.md) | [Previous Chapter: Tool Scripts](CHAPTER_3_TOOLS_AND_PROMPTS.md)

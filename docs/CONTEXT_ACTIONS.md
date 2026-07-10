# Context Actions Documentation

This document provides a comprehensive guide on the platform context capabilities in the Hubscape Agent Development Kit (ADK). These operations are implemented in [app/core/hubscape_adk.py](../app/core/hubscape_adk.py) under the [RemoteContext](../app/core/hubscape_adk.py#L19) class.


---


## 1. Overview of Context Lifecycle

In the ADK, every tool invocation runs within an active session. The current execution thread stores the active [RemoteContext](../app/core/hubscape_adk.py#L19) instance in a thread-local context variable (`_current_context`).

To obtain the current context within your tool implementation, import and call [get_context()](../app/core/hubscape_adk.py#L303):

```python
from app.core.hubscape_adk import get_context

# Retrieve the active context
context = get_context()
```

> [!NOTE]
> If a tool is executed outside a valid [context_session](../app/core/hubscape_adk.py#L316) during local execution, the system falls back to a global mock context if available, otherwise it raises a `RuntimeError`.


---


## 2. Understanding Database & Storage Scopes

All database (Firestore) and file storage (Google Cloud Storage) actions require a `scope` argument. This scope segregates and permissions data access.

| Scope | Firestore Collection Path Pattern | Storage (GCS) Prefix Pattern | Pre-requisites / Rules |
| :--- | :--- | :--- | :--- |
| **`user`** | `platform_users/{userId}/agent_data/{agentId}/{collectionName}` | `agents/{agentId}/user/{userId}/{filename}` | Requires an authenticated `user_id` to be present in context auth metadata. |
| **`hub`** | `organizations/{orgId}/hubs/{hubId}/agent_data/{agentId}/{collectionName}` | `agents/{agentId}/hub/{hubId}/{filename}` | Requires both `org_id` and `hub_id` to be present in context auth metadata. |
| **`org`** | `organizations/{orgId}/agent_data/{agentId}/{collectionName}` | `agents/{agentId}/org/{orgId}/{filename}` | Requires `org_id` to be present in context auth metadata. |
| **`platform`** | `agents/{agentId}/agent_data/platform/{collectionName}` | `agents/{agentId}/platform/{filename}` | Global agent-specific platform scope. |


---


## 3. Database Scoped CRUD Operations

Database operations interact directly with Google Cloud Firestore. The helper methods automatically resolve the complex hierarchical paths based on the requested scope.


### A. [save()](../app/core/hubscape_adk.py#L77)
* **Signature:** `def save(self, scope: str, collection_name: str, doc_id: str, data: dict) -> dict`
* **Description:** Persists or merges a dictionary of data into a Firestore document.
* **Responsibilities:**
  * **Path Resolution:** Calls [get_agent_db_path()](../app/core/hubscape_adk.py#L57) to compute the exact Firestore document path based on scope, collection, and document ID.
  * **Metadata Tracking & Versioning:** 
    * If the document **does not exist**, the method injects audit timestamps (`created_at` & `updated_at` in ISO-8601 UTC format), creator/updater identification (`created_by` & `updated_by` mapped to the active user's ID), and initializes `version` to `1`.
    * If the document **already exists**, it preserves the original creation metadata, sets `updated_at` and `updated_by` to the current session details, and increments the `version` field by `1`.
  * **Persistence:** Saves/merges the payload using `.set(payload, merge=True)`.
  * **Return Value:** Returns the final mutated dictionary payload including all generated metadata.


### B. [get()](../app/core/hubscape_adk.py#L108)
* **Signature:** `def get(self, scope: str, collection_name: str, doc_id: str) -> Optional[dict]`
* **Description:** Retrieves a single document from Firestore.
* **Responsibilities:**
  * Computes the document path and requests the snapshot from Firestore.
  * If the document exists, converts the document data to a dictionary, injects the document ID under the key `"id"`, and returns the dictionary.
  * If the document does not exist, returns `None`.


### C. [delete()](../app/core/hubscape_adk.py#L129)
* **Signature:** `def delete(self, scope: str, collection_name: str, doc_id: str)`
* **Description:** Removes a single document from Firestore.
* **Responsibilities:**
  * Computes the document path and triggers the Firestore `.delete()` method on the reference.


### D. [list()](../app/core/hubscape_adk.py#L118)
* **Signature:** `def list(self, scope: str, collection_name: str) -> list`
* **Description:** Streams and retrieves all documents within a given collection under the specified scope.
* **Responsibilities:**
  * Streams all matching documents from the scoped collection path, injects their document IDs as `"id"`, and returns a list of dictionary representations.


---


## 4. Google Cloud Storage (GCS) / File Scoped Operations

File-based context operations interface with Google Cloud Storage / Firebase Storage to upload, read, or delete binary files.


### A. [save_file()](../app/core/hubscape_adk.py#L201)
* **Signature:** `def save_file(self, scope: str, filename: str, content: bytes, content_type: Optional[str] = None) -> dict`
* **Description:** Uploads a binary blob/file to the configured Firebase Storage bucket under the scoped path.
* **Responsibilities:**
  * **Path Resolution:** Resolves the destination path in GCS using [get_agent_storage_path()](../app/core/hubscape_adk.py#L171).
  * **Client Configuration:** Lazily fetches GCS credentials/client using [_storage_client](../app/core/hubscape_adk.py#L135) and targets the storage bucket via [_storage_bucket](../app/core/hubscape_adk.py#L160).
  * **Upload Execution:** Uploads the raw bytes via `.upload_from_string()` with the specified `content_type`.
  * **URL Generation:** Encodes the file path and generates a public-facing Firebase Storage download URL:
    `https://firebasestorage.googleapis.com/v0/b/{bucket_name}/o/{encoded_path}?alt=media`
  * **Return Value:** Returns a dictionary containing `"storage_path"` (the relative GCS path) and `"download_url"` (the direct media link).


### B. [get_file()](../app/core/hubscape_adk.py#L220)
* **Signature:** `def get_file(self, scope: str, filename: str) -> Optional[bytes]`
* **Description:** Downloads file content as raw bytes from the GCS bucket.
* **Responsibilities:**
  * Computes the storage path, checks for file existence via `.exists()`, and downloads the bytes using `.download_as_bytes()`.
  * Returns `None` if the file doesn't exist in the storage bucket.


### C. [delete_file()](../app/core/hubscape_adk.py#L231)
* **Signature:** `def delete_file(self, scope: str, filename: str)`
* **Description:** Deletes a file from the GCS bucket.
* **Responsibilities:**
  * Computes the storage path, checks for file existence, and deletes the blob from the bucket.


---


## 5. Other Actionable Context Methods

In addition to data persistence, [RemoteContext](../app/core/hubscape_adk.py#L19) is responsible for queueing user interface updates for the host application client.

* **[show_widget()](../app/core/hubscape_adk.py#L241):** Reads a predefined JSON widget template from either `app/ui/widgets/` (ADK standard) or `app/widgets/` (GEAP standard), binds provided data parameters, and appends an `OPEN_AGENT_WIDGET` action to the client execution queue (`context.actions`).
* **[show_custom_ui()](../app/core/hubscape_adk.py#L285):** Dynamically queues a layout generated at runtime by the LLM as an `OPEN_AGENT_WIDGET` directive (provided `allow_generative_ui` is enabled).

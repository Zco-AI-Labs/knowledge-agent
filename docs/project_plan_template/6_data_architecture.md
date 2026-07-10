## 💾 6. Data Architecture & DB Schemas
Define the collections, subcollections, fields, and indexes. Strictly adhere to ADK scoping paths:
*   **User Scope:** `platform_users/{user_id}/agent_data/{agent_id}/{collection_name}`
*   **Hub Scope:** `organizations/{org_id}/hubs/{hub_id}/agent_data/{agent_id}/{collection_name}`
*   **Org Scope:** `organizations/{org_id}/agent_data/{agent_id}/{collection_name}`
*   **User Tokens:** `platform_users/{user_id}/tokens/{agent_id}/{token_name}`

### Collection: `<!-- collection_name -->`
*   **Scope:** `<!-- user / hub / org -->`
*   **Document ID Format:** `<!-- e.g. evt_{timestamp} or UUID -->`

#### Fields Table
| Field Name | Type | Description | Mandatory / Optional |
| :--- | :--- | :--- | :--- |
| `id` | `String` | Document ID duplicated in payload (for collection groups) | Mandatory |
| `created_at` | `Timestamp` | Injected automatically by context helpers | Mandatory |
| `created_by` | `String` | Injected automatically by context helpers | Mandatory |
| `updated_at` | `Timestamp` | Injected automatically by context helpers | Mandatory |
| `updated_by` | `String` | Injected automatically by context helpers | Mandatory |
| `version` | `Integer` | Injected automatically by context helpers | Mandatory |
| `<!-- custom_field -->` | `<!-- Type -->` | `<!-- Description -->` | `<!-- Status -->` |

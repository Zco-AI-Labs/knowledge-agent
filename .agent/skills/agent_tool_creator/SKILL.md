---
name: Agent Tool Creator
description: Expert at breaking down the requirements, schemas, and context behaviors needed to implement custom tools in the Hubscape ADK/GEAP system.
---

# Agent Tool Creator Skill

You are the **Hubscape Agent Tool Creator**. Your primary mission is to guide the implementation of custom Python tool functions that are robust, secure, and properly integrated with the Hubscape ADK and Gemini Enterprise Agent Platform (GEAP) frameworks.

---

## 🚨 Mandatory Tool Implementation Standards

Every tool implemented or modified **MUST** strictly adhere to the following checklist. Do **NOT** skip any step, even for simple utility, helper, or calculation functions:

1. **Error Isolation & Resilience:** Wrap the entire tool body in a `try-except` block to ensure runtime exceptions do not crash the agent or platform.
2. **Standard Error Observability:** Catch the base `Exception`, extract the full traceback using `traceback.format_exc()`, log the error with `logger.error(...)`, and return a clear error dict structure.
3. **Caller Identity & Context Audit:** Retrieve the active execution context using `hubscape_adk.get_context()`. Log the requesting user ID (`context.auth.get_user_id()`) for security audits.
4. **Standardized Return Type:** The return type **MUST** be a JSON-serializable `dict` (e.g. `{"status": "success", ...}` or `{"status": "error", "message": ...}`).

---


## 🏛️ Tool Registry & Location Options

Ensure every custom tool is placed in a standalone file under `app/scripts/` (e.g. `app/scripts/add_task.py`) containing a single function with the exact same name as the file.

---

## 📐 Schema Generation Contract (Docstring & Typing)

Vertex AI Reasoning Engines dynamically derive the model's tool schema from Python function declarations. You **MUST** strictly adhere to this format:

1. **Type Annotations:** All function parameters must have explicit type hints (e.g., `task_name: str`, `priority: int = 1`, `due_date: Optional[str] = None`).
2. **Detailed Docstring:** You must write a descriptive docstring with a general description and a detailed `Args:` block describing every parameter.
3. **Observation Return Value:** The function must return a JSON-serializable structure, typically a `dict` (such as `{"status": "success", "message": "..."}`).

### Example Schema Declaration:
```python
def add_task(task_name: str, priority: int = 1) -> dict:
    """Adds a new task to the user's to-do list.

    Args:
        task_name: The description or name of the task to add.
        priority: The priority score of the task (default is 1).
    """
    pass
```

---

## 🔑 The Power of Context (`RemoteContext`)

The `RemoteContext` (retrieved via `hubscape_adk.get_context()`) is a fundamental gatekeeper for security, database isolation, client interactions, and platform adaptability.

### 1. Database Scoping & Auditing (Firestore Scopes)
Tools must read and write data through Firestore scopes to prevent cross-tenant and cross-user leaks. Never query Firestore collections using raw custom paths.
* **`scope="user"`:** Private to the active user. Resolves to:
  `platform_users/{userId}/agent_data/{agentId}/{collection_name}/{docId}`
* **`scope="hub"`:** Shared workspace within the organization. Resolves to:
  `organizations/{orgId}/hubs/{hubId}/agent_data/{agentId}/{collection_name}/{docId}`
* **`scope="org"`:** Shared org-wide settings. Resolves to:
  `organizations/{orgId}/agent_data/{agentId}/{collection_name}/{docId}`

> [!NOTE]
> **Audit Metadata Injection:** The `context.save()` method automatically injects and maintains the auditing metadata block (`created_at`, `created_by`, `updated_at`, `updated_by`, `version`), so do not write these fields manually in your tools.

### 2. Client Action Queuing (`context.actions`)
Tools can request the host application UI to perform navigation, quick replies, rendering layouts, or call termination by appending action payloads to `context.actions`:
* **`OPEN_AGENT_WIDGET`:** Queues rendering of dynamic dynamic widget configurations.
* **`SET_SUGGESTIONS`:** Sets list of prompt suggestions for the chat interface.
* **`SWITCH_HUB`:** Navigates the user to a different hub workspace.
* **`END_CALL`:** Terminates live voice call connections.

### 3. Interface Mode Adaptation (Chat vs. Voice vs. SMS)
Tools should check the active interface mode to format observations appropriately:
* **Chat Mode:** Use `context.show_widget(widget_id)` to queue interactive UI widgets.
* **Voice Mode:** Return concise, natural text responses optimized for text-to-speech, and avoid queuing complex UI cards. Use the `END_CALL` action directive if the conversation is concluded.
* **SMS Mode:** Return brief, text-only summaries.

---

## 🛠️ Code Blueprints & Standard Formats

### 1. Standard Task Creation Tool (Database Scope)
This blueprint demonstrates database scoping, automatic ID generation, context retrieval, error tracebacks, and structured response logging:

```python
import uuid
import logging
import traceback
import hubscape_adk

logger = logging.getLogger(__name__)

def add_task(task_name: str) -> dict:
    """Adds a new task to the user's to-do list.

    Args:
        task_name: The description or name of the task to add.
    """
    try:
        context = hubscape_adk.get_context()
        user_id = context.auth.get_user_id()
        logger.info(f"Adding task '{task_name}' for user {user_id}")
        
        task_id = uuid.uuid4().hex
        
        # Save scoped data securely under the active user's document
        context.save(
            scope="user",
            collection_name="tasks",
            doc_id=task_id,
            data={
                "name": task_name,
                "status": "open"
            }
        )
        
        return {
            "status": "success",
            "message": f"Task '{task_name}' added successfully.",
            "task_id": task_id
        }
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Error adding task: {e}\n{tb}")
        return {
            "status": "error",
            "message": f"Failed to add task: {str(e)}",
            "traceback": tb
        }
```

### 2. Mode-Adapting Telephony Tool (Voice and Action Queues)
This blueprint demonstrates checking interaction mode (Voice vs. Chat) and sending client directives to terminate the call:

```python
import logging
import hubscape_adk

logger = logging.getLogger(__name__)

def finalize_checkout(order_id: str) -> dict:
    """Confirms checkout and terminates the order workflow.

    Args:
        order_id: The ID of the order to finalize.
    """
    try:
        context = hubscape_adk.get_context()
        mode = context.raw_context.get("mode") or "chat"
        logger.info(f"Finalizing order {order_id} in {mode} mode.")
        
        # Update order state in org-scoped collection
        context.save(
            scope="org",
            collection_name="orders",
            doc_id=order_id,
            data={"status": "completed"}
        )
        
        # Adapt UI & Outbound Directives based on Interface Mode
        if mode == "voice":
            # For voice telephony, queue standard call termination directive
            context.actions.append({"type": "END_CALL"})
            message = "Your order has been placed successfully. Thank you for shopping with us! Goodbye."
        else:
            # For chat interface, suggest quick next-step queries and show order status widget
            context.actions.append({
                "type": "SET_SUGGESTIONS", 
                "queries": ["View My Orders", "Browse Catalog"]
            })
            context.show_widget(widget_template_id="order_summary", data={"order_id": order_id})
            message = f"Order {order_id} has been confirmed. You can review details in the widget below."
            
        return {
            "status": "success",
            "message": message,
            "order_id": order_id
        }
    except Exception as e:
        logger.error(f"Error finalizing checkout: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to finalize order: {str(e)}"
        }

### 3. Standard Utility/Helper Tool Template
This blueprint demonstrates how to write a simple helper or utility tool (e.g., date fetching, string formatting, calculations) that fully adheres to the mandatory context, RBAC, logging, and error isolation standards:

```python
import logging
import traceback
import hubscape_adk

logger = logging.getLogger(__name__)

def parse_user_date(date_str: str) -> dict:
    """Parses a user-supplied date string and returns structured metadata.

    Args:
        date_str: The raw date string supplied by the user (e.g. '2026-06-26').
    """
    try:
        # 1. Retrieve RemoteContext & Audit Caller
        context = hubscape_adk.get_context()
        user_id = context.auth.get_user_id()
        logger.info(f"User '{user_id}' requested date parsing for '{date_str}'")
        
        # 2. Core Logic
        import datetime
        parsed = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        
        return {
            "status": "success",
            "formatted": parsed.strftime("%A, %B %d, %Y"),
            "year": parsed.year,
            "month": parsed.month,
            "day": parsed.day
        }
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Error parsing date '{date_str}': {e}\n{tb}")
        return {
            "status": "error",
            "message": f"Failed to parse date: {str(e)}",
            "traceback": tb
        }
```
```

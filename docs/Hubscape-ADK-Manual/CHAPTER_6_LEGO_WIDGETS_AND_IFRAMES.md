# Chapter 6: Lego Widgets & Sandboxed IFrames

Custom agents can display rich interfaces inside the companion chat UI. Simple forms are built using declarative JSON (Lego Widgets), while complex visuals (such as poster compositors or canvas editors) use custom HTML iframes.

---

## 1. Declarative Lego Widgets

Lego widgets are JSON files representing a tree of nested components. They must be saved inside:
`app/ui/widgets/<widget_name>.json`

### Data Binding Rules:
1. **Flat Keys:** The React UI parser flattens variables passed to widgets. Reference keys directly (e.g. use `{{image_url}}` rather than `{{data.image_url}}`).
2. **No Dot Notation:** Variable placeholders are parsed using the regex pattern `/\{\{\s*(\w+)\s*\}\}/g`. Because dots (`.`) are not word characters, placeholders containing dots will fail to parse and render literally in the DOM.

---

## 2. Visual Sandboxed IFrames (`iframe`)

For complex UIs requiring canvas interactions, dragging, or real-time editing, use the `iframe` Lego component to embed custom HTML files:

```json
{
  "type": "iframe",
  "props": {
    "src": "/api/agents/{{agent_id}}/static/my_widget.html",
    "className": "w-full h-[600px] border-0 rounded-xl"
  }
}
```

* **Relative Src Rule:** Always use relative platform paths (e.g. `/api/agents/{{agent_id}}/static/widget.html`) inside the `src` property. Never hardcode absolute URLs or ports (like `http://localhost:8090/...`) as they will fail when deployed to production cloud routing.

---

## 3. Bidirectional IFrame Communication

Because GEAP/ADK agent containers are sandboxed, iframes cannot directly send HTTP requests (`fetch` or `Axios`) to custom agent API routes. Instead, they communicate using standard HTML5 browser messages:

```text
  Custom HTML (IFrame)                 Hubscape Chat UI                     Agent Container
------------------------               ----------------                     ---------------
window.parent.postMessage()  ----->    Intercepts Submit       ----->       Executes Python Tool
                                       Sends HTTP POST                      (e.g., generate_qr)
IFrame Message Listener      <-----    Returns tool response   <-----       Returns JSON Dict
```

### 1. Sending an Action from inside the IFrame
When the user clicks a button inside your HTML page, post a message containing the tool name and payload arguments to the parent window:
```javascript
// Extract dynamic agent ID from window pathname
const pathParts = window.location.pathname.split('/');
const agentId = ((pathParts[2] === 'plugins' || pathParts[2] === 'agents') && pathParts[3]) ? pathParts[3] : 'my_agent';

window.parent.postMessage({
  type: 'SUBMIT_FORM',
  actionUrl: `agent://${agentId}/my_backend_tool`,
  payload: { param1: 'value1' }
}, '*');
```

### 2. Processing the Response
The parent Hubscape container captures this request, executes the corresponding Python tool script (e.g., `app/scripts/my_backend_tool.py`), and posts the tool's JSON output back to the iframe. Listen for this response in your HTML JavaScript:
```javascript
window.addEventListener('message', (event) => {
  const data = event.data;
  if (data && data.type === 'TOOL_RESPONSE') {
    console.log("Received data from Python script:", data.payload);
    // Update HTML DOM visually
  }
});
```

---

## 4. Widget Closing Protocols (`client://` vs `agent://`)

Lego widgets support dual-channel closure: pure client-side UI actions and agent-driven programmatic closures.

### Option A: Pure Client-Side Button Action (`client://close_widget`)
Use `client://close_widget` (or `client://dismiss`) for cancel, close, or dismiss buttons in Lego JSON widget schemas. This unmounts the widget 100% locally on the browser with **zero network requests** and zero Host LLM calls:

```json
{
  "type": "button",
  "props": {
    "label": "Cancel",
    "actionUrl": "client://close_widget?text=Form+cancelled",
    "styling": { "colorTheme": "slate" }
  }
}
```

### Option B: Agent-Initiated Tool Closure (`context.close_widget()`)
For buttons with `agent://<action_name>`, the button submits data to the backend host agent. Inside a Python tool, call `context.close_widget()` to save state and instruct the client UI to unmount:

```python
from app.core.hubscape_adk import get_context

async def submit_and_close_form(data: str) -> dict:
    context = get_context()
    
    # 1. Process or save data...
    context.save(scope="user", collection_name="submissions", doc_id="form_1", data={"info": data})
    
    # 2. Append close directive action
    context.close_widget(result_text="Form submitted successfully! Widget closing.")
    
    return {"status": "success"}
```

This appends the `CLOSE_AGENT_WIDGET` action directive to the response payload:
```json
{
  "type": "CLOSE_AGENT_WIDGET",
  "payload": {
    "messageId": null,
    "resultText": "Form submitted successfully! Widget closing."
  }
}
```

---

## 5. Declarative Field Validation

Lego form inputs (`input`, `select`, `choice-picker`) support standardized declarative validation.

### Validation Properties:
* `required` (boolean | string): Ensures field is non-empty. Optional custom error string.
* `validationType` (string): Built-in format validator: `"email"`, `"phone"` (10+ digits, area code required), `"pattern"`, `"numeric"`, `"length"`.
* `pattern` (string): Custom Regular Expression string.
* `errorMessage` (string): Custom error message override displayed under field.

### Validation Example:
```json
{
  "type": "input",
  "props": {
    "name": "user_email",
    "label": "Email Address",
    "required": true,
    "validationType": "email",
    "errorMessage": "Valid structured email address required (e.g. officer@starfleet.org)."
  }
}
```

---

## 6. Live Error Banners (`live-error-banner`)

For live-monitored tasks or background streams, render a `live-error-banner` element to provide diagnostic feedback and retry buttons:

```json
{
  "type": "live-error-banner",
  "props": {
    "title": "Stream Process Error",
    "message": "Connection to the monitoring array timed out.",
    "errorCode": "ERR_TIMEOUT",
    "details": { "sensor_id": "array_01", "latency_ms": 30000 },
    "retryActionUrl": "agent://reconnect_sensor",
    "retryLabel": "Reconnect Sensor"
  }
}
```

---

[Next Chapter: OAuth Integration & Hubscape ADK API](CHAPTER_7_OAUTH_INTEGRATION_AND_ADK_API.md) | [Previous Chapter: Sandbox Emulation](CHAPTER_5_SANDBOX_EMULATION.md)


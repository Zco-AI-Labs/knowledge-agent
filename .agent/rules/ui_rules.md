# UI Rules: Custom Agent Lego Widget Standards

> [!IMPORTANT]
> These rules ensure that custom Lego UI widgets are structured correctly to render without issues in the Hubscape React frontend application.

## 1. Data Binding & Variable Interpolation Rules
When referencing dynamic data (such as image URLs, text variables, or button action URLs) inside JSON widget templates under `app/ui/widgets/` (or `widgets/`):

* **Use Flat Keys**: 
  The React frontend (`DynamicWidget.tsx`) automatically unwraps/flattens dynamic payload namespaces (`data`, `response`, `result`, `widget_data`, etc.). 
  * **Rule:** Do not prefix variables with `data.` or any namespace name. Reference keys directly at the root level.
  * **Correct:** `{{image_url}}`
  * **Incorrect:** `{{data.image_url}}`

* **No Dot Notation**:
  The frontend's template interpolator resolves variables using the regex pattern `/\{\{\s*(\w+)\s*\}\}/g`. Because a dot (`.`) is not matched by `\w`, the regex will completely ignore any placeholders containing a dot.
  * **Rule:** Never use dot notation or nested property paths inside template placeholders. If you need a nested property, flatten it in your backend python tool response before returning the widget payload.
  * **Correct:** `{{target}}`
  * **Incorrect:** `{{data.target}}`

## 2. Lego Widget Component & Registry Rules
* **Strict Catalog Compliance:** All widget files must be structured as nested Lego components complying with the official element catalog schema. The root component must be `"type": "container"` with nested `"children"` nodes.
* **No Deprecated/Custom Layouts:** Do not use custom layouts or legacy root schemas like `"layout": "list_tiles"`, `"layout": "card_grid"`, or mapping list arrays directly to top-level attributes. Use standard list structures (`list`, `table`, or nested `container` elements) to render collections of records.
* **Standard Component Registry:** Only instantiate components registered in the platform registry: `container`, `text`, `icon`, `image`, `spacer`, `button`, `input`, `select`, `iframe`, `calendar-grid`, `table`, `list`, `progress`, `youtube`, `media-player`, `file-handler`, `human-approval-gate`, `flow-chart`, `toggle`, `choice-picker`, `slider`, `tabs`, `accordion`.
* **Redirection Actions:** Do not use external domains (e.g. `https://www.google.com`) directly in a button's `actionUrl` prop. Buttons trigger form POST actions to the backend which will fail on cross-origin requests. Instead, render an `iframe` element pointing to a local static HTML page (e.g. `/api/agents/{{agent_id}}/static/redirect.html`) that uses a standard HTML anchor link with `target="_blank"`.
* **Forbid Hardcoded URLs in IFrames:** Never hardcode absolute host domains, ports, or protocols (e.g., `http://localhost:8090/...` or `https://my-app.com/...`) inside the `src` property of an `iframe` component. Hardcoded absolute URLs will break local testing ports and production cloud routing. Always use relative platform paths using the `{{agent_id}}` variable binding:
  * **Correct:** `/api/agents/{{agent_id}}/static/my_widget.html`
  * **Incorrect:** `http://localhost:8090/api/plugins/my_agent/my_widget.html`

## 3. Mandatory Widget Schema Validation Step
* **Rule:** Prior to implementing or modifying any widget JSON files under `app/ui/widgets/` (or `widgets/`), the agent MUST explicitly validate the proposed schema against the official [Lego Widgets & IFrames Guide](file:///Users/rajvekeria/Documents/GitHub/hubscape-agent-template/docs/Hubscape-Agent-Template-Guide/CHAPTER_6_LEGO_WIDGETS_AND_IFRAMES.md).
* **Validation Checklist:**
  1. Verify every component type is in the registry (e.g. no `card`, `title`, `text-input`, `dropdown`, or `metadata-grid`).
  2. Confirm inputs and dropdowns use `"name"` (not `"id"`) for payload keys.
  3. Ensure buttons and inputs use standard styling configurations (Tailwind classes in `"className"` or standard props) rather than custom properties like `"variant"`.

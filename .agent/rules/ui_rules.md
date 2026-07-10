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

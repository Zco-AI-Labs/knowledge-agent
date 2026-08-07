---
name: Agent UI Creator
description: Expert at designing and structuring JSON widget templates using the Hubscape Lego UI element catalog.
---

# Agent UI Creator Skill

You are the Hubscape UI/UX and Lego Widget Specialist. Your mission is to help the Captain design, structure, and create custom JSON widget templates that render seamlessly within the Hubscape frontend widget container.

---

## 🏗️ Lego Widget Architecture

Widgets are defined as declarative JSON files representing a tree of nested components.

### 1. File Location
All predefined widget templates must be saved in the agent's widget template directory:
* **Standard path:** `app/ui/widgets/<widget_name>.json` (or `widgets/<widget_name>.json` depending on configuration).

### 2. General JSON Schema
Every widget template consists of a root layout component (usually a `container`) with properties and nested child components:
```json
{
  "type": "container",
  "props": {
    "direction": "vertical",
    "gap": "sm",
    "padding": "md"
  },
  "children": [
    // Nested components go here
  ]
}
```

---

## 🧱 Core Component Catalog & Props

> [!IMPORTANT]
> **Official Component Reference:** For the complete specification and details on Lego UI elements, refer directly to the [Lego Widgets & IFrames Guide](file:///Users/rajvekeria/Documents/GitHub/hubscape-agent-template/docs/Hubscape-Agent-Template-Guide/CHAPTER_6_LEGO_WIDGETS_AND_IFRAMES> The standard registry of supported elements is:
> `container`, `text`, `icon`, `image`, `spacer`, `button`, `input`, `select`, `iframe`, `calendar-grid`, `table`, `list`, `progress`, `youtube`, `media-player`, `file-handler`, `human-approval-gate`, `flow-chart`, `toggle`, `choice-picker`, `slider`, `tabs`, `accordion`, `live-error-banner`.

Below are the most common component types and their configurations:

### 1. Container (`container`)
Groups and aligns nested components.
* **Props:**
  * `direction` (string): `"vertical"` or `"horizontal"`
  * `gap` (string): `"xs"`, `"sm"`, `"md"`, `"lg"`
  * `padding` (string): `"xs"`, `"sm"`, `"md"`, `"lg"`
  * `className` (string): Optional custom Tailwind utility classes for advanced styling.

### 2. Text (`text`)
Displays headings, labels, or paragraphs.
* **Props:**
  * `text` (string): The text content (supports variable binding/interpolation).
  * `size` (string): `"xs"`, `"sm"`, `"md"`, `"lg"`, `"xl"`
  * `weight` (string): `"normal"`, `"medium"`, `"bold"`
  * `className` (string): Optional Tailwind overrides.

### 3. Input (`input`)
Renders text fields, multi-line text areas, numeric entries, or date/time pickers.
* **Props:**
  * `name` (string): **REQUIRED.** The payload key. When submitted, the value entered is sent back under this key.
  * `label` (string): Label displayed above the input.
  * `placeholder` (string): Contextual hint inside the field.
  * `required` (boolean | string): Enforces non-empty field validation. Optional custom error string.
  * `validationType` (string): Built-in format validator: `"email"`, `"phone"` (requires area code), `"pattern"`, `"numeric"`, `"length"`.
  * `pattern` (string): Custom regex pattern for format matching.
  * `errorMessage` (string): Custom error message override displayed on validation failure.
  * `multiline` (boolean): If `true`, renders a text area instead of a single line.
  * `inputType` (string): `"text"`, `"email"`, `"number"`, `"date"`, or `"time"`. Defaults to `"text"`.

### 4. Button (`button`)
Renders interactive submit/action buttons.
* **Props:**
  * `label` (string): Display text of the button.
  * `actionUrl` (string): **REQUIRED.** The URI protocol to hit. Standard formats:
    * `agent://<action_name>`: Intercepted by the platform to trigger an async slash command callback `/action <action_name> <payload>` back to the agent.
    * `/api/plugins/{{agent_id}}/<route>`: Direct API POST call to the agent's webserver.
  * `styling` (object):
    * `colorTheme` (string): Accent color palette (e.g. `"blue"`, `"green"`, `"red"`).

### 5. Live Error Banner (`live-error-banner`)
Renders a standardized error alert card for live monitoring process failures with diagnostic details expander and optional retry actions.
* **Props:**
  * `title` (string): Header title (defaults to `"Operation Error Detected"`).
  * `message` (string): Human-readable error description.
  * `errorCode` (string, optional): Short error tag (e.g. `"ERR_PAYMENT_FAILED"`).
  * `details` (string | object, optional): Raw error stack trace or diagnostic payload.
  * `retryActionUrl` (string, optional): Action URL triggered when clicking "Retry Operation".
  * `retryLabel` (string, optional): Button label for retry action.

---

## 🛡️ Validation & Error Handling Protocol

When designing forms and interactive widgets:
1. **Declarative Validation**: Always include `required: true` and appropriate `validationType` (`"email"`, `"phone"`) for user input fields.
2. **Interactive Triggers**: Input fields validate automatically on blur (`onBlur`) and when submit buttons are clicked. Submission is blocked if invalid fields exist.
3. **Live Monitoring Errors**: When live operations or streaming tasks fail, render a `live-error-banner` widget element containing diagnostic details and retry actions.

---

## 📝 Practical Example: Validated Support Form Widget

Below is a complete, working reference widget template (`app/ui/widgets/contact_form.json`) using email and phone validation:

```json
{
  "type": "container",
  "props": {
    "direction": "vertical",
    "gap": "sm",
    "padding": "md"
  },
  "children": [
    {
      "type": "text",
      "props": {
        "text": "Contact Support Form",
        "size": "lg",
        "weight": "bold"
      }
    },
    {
      "type": "input",
      "props": {
        "name": "name",
        "label": "Your Name",
        "placeholder": "Enter your full name",
        "required": true,
        "errorMessage": "Full name is required"
      }
    },
    {
      "type": "input",
      "props": {
        "name": "email",
        "label": "Email Address",
        "placeholder": "officer@starfleet.org",
        "inputType": "email",
        "required": true,
        "validationType": "email",
        "errorMessage": "Please enter a valid email address (e.g. user@domain.com)"
      }
    },
    {
      "type": "input",
      "props": {
        "name": "phone",
        "label": "Phone Number",
        "placeholder": "(555) 019-2834",
        "required": true,
        "validationType": "phone",
        "errorMessage": "10-digit phone number with area code is required"
      }
    },
    {
      "type": "input",
      "props": {
        "name": "description",
        "label": "Description of Help Needed",
        "placeholder": "How can we help you?",
        "required": true,
        "multiline": true,
        "errorMessage": "Please describe your request"
      }
    },
    {
      "type": "button",
      "props": {
        "label": "Submit Contact Request",
        "actionUrl": "agent://save_contact",
        "styling": {
          "colorTheme": "blue"
        }
      }
    }
  ]
}
```   }
  ]
}

---

## ⚠️ Data Binding & Variable Interpolation Rules

When referencing dynamic data inside widget templates (e.g., text fields, image URLs, button action URLs):
* **Use Flat Keys**: The React frontend (`DynamicWidget.tsx`) automatically unwraps/flattens dynamic payload namespaces (`data`, `response`, `result`, `widget_data`, etc.). Therefore, reference keys directly (e.g., use `{{image_url}}` instead of `{{data.image_url}}`).
* **No Dot Notation**: The frontend's template interpolator matches variables using the regex `/\{\{\s*(\w+)\s*\}\}/g`. Because a dot (`.`) is not a word character (`\w`), the regex will fail to match placeholders containing dots, causing them to render literally in the DOM. Never use dots in template variable names.

---

## 🧱 Lego Component Schema Rules
1. **Catalog Enforcement:** Root elements MUST have `"type": "container"` with nested elements in `"children"`.
2. **Layout Enforcement:** Never invent custom layouts or schemas (like `"layout": "list_tiles"` or `"layout": "card_grid"`). Render grids or lists using the standard `list`, `table`, or nested `container` components.
3. **No External Redirection Buttons:** Buttons trigger backend form actions (POST). Do not assign full external URLs to `actionUrl`. Instead, load a local static helper page (e.g., `/api/agents/{{agent_id}}/static/redirect.html`) inside an `iframe` component that uses a standard anchor link with `target="_blank"`.
```

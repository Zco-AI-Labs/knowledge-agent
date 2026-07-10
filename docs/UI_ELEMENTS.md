# Hubscape ADK UI Elements Catalog

This catalog outlines the available **Lego UI elements** supported by the Hubscape ADK Generative UI renderer. Developers can use these components in predefined JSON widget templates or output them dynamically via `tools.py` generative layouts.

---

## 🎨 Styling Systems: Tailwind CSS vs. Explicit Props

Hubscape UI components support two main ways to control styling and layout:
1. **Tailwind Utility Classes (`className`):** Recommended for custom styling. You can pass standard Tailwind utility classes under `props.className` (e.g., `"props": { "className": "flex flex-col gap-4 p-4" }`).
2. **Explicit Layout Props:** For standard layouts, components support explicit keys inside `props` (e.g., `"direction": "vertical"`, `"gap": "sm"`, `"padding": "md"` for containers; `"size": "lg"`, `"weight": "bold"` for text; `"required": true`, `"multiline": true` for input fields). 

The examples in this catalog focus on the flexible Tailwind-based `className` styling system, but either approach (or a mixture of both) will render correctly. Refer to [contact_form.json](file:///Users/rajvekeria/Documents/GitHub/hubscape-agent-template/app/ui/widgets/contact_form.json) for a demonstration of explicit layout props.

---

## 🏗️ 1. Container (`container`)
Renders a container box to group children. Use Tailwind classes to design grids, flexboxes, margins, and backgrounds.

### Props:
* `className` (string): Standard Tailwind CSS utility classes.
* `children` (array): A list of nested element configurations.

### Example JSON:
```json
{
  "type": "container",
  "props": {
    "className": "flex flex-col gap-4 p-4 bg-slate-50 dark:bg-slate-900 rounded-xl"
  },
  "children": [
    {
      "type": "text",
      "props": { "text": "Container Title", "className": "font-bold" }
    }
  ]
}
```

---

## 📝 2. Text (`text`)
Displays formatted text blocks.

### Props:
* `text` (string): Text content to display. Supports variable interpolations if loaded from a widget template.
* `className` (string): Tailwind CSS classes for size, color, weight, and layout (e.g. `text-lg font-semibold text-slate-800`).

### Example JSON:
```json
{
  "type": "text",
  "props": {
    "text": "This is a descriptive text line.",
    "className": "text-xs text-slate-500 dark:text-slate-400"
  }
}
```

---

## 🔘 3. Button (`button`)
Renders a button. When clicked, it packages the input values of all elements inside its container parent and executes an HTTP POST to the specified `actionUrl`.

### Props:
* `label` (string): Button display text.
* `actionUrl` (string): The target endpoint path (e.g., `/api/plugins/{{agent_id}}/save`).
* `className` (string): Tailwind CSS utility styling classes.

### Example JSON:
```json
{
  "type": "button",
  "props": {
    "label": "Save Changes",
    "actionUrl": "/api/plugins/{{agent_id}}/update_settings",
    "className": "bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700"
  }
}
```

---

## ⌨️ 4. Input (`input`)
Renders standard form inputs, including text boxes, date pickers, time selectors, and numerical entries.

### Props:
* `name` (string): The payload key. When submitted, this element's value is sent to the backend under this field name.
* `label` (string): Input label displayed above the field.
* `placeholder` (string): Hint text.
* `inputType` (string): One of: `"text"`, `"date"`, `"time"`, `"number"`. Defaults to `"text"`.
* `className` (string): Styling overrides.

### Example JSON:
```json
{
  "type": "input",
  "props": {
    "name": "event_date",
    "label": "Event Date",
    "inputType": "date",
    "placeholder": "Select a date..."
  }
}
```

---

## 🗂️ 5. Select Dropdown (`select`)
Renders a dropdown selection menu.

### Props:
* `name` (string): The payload key. When submitted, the selected option's value is sent under this field name.
* `label` (string): Field label.
* `options` (array of objects): A list of items to select from. Each object must have:
  * `value` (string | number): The value sent to the API.
  * `label` (string): The user-friendly label displayed in the dropdown.
* `className` (string): Styling overrides.

### Example JSON:
```json
{
  "type": "select",
  "props": {
    "name": "priority",
    "label": "Event Priority",
    "options": [
      { "value": "low", "label": "Low Priority" },
      { "value": "medium", "label": "Medium Priority" },
      { "value": "high", "label": "High Priority" }
    ]
  }
}
```

---

## 📅 6. Calendar Grid (`calendar-grid`)
Exposes a responsive month calendar or week list. 

### Customization Sovereignty:
This element automatically consumes the user's platform preferences (`weekStartDay` and `excludeSundays`) from the parent session context, rotating headers and omitting Sunday columns dynamically without any developer input.

### Props:
* `view` (string): Either `"month"` (renders grid cells) or `"week"` (renders a list of events).
* `events` (array of objects): Array of calendar event details. Each object contains:
  * `id` (string, optional): Unique event identifier.
  * `title` (string): Event name.
  * `date` (string): Format `"YYYY-MM-DD"`.
  * `time` (string, optional): E.g. `"10:00 AM"`.
  * `color` (string, optional): Supported colors for highlight tag: `"blue"`, `"green"`, `"red"`.
* `className` (string): Styling overrides.

### Example JSON:
```json
{
  "type": "calendar-grid",
  "props": {
    "view": "month",
    "events": [
      { "id": "1", "title": "Dev Sync", "date": "2026-05-21", "color": "blue" },
      { "id": "2", "title": "Lunch Meeting", "date": "2026-05-22", "time": "12:00 PM", "color": "green" }
    ]
  }
}
```

---

## 🖥️ 7. Sandboxed IFrame (`iframe`)
An escape hatch to load custom, interactive HTML pages. Enables support for custom canvases, drawing pads, interactive charts, and external widget scripts.

### Props:
* `src` (string): Path to your static files (e.g. `/api/agents/{{agent_id}}/static/widget.html`).
* `height` (string): Container height (e.g., `"350px"`).
* `className` (string): Styling overrides.

### Communication (Bidirectional `postMessage`):
* **Submit data from inside the IFrame:**
  ```javascript
  // Extract dynamic agent ID from window pathname to construct the correct endpoint
  const pathParts = window.location.pathname.split('/');
  const agentId = ((pathParts[2] === 'plugins' || pathParts[2] === 'agents') && pathParts[3]) ? pathParts[3] : 'my_agent';

  window.parent.postMessage({
    type: 'SUBMIT_FORM',
    actionUrl: `/api/plugins/${agentId}/submit_data`,
    payload: { signature_path: '...' }
  }, '*');
  ```
* The host will perform the HTTP POST to your agent's API endpoint and send the backend's response back to your iframe page so you can trigger success animations.

### Example JSON:
```json
{
  "type": "iframe",
  "props": {
    "src": "/api/agents/{{agent_id}}/static/signature_pad.html",
    "height": "300px"
  }
}
```

---

## 🔐 8. OAuth Connection Card (`oauth`)
Renders a standardized premium card to request user authorization/connection approval for third-party platforms (e.g. GitHub, Google, Slack, Jira).

### Props:
* `providerName` / `provider_name` (string): Display name of the provider (e.g. `"GitHub"`).
* `authDescription` / `auth_description` (string): Context/instructions explaining why the integration is required.
* `actionUrl` / `action_url` (string): The API endpoint to post the redirect challenge request to (e.g. `/api/plugins/{{agent_id}}/authorize_github`).
* `className` (string): Styling overrides.

### Example JSON:
```json
{
  "type": "oauth",
  "props": {
    "providerName": "GitHub",
    "authDescription": "To verify GitHub OAuth functionality and list profile statistics, this agent requires connection approval.",
    "actionUrl": "/api/plugins/{{agent_id}}/authorize_github"
  }
}
```

---

## 🎛️ 9. Toggle Switch (`toggle`)
Renders a boolean checkbox or custom animated sliding toggle switch.

### Props:
* `name` (string): Payload field name.
* `label` (string): Description label.
* `variant` (string): `"checkbox"` or `"switch"`. Defaults to `"checkbox"`.
* `size` (string): `"sm"`, `"md"`, or `"lg"`.
* `colorTheme` (string): Accent color override.
* `borderRadius` (string): Border rounding override.

### Example JSON:
```json
{
  "type": "toggle",
  "props": {
    "name": "enable_notifications",
    "label": "Enable email alerts",
    "variant": "switch",
    "size": "md"
  }
}
```

---

## 🔘 10. Choice Picker (`choice-picker`)
Renders visible radio buttons or checkbox options (supports multi-selection lists).

### Props:
* `name` (string): Payload field name.
* `label` (string): Section header text.
* `options` (array of objects): Options array. Each object requires `value` and `label`.
* `multiSelect` (boolean): Set to `true` to allow choosing multiple items.
* `layout` (string): `"vertical"` or `"horizontal"`.
* `size` (string): `"sm"`, `"md"`, or `"lg"`.
* `colorTheme` (string): Accent color override.

### Example JSON:
```json
{
  "type": "choice-picker",
  "props": {
    "name": "hobbies",
    "label": "Select your hobbies",
    "multiSelect": true,
    "layout": "horizontal",
    "options": [
      { "value": "reading", "label": "Reading" },
      { "value": "hiking", "label": "Hiking" }
    ]
  }
}
```

---

## 🎚️ 11. Range Slider (`slider`)
Renders a numeric slider for selecting values within bounds.

### Props:
* `name` (string): Payload field name.
* `label` (string): Section title.
* `min` (number): Minimum boundary. Defaults to `0`.
* `max` (number): Maximum boundary. Defaults to `100`.
* `step` (number): Increments of slider steps. Defaults to `1`.
* `defaultValue` (number): Initial marker position. Defaults to `50`.
* `size` (string): `"sm"`, `"md"`, or `"lg"`.
* `colorTheme` (string): Accent color override.

### Example JSON:
```json
{
  "type": "slider",
  "props": {
    "name": "alert_threshold",
    "label": "Sensitivity Level",
    "min": 10,
    "max": 90,
    "step": 5,
    "defaultValue": 45
  }
}
```

---

## 🗂️ 12. Tabs Container (`tabs`)
Nestable container displaying switchable tab panels.

> [!WARNING]
> Multi-layered tabs (`tabs` nested within `tabs`) are automatically filtered out to ensure mobile screen safety.

### Props:
* `tabs` (array of objects): Active tabs. Each tab requires `id`, `label`, and a list of nested widget configurations under `children`.
* `size` (string): `"sm"`, `"md"`, or `"lg"`.
* `colorTheme` (string): Accent underline color.
* `borderRadius` (string): Rounding override.

### Example JSON:
```json
{
  "type": "tabs",
  "props": {
    "tabs": [
      {
        "id": "info",
        "label": "General Info",
        "children": [
          { "type": "text", "props": { "text": "This is tab 1 content." } }
        ]
      },
      {
        "id": "settings",
        "label": "Settings",
        "children": [
          { "type": "toggle", "props": { "name": "enabled", "label": "Active" } }
        ]
      }
    ]
  }
}
```

---

## 📂 13. Accordion (`accordion`)
Collapsible layout panel for toggling information details.

### Props:
* `title` (string): Collapse header label.
* `defaultOpen` (boolean): Initial state. Defaults to `false`.
* `size` (string): `"sm"`, `"md"`, or `"lg"`.
* `colorTheme` (string): Header highlight hover theme.
* `borderRadius` (string): Box rounding override.

### Example JSON:
```json
{
  "type": "accordion",
  "props": {
    "title": "Advanced Parameters",
    "defaultOpen": false
  },
  "children": [
    { "type": "text", "props": { "text": "Hidden configuration lines go here." } }
  ]
}
```

---

## 📊 14. Data Table (`table`)
Renders rows and columns of data, supporting column sorting and client-side pagination.

> [!IMPORTANT]
> **Mobile Responsive Reflow:** On viewports under 768px, the table automatically reflows into a list of stacked cards representing each row to prevent clipping.

### Props:
* `columns` (array of objects): Column definitions. Requires `key` and `name`. Supports `width` (string) and `sortable` (boolean).
* `rows` (array of objects): Row values mapped to column keys. Supports nesting simple UI widgets (like status buttons or switches) directly inside cells.
* `paginated` (boolean): Set to `true` to enable client pagination. Defaults to `false`.
* `pageSize` (number): Row count per page. Defaults to `5`.
* `size` (string): `"sm"`, `"md"`, or `"lg"`.
* `colorTheme` (string): Accent border and active pagination theme.

### Example JSON:
```json
{
  "type": "table",
  "props": {
    "paginated": true,
    "pageSize": 2,
    "columns": [
      { "key": "id", "name": "ID", "width": "20%" },
      { "key": "status", "name": "Status" }
    ],
    "rows": [
      { "id": "1", "status": "Active" },
      { "id": "2", "status": "Pending" }
    ]
  }
}
```

---

## 📜 15. Scrollable List (`list`)
A container to list simple repeating items or child layouts.

### Props:
* `items` (array): List of primitives or key-value structures. Used if no React children are nested.
* `scrollable` (boolean): Set to `true` to enable scrollbars. Defaults to `true`.
* `maxHeight` (string): Maximum boundary height (e.g. `"250px"`).
* `borderRadius` (string): Frame rounding override.

### Example JSON:
```json
{
  "type": "list",
  "props": {
    "scrollable": true,
    "maxHeight": "200px",
    "items": [
      "Item index 1",
      "Item index 2"
    ]
  }
}
```

---

## 📈 16. Progress Tracker (`progress`)
Renders vertical progress indicators, circular dials, or infinite spinners.

### Props:
* `value` (number): Value between `0` and `100`.
* `variant` (string): `"bar"`, `"circle"`, or `"spinner"`. Defaults to `"bar"`.
* `label` (string): Text annotation.
* `size` (string): `"sm"`, `"md"`, or `"lg"`.
* `colorTheme` (string): Fill accent theme.

### Example JSON:
```json
{
  "type": "progress",
  "props": {
    "value": 75,
    "variant": "circle",
    "label": "Loading data assets..."
  }
}
```

---

## 📺 17. YouTube Video (`youtube`)
Natively embeds a YouTube video frame using our lazy-loaded LiteYouTube thumbnail facade.

### Props:
* `url` (string): Full YouTube address.
* `videoId` (string): Target 11-character identifier. Used if `url` is absent.
* `start` (number): Offset time stamp in seconds.

### Example JSON:
```json
{
  "type": "youtube",
  "props": {
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "start": 42
  }
}
```

---

## 🔊 18. Media Player (`media-player`)
Streams local or remote video/audio files directly, with token decoration.

### Props:
* `src` (string): Path to media file (decorates tokens for `/api/media` calls).
* `mediaType` (string): `"video"` or `"audio"`. Defaults to `"video"`.
* `controls` (boolean): Toggle play controllers. Defaults to `true`.
* `autoplay` (boolean): Auto-start on load. Defaults to `false`.

### Example JSON:
```json
{
  "type": "media-player",
  "props": {
    "src": "/api/media/audio_clip.mp3",
    "mediaType": "audio"
  }
}
```

---

## 💾 19. File Handler (`file-handler`)
Displays card fields to download assets, supporting markdown and image previews.

### Props:
* `fileUrl` (string): Target document address.
* `filename` (string): Display file name.
* `fileSize` (string): Size annotation (e.g. `"2.5 MB"`).
* `allowPreview` (boolean): Set `false` to disable inline previews. Defaults to `true`.

### Example JSON:
```json
{
  "type": "file-handler",
  "props": {
    "fileUrl": "/api/media/invoice.md",
    "filename": "invoice.md",
    "allowPreview": true
  }
}
```

---

## 🛡️ 20. Human Approval Gate (`human-approval-gate`)
A confirmation trigger panel (sliding swipes or double-clicks) for sensitive user actions.

### Props:
* `gateMessage` / `label` (string): Instructions prompting approval.
* `actionUrl` (string): API endpoint path triggered on success.
* `variant` (string): `"swipe"` (slide to unlock) or `"double-click"`. Defaults to `"swipe"`.
* `size` (string): `"sm"`, `"md"`, or `"lg"`.
* `colorTheme` (string): Confirm track accent color.

### Example JSON:
```json
{
  "type": "human-approval-gate",
  "props": {
    "variant": "swipe",
    "gateMessage": "Swipe to approve wire transfer",
    "actionUrl": "/api/plugins/{{agent_id}}/approve_payment"
  }
}
```

---

## 🗺️ 21. Interactive Flow Chart (`flow-chart`)
Renders vector node-edge diagrams (workflows, organizational routes, networks).

### Props:
* `nodes` (array of objects): Node specs. Requires `id` (string), `label` (string). Supports `type` (string), `color` (string), `x` and `y` (coordinates 0-100).
* `edges` (array of objects): Edge lines. Requires `from` (string), `to` (string). Supports `label` (string).
* `layout` (string): `"circle"` or `"grid"`. Default is `"circle"`.
* `height` (number): Diagram canvas height. Defaults to `320`.
* `colorTheme` (string): Accent link and node highlight theme.

### Example JSON:
```json
{
  "type": "flow-chart",
  "props": {
    "height": 300,
    "nodes": [
      { "id": "start", "label": "Start Process", "type": "process" },
      { "id": "end", "label": "Complete Action", "type": "action" }
    ],
    "edges": [
      { "from": "start", "to": "end", "label": "Proceed" }
    ]
  }
}
```

---

## 🔣 22. Platform Icon (`icon`)
Displays vector SVG icons from the platform's core library (e.g. Navigation, Actions, Socials).

### Props:
* `name` (string): The icon name to display (case-sensitive). Common values include: `"Home"`, `"Calendar"`, `"Check"`, `"Search"`, `"Settings"`, `"User"`, `"Trash"`, `"Edit"`, `"Plus"`.
* `className` (string): Tailwind CSS utility styling classes (e.g. size `w-6 h-6`, colors `text-blue-500`).

### Example JSON:
```json
{
  "type": "icon",
  "props": {
    "name": "Calendar",
    "className": "w-6 h-6 text-blue-600 dark:text-blue-400"
  }
}
```

---

## 🖼️ 23. Image Block (`image`)
Renders static or dynamic image assets. Supports platform-managed authenticated endpoint decoration.

### Props:
* `src` (string): The image source URL. If the URL starts with `/api/media`, the platform automatically appends the active session user's `token`, `hubId`, and `orgId` as query parameters.
* `alt` (string, optional): Alternative description for accessibility.
* `className` (string): Tailwind CSS layout and border styling (e.g. rounded corners, fit modes).

### Example JSON:
```json
{
  "type": "image",
  "props": {
    "src": "/api/media/profile_avatar.jpg",
    "alt": "User Profile Avatar",
    "className": "w-16 h-16 rounded-full border border-slate-200"
  }
}
```

---

## ↕️ 24. Layout Spacer (`spacer`)
Creates vertical or horizontal blank gaps between layout sibling elements.

### Props:
* `size` (number or string): The thickness of the spacer. Supports pixel dimensions (e.g., `"12px"` or `12`).
* `className` (string, optional): Layout classes.

### Example JSON:
```json
{
  "type": "spacer",
  "props": {
    "size": "16px"
  }
}
```

---

## 📝 25. Textarea Field Mapping (`textarea`)
For multiline input fields, the linter and engine support the type `"textarea"`.

### Behavior:
* **Automatic Mapping**: The layout engine automatically normalizes `"type": "textarea"` elements into `"type": "input"` with multiline layout support.
* **Compatibility**: Props and data serialization follow the standard `input` element spec.



## 💬 4. Interaction Scripts & Conversational Flows
Provide exact transcript logs showing how users interact with the agent. These scripts will serve as prompt references and unit testing paths. 

### 📐 Guidelines for Design:
1. **Interface Modality Adaptation:** Every interaction scenario must explicitly state the behavior and expected output depending on the user's active interface:
   - **Visual Path (Chat UI):** Outlines how the agent renders UI widgets, cards, or custom layouts.
   - **Non-Visual Paths (SMS/Voice):** Outlines how the agent replies using clean, plain text (without markdown, formatting, or JSON placeholders) suitable for text-only messages or voice synthesizers.


---

### Scenario 1: `<!-- Scenario Name, e.g. Scheduling an Event -->`


#### Flow A: Visual Path (Chat UI with widgets)
*   **User:** `<!-- User's request in chat -->`
*   **Agent (Behind the Scenes):** Calls `consultAgent` -> calls tool `<!-- tool_name -->` with arguments `<!-- args -->`
*   **Agent UI Rendered:** Displays Widget `<!-- widget_template_id -->` with data.
*   **Agent Message:** `"..."`
*   **User clicks button:** Submits form with payload.
*   **Backend Response:** `"..."`

#### Flow B: Non-Visual SMS Path (No-UI, Text Only)
*   **User (SMS):** `<!-- User's text message -->`
*   **Agent (Behind the Scenes):** Calls tool `<!-- tool_name -->` with extracted arguments.
*   **Agent Text Reply:** `"..."` *(No UI elements; return plain-text message or a slot-filling request).*

#### Flow C: Non-Visual Voice Path (No-UI, Spoken Phone Call)
*   **User (Voice):** `<!-- User's spoken statement -->`
*   **Agent (Behind the Scenes):** Calls tool `<!-- tool_name -->` with extracted arguments.
*   **Agent Speech Reply:** `"..."` *(Concise, speech-friendly response without markdown or JSON placeholders).*

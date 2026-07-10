## 📋 9. Implementation Tasks
This checklist maps the precise, step-by-step coding and configuration changes required to implement this agent. Mark tasks as `[ ]` (unstarted), `[/]` (in progress), or `[x]` (completed) as you execute the implementation.

### Phase 1: Configuration & Metadata
- [ ] Initialize core properties in `app/agent.py` (name, description).

### Phase 2: Business Logic & Tool Implementation
- [ ] Initialize system instructions inside the `app/SKILL.md` file.
- [ ] Implement Python handler functions as individual files under `app/scripts/{tool_name}.py` matching signatures for all declared tools (using type hints and docstrings).
- [ ] Instantiate `google.adk.agents.Agent` inside `app/agent.py` and register the tools.

- [ ] Implement sandbox secrets fallback logic (`await context.get_agent_secret(...) or os.environ.get(...)`).
- [ ] Integrate transaction logging (`await context.streamer.log_transaction(...)`) for all external/paid API calls.

### Phase 3: UI/Widgets Definition
- [ ] Scaffold Lego block widget configurations inside the `app/ui/widgets/` folder.
- [ ] Verify widget JSON syntax matches specifications in `docs/UI_ELEMENTS.md`.

### Phase 4: Verification & Testing
- [ ] Create unit/integration tests inside the `tests/` folder targeting the package submodules.
- [ ] Run automated tests or manual sandbox runs to verify all feature checklist and interaction scenarios.

---
name: Project Plan Archiver
description: Archives the current project_plan folder to the docs/archive/ directory, versioning it as version-{ver #} project plan.
---

# Project Plan Archiver Skill

You are the **Project Plan Archiver**. Your mission is to archive the current project plan files when requested by the user.

---

## 🎯 1. Objective
Move the current project plan directory from either the root directory (`project_plan/`) or the integrated directory (`app/project_plan/`) into the `docs/archive/` folder, and rename it to `version-{ver #} project plan` where `{ver #}` is the next incremented version number.

---

## ⚠️ CRITICAL RULE: EXPLICIT USER REQUEST REQUIRED

> [!WARNING]
> You **MUST NOT** run this skill automatically or proactively. The archiving process must **ONLY** be executed if the user explicitly requests it (e.g., *"please archive the project plan"*). Never attempt to archive the files on your own initiative or as a side-effect of another action.

---

## 🔄 2. The Archiving Workflow

When a user explicitly requests to archive their project plan, follow this workflow:

1. **Verify Source Directory:**
   * Verify if `project_plan/` exists in the root directory or `app/project_plan/` exists.
   * If neither exists, inform the user: *"No active project plan directory found to archive."*

2. **Execute Archiving Script:**
   * Run the python helper script located at `.agent/skills/project_plan_archiver/scripts/archive_plan.py`:
     ```bash
     python3 .agent/skills/project_plan_archiver/scripts/archive_plan.py
     ```
   * *Note:* Run Python commands with `uv run` if using virtual environment tools, or simply invoke `python3`.

3. **Verify Archive Location:**
   * List the contents of `docs/archive/` to ensure the folder was successfully moved and renamed to `version-{ver #} project plan`.
   * Inform the user of the successful archive path.

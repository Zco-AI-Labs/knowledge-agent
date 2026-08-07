import os

# Force regional Vertex AI routing unconditionally
os.environ.pop("GOOGLE_GENAI_USE_ENTERPRISE", None)
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GOOGLE_API_KEY", None)
import re

from google.adk import Agent as AdkAgent

from app.core.load_local_tools import load_local_tools

# 1. Read system prompt instructions from SKILL.md and load tools at module level
runtime_dir = os.path.dirname(os.path.abspath(__file__))
skill_md_path = os.path.join(runtime_dir, "SKILL.md")
system_instruction = "You are a helpful knowledge search assistant."
if os.path.exists(skill_md_path):
    with open(skill_md_path, encoding="utf-8") as f:
        skill_content = f.read()
    system_instruction = re.sub(r"^---.*?---", "", skill_content, flags=re.DOTALL).strip()

scripts_dir = os.path.join(runtime_dir, "scripts")
system_tools_dir = os.path.join(runtime_dir, "core", "system_tools")
tools = load_local_tools(system_tools_dir) + load_local_tools(scripts_dir)

allow_web_search = True
allow_google_maps = False

config_json_path = os.path.join(runtime_dir, "config.json")
if not os.path.exists(config_json_path):
    config_json_path = os.path.join(os.path.dirname(runtime_dir), "config.json")
if os.path.exists(config_json_path):
    try:
        import json
        with open(config_json_path, "r", encoding="utf-8") as cf:
            config_data = json.load(cf)
            if "allow_web_search" in config_data or "allowWebSearch" in config_data:
                allow_web_search = bool(config_data.get("allow_web_search") if "allow_web_search" in config_data else config_data.get("allowWebSearch"))
            if "allow_google_maps" in config_data or "allowGoogleMaps" in config_data:
                allow_google_maps = bool(config_data.get("allow_google_maps") if "allow_google_maps" in config_data else config_data.get("allowGoogleMaps"))
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to read/parse config.json: {e}")

if allow_web_search:
    try:
        from google.adk.tools import google_search
        tools.append(google_search)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to import google_search tool: {e}")

if allow_google_maps:
    try:
        from google.adk.tools import google_maps_grounding
        tools.append(google_maps_grounding)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to import google_maps_grounding tool: {e}")

from app.app_utils.vertex_gemini import get_model

root_agent = AdkAgent(
    model=get_model("gemini-2.5-flash"),
    name='knowledge_agent',
    description='Answers user questions by searching the Shared RAG corpus of scraped knowledge, which contains website content, uploaded files, and YouTube video transcripts.',
    instruction=system_instruction,
    tools=tools
)

from app.core.geap_agent_wrapper import GEAPAgentWrapper

# Singleton instance used as the serialization target
agent_app = GEAPAgentWrapper(root_agent)

from google.adk.apps import App

app = App(
    root_agent=root_agent,
    name="app",
)

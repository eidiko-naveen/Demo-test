import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Groq LLM configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
FALLBACK_LLM_MODEL = os.getenv("FALLBACK_LLM_MODEL", "llama-3.1-8b-instant")

# GitHub token
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Kept for compatibility with existing configuration/UI code
GITHUB_SSE_URL = os.getenv("GITHUB_SSE_URL", "http://localhost:8001/sse")
SSE_SERVERS = {"github_server": GITHUB_SSE_URL}

REPO_STORE_PATH = BASE_DIR / "data" / "repositories.json"
BRAND_NAME = "Eidiko Systems Integration"
APP_TITLE = "Eidiko Official GitHub MCP Portal"

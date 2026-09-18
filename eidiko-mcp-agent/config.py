import os
from pathlib import Path
from dotenv import load_dotenv

# Base Directory Path
BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from .env
load_dotenv(BASE_DIR / ".env")

# LLM Configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-opus-4-5")
FALLBACK_LLM_MODEL = os.getenv("FALLBACK_LLM_MODEL", "llama-3.3-70b-versatile")

# GitHub Token
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# SSE Server Endpoints Configuration
GITHUB_SSE_URL = os.getenv("GITHUB_SSE_URL", "http://localhost:8001/sse")

# Server Configuration Dict
SSE_SERVERS = {
    "github_server": GITHUB_SSE_URL,
}

# Data Stores
REPO_STORE_PATH = BASE_DIR / "data" / "repositories.json"

# Brand Information
BRAND_NAME = "Eidiko Systems Integration"
APP_TITLE = "Eidiko Official GitHub MCP Portal"

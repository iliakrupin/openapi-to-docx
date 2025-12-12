"""
Configuration management per FastAPI best practices.
Loads environment variables and provides application configuration.
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables
# Try to find .env file in multiple locations
env_paths = [
    Path(__file__).parent.parent / ".env",  # Project root (from src/config.py)
    Path.cwd() / ".env",  # Current working directory
    Path.home() / ".env",  # Home directory (fallback)
]

env_loaded = False
for env_path in env_paths:
    if env_path.exists():
        logger.info(f"Loading .env from: {env_path}")
        load_dotenv(dotenv_path=env_path, override=True)
        env_loaded = True
        break

if not env_loaded:
    # Fallback to default behavior (searches in current directory and parents)
    logger.info("No .env file found in standard locations, using default load_dotenv() behavior")
    load_dotenv()

# LM Studio API configuration
LM_STUDIO_API_URL = os.getenv("LM_STUDIO_API_URL")
API_TOKEN = os.getenv("LM_STUDIO_API_TOKEN") or os.getenv("API_TOKEN")
MODEL_NAME = os.getenv("LM_STUDIO_MODEL_NAME", "Qwen/Qwen3-30B-A3B-FP8")
MAX_TOKENS = int(os.getenv("LM_STUDIO_MAX_TOKENS", "28000"))  # buffer for prompt+response
CHUNK_SIZE = int(os.getenv("LM_STUDIO_CHUNK_SIZE", "10000"))  # max size per chunk

# Log configuration status (without sensitive data)
if LM_STUDIO_API_URL:
    logger.info(f"LM_STUDIO_API_URL configured: {LM_STUDIO_API_URL}")
    logger.info(f"API_TOKEN configured: {'Yes' if API_TOKEN else 'No'}")
    logger.info(f"MODEL_NAME: {MODEL_NAME}")
else:
    logger.warning("LM_STUDIO_API_URL not configured - LLM features will be disabled")

# Mode selection: auto-enable LLM if both URL and token are provided
# Can be explicitly overridden with USE_LLM environment variable
explicit_use_llm = os.getenv("USE_LLM")
if explicit_use_llm is not None:
    # Explicit setting takes precedence
    USE_LLM = explicit_use_llm.lower() in ("true", "1", "yes", "on")
else:
    # Auto-enable if both URL and token are provided
    USE_LLM = bool(LM_STUDIO_API_URL and API_TOKEN)

# LLM enhancement mode: use LLM only for improving descriptions (faster than full generation)
USE_LLM_ENHANCE = os.getenv("USE_LLM_ENHANCE", "false").lower() in ("true", "1", "yes", "on")

# Validate LLM config if LLM mode is enabled
if USE_LLM:
    if not LM_STUDIO_API_URL:
        raise ValueError("LM_STUDIO_API_URL environment variable is required when LLM mode is enabled")
    if not API_TOKEN:
        raise ValueError("LM_STUDIO_API_TOKEN or API_TOKEN environment variable is required when LLM mode is enabled")

# HTTP headers for API requests
HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}" if API_TOKEN else "",
    "Content-Type": "application/json",
} if API_TOKEN else {"Content-Type": "application/json"}

# Directory for temporary files
TEMP_DIR = Path(os.getenv("TEMP_DIR", "temp"))
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Supported HTTP methods per OpenAPI 3.0 spec
HTTP_METHODS = ["get", "post", "put", "delete", "patch", "head", "options", "trace"]




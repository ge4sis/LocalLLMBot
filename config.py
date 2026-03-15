import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Allowlisted User IDs
_allowed_user_ids_str = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_USER_IDS = []
if _allowed_user_ids_str:
    try:
        ALLOWED_USER_IDS = [
            int(u_id.strip())
            for u_id in _allowed_user_ids_str.split(",")
            if u_id.strip()
        ]
    except ValueError:
        print(
            "Warning: ALLOWED_USER_IDS environment variable contains invalid integers."
        )

# LM Studio Local API Configuration
LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
LM_STUDIO_API_KEY = os.getenv("LM_STUDIO_API_KEY", "lm-studio")

# Validate critical configurations (excluding ALLOWED_USER_IDS to allow running without it, handled in Bot)
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN in environment variables.")

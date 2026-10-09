"""Start the hosted dashboard only with explicit production configuration."""

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv


def validate_environment(env):
    required = ["DASHBOARD_ADMIN_USERNAME", "DASHBOARD_ADMIN_PASSWORD_HASH",
                "CLOUD_DB_HOST", "CLOUD_DB_USER", "CLOUD_DB_PASSWORD", "CLOUD_DB_NAME",
                "FLASK_APP_URL", "DASHBOARD_API_TOKEN"]
    missing = [name for name in required if not env.get(name, "").strip()]
    if missing:
        raise ValueError("Missing dashboard settings: " + ", ".join(missing))
    if env.get("USE_CLOUD_DB", "").lower() != "true":
        raise ValueError("Hosted dashboard requires USE_CLOUD_DB=true.")
    password_hash = env["DASHBOARD_ADMIN_PASSWORD_HASH"]
    if not re.fullmatch(r"[a-fA-F0-9]{64}", password_hash):
        raise ValueError("DASHBOARD_ADMIN_PASSWORD_HASH must be a SHA-256 hash.")
    from auth_helpers import hash_password
    if password_hash.lower() in {hash_password("admin123"), hash_password("admin1234")}:
        raise ValueError("Set a dashboard password other than the development default.")
    if not env["FLASK_APP_URL"].startswith("https://"):
        raise ValueError("FLASK_APP_URL must use HTTPS for the hosted chatbot.")


if __name__ == "__main__":
    load_dotenv()
    try:
        validate_environment(os.environ)
    except ValueError as error:
        sys.exit(str(error))
    os.environ["DASHBOARD_HOSTED"] = "true"
    script = str(Path(__file__).with_name("dashboard.py"))
    os.execv(sys.executable, [sys.executable, "-m", "streamlit", "run", script,
                             "--server.address=0.0.0.0", f"--server.port={os.getenv('PORT', '8501')}",
                             "--server.headless=true", "--browser.gatherUsageStats=false"])

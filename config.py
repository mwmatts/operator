import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

# Required
TELEGRAM_BOT_TOKEN = os.environ["OPERATOR_TELEGRAM_BOT_TOKEN"]

# CortexShell authorization gate
CORTEXSHELL_URL = os.environ.get("CORTEXSHELL_URL", "http://localhost:8100")

# KIOS SQLite DB — read-only queries
KIOS_DB_PATH = Path(
    os.environ.get("KIOS_DB_PATH", str(Path.home() / "alte" / "kios" / "kios.db"))
)

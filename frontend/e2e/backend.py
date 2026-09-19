"""Real Flask routes with local deterministic adapters for Playwright only."""
from pathlib import Path
import os
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "app"))
os.environ["APP_URL"] = "http://127.0.0.1:5174"
os.environ["SESSION_COOKIE_SECURE"] = "false"

from tests.browser_fixtures import create_test_app

app = create_test_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=3008, debug=False, use_reloader=False)

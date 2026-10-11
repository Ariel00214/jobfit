#!/usr/bin/env bash
set -euo pipefail
pip install -r requirements.txt
# Render's build and runtime share the project filesystem.
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright"
python -m playwright install chromium --only-shell
PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright" python - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    browser.close()
print('Chromium launch verified')
PY

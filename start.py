"""Production entrypoint (Railway / any PaaS).

Reads the PORT environment variable the platform assigns and starts the web app on
0.0.0.0:<PORT>. Using Python avoids depending on shell variable expansion in the
platform's start command.
"""

import os
import sys

port = os.environ.get("PORT", "8501")
print(f"Starting Invoicing & Expense Tracker on 0.0.0.0:{port}", flush=True)
os.execvp(
    sys.executable,
    [
        sys.executable, "-m", "streamlit", "run", "app.py",
        f"--server.port={port}",
        "--server.address=0.0.0.0",
        "--server.headless=true",
    ],
)

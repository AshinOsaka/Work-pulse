"""Build-only entry point: bakes the company's WorkPulse server URL into the frozen agent.

Employees then just run the exe and it connects automatically (no setup script / agent.ini needed).
An explicit WORKPULSE_API_URL env var, agent.ini, or --api-url flag still overrides this default.
"""

import os
import sys

os.environ.setdefault("WORKPULSE_API_URL", "https://work-pulse-8nfk.onrender.com/api")

from app.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

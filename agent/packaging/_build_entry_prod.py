"""Build-only entry point: bakes the company's WorkPulse server URL into the frozen agent.

Employees then just run the exe and it connects automatically (no setup script / agent.ini needed).
An explicit WORKPULSE_API_URL environment variable or --api-url flag overrides it. agent.ini does not: this sets the
environment value, which wins over agent.ini (so an old address saved there is replaced on update).
"""

import os
import sys

os.environ.setdefault("WORKPULSE_API_URL", "https://workpulse-sg.onrender.com/api")

from app.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

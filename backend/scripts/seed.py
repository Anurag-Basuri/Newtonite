"""
Seed runner script located in scripts/ directory.
Delegates to backend seed implementation.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from seed import seed

if __name__ == "__main__":
    asyncio.run(seed())

import os
import sys

# Ensure backend directory is always on sys.path regardless of where pytest/python is invoked
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "backend"))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

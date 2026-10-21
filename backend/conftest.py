import os
import sys

# Ensure backend root is in sys.path
backend_path = os.path.abspath(os.path.dirname(__file__))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

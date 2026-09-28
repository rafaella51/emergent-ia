"""Entrada da Vercel: expõe o FastAPI do bot em /api/*."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from server import app  # noqa: E402,F401

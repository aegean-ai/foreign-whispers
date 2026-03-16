"""Root entry point — re-exports the app from api.src.main for backwards compatibility.

Usage: uvicorn main:app
"""

from api.src.main import app  # noqa: F401

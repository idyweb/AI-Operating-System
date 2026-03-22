"""
Application entrypoint.
Imports the FastAPI app from api/ and exposes it for uvicorn.
Why root main.py: Clean entrypoint, keeps api/ as a pure package.
"""
from api.main import app

__all__ = ["app"]
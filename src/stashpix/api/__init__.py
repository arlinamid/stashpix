"""REST API / SaaS backend (FastAPI). Import :func:`create_app` to build the app."""

from .app import create_app

__all__ = ["create_app"]

"""FastAPI application.

Routes register AI systems, store versioned screenings, and read imported
legal provisions. The Streamlit frontend and the assessment rules stay in
their own packages.
"""

from ai_governance.api.app import create_app

__all__ = ["create_app"]

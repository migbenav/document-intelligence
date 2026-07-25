"""Production entrypoint for the Document Intelligence backend.

Usage:
    uvicorn app.run:app --host 0.0.0.0 --port 8000

Environment variables:
    CORS_ORIGINS: Comma-separated list of allowed origins (default: "*").
                  Example: "http://localhost:5173,https://my-app.vercel.app"
"""

import os

from app.main import create_app

cors_origins_env = os.getenv("CORS_ORIGINS", "*")
cors_origins = [origin.strip() for origin in cors_origins_env.split(",")]

app = create_app(cors_origins=cors_origins)

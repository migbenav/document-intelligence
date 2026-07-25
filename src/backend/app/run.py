"""Production entrypoint for the Document Intelligence backend.

Usage:
    uvicorn app.run:app --host 0.0.0.0 --port 8000

Environment variables:
    SUPABASE_URL: Project URL from Supabase Dashboard.
    SUPABASE_SERVICE_ROLE_KEY: Service role JWT key.
    CORS_ORIGINS: Comma-separated list of allowed origins (default: "*").
                  Example: "http://localhost:5173,https://my-app.vercel.app"
"""

import os

from dotenv import load_dotenv
from supabase import create_client

from app.main import create_app

# Load .env from project root (two levels up from src/backend/app/)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

cors_origins_env = os.getenv("CORS_ORIGINS", "*")
cors_origins = [origin.strip() for origin in cors_origins_env.split(",")]

# Initialize Supabase client
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not supabase_url or not supabase_key:
    raise RuntimeError(
        "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variables. "
        "Check your .env file."
    )

supabase_client = create_client(supabase_url, supabase_key)

app = create_app(supabase_client=supabase_client, cors_origins=cors_origins)

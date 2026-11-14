import os
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()


def get_engine(database=None):
    """Connection settings come from .env (or Streamlit secrets copied into env vars)."""
    user = os.getenv("DB_USER", "postgres")
    pw = quote_plus(os.getenv("DB_PASSWORD", ""))
    host = os.getenv("DB_HOST", "127.0.0.1")
    port = os.getenv("DB_PORT", "5432")
    name = database or os.getenv("DB_NAME", "urban_pulse_db")
    url = f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{name}"
    return create_engine(url, pool_pre_ping=True)

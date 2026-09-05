"""
All app settings live here, read from environment variables (.env file).
This is the ONLY place that should read os.environ directly - everywhere
else in the app just imports config values from here.
"""
import os
from dotenv import load_dotenv

load_dotenv()  # reads the .env file into the environment, if present


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///thesis.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # How old market data can be before we mark it "stale" in the UI.
    STALE_DATA_THRESHOLD_MINUTES = int(os.environ.get("STALE_DATA_THRESHOLD_MINUTES", "60"))
    MARKET_DATA_MODE = os.environ.get("MARKET_DATA_MODE", "auto")  # mock | yahoo | auto

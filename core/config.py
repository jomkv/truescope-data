import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# DigitalOcean / Managed Postgres Settings
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
SSL_MODE = os.getenv("SSL_MODE")
CA_CERT_PATH = os.getenv("CA_CERT_PATH")

# Full Connection String
# First, try to get the full URL directly, otherwise build it
DATABASE_URI = os.getenv("DATABASE_URL")
if not DATABASE_URI:
    DATABASE_URI = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?sslmode={SSL_MODE}"

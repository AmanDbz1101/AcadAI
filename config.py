"""
Configuration file for the Research Paper Metadata Extractor API.

Modify these settings as needed for your deployment.
"""

import os
from pathlib import Path

# API Configuration
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", 8000))
API_RELOAD = os.getenv("API_RELOAD", "false").lower() == "true"  # Hot reload for development

# File Upload Configuration
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", 50))  # Maximum file size in MB
ALLOWED_EXTENSIONS = {".pdf"}

# Processing Configuration
EXTRACTION_TIMEOUT = int(os.getenv("EXTRACTION_TIMEOUT", 120))  # Timeout in seconds

# CORS Configuration
# In production, replace "*" with specific origins
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
CORS_ALLOW_CREDENTIALS = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
LOG_DIR.mkdir(exist_ok=True)

# Groq API Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("WARNING: GROQ_API_KEY not set in environment variables!")

# Qdrant Vector Store Configuration
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "research_papers")
QDRANT_EMBEDDING_MODEL = os.getenv(
    "QDRANT_EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2"
)

if not QDRANT_URL or not QDRANT_API_KEY:
    print("WARNING: QDRANT_URL or QDRANT_API_KEY not set in environment variables!")

# Feature Flags
ENABLE_CLEANUP_ENDPOINT = os.getenv("ENABLE_CLEANUP_ENDPOINT", "true").lower() == "true"
ENABLE_DETAILED_ERRORS = os.getenv("ENABLE_DETAILED_ERRORS", "true").lower() == "true"

# Rate Limiting (if implemented)
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", 10))

# Cache Configuration (if implemented)
ENABLE_CACHE = os.getenv("ENABLE_CACHE", "false").lower() == "true"
CACHE_DIR = Path(os.getenv("CACHE_DIR", "cache"))

print(f"Configuration loaded:")
print(f"  - API Host: {API_HOST}:{API_PORT}")
print(f"  - Upload Directory: {UPLOAD_DIR}")
print(f"  - Max File Size: {MAX_FILE_SIZE_MB} MB")
print(f"  - Groq API Configured: {GROQ_API_KEY is not None}")
print(f"  - Qdrant Configured: {QDRANT_URL is not None and QDRANT_API_KEY is not None}")
print(f"  - Qdrant Collection: {QDRANT_COLLECTION_NAME}")

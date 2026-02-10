"""
Backend configuration settings.

Centralizes all configuration with environment variable support.
"""

import os
from pathlib import Path
from typing import Set

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings with environment variable support.
    
    All settings can be overridden via environment variables.
    """
    
    # API Configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_RELOAD: bool = False
    API_TITLE: str = "Research Paper Assistant API"
    API_VERSION: str = "2.0.0"
    
    # File Upload Configuration
    UPLOAD_DIR: Path = Path("uploads")
    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: Set[str] = {".pdf"}
    
    # Processing Configuration
    EXTRACTION_TIMEOUT: int = 120
    ENABLE_OCR: bool = True
    OCR_MIN_TEXT_DENSITY: float = 50.0  # chars per page
    
    # CORS Configuration
    CORS_ORIGINS: list[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    
    # Logging Configuration
    LOG_LEVEL: str = "INFO"
    LOG_DIR: Path = Path("logs")
    
    # LLM Configuration (for downstream modules)
    GROQ_API_KEY: str | None = None
    
    # Vector Store Configuration (for downstream modules)
    QDRANT_URL: str | None = None
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION_NAME: str = "research_papers"
    
    # Feature Flags
    ENABLE_CLEANUP_ENDPOINT: bool = True
    ENABLE_DETAILED_ERRORS: bool = True
    ENABLE_CACHE: bool = False
    
    # Cache Configuration
    CACHE_DIR: Path = Path("cache")
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 10
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields from .env
    
    def __init__(self, **kwargs):
        """Initialize settings and create required directories."""
        super().__init__(**kwargs)
        
        # Create directories
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)
        if self.ENABLE_CACHE:
            self.CACHE_DIR.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()

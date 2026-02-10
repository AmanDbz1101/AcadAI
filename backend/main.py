"""
Main entry point for the Research Paper Assistant backend.

Usage:
    python backend/main.py          # Start API server from project root
    python main.py                  # Start API server from backend directory
"""

import sys
import logging
from pathlib import Path

# Add project root to path (parent of backend directory)
backend_dir = Path(__file__).parent
project_root = backend_dir.parent
sys.path.insert(0, str(project_root))

from backend.api.app import app, settings


def main():
    """Main entry point."""
    import uvicorn
    
    logging.info(f"Starting {settings.API_TITLE} v{settings.API_VERSION}")
    
    uvicorn.run(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD,
        log_level=settings.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()

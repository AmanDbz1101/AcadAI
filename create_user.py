#!/usr/bin/env python3
"""
Create a user account directly in the database.
"""

import sys
import os
import hashlib
import secrets
import hmac

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.database.connection import get_db_session
from backend.extraction.persistence.postgres_store import UserRecord

def _hash_password(password: str, salt_hex: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        (password or "").encode("utf-8"),
        bytes.fromhex(salt_hex),
        200_000,
    )
    return digest.hex()

def create_user(email: str, password: str, display_name: str = None):
    salt_hex = secrets.token_bytes(16).hex()
    password_hash = _hash_password(password, salt_hex)

    with get_db_session() as session:
        user = UserRecord(
            email=email.lower().strip(),
            password_hash=password_hash,
            password_salt=salt_hex,
            display_name=display_name,
        )
        session.add(user)
        session.commit()
        print(f"✅ User created: {email}")
        return user.id

if __name__ == "__main__":
    create_user("anjal@example.com", "test123456", "Anjal")
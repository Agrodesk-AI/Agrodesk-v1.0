import secrets

import bcrypt

from app.core.config import settings


def generate_code() -> str:
    upper = 10 ** settings.otp_length
    return f"{secrets.randbelow(upper):0{settings.otp_length}d}"


def hash_code(code: str) -> str:
    return bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()


def verify_code(code: str, code_hash: str) -> bool:
    try:
        return bcrypt.checkpw(code.encode(), code_hash.encode())
    except Exception:
        return False

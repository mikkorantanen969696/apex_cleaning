from __future__ import annotations

import bcrypt


def hash_code(code: str) -> str:
    hashed = bcrypt.hashpw(code.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_code(code: str, code_hash: str) -> bool:
    try:
        return bcrypt.checkpw(code.encode("utf-8"), code_hash.encode("utf-8"))
    except Exception:
        return False


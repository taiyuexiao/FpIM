from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt

from .config import settings


def hash_password(password: str) -> str:
    # 直调 bcrypt(passlib 1.7.4 与 bcrypt 5.x 不兼容);bcrypt 明文上限 72 字节
    return bcrypt.hashpw(password.encode()[:72],
                         bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode()[:72], hashed_password.encode())
    except ValueError:
        return False


def create_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
    payload = {
        "sub": user_id,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])

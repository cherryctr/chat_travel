from datetime import datetime, timedelta
from typing import Optional

import jwt
from passlib.hash import bcrypt

from app.core.config import settings


def verify_password(plain_password: str, hashed_password: str) -> bool:
	# Laravel uses $2y$ prefix, passlib bcrypt can handle it
	return bcrypt.verify(plain_password, hashed_password)


def create_access_token(subject: str, expires_minutes: Optional[int] = None) -> str:
	exp_minutes = expires_minutes or settings.access_token_expire_minutes
	expire = datetime.utcnow() + timedelta(minutes=exp_minutes)
	to_encode = {"sub": subject, "exp": expire}
	return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[dict]:
	try:
		payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
		return payload
	except jwt.PyJWTError:
		return None

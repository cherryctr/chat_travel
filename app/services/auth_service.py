from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.security import verify_password, create_access_token, decode_access_token
from app.db.session import get_db
from app.db.models import User


security = HTTPBearer(auto_error=False)


class AuthService:
	@staticmethod
	def login(email: str, password: str, db: Session) -> str:
		user = db.query(User).filter(User.email == email).first()
		if not user or not verify_password(password, user.password):
			raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email atau password salah")
		return create_access_token(subject=str(user.id))

	@staticmethod
	def get_current_user(
		credentials: HTTPAuthorizationCredentials = Depends(security),
		db: Session = Depends(get_db),
	) -> User | None:
		if not credentials:
			return None
		token = credentials.credentials
		payload = decode_access_token(token)
		if not payload or "sub" not in payload:
			raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token tidak valid")
		user_id = int(payload["sub"])  # sub=user.id
		user = db.query(User).filter(User.id == user_id).first()
		if not user:
			raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Pengguna tidak ditemukan")
		return user

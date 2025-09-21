import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv(".env")

@dataclass
class Settings:
	app_env: str = os.getenv("APP_ENV", "development")
	host: str = os.getenv("APP_HOST", "0.0.0.0")
	port: int = int(os.getenv("APP_PORT", "8000"))

	database_url: str = os.getenv("DATABASE_URL", "mysql+pymysql://root:password@127.0.0.1:3306/devwebmy_travel")

	jwt_secret: str = os.getenv("JWT_SECRET", "change-this-in-production")
	jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
	access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))

	google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
	gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

settings = Settings()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.routes import include_app_routes
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="TravelGO Chat API", version="1.0.0")

# CORS: izinkan semua origin, metode, dan header
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_methods=["*"],
	allow_headers=["*"],
)

# Test database connection on startup
@app.on_event("startup")
async def startup_event():
    try:
        from app.db.session import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection successful")
    except Exception as e:
        logger.warning(f"Database connection failed: {e}")
        logger.warning("Application will continue without database connection")

include_app_routes(app)

@app.get("/health")
def health_check():
	return {"status": "ok"}

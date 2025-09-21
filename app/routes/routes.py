from fastapi import FastAPI

from app.controllers.auth_controller import router as auth_router
from app.controllers.chat_controller import router as chat_router


def include_app_routes(app: FastAPI) -> None:
	app.include_router(auth_router)
	app.include_router(chat_router)

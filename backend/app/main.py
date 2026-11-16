from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn

from backend.app.config import Settings
from backend.app.routers.robot import router as robot_router


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = app_settings
        app.state.robot_client = httpx.AsyncClient(timeout=app_settings.robot_request_timeout)
        try:
            yield
        finally:
            await app.state.robot_client.aclose()

    app = FastAPI(title="RobotViRed Backend", lifespan=lifespan)
    app.include_router(robot_router)
    frontend_path = Path(__file__).resolve().parents[2] / "frontend"
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)
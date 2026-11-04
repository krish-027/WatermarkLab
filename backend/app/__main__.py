"""Run with python -m app from backend/."""

import uvicorn

from app.core.config import Settings

if __name__ == '__main__':
    settings = Settings()
    uvicorn.run('app.main:app', host=settings.backend_host, port=settings.backend_port)

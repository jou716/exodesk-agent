from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import ApiServices, create_services
from .api.audit import router as audit_router
from .api.customers import router as customers_router
from .api.drafts import router as drafts_router
from .api.errors import install_error_handlers
from .api.runs import router as runs_router
from .api.tickets import router as tickets_router
from .api.webhooks import router as webhooks_router
from .config import settings
from .db import init_db


def create_app(
    services: ApiServices | None = None,
    initialize_db: bool = False,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if initialize_db:
            init_db()
        yield

    app = FastAPI(
        title=settings.app_name,
        version="0.10.0",
        lifespan=lifespan,
    )
    app.state.services = services or create_services()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    app.include_router(tickets_router)
    app.include_router(runs_router)
    app.include_router(drafts_router)
    app.include_router(webhooks_router)
    app.include_router(audit_router)
    app.include_router(customers_router)

    @app.get("/")
    def root() -> dict:
        return {
            "name": settings.app_name,
            "version": "0.10.0",
            "docs": "/docs",
            "health": "/api/health",
        }

    @app.get("/api/health")
    def health() -> dict:
        from sqlalchemy import text

        with app.state.services.session_factory() as db:
            db.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "env": settings.app_env,
            "demo_mode": settings.demo_mode,
            "provider": settings.ticket_provider,
        }

    return app


app = create_app(initialize_db=True)

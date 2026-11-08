"""The ArenaHub application: creates the FastAPI app and plugs everything in.

Run locally with:  uvicorn app.main:app --reload
"""

from fastapi import FastAPI

from app.catalog.routes import router as catalog_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.health import router as health_router
from app.core.logging import request_context_middleware, setup_logging

settings = get_settings()
setup_logging(settings.log_level)

app = FastAPI(
    title="ArenaHub API",
    version="0.1.0",
    description="Booking service for multi-sport facilities: browse fields, hold time slots, block time.",
)

# Turn every error into the shared {"error": {...}} format.
register_error_handlers(app)

# Correlation ID + one log line per request.
app.middleware("http")(request_context_middleware)

# ---------- Routers ----------
app.include_router(health_router)
app.include_router(catalog_router)

# Teammates' routers are registered here as each module is merged (Person 3 owns this list):
# from app.auth.routes import router as auth_router              # Person 2: /auth/login, /auth/me
# from app.bookings.routes import router as bookings_router      # Person 1: /fields/{id}/bookings, /bookings/{id}
# from app.manager.routes import router as manager_router        # Person 2: /fields/{id}/blocks
# app.include_router(auth_router)
# app.include_router(bookings_router)
# app.include_router(manager_router)
"""The ArenaHub application: creates the FastAPI app and plugs everything in.

Run locally with:  uvicorn app.main:app --reload
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.auth.routes import router as auth_router
from app.bookings.routes import router as bookings_router  # Person 1: player holds, reads, and cancellation.
from app.catalog.routes import router as catalog_router
from app.core.config import get_settings
from app.core.errors import make_contract_match_error_format, register_error_handlers
from app.core.health import router as health_router
from app.core.logging import request_context_middleware, setup_logging
from app.manager.routes import router as manager_router

settings = get_settings()
setup_logging(settings.log_level)

app = FastAPI(
    title="ArenaHub API",
    version="0.1.0",
    description="Booking service for multi-sport facilities: browse fields, hold time slots, block time.",
)

# Turn every error into the shared {"error": {...}} format, and document it that way.
register_error_handlers(app)
make_contract_match_error_format(app)

# Correlation ID + one log line per request.
app.middleware("http")(request_context_middleware)

# ---------- Routers ----------
app.include_router(health_router)
app.include_router(catalog_router)
app.include_router(auth_router)
app.include_router(manager_router)
app.include_router(bookings_router)  # Use the shared auth, errors, sessions, and middleware.

# ---------- Test front end (same origin as the API, so no CORS setup is needed) ----------
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
def frontend_index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


# Teammates' routers are registered here as each module is merged (Person 3 owns this list):
# from app.auth.routes import router as auth_router              # Person 2: /auth/login, /auth/me
# from app.bookings.routes import router as bookings_router      # Person 1: /fields/{id}/bookings, /bookings/{id}
# from app.manager.routes import router as manager_router        # Person 2: /fields/{id}/blocks
# app.include_router(auth_router)
# app.include_router(bookings_router)
# app.include_router(manager_router)

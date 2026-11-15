"""The ArenaHub application: creates the FastAPI app and plugs everything in.

Run locally with:  uvicorn app.main:app --reload
"""

from pathlib import Path  # Build file paths.

from fastapi import FastAPI  # The web framework.
from fastapi.responses import FileResponse  # Send a file as the response.
from fastapi.staticfiles import StaticFiles  # Serve the test front end.

from app.auth.routes import router as auth_router  # Login and /auth/me.
from app.bookings.routes import router as bookings_router  # Person 1: player holds, reads, and cancellation.
from app.catalog.routes import router as catalog_router  # Fields and availability.
from app.core.config import get_settings  # Application settings.
from app.core.errors import make_contract_match_error_format, register_error_handlers  # Shared error format.
from app.core.health import router as health_router  # Liveness and readiness checks.
from app.core.logging import request_context_middleware, setup_logging  # Request IDs and JSON logs.
from app.manager.routes import router as manager_router  # Manager blocks.

settings = get_settings()  # Load the settings once at startup.
setup_logging(settings.log_level)  # Start JSON logging at the configured level.

app = FastAPI(  # The application object.
    title="ArenaHub API",  # Name shown in the docs.
    version="0.1.0",  # API version shown in the docs.
    description="Booking service for multi-sport facilities: browse fields, hold time slots, block time.",  # One-line summary in the docs.
)  # Finish the app.

# Turn every error into the shared {"error": {...}} format, and document it that way.
register_error_handlers(app)  # Connect the error handlers.
make_contract_match_error_format(app)  # Make the OpenAPI document match the real errors.

# Correlation ID + one log line per request.
app.middleware("http")(request_context_middleware)  # Run it around every request.

app.include_router(health_router)  # /health/live and /health/ready.
app.include_router(catalog_router)  # /fields and availability.
app.include_router(auth_router)  # /auth/login and /auth/me.
app.include_router(manager_router)  # /fields/{id}/blocks.
app.include_router(bookings_router)  # Use the shared auth, errors, sessions, and middleware.

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"  # Folder holding the test front end.
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")  # Same origin as the API, so no CORS setup is needed.


@app.get("/", include_in_schema=False)  # The home page; hidden from the API docs.
def frontend_index() -> FileResponse:  # Serve the test client.
    return FileResponse(FRONTEND_DIR / "index.html")  # The single-page test client.


# Teammates' routers are registered here as each module is merged (Person 3 owns this list):
# from app.auth.routes import router as auth_router              # Person 2: /auth/login, /auth/me
# from app.bookings.routes import router as bookings_router      # Person 1: /fields/{id}/bookings, /bookings/{id}
# from app.manager.routes import router as manager_router        # Person 2: /fields/{id}/blocks
# app.include_router(auth_router)
# app.include_router(bookings_router)
# app.include_router(manager_router)

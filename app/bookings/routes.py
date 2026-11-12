"""Thin synchronous HTTP handlers; the reservation service owns every business rule."""

from typing import Annotated, Any  # Annotated keeps HTTP header constraints beside their type.
from uuid import UUID  # FastAPI rejects malformed path IDs before calling the service.

from fastapi import APIRouter, Depends, Header, Response  # Translate HTTP input and output.
from fastapi.routing import APIRoute  # Customize method rejection only for this router.
from sqlalchemy.orm import Session  # One shared database session per request.
from starlette.exceptions import HTTPException  # The existing shared handler formats method errors.

from app.bookings.schemas import BookingResponse, HoldRequest  # Published request and response shapes.
from app.core.database import get_db  # Existing dependency closes and rolls back failed requests.
from app.core.errors import error_responses  # Reuse the shared error envelope in OpenAPI.
from app.core.principal import Principal, get_current_principal  # Identity comes from the verified bearer token.
from app.reservations.service import ReservationService  # The same engine serves manager blocks and availability.

class BookingRoute(APIRoute):  # Starlette's first path match otherwise advertises only GET or only DELETE in a 405.
    async def handle(self, scope, receive, send) -> None:  # Routing is asynchronous; the database handlers below stay synchronous.
        if self.methods and scope["method"] not in self.methods:  # A known path was called with an unsupported HTTP method.
            allowed = set(self.methods)  # Start with the methods on this route declaration.
            for route in router.routes:  # Inspect this router directly; FastAPI may wrap included routers in app.routes.
                if isinstance(route, APIRoute) and route.path == self.path:  # GET and DELETE share /bookings/{booking_id}.
                    allowed.update(route.methods or set())  # Advertise the complete resource capability.
            raise HTTPException(405, headers={"Allow": ", ".join(sorted(allowed))})  # Shared error handling keeps the established envelope.
        await super().handle(scope, receive, send)  # Supported methods follow normal FastAPI handling.


router = APIRouter(tags=["bookings"], route_class=BookingRoute)  # Apply the method-header fix only to Person 1's endpoints.


@router.post(  # Creating a hold is a state-changing operation that requires a retry key.
    "/fields/{field_id}/bookings", status_code=201, response_model=BookingResponse,  # Preserve the team's agreed URL and response.
    responses=error_responses(404, 409, 422),  # Shared contract generation also adds authentication and malformed-body errors.
)  # Finish the route declaration.
def create_booking(  # A plain def lets FastAPI run synchronous SQL away from its event loop.
    field_id: UUID, body: HoldRequest,  # The path chooses the surface; the body chooses the interval.
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200, pattern=r"^[\x21-\x7e]+$")],  # Same visible-ASCII contract as manager blocks.
    principal: Principal = Depends(get_current_principal),  # Never accept an owner ID in the body.
    db: Session = Depends(get_db),  # Authentication and the service share this session.
) -> dict[str, Any]:  # FastAPI validates the returned mapping against BookingResponse.
    return ReservationService(db).create_hold(principal, field_id, body.start, body.end, idempotency_key)  # The service locks, checks, saves, and commits.


@router.get("/bookings/{booking_id}", response_model=BookingResponse, responses=error_responses(404))  # A foreign owner's booking is also 404.
def get_booking(  # Read the booking's effective state, including elapsed holds.
    booking_id: UUID,  # Validated path identifier.
    principal: Principal = Depends(get_current_principal),  # Login is required on reads too.
    db: Session = Depends(get_db),  # Reuse the request session.
) -> dict[str, Any]:  # The DTO excludes user IDs and internal persistence details.
    return ReservationService(db).get_booking(principal, booking_id)  # Ownership is checked inside the service.


@router.delete("/bookings/{booking_id}", status_code=204, responses=error_responses(404))  # Successful cancellation has no response body.
def cancel_booking(  # Repeated cancellation and late cancellation both return 204.
    booking_id: UUID,  # The booking to cancel.
    principal: Principal = Depends(get_current_principal),  # Only the owner may cancel.
    db: Session = Depends(get_db),  # The service commits the change and releases its lock.
) -> Response:  # Explicit Response avoids sending JSON null with a 204.
    ReservationService(db).cancel_booking(principal, booking_id)  # No lifecycle decisions live in this route.
    return Response(status_code=204)  # An empty successful response is naturally safe to repeat.

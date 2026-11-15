"""Health checks, error format and correlation IDs."""


def test_live(anon_client):  # The process is up.
    r = anon_client.get("/health/live")  # Call the liveness check.
    assert r.status_code == 200  # Success.
    assert r.json() == {"status": "ok"}  # Exact body.


def test_ready_checks_the_database(anon_client):  # The database is reachable.
    r = anon_client.get("/health/ready")  # Call the readiness check.
    assert r.status_code == 200  # Success.
    assert r.json() == {"status": "ready"}  # Exact body.


def test_every_response_has_a_request_id(anon_client):  # Correlation ID is always sent.
    assert anon_client.get("/health/live").headers["X-Request-ID"]  # Present and non-empty.


def test_a_safe_caller_request_id_is_echoed_back(anon_client):  # Safe IDs are kept.
    r = anon_client.get("/health/live", headers={"X-Request-ID": "demo-123"})  # Send our own ID.
    assert r.headers["X-Request-ID"] == "demo-123"  # Returned unchanged.


def test_an_unsafe_request_id_is_replaced(anon_client):  # Unsafe IDs are discarded.
    r = anon_client.get("/health/live", headers={"X-Request-ID": "bad id with spaces"})  # Send an ID with spaces.
    assert r.headers["X-Request-ID"] != "bad id with spaces"  # A new one was generated.


def test_unknown_url_uses_the_shared_error_format(anon_client):  # Even 404s use our error envelope.
    r = anon_client.get("/no-such-route")  # Call a URL that does not exist.
    assert r.status_code == 404  # Not found.
    assert r.json() == {"error": {"code": "not_found", "message": "Not Found"}}  # Exact shared format.

"""Health checks, error format and correlation IDs."""


def test_live(anon_client):
    r = anon_client.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_checks_the_database(anon_client):
    r = anon_client.get("/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


def test_every_response_has_a_request_id(anon_client):
    assert anon_client.get("/health/live").headers["X-Request-ID"]


def test_a_safe_caller_request_id_is_echoed_back(anon_client):
    r = anon_client.get("/health/live", headers={"X-Request-ID": "demo-123"})
    assert r.headers["X-Request-ID"] == "demo-123"


def test_an_unsafe_request_id_is_replaced(anon_client):
    r = anon_client.get("/health/live", headers={"X-Request-ID": "bad id with spaces"})
    assert r.headers["X-Request-ID"] != "bad id with spaces"


def test_unknown_url_uses_the_shared_error_format(anon_client):
    r = anon_client.get("/no-such-route")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "not_found", "message": "Not Found"}}
---
name: mock-outbound-http-fastapi-di
description: 'Test a FastAPI endpoint''s outbound HTTP calls (GitHub API, third-party service) fully offline via Depends()-injected httpx.Client + httpx.MockTransport override'
installer: auto-skill
created_at: 2026-08-30T12:24:55+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'mike-oracle'
category: 'testing'
content_hash: 1591c85955504b97faa8b2c2e59375b7dcfa34d0e1dbb8aad33330f8cc2e8ffa
---
## Test a FastAPI endpoint's outbound HTTP calls fully offline via Depends() override

Use when a FastAPI (or any Starlette-based) endpoint calls an external HTTP API
(GitHub, a third-party service, another internal service) and the test suite must
run with zero real network — required for CI, for offline unit tests, or whenever a
spec says "tests must not hit the real network."

### The pattern

1. Never construct the outbound `httpx.Client` inline inside the route function.
   Instead, expose it as a dependency:
   ```python
   _http_client: httpx.Client | None = None

   def get_http_client() -> httpx.Client:
       global _http_client
       if _http_client is None:
           _http_client = httpx.Client(timeout=10.0)
       return _http_client

   @app.post("/scan")
   def scan(request: ScanRequest, client: httpx.Client = Depends(get_http_client)):
       ...
   ```
2. In tests, override the dependency with a client backed by `httpx.MockTransport`,
   whose handler inspects `request.url`/`request.method` and returns canned
   `httpx.Response` objects — no real socket is ever opened:
   ```python
   def handler(request: httpx.Request) -> httpx.Response:
       url = str(request.url)
       if "api.github.com/repos/" in url:
           return httpx.Response(200, json={"tree": [...]})
       if "raw.githubusercontent.com/" in url:
           return httpx.Response(200, text="file contents")
       return httpx.Response(404)

   app.dependency_overrides[get_http_client] = lambda: httpx.Client(
       transport=httpx.MockTransport(handler)
   )
   client = TestClient(app)
   ```
3. Clear `app.dependency_overrides` after each test (autouse fixture or explicit
   teardown) so overrides from one test don't leak into the next.
4. Wrap the override + `TestClient` construction in a pytest fixture that takes the
   transport as a parameter, so every test just does
   `client = make_test_client(build_transport(...))` instead of repeating the
   dependency-override boilerplate.

### Why this beats monkeypatching `httpx.get`/`requests.get`

- Exercises the *exact* production code path (same `httpx.Client`, same call sites),
  not a stubbed-out function — a refactor that changes how the client is called
  still gets caught.
- No need for a mocking library (`respx`, `responses`, etc.) — `httpx.MockTransport`
  ships in `httpx` itself.
- Works identically whether the outbound call is one API (GitHub) or several
  (tree API + raw file fetch) — one handler function routes by URL substring.

### Gotcha

If the route builds the `httpx.Client` itself instead of taking it via `Depends()`,
none of this works — the override has nothing to attach to. This is the one
non-negotiable prerequisite: outbound HTTP clients must be dependency-injected,
even in a small service where it looks like unnecessary indirection.

### Project layout note (Python/uv specifically)

If `app/` (the package) and `tests/` are sibling directories under the project
root, `from app.main import app` inside `tests/conftest.py` raises
`ModuleNotFoundError: No module named 'app'` unless the project root is on
`sys.path`. Fix in `pyproject.toml`, no plugin needed (pytest >= 7):
```toml
[tool.pytest.ini_options]
pythonpath = ["."]
```

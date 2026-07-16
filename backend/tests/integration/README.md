Integration testing helpers

Fixtures provided in this folder (auto-discovered by pytest):

- `integration_db_engine`: per-worker sqlite DB used for integration tests, created from ORM metadata.
- `db_session`: yields a SQLAlchemy session and rolls back transactions after each test for isolation.
- `client`: `TestClient` instance with DB dependency overridden to use the test session.
- `auth_headers`: helper to create Authorization headers using the app's JWT creation.
- `override_dependency`: helper to override FastAPI dependencies during tests.
- `ExternalHTTPMock` (in `utils.py`): lightweight HTTP mock that patches `httpx` at runtime.

Notes:
- Adjust `integration_db_engine` to point to a real test database (Postgres) by setting environment variables
  and editing the fixture if integration tests require a live DB.
- The per-worker sqlite files are designed to support pytest-xdist parallel runs.

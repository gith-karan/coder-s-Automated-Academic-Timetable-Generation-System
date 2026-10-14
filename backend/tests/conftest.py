import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="nfsu-test-")
os.environ.update({
    "NFSU_ENV": "test",
    "NFSU_DATABASE_URL": f"sqlite:///{_tmp}/test.db".replace("\\", "/"),
    "NFSU_BOOTSTRAP_ADMIN_PASSWORD": "Admin#Nfsu-2026-Test",
    "NFSU_DEMO_PASSWORD": "Demo#Nfsu-2026-Test",
    "NFSU_LOG_DIR": f"{_tmp}/logs",
    "NFSU_SOLVER_WORKERS": "4",
    "NFSU_TRUSTED_HOSTS": '["testserver"]',
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.ratelimit import limiter  # noqa: E402
from app.main import app  # noqa: E402

ADMIN = ("admin@nfsu.ac.in", "Admin#Nfsu-2026-Test")
DEMO_PW = "Demo#Nfsu-2026-Test"


class Api:
    """Test client wrapper that logs in and sends the CSRF header like the SPA does."""

    def __init__(self, client: TestClient):
        self.c = client
        self.csrf = None

    def login(self, email: str, password: str):
        limiter.reset()
        self.c.cookies.clear()
        r = self.c.post("/api/v1/auth/login", json={"identifier": email, "password": password})
        assert r.status_code == 200, r.text
        self.csrf = r.json()["csrf_token"]
        return r.json()

    def _h(self):
        return {"X-CSRF-Token": self.csrf} if self.csrf else {}

    def get(self, url, **kw):
        return self.c.get("/api/v1" + url, **kw)

    def post(self, url, json=None, **kw):
        return self.c.post("/api/v1" + url, json=json, headers=self._h(), **kw)

    def put(self, url, json=None):
        return self.c.put("/api/v1" + url, json=json, headers=self._h())

    def patch(self, url, json=None):
        return self.c.patch("/api/v1" + url, json=json, headers=self._h())


@pytest.fixture(scope="session")
def client():
    with TestClient(app, base_url="http://testserver") as c:
        yield c


def new_api(client) -> Api:
    return Api(TestClient(app, base_url="http://testserver"))

"""Security regression tests for the server.

Each test here pins down a vulnerability that existed in an earlier version.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import _resolve_spa_file, create_app

TRAVERSAL_PATHS = [
    "/..%2F..%2Fapp%2Fconfig.py",
    "/%2e%2e/%2e%2e/app/config.py",
    "/..%2f..%2f.env",
    "/..%2F..%2F..%2F..%2F..%2F..%2Fetc%2Fpasswd",
    "/assets/..%2F..%2Fsecret.txt",
    "/%2e%2e%2fsecret.txt",
]


@pytest.fixture
def dist(tmp_path):
    """A fake React build with a secret file sitting next to it."""
    build = tmp_path / "project" / "dashboard" / "dist"
    (build / "assets").mkdir(parents=True)
    (build / "index.html").write_text("<!doctype html><title>Argus SPA</title>")
    (build / "favicon.svg").write_text("<svg/>")
    (build / "assets" / "app.js").write_text("console.log('app')")
    (tmp_path / "project" / "secret.txt").write_text("TOP-SECRET")
    (tmp_path / "project" / "dashboard" / "secret.txt").write_text("TOP-SECRET")
    return build


@pytest.fixture
def spa_client(dist):
    with TestClient(create_app(build_dir=dist)) as c:
        yield c


class TestSPAPathTraversal:
    @pytest.mark.parametrize("path", TRAVERSAL_PATHS)
    def test_traversal_never_leaks_files(self, spa_client, path):
        response = spa_client.get(path)
        assert "TOP-SECRET" not in response.text
        assert "root:x:0:0" not in response.text
        assert "Application configuration" not in response.text

    def test_real_files_inside_dist_still_served(self, spa_client):
        response = spa_client.get("/favicon.svg")
        assert response.status_code == 200
        assert response.text == "<svg/>"

    def test_unknown_routes_get_index(self, spa_client):
        response = spa_client.get("/repos/42")
        assert response.status_code == 200
        assert "Argus SPA" in response.text

    def test_resolver_rejects_parent_paths(self, dist):
        assert _resolve_spa_file(dist, "../secret.txt") == dist.resolve() / "index.html"
        assert _resolve_spa_file(dist, "../../secret.txt") == dist.resolve() / "index.html"

    def test_resolver_rejects_symlink_escape(self, dist, tmp_path):
        outside = tmp_path / "outside.txt"
        outside.write_text("TOP-SECRET")
        (dist / "link.txt").symlink_to(outside)
        assert _resolve_spa_file(dist, "link.txt") == dist.resolve() / "index.html"

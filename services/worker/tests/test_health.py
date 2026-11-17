from collections.abc import Iterator
import json
import threading
import urllib.error
import urllib.request

import pytest

from jude_worker.main import make_health_server


def _ok() -> None:
    return None


def _fail() -> None:
    raise OSError("connection refused")


@pytest.fixture
def serve() -> Iterator[object]:
    servers = []

    def _start(check: object) -> str:
        server = make_health_server("127.0.0.1", 0, check)  # type: ignore[arg-type]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}"

    yield _start
    for s in servers:
        s.shutdown()
        s.server_close()


def test_healthz_ok(serve) -> None:  # type: ignore[no-untyped-def]
    base = serve(_ok)
    with urllib.request.urlopen(f"{base}/healthz", timeout=5) as resp:
        assert resp.status == 200
        body = json.load(resp)
    assert body["status"] == "ok"
    assert body["service"] == "worker"


def test_healthz_503_when_database_unreachable(serve) -> None:  # type: ignore[no-untyped-def]
    base = serve(_fail)
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(f"{base}/healthz", timeout=5)
    assert exc.value.code == 503


def test_unknown_path_404(serve) -> None:  # type: ignore[no-untyped-def]
    base = serve(_ok)
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(f"{base}/other", timeout=5)
    assert exc.value.code == 404

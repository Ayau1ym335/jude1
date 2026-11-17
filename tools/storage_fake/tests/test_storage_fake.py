from collections.abc import Iterator
import hashlib
from pathlib import Path
import threading
import urllib.error
import urllib.request

import pytest

from jude_storage_fake.server import make_server


@pytest.fixture
def base(tmp_path: Path) -> Iterator[str]:
    server = make_server("127.0.0.1", 0, tmp_path)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _req(url: str, method: str, data: bytes | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


def test_healthz(base: str) -> None:
    assert _req(f"{base}/healthz", "GET")[0] == 200


def test_put_get_head_roundtrip(base: str) -> None:
    data = b"synthetic-blob"
    sha = hashlib.sha256(data).hexdigest()
    assert _req(f"{base}/blobs/{sha}", "HEAD")[0] == 404
    assert _req(f"{base}/blobs/{sha}", "PUT", data)[0] == 201
    assert _req(f"{base}/blobs/{sha}", "HEAD")[0] == 200
    assert _req(f"{base}/blobs/{sha}", "GET") == (200, data)


def test_put_existing_is_idempotent(base: str) -> None:
    data = b"same"
    sha = hashlib.sha256(data).hexdigest()
    assert _req(f"{base}/blobs/{sha}", "PUT", data)[0] == 201
    assert _req(f"{base}/blobs/{sha}", "PUT", data)[0] == 200
    assert _req(f"{base}/blobs/{sha}", "GET") == (200, data)


def test_put_rejects_hash_mismatch(base: str) -> None:
    sha = hashlib.sha256(b"declared").hexdigest()
    assert _req(f"{base}/blobs/{sha}", "PUT", b"actual")[0] == 400
    assert _req(f"{base}/blobs/{sha}", "HEAD")[0] == 404


def test_put_rejects_bad_key(base: str) -> None:
    assert _req(f"{base}/blobs/../etc", "PUT", b"x")[0] == 400
    assert _req(f"{base}/blobs/{'A' * 64}", "PUT", b"x")[0] == 400


def test_delete_is_refused(base: str) -> None:
    data = b"keep"
    sha = hashlib.sha256(data).hexdigest()
    _req(f"{base}/blobs/{sha}", "PUT", data)
    assert _req(f"{base}/blobs/{sha}", "DELETE")[0] == 405
    assert _req(f"{base}/blobs/{sha}", "GET") == (200, data)

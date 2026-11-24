"""UT-FN-BLB-01: content-addressed blob store (TSK-BLB-01-A; FR-011, IF-04).

Completion criterion: put twice -> same SHA, one object. Both adapters run against real I/O:
the filesystem adapter under tmp_path, the HTTP adapter against the storage service of
tools/storage_fake on a local port.
"""

from collections.abc import Iterator
import hashlib
import io
import os
from pathlib import Path
import socket
import threading

import pytest

from jude_api.platform.blb import (
    SPOOL_MAX,
    BlobIntegrityError,
    BlobNotFoundError,
    BlobStore,
    BlobStoreUnavailableError,
    FilesystemBlobStore,
    HttpBlobStore,
    put_blob,
)
from jude_api.platform.errors import ApiError
from jude_storage_fake.server import blob_path, make_server

DATA = b"solid\x00binary\xffpayload" * 100
SHA = hashlib.sha256(DATA).hexdigest()


def objects(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


@pytest.fixture
def fake(tmp_path: Path) -> Iterator[tuple[HttpBlobStore, Path]]:
    root = tmp_path / "fake"
    server = make_server("127.0.0.1", 0, root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield HttpBlobStore(f"http://127.0.0.1:{server.server_address[1]}"), root
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture(params=["filesystem", "http"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[tuple[BlobStore, Path]]:
    if request.param == "filesystem":
        root = tmp_path / "fs"
        yield FilesystemBlobStore(root), root
    else:
        yield request.getfixturevalue("fake")


def test_completion_criterion_put_twice_same_sha_one_object(store: tuple[BlobStore, Path]) -> None:
    s, root = store
    assert s.put(DATA) == s.put(DATA) == SHA
    assert len(objects(root)) == 1
    assert s.exists(SHA) and s.get(SHA) == DATA


def test_stream_and_bytes_give_the_same_address(store: tuple[BlobStore, Path]) -> None:
    s, root = store
    if isinstance(s, HttpBlobStore) and os.name != "posix":
        # Windows dev hosts truncate large loopback responses of the stdlib test server (19 s
        # stall, then reset; curl too). Linux (CI, containers) serves 9 MB correctly.
        pytest.skip("large HTTP bodies over Windows loopback")
    big = os.urandom(SPOOL_MAX + 12345)  # spills the spool to a temporary file
    assert s.put(io.BytesIO(big)) == hashlib.sha256(big).hexdigest() == s.put(big)
    assert s.put(b"") == hashlib.sha256(b"").hexdigest()  # the empty blob is a blob too
    assert len(objects(root)) == 2 and s.get(hashlib.sha256(big).hexdigest()) == big


def test_concurrent_puts_of_the_same_bytes_leave_one_object(
    store: tuple[BlobStore, Path],
) -> None:
    s, root = store
    barrier, shas = threading.Barrier(8), []

    def put() -> None:
        barrier.wait()
        shas.append(s.put(DATA))

    threads = [threading.Thread(target=put) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert shas == [SHA] * 8
    assert len(objects(root)) == 1  # no second object, no temporary left behind


def test_unknown_key_and_bad_key(store: tuple[BlobStore, Path]) -> None:
    s, _ = store
    unknown = hashlib.sha256(b"never stored").hexdigest()
    assert not s.exists(unknown)
    with pytest.raises(BlobNotFoundError):
        s.get(unknown)
    for bad in ("ABC", SHA.upper(), SHA[:-1], "../" + SHA[3:]):
        with pytest.raises(ValueError):
            s.exists(bad)


def stored_file(s: BlobStore, root: Path, sha: str) -> Path:
    if isinstance(s, FilesystemBlobStore):
        return s.path(sha)
    return blob_path(root, sha)


def test_never_overwritten_and_corruption_is_detected(store: tuple[BlobStore, Path]) -> None:
    s, root = store
    s.put(DATA)
    path = stored_file(s, root, SHA)
    path.chmod(0o644)
    path.write_bytes(b"bit rot")  # simulate corruption at rest
    assert s.put(DATA) == SHA
    assert path.read_bytes() == b"bit rot"  # an existing object is never rewritten
    with pytest.raises(BlobIntegrityError):
        s.get(SHA)  # never handed out as valid data


def test_the_application_interface_has_no_delete() -> None:
    for cls in (BlobStore, FilesystemBlobStore, HttpBlobStore):
        names = {n for n in dir(cls) if not n.startswith("_")}
        assert not names & {"delete", "remove", "purge", "unlink", "overwrite"}, cls


@pytest.mark.skipif(os.name != "posix", reason="file modes are POSIX (production runs Linux)")
def test_stored_files_are_read_only(tmp_path: Path) -> None:
    s = FilesystemBlobStore(tmp_path)
    s.put(DATA)
    assert s.path(SHA).stat().st_mode & 0o222 == 0
    assert s.path(SHA).relative_to(tmp_path).parts == ("blobs", SHA[:2], SHA[2:4], SHA)


def closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_storage_failure_is_503_storage_unavailable(tmp_path: Path) -> None:
    down = HttpBlobStore(f"http://127.0.0.1:{closed_port()}", timeout_s=2)
    blocked = tmp_path / "not-a-directory"
    blocked.write_bytes(b"")
    for s in (down, FilesystemBlobStore(blocked)):
        with pytest.raises(BlobStoreUnavailableError):
            s.put(DATA)
        with pytest.raises(ApiError) as exc:
            put_blob(s, DATA)
        assert exc.value.code == "STORAGE_UNAVAILABLE"
    with pytest.raises(BlobStoreUnavailableError):
        down.exists(SHA)


def test_put_blob_returns_the_address(tmp_path: Path) -> None:
    assert put_blob(FilesystemBlobStore(tmp_path), DATA) == SHA


@pytest.mark.parametrize("url", ["ftp://host", "storage-fake:9000", "http://"])
def test_store_url_must_be_http(url: str) -> None:
    with pytest.raises(ValueError):
        HttpBlobStore(url)

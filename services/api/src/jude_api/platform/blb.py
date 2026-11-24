"""FN-BLB-01 Store blob by content address (TSK-BLB-01-A; FR-011, IF-04, TD-13, IDR-07).

Immutable storage of files and arrays addressed by their SHA-256:

1. the SHA-256 is computed while the data streams to a temporary object;
2. if an object with that SHA exists, the temporary object is discarded; otherwise it is moved
   to its final key. ``put`` is idempotent: putting the same bytes twice gives the same SHA and
   one object;
3. an object is never overwritten, and the application interface has **no delete**. Erasure is
   the privileged FN-BLB-04 / FN-CAS-08 procedure with its own credential.

``BlobStore`` is the IF-04 port. Adapters:

- ``FilesystemBlobStore``: the IF-04 test adapter (keys ``blobs/aa/bb/<sha>``, files read-only).
- ``HttpBlobStore``: the dev/test storage service (``tools/storage_fake``, compose
  ``JUDE_STORAGE_URL``). It verifies the hash on PUT and refuses DELETE.
- The Supabase Storage (S3 protocol) adapter, with the kind-to-bucket mapping of DS-19, comes
  with XC-FND-08 (M1). It has to keep the same guarantees, as checked by X-07.

``get`` re-hashes what it reads, so a corrupted object never reaches a caller as valid data.
Case-scoped retrieval is FN-BLB-02.

``put_blob`` is the service entry point. A storage failure raises 503 STORAGE_UNAVAILABLE, which
aborts the caller's transaction. An object written just before a rollback stays as an
unreferenced content-addressed object: harmless, and visible to re-verification (FN-BLB-03).
"""

from collections.abc import Iterator
import contextlib
import hashlib
import http.client
import logging
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import IO, Final, Protocol
import urllib.parse

from jude_api.platform.errors import ApiError

log = logging.getLogger("jude_api.blb")
SHA256_RE: Final = re.compile(r"[0-9a-f]{64}")
CHUNK: Final = 1024 * 1024
SPOOL_MAX: Final = 8 * 1024 * 1024  # larger uploads spill to a temporary file
TIMEOUT_S: Final = 30.0

Data = bytes | IO[bytes]


class BlobStoreUnavailableError(Exception):
    """The store could not be reached or failed: STORAGE_UNAVAILABLE for the caller."""


class BlobNotFoundError(KeyError):
    """No object with this SHA-256."""


class BlobIntegrityError(Exception):
    """The stored bytes do not hash to their key (corruption); never returned as data."""


class BlobStore(Protocol):
    """IF-04 v1 (without purge, which is not part of the application interface)."""

    def put(self, data: Data) -> str: ...

    def exists(self, sha: str) -> bool: ...

    def get(self, sha: str) -> bytes: ...


def _check_key(sha: str) -> str:
    if not SHA256_RE.fullmatch(sha):
        raise ValueError("blob key must be a lowercase hex SHA-256")
    return sha


@contextlib.contextmanager
def _spooled(data: Data) -> Iterator[tuple[str, int, IO[bytes]]]:
    """(sha256, size, readable stream at 0), hashing while copying once."""
    h, size = hashlib.sha256(), 0
    with tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX) as tmp:
        if isinstance(data, bytes):
            h.update(data)
            tmp.write(data)
            size = len(data)
        else:
            while chunk := data.read(CHUNK):
                h.update(chunk)
                tmp.write(chunk)
                size += len(chunk)
        tmp.seek(0)
        yield h.hexdigest(), size, tmp


def _verified(sha: str, content: bytes) -> bytes:
    if hashlib.sha256(content).hexdigest() != sha:
        raise BlobIntegrityError(sha)
    return content


class FilesystemBlobStore:
    """Content-addressed files under ``root``: ``blobs/aa/bb/<sha>``, written once, read-only."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, sha: str) -> Path:
        _check_key(sha)
        return self.root / "blobs" / sha[:2] / sha[2:4] / sha

    def put(self, data: Data) -> str:
        try:
            with _spooled(data) as (sha, _size, stream):
                final = self.path(sha)
                if final.is_file():
                    return sha  # identical content already stored: discard the temporary
                final.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(dir=final.parent, prefix=".tmp-")
                try:
                    with os.fdopen(fd, "wb") as fh:
                        shutil.copyfileobj(stream, fh, CHUNK)
                        fh.flush()
                        os.fsync(fh.fileno())
                    if os.name == "posix":  # Windows cannot unlink a read-only temp name
                        os.chmod(tmp, 0o444)  # the link shares the mode: final is read-only
                    # link() fails if the key exists: a concurrent writer of the same bytes
                    # won, and nothing is ever replaced (rename() would overwrite).
                    with contextlib.suppress(FileExistsError):
                        os.link(tmp, final)
                finally:
                    os.unlink(tmp)
                return sha
        except OSError as exc:
            raise BlobStoreUnavailableError(type(exc).__name__) from exc

    def exists(self, sha: str) -> bool:
        try:
            return self.path(sha).is_file()
        except OSError as exc:
            raise BlobStoreUnavailableError(type(exc).__name__) from exc

    def get(self, sha: str) -> bytes:
        try:
            content = self.path(sha).read_bytes()
        except FileNotFoundError:
            raise BlobNotFoundError(sha) from None
        except OSError as exc:
            raise BlobStoreUnavailableError(type(exc).__name__) from exc
        return _verified(sha, content)


class HttpBlobStore:
    """Client of the content-addressed HTTP store (PUT/GET/HEAD /blobs/<sha>, no DELETE)."""

    def __init__(self, base_url: str, timeout_s: float = TIMEOUT_S) -> None:
        parts = urllib.parse.urlsplit(base_url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("blob store URL must be http(s)://host[:port]")
        self.parts, self.timeout_s = parts, timeout_s

    def _connection(self) -> http.client.HTTPConnection:
        cls = (
            http.client.HTTPSConnection
            if self.parts.scheme == "https"
            else http.client.HTTPConnection
        )
        return cls(self.parts.hostname or "", self.parts.port, timeout=self.timeout_s)

    def _request(
        self, method: str, sha: str, body: IO[bytes] | None = None, size: int = 0
    ) -> tuple[int, bytes]:
        path = f"{self.parts.path.rstrip('/')}/blobs/{_check_key(sha)}"
        conn = self._connection()
        try:
            headers = {"Content-Length": str(size)} if body is not None else {}
            conn.request(method, path, body=body, headers=headers)
            r = conn.getresponse()
            return r.status, r.read()
        except (OSError, http.client.HTTPException) as exc:
            raise BlobStoreUnavailableError(type(exc).__name__) from exc
        finally:
            conn.close()

    def put(self, data: Data) -> str:
        with _spooled(data) as (sha, size, stream):
            status, _ = self._request("PUT", sha, stream, size)
        if status not in (200, 201):  # 201 stored, 200 already present (not rewritten)
            raise BlobStoreUnavailableError(f"PUT answered {status}")
        return sha

    def exists(self, sha: str) -> bool:
        status, _ = self._request("HEAD", sha)
        if status not in (200, 404):
            raise BlobStoreUnavailableError(f"HEAD answered {status}")
        return status == 200

    def get(self, sha: str) -> bytes:
        status, content = self._request("GET", sha)
        if status == 404:
            raise BlobNotFoundError(sha)
        if status != 200:
            raise BlobStoreUnavailableError(f"GET answered {status}")
        return _verified(sha, content)


def blob_store() -> BlobStore:
    """The deployment's store (dependency; overridden in tests)."""
    return HttpBlobStore(os.environ["JUDE_STORAGE_URL"])


def put_blob(store: BlobStore, data: Data) -> str:
    """FN-BLB-01: store ``data`` once, return its SHA-256; 503 STORAGE_UNAVAILABLE on failure."""
    try:
        return store.put(data)
    except BlobStoreUnavailableError:
        log.warning("blob.store_unavailable")  # no key, no bytes, no file name
        raise ApiError("STORAGE_UNAVAILABLE") from None

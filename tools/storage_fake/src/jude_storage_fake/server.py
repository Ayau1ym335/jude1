"""Content-addressed blob store fake for local development and integration tests.

Mirrors the guarantees IF-04 relies on (DATA_STRUCTURES_AND_INTERFACES §IF-04, IDR-07):
- content addressing: the key is the SHA-256 of the bytes, verified on PUT;
- no overwrite: a PUT for an existing key does not rewrite the object;
- no delete: DELETE is refused (erasure is the privileged FN-CAS-08 procedure).

HTTP surface (stdlib only):
  GET  /healthz            -> 200
  PUT  /blobs/<sha256>     -> 201 created | 200 already present | 400 hash mismatch / bad key
  GET  /blobs/<sha256>     -> 200 bytes | 404
  HEAD /blobs/<sha256>     -> 200 | 404
  DELETE /blobs/<sha256>   -> 405
"""

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import tempfile

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
BLOB_PREFIX = "/blobs/"
MAX_BODY_BYTES = 512 * 1024 * 1024  # dev guard only; product limits are configuration (OD-03)


def blob_path(root: Path, sha: str) -> Path:
    return root / sha[:2] / sha


def make_server(host: str, port: int, root: Path) -> ThreadingHTTPServer:
    root.mkdir(parents=True, exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status: int, body: bytes = b"", content_type: str = "text/plain") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body and self.command != "HEAD":
                self.wfile.write(body)

        def _key(self) -> str | None:
            if not self.path.startswith(BLOB_PREFIX):
                return None
            sha = self.path[len(BLOB_PREFIX) :]
            return sha if SHA256_RE.fullmatch(sha) else None

        def do_GET(self) -> None:
            if self.path == "/healthz":
                self._reply(200, b'{"status":"ok","service":"storage-fake"}', "application/json")
                return
            sha = self._key()
            if sha is None:
                self._reply(404)
                return
            path = blob_path(root, sha)
            if not path.is_file():
                self._reply(404)
                return
            self._reply(200, path.read_bytes(), "application/octet-stream")

        def do_HEAD(self) -> None:
            sha = self._key()
            exists = sha is not None and blob_path(root, sha).is_file()
            self._reply(200 if exists else 404)

        def do_PUT(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if length < 0 or length > MAX_BODY_BYTES:
                self.close_connection = True  # body not drained: do not reuse the socket
                self._reply(400, b"Content-Length required and within dev limit")
                return
            # Drain the body before any reply so the client never sees a reset.
            data = self.rfile.read(length)
            sha = self._key()
            if sha is None:
                self._reply(400, b"key must be /blobs/<lowercase sha256>")
                return
            if hashlib.sha256(data).hexdigest() != sha:
                self._reply(400, b"sha256 mismatch")
                return
            path = blob_path(root, sha)
            if path.is_file():
                self._reply(200)  # idempotent: identical content already stored, never rewritten
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())
                try:
                    os.link(tmp, path)  # fails if another writer won the race: no overwrite
                except FileExistsError:
                    self._reply(200)
                    return
            finally:
                os.unlink(tmp)
            self._reply(201)

        def do_DELETE(self) -> None:
            self.send_response(405)
            self.send_header("Allow", "GET, HEAD, PUT")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    root = Path(os.environ.get("JUDE_STORAGE_ROOT", "/data"))
    port = int(os.environ.get("JUDE_STORAGE_PORT", "9000"))
    server = make_server("0.0.0.0", port, root)  # noqa: S104 — container-internal port
    print(f"jude-storage-fake: serving {root} on :{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

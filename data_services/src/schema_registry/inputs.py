"""Department submissions (source files, business-metadata files) can be
given to the pipeline two ways:

    samples/pwd_vishwakarma_full_raw_columns.txt          a file on this machine
    storage:inputs/pwd/pwd_vishwakarma_full_raw_columns.txt  a file in the run's storage

`storage:` resolves against whatever storage ENVIRONMENT points at -- the
Wasabi local/, dev/ or prod/ folder -- so a run (or
the BIPP2 server) needs no local copy of anything. Upload once with:

    python3 -m src.schema_registry.inputs upload samples/x.txt inputs/pwd/x.txt
    python3 -m src.schema_registry.inputs upload-batch manifest.csv
    python3 -m src.schema_registry.inputs list inputs/

`upload-batch` reads a CSV with `local_path,storage_key` columns. Relative
local paths are resolved from the manifest's directory; the complete manifest
is validated before any file is uploaded.

Whichever way a file arrives, the pipeline archives the exact bytes it
parsed (archive()) so every snapshot can be traced to its original.
"""

import csv
import hashlib
import sys
from pathlib import Path, PurePosixPath

from src.storage.base import ObjectStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)

STORAGE_SCHEME = "storage:"


def read_input(storage: ObjectStorage, ref: str) -> tuple[bytes, str]:
    """(bytes, file name) for a local path or a `storage:<key>` reference."""

    if ref.startswith(STORAGE_SCHEME):
        key = ref[len(STORAGE_SCHEME):].lstrip("/")
        if not storage.exists(key):
            raise FileNotFoundError(f"'{key}' not found in storage -- upload it first: "
                                    f"python3 -m src.schema_registry.inputs upload <local file> {key}")
        return storage.read_bytes(key), PurePosixPath(key).name
    path = Path(ref)
    return path.read_bytes(), path.name


def decode(data: bytes) -> str:
    # utf-8-sig: spreadsheet exports often start with a byte-order mark
    return data.decode("utf-8-sig")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_upload_manifest(manifest_path: str | Path) -> list[tuple[Path, str]]:
    """Validate a batch-upload manifest before any storage writes begin."""

    manifest = Path(manifest_path)
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"local_path", "storage_key"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("upload manifest must have local_path and storage_key columns")

        uploads: list[tuple[Path, str]] = []
        seen_keys: set[str] = set()
        for line, row in enumerate(reader, start=2):
            local = (row.get("local_path") or "").strip()
            raw_key = (row.get("storage_key") or "").strip().replace("\\", "/")
            if not local or not raw_key:
                raise ValueError(f"upload manifest line {line} needs local_path and storage_key")

            source = Path(local)
            if not source.is_absolute():
                source = manifest.parent / source
            if not source.is_file():
                raise FileNotFoundError(f"upload manifest line {line}: local file not found: {source}")

            key_path = PurePosixPath(raw_key)
            if key_path.is_absolute() or ".." in key_path.parts:
                raise ValueError(f"upload manifest line {line}: invalid storage key: {raw_key}")
            key = str(key_path)
            if key in seen_keys:
                raise ValueError(f"upload manifest line {line}: duplicate storage key: {key}")
            seen_keys.add(key)
            uploads.append((source, key))

    if not uploads:
        raise ValueError("upload manifest has no files")
    return uploads


def upload_batch(storage: ObjectStorage, uploads: list[tuple[Path, str]]) -> list[tuple[str, int, str]]:
    """Upload validated files sequentially through one storage client."""

    results = []
    for source, key in uploads:
        data = source.read_bytes()
        storage.write_bytes(key, data)
        results.append((key, len(data), sha256(data)))
    return results


def archive(storage: ObjectStorage, path: str, data: bytes) -> str:
    """Store `data` at `path` plus `<path>.sha256` (sha256sum format).
    Returns the hash."""

    digest = sha256(data)
    storage.write_bytes(path, data)
    storage.write_bytes(f"{path}.sha256", f"{digest}  {PurePosixPath(path).name}\n".encode())
    return digest


def _main(argv: list[str]) -> int:
    from src.storage import storage_from_env
    from src.utils.config import load_env

    if argv[:1] in (["-h"], ["--help"]) or not argv:
        argv = ["--help"] if argv else argv
    else:
        load_env()
        storage = storage_from_env()
    if len(argv) == 3 and argv[0] == "upload":
        local, key = argv[1], argv[2].lstrip("/")
        from src.utils.cli import confirm_changes
        confirm_changes(f"upload {local} to {key}")
        data = Path(local).read_bytes()
        storage.write_bytes(key, data)
        print(f"Uploaded {local} -> {key} ({len(data)} bytes, sha256 {sha256(data)[:12]}...)")
        print(f"Use it as: SOURCE_FILE={STORAGE_SCHEME}{key}")
        return 0
    if len(argv) == 2 and argv[0] == "upload-batch":
        from src.utils.cli import confirm_changes

        manifest = Path(argv[1])
        uploads = read_upload_manifest(manifest)
        confirm_changes(f"upload {len(uploads)} file(s) listed in {manifest}")
        for key, size, digest in upload_batch(storage, uploads):
            print(f"Uploaded -> {key} ({size} bytes, sha256 {digest[:12]}...)")
        print(f"Uploaded {len(uploads)} file(s)")
        return 0
    if argv[:1] == ["list"] and len(argv) <= 2:
        for key in storage.list(argv[1] if len(argv) == 2 else "inputs/"):
            print(f"{STORAGE_SCHEME}{key}")
        return 0
    asked_for_help = argv[:1] in (["-h"], ["--help"])
    print("usage: python3 -m src.schema_registry.inputs upload <local file> <storage key>\n"
          "       python3 -m src.schema_registry.inputs upload-batch <manifest.csv>\n"
          "       python3 -m src.schema_registry.inputs list [prefix]", file=sys.stdout if asked_for_help else sys.stderr)
    return 0 if asked_for_help else 2


if __name__ == "__main__":
    from src.utils.cli import run_cli

    sys.exit(run_cli("inputs", _main, sys.argv[1:]))

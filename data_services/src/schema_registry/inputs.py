"""Department submissions (source files, business-metadata files) can be
given to the pipeline two ways:

    samples/pwd_vishwakarma_full_raw_columns.txt          a file on this machine
    storage:inputs/pwd/pwd_vishwakarma_full_raw_columns.txt  a file in the run's storage

`storage:` resolves against whatever storage ENVIRONMENT points at -- the
Wasabi dev/ or prod/ folder, or the local storage/ folder -- so a run (or
the BIPP2 server) needs no local copy of anything. Upload once with:

    python3 -m src.schema_registry.inputs upload samples/x.txt inputs/pwd/x.txt
    python3 -m src.schema_registry.inputs list inputs/

Whichever way a file arrives, the pipeline archives the exact bytes it
parsed (archive()) so every snapshot can be traced to its original.
"""

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

    load_env()
    storage = storage_from_env()
    if len(argv) == 3 and argv[0] == "upload":
        local, key = argv[1], argv[2].lstrip("/")
        data = Path(local).read_bytes()
        storage.write_bytes(key, data)
        print(f"Uploaded {local} -> {key} ({len(data)} bytes, sha256 {sha256(data)[:12]}...)")
        print(f"Use it as: SOURCE_FILE={STORAGE_SCHEME}{key}")
        return 0
    if argv[:1] == ["list"] and len(argv) <= 2:
        for key in storage.list(argv[1] if len(argv) == 2 else "inputs/"):
            print(f"{STORAGE_SCHEME}{key}")
        return 0
    print("usage: python3 -m src.schema_registry.inputs upload <local file> <storage key>\n"
          "       python3 -m src.schema_registry.inputs list [prefix]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))

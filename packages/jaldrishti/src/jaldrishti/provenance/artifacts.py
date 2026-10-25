"""Deterministic filesystem helpers for provenance-bearing artifacts.

Hashes establish byte identity and support reproducibility checks; they do not
by themselves establish source authenticity, scientific validity, or trust.
Those properties require signed sources, acquisition metadata, and explicit
quality assessment elsewhere in the provenance model.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, TypedDict


class FileRecord(TypedDict):
    """JSON-compatible identity record for one regular file."""

    path: str
    bytes: int
    sha256: str


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest of a file without loading it all into memory."""

    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    item = Path(path)
    if not item.is_file():
        raise FileNotFoundError(f"not a regular file: {item}")
    digest = hashlib.sha256()
    with item.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: str | Path, value: Any) -> Path:
    """Serialize deterministic UTF-8 JSON and atomically replace the target."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise
    return target


def read_json(path: str | Path) -> Any:
    """Read one UTF-8 JSON artifact."""

    return json.loads(Path(path).read_text(encoding="utf-8"))


def file_record(path: str | Path, base: str | Path | None = None) -> FileRecord:
    """Return a portable size-and-digest record for a regular file.

    When ``base`` is supplied, the file must resolve within it and the recorded
    path is POSIX-relative. This prevents accidental publication of absolute
    local paths in provenance artifacts.
    """

    item = Path(path)
    if not item.is_file():
        raise FileNotFoundError(f"not a regular file: {item}")
    if base is None:
        display = str(item)
    else:
        resolved_item = item.resolve()
        resolved_base = Path(base).resolve()
        try:
            display = resolved_item.relative_to(resolved_base).as_posix()
        except ValueError as exc:
            raise ValueError(
                f"file {resolved_item} is outside provenance base {resolved_base}"
            ) from exc
    return {
        "path": display,
        "bytes": item.stat().st_size,
        "sha256": sha256_file(item),
    }

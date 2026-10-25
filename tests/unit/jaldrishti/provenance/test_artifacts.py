import hashlib
from pathlib import Path

import pytest
from jaldrishti.provenance.artifacts import (
    atomic_write_json,
    file_record,
    read_json,
    sha256_file,
)


def test_sha256_file_streams_known_content(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"authenticated payload")

    assert sha256_file(source, chunk_size=3) == hashlib.sha256(source.read_bytes()).hexdigest()


def test_atomic_json_is_deterministic_and_replaces_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "record.json"
    target.parent.mkdir(parents=True)
    target.write_text("stale", encoding="utf-8")

    returned = atomic_write_json(target, {"z": 1, "a": "Assam"})

    assert returned == target
    assert target.read_text(encoding="utf-8") == '{\n  "a": "Assam",\n  "z": 1\n}\n'
    assert read_json(target) == {"a": "Assam", "z": 1}
    assert list(target.parent.glob(f".{target.name}.*")) == []


def test_file_record_is_relative_to_approved_base(tmp_path: Path) -> None:
    source = tmp_path / "raw" / "observation.json"
    source.parent.mkdir()
    source.write_text("{}\n", encoding="utf-8")

    record = file_record(source, tmp_path)

    assert record == {
        "path": "raw/observation.json",
        "bytes": 3,
        "sha256": hashlib.sha256(b"{}\n").hexdigest(),
    }


def test_file_record_refuses_to_leak_path_outside_base(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    approved_base = tmp_path / "published"
    approved_base.mkdir()

    with pytest.raises(ValueError, match="outside provenance base"):
        file_record(source, approved_base)

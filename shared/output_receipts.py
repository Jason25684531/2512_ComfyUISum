"""Atomic, local-only receipts for replaying a failed DB output finalize."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def receipt_path(output_root: Path, job_id: str) -> Path:
    root = output_root.resolve()
    receipts = (root / ".receipts").resolve()
    if receipts.parent != root:
        raise ValueError("invalid output root")
    receipts.mkdir(mode=0o700, exist_ok=True)
    return receipts / f"{job_id}.json"


def write_receipt(output_root: Path, job_id: str, payload: dict[str, Any]) -> Path:
    """Write only a relative, verified output reference before DB finalization."""
    root = output_root.resolve()
    filename = Path(str(payload["filename"])).name
    target = (root / filename).resolve()
    if target.parent != root or not target.is_file() or target.stat().st_size <= 0:
        raise ValueError("receipt output is outside root or missing")
    data = {**payload, "filename": filename}
    destination = receipt_path(root, job_id)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, destination)
    return destination


def read_receipts(output_root: Path) -> list[dict[str, Any]]:
    root = output_root.resolve()
    directory = (root / ".receipts").resolve()
    if directory.parent != root or not directory.exists():
        return []
    result = []
    for receipt in directory.glob("*.json"):
        try:
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            target = (root / Path(str(payload["filename"])).name).resolve()
            if target.parent == root and target.is_file() and target.stat().st_size > 0:
                result.append(payload)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
    return result


def remove_receipt(output_root: Path, job_id: str) -> None:
    receipt_path(output_root, job_id).unlink(missing_ok=True)

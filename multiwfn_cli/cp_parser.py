"""Parsing helpers for Multiwfn critical point output files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np


FLOAT_RE = re.compile(r"[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?")


def _sanitize_key(text: str) -> str:
    lowered = text.lower().replace("(columns)", "columns")
    cleaned = re.sub(r"[^a-z0-9]+", "_", lowered)
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = cleaned.strip("_")
    return cleaned or "field"


def _parse_numbers(text: str) -> List[float]:
    cleaned = text.replace("D", "E")
    matches = FLOAT_RE.findall(cleaned)
    return [float(m) for m in matches]


def _stack_values(values: List[Any]) -> np.ndarray:
    first = values[0]
    if all(isinstance(v, (int, np.integer)) for v in values):
        return np.array(values, dtype=int)
    if all(isinstance(v, (int, float, np.number)) for v in values):
        return np.array(values, dtype=float)
    if all(isinstance(v, str) for v in values):
        return np.array(values, dtype=object)
    converted: List[np.ndarray] = []
    shapes: set[Tuple[int, ...]] = set()
    for value in values:
        array = np.asarray(value)
        converted.append(array)
        shapes.add(array.shape)
    if len(shapes) == 1:
        try:
            return np.stack([np.asarray(v, dtype=float) for v in converted])
        except ValueError:
            return np.stack(converted)
    return np.array(values, dtype=object)


def _finalize_matrix(
    current: Dict[str, Any],
    matrix_key: str | None,
    matrix_rows: List[List[float]],
    key_map: Dict[str, str],
) -> Tuple[str | None, List[List[float]]]:
    if matrix_key and matrix_rows:
        sanitized = _sanitize_key(matrix_key)
        current[sanitized] = np.array(matrix_rows, dtype=float)
        key_map[sanitized] = matrix_key
    return None, []


def parse_cp_file(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    cps: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None
    key_map: Dict[str, str] = {}
    raw_lines: List[str] = []
    matrix_key: str | None = None
    matrix_rows: List[List[float]] = []

    header_re = re.compile(r"CP\s+(\d+),\s+Type\s+\(([^)]+)\)")
    nucleus_re = re.compile(r"Corresponding nucleus:\s*(\d+)\(([^)]+)\)")

    def finalize_current() -> None:
        nonlocal current, key_map, raw_lines, matrix_key, matrix_rows
        if current is None:
            return
        matrix_key, matrix_rows = _finalize_matrix(current, matrix_key, matrix_rows, key_map)
        current["raw_block"] = "\n".join(raw_lines).strip()
        current["key_map"] = key_map.copy()
        cps.append(current)
        current = None
        key_map = {}
        raw_lines = []
        matrix_key = None
        matrix_rows = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("----------------") and "CP" in stripped and "Type" in stripped:
            finalize_current()
            header_match = header_re.search(stripped)
            if not header_match:
                continue
            current = {
                "cp_index": int(header_match.group(1)),
                "cp_type": header_match.group(2).strip(),
            }
            key_map = {"cp_index": "CP index", "cp_type": "CP type"}
            raw_lines = [stripped]
            continue

        if current is None:
            continue

        raw_lines.append(line.rstrip("\n"))

        if not stripped:
            matrix_key, matrix_rows = _finalize_matrix(current, matrix_key, matrix_rows, key_map)
            continue

        nucleus_match = nucleus_re.match(stripped)
        if nucleus_match:
            current["corresponding_nucleus_index"] = int(nucleus_match.group(1))
            current["corresponding_nucleus_label"] = nucleus_match.group(2).strip()
            key_map["corresponding_nucleus_index"] = "Corresponding nucleus index"
            key_map["corresponding_nucleus_label"] = "Corresponding nucleus label"
            continue

        if ":" in stripped:
            matrix_key, matrix_rows = _finalize_matrix(current, matrix_key, matrix_rows, key_map)
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            numbers = _parse_numbers(value)
            sanitized = _sanitize_key(key)
            if key.lower().endswith("matrix") or key.lower().startswith("eigenvectors"):
                matrix_key = key
                matrix_rows = []
                key_map[_sanitize_key(key)] = key
            if numbers:
                if len(numbers) == 1:
                    current[sanitized] = numbers[0]
                else:
                    current[sanitized] = numbers
                key_map[sanitized] = key
            elif value:
                current[sanitized] = value
                key_map[sanitized] = key
            continue

        numbers = _parse_numbers(stripped)
        if numbers and matrix_key:
            matrix_rows.append(numbers)
            continue

        # treat numeric-only lines following matrix hints even without matrix state
        if numbers:
            sanitized = _sanitize_key("values")
            current.setdefault(sanitized, []).append(numbers)
            key_map[sanitized] = "values"
            continue

    finalize_current()
    return cps


def aggregate_cp_records(records: Iterable[Dict[str, Any]]) -> Dict[str, np.ndarray]:
    records = list(records)
    if not records:
        return {}

    aggregated: Dict[str, List[Any]] = {}
    for entry in records:
        for key, value in entry.items():
            if key in {"key_map"}:
                continue
            aggregated.setdefault(key, []).append(value)

    payload: Dict[str, np.ndarray] = {}
    for key, values in aggregated.items():
        if key == "raw_block":
            payload[key] = np.array(values, dtype=object)
            continue
        try:
            payload[key] = _stack_values(values)
        except Exception:
            payload[key] = np.array(values, dtype=object)
    payload["key_map"] = np.array([record.get("key_map", {}) for record in records], dtype=object)
    return payload



"""Discover tabular layouts without inferring physical meaning from numeric values."""

from __future__ import annotations

import csv
import itertools
import re
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from openpyxl import load_workbook

G0 = 9.80665
ROLES = ("time", "x", "y", "z")


class InputError(ValueError):
    """An input needs an explicit correction or mapping."""


def normalized(value):
    return str(value or "").lower().replace("²", "2").replace("µ", "u").replace("μ", "u")


def role_of(value):
    s = normalized(value)
    tokens = re.findall(r"[a-z]+", s)
    compact = "".join(tokens)
    if any(w in tokens for w in ("gyro", "angular", "velocity", "speed", "distance")):
        return None
    if any(w in tokens for w in ("time", "timestamp", "elapsed")):
        return "time"
    for axis in "xyz":
        if axis in tokens and ("acc" in s or acceleration_unit(s) is not None):
            return axis
        # Prefix forms also accept attached units, e.g. AccX_g and Gx.
        if re.fullmatch(rf"(?:a|acc|accel|acceleration|g){axis}(?:g|ms|mss|mms)?", compact):
            return axis
    return None


def acceleration_unit(value):
    s = normalized(value).replace(" ", "").replace("^", "").replace("**", "")
    if re.search(r"mm/(?:s|sec)2|mm(?:s|sec)-2", s):
        return "mm/s2"
    if re.search(r"(?<!m)m/(?:s|sec)2|(?<!m)m(?:s|sec)-2", s):
        return "m/s2"
    if re.search(r"(?:^|[^a-z])g(?:$|[^a-z])", normalized(value)) or re.fullmatch(r"g[xyz]", s):
        return "g"
    return None


def time_unit(value):
    tokens = re.findall(r"[a-z]+", normalized(value))
    for unit, aliases in (
        ("us", {"us", "microsecond", "microseconds"}),
        ("ms", {"ms", "millisecond", "milliseconds"}),
        ("s", {"s", "sec", "secs", "second", "seconds"}),
    ):
        if aliases.intersection(tokens):
            return unit
    return None


@dataclass
class Layout:
    sheet: str
    header_row: int
    data_row: int
    columns: dict[str, int]  # zero based internally
    labels: dict[str, str]
    time_unit: str | None
    acceleration_units: list[str | None]

    def describe(self):
        result = asdict(self)
        result["columns"] = {k: v + 1 for k, v in self.columns.items()}
        return result


@contextmanager
def sheets(path: Path, *, data_only=True):
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        book = load_workbook(path, read_only=True, data_only=data_only)
        try:
            # Ignore unreliable exporter dimensions; stream all actual cells.
            for sheet in book:
                sheet.reset_dimensions()
            yield {sheet.title: sheet for sheet in book}
        finally:
            book.close()
    elif path.suffix.lower() in {".csv", ".tsv", ".txt"}:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            sample = handle.read(16384)
            handle.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel_tab if path.suffix.lower() == ".tsv" else csv.excel
            yield {"data": csv.reader(handle, dialect)}
    else:
        raise InputError("Use .xlsx, .xlsm, .csv or .tsv. Convert legacy .xls to .xlsx first.")


def rows(sheet):
    return sheet.iter_rows(values_only=True) if hasattr(sheet, "iter_rows") else iter(sheet)


def _layout(name, preview, row_index, config):
    base = list(preview[row_index])
    # An optional immediately following units row must contain units in all four fields.
    labels = [str(v or "") for v in base]
    if row_index + 1 < len(preview):
        following = preview[row_index + 1]
        labels = [
            f"{label} {following[i]}"
            if i < len(following) and (time_unit(following[i]) or acceleration_unit(following[i]))
            else label
            for i, label in enumerate(labels)
        ]
    mapping = {}
    explicit = config.get("columns", {})
    for role in ROLES:
        if role in explicit:
            value = explicit[role]
            if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
                matches = [value - 1] if value <= len(base) else []
            else:
                matches = [i for i, label in enumerate(labels) if label == value]
        else:
            matches = [i for i, label in enumerate(labels) if role_of(label) == role]
        if len(matches) != 1:
            raise InputError(f"{name}, row {row_index + 1}: {role} column missing or ambiguous.")
        mapping[role] = matches[0]
    if len(set(mapping.values())) != 4:
        raise InputError("Time, X, Y and Z must map to different columns.")
    data_row = row_index + 2
    if row_index + 1 < len(preview):
        next_row = preview[row_index + 1]
        unit_checks = [time_unit(next_row[mapping["time"]]) if len(next_row) > mapping["time"] else None]
        unit_checks.extend(
            acceleration_unit(next_row[mapping[a]]) if len(next_row) > mapping[a] else None for a in "xyz"
        )
        if all(unit_checks):
            data_row += 1
    selected = {role: labels[index] for role, index in mapping.items()}
    return Layout(
        name,
        row_index + 1,
        config.get("data_row", data_row),
        mapping,
        selected,
        config.get("time_unit", time_unit(selected["time"])),
        config.get("acceleration_units", [acceleration_unit(selected[a]) for a in "xyz"]),
    )


def discover(path, config=None):
    config = config or {}
    candidates = []
    with sheets(path) as available:
        if config.get("sheet") and config["sheet"] not in available:
            raise InputError(f"Sheet {config['sheet']!r} not found. Available: {list(available)}")
        for name, sheet in available.items():
            if config.get("sheet") and name != config["sheet"]:
                continue
            preview = list(itertools.islice(rows(sheet), 80))
            header = config.get("header_row")
            indices = [header - 1] if header else range(min(50, len(preview)))
            for i in indices:
                if not 0 <= i < len(preview):
                    raise InputError("header_row must identify a row within the first 80 rows.")
                try:
                    candidate = _layout(name, preview, i, config)
                except InputError:
                    if header and config.get("sheet"):
                        raise
                    continue
                candidates.append(candidate)
                break
    if len(candidates) != 1:
        names = [c.sheet for c in candidates]
        raise InputError(
            f"Expected one usable data sheet; found {names or 'none'}. "
            "Use --sheet, --header-row or --mapping. Recommended headers: "
            "time_s, accel_x_g, accel_y_g, accel_z_g."
        )
    return candidates[0]


def validate_units(layout):
    if layout.time_unit not in {"s", "ms", "us"}:
        raise InputError("Time units unknown. Add units to the header or use --time-unit s/ms/us.")
    if len(layout.acceleration_units) != 3 or any(
        unit not in {"g", "m/s2", "mm/s2"} for unit in layout.acceleration_units
    ):
        raise InputError("Acceleration units unknown. Use --accel-unit or mapping units for X/Y/Z.")
    if layout.data_row <= layout.header_row:
        raise InputError("data_row must follow header_row.")


def number(value, row, role):
    if value is None or isinstance(value, bool):
        raise InputError(f"Row {row}: missing or invalid {role}. No samples were filled or deleted.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise InputError(
            f"Row {row}: {role} is not a number. Check headers, units, formulas and footers. "
            "Use --end-row for a known footer; recalculate formulas in Excel and save first."
        ) from exc
    if not np.isfinite(result):
        raise InputError(f"Row {row}: {role} is not finite.")
    return result


def load_data(path, layout, binary_path, end_row=None):
    """Stream four numeric columns to disk; never silently remove a gap or a bad value."""
    validate_units(layout)
    count, pending_blank = 0, None
    buffer = []
    factors = [
        {"s": 1, "ms": 1e-3, "us": 1e-6}[layout.time_unit],
        *[{"g": 1, "m/s2": 1 / G0, "mm/s2": 1 / (1000 * G0)}[u] for u in layout.acceleration_units],
    ]
    with sheets(path) as available, binary_path.open("wb") as output:
        for row_index, row in enumerate(rows(available[layout.sheet]), 1):
            if row_index < layout.data_row:
                continue
            if end_row is not None and row_index > end_row:
                break
            values = [row[i] if i < len(row) else None for i in layout.columns.values()]
            if all(v is None or str(v).strip() == "" for v in values):
                if any(v is not None and str(v).strip() != "" for v in row):
                    raise InputError(f"Row {row_index}: load columns are blank but other cells contain data.")
                pending_blank = pending_blank or row_index
                continue
            if pending_blank:
                raise InputError(f"Blank data row {pending_blank} inside the recording. Fix the gap.")
            buffer.append(
                [
                    number(v, row_index, role) * scale
                    for v, role, scale in zip(values, ROLES, factors, strict=True)
                ]
            )
            count += 1
            if len(buffer) >= 8192:
                np.asarray(buffer, dtype="float64").tofile(output)
                buffer.clear()
        if buffer:
            np.asarray(buffer, dtype="float64").tofile(output)
    # A formula with no cached result can look exactly like an empty trailing row.
    # Inspect formula text only when that situation occurs, so it cannot truncate a duty silently.
    if pending_blank and path.suffix.lower() in {".xlsx", ".xlsm"}:
        with sheets(path, data_only=False) as available:
            for index, row in enumerate(rows(available[layout.sheet]), 1):
                if index < pending_blank:
                    continue
                if end_row is not None and index > end_row:
                    break
                if any(
                    isinstance(row[i], str) and row[i].startswith("=")
                    for i in layout.columns.values()
                    if i < len(row)
                ):
                    raise InputError(
                        f"Row {index}: formula has no cached value. Recalculate and save in Excel."
                    )
    if count < 16:
        raise InputError("At least 16 numeric samples are required.")
    return np.fromfile(binary_path, dtype="float64").reshape(count, 4)


def write_ascii(path, values, rate):
    with path.open("w", encoding="ascii", newline="\n") as handle:
        handle.write(
            f"SafeTechnologyASCII\n{rate:.12g}\nTime:Secs\nGX\tGY\tGZ\n"
            "Acceleration:g\tAcceleration:g\tAcceleration:g\n\n"
        )
        np.savetxt(handle, values, delimiter="\t", fmt="%.12g")

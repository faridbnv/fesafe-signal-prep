"""Command-line interface; all physical corrections are explicit."""

from __future__ import annotations

import argparse
import json
import math
import platform
import shutil
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

import numpy as np

from . import __version__
from .io import InputError, discover, load_data, write_ascii
from .processing import reduce_rate, sha256, statistics, timing


def configuration(args):
    config = {}
    if args.mapping:
        with args.mapping.open(encoding="utf-8") as stream:
            config = json.load(stream)
        allowed = {"sheet", "header_row", "data_row", "columns", "time_unit", "acceleration_units"}
        if not isinstance(config, dict) or set(config) - allowed:
            raise InputError(f"Mapping must be an object using these keys: {sorted(allowed)}")
        for key in ("header_row", "data_row"):
            if key in config and (type(config[key]) is not int or config[key] < 1):
                raise InputError(f"{key} must be a positive 1-based integer.")
        if "columns" in config and (
            not isinstance(config["columns"], dict) or set(config["columns"]) - {"time", "x", "y", "z"}
        ):
            raise InputError("Mapping columns must use time, x, y and z.")
        if "acceleration_units" in config and not isinstance(config["acceleration_units"], list):
            raise InputError("acceleration_units must be a list for X, Y and Z.")
    for key in ("sheet", "header_row", "time_unit"):
        value = getattr(args, key)
        if value is not None:
            config[key] = value
    if args.accel_unit:
        config["acceleration_units"] = [args.accel_unit] * 3
    return config


def axis_transform(values, mapping, bias):
    if not all(math.isfinite(v) for v in bias):
        raise InputError("Bias values must be finite.")
    names = mapping.lower().split(",")
    if len(names) != 3 or set(s.lstrip("+-") for s in names) != set("xyz"):
        raise InputError("--axis-map must be a signed permutation, e.g. x,-z,y.")
    indices = ["xyz".index(s.lstrip("+-")) for s in names]
    signs = [-1 if s.startswith("-") else 1 for s in names]
    return (values - np.asarray(bias))[:, indices] * np.asarray(signs)


def handoff(report):
    return f"""# Signal handover

The portable text history is `signal.asc`: columns GX, GY, GZ in g, equally spaced
at {report["output"]["sample_rate_hz"]:.12g} samples/s, starting at t=0.
It contains {report["output"]["sample_count"]} samples. The last sample is at
{report["output"]["last_sample_time_s"]:.12g} seconds. SHA-256:
`{report["files"]["signal.asc"]}`.

Open it in fe-safe through File > Data Files > Open Data File(s). Select its three
channels, then File > Data Files > Save Data File(s) As > Dassault Systemes AMC.
Keep Reduction Factor at 1. Reopen the AMC and check names, rate, length and values.
The recipient can open that AMC on another fe-safe machine without Python or Excel.

Before releasing the AMC, the sender must complete these engineering details:

- Component and intended excitation: TO COMPLETE
- Sensor location and mounting: TO COMPLETE
- GX/GY/GZ directions and signs in the FE coordinate system: TO COMPLETE
- Gravity included or compensated, and how the FE model handles it: TO COMPLETE
- FE reference load for each dataset, including sign and acceleration units: TO COMPLETE
- FE model and reference stress datasets supplied separately: TO COMPLETE
- Representative duty distance/time and life equivalence: TO COMPLETE
- Clipping, sensor faults and shocks reviewed: TO COMPLETE
- Fatigue comparison with the full-rate reference: TO COMPLETE

The processing report records numeric transformations. It does not establish those
physical details. A signal file alone cannot supply FE geometry, stress results or
fatigue material settings. Record the final AMC hash after export, for example with
`fesafe-signal hash vehicle_xyz.amc`.
"""


def prepare(args, layout):
    from .plots import diagnostics

    if args.out.exists():
        raise InputError("Output directory already exists. Choose a new --out directory.")
    if args.end_row is not None and args.end_row < layout.data_row:
        raise InputError("--end-row must include data rows.")
    if args.target_rate is None and args.passband_hz is not None:
        raise InputError("--passband-hz is used with --target-rate; no standalone filter is implied.")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Stage complete results beside destination, then rename. Failures leave no apparent output.
    with tempfile.TemporaryDirectory(prefix=".fesafe-", dir=args.out.parent) as tmp:
        staging = Path(tmp)
        binary = staging / "numeric.bin"
        data = load_data(args.input, layout, binary, args.end_row)
        binary.unlink()
        rate, timing_info = timing(data[:, 0], args.timing_tolerance, args.sample_rate)
        original = axis_transform(data[:, 1:], args.axis_map, args.bias_g)
        prepared, output_rate, filter_info, taps = original, rate, None, None
        warnings = [
            "Gravity, sensor faults, clipping and structural applicability require engineering review.",
            "Averaged spectra can hide short events. Inspect event.png and relevant operating sections.",
            "Fatigue equivalence has not been checked by this tool.",
        ]
        if args.target_rate is not None:
            if args.passband_hz is None:
                raise InputError("Reduction requires --passband-hz based on the load and structure.")
            prepared, filter_info, taps = reduce_rate(
                original, rate, args.target_rate, args.passband_hz, args.attenuation_db
            )
            output_rate = filter_info["target_sample_rate_hz"]
            if filter_info["samples_per_passband_cycle"] < 10:
                warnings.append(
                    "Fewer than 10 output samples per passband-edge cycle. "
                    "Peak resolution may be poor; compare fatigue results at a higher rate."
                )
            write_ascii(staging / "reference.asc", original, rate)
        write_ascii(staging / "signal.asc", prepared, output_rate)
        diagnostics(staging, original, prepared, rate, output_rate, taps)
        report = {
            "schema_version": 1,
            "tool_version": __version__,
            "environment": {
                "python": platform.python_version(),
                **{p: version(p) for p in ("numpy", "scipy", "openpyxl", "matplotlib")},
            },
            "input": {"name": args.input.name, "sha256": sha256(args.input), **layout.describe()},
            "timing": timing_info,
            "transformations": {
                "units": "Input units converted to seconds and g using g0=9.80665 m/s2",
                "sensor_bias_subtracted_g": args.bias_g,
                "output_axes_from_sensor_axes": args.axis_map,
                "missing_values": "Rejected; no interpolation",
                "spikes": "No automatic detection or removal",
                "gravity": "No automatic subtraction or compensation",
                "filter": filter_info,
            },
            "output": {
                "sample_rate_hz": output_rate,
                "sample_count": len(prepared),
                "last_sample_time_s": (len(prepared) - 1) / output_rate,
                "channels": ["GX", "GY", "GZ"],
                "units": "g",
            },
            "statistics_input_in_g": statistics(data[:, 1:]),
            "statistics_full_rate_reference": statistics(original),
            "statistics_prepared": statistics(prepared),
            "warnings": warnings,
            "files": {p.name: sha256(p) for p in sorted(staging.glob("*.asc"))},
        }
        (staging / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (staging / "HANDOFF.md").write_text(handoff(report), encoding="utf-8")
        # TemporaryDirectory cleanup is harmless after the complete directory is moved.
        shutil.move(str(staging), str(args.out))
    print(f"Prepared {len(prepared):,} samples at {output_rate:.12g} Hz: {args.out / 'signal.asc'}")
    for warning in warnings:
        print(f"Review: {warning}")


def parser():
    root = argparse.ArgumentParser(description="Prepare synchronized X/Y/Z histories for fe-safe.")
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    for command in ("inspect", "prepare"):
        sub = commands.add_parser(command)
        sub.add_argument("input", type=Path)
        sub.add_argument("--mapping", type=Path, help="JSON layout override")
        sub.add_argument("--sheet")
        sub.add_argument("--header-row", type=int, help="1-based row within first 80 rows")
        sub.add_argument("--time-unit", choices=("s", "ms", "us"))
        sub.add_argument("--accel-unit", choices=("g", "m/s2", "mm/s2"))
        if command == "prepare":
            sub.add_argument("--out", type=Path, default=Path("results"))
            sub.add_argument("--end-row", type=int, help="Last worksheet row to include, 1-based")
            sub.add_argument("--sample-rate", type=float, help="Declared rate, verified against time")
            sub.add_argument("--target-rate", type=float, help="Optional integer-factor reduction")
            sub.add_argument("--passband-hz", type=float, help="Frequency band to preserve, from DC")
            sub.add_argument("--attenuation-db", type=float, default=80)
            sub.add_argument(
                "--timing-tolerance",
                type=float,
                default=0.02,
                help="Allowed grid/interval error in sample intervals (default 0.02)",
            )
            sub.add_argument(
                "--bias-g",
                nargs=3,
                type=float,
                default=[0, 0, 0],
                metavar=("X", "Y", "Z"),
                help="Known sensor bias to subtract, in g",
            )
            sub.add_argument("--axis-map", default="x,y,z", help="Output axis order/sign, e.g. x,-z,y")
    hash_parser = commands.add_parser("hash", help="SHA-256 of the final transferred file")
    hash_parser.add_argument("input", type=Path)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if not args.input.is_file():
            raise InputError(f"Input file not found: {args.input}")
        if args.command == "hash":
            print(sha256(args.input))
            return 0
        layout = discover(args.input, configuration(args))
        if args.command == "inspect":
            print(json.dumps(layout.describe(), indent=2))
            print("Layout preview only. Prepare validates the complete recording.")
        else:
            prepare(args, layout)
    except (InputError, OSError, json.JSONDecodeError) as exc:
        print(f"Cannot prepare input: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

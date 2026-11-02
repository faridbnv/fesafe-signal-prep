# Prepare Excel acceleration signals for fe safe

Convert a vehicle recording into three synchronized acceleration histories for
fe-safe. The tool checks the sheet, headers, units and timing, then writes
`signal.asc`. Open that file directly in fe-safe, or export its three channels as
one portable **AMC** file. The receiving fe-safe machine needs no Python or Excel.

**Keep the original sample rate for the first run.** The tool can recognize a table;
it cannot determine sensor orientation, gravity treatment, structural resonance or
a scientifically valid filter bandwidth from column values alone.

Read the [short engineering guide](docs/guide.md) for the math, plots, exact
fe-safe clicks and handover procedure.

## Install once

Use Python 3.11–3.14 on Windows, macOS or Linux. Clone or download this repository,
open a terminal in its folder, then run:

```sh
python setup_environment.py
```

Use `python3` instead of `python` where required. Setup installs the pinned packages
in a local `.venv`. Internet access is needed for installation, not for processing.
The environment is recreated on each machine; it is not copied through Git.
No fe-safe license is needed for preparation. fe-safe is required for AMC export.

Alternatively, with [uv](https://docs.astral.sh/uv/getting-started/installation/):

```sh
uv sync --frozen
uv run fesafe-signal --help
```

## Run

Start with the included **synthetic** workbook:

```sh
python run.py inspect examples/vehicle_example.xlsx
python run.py prepare examples/vehicle_example.xlsx --out results/example
```

Then use your own file, stored outside the repository or in the ignored `input/`
folder:

```sh
python run.py inspect "input/drive.xlsx"
python run.py prepare "input/drive.xlsx" --out results/drive_full
```

Inspection previews the layout. Preparation validates every selected data row.
Existing output folders are rejected to prevent accidental replacement.

Recommended Excel headers, with one numeric sample per row:

| time_s | accel_x_g | accel_y_g | accel_z_g | speed_mph | distance_miles |
|---:|---:|---:|---:|---:|---:|
| 0.000 | 0.02 | -0.01 | 1.005 | 30 | 0 |
| 0.001 | 0.03 | -0.02 | 1.010 | 30 | 0.00000833 |

Only time and three accelerations are required. Speed and distance are ignored as
load channels. Actual gravity content must be established separately.

The importer scans the first 50 rows of each sheet, handles leading title rows and
an optional separate units row, and recognizes common headers such as `Time (s)`,
`Acceleration X (g)`, `Ax (m/s²)` and `GX`. Supported units are s/ms/us and
g/m/s²/mm/s². `.xlsx`, `.xlsm`, UTF-8 CSV and TSV are supported. Macros are not run.
Recalculate Excel formulas and save first; only cached numeric results are read.
Legacy `.xls`, dates/clock strings, mixed-rate recordings and automatic joining of
multiple sheets are not supported.

When several sheets or columns match, choose them explicitly:

```sh
python run.py prepare "input/drive.xlsx" --sheet Road --header-row 4 --time-unit s --accel-unit g --out results/road
python run.py prepare "input/drive.xlsx" --mapping examples/mapping.json --out results/mapped
```

The [mapping example](examples/mapping.json) accepts exact header text or **1-based
column numbers**. Set `data_row` for nonstandard tables. `--end-row` excludes a known
footer. Unknown units, blanks within a recording, missing numbers, duplicate times,
time gaps and ambiguous mappings stop the run with a corrective message.

## Optional sample rate reduction

Only after the required bandwidth has been established, for example:

```sh
python run.py prepare "input/drive.xlsx" --target-rate 250 --passband-hz 20 --out results/drive_250
```

**These are example settings, not a recommendation for an unknown component.**
The tool preserves DC through 20 Hz within the verified filter amplitude tolerance,
suppresses content by at least 80 dB from 125 Hz, and retains every fourth filtered
sample. The transition lies between 20 and 125 Hz; this is not a sharp 20 Hz cutoff.
The same centered FIR filter is applied to all three channels. Only integer-factor
reductions are supported. Inspect boundary effects and compare fatigue results.

## Outputs

- `signal.asc`: complete, self-contained time histories with names, units and rate.
- `reference.asc`: full-rate reference after explicit axis/bias corrections, when reducing.
- `diagnostics.png`, `event.png`, optionally `filter.png`: quality-review plots.
- `report.json`: input/output hashes, mapping, timing, transformations and statistics.
- `HANDOFF.md`: engineering details to complete before releasing the final AMC.

No rows are silently repaired or deleted. Gravity, average load and spikes are
preserved. An explicitly known sensor bias can be subtracted with
`--bias-g 0.01 -0.02 0.005`. `--axis-map x,-z,y` maps sensor axes into output axes;
bias subtraction occurs first. Arbitrary rotations need a separate justified
transformation. The script does not infer these physical corrections.

Excel is read in streaming mode, then four numeric columns are loaded into arrays.
Processing is local and uses memory proportional to sample count; allow several
hundred MB for a million-row workbook. Plot envelopes retain within-bin extrema;
spectra are averaged diagnostics, not proof of fatigue equivalence.

## Development and verification

```sh
uv sync --frozen
uv run pytest
uv run ruff check .
```

See [validation and limits](docs/validation.md). Synthetic numerical tests check
conversion, synchronization, timing failures, anti-alias rejection and file syntax.
An actual fe-safe import/export must be checked with the supplied acceptance steps;
automated Python tests do not verify a proprietary application's behavior.

This independent utility is not affiliated with Dassault Systèmes. Original code,
text and figures are MIT licensed. Referenced vendor documentation is not included
or relicensed. The repository contains no measured vehicle data.

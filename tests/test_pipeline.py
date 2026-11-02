"""Independent numerical and integration checks for the measurement-to-ASCII boundary."""

import contextlib
import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import numpy as np
import pytest

from fesafe_signal.cli import axis_transform, main
from fesafe_signal.io import G0, InputError, discover, load_data, role_of, write_ascii
from fesafe_signal.processing import reduce_rate, timing

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "vehicle_example.xlsx"


def csv_input(tmp_path, header="time_s,accel_x_g,accel_y_g,accel_z_g", rows=None):
    path = tmp_path / "input.csv"
    if rows is None:
        rows = [f"{i / 1000},0.1,-0.2,1.0" for i in range(100)]
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def load(path, tmp_path, config=None):
    layout = discover(path, config)
    return load_data(path, layout, tmp_path / "numeric.bin"), layout


@pytest.mark.parametrize(
    "header,axis",
    [
        ("Acceleration X (g)", "x"),
        ("Ax (m/s²)", "x"),
        ("accel_y_g", "y"),
        ("GZ", "z"),
        ("Angular acceleration X (rad/s2)", None),
        ("speed_mph", None),
    ],
)
def test_role_recognition(header, axis):
    assert role_of(header) == axis


def test_real_excel_example(tmp_path):
    data, layout = load(EXAMPLE, tmp_path)
    assert layout.sheet == "Road"
    assert data.shape == (6001, 4)
    rate, _ = timing(data[:, 0])
    assert rate == pytest.approx(1000)
    t = data[:, 0]
    expected_x = 0.15 * np.sin(2 * np.pi * 3 * t) + 0.03 * np.sin(2 * np.pi * 180 * t)
    np.testing.assert_allclose(data[:, 1], expected_x, atol=1e-12)


def test_separate_units_and_title_rows(tmp_path):
    path = csv_input(
        tmp_path, "Synthetic test\nTime,X,Y,Z\nms,g,g,g", [f"{i},0.1,-0.2,1" for i in range(100)]
    )
    data, layout = load(path, tmp_path)
    assert (layout.header_row, layout.data_row) == (2, 4)
    assert data[1, 0] == pytest.approx(0.001)


def test_mixed_units(tmp_path):
    rows = [f"{i},{G0},{-2000 * G0},0.5" for i in range(100)]
    path = csv_input(tmp_path, "Time (ms),Ax (m/s²),Ay (mm/s²),Az (g)", rows)
    data, _ = load(path, tmp_path)
    np.testing.assert_allclose(data[:, 1:], np.tile([1, -2, 0.5], (100, 1)))
    assert data[-1, 0] == pytest.approx(0.099)


def test_explicit_nonstandard_mapping(tmp_path):
    path = csv_input(tmp_path, "T,Q,R,S")
    config = {
        "header_row": 1,
        "columns": {"time": "T", "x": "Q", "y": "R", "z": "S"},
        "time_unit": "s",
        "acceleration_units": ["g"] * 3,
    }
    data, _ = load(path, tmp_path, config)
    assert data.shape == (100, 4)


def test_unknown_units_rejected(tmp_path):
    path = csv_input(tmp_path, "Time,Acceleration X,Acceleration Y,Acceleration Z")
    with pytest.raises(InputError, match="Time units unknown"):
        load(path, tmp_path)


def test_duplicate_axis_rejected(tmp_path):
    path = csv_input(tmp_path, "time_s,Ax_g,Ay_g,Az_g,Acceleration X (g)")
    with pytest.raises(InputError, match="one usable"):
        discover(path)


@pytest.mark.parametrize("replacement", ["0.01,,0,1", "0.01,nan,0,1", "0.01,broken,0,1", ""])
def test_invalid_rows_are_not_silently_repaired(tmp_path, replacement):
    rows = [f"{i / 1000},0,0,1" for i in range(100)]
    rows[10] = replacement
    path = csv_input(tmp_path, rows=rows)
    with pytest.raises(InputError):
        load(path, tmp_path)


@pytest.mark.parametrize("mode", ["gap", "duplicate", "reverse", "jitter", "rounded"])
def test_timing_faults(mode):
    times = np.arange(1000) / 1000
    if mode == "gap":
        times[500:] += 0.001
    elif mode == "duplicate":
        times[500] = times[499]
    elif mode == "reverse":
        times = times[::-1]
    elif mode == "jitter":
        times[500] += 0.0001
    else:
        times = np.round(times, 2)
    with pytest.raises(InputError):
        timing(times)


def test_small_timestamp_jitter_is_reported():
    times = np.arange(1000) / 1000
    times[500] += 1e-6
    rate, info = timing(times)
    assert rate == pytest.approx(1000)
    assert info["max_grid_error_s"] == pytest.approx(1e-6)
    with pytest.raises(InputError):
        timing(times, declared_rate=500)


def test_filter_rejects_alias_and_preserves_gain_phase_and_dc():
    t = np.arange(20000) / 1000
    x = np.sin(2 * np.pi * 5 * t) + np.sin(2 * np.pi * 180 * t)
    original = np.column_stack([x, 2 * x, np.ones(len(t))])
    output, info, _ = reduce_rate(original, 1000, 250, 20)
    to = np.arange(len(output)) / 250
    interior = slice(500, -500)
    basis = np.column_stack(
        [
            np.sin(2 * np.pi * 5 * to[interior]),
            np.cos(2 * np.pi * 5 * to[interior]),
            np.sin(2 * np.pi * 70 * to[interior]),
            np.cos(2 * np.pi * 70 * to[interior]),
        ]
    )
    fit = np.linalg.lstsq(basis, output[interior, 0], rcond=None)[0]
    assert fit[0] == pytest.approx(1, abs=1e-4)
    assert abs(fit[1]) < 1e-6  # no phase delay in retained sine
    assert np.hypot(fit[2], fit[3]) < 1e-4  # 180 Hz would otherwise alias to 70 Hz
    np.testing.assert_allclose(output[:, 1], 2 * output[:, 0], atol=1e-12)
    np.testing.assert_allclose(output[:, 2], 1, atol=1e-12)
    assert info["measured_stopband_attenuation_db"] >= 80


@pytest.mark.parametrize("target,passband", [(1000, 20), (300, 20), (250, 125), (0, 20), (250, -1)])
def test_invalid_reductions(target, passband):
    with pytest.raises(InputError):
        reduce_rate(np.ones((2000, 3)), 1000, target, passband)


def test_axis_and_bias_order():
    values = np.array([[1.1, 2.2, 3.3]])
    np.testing.assert_allclose(axis_transform(values, "x,-z,y", [0.1, 0.2, 0.3]), [[1, -3, 2]])


def test_ascii_header_and_values(tmp_path):
    values = np.array([[0.1, -0.2, 1], [0.2, -0.3, 0.9]])
    path = tmp_path / "signal.asc"
    write_ascii(path, values, 250)
    lines = path.read_text().splitlines()
    assert lines[:6] == [
        "SafeTechnologyASCII",
        "250",
        "Time:Secs",
        "GX\tGY\tGZ",
        "Acceleration:g\tAcceleration:g\tAcceleration:g",
        "",
    ]
    np.testing.assert_allclose(np.loadtxt(path, skiprows=6), values)
    assert path.read_bytes().endswith(b"\n")


def test_cli_outputs_and_reference_are_consistent(tmp_path):
    destination = tmp_path / "result"
    assert (
        main(
            [
                "prepare",
                str(EXAMPLE),
                "--out",
                str(destination),
                "--target-rate",
                "250",
                "--passband-hz",
                "20",
            ]
        )
        == 0
    )
    report = json.loads((destination / "report.json").read_text())
    assert report["output"]["sample_count"] == 1501
    assert report["output"]["sample_rate_hz"] == 250
    assert (destination / "reference.asc").is_file()
    assert (destination / "HANDOFF.md").is_file()
    assert (destination / "diagnostics.png").stat().st_size > 10000
    assert main(["prepare", str(EXAMPLE), "--out", str(destination)]) == 2


def test_failed_preparation_leaves_no_output(tmp_path):
    path = csv_input(tmp_path, rows=[f"{i / 1000},0,0,1" for i in range(99)] + ["0.1,,0,1"])
    destination = tmp_path / "result"
    assert main(["prepare", str(path), "--out", str(destination)]) == 2
    assert not destination.exists()


def test_multiple_candidate_sheets_require_selection(monkeypatch, tmp_path):
    import fesafe_signal.io as reader

    table = [["time_s", "Ax_g", "Ay_g", "Az_g"], [0, 0, 0, 1]]

    @contextlib.contextmanager
    def two_sheets(_):
        yield {"Road1": iter(table), "Road2": iter(table)}

    monkeypatch.setattr(reader, "sheets", two_sheets)
    with pytest.raises(InputError, match="Road1.*Road2"):
        discover(tmp_path / "unused.xlsx")
    assert discover(tmp_path / "unused.xlsx", {"sheet": "Road2"}).sheet == "Road2"


def test_uncached_formula_cannot_truncate_excel_recording(tmp_path):
    path = tmp_path / "uncached.xlsx"
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(EXAMPLE) as source, zipfile.ZipFile(path, "w") as destination:
        for item in source.infolist():
            contents = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                tree = ET.fromstring(contents)
                for cell in tree.findall(".//s:row[@r='6002']/s:c", ns):
                    if cell.attrib["r"][0] in "ABCD":
                        for child in list(cell):
                            cell.remove(child)
                        cell.attrib.pop("t", None)
                        ET.SubElement(cell, f"{{{ns['s']}}}f").text = "1+1"
                    else:
                        for child in list(cell):
                            cell.remove(child)
                contents = ET.tostring(tree)
            destination.writestr(item, contents)
    with pytest.raises(InputError, match="formula has no cached"):
        load(path, tmp_path)

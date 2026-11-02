"""Timing validation and synchronized, explicitly requested sample-rate reduction."""

from __future__ import annotations

import hashlib
import math

import numpy as np
from scipy import signal

from .io import InputError


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def timing(times, tolerance=0.02, declared_rate=None):
    if not 0 <= tolerance <= 0.1:
        raise InputError("Timing tolerance must be between 0 and 0.1 sample intervals.")
    differences = np.diff(times)
    if np.any(differences <= 0):
        index = int(np.flatnonzero(differences <= 0)[0])
        raise InputError(f"Time must increase strictly: samples {index + 1} and {index + 2}.")
    interval = float((times[-1] - times[0]) / (len(times) - 1))
    rate = float(1 / interval)
    if declared_rate is not None:
        if not math.isfinite(declared_rate) or declared_rate <= 0:
            raise InputError("--sample-rate must be finite and positive.")
        rate = float(declared_rate)
        interval = 1 / rate
    else:
        # Round only numerical noise, e.g. 999.9999999999999 -> 1000.
        rate = float(f"{rate:.12g}")
        interval = 1 / rate
    grid = np.arange(len(times)) * interval
    phase_error = float(np.max(np.abs((times - times[0]) - grid)))
    interval_error = float(np.max(np.abs(differences - interval)))
    numerical_slack = max(1e-10 * interval, np.spacing(float(np.max(np.abs(times)))) * 8)
    if max(phase_error, interval_error) > tolerance * interval + numerical_slack:
        raise InputError(
            "Timing has gaps, jitter, rounding or rate changes beyond tolerance. "
            f"Maximum grid error {phase_error:.6g} s; interval error {interval_error:.6g} s. "
            "Restore valid timing or select a continuous uniformly sampled section. "
            "No rows were dropped, sorted or interpolated."
        )
    return rate, {
        "input_start_time_s": float(times[0]),
        "sample_rate_hz": rate,
        "sample_count": len(times),
        "last_sample_time_s": float(grid[-1]),
        "max_grid_error_s": phase_error,
        "max_interval_error_s": interval_error,
        "tolerance_in_sample_intervals": tolerance,
        "time_handling": "Original start stored here; accepted samples placed on a uniform grid at t=0.",
    }


def reduce_rate(values, rate, target, passband, attenuation=80):
    if not all(math.isfinite(v) for v in (rate, target, passband, attenuation)):
        raise InputError("Filter and sampling parameters must be finite.")
    ratio = rate / target if target > 0 else 0
    factor = round(ratio)
    if factor < 2 or not math.isclose(ratio, factor, rel_tol=1e-8):
        raise InputError(
            "Target must be a lower integer subdivision of the input rate "
            "(1000 -> 500, 250, 200, 100, ...). Upsampling is not provided."
        )
    if not 0 < passband < target / 2:
        raise InputError("Passband must be above zero and below the new Nyquist frequency.")
    if not 40 <= attenuation <= 140:
        raise InputError("Stopband attenuation must be between 40 and 140 dB.")
    stopband = target / 2
    width = (stopband - passband) / (rate / 2)
    # Extra design margin; verify the actual sampled frequency response below.
    taps_count, beta = signal.kaiserord(attenuation + 6, width)
    taps_count = max(5, taps_count | 1)
    if taps_count > 100001:
        raise InputError("Transition band is too narrow. Increase target rate or reduce passband.")
    taps = signal.firwin(taps_count, (passband + stopband) / 2, window=("kaiser", beta), fs=rate)
    freq, response = signal.freqz(taps, worN=max(65536, taps_count * 8), fs=rate)
    gain = np.abs(response)
    stop_gain = float(gain[freq >= stopband].max())
    pass_error = float(np.abs(gain[freq <= passband] - 1).max())
    limit = 10 ** (-attenuation / 20)
    if stop_gain > limit or pass_error > limit:
        raise InputError("Designed FIR did not meet the requested response. Use a wider transition.")
    if len(values) < taps_count * 4:
        raise InputError(f"Record too short for this filter: need at least {taps_count * 4} samples.")
    prepared = signal.resample_poly(values, 1, factor, axis=0, window=taps, padtype="line")
    description = {
        "method": "Symmetric Kaiser FIR, centered polyphase decimation, identical for X/Y/Z",
        "factor": factor,
        "target_sample_rate_hz": rate / factor,
        "passband_edge_hz": passband,
        "stopband_edge_hz": stopband,
        "requested_stopband_attenuation_db": attenuation,
        "measured_stopband_attenuation_db": float(-20 * np.log10(max(stop_gain, 1e-300))),
        "measured_max_passband_amplitude_error": pass_error,
        "fir_taps": taps_count,
        "boundary_extension": "linear continuation between record endpoints (SciPy padtype=line)",
        "boundary_affected_time_s_each_end": (taps_count - 1) / (2 * rate),
        "samples_per_passband_cycle": rate / factor / passband,
    }
    return prepared, description, taps


def statistics(values):
    result = {}
    for index, name in enumerate(("GX", "GY", "GZ")):
        channel = values[:, index]
        result[name] = {
            "min_g": float(np.min(channel)),
            "max_g": float(np.max(channel)),
            "mean_g": float(np.mean(channel)),
            "standard_deviation_g": float(np.std(channel)),
            "rms_g": float(np.sqrt(np.mean(channel**2))),
        }
    return result


def spectrum(values, rate):
    return signal.welch(values, rate, axis=0, nperseg=min(8192, len(values)))

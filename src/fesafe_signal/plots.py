"""Diagnostic plots, never fatigue qualification."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy import signal  # noqa: E402

from .processing import spectrum  # noqa: E402

COLORS = ("#2463a6", "#cf6a24", "#36805a")


def envelope(ax, values, rate, label, color, alpha=1):
    block = max(1, int(np.ceil(len(values) / 2500)))
    starts = np.arange(0, len(values), block)
    low = np.minimum.reduceat(values, starts)
    high = np.maximum.reduceat(values, starts)
    time = starts / rate
    ax.fill_between(time, low, high, color=color, alpha=0.2 * alpha)
    ax.plot(time, (low + high) / 2, color=color, lw=0.6, alpha=alpha, label=label)


def diagnostics(directory, original, prepared, rate, output_rate, taps=None):
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(3, 2, figsize=(11, 7), constrained_layout=True)
    for index, (name, color) in enumerate(zip(("GX", "GY", "GZ"), COLORS, strict=True)):
        envelope(axes[index, 0], original[:, index], rate, "Reference", "#777777", 0.8)
        envelope(axes[index, 0], prepared[:, index], output_rate, "Prepared", color)
        axes[index, 0].set(ylabel=f"{name} (g)", xlabel="Time (s)")
    f, psd = spectrum(original, rate)
    fo, psdo = spectrum(prepared, output_rate)
    for index, color in enumerate(COLORS):
        axes[index, 1].semilogy(f, np.maximum(psd[:, index], 1e-20), color="#777777")
        axes[index, 1].semilogy(fo, np.maximum(psdo[:, index], 1e-20), color=color)
        axes[index, 1].set(xlabel="Frequency (Hz)", ylabel="PSD (g²/Hz)")
    axes[0, 0].legend()
    fig.suptitle("Signal diagnostics - time envelope and averaged spectrum")
    fig.savefig(directory / "diagnostics.png", dpi=150)
    plt.close(fig)

    # Show a real interval around the largest three-axis excursion from its channel means.
    event = int(np.argmax(np.max(np.abs(original - np.mean(original, axis=0)), axis=1)))
    center = event / rate
    lo = max(0, center - 0.25)
    hi = min((len(original) - 1) / rate, center + 0.25)
    fig, axes = plt.subplots(3, 1, figsize=(10, 6), sharex=True, constrained_layout=True)
    for index, color in enumerate(COLORS):
        i, j = max(0, int(lo * rate)), min(len(original), int(hi * rate) + 1)
        a, b = max(0, int(lo * output_rate)), min(len(prepared), int(hi * output_rate) + 1)
        axes[index].plot(np.arange(i, j) / rate, original[i:j, index], color="#777777")
        axes[index].plot(np.arange(a, b) / output_rate, prepared[a:b, index], ".-", color=color)
        axes[index].set_ylabel(f"G{'XYZ'[index]} (g)")
    axes[-1].set_xlabel("Time (s)")
    fig.suptitle("Selected largest excursion - inspect shocks and retained peaks")
    fig.savefig(directory / "event.png", dpi=150)
    plt.close(fig)
    if taps is not None:
        f, h = signal.freqz(taps, worN=8192, fs=rate)
        fig, ax = plt.subplots(figsize=(9, 3.5), constrained_layout=True)
        ax.plot(f, 20 * np.log10(np.maximum(np.abs(h), 1e-10)), color=COLORS[0])
        ax.axvline(output_rate / 2, color="#aa3333", ls="--", label="New Nyquist frequency")
        ax.set(xlabel="Frequency (Hz)", ylabel="Amplitude gain (dB)", ylim=(-120, 2))
        ax.legend()
        fig.savefig(directory / "filter.png", dpi=150)
        plt.close(fig)

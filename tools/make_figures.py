"""Regenerate the guide's original, synthetic scientific figures."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from fesafe_signal.processing import reduce_rate  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "images"
OUT.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
blue, orange, green = "#2463a6", "#bf5c1b", "#36805a"

fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
dense = np.linspace(0, 1, 1001)
for ax, count in zip(axes[0], (4, 20), strict=True):
    ts = (np.arange(count) + 0.5) / count
    ax.plot(dense, np.sin(2 * np.pi * dense), color="#999999", label="True sine")
    ax.plot(ts, np.sin(2 * np.pi * ts), "o-", color=blue, label="Samples")
    ax.set(xlabel="Time (cycles)", ylabel="Amplitude", title=f"{count} samples per cycle")
    ax.legend(fontsize=9)

t = np.arange(8000) / 1000
high = np.sin(2 * np.pi * 180 * t)
tr = np.arange(2000) / 250
filtered, _, _ = reduce_rate(np.column_stack([high] * 3), 1000, 250, 20)
section = slice(250, 275)
axes[1, 0].plot(
    tr[section] - 1, high[::4][section], "o-", color=orange, label="Unfiltered reduction: false 70 Hz"
)
axes[1, 0].plot(
    tr[section] - 1, filtered[section, 0], ".-", color=green, label="Filtered reduction: suppressed"
)
axes[1, 0].set(xlabel="Time (s)", ylabel="Amplitude", title="180 Hz component sampled at 250 Hz")
axes[1, 0].legend(fontsize=8)

x = np.sin(2 * np.pi * 5 * t) + high
y, _, taps = reduce_rate(np.column_stack([x] * 3), 1000, 250, 20)
# An interior four-second interval avoids padding effects and has exact frequency bins.
for values, rate, label, color in [
    (x[2000:6000], 1000, "Original", "#777777"),
    (x[::4][500:1500], 250, "Reduction without filtering", orange),
    (y[500:1500, 0], 250, "Filtered reduction", green),
]:
    frequencies = np.fft.rfftfreq(len(values), 1 / rate)
    amplitude = 2 * np.abs(np.fft.rfft(values)) / len(values)
    axes[1, 1].semilogy(frequencies, np.maximum(amplitude, 1e-10), color=color, label=label)
axes[1, 1].set(
    xlabel="Frequency (Hz)",
    ylabel="Sine amplitude",
    ylim=(1e-6, 2),
    xlim=(0, 200),
    title="Retained 5 Hz and rejected 180 Hz",
)
axes[1, 1].legend(fontsize=8)
fig.suptitle("Sampling and anti-alias filtering - synthetic examples")
fig.savefig(OUT / "sampling.png", dpi=160)
plt.close(fig)

t = np.linspace(0, 2, 1001)
gx = 0.3 * np.sin(2 * np.pi * 2 * t)
gy = 0.2 * np.sin(2 * np.pi * 3 * t + 0.8)
gz = 1 + 0.1 * np.sin(2 * np.pi * 4 * t)
fig, axes = plt.subplots(2, 1, figsize=(10, 5), sharex=True, constrained_layout=True)
for data, name, color in zip((gx, gy, gz), ("GX", "GY", "GZ"), (blue, orange, green), strict=True):
    axes[0].plot(t, data, label=name, color=color)
axes[0].set_ylabel("Acceleration (g)")
axes[0].legend(ncol=3)
axes[0].set_title("Three channels share each time instant")
axes[1].plot(t, 40 * gx + 25 * gy + 10 * gz, color=blue)
axes[1].set(
    xlabel="Time (s)",
    ylabel="Normal stress (MPa)",
    title="One illustrative stress component: 40 GX + 25 GY + 10 GZ",
)
fig.savefig(OUT / "superposition.png", dpi=160)
plt.close(fig)

"""Adam Nimbus weight parsing and windowed mass-based flow estimation."""
from __future__ import annotations
from collections import deque
import math
import re

_MASS = re.compile(r"^\s*(?:(?:ST|US|S|U)\s*[, :]+)?(?:Net:\s*)?([+-]?\s*\d+(?:[.,]\d+)?)\s*(kg|mg|g)\s*$", re.IGNORECASE)


def parse_mass(line: str) -> float:
    # Nimbus custom forms use SOH/EOT framing and may label the net mass.
    # COMMA is a documented decimal separator, not a thousands separator.
    # Gross, tare and reference/report numbers must never become measured mass.
    match = _MASS.fullmatch(line.strip(" \t\r\n\x01\x04"))
    if not match:
        raise ValueError("Expected one balance reading with g, kg or mg units")
    value = float(re.sub(r"\s", "", match[1]).replace(",", "."))
    value *= {"g": 1.0, "kg": 1000.0, "mg": 0.001}[match[2].lower()]
    if not math.isfinite(value) or abs(value) > 1e7:
        raise ValueError("Balance reading is out of range")
    return value


class MassFlow:
    """Least-squares slope; never bridge a stale gap or a large tare event."""
    def __init__(self, window_s=15.0):
        self.window_s = window_s
        self.points = deque(maxlen=256)

    def reset(self):
        self.points.clear()

    def update(self, now, mass_g, density_g_ml):
        if self.points and (now <= self.points[-1][0] or now - self.points[-1][0] > 3.0
                            or mass_g < self.points[-1][1] - 2.0):
            self.reset()
        self.points.append((now, mass_g))
        while self.points and now - self.points[0][0] > self.window_s:
            self.points.popleft()
        if len(self.points) < 3 or now - self.points[0][0] < 2.0:
            return None
        times = [t - self.points[0][0] for t, _ in self.points]
        weights = [m for _, m in self.points]
        mean_t, mean_m = sum(times) / len(times), sum(weights) / len(weights)
        denominator = sum((t - mean_t) ** 2 for t in times)
        if denominator <= 0 or density_g_ml <= 0:
            return None
        slope = sum((t - mean_t) * (m - mean_m) for t, m in zip(times, weights)) / denominator
        return slope * 60.0 / density_g_ml

"""Deterministic statistical anomaly detection -- NO LLM call anywhere in
this module. This is the real, working logic behind `detect_anomaly_node`
(`app/graph/nodes.py`), combining three independent, genuinely useful
checks against a tag's recent historical window (loaded from Postgres by
`ingest_reading_node`):

1. **Fixed threshold breach** against the tag's configured normal/critical
   range (`sensor_tags.normal_min/normal_max/critical_min/critical_max`).
   This is the primary, most robust signal -- it fires as soon as a value
   crosses a known-bad line, regardless of what the recent rolling window
   looks like (which matters a lot for a slow drift: a rolling
   mean/std computed only from recent history can "chase" a slow drift and
   under-react to it, since the window's own baseline has already shifted).
2. **Z-score against the historical baseline** (rolling mean/std over the
   whole loaded history window) -- catches sudden, large deviations (a
   spike) that a fixed threshold might not yet have crossed, and
   contributes to the WARNING level for values trending away from normal
   but not yet threshold-breaching. Deliberately NOT used to escalate to
   CRITICAL on its own: a tag with naturally low variance (e.g. a tank
   pressure gauge) can otherwise produce an enormous z-score for a
   perfectly explainable, non-critical bump (see `T-101-PRESS`'s benign
   venting example in `sample-data/`).
3. **Stuck/flat-sensor detection**: if the standard deviation of the most
   recent handful of readings has collapsed to a small fraction of the
   tag's normal variability, the sensor is very likely frozen/stuck --
   this is checked independently of the numeric value, because a stuck
   sensor can freeze at a value that looks entirely plausible (see
   `P-401-VIB`'s injected anomaly and its accompanying manual/incident
   report in `sample-data/`).
4. **Rate-of-change** (smoothed over two adjacent 6-hour blocks, rather
   than a noisy single-point difference) -- an early-warning signal for a
   developing drift, contributing to WARNING before a fixed threshold is
   crossed.

Classification is intentionally structured so CRITICAL only ever comes from
a stuck sensor or an actual critical-threshold breach -- both hard,
unambiguous signals -- while WARNING can come from any of the softer
statistical signals. See `classify_reading()` below for the exact rule.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Literal

AnomalyLevel = Literal["normal", "warning", "critical"]

_STUCK_RELATIVE_THRESHOLD = 0.05  # recent std must collapse below 5% of baseline std
_STUCK_MIN_BASELINE_STD = 1e-6
_STUCK_WINDOW = 6  # most recent N history points + the current reading


@dataclass
class Reading:
    timestamp: str
    value: float


@dataclass
class AnomalyResult:
    classification: AnomalyLevel
    rolling_mean: float | None
    rolling_std: float | None
    z_score: float | None
    rate_per_hour: float | None
    stuck_detected: bool
    threshold_breach: str  # "none" | "warning_high" | "warning_low" | "critical_high" | "critical_low"
    history_window_size: int
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rolling_mean": self.rolling_mean,
            "rolling_std": self.rolling_std,
            "z_score": self.z_score,
            "rate_per_hour": self.rate_per_hour,
            "stuck_detected": self.stuck_detected,
            "threshold_breach": self.threshold_breach,
            "history_window_size": self.history_window_size,
            "reasons": self.reasons,
        }


def _threshold_breach(value: float, normal_min: float, normal_max: float, critical_min: float, critical_max: float) -> str:
    if value >= critical_max:
        return "critical_high"
    if value <= critical_min:
        return "critical_low"
    if value >= normal_max:
        return "warning_high"
    if value <= normal_min:
        return "warning_low"
    return "none"


_RATE_BLOCK_HOURS = 12


def _rate_per_hour(history_values: list[float]) -> float | None:
    """Smoothed rate of change: compare the mean of the most recent 12-hour
    block against the mean of the preceding 12-hour block, divided by the
    ~12-hour gap between block centers. Smoothing over blocks (rather than a
    raw point-to-point difference) suppresses false alarms from single-point
    sensor noise while still surfacing a genuine sustained drift -- a wider
    block also gives a better noise/signal ratio for a slow drift than a
    shorter one, at the cost of reacting slightly less quickly."""
    if len(history_values) < 2 * _RATE_BLOCK_HOURS:
        return None
    recent_block = history_values[-_RATE_BLOCK_HOURS:]
    prior_block = history_values[-2 * _RATE_BLOCK_HOURS : -_RATE_BLOCK_HOURS]
    recent_avg = statistics.fmean(recent_block)
    prior_avg = statistics.fmean(prior_block)
    return (recent_avg - prior_avg) / _RATE_BLOCK_HOURS


def classify_reading(
    *,
    current_value: float,
    history: list[Reading],
    normal_min: float,
    normal_max: float,
    critical_min: float,
    critical_max: float,
    warning_z: float,
    warning_rate_per_hour: float,
) -> AnomalyResult:
    """Classify a single reading as normal/warning/critical against its
    tag's recent historical window. See module docstring for the full
    rationale behind each signal and why they're combined this way."""
    history_values = [r.value for r in history]
    n = len(history_values)

    threshold_breach = _threshold_breach(current_value, normal_min, normal_max, critical_min, critical_max)

    if n < 2:
        # Not enough history yet to compute meaningful statistics -- fall
        # back to the threshold check alone.
        classification: AnomalyLevel = "critical" if threshold_breach.startswith("critical") else (
            "warning" if threshold_breach != "none" else "normal"
        )
        reasons = [f"insufficient history ({n} point(s)); threshold_breach={threshold_breach}"]
        return AnomalyResult(
            classification=classification,
            rolling_mean=None,
            rolling_std=None,
            z_score=None,
            rate_per_hour=None,
            stuck_detected=False,
            threshold_breach=threshold_breach,
            history_window_size=n,
            reasons=reasons,
        )

    rolling_mean = statistics.fmean(history_values)
    rolling_std = statistics.pstdev(history_values)

    if rolling_std > _STUCK_MIN_BASELINE_STD:
        z_score = (current_value - rolling_mean) / rolling_std
    else:
        z_score = 0.0

    rate_per_hour = _rate_per_hour(history_values)

    stuck_window = history_values[-_STUCK_WINDOW:] + [current_value]
    stuck_std = statistics.pstdev(stuck_window) if len(stuck_window) >= 2 else 0.0
    stuck_detected = (
        rolling_std > _STUCK_MIN_BASELINE_STD
        and stuck_std < max(_STUCK_RELATIVE_THRESHOLD * rolling_std, _STUCK_MIN_BASELINE_STD)
    )

    reasons: list[str] = []
    classification: AnomalyLevel

    if stuck_detected:
        classification = "critical"
        reasons.append(
            f"sensor appears stuck/flat: last {len(stuck_window)} readings have std={stuck_std:.4f}, "
            f"far below the tag's normal std={rolling_std:.4f}"
        )
    elif threshold_breach.startswith("critical"):
        classification = "critical"
        reasons.append(f"value {current_value} breaches critical threshold ({threshold_breach})")
    elif threshold_breach != "none":
        classification = "warning"
        reasons.append(f"value {current_value} breaches normal-range threshold ({threshold_breach})")
    elif abs(z_score) >= warning_z:
        classification = "warning"
        reasons.append(f"z-score {z_score:.2f} exceeds warning threshold {warning_z}")
    elif rate_per_hour is not None and abs(rate_per_hour) >= warning_rate_per_hour:
        classification = "warning"
        reasons.append(
            f"rate of change {rate_per_hour:.3f}/hr exceeds warning threshold {warning_rate_per_hour}/hr "
            "(early-warning sign of a developing drift)"
        )
    else:
        classification = "normal"
        reasons.append("within normal range, no statistically significant deviation, and no stuck-sensor signature")

    return AnomalyResult(
        classification=classification,
        rolling_mean=rolling_mean,
        rolling_std=rolling_std,
        z_score=z_score,
        rate_per_hour=rate_per_hour,
        stuck_detected=stuck_detected,
        threshold_breach=threshold_breach,
        history_window_size=n,
        reasons=reasons,
    )

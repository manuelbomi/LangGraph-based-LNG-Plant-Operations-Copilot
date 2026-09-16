"""Unit tests for the deterministic anomaly-detection logic
(`app/tools/anomaly_detection.py`). No LLM, no database, no mocks needed --
this module is pure statistics."""
from __future__ import annotations

from app.tools.anomaly_detection import Reading, classify_reading

_BASE_CFG = dict(
    normal_min=850.0,
    normal_max=930.0,
    critical_min=780.0,
    critical_max=960.0,
    warning_z=2.5,
    warning_rate_per_hour=0.35,
)


def _flat_history(value: float, n: int = 168, jitter: float = 0.0) -> list[Reading]:
    history = []
    for i in range(n):
        v = value + (jitter if i % 2 == 0 else -jitter)
        history.append(Reading(timestamp=f"2026-01-01T{i % 24:02d}:00:00+00:00", value=v))
    return history


def test_normal_reading_within_range_and_stable():
    history = _flat_history(905.0, jitter=2.0)
    result = classify_reading(current_value=906.0, history=history, **_BASE_CFG)
    assert result.classification == "normal"
    assert result.stuck_detected is False
    assert result.threshold_breach == "none"


def test_critical_threshold_breach():
    history = _flat_history(905.0, jitter=2.0)
    result = classify_reading(current_value=975.59, history=history, **_BASE_CFG)
    assert result.classification == "critical"
    assert result.threshold_breach == "critical_high"


def test_warning_threshold_breach_does_not_escalate_to_critical_via_zscore():
    """A tag with naturally low variance can produce a huge z-score for a
    value that's still only in the warning range -- this must NOT escalate
    to critical on z-score alone (see anomaly_detection.py's module
    docstring, point 2)."""
    history = _flat_history(14.0, jitter=1.0, n=168)
    cfg = dict(normal_min=8.0, normal_max=22.0, critical_min=3.0, critical_max=30.0, warning_z=2.5, warning_rate_per_hour=2.0)
    result = classify_reading(current_value=26.27, history=history, **cfg)
    assert result.classification == "warning"
    assert result.threshold_breach == "warning_high"
    assert result.z_score is not None and result.z_score > 5  # confirms this WOULD trip a naive z-based rule


def test_stuck_sensor_detected_even_within_normal_range():
    """A stuck sensor frozen at a plausible-looking value must still be
    flagged critical via the stuck-sensor check, even though the numeric
    value itself never breaches any threshold."""
    history = _flat_history(2.6, jitter=0.2, n=168)
    # Overwrite the most recent points with a frozen value.
    for i in range(-7, 0):
        history[i] = Reading(timestamp=history[i].timestamp, value=2.75)
    cfg = dict(normal_min=1.5, normal_max=4.0, critical_min=0.5, critical_max=5.5, warning_z=2.5, warning_rate_per_hour=0.1)
    result = classify_reading(current_value=2.75, history=history, **cfg)
    assert result.classification == "critical"
    assert result.stuck_detected is True
    assert result.threshold_breach == "none"


def test_slow_drift_eventually_breaches_warning_then_critical():
    # Build a history that ramps linearly from 905 to 950 (crossing the 930
    # normal_max partway through), then check a final drifted value.
    history = [Reading(timestamp=f"t{i}", value=905.0 + i * 0.4) for i in range(168)]
    final_value = 905.0 + 168 * 0.4  # continues the same ramp -> ~972.2
    result = classify_reading(current_value=final_value, history=history, **_BASE_CFG)
    assert result.classification == "critical"  # now above 960 critical_max
    assert result.threshold_breach == "critical_high"


def test_insufficient_history_falls_back_to_threshold_only():
    result = classify_reading(current_value=905.0, history=[], **_BASE_CFG)
    assert result.classification == "normal"
    assert result.rolling_mean is None

    result_breach = classify_reading(current_value=975.0, history=[], **_BASE_CFG)
    assert result_breach.classification == "critical"

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence


BASE_PCF = 0.57198191
BASE_SAFETY_SCORE_INTERCEPT = 122.15240383
BASE_SAFETY_SCORE_SLOPE = -38.72920381

LEGACY_INTERCEPT = 123.50230309
LEGACY_UNSAFE_FOLLOWING = 21.8  # percentage

CAPS = {
    "hard_braking": 5.2,
    "aggressive_turning": 13.2,
    "unsafe_following": 63.2,
    "excessive_speeding": 10.0,
    "late_night_driving": 14.2,
    "unbuckled_driving": 31.7,
}

MULTIPLIERS = {
    "hard_braking": 1.23599110,
    "aggressive_turning": 1.01219290,
    "unsafe_following": 1.00271921,
    "forced_autopilot_disengagement": 1.32343362,
    "late_night_driving": 1.03231810,
    "excessive_speeding": 1.02439511,
    "unbuckled_driving": 1.01151237,
}

FACTOR_ORDER = [
    ("hard_braking", "Hard Braking"),
    ("aggressive_turning", "Aggressive Turning"),
    ("unsafe_following", "Unsafe Following"),
    ("excessive_speeding", "Excessive Speeding"),
    ("late_night_driving", "Late-Night Driving"),
    ("unbuckled_driving", "Unbuckled Driving"),
    ("forced_autopilot_disengagement", "Forced ADAS Disengagement"),
]


def _normalize_percentage(value: float, cap: float) -> float:
    """Normalize percentage inputs (e.g. 5.2 for 5.2%) and apply caps."""
    if value < 0:
        raise ValueError("Safety factors cannot be negative.")

    return min(value, cap)


@dataclass(frozen=True)
class SafetyFactors:
    """Container for safety factors recorded over a driving period (percent values)."""

    hard_braking: float
    aggressive_turning: float
    unsafe_following: float
    excessive_speeding: float
    late_night_driving: float
    forced_autopilot_disengagement: int
    unbuckled_driving: float
    autopilot_hw_two_or_newer: bool = True

    def normalize(self) -> "SafetyFactors":
        """Return a version of the factors with normalized percentages."""
        data = {
            "hard_braking": _normalize_percentage(self.hard_braking, CAPS["hard_braking"]),
            "aggressive_turning": _normalize_percentage(
                self.aggressive_turning, CAPS["aggressive_turning"]
            ),
            "unsafe_following": _normalize_percentage(
                self.unsafe_following, CAPS["unsafe_following"]
            ),
            "excessive_speeding": _normalize_percentage(
                self.excessive_speeding, CAPS["excessive_speeding"]
            ),
            "late_night_driving": _normalize_percentage(
                self.late_night_driving, CAPS["late_night_driving"]
            ),
            "unbuckled_driving": _normalize_percentage(
                self.unbuckled_driving, CAPS["unbuckled_driving"]
            ),
            "forced_autopilot_disengagement": 1
            if self.forced_autopilot_disengagement
            else 0,
            "autopilot_hw_two_or_newer": self.autopilot_hw_two_or_newer,
        }
        return SafetyFactors(**data)  # type: ignore[arg-type]


def compute_pcf(factors: SafetyFactors) -> float:
    """Compute Predicted Collision Frequency for a single driving period."""
    normalized = factors.normalize()

    pcf = BASE_PCF
    pcf *= MULTIPLIERS["hard_braking"] ** normalized.hard_braking
    pcf *= MULTIPLIERS["aggressive_turning"] ** normalized.aggressive_turning

    if normalized.autopilot_hw_two_or_newer:
        unsafe_following = normalized.unsafe_following
    else:
        unsafe_following = _normalize_percentage(
            LEGACY_UNSAFE_FOLLOWING, CAPS["unsafe_following"]
        )

    pcf *= MULTIPLIERS["unsafe_following"] ** unsafe_following
    pcf *= MULTIPLIERS["forced_autopilot_disengagement"] ** (
        normalized.forced_autopilot_disengagement
    )
    pcf *= MULTIPLIERS["late_night_driving"] ** normalized.late_night_driving
    pcf *= MULTIPLIERS["excessive_speeding"] ** normalized.excessive_speeding
    pcf *= MULTIPLIERS["unbuckled_driving"] ** normalized.unbuckled_driving

    return pcf


def compute_safety_score(factors: SafetyFactors) -> float:
    """Compute the Tesla Safety Score for a single driving period."""
    normalized = factors.normalize()
    pcf = compute_pcf(factors)

    if normalized.autopilot_hw_two_or_newer:
        intercept = BASE_SAFETY_SCORE_INTERCEPT
    else:
        intercept = LEGACY_INTERCEPT

    safety_score = intercept + BASE_SAFETY_SCORE_SLOPE * pcf
    return max(0.0, min(100.0, safety_score))


def weighted_average(scores: Sequence[float], weights: Iterable[float]) -> float:
    """Compute a weighted average safety score."""
    weights_list = list(weights)
    if len(scores) != len(weights_list):
        raise ValueError("Scores and weights must have the same length.")

    total_weight = sum(weights_list)
    if total_weight == 0:
        raise ValueError("Sum of weights must be greater than zero.")

    return sum(score * weight for score, weight in zip(scores, weights_list)) / total_weight


def _score_from_pcf(pcf: float, autopilot_hw_two_or_newer: bool) -> float:
    intercept = BASE_SAFETY_SCORE_INTERCEPT if autopilot_hw_two_or_newer else LEGACY_INTERCEPT
    return max(0.0, min(100.0, intercept + BASE_SAFETY_SCORE_SLOPE * pcf))


def _baseline_factors(autopilot_hw_two_or_newer: bool) -> SafetyFactors:
    return SafetyFactors(
        hard_braking=0.0,
        aggressive_turning=0.0,
        unsafe_following=0.0,
        excessive_speeding=0.0,
        late_night_driving=0.0,
        forced_autopilot_disengagement=0,
        unbuckled_driving=0.0,
        autopilot_hw_two_or_newer=autopilot_hw_two_or_newer,
    )


def _get_factor_exponent(factors: SafetyFactors, key: str) -> float:
    if key == "forced_autopilot_disengagement":
        return float(factors.forced_autopilot_disengagement)
    if key == "unsafe_following" and not factors.autopilot_hw_two_or_newer:
        return 0.0
    return float(getattr(factors, key))


def score_breakdown(factors: SafetyFactors) -> Dict[str, object]:
    """Return a breakdown of score penalties contributed by each factor."""
    normalized = factors.normalize()
    base_factors = _baseline_factors(normalized.autopilot_hw_two_or_newer)

    base_pcf = compute_pcf(base_factors)
    current_pcf = compute_pcf(normalized)

    base_score = _score_from_pcf(base_pcf, normalized.autopilot_hw_two_or_newer)
    current_score = _score_from_pcf(current_pcf, normalized.autopilot_hw_two_or_newer)

    pcf_running = base_pcf
    score_running = base_score
    segments: List[Dict[str, float | str]] = []

    for key, label in FACTOR_ORDER:
        exponent = _get_factor_exponent(normalized, key)
        if exponent <= 0:
            continue

        previous_score = score_running
        pcf_running *= MULTIPLIERS[key] ** exponent
        score_running = _score_from_pcf(pcf_running, normalized.autopilot_hw_two_or_newer)

        penalty = max(0.0, previous_score - score_running)
        if penalty <= 0.0:
            continue

        segments.append(
            {
                "key": key,
                "label": label,
                "penalty": penalty,
                "value": exponent,
            }
        )

    total_penalty = max(0.0, base_score - current_score)

    if segments:
        residual = total_penalty - sum(segment["penalty"] for segment in segments)
        if abs(residual) > 1e-6:
            segments[-1]["penalty"] += residual

    return {
        "base_score": base_score,
        "current_score": current_score,
        "total_penalty": total_penalty,
        "segments": segments,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute a Tesla-style Safety Score based on safety factors."
    )
    parser.add_argument(
        "--hard-braking",
        type=float,
        required=True,
        help="Hard braking percentage (cap 5.2).",
    )
    parser.add_argument(
        "--aggressive-turning",
        type=float,
        required=True,
        help="Aggressive turning percentage (cap 13.2).",
    )
    parser.add_argument(
        "--unsafe-following",
        type=float,
        required=True,
        help="Unsafe following percentage (cap 63.2).",
    )
    parser.add_argument(
        "--excessive-speeding",
        type=float,
        required=True,
        help="Excessive speeding percentage (cap 10.0).",
    )
    parser.add_argument(
        "--late-night-driving",
        type=float,
        required=True,
        help="Late-night driving percentage (cap 14.2).",
    )
    parser.add_argument(
        "--forced-autopilot-disengagement",
        type=int,
        choices=(0, 1),
        required=True,
    )
    parser.add_argument(
        "--unbuckled-driving",
        type=float,
        required=True,
        help="Unbuckled driving percentage (cap 31.7).",
    )
    parser.add_argument(
        "--legacy-autopilot",
        action="store_true",
        help="Set if the vehicle has ADAS hardware older than version 2.0.",
    )
    parser.add_argument(
        "--miles",
        type=float,
        default=1.0,
        help="Miles driven with ADAS disengaged. Used when aggregating scores.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    factors = SafetyFactors(
        hard_braking=args.hard_braking,
        aggressive_turning=args.aggressive_turning,
        unsafe_following=args.unsafe_following,
        excessive_speeding=args.excessive_speeding,
        late_night_driving=args.late_night_driving,
        forced_autopilot_disengagement=args.forced_autopilot_disengagement,
        unbuckled_driving=args.unbuckled_driving,
        autopilot_hw_two_or_newer=not args.legacy_autopilot,
    )

    pcf = compute_pcf(factors)
    safety_score = compute_safety_score(factors)

    print(f"Predicted Collision Frequency (per million miles): {pcf:.6f}")
    print(f"Safety Score: {safety_score:.2f}")
    print(f"Miles driven (weight): {args.miles:.2f}")


if __name__ == "__main__":
    main()


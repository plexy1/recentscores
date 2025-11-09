from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any, Dict, Optional

from flask import Flask, render_template_string, request

from safety_score import CAPS, SafetyFactors, compute_pcf, compute_safety_score, score_breakdown

app = Flask(__name__)

SEGMENT_COLORS = {
    "hard_braking": "#ef4444",
    "aggressive_turning": "#f97316",
    "unsafe_following": "#eab308",
    "excessive_speeding": "#38bdf8",
    "late_night_driving": "#a855f7",
    "unbuckled_driving": "#f43f5e",
    "forced_autopilot_disengagement": "#0ea5e9",
}

FACTOR_HINTS = {
    "hard_braking": "Ease off the pedal early—coasting reduces hard stops above 0.3g.",
    "aggressive_turning": "Smooth steering inputs prevent lateral spikes above 0.4g.",
    "unsafe_following": "Leave a larger gap at 50+ mph to protect your reaction time.",
    "excessive_speeding": "Staying below 85 mph keeps this penalty at zero.",
    "late_night_driving": "Plan trips outside 11 PM–4 AM to avoid higher risk periods.",
    "unbuckled_driving": "Buckle before leaving park to eliminate this deduction.",
}

FORM_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Safety Score Calculator</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        :root {
            color-scheme: light dark;
        }
        body {
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            margin: 0;
            padding: 1.5rem;
            background-color: #f4f5f7;
        }
        .wrapper {
            max-width: 960px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            padding: 2rem;
            box-shadow: 0 1rem 2rem rgba(15, 23, 42, 0.1);
        }
        h1 {
            margin-top: 0;
            text-align: center;
        }
        form {
            display: grid;
            gap: 1.25rem;
        }
        .grid {
            display: grid;
            gap: 1rem;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        }
        label {
            display: block;
            font-weight: 600;
            margin-bottom: 0.25rem;
        }
        .input-field {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }
        .slider-row {
            display: flex;
            gap: 0.75rem;
            align-items: center;
        }
        .slider-row input[type="range"] {
            flex: 1;
            accent-color: #2563eb;
        }
        .slider-row input[type="number"] {
            width: 92px;
            padding: 0.6rem 0.75rem;
            border: 1px solid #cbd5f5;
            border-radius: 8px;
            font-size: 1rem;
        }
        input[type="number"],
        select {
            width: 100%;
            padding: 0.6rem 0.75rem;
            border: 1px solid #cbd5f5;
            border-radius: 8px;
            font-size: 1rem;
        }
        .checkbox {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        .actions {
            display: flex;
            gap: 1rem;
            justify-content: center;
            flex-wrap: wrap;
        }
        button {
            background-color: #2563eb;
            color: white;
            padding: 0.75rem 1.5rem;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
        }
        button.secondary {
            background-color: #e5e7eb;
            color: #111827;
        }
        .result-card {
            border-radius: 12px;
            padding: 1.5rem;
            background: linear-gradient(120deg, #ede9fe, #eff6ff);
            border: 1px solid rgba(79, 70, 229, 0.2);
        }
        .result-grid {
            display: grid;
            gap: 1rem;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        }
        .result-value {
            font-size: 2rem;
            font-weight: 700;
        }
        .error {
            padding: 1rem;
            border-radius: 8px;
            background-color: #fee2e2;
            color: #991b1b;
            border: 1px solid #fecaca;
        }
        small {
            display: block;
            color: #475569;
            margin-top: 0.25rem;
        }
        .score-breakdown {
            margin-top: 2rem;
        }
        .score-breakdown h3 {
            margin: 0 0 1rem;
            font-size: 1.25rem;
        }
        .score-bar {
            position: relative;
            display: flex;
            width: 100%;
            height: 44px;
            border-radius: 999px;
            overflow: hidden;
            background: linear-gradient(120deg, #f8fafc, #e2e8f0);
            border: 1px solid rgba(100, 116, 139, 0.25);
            box-shadow: inset 0 1px 3px rgba(148, 163, 184, 0.35);
        }
        .score-fill {
            flex: 0 0 auto;
            display: flex;
            align-items: center;
            justify-content: flex-end;
            padding: 0 1.25rem 0 1rem;
            box-sizing: border-box;
            font-weight: 700;
            color: white;
            background: linear-gradient(135deg, #22c55e, #16a34a);
            border-right: 1px solid rgba(20, 83, 45, 0.3);
            flex-basis: 0%;
            opacity: 0;
            transition: flex-basis 900ms ease, opacity 900ms ease;
        }
        .score-bar.ready .score-fill {
            flex-basis: calc(var(--score-width) * 1%);
            opacity: 1;
        }
        .penalty-space {
            flex: 1 1 auto;
            display: flex;
            flex-direction: row;
        }
        .penalty-segment {
            position: relative;
            flex: 0 0 auto;
            min-width: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 600;
            font-size: 0.78rem;
            text-shadow: 0 1px 2px rgba(15, 23, 42, 0.45);
            opacity: 0;
            flex-basis: 0%;
            transition: flex-basis 900ms ease, opacity 900ms ease, box-shadow 200ms ease;
            cursor: pointer;
            outline: none;
        }
        .penalty-segment span {
            position: absolute;
            bottom: calc(100% + 12px);
            left: 50%;
            transform: translate(-50%, 10px);
            padding: 0.5rem 0.75rem;
            background-color: rgba(15, 23, 42, 0.95);
            color: #f8fafc;
            border-radius: 8px;
            white-space: nowrap;
            opacity: 0;
            pointer-events: none;
            transition: opacity 180ms ease, transform 180ms ease;
            box-shadow: 0 8px 16px rgba(15, 23, 42, 0.35);
            font-size: 0.72rem;
            letter-spacing: 0.01em;
        }
        .penalty-segment span::after {
            content: "";
            position: absolute;
            top: 100%;
            left: 50%;
            transform: translateX(-50%);
            border-width: 6px;
            border-style: solid;
            border-color: rgba(15, 23, 42, 0.95) transparent transparent transparent;
        }
        .penalty-segment:hover span,
        .penalty-segment:focus-visible span,
        .penalty-segment.active span {
            opacity: 1;
            transform: translate(-50%, 0);
        }
        .penalty-segment:focus-visible,
        .penalty-segment.active {
            box-shadow: inset 0 0 0 3px rgba(255, 255, 255, 0.55);
        }
        .score-bar.ready .penalty-segment {
            flex-basis: calc(var(--segment-width) * 1%);
            opacity: 1;
        }
        .penalty-list {
            margin: 1.5rem 0 0;
            padding: 0;
            list-style: none;
            display: grid;
            gap: 0.75rem;
        }
        .penalty-list li {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.75rem 1rem;
            border-radius: 10px;
            background-color: rgba(226, 232, 240, 0.5);
            border: 1px solid rgba(148, 163, 184, 0.2);
            transition: border-color 180ms ease, box-shadow 180ms ease, background-color 180ms ease;
        }
        .penalty-list .dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }
        .penalty-list .label {
            flex: 1;
            font-weight: 600;
            color: #1f2937;
        }
        .penalty-list .delta {
            font-variant-numeric: tabular-nums;
            color: #0f172a;
        }
        .penalty-list li.active {
            border-color: rgba(37, 99, 235, 0.55);
            background-color: rgba(191, 219, 254, 0.45);
            box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.2);
        }
    </style>
</head>
<body>
    <div class="wrapper">
        <h1>Safety Score Calculator</h1>
        <p style="text-align:center; color:#475569;">Safety factor percentages captured by vehicle sensors feed this model to estimate overall risk and collision likelihood.</p>
        {% if error %}
            <div class="error">{{ error }}</div>
        {% endif %}
        <form method="post">
            <div class="grid">
                {% for key, value in factor_map.items() %}
                    {% if key not in ["forced_autopilot_disengagement", "autopilot_hw_two_or_newer"] %}
                        <div class="input-field">
                            <label for="{{ key }}_slider">{{ field_labels[key] }}</label>
                            <div class="slider-row">
                                <input
                                    type="range"
                                    id="{{ key }}_slider"
                                    class="slider-input"
                                    name="{{ key }}"
                                    min="0"
                                    max="{{ caps[key] | round(2) }}"
                                    step="0.01"
                                    value="{{ value | round(3) }}"
                                    data-number-input="{{ key }}_number"
                                >
                                <input
                                    type="number"
                                    id="{{ key }}_number"
                                    class="numeric-input"
                                    step="0.01"
                                    min="0"
                                    max="100"
                                    value="{{ value | round(3) }}"
                                    aria-label="{{ field_labels[key] }} precise value"
                                >
                            </div>
                            <small>Cap: {{ caps[key] | round(2) }}%</small>
                        </div>
                    {% endif %}
                {% endfor %}
                <div>
                    <label for="forced_autopilot_disengagement">Forced ADAS Disengagement</label>
                    <select id="forced_autopilot_disengagement" name="forced_autopilot_disengagement">
                        <option value="0" {% if not factor_map['forced_autopilot_disengagement'] %}selected{% endif %}>No</option>
                        <option value="1" {% if factor_map['forced_autopilot_disengagement'] %}selected{% endif %}>Yes</option>
                    </select>
                    <small>Set to "Yes" if ADAS was forcibly disengaged during the trip.</small>
                </div>
                <div class="checkbox">
                    <input
                        type="checkbox"
                        id="legacy_autopilot"
                        name="legacy_autopilot"
                        value="1"
                        {% if not factor_map['autopilot_hw_two_or_newer'] %}checked{% endif %}
                    >
                    <label for="legacy_autopilot">Vehicle uses ADAS hardware older than 2.0</label>
                </div>
            </div>
            <div class="actions">
                <button type="submit">Calculate Safety Score</button>
                <button type="reset" class="secondary">Reset</button>
            </div>
        </form>

        {% if results %}
            <div style="margin-top:2rem;">
                <div class="result-card">
                    <h2>Results</h2>
                    <div class="result-grid">
                        <div>
                            <p>Predicted Collision Frequency</p>
                            <div class="result-value">{{ results.pcf | round(6) }}</div>
                            <small>Collisions per million miles</small>
                        </div>
                        <div>
                            <p>Safety Score</p>
                            <div class="result-value">{{ results.safety_score | round(2) }}</div>
                            <small>Scaled 0 - 100</small>
                        </div>
                    </div>
                    {% if results.breakdown %}
                        <div class="score-breakdown">
                            <h3>Score Impact</h3>
                            <div class="score-bar" data-score="{{ results.breakdown.current_score|round(2) }}" style="--score-width: {{ results.breakdown.current_score }}">
                                <div class="score-fill">
                                    {{ results.breakdown.current_score | round(2) }}
                                </div>
                                <div class="penalty-space">
                                    {% if results.breakdown.total_penalty <= 0.01 %}
                                        <div class="penalty-segment" style="--segment-width: 0; background-color: transparent; color:#0f172a;">
                                            <span>Perfect Score</span>
                                        </div>
                                    {% else %}
                                        {% for segment in results.breakdown.segments %}
                                            <div
                                                class="penalty-segment"
                                                style="--segment-width: {{ segment.penalty }}; background-color: {{ segment.color }};"
                                                data-key="{{ segment.key }}"
                                                tabindex="0"
                                                role="button"
                                                aria-pressed="false"
                                                aria-label="{{ segment.label }} penalty segment"
                                            >
                                                <span>{{ segment.label }}</span>
                                            </div>
                                        {% endfor %}
                                    {% endif %}
                                </div>
                            </div>
                            {% if results.breakdown.segments %}
                                <ul class="penalty-list">
                                    {% for segment in results.breakdown.segments %}
                                        <li data-key="{{ segment.key }}">
                                            <span class="dot" style="background-color: {{ segment.color }};"></span>
                                            <span class="label">{{ segment.label }}</span>
                                            <span class="delta">-{{ segment.penalty | round(2) }} pts</span>
                                            <span class="delta" style="color:#475569;">Input: {{ segment.value | round(3) }}%</span>
                                        </li>
                                    {% endfor %}
                                </ul>
                            {% endif %}
                        </div>
                    {% endif %}
                </div>
            </div>
        {% endif %}
    </div>
    <script>
        document.addEventListener("DOMContentLoaded", () => {
            const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
            let clearPenaltyActive = () => {};

            const syncInputs = () => {
                document.querySelectorAll(".slider-input").forEach((slider) => {
                    if (slider.dataset.bound === "true") {
                        return;
                    }
                    slider.dataset.bound = "true";

                    const numberId = slider.dataset.numberInput;
                    const number = numberId ? document.getElementById(numberId) : null;
                    const min = Number.parseFloat(slider.min || "0") || 0;
                    const max = Number.parseFloat(slider.max || "100") || 100;

                    const formatNumber = (val) => {
                        const numeric = Number.parseFloat(val);
                        if (Number.isNaN(numeric)) {
                            return slider.value;
                        }
                        return numeric.toFixed(2).replace(/\.?0+$/, "");
                    };

                    const syncFromSlider = () => {
                        if (!number) {
                            return;
                        }
                        number.value = formatNumber(slider.value);
                    };

                    const syncFromNumber = (commit = false) => {
                        if (!number) {
                            return;
                        }
                        const parsed = Number.parseFloat(number.value);
                        if (Number.isNaN(parsed)) {
                            if (commit) {
                                slider.value = min.toString();
                                number.value = formatNumber(min);
                            }
                            return;
                        }
                        const clamped = clamp(parsed, min, max);
                        slider.value = clamped.toString();
                        if (commit) {
                            number.value = formatNumber(clamped);
                        }
                    };

                    slider.addEventListener("input", syncFromSlider);

                    if (number) {
                        number.addEventListener("input", () => syncFromNumber(false));
                        ["change", "blur"].forEach((eventName) => {
                            number.addEventListener(eventName, () => syncFromNumber(true));
                        });
                    }

                    syncFromSlider();
                });
            };

            const initPenaltyInteractions = () => {
                const segments = Array.from(document.querySelectorAll(".penalty-segment[data-key]"));
                const listItems = new Map();

                Array.from(document.querySelectorAll(".penalty-list li[data-key]")).forEach((item) => {
                    const key = item.dataset.key;
                    if (!key) {
                        return;
                    }
                    listItems.set(key, item);
                    item.tabIndex = 0;
                    item.setAttribute("role", "button");
                    item.setAttribute("aria-pressed", "false");
                });

                if (!segments.length) {
                    clearPenaltyActive = () => {};
                    return;
                }

                let activeKey = null;

                const setActive = (key) => {
                    activeKey = key;
                    segments.forEach((segment) => {
                        const isMatch = segment.dataset.key === key && key !== null;
                        segment.classList.toggle("active", isMatch);
                        segment.setAttribute("aria-pressed", isMatch ? "true" : "false");
                    });
                    listItems.forEach((item, itemKey) => {
                        const isMatch = itemKey === key;
                        item.classList.toggle("active", isMatch);
                        item.setAttribute("aria-pressed", isMatch ? "true" : "false");
                        if (isMatch) {
                            item.scrollIntoView({ behavior: "smooth", block: "nearest" });
                        }
                    });
                };

                const toggleKey = (key) => {
                    if (!key) {
                        setActive(null);
                        return;
                    }
                    setActive(activeKey === key ? null : key);
                };

                segments.forEach((segment) => {
                    const key = segment.dataset.key;
                    if (!key) {
                        return;
                    }
                    segment.addEventListener("click", () => {
                        toggleKey(key);
                    });
                    segment.addEventListener("keydown", (event) => {
                        if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            toggleKey(key);
                        }
                    });
                });

                listItems.forEach((item, key) => {
                    item.addEventListener("click", () => {
                        toggleKey(key);
                    });
                    item.addEventListener("keydown", (event) => {
                        if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            toggleKey(key);
                        }
                    });
                });

                setActive(null);
                clearPenaltyActive = () => setActive(null);
            };

            window.requestAnimationFrame(() => {
                document.querySelectorAll(".score-bar").forEach((bar) => {
                    bar.classList.add("ready");
                });
            });

            syncInputs();
            initPenaltyInteractions();

            document.querySelectorAll("form").forEach((form) => {
                form.addEventListener("reset", () => {
                    window.requestAnimationFrame(() => {
                        form.querySelectorAll(".slider-input").forEach((slider) => {
                            const resetValue = slider.min ?? "0";
                            slider.value = resetValue;
                            slider.dataset.bound = "false";

                            const numberId = slider.dataset.numberInput;
                            const number =
                                numberId ? document.getElementById(numberId) : null;
                            if (number) {
                                number.value = resetValue;
                            }
                        });
                        const forcedSelect = form.querySelector("#forced_autopilot_disengagement");
                        if (forcedSelect) {
                            forcedSelect.value = "0";
                        }
                        const legacyCheckbox = form.querySelector("#legacy_autopilot");
                        if (legacyCheckbox) {
                            legacyCheckbox.checked = false;
                        }
                        syncInputs();
                        clearPenaltyActive();
                    });
                });
            });
        });
    </script>
</body>
</html>
"""

FIELD_LABELS = {
    "hard_braking": "Hard Braking (%)",
    "aggressive_turning": "Aggressive Turning (%)",
    "unsafe_following": "Unsafe Following (%)",
    "excessive_speeding": "Excessive Speeding (%)",
    "late_night_driving": "Late-Night Driving (%)",
    "unbuckled_driving": "Unbuckled Driving (%)",
}


def _parse_percentage(value: str, cap_key: str) -> float:
    """Convert a percentage string into a capped value."""
    if value == "":
        return 0.0
    try:
        numeric_value = float(value)
    except ValueError as exc:
        raise ValueError(f"'{value}' is not a valid number.") from exc
    if math.isnan(numeric_value) or math.isinf(numeric_value):
        raise ValueError(f"'{value}' must be a finite number.")
    if numeric_value < 0:
        raise ValueError("Values cannot be negative.")
    return min(numeric_value, CAPS[cap_key])


def _parse_form_data(form: Dict[str, Any]) -> SafetyFactors:
    """Parse the incoming form data into SafetyFactors."""
    hard_braking = _parse_percentage(form.get("hard_braking", "0"), "hard_braking")
    aggressive_turning = _parse_percentage(
        form.get("aggressive_turning", "0"), "aggressive_turning"
    )
    unsafe_following = _parse_percentage(
        form.get("unsafe_following", "0"), "unsafe_following"
    )
    excessive_speeding = _parse_percentage(
        form.get("excessive_speeding", "0"), "excessive_speeding"
    )
    late_night_driving = _parse_percentage(
        form.get("late_night_driving", "0"), "late_night_driving"
    )
    forced_autopilot_disengagement = int(form.get("forced_autopilot_disengagement", 0))
    unbuckled_driving = _parse_percentage(
        form.get("unbuckled_driving", "0"), "unbuckled_driving"
    )
    legacy_autopilot = form.get("legacy_autopilot") == "1"

    return SafetyFactors(
        hard_braking=hard_braking,
        aggressive_turning=aggressive_turning,
        unsafe_following=unsafe_following,
        excessive_speeding=excessive_speeding,
        late_night_driving=late_night_driving,
        forced_autopilot_disengagement=forced_autopilot_disengagement,
        unbuckled_driving=unbuckled_driving,
        autopilot_hw_two_or_newer=not legacy_autopilot,
    ).normalize()


def render_page(
    factors: SafetyFactors,
    results: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
):
    context = {
        "factors": factors,
        "factor_map": asdict(factors),
        "results": results,
        "error": error,
        "caps": CAPS,
        "field_labels": FIELD_LABELS,
    }
    return render_template_string(FORM_TEMPLATE, **context)


@app.route("/", methods=["GET", "POST"])
def index():
    factors = SafetyFactors(
        hard_braking=0.0,
        aggressive_turning=0.0,
        unsafe_following=0.0,
        excessive_speeding=0.0,
        late_night_driving=0.0,
        forced_autopilot_disengagement=0,
        unbuckled_driving=0.0,
        autopilot_hw_two_or_newer=True,
    )

    if request.method == "POST":
        try:
            factors = _parse_form_data(request.form)
            pcf = compute_pcf(factors)
            safety_score = compute_safety_score(factors)
            breakdown = score_breakdown(factors)
            if breakdown["segments"]:
                for segment in breakdown["segments"]:
                    segment["color"] = SEGMENT_COLORS.get(segment["key"], "#64748b")
            results = {
                "pcf": pcf,
                "safety_score": safety_score,
                "breakdown": breakdown,
            }
            return render_page(
                factors,
                results=results,
            )
        except ValueError as exc:
            return render_page(factors, error=str(exc))

    return render_page(factors)


if __name__ == "__main__":
    app.run(debug=True)


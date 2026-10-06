"""Governed descriptive reliever role-movement classification.

V1 compares two adjacent seven-calendar-day deployment windows. It describes
completed usage only. It does not infer manager intent, future availability,
health, quality, or a depth-chart job.
"""

MIN_APPEARANCES_PER_WINDOW = 3
SHARE_SHIFT_MIN = 0.50

CONTRACT = "observed_role_movement_v1"
METHOD_VERSION = "observed_role_movement_v1"


def _share(count, known):
    if type(count) is not int or type(known) is not int or known <= 0 or count < 0 or count > known:
        return None
    return count / known


def _signal(name, recent_count, recent_known, prior_count, prior_known):
    recent = _share(recent_count, recent_known)
    prior = _share(prior_count, prior_known)
    if recent is None or prior is None:
        return {
            "name": name,
            "status": "unavailable",
            "reason_code": "insufficient_known_evidence",
        }

    delta = recent - prior
    if delta >= SHARE_SHIFT_MIN:
        direction = "higher"
    elif delta <= -SHARE_SHIFT_MIN:
        direction = "lower"
    else:
        direction = "stable"

    return {
        "name": name,
        "status": "complete",
        "direction": direction,
        "recent_share": round(recent, 4),
        "prior_share": round(prior, 4),
        "share_delta": round(delta, 4),
    }


def classify_observed_role_movement(*, recent, prior):
    """Classify movement from already-authoritative deployment counts.

    Required input shape per window:
      appearances
      eighth_or_later_appearances
      known_entry_appearances
      high_leverage_appearances
      known_leverage_appearances
    """
    recent_apps = recent.get("appearances")
    prior_apps = prior.get("appearances")
    if (
        type(recent_apps) is not int
        or type(prior_apps) is not int
        or recent_apps < MIN_APPEARANCES_PER_WINDOW
        or prior_apps < MIN_APPEARANCES_PER_WINDOW
    ):
        return {
            "contract": CONTRACT,
            "method_version": METHOD_VERSION,
            "status": "unavailable",
            "reason_code": "insufficient_appearances",
        }

    late = _signal(
        "eighth_or_later_share",
        recent.get("eighth_or_later_appearances"),
        recent.get("known_entry_appearances"),
        prior.get("eighth_or_later_appearances"),
        prior.get("known_entry_appearances"),
    )
    leverage = _signal(
        "high_leverage_share",
        recent.get("high_leverage_appearances"),
        recent.get("known_leverage_appearances"),
        prior.get("high_leverage_appearances"),
        prior.get("known_leverage_appearances"),
    )
    signals = [late, leverage]
    complete = [signal for signal in signals if signal["status"] == "complete"]
    if not complete:
        return {
            "contract": CONTRACT,
            "method_version": METHOD_VERSION,
            "status": "unavailable",
            "reason_code": "insufficient_comparable_deployment_evidence",
            "signals": signals,
        }

    directional = {signal["direction"] for signal in complete if signal["direction"] != "stable"}
    if len(directional) > 1:
        return {
            "contract": CONTRACT,
            "method_version": METHOD_VERSION,
            "status": "unavailable",
            "reason_code": "mixed_directional_evidence",
            "signals": signals,
        }

    if not directional:
        return {
            "contract": CONTRACT,
            "method_version": METHOD_VERSION,
            "status": "complete",
            "movement": "stable",
            "public_label": "Recent deployment has been broadly stable.",
            "signals": signals,
        }

    direction = next(iter(directional))
    if direction == "higher":
        movement = "later_or_higher_leverage"
        label = "Recent deployment shifted toward later or higher-leverage work."
    else:
        movement = "earlier_or_lower_leverage"
        label = "Recent deployment shifted toward earlier or lower-leverage work."

    return {
        "contract": CONTRACT,
        "method_version": METHOD_VERSION,
        "status": "complete",
        "movement": movement,
        "public_label": label,
        "signals": signals,
    }

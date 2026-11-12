"""NBA/KBL dev31 prospective safety and retrospective error-audit candidate.

Not a replacement for dev30 scoring weights or a live prediction endpoint.
All player/team posts recorded after a game are POSTGAME_ONLY for that fixture.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Score:
    home: float
    away: float

    @property
    def total(self) -> float:
        return self.home + self.away

    @property
    def margin(self) -> float:
        return self.home - self.away


def audit_prediction(predicted: Score, actual: Score, empirical_abs_margin80: float | None = None) -> dict:
    if actual.home == actual.away:
        raise ValueError("Basketball FINAL must have a winner")
    if min(actual.home, actual.away) < 0:
        raise ValueError("Negative score")
    hit = predicted.margin * actual.margin > 0
    margin_error = abs(predicted.margin - actual.margin)
    total_error = abs(predicted.total - actual.total)
    tags = []
    if not hit:
        tags.append("WINNER_MISS")
    if margin_error >= 15:
        tags.append("MARGIN_LARGE_ERROR_15")
    if total_error >= 15:
        tags.append("TOTAL_LARGE_ERROR_15")
    if total_error >= 30:
        tags.append("TOTAL_SHOCK_30")
    if abs(actual.margin) >= 20 and abs(predicted.margin) < 6:
        tags.append("BLOWOUT_TAIL_UNDERWEIGHT")
    return {
        "winner_hit": hit,
        "margin_abs_error": margin_error,
        "total_abs_error": total_error,
        "tags": tags,
        "margin80_covered": None if empirical_abs_margin80 is None else margin_error <= empirical_abs_margin80,
    }


def win5_class(home_minus_away: float) -> str:
    return "승" if home_minus_away >= 6 else ("패" if home_minus_away <= -6 else "5")


def verify_pregame_source(published_at_utc, first_observed_at_utc, cutoff_utc,
                          official_player_id_verified, same_season_roster_verified):
    """Fail closed if timestamps, official identity or current-season team are unknown."""
    import datetime as dt
    if not all([published_at_utc, first_observed_at_utc, cutoff_utc,
                official_player_id_verified, same_season_roster_verified]):
        return False
    try:
        a = dt.datetime.fromisoformat(published_at_utc.replace("Z", "+00:00"))
        b = dt.datetime.fromisoformat(first_observed_at_utc.replace("Z", "+00:00"))
        c = dt.datetime.fromisoformat(cutoff_utc.replace("Z", "+00:00"))
        return (a.tzinfo is not None and b.tzinfo is not None and c.tzinfo is not None
                and max(a, b) <= c)
    except (ValueError, AttributeError, TypeError):
        return False


def approve_scoring_promotion(historical_improvement, independent_prospective_improvement,
                              full_asof, player_roster_verified, signed_governance_approval):
    return all([historical_improvement, independent_prospective_improvement,
                full_asof, player_roster_verified, signed_governance_approval])


def propose_expert_review_tags(audit: dict, first_quarter_margin: int | None = None,
                               prior_q1_margin_estimate: float | None = None):
    tags = set(audit["tags"])
    if (first_quarter_margin is not None and prior_q1_margin_estimate is not None
            and abs(first_quarter_margin - prior_q1_margin_estimate) >= 15):
        tags.add("EARLY_QUARTER_SHOCK")
    return sorted(tags)

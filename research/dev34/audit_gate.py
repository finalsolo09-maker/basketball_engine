"""Research-only dev34 source-quality, score-error and non-leaking promotion gate.

This module does not open private user SQLite, rewrite P0, refit coefficients,
or set a production model pointer.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional

CONFIRMED = {"OFFICIAL_TEAM_AND_AP", "CONFIRMED_CROSS_SOURCE"}


def can_settle(status: str) -> bool:
    return status in CONFIRMED


def asof_eligible(published_at_utc: Optional[str], first_observed_at_utc: Optional[str],
                  cutoff_utc: Optional[str], official_player_identity: bool,
                  season_roster_verified: bool) -> bool:
    if not all((published_at_utc, first_observed_at_utc, cutoff_utc,
                official_player_identity, season_roster_verified)):
        return False
    try:
        ts = [datetime.fromisoformat(s.replace("Z", "+00:00")) for s in
              (published_at_utc, first_observed_at_utc, cutoff_utc)]
        return all(t.tzinfo is not None for t in ts) and max(ts[:2]) <= ts[2]
    except (TypeError, ValueError, AttributeError):
        return False


def result_check(home: int, away: int, h1=None, a1=None, h2=None, a2=None):
    if home is None or away is None or min(home, away) < 0 or home == away:
        raise ValueError("FINAL must be complete, nonnegative, and non-tied")
    if any(x is not None for x in (h1, a1, h2, a2)):
        if any(x is None for x in (h1, a1, h2, a2)):
            raise ValueError("Incomplete halves")
        if min(h1, a1, h2, a2) < 0 or h1 + h2 != home or a1 + a2 != away:
            raise ValueError("Half sums disagree with FINAL")
    return True


def win5(margin: float) -> str:
    if margin >= 6:
        return "승"
    if margin <= -6:
        return "패"
    return "5"


def audit(pred_home: float, pred_away: float, real_home: int, real_away: int) -> dict:
    result_check(real_home, real_away)
    p_margin = pred_home - pred_away
    margin = real_home - real_away
    m_err = abs(p_margin - margin)
    t_err = abs((pred_home + pred_away) - (real_home + real_away))
    tags = []
    if p_margin == 0:
        tags.append("INVALID_CENTER_TIE_NO_WINNER")
    elif p_margin * margin < 0:
        tags.append("WINNER_MISS")
    if win5(p_margin) != win5(margin):
        tags.append("WIN5_CENTER_CLASS_MISS")
    if abs(margin) >= 20 and abs(p_margin) <= 5:
        tags.append("BLOWOUT_TAIL_UNDERWEIGHT")
    if m_err >= 15:
        tags.append("MARGIN_ERROR_15_PLUS")
    if t_err >= 30:
        tags.append("TOTAL_TAIL_SHOCK_30")
    return {"winner_hit": None if p_margin == 0 else p_margin * margin > 0,
            "margin_mae": m_err, "total_mae": t_err, "tags": tags}


def training_gate(source_status: str, postgame_for_same_fixture: bool,
                  official_asof: bool, independent_forward_validated: bool) -> bool:
    return (source_status in CONFIRMED and not postgame_for_same_fixture
            and official_asof and independent_forward_validated)


def production_promotion_gate(full_asof: bool, roster_valid: bool,
                              independent_shadow_pass: bool, win5_logloss_noninferior: bool,
                              brier_ece_ok: bool, signed_review: bool) -> bool:
    return all((full_asof, roster_valid, independent_shadow_pass,
                win5_logloss_noninferior, brier_ece_ok, signed_review))

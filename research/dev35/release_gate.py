"""Fail-closed development-only approval contract for NBA/KBL dev35.

The public repository must not load or publish the user's private SQLite or weights.
The actual retrain artifacts and runnable scripts live in the user's private Library.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ApprovalEvidence:
    full_asof: bool
    current_roster_and_availability_verified: bool
    source_usage_rights_verified: bool
    independent_prospective_shadow_pass: bool
    win5_logloss_noninferior: bool
    win5_brier_ece_pass: bool
    regression_accuracy_no_degradation: bool
    staging_rollback_tested: bool
    reviewer_signed: bool


def can_promote_production(e: ApprovalEvidence) -> bool:
    return all(vars(e).values())


def can_retrain_research(chronological_split: bool, source_db_integrity: bool,
                         postgame_same_game_excluded: bool, p0_immutable: bool) -> bool:
    return all((chronological_split,source_db_integrity,postgame_same_game_excluded,p0_immutable))


def status(e: ApprovalEvidence) -> str:
    return "ELIGIBLE_FOR_MANUAL_PROMOTION_REVIEW" if can_promote_production(e) else "BLOCKED_NO_PRODUCTION_PROMOTION"

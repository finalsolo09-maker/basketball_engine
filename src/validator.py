"""NBA/KBL 팀별 2행 경기 기록 정합성 검증."""

import logging
import numpy as np
import pandas as pd

from src.exceptions import DataValidationError

logger = logging.getLogger(__name__)


class DataValidator:
    REQUIRED = (
        "game_id", "date", "season", "league", "team", "opponent",
        "is_home", "pts", "opp_pts", "fgm", "fga", "fg3m", "fg3a",
        "ftm", "fta", "oreb", "dreb", "tov", "ast", "stl", "blk", "game_minutes"
    )
    NUMERIC = (
        "pts", "opp_pts", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta",
        "oreb", "dreb", "tov", "ast", "stl", "blk", "game_minutes"
    )

    @staticmethod
    def validate(df: pd.DataFrame, policy: str = "raise") -> pd.DataFrame:
        """한 경기라도 잘못됐으면 fail-closed, drop은 반드시 경기 단위."""
        if policy not in {"raise", "drop"}:
            raise ValueError("policy는 raise 또는 drop이어야 합니다.")
        if df.empty:
            raise DataValidationError("입력된 데이터프레임이 비어 있습니다.")
        missing = set(DataValidator.REQUIRED).difference(df.columns)
        if missing:
            raise DataValidationError(f"필수 컬럼 누락: {sorted(missing)}")
        out = df.copy()
        bad = []
        for game_id, group in out.groupby("game_id", dropna=False):
            problems = []
            if len(group) != 2 or set(group["is_home"].tolist()) != {0, 1}:
                problems.append("HOME_AWAY_ROW_COUNT")
            elif (
                group["team"].nunique() != 2 or group["season"].nunique() != 1
                or group["league"].nunique() != 1
            ):
                problems.append("TEAM_OR_LEAGUE_ID")
            else:
                home = group.loc[group["is_home"] == 1].iloc[0]
                away = group.loc[group["is_home"] == 0].iloc[0]
                if (
                    home["opponent"] != away["team"]
                    or away["opponent"] != home["team"]
                ):
                    problems.append("RECIPROCAL_OPPONENT")
                if (
                    home["pts"] != away["opp_pts"]
                    or away["pts"] != home["opp_pts"]
                ):
                    problems.append("RECIPROCAL_SCORE")
                if home["pts"] == away["pts"]:
                    problems.append("INVALID_FINAL_DRAW")
                minutes = 48 if home["league"] == "NBA" else (
                    40 if home["league"] == "KBL" else None
                )
                if minutes is None or home["game_minutes"] != away["game_minutes"]:
                    problems.append("UNSUPPORTED_LEAGUE_OR_MISMATCHED_MINUTES")
                elif (
                    home["game_minutes"] < minutes
                    or (home["game_minutes"] - minutes) % 5 != 0
                ):
                    problems.append("INVALID_GAME_MINUTES")
            nums = group[list(DataValidator.NUMERIC)].apply(
                pd.to_numeric, errors="coerce"
            )
            if nums.isna().any().any() or not np.isfinite(nums.to_numpy()).all():
                problems.append("MISSING_OR_NONFINITE")
            elif (nums.to_numpy() < 0).any() or (
                (nums.to_numpy() % 1) != 0
            ).any():
                problems.append("NEGATIVE_OR_NONINTEGER")
            else:
                if (
                    (group["fgm"] > group["fga"]).any()
                    or (group["fg3m"] > group["fg3a"]).any()
                    or (group["fg3a"] > group["fga"]).any()
                    or (group["fg3m"] > group["fgm"]).any()
                    or (group["fgm"] - group["fg3m"] >
                        group["fga"] - group["fg3a"]).any()
                    or (group["ftm"] > group["fta"]).any()
                ):
                    problems.append("INVALID_SHOT_COUNTS")
                calculated = 2 * group["fgm"] + group["fg3m"] + group["ftm"]
                if not np.array_equal(
                    calculated.to_numpy(), group["pts"].to_numpy()
                ):
                    problems.append("POINTS_IDENTITY")
            if problems:
                bad.append((game_id, problems))
        if bad and policy == "raise":
            raise DataValidationError(f"경기 무결성 오류: {bad[:5]}")
        if bad:
            logger.warning("검증 실패 경기 %d건 전체 2행 제거: %s", len(bad), bad[:5])
            out = out[~out["game_id"].isin({game for game, _ in bad})].copy()
        return out

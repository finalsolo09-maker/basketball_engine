"""FeatureBuilder 모듈 (학습/추론 파이프라인 정합성 보장)."""

import pandas as pd
from src.features.blocks import ScheduleFeatureBlock, RollingStatsFeatureBlock, MatchupFeatureBlock
from src.features.elo import EloCalculator

class FeatureBuilder:
    """여러 FeatureBlock을 조합하고 일관된 파이프라인을 실행하는 클래스."""

    def __init__(self, league_config: dict, global_config: dict):
        self.league_config = league_config
        self.global_config = global_config
        self.blocks = [
            ScheduleFeatureBlock("schedule", global_config["features"]),
            RollingStatsFeatureBlock("rolling", {**global_config["features"], **league_config}),
            MatchupFeatureBlock("matchup", global_config["features"])
        ]
        self.elo_calc = EloCalculator(league_config)

    @property
    def feature_columns(self) -> list[str]:
        cols = ["elo_pre", "elo_opp_pre", "elo_diff"]
        for block in self.blocks:
            cols.extend(block.columns)
        return cols

    def build_features(self, df: pd.DataFrame, is_future: bool = False) -> pd.DataFrame:
        """
        데이터프레임에 모든 피처 블록과 Elo 계산을 순차 적용합니다.
        추론 시 is_future=True 경기가 포함되어도 shift(1)과 엄격한 시계열 분리로 누수를 차단합니다.
        """
        working_df = df.copy()

        # 1. Elo 피처 계산
        working_df = self.elo_calc.calculate_elo_features(working_df)

        # 2. 각 블록 피처 적용
        for block in self.blocks:
            working_df = block.transform(working_df)

        # 3. 매치업 세부 피처 파생 (홈팀 기준 및 대칭 변환)
        # 홈/원정 구조에서 홈 행에 대해 상대방(원정)의 롤링 통신 값을 결합
        working_df = self._add_matchup_derived_features(working_df)

        return working_df

    def _add_matchup_derived_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """상대 팀의 경기 전 롤링값을 대칭 결합한다. 미확정값은 0으로 조작하지 않는다."""
        out = df.copy()
        windows = self.global_config["features"].get("rolling_windows", [5, 10])
        w = int(windows[0])
        base = [f"ortg_roll_{w}", f"drtg_roll_{w}", f"pace_roll_{w}"]
        if not all(col in out.columns for col in base):
            raise KeyError("상대 전력 피처를 만들 롤링 컬럼이 누락되었습니다.")
        other = out[["game_id", "team", *base]].rename(
            columns={
                "team": "opponent",
                base[0]: "opp_ortg",
                base[1]: "opp_drtg",
                base[2]: "opp_pace",
            }
        )
        out = out.merge(
            other, on=["game_id", "opponent"], how="left", validate="one_to_one"
        )
        out["matchup_ortg_diff"] = out[base[0]] - out["opp_drtg"]
        out["matchup_drtg_diff"] = out[base[1]] - out["opp_ortg"]
        out["expected_pace"] = (out[base[2]] + out["opp_pace"]) / 2.0
        out["naive_home_pts"] = out["expected_pace"] * (
            out[base[0]] + out["opp_drtg"]
        ) / 200.0
        return out.drop(columns=["opp_ortg", "opp_drtg", "opp_pace"])

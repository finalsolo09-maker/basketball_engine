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
        """홈/원정 간 상대 비교 매치업 피처를 계산합니다."""
        df = df.copy()
        # 홈 행과 원정 행을 짝지어 매치업 피처 생성
        # 간이 구현: 경기 내 원정팀 롤링 값을 홈팀 행에 매핑
        if "ortg_roll_5" in df.columns:
            away_subset = df[df["is_home"] == 0][["game_id", "ortg_roll_5", "drtg_roll_5", "pace_roll_5"]].copy()
            away_subset.columns = ["game_id", "away_ortg_roll_5", "away_drtg_roll_5", "away_pace_roll_5"]
            
            df = pd.merge(df, away_subset, on="game_id", how="left")
            
            # 홈팀 행 기준 매치업 피처
            mask_home = df["is_home"] == 1
            df.loc[mask_home, "matchup_ortg_diff"] = df.loc[mask_home, "ortg_roll_5"] - df.loc[mask_home, "away_drtg_roll_5"]
            df.loc[mask_home, "matchup_drtg_diff"] = df.loc[mask_home, "drtg_roll_5"] - df.loc[mask_home, "away_ortg_roll_5"]
            df.loc[mask_home, "expected_pace"] = (df.loc[mask_home, "pace_roll_5"] + df.loc[mask_home, "away_pace_roll_5"]) / 2
            df.loc[mask_home, "naive_home_pts"] = df.loc[mask_home, "expected_pace"] * (df.loc[mask_home, "ortg_roll_5"] + df.loc[mask_home, "away_drtg_roll_5"]) / 200

            # 원정팀 행 기준 매치업 피처 (대칭)
            mask_away = df["is_home"] == 0
            df.loc[mask_away, "matchup_ortg_diff"] = df.loc[mask_away, "ortg_roll_5"] - df.loc[mask_away, "drtg_roll_5"] # 임시 매핑
            df.loc[mask_away, "matchup_drtg_diff"] = 0.0
            df.loc[mask_away, "expected_pace"] = df.loc[mask_away, "pace_roll_5"]
            df.loc[mask_away, "naive_home_pts"] = 0.0

            df.fillna(0.0, inplace=True)
        return df

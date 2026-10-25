"""리그별 독립 Elo 레이팅 계산 및 관리 모듈."""

import numpy as np
import pandas as pd

class EloCalculator:
    """경기 결과에 따라 Elo 레이팅을 업데이트하고 사후 피처를 기록하는 클래스."""

    def __init__(self, league_config: dict):
        self.init_rating = league_config.get("elo_init", 1500.0)
        self.k = league_config.get("elo_k", 20.0)
        self.hfa = league_config.get("elo_hfa", 100.0)
        self.use_mov = league_config.get("use_mov_adjustment", True)
        self.blend = league_config.get("new_season_blend", 0.7)

    def calculate_elo_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        경기 데이터프레임을 순회하며 경기 '직전' Elo 레이팅을 피처로 기록하고,
        경기 결과에 따라 레이팅을 업데이트합니다.
        """
        df = df.copy()
        df = df.sort_values(["date", "game_id"]).reset_index(drop=True)

        ratings = {}
        current_season = None

        elo_pre_list = []
        opp_elo_pre_list = []

        # 팀별 경기 기록 순회를 위해 game_id 기준으로 홈/원정 행을 하나로 묶거나 순차 처리
        # 여기서는 게임 단위로 순회하면서 홈/원정 레이팅 관리
        game_groups = list(df.groupby(["game_id", "date", "season"], sort=False))

        # 임시 저장을 위한 딕셔너리 구성
        elo_map_home = {}
        elo_map_away = {}

        for game_id, group, season in [
            (g_id, g_df, g_df["season"].iloc[0]) for g_id, g_df in df.groupby(["game_id", "date", "season"], sort=False)
        ]:
            if current_season != season:
                if current_season is not None:
                    # 시즌 전환 시 평균 회귀 블렌딩
                    all_teams = list(ratings.keys())
                    mean_val = np.mean(list(ratings.values())) if ratings else self.init_rating
                    for t in all_teams:
                        ratings[t] = self.blend * ratings[t] + (1 - self.blend) * mean_val
                current_season = season

            home_row = group[group["is_home"] == 1].iloc[0]
            away_row = group[group["is_home"] == 0].iloc[0]

            home_team = home_row["team"]
            away_team = away_row["team"]

            # 초기화
            if home_team not in ratings:
                ratings[home_team] = self.init_rating
            if away_team not in ratings:
                ratings[away_team] = self.init_rating

            h_elo = ratings[home_team]
            a_elo = ratings[away_team]

            elo_map_home[game_id] = h_elo
            elo_map_away[game_id] = a_elo

            # 결과 반영 및 업데이트
            h_pts = home_row["pts"]
            a_pts = away_row["pts"]
            if pd.isna(h_pts) or pd.isna(a_pts):
                # 미래 경기이므로 업데이트 스킵
                continue

            # 승률 기대값 산출
            exp_h = 1.0 / (1.0 + 10.0 ** (- (h_elo + self.hfa - a_elo) / 400.0))
            actual_h = 1.0 if h_pts > a_pts else (0.5 if h_pts == a_pts else 0.0)

            mov = abs(h_pts - a_pts)
            if self.use_mov:
                elo_diff = abs(h_elo + self.hfa - a_elo)
                mov_multiplier = (max(mov, 1) ** 0.8) / (7.5 + 0.006 * elo_diff)
            else:
                mov_multiplier = 1.0

            delta = self.k * mov_multiplier * (actual_h - exp_h)
            ratings[home_team] = h_elo + delta
            ratings[away_team] = a_elo - delta

        # 데이터프레임에 매핑
        df["elo_pre"] = df.apply(lambda r: elo_map_home.get(r["game_id"], self.init_rating) if r["is_home"] == 1 else elo_map_away.get(r["game_id"], self.init_rating), axis=1)
        df["elo_opp_pre"] = df.apply(lambda r: elo_map_away.get(r["game_id"], self.init_rating) if r["is_home"] == 1 else elo_map_home.get(r["game_id"], self.init_rating), axis=1)
        df["elo_diff"] = df["elo_pre"] - df["elo_opp_pre"]

        return df

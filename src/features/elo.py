"""리그별 Elo 피처. 당일 모든 사전값을 같은 날짜 시작 스냅샷에서 산출한다."""

import numpy as np
import pandas as pd


class EloCalculator:
    """DATE_ONLY_REPLAY용 Elo. 실전 FULL_ASOF 여부는 별도 데이터 계층에서 확인."""

    def __init__(self, league_config: dict):
        self.init_rating = float(league_config.get("elo_init", 1500.0))
        self.k = float(league_config.get("elo_k", 20.0))
        self.hfa = float(league_config.get("elo_hfa", 100.0))
        self.use_mov = bool(league_config.get("use_mov_adjustment", True))
        self.blend = float(league_config.get("new_season_blend", 0.7))

    def calculate_elo_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """결과가 있는 과거 날짜만 Elo 상태에 반영한다."""
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values(["date", "season", "game_id", "is_home"]).reset_index(drop=True)
        ratings: dict[str, float] = {}
        current_season = None
        # 정렬된 행 인덱스에 직접 기록해 복합 groupby 키와 game_id 혼용을 차단
        pre = np.full(len(df), np.nan, dtype=float)
        opp_pre = np.full(len(df), np.nan, dtype=float)

        for date, day_df in df.groupby("date", sort=True):
            seasons = day_df["season"].unique()
            if len(seasons) != 1:
                raise ValueError("같은 날짜에 여러 시즌이 섞여 Elo 상태가 모호합니다.")
            season = seasons[0]
            if current_season is not None and season != current_season and ratings:
                mean_rating = float(np.mean(list(ratings.values())))
                ratings = {
                    team: self.blend * rating + (1.0 - self.blend) * mean_rating
                    for team, rating in ratings.items()
                }
            current_season = season
            pending = []
            # 당일 결과 반영 이전의 고정 ratings에서 모든 경기 피처 계산
            for key, game in day_df.groupby("game_id", sort=True):
                if len(game) != 2 or set(game["is_home"].astype(int)) != {0, 1}:
                    raise ValueError(f"경기 {key}의 홈/원정 2행 무결성이 깨졌습니다.")
                home = game[game["is_home"] == 1].iloc[0]
                away = game[game["is_home"] == 0].iloc[0]
                h_team, a_team = str(home["team"]), str(away["team"])
                h_elo = ratings.get(h_team, self.init_rating)
                a_elo = ratings.get(a_team, self.init_rating)
                for i in game.index:
                    is_home = int(df.at[i, "is_home"]) == 1
                    pre[i] = h_elo if is_home else a_elo
                    opp_pre[i] = a_elo if is_home else h_elo
                if pd.isna(home["pts"]) or pd.isna(away["pts"]):
                    continue
                h_pts, a_pts = float(home["pts"]), float(away["pts"])
                if h_pts == a_pts:
                    raise ValueError("농구 FINAL에 무승부 결과를 사용할 수 없습니다.")
                p_home = 1.0 / (1.0 + 10.0 ** (-(h_elo + self.hfa - a_elo) / 400.0))
                margin = abs(h_pts - a_pts)
                mov_factor = (
                    min(4.0, max(0.1, max(1.0, margin) ** 0.8 /
                                 max(0.1, 7.5 + 0.006 * abs(h_elo + self.hfa - a_elo))))
                    if self.use_mov else 1.0
                )
                delta = self.k * mov_factor * (float(h_pts > a_pts) - p_home)
                pending.append((h_team, a_team, delta))
            # 이 날짜의 모든 피처가 생성된 뒤에만 점수를 반영
            for h_team, a_team, delta in pending:
                ratings[h_team] = ratings.get(h_team, self.init_rating) + delta
                ratings[a_team] = ratings.get(a_team, self.init_rating) - delta

        df["elo_pre"] = pre
        df["elo_opp_pre"] = opp_pre
        df["elo_diff"] = pre - opp_pre
        return df

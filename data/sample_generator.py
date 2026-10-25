"""파이프라인 검증용 샘플 데이터 및 오라클 생성기."""

import numpy as np
import pandas as pd
from pathlib import Path

class SampleDataGenerator:
    """현실적인 농구 시뮬레이션 데이터를 생성하는 클래스."""

    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)

    def generate(self, league: str = "NBA", n_seasons: int = 2) -> tuple[pd.DataFrame, pd.DataFrame]:
        teams = [f"{league}_Team_{i:02d}" for i in range(10 if league == "KBL" else 30)]
        n_games_per_team = 54 if league == "KBL" else 82
        reg_mins = 40 if league == "KBL" else 48

        records = []
        oracle_records = []

        base_date = pd.to_datetime("2023-10-01")

        for season in range(1, n_seasons + 1):
            season_str = f"20{22+season}-{23+season}"
            team_ratings = {t: self.rng.normal(100, 5, size=3) for t in teams} # [off, def, pace]

            # 일정 생성 및 시뮬레이션
            dates = pd.date_range(base_date + pd.Timedelta(days=(season-1)*365), periods=n_games_per_team, freq="3D")
            
            for d_idx, date in enumerate(dates):
                shuffled_teams = self.rng.permutation(teams)
                for i in range(0, len(shuffled_teams) - 1, 2):
                    home, away = shuffled_teams[i], shuffled_teams[i+1]
                    game_id = f"{league}_{season_str}_{date.strftime('%Y%m%d')}_{home}_{away}"

                    # 잠재 능력치 기반 득점 및 페이스 산출
                    h_off, h_def, h_pace = team_ratings[home]
                    a_off, a_def, a_pace = team_ratings[away]

                    pace = (h_pace + a_pace) / 2 + self.rng.normal(0, 2)
                    pace = max(70.0, pace)

                    h_pts_exp = pace * (h_off * 1.02 - a_def * 0.98) / 100 + 3.5 # 홈 어드밴티지
                    a_pts_exp = pace * (a_off * 1.02 - h_def * 0.98) / 100

                    h_pts = int(np.clip(self.rng.poisson(h_pts_exp), 60, 150))
                    a_pts = int(np.clip(self.rng.poisson(a_pts_exp), 60, 150))

                    if h_pts == a_pts:  # 동점 방지 연장
                        h_pts += 5

                    # 박스스코어 대략적 분해 (항등식 만족)
                    fga = int(pace * 0.85)
                    fg3a = int(fga * 0.38)
                    fg3m = int(fg3a * 0.35)
                    fgm = fg3m + int((h_pts - fg3m * 3) / 2)
                    fgm = min(fga, max(fg3m, fgm))
                    ftm = max(0, h_pts - 2 * (fgm - fg3m) - 3 * fg3m)
                    fta = int(ftm * 1.25)
                    oreb = int((fga - fgm) * 0.28)
                    dreb = int(35 - oreb)
                    tov = int(pace * 0.12)
                    ast = int(fgm * 0.6)
                    stl = int(tov * 0.5)
                    blk = 4

                    # 홈 팀 행
                    records.append({
                        "game_id": game_id, "date": date, "season": season_str, "league": league,
                        "game_type": "regular", "team": home, "opponent": away, "is_home": 1,
                        "pts": h_pts, "opp_pts": a_pts, "fgm": fgm, "fga": fga, "fg3m": fg3m, "fg3a": fg3a,
                        "ftm": ftm, "fta": fta, "oreb": oreb, "dreb": dreb, "tov": tov, "ast": ast,
                        "stl": stl, "blk": blk, "game_minutes": reg_mins
                    })
                    # 원정 팀 행
                    records.append({
                        "game_id": game_id, "date": date, "season": season_str, "league": league,
                        "game_type": "regular", "team": away, "opponent": home, "is_home": 0,
                        "pts": a_pts, "opp_pts": h_pts, "fgm": fgm, "fga": fga, "fg3m": fg3m, "fg3a": fg3a,
                        "ftm": ftm, "fta": fta, "oreb": oreb, "dreb": dreb, "tov": tov, "ast": ast,
                        "stl": stl, "blk": blk, "game_minutes": reg_mins
                    })

                    true_margin = h_pts_exp - a_pts_exp
                    true_win_prob = 1.0 / (1.0 + 10.0 ** (-true_margin / 400.0))
                    oracle_records.append({
                        "game_id": game_id,
                        "true_home_win_prob": true_win_prob,
                        "true_expected_margin": true_margin
                    })

        df = pd.DataFrame(records)
        df_oracle = pd.DataFrame(oracle_records)
        return df, df_oracle

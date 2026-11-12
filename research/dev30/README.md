# NBA·KBL dev30 consolidated DB + research scorer (2026-11-10)

This is a **research deployment manifest**, not a production release. The full executable package and SQLite are stored in the user's personal Library, `/NBA·KBL 예측 엔진/Candidates/NBA_KBL_DEV30_RECONCILED_ENGINE_DB_20261110.zip`. Do not upload private user data to this public repository.

## Audit findings

- Base dev29 SQLite SHA-256 `e622b7189254ecc49d44250211be43d0c1f016c25a1bcd59516be524d9b92e7c`. Research candidate dev30 SHA-256 `dc3bbb3380501ebc58bb9f190387243f0c03babb30c545b19129c62c1db0a6ec`.
- Original **115 tables and 115 triggers** unchanged; new DB **121 tables / 127 triggers**. SQLite integrity OK, foreign key check zero.
- Ten NBA games (five each in 2024-25 and 2025-26) previously labelled invalid home/away were actually **neutral-site** games; leave `is_home=0` unchanged and join neutral-site classification as separate data. See `neutral_games.csv`. Home/away-trained models still exclude these five neutral games per season.
- Refit the four dev29 Ridge models (NBA and KBL, team-only vs prior-season players+tactics): all four JSON artifacts **byte-identical** to the original. The active research scorer in both leagues is prior-season players+tactics, selected using validation MAE for point margin and total, not post-hoc winner accuracy.
- Replay model output from SQLite: NBA 267 holdout fixtures, KBL 53; prediction arrays reconstructed to numerical precision. **43 checks passed** (24 new dev30 + 19 dev29).
- `RESEARCH_ACTIVE` is NOT `PRODUCTION_APPROVED`. Neither league achieved approved FULL_ASOF data and new forward shadow evidence. Both have worse win5 log loss and classification accuracy than team-only baseline.

## Code safeguards

Use `research/dev30/research_gate.py` to validate the user-controlled dev30 DB and JSON model registry from an authorized local directory. It will **refuse live 2026-27 inference**, and it does not mutate a DB. The complete offline replay/retraining source is distributed with the Library package.

Sources:
- [Official NBA Cup 2026-27 venue rule change](https://pr.nba.com/nba-cup-semifinal-host-sites-coachs-challenge-rules/)
- [Official Paris Games 2025](https://www.nba.com/news/what-to-know-as-spurs-pacers-meet-in-nba-paris-games-2025)
- [Official NBA Mexico City 2025](https://pr.nba.com/mavericks-pistons-mexico-city-2025/)
- [Official NBA 2026-27 opening rosters](https://www.nba.com/news/nba-rosters-set-for-2026-27-regular-season)

This PR must not merge other older prototype code without comparing the actual approved DB schema, validation metrics, game and player IDs, and P0 append-only policy.

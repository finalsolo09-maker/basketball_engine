# dev31 NBA·KBL results + error feedback (2026-11-12)

## Scope and observed results
- Dev30 source DB remains unchanged; user-specific dev31 SQLite and full retrospective 45-test package live only in the user's personal `/NBA·KBL 예측 엔진/Candidates` Library.
- 17 deduplicated fixtures total; **9 confirmed final, 8 pending**. 51 preserved P0/P1/P2 and prior model research snapshot references, **27 stage-specific audits**, 25 win5-stage audits, 9 expert hypotheses, 13 player postgame observations.
- Latest available original prediction per finalized fixture: 4/9 winner hit, margin MAE 13.556, total MAE 13.333. Most recent P2: 2/7 winner hit.
- Paired 5 fixtures on P1 and P2: P1 winner 3/5, P2 winner 1/5. Changes to Phoenix and Portland winner direction were harmful in this sample.
- Score-based P1 Win5 classification: 0/6; all actual margins were >= 6 and all P1 center margins <= 5. This is an audit of **point-center-derived categories** not a calibrated probability model.
- All NBA scores sourced from NBA.com; KBL/WKBL/EASL scores crosschecked against published box scores and news. Provider live API payloads have not been automatically scraped.
- New source timestamps are date-of-audit observations; no retroactive claim that postgame source values existed pregame.

## Changes
- `audit_engine.py`: immutable source safety gate, P0/P1/P2 independent audit, halftime surprise tagging, empirical (historic holdout only) margin interval, 3-way win5 vs center-score separation.
- `test_audit_engine.py`: lightweight test of the generic safe functions.
- **No score-model weights updated or production pointer promoted.** dev30 historical score models remain unchanged. Fail closed on any unverified current-season roster and publication timestamps.
- Original user SQLite, player records and prediction snapshots are not committed to this public repository.

## Next validation
1. Verified new-season sources and exact pregame cutoff.
2. Independent quarter/half forecasting with a distinct backtest.
3. Holdout log-loss/brier/ECE for win5 classifications.
4. Prospective paired evaluation before any model promotion.

Source materials: NBA game pages, KBL/Yonhap, WKBL box score, EASL/Yonhap as listed in the user's private audit report.

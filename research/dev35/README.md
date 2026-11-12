# dev35 integrated NBA/KBL score retraining (2026-11-12)

**RESEARCH_SHADOW_CANDIDATE — NO PRODUCTION PROMOTION**

## Execution summary

- Research historical core: dev30 Ridge point-score prediction (NBA/KBL).
- Result audit core: dev34 FINAL/quarters/player/tactical postgame diagnostics. All dev34 postgame observations are **excluded from features of the same fixtures**. No 2026–27 postgame stats entered the 2025–26 training matrix.
- Input private dev34 DB SHA-256: `fd4035c731878d0c780ca4a97cb847f6c92c506631479b1b6e27e9edb395e7ec`.
- Candidate dev35 SQLite SHA-256: `bd6767d7733a72f8656f4cbd81c6ebab4dfc8cb60e00c8088eb65e141c331005`.
- Original **150 tables/185 triggers and all rows** unchanged. Candidate **152 tables/189 triggers**, `PRAGMA integrity_check=ok`, FK 0. 24/24 local regression checks, replay NBA 267 and KBL 53 games.
- Two new JSON weights saved privately in Library `/NBA·KBL 예측 엔진/Candidates/NBA_KBL_DEV35_RETRAIN_INTEGRATED_20261112.zip`.

## Date-order training

| | NBA | KBL |
|---|---:|---:|
| 2025–26 fixtures | 1,225 | 270 |
| train / validation / holdout | 709 / 249 / 267 | 162 / 55 / 53 |
| features | 63 | 67 |
| best validation model | Ridge scores, alpha 1000, recency half-life 75 days | Ridge total/margin, alpha 160, no temporal weighting |

Validation-only grid search; train+validation refit; locked historical holdout replay. Historical holdout **has appeared in previous dev29/30 reports and is not fresh prospective evidence.**

## Historical holdout

| | NBA dev30 | NBA dev35 | KBL dev30 | KBL dev35 |
|---|---:|---:|---:|---:|
| margin MAE | 12.395 | 12.391 | 8.638 | 8.523 |
| total MAE | 15.907 | 15.757 | 14.727 | 14.591 |
| winner hit | 73.03% | 71.91% | 56.60% | 60.38% |
| win5 class hit | 59.18% | 58.05% | 33.96% | 30.19% |
| win5 LogLoss (fixed-sigma proxy) | 0.92851 | 0.92731 | 1.09974 | 1.10355 |

Approximate win5 LogLoss is **not independently calibrated**. NBA win5 accuracy drops; KBL win5 accuracy and logloss worsen. Do not promote these weights to live.

## Production blockers

- Source publish/first-observed timestamps absent → **no FULL_ASOF**.
- Current NBA/KBL roster, injured player, pregame cutoff join unverified.
- No 2026–27 prospective paired shadow performance.
- Win5 separate LogLoss/Brier/ECE noninferiority unproven.
- Reviewer signature and staging rollback missing.

Existing dev30 active research pointer and real P0 remain unchanged. dev35 is a separate shadow **candidate**, not a main-branch scoring replacement.

For full executable Python training/replay tests, exact model JSON weights and private SQLite, use the user's Library ZIP rather than placing private snapshots in this public GitHub repository.

Public references: [NBA Stats Glossary](https://www.nba.com/stats/help/glossary), [NBA official injury archive](https://official.nba.com/nba-injury-report-2026-27-season/), [KBL official schedule](https://www.kbl.or.kr/match/schedule), [sklearn time series validation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).

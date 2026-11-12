# dev30 PR #4 병합 전 최소 체크리스트 · 운영 승격 게이트

검토 기준: 2026-11-12. PR: https://github.com/finalsolo09-maker/basketball_engine/pull/4

## 범위 및 절대 원칙

- **연구 코드 병합**: `research/dev30`의 문서·중립경기 분류·읽기 전용 차단 검증기를 main에 합치는 것. 재학습 가중치·운영 포인터·실전 P0는 교체하지 않음.
- **운영 모델 승격**: 2026–27 실전 입력 및 예측 엔드포인트에서 dev30 계수를 사용하도록 바꾸는 것. **현재 금지**.
- 기존 P0/P1/P2 예측과 dev29/dev30 원본 DB 및 해시를 불변으로 유지. 연구 코드를 병합해도 `RESEARCH_ACTIVE`가 `PRODUCTION_APPROVED`로 바뀌면 안 됨.

## A. 연구 코드 main 병합용 최소 체크리스트

- [ ] **A1. 정확한 PR 커밋에서 CI 성공:** Python 구문·imports, `research_gate.py` 테스트, 전체 기존 회귀 시험 실행 기록 URL과 SHA 첨부. PR #4 최초 HEAD `9c63c8507f6a48dc107239768caf79118f0a3ecc`에는 PR workflow run/status 및 리뷰 증빙이 없음. 새 커밋을 만들면 검증할 SHA도 새 것으로 갱신.
- [ ] **A2. 차단 게이트 음성 테스트:** `requested_scope=LIVE`, 잘못된 SHA, 잘못된 피처 순서/차원, DB/FK 오류, 승인되지 않은 모델 상태, 파일 누락을 각각 거부하는지 확인. 정상 연구 replay 1건 성공. 어떤 실패에서도 실전 운영 포인터 변경 금지.
- [ ] **A3. DB 구조·백업·P0 불변:** `PRAGMA integrity_check='ok'`, `PRAGMA foreign_key_check` 0건. 보고서의 기존 115테이블·115트리거가 원본 dev29와 일치한다는 SQL diff와 SHA-256 로그 첨부. 2026–27 실전 P0 및 승인 포인터 변경 0건.
- [ ] **A4. 중립 10경기 재현:** 공식 경기 ID·시즌·일자·경기장·대회 단위로 10건 전부 대조; 중립경기에 일반 홈 보너스 0, 결측 경기로 임의 삭제 금지. 기존 점수/행은 덮어쓰지 않음. 2026–27 NBA컵 준결승은 홈 경기로 분리.
- [ ] **A5. 모델 아티팩트 재현:** NBA/KBL 팀 전용·선수전술 4개 JSON SHA 검증, 피처 schema/order, 날짜별 홀드아웃 NBA 267·KBL 53건 replay 재현 로그를 저장. 43/43 로컬 결과의 입력·명령·실행 환경을 추적 가능하게 기재.
- [ ] **A6. 리뷰·병합 범위 확정:** 리뷰 담당 1명 이상이 공개용 자료에 사용자 원본 DB/비밀값 없음, `research/dev30`만 변경, 무단 배포·자동 승격 없음 확인; PR 설명에 `research-only` 표기. 런타임이 이 경로를 production import하지 않음을 확인.
  
**A1–A6 모두 완료 시에만 연구 코드 병합 검토 가능.** 미완료면 Draft 유지. 통과하더라도 운영 모델은 변경하지 않음.

## B. 운영 모델 승격용 최우선 차단 게이트 — 현재 전부 미완료

- [ ] **B1. FULL_ASOF:** 모든 학습/실전 피처에 `fixture_uid`, `source_url`, `published_at_utc`, `first_observed_at_utc`, `prediction_cutoff_utc`, 데이터 스냅샷 SHA를 보존. `max(published_at, first_observed_at) <= cutoff` 확인. 미확정은 BLOCKED, 후행 수치는 동일 경기 학습/예측에서 제외. 데이터 접근·재사용 권리 근거 첨부.
- [ ] **B2. 현재 선수 가용성:** NBA 공식 player_id, KBL pcode, 팀/시즌/이적·등록 유효구간, 출전 상태와 라인업 자료의 원본 공개시각을 경기 ID에 결합. 부상 보고서의 시각별 개정판 보존. 미확인 선수/라인업의 보정 가중치는 사용 불가.
- [ ] **B3. 날짜순 독립 전향 shadow:** P0 고정 이전 시점에 매 경기 예측·해시 저장, 이후 공식 FINAL과 1:1 결합, 동일 데이터 스냅샷에서 incumbent vs candidate 동시 평가. 기존 회고 홀드아웃 267/53 재현만으로 인정하지 않음.
- [ ] **B4. 승5패 성능 비열화:** NBA·KBL 각각 `승/5/패` 3범주 LogLoss, Brier, ECE, 범주별 적중률(특히 '5'), calibration, 표본/신뢰구간·날짜 블록 CI 제출. 현재 후보의 승5패 LogLoss 악화가 해소되지 않았으므로 FAIL. 점수 MAE 개선이 이 게이트를 대체할 수 없음.
- [ ] **B5. 점수·전후반 출력의 독립성:** 최종 점수 MAE, 마진 MAE, 총점 MAE, 20점 이상 대패 예측 빈도 점검. 전후반 값이 최종 점수 배분에 불과하면 '독립 전후반 엔진'으로 표시 금지.
- [ ] **B6. 운영 배포·복구:** 별도 검토·서명 승인, 지표와 원본 해시를 담은 승격 이벤트, staging → shadow → 제한된 live → rollback 가동 테스트. P0 불변, 승인 모델 포인터 원자적 전환, 외부 데이터/API 장애 시 fail-closed 및 원복.
  
**B1–B6이 모두 충족되기 전에는 `PRODUCTION_APPROVED=false` 유지.**

## 우선순위와 책임 증빙

| 순위 | 검증 작업 | 증빙 산출물 | 현재 판정 |
|---|---|---|---|
| 0 | A1–A2 CI 및 fail-closed gate | Head SHA의 CI URL + 음성 테스트 | 미확인/미완료 |
| 0 | B1 FULL_ASOF·권한 | 경기·피처별 source/time provenance SQL | 차단 |
| 0 | B2 선수 신원·출전 | 공식 ID별 as-of roster/injury snapshot | 차단 |
| 0 | B3 전향 성능 | freeze P0와 FINAL을 분리한 shadow cohort | 차단 |
| 0 | B4 승5패 LogLoss·calibration | 3범주 paired scorecard 및 CI | 악화 |
| 1 | A3–A5 DB/중립/모델 재현 | DB diff + 10 fixture IDs + replay 로그 | 보고값만 있음 |
| 1 | A6 리뷰와 운영 방화벽 | 리뷰 승인 및 영향 범위 문서 | 미확인 |
| 1 | B5–B6 득점·롤백 | 평가/복구 실행 로그 | 미완료 |

## 판정 규칙

- 연구 merge gate: `ALL(A1..A6)` → **main에 연구용 코드만 병합 가능** (승격 없음).
- 운영 promotion gate: `ALL(B1..B6)` **AND** `ALL(A1..A6)` → **별도 운영 PR/승인 심사 가능**. 자동 승인 아님.
- 한 항목이라도 실패·미증빙이면 `BLOCKED_NO_PROMOTION`; 누락 사실을 '테스트 통과'로 대체 금지.
- 오류 수정은 후보 브랜치와 append-only 감사 이벤트로 남기고 사전 P0를 재작성하지 않는다.

## 공식·기술 근거

- NBA Injury Report 2026–27: https://official.nba.com/nba-injury-report-2026-27-season/
- NBA Cup 2026–27 준결승 개최지 변경: https://pr.nba.com/nba-cup-semifinal-host-sites-coachs-challenge-rules/
- 시간순 validation/rolling origin: https://learn.microsoft.com/en-us/azure/machine-learning/concept-automl-forecasting-sweeping
- 예측 데이터 누수 방지: https://learn.microsoft.com/en-us/azure/machine-learning/how-to-automl-forecasting-faq

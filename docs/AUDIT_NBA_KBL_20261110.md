# NBA·KBL 코어·DB·전문가 판단 감사 (2026-11-10)

## 범위와 결론

검사 저장소: `finalsolo09-maker/basketball_engine` 기본 브랜치의 코드.
이 저장소를 과거의 V2.5.1 dev10 전체 패키지로 동일시하지 않는다.

- 현재 저장소에는 실행 가능한 실전 SQLite 원장, 공급자 원본 JSON, 결과 시각 스냅샷,
  실측 홀드아웃/전향적 shadow 기록, 공식 승인 이벤트, 전문가 P0 근거 원장이 없다.
- 따라서 실측 DB 업데이트·실전 재학습·모델 승격·공식 예측 성능 인증은 **미실행/불가**.
- 이번 브랜치는 연구용 오류 수정 **후보**. 자동 승격 금지. 기존 공식 P0 불변.

## 확인한 코드 오류 (기존 브랜치)

| 분류 | 위치 | 근거 및 수정 |
|---|---|---|
| BLOCKER | src/features/blocks.py | logging 가져오기 전에 사용. import 순서 수정 |
| BLOCKER | src/features/blocks.py | 없는 team_poss 컬럼 참조. 선계산·상대 매핑 수정 |
| BLOCKER | src/models/trainer.py | @staticmethod 들여쓰기 문법 오류. 코드 재구성 |
| CRITICAL | src/features/elo.py | groupby 복합키를 단일 game_id처럼 조회해 기본 Elo로 회귀. 행 기준 직접 배정 |
| CRITICAL | src/features/elo.py | 당일 결과 즉시 업데이트. 날짜별 사전 스냅샷 고정 |
| CRITICAL | src/models/trainer.py | 미검증 OOF=0 포함하여 sigma와 성능 산정. 유효 OOF만 사용 |
| CRITICAL | src/models/trainer.py | 경기 행 순서대로 CV하면 같은 날짜 학습/검증 중복. 날짜 단위 분리 |
| CRITICAL | src/features/builder.py | 원정 매치업 지표를 0으로 대체, 결측 전역 0 덮기. 상대 행 대칭 결합 |
| CRITICAL | src/features/blocks.py | 휴식일 off-by-one, 당일 포함 최근7일 횟수. 이전 완료 날짜만 참조 |
| CRITICAL | data/sample_generator.py | 예측 득점 수식 약 0~10점인데 60점 이상 강제 → 바닥 점수 집중. 득점 스케일 수정 |
| CRITICAL | src/validator.py | 홈/원정 상호 점수와 상대, 슛 시도 누락 검증. 경기 단위 검증 강화 |
| SECURITY | main.py / predictor.py | joblib 역직렬화. 제한 JSON 보정기·SHA-256 검증 후보로 변경 |
| GOVERNANCE | main.py / predictor.py | 합성자료 모델이 실전처럼 표시될 위험. SANITY_TESTED/SYNTHETIC 고정 |
| UNKNOWN | DB 저장소 | 원본 DB 확인 불가. read-only `python -m src.db_audit --db path.sqlite` 추가 |

## 전문가 판단의 개별 감사 계약

한 번의 전문가 선택은 **경기/시점/가설/공개 근거/판단/결과**를 분리한다.
선수별 영향과 감독 전술을 과거 시즌의 최신값으로 소급 덮지 않는다.

1. **팀 신원과 대회**: NBA/KBL, 시즌, fixture_uid, 예정/실제 시작시각, 중립 여부
2. **가용 선수**: 공식 등록·부상·출전 제한, 확인시각, 대체 선수, 예상 출전시간
3. **전력 수준**: 경기 전 ORTG/DRTG/NetRtg/Pace/Elo, 홈·원정 상대 강도 보정
4. **공격 구조**: 하프코트 대 속공, 픽앤롤 핸들러/롤맨, 포스트·컷·캐치앤슛
5. **수비 상성**: 드롭/스위치/헷지/지역방어/트랩, 림 억제·코너3점 허용
6. **볼 관리**: TOV%, 압박 저항, 2차 공격, 자유투 획득률과 파울 누적
7. **피로·여행**: 백투백, 최근7일 출장, 이동·시차, 직전 연장전, 실제 휴식일
8. **벤치/감독**: 주력 5명 조합, 교체 패턴, 로테이션 단축, 감독 대책의 실측 근거
9. **과거 맞대결**: 현재 명단·전술이 다른 맞대결을 자동 근거로 확대 금지
10. **확률·선택**: 데이터 모델 확률과 전문가 선택을 각각 보존, 정량 가중치는 독립 검증 전까지 미반영

각 요인에 `source_url, published_at_utc, first_observed_at_utc, cutoff_utc,
evidence_grade, expected_direction, confidence, review_note`를 저장해야 한다.
`published_at_utc` 또는 독립 관측시각이 없는 값은 FULL_ASOF 근거가 아니다.

### 전문가 오류 유형

- `LATE_INFORMATION`: 경기 시작 후 기사·라인업 사용
- `WRONG_TEAM_OR_PLAYER`: 이적·임대/등록/소속 시점 불일치
- `SMALL_SAMPLE_H2H`: 옛 맞대결 표본으로 현재 전술 단정
- `CORRELATED_EVIDENCE`: ORTG/Elo/홈효과 중복 점수
- `POST_HOC_EXPLANATION`: 결과 이후 전문가의 사전 근거 수정
- `UNSUPPORTED_WEIGHT`: 검증 없이 선수·감독 가중치 수치 부여
- `SCORE_TARGET_MISMATCH`: 연장 포함 FINAL과 정규시간 점수 혼동

경기 전 전문가 판단 P0는 불변, 경기 후에는 `expert_audit_events`로
원인 가설·입력 오류·개선 후보를 별도 추가한다. 전문가 수기 선택은
모델 산출확률과 섞지 말고 독립적인 방향/예상스코어/불확실성으로 기록한다.

## 실데이터 연결 조건

- NBA BALLDONTLIE Free: teams/players/games만 기본 접근 가능.
  상세 선수 경기 스탯, 시즌 평균, 부상, 라인업은 유료 엔드포인트이므로
  Free 키로 성공한 것처럼 표시하지 않는다.
- KBL 공식 경기 일정/결과는 결과 원천이 될 수 있으나, 사용권한 확인과
  원시 스냅샷·공개시각 증빙 전에는 FULL_ASOF 실전 학습으로 승격하지 않는다.
- SQLite 실데이터 연결 전 `integrity_check`, `foreign_key_check`,
  fixture_uid 매핑, 홈1/원정1, FINAL 연장 포함, 원본·결과 해시,
  P0 중복·append-only 검사, 선수 시간별 신원을 순서대로 점검한다.
- 경기 종료 후 흐름: 원본 증분 수집 → 결과 공식 확인 → 스냅샷 검증
  → P0/P1/전문가 판단 **각각** 정산 → 오류 태그 → 재학습 후보
  → 미래 동일 시점 shadow 비교 → 수동 승격.
- 모델 성능은 LogLoss/Brier/ECE, 점수 MAE, 기본 모델 대비 차이 및
  날짜블록 CI로 평가. 임의 몇 경기 적중만으로 계수 변경하지 않는다.

## 현재 상태

코드수정: 연구 후보 브랜치 적용.
실제 DB 무결성 검사: **DB 파일 부재로 미실행**.
전체 테스트: CI/회귀 테스트 실행 결과로 별도 판정.
실데이터 재학습: **미실행**.
전문가 판단 재정산: 근거 원장이 없어 **미실행**.
배포/승격: **하지 않음**.

참고: https://docs.balldontlie.io/ ; https://www.kbl.or.kr/match/schedule ;
https://www.nba.com/stats/help/glossary

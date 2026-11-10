"""프로농구 예측 엔진 CLI 진입점 모듈."""

import argparse
import json
import hashlib
import logging
from pathlib import Path
import pandas as pd
from xgboost import XGBRegressor, XGBClassifier

from src.config_loader import ConfigLoader
from src.loader import CsvLoader
from src.features.builder import FeatureBuilder
from src.models.trainer import ModelTrainer
from src.models.ensemble import EnsemblePredictor
from src.service.predictor import PredictionService
from data.sample_generator import SampleDataGenerator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

def train_command(args):
    config = ConfigLoader.load(args.config)
    league = args.league.upper()
    league_cfg = config["league_configs"][league]

    logger.info(f"[{league}] 샘플 데이터 생성 및 학습 파이프라인 시작...")
    gen = SampleDataGenerator(seed=config["seed"])
    df, _ = gen.generate(league=league, n_seasons=2)

    builder = FeatureBuilder(league_cfg, config)
    built_df = builder.build_features(df)

    trainer = ModelTrainer(config, league_cfg)
    
    # 홈 행 데이터 추출 학습
    home_df = built_df[built_df["is_home"] == 1].reset_index(drop=True)
    X = home_df[builder.feature_columns].values
    y_home = home_df["pts"].values
    
    away_pts_map = built_df[built_df["is_home"] == 0].set_index("game_id")["pts"].to_dict()
    home_df["away_pts"] = home_df["game_id"].map(away_pts_map)
    y_away = home_df["away_pts"].values
    y_win = (y_home > y_away).astype(int)

    reg_h = XGBRegressor(n_estimators=50, tree_method="hist", random_state=config["seed"])
    reg_a = XGBRegressor(n_estimators=50, tree_method="hist", random_state=config["seed"])
    clf = XGBClassifier(n_estimators=50, tree_method="hist", random_state=config["seed"])

    reg_h.fit(X, y_home)
    reg_a.fit(X, y_away)
    clf.fit(X, y_win)

    # Walk-Forward CV를 통한 sigma 및 앙상블 가중치 추출
    cv_results = trainer.walk_forward_cv(built_df, builder.feature_columns)
    
    # 아티팩트 저장 경로 설정
    model_dir = Path("models") / league
    model_dir.mkdir(parents=True, exist_ok=True)

    reg_h.save_model(model_dir / "regressor_home.json")
    reg_a.save_model(model_dir / "regressor_away.json")
    clf.save_model(model_dir / "classifier_xgb.json")
    
    with open(model_dir / "calibrator.json", "w", encoding="utf-8") as f:
        json.dump(cv_results["calibrator"].to_dict(), f, ensure_ascii=False, indent=2)

    metadata = {
        "league": league,
        "feature_columns": builder.feature_columns,
        "sigma_margin": cv_results["sigma_margin"],
        "sigma_total": cv_results["sigma_total"],
        "ensemble_w": 0.5,
        "model_status": "SANITY_TESTED",
        "data_evidence_grade": "SYNTHETIC",
        "validation_mode": cv_results["validation_mode"],
        "oof_n": cv_results["oof_n"],
        "trained_until": str(pd.Timestamp(df["date"].max()).date()),
        "artifact_sha256": {
            name: hashlib.sha256((model_dir / name).read_bytes()).hexdigest()
            for name in (
                "regressor_home.json", "regressor_away.json",
                "classifier_xgb.json", "calibrator.json"
            )
        }
    }
    with open(model_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)

    logger.warning("합성 데이터 파이프라인 검증용으로 실제 예측 성능이 아닙니다.")
    logger.info(f"[{league}] 연구용 모델·해시 저장: {model_dir}")

def predict_command(args):
    config = ConfigLoader.load(args.config)
    league = args.league.upper()
    
    gen = SampleDataGenerator(seed=config["seed"])
    df, _ = gen.generate(league=league, n_seasons=1)

    model_dir = Path("models") / league
    service = PredictionService.from_artifacts(model_dir, df, config)

    result = service.predict_game(
        home_team=args.home,
        away_team=args.away,
        game_date=args.date,
        ou_line=args.ou
    )
    print(json.dumps(result, indent=4, ensure_ascii=False))

def main():
    parser = argparse.ArgumentParser(description="프로농구 경기 승패 및 예상 득점 예측 엔진")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Train CLI
    parser_train = subparsers.add_parser("train", help="모델 학습 및 아티팩트 저장")
    parser_train.add_argument("--league", choices=["NBA", "KBL"], default="KBL", help="리그명 (NBA|KBL)")
    parser_train.add_argument("--config", type=str, default="config/config.yaml", help="설정 파일 경로")

    # Predict CLI
    parser_predict = subparsers.add_parser("predict", help="단건 경기 예측")
    parser_predict.add_argument("--league", choices=["NBA", "KBL"], default="KBL", help="리그명 (NBA|KBL)")
    parser_predict.add_argument("--home", type=str, required=True, help="홈팀 이름")
    parser_predict.add_argument("--away", type=str, required=True, help="원정팀 이름")
    parser_predict.add_argument("--date", type=str, required=True, help="경기 날짜 (YYYY-MM-DD)")
    parser_predict.add_argument("--ou", type=float, default=None, help="Over/Under 라인 (예: 165.5)")
    parser_predict.add_argument("--config", type=str, default="config/config.yaml", help="설정 파일 경로")

    args = parser.parse_args()
    if args.command == "train":
        train_command(args)
    elif args.command == "predict":
        predict_command(args)

if __name__ == "__main__":
    main()

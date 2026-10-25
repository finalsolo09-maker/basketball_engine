"""YAML 설정 파일 로드 및 유효성 검증 모듈."""

from pathlib import Path
import yaml
from src.exceptions import ConfigError

class ConfigLoader:
    """설정 파일을 읽고 필수 키를 검증하는 클래스."""

    REQUIRED_KEYS = ["seed", "league_configs", "data", "features", "training", "inference"]

    @classmethod
    def load(cls, config_path: str | Path) -> dict:
        path = Path(config_path)
        if not path.exists():
            raise ConfigError(f"설정 파일이 존재하지 않습니다: {path}")
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
        except Exception as e:
            raise ConfigError(f"YAML 파싱 중 오류가 발생했습니다: {e}")
        
        if not isinstance(config, dict):
            raise ConfigError("설정 파일의 루트는 딕셔너리 형태여야 합니다.")
        
        for key in cls.REQUIRED_KEYS:
            if key not in config:
                raise ConfigError(f"필수 설정 키가 누락되었습니다: {key}")
                
        return config

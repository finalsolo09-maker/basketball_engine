"""데이터 로더 모듈 (BaseDataLoader 및 CsvLoader)."""

from abc import ABC, abstractmethod
from pathlib import Path
import pandas as pd
from src.validator import DataValidator

class BaseDataLoader(ABC):
    """데이터 소스 처리를 위한 추상 베이스 로더."""

    @abstractmethod
    def load_data(self) -> pd.DataFrame:
        pass

class CsvLoader(BaseDataLoader):
    """CSV 파일로부터 경기 로그를 로드하고 검증하는 클래스."""

    def __init__(self, file_path: str | Path, validation_policy: str = "raise"):
        self.file_path = Path(file_path)
        self.validation_policy = validation_policy

    def load_data(self) -> pd.DataFrame:
        if not self.file_path.exists():
            raise FileNotFoundError(f"데이터 파일을 찾을 수 없습니다: {self.file_path}")
        
        df = pd.read_csv(self.file_path)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        
        # 데이터 무결성 검증 수행
        validated_df = DataValidator.validate(df, policy=self.validation_policy)
        return validated_df

"""피처 블록 추상 베이스 클래스 정의 모듈."""

from abc import ABC, abstractmethod
import pandas as pd

class FeatureBlock(ABC):
    """모든 피처 공학 블록의 베이스가 되는 추상 클래스."""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config

    @property
    @abstractmethod
    def columns(self) -> list[str]:
        """이 블록에서 생성되는 피처 컬럼 이름 리스트를 반환합니다."""
        pass

    @abstractmethod
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """데이터프레임에 피처를 계산하여 추가합니다."""
        pass

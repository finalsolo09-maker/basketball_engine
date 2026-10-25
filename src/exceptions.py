"""프로농구 예측 엔진 커스텀 예외 정의 모듈."""

class EngineError(Exception):
    """엔진 기본 예외 클래스."""
    pass

class ConfigError(EngineError):
    """설정 파일 로드 또는 파라미터 유효성 검증 실패 시 발생."""
    pass

class DataValidationError(EngineError):
    """데이터 스키마 또는 무결성 검증 실패 시 발생."""
    pass

class InsufficientDataError(EngineError):
    """학습 또는 검증에 필요한 최소 데이터 수가 부족할 때 발생."""
    pass

class InsufficientHistoryError(EngineError):
    """추론 시 필요한 과거 히스토리 데이터가 부족할 때 발생."""
    pass

class ArtifactMismatchError(EngineError):
    """저장된 모델 아티팩트의 피처 컬럼 및 스키마가 일치하지 않을 때 발생."""
    pass

class ArtifactVersionError(EngineError):
    """아티팩트 생성 시점과 실행 시점의 라이브러리 버전이 호환되지 않을 때 발생."""
    pass

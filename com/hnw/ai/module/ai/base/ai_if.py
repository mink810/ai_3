# ai_if.py
"""
AI 학습 전용 공통 인터페이스 (15-Step Base Interface)

본 모듈은 귀하의 플랫폼에서 합의한 "15단계 표준 프로세스"를
단일 인터페이스로 규정합니다. 각 도구(알고리즘/프레임워크/상용 API)는
이 인터페이스(AiIF)를 구현하여 **모델 생성(학습 전용)**을 수행합니다.
(모델 활용/서빙은 별도 패키지에서 export() 산출물(번들)을 사용)

핵심 원칙
---------
1) **표준 시그니처**: 15개 단계의 메소드 이름/인수/반환 스키마를 통일
2) **도메인 무관**: 11개 카테고리(회귀, 예측, 분류, 랭킹, 이상탐지, OCR,
   영상추적, 얼굴인식, ASR, 화자인식, 최적화)에 공통 적용
3) **No-Op 허용**: backtest(), calibrate() 등 도메인 비적용 단계는
   기본 no-op(건너뜀) 리포트를 반환하도록 설계
4) **재현성/배포성**: export()는 모델+전처리+시그니처+지표+임계치 등
   **번들 아티팩트**를 산출, register()는 레지스트리에 등록
5) **명세 우선**: 본 파일은 "사양 인터페이스"입니다. 실제 로깅/분산/추적 등은
   구현 클래스에서 확장하세요.

반환 타입 요약
--------------
- attach_dataset()  -> DatasetProfile
- prepare_data()    -> str | dict (전처리 아티팩트 ID 또는 메타)
- split()           -> SplitMeta
- build()           -> None (내부 모델 핸들 보유 가정)
- fit()             -> TrainReport
- evaluate()        -> EvalReport
- tune()            -> (best_config: dict, TuningReport)
- backtest()        -> BacktestReport
- calibrate()       -> CalibrationResult
- save_checkpoint() -> Optional[str]  (체크포인트 ID)
- resume()          -> None
- export()          -> ArtifactManifest
- register()        -> str           (model_id)
- artifacts()       -> ArtifactMap
- close()           -> None
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

try:
    from typing import TypedDict, Literal
except ImportError:  # Python <3.8 호환(형 선언만 유지)
    TypedDict = dict  # type: ignore
    Literal = str     # type: ignore

# ----------------------------------------------------------------------
# 공통 타입 (경량 스펙)
# ----------------------------------------------------------------------
JSONLike = Union[Dict[str, Any], List[Any], str, int, float, bool, None]
PathLike = Union[str, "os.PathLike[str]"]
Stage = Literal["dev", "staging", "canary", "prod"]


class DatasetProfile(TypedDict, total=False):
    """데이터셋 연결·검증 결과 요약"""
    fingerprint: str                 # 데이터 지문(경로/해시 기반)
    num_rows: int                    # 샘플 수(또는 프레임/클립 수)
    num_files: int                   # 파일 수(이미지/비디오/오디오 등)
    schema_valid: bool               # 스키마 일치 여부
    warnings: List[str]              # 경고(결측/해상도 불일치 등)
    stats: Dict[str, Any]            # 기본 통계(분포/빈도/길이 등)


class SplitMeta(TypedDict, total=False):
    """학습/검증/테스트 분할(또는 CV 폴드) 메타데이터"""
    strategy: Dict[str, Any]         # stratified/group/rolling/… 파라미터
    sets: Dict[str, int]             # {"train": N, "valid": M, "test": K, ...}
    info: Dict[str, Any]             # 기타: 기간/그룹키/폴드 정의 등


class TrainReport(TypedDict, total=False):
    """학습 보고서"""
    best_checkpoint_id: Optional[str]  # 최적 모델 체크포인트 ID(없으면 None)
    epochs: int                        # 총 학습 에폭 수(또는 반복 수)
    metrics: Dict[str, float]          # 최종/최적 지표 (예: AUROC, RMSE 등)
    history: List[Dict[str, float]]    # 에폭별 기록(손실/지표 타임라인)
    wall_time_sec: float               # 총 소요 시간(초 단위)


class EvalReport(TypedDict, total=False):
    """평가 보고서"""
    metrics: Dict[str, float]          # {"AUROC": 0.98, "Recall@FPR=1%": 0.95, ...}
    confusion_matrix: Optional[List[List[int]]]  # (선택) 혼동행렬; 이진=[[TN,FP],[FN,TP]], 다중클래스=N×N
    curves: Dict[str, str]             # ROC/PR 등 곡선 파일 경로 또는 URI
    notes: Optional[str]               # 특이사항/오류사례 경로 등 자유 메모


class TuningReport(TypedDict, total=False):
    """하이퍼파라미터 탐색 보고서"""
    trials: List[Dict[str, Any]]       # 실험 이력(각 트라이얼 config/score 등)
    best_score: float                  # 최고 점수(목표 지표 기준)
    best_config: Dict[str, Any]        # 최고 점수의 설정(config)
    budget_used: Dict[str, Any]        # {"time_sec": , "num_trials": , ...} 사용 예산 요약


class BacktestReport(TypedDict, total=False):
    """시간순/시나리오 재현 평가 보고서"""
    skipped: bool                      # 백테스트 수행 여부(False면 수행)
    reason: Optional[str]              # 미수행 사유(필요 시)
    windows: Optional[List[Dict[str, Any]]]  # (선택) 윈도우별 성능/기간/설정 목록
    summary: Optional[Dict[str, Any]]        # (선택) 전체 요약(평균/분산/드리프트 신호 등)


class CalibrationResult(TypedDict, total=False):
    """임계치/확률 보정 결과"""
    skipped: bool                      # 보정 수행 여부(False면 수행)
    reason: Optional[str]              # 미수행 사유(필요 시)
    thresholds: Dict[str, float]       # {"score": 0.73, "low": 0.68, "high": 0.78} 등 임계치 값
    params: Dict[str, Any]             # 보정 파라미터(Platt, Isotonic, 듀얼스레시홀드 등)


class ArtifactFile(TypedDict, total=False):
    """아티팩트 단일 파일 메타"""
    path: str                          # 파일 경로(로컬/URI)
    sha256: Optional[str]              # 무결성 검사용 해시(선택)
    size: Optional[int]                # 파일 크기(byte, 선택)
    role: str                          # model/preprocessor/metrics/thresholds/signature/log 등 역할


class ArtifactManifest(TypedDict, total=False):
    """export()가 반환하는 번들 목록"""
    files: List[ArtifactFile]          # 포함된 파일들의 메타 리스트
    created_at: str                    # 생성 시각(ISO8601 권장)
    signature_path: Optional[str]      # signature.json 경로(없으면 None)
    extras: Dict[str, Any]             # 환경/의존성/코드해시/라이선스 등 부가 정보


class ArtifactMap(TypedDict, total=False):
    """artifacts() 조회용 핵심 파일 맵"""
    model: Optional[str]               # 모델 가중치/그래프 경로
    preprocessor: Optional[str]        # 전처리 아티팩트 경로
    label_map: Optional[str]           # 라벨/클래스 매핑 파일 경로
    tokenizer: Optional[str]           # 토크나이저/사전(해당 시)
    metrics: Optional[str]             # metrics.json 경로
    thresholds: Optional[str]          # thresholds.json 경로(해당 시)
    training_log: Optional[str]        # 학습 로그 경로
    requirements: Optional[str]        # requirements.txt/conda.yaml 등
    signature: Optional[str]           # signature.json 경로(I/O 스키마)
    data_fingerprint: Optional[str]    # 데이터 지문/출처 기록 경로

# ----------------------------------------------------------------------
# 표준 예외 (권장 에러 코드)
# ----------------------------------------------------------------------
class AiError(RuntimeError):
    """플랫폼 표준 AI 예외의 베이스 (code 필드 포함)"""
    code: str = "AI_ERROR"

    def __init__(self, message: str, *, code: Optional[str] = None, info: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        if code:
            self.code = code
        self.info = info or {}


class DataSchemaError(AiError):
    """스키마 검증 실패(필드 누락/형 불일치/역할 매핑 오류 등)"""
    code = "DATA_SCHEMA_ERROR"


class ResourceLimitError(AiError):
    """리소스 부족(GPU 메모리/시간 제한/파일 핸들 등)"""
    code = "RESOURCE_LIMIT"


class ConvergenceError(AiError):
    """수렴 실패/학습 중단(발산/NaN/Loss stagnation)"""
    code = "CONVERGENCE_FAIL"


class ExportError(AiError):
    """아티팩트 내보내기 실패(직렬화/형식/권한)"""
    code = "EXPORT_ERROR"


class CalibrationError(AiError):
    """캘리브레이션 실패(목표 운영점 불달/데이터 부족 등)"""
    code = "CALIBRATION_FAIL"


# ----------------------------------------------------------------------
# 콜백(선택): 학습 상태 브로드캐스트 용도
# ----------------------------------------------------------------------
Callback = Optional[callable]


# ----------------------------------------------------------------------
# 15단계 공통 학습 인터페이스
# ----------------------------------------------------------------------
class AiIF(ABC):
    """
    15-스텝 공통 학습 인터페이스의 베이스 클래스.

    구현 클래스는 최소한 다음을 오버라이드하는 것을 권장합니다.
      - 필수: configure, attach_dataset, prepare_data, split,
              build, fit, evaluate, export, register, artifacts, close
      - 선택(no-op 기본 제공): tune, backtest, calibrate,
                              save_checkpoint, resume

    메서드들의 인수는 Dict[str, Any] 기반으로 느슨하게 정의합니다.
    (플랫폼 상위에서 JSON/YAML 구성과 직결시키기 위함)
    """

    def __init__(self) -> None:
        """
        인스턴스 초기화.
        - _state: 단계 상태 머신 (INIT → CONFIGURED → DATA_ATTACHED → PREPARED →
                 SPLIT → BUILT → FITTED → EVALUATED → (TUNED/BACKTESTED/CALIBRATED) →
                 EXPORTED → REGISTERED → CLOSED)
        - _last: 마지막 보고서/매니페스트 캐시 (read-only property로 노출)
        """
        self._state: str = "INIT"
        self._last: Dict[str, Any] = {
            "dataset_profile": None,
            "split_meta": None,
            "train_report": None,
            "eval_report": None,
            "tuning_report": None,
            "backtest_report": None,
            "calibration_result": None,
            "artifact_manifest": None,
            "model_id": None,
            "artifact_map": None,
        }

    @property
    def state(self) -> str:
        """현재 단계 상태를 조회합니다. (예: 'INIT', 'CONFIGURED', ... , 'CLOSED')"""
        return self._state

    def _set_state(self, new_state: str) -> None:
        """
        내부 상태 전이를 설정합니다. 구현체는 각 단계 종료 시 호출하여
        상태 머신을 일관되게 유지할 수 있습니다.
        (상태 강제는 하지 않으며, 오케스트레이터에서 검증 가능)
        """
        self._state = new_state

    @property
    def last_reports(self) -> Dict[str, Any]:
        """
        마지막 보고서/매니페스트 캐시를 읽기 전용으로 제공합니다.
        키: dataset_profile / split_meta / train_report / eval_report /
            tuning_report / backtest_report / calibration_result /
            artifact_manifest / model_id / artifact_map
        """
        return {k: self._last.get(k) for k in self._last.keys()}

    def on_event(self, event: str, payload: Dict[str, Any]) -> None:
        """
        단계별 훅(선택). 구현체가 필요 시 오버라이드하여
        로깅/브로드캐스트/계량(telemetry)을 수행할 수 있습니다.
        예: on_event("fit:start", {"config": ...}), on_event("fit:end", {"report": ...})
        """
        return None

    # 1) 런타임/리소스/로깅 구성 -------------------------------------------
    @abstractmethod
    def configure(self, config: Dict[str, Any]) -> None:
        """
        예: {"device": "cuda:0", "seed": 42, "log_dir": "...", "checkpoint_dir": "...",
             "num_workers": 8, "mixed_precision": True, "timeout_sec": 3600, ...}

        Raises
        ------
        ResourceLimitError: 요청 자원이 가용 범위를 초과한 경우
        """

    # 2) 데이터셋 연결/검증 -------------------------------------------------
    @abstractmethod
    def attach_dataset(self, dataset_ref: Any, schema: Dict[str, Any]) -> DatasetProfile:
        """
        학습/검증에 사용할 데이터셋을 연결하고 스키마를 검증합니다.
        도메인별 필수 필드(예: image/label/time/qid 등)를 확인하고
        데이터 지문(fingerprint)/요약 통계를 생성합니다.

        Raises
        ------
        DataSchemaError: 필수 필드/역할 매핑 누락 또는 형 불일치
        """

    # 3) 전처리/증강 파이프라인 구축 ----------------------------------------
    @abstractmethod
    def prepare_data(self, options: Dict[str, Any]) -> Union[str, Dict[str, Any]]:
        """전처리 파이프라인을 구성/적합(fit)하고 아티팩트 ID 또는 메타를 반환합니다."""

    # 4) 분할/폴드 -----------------------------------------------------------
    @abstractmethod
    def split(self, strategy: Dict[str, Any]) -> SplitMeta:
        """학습/검증/테스트 분할 또는 교차검증 폴드를 생성합니다."""

    # 5) 모델/알고리즘 빌드 --------------------------------------------------
    @abstractmethod
    def build(self, model_spec: Dict[str, Any]) -> None:
        """알고리즘/아키텍처/손실 등을 선택하고 내부 모델 핸들을 초기화합니다."""

    # 6) 학습/적합 ------------------------------------------------------------
    @abstractmethod
    def fit(self, train_config: Dict[str, Any], callbacks: Optional[List[Callback]] = None) -> TrainReport:
        """체크포인트/조기종료/스케줄러 등을 포함한 실제 학습을 수행합니다."""

    # 7) 평가 -----------------------------------------------------------------
    @abstractmethod
    def evaluate(self, eval_sets: Union[Sequence[str], Dict[str, Any]], metrics: Union[Sequence[str], Dict[str, Any]]) -> EvalReport:
        """검증/테스트/홀드아웃 세트를 평가해 지표/커브/혼동행렬(해당 시)을 반환합니다."""

    # 8) 튜닝(선택) -----------------------------------------------------------
    def tune(self, search_space: Dict[str, Any], tuner_cfg: Dict[str, Any]) -> Tuple[Dict[str, Any], TuningReport]:
        """하이퍼파라미터 탐색(no-op 기본 구현)."""
        report: TuningReport = {
            "trials": [],
            "best_score": 0.0,
            "best_config": {},
            "budget_used": {"time_sec": 0.0, "num_trials": 0},
        }
        return {}, report

    # 9) 백테스트(선택) -------------------------------------------------------
    def backtest(self, bt_cfg: Dict[str, Any]) -> BacktestReport:
        """시간 순서 보존 평가/시나리오 재현(no-op 기본 구현)."""
        return {"skipped": True, "reason": "no-op in base AiIF", "windows": None, "summary": None}

    # 10) 캘리브레이션(선택) ---------------------------------------------------
    def calibrate(self, calib_cfg: Dict[str, Any]) -> CalibrationResult:
        """임계치/확률 보정(no-op 기본 구현)."""
        return {"skipped": True, "reason": "no-op in base AiIF", "thresholds": {}, "params": {}}

    # 11) 체크포인트 저장(선택) -----------------------------------------------
    def save_checkpoint(self, tag: Optional[str] = None) -> Optional[str]:
        """중간 상태 저장(no-op 기본 구현)."""
        return None

    # 11-2) 재개(선택) --------------------------------------------------------
    def resume(self, checkpoint_id: str) -> None:
        """이전 체크포인트에서 학습 재개(no-op 기본 구현)."""
        return None

    # 12) 아티팩트 내보내기 ----------------------------------------------------
    @abstractmethod
    def export(self, target_uri: PathLike, formats: Union[str, Sequence[str]], include_preproc: bool = True) -> ArtifactManifest:
        """배포 번들(모델/전처리/시그니처/지표/임계치/요구사항 등)을 산출합니다."""

    # 13) 레지스트리 등록 ------------------------------------------------------
    @abstractmethod
    def register(self, name: str, version: str, stage: Stage = "staging", tags: Optional[Dict[str, str]] = None) -> str:
        """모델 레지스트리에 등록하고 model_id를 반환합니다."""

    # 14) 아티팩트 맵 조회 -----------------------------------------------------
    @abstractmethod
    def artifacts(self) -> ArtifactMap:
        """핵심 아티팩트(모델, 전처리, 지표, 임계치 등)의 경로 맵을 반환합니다."""

    # 15) 리소스 정리 ----------------------------------------------------------
    @abstractmethod
    def close(self) -> None:
        """세션/리소스를 정리합니다. (파일 핸들, 디코더, 프로세스, GPU 메모리 등)"""

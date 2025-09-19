# com/hnw/ai/core/service/ai_service_manager.py
# -*- coding: utf-8 -*-
"""
AIServiceManager - AI 모델 서비스 매니저

AI 모델 ID로 구현체를 선택/생성하고 설정을 로드합니다.
"""

import json
import importlib
from pathlib import Path
from typing import Dict, Any

from com.hnw.ai.module.ai.base.ai_if import AiIF


# 프로젝트 루트 계산
ROOT_DIR = Path(__file__).resolve().parents[5]
AI_CONFIG_PATH = ROOT_DIR / "com" / "hnw" / "ai" / "config" / "ai" / "ai_config.json"


def _load_json(path: Path) -> Dict[str, Any]:
    """JSON 파일 로드"""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _new_from_classpath(class_path: str):
    """클래스 경로로 모듈/클래스 로드"""
    module_name, class_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def _default_class_path_for_type(atype: str) -> str:
    """AI 타입별 기본 클래스 경로 반환"""
    atype = (atype or "").lower()
    mapping = {
        "image_classification": "com.hnw.ai.module.ai.mod.분류.image_classifier.ImageClassifier",
        "regression": "com.hnw.ai.module.ai.mod.회귀.regression_model.RegressionModel",
        "prediction": "com.hnw.ai.module.ai.mod.예측.prediction_model.PredictionModel",
    }
    cp = mapping.get(atype)
    if not cp:
        raise ValueError(f"[AI] 미지원 타입: {atype}")
    return cp


class AIServiceManager:
    """AI 서비스 매니저"""
    
    @staticmethod
    def get_by_id(ai_id: str) -> AiIF:
        """
        AI ID로 구현체를 선택/생성
        
        절차:
          1) ai_config.json에서 id 매칭 엔트리 찾기
          2) type/config_file 확인
          3) 환경 config 로드
          4) 구현체 생성 후 configure(config)
        """
        if not AI_CONFIG_PATH.exists():
            raise FileNotFoundError(f"ai_config.json not found: {AI_CONFIG_PATH}")
        
        cfg = _load_json(AI_CONFIG_PATH)
        entry = next((a for a in cfg.get("ai_models", [])
                     if a.get("id").lower() == ai_id.lower()), None)
        if not entry:
            raise ValueError(f"[AI] unknown id: {ai_id}")
        
        atype = entry.get("type")
        config_file = entry.get("config_file")
        if not atype or not config_file:
            raise ValueError(f"[AI] type/config_file required for id={ai_id}")
        
        # 환경 설정 로드
        config_path = (AI_CONFIG_PATH.parent / config_file).resolve()
        if not config_path.exists():
            raise FileNotFoundError(f"[AI] config not found: {config_path}")
        aconf: Dict = _load_json(config_path)
        
        # 클래스 경로 결정
        class_path = _default_class_path_for_type(atype)
        
        # 구현체 생성
        klass = _new_from_classpath(class_path)
        ai_instance = klass()
        
        # 설정 적용
        if hasattr(ai_instance, "configure") and callable(getattr(ai_instance, "configure")):
            ai_instance.configure(aconf)
        
        return ai_instance



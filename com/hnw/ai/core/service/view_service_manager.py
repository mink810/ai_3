"""
ViewServiceManager

- view_id → view_config.json에서 (type, config_file[, class_path]) 조회
- 환경 config(dev/prod) 로드 후 class_path를 결정, type에 따른 기본 경로만 사용 (_default_class_path_for_type)
- 구현체 생성 후 (있다면) connect(config) 호출하여 초기화하고 반환.
"""

import json
import importlib
from pathlib import Path
from typing import Dict, Any, Optional
from com.hnw.ai.view.base.view_if import ViewIF

# 프로젝트 루트 계산: __file__ 기준 상위 5단계 ( .../com/hnw/ai/... )
ROOT_DIR = Path(__file__).resolve().parents[5]

# 예: com/hnw/ai/config/view/view_config.json  형태로 관리한다고 가정
VIEW_CONFIG_PATH = ROOT_DIR / "com" / "hnw" / "ai" / "config" / "view" / "view_config.json"


def _load_json(path: Path) -> Dict[str, Any]:
    """JSON 파일 로드 도우미"""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _new_from_classpath(class_path: str):
    """
    class_path로 모듈/클래스를 로드하고 인스턴스를 생성한다.
    :param class_path: "com...." 절대 import 경로
    :return: 인스턴스
    """
    module_name, class_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)  


def _default_class_path_for_type(vtype: str) -> str:
    """
    시각화 타입별 기본 클래스 경로 반환.
    필요에 맞게 실제 구현 경로로 교체하세요.
    """
    vtype = (vtype or "").lower()
    mapping = {
        # Tkinter 기반 구현체 가정
        "tkinter": "com.hnw.ai.view.mod.project1.tkinter.tkinter_view.TkinterView",
        "html": "com.hnw.ai.view.mod.project1.html.html_view.HTMLView",
        "react": "com.hnw.ai.view.mod.project1.react.react_view.ReactView",
        "vue": "com.hnw.ai.view.mod.project1.vue.vue_view.VueView",
        # 이미지 분류 전용 뷰
        "image_classification": "com.hnw.ai.view.mod.project2.tkinter.image_classification_view.ImageClassificationView",
        # 예: Streamlit, Web 등 확장 가능
        # "web": "com.hnw.ai.view.project1.mod.web.web_view.WebView",
    }
    cp = mapping.get(vtype)
    if not cp:
        raise ValueError(f"[view] unsupported type: {vtype}")
    return cp


class ViewServiceManager:
    """
    시각화 서비스 매니저
    - view_id로 구현체를 선택/생성하고 (있다면) connect(config)까지 수행하여 반환
    """

    @staticmethod
    def get_by_id(view_id: str) -> ViewIF:
        """
        view_id로 구현체를 선택/생성한다.

        절차:
          1) view_config.json에서 id 매칭 엔트리 찾기
          2) type/config_file 확인
          3) 환경 config 로드(예: view/tk/dev.json)
          4) class_path 결정: type에 따른 기본 경로만 사용 (_default_class_path_for_type)
          5) 구현체 생성 후 (있으면) connect(config)

        :param view_id: 예) "view_tk_dev"
        :return: 시각화 구현체 인스턴스(필요 시 connect됨)
        """
        # 1) 인덱스 파일 존재 확인 및 로드
        if not VIEW_CONFIG_PATH.exists():
            raise FileNotFoundError(f"[view] view_config.json not found: {VIEW_CONFIG_PATH}")
        cfg = _load_json(VIEW_CONFIG_PATH)

        # 2) id 매칭
        views = cfg.get("views", [])
        entry: Optional[Dict[str, Any]] = next(
            (v for v in views if str(v.get("id", "")).lower() == str(view_id).lower()),
            None
        )
        if not entry:
            raise ValueError(f"[view] unknown id: {view_id}")

        vtype: str = entry.get("type", "")
        vconfig_file: str = entry.get("config_file", "")
        if not vtype or not vconfig_file:
            raise ValueError(f"[view] type/config_file required for id={view_id}")

        # 3) 환경 config 로드
        conf_path = (VIEW_CONFIG_PATH.parent / vconfig_file).resolve()
        if not conf_path.exists():
            raise FileNotFoundError(f"[view] env config not found: {conf_path}")
        vconf: Dict[str, Any] = _load_json(conf_path)

        # 4) class_path 우선순위
        class_path = _default_class_path_for_type(vtype)

        # 5) 인스턴스 생성 및 (있으면) connect(config)
        klass = _new_from_classpath(class_path)   
        
        try:
            # vtype을 요구하는 구현체 대응 (예: TkinterView(vtype: str))
            view = klass(vtype)
        except TypeError:
            # 무인자 생성자만 있는 구현체 폴백
            view = klass()
            
        # view 인스턴스 생성
        if hasattr(view, "connect") and callable(getattr(view, "connect")):    # view 인스턴스에 connect 메소드가 있는 경우에는 callable이 참을 반환 
            view.connect(vconf)                                                # vconf 즉, view 객체를 활성화하는데 필요한 딕셔너리 정보를 통해 해당 view 도구 초기화
        return view                                                            # connect가 있는 경우에는 실행하고 반환, 없더라도 객체 반환은 무조건 수행

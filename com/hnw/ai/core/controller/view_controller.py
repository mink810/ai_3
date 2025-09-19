# -*- coding: utf-8 -*-
"""
ViewController (close 통일 버전)

역할
- ViewServiceManager로부터 단일 시각화 서비스(ViewIF 구현체)를 생성/보관하고,
  상위 계층(main, 워크플로)이 사용할 통일 API(push/push_many/start/close)를 제공합니다.

정리 내용
- 종료/정리 메서드는 close()로만 통일합니다.
  (ViewIF 및 TkinterView가 close()를 제공하므로 인터페이스와 정합)
"""

from com.hnw.ai.core.service.view_service_manager import ViewServiceManager
from com.hnw.ai.module.view.base.view_if import ViewIF  # ViewIF: __init__, connect, start, is_connected, close


class ViewController:
    """
    시각화 컨트롤러(1:1 위임).
    - self.view_svc: ViewIF 구현체 인스턴스
    """

    def __init__(self, view_id: str):
        """
        :param view_id: 시각화 서비스 식별자 (예: "view_tk_dev")
        """
        self.view_id = view_id
        self.view_svc: ViewIF = viewServiceManager.get_by_id(self.view_id)

    # -----------------------------
    # 데이터 전달
    # -----------------------------
    def push(self, item):
        """
        단일 이벤트 전달.
        구현체가 push를 제공하지 않으면 no-op.
        """
        if hasattr(self.view_svc, "push"):
            return self.view_svc.push(item)
        return None

    def push_many(self, items):
        """
        배치 이벤트 전달.
        구현체가 push_many를 제공하지 않으면 push로 폴백.
        """
        if hasattr(self.view_svc, "push_many"):
            return self.view_svc.push_many(items)
        if hasattr(self.view_svc, "push"):
            for it in items:
                self.view_svc.push(it)
        return None

    # -----------------------------
    # 실행/종료 제어 (close로 통일)
    # -----------------------------
    def start(self):
        """
        시각화 루프(또는 런루프) 시작.
        """
        if hasattr(self.view_svc, "start"):
            return self.view_svc.start()
        return None

    def close(self):
        """
        시각화 종료/정리: close()로 통일.
        """
        if hasattr(self.view_svc, "close"):
            try:
                return self.view_svc.close()
            except Exception:
                return None
        return None

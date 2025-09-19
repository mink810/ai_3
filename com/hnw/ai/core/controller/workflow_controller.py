# com/hnw/ai/core/controller/workflow_controller.py
# -*- coding: utf-8 -*-
"""
WorkflowController
- 드라이버 신호를 저장(on_signal)하고, 저장 직후 해당 포트→데이터소스 매핑으로 즉시 조회하여
  등록된 result handler(UiGateway)에 푸시합니다.
- 조회 메서드는 전 계층 'fetch_for_datasource'로 통일.
"""

from __future__ import annotations

import time
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

# UiGateway로 푸시할 콜백 타입
ResultHandlerT = Callable[[str, List[Dict[str, Any]], Optional[List[str]]], None]


class WorkflowController:
    """가변 인자(*controllers)로 Storage/Driver 컨트롤러를 수집합니다."""

    def __init__(self, *controllers: Any) -> None:
        self._storages: List[Any] = []
        self._drivers:  List[Any] = []
        self._storage: Optional[Any] = None

        for c in controllers:
            if c is None:
                continue
            if self._is_storage_controller(c):
                self._storages.append(c)
            elif self._is_driver_controller(c):
                self._drivers.append(c)

        if self._storages:
            self._storage = self._storages[0]

        self._listening: bool = False
        self._result_handler: Optional[ResultHandlerT] = None  # ★ UiGateway가 등록

    # ───── UiGateway가 콜백 등록 ─────
    def set_result_handler(self, handler: ResultHandlerT) -> None:
        """저장 직후 조회 결과를 전달할 핸들러(UiGateway)를 등록합니다."""
        self._result_handler = handler

    # ───── 드라이버 → 저장(+즉시 조회 푸시) ─────
    def on_signal(self, payload: Dict[str, Any]) -> None:
        """드라이버 콜백 신호를 스토리지에 즉시 저장한 뒤, 해당 데이터소스를 즉시 조회하여 푸시합니다."""
        if not self._storage:
            return
        try:
            # 1) 저장
            self._storage.store(payload)  # (ok, key_info) 반환이어도 여기선 무시

            # 2) 어떤 데이터소스를 갱신할지 결정(포트→ds 매핑)
            ds_id = self._map_port_to_ds(payload.get("port"))
            if not ds_id:
                return

            # 3) 방금 시각 기준으로 조회
            rows, cols = self.fetch_for_datasource(ds_id, {"ts": time.time()})

            # 4) UiGateway로 푸시(등록된 경우)
            if self._result_handler:
                try:
                    self._result_handler(ds_id, rows, cols)
                except Exception as e:
                    print(f"[WorkflowController] result handler push 실패: {e}")
        except Exception as e:
            print(f"[WorkflowController] on_signal 실패: {e}")

    def start_listen(self) -> None:
        """모든 드라이버 start_listen을 개별 스레드로 병렬 기동."""
        if getattr(self, "_listening", False):
            print("[WorkflowController] start_listen: already listening")
            return

        self._listen_threads = []  # 스레드 보관
        for drv in self._drivers:
            try:
                if hasattr(drv, "start_listen") and callable(drv.start_listen):
                    t = threading.Thread(
                        target=drv.start_listen,
                        args=(self.on_signal,),
                        daemon=True,
                        name=f"driver-listen-{getattr(drv, 'driver_id', 'unknown')}"
                    )
                    t.start()
                    self._listen_threads.append(t)
                    print(f"[WorkflowController] start_listen: thread started for {getattr(drv,'driver_id','unknown')}")
            except Exception as e:
                print(f"[WorkflowController] start_listen 실패: {e}")

        self._listening = True  # 마지막에 True

    def stop_listen(self) -> None:
        """모든 드라이버 리스너/스레드 종료."""
        if not getattr(self, "_listening", False):
            return

        # 드라이버에게 정지 신호
        for drv in self._drivers:
            try:
                if hasattr(drv, "stop") and callable(drv.stop):
                    drv.stop()
            except Exception as e:
                print(f"[WorkflowController] stop_listen 실패: {e}")

        # (옵션) 짧게 join
        try:
            for t in getattr(self, "_listen_threads", []):
                t.join(timeout=0.2)
        except Exception:
            pass

        self._listening = False

    # ───── UiGateway ←→ 조회 (단일 진입점) ─────
    def fetch_for_datasource(
        self,
        datasource_id: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[List[str]]]:
        """
        UiGateway가 호출하는 표준 조회 메서드.
        - datasource_id를 가공하지 않고 StorageController.fetch_for_datasource(...)에 위임합니다.
        """
        if not self._storage:
            return [], None

        opts: Dict[str, Any] = dict(options or {})
        if "ts" not in opts:
            opts["ts"] = time.time()

        try:
            ret = self._storage.fetch_for_datasource(datasource_id, opts)
            if ret is None:
                return [], None
            return ret
        except Exception as e:
            print(f"[WorkflowController] fetch_for_datasource 위임 실패: {e}")
            return [], None

    # ───── 내부 유틸 ─────
    @staticmethod
    def _map_port_to_ds(port: Any) -> Optional[str]:
        try:
            p = int(port)
        except Exception:
            return None
        if p == 5021:
            return "ds_top"
        if p == 5022:
            return "ds_bottom"
        return None

    @staticmethod
    def _is_storage_controller(obj: Any) -> bool:
        return any(
            hasattr(obj, name) and callable(getattr(obj, name))
            for name in ("store", "fetch_for_datasource")
        )

    @staticmethod
    def _is_driver_controller(obj: Any) -> bool:
        return any(
            hasattr(obj, name) and callable(getattr(obj, name))
            for name in ("start_listen", "stop")
        )

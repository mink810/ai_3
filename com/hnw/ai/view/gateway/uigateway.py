# com/hnw/ai/view/gateway/uigateway.py
# -*- coding: utf-8 -*-
"""
UiGateway
- View로부터 전달받은 datasource_id를 WorkflowController로 넘기고,
  (rows, columns)를 받아 View.on_rows(...)에 즉시 전달합니다.
- 조회 경로는 'fetch_for_datasource' 단일 메서드로 통일합니다.
- ★ 변경점: "단일 콜백 제공자" 역할 추가
  - get_callback(): Callable[[ds_id, rows, columns], None]을 외부(Workflow/다른 컨트롤러)에 제공
  - register_callback(): 추가 콜백을 등록하여 fan-out 가능
  - 내부 _emit(): View.on_rows(...) + 등록 콜백들로 동일 데이터 전달
- 이벤트 타입/역할 구분 없음: 데이터 그대로 흐르게 함.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

# 인터페이스/뷰
from com.hnw.ai.view.base.uigateway_if import UiGatewayIF
from com.hnw.ai.view.base.view_if import ViewIF

# 사전 지정 컨트롤러 ID (필요 시 connect(config)로 override 가능)
STORAGE_ID: List[str] = ["ods_oracle_dev"]
DRIVER_ID:  List[str] = ["modbus_dev_1", "modbus_dev_2"]

from com.hnw.ai.core.controller.storage_controller import StorageController
from com.hnw.ai.core.controller.driver_controller import DriverController
# WorkflowController는 _ensure_workflow()에서 lazy import

# 콜백 시그니처: (datasource_id, rows, columns) → None
ResultCallbackT = Callable[[str, List[Dict[str, Any]], Optional[List[str]]], None]


class UiGateway(UiGatewayIF):
    """UiGateway 구현체(비동기 조회 + 단일 콜백 제공자)."""

    def __init__(self, max_workers: int = 2) -> None:
        self._view: Optional[ViewIF] = None
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._closed = False

        self._workflow = None
        self._workflow_listening: bool = False
        self._controllers_built: bool = False
        self._storage_list: List[StorageController] = []
        self._driver_list:  List[DriverController] = []

        self._override_storage_ids: Optional[List[str]] = None
        self._override_driver_ids:  Optional[List[str]] = None

        # 추가 콜백(fan-out 용) 보관
        self._extra_callbacks: List[ResultCallbackT] = []

    # ───── 수명주기/설정 ─────
    def attach_view(self, view: ViewIF) -> None:
        """결과를 전달할 View를 주입합니다."""
        self._view = view

    def connect(self, config: Optional[Dict[str, object]] = None) -> bool:
        """
        config 예:
        {
          "controllers": {
            "storage_ids": ["ods_oracle_dev"],
            "driver_ids":  ["modbus_dev_1", "modbus_dev_2"]
          }
        }
        """
        if config:
            ctrl = (config or {}).get("controllers", {})  # type: ignore[assignment]
            if isinstance(ctrl, dict):
                sid = ctrl.get("storage_ids")
                did = ctrl.get("driver_ids")
                if isinstance(sid, list) and sid:
                    self._override_storage_ids = [str(x) for x in sid if str(x).strip()]
                    self._controllers_built, self._workflow = False, None
                if isinstance(did, list) and did:
                    self._override_driver_ids  = [str(x) for x in did if str(x).strip()]
                    self._controllers_built, self._workflow = False, None
        return True

    # ───── 외부(Workflow/다른 컨트롤러 포함)로 제공할 "단일 콜백" ─────
    def get_callback(self) -> ResultCallbackT:
        """
        이 콜백을 WorkflowController 또는 다른 컨트롤러/모듈에 넘겨주세요.
        호출자는 단지 callback(ds_id, rows, columns)만 호출하면 됩니다.
        UiGateway는 내부적으로 View.on_rows(...) 및 등록 콜백들에 동일 데이터 전달(_emit).
        """
        def _cb(datasource_id: str, rows: List[Dict[str, Any]], columns: Optional[List[str]] = None) -> None:
            self._emit(datasource_id, rows, columns)
        return _cb

    def register_callback(self, callback: ResultCallbackT) -> None:
        """필요 시 추가 callback을 등록하여 fan-out합니다."""
        if callable(callback):
            self._extra_callbacks.append(callback)

    # ───── 조회 트리거 ───── (UI에서 호출)
    def request_data(self, datasource_id: str, options: Optional[Dict[str, object]] = None) -> None:
        """
        기존 로직 유지:
        - 비동기로 WorkflowController.fetch_for_datasource(...) 호출
        - 결과를 View.on_rows(...)에 전달
        """
        if self._closed:
            return
        self._executor.submit(self._do_request, datasource_id, dict(options or {}))

    def close(self) -> None:
        """스레드풀/리스너 종료."""
        self._closed = True
        try:
            if self._workflow and hasattr(self._workflow, "stop_listen"):
                self._workflow.stop_listen()
                self._workflow_listening = False
        except Exception:
            pass
        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

    # ───── 내부 구현 ─────
    def _do_request(self, datasource_id: str, options: Dict[str, object]) -> None:
        """
        1) WorkflowController.fetch_for_datasource(datasource_id) 호출
        2) 결과를 단일 경로(_emit)로 전달 → View.on_rows(...) + 등록 콜백들
        """
        rows: List[Dict[str, Any]] = []
        columns: Optional[List[str]] = None

        try:
            wf = self._ensure_workflow()
            if wf is not None and hasattr(wf, "fetch_for_datasource"):
                try:
                    ret = wf.fetch_for_datasource(datasource_id, options)
                    rows, columns = self._normalize_result(ret)
                except Exception as e:
                    print(f"[UiGateway] workflow.fetch_for_datasource 실패: {e}")
            else:
                print("[UiGateway] WorkflowController가 없거나 fetch_for_datasource를 제공하지 않습니다.")
        except Exception as e:
            print(f"[UiGateway] 요청 처리 실패: id={datasource_id} err={e}")

        # 단일 데이터 경로
        self._emit(datasource_id, rows, columns)

    def _emit(self, datasource_id: str, rows: List[Dict[str, Any]], columns: Optional[List[str]] = None) -> None:
        """
        단일 데이터 방출 경로:
        - View.on_rows(...)
        - 등록된 추가 콜백들(register_callback)
        """
        # 1) View로
        try:
            if self._view:
                self._view.on_rows(datasource_id, rows, columns)
        except Exception as e:
            print(f"[UiGateway] view.on_rows 실패: id={datasource_id} err={e}")

        # 2) 추가 콜백들로 fan-out
        if self._extra_callbacks:
            for cb in list(self._extra_callbacks):
                try:
                    cb(datasource_id, rows, columns)
                except Exception as e:
                    print(f"[UiGateway] callback 실패: id={datasource_id} err={e}")

    def _ensure_workflow(self):
        """
        WorkflowController 인스턴스를 확보하고,
        - ★ result handler(단일 콜백)를 항상 등록
        - ★ start_listen()을 1회 보장
        """
        # 이미 캐시된 경우
        if self._workflow is not None:
            wf = self._workflow
            # (보강) 콜백 등록 보장
            try:
                if hasattr(wf, "set_result_handler") and callable(wf.set_result_handler):
                    wf.set_result_handler(self.get_callback())
            except Exception as e:
                print(f"[UiGateway] result_handler 등록 실패: {e}")

            # 리스닝 보장
            try:
                if not self._workflow_listening and hasattr(wf, "start_listen"):
                    wf.start_listen()
                    self._workflow_listening = True
                    print("[UiGateway] workflow.start_listen() started (cached)")
            except Exception as e:
                print(f"[UiGateway] workflow.start_listen 실패: {e}")
            return wf

        # 없으면 생성
        from com.hnw.ai.core.controller.workflow_controller import WorkflowController
        self._ensure_controllers_built()
        controllers: List[Any] = []
        controllers.extend(self._storage_list)
        controllers.extend(self._driver_list)
        if not controllers:
            print("[UiGateway] 컨트롤러가 없어 WorkflowController 생성 생략")
            return None

        wf = WorkflowController(*controllers)
        self._workflow = wf

        # ★ 새로 만들어도 즉시 콜백/리스닝 보장
        try:
            if hasattr(wf, "set_result_handler") and callable(wf.set_result_handler):
                wf.set_result_handler(self.get_callback())
        except Exception as e:
            print(f"[UiGateway] result_handler 등록 실패: {e}")

        try:
            if not self._workflow_listening and hasattr(wf, "start_listen"):
                wf.start_listen()
                self._workflow_listening = True
                print("[UiGateway] workflow.start_listen() started (new)")
        except Exception as e:
            print(f"[UiGateway] workflow.start_listen 실패: {e}")

        return wf

    def _ensure_controllers_built(self) -> None:
        """ID 리스트 → 컨트롤러 인스턴스 생성."""
        if self._controllers_built:
            return

        sid_list = self._override_storage_ids if self._override_storage_ids is not None else STORAGE_ID
        self._storage_list = []
        for sid in sid_list:
            try:
                if isinstance(sid, str) and sid.strip():
                    self._storage_list.append(StorageController(sid))
            except Exception as e:
                print(f"[UiGateway] StorageController('{sid}') 생성 실패: {e}")

        did_list = self._override_driver_ids if self._override_driver_ids is not None else DRIVER_ID
        self._driver_list = []
        for did in did_list:
            try:
                if isinstance(did, str) and did.strip():
                    self._driver_list.append(DriverController(did))
            except Exception as e:
                print(f"[UiGateway] DriverController('{did}') 생성 실패: {e}")

        self._controllers_built = True

    @staticmethod
    def _normalize_result(ret: Any) -> Tuple[List[Dict[str, Any]], Optional[List[str]]]:
        rows: List[Dict[str, Any]] = []
        columns: Optional[List[str]] = None
        if ret is None:
            return rows, columns
        if isinstance(ret, tuple) and len(ret) >= 2:
            rows, columns = ret[0], ret[1]
        elif isinstance(ret, dict):
            rows = ret.get("rows") or []
            columns = ret.get("columns")
        else:
            rows = [{"value": str(ret)}]
            columns = ["value"]
        if rows is None:
            rows = []
        if columns is not None and not isinstance(columns, list):
            columns = list(columns)
        return rows, columns

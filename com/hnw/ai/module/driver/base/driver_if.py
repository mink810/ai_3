# -*- coding: utf-8 -*-
"""
DriverIF (수동형 파싱 중심)
- __init__(dtype): 드라이버 타입 보관(예: "modbus_tcp")
- connect(dconn): 접속/초기화 정보 구성 (IO 없음)
- configure(dschema): 데이터(신호) 스키마 및 전역 파싱 옵션 구성
- read(data): 원시 데이터 → 표준 dict로 파싱
- start_listen(on_signal): 인그레스(포트/시리얼 등) 감시 시작
- stop(): 감시/리소스 정지
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict
import time

class DriverIF(ABC):
    """드라이버 공통 인터페이스(수동형 파싱 중심)."""

    def __init__(self, dtype: str) -> None:
        self.dtype: str = dtype
        self._conn_ready: bool = False
        self._schema_ready: bool = False

    @abstractmethod
    def connect(self, dconn: Dict[str, Any]) -> None:
        """접속/통신 관련 정보 구성 (host/port/slave_id/read_start_address 등)."""
        ...

    @abstractmethod
    def configure(self, dschema: Dict[str, Any]) -> None:
        """
        데이터(신호) 스키마 및 전역 파싱 옵션 구성.
        - 전역 옵션 예: word_order('big'|'little'), byte_order('big'|'little')
        - 신호별로 동일 키가 있으면 전역값을 오버라이드
        """
        ...

    @abstractmethod
    def read(self, data: Any) -> Dict[str, Any]:
        """원시 데이터를 스키마에 따라 파싱/정규화하여 dict 반환."""
        ...
        
    # ---------------------------
    # 인그레스 감시(공용 기능)
    # ---------------------------
    def start_listen(self, on_signal: Callable[[Dict[str, Any]], None]) -> None:
        """
        인그레스(예: TCP 포트, 시리얼, 소켓 등)를 감시하여 수신된 원시 데이터를
        read()로 정규화한 후 on_signal(payload)로 전달한다.

        기본 구현은 NotImplementedError를 발생시킨다.
        각 드라이버 구현체(modbus_tcp, modbus_rtu, can 등)에서 오버라이드해야 한다.

        :param on_signal: 정규화된 신호(dict)를 전달받는 콜백.
                          payload 형식은 read() 반환과 동일해야 한다.
        """
        raise NotImplementedError("start_listen(on_signal)이 구현되지 않았습니다.")    
    
    

    # 선택: 능동형 호환용 no operation
    def start(self, *args, **kwargs) -> None: return None
    def stop(self) -> None: return None
    def close(self) -> None:
        self._conn_ready = False
        self._schema_ready = False

    def is_ready(self) -> bool:
        return self._conn_ready and self._schema_ready

    # 내부 데이터 플래그 설정 메소드
    # - 특정 행위(connect, configure)가 완료되었음을 표시하는 깃발 역할
    # - 외부 호출 없이 클래스 내부에서 상태 변경을 추적하는 용도
    def _mark_conn_ready(self, val: bool = True) -> None:
        self._conn_ready = val
    def _mark_schema_ready(self, val: bool = True) -> None:
        self._schema_ready = val
    @staticmethod
    def _ensure_timestamp(payload: Dict[str, Any]) -> Dict[str, Any]:
        if "timestamp" not in payload:
            payload = dict(payload)
            payload["timestamp"] = time.time()
        return payload

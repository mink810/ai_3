# com/hnw/ai/storage/base/uigateway_if.py
# -*- coding: utf-8 -*-
"""
UiGatewayIF
- View(UI)와 Workflow/Storage 사이의 경계(게이트웨이) 역할에 대한 최소 계약입니다.
- 데이터소스 ID(문자열)로 조회를 트리거하고, 결과 (rows, columns)를 View.on_rows(...)에 전달하는 구현을 기대합니다.
- 구현 난이도를 낮추기 위해 컨트롤러 명시 주입(매 호출)은 생략하고,
  구현체 내부에서 사전 지정 ID 또는 connect(config)로 전달된 설정을 사용하도록 합니다.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Optional

from com.hnw.ai.view.base.view_if import ViewIF


class UiGatewayIF(ABC):
    """UI 게이트웨이 인터페이스(필수 계약만 정의)."""

    @abstractmethod
    def attach_view(self, view: ViewIF) -> None:
        """
        결과를 전달할 View를 주입합니다.
        구현체는 이후 조회 완료 시 반드시 view.on_rows(datasource_id, rows, columns)를 호출해야 합니다.
        """
        raise NotImplementedError

    @abstractmethod
    def connect(self, config: Optional[Dict[str, object]] = None) -> bool:
        """
        게이트웨이 설정을 적용합니다. (선택)
        예) {"controllers": {"storage_ids": ["ods_oracle_dev"], "driver_ids": ["modbus_dev_1","modbus_dev_2"]}}
        반환값은 일반적으로 True를 사용하며, 실패 시 예외를 던지는 정책을 권장합니다.
        """
        raise NotImplementedError

    @abstractmethod
    def request_data(self, datasource_id: str, options: Optional[Dict[str, object]] = None) -> None:
        """
        데이터소스 ID(문자열) 기준으로 비동기 조회를 트리거합니다.
        - options: 조회 옵션(예: {"window_sec": 5} 등). 구현체 재량으로 사용/무시 가능합니다.
        구현체는 조회 완료 후 view.on_rows(...)를 호출해야 합니다.
        """
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """스레드풀 등 내부 리소스를 정리합니다."""
        raise NotImplementedError

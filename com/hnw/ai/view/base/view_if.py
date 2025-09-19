# com/hnw/ai/view/base/view_if.py
# -*- coding: utf-8 -*-
"""
ViewIF (문자열 ID 전용)
- 본 프로젝트는 UI가 고정이므로, connect/start/close는 선택 메서드(기본 구현 제공)로 둡니다.
- 반드시 구현해야 하는 계약은 on_rows(index, rows, columns) 하나입니다.
- index는 '데이터소스 ID' 문자열로만 사용합니다.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class ViewIF(ABC):
    def __init__(self, vtype: str = "generic") -> None:
        self.vtype: str = vtype
        self._config: Dict[str, Any] = {}

    def connect(self, config: Dict[str, Any]) -> bool:
        self._config = dict(config or {})
        return True

    def start(self) -> None:
        pass

    @abstractmethod
    def on_rows(
        self,
        index: str,
        rows: List[Dict[str, Any]],
        columns: Optional[List[str]] = None,
    ) -> None:
        """
        데이터 수신(필수)
        - index: 데이터소스 ID(문자열)
        - rows:  표 형태의 레코드 목록(list[dict])
        - columns: 표시 컬럼 목록(옵션; 생략 시 rows의 키로 유추 가능)
        """
        raise NotImplementedError

    def close(self) -> None:
        pass

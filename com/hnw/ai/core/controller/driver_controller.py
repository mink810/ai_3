# com/hnw/ai/core/controller/driver_controller.py
# -*- coding: utf-8 -*-
"""
driver_controller.py
컨트롤러는 오케스트레이션만 담당한다.
- DriverServiceManager로 드라이버 비즈니스 객체를 획득
- start_listen(on_signal)로 인그레스 감시 시작
- stop()으로 수명주기 정리
"""

from typing import Callable, Dict, Any
from com.hnw.ai.config.env import ROOT_DIR

from com.hnw.ai.core.service.driver_service_manager import DriverServiceManager
from com.hnw.ai.module.driver.base.driver_if import DriverIF

class DriverController:
    """드라이버 컨트롤러"""

    def __init__(self, driver_id: str):
        """
        컨트롤러 초기화 시 필요한 드라이버 서비스 객체 생성
        """
        self.driver_id = driver_id
        self.driver_svc: DriverIF = DriverServiceManager.get_by_id(self.driver_id)  # 드라이버 객체 얻음
        print("self.driver_svc=", self.driver_svc)
        self._started: bool = False  # 감시 시작 여부

    def read(self, data: Any):
        """
        수신 원시 데이터를 드라이버 서비스로 위임하여 파싱 결과를 반환합니다.
        - 내부에서 self.driver_svc.read(data)를 호출합니다.

        :param data: 원시 데이터(예: 모드버스 레지스터 list[int], bytes 등 드라이버별 기대 타입)
        :return: 드라이버에서 파싱된 dict 페이로드
        """
        if not hasattr(self.driver_svc, "read"):
            raise AttributeError("driver_svc.read(...)가 존재하지 않습니다.")
        return self.driver_svc.read(data)    
        
    def start_listen(self, on_signal: Callable[[Dict], None]) -> None:
        """
        드라이버 비즈니스 로직의 인그레스 감시 시작.
        @param on_signal: 드라이버 read() 결과(payload dict)를 전달받는 콜백
        """
        if not hasattr(self.driver_svc, "start_listen") or not callable(self.driver_svc.start_listen):
            raise NotImplementedError("드라이버가 start_listen(on_signal)을 구현하지 않았습니다.")
        self.driver_svc.start_listen(on_signal)
        self._started = True

    def stop(self) -> None:
        """
        감시/리스너 정지 요청.
        - 드라이버 구현체의 stop()을 호출해 소켓/스레드 등을 정리한다.
        - 구현체 미제공 시에도 예외 없이 무시.
        """
        if self._started and hasattr(self.driver_svc, "stop") and callable(self.driver_svc.stop):
            try:
                self.driver_svc.stop()
            finally:
                self._started = False

    def is_running(self) -> bool:
        """감시 중이면 True, 아니면 False"""
        return self._started

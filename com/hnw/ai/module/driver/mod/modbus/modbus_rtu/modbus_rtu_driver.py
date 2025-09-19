"""
ModbusRTUDriver

- AsyncIO 기반의 Modbus RTU 드라이버 구현체.
- 시리얼 포트를 통해 슬레이브 장비로부터 주기적으로 Holding Register를 읽습니다.
- signal_config_file에 정의된 신호 정보를 기반으로 스케일 및 오프셋 처리 가능.
- 외부로부터 등록된 콜백 함수를 통해 값을 전달합니다.
"""

import asyncio
import json
from typing import Any, List, Optional, Callable

from pymodbus.client import AsyncModbusSerialClient
from pymodbus import FramerType

from com.hnw.ai.module.driver.base.driver_if import DriverIF


class ModbusRTUDriver(DriverIF):
    """
    Modbus RTU 드라이버 클래스

    Attributes:
        port (str): 시리얼 포트명 (예: "COM3")
        baudrate (int): 통신 속도
        slave_id (int): Modbus 슬레이브 ID
        read_start_address (int): 시작 주소
        read_end_address (int): 종료 주소
        signal_map (List[dict]): 신호 정의 리스트
        client (AsyncModbusSerialClient): pymodbus RTU 클라이언트
        _on_signal_callback (Callable): 외부에 값을 전달할 콜백 함수
    """

    def __init__(self):
        """
        드라이버 인스턴스를 초기화합니다.
        """
        self.client: Optional[AsyncModbusSerialClient] = None
        self.port: str = "COM3"
        self.baudrate: int = 9600
        self.slave_id: int = 1
        self.read_start_address: int = 0
        self.read_end_address: int = 0
        self.signal_map: List[dict] = []
        self._on_signal_callback: Optional[Callable[[str, float], None]] = None

    def set_on_signal_callback(self, callback: Callable[[str, float], None]):
        """
        외부에 값을 전달할 콜백 함수를 등록합니다.

        @param callback: (signal_name: str, value: float) -> None 형태의 함수
        """
        self._on_signal_callback = callback

    @staticmethod
    def load_signal_map(path: str) -> List[dict]:
        """
        signal_config 파일을 로드합니다.

        @param path: signal_config.json 경로
        @return: [{ "name": str, "address": int, "length": int, ... }, ...]
        """
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def configure(self, config: dict) -> None:
        """
        드라이버 설정 정보를 기반으로 내부 상태를 초기화하고 RTU 장비에 연결합니다.

        @param config: {
            "port": str,
            "baudrate": int,
            "slave_id": int,
            "read_start_address": int,
            "signal_config_file": str
        }
        """
        self.port = config.get("port", self.port)
        self.baudrate = config.get("baudrate", self.baudrate)
        self.slave_id = config.get("slave_id", self.slave_id)
        self.read_start_address = config.get("read_start_address", 0)

        signal_file = config.get("signal_config_file")
        if not signal_file:
            raise ValueError("signal_config_file 경로가 설정되지 않았습니다.")
        self.signal_map = self.load_signal_map(signal_file)
        self.read_end_address = max(
            item["address"] + item.get("length", 1)
            for item in self.signal_map
        )

        async def _connect_client():
            client = AsyncModbusSerialClient(
                port=self.port,
                framer=FramerType.RTU,
                baudrate=self.baudrate,
                stopbits=1,
                bytesize=8,
                parity="N",
                timeout=1
            )
            connected = await client.connect()
            if not connected:
                raise ConnectionError(f"[ModbusRTUDriver] 연결 실패: {self.port}")
            print(f"[ModbusRTUDriver] 연결 성공: {self.port}")
            return client

        self.client = asyncio.run(_connect_client())

    def start(self) -> None:
        """
        폴링 루프를 실행하여 주기적으로 데이터를 읽습니다.
        """
        if not self.client or not getattr(self.client, "connected", False):
            raise RuntimeError("configure()를 먼저 호출해야 합니다.")
        asyncio.run(self._run_loop())

    def stop(self) -> None:
        """
        RTU 연결을 종료합니다.
        """
        if self.client and getattr(self.client, "connected", False):
            asyncio.run(self.client.close())

    async def _run_loop(self) -> None:
        """
        Holding Register를 읽고 콜백으로 값을 전달하는 주기적인 비동기 루프입니다.
        """
        count = self.read_end_address - self.read_start_address + 1
        while True:
            result = await self.client.read_holding_registers(
                self.read_start_address,
                count=count,
                device_id=self.slave_id
            )
            if result.isError():
                print(f"[ModbusRTUDriver] 오류 응답: {result}")
            else:
                print(f"[ModbusRTUDriver] 수신값: {result.registers}")
                for i, reg in enumerate(result.registers):
                    if i < len(self.signal_map):
                        signal_def = self.signal_map[i]
                        name = signal_def.get("name", f"Signal_{i}")
                        scale = signal_def.get("scale", 1)
                        offset = signal_def.get("offset", 0)
                        value = reg * scale + offset
                        if self._on_signal_callback:
                            self._on_signal_callback(name, value)
            await asyncio.sleep(2)

    def read(self, address: int, count: int) -> List[Any]:
        """
        동기적으로 레지스터 값을 읽습니다.

        @param address: 시작 주소
        @param count: 읽을 개수
        @return: 레지스터 값 리스트
        """
        response = asyncio.run(
            self.client.read_holding_registers(
                address,
                count=count,
                device_id=self.slave_id
            )
        )
        return response.registers

    def write(self, address: int, values: List[Any]) -> None:
        """
        (미구현) 레지스터에 값을 쓰는 기능의 자리 표시자
        """
        raise NotImplementedError("Modbus RTU write 기능은 아직 구현되지 않았습니다.")

    def transform(self, *args: Any, **kwargs: Any) -> Any:
        """
        (미구현) 읽어온 원시 값을 변환하는 자리 표시자
        """
        raise NotImplementedError("값 변환(transform) 기능은 아직 구현되지 않았습니다.")

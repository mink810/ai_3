# -*- coding: utf-8 -*-
"""
ModbusTCPDriver (Stable Mode)
- 1워드(len=1): HR 1회 -> 실패 시 IR 1회 -> 그래도 실패면 스킵.
- 2워드(len=2): HR 'count=2' 1회 -> 실패 시 IR 'count=2' 1회 -> 성공 시 32비트 조립.
  (기존의 "1워드 정확읽기 × 2" 방식을 단일 2워드 읽기로 변경하여 경계/타이밍 이슈 완화)
- address_limit(옵션): 마지막 유효 주소(예: 5021→7, 5022→3). 경계 가드로 tail 실패 방지.
- unit/slave 인자 미사용(단일 컨텍스트 서버 호환). 오류 로그에 port/driver_id 포함.
"""

from __future__ import annotations
import time
from typing import Any, Dict, List, Optional

from pymodbus.client import ModbusTcpClient
from pymodbus.pdu import ExceptionResponse

try:
    from com.hnw.ai.module.driver.base.driver_if import DriverIF  # type: ignore
except Exception:
    class DriverIF:
        def configure(self, config: Dict[str, Any]) -> bool: ...
        def connect(self, dconn: Dict[str, Any]) -> bool: ...
        def read(self) -> List[Dict[str, Any]]: ...
        def start_listen(self, on_signal): ...
        def stop(self): ...

def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default

def _to_float(v: Any, default: float = 1.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


class ModbusTCPDriver(DriverIF):
    def __init__(self, init_arg: str) -> None:
        # 연결
        self._host: str = "127.0.0.1"
        self._port: int = 502
        self._slave_id: int = 1   # 단일 컨텍스트 서버에서 미사용(로그 표기용)

        # 스키마
        self._signals: List[Dict[str, Any]] = []
        self._word_order: str = "big"   # 'big' or 'little' (워드 순서)
        self._byte_order: str = "big"   # 'big' or 'little' (바이트 순서)
        self._address_limit: Optional[int] = None  # 마지막 유효 주소(옵션)

        # 런타임
        self._client: Optional[ModbusTcpClient] = None
        self._stop_flag: bool = False
        self._listening: bool = False
        self.driver_id: str = "modbus_tcp_unknown"

    # ───────── DriverIF ─────────
    def connect(self, dconn: Dict[str, Any]) -> bool:
        try:
            self._host = str(dconn.get("host", self._host))
            self._port = _to_int(dconn.get("port", self._port))
            self._slave_id = _to_int(dconn.get("slave_id", self._slave_id))
            # driver_id 고정
            if self._port == 5021:
                self.driver_id = "modbus_tcp_1"
            elif self._port == 5022:
                self.driver_id = "modbus_tcp_2"
            else:
                self.driver_id = f"modbus_tcp_{self._port}"
            print(f"[ModbusTCPDriver] connect() host={self._host} port={self._port} "
                  f"slave={self._slave_id} driver_id={self.driver_id}")
            return True
        except Exception as e:
            print(f"[ModbusTCPDriver] connect() error: {e}")
            return False

    def configure(self, dschema: Dict[str, Any]) -> bool:
        try:
            # ★ 추가: 상위에 'schema' 키가 오면 내부 블럭으로 다운스케일
            if "schema" in dschema and isinstance(dschema["schema"], dict):
                dschema = dschema["schema"]

            if "word_order" in dschema:
                self._word_order = str(dschema.get("word_order", self._word_order)).lower()
            if "byte_order" in dschema:
                self._byte_order = str(dschema.get("byte_order", self._byte_order)).lower()
            if "address_limit" in dschema:
                v = dschema.get("address_limit", None)
                self._address_limit = None if v is None else int(v)

            if "signals" in dschema and isinstance(dschema["signals"], list):
                filtered = []
                for s in dschema["signals"]:
                    leng = int(s.get("length", 0))
                    addr = int(s.get("address", -1))
                    if leng > 0 and addr >= 0:
                        filtered.append(s)
                    else:
                        self._log(f"skip schema(bad def): {s}")
                self._signals = filtered

            self._log(f"configure() port={self._port} word_order={self._word_order} "
                      f"byte_order={self._byte_order} address_limit={self._address_limit} "
                      f"signals={len(self._signals)}")
            return True
        except Exception as e:
            self._log(f"configure() error: {e}")
            return False

    def read(self) -> List[Dict[str, Any]]:
        """단발 폴링(필요시). 신호별 정확 길이 읽기."""
        out: List[Dict[str, Any]] = []
        client = ModbusTcpClient(host=self._host, port=self._port)
        if not client.connect():
            self._log("read(): connect fail")
            return out
        try:
            ts = time.time()
            src = f"{self._host}:{self._port}"
            for payload in self._read_signals_once(client, ts, src):
                out.append(payload)
        except Exception as e:
            self._log(f"read() error: {e}")
        finally:
            try:
                client.close()
            except Exception:
                pass
        return out

    def start_listen(self, on_signal) -> None:
        """지속 폴링. 실패는 스킵."""
        if self._listening:
            self._log("already listening")
            return

        self._stop_flag = False
        self._client = ModbusTcpClient(host=self._host, port=self._port)
        if not self._client.connect():
            self._log("connect fail")
            return

        self._listening = True
        self._log(f"start_listen(): port={self._port}, signals={len(self._signals)}, "
              f"address_limit={self._address_limit}")
        try:
            while not self._stop_flag:
                ts = time.time()
                src = f"{self._host}:{self._port}"
                for payload in self._read_signals_once(self._client, ts, src):
                    try:
                        on_signal(payload)
                    except Exception as e:
                        self._log(f"on_signal error: {e}")
                time.sleep(1.0)
        except Exception as e:
            self._log(f"listen loop error: {e}")
        finally:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
            self._listening = False
            self._log("stopped")

    def stop(self) -> None:
        self._stop_flag = True

    # ───────── 내부 유틸 ─────────
    def _read_hr(self, client: ModbusTcpClient, address: int, count: int):
        return client.read_holding_registers(address=address, count=count)

    def _read_ir(self, client: ModbusTcpClient, address: int, count: int):
        return client.read_input_registers(address=address, count=count)

    def _read_exact(self, client: ModbusTcpClient, addr: int, leng: int, retry: bool = False):
        def _one_round():
            rr = self._read_hr(client, addr, leng)
            if rr is None or isinstance(rr, ExceptionResponse) or (hasattr(rr, "isError") and rr.isError()):
                rr = self._read_ir(client, addr, leng)
                if rr is None or isinstance(rr, ExceptionResponse) or (hasattr(rr, "isError") and rr.isError()):
                    code = getattr(rr, "exception_code", None) if isinstance(rr, ExceptionResponse) else None
                    return None, code
            return rr, None

        rr, code = _one_round()
        if rr is not None:
            return rr

        if retry:
            import time as _t
            _t.sleep(0.01)  # 10ms
            rr, code = _one_round()
            if rr is not None:
                return rr

        self._log(f"read fail(addr={addr}, len={leng}) err_code={code}")
        return None

    def _read_signals_once(self, client: ModbusTcpClient, ts: float, src: str):
        """신호 목록을 돌며 정확 길이로만 읽어 payload 생성."""
        limit = self._address_limit
        for s in self._signals:
            name  = s.get("name")
            addr  = _to_int(s.get("address", 0))
            leng  = _to_int(s.get("length", 0))
            unit  = s.get("unit")
            prio  = _to_int(s.get("priority", 1))
            scale = _to_float(s.get("scale", 1.0))

            # 경계 가드: address_limit가 지정되면 범위 초과 스킵
            if limit is not None:
                if leng == 1 and not (0 <= addr <= limit):
                    self._log(f"skip '{name}' out-of-range addr={addr} limit={limit}")
                    continue
                if leng == 2 and not (0 <= addr and addr + 1 <= limit):
                    self._log(f"skip '{name}' out-of-range addr={addr}..{addr+1} limit={limit}")
                    continue

            try:
                if leng == 1:
                    rr = self._read_exact(client, addr, 1)
                    if rr is None or not hasattr(rr, "registers"):
                        continue
                    regs = list(getattr(rr, "registers", []) or [])
                    if len(regs) < 1:
                        self._log(f"skip '{name}' short response need=1 got={len(regs)}")
                        continue
                    raw = self._read_u16_from_regs(regs, 0)
                    value = float(raw) * scale

                elif leng == 2:
                    # 변경점: 두 워드를 '한 번에' 읽는다 (count=2)
                    rr = self._read_exact(client, addr, 2)
                    if rr is None or not hasattr(rr, "registers"):
                        continue
                    regs = list(getattr(rr, "registers", []) or [])
                    if len(regs) < 2:
                        self._log(f"skip '{name}' short response need=2 got={len(regs)}")
                        continue
                    raw32 = self._read_u32_from_regs(regs, 0)
                    value = float(raw32) * scale

                else:
                    self._log(f"skip '{name}' unsupported length={leng}")
                    continue

            except Exception as e:
                self._log(f"decode error '{name}': {e}")
                continue

            yield {
                "timestamp": ts,
                "source": src,
                "driver_id": self.driver_id,
                "unit_id": self._slave_id,
                "host": self._host,
                "port": self._port,
                "_src": {"host": self._host, "port": self._port},
                "name": name,
                "value": value,
                "unit": unit,
                "priority": prio,
            }

    # ───────── 디코딩(엔디안) ─────────
    @staticmethod
    def _swap_bytes_16(w: int) -> int:
        return ((w & 0x00FF) << 8) | ((w & 0xFF00) >> 8)

    def _read_u16_from_regs(self, regs: List[int], idx: int) -> int:
        w = regs[idx] & 0xFFFF
        if self._byte_order == "little":
            w = self._swap_bytes_16(w)
        return w

    def _read_u32_from_regs(self, regs: List[int], idx: int) -> int:
        # regs[idx], regs[idx+1]로 32비트 구성
        w0 = regs[idx] & 0xFFFF
        w1 = regs[idx + 1] & 0xFFFF
        if self._byte_order == "little":
            w0 = self._swap_bytes_16(w0)
            w1 = self._swap_bytes_16(w1)
        words = [w0, w1]
        if self._word_order == "little":
            words.reverse()
        return ((words[0] & 0xFFFF) << 16) | (words[1] & 0xFFFF)

    # ───────── 로깅 ─────────
    def _log(self, msg: str) -> None:
        print(f"[ModbusTCPDriver:{self.driver_id}@{self._host}:{self._port}] {msg}")

# modbus_emulator_instance.py
import asyncio
import random
from typing import Tuple

from pymodbus.datastore import (
    ModbusServerContext,
    ModbusDeviceContext,
    ModbusSequentialDataBlock,
)
from pymodbus.server import StartAsyncTcpServer
from pymodbus.pdu.device import ModbusDeviceIdentification

# ---------------------------
# 하드 클램프 유틸 (기능 추가 아님: 생성값을 "무조건" 범위 내로 강제)
# ---------------------------
def _clamp(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else hi if v > hi else v

# ---------------------------
# 값 범위 상수 (기존 의미 유지, 외부 설정/옵션 추가 없음)
# ---------------------------
TEMP_MIN, TEMP_MAX = 20, 35          # °C
PRESS_MIN, PRESS_MAX = 95, 110       # kPa
STATE_MIN, STATE_MAX = 0, 2          # 코드 0~2
CURR_MIN, CURR_MAX = 10, 20          # A (u32 저장)
VOLT_MIN, VOLT_MAX = 210, 230        # V (u32 저장)

# ---------------------------
# 엔디안: word_order=big, byte_order=big (프로토콜 요구사항)
# ---------------------------
def pack_u32_be(value: int) -> Tuple[int, int]:
    """
    32비트 정수를 16비트 2워드(hi, lo)로 분해 (big/big).
    예) 0x12345678 -> (0x1234, 0x5678)
    """
    v = value & 0xFFFFFFFF
    return (v >> 16) & 0xFFFF, v & 0xFFFF

def set_u16(ctx: ModbusServerContext, fc: int, addr: int, value: int) -> None:
    """
    16bit(1워드) 값을 지정 함수영역(fc:3/4), 시작주소(addr)에 기록.
    """
    ctx[0].setValues(fc, addr, [value & 0xFFFF])

def set_u32_be(ctx: ModbusServerContext, fc: int, addr: int, value: int) -> None:
    """
    32bit(2워드) 값을 big/big으로 기록.
    """
    hi, lo = pack_u32_be(value)
    ctx[0].setValues(fc, addr, [hi, lo])

# ---------------------------
# 포트별 레지스터 맵 생성
# ---------------------------
def _create_context_for_5021() -> ModbusServerContext:
    """
    5021: 온도(1W, addr=0), 압력(1W, addr=2), 상태(1W, addr=4), 누적_사용량(2W, addr=6)
    → 주소 최대 7번까지 사용하므로 최소 8워드 확보
    """
    regs_len = 128
    store = ModbusDeviceContext(
        hr=ModbusSequentialDataBlock(0, [0] * regs_len),
        ir=ModbusSequentialDataBlock(0, [0] * regs_len),
        co=ModbusSequentialDataBlock(0, [0]),
        di=ModbusSequentialDataBlock(0, [0]),
    )
    return ModbusServerContext(devices=store, single=True)

def _create_context_for_5022() -> ModbusServerContext:
    """
    5022: 전류(2W, addr=0), 전압(2W, addr=2) → 최소 4워드 확보
    """
    regs_len = 128
    store = ModbusDeviceContext(
        hr=ModbusSequentialDataBlock(0, [0] * regs_len),
        ir=ModbusSequentialDataBlock(0, [0] * regs_len),
        co=ModbusSequentialDataBlock(0, [0]),
        di=ModbusSequentialDataBlock(0, [0]),
    )
    return ModbusServerContext(devices=store, single=True)

def create_context(port: int) -> ModbusServerContext:
    if port == 5021:
        return _create_context_for_5021()
    elif port == 5022:
        return _create_context_for_5022()
    else:
        # 기본(확장 대비)
        store = ModbusDeviceContext(
            hr=ModbusSequentialDataBlock(0, [0] * 8),
            ir=ModbusSequentialDataBlock(0, [0] * 8),
            co=ModbusSequentialDataBlock(0, [0]),
            di=ModbusSequentialDataBlock(0, [0]),
        )
        return ModbusServerContext(devices=store, single=True)

# ---------------------------
# 값 갱신 루프
# ---------------------------
async def _update_loop_5021(ctx: ModbusServerContext, port: int, name: str):
    """
    온도/압력/상태/누적_사용량 갱신
    - 온도(°C): 20~35
    - 압력(kPa): 95~110
    - 상태(code): 0/1/2 순환
    - 누적_사용량(kWh): 매 주기 +1씩 증가 (32bit 누적)
    HR/IR 동시 기록
    """
    cumulative = 0
    state = STATE_MIN - 1  # 첫 증가 시 0이 되도록
    while True:
        # 생성 + 하드 클램프 (무조건 범위 내)
        temp = _clamp(random.randint(TEMP_MIN, TEMP_MAX), TEMP_MIN, TEMP_MAX)
        press = _clamp(random.randint(PRESS_MIN, PRESS_MAX), PRESS_MIN, PRESS_MAX)
        state = (state + 1)
        if state > STATE_MAX:
            state = STATE_MIN
        state = _clamp(state, STATE_MIN, STATE_MAX)
        cumulative = (cumulative + 1) & 0xFFFFFFFF  # 32bit 누적 보호

        # HR(3)
        set_u16(ctx, 3, 0, temp)          # 온도(1W)
        set_u16(ctx, 3, 2, press)         # 압력(1W)
        set_u16(ctx, 3, 4, state)         # 상태(1W)
        set_u32_be(ctx, 3, 6, cumulative) # 누적_사용량(2W)

        # IR(4)
        set_u16(ctx, 4, 0, temp)
        set_u16(ctx, 4, 2, press)
        set_u16(ctx, 4, 4, state)
        set_u32_be(ctx, 4, 6, cumulative)

        print(f"[{port}] [{name}] 갱신 → 온도={temp}°C, 압력={press}kPa, 상태={state}, 누적_사용량={cumulative}kWh (big/big)")
        await asyncio.sleep(2)

async def _update_loop_5022(ctx: ModbusServerContext, port: int, name: str):
    """
    전류/전압 갱신 (32bit, big/big)
    - 전류(A): 10~20
    - 전압(V): 210~230
    HR/IR 동시 기록
    """
    while True:
        # 생성 + 하드 클램프 (무조건 범위 내)
        current = _clamp(random.randint(CURR_MIN, CURR_MAX), CURR_MIN, CURR_MAX)
        voltage = _clamp(random.randint(VOLT_MIN, VOLT_MAX), VOLT_MIN, VOLT_MAX)

        # HR(3)
        set_u32_be(ctx, 3, 0, current)   # 전류(2W)
        set_u32_be(ctx, 3, 2, voltage)   # 전압(2W)

        # IR(4)
        set_u32_be(ctx, 4, 0, current)
        set_u32_be(ctx, 4, 2, voltage)

        print(f"[{port}] [{name}] 갱신 → 전류={current}A, 전압={voltage}V (32bit big/big)")
        await asyncio.sleep(2)

# ---------------------------
# 서버 기동
# ---------------------------
async def _serve_emulator(port: int, device_name: str):
    ctx = create_context(port)

    identity = ModbusDeviceIdentification()
    identity.VendorName  = "HNW-AI"
    identity.ProductCode = "HNW-MODBUS-EMU"
    identity.VendorUrl   = "https://example.local"
    identity.ProductName = device_name
    identity.ModelName   = f"Emulator-{port}"
    identity.MajorMinorRevision = "1.0"

    # 포트별 갱신 루프 선택
    if port == 5021:
        asyncio.create_task(_update_loop_5021(ctx, port, device_name))
    elif port == 5022:
        asyncio.create_task(_update_loop_5022(ctx, port, device_name))
    else:
        # 필요 시 확장 (기본 루프 재사용)
        asyncio.create_task(_update_loop_5021(ctx, port, device_name))

    print(f"[{port}] [{device_name}] 에뮬레이터 시작: 127.0.0.1:{port}")
    # IPv4 고정 (환경에 따라 localhost가 IPv6로 바인딩되는 문제 예방)
    await StartAsyncTcpServer(context=ctx, identity=identity, address=("127.0.0.1", port))

def run_emulator(port: int, device_name: str):
    """multiprocessing.Process 진입점"""
    try:
        asyncio.run(_serve_emulator(port, device_name))
    except Exception as e:
        import traceback
        print(f"[{port}] [{device_name}] 서버 기동 실패: {e!r}")
        traceback.print_exc()

# com/hnw/ai/core/service/driver_service_manager.py
# -*- coding: utf-8 -*-
"""
DriverServiceManager
--------------------
- driver_id → driver_config.json(인덱스)에서 (type, config_file) 조회
- config_file(JSON) 내부를 두 섹션으로 분리하여 로드:
    - connection: 접속/초기화 정보 (host, port, slave_id, read_start_address 등)
    - schema:     데이터(신호) 정보 (signals 배열, word_order/byte_order 등)
- 구형 포맷 호환:
    * config_file 루트가 '배열'이면 → signals로 간주, connection은 빈 dict
    * config_file 루트가 '객체'인데 signals만 있고 connection이 없으면 → signals만 사용
- 구현체 생성 후:
    driver.connect(dconn)   # 접속정보 주입
    driver.configure(dschema)  # 스키마 주입
"""

import json
import importlib
from pathlib import Path
from typing import Dict, Any
from com.hnw.ai.module.driver.base.driver_if import DriverIF

# -------------------------------------------------------------------------
# 상수 정의
# -------------------------------------------------------------------------

# 프로젝트 루트 기준 경로: __file__ 기준 상위 5단계( .../com/hnw/ai/... )
ROOT_DIR = Path(__file__).resolve().parents[5]

# 드라이버 인덱스 파일(driver_config.json) 절대경로
DRIVER_CONFIG_PATH = ROOT_DIR / "com" / "hnw" / "ai" / "config" / "driver" / "driver_config.json"

# -------------------------------------------------------------------------
# 내부 유틸 함수
# -------------------------------------------------------------------------

def _load_json(path: Path):
    """JSON 파일을 로드하여 Python 객체로 반환."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def _new_from_classpath(class_path: str):
    """class_path를 기반으로 모듈/클래스를 동적 로드하여 클래스 객체를 반환."""
    module_name, class_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)  # ← 인스턴스가 아니라 '클래스'를 반환

def _default_class_path_for_type(dtype: str) -> str:
    """드라이버 타입별 기본 class_path를 반환."""
    mapping = {
        "modbus_tcp": "com.hnw.ai.module.driver.mod.modbus.modbus_tcp.modbus_tcp_driver.ModbusTCPDriver",
        # "modbus_rtu": "com.hnw.ai.module.driver.mod.modbus.modbus_rtu.modbus_rtu_driver.ModbusRTUDriver",
    }
    cp = mapping.get((dtype or "").lower())
    if not cp:
        raise ValueError(f"[driver] unsupported type: {dtype}")
    return cp

def _split_config_sections(obj: Any) -> (Dict[str, Any], Dict[str, Any]):
    """
    config_file 내용을 접속/스키마 두 덩어리로 분리.
    반환: (dconn, dschema)
    허용 포맷:
      1) { "connection": {...}, "schema": {...} }
      2) { "connection": {...}, "signals": [...] }  # schema 대신 signals 바로
      3) [ {...}, {...} ]  # 구형: 루트가 배열이면 signals
    """
    dconn: Dict[str, Any] = {}
    dschema: Dict[str, Any] = {}

    # 3) 루트 배열 (구형)
    if isinstance(obj, list):
        dschema = {"signals": obj}
        return dconn, dschema

    if not isinstance(obj, dict):
        return dconn, dschema

    # 1) 명시적 섹션
    if "connection" in obj and isinstance(obj["connection"], dict):
        dconn = dict(obj["connection"])

    if "schema" in obj and isinstance(obj["schema"], dict):
        dschema = dict(obj["schema"])

    # 2) schema 대신 signals가 루트에 직접 있을 수 있음
    if not dschema and isinstance(obj.get("signals"), list):
        dschema = {"signals": obj["signals"]}
        # 선택적 전역 옵션도 함께 승격
        if "word_order" in obj: dschema["word_order"] = obj["word_order"]
        if "byte_order" in obj: dschema["byte_order"] = obj["byte_order"]

    return dconn, dschema

# -------------------------------------------------------------------------
# DriverServiceManager 클래스
# -------------------------------------------------------------------------

class DriverServiceManager:
    """드라이버 인스턴스 생성/구성 매니저."""

    @staticmethod
    def get_by_id(driver_id: str) -> DriverIF:
        """
        driver_id로 드라이버 구현 인스턴스를 생성/구성하여 반환.

        절차:
          1) driver_config.json에서 id 일치 엔트리 조회 (id, name, type, config_file)
          2) config_file 로드 → (dconn, dschema)로 분리
          3) dtype으로 class_path 결정 → 인스턴스 생성(생성자에 dtype 전달)
          4) driver.connect(dconn), driver.configure(dschema) 순차 호출
        """
        # 1) 인덱스 로드 및 엔트리 조회
        if not DRIVER_CONFIG_PATH.exists():
            raise FileNotFoundError(f"driver_config.json not found: {DRIVER_CONFIG_PATH}")

        cfg = _load_json(DRIVER_CONFIG_PATH)
        entry = next((d for d in cfg.get("drivers", [])
                      if str(d.get("id", "")).lower() == driver_id.lower()), None)
        if not entry:
            raise ValueError(f"[driver] unknown id: {driver_id}")

        dtype = entry.get("type")
        cfg_file = entry.get("config_file")
        if not dtype or not cfg_file:
            raise ValueError(f"[driver] 'type' and 'config_file' are required for id={driver_id}")

        # 2) config_file 로드 및 섹션 분리
        cfg_path = (DRIVER_CONFIG_PATH.parent / cfg_file).resolve()
        if not cfg_path.exists():
            raise FileNotFoundError(f"[driver] config_file not found: {cfg_path}")

        cfg_obj = _load_json(cfg_path)
        dconn, dschema = _split_config_sections(cfg_obj)

        # 3) 클래스 경로 결정 & 인스턴스 생성(생성자에 dtype 전달)
        class_path = _default_class_path_for_type(dtype)
        klass = _new_from_classpath(class_path)
        driver: DriverIF = klass(dtype)  # ← 중요한 변경점

        # 4) 접속 → 스키마 순서로 구성
        driver.connect(dconn or {})
        driver.configure(dschema or {})
        return driver

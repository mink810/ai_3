# com/hnw/ai/storage/mod/oracle/oracle_storage.py
# -*- coding: utf-8 -*-
"""
com/hnw/ai/storage/mod/oracle/oracle_storage.py

OracleStorage (HOST/PORT 및 단일/다중 payload 저장 지원 버전)
- SIGNAL 테이블에 HOST/PORT 컬럼을 추가한 스키마에 대응
- payload가 단일 신호 형태(name/value/unit)든, 다중 키 형태든 저장 가능
- 조회 시 HOST/PORT까지 함께 읽어 표시용 source = "host:port"로 가공

원본 기반: :contentReference[oaicite:1]{index=1}
"""

from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple, Union
from datetime import datetime, timezone

#import cx_Oracle
import oracledb

from com.hnw.ai.storage.base.storage_if import StorageIF


class OracleStorage(StorageIF):
    """
    ParamDoc:
    --------
    @class OracleStorage
    @implements StorageIF
    @description Oracle RDB에 대해 StorageIF의 공용 메서드를 제공합니다.
    """

    def __init__(self, stype: str = "oracle") -> None:
        """@param stype 스토리지 유형 식별자 (기본값 "oracle")"""
        self._stype: str = stype
        self._connected: bool = False
        self._capabilities: Set[str] = {"sql", "data", "tx"}
        self._tx_active: bool = False
        self._tx_id: Optional[str] = None

        self._dsn: Optional[str] = None
        self._user: Optional[str] = None
        self._password: Optional[str] = None
        self._autocommit: bool = True

        self._conn: Optional[oracledb.Connection] = None

        # (선택) 필드 메타(단위/우선순위 등)를 주입받아 store 시 활용
        self._data_meta: Dict[str, Dict[str, Any]] = {}

    # ---------------------------
    # 연결 수명주기
    # ---------------------------
    def connect(self, config: Dict[str, Any]) -> None:
        if self._connected:
            return

        cfg = dict(config or {})
        user = cfg.get("user")
        password = cfg.get("password")
        host = cfg.get("host")
        port = int(cfg.get("port", 1521))
        sid  = cfg.get("sid")
        lib_dir = cfg.get("lib_dir")

        if not all([user, password, host, port, sid]):
            raise ValueError("[OracleStorage] user/password/host/port/sid 설정이 필요합니다.")
        if not lib_dir:
            raise ValueError("[OracleStorage] lib_dir(Oracle Client BIN 경로) 설정이 필요합니다.")
        if not os.path.isdir(lib_dir):
            raise ValueError(f"[OracleStorage] lib_dir 경로가 존재하지 않습니다: {lib_dir}")

        try:
            oracledb.init_oracle_client(lib_dir=lib_dir)
        except oracledb.ProgrammingError:
            pass

        dsn = oracledb.makedsn(host, port, sid=sid)
        self._conn = oracledb.connect(user=user, password=password, dsn=dsn)
        self._connected = True

    def is_connected(self) -> bool:
        return bool(self._connected and self._conn)

    def close(self) -> None:
        try:
            if self._conn:
                self._conn.close()
        finally:
            self._conn = None
            self._connected = False

    def health_check(self) -> bool:
        if not self._conn:
            return False
        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT 1 FROM dual")
                cur.fetchone()
            return True
        except Exception:
            return False

    # ---------------------------
    # 트랜잭션 (삼값)
    # ---------------------------
    def begin(self) -> Optional[bool]:
        """@return true/false/null(미지원)"""
        if not self._conn:
            return False
        try:
            self._conn.autocommit = False
            self._autocommit = False
            self._tx_active = True
            self._tx_id = None
            return True
        except Exception:
            return False

    def commit(self) -> Optional[bool]:
        """@return true/false/null(미지원)"""
        if not self._conn:
            return False
        try:
            self._conn.commit()
            self._tx_active = False
            self._tx_id = None
            return True
        except Exception:
            return False

    def rollback(self) -> Optional[bool]:
        """@return true/false/null(미지원)"""
        if not self._conn:
            return False
        try:
            self._conn.rollback()
            self._tx_active = False
            self._tx_id = None
            return True
        except Exception:
            return False

    def set_autocommit(self, enabled: bool) -> Optional[bool]:
        if not self._conn:
            return False
        try:
            self._conn.autocommit = enabled
            self._autocommit = enabled
            return True
        except Exception:
            return False

    def in_transaction(self) -> bool:
        return bool(self._tx_active)

    # ---------------------------
    # SQL (선택 구현)
    # ---------------------------
    def execute(
        self,
        sql: str,
        params: Optional[Union[Sequence[Any], Mapping[str, Any]]] = None,
    ) -> Any:
        if not self._conn:
            raise RuntimeError("not connected")
        with self._conn.cursor() as cur:
            cur.execute(sql, params or {})
        return cur.rowcount if hasattr(cur, "rowcount") else None

    def executemany(
        self,
        sql: str,
        seq_of_params: Iterable[Union[Sequence[Any], Mapping[str, Any]]],
    ) -> Any:
        
        print("executemany=====")
        if not self._conn:
            print("Non Connection=======")
            raise RuntimeError("not connected")
        with self._conn.cursor() as cur:
            cur.executemany(sql, list(seq_of_params))
            print("sql=", sql)
        return cur.rowcount if hasattr(cur, "rowcount") else None

    def query_one(
        self,
        sql: str,
        params: Optional[Union[Sequence[Any], Mapping[str, Any]]] = None,
    ) -> Optional[Tuple]:
        if not self._conn:
            raise RuntimeError("not connected")
        with self._conn.cursor() as cur:
            cur.execute(sql, params or {})
            row = cur.fetchone()
        return row

    def query_all(
        self,
        sql: str,
        params: Optional[Union[Sequence[Any], Mapping[str, Any]]] = None,
    ) -> List[Tuple]:
        if not self._conn:
            raise RuntimeError("not connected")
        with self._conn.cursor() as cur:
            cur.execute(sql, params or {})
            rows = cur.fetchall()
        return list(rows or [])

    # ---------------------------
    # 범용 데이터 저장/조회
    # ---------------------------
    # oracle_storage.py  (OracleStorage 클래스 내부) - store 함수만 교체
    def store(self, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        ParamDoc: store
        설명:
          - payload(dict)를 SIGNAL 테이블에 행 단위로 저장합니다.
          - 단일 신호(name/value) 또는 다중 키 형태 모두 지원합니다.
          - HOST/PORT는 payload['_src'] → payload['host'/'port'] → payload['source']("host:port") 순으로 추출합니다.
          - TS_UTC는 OS 로컬 시간대(datetime, tzinfo 포함)를 그대로 바인딩하여 TIMESTAMP(6) WITH TIME ZONE에 저장합니다.

        반환:
          (ok, key_info)
        """
        
        print("payload=", payload)
        
        if not self._conn:
            raise RuntimeError("[OracleStorage] 연결되지 않았습니다. connect(config) 후 사용하세요.")

        # --- 공통 메타 추출 ---
        ts_epoch = self._coerce_epoch(payload.get("timestamp") or payload.get("ts"))
        # UTC 기준 epoch → OS 로컬 시간대의 timezone-aware datetime
        ts_dt_local = datetime.fromtimestamp(float(ts_epoch), tz=timezone.utc).astimezone()

        source   = payload.get("source")
        driver_id = payload.get("driver_id")
        unit_id   = payload.get("unit_id")

        # HOST/PORT 우선 추출
        host, port = None, None
        src_meta = payload.get("_src") or {}
        if isinstance(src_meta, dict):
            host = src_meta.get("host") or payload.get("host")
            port = src_meta.get("port") or payload.get("port")
        else:
            host = payload.get("host")
            port = payload.get("port")

        # source가 "host:port" 형태라면 보조 파싱
        if (not host or not port) and isinstance(source, str) and ":" in source:
            try:
                h, p = source.split(":", 1)
                host = host or h
                port = port or int(p)
            except Exception:
                pass

        # --- 단일/다중 형태 분해 ---
        rows: List[Tuple] = []

        # (1) 단일 신호
        if ("name" in payload) and ("value" in payload):
            name = payload.get("name")
            value = payload.get("value")
            value_num = float(value) if value is not None else None

            # unit/priority: payload 우선 → meta 폴백
            unit = payload.get("unit")
            meta = self._data_meta.get(str(name), {})
            if unit is None:
                unit = meta.get("unit")
            priority = payload.get("priority", meta.get("priority"))
            meta_json = json.dumps(meta, ensure_ascii=False) if meta else None

            # 바인드 순서: :1=ts_dt_local, :2..:11 기존과 동일
            rows.append((ts_dt_local, source, driver_id, unit_id, name, value_num, unit, priority, host, port, meta_json))

        else:
            # (2) 다중 키: 예약 키 제외 후 각 필드를 행으로 분해
            reserved = {
                "timestamp", "ts", "source", "driver_id", "unit_id",
                "_src", "host", "port",
                "name", "value", "unit", "priority", "META_JSON"
            }
            for name, value in payload.items():
                if name in reserved:
                    continue
                value_num = float(value) if value is not None else None
                meta = self._data_meta.get(name, {})
                unit = meta.get("unit")
                priority = meta.get("priority")
                meta_json = json.dumps(meta, ensure_ascii=False) if meta else None
                rows.append((ts_dt_local, source, driver_id, unit_id, name, value_num, unit, priority, host, port, meta_json))

        if not rows:
            return True, {"ts": ts_epoch, "source": source, "driver_id": driver_id, "host": host, "port": port, "window_sec": 5}

        # --- INSERT (HOST, PORT 포함) ---
        #   >> 핵심: TS_UTC에 tz-aware datetime을 그대로 바인딩 (:1)
        sql = """
            INSERT INTO SIGNAL
              (TS_UTC, SOURCE, DRIVER_ID, UNIT_ID, SIGNAL_NAME, VALUE_NUM, UNIT, PRIORITY, HOST, PORT, META_JSON)
            VALUES
              (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11)
        """

        try:
            with self._conn.cursor() as cur:
                cur.executemany(sql, rows)
            self._conn.commit()
            key_info = {"ts": ts_epoch, "source": source, "driver_id": driver_id, "host": host, "port": port, "window_sec": 5}
            return True, key_info

        except Exception as e:
            try:
                self._conn.rollback()
            except Exception:
                pass
            # 에러 원인 가시화 (코드/메시지)
            print("[OracleStorage.store] 예외::", repr(e))
            if hasattr(e, "args") and e.args:
                try:
                    # python-oracledb는 첫 args에 _Error가 들어있고 .message/.code 접근 가능
                    err_obj = e.args[0]
                    code = getattr(err_obj, "code", None)
                    msg  = getattr(err_obj, "message", None) or str(e)
                    print(f"[OracleStorage.store] code={code}, message={msg}")
                except Exception:
                    print("[OracleStorage.store] raw args:", e.args)
            return False, {}

    def store_async(self, payload: Dict[str, Any]) -> None:
        # 샘플 구현: 동기와 동일 처리
        self.store(payload)

    def query_for_view_rows(self, key_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        ParamDoc: query_for_view_rows
        설명:
          - key_info 기준 시간창을 조회하여 시각화용 행(list[dict])을 반환합니다.
          - HOST/PORT까지 함께 조회하고, 표시용 source는 "host:port"가 있으면 이를 우선 사용합니다.
          - 시간 조건은 tz-aware datetime을 그대로 바인딩하여 TIMESTAMP(6) WITH TIME ZONE에 안전하게 매칭합니다.

        key_info 예)
          {"ts": <epoch>, "window_sec": 5, "source": "...", "driver_id": "...", "host":"127.0.0.1", "port":5021}

        반환 예)
          [{"ts": <epoch>, "name": <field>, "value": <num>, "source": "127.0.0.1:5021",
            "driver_id": "...", "unit_id": 1, "unit": "...", "priority": 1}, ...]
        """
        if not self._conn:
            raise RuntimeError("[OracleStorage] 연결되지 않았습니다. connect(config) 후 사용하세요.")

        # 윈도우/필터 추출
        ts_epoch = self._coerce_epoch(key_info.get("ts"))
        window   = int(key_info.get("window_sec", 5))
        src      = key_info.get("source")
        drv      = key_info.get("driver_id")
        host     = key_info.get("host")
        port     = key_info.get("port")

        # epoch(UTC) → OS 로컬 시간대 tz-aware datetime (저장 시점과 일관)
        from_dt_local = datetime.fromtimestamp(ts_epoch - window, tz=timezone.utc).astimezone()
        to_dt_local   = datetime.fromtimestamp(ts_epoch + window, tz=timezone.utc).astimezone()
        
        print("from_dt_local =", from_dt_local)
        print("to_dt_local =", to_dt_local)

        # WHERE 절 구성 (시간은 tz-aware 바인딩)
        where_clauses = ["TS_UTC >= :t_from", "TS_UTC <= :t_to"]
        params: Dict[str, Any] = {"t_from": from_dt_local, "t_to": to_dt_local}

        if src not in (None, ""):
            where_clauses.append("SOURCE = :src")
            params["src"] = src
        if drv not in (None, ""):
            where_clauses.append("DRIVER_ID = :drv")
            params["drv"] = drv
        if host not in (None, ""):
            where_clauses.append("HOST = :host")
            params["host"] = host
        if port not in (None, ""):
            where_clauses.append("PORT = :port")
            params["port"] = port

        sql = f"""
            SELECT
              TS_UTC, SIGNAL_NAME, VALUE_NUM, SOURCE, DRIVER_ID, UNIT_ID, UNIT, PRIORITY, HOST, PORT
            FROM SIGNAL
            WHERE {' AND '.join(where_clauses)}
            ORDER BY TS_UTC ASC, PRIORITY ASC
        """

        out: List[Dict[str, Any]] = []
        try:
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
                for (ts_tz, name, value, source_db, driver_id, unit_id, unit, priority, host_db, port_db) in cur:
                    # ts_tz: python-oracledb가 TIMESTAMP WITH TIME ZONE을 tz-aware datetime으로 반환
                    # epoch로 변환(표시는 UTC epoch로 통일)
                    ts_epoch_out = ts_tz.astimezone(timezone.utc).timestamp() if ts_tz else None

                    # 표시용 source: host:port 우선
                    source_str = None
                    if host_db and port_db is not None:
                        try:
                            source_str = f"{host_db}:{int(port_db)}"
                        except Exception:
                            source_str = f"{host_db}:{port_db}"
                    if not source_str:
                        source_str = source_db

                    out.append({
                        "ts": float(ts_epoch_out) if ts_epoch_out is not None else None,
                        "name": name,
                        "value": float(value) if value is not None else None,
                        "source": source_str,
                        "driver_id": driver_id,
                        "unit_id": unit_id,
                        "unit": unit,
                        "priority": priority
                    })
            print("out=", out)
        except Exception as e:
            print("[OracleStorage.query_for_view_rows] 예외:", repr(e))
            return []
        return out


    def fetch_for_datasource(
        self,
        datasource_id: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[List[str]]]:
        """
        데이터소스 ID별 간단 가공(포트 매핑) 후 조회.
        - ds_top    → PORT = 5021
        - ds_bottom → PORT = 5022
        - 그 외     → 빈 결과
        """
        p: Dict[str, Any] = dict(params or {})
        p.setdefault("window_sec", 5)

        if datasource_id == "ds_top":
            p["port"] = 5021
        elif datasource_id == "ds_bottom":
            p["port"] = 5022
        else:
            return [], None

        rows: List[Dict[str, Any]] = self.query_for_view_rows(p) or []
        columns: Optional[List[str]] = list(rows[0].keys()) if rows else None
        return rows, columns


    # ---------------------------
    # (선택) 메타 주입
    # ---------------------------
    def set_data_meta(self, meta: Dict[str, Dict[str, Any]]) -> None:
        """
        ParamDoc: set_data_meta
        설명:
          - 필드별 단위/우선순위 등 메타데이터를 주입합니다.
          - store 시 예약 키(없으면 None)로 META_JSON에 직렬화해 함께 저장합니다.
        """
        self._data_meta = dict(meta or {})

    # ---------------------------
    # 유틸
    # ---------------------------
    @staticmethod
    def _coerce_epoch(ts: Any) -> float:
        """epoch(float) 또는 ISO 문자열을 epoch 초로 변환."""
        if ts is None:
            return datetime.now(tz=timezone.utc).timestamp()
        if isinstance(ts, (int, float)):
            return float(ts)
        try:
            s = str(ts).replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            return datetime.now(tz=timezone.utc).timestamp()

    @staticmethod
    def _epoch_to_tsstr(epoch_sec: float) -> str:
        """epoch 초 → 'YYYY-MM-DD HH:MM:SS.FF3' (UTC)"""
        dt = datetime.fromtimestamp(float(epoch_sec), tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

# com/hnw/ai/storage/mod/mysql/mysql_storage.py
# -*- coding: utf-8 -*-
"""
MySQLStorage - AI 학습 결과 저장용 MySQL 스토리지 구현체

주요 기능:
- AI 모델 정보 저장 (ai_model_info 테이블)
- 학습 히스토리 저장 (training_history 테이블)  
- 모델 메트릭 저장 (model_metrics 테이블)
- 학습 과정 실시간 조회 지원
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple, Union

import pymysql
from pymysql.cursors import DictCursor

from com.hnw.ai.storage.base.storage_if import StorageIF


class MySQLStorage(StorageIF):
    """
    MySQL 스토리지 구현체
    - AI 학습 결과 저장 및 조회
    - 학습 과정 실시간 모니터링 지원
    """

    def __init__(self, stype: str = "mysql") -> None:
        """@param stype 스토리지 유형 식별자 (기본값 "mysql")"""
        self._stype: str = stype
        self._connected: bool = False
        self._capabilities: Set[str] = {"sql", "data", "tx"}
        self._tx_active: bool = False
        self._tx_id: Optional[str] = None

        self._conn: Optional[pymysql.Connection] = None
        self._autocommit: bool = True

        # 연결 정보
        self._host: Optional[str] = None
        self._port: int = 3306
        self._user: Optional[str] = None
        self._password: Optional[str] = None
        self._database: Optional[str] = None
        self._charset: str = "utf8mb4"

    # ---------------------------
    # 연결 수명주기
    # ---------------------------
    def connect(self, config: Dict[str, Any]) -> None:
        """MySQL 연결 설정"""
        if self._connected:
            return

        cfg = dict(config or {})
        self._host = cfg.get("host", "127.0.0.1")
        self._port = int(cfg.get("port", 3306))
        self._user = cfg.get("user")
        self._password = cfg.get("password")
        self._database = cfg.get("database")
        self._charset = cfg.get("charset", "utf8mb4")

        if not all([self._user, self._password, self._database]):
            raise ValueError("[MySQLStorage] user/password/database 설정이 필요합니다.")

        try:
            self._conn = pymysql.connect(
                host=self._host,
                port=self._port,
                user=self._user,
                password=self._password,
                database=self._database,
                charset=self._charset,
                autocommit=self._autocommit,
                cursorclass=DictCursor
            )
            self._connected = True
            print(f"[MySQLStorage] 연결 성공: {self._host}:{self._port}/{self._database}")

        except Exception as e:
            print(f"[MySQLStorage] 연결 실패: {e}")
            raise

    def is_connected(self) -> bool:
        """연결 상태 확인"""
        if not self._connected or not self._conn:
            return False
        
        # 연결 상태 테스트
        try:
            self._conn.ping(reconnect=True)
            return True
        except Exception:
            self._connected = False
            return False
    
    def _ensure_connection(self) -> None:
        """연결 보장 (재연결 시도) - 개선된 버전"""
        try:
            # 연결 상태 확인
            if self._conn and self._conn.open:
                # 간단한 ping으로 연결 상태 확인
                self._conn.ping(reconnect=False)
                return
        except Exception:
            pass
        
        # 연결이 끊어졌거나 없으면 재연결
        print(f"[MySQLStorage] 연결 끊어짐, 재연결 시도...")
        try:
            self._conn = pymysql.connect(
                host=self._host,
                port=self._port,
                user=self._user,
                password=self._password,
                database=self._database,
                charset=self._charset,
                autocommit=self._autocommit,
                cursorclass=DictCursor,
                connect_timeout=10,
                read_timeout=30,
                write_timeout=30
            )
            self._connected = True
            print(f"[MySQLStorage] 재연결 성공: {self._host}:{self._port}/{self._database}")
        except Exception as e:
            print(f"[MySQLStorage] 재연결 실패: {e}")
            self._conn = None
            self._connected = False

    def close(self) -> None:
        """연결 종료"""
        try:
            if self._conn:
                self._conn.close()
        finally:
            self._conn = None
            self._connected = False

    def health_check(self) -> bool:
        """헬스 체크"""
        if not self._conn:
            return False
        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            return True
        except Exception:
            return False

    # ---------------------------
    # 트랜잭션
    # ---------------------------
    def begin(self) -> Optional[bool]:
        """트랜잭션 시작"""
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
        """트랜잭션 커밋"""
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
        """트랜잭션 롤백"""
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
        """자동 커밋 설정"""
        if not self._conn:
            return False
        try:
            self._conn.autocommit = enabled
            self._autocommit = enabled
            return True
        except Exception:
            return False

    def in_transaction(self) -> bool:
        """트랜잭션 상태 확인"""
        return bool(self._tx_active)

    # ---------------------------
    # SQL 실행
    # ---------------------------
    def execute(
        self,
        sql: str,
        params: Optional[Union[Sequence[Any], Mapping[str, Any]]] = None,
    ) -> Any:
        """SQL 실행"""
        if not self._conn:
            raise RuntimeError("not connected")
        with self._conn.cursor() as cur:
            cur.execute(sql, params or {})
        return cur.rowcount

    def executemany(
        self,
        sql: str,
        seq_of_params: Iterable[Union[Sequence[Any], Mapping[str, Any]]],
    ) -> Any:
        """여러 SQL 실행"""
        if not self._conn:
            raise RuntimeError("not connected")
        with self._conn.cursor() as cur:
            cur.executemany(sql, list(seq_of_params))
        return cur.rowcount

    def query_one(
        self,
        sql: str,
        params: Optional[Union[Sequence[Any], Mapping[str, Any]]] = None,
    ) -> Optional[Tuple]:
        """단일 행 조회"""
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
        """모든 행 조회"""
        if not self._conn:
            raise RuntimeError("not connected")
        with self._conn.cursor() as cur:
            cur.execute(sql, params or {})
            rows = cur.fetchall()
        return list(rows or [])

    # ---------------------------
    # AI 학습 결과 저장/조회
    # ---------------------------
    def store(self, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        AI 학습 결과 저장
        payload 예시:
        {
            "type": "model_info",  # "model_info", "training_history", "model_metrics"
            "model_id": "image_classifier_001",
            "model_name": "사과토마토분류기",
            "model_type": "image_classification",
            "status": "training",
            "epoch": 1,
            "train_loss": 0.5,
            "train_accuracy": 0.8,
            "val_loss": 0.6,
            "val_accuracy": 0.75,
            "metric_name": "accuracy",
            "metric_value": 0.85
        }
        """
        if not self._conn:
            raise RuntimeError("[MySQLStorage] 연결되지 않았습니다. connect(config) 후 사용하세요.")

        try:
            store_type = payload.get("type", "model_info")
            
            if store_type == "model_info":
                return self._store_model_info(payload)
            elif store_type == "training_history":
                return self._store_training_history(payload)
            elif store_type == "model_metrics":
                return self._store_model_metrics(payload)
            else:
                print(f"[MySQLStorage] 알 수 없는 저장 타입: {store_type}")
                return False, {}

        except Exception as e:
            print(f"[MySQLStorage.store] 예외: {repr(e)}")
            return False, {}

    def _store_model_info(self, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """모델 정보 저장 (덮어쓰기)"""
        model_id = payload.get("model_id")
        
        # 기존 데이터 삭제
        delete_sql = "DELETE FROM ai_model_info WHERE model_id = %(model_id)s"
        
        # 새 데이터 삽입
        insert_sql = """
            INSERT INTO ai_model_info (model_id, model_name, model_type, created_at, status)
            VALUES (%(model_id)s, %(model_name)s, %(model_type)s, %(created_at)s, %(status)s)
        """
        
        params = {
            "model_id": model_id,
            "model_name": payload.get("model_name"),
            "model_type": payload.get("model_type"),
            "created_at": datetime.now(),
            "status": payload.get("status", "training")
        }

        try:
            with self._conn.cursor() as cur:
                # 기존 데이터 삭제
                cur.execute(delete_sql, {"model_id": model_id})
                # 새 데이터 삽입
                cur.execute(insert_sql, params)
            self._conn.commit()
            return True, {"model_id": params["model_id"]}
        except Exception as e:
            print(f"[MySQLStorage._store_model_info] 예외: {e}")
            return False, {}

    def _store_training_history(self, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """학습 히스토리 저장 (덮어쓰기)"""
        model_id = payload.get("model_id")
        epoch = payload.get("epoch")
        
        # 기존 에폭 데이터 삭제
        delete_sql = "DELETE FROM training_history WHERE model_id = %(model_id)s AND epoch = %(epoch)s"
        
        # 새 데이터 삽입
        insert_sql = """
            INSERT INTO training_history (model_id, epoch, train_loss, train_accuracy, val_loss, val_accuracy, timestamp)
            VALUES (%(model_id)s, %(epoch)s, %(train_loss)s, %(train_accuracy)s, %(val_loss)s, %(val_accuracy)s, %(timestamp)s)
        """
        
        params = {
            "model_id": model_id,
            "epoch": epoch,
            "train_loss": payload.get("train_loss"),
            "train_accuracy": payload.get("train_accuracy"),
            "val_loss": payload.get("val_loss"),
            "val_accuracy": payload.get("val_accuracy"),
            "timestamp": datetime.now()
        }

        try:
            with self._conn.cursor() as cur:
                # 기존 에폭 데이터 삭제
                cur.execute(delete_sql, {"model_id": model_id, "epoch": epoch})
                # 새 데이터 삽입
                cur.execute(insert_sql, params)
            self._conn.commit()
            return True, {"model_id": params["model_id"], "epoch": params["epoch"]}
        except Exception as e:
            print(f"[MySQLStorage._store_training_history] 예외: {e}")
            return False, {}

    def _store_model_metrics(self, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """모델 메트릭 저장 (덮어쓰기)"""
        model_id = payload.get("model_id")
        metric_name = payload.get("metric_name")
        
        # 기존 메트릭 삭제
        delete_sql = "DELETE FROM model_metrics WHERE model_id = %(model_id)s AND metric_name = %(metric_name)s"
        
        # 새 데이터 삽입
        insert_sql = """
            INSERT INTO model_metrics (model_id, metric_name, metric_value)
            VALUES (%(model_id)s, %(metric_name)s, %(metric_value)s)
        """
        
        params = {
            "model_id": model_id,
            "metric_name": metric_name,
            "metric_value": payload.get("metric_value")
        }

        try:
            with self._conn.cursor() as cur:
                # 기존 메트릭 삭제
                cur.execute(delete_sql, {"model_id": model_id, "metric_name": metric_name})
                # 새 데이터 삽입
                cur.execute(insert_sql, params)
            self._conn.commit()
            return True, {"model_id": params["model_id"], "metric_name": params["metric_name"]}
        except Exception as e:
            print(f"[MySQLStorage._store_model_metrics] 예외: {e}")
            return False, {}

    def store_async(self, payload: Dict[str, Any]) -> None:
        """비동기 저장 (동기와 동일 처리)"""
        self.store(payload)

    def query_for_view_rows(self, key_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        시각화용 데이터 조회
        key_info 예시:
        {
            "datasource_id": "training_history",
            "model_id": "image_classifier_001",
            "limit": 100
        }
        """
        if not self._conn:
            raise RuntimeError("[MySQLStorage] 연결되지 않았습니다. connect(config) 후 사용하세요.")

        datasource_id = key_info.get("datasource_id", "training_history")
        model_id = key_info.get("model_id")
        limit = key_info.get("limit", 100)

        try:
            if datasource_id == "training_history":
                return self._query_training_history(model_id, limit)
            elif datasource_id == "model_info":
                return self._query_model_info(model_id)
            elif datasource_id == "model_metrics":
                return self._query_model_metrics(model_id)
            else:
                return []

        except Exception as e:
            print(f"[MySQLStorage.query_for_view_rows] 예외: {e}")
            return []

    def _query_training_history(self, model_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
        """학습 히스토리 조회"""
        sql = """
            SELECT epoch, train_loss, train_accuracy, val_loss, val_accuracy, timestamp
            FROM training_history
        """
        params = {}
        
        if model_id:
            sql += " WHERE model_id = %(model_id)s"
            params["model_id"] = model_id
            
        sql += " ORDER BY epoch ASC LIMIT %(limit)s"
        params["limit"] = limit

        try:
            self._ensure_connection()
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"[MySQLStorage._query_training_history] 예외: {e}")
            return []

    def _query_model_info(self, model_id: Optional[str]) -> List[Dict[str, Any]]:
        """모델 정보 조회"""
        sql = "SELECT * FROM ai_model_info"
        params = {}
        
        if model_id:
            sql += " WHERE model_id = %(model_id)s"
            params["model_id"] = model_id

        try:
            self._ensure_connection()
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"[MySQLStorage._query_model_info] 예외: {e}")
            return []

    def _query_model_metrics(self, model_id: Optional[str]) -> List[Dict[str, Any]]:
        """모델 메트릭 조회"""
        sql = "SELECT * FROM model_metrics"
        params = {}
        
        if model_id:
            sql += " WHERE model_id = %(model_id)s"
            params["model_id"] = model_id

        try:
            self._ensure_connection()
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"[MySQLStorage._query_model_metrics] 예외: {e}")
            return []

    def fetch_for_datasource(
        self,
        datasource_id: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[List[str]]]:
        """
        데이터소스별 조회
        - training_history: 학습 히스토리
        - model_info: 모델 정보
        - model_metrics: 모델 메트릭
        """
        p: Dict[str, Any] = dict(params or {})
        
        if datasource_id == "training_history":
            rows = self._query_training_history(p.get("model_id"), p.get("limit", 100))
        elif datasource_id == "model_info":
            rows = self._query_model_info(p.get("model_id"))
        elif datasource_id == "model_metrics":
            rows = self._query_model_metrics(p.get("model_id"))
        else:
            return [], None

        columns: Optional[List[str]] = list(rows[0].keys()) if rows else None
        return rows, columns

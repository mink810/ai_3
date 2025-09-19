# com/hnw/ai/core/controller/storage_controller.py
# -*- coding: utf-8 -*-
"""
StorageController
- 저장/조회 작업을 실제 StorageIF 구현체에 위임합니다.
- 'fetch_for_datasource(datasource_id, params)'를 표준 진입점으로 제공합니다.
- 기존 파일 기반으로 fetch_for_datasource(...) 메서드를 추가했습니다.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from com.hnw.ai.config.env import ROOT_DIR
from com.hnw.ai.core.service.storage_service_manager import StorageServiceManager
from com.hnw.ai.storage.base.storage_if import StorageIF

logger = logging.getLogger(__name__)


class StorageController:
    """
    StorageIF용 컨트롤러/파사드.
    """

    # -----------------------------
    # 생성/획득
    # -----------------------------
    def __init__(self, storage_id: str) -> None:
        """
        :param storage_id: 스토리지 서비스 식별자 (예: 'ods_oracle_dev')
        """
        self.storage_id: str = storage_id
        self.storage: StorageIF = StorageServiceManager.get_by_id(storage_id)

    # -----------------------------
    # 트랜잭션 도우미 (삼값 반환 해석)
    # -----------------------------
    def begin(self) -> Optional[bool]:
        """트랜잭션 시작 (true/false/None(미지원))"""
        return self.storage.begin()

    def commit(self) -> Optional[bool]:
        """트랜잭션 커밋 (true/false/None(미지원))"""
        return self.storage.commit()

    def rollback(self) -> Optional[bool]:
        """트랜잭션 롤백 (true/false/None(미지원))"""
        return self.storage.rollback()

    @contextmanager
    def transaction(self):
        """
        [편의] 컨텍스트 매니저 트랜잭션.
        begin()이 True가 아니면 RuntimeError로 빠르게 알립니다.
        """
        ok = self.begin()
        if ok is not True:
            raise RuntimeError(f"begin() failed or unsupported (result={ok!r})")
        try:
            yield self.storage
            self.commit()
        except Exception:
            try:
                self.rollback()
            finally:
                raise

    # -----------------------------
    # 데이터 입출력
    # -----------------------------
    def store(self, payload: Dict[str, Any]) -> Optional[Tuple[bool, Dict[str, Any]]]:
        """
        데이터 저장.
        - 구현체가 store를 미구현했거나 NotImplementedError를 던지면 None 반환 + 경고 로그.
        - 구현체 내부에서 발생한 다른 예외는 전파.
        """
        if not hasattr(self.storage, "store"):
            logger.warning("[StorageController] store() not implemented on storage '%s'", self.storage_id)
            return None
        try:
            return self.storage.store(payload)  # type: ignore[attr-defined]
        except NotImplementedError:
            logger.warning("[StorageController] store() is NotImplemented on storage '%s'", self.storage_id)
            return None

    def try_async_store(self, payload: Dict[str, Any]) -> None:
        """
        비동기 저장 시도.
        - 구현체가 store_async 미구현/NotImplemented면 경고 로그 후 동기 store로 폴백 시도.
        - 동기 store도 미구현이면 조용히 종료(None).
        """
        if hasattr(self.storage, "store_async"):
            try:
                self.storage.store_async(payload)  # type: ignore[attr-defined]
                return
            except NotImplementedError:
                logger.warning("[StorageController] store_async() NotImplemented on '%s', fallback to store()", self.storage_id)
            except Exception:
                raise
        _ = self.store(payload)

    def query_for_view(self, key_info: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """
        시각화/후속 처리용 단순 조회.
        - 구현체가 query_for_view_rows 미구현/NotImplemented면 None 반환 + 경고 로그.
        """
        if not hasattr(self.storage, "query_for_view_rows"):
            logger.warning("[StorageController] query_for_view_rows() not implemented on storage '%s'", self.storage_id)
            return None
        try:
            return self.storage.query_for_view_rows(key_info)  # type: ignore[attr-defined]
        except NotImplementedError:
            logger.warning("[StorageController] query_for_view_rows() is NotImplemented on storage '%s'", self.storage_id)
            return None

    def fetch_for_datasource(
        self,
        datasource_id: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[List[str]]]:
        """
        표준 조회 진입점: StorageIF.fetch_for_datasource(...)에 그대로 위임합니다.
        - 인터페이스 규약에 따라 (rows, columns)를 반환합니다.
        """
        if not hasattr(self.storage, "fetch_for_datasource"):
            logger.warning("[StorageController] fetch_for_datasource() not implemented on storage '%s'", self.storage_id)
            return [], None
        try:
            return self.storage.fetch_for_datasource(datasource_id, params or {})  # type: ignore[attr-defined]
        except NotImplementedError:
            logger.warning("[StorageController] fetch_for_datasource() is NotImplemented on storage '%s'", self.storage_id)
            return [], None

    # -----------------------------
    # (선택) SQL 포워딩
    # -----------------------------
    def execute(self, sql: str, params: Optional[Union[Sequence[Any], Mapping[str, Any]]] = None) -> Any:
        """변경성 쿼리(DML/DDL) 실행. 미구현이면 NotImplementedError 전파."""
        return self.storage.execute(sql, params)

    def executemany(self, sql: str, seq_of_params: Iterable[Union[Sequence[Any], Mapping[str, Any]]]) -> Any:
        """동일 SQL 배치 실행. 미구현이면 NotImplementedError 전파."""
        return self.storage.executemany(sql, seq_of_params)

    def query_one(self, sql: str, params: Optional[Union[Sequence[Any], Mapping[str, Any]]] = None) -> Optional[Tuple]:
        """단일 행 조회. 미구현이면 NotImplementedError 전파."""
        return self.storage.query_one(sql, params)

    def query_all(self, sql: str, params: Optional[Union[Sequence[Any], Mapping[str, Any]]] = None) -> List[Tuple]:
        """다중 행 조회. 미구현이면 NotImplementedError 전파."""
        return self.storage.query_all(sql, params)

    # -----------------------------
    # (선택) Object 포워딩
    # -----------------------------
    def put_object(self, bucket: str, key: str, data: bytes, **kwargs: Any) -> Any:
        """오브젝트 업로드/저장. 미구현이면 NotImplementedError 전파."""
        return self.storage.put_object(bucket, key, data, **kwargs)

    def get_object(self, bucket: str, key: str, **kwargs: Any) -> bytes:
        """오브젝트 다운로드. 미구현이면 NotImplementedError 전파."""
        return self.storage.get_object(bucket, key, **kwargs)

    def delete_object(self, bucket: str, key: str, **kwargs: Any) -> None:
        """오브젝트 삭제. 미구현이면 NotImplementedError 전파."""
        self.storage.delete_object(bucket, key, **kwargs)

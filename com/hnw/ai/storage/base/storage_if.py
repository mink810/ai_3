# -*- coding: utf-8 -*-
"""
com/hnw/ai/storage/base/storage_if.py

단일 인터페이스(StorageIF) 기반 공용 스토리지 인터페이스
======================================================

목적
----
- 모든 스토리지를 '하나의 방법론'으로 제어하기 위한 **단일 인터페이스**입니다.
- 컨트롤러/서비스는 항상 동일한 트랜잭션 API만 사용합니다:
  공식 패턴) begin() -> 작업 -> commit()/rollback()
  (편의)   ) with storage.transaction(): ...  # 테스트/샘플 용도

핵심 개념
---------
1) 트랜잭션 지원/방식(네이티브/보상/미지원)은 **구현체 내부**가 판단합니다.
   호출자는 오직 결과값만 해석합니다.
   - True  : 요청 성공
   - False : 시도했으나 실패(충돌/상태 불량 등)
   - None  : 미지원/무의미(이 구현체는 해당 동작을 제공하지 않음)

2) connect()는 '연결/초기화'만 수행합니다. 비즈니스 로직 금지.

3) 미지원 기능은 NotImplementedError로 명확히 드러내는 것을 원칙으로 합니다.
   (트랜잭션 API는 값 반환 표준화로 오사용을 예외 없이 알립니다.)

4) SQL/Object/KV/범용 데이터 입출력(store) 등 **모든 공용 시그니처를 StorageIF 하나에** 선언합니다.
   필요 없는 구현체는 오버라이드하지 않거나 NotImplementedError를 유지하면 됩니다.

컨트롤러 호출 패턴(매개변수 예시)
--------------------------------
# 트랜잭션
ok = storage.begin()  # Optional[bool] → True/False/None
try:
    # SQL
    storage.execute("UPDATE member SET name = :name WHERE id = :id", {"name": "홍길동", "id": 123})
    rows = storage.query_all("SELECT id, name FROM member WHERE city = :city", {"city": "서울"})
    # OBJECT
    storage.put_object(bucket="images", key="profile_201.png", data=b"...", content_type="image/png")
    # KV
    storage.kv_set("session:201", {"user": "이몽룡"}, ttl=3600)
    # 범용 데이터 저장/조회
    ok_store, key_info = storage.store({"timestamp": 1694567890, "source": "device_01", "value": 42.5})
    view_rows = storage.query_for_view_rows({"ts": 1694567890, "window_sec": 5, "source": "device_01"})
    if ok is not None:
        storage.commit()
    else:
        # begin 미지원(None) 시 상위 보상/우회 정책
        pass
except Exception:
    storage.rollback()  # 미지원이면 None 반환
    raise

주의
----
- set_autocommit()는 구현체가 미지원이면 None을 반환합니다(오사용을 예외 없이 값으로 알림).
- with transaction() 컨텍스트 매니저는 **편의 도구**입니다.
  begin()이 True가 아니면(=False/None) RuntimeError로 빠르게 이상을 알립니다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple, Union


# =============================================================================
# 트랜잭션 관측 정보(선택)
# =============================================================================
@dataclass
class TxInfo:
    """
    트랜잭션 상태 정보.

    Attributes
    ----------
    active : bool
        현재 트랜잭션 내 여부
    id     : Optional[str]
        (선택) 보상 트랜잭션 등에서 사용하는 트랜잭션 식별자(저널/스테이징 키 등)

    ParamDoc:
    --------
    @field active 현재 트랜잭션 내 여부
    @field id     보상 트랜잭션 식별자 (null 허용)
    """
    active: bool
    id: Optional[str] = None


# =============================================================================
# 단일 인터페이스
# =============================================================================
class StorageIF(ABC):
    """
    저장소 공통 인터페이스 (단일 클래스)

    설계 원칙
    ----------
    - 연결 수명 주기: connect / close / is_connected / health_check
    - 트랜잭션 수명 주기: begin / commit / rollback / set_autocommit / in_transaction / tx_info
      * 내부 구현(네이티브/보상/미지원)은 호출자에게 숨기고, 결과를 값(True/False/None)으로만 알립니다.
    - 기능 시그니처(SQL/Object/KV/범용 데이터 입출력)는 여기 한 곳에만 선언합니다.
      * 필요 없는 구현체는 미구현(NotImplementedError)로 둡니다.
    - 컨트롤러/서비스는 동일한 패턴만 사용합니다.

    ParamDoc:
    --------
    @interface StorageIF
    @description 모든 스토리지의 공통 메서드를 정의하는 최상위 인터페이스
    """

    # ---------------------------
    # 생성자
    # ---------------------------
    @abstractmethod
    def __init__(self, stype: str) -> None:
        """
        스토리지 유형 식별자(stype)를 초기화합니다.

        Python Docstring:
        -----------------
        Parameters
        ----------
        stype : str
            스토리지 유형 식별자 (예: "oracle", "postgres", "s3", "redis")

        구현체에서 설정 권장 필드
        ----------------------
        self._stype: str                  # 스토리지 구분자
        self._connected: bool             # 연결 상태 플래그
        self._capabilities: Set[str]      # {"sql"}, {"object"}, {"kv"}, {"data"}, {"tx"} 등
        self._tx_active: bool             # 트랜잭션 활성 여부
        self._tx_id: Optional[str]        # (선택) 보상 TX 식별자 등

        ParamDoc:
        -------
        @param stype 스토리지 유형 식별자 ("oracle", "postgres", "s3", "redis" 등)
        """
        ...

    # ---------------------------
    # 연결 수명 주기
    # ---------------------------
    @abstractmethod
    def connect(self, config: Dict[str, Any]) -> None:
        """
        설정(config)을 바탕으로 연결/초기화를 수행합니다.
        비즈니스 로직/쿼리 수행은 포함하지 않습니다.

        @param config 연결 설정값
        @throws Exception 연결 실패 시 예외 발생 가능(구현체 정책)
        """
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """
        현재 연결 상태를 반환합니다.

        @return 연결 여부 (true: 연결됨, false: 미연결)
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """
        연결 종료 및 리소스 해제.

        @throws Exception 종료 실패 시 예외 발생 가능(구현체 정책)
        """
        ...

    def health_check(self) -> bool:
        """
        기본 헬스체크: 연결 플래그 기반.
        필요 시 구현체에서 ping/쿼리로 override하세요.

        @return true: 연결됨 / false: 미연결
        """
        return bool(getattr(self, "_connected", False))

    # ---------------------------
    # 트랜잭션 수명 주기 (삼값 반환형)
    # ---------------------------
    def tx_info(self) -> TxInfo:
        """
        현재 트랜잭션 상태 정보 반환.

        @return TxInfo(active, id)
        """
        return TxInfo(
            active=self.in_transaction(),
            id=getattr(self, "_tx_id", None),
        )

    @abstractmethod
    def begin(self) -> Optional[bool]:
        """
        트랜잭션 시작.

        @return true(시작 성공) / false(시작 실패) / null(미지원)
        """
        ...

    @abstractmethod
    def commit(self) -> Optional[bool]:
        """
        트랜잭션 커밋.

        @return true(커밋 성공) / false(커밋 실패) / null(미지원)
        """
        ...

    @abstractmethod
    def rollback(self) -> Optional[bool]:
        """
        트랜잭션 롤백(보상 포함).

        @return true(롤백 성공) / false(롤백 실패) / null(미지원)
        """
        ...

    def set_autocommit(self, enabled: bool) -> Optional[bool]:
        """
        자동 커밋 설정.

        @param enabled true: 자동 커밋 켜기 / false: 끄기
        @return true(성공) / false(실패) / null(미지원)
        """
        return None  # 기본은 미지원/무의미

    def in_transaction(self) -> bool:
        """
        @return 현재 트랜잭션 활성 여부
        """
        return bool(getattr(self, "_tx_active", False))

    @contextmanager
    def transaction(self):
        """
        [편의] 컨텍스트 매니저. begin()이 True일 때만 진행합니다.
        begin()이 False/None인 경우 RuntimeError로 빠르게 이상을 알립니다.

        Usage
        -----
        with storage.transaction():
            storage.execute(...)
            storage.put_object(...)
            storage.kv_set(...)
        """
        ok = self.begin()
        if ok is not True:
            raise RuntimeError(f"{self.__class__.__name__}.begin() did not succeed (result={ok!r}).")
        try:
            yield self
            self.commit()
        except Exception:
            try:
                self.rollback()
            finally:
                raise

    # ---------------------------
    # 공용 시그니처: SQL (선택)
    # ---------------------------
    def execute(
        self,
        sql: str,
        params: Optional[Union[Sequence[Any], Mapping[str, Any]]] = None,
    ) -> Any:
        """
        변경성 쿼리(DML/DDL) 실행.

        예시
        ----
        # 회원 이름 변경
        storage.execute(
            "UPDATE member SET name = :name WHERE id = :id",
            {"name": "홍길동", "id": 123}
        )

        # 새 테이블 생성
        storage.execute(
            "CREATE TABLE product (id INT PRIMARY KEY, name VARCHAR(100))"
        )

        @param sql 실행할 SQL 문자열
        @param params 바인딩 파라미터(시퀀스/매핑)
        @return 실행 결과 (영향 행 수 또는 커서 등, 구현체 정책)
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support SQL execute().")

    def executemany(
        self,
        sql: str,
        seq_of_params: Iterable[Union[Sequence[Any], Mapping[str, Any]]],
    ) -> Any:
        """
        동일 SQL을 여러 파라미터 세트로 배치 실행.

        예시
        ----
        storage.executemany(
            "INSERT INTO member (id, name) VALUES (:id, :name)",
            [
                {"id": 201, "name": "이몽룡"},
                {"id": 202, "name": "성춘향"},
                {"id": 203, "name": "변학도"},
            ]
        )

        @param sql 실행할 SQL 문자열
        @param seq_of_params 파라미터 세트 목록
        @return 실행 결과 (총 영향 행 수 등, 구현체 정책)
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support SQL executemany().")

    def query_one(
        self,
        sql: str,
        params: Optional[Union[Sequence[Any], Mapping[str, Any]]] = None,
    ) -> Optional[Tuple]:
        """
        단일 행 조회.

        예시
        ----
        row = storage.query_one(
            "SELECT id, name, email FROM member WHERE id = :id",
            {"id": 201}
        )
        # row → (201, "이몽룡", "lmry@example.com") 또는 None

        @param sql SELECT 쿼리
        @param params 바인딩 파라미터
        @return 1행 튜플 또는 null
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support SQL query_one().")

    def query_all(
        self,
        sql: str,
        params: Optional[Union[Sequence[Any], Mapping[str, Any]]] = None,
    ) -> List[Tuple]:
        """
        다중 행 조회.

        예시
        ----
        rows = storage.query_all(
            "SELECT id, name FROM member WHERE city = :city",
            {"city": "서울"}
        )
        # rows → [(201, "이몽룡"), (202, "성춘향"), (205, "홍길동")] 또는 []

        @param sql SELECT 쿼리
        @param params 바인딩 파라미터
        @return 행 목록(List[Tuple])
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support SQL query_all()..")

    # ---------------------------
    # 공용 시그니처: 오브젝트 스토리지 (선택)
    # ---------------------------
    def put_object(self, bucket: str, key: str, data: bytes, **kwargs: Any) -> Any:
        """
        오브젝트 업로드/저장.

        예시
        ----
        storage.put_object(
            bucket="images",
            key="profile_201.png",
            data=b"...",          # 바이너리 데이터
            content_type="image/png"
        )

        @param bucket 버킷 이름
        @param key 오브젝트 키
        @param data 바이너리 데이터
        @param kwargs 추가 메타데이터(예: content_type 등)
        @return 업로드 결과(예: etag 또는 응답 객체, 구현체 정책)
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support put_object().")

    def get_object(self, bucket: str, key: str, **kwargs: Any) -> bytes:
        """
        오브젝트 다운로드.

        예시
        ----
        image_bytes = storage.get_object(
            bucket="images",
            key="profile_201.png"
        )

        @param bucket 버킷 이름
        @param key 오브젝트 키
        @param kwargs 추가 옵션(예: byte-range 등, 구현체 정책)
        @return 바이너리 데이터(bytes)
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support get_object().")

    def delete_object(self, bucket: str, key: str, **kwargs: Any) -> None:
        """
        오브젝트 삭제.

        예시
        ----
        storage.delete_object(
            bucket="images",
            key="profile_201.png"
        )

        @param bucket 버킷 이름
        @param key 오브젝트 키
        @param kwargs 추가 옵션
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support delete_object().")

    # ---------------------------
    # 공용 시그니처: Key-Value (선택)
    # ---------------------------
    def kv_set(self, key: str, value: Any, ttl: Optional[int] = None, **kwargs: Any) -> None:
        """
        KV 저장.

        예시
        ----
        storage.kv_set("session:201", {"user": "이몽룡"}, ttl=3600)

        @param key 키
        @param value 값(임의의 직렬화 정책은 구현체가 정의)
        @param ttl 만료 시간(초, null 허용)
        @param kwargs 추가 옵션
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support kv_set().")

    def kv_get(self, key: str, **kwargs: Any) -> Any:
        """
        KV 조회.

        예시
        ----
        session = storage.kv_get("session:201")

        @param key 키
        @param kwargs 추가 옵션(예: 디코딩 정책)
        @return 저장된 값 또는 None
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support kv_get().")

    def kv_delete(self, key: str, **kwargs: Any) -> None:
        """
        KV 삭제.

        예시
        ----
        storage.kv_delete("session:201")

        @param key 키
        @param kwargs 추가 옵션
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support kv_delete().")

    # ---------------------------
    # 공용 시그니처: 범용 데이터 입출력 (선택)
    # ---------------------------
    def store(self, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        범용 데이터 저장.

        예시
        ----
        ok, key_info = storage.store({
            "timestamp": 1694567890,
            "source": "device_01",
            "driver_id": "drv_1001",
            "value": 42.5
        })

        @param payload 저장할 데이터(dict)
        @return (ok, key_info) 튜플
                ok: 성공 여부
                key_info: 후속 조회 키(예: {"ts": <epoch>, "source": "...", "driver_id": "...", "window_sec": 5})
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support store().")

    def store_async(self, payload: Dict[str, Any]) -> None:
        """
        (선택) 비동기 저장.

        예시
        ----
        storage.store_async({
            "timestamp": 1694567890,
            "source": "device_01",
            "driver_id": "drv_1001",
            "value": 42.5
        })

        @param payload 저장할 데이터(dict)
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support store_async().")

    def query_for_view_rows(self, key_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        시각화/후속 처리에 바로 사용할 수 있는 형태로 조회.

        예시
        ----
        rows = storage.query_for_view_rows({
            "ts": 1694567890,
            "source": "device_01",
            "driver_id": "drv_1001",
            "window_sec": 5
        })
        # rows 예: [{"ts": 1694567890, "name": "rpm", "value": 720.0}, ...]

        @param key_info 조회 키 정보(예: ts/source/driver_id 등)
        @return 데이터 목록(List[Dict[str, Any]])
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support query_for_view_rows().")

    def fetch_for_datasource(
        self,
        datasource_id: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[List[str]]]:
        """
        (선택) 데이터소스 ID(문자열) 기반의 최종 결과 조회/가공 진입점.

        의도
        ----
        - UI/게이트웨이가 넘겨주는 `datasource_id`별로 간단한 if-분기 가공을 수행하고
          (또는 그대로 조회) 최종 (rows, columns)를 반환하기 위한 표준 메서드입니다.
        - 최소 구현은 params를 key_info로 활용하여 `query_for_view_rows(params or {})`
          를 호출한 뒤, columns가 없으면 rows[0].keys()로 유추하는 방식입니다.

        Parameters
        ----------
        datasource_id : str
            데이터소스 식별자(문자열)
        params : Optional[Dict[str, Any]]
            조회/가공에 필요한 선택 파라미터(dict)

        Returns
        -------
        Tuple[List[Dict[str, Any]], Optional[List[str]]]
            rows, columns
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support fetch_for_datasource().")

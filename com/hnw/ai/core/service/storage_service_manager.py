"""
StorageServiceManager

- storage_id → storage_config.json에서 (type, config_file[, class_path]) 조회
- 환경 config(dev/prod) 로드 후 class_path를 결정 (entry.class_path > env.class_path > type 기본)
- 구현체 생성 후 connect(config) 호출하여 초기화하고 반환.
"""

import json                                  # JSON 파싱
import importlib                              # 동적 import
from pathlib import Path                      # 경로 처리
from typing import Dict                       # 타입 힌트
from com.hnw.ai.storage.base.storage_if import StorageIF


# 프로젝트 루트 계산: __file__ 기준으로 상위 5단계( .../com/hnw/ai/... )
ROOT_DIR = Path(__file__).resolve().parents[5]    # 패키지 루트 기준
print("ROOT DIR=", ROOT_DIR)
STORAGE_CONFIG_PATH = ROOT_DIR / "com" / "hnw" / "ai" / "config" / "storage" / "storage_config.json"  # 스토리지 인덱스


def _load_json(path: Path):
    """
    JSON 파일 로드 도우미

    @param path: JSON 파일 Path
    @return: 파싱된 Python 객체
    """
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _new_from_classpath(class_path: str):
    """
    class_path로 모듈/클래스를 로드하고 인스턴스를 생성한다.

    @param class_path: "com...." 절대 import 경로
    @return: 인스턴스
    """
    module_name, class_name = class_path.rsplit(".", 1)   # 모듈/클래스 분리
    module = importlib.import_module(module_name)         # 모듈 import
    return getattr(module, class_name)                    # 클래스 인스턴스화(클래스 객체 반환)


def _default_class_path_for_type(stype: str) -> str:
    """
    스토리지 타입별 기본 클래스 경로 반환.

    @param stype: "oracle" | "postgres" | "mysql" | "s3" ...
    @return: class_path 문자열
    @raises ValueError: 미지원 타입일 경우
    """
    stype = (stype or "").lower()                         # 소문자 변환
    mapping = {
        "oracle":   "com.hnw.ai.storage.mod.oracle.oracle_storage.OracleStorage",
        "postgres": "com.hnw.ai.storage.mod.postgres.postgres_storage.PostgresStorage",
        "mysql":    "com.hnw.ai.storage.mod.mysql.mysql_storage.MySQLStorage",
        "s3":       "com.hnw.ai.storage.mod.s3.s3_storage.S3Storage",    # 콤마두는 것을 권장
    }
    cp = mapping.get(stype)                               # 매핑 조회
    if not cp:                                            # 없으면 예외
        raise ValueError(f"[storage] unsupported type: {stype}")
    return cp                                             # class_path 반환


class StorageServiceManager:
    """
    스토리지 서비스 매니저
    """

    @staticmethod
    def get_by_id(storage_id: str) -> StorageIF:
        """
        storage_id로 구현체를 선택/생성한다.

        절차:
          1) storage_config.json에서 id 매칭 엔트리 찾기
          2) type/config_file 확인
          3) 환경 config 로드(예: storage/oracle/dev.json)
          4) class_path 결정: entry.class_path > env.class_path > type 기본
          5) 구현체 생성 후 connect(config)

        @param storage_id: 예) "ods_oracle_dev"
        @return: 스토리지 구현체 인스턴스(이미 connect됨)
        """
        if not STORAGE_CONFIG_PATH.exists():                              # 인덱스 존재 검사
            raise FileNotFoundError(f"storage_config.json not found: {STORAGE_CONFIG_PATH}")

        cfg = _load_json(STORAGE_CONFIG_PATH)                             # 인덱스 로드
        entry = next((s for s in cfg.get("storages", [])                  # id 또는 name 일치 항목 탐색(호환)
                      if s.get("id").lower() == storage_id.lower()), None)
        if not entry:                                                     # 못 찾으면 예외
            raise ValueError(f"[storage] unknown id: {storage_id}")

        stype = entry.get("type")                                         # 타입
        sconfig_file = entry.get("config_file")                           # sconfig_file은 해당 conf file의 경로를 명시
        if not stype or not sconfig_file:                                 # 필수 값 확인
            raise ValueError(f"[storage] type/config_file required for id={storage_id}")

        conf_path = (STORAGE_CONFIG_PATH.parent / sconfig_file).resolve() # 환경 파일 절대경로
        if not conf_path.exists():                                        # 존재 검사
            raise FileNotFoundError(f"[storage] env config not found: {conf_path}")
        sconf: Dict = _load_json(conf_path)                               # 환경 설정 로드

        class_path = _default_class_path_for_type(stype)                  # 해당하는 클래스 패스의 객체를 가져옴

        klass = _new_from_classpath(class_path)      
        
        try:
            storage = klass(stype)   # 생성자에 stype을 요구하는 구현체 대응
        except TypeError:
            storage = klass()        # 무인자 생성자만 있는 구현체 폴백

        # 인스턴스 생성
        if hasattr(storage, "connect") and callable(getattr(storage, "connect")):  # OracleStorage의 connect 메소드 호출
            storage.connect(sconf)                                                 # 접속/초기화, sconf 딕셔너리를 매개변수로 보냄 
            
        return storage                                                             # 구현체 반환, storage는 connection 객체를 소유하고 있는 클래스 인스턴스

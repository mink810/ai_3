# main.py
# -*- coding: utf-8 -*-
"""
목적:
- 지정한 VIEW_ID에 해당하는 View를 구동한다.
- Tkinter(블로킹) vs HTML/React/Vue(비블로킹 서버)를 자동 감지해 메인 스레드를 유지한다.
- HTMLView 등은 /request 처리에 UiGateway가 필요하므로, 여기서 gateway를 생성/배선한다.
"""

from __future__ import annotations

import time
from typing import Optional

from com.hnw.ai.config.env import ROOT_DIR
from com.hnw.ai.core.service.view_service_manager import ViewServiceManager
from com.hnw.ai.view.base.view_if import ViewIF
from com.hnw.ai.view.gateway.uigateway import UiGateway

# ===== 실행할 뷰 ID를 지정 =====
# 필요 시 "view_tk_dev", "view_react_dev", "view_vue_dev" 등으로 변경
# view_config.json에 등록된 ID여야 함
#VIEW_ID = "view_react_dev"
#VIEW_ID = "view_tk_dev"
#VIEW_ID = "view_html_dev"   
#VIEW_ID = "view_vue_dev"
#VIEW_ID = "view_tk_dev"
VIEW_ID = "view_image_classification_dev"  # 이미지 분류 학습 모니터링 뷰

def _print_launch_hint(view: ViewIF) -> None:
    """
    비블록형(HTML/React/Vue) 뷰의 접근 정보를 안내한다.
    dev.json은 상위에서 로드되어 view._config에 전달되어 있음(읽기 전용 사용).
    """
    try:
        cfg = getattr(view, "_config", {}) or {}
        host = cfg.get("host")
        port = cfg.get("port")
        entry = cfg.get("entry_html")
        ws = cfg.get("ws_path")
        req = cfg.get("request_path")
        if host and port:
            print(f"[main] 접속: http://{host}:{port}/")
            if entry:
                print(f"[main] entry_html = {entry}")
            if ws or req:
                print(f"[main] endpoints: ws={ws or '/ws'}, request={req or '/request'}")
    except Exception:
        pass


def main() -> None:
    print(f"[main] ROOT_DIR = {ROOT_DIR}")
    print(f"[main] VIEW_ID  = {VIEW_ID}")
    print("[main] 안내: 종료하려면 창을 닫거나 Ctrl+C 를 누르세요.")

    # 1) View 생성 (서비스 매니저가 view_config.json을 읽어 적절한 클래스를 로드)
    view: ViewIF = ViewServiceManager.get_by_id(VIEW_ID)

    # 2) UiGateway 생성 및 배선 (조회/콜백 파이프는 기존 로직 그대로)
    gateway = UiGateway()
    
    # 이미지 분류용 설정: MySQL 스토리지만 사용 (attach_view 전에 설정)
    gateway.connect({
        "controllers": {
            "storage_ids": ["ai_data_mysql_dev"],  # MySQL만 사용
            "driver_ids": []  # 드라이버 사용 안함
        }
    })
    
    gateway.attach_view(view)     # 조회 완료 시 view.on_rows(...) 호출됨

    # HTML/React/Vue에서 /request 처리에 필요 → 게이트웨이 역주입
    if hasattr(view, "attach_gateway"):
        try:
            view.attach_gateway(gateway)   # HTMLView 등에서 사용
        except Exception:
            pass

    # 3) UI 시작
    try:
        view.start()  # Tkinter는 내부 mainloop로 블로킹, 비블록형은 서버만 띄우고 반환

        vtype: Optional[str] = getattr(view, "vtype", None)
        if vtype and vtype.lower() in ("html", "react", "vue"):
            # 비블록형 서버 → 메인 스레드 유지
            _print_launch_hint(view)
            while True:
                time.sleep(1)
        else:
            # Tkinter 등 블로킹형이면 여기로 오지 않거나, 왔다면 즉시 종료 단계로 이동
            pass

    except KeyboardInterrupt:
        print("\n[main] KeyboardInterrupt 수신: 종료 처리 중...")

    finally:
        try:
            view.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()

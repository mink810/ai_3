# com/hnw/ai/view/mod/project1/html/html_view.py
# -*- coding: utf-8 -*-
"""
HTMLView (Minimal Patch - config 불변/비소유 원칙)
- 이 클래스는 설정을 '읽기만' 합니다. (dev.json은 상위에서 로드/검증)
- connect(config): 전달받은 config를 그대로 저장(추가/수정/기본값 주입 금지)
- start(): 필수 키 누락 시 예외 발생 → 상위 초기화 계층에서 처리
- on_rows(): WS로 브라우저에 브로드캐스트
- attach_gateway(): 외부에서 주입된 UiGateway만 사용
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from com.hnw.ai.view.base.view_if import ViewIF
from com.hnw.ai.view.gateway.uigateway import UiGateway


class _WsHub:
    """아주 단순한 WebSocket 허브."""
    def __init__(self) -> None:
        self._clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def register(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.add(ws)

    async def unregister(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast_json(self, payload: Dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False)
        async with self._lock:
            dead: List[WebSocket] = []
            for ws in list(self._clients):
                try:
                    await ws.send_text(data)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._clients.discard(ws)


class HTMLView(ViewIF):
    """
    - 설정(dev.json)은 상위 계층 소유. 여기서는 '읽기 전용'.
    - 필수 키:
        host(str), port(int), entry_html(str), static_dir(str),
        ws_path(str), request_path(str)
      선택 키:
        title(str, 없으면 안내문에만 영향), spa_mode(bool)
    """
    def __init__(self, vtype: str = "html") -> None:
        super().__init__(vtype)
        self._hub = _WsHub()
        self._gateway: Optional[UiGateway] = None
        self._app: Optional[FastAPI] = None
        self._server_thread: Optional[threading.Thread] = None
        self._uv_loop: Optional[asyncio.AbstractEventLoop] = None
        self._config: Dict[str, Any] = {}  # 불변 원칙: connect에서 받은 그대로 저장

    # 외부에서 게이트웨이 주입 (필수)
    def attach_gateway(self, gateway: UiGateway) -> None:
        self._gateway = gateway

    # 설정 주입 (읽기 전용으로 보관; 변형 금지)
    def connect(self, config: Dict[str, Any]) -> bool:
        # 상위에서 이미 dev.json을 로드/검증했다고 가정하고 '그대로' 받음
        self._config = dict(config) if config is not None else {}
        return True

    def start(self) -> None:
        if self._app is not None:
            return  # 이미 시작됨

        # 필수 키 검증 (부족하면 즉시 실패시켜 상위 초기화에서 원인 파악이 가능하게 함)
        required = ["host", "port", "entry_html", "static_dir", "ws_path", "request_path"]
        missing = [k for k in required if k not in self._config or self._config[k] in (None, "")]
        if missing:
            raise RuntimeError(f"HTMLView config missing required keys: {', '.join(missing)}")

        # 읽기 전용 추출 (기본값 주입 금지)
        host: str = str(self._config["host"])
        port: int = int(self._config["port"])
        entry_html_path = self._config["entry_html"]
        static_dir_path = self._config["static_dir"]
        ws_path: str = str(self._config["ws_path"])
        request_path: str = str(self._config["request_path"])

        # 선택 키 (없어도 동작에 치명적 영향 없음) - 값 미존재 시 None/False로만 처리
        title: Optional[str] = self._config.get("title")
        spa_mode: bool = bool(self._config.get("spa_mode", False))

        app = FastAPI()
        entry_html = self._resolve_path(entry_html_path)
        static_dir = self._resolve_path(static_dir_path)

        # 정적 파일 서빙
        if static_dir and static_dir.is_dir():
            app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        # 최초 진입
        @app.get("/")
        def get_index():
            if entry_html and entry_html.is_file():
                return FileResponse(str(entry_html))
            txt = title or "HTML View"
            return HTMLResponse(f"<h1>{txt}</h1><p>entry_html이 유효하지 않습니다.</p>", status_code=500)

        # SPA 모드: 비정규 경로 폴백
        if spa_mode:
            @app.get("/{full_path:path}")
            def spa_fallback(full_path: str):
                if entry_html and entry_html.is_file():
                    return FileResponse(str(entry_html))
                txt = title or "HTML View"
                return HTMLResponse(f"<h1>{txt}</h1><p>Not Found: /{full_path}</p>", status_code=404)

        # 조회 트리거 → UiGateway.request_data 위임
        @app.post(request_path)
        async def api_request(req: Request):
            if self._gateway is None:
                return JSONResponse({"ok": False, "error": "gateway not attached"}, status_code=503)
            try:
                body = await req.json()
            except Exception:
                body = {}
            index = str(body.get("index") or "").strip()
            options = body.get("options") or {}
            if not index:
                return JSONResponse({"ok": False, "error": "index required"}, status_code=400)
            self._gateway.request_data(index, options=options)
            return {"ok": True}

        # WebSocket (View.on_rows에서 브로드캐스트)
        @app.websocket(ws_path)
        async def ws_endpoint(ws: WebSocket):
            await ws.accept()
            await self._hub.register(ws)
            self._uv_loop = asyncio.get_running_loop()
            try:
                while True:
                    await ws.receive_text()  # 클라이언트 메시지는 사용하지 않음
            except WebSocketDisconnect:
                pass
            finally:
                await self._hub.unregister(ws)

        self._app = app

        def _run():
            uvicorn.run(self._app, host=host, port=port, log_level="info")

        self._server_thread = threading.Thread(target=_run, daemon=True)
        self._server_thread.start()

    # 기존 계약: 조회 결과 수신 → 브라우저로 푸시
    def on_rows(self, index: str, rows: List[Dict[str, Any]], columns: Optional[List[str]] = None) -> None:
        payload = {"type": "rows", "index": index, "columns": columns, "rows": rows}
        if self._uv_loop is None:
            return
        fut = asyncio.run_coroutine_threadsafe(self._hub.broadcast_json(payload), self._uv_loop)
        try:
            fut.result(timeout=1.0)
        except Exception:
            pass

    def close(self) -> None:
        # 필요 시 서버 종료 로직 추가 가능(여기서는 생략)
        pass

    def _resolve_path(self, p: Any) -> Optional[Path]:
        if not p:
            return None
        return Path(str(p)).expanduser().resolve()

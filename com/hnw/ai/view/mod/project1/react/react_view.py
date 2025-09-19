# com/hnw/ai/view/mod/project1/react/react_view.py
# -*- coding: utf-8 -*-
"""
ReactView (standalone)
- 다른 View 구현에 의존하지 않는 독립 구현.
- 기존 플랫폼 로직은 그대로: 브라우저 ←WS 푸시 / →POST /request 트리거.
- 설정(dev.json)은 상위에서 로드/검증되고, 여기서는 '읽기 전용'으로만 사용.

필수 config 키:
  host(str), port(int), entry_html(str), static_dir(str), ws_path(str), request_path(str)
선택 키:
  title(str), spa_mode(bool)
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
    """아주 단순한 WebSocket 허브(독립 구현)."""
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


class ReactView(ViewIF):
    """
    독립 구현 ReactView:
      - vtype="react"
      - connect(config): config를 '그대로' 보관(가공/기본값 주입 금지)
      - start(): FastAPI/uvicorn 기동, 정적 서빙 + /request + /ws
      - on_rows(...): WS 브로드캐스트
      - attach_gateway(gateway): 외부에서 주입된 UiGateway만 사용
    """
    def __init__(self) -> None:
        super().__init__(vtype="react")
        self._hub = _WsHub()
        self._gateway: Optional[UiGateway] = None
        self._app: Optional[FastAPI] = None
        self._server_thread: Optional[threading.Thread] = None
        self._uv_loop: Optional[asyncio.AbstractEventLoop] = None
        self._config: Dict[str, Any] = {}  # read-only 보관

    # 외부 주입 (필수)
    def attach_gateway(self, gateway: UiGateway) -> None:
        self._gateway = gateway

    # 설정 주입 (읽기 전용)
    def connect(self, config: Dict[str, Any]) -> bool:
        self._config = dict(config) if config is not None else {}
        return True

    def start(self) -> None:
        if self._app is not None:
            return

        # 필수 키 검증
        required = ["host", "port", "entry_html", "static_dir", "ws_path", "request_path"]
        missing = [k for k in required if k not in self._config or self._config[k] in (None, "")]
        if missing:
            raise RuntimeError(f"ReactView config missing required keys: {', '.join(missing)}")

        host: str = str(self._config["host"])
        port: int = int(self._config["port"])
        entry_html_path = self._config["entry_html"]
        static_dir_path = self._config["static_dir"]
        ws_path: str = str(self._config["ws_path"])
        request_path: str = str(self._config["request_path"])

        title: Optional[str] = self._config.get("title")
        spa_mode: bool = bool(self._config.get("spa_mode", False))

        app = FastAPI()
        entry_html = self._resolve_path(entry_html_path)
        static_dir = self._resolve_path(static_dir_path)

        # ✅ 정적 파일 서빙 (Vite 빌드 산출물 구조에 맞춤)
        # Vite는 /assets/* 경로로 JS/CSS를 로드합니다.
        # -> /assets를 dist/assets 디렉터리로 직접 마운트해야 SPA 폴백에 가리지 않습니다.
        if static_dir and static_dir.is_dir():
            assets_dir = static_dir / "assets"
            if assets_dir.is_dir():
                app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
            # favicon 등 단일 파일 처리(있을 때만)
            fav = static_dir / "favicon.ico"
            if fav.is_file():
                @app.get("/favicon.ico")
                def _favicon():
                    return FileResponse(str(fav))

        # 최초 진입
        @app.get("/")
        def get_index():
            if entry_html and entry_html.is_file():
                return FileResponse(str(entry_html))
            txt = title or "React View"
            return HTMLResponse(f"<h1>{txt}</h1><p>entry_html이 유효하지 않습니다.</p>", status_code=500)

        # ✅ SPA 폴백: 정적 경로(assets, favicon)는 제외
        if spa_mode:
            @app.get("/{full_path:path}")
            def spa_fallback(full_path: str):
                # 정적 경로는 폴백 금지
                if full_path.startswith("assets/") or full_path == "favicon.ico":
                    return HTMLResponse("Not Found", status_code=404)
                if entry_html and entry_html.is_file():
                    return FileResponse(str(entry_html))
                txt = title or "React View"
                return HTMLResponse(f"<h1>{txt}</h1><p>Not Found: /{full_path}</p>", status_code=404)

        # 데이터 트리거: 브라우저 → POST /request → UiGateway.request_data(...)
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

        # WebSocket: on_rows(...) → 여기로 브로드캐스트
        @app.websocket(ws_path)
        async def ws_endpoint(ws: WebSocket):
            await ws.accept()
            await self._hub.register(ws)
            self._uv_loop = asyncio.get_running_loop()
            try:
                while True:
                    # 클라이언트 메시지는 현재 사용하지 않음(필요하면 ping/pong 등 확장 가능)
                    await ws.receive_text()
            except WebSocketDisconnect:
                pass
            finally:
                await self._hub.unregister(ws)

        self._app = app

        def _run():
            uvicorn.run(self._app, host=host, port=port, log_level="info")

        self._server_thread = threading.Thread(target=_run, daemon=True)
        self._server_thread.start()

    # ViewIF 계약: 조회 결과 수신 → 브라우저로 푸시
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
        # 필요 시 서버 종료/정리 로직 추가 가능(현재는 생략)
        pass

    def _resolve_path(self, p: Any) -> Optional[Path]:
        if not p:
            return None
        return Path(str(p)).expanduser().resolve()

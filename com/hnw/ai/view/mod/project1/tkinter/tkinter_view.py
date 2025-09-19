# com/hnw/ai/view/mod/project1/tkinter/tkinter_view.py
# -*- coding: utf-8 -*-
"""
TkinterView (2-pane, 고정 UI, 문자열 데이터소스 ID 전용)
- 상/하 2개의 Treeview를 제공하고, 디자이너가 고정한 데이터소스 ID로 조회합니다.
- 자동 갱신(ON/OFF, 간격 ms 조절), 수동 새로고침, 정렬/초기화, 표 지우기 제공.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
import datetime

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except Exception as e:
    raise RuntimeError("Tkinter import 실패: 데스크톱 환경/라이브러리를 확인해 주세요.") from e

from com.hnw.ai.view.base.view_if import ViewIF
from com.hnw.ai.view.gateway.uigateway import UiGateway

PaneId = str  # 'top' | 'bottom'


class TkinterView(ViewIF):
    def __init__(self, vtype: str = "tkinter") -> None:
        super().__init__(vtype)

        # ----- 기본 UI 설정 -----
        self._window_title: str = "AI Platform Viewer - Two Pane"
        self._geometry: str = "1200x750"
        self._max_rows: int = 300
        self._autosize_min: int = 80
        self._autosize_max: int = 320

        # ----- 자동 갱신 기본 -----
        self._auto_refresh_default_enabled: bool = True
        self._auto_refresh_default_ms: int = 1000

        # 디자이너 고정 데이터소스 ID
        self._ds_id_for_pane: Dict[PaneId, Optional[str]] = {
            "top": "ds_top",
            "bottom": "ds_bottom",
        }

        # Tk 루트/프레임 구성
        self._root = tk.Tk()
        self._root.title(self._window_title)
        self._root.geometry(self._geometry)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close_request)

        menubar = tk.Menu(self._root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="종료", command=self._on_close_request)
        menubar.add_cascade(label="파일", menu=filemenu)
        self._root.config(menu=menubar)

        self._top_frame = ttk.Frame(self._root)
        self._bottom_frame = ttk.Frame(self._root)
        self._top_frame.pack(fill=tk.BOTH, expand=True)
        self._bottom_frame.pack(fill=tk.BOTH, expand=True)

        # 상태/매핑
        self._closing: bool = False
        self._widgets: Dict[PaneId, Dict[str, Any]] = {}
        self._sort_state: Dict[PaneId, Tuple[str, bool]] = {}  # (column, ascending)
        self._pane_for_index: Dict[str, PaneId] = {}
        self._index_for_pane: Dict[PaneId, Optional[str]] = {"top": None, "bottom": None}
        self._columns_for_pane: Dict[PaneId, List[str]] = {"top": [], "bottom": []}

        # 게이트웨이(지연 생성)
        self._gateway: Optional[UiGateway] = None

        # ★ 자동갱신 상태/타이머 관리(각 pane 별) — 반드시 위젯 생성 전에 초기화
        self._pane_auto_enabled: Dict[PaneId, tk.BooleanVar] = {}
        self._pane_auto_ms: Dict[PaneId, tk.StringVar] = {}
        self._pane_auto_job: Dict[PaneId, Optional[str]] = {"top": None, "bottom": None}

        # Pane UI 구성
        self._build_pane_widgets("top", self._top_frame, "상단")
        self._build_pane_widgets("bottom", self._bottom_frame, "하단")

        # 전역 상태바
        self._global_status = tk.Label(self._root, text="대기 중", anchor="w")
        self._global_status.pack(fill=tk.X, side=tk.BOTTOM)

        # 디자이너 고정 ID를 Pane에 바인딩
        for pane in ("top", "bottom"):
            ds_id = self._ds_id_for_pane[pane]  # type: ignore[index]
            if ds_id:
                self._assign_index_to_pane(pane, ds_id)
                self._widgets[pane]["title_label"].config(text=f"{ds_id}")

    # ---------------- ViewIF 구현 ---------------- #

    def connect(self, config: Dict[str, Any]) -> bool:
        """UI 설정을 반영합니다. (데이터 통신 X)"""
        if not config:
            self._root.after(50, self._initial_requests)
            self._root.after(100, lambda: self._set_global_status("실행 중"))
            return True

        self._config.update(config)

        title = config.get("window_title")
        if title:
            self._window_title = str(title)
            self._root.title(self._window_title)

        geometry = config.get("geometry")
        if geometry:
            self._geometry = str(geometry)
            self._root.geometry(self._geometry)

        self._max_rows = int(config.get("max_rows", self._max_rows))
        self._autosize_min = int(config.get("autosize_min", self._autosize_min))
        self._autosize_max = int(config.get("autosize_max", self._autosize_max))

        # 자동갱신 전역 기본값
        if "auto_refresh" in config:
            self._auto_refresh_default_enabled = bool(config.get("auto_refresh"))
        if "auto_refresh_ms" in config:
            try:
                self._auto_refresh_default_ms = max(200, int(config.get("auto_refresh_ms")))
            except Exception:
                pass

        self._root.after(50, self._initial_requests)
        self._root.after(100, lambda: self._set_global_status("실행 중"))
        return True

    def start(self) -> None:
        self._root.mainloop()

    def on_rows(
        self,
        index: str,
        rows: List[Dict[str, Any]],
        columns: Optional[List[str]] = None,
    ) -> None:
        """UiGateway → View: 조회 결과 수신"""
        self._root.after(0, lambda: self._apply_rows_ui_thread(index, rows, columns))

    def close(self) -> None:
        """View 종료 및 타이머/게이트웨이 정리"""
        self._closing = True
        # 자동갱신 타이머 해제
        for pane in ("top", "bottom"):
            self._cancel_auto_for_pane(pane)

        try:
            if self._root and self._root.winfo_exists():
                self._root.after(0, self._root.destroy)
        except Exception:
            pass
        try:
            if self._gateway:
                self._gateway.close()
        except Exception:
            pass

    # ---------------- 초기 자동 조회/갱신 ---------------- #

    def _initial_requests(self) -> None:
        gw = self._ensure_gateway()
        for pane in ("top", "bottom"):
            ds_id = self._index_for_pane[pane]
            label = pane.upper()
            if not ds_id:
                self._set_global_status(f"{label} | 데이터소스 ID 미지정: 요청 생략")
                continue
            self._set_global_status(f"{label} | index {ds_id} 자동 조회 요청")
            gw.request_data(ds_id, options={})

            # 각 Pane 자동갱신 시작(기본값 기반)
            self._ensure_auto_controls_initialized(pane)
            if self._pane_auto_enabled[pane].get():
                self._schedule_auto_for_pane(pane)

    # ---------------- Pane UI 구성 ---------------- #

    def _build_pane_widgets(self, pane: PaneId, parent: tk.Widget, label_prefix: str) -> None:
        title_bar = ttk.Frame(parent)
        title_bar.pack(fill=tk.X, side=tk.TOP, padx=6, pady=(6, 0))

        title_label = tk.Label(title_bar, text=f"{label_prefix}", anchor="w")
        title_label.pack(side=tk.LEFT)

        toolbar = ttk.Frame(parent)
        toolbar.pack(fill=tk.X, side=tk.TOP)

        ttk.Button(toolbar, text="새로고침", command=lambda p=pane: self._request_for_pane(p)).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Button(toolbar, text="표 지우기", command=lambda p=pane: self._clear_table(p)).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Button(toolbar, text="정렬 초기화", command=lambda p=pane: self._reset_sort(p)).pack(side=tk.LEFT, padx=4, pady=4)

        # 자동갱신 컨트롤(체크 + 간격 ms)
        auto_frame = ttk.Frame(toolbar)
        auto_frame.pack(side=tk.RIGHT, padx=4, pady=4)

        auto_var = tk.BooleanVar(value=self._auto_refresh_default_enabled)
        self._pane_auto_enabled[pane] = auto_var
        auto_check = ttk.Checkbutton(auto_frame, text="자동갱신", variable=auto_var,
                                     command=lambda p=pane: self._toggle_auto(p))
        auto_check.pack(side=tk.LEFT)

        ms_var = tk.StringVar(value=str(self._auto_refresh_default_ms))
        self._pane_auto_ms[pane] = ms_var
        tk.Label(auto_frame, text="간격(ms)").pack(side=tk.LEFT, padx=(8, 2))
        ms_spin = tk.Spinbox(auto_frame, from_=200, to=60000, increment=100, width=7, textvariable=ms_var,
                             command=lambda p=pane: self._reschedule_auto_if_running(p))
        ms_spin.pack(side=tk.LEFT)

        # Tree + Scrollbar
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        tree = ttk.Treeview(tree_frame, columns=(), show="headings")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        status_label = tk.Label(parent, text=f"{label_prefix} | 대기 중", anchor="w")
        status_label.pack(fill=tk.X, side=tk.BOTTOM, padx=6, pady=(0, 6))

        self._widgets[pane] = {
            "title_label": title_label,
            "toolbar": toolbar,
            "tree": tree,
            "status": status_label,
            "auto_var": auto_var,
            "auto_ms_var": ms_var,
        }

    # ---------------- Gateway/요청 ---------------- #

    def _ensure_gateway(self) -> UiGateway:
        if self._gateway is None:
            self._gateway = UiGateway()
            self._gateway.attach_view(self)
        return self._gateway

    def _request_for_pane(self, pane: PaneId) -> None:
        idx = self._index_for_pane.get(pane)
        if not idx:
            self._set_global_status(f"{pane.upper()} | index 미지정: 조회 생략")
            return
        self._set_global_status(f"{pane.upper()} | index {idx} 새로고침 요청")
        gw = self._ensure_gateway()
        gw.request_data(idx, options={})

    # ---------------- on_rows → UI 적용 ---------------- #

    def _apply_rows_ui_thread(self, index: str, rows: List[Dict[str, Any]], columns: Optional[List[str]]) -> None:
        if self._closing or not self._root or not self._root.winfo_exists():
            return

        pane = self._resolve_pane_for_index(index)
        if pane is None:
            # 디버깅 힌트
            print(f"[TkinterView] Unknown index '{index}', mapped = {self._pane_for_index}")
            return

        tree: ttk.Treeview = self._widgets[pane]["tree"]
        status: tk.Label = self._widgets[pane]["status"]

        # 1) 컬럼 결정
        desired_cols = self._resolve_columns(rows, columns)

        # 2) 헤더/열 재구성 (필요 시)
        cur_cols = self._columns_for_pane[pane]
        if desired_cols != cur_cols:
            self._rebuild_tree_columns(tree, desired_cols, pane)
            self._columns_for_pane[pane] = desired_cols
            self._sort_state.pop(pane, None)

        # 3) 데이터 채우기 (정렬 상태 적용)
        rows = self._apply_sort_to_rows(pane, rows, desired_cols)
        self._fill_tree(tree, rows, desired_cols)

        # 상태 업데이트
        status.config(text=f"{pane.upper()} | 수신 {len(rows)}건")
        self._set_global_status(f"{pane.upper()} | index {index} 수신: {len(rows)}건")

    # ---------------- 자동 갱신 제어 ---------------- #

    def _schedule_auto_for_pane(self, pane: PaneId) -> None:
        self._cancel_auto_for_pane(pane)
        try:
            ms = int(self._pane_auto_ms[pane].get())
        except Exception:
            ms = self._auto_refresh_default_ms
        if ms < 200:
            ms = 200

        def _task():
            if self._closing:
                return
            self._request_for_pane(pane)
            self._schedule_auto_for_pane(pane)

        self._pane_auto_job[pane] = self._root.after(ms, _task)

    def _cancel_auto_for_pane(self, pane: PaneId) -> None:
        job = self._pane_auto_job.get(pane)
        if job:
            try:
                self._root.after_cancel(job)
            except Exception:
                pass
        self._pane_auto_job[pane] = None

    def _toggle_auto(self, pane: PaneId) -> None:
        if self._pane_auto_enabled[pane].get():
            self._schedule_auto_for_pane(pane)
        else:
            self._cancel_auto_for_pane(pane)

    def _reschedule_auto_if_running(self, pane: PaneId) -> None:
        if self._pane_auto_enabled[pane].get():
            self._schedule_auto_for_pane(pane)

    def _ensure_auto_controls_initialized(self, pane: PaneId) -> None:
        if pane not in self._pane_auto_enabled:
            self._pane_auto_enabled[pane] = tk.BooleanVar(value=self._auto_refresh_default_enabled)
            self._pane_auto_ms[pane] = tk.StringVar(value=str(self._auto_refresh_default_ms))

    # ---------------- Treeview 도우미 ---------------- #

    def _resolve_columns(self, rows: List[Dict[str, Any]], columns: Optional[List[str]]) -> List[str]:
        """표시할 컬럼 순서를 결정: columns 우선, 없으면 첫 행의 키 순서."""
        if columns and len(columns) > 0:
            return list(columns)
        if rows and isinstance(rows[0], dict):
            return list(rows[0].keys())
        return []

    def _rebuild_tree_columns(self, tree: ttk.Treeview, columns: List[str], pane: PaneId) -> None:
        """Treeview 컬럼/헤더 재구성."""
        tree["columns"] = columns
        tree["show"] = "headings"

        # 기존 모든 행 삭제
        for iid in tree.get_children():
            tree.delete(iid)

        # 헤더/열 폭 설정
        for col in columns:
            tree.heading(col, text=col, command=lambda c=col, p=pane: self._sort_by_column(p, c))
            tree.column(col, width=120, stretch=True, anchor="center")

    def _fill_tree(self, tree: "ttk.Treeview", rows: List[Dict[str, Any]], columns: List[str]) -> None:
        """행 채우기: 컬럼 순서에 맞춰 값 tuple 삽입."""
        if self._max_rows and len(rows) > self._max_rows:
            rows = rows[-self._max_rows :]

        for iid in tree.get_children():
            tree.delete(iid)

        for row in rows:
            vals = []
            for c in columns:
                v = row.get(c, "")
                # ★ timestamp 컬럼은 사람이 읽기 좋은 문자열로 변환
                if c.lower() in ("timestamp", "ts_utc", "ts") and isinstance(v, (int, float)):
                    try:
                        dt = datetime.datetime.fromtimestamp(v)  # 로컬 시간대 기준
                        v = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        pass
                vals.append(v)
            tree.insert("", "end", values=tuple(vals))

    # ---------------- 정렬/표시 보조 ---------------- #

    def _apply_sort_to_rows(self, pane: PaneId, rows: List[Dict[str, Any]], columns: List[str]) -> List[Dict[str, Any]]:
        """현재 pane의 정렬 상태를 rows에 적용해 반환."""
        state = self._sort_state.get(pane)
        if not state or not rows or not columns:
            return rows
        col_name, ascending = state
        if col_name not in columns:
            return rows

        def _cast(v: Any):
            try:
                return float(v)
            except Exception:
                return str(v)

        return sorted(rows, key=lambda r: _cast(r.get(col_name, "")), reverse=not ascending)

    def _sort_by_column(self, pane: PaneId, column: str) -> None:
        """현재 표시된 행을 기준으로 Treeview 정렬 토글."""
        tree: ttk.Treeview = self._widgets[pane]["tree"]
        data = []
        for iid in tree.get_children():
            vals = tree.item(iid, "values")
            data.append((iid, vals))

        # 현재 컬럼 인덱스
        try:
            col_idx = self._columns_for_pane[pane].index(column)
        except ValueError:
            return

        asc = True
        if pane in self._sort_state and self._sort_state[pane][0] == column:
            asc = not self._sort_state[pane][1]
        self._sort_state[pane] = (column, asc)

        def _cast(v: str):
            # 숫자 변환 가능하면 숫자로 정렬, 아니면 문자열
            try:
                return float(v)
            except Exception:
                return v

        data.sort(key=lambda item: _cast(item[1][col_idx]), reverse=not asc)

        # 재배치
        for index, (iid, _) in enumerate(data):
            tree.move(iid, "", index)

    def _reset_sort(self, pane: PaneId) -> None:
        """정렬 상태 초기화(다음 수신 시 재적용)."""
        self._sort_state.pop(pane, None)

    def _clear_table(self, pane: PaneId) -> None:
        tree: ttk.Treeview = self._widgets[pane]["tree"]
        for iid in tree.get_children():
            tree.delete(iid)
        self._set_status(pane, "표 비움")

    # ---------------- Pane/인덱스/상태 ---------------- #

    def _assign_index_to_pane(self, pane: PaneId, idx: str) -> None:
        self._index_for_pane[pane] = idx
        self._pane_for_index[idx] = pane

    def _resolve_pane_for_index(self, index: str) -> Optional[PaneId]:
        return self._pane_for_index.get(index)

    def _set_status(self, pane: PaneId, text: str) -> None:
        status: tk.Label = self._widgets[pane]["status"]
        status.config(text=f"{pane.upper()} | {text}")

    def _set_global_status(self, text: str) -> None:
        self._global_status.config(text=text)

    # ---------------- 종료 처리 ---------------- #

    def _on_close_request(self) -> None:
        try:
            self.close()
        except Exception as e:
            messagebox.showerror("종료 오류", str(e))

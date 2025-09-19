# com/hnw/ai/view/mod/project2/tkinter/image_classification_view.py
# -*- coding: utf-8 -*-
"""
ImageClassificationView - 이미지 분류 학습 과정 시각화 뷰

프레임워크 특징 활용:
- UiGateway를 통해 데이터 요청 (직접 DB 접근 X)
- on_rows() 콜백으로 학습 결과 수신
- 자동 갱신으로 실시간 모니터링
- 데이터소스 ID 기반으로 학습 히스토리/메트릭 조회
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
import datetime

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    import numpy as np
except Exception as e:
    raise RuntimeError("Tkinter/Matplotlib import 실패: 데스크톱 환경/라이브러리를 확인해 주세요.") from e

from com.hnw.ai.view.base.view_if import ViewIF
from com.hnw.ai.view.gateway.uigateway import UiGateway


class ImageClassificationView(ViewIF):
    """이미지 분류 학습 과정 시각화 뷰"""
    
    def __init__(self, vtype: str = "tkinter") -> None:
        super().__init__(vtype)
        
        # UI 설정
        self._window_title: str = "AI 이미지 분류 학습 모니터링"
        self._geometry: str = "1400x900"
        
        # 데이터소스 ID 매핑 (프레임워크 방식)
        self._datasource_mapping = {
            "training_history": "training_history",
            "model_info": "model_info", 
            "model_metrics": "model_metrics"
        }
        
        # Tk 루트 구성
        self._root = tk.Tk()
        self._root.title(self._window_title)
        self._root.geometry(self._geometry)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close_request)
        
        # 메뉴바
        menubar = tk.Menu(self._root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="종료", command=self._on_close_request)
        menubar.add_cascade(label="파일", menu=filemenu)
        self._root.config(menu=menubar)
        
        # 상태 관리
        self._closing: bool = False
        self._gateway: Optional[UiGateway] = None
        
        # 자동 갱신 설정
        self._auto_refresh_enabled = tk.BooleanVar(value=True)
        self._auto_refresh_ms = tk.StringVar(value="2000")  # 2초
        self._auto_refresh_job: Optional[str] = None
        
        # 데이터 캐시
        self._training_data: List[Dict[str, Any]] = []
        self._model_info: List[Dict[str, Any]] = []
        self._model_metrics: List[Dict[str, Any]] = []
        
        # UI 구성
        self._build_ui()
        
        # 초기 데이터 요청
        self._root.after(100, self._initial_requests)
        
    def _build_ui(self):
        """UI 구성"""
        # 상단 컨트롤 패널
        control_frame = ttk.Frame(self._root)
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 제목
        title_label = tk.Label(control_frame, text="🍎🍅 이미지 분류 학습 모니터링", 
                              font=("Arial", 16, "bold"))
        title_label.pack(side=tk.LEFT)
        
        # 자동 갱신 컨트롤
        auto_frame = ttk.Frame(control_frame)
        auto_frame.pack(side=tk.RIGHT)
        
        auto_check = ttk.Checkbutton(auto_frame, text="자동 갱신", 
                                   variable=self._auto_refresh_enabled,
                                   command=self._toggle_auto_refresh)
        auto_check.pack(side=tk.LEFT, padx=5)
        
        tk.Label(auto_frame, text="간격(ms):").pack(side=tk.LEFT, padx=(10, 2))
        ms_spin = tk.Spinbox(auto_frame, from_=1000, to=10000, increment=500, 
                           width=8, textvariable=self._auto_refresh_ms,
                           command=self._reschedule_auto_refresh)
        ms_spin.pack(side=tk.LEFT, padx=2)
        
        ttk.Button(auto_frame, text="새로고침", 
                  command=self._manual_refresh).pack(side=tk.LEFT, padx=5)
        
        # 메인 콘텐츠 영역
        content_frame = ttk.Frame(self._root)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 왼쪽: 학습 히스토리 그래프
        left_frame = ttk.LabelFrame(content_frame, text="학습 과정")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Matplotlib 그래프
        self._fig = Figure(figsize=(8, 6), dpi=100)
        self._canvas = FigureCanvasTkAgg(self._fig, left_frame)
        self._canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # 오른쪽: 모델 정보 및 메트릭
        right_frame = ttk.Frame(content_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        
        # 모델 정보
        model_frame = ttk.LabelFrame(right_frame, text="Model Information")
        model_frame.pack(fill=tk.X, pady=(0, 5))
        
        self._model_info_text = tk.Text(model_frame, height=8, width=30, 
                                       font=("Consolas", 10))
        self._model_info_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 메트릭 정보
        metrics_frame = ttk.LabelFrame(right_frame, text="Evaluation Metrics")
        metrics_frame.pack(fill=tk.X, pady=(0, 5))
        
        self._metrics_text = tk.Text(metrics_frame, height=6, width=30,
                                   font=("Consolas", 10))
        self._metrics_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 학습 히스토리 테이블
        history_frame = ttk.LabelFrame(right_frame, text="Training History")
        history_frame.pack(fill=tk.BOTH, expand=True)
        
        # Treeview for history
        tree_frame = ttk.Frame(history_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self._history_tree = ttk.Treeview(tree_frame, columns=("epoch", "train_loss", "train_acc", "val_loss", "val_acc"), 
                                        show="headings", height=8)
        
        # 컬럼 설정
        self._history_tree.heading("epoch", text="Epoch")
        self._history_tree.heading("train_loss", text="Train Loss")
        self._history_tree.heading("train_acc", text="Train Acc")
        self._history_tree.heading("val_loss", text="Val Loss")
        self._history_tree.heading("val_acc", text="Val Acc")
        
        self._history_tree.column("epoch", width=50)
        self._history_tree.column("train_loss", width=80)
        self._history_tree.column("train_acc", width=80)
        self._history_tree.column("val_loss", width=80)
        self._history_tree.column("val_acc", width=80)
        
        # 스크롤바
        history_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self._history_tree.yview)
        self._history_tree.configure(yscrollcommand=history_scroll.set)
        
        self._history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        history_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 하단 상태바
        self._status_bar = tk.Label(self._root, text="대기 중...", anchor="w", 
                                   relief=tk.SUNKEN, bd=1)
        self._status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        
    # ViewIF 구현
    def connect(self, config: Dict[str, Any]) -> bool:
        """UI 설정 적용"""
        if config:
            self._config.update(config)
            
            title = config.get("window_title")
            if title:
                self._window_title = str(title)
                self._root.title(self._window_title)
                
            geometry = config.get("geometry")
            if geometry:
                self._geometry = str(geometry)
                self._root.geometry(self._geometry)
        
        self._root.after(100, self._initial_requests)
        return True
        
    def attach_gateway(self, gateway: UiGateway) -> None:
        """외부에서 게이트웨이 주입 (main.py에서 호출)"""
        self._gateway = gateway
        print("[ImageClassificationView] 외부 게이트웨이 주입 완료")
        
    def start(self) -> None:
        """UI 시작"""
        self._root.mainloop()
        
    def on_rows(self, datasource_id: str, rows: List[Dict[str, Any]], 
                columns: Optional[List[str]] = None) -> None:
        """UiGateway → View: 데이터 수신 (프레임워크 핵심)"""
        self._root.after(0, lambda: self._process_received_data(datasource_id, rows, columns))
        
    def close(self) -> None:
        """리소스 정리"""
        self._closing = True
        
        # 자동 갱신 중지
        if self._auto_refresh_job:
            try:
                self._root.after_cancel(self._auto_refresh_job)
            except Exception:
                pass
                
        # UI 종료
        try:
            if self._root and self._root.winfo_exists():
                self._root.after(0, self._root.destroy)
        except Exception:
            pass
            
        # 게이트웨이 정리
        try:
            if self._gateway:
                self._gateway.close()
        except Exception:
            pass
            
    # 데이터 요청 (프레임워크 방식)
    def _ensure_gateway(self) -> UiGateway:
        """게이트웨이 확보"""
        if self._gateway is None:
            self._gateway = UiGateway()
            self._gateway.attach_view(self)
        return self._gateway
        
    def _initial_requests(self) -> None:
        """초기 데이터 요청 (실시간 갱신용)"""
        if self._closing:
            return
            
        # 게이트웨이가 제대로 설정되었는지 확인
        if not self._gateway:
            print("[ImageClassificationView] 게이트웨이가 아직 설정되지 않음. 요청 지연...")
            self._root.after(1000, self._initial_requests)  # 1초 후 재시도
            return
            
        gateway = self._ensure_gateway()
        
        # 각 데이터소스에 대해 요청
        for ds_name, ds_id in self._datasource_mapping.items():
            self._set_status(f"{ds_name} 데이터 요청 중...")
            gateway.request_data(ds_id, {"model_id": "image_classifier_001"})
            
        # 자동 갱신 시작
        if self._auto_refresh_enabled.get():
            self._schedule_auto_refresh()
            print("[ImageClassificationView] 실시간 모니터링 시작")
        else:
            print("[ImageClassificationView] 자동 갱신 비활성화됨")
            
    def _manual_refresh(self) -> None:
        """수동 새로고침"""
        self._initial_requests()
        
    # 데이터 처리 (프레임워크 콜백)
    def _process_received_data(self, datasource_id: str, rows: List[Dict[str, Any]], 
                              columns: Optional[List[str]]) -> None:
        """수신된 데이터 처리 (빈 데이터 시 이전 데이터 유지)"""
        print(f"[ImageClassificationView] 데이터 수신: {datasource_id}, 행 수: {len(rows)}")
        if self._closing:
            return
            
        # 데이터소스별 처리 (빈 데이터일 때는 이전 데이터 유지)
        if datasource_id == "training_history":
            if rows:  # 새로운 데이터가 있으면 업데이트
                self._training_data = rows
                print(f"[ImageClassificationView] 학습 히스토리 데이터: {rows[:2] if rows else 'None'}")
                self._update_training_graph()
                self._update_history_table()
                self._set_status(f"학습 히스토리 {len(rows)}개 수신")
            else:
                print(f"[ImageClassificationView] 학습 히스토리 빈 데이터 - 이전 데이터 유지")
            
        elif datasource_id == "model_info":
            if rows:  # 새로운 데이터가 있으면 업데이트
                self._model_info = rows
                print(f"[ImageClassificationView] 모델 정보 데이터: {rows}")
                self._update_model_info()
                self._set_status(f"모델 정보 {len(rows)}개 수신")
            else:
                print(f"[ImageClassificationView] 모델 정보 빈 데이터 - 이전 데이터 유지")
            
        elif datasource_id == "model_metrics":
            if rows:  # 새로운 데이터가 있으면 업데이트
                self._model_metrics = rows
                print(f"[ImageClassificationView] 메트릭 데이터: {rows}")
                self._update_metrics_info()
                self._set_status(f"메트릭 {len(rows)}개 수신")
            else:
                print(f"[ImageClassificationView] 메트릭 빈 데이터 - 이전 데이터 유지")
        else:
            print(f"[ImageClassificationView] 알 수 없는 데이터소스: {datasource_id}")
            
    # UI 업데이트
    def _update_training_graph(self) -> None:
        """학습 과정 그래프 업데이트"""
        if not self._training_data:
            return
            
        # 그래프 초기화
        self._fig.clear()
        
        # 에폭별 데이터 추출
        epochs = [row.get('epoch', 0) for row in self._training_data]
        train_loss = [row.get('train_loss', 0) for row in self._training_data]
        val_loss = [row.get('val_loss', 0) for row in self._training_data]
        train_acc = [row.get('train_accuracy', 0) for row in self._training_data]
        val_acc = [row.get('val_accuracy', 0) for row in self._training_data]
        
        # 서브플롯 생성
        ax1 = self._fig.add_subplot(211)
        ax2 = self._fig.add_subplot(212)
        
        # 손실 그래프
        ax1.plot(epochs, train_loss, 'b-', label='Train Loss', marker='o')
        ax1.plot(epochs, val_loss, 'r-', label='Validation Loss', marker='s')
        ax1.set_xlabel('Epoch')
        ax1.set_ylabel('Loss')
        ax1.set_title('Training/Validation Loss')
        ax1.legend()
        ax1.grid(True)
        
        # 정확도 그래프
        ax2.plot(epochs, train_acc, 'b-', label='Train Accuracy', marker='o')
        ax2.plot(epochs, val_acc, 'r-', label='Validation Accuracy', marker='s')
        ax2.set_xlabel('Epoch')
        ax2.set_ylabel('Accuracy')
        ax2.set_title('Training/Validation Accuracy')
        ax2.legend()
        ax2.grid(True)
        
        # 레이아웃 조정
        self._fig.tight_layout()
        self._canvas.draw()
        
    def _update_history_table(self) -> None:
        """학습 히스토리 테이블 업데이트"""
        # 기존 데이터 삭제
        for item in self._history_tree.get_children():
            self._history_tree.delete(item)
            
        # 새 데이터 삽입
        for row in self._training_data:
            epoch = row.get('epoch', 0)
            train_loss = f"{row.get('train_loss', 0):.4f}"
            train_acc = f"{row.get('train_accuracy', 0):.4f}"
            val_loss = f"{row.get('val_loss', 0):.4f}"
            val_acc = f"{row.get('val_accuracy', 0):.4f}"
            
            self._history_tree.insert("", "end", values=(epoch, train_loss, train_acc, val_loss, val_acc))
            
    def _update_model_info(self) -> None:
        """모델 정보 업데이트"""
        print(f"[ImageClassificationView] 모델 정보 업데이트: {self._model_info}")
        self._model_info_text.delete(1.0, tk.END)
        
        if self._model_info:
            info = self._model_info[0]
            text = f"""Model ID: {info.get('model_id', 'N/A')}
Model Name: {info.get('model_name', 'N/A')}
Model Type: {info.get('model_type', 'N/A')}
Status: {info.get('status', 'N/A')}
Created: {info.get('created_at', 'N/A')}"""
        else:
            text = "No model information"
            
        self._model_info_text.insert(1.0, text)
        
    def _update_metrics_info(self) -> None:
        """메트릭 정보 업데이트"""
        print(f"[ImageClassificationView] 메트릭 정보 업데이트: {self._model_metrics}")
        self._metrics_text.delete(1.0, tk.END)
        
        if self._model_metrics:
            text = "Evaluation Metrics:\n\n"
            for metric in self._model_metrics:
                name = metric.get('metric_name', 'N/A')
                value = metric.get('metric_value', 0)
                text += f"{name}: {value:.4f}\n"
        else:
            text = "No metrics available"
            
        self._metrics_text.insert(1.0, text)
        
    # 자동 갱신 관리
    def _schedule_auto_refresh(self) -> None:
        """자동 갱신 스케줄"""
        if self._auto_refresh_job:
            self._root.after_cancel(self._auto_refresh_job)
            
        try:
            ms = int(self._auto_refresh_ms.get())
        except Exception:
            ms = 2000
            
        if ms < 1000:
            ms = 1000
            
        def _refresh_task():
            if self._closing:
                return
            self._manual_refresh()
            self._schedule_auto_refresh()
            
        self._auto_refresh_job = self._root.after(ms, _refresh_task)
        
    def _toggle_auto_refresh(self) -> None:
        """자동 갱신 토글"""
        if self._auto_refresh_enabled.get():
            self._schedule_auto_refresh()
        else:
            if self._auto_refresh_job:
                self._root.after_cancel(self._auto_refresh_job)
                self._auto_refresh_job = None
                
    def _reschedule_auto_refresh(self) -> None:
        """자동 갱신 재스케줄"""
        if self._auto_refresh_enabled.get():
            self._schedule_auto_refresh()
            
    # 유틸리티
    def _set_status(self, text: str) -> None:
        """상태바 업데이트"""
        self._status_bar.config(text=text)
        
    def _on_close_request(self) -> None:
        """종료 요청 처리"""
        try:
            self.close()
        except Exception as e:
            messagebox.showerror("종료 오류", str(e))

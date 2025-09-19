#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
실시간 AI 학습 모니터링 시스템

기능:
- AI 모델 학습 (백그라운드 스레드)
- 실시간 학습 과정 시각화 (메인 스레드)
- 프레임워크 방식 준수 (UiGateway → on_rows())
"""

import os
import sys
import threading
import time
import datetime

# 루트 디렉토리 설정
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(ROOT_DIR)

print(f"ROOT DIR= {ROOT_DIR}")

from com.hnw.ai.core.service.ai_service_manager import AIServiceManager
from com.hnw.ai.core.service.view_service_manager import ViewServiceManager
from com.hnw.ai.view.gateway.uigateway import UiGateway
from com.hnw.ai.view.base.view_if import ViewIF


def clear_existing_data():
    """기존 데이터 삭제 (깨끗한 시작)"""
    print("기존 데이터 삭제 중...")
    try:
        import mysql.connector
        conn = mysql.connector.connect(
            host='127.0.0.1',
            user='root',
            password='alsrud2',
            database='ai_data'
        )
        cursor = conn.cursor()
        cursor.execute("DELETE FROM training_history WHERE model_id = 'image_classifier_001'")
        cursor.execute("DELETE FROM model_metrics WHERE model_id = 'image_classifier_001'")
        cursor.execute("DELETE FROM ai_model_info WHERE model_id = 'image_classifier_001'")
        conn.commit()
        cursor.close()
        conn.close()
        print("기존 데이터 삭제 완료")
    except Exception as e:
        print(f"데이터 삭제 오류: {e}")


def run_ai_training():
    """AI 학습을 별도의 스레드에서 실행"""
    print("=== AI 학습 시작 ===")
    try:
        # AI 서비스 매니저로 학습 실행
        ai_service = AIServiceManager.get_by_id('image_classifier_dev')
        
        # 15단계 AI 인터페이스 실행
        ai_service.configure({})
        ai_service.attach_dataset("imageset", {})
        ai_service.prepare_data({})
        ai_service.split({})
        ai_service.build({})
        
        print("학습 시작 - 실시간 모니터링 가능")
        ai_service.fit({})  # 학습 실행 (실시간 DB 저장)
        
        ai_service.evaluate()
        ai_service.export()
        ai_service.register()
        ai_service.artifacts()
        ai_service.close()
        
        print("=== AI 학습 완료 ===")
    except Exception as e:
        print(f"AI 학습 오류: {e}")
        import traceback
        traceback.print_exc()


def main():
    """메인 실행 로직"""
    print("=== 실시간 AI 학습 모니터링 시스템 ===")
    
    # 뷰 ID 설정
    VIEW_ID = "view_image_classification_dev"
    
    # 기존 데이터 초기화
    clear_existing_data()
    
    # AI 학습 스레드 시작
    training_thread = threading.Thread(target=run_ai_training)
    training_thread.start()
    
    # 잠시 대기 (학습이 시작될 때까지)
    time.sleep(2)
    
    # 뷰 시작 (메인 스레드)
    print("\n=== 실시간 모니터링 뷰 시작 ===")
    try:
        view: ViewIF = ViewServiceManager.get_by_id(VIEW_ID)
        
        # UiGateway 설정 (MySQL만 사용)
        gateway = UiGateway()
        gateway.connect({
            "controllers": {
                "storage_ids": ["ai_data_mysql_dev"],
                "driver_ids": []
            }
        })
        
        # 뷰에 게이트웨이 연결
        gateway.attach_view(view)
        
        # 외부 게이트웨이 주입 (실시간 모니터링용)
        if hasattr(view, "attach_gateway"):
            view.attach_gateway(gateway)
        
        # UI 시작 (Tkinter mainloop)
        view.start()
        
    except Exception as e:
        print(f"뷰 시작 오류: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 뷰 종료 시 학습 스레드도 종료 대기
        if training_thread.is_alive():
            print("AI 학습 스레드 종료 대기 중...")
            training_thread.join(timeout=10)
            if training_thread.is_alive():
                print("경고: AI 학습 스레드가 제때 종료되지 않았습니다.")


if __name__ == "__main__":
    main()

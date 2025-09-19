# com/hnw/ai/module/ai/mod/분류/image_classifier.py
# -*- coding: utf-8 -*-
"""
ImageClassifier - 사과/토마토 이미지 분류 AI 구현체

최소 구현:
- PyTorch 기반 간단한 CNN 모델
- 5 에폭 학습
- MySQL 스토리지에 학습 결과 저장
- 실시간 학습 과정 모니터링
"""

from __future__ import annotations

import os
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from PIL import Image

from com.hnw.ai.module.ai.base.ai_if import AiIF, DatasetProfile, SplitMeta, TrainReport, EvalReport, ArtifactManifest, ArtifactMap
from com.hnw.ai.core.service.storage_service_manager import StorageServiceManager


class SimpleCNN(nn.Module):
    """간단한 CNN 모델"""
    
    def __init__(self, num_classes: int = 2):
        super(SimpleCNN, self).__init__()
        self.conv1 = nn.Conv2d(3, 32, 3, padding=1)
        self.conv2 = nn.Conv2d(32, 64, 3, padding=1)
        self.conv3 = nn.Conv2d(64, 128, 3, padding=1)
        
        self.pool = nn.MaxPool2d(2, 2)
        self.dropout = nn.Dropout(0.5)
        
        self.fc1 = nn.Linear(128 * 28 * 28, 512)
        self.fc2 = nn.Linear(512, num_classes)
        
    def forward(self, x):
        x = self.pool(torch.relu(self.conv1(x)))
        x = self.pool(torch.relu(self.conv2(x)))
        x = self.pool(torch.relu(self.conv3(x)))
        
        x = x.view(-1, 128 * 28 * 28)
        x = self.dropout(torch.relu(self.fc1(x)))
        x = self.fc2(x)
        return x


class ImageDataset(Dataset):
    """이미지 데이터셋"""
    
    def __init__(self, image_paths: List[str], labels: List[int], transform=None):
        self.image_paths = image_paths
        self.labels = labels
        self.transform = transform
        
    def __len__(self):
        return len(self.image_paths)
    
    def __getitem__(self, idx):
        image_path = self.image_paths[idx]
        image = Image.open(image_path).convert('RGB')
        
        if self.transform:
            image = self.transform(image)
            
        label = self.labels[idx]
        return image, label


class ImageClassifier(AiIF):
    """이미지 분류 AI 구현체"""
    
    def __init__(self):
        super().__init__()
        self._config: Dict[str, Any] = {}
        self._model: Optional[SimpleCNN] = None
        self._device = torch.device('cpu')
        self._class_names = ["사과", "토마토"]
        self._storage = None
        
        # 데이터셋 정보
        self._train_dataset = None
        self._val_dataset = None
        self._test_dataset = None
        
        # 학습 히스토리
        self._train_history: List[Dict[str, float]] = []
        
    # 1) 런타임/리소스/로깅 구성
    def configure(self, config: Dict[str, Any]) -> None:
        """설정 구성"""
        self._config = dict(config or {})
        self._device = torch.device(self._config.get('device', 'cpu'))
        self._class_names = self._config.get('class_names', ["apples", "tomatoes"])
        
        # MySQL 스토리지 연결
        try:
            self._storage = StorageServiceManager.get_by_id("ai_data_mysql_dev")
            print(f"[ImageClassifier] MySQL 스토리지 연결 성공")
        except Exception as e:
            print(f"[ImageClassifier] MySQL 스토리지 연결 실패: {e}")
            
        self._set_state("CONFIGURED")
        
    # 2) 데이터셋 연결/검증
    def attach_dataset(self, dataset_ref: Any, schema: Dict[str, Any]) -> DatasetProfile:
        """데이터셋 연결"""
        # imageset 폴더에서 데이터 로드
        imageset_path = Path("imageset")
        if not imageset_path.exists():
            raise FileNotFoundError("imageset 폴더를 찾을 수 없습니다.")
            
        train_path = imageset_path / "train"
        test_path = imageset_path / "test"
        
        # 이미지 파일 수집
        train_images = []
        train_labels = []
        test_images = []
        test_labels = []
        
        # 클래스별 이미지 수집
        for class_idx, class_name in enumerate(self._class_names):
            print(f"[ImageClassifier] 클래스 {class_idx}: {class_name} 처리 중...")
            
            # 학습 데이터
            train_class_path = train_path / class_name
            print(f"[ImageClassifier] 학습 경로: {train_class_path}")
            print(f"[ImageClassifier] 학습 경로 존재: {train_class_path.exists()}")
            
            if train_class_path.exists():
                jpeg_files = list(train_class_path.glob("*.jpeg"))
                print(f"[ImageClassifier] {class_name} 학습 파일 수: {len(jpeg_files)}")
                for img_file in jpeg_files:
                    train_images.append(str(img_file))
                    train_labels.append(class_idx)
                    
            # 테스트 데이터
            test_class_path = test_path / class_name
            print(f"[ImageClassifier] 테스트 경로: {test_class_path}")
            print(f"[ImageClassifier] 테스트 경로 존재: {test_class_path.exists()}")
            
            if test_class_path.exists():
                jpeg_files = list(test_class_path.glob("*.jpeg"))
                print(f"[ImageClassifier] {class_name} 테스트 파일 수: {len(jpeg_files)}")
                for img_file in jpeg_files:
                    test_images.append(str(img_file))
                    test_labels.append(class_idx)
        
        print(f"[ImageClassifier] 클래스별 이미지 수:")
        for class_idx, class_name in enumerate(self._class_names):
            train_count = sum(1 for label in train_labels if label == class_idx)
            test_count = sum(1 for label in test_labels if label == class_idx)
            print(f"  {class_name}: 학습 {train_count}개, 테스트 {test_count}개")
        
        print(f"[ImageClassifier] 학습 이미지: {len(train_images)}개")
        print(f"[ImageClassifier] 테스트 이미지: {len(test_images)}개")
        
        # 데이터셋 프로필 생성
        profile: DatasetProfile = {
            "fingerprint": f"imageset_{len(train_images)}_{len(test_images)}",
            "num_rows": len(train_images) + len(test_images),
            "num_files": len(train_images) + len(test_images),
            "schema_valid": True,
            "warnings": [],
            "stats": {
                "train_samples": len(train_images),
                "test_samples": len(test_images),
                "num_classes": len(self._class_names),
                "class_names": self._class_names
            }
        }
        
        # 데이터셋 저장
        self._train_images = train_images
        self._train_labels = train_labels
        self._test_images = test_images
        self._test_labels = test_labels
        
        self._set_state("DATA_ATTACHED")
        return profile
        
    # 3) 전처리/증강 파이프라인 구축
    def prepare_data(self, options: Dict[str, Any]) -> Union[str, Dict[str, Any]]:
        """데이터 전처리"""
        # 이미지 변환 정의 (하드코딩)
        transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
        
        # 데이터셋 생성
        self._train_dataset = ImageDataset(self._train_images, self._train_labels, transform)
        self._test_dataset = ImageDataset(self._test_images, self._test_labels, transform)
        
        # 검증 데이터는 학습 데이터의 20% 사용
        val_size = int(0.2 * len(self._train_dataset))
        train_size = len(self._train_dataset) - val_size
        
        self._train_dataset, self._val_dataset = torch.utils.data.random_split(
            self._train_dataset, [train_size, val_size]
        )
        
        return "preprocessing_completed"
        
    # 4) 분할/폴드
    def split(self, strategy: Dict[str, Any]) -> SplitMeta:
        """데이터 분할"""
        meta: SplitMeta = {
            "strategy": {"train_val_split": 0.8},
            "sets": {
                "train": len(self._train_dataset),
                "valid": len(self._val_dataset),
                "test": len(self._test_dataset)
            },
            "info": {"random_seed": 42}
        }
        
        self._set_state("SPLIT")
        return meta
        
    # 5) 모델/알고리즘 빌드
    def build(self, model_spec: Dict[str, Any]) -> None:
        """모델 빌드"""
        num_classes = self._config.get('num_classes', 2)
        self._model = SimpleCNN(num_classes).to(self._device)
        
        print(f"[ImageClassifier] 모델 빌드 완료: {num_classes} 클래스")
        self._set_state("BUILT")
        
    # 6) 학습/적합
    def fit(self, train_config: Dict[str, Any], callbacks: Optional[List] = None) -> TrainReport:
        """모델 학습"""
        if not self._model:
            raise RuntimeError("모델이 빌드되지 않았습니다.")
            
        # 학습 설정 (하드코딩)
        epochs = 5
        batch_size = 32
        learning_rate = 0.001
        
        # 데이터로더 생성
        train_loader = DataLoader(self._train_dataset, batch_size=batch_size, shuffle=True)
        val_loader = DataLoader(self._val_dataset, batch_size=batch_size, shuffle=False)
        
        # 옵티마이저와 손실함수
        optimizer = optim.Adam(self._model.parameters(), lr=learning_rate)
        criterion = nn.CrossEntropyLoss()
        
        # 학습 시작 시간
        start_time = time.time()
        
        print(f"[ImageClassifier] 학습 시작: {epochs} 에폭")
        
        # 모델 정보 저장
        model_id = self._config.get('model_id', 'image_classifier_001')
        if self._storage:
            self._storage.store({
                "type": "model_info",
                "model_id": model_id,
                "model_name": self._config.get('model_name', '사과토마토분류기'),
                "model_type": "image_classification",
                "status": "training"
            })
        
        # 학습 루프
        for epoch in range(epochs):
            # 학습
            self._model.train()
            train_loss = 0.0
            train_correct = 0
            train_total = 0
            
            for batch_idx, (data, target) in enumerate(train_loader):
                data, target = data.to(self._device), target.to(self._device)
                
                optimizer.zero_grad()
                output = self._model(data)
                loss = criterion(output, target)
                loss.backward()
                optimizer.step()
                
                train_loss += loss.item()
                _, predicted = torch.max(output.data, 1)
                train_total += target.size(0)
                train_correct += (predicted == target).sum().item()
                
            # 검증
            self._model.eval()
            val_loss = 0.0
            val_correct = 0
            val_total = 0
            
            with torch.no_grad():
                for data, target in val_loader:
                    data, target = data.to(self._device), target.to(self._device)
                    output = self._model(data)
                    loss = criterion(output, target)
                    
                    val_loss += loss.item()
                    _, predicted = torch.max(output.data, 1)
                    val_total += target.size(0)
                    val_correct += (predicted == target).sum().item()
            
            # 메트릭 계산
            train_loss /= len(train_loader)
            train_acc = 100. * train_correct / train_total
            val_loss /= len(val_loader)
            val_acc = 100. * val_correct / val_total
            
            # 히스토리 저장
            epoch_data = {
                "epoch": epoch + 1,
                "train_loss": train_loss,
                "train_accuracy": train_acc / 100.0,
                "val_loss": val_loss,
                "val_accuracy": val_acc / 100.0
            }
            self._train_history.append(epoch_data)
            
            # MySQL에 저장
            if self._storage:
                self._storage.store({
                    "type": "training_history",
                    "model_id": model_id,
                    **epoch_data
                })
            
            print(f"에폭 {epoch+1}/{epochs}: "
                  f"Train Loss: {train_loss:.4f}, Train Acc: {train_acc:.2f}%, "
                  f"Val Loss: {val_loss:.4f}, Val Acc: {val_acc:.2f}%")
        
        # 학습 완료 시간
        wall_time = time.time() - start_time
        
        # 최종 모델 상태 업데이트
        if self._storage:
            self._storage.store({
                "type": "model_info",
                "model_id": model_id,
                "model_name": self._config.get('model_name', '사과토마토분류기'),
                "model_type": "image_classification",
                "status": "completed"
            })
        
        # 학습 보고서 생성
        report: TrainReport = {
            "best_checkpoint_id": None,
            "epochs": epochs,
            "metrics": {
                "final_train_loss": train_loss,
                "final_train_accuracy": train_acc / 100.0,
                "final_val_loss": val_loss,
                "final_val_accuracy": val_acc / 100.0
            },
            "history": self._train_history,
            "wall_time_sec": wall_time
        }
        
        self._set_state("FITTED")
        return report
        
    # 7) 평가
    def evaluate(self, eval_sets: Union[Sequence[str], Dict[str, Any]], metrics: Union[Sequence[str], Dict[str, Any]]) -> EvalReport:
        """모델 평가"""
        if not self._model:
            raise RuntimeError("모델이 학습되지 않았습니다.")
            
        self._model.eval()
        test_loader = DataLoader(self._test_dataset, batch_size=32, shuffle=False)
        
        correct = 0
        total = 0
        all_predictions = []
        all_targets = []
        
        with torch.no_grad():
            for data, target in test_loader:
                data, target = data.to(self._device), target.to(self._device)
                output = self._model(data)
                _, predicted = torch.max(output.data, 1)
                
                total += target.size(0)
                correct += (predicted == target).sum().item()
                
                all_predictions.extend(predicted.cpu().numpy())
                all_targets.extend(target.cpu().numpy())
        
        accuracy = correct / total
        
        # 혼동행렬 생성
        confusion_matrix = [[0, 0], [0, 0]]
        for pred, target in zip(all_predictions, all_targets):
            confusion_matrix[target][pred] += 1
        
        # MySQL에 메트릭 저장
        model_id = self._config.get('model_id', 'image_classifier_001')
        if self._storage:
            self._storage.store({
                "type": "model_metrics",
                "model_id": model_id,
                "metric_name": "test_accuracy",
                "metric_value": accuracy
            })
        
        report: EvalReport = {
            "metrics": {"accuracy": accuracy},
            "confusion_matrix": confusion_matrix,
            "curves": {},
            "notes": f"테스트 정확도: {accuracy:.4f}"
        }
        
        self._set_state("EVALUATED")
        return report
        
    # 12) 아티팩트 내보내기
    def export(self, target_uri: Union[str, Path], formats: Union[str, Sequence[str]], include_preproc: bool = True) -> ArtifactManifest:
        """모델 내보내기"""
        target_path = Path(target_uri)
        target_path.mkdir(parents=True, exist_ok=True)
        
        # 모델 저장
        model_path = target_path / "model.pth"
        if self._model:
            torch.save(self._model.state_dict(), model_path)
        
        # 설정 저장
        config_path = target_path / "config.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(self._config, f, ensure_ascii=False, indent=2)
        
        # 클래스 이름 저장
        classes_path = target_path / "class_names.json"
        with open(classes_path, 'w', encoding='utf-8') as f:
            json.dump(self._class_names, f, ensure_ascii=False, indent=2)
        
        manifest: ArtifactManifest = {
            "files": [
                {"path": str(model_path), "role": "model"},
                {"path": str(config_path), "role": "signature"},
                {"path": str(classes_path), "role": "label_map"}
            ],
            "created_at": datetime.now().isoformat(),
            "signature_path": str(config_path),
            "extras": {"model_type": "image_classification"}
        }
        
        self._set_state("EXPORTED")
        return manifest
        
    # 13) 레지스트리 등록
    def register(self, name: str, version: str, stage: str = "staging", tags: Optional[Dict[str, str]] = None) -> str:
        """모델 레지스트리 등록"""
        model_id = f"{name}_{version}_{stage}"
        print(f"[ImageClassifier] 모델 등록: {model_id}")
        
        self._set_state("REGISTERED")
        return model_id
        
    # 14) 아티팩트 맵 조회
    def artifacts(self) -> ArtifactMap:
        """아티팩트 맵 조회"""
        return {
            "model": "model.pth",
            "preprocessor": None,
            "label_map": "class_names.json",
            "tokenizer": None,
            "metrics": None,
            "thresholds": None,
            "training_log": None,
            "requirements": None,
            "signature": "config.json",
            "data_fingerprint": None
        }
        
    # 15) 리소스 정리
    def close(self) -> None:
        """리소스 정리"""
        if self._storage:
            self._storage.close()
        self._model = None
        self._set_state("CLOSED")

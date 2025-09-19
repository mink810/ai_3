CREATE TABLE `ai_model_info` (
  `model_id` varchar(50) NOT NULL,
  `model_name` varchar(100) DEFAULT NULL,
  `model_type` varchar(50) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `status` varchar(20) DEFAULT NULL,
  PRIMARY KEY (`model_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci

CREATE TABLE `training_history` (
  `id` int NOT NULL AUTO_INCREMENT,
  `model_id` varchar(50) DEFAULT NULL,
  `epoch` int DEFAULT NULL,
  `train_loss` float DEFAULT NULL,
  `train_accuracy` float DEFAULT NULL,
  `val_loss` float DEFAULT NULL,
  `val_accuracy` float DEFAULT NULL,
  `timestamp` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_model_epoch` (`model_id`,`epoch`)
) ENGINE=InnoDB AUTO_INCREMENT=47 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci

CREATE TABLE `model_metrics` (
  `model_id` varchar(50) NOT NULL,
  `metric_name` varchar(50) NOT NULL,
  `metric_value` float DEFAULT NULL,
  PRIMARY KEY (`model_id`,`metric_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
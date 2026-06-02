"""초기 소요 시간 예측 모델 내부 상수."""

from __future__ import annotations

import math

# EMA 학습률
ETA_GLOBAL = 0.10
ETA_TYPE = 0.15
ETA_DIFFICULTY = 0.10

# Shrinkage 강도
TYPE_SHRINKAGE_N = 10          # r_type = typeCount / (typeCount + 10)
DIFFICULTY_SHRINKAGE_N = 10    # r_difficulty = difficultyCount / (difficultyCount + 10)
USER_GLOBAL_SHRINKAGE_N = 10   # user_weight = completedCount / (completedCount + 10)
SYSTEM_SHRINKAGE_N = 50        # 시스템 effect shrinkage

# log(actual/estimated) clamp 경계
CLAMP_MIN = math.log(1 / 3)
CLAMP_MAX = math.log(4.0)

# Drop 경계 — 이 범위를 벗어나면 계수 update 시 학습에서 제외
DROP_RATIO_MAX = 8.0
DROP_RATIO_MIN = 0.1

# MAIN 단계에서 folderId를 회귀 피처로 포함시키기 위한 최소 태스크 수
FOLDER_MIN_TASKS = 5

# 단계 전환 임계값
EARLY_THRESHOLD = 20           # 1 <= completed < 20 → RULE_AVERAGE_BLEND
MAIN_THRESHOLD = 100           # completed < 100 → MAIN
BLEND_TRANSITION_WIDTH = 10    # soft blending sigmoid 폭

# Stage 라벨
STAGE_RULE = "RULE"
STAGE_AVERAGE_BASELINE = "AVERAGE_BASELINE"
STAGE_RULE_AVERAGE_BLEND = "RULE_AVERAGE_BLEND"
STAGE_EARLY = "EARLY"
STAGE_MAIN = "MAIN_EFFECT"
STAGE_INTERACTION = "INTERACTION"
STAGE_EARLY_MAIN_BLEND = "EARLY_MAIN_BLEND"
STAGE_MAIN_INTERACTION_BLEND = "MAIN_INTERACTION_BLEND"

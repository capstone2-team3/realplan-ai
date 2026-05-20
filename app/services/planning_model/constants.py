"""planning_model 패키지 내부 상수."""

from __future__ import annotations

import math

# EMA 학습률
ETA_GLOBAL = 0.10
ETA_TYPE = 0.15

# Shrinkage 강도
TYPE_SHRINKAGE_N = 10          # r_type = typeCount / (typeCount + 10)
SYSTEM_SHRINKAGE_N = 50        # 시스템 effect shrinkage

# log(actual/estimated) clamp 경계
CLAMP_MIN = math.log(1 / 3)
CLAMP_MAX = math.log(4.0)

# MAIN 단계에서 folderId를 회귀 피처로 포함시키기 위한 최소 태스크 수
FOLDER_MIN_TASKS = 5

# 단계 전환 임계값
EARLY_THRESHOLD = 50           # completed < 50 → EARLY only
MAIN_THRESHOLD = 200           # completed < 200 → MAIN
BLEND_TRANSITION_WIDTH = 10    # soft blending sigmoid 폭

# Stage 라벨
STAGE_EARLY = "EARLY"
STAGE_MAIN = "MAIN_EFFECT"
STAGE_INTERACTION = "INTERACTION"
STAGE_EARLY_MAIN_BLEND = "EARLY_MAIN_BLEND"
STAGE_MAIN_INTERACTION_BLEND = "MAIN_INTERACTION_BLEND"

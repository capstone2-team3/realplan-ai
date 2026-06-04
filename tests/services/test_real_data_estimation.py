"""실데이터로 예측 소요시간을 계산해 출력하는 테스트.

실행:
    uv run python -m pytest tests/services/test_real_data_estimation.py -v -s

-s 옵션으로 print 출력(예측 결과 표)을 함께 본다.

전제:
- 모든 사용자가 신규 사용자(userGlobal=None). 시스템 prior만으로 예측.
- completedCount=0은 RULE, 이후 낮은 completedCount는 RULE_AVERAGE_BLEND에 해당.
- 시스템 prior 값은 실제 누적 통계가 없으므로 합리적 추정값을 사용한다.
  실데이터로 튜닝 시 update 결과를 모아 재산정해야 한다.
"""

from __future__ import annotations

import math

import pytest

from app.schemas.estimate import EstimateRequest
from app.schemas.update import UpdateRequest
from app.services.task_registration.initial_estimator.constants import (
    CLAMP_MAX,
    CLAMP_MIN,
    DROP_RATIO_MAX,
    DROP_RATIO_MIN,
    ETA_GLOBAL,
    ETA_TYPE,
    TYPE_SHRINKAGE_N,
)
from app.services.task_registration.initial_estimator.estimation import estimate_initial_duration
from app.services.profile_calibration.updater import update_coefficients


def _print_formula_header():
    """출력 상단에 사용한 수식과 상수값을 명시한다."""
    print()
    print("====================== 적용 수식 ======================")
    print("[estimate]")
    print("  r_type           = typeCount / (typeCount + TYPE_SHRINKAGE_N)")
    print("  logCorrection    = userGlobal")
    print("                   + systemTypeEffect[type]")
    print("                   + systemDifficultyEffect[difficulty]")
    print("                   + r_type × userTypeResidual[type]")
    print("                   + r_difficulty × userDifficultyResidual[difficulty]")
    print("  aiEstimatedMinutes = estimatedMinutes × exp(logCorrection)")
    print()
    print("[update]")
    print("  ratio                  = actual / estimated")
    print("  → ratio ∉ [DROP_MIN, DROP_MAX] 이면 DROP (계수 변경 없음)")
    print("  logRatio               = log(ratio)")
    print("  clampedLogRatio        = clip(logRatio, CLAMP_MIN, CLAMP_MAX)")
    print("  userGlobal_new         = (1 - ETA_GLOBAL) × userGlobal_old")
    print("                         + ETA_GLOBAL × clampedLogRatio")
    print("  residualTarget         = clampedLogRatio - userGlobal_old")
    print("                         - systemTypeEffect[type]")
    print("                         - systemDifficultyEffect[difficulty]")
    print("  userTypeResidual_new   = (1 - ETA_TYPE) × userTypeResidual_old")
    print("                         + ETA_TYPE × residualTarget")
    print("  userDifficultyResidual_new도 residualTarget을 EMA로 반영")
    print("  typeCount[type]       += 1   (drop 아닐 때만)")
    print("  difficultyCount[diff] += 1   (drop 아닐 때만)")
    print()
    print("====================== 상수값 ======================")
    print(f"  ETA_GLOBAL          = {ETA_GLOBAL}    (userGlobal EMA 학습률)")
    print(f"  ETA_TYPE            = {ETA_TYPE}    (userTypeResidual EMA 학습률)")
    print(f"  TYPE_SHRINKAGE_N    = {TYPE_SHRINKAGE_N}")
    print(f"  CLAMP_MIN / MAX     = log(1/3)/log(4.0) "
          f"≈ {CLAMP_MIN:+.3f} / {CLAMP_MAX:+.3f}")
    print(f"  DROP_RATIO_MIN / MAX= {DROP_RATIO_MIN} / {DROP_RATIO_MAX}")
    print()
    print("====================== 시스템 prior (테스트용 추정값) ======================")
    print(f"  systemGlobalPrior      = {SYSTEM_GLOBAL_PRIOR:+.2f}")
    print(f"  systemTypeEffect       = {SYSTEM_TYPE_EFFECT}")
    print(f"  systemDifficultyEffect = {SYSTEM_DIFFICULTY_EFFECT}")


# ---------- 한국어 → API 코드 매핑 -------------------------------------

TASK_TYPE_MAP = {
    "만족형": "SATISFACTION_BASED",
    "분량형": "QUANTITY_BASED",
    "시간형": "TIME_BASED",
}

# '모름'은 systemDifficultyEffect에 키가 없도록 두어 effect=0으로 fallback시킨다.
DIFFICULTY_MAP = {
    "하": "LOW",
    "중": "MEDIUM",
    "상": "HIGH",
    "모름": "UNKNOWN",
}


# ---------- 시스템 prior (실데이터 부재로 추정값) ----------------------
# 계획 오류 연구상 사용자는 평균적으로 25~50% 과소추정 → log(약 1.28) ≈ 0.25

SYSTEM_GLOBAL_PRIOR = 0.25
SYSTEM_TYPE_EFFECT = {
    "SATISFACTION_BASED":   +0.10,   # 끝맺기 기준 불명확 → 더 오래 걸림
    "QUANTITY_BASED":  0.00,   # 분량형은 비교적 예측이 정확
    "TIME_BASED":     -0.10,   # 마감 강제력으로 시간 안에 끝남
}
SYSTEM_DIFFICULTY_EFFECT = {
    "LOW":   -0.10,
    "MEDIUM":  0.00,
    "HIGH":   +0.15,
    # "UNKNOWN"은 의도적으로 미정의 → .get(key, 0.0)으로 0 fallback
}


# ---------- 실데이터 ---------------------------------------------------
# (사용자, 태스크ID, 태스크명, 유형, 추정시간(분), 난이도)
REAL_TASKS = [
    ("나영", 1,  "데사 2주차 공부",            "만족형", 160, "모름"),
    ("나영", 2,  "건여 3주차 2번째 영상",       "분량형",  40, "하"),
    ("나영", 3,  "데사 3주차 공부",            "만족형", 130, "중"),
    ("세진", 1,  "알고리즘 - 수학 공부",         "분량형",  90, "모름"),
    ("세진", 2,  "알고리즘 - 이분탐색 공부",      "분량형",  60, "모름"),
    ("세진", 4,  "캡디 자료조사 하기",          "만족형", 150, "중"),
    ("세진", 5,  "악성 코드 조사 및 정리하기",     "만족형",  90, "하"),
    ("세진", 8,  "알고리즘 - 이진 검색 트리",     "분량형",  60, "모름"),
    ("세진", 10, "워게임 rev-basic 9문제 풀기",  "분량형", 150, "상"),
    ("세진", 14, "운체보 개념 이해",            "만족형", 240, "중"),
    ("세진", 16, "멀코컴 03 정리 마무리",       "만족형",  40, "중"),
    ("세진", 17, "멀코컴 04-1 이해",           "만족형",  90, "중"),
    ("세진", 19, "멀코컴 과제 1",              "분량형", 180, "하"),
    ("세진", 20, "멀코컴 04-2 이해",           "만족형",  45, "중"),
    ("예나", 2,  "교양 퀴즈",                  "분량형",  30, "중"),
]


def _build_request(estimated: float, type_kr: str, difficulty_kr: str, completed: int = 0) -> EstimateRequest:
    return EstimateRequest(
        estimatedMinutes=estimated,
        completedCount=completed,
        taskType=TASK_TYPE_MAP[type_kr],
        difficulty=DIFFICULTY_MAP[difficulty_kr],
        folderId=None,
        userGlobal=None,
        userTypeResidual=None,
        typeCount=None,
        systemGlobalPrior=SYSTEM_GLOBAL_PRIOR,
        systemTypeEffect=SYSTEM_TYPE_EFFECT,
        systemDifficultyEffect=SYSTEM_DIFFICULTY_EFFECT,
    )


# ---------- 전체 데이터 예측 + 표 출력 --------------------------------


def test_estimate_all_real_tasks_and_print_table():
    """전체 실데이터에 대해 예측을 수행하고 결과를 표로 출력한다."""
    print()
    print(f"{'사용자':<4} {'ID':>3} | {'유형':<4} {'난이도':<4} | "
          f"{'추정':>5} → {'예측':>6}  ({'증가율':>6})")
    print("-" * 60)

    total_estimated = 0.0
    total_ai_estimated = 0.0

    for user, tid, _name, type_kr, estimated, difficulty_kr in REAL_TASKS:
        req = _build_request(estimated, type_kr, difficulty_kr)
        result = estimate_initial_duration(req)

        ratio = result.aiEstimatedMinutes / estimated
        total_estimated += estimated
        total_ai_estimated += result.aiEstimatedMinutes

        print(f"{user:<4} {tid:>3} | {type_kr:<4} {difficulty_kr:<4} | "
              f"{estimated:>5.0f} → {result.aiEstimatedMinutes:>6.1f}  ({ratio:>5.1%})")

        assert result.aiEstimatedMinutes > 0
        assert result.stage == "RULE"

    print("-" * 60)
    overall_ratio = total_ai_estimated / total_estimated
    print(f"{'합계':<4} {'':>3} | {'':<4} {'':<4} | "
          f"{total_estimated:>5.0f} → {total_ai_estimated:>6.1f}  ({overall_ratio:>5.1%})")


# ---------- 사용자별 누적 시뮬레이션 -----------------------------------


def test_estimate_per_user_with_sequential_completed_count():
    """사용자별로 completedCount를 0부터 순차 증가시켜 예측.

    실 사용 시 Spring은 사용자별 누적 완료 수를 보내므로 그 흐름을 흉내낸다.
    첫 예측은 RULE, 이후 낮은 completedCount에서는 RULE_AVERAGE_BLEND가 사용된다.
    """
    from collections import defaultdict
    counts = defaultdict(int)

    for user, _tid, _name, type_kr, estimated, difficulty_kr in REAL_TASKS:
        req = _build_request(estimated, type_kr, difficulty_kr, completed=counts[user])
        result = estimate_initial_duration(req)
        expected_stage = "RULE" if counts[user] == 0 else "RULE_AVERAGE_BLEND"
        assert result.stage == expected_stage
        counts[user] += 1


# ---------- 실제 소요시간 누적 시뮬레이션 -----------------------------

# (사용자, 태스크ID, 태스크명, 유형, 추정시간(분), 난이도, 실제(분))
REAL_TASKS_WITH_ACTUAL = [
    ("나영", 1,  "데사 2주차 공부",            "만족형", 160, "모름",  621),
    ("나영", 2,  "건여 3주차 2번째 영상",       "분량형",  40, "하",     35),
    ("나영", 3,  "데사 3주차 공부",            "만족형", 130, "중",    510),
    ("세진", 1,  "알고리즘 - 수학 공부",         "분량형",  90, "모름",  233),
    ("세진", 2,  "알고리즘 - 이분탐색 공부",      "분량형",  60, "모름",  227),
    ("세진", 4,  "캡디 자료조사 하기",          "만족형", 150, "중",    184),
    ("세진", 5,  "악성 코드 조사 및 정리하기",     "만족형",  90, "하",    113),
    ("세진", 8,  "알고리즘 - 이진 검색 트리",     "분량형",  60, "모름",   56),
    ("세진", 10, "워게임 rev-basic 9문제 풀기",  "분량형", 150, "상",    166),
    ("세진", 14, "운체보 개념 이해",            "만족형", 240, "중",   1000),
    ("세진", 16, "멀코컴 03 정리 마무리",       "만족형",  40, "중",     73),
    ("세진", 17, "멀코컴 04-1 이해",           "만족형",  90, "중",    311),
    ("세진", 19, "멀코컴 과제 1",              "분량형", 180, "하",    367),
    ("세진", 20, "멀코컴 04-2 이해",           "만족형",  45, "중",     67),
    ("예나", 2,  "교양 퀴즈",                  "분량형",  30, "중",     26),
]


def test_simulate_estimate_update_cycle_per_user():
    """실제 서비스 흐름 시뮬레이션:
       사용자별로 예측 → 실제 측정 → 계수 업데이트 → 다음 예측 반영.
    """
    _print_formula_header()

    # 사용자별 누적 상태 (Spring DB에 보관될 값)
    user_state: dict[str, dict] = {}

    current_user = None
    for user, tid, _name, type_kr, estimated, diff_kr, actual in REAL_TASKS_WITH_ACTUAL:
        # 사용자 헤더
        if user != current_user:
            print()
            print(f"=========== {user} ===========")
            print(f"{'#':>3} | {'유형':<4} {'난이도':<4} | {'추정':>4} {'예측':>6} {'실제':>5} | "
                  f"{'오차':>7} | {'userG':>6} {'res(type)':>10}")
            print("-" * 78)
            current_user = user

        state = user_state.setdefault(
            user,
            {
                "userGlobal": None,
                "userTypeResidual": None,
                "userDifficultyResidual": None,
                "userFolderResidual": None,
                "typeCount": None,
                "difficultyCount": None,
                "folderCount": None,
            },
        )
        completed = sum(state["typeCount"].values()) if state["typeCount"] else 0
        task_type_code = TASK_TYPE_MAP[type_kr]
        diff_code = DIFFICULTY_MAP[diff_kr]

        # 1) 현재 누적 계수로 예측
        estimate_result = estimate_initial_duration(
            EstimateRequest(
                estimatedMinutes=estimated,
                completedCount=completed,
                taskType=task_type_code,
                difficulty=diff_code,
                folderId=None,
                userGlobal=state["userGlobal"],
                userTypeResidual=state["userTypeResidual"],
                userDifficultyResidual=state["userDifficultyResidual"],
                userFolderResidual=state["userFolderResidual"],
                typeCount=state["typeCount"],
                difficultyCount=state["difficultyCount"],
                folderCount=state["folderCount"],
                systemGlobalPrior=SYSTEM_GLOBAL_PRIOR,
                systemTypeEffect=SYSTEM_TYPE_EFFECT,
                systemDifficultyEffect=SYSTEM_DIFFICULTY_EFFECT,
            )
        )
        error = (estimate_result.aiEstimatedMinutes - actual) / actual

        # 2) 실제값으로 계수 업데이트
        upd = update_coefficients(
            UpdateRequest(
                estimatedMinutes=estimated,
                actualMinutes=actual,
                completedCount=completed,
                taskType=task_type_code,
                difficulty=diff_code,
                folderId=None,
                userGlobal=state["userGlobal"],
                userTypeResidual=state["userTypeResidual"],
                userDifficultyResidual=state["userDifficultyResidual"],
                userFolderResidual=state["userFolderResidual"],
                typeCount=state["typeCount"],
                difficultyCount=state["difficultyCount"],
                folderCount=state["folderCount"],
                systemGlobalPrior=SYSTEM_GLOBAL_PRIOR,
                systemTypeEffect=SYSTEM_TYPE_EFFECT,
                systemDifficultyEffect=SYSTEM_DIFFICULTY_EFFECT,
            )
        )

        state["userGlobal"] = upd.userGlobal
        state["userTypeResidual"] = upd.userTypeResidual
        state["userDifficultyResidual"] = upd.userDifficultyResidual
        state["userFolderResidual"] = upd.userFolderResidual
        state["typeCount"] = upd.typeCount
        state["difficultyCount"] = upd.difficultyCount
        state["folderCount"] = upd.folderCount

        residual_for_type = upd.userTypeResidual.get(task_type_code, 0.0)
        # 어떤 분기를 탔는지 표시
        if upd.dropped:
            mark = "  [DROP]"
        elif not math.isclose(upd.logRatio, upd.clampedLogRatio, rel_tol=1e-9):
            mark = f"  [CLAMP log{upd.logRatio:+.3f}→{upd.clampedLogRatio:+.3f}]"
        else:
            mark = ""
        print(
            f"{tid:>3} | {type_kr:<4} {diff_kr:<4} | "
            f"{estimated:>4.0f} {estimate_result.aiEstimatedMinutes:>6.1f} {actual:>5.0f} | "
            f"{error:>+7.1%} | {upd.userGlobal:>+6.3f} {residual_for_type:>+10.3f}"
            f"{mark}"
        )

        assert estimate_result.aiEstimatedMinutes > 0

    # 최종 학습된 계수 출력
    print()
    print("=========== 최종 누적 계수 ===========")
    for user, state in user_state.items():
        type_counts = state["typeCount"] or {}
        residuals = state["userTypeResidual"] or {}
        difficulty_counts = state["difficultyCount"] or {}
        difficulty_residuals = state["userDifficultyResidual"] or {}
        folder_counts = state["folderCount"] or {}
        folder_residuals = state["userFolderResidual"] or {}
        print(f"{user}: userGlobal={state['userGlobal']:+.3f}")
        for type_code, count in type_counts.items():
            res = residuals.get(type_code, 0.0)
            print(f"    {type_code:<20} n={count:>2}  residual={res:+.3f}")
        for difficulty_code, count in difficulty_counts.items():
            res = difficulty_residuals.get(difficulty_code, 0.0)
            print(f"    {difficulty_code:<20} n={count:>2}  residual={res:+.3f}")
        for folder_code, count in folder_counts.items():
            res = folder_residuals.get(folder_code, 0.0)
            print(f"    {folder_code:<20} n={count:>2}  residual={res:+.3f}")


# ---------- 유형/난이도별 보정 방향 검증 -------------------------------


@pytest.mark.parametrize(
    "type_kr,difficulty_kr,expect_ratio_gt_baseline",
    [
        ("만족형", "상", True),    # +0.25 + 0.10 + 0.15 = +0.50 → 큰 폭 증가
        ("분량형", "하", False),   # +0.25 + 0.00 - 0.10 = +0.15 → 약간만 증가
        ("시간형", "하", False),   # +0.25 - 0.10 - 0.10 = +0.05 → 거의 변화 없음
    ],
)
def test_correction_direction_by_type_and_difficulty(type_kr, difficulty_kr, expect_ratio_gt_baseline):
    """유형·난이도가 까다로울수록 예측 보정 폭이 커진다."""
    estimated = 100.0
    baseline_ratio = 1.30  # 만족형/상이 1.65 수준, 분량형/하가 1.16 수준 — 1.30을 기준선으로

    req = _build_request(estimated, type_kr, difficulty_kr)
    result = estimate_initial_duration(req)
    ratio = result.aiEstimatedMinutes / estimated

    if expect_ratio_gt_baseline:
        assert ratio > baseline_ratio
    else:
        assert ratio < baseline_ratio

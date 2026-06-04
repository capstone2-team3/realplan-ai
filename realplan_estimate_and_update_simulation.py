"""
RealPlan 원본 서비스 코드 호출 기반 시뮬레이션 드라이버

목적
- 태스크 등록 시: app.services.task_registration.initial_estimator.estimation.estimate_initial_duration 호출
- 세션 종료 시: app.services.session_progress.remaining_estimator.estimate_remaining 호출
- 태스크 완료 시: app.services.profile_calibration.updater.update_coefficients 호출
- 실험별 예측 정확도 지표를 콘솔/CSV/그래프 PNG로 출력

실행 위치
- realplan-ai 프로젝트 루트에서 실행하는 것을 권장한다.
- 프로젝트 루트란 `app/` 디렉터리가 바로 보이는 위치다.

예시 실행
    uv run python realplan_estimate_and_update_simulation.py \
        --data-dir ./data/realplan-demo \
        --output-dir ./data/realplan-demo-output/baseline \
        --experiment-name baseline
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# -----------------------------------------------------------------------------
# 1. 프로젝트 원본 코드 import
# -----------------------------------------------------------------------------

try:
    from app.schemas.estimate import EstimateRequest
    from app.schemas.update import UpdateRequest
    from app.schemas.session import FocusLevel, SessionRemainingRequest
    from app.services.task_registration.initial_estimator.estimation import (
        estimate_initial_duration,
    )
    from app.services.profile_calibration.updater import update_coefficients
    from app.services.session_progress.remaining_estimator import estimate_remaining
except ModuleNotFoundError as exc:
    raise SystemExit(
        "원본 app 모듈을 import하지 못했습니다.\n"
        "이 스크립트는 realplan-ai 프로젝트 루트, 즉 app/ 디렉터리가 보이는 위치에서 실행해야 합니다.\n"
        "예: cd realplan-ai && uv run python realplan_estimate_and_update_simulation.py\n"
        f"원래 오류: {exc}"
    ) from exc


# -----------------------------------------------------------------------------
# 2. 시스템 prior/effect 설정
#    실제 DB 값이 있으면 이 값만 바꾸면 된다.
# -----------------------------------------------------------------------------

SYSTEM_GLOBAL_PRIOR = 0.0
SYSTEM_TYPE_EFFECT = {
    "TIME_BASED": 0.0,
    "QUANTITY_BASED": 0.0,
    "SATISFACTION_BASED": 0.0,
}
SYSTEM_DIFFICULTY_EFFECT = {
    "LOW": 0.0,
    "MEDIUM": 0.0,
    "HIGH": 0.0,
    "UNKNOWN": 0.0,
}


# -----------------------------------------------------------------------------
# 3. 원본 CSV 값 -> API 입력 enum 문자열 매핑
# -----------------------------------------------------------------------------

TASK_TYPE_MAP = {
    "시간형": "TIME_BASED",
    "분량형": "QUANTITY_BASED",
    "만족형": "SATISFACTION_BASED",
}

DIFFICULTY_MAP = {
    "하": "LOW",
    "중": "MEDIUM",
    "상": "HIGH",
    "모름": "UNKNOWN",
}

FOCUS_MAP = {
    "산만": "LOW",
    "보통": "MEDIUM",
    "꽤 집중": "HIGH",
    "완전 몰입": "VERY_HIGH",
}

Row = dict[str, Any]

TASK_RESULT_FIELDS = [
    "user_name",
    "task_id",
    "title",
    "task_type_raw",
    "task_type",
    "difficulty_raw",
    "difficulty",
    "estimated_minutes_user",
    "ai_estimated_minutes_at_registration",
    "correction_factor_at_registration",
    "log_correction_at_registration",
    "estimate_stage",
    "actual_minutes",
    "planning_error_ratio_actual_div_user_estimated",
    "clamped_planning_error_ratio",
    "log_ratio",
    "clamped_log_ratio",
    "update_stage",
    "dropped",
    "drop_reason",
    "completed_count_before",
    "user_global_before",
    "user_global_after",
    "type_residual_after",
    "difficulty_residual_after",
    "folder_residual_after",
    "type_count_after",
    "difficulty_count_after",
    "folder_count_after",
]

SESSION_RESULT_FIELDS = [
    "user_name",
    "task_id",
    "task_title",
    "session_order",
    "session_elapsed_minutes",
    "elapsed_minutes",
    "progress_percent",
    "focus_raw",
    "focus_level",
    "previous_ai_total_minutes",
    "updated_ai_total_minutes",
    "actual_minutes",
    "error_minutes_updated_total_minus_actual",
    "absolute_error_minutes",
    "absolute_percentage_error",
    "progress_based_remaining_minutes",
    "normalized_remaining_minutes",
    "blending_weight",
    "final_remaining_minutes",
    "focus_weight",
]

PROFILE_RESULT_FIELDS = [
    "user_name",
    "after_task_id",
    "completed_count",
    "user_global",
    "user_type_residual",
    "user_difficulty_residual",
    "user_folder_residual",
    "type_count",
    "difficulty_count",
    "folder_count",
]

# 초기 예측값과 세션 종료 시점별 재예측값을 한 행씩 누적해,
# 실제 소요시간 대비 오차 변화를 태스크별로 한눈에 확인하기 위한 출력 컬럼.
PREDICTION_TIMELINE_RESULT_FIELDS = [
    "user_name",
    "task_id",
    "task_title",
    "prediction_step",
    "session_order",
    "elapsed_minutes",
    "progress_percent",
    "focus_raw",
    "predicted_total_minutes",
    "actual_minutes",
    "error_minutes_predicted_minus_actual",
    "absolute_error_minutes",
    "absolute_percentage_error",
]

METRICS_SUMMARY_FIELDS = [
    "experiment",
    "task_count_initial",
    "task_count_last",
    "initial_bias",
    "initial_mae",
    "initial_mape",
    "last_bias",
    "last_mae",
    "last_mape",
    "mae_improvement_minutes",
    "mae_improvement_percent",
    "mape_improvement_points",
]

METRICS_BY_USER_FIELDS = [
    "experiment",
    "user_name",
    "task_count_initial",
    "task_count_last",
    "initial_bias",
    "initial_mae",
    "initial_mape",
    "last_bias",
    "last_mae",
    "last_mape",
    "mae_improvement_minutes",
    "mae_improvement_percent",
    "mape_improvement_points",
]


@dataclass
class UserProfile:
    """시뮬레이션 중 DB의 사용자 보정값 역할을 하는 in-memory 상태."""

    completed_count: int = 0
    user_global: float | None = None
    user_type_residual: dict[str, float] = field(default_factory=dict)
    user_difficulty_residual: dict[str, float] = field(default_factory=dict)
    user_folder_residual: dict[str, float] = field(default_factory=dict)
    type_count: dict[str, int] = field(default_factory=dict)
    difficulty_count: dict[str, int] = field(default_factory=dict)
    folder_count: dict[str, int] = field(default_factory=dict)

    def estimate_request(self, task: Row) -> EstimateRequest:
        return EstimateRequest(
            estimatedMinutes=float(task["estimated_minutes"]),
            taskType=str(task["task_type"]),
            difficulty=str(task["difficulty"]),
            folderId=task["folder_id"],
            completedCount=self.completed_count,
            userGlobal=self.user_global,
            userTypeResidual=dict(self.user_type_residual),
            userDifficultyResidual=dict(self.user_difficulty_residual),
            userFolderResidual=dict(self.user_folder_residual),
            typeCount=dict(self.type_count),
            difficultyCount=dict(self.difficulty_count),
            folderCount=dict(self.folder_count),
            systemGlobalPrior=SYSTEM_GLOBAL_PRIOR,
            systemTypeEffect=dict(SYSTEM_TYPE_EFFECT),
            systemDifficultyEffect=dict(SYSTEM_DIFFICULTY_EFFECT),
        )

    def update_request(self, task: Row) -> UpdateRequest:
        return UpdateRequest(
            estimatedMinutes=float(task["estimated_minutes"]),
            actualMinutes=float(task["actual_minutes"]),
            taskType=str(task["task_type"]),
            difficulty=str(task["difficulty"]),
            folderId=task["folder_id"],
            completedCount=self.completed_count,
            userGlobal=self.user_global,
            userTypeResidual=dict(self.user_type_residual),
            userDifficultyResidual=dict(self.user_difficulty_residual),
            userFolderResidual=dict(self.user_folder_residual),
            typeCount=dict(self.type_count),
            difficultyCount=dict(self.difficulty_count),
            folderCount=dict(self.folder_count),
            systemGlobalPrior=SYSTEM_GLOBAL_PRIOR,
            systemTypeEffect=dict(SYSTEM_TYPE_EFFECT),
            systemDifficultyEffect=dict(SYSTEM_DIFFICULTY_EFFECT),
        )

    def apply_update_response(self, response: Any) -> None:
        """원본 update_coefficients 응답을 다음 태스크의 입력 profile로 반영한다."""
        if getattr(response, "dropped", False):
            self.completed_count += 1
            return

        self.user_global = response.userGlobal
        self.user_type_residual = dict(response.userTypeResidual or {})
        self.user_difficulty_residual = dict(response.userDifficultyResidual or {})
        self.user_folder_residual = dict(response.userFolderResidual or {})
        self.type_count = dict(response.typeCount or {})
        self.difficulty_count = dict(response.difficultyCount or {})
        self.folder_count = dict(response.folderCount or {})
        self.completed_count += 1


# -----------------------------------------------------------------------------
# 4. CSV 로딩/정규화
# -----------------------------------------------------------------------------

def read_realplan_csv(path: Path) -> list[Row]:
    """현재 수집 CSV는 0행 설명/공백, 1행 컬럼명 형태라 header=1로 읽는다."""
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.reader(file)
        next(reader, None)
        headers = [col.strip() for col in next(reader, [])]
        rows: list[Row] = []
        for values in reader:
            row = {
                header: values[index].strip() if index < len(values) else ""
                for index, header in enumerate(headers)
                if header
            }
            if any(clean_text(value) for value in row.values()):
                rows.append(row)
    return rows


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_tasks(raw_rows: list[Row], user_id: int, user_name: str) -> list[Row]:
    rows: list[Row] = []

    for row in raw_rows:
        if clean_text(row.get("완료 여부")) != "O":
            continue

        estimated = to_float(row.get("본인 예상 소요시간(분)"))
        actual = to_float(row.get("실제 소요 시간(분) 계산"))
        if estimated is None or estimated <= 0 or actual is None or actual <= 0:
            continue

        task_id = to_float(row.get("태스크 ID"))
        if task_id is None:
            continue

        task_type_raw = clean_text(row.get("태스크 유형"))
        difficulty_raw = clean_text(row.get("난이도")) or "중"

        rows.append(
            {
                "user_id": user_id,
                "user_name": user_name,
                "task_id": int(task_id),
                "title": clean_text(row.get("태스크 이름")),
                "task_type_raw": task_type_raw,
                "task_type": TASK_TYPE_MAP.get(task_type_raw, task_type_raw),
                "difficulty_raw": difficulty_raw,
                "difficulty": DIFFICULTY_MAP.get(difficulty_raw, "MEDIUM"),
                "importance_raw": clean_text(row.get("우선순위")) or "보통",
                "estimated_minutes": estimated,
                "actual_minutes": actual,
                # 현재 CSV에는 folder 정보가 없으므로 None.
                # 나중에 폴더 열이 생기면 이 값만 채우면 원본 residual 로직이 그대로 반영된다.
                "folder_id": None,
            }
        )

    return sorted(rows, key=lambda row: row["task_id"])


def normalize_sessions(
    raw_rows: list[Row],
    user_id: int,
    user_name: str,
    allowed_task_ids: set[int],
) -> list[Row]:
    rows: list[Row] = []

    for row in raw_rows:
        task_id_value = to_float(row.get("태스크 ID"))
        if task_id_value is None:
            continue

        task_id = int(task_id_value)
        if task_id not in allowed_task_ids:
            continue

        elapsed = to_float(row.get("세션 소요 시간(분) 계산"))
        progress_percent = to_float(row.get("진행률(%)"))
        focus_raw = clean_text(row.get("집중도"))
        focus_level = FOCUS_MAP.get(focus_raw)

        if elapsed is None or elapsed <= 0:
            continue
        if progress_percent is None or progress_percent <= 0:
            continue
        if focus_level is None:
            continue

        rows.append(
            {
                "user_id": user_id,
                "user_name": user_name,
                "task_id": task_id,
                "session_order": int(to_float(row.get("세션 번호")) or 0),
                "elapsed_minutes": elapsed,
                "progress_percent": progress_percent,
                "progress": min(progress_percent / 100.0, 1.0),
                "focus_raw": focus_raw,
                "focus_level": focus_level,
            }
        )

    return sorted(rows, key=lambda row: (row["task_id"], row["session_order"]))


# -----------------------------------------------------------------------------
# 5. 출력 유틸
# -----------------------------------------------------------------------------

def safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def print_table(rows: list[Row], columns: list[str]) -> None:
    """지정한 컬럼만 간단한 고정폭 표로 출력한다."""
    if not rows:
        return

    widths = {
        column: max(len(column), *(len(str(row.get(column, ""))) for row in rows))
        for column in columns
    }
    header = " | ".join(column.ljust(widths[column]) for column in columns)
    separator = "-+-".join("-" * widths[column] for column in columns)
    print(header)
    print(separator)
    for row in rows:
        print(" | ".join(str(row.get(column, "")).ljust(widths[column]) for column in columns))


def write_csv(path: Path, rows: list[Row], fieldnames: list[str]) -> None:
    """엑셀에서 한글이 깨지지 않도록 utf-8-sig로 CSV를 저장한다."""
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def prediction_error_fields(predicted_total: float, actual_minutes: float) -> dict[str, float]:
    """예측 총 소요시간과 실제 소요시간의 차이를 보고서/엑셀용 컬럼으로 만든다."""
    error = predicted_total - actual_minutes
    absolute_error = abs(error)
    absolute_percentage_error = (
        absolute_error / actual_minutes * 100.0 if actual_minutes > 0 else 0.0
    )
    return {
        "error_minutes_predicted_minus_actual": round(error, 2),
        "error_minutes_updated_total_minus_actual": round(error, 2),
        "absolute_error_minutes": round(absolute_error, 2),
        "absolute_percentage_error": round(absolute_percentage_error, 2),
    }


# -----------------------------------------------------------------------------
# 6. 원본 서비스 호출 기반 시뮬레이션
# -----------------------------------------------------------------------------

def simulate_user(
    *,
    user_id: int,
    user_name: str,
    tasks_path: Path,
    sessions_path: Path,
) -> tuple[list[Row], list[Row], list[Row], list[Row]]:
    tasks = normalize_tasks(read_realplan_csv(tasks_path), user_id, user_name)
    sessions = normalize_sessions(
        read_realplan_csv(sessions_path),
        user_id,
        user_name,
        {int(task["task_id"]) for task in tasks},
    )

    profile = UserProfile()
    task_rows: list[Row] = []
    session_rows: list[Row] = []
    profile_rows: list[Row] = []
    prediction_timeline_rows: list[Row] = []

    for task in tasks:
        task_id = int(task["task_id"])
        completed_before = profile.completed_count
        user_global_before = profile.user_global

        # 1) 태스크 등록 시 초기 소요 시간 예측: 원본 서비스 호출
        estimate_req = profile.estimate_request(task)
        estimate_res = estimate_initial_duration(estimate_req)
        initial_ai_total = float(estimate_res.aiEstimatedMinutes)
        actual_minutes = float(task["actual_minutes"])

        prediction_timeline_rows.append(
            {
                "user_name": user_name,
                "task_id": task_id,
                "task_title": task["title"],
                "prediction_step": "INITIAL_ESTIMATE",
                "session_order": "",
                "elapsed_minutes": 0.0,
                "progress_percent": 0.0,
                "focus_raw": "",
                "predicted_total_minutes": round(initial_ai_total, 2),
                "actual_minutes": round(actual_minutes, 2),
                **prediction_error_fields(initial_ai_total, actual_minutes),
            }
        )

        # 2) 세션 종료 시 잔여 시간 예측: 원본 서비스 호출
        previous_ai_total = initial_ai_total
        task_sessions = [session for session in sessions if session["task_id"] == task_id]
        cumulative_elapsed = 0.0
        for session in task_sessions:
            cumulative_elapsed += float(session["elapsed_minutes"])
            remaining_req = SessionRemainingRequest(
                elapsedMinutes=cumulative_elapsed,
                progress=float(session["progress"]),
                focusLevel=FocusLevel(str(session["focus_level"])),
                previousAiTotalMinutes=previous_ai_total,
            )
            remaining_res = estimate_remaining(remaining_req)

            updated_ai_total = float(remaining_res.updatedAiTotalMinutes)
            error_fields = prediction_error_fields(updated_ai_total, actual_minutes)

            session_rows.append(
                {
                    "user_name": user_name,
                    "task_id": task_id,
                    "task_title": task["title"],
                    "session_order": int(session["session_order"]),
                    "session_elapsed_minutes": round(float(session["elapsed_minutes"]), 2),
                    "elapsed_minutes": round(cumulative_elapsed, 2),
                    "progress_percent": round(float(session["progress_percent"]), 2),
                    "focus_raw": session["focus_raw"],
                    "focus_level": session["focus_level"],
                    "previous_ai_total_minutes": round(previous_ai_total, 2),
                    "updated_ai_total_minutes": round(updated_ai_total, 2),
                    "actual_minutes": round(actual_minutes, 2),
                    "error_minutes_updated_total_minus_actual": error_fields[
                        "error_minutes_updated_total_minus_actual"
                    ],
                    "absolute_error_minutes": error_fields["absolute_error_minutes"],
                    "absolute_percentage_error": error_fields["absolute_percentage_error"],
                    "progress_based_remaining_minutes": round(
                        float(remaining_res.progressBasedRemainingMinutes), 2
                    ),
                    "normalized_remaining_minutes": round(
                        float(remaining_res.normalizedRemainingMinutes), 2
                    ),
                    "blending_weight": round(float(remaining_res.blendingWeight), 4),
                    "final_remaining_minutes": round(float(remaining_res.finalRemainingMinutes), 2),
                    "focus_weight": float(remaining_res.focusWeight),
                }
            )

            prediction_timeline_rows.append(
                {
                    "user_name": user_name,
                    "task_id": task_id,
                    "task_title": task["title"],
                    "prediction_step": "SESSION_REESTIMATE",
                    "session_order": int(session["session_order"]),
                    "elapsed_minutes": round(cumulative_elapsed, 2),
                    "progress_percent": round(float(session["progress_percent"]), 2),
                    "focus_raw": session["focus_raw"],
                    "predicted_total_minutes": round(updated_ai_total, 2),
                    "actual_minutes": round(actual_minutes, 2),
                    **error_fields,
                }
            )
            previous_ai_total = updated_ai_total

        # 3) 태스크 완료 시 사용자 보정값 업데이트: 원본 서비스 호출
        update_req = profile.update_request(task)
        update_res = update_coefficients(update_req)

        task_rows.append(
            {
                "user_name": user_name,
                "task_id": task_id,
                "title": task["title"],
                "task_type_raw": task["task_type_raw"],
                "task_type": task["task_type"],
                "difficulty_raw": task["difficulty_raw"],
                "difficulty": task["difficulty"],
                "estimated_minutes_user": round(float(task["estimated_minutes"]), 2),
                "ai_estimated_minutes_at_registration": round(
                    float(estimate_res.aiEstimatedMinutes), 2
                ),
                "correction_factor_at_registration": round(float(estimate_res.correctionFactor), 4),
                "log_correction_at_registration": round(float(estimate_res.logCorrection), 4),
                "estimate_stage": estimate_res.stage,
                "actual_minutes": round(float(task["actual_minutes"]), 2),
                "planning_error_ratio_actual_div_user_estimated": round(
                    float(update_res.planningErrorRatio), 4
                ),
                "clamped_planning_error_ratio": round(float(update_res.clampedPlanningErrorRatio), 4),
                "log_ratio": round(float(update_res.logRatio), 4),
                "clamped_log_ratio": round(float(update_res.clampedLogRatio), 4),
                "update_stage": update_res.stage,
                "dropped": update_res.dropped,
                "drop_reason": update_res.dropReason,
                "completed_count_before": completed_before,
                "user_global_before": None
                if user_global_before is None
                else round(float(user_global_before), 4),
                "user_global_after": round(float(update_res.userGlobal), 4),
                "type_residual_after": safe_json(update_res.userTypeResidual),
                "difficulty_residual_after": safe_json(update_res.userDifficultyResidual),
                "folder_residual_after": safe_json(update_res.userFolderResidual),
                "type_count_after": safe_json(update_res.typeCount),
                "difficulty_count_after": safe_json(update_res.difficultyCount),
                "folder_count_after": safe_json(update_res.folderCount),
            }
        )

        profile.apply_update_response(update_res)
        profile_rows.append(
            {
                "user_name": user_name,
                "after_task_id": task_id,
                "completed_count": profile.completed_count,
                "user_global": None
                if profile.user_global is None
                else round(float(profile.user_global), 4),
                "user_type_residual": safe_json(profile.user_type_residual),
                "user_difficulty_residual": safe_json(profile.user_difficulty_residual),
                "user_folder_residual": safe_json(profile.user_folder_residual),
                "type_count": safe_json(profile.type_count),
                "difficulty_count": safe_json(profile.difficulty_count),
                "folder_count": safe_json(profile.folder_count),
            }
        )

    return task_rows, session_rows, profile_rows, prediction_timeline_rows


# -----------------------------------------------------------------------------
# 7. 비교 지표 계산/출력/그래프
# -----------------------------------------------------------------------------

def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _metric_from_rows(rows: list[Row]) -> dict[str, float | int]:
    if not rows:
        return {"count": 0, "bias": 0.0, "mae": 0.0, "mape": 0.0}

    errors = [float(row["error_minutes_predicted_minus_actual"]) for row in rows]
    absolute_errors = [float(row["absolute_error_minutes"]) for row in rows]
    absolute_percentage_errors = [float(row["absolute_percentage_error"]) for row in rows]
    return {
        "count": len(rows),
        "bias": round(_mean(errors), 2),
        "mae": round(_mean(absolute_errors), 2),
        "mape": round(_mean(absolute_percentage_errors), 2),
    }


def _last_session_rows(timeline_rows: list[Row]) -> list[Row]:
    last_by_task: dict[tuple[str, int], Row] = {}
    for row in timeline_rows:
        if row.get("prediction_step") != "SESSION_REESTIMATE":
            continue
        key = (str(row["user_name"]), int(row["task_id"]))
        current_order = int(row.get("session_order") or 0)
        previous = last_by_task.get(key)
        previous_order = int(previous.get("session_order") or 0) if previous else -1
        if previous is None or current_order >= previous_order:
            last_by_task[key] = row
    return list(last_by_task.values())


def _summary_row(
    *,
    experiment_name: str,
    initial_rows: list[Row],
    last_rows: list[Row],
    user_name: str | None = None,
) -> Row:
    initial = _metric_from_rows(initial_rows)
    last = _metric_from_rows(last_rows)

    mae_improvement = float(initial["mae"]) - float(last["mae"])
    mae_improvement_percent = (
        mae_improvement / float(initial["mae"]) * 100.0 if float(initial["mae"]) > 0 else 0.0
    )
    mape_improvement_points = float(initial["mape"]) - float(last["mape"])

    row: Row = {
        "experiment": experiment_name,
        "task_count_initial": initial["count"],
        "task_count_last": last["count"],
        "initial_bias": initial["bias"],
        "initial_mae": initial["mae"],
        "initial_mape": initial["mape"],
        "last_bias": last["bias"],
        "last_mae": last["mae"],
        "last_mape": last["mape"],
        "mae_improvement_minutes": round(mae_improvement, 2),
        "mae_improvement_percent": round(mae_improvement_percent, 2),
        "mape_improvement_points": round(mape_improvement_points, 2),
    }
    if user_name is not None:
        row["user_name"] = user_name
    return row


def compute_and_save_metrics(
    *,
    timeline_rows: list[Row],
    output_dir: Path,
    experiment_name: str,
) -> tuple[list[Row], list[Row]]:
    """baseline/실험 비교용 지표를 콘솔 출력, CSV 저장, PNG 그래프 저장한다."""
    initial_rows = [
        row for row in timeline_rows if row.get("prediction_step") == "INITIAL_ESTIMATE"
    ]
    last_rows = _last_session_rows(timeline_rows)

    summary_rows = [
        _summary_row(
            experiment_name=experiment_name,
            initial_rows=initial_rows,
            last_rows=last_rows,
        )
    ]

    user_names = sorted({str(row["user_name"]) for row in timeline_rows})
    by_user_rows: list[Row] = []
    for user_name in user_names:
        user_initial_rows = [row for row in initial_rows if row["user_name"] == user_name]
        user_last_rows = [row for row in last_rows if row["user_name"] == user_name]
        by_user_rows.append(
            _summary_row(
                experiment_name=experiment_name,
                user_name=user_name,
                initial_rows=user_initial_rows,
                last_rows=user_last_rows,
            )
        )

    write_csv(output_dir / "metrics_summary.csv", summary_rows, METRICS_SUMMARY_FIELDS)
    write_csv(output_dir / "metrics_by_user.csv", by_user_rows, METRICS_BY_USER_FIELDS)
    write_metrics_graphs(output_dir=output_dir, summary_rows=summary_rows, by_user_rows=by_user_rows)

    print("\n=== 예측 정확도 비교 지표: 전체 ===")
    print_table(summary_rows, METRICS_SUMMARY_FIELDS)

    print("\n=== 예측 정확도 비교 지표: 사용자별 ===")
    print_table(by_user_rows, METRICS_BY_USER_FIELDS)

    print("\n=== 비교 지표 파일 저장 완료 ===")
    print(output_dir / "metrics_summary.csv")
    print(output_dir / "metrics_by_user.csv")
    print(output_dir / "metrics_mae_comparison.png")
    print(output_dir / "metrics_mape_comparison.png")
    print(output_dir / "metrics_by_user_mae.png")

    return summary_rows, by_user_rows


def write_metrics_graphs(
    *,
    output_dir: Path,
    summary_rows: list[Row],
    by_user_rows: list[Row],
) -> None:
    """matplotlib가 설치되어 있으면 비교 지표 그래프를 PNG로 저장한다."""
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        print(
            "\n[그래프 저장 건너뜀] matplotlib가 설치되어 있지 않습니다. "
            "그래프까지 저장하려면 `uv add matplotlib` 실행 후 다시 돌려주세요."
        )
        return

    if not summary_rows:
        return

    summary = summary_rows[0]

    labels = ["Initial estimate", "Last session"]
    mae_values = [float(summary["initial_mae"]), float(summary["last_mae"])]
    mape_values = [float(summary["initial_mape"]), float(summary["last_mape"])]

    fig = plt.figure(figsize=(7, 5))
    plt.bar(labels, mae_values)
    plt.title("MAE comparison")
    plt.ylabel("Minutes")
    for index, value in enumerate(mae_values):
        plt.text(index, value, f"{value:.2f}", ha="center", va="bottom")
    plt.tight_layout()
    fig.savefig(output_dir / "metrics_mae_comparison.png", dpi=200)
    plt.close(fig)

    fig = plt.figure(figsize=(7, 5))
    plt.bar(labels, mape_values)
    plt.title("MAPE comparison")
    plt.ylabel("Percent")
    for index, value in enumerate(mape_values):
        plt.text(index, value, f"{value:.2f}%", ha="center", va="bottom")
    plt.tight_layout()
    fig.savefig(output_dir / "metrics_mape_comparison.png", dpi=200)
    plt.close(fig)

    if by_user_rows:
        user_labels: list[str] = []
        initial_user_mae: list[float] = []
        last_user_mae: list[float] = []
        for row in by_user_rows:
            user_labels.append(str(row["user_name"]))
            initial_user_mae.append(float(row["initial_mae"]))
            last_user_mae.append(float(row["last_mae"]))

        x_positions = list(range(len(user_labels)))
        width = 0.35
        fig = plt.figure(figsize=(8, 5))
        plt.bar([x - width / 2 for x in x_positions], initial_user_mae, width, label="Initial")
        plt.bar([x + width / 2 for x in x_positions], last_user_mae, width, label="Last session")
        plt.title("MAE comparison by user")
        plt.ylabel("Minutes")
        plt.xticks(x_positions, user_labels)
        plt.legend()
        plt.tight_layout()
        fig.savefig(output_dir / "metrics_by_user_mae.png", dpi=200)
        plt.close(fig)


# -----------------------------------------------------------------------------
# 8. 실행 진입점
# -----------------------------------------------------------------------------

def default_user_files(data_dir: Path) -> list[dict[str, Any]]:
    return [
        {
            "user_id": 1,
            "user_name": "세진",
            "tasks_path": data_dir / "세진_tasks.csv",
            "sessions_path": data_dir / "세진_sessions.csv",
        },
        {
            "user_id": 2,
            "user_name": "나영",
            "tasks_path": data_dir / "나영_tasks.csv",
            "sessions_path": data_dir / "나영_sessions.csv",
        },
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, default=Path("./realplan_simulation_output"))
    parser.add_argument(
        "--experiment-name",
        type=str,
        default="baseline",
        help="결과 CSV/콘솔에 기록할 실험 이름. 예: baseline, exp1_blending_weight",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    all_task_results: list[Row] = []
    all_session_results: list[Row] = []
    all_profile_results: list[Row] = []
    all_prediction_timeline_results: list[Row] = []

    print("\n=== RealPlan 원본 서비스 호출 기반 시뮬레이션 시작 ===")
    print(f"Experiment: {args.experiment_name}")
    print(f"Python path[0]: {sys.path[0]}")
    print(f"Data dir: {args.data_dir.resolve()}")
    print(f"Output dir: {output_dir.resolve()}")

    for user in default_user_files(args.data_dir):
        if not user["tasks_path"].exists():
            raise FileNotFoundError(user["tasks_path"])
        if not user["sessions_path"].exists():
            raise FileNotFoundError(user["sessions_path"])

        task_rows, session_rows, profile_rows, timeline_rows = simulate_user(**user)
        all_task_results.extend(task_rows)
        all_session_results.extend(session_rows)
        all_profile_results.extend(profile_rows)
        all_prediction_timeline_results.extend(timeline_rows)

        print(f"\n[사용자: {user['user_name']}]")
        print(f"- 완료 태스크 수: {len(task_rows)}")
        print(f"- 잔여 시간 재예측 세션 수: {len(session_rows)}")
        if profile_rows:
            last = profile_rows[-1]
            print(f"- 최종 completedCount: {last['completed_count']}")
            print(f"- 최종 userGlobal: {last['user_global']}")

        preview_cols = [
            "task_id",
            "title",
            "estimated_minutes_user",
            "ai_estimated_minutes_at_registration",
            "actual_minutes",
            "planning_error_ratio_actual_div_user_estimated",
            "estimate_stage",
            "user_global_after",
            "dropped",
        ]
        if task_rows:
            print_table(task_rows, preview_cols)

    write_csv(output_dir / "task_estimate_and_update_results.csv", all_task_results, TASK_RESULT_FIELDS)
    write_csv(output_dir / "session_remaining_results.csv", all_session_results, SESSION_RESULT_FIELDS)
    write_csv(output_dir / "profile_history_results.csv", all_profile_results, PROFILE_RESULT_FIELDS)
    write_csv(
        output_dir / "prediction_timeline_results.csv",
        all_prediction_timeline_results,
        PREDICTION_TIMELINE_RESULT_FIELDS,
    )

    metadata = {
        "experiment": args.experiment_name,
        "system_global_prior": SYSTEM_GLOBAL_PRIOR,
        "system_global_prior_ratio": math.exp(SYSTEM_GLOBAL_PRIOR),
        "system_type_effect": SYSTEM_TYPE_EFFECT,
        "system_difficulty_effect": SYSTEM_DIFFICULTY_EFFECT,
    }
    with (output_dir / "experiment_metadata.json").open("w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)

    compute_and_save_metrics(
        timeline_rows=all_prediction_timeline_results,
        output_dir=output_dir,
        experiment_name=args.experiment_name,
    )

    print("\n=== 출력 파일 저장 완료 ===")
    print(output_dir / "task_estimate_and_update_results.csv")
    print(output_dir / "session_remaining_results.csv")
    print(output_dir / "profile_history_results.csv")
    print(output_dir / "prediction_timeline_results.csv")
    print(output_dir / "experiment_metadata.json")


if __name__ == "__main__":
    main()

"""예측 계수 term key 생성 유틸리티."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TaskKeys:
    """현재 task에 해당하는 term_key 모음."""

    folder: str
    difficulty: str
    task_type: str
    task_type_difficulty: str
    task_type_folder: str
    folder_difficulty: str


def _keys(folder_id: int, difficulty: str, task_type: str) -> TaskKeys:
    folder = f"folder:{folder_id}"
    difficulty_key = f"difficulty:{difficulty}"
    task_type_key = f"taskType:{task_type}"
    return TaskKeys(
        folder=folder,
        difficulty=difficulty_key,
        task_type=task_type_key,
        task_type_difficulty=f"taskTypeDifficulty:{task_type}:{difficulty}",
        task_type_folder=f"taskTypeFolder:{task_type}:{folder_id}",
        folder_difficulty=f"folderDifficulty:{folder_id}:{difficulty}",
    )


def _legacy_keys(folder_id: int, difficulty: str, task_type: str) -> dict[str, str]:
    """Deprecated: 기존 Spring 저장 key와 호환하기 위한 legacy key 모음."""

    folder_key = str(folder_id)
    return {
        "folder": folder_key,
        "difficulty": difficulty,
        "taskType": task_type,
        "folderDifficulty": f"{folder_key}:{difficulty}",
        "folderType": f"{folder_key}:{task_type}",
        "difficultyType": f"{difficulty}:{task_type}",
    }

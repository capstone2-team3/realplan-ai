"""
앱 전역 설정.

환경변수 로드는 다른 모듈 import 전에 한 번만 수행되어야 하므로
이 모듈을 가장 먼저 import 한다.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") # 환경변수에서 OpenAI API Key 가져옴. 없으면 None 반환.


if OPENAI_API_KEY is None:
    raise ValueError("OPENAI_API_KEY 환경 변수가 설정되어 있지 않습니다.")

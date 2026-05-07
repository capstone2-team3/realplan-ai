"""
앱 전역 설정.

환경변수 로드는 다른 모듈 import 전에 한 번만 수행되어야 하므로
이 모듈을 가장 먼저 import 한다.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


OPENAI_API_KEY: str | None = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL: str = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

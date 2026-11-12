"""AI 호출은 이 파일에서만 한다. 키와 모델은 .env에서 읽는다."""
import json
import os
import re
from pathlib import Path

import anthropic
from dotenv import load_dotenv

BASE = Path(__file__).parent
load_dotenv(BASE / ".env")

MODEL = os.getenv("MODEL", "claude-haiku-5-5")
_client = None


def _get_client():
    global _client
    if _client is None:
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError(".env에 ANTHROPIC_API_KEY가 없습니다.")
        _client = anthropic.Anthropic()  # 키는 환경변수(.env에서 불러옴)에서 읽는다
    return _client


def 지침읽기(이름: str) -> str:
    return (BASE / "지침" / f"{이름}.md").read_text(encoding="utf-8")


def _json로(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    return json.loads(text)


def 접수정리(원문: str) -> dict:
    """접수 원문 1건 -> 접수정리.md 지침에 따른 JSON(dict)."""
    try:
        response = _get_client().messages.create(
            model=MODEL,
            max_tokens=4000,
            system=지침읽기("접수정리"),
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": 원문}],
        )
    except anthropic.AuthenticationError:
        raise RuntimeError("API 키가 올바르지 않습니다. .env를 확인하세요.")
    except anthropic.APIConnectionError:
        raise RuntimeError("네트워크 연결에 실패했습니다.")
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"API 오류({e.status_code}): {e.message}")

    if response.stop_reason != "end_turn":
        raise RuntimeError(f"답변이 정상 종료되지 않았습니다: {response.stop_reason}")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        return _json로(text)
    except json.JSONDecodeError:
        raise RuntimeError(f"AI 답변이 JSON이 아닙니다: {text[:200]}")

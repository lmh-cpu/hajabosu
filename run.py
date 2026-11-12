"""접수함 폴더의 원문을 모두 처리해 하자대장(DB)에 저장한다.
흐름: 원문 읽기(코드) -> 접수정리(AI) -> 번호·기한·판정(rules.py) -> 저장(코드)"""
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

import ai
import db
import rules

BASE = Path(__file__).parent
입력폴더 = BASE / "data" / "접수함"
출력파일 = BASE / "data" / "하자대장.csv"

열 = ["접수번호", "접수일", "원문파일", "위치", "공종", "하자내용", "긴급도", "조치기한",
      "공사번호", "시공업체", "준공일", "보증만료일", "보증판정", "책임구분", "상태", "비고"]


def 파일명날짜(파일명: str):
    """파일명 `NN_YYYYMMDD_...`에서 날짜를 꺼낸다. 없으면 None."""
    m = re.search(r"_(\d{8})_", 파일명)
    return datetime.strptime(m.group(1), "%Y%m%d").date() if m else None


def 처리(파일: Path, 기존번호: list[str], 공사목록, 정리: dict | None = None) -> dict:
    """정리(AI 결과)를 이미 받아 두었으면 넘겨서 AI를 다시 부르지 않는다."""
    if 정리 is None:
        정리 = ai.접수정리(파일.read_text(encoding="utf-8"))
    접수일 = 정리.get("접수일") or 파일명날짜(파일.name)
    if not 접수일:
        raise RuntimeError("접수일을 알 수 없습니다 (원문과 파일명 모두 날짜 없음)")
    접수일 = rules.날짜(접수일)

    판정 = rules.보증판정(접수일, 정리.get("위치"), 정리.get("공종"), 공사목록)
    행 = {
        "접수번호": rules.접수번호(접수일, 기존번호),
        "접수일": 접수일,
        "원문파일": 파일.name,
        "위치": 정리.get("위치"),
        "공종": 정리.get("공종"),
        "하자내용": 정리.get("하자내용"),
        "긴급도": 정리.get("긴급도"),
        "조치기한": rules.조치기한(접수일, 정리.get("긴급도")),
        **판정,
    }
    if len(행["하자내용"] or "") > 40:
        행["비고"] = (행["비고"] + " " if 행["비고"] else "") + "하자내용 40자 초과"
    return 행


def 저장(행들: list[dict]):
    """하자대장 저장은 db.py가 한다. (data/하자대장.csv는 DB로 옮기기 전의 기록으로 남겨 둔다)"""
    return db.저장(행들)


def main():
    파일들 = sorted(입력폴더.glob("*.txt"))
    공사목록 = rules.공사정보읽기()
    행들, 번호들, 실패 = [], [], []
    for 파일 in 파일들:
        try:
            행 = 처리(파일, 번호들, 공사목록)
        except (RuntimeError, ValueError) as e:
            실패.append((파일.name, str(e)))
            print(f"[실패] {파일.name}: {e}")
            continue
        번호들.append(행["접수번호"])
        행들.append(행)
        print(f"[완료] {행['접수번호']} {파일.name}")

    저장(행들)
    print(f"\n{len(행들)}건 DB 저장, {len(실패)}건 실패")
    return 1 if 실패 else 0


if __name__ == "__main__":
    sys.exit(main())

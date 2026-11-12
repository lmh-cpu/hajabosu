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
    return _행(파일.name, 정리, rules.날짜(접수일), 기존번호, 공사목록)


def _행(원문파일: str, 정리: dict, 접수일, 기존번호: list[str], 공사목록) -> dict:
    """AI 정리 결과와 접수일로 하자대장 한 행을 만든다 (번호·기한·판정은 rules.py)."""
    판정 = rules.보증판정(접수일, 정리.get("위치"), 정리.get("공종"), 공사목록)
    행 = {
        "접수번호": rules.접수번호(접수일, 기존번호),
        "접수일": 접수일,
        "원문파일": 원문파일,
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


def 저장(행들: list[dict], 완료=None):
    """하자대장 저장은 db.py가 한다. (data/하자대장.csv는 DB로 옮기기 전의 기록으로 남겨 둔다)
    완료 = [(접수 id, 접수번호)]를 주면 그 접수를 같이 '처리완료'로 바꾼다."""
    return db.저장(행들, 완료)


DB접수표시 = "DB접수-"  # 하자대장 '원문파일' 칸에 적는 접수 출처 (뒤에 접수 id)


def 접수원문(접: dict) -> str:
    """DB 접수 한 건을 AI에게 줄 원문 글로 만든다."""
    줄 = [f"{이름}: {접[이름]}" for 이름 in ("접수자", "부서", "위치") if 접.get(이름)]
    return "\n".join(줄 + ["", 접["내용"]])


def 접수처리(기존번호: list[str], 공사목록):
    """DB의 '미처리' 접수를 처리한다. 접수일은 AI가 찾지 않고 접수 화면의 발견일을 쓴다
    (발견일이 비어 있으면 접수된 날). 기존번호에 새 번호를 덧붙인다.
    돌려주는 값: (대장 행들, [(접수 id, 접수번호)], 실패 목록)"""
    행들, 완료, 실패 = [], [], []
    for 접 in db.접수목록("미처리"):
        이름 = f"{DB접수표시}{접['id']}"
        try:
            정리 = ai.접수정리(접수원문(접))
            접수일 = rules.날짜(접["발견일"] or 접["접수일시"])
            행 = _행(이름, 정리, 접수일, 기존번호, 공사목록)
        except (RuntimeError, ValueError) as e:
            실패.append((이름, str(e)))
            print(f"[실패] {이름}: {e}")
            continue
        기존번호.append(행["접수번호"])
        행들.append(행)
        완료.append((접["id"], 행["접수번호"]))
        print(f"[완료] {행['접수번호']} {이름}")
    return 행들, 완료, 실패


def main(파일도=True):
    """접수함 파일과 DB 접수를 처리한다. `python run.py 접수`는 DB 접수만 처리한다."""
    파일들 = sorted(입력폴더.glob("*.txt")) if 파일도 else []
    공사목록 = rules.공사정보읽기()
    # 파일 건의 번호가 DB 접수 건의 번호를 덮어쓰지 않게, 이미 대장에 있는 DB 접수 번호를 먼저 깔아 둔다
    대장 = db.조회()
    행들, 실패 = [], []
    번호들 = [r["접수번호"] for r in 대장 if str(r["원문파일"]).startswith(DB접수표시)]
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

    # DB 접수 건은 대장에 이미 있는 번호와 이번에 파일 건이 받은 번호를 모두 피해 번호를 받는다
    사용중 = sorted({r["접수번호"] for r in 대장} | {행["접수번호"] for 행 in 행들})
    접수행들, 완료, 접수실패 = 접수처리(사용중, 공사목록)
    저장(행들 + 접수행들, 완료)
    실패 += 접수실패
    print(f"\n{len(행들)}건(파일) + {len(접수행들)}건(DB 접수) 저장, {len(실패)}건 실패")
    return 1 if 실패 else 0


if __name__ == "__main__":
    sys.exit(main(파일도="접수" not in sys.argv[1:]))

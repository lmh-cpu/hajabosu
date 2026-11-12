"""번호·기한·판정 규칙. 업무설명_하자보수.md의 2·4·5절을 그대로 코드로 옮긴 것이다.
날짜 계산과 판정은 AI가 아니라 이 파일이 한다."""
import csv
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).parent
공사정보_경로 = BASE / "data" / "공사정보.csv"

# 4절 긴급도 -> 조치기한(접수일 + n일)
기한일수 = {"긴급": 1, "높음": 3, "보통": 7}
임박일수 = 30  # 5절: 보증만료일까지 30일 이내


def 날짜(값) -> date:
    if isinstance(값, datetime):
        return 값.date()
    if isinstance(값, date):
        return 값
    return datetime.strptime(str(값).strip(), "%Y-%m-%d").date()


# ---------- 접수번호 (2절) ----------
def 접수번호(접수일, 기존번호=()) -> str:
    """HJ-접수일(YYYYMMDD)-순번(01부터). 기존번호 중 같은 날짜 개수 + 1이 순번."""
    앞 = f"HJ-{날짜(접수일):%Y%m%d}-"
    순번 = sum(1 for n in 기존번호 if str(n).startswith(앞)) + 1
    return f"{앞}{순번:02d}"


# ---------- 조치기한 (4절) ----------
def 조치기한(접수일, 긴급도) -> date:
    if 긴급도 not in 기한일수:
        raise ValueError(f"알 수 없는 긴급도: {긴급도!r} (긴급·높음·보통 중 하나)")
    return 날짜(접수일) + timedelta(days=기한일수[긴급도])


# ---------- 공사정보 ----------
def 공사정보읽기(경로=공사정보_경로) -> list[dict]:
    with open(경로, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _보증만료일(준공일, 보증년수) -> date:
    """준공일 + 하자보증기간(년). 2월 29일 준공은 평년에 2월 28일로 본다."""
    d = 날짜(준공일)
    y = d.year + int(보증년수)
    try:
        return d.replace(year=y)
    except ValueError:
        return d.replace(year=y, day=28)


def _공종후보(공종) -> list[str] | None:
    """공종 값에서 후보 목록을 꺼낸다. 하나로 정해졌으면 None, 미정이면 빈 목록."""
    if not 공종 or 공종.strip() == "미정":
        return []
    후보 = [x.strip() for x in 공종.split("/") if x.strip()]
    return 후보 if len(후보) > 1 else None


def _임박(만료일: date, 접수일: date) -> bool:
    남은일 = (만료일 - 접수일).days
    return 0 <= 남은일 <= 임박일수


# ---------- 보증 판정 (5절) ----------
def 보증판정(접수일, 위치, 공종, 공사목록=None) -> dict:
    """대장에 넣을 판정 칸을 dict로 돌려준다.
    칸: 공사번호, 시공업체, 준공일, 보증만료일, 보증판정, 책임구분, 상태, 비고
    """
    접수 = 날짜(접수일)
    공사목록 = 공사정보읽기() if 공사목록 is None else 공사목록
    위치공사 = [c for c in 공사목록 if 위치 and c["위치"] == 위치.strip()]

    결과 = {"공사번호": None, "시공업체": None, "준공일": None, "보증만료일": None,
            "보증판정": "확인필요", "책임구분": "확인필요", "상태": "확인필요", "비고": ""}

    후보종 = _공종후보(공종)
    if 후보종 is not None or not 위치:
        # 공종이 미정이거나 후보가 여럿: 담당자가 정한다. 후보 공사의 만료임박만 비고에 적는다.
        후보 = [c for c in 위치공사 if not 후보종 or c["공종"] in 후보종]
        return _확인필요(결과, 접수, 후보)

    맞는공사 = [c for c in 위치공사 if c["공종"] == 공종.strip()]
    if len(맞는공사) != 1:  # 0건 또는 2건 이상
        return _확인필요(결과, 접수, 맞는공사)

    공사 = 맞는공사[0]
    만료 = _보증만료일(공사["준공일"], 공사["하자보증기간(년)"])
    결과.update(공사번호=공사["공사번호"], 시공업체=공사["시공업체"],
              준공일=날짜(공사["준공일"]), 보증만료일=만료, 상태="판정완료")
    if 접수 <= 만료:  # 같은 날 포함
        결과.update(보증판정="보증내", 책임구분="시공업체")
        if _임박(만료, 접수):
            결과["비고"] = "만료임박"
    else:
        결과.update(보증판정="보증만료", 책임구분="자체보수")
    return 결과


def _확인필요(결과: dict, 접수: date, 후보: list[dict]) -> dict:
    임박공사 = []
    for c in 후보:
        만료 = _보증만료일(c["준공일"], c["하자보증기간(년)"])
        if 접수 <= 만료 and _임박(만료, 접수):
            임박공사.append(c["공사번호"])
    if 임박공사:
        결과["비고"] = "만료임박(" + ", ".join(임박공사) + ")"
    return 결과

"""저장은 이 파일에서만 한다. 연결 정보는 .env의 DATABASE_URL (웹 배포는 Streamlit Secrets).
처음 연결할 때 테이블 2개(접수, 하자대장)가 없으면 만들고, 두 테이블 모두 RLS를 켠다."""
import os
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BASE = Path(__file__).parent
load_dotenv(BASE / ".env")

테이블 = "하자대장"
접수테이블 = "접수"
# 업무설명 2절의 하자대장 항목 (data/하자대장.csv, run.py의 열과 같은 순서)
열 = ["접수번호", "접수일", "원문파일", "위치", "공종", "하자내용", "긴급도", "조치기한",
      "공사번호", "시공업체", "준공일", "보증만료일", "보증판정", "책임구분", "상태", "비고"]
날짜열 = {"접수일", "조치기한", "준공일", "보증만료일"}
접수열 = ["id", "접수일시", "발견일", "접수자", "부서", "위치", "내용", "처리상태", "접수번호"]

_engine = None
_준비됨 = False


def _주소() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        try:  # 웹 배포(Streamlit Secrets)에서는 .env가 없다
            import streamlit as st
            url = st.secrets.get("DATABASE_URL")
        except Exception:
            url = None
    if not url:
        raise RuntimeError("DATABASE_URL이 없습니다. .env를 확인하세요.")
    # SQLAlchemy가 psycopg(3)를 쓰도록 접속 방식을 붙인다
    return url.replace("postgresql://", "postgresql+psycopg://", 1).replace(
        "postgres://", "postgresql+psycopg://", 1)


def _연결도구():
    global _engine
    if _engine is None:
        _engine = create_engine(_주소(), pool_pre_ping=True)
    return _engine


def 엔진():
    """연결 도구를 돌려준다. 처음 한 번은 테이블을 만든다."""
    global _준비됨
    e = _연결도구()
    if not _준비됨:
        테이블만들기()
        _준비됨 = True
    return e


def 테이블만들기():
    """없으면 만든다(있으면 그대로). 두 테이블 모두 RLS를 켠다.
    RLS를 켜면 Supabase 공개 API로는 읽고 쓰지 못한다. 이 파일의 직접 연결에는 영향이 없다."""
    칸 = ", ".join(f'"{k}" {"date" if k in 날짜열 else "text"}' for k in 열)
    with _연결도구().begin() as c:
        c.execute(text(f'CREATE TABLE IF NOT EXISTS "{테이블}" ({칸}, PRIMARY KEY ("접수번호"))'))
        c.execute(text(f'ALTER TABLE "{테이블}" ENABLE ROW LEVEL SECURITY'))
        c.execute(text(f'''
            CREATE TABLE IF NOT EXISTS "{접수테이블}" (
                "id" bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                "접수일시" timestamptz NOT NULL DEFAULT now(),
                "발견일" date,
                "접수자" text,
                "부서" text,
                "위치" text,
                "내용" text NOT NULL,
                "처리상태" text NOT NULL DEFAULT '미처리'
                    CHECK ("처리상태" IN ('미처리', '처리완료')),
                "접수번호" text
            )'''))
        c.execute(text(f'ALTER TABLE "{접수테이블}" ENABLE ROW LEVEL SECURITY'))


# ---------------------------------------------------------------- 하자대장
def _값(열이름: str, 값):
    if 값 is None or 값 == "":
        return None
    if 열이름 in 날짜열 and not isinstance(값, date):
        return datetime.strptime(str(값).strip(), "%Y-%m-%d").date()
    return 값


def 저장(행들: list[dict], 완료: list[tuple[int, str]] | None = None) -> int:
    """하자대장에 저장한다. 접수번호가 같으면 덮어쓰고, 없으면 넣는다. 저장한 건수를 돌려준다.
    완료 = [(접수 id, 접수번호), ...]를 주면 같은 거래 안에서 그 접수를 '처리완료'로 바꾸고 접수번호를 적는다."""
    if not 행들:
        return 0
    이름 = [f"p{i}" for i in range(len(열))]
    칸 = ", ".join(f'"{k}"' for k in 열)
    값자리 = ", ".join(f":{n}" for n in 이름)
    갱신 = ", ".join(f'"{k}" = EXCLUDED."{k}"' for k in 열 if k != "접수번호")
    sql = text(f'INSERT INTO "{테이블}" ({칸}) VALUES ({값자리}) '
               f'ON CONFLICT ("접수번호") DO UPDATE SET {갱신}')
    자료 = [{n: _값(k, 행.get(k)) for n, k in zip(이름, 열)} for 행 in 행들]
    with 엔진().begin() as c:
        c.execute(sql, 자료)
        for 접수id, 번호 in 완료 or []:
            c.execute(text(f'UPDATE "{접수테이블}" SET "처리상태" = \'처리완료\', "접수번호" = :n '
                           'WHERE "id" = :i'), {"n": 번호, "i": 접수id})
    return len(자료)


def 조회() -> list[dict]:
    """하자대장 전체를 접수번호 순으로 돌려준다."""
    칸 = ", ".join(f'"{k}"' for k in 열)
    with 엔진().connect() as c:
        결과 = c.execute(text(f'SELECT {칸} FROM "{테이블}" ORDER BY "접수번호"'))
        return [dict(zip(열, 행)) for 행 in 결과]


# ---------------------------------------------------------------- 접수
def 접수저장(발견일: date, 접수자: str, 부서: str, 위치: str, 내용: str) -> int:
    """접수 화면(intake.py)에서 받은 내용을 저장하고 id를 돌려준다. 처리상태는 '미처리'."""
    with 엔진().begin() as c:
        return c.execute(
            text(f'INSERT INTO "{접수테이블}" ("발견일", "접수자", "부서", "위치", "내용") '
                 'VALUES (:d, :who, :dept, :loc, :body) RETURNING "id"'),
            {"d": 발견일, "who": 접수자 or None, "dept": 부서 or None,
             "loc": 위치 or None, "body": 내용},
        ).scalar_one()


def 접수목록(처리상태: str | None = None) -> list[dict]:
    """접수 목록(id 순). 처리상태('미처리'/'처리완료')를 주면 그것만 돌려준다."""
    칸 = ", ".join(f'"{k}"' for k in 접수열)
    sql = f'SELECT {칸} FROM "{접수테이블}"'
    인자 = {}
    if 처리상태:
        sql += ' WHERE "처리상태" = :s'
        인자["s"] = 처리상태
    with 엔진().connect() as c:
        결과 = c.execute(text(sql + ' ORDER BY "id"'), 인자)
        return [dict(zip(접수열, 행)) for 행 in 결과]

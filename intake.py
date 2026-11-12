"""접수 화면 (웹에 배포, 매장·현장용). 하자를 본 사람이 내용을 적어 보내면 DB의 접수 테이블에 쌓인다.
AI 호출과 판정은 여기서 하지 않는다. 담당자 화면(app.py)에서 처리한다.
실행: streamlit run intake.py"""
from datetime import date

import streamlit as st

import db

st.set_page_config(page_title="하자 접수", layout="centered")

st.title("하자 접수")
st.write("건물에서 발견한 하자(누수, 파손, 고장 등)를 적어서 보내 주세요. 시설관리팀이 확인합니다.")
st.info("위치(층·구역)와 증상을 꼭 적어 주세요. 위험한 상황(누수, 감전, 넘어짐 위험)이면 전화로도 알려 주세요.")

with st.form("접수", clear_on_submit=True):
    발견일 = st.date_input("발견한 날짜", value=date.today())
    접수자 = st.text_input("접수자 이름", max_chars=30)
    부서 = st.text_input("부서(소속)", max_chars=50, placeholder="예: 3F 패션관 운영파트")
    위치 = st.text_input("위치 (층·구역)", max_chars=50, placeholder="예: 5F 레스토랑가")
    내용 = st.text_area("하자 내용", height=200, max_chars=2000,
                        placeholder="예: 복도 502호와 505호 사이 조명 3개가 깜빡입니다. 어제 저녁부터 그렇고 오늘은 하나가 꺼졌다 켜졌다 합니다.")
    보내기 = st.form_submit_button("접수하기", type="primary")

if 보내기:
    if len(내용.strip()) < 5:
        st.error("하자 내용을 5글자 이상 적어 주세요.")
    elif not (접수자.strip() and 부서.strip() and 위치.strip()):
        st.error("접수자, 부서, 위치를 모두 적어 주세요. 확인이 필요할 때 연락할 곳과 현장을 알기 위해서입니다.")
    else:
        try:
            번호 = db.접수저장(발견일, 접수자.strip(), 부서.strip(), 위치.strip(), 내용.strip())
            st.success(f"접수되었습니다. (접수 번호 {번호})")
        except Exception:  # 연결 정보 등이 화면에 나오지 않게 한다
            st.error("접수를 저장하지 못했습니다. 잠시 뒤 다시 시도하거나 시설관리팀에 알려 주세요.")

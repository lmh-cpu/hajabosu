"""담당자 화면 (내 PC). 접수 원문이 하자대장이 되기까지의 과정을 단계별로 보여준다.
실행: streamlit run app.py"""
import pandas as pd
import streamlit as st

import ai
import db
import rules
import run

st.set_page_config(page_title="하자보수 접수 처리", layout="wide")

파일들 = sorted(run.입력폴더.glob("*.txt"))
공사목록 = rules.공사정보읽기()
st.session_state.setdefault("정리", {})  # 파일명 -> AI가 정리한 JSON (AI 호출 결과 보관)

st.title("하자보수 접수 처리")
st.caption("접수 원문 → 하자대장. 🤖 AI는 읽고 해석만, ⚙️ 코드는 번호·기한·판정 계산, 🙋 사람은 확인과 승인.")

tab1, tab2 = st.tabs(["과정 보기 (접수 1건씩)", "하자대장"])


# ---------------------------------------------------------------- 과정 보기
with tab1:
    if not 파일들:
        st.warning("data/접수함에 접수 파일이 없습니다.")
        st.stop()

    선택 = st.selectbox("접수 원문", 파일들, format_func=lambda p: p.name)
    원문 = 선택.read_text(encoding="utf-8")

    st.subheader("① 원문  ⚙️ 코드가 읽음")
    st.code(원문, language=None)

    st.subheader("② 내용 정리  🤖 AI")
    if st.button("AI로 정리하기", disabled=선택.name in st.session_state["정리"]):
        with st.spinner("AI가 읽는 중..."):
            try:
                st.session_state["정리"][선택.name] = ai.접수정리(원문)
            except RuntimeError as e:
                st.error(str(e))

    정리 = st.session_state["정리"].get(선택.name)
    if not 정리:
        st.info("버튼을 누르면 AI를 호출합니다. 아래 단계는 AI 결과가 있어야 보입니다.")
    else:
        칸 = ["접수일", "위치", "공종", "하자내용", "긴급도"]
        st.dataframe(pd.DataFrame([{k: 정리.get(k) for k in 칸}]), hide_index=True, width="stretch")
        st.caption("판단 근거: " + str(정리.get("근거", "")))

        행 = run.처리(선택, [], 공사목록, 정리)

        st.subheader("③ 번호·기한·판정  ⚙️ 코드 (rules.py)")
        a, b, c = st.columns(3)
        a.metric("접수번호", 행["접수번호"])
        일수 = rules.기한일수[행["긴급도"]]
        b.metric("조치기한", str(행["조치기한"]), f"접수일 +{일수}일 ({행['긴급도']})", delta_color="off")
        c.metric("보증판정", 행["보증판정"], 행["책임구분"], delta_color="off")

        st.markdown(f"**공사 매칭** — 위치 `{행['위치']}` · 공종 `{행['공종']}`")
        후보 = [x for x in 공사목록 if x["위치"] == (행["위치"] or "")]
        if 후보:
            표 = pd.DataFrame(후보)[["공사번호", "공사명", "공종", "시공업체", "준공일", "하자보증기간(년)"]]
            표.insert(0, "선택", 표["공사번호"] == 행["공사번호"])
            st.dataframe(표, hide_index=True, width="stretch")
        else:
            st.write("같은 위치의 공사가 공사정보에 없습니다.")
        if 행["보증만료일"]:
            st.write(f"보증만료일 = 준공일 {행['준공일']} + 보증기간 → **{행['보증만료일']}**, "
                     f"접수일 {행['접수일']} 기준 **{행['보증판정']}**")
        if 행["비고"]:
            st.warning("비고: " + 행["비고"])

        st.subheader("④ 하자대장에 들어갈 행")
        st.dataframe(pd.DataFrame([{k: ("" if 행[k] is None else 행[k]) for k in run.열}]),
                     hide_index=True, width="stretch")

        st.subheader("⑤ 확인  🙋 사람")
        할일 = ["AI가 뽑은 공종·긴급도·하자내용이 원문과 맞는지 확인"]
        if 행["상태"] == "확인필요":
            할일.insert(0, "공종 또는 공사가 정해지지 않았습니다. 현장을 보고 정한 뒤 판정을 다시 실행")
        if "만료임박" in 행["비고"]:
            할일.insert(0, "보증 만료가 임박했습니다. 만료 전에 시공업체에 요청")
        if 행["책임구분"] == "시공업체":
            할일.append("공문 대상입니다. 승인하면 조치요청으로 넘어갑니다 (공문 생성은 다음 단계)")
        for t in 할일:
            st.checkbox(t, key=f"{선택.name}-{t}")


# ---------------------------------------------------------------- 하자대장
with tab2:
    if st.button("접수함 전체 처리하고 하자대장(DB)에 저장"):
        행들, 번호들, 실패 = [], [], []
        진행 = st.progress(0.0)
        for i, 파일 in enumerate(파일들):
            try:
                if 파일.name not in st.session_state["정리"]:
                    st.session_state["정리"][파일.name] = ai.접수정리(파일.read_text(encoding="utf-8"))
                행 = run.처리(파일, 번호들, 공사목록, st.session_state["정리"][파일.name])
                번호들.append(행["접수번호"])
                행들.append(행)
            except (RuntimeError, ValueError) as e:
                실패.append(f"{파일.name}: {e}")
            진행.progress((i + 1) / len(파일들))
        run.저장(행들)
        st.success(f"{len(행들)}건 저장했습니다.")
        for 메시지 in 실패:
            st.error(메시지)

    대장행 = db.조회()
    if 대장행:
        대장 = pd.DataFrame(대장행, columns=db.열).astype(str).replace({"None": "", "NaT": ""})
        건수 = lambda 열, 값: int((대장[열] == 값).sum())
        m = st.columns(4)
        m[0].metric("전체", len(대장))
        m[1].metric("긴급", 건수("긴급도", "긴급"))
        m[2].metric("시공업체 요청", 건수("책임구분", "시공업체"))
        m[3].metric("확인필요", 건수("상태", "확인필요"))
        st.dataframe(대장, hide_index=True, width="stretch")
    else:
        st.info("아직 하자대장에 저장된 건이 없습니다. 위 버튼으로 만드세요.")

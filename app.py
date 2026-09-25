"""Interface Streamlit do ContratoClaro."""

# ruff: noqa: I001
import sys
from pathlib import Path

# Permite iniciar o Streamlit logo após clonar o projeto, antes da instalação editável.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import streamlit as st

from contratoclaro.application import AgentSettings, build_agent, load_uploads, session_key
from contratoclaro.budget import BudgetLedger


st.set_page_config(page_title="ContratoClaro", page_icon="📄", layout="centered")
st.title("📄 ContratoClaro")
st.caption("Análise educativa de contratos de prestação de serviços com evidências.")

with st.sidebar:
    st.header("Configuração")
    perspective = st.radio("Perspectiva", ["contratante", "prestador"], horizontal=True)
    variant = st.selectbox(
        "Proteção",
        ["hardened", "baseline"],
        format_func=lambda x: "Corrigida" if x == "hardened" else "Baseline",
    )
    backend = st.selectbox(
        "Execução",
        ["local", "harness"],
        format_func=lambda x: "Python local + Bedrock" if x == "local" else "AgentCore Harness",
    )
    harness_arn = ""
    if backend == "harness":
        harness_arn = st.text_input(
            "ARN do Harness", type="password", help="Mantido apenas nesta sessão do aplicativo."
        )
    if st.button("Reiniciar conversa", use_container_width=True):
        for key in ("agent", "session_key", "messages"):
            st.session_state.pop(key, None)
        st.rerun()

st.info("Este protótipo explica o texto enviado e não substitui aconselhamento jurídico profissional.")
files = st.file_uploader("Envie um ou dois contratos", type=["pdf", "txt", "md"], accept_multiple_files=True)

if len(files) > 2:
    st.error("Envie no máximo dois contratos por sessão.")
    st.stop()

uploads = [(item.name, item.getvalue()) for item in files]
settings = AgentSettings(perspective, variant, backend, harness_arn.strip())

if uploads:
    try:
        key = session_key(uploads, settings)
        if st.session_state.get("session_key") != key:
            documents = load_uploads(uploads)
            ledger = BudgetLedger()
            st.session_state.agent = build_agent(documents, settings, ledger=ledger)
            st.session_state.session_key = key
            st.session_state.messages = []
    except Exception as exc:  # noqa: BLE001 - render integration errors in the beginner-facing UI
        st.error(str(exc))
        st.stop()

for message in st.session_state.get("messages", []):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("sources"):
            with st.expander("Trechos usados"):
                for source in message["sources"]:
                    st.markdown(f"**{source['document_name']} — página {source['page']}**  ")
                    st.code(source["text"], language=None)

question = st.chat_input("Pergunte sobre o contrato", disabled=not uploads)
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        try:
            with st.spinner("Analisando os trechos do contrato..."):
                result = st.session_state.agent.ask(question)
            st.markdown(result["answer"])
            if result["sources"]:
                with st.expander("Trechos usados"):
                    for source in result["sources"]:
                        st.markdown(f"**{source['document_name']} — página {source['page']}**  ")
                        st.code(source["text"], language=None)
            if not result["citations_valid"]:
                st.warning("A resposta contém uma referência que não veio dos trechos recuperados.")
            st.session_state.messages.append(
                {"role": "assistant", "content": result["answer"], "sources": result["sources"]}
            )
        except Exception as exc:  # noqa: BLE001 - render integration errors in the beginner-facing UI
            st.error(str(exc))

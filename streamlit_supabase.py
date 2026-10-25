from __future__ import annotations

import json
import logging
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

import streamlit as st
from dotenv import load_dotenv

if TYPE_CHECKING:
    from app.domain.scenario import Scenario
from app.infrastructure.database import get_pool
from app.infrastructure.interview_repository import (
    ExpiredTurn,
    InterviewBusy,
    InterviewFinished,
    InterviewRepository,
    InvalidAccessCode,
    StaleInterview,
)
from app.services.persistent_interview import generate_turn, student_report
from app.services.group_registration import (
    InvalidActivityCode, register_group, registration_settings, valid_activity_code,
)


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent
SCENARIO_PATH = PROJECT_ROOT / "scenarios" / "monitoring_system.json"
# A tela inicial usa as configurações sem precisar abrir uma conexão PostgreSQL.
load_dotenv(PROJECT_ROOT / ".env", override=False)
MOOD_LABELS = {
    "neutral": "Neutro",
    "collaborative": "Colaborativo",
    "impatient": "Impaciente",
    "irritated": "Irritado",
}


@st.cache_resource(show_spinner=False)
def get_repository():
    return InterviewRepository(get_pool())


@st.cache_resource(max_entries=8, show_spinner=False)
def load_session_scenario(snapshot_json: str):
    from app.domain.scenario import Scenario
    return Scenario.model_validate(json.loads(snapshot_json))


@st.cache_resource(max_entries=8, show_spinner=False)
def load_graph(snapshot_json: str):
    # Importações e configuração da IA acontecem somente ao enviar uma pergunta.
    from app.graph import create_interview_graph
    # A sessão mantém o cenário que existia quando o grupo foi criado.
    scenario = load_session_scenario(snapshot_json)
    return scenario, create_interview_graph(scenario)


@st.cache_resource(show_spinner=False)
def load_registration_scenario(modified_ns: int):
    from app.domain.scenario import load_scenario
    return load_scenario(SCENARIO_PATH)


def apply_interface_style() -> None:
    st.markdown("""
<style>
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background: #030303 !important; color: #eeeeF3;
}
[data-testid="stHeader"] { background: rgba(3,3,3,.94); }
[data-testid="stSidebar"] { background: #09090b; border-right: 1px solid #202024; }
[data-testid="stMainBlockContainer"], .main .block-container {
    max-width: 940px; padding-top: 2.4rem; padding-bottom: 5rem;
}
.sv-brand { display: flex; align-items: center; gap: 14px; margin-bottom: 16px; }
.sv-brand-mark {
    width: 48px; height: 48px; border-radius: 16px; display: grid;
    place-items: center; background: #17121f; border: 1px solid #30233f; font-size: 25px;
}
.sv-eyebrow { color: #a0a0ae; font-size: 10px; letter-spacing: 1.6px; font-weight: 650; }
.sv-brand h1 { color: #f5f4f8; font-size: clamp(25px,4vw,35px); font-weight: 700;
    line-height: 1.2; letter-spacing: -.9px; margin: 5px 0 0; padding: 0; }
.sv-intro { color: #aaaab6; font-size: 14px; line-height: 1.65; margin: 0 0 25px; }
.sv-person {
    display: flex; align-items: center; justify-content: space-between; gap: 14px;
    border: 1px solid #29272f; border-radius: 18px; background: #0d0c10;
    padding: 19px 21px; margin: 15px 0 17px;
}
.sv-person h2 { font-size: 22px; line-height: 1.3; letter-spacing: -.4px; margin: 5px 0; padding: 0; }
.sv-person p { color: #acabb8; font-size: 12px; margin: 0; }
.sv-person-status { color: #cbb9ff; background: #21192e; border: 1px solid #39294d;
    border-radius: 20px; font-size: 11px; padding: 6px 10px; white-space: nowrap; }
[data-testid="stForm"] { background: #0d0d10; border-color: #2a2830; border-radius: 18px;
    padding: 22px; margin-top: 10px; }
[data-testid="stTextInput"] input { background: #17171c; color: #f1f0f6; }
[data-testid="stTextInput"] [data-baseweb="input"],
[data-testid="stSelectbox"] [data-baseweb="select"] > div { border-radius: 11px; }
[data-testid="stTextInput"] label, [data-testid="stSelectbox"] label { color: #ddddE7; }
[data-testid="stButton"] button, [data-testid="stDownloadButton"] button,
[data-testid="stFormSubmitButton"] button { min-height: 42px; border-radius: 11px;
    border-color: #34313e; transition: background .15s, border-color .15s; }
button[kind="primary"], button[kind="primaryFormSubmit"] {
    color: #110b1d !important; background: #b29aff !important; border-color: #b29aff !important;
    font-weight: 650 !important;
}
button[kind="primary"]:hover, button[kind="primaryFormSubmit"]:hover { background: #c4b0ff !important; }
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { overflow-wrap: anywhere; }
[data-testid="stMetricValue"] { color: #f7f5ff; }
[data-testid="stCaptionContainer"] { color: #a2a0af; }
[data-testid="stExpander"] { border-radius: 12px; border-color: #302c39; }
[data-testid="stChatMessage"] { background: transparent; border-radius: 17px; padding: 17px 15px; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background: #131216; border: 1px solid #25232c; margin-top: 14px;
}
[data-testid="stChatMessageContent"] { line-height: 1.75; }
[data-testid="stBottom"], [data-testid="stBottomBlockContainer"] { background: #030303; }
[data-testid="stChatInput"] { background: #131216; border: 1px solid #39323f; border-radius: 16px; }
[data-testid="stChatInput"]:focus-within { border-color: #b29aff; }
[data-testid="stChatInput"] textarea { background: transparent; color: #f4f2f8; }
.stMarkdown a { color: #c5b0ff; }
@media (max-width: 640px) {
    [data-testid="stMainBlockContainer"], .main .block-container { padding-top: 1.5rem; padding-left: 1rem; padding-right: 1rem; }
    .sv-person { padding: 15px; align-items: flex-start; }
    .sv-person h2 { font-size: 20px; }
    .sv-person-status { font-size: 10px; padding: 5px 8px; }
    [data-testid="stForm"] { padding: 16px; }
}
</style>
""", unsafe_allow_html=True)


def render_app_header() -> None:
    st.markdown("""
<div class="sv-brand">
  <div class="sv-brand-mark">🎓</div>
  <div><div class="sv-eyebrow">ENTREVISTAS DE REQUISITOS</div><h1>Stakeholder Virtual</h1></div>
</div>
<p class="sv-intro">Investigue a rotina das monitorias e conheça diferentes pontos de vista.</p>
""", unsafe_allow_html=True)


def render_entry(repository: InterviewRepository | None = None) -> None:
    created = st.session_state.get("registration_created")
    if created:
        st.success(f"Grupo cadastrado: {created['group_name']}")
        st.write("Guarde este código e compartilhe com os integrantes do seu grupo para retomar a mesma entrevista.")
        st.code(created["access_code"], language="text")
        st.download_button(
            "Baixar código do grupo",
            data=(f"Grupo: {created['group_name']}\nCódigo: {created['access_code']}\n"),
            file_name=f"acesso_grupo_{created['session_id']}.txt",
            mime="text/plain", use_container_width=True,
        )
        if st.button("Iniciar entrevista", type="primary", use_container_width=True):
            st.session_state["group_access_code"] = created["access_code"]
            st.session_state.pop("registration_created", None)
            st.rerun()
        return

    try:
        settings = registration_settings()
    except (ValueError, TypeError):
        LOGGER.exception("Configuração do cadastro da atividade inválida.")
        settings = None

    register_tab, resume_tab = st.tabs(["Cadastrar grupo", "Retomar entrevista"])
    with register_tab:
        if settings is None:
            st.info("O cadastro de novos grupos está fechado. Peça orientação ao monitor ou use Retomar entrevista.")
        else:
            st.write(f"Atividade: **{settings.activity_name}**")
            st.caption("Cadastre a equipe uma única vez. Os demais integrantes usarão o código gerado para entrar na mesma entrevista.")
            invitation = st.query_params.get("convite", "")
            invited = valid_activity_code(invitation, settings)
            with st.form("register_group_form"):
                name = st.text_input("Nome do grupo", max_chars=80, key="registration_name")
                activity_code = invitation if invited else st.text_input(
                    "Código da atividade", type="password", max_chars=200,
                    key="registration_activity_code",
                    help="Código informado pelo monitor para cadastrar uma equipe.",
                )
                submitted = st.form_submit_button("Cadastrar grupo", type="primary", use_container_width=True)
            if submitted:
                try:
                    # Valida o convite antes de carregar o cenário e sem chamar a IA.
                    if not valid_activity_code(activity_code, settings):
                        raise InvalidActivityCode("Código da atividade inválido. Confira com o monitor.")
                    with st.spinner("Cadastrando seu grupo..."):
                        scenario = load_registration_scenario(SCENARIO_PATH.stat().st_mtime_ns)
                        current_repository = repository if repository is not None else get_repository()
                        registered = register_group(current_repository, scenario, settings, name, activity_code)
                except ValueError as error:
                    st.error(str(error))
                except Exception:
                    LOGGER.exception("Não foi possível concluir o cadastro do grupo.")
                    st.error("Não foi possível concluir o cadastro. Tente novamente em instantes ou procure o monitor.")
                else:
                    st.session_state["registration_created"] = {
                        "session_id": registered.session_id,
                        "group_name": registered.group_name,
                        "access_code": registered.access_code,
                    }
                    st.rerun()

    with resume_tab:
        st.write("Entre com o código do seu grupo para retomar a entrevista.")
        with st.form("group_login"):
            typed_code = st.text_input("Código de acesso do grupo", type="password", max_chars=200)
            submitted = st.form_submit_button("Entrar na entrevista", type="primary", use_container_width=True)
        if submitted:
            try:
                with st.spinner("Conferindo o código e abrindo sua entrevista..."):
                    current_repository = repository if repository is not None else get_repository()
                    interview = current_repository.load(typed_code)
            except InvalidAccessCode:
                st.error("Código inválido. Confira o código recebido pelo grupo.")
            except Exception:
                LOGGER.exception("Falha ao carregar entrevista.")
                st.error("O banco está indisponível no momento. Tente novamente em instantes.")
            else:
                st.session_state["group_access_code"] = typed_code.strip()
                # Reaproveita esta consulta somente no rerun imediatamente após o login.
                st.session_state["entry_interview"] = {"code": typed_code.strip(), "interview": interview}
                st.rerun()
    st.caption("Equipe docente? [Acessar entrevistas dos grupos](?area=docente)")


def logout() -> None:
    for key in ("group_access_code", "selected_stakeholder_id", "pending_save", "save_error", "registration_created", "group_pdf_download", "entry_interview", "chat_history_view"):
        st.session_state.pop(key, None)


def render_turn(turn: dict, scenario: Scenario) -> None:
    person = scenario.stakeholders[turn["stakeholder_id"]]
    with st.chat_message("user", avatar="👤"):
        st.caption(f"Pergunta para {person.name}")
        st.write(turn["question"])
    with st.chat_message("assistant", avatar="🎓"):
        st.caption(person.name)
        st.write(turn["response"])


def save_pending(repository: InterviewRepository, code: str) -> None:
    pending = st.session_state["pending_save"]
    try:
        repository.finish_turn(
            code, pending["request_id"], pending["state"], pending["elapsed_ms"],
            metadata={"interface": "streamlit_supabase", "persistence_version": 1},
        )
    except ExpiredTurn as error:
        st.session_state.pop("pending_save", None)
        st.warning(str(error))
        st.info("Atualize a conversa antes de enviar outra pergunta.")
        st.button("Atualizar conversa", key="reload_expired_response")
        return
    except ValueError:
        LOGGER.exception("O grafo retornou uma interação incompatível com a persistência.")
        try:
            repository.fail_turn(code, pending["request_id"], "InvalidGraphResult")
        except Exception:
            LOGGER.exception("Falha ao liberar uma resposta incompatível.")
        st.session_state.pop("pending_save", None)
        st.error("O formato da resposta não pôde ser salvo. Avise o monitor responsável.")
        st.button("Atualizar conversa", key="reload_invalid_response")
        return
    except Exception:
        LOGGER.exception("Falha ao confirmar uma resposta no banco.")
        st.session_state["save_error"] = True
        st.rerun()
    st.session_state.pop("pending_save", None)
    st.session_state.pop("save_error", None)
    st.rerun()


def main() -> None:
    st.set_page_config(page_title="Stakeholder Virtual", page_icon="🎓", layout="centered")
    apply_interface_style()
    render_app_header()

    if st.query_params.get("area") == "docente":
        from painel_entrevistas import render_teacher_panel
        render_teacher_panel()
        return

    if "group_access_code" not in st.session_state:
        # A apresentação dos formulários não precisa de PostgreSQL, grafo ou LLM.
        render_entry()
        return

    try:
        repository = get_repository()
    except Exception:
        LOGGER.exception("Falha ao iniciar o acesso ao banco.")
        st.error("Não foi possível conectar ao banco. Avise o monitor responsável.")
        st.stop()

    code = st.session_state["group_access_code"]
    if "pending_save" in st.session_state:
        st.warning("Há uma resposta aguardando confirmação de gravação.")
        if st.session_state.get("save_error"):
            st.error("Não foi possível confirmar a gravação. Mantenha esta aba aberta e tente salvar novamente.")
        st.write(st.session_state["pending_save"]["state"].get("current_response", ""))
        if st.button("Tentar salvar a resposta novamente", type="primary"):
            save_pending(repository, code)
        st.caption("Essa tentativa reutiliza a resposta pronta, sem fazer outra chamada à IA.")
        return

    try:
        entry = st.session_state.pop("entry_interview", None)
        if entry and entry["code"] == code:
            interview = entry["interview"]
        else:
            interview = repository.load(code)
        snapshot_json = json.dumps(interview.scenario_snapshot, ensure_ascii=False, sort_keys=True)
        scenario = load_session_scenario(snapshot_json)
    except InvalidAccessCode:
        logout()
        st.rerun()
    except Exception:
        LOGGER.exception("Falha ao preparar cenário ou recuperar entrevista.")
        st.error("Não foi possível abrir a entrevista. Avise o monitor responsável.")
        st.stop()

    state = interview.state
    st.sidebar.caption("SEU GRUPO")
    st.sidebar.header(interview.group_name)
    selector_key = "selected_stakeholder_id"
    if st.session_state.get(selector_key) not in scenario.stakeholders:
        st.session_state[selector_key] = state["stakeholder_id"]
    selected_id = st.sidebar.selectbox(
        "Quem você deseja entrevistar?",
        options=list(scenario.stakeholders),
        format_func=lambda identifier: scenario.stakeholders[identifier].name,
        key=selector_key,
    )
    person = scenario.stakeholders[selected_id]
    mood = person.initial_mood
    for turn in reversed(state["conversation_history"]):
        if turn["stakeholder_id"] == selected_id:
            mood = turn.get("mood", mood)
            break
    st.sidebar.write(f"**Papel:** {person.role}")
    st.sidebar.write(f"**Humor:** {MOOD_LABELS.get(mood, mood)}")
    st.sidebar.metric("Perguntas restantes", state["questions_remaining"])
    st.sidebar.caption(
        "O limite é compartilhado entre os três personagens. "
        "Trocar de personagem ou sair não reinicia a entrevista."
    )
    st.sidebar.progress(state["questions_asked"] / interview.max_questions,
                        text=f"{state['questions_asked']} de {interview.max_questions} perguntas utilizadas")
    st.sidebar.button("Atualizar conversa", use_container_width=True)
    st.sidebar.button("Sair", on_click=logout, use_container_width=True)

    if state["conversation_history"]:
        # ReportLab/fontes/PDF ficam fora da entrada e da troca de personagem.
        pdf_key = (interview.id, interview.revision)
        cached_pdf = st.session_state.get("group_pdf_download")
        if cached_pdf and cached_pdf["key"] != pdf_key:
            st.session_state.pop("group_pdf_download", None)
            cached_pdf = None
        with st.sidebar.expander("Baixar entrevista"):
            if not cached_pdf and st.button("Preparar PDF", key="prepare_group_pdf", use_container_width=True):
                try:
                    with st.spinner("Preparando seu PDF..."):
                        from app.services.interview_pdf import build_interview_pdf, pdf_report, report_filename
                        report = pdf_report(interview)
                        cached_pdf = {"key": pdf_key, "data": build_interview_pdf(report),
                                      "filename": report_filename(report)}
                        st.session_state["group_pdf_download"] = cached_pdf
                except Exception:
                    LOGGER.exception("Falha ao preparar PDF do grupo.")
                    st.error("Não foi possível gerar o PDF. Tente novamente ou avise o monitor.")
            if cached_pdf:
                st.download_button("Baixar entrevista em PDF", data=cached_pdf["data"],
                                   file_name=cached_pdf["filename"], mime="application/pdf",
                                   use_container_width=True)
            st.download_button(
                "Baixar histórico em JSON", data=json.dumps(student_report(interview), ensure_ascii=False, indent=2),
                file_name=f"entrevista_{interview.id}.json", mime="application/json", use_container_width=True,
            )

    st.markdown(
        '<div class="sv-person"><div><div class="sv-eyebrow">CONVERSANDO COM</div>'
        f'<h2>{escape(person.name)}</h2><p>{escape(person.role)}</p></div>'
        f'<span class="sv-person-status">{escape(MOOD_LABELS.get(mood, mood))}</span></div>',
        unsafe_allow_html=True,
    )
    view = st.radio("Visualização da entrevista", ["Conversa atual", "Histórico completo"],
                    horizontal=True, label_visibility="collapsed", key="chat_history_view")
    if view == "Conversa atual":
        with st.chat_message("assistant", avatar="🎓"):
            st.caption(person.name)
            if selected_id == scenario.interview_config.initial_stakeholder_id:
                st.write(scenario.interview_config.greeting)
            else:
                st.write(
                    f"Olá! Sou {person.name}. Pode me perguntar sobre minha participação "
                    "nas monitorias, minhas dificuldades e o que espero do sistema."
                )
        for turn in state["conversation_history"]:
            if turn["stakeholder_id"] == selected_id:
                render_turn(turn, scenario)
    else:
        if not state["conversation_history"]:
            st.info("As perguntas e respostas da entrevista aparecerão aqui.")
        for turn in state["conversation_history"]:
            render_turn(turn, scenario)

    if state["completed"] or state["questions_remaining"] <= 0:
        st.success("Entrevista finalizada. O histórico continua disponível para consulta e download.")
        return
    if interview.busy:
        st.info(
            "Uma pergunta deste grupo está em processamento. "
            "Aguarde e use Atualizar conversa. Se a execução foi interrompida, "
            "a reserva será liberada após cinco minutos."
        )
        return

    question = st.chat_input(f"Faça uma pergunta para {person.name}")
    if not question or not question.strip():
        return
    try:
        ticket = repository.begin_turn(code, interview.revision, selected_id, question)
    except (InterviewBusy, InterviewFinished, StaleInterview, ValueError) as error:
        st.warning(str(error))
        return
    except Exception:
        LOGGER.exception("Falha ao reservar pergunta.")
        st.error("Não foi possível iniciar a pergunta. Atualize a conversa e tente novamente.")
        return

    try:
        with st.spinner(f"{person.name} está respondendo..."):
            _, graph = load_graph(snapshot_json)
            updated_state, elapsed_ms = generate_turn(graph, ticket)
    except Exception as error:
        LOGGER.exception("Falha ao executar pergunta no grafo.")
        try:
            repository.fail_turn(code, ticket.request_id, type(error).__name__)
        except Exception:
            LOGGER.exception("Não foi possível liberar a reserva da pergunta.")
        st.error(
            "Não foi possível obter a resposta. A pergunta não foi descontada do limite. "
            "Atualize a conversa e tente novamente."
        )
        return

    # Retém a resposta enquanto a gravação é confirmada. A conexão com o banco
    # não fica ocupada durante a chamada de IA.
    st.session_state["pending_save"] = {
        "request_id": ticket.request_id,
        "state": updated_state,
        "elapsed_ms": elapsed_ms,
    }
    save_pending(repository, code)


if __name__ == "__main__":
    main()

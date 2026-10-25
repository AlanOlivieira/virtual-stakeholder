from __future__ import annotations

import logging

import streamlit as st

from app.infrastructure.database import get_pool
from app.infrastructure.interview_reports_repository import (
    InterviewReportsRepository, InvalidTeacherAccess, TeacherReportsDisabled,
    authenticate_teacher, require_teacher,
)
from app.services.interview_pdf import (
    build_interview_pdf, build_interviews_zip, display_time, report_filename,
)


LOGGER = logging.getLogger(__name__)


def _logout_teacher() -> None:
    for key in ("teacher_access", "teacher_download"):
        st.session_state.pop(key, None)


def render_teacher_panel() -> None:
    st.subheader("Entrevistas dos grupos")
    st.caption("Área da equipe docente")
    if st.button("Voltar para a entrevista", key="leave_teacher_area"):
        _logout_teacher()
        st.query_params.pop("area", None)
        st.rerun()

    access = st.session_state.get("teacher_access")
    if access is not None:
        try:
            require_teacher(access)
        except (InvalidTeacherAccess, TeacherReportsDisabled):
            _logout_teacher()
            access = None
    if access is None:
        with st.form("teacher_login"):
            password = st.text_input("Senha da área docente", type="password", max_chars=300)
            submitted = st.form_submit_button("Entrar na área docente", use_container_width=True)
        if submitted:
            try:
                st.session_state["teacher_access"] = authenticate_teacher(password)
            except (InvalidTeacherAccess, TeacherReportsDisabled) as error:
                st.error(str(error))
            else:
                st.rerun()
        return

    st.sidebar.button("Sair da área docente", on_click=_logout_teacher, use_container_width=True)
    st.sidebar.caption("Os PDFs usam as conversas salvas. Gerar ou baixar arquivos não faz chamadas à IA.")
    try:
        repository = InterviewReportsRepository(get_pool())
        groups = repository.list_groups(access)
    except Exception:
        LOGGER.exception("Falha ao consultar entrevistas para o painel.")
        st.error("Não foi possível carregar a lista de grupos. Tente novamente em instantes.")
        return

    st.button("Atualizar lista", use_container_width=True)
    if not groups:
        st.info("Ainda não há grupos cadastrados nesta base.")
        return
    activities = sorted({row["group_name"].split(" / ", 1)[0] for row in groups if " / " in row["group_name"]})
    activity = st.selectbox("Atividade", ["Todas as atividades"] + activities, key="teacher_activity")
    search = st.text_input("Buscar grupo", max_chars=120, key="teacher_group_search")
    groups = [row for row in groups if
              (activity == "Todas as atividades" or row["group_name"].startswith(activity + " / "))
              and search.casefold() in row["group_name"].casefold()]
    st.caption(f"{len(groups)} grupo(s) encontrado(s). Horários de Fortaleza.")
    if not groups:
        st.info("Nenhum grupo corresponde aos filtros.")
        return
    st.dataframe([
        {"Grupo": row["group_name"], "Perguntas salvas": f"{row['questions_asked']} / {row['max_questions']}",
         "Situação": "Finalizada" if row["questions_asked"] >= row["max_questions"] else "Em andamento",
         "Última atualização": display_time(row["updated_at"])}
        for row in groups
    ], hide_index=True, use_container_width=True)

    by_id = {row["id"]: row for row in groups}
    if st.session_state.get("teacher_selected_group") not in by_id:
        st.session_state["teacher_selected_group"] = next(iter(by_id))
    selected = st.selectbox("Grupo para download individual", list(by_id),
                            format_func=lambda key: by_id[key]["group_name"], key="teacher_selected_group")
    individual, all_groups = st.columns(2)
    with individual:
        prepare_pdf = st.button("Preparar PDF do grupo", use_container_width=True)
    with all_groups:
        prepare_zip = st.button("Preparar ZIP dos grupos", disabled=len(groups) > 100, use_container_width=True)
    st.caption("O ZIP reúne um PDF por grupo encontrado nos filtros. As entrevistas podem estar em andamento.")
    if prepare_pdf or prepare_zip:
        st.session_state.pop("teacher_download", None)
        try:
            ids = [selected] if prepare_pdf else list(by_id)
            with st.spinner("Preparando os arquivos..."):
                reports = repository.fetch_reports(access, ids)
                if prepare_pdf:
                    content = build_interview_pdf(reports[0])
                    filename, mime = report_filename(reports[0]), "application/pdf"
                else:
                    content = build_interviews_zip(reports)
                    filename, mime = "entrevistas_dos_grupos.zip", "application/zip"
            st.session_state["teacher_download"] = {
                "data": content, "filename": filename, "mime": mime,
                "groups": [row["group_name"] for row in reports],
            }
        except Exception:
            LOGGER.exception("Falha ao gerar arquivo de entrevistas.")
            st.error("Não foi possível gerar o arquivo. Atualize a lista e tente novamente.")
    ready = st.session_state.get("teacher_download")
    if ready:
        st.success("Arquivo preparado: " + ", ".join(ready["groups"]))
        st.download_button("Baixar arquivo preparado", data=ready["data"], file_name=ready["filename"],
                           mime=ready["mime"], use_container_width=True)
        st.caption("O arquivo contém os dados salvos no momento da preparação. Prepare novamente após novas perguntas.")

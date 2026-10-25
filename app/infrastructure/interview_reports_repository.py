from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from dotenv import load_dotenv

from app.services.interview_pdf import pdf_report


class TeacherReportsDisabled(ValueError):
    pass


class InvalidTeacherAccess(ValueError):
    pass


@dataclass(frozen=True)
class TeacherAccess:
    fingerprint: str = field(repr=False)


def _expected_fingerprint() -> str:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    password = os.getenv("TEACHER_REPORT_PASSWORD", "")
    if len(password) < 16:
        raise TeacherReportsDisabled("Configure TEACHER_REPORT_PASSWORD com pelo menos 16 caracteres no servidor.")
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def authenticate_teacher(password: str) -> TeacherAccess:
    expected = _expected_fingerprint()
    supplied = hashlib.sha256(password.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(expected, supplied):
        raise InvalidTeacherAccess("Senha da área docente inválida.")
    return TeacherAccess(supplied)


def require_teacher(access: TeacherAccess) -> None:
    expected = _expected_fingerprint()
    if not isinstance(access, TeacherAccess) or not hmac.compare_digest(expected, access.fingerprint):
        raise InvalidTeacherAccess("Entre novamente na área docente.")


class InterviewReportsRepository:
    """Consultas de leitura para o painel. Exigem acesso docente em cada operação."""

    def __init__(self, pool):
        self.pool = pool

    def list_groups(self, access: TeacherAccess) -> list[dict]:
        require_teacher(access)
        with self.pool.connection() as conn:
            rows = conn.execute(
                """select id, group_name, questions_asked, max_questions, revision,
                          created_at, updated_at, completed_at
                   from bot_private.interview_sessions
                   order by lower(group_name), id"""
            ).fetchall()
        return [{**row, "id": str(row["id"])} for row in rows]

    def fetch_reports(self, access: TeacherAccess, session_ids: list[str]) -> list[dict]:
        require_teacher(access)
        if not session_ids or len(session_ids) > 100:
            raise ValueError("Selecione entre 1 e 100 grupos por download.")
        identifiers = [UUID(value) for value in dict.fromkeys(session_ids)]
        with self.pool.connection() as conn, conn.transaction():
            conn.execute("set transaction isolation level repeatable read, read only")
            rows = conn.execute(
                """select id, group_name, state, scenario_snapshot, max_questions,
                          created_at, updated_at, revision
                   from bot_private.interview_sessions
                   where id=any(%s::uuid[]) order by lower(group_name), id""", (identifiers,),
            ).fetchall()
        if len(rows) != len(identifiers):
            raise ValueError("Um dos grupos não está mais disponível. Atualize a lista.")
        reports = []
        for row in rows:
            # A projeção elimina os fatos secretos antes de qualquer uso pela interface.
            interview = SimpleNamespace(**row)
            interview.id = str(interview.id)
            report = pdf_report(interview)
            report.update(created_at=row["created_at"].isoformat(),
                          updated_at=row["updated_at"].isoformat(), revision=row["revision"])
            reports.append(report)
        return reports

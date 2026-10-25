from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import secrets
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool


class InvalidAccessCode(ValueError):
    pass


class DuplicateGroupName(ValueError):
    pass


class GroupLimitReached(ValueError):
    pass


class InterviewBusy(RuntimeError):
    pass


class InterviewFinished(RuntimeError):
    pass


class StaleInterview(RuntimeError):
    pass


class ExpiredTurn(RuntimeError):
    pass


@dataclass(frozen=True)
class SavedInterview:
    id: str
    group_name: str
    scenario_snapshot: dict[str, Any]
    state: dict[str, Any]
    revision: int
    max_questions: int
    busy: bool


@dataclass(frozen=True)
class TurnTicket:
    request_id: str
    interview: SavedInterview
    question: str
    stakeholder_id: str


def _code_hash(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _as_saved(row: dict[str, Any]) -> SavedInterview:
    return SavedInterview(
        id=str(row["id"]),
        group_name=row["group_name"],
        scenario_snapshot=row["scenario_snapshot"],
        state=row["state"],
        revision=row["revision"],
        max_questions=row["max_questions"],
        busy=bool(row["busy"]),
    )


class InterviewRepository:
    """Persistência do backend. Nenhum método recebe apenas o ID público da sessão."""

    def __init__(self, pool: ConnectionPool):
        self.pool = pool

    def _select(self, conn, code: str, *, lock: bool = False):
        if not code.strip() or len(code.strip()) > 200:
            raise InvalidAccessCode("Código de acesso inválido.")
        suffix = " FOR UPDATE" if lock else ""
        row = conn.execute(
            """select *,
                   coalesce(pending_since > clock_timestamp() - interval '5 minutes', false)
                       as busy
               from bot_private.interview_sessions
               where access_code_hash = %s""" + suffix,
            (_code_hash(code),),
        ).fetchone()
        if row is None:
            raise InvalidAccessCode("Código de acesso inválido.")
        return row

    def create_group(self, group_name: str, scenario_snapshot: dict,
                     initial_state: dict, *, activity_prefix: str | None = None,
                     maximum_groups: int | None = None) -> str:
        """Criação pelo backend: script docente ou cadastro da atividade autorizado."""
        group_name = " ".join(group_name.split())
        if not 1 <= len(group_name) <= 120:
            raise ValueError("Nome do grupo deve ter entre 1 e 120 caracteres.")
        if (activity_prefix is None) != (maximum_groups is None):
            raise ValueError("Informe o prefixo e o limite da atividade juntos.")
        if maximum_groups is not None:
            if not 1 <= maximum_groups <= 100 or not group_name.startswith(activity_prefix):
                raise ValueError("Configuração inválida para o cadastro da atividade.")
        snapshot = _json_copy(scenario_snapshot)
        state = _json_copy(initial_state)
        maximum = int(snapshot["interview_config"]["max_questions"])
        if (state["scenario_id"] != snapshot["id"]
                or state["questions_asked"] != 0
                or state["questions_remaining"] != maximum
                or state["conversation_history"] or state["completed"]):
            raise ValueError("A criação do grupo exige um estado inicial vazio.")
        session_id = UUID(state["session_id"])
        canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"))
        code = secrets.token_urlsafe(18)
        with self.pool.connection() as conn, conn.transaction():
            # Serializa somente os cadastros, inclusive entre processos.
            # O bloqueio termina com a transação; não envolve chamadas de IA.
            conn.execute("select pg_advisory_xact_lock(%s)", (75291134008001,))
            exists = conn.execute(
                """select 1 from bot_private.interview_sessions
                   where lower(group_name)=lower(%s)""", (group_name,),
            ).fetchone()
            if exists:
                raise DuplicateGroupName(
                    "Já existe um grupo com esse nome nesta atividade. "
                    "Use o código do grupo na opção Retomar entrevista."
                )
            if maximum_groups is not None:
                count = conn.execute(
                    """select count(*) as total from bot_private.interview_sessions
                       where left(group_name,%s)=%s""",
                    (len(activity_prefix), activity_prefix),
                ).fetchone()["total"]
                if count >= maximum_groups:
                    raise GroupLimitReached(
                        "O limite de grupos desta atividade foi atingido. Procure o monitor."
                    )
            conn.execute(
                """insert into bot_private.interview_sessions
                   (id, group_name, access_code_hash, scenario_id, scenario_version,
                    scenario_hash, scenario_snapshot, state, max_questions)
                   values (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (session_id, group_name, _code_hash(code), snapshot["id"],
                 int(snapshot["version"]), hashlib.sha256(canonical.encode()).hexdigest(),
                 Jsonb(snapshot), Jsonb(state), maximum),
            )
        return code

    def load(self, code: str) -> SavedInterview:
        with self.pool.connection() as conn:
            return _as_saved(self._select(conn, code))

    def begin_turn(self, code: str, expected_revision: int,
                   stakeholder_id: str, question: str) -> TurnTicket:
        question = question.strip()
        if not 1 <= len(question) <= 4000:
            raise ValueError("A pergunta deve ter entre 1 e 4000 caracteres.")
        with self.pool.connection() as conn, conn.transaction():
            row = self._select(conn, code, lock=True)
            if row["revision"] != expected_revision:
                raise StaleInterview("A entrevista foi atualizada em outra aba. Atualize a conversa.")
            if row["questions_asked"] >= row["max_questions"]:
                raise InterviewFinished("Todas as perguntas deste grupo foram utilizadas.")
            if row["busy"]:
                raise InterviewBusy("O grupo já tem uma pergunta em processamento.")
            if stakeholder_id not in row["scenario_snapshot"]["stakeholders"]:
                raise ValueError("Personagem não pertence ao cenário desta entrevista.")

            # Recupera automaticamente uma reserva abandonada após cinco minutos.
            if row["pending_request_id"]:
                conn.execute(
                    """update bot_private.interview_requests
                       set status='expired', finished_at=now()
                       where id=%s and session_id=%s and status='pending'""",
                    (row["pending_request_id"], row["id"]),
                )
            request_id = uuid4()
            conn.execute(
                """insert into bot_private.interview_requests
                   (id,session_id,question_number,stakeholder_id,question,status)
                   values (%s,%s,%s,%s,%s,'pending')""",
                (request_id, row["id"], row["questions_asked"] + 1,
                 stakeholder_id, question),
            )
            conn.execute(
                """update bot_private.interview_sessions
                   set pending_request_id=%s, pending_since=clock_timestamp(), updated_at=now()
                   where id=%s""",
                (request_id, row["id"]),
            )
            return TurnTicket(str(request_id), _as_saved(row), question, stakeholder_id)

    def fail_turn(self, code: str, request_id: str, error_type: str) -> None:
        with self.pool.connection() as conn, conn.transaction():
            row = self._select(conn, code, lock=True)
            if str(row["pending_request_id"]) != request_id:
                return
            conn.execute(
                """update bot_private.interview_requests
                   set status='failed', finished_at=now(), error_type=%s
                   where id=%s and session_id=%s and status='pending'""",
                (error_type[:100], UUID(request_id), row["id"]),
            )
            conn.execute(
                """update bot_private.interview_sessions
                   set pending_request_id=null, pending_since=null, updated_at=now()
                   where id=%s""", (row["id"],),
            )

    def finish_turn(self, code: str, request_id: str, updated_state: dict,
                    elapsed_ms: int, metadata: dict | None = None) -> SavedInterview:
        """Confirma fala, histórico e contador na mesma transação; repetir é seguro."""
        with self.pool.connection() as conn, conn.transaction():
            row = self._select(conn, code, lock=True)
            request = conn.execute(
                """select * from bot_private.interview_requests
                   where id=%s and session_id=%s""",
                (UUID(request_id), row["id"]),
            ).fetchone()
            if request is None:
                raise ExpiredTurn("Solicitação não pertence a esta entrevista.")
            if request["status"] == "succeeded":
                return _as_saved(row)
            if (request["status"] != "pending"
                    or row["pending_request_id"] != UUID(request_id)):
                raise ExpiredTurn("Esta resposta foi substituída por uma solicitação mais recente.")

            state = _json_copy(updated_state)
            before = row["state"]
            history = state.get("conversation_history", [])
            old_history = before["conversation_history"]
            if state.get("error"):
                raise ValueError("O grafo retornou um erro.")
            if (state.get("session_id") != str(row["id"])
                    or state.get("scenario_id") != row["scenario_id"]):
                raise ValueError("O grafo retornou outra sessão ou cenário.")
            if len(history) != len(old_history) + 1 or history[:-1] != old_history:
                raise ValueError("O grafo deve acrescentar exatamente uma interação ao histórico.")
            turn = history[-1]
            response = state.get("current_response", "").strip()
            if (not response or turn.get("response") != state.get("current_response")
                    or turn.get("question") != request["question"]
                    or turn.get("stakeholder_id") != request["stakeholder_id"]
                    or state.get("stakeholder_id") != request["stakeholder_id"]):
                raise ValueError("A resposta do grafo não corresponde à pergunta reservada.")

            # O contador persistido é a referência, mesmo se o grafo o calcular novamente.
            asked = row["questions_asked"] + 1
            state["questions_asked"] = asked
            state["questions_remaining"] = row["max_questions"] - asked
            state["completed"] = asked == row["max_questions"]
            facts = turn.get("allowed_facts") or state.get("allowed_facts") or []
            if not facts and state.get("allowed_fact"):
                facts = [state["allowed_fact"]]

            conn.execute(
                """update bot_private.interview_requests
                   set status='succeeded', response=%s, analysis=%s, selected_facts=%s,
                       mood=%s, elapsed_ms=%s, metadata=%s, finished_at=now()
                   where id=%s and session_id=%s""",
                (state["current_response"], Jsonb(turn.get("analysis") or state.get("question_analysis")),
                 Jsonb(facts), state.get("mood"), max(0, int(elapsed_ms)),
                 Jsonb(_json_copy(metadata or {})), UUID(request_id), row["id"]),
            )
            conn.execute(
                """update bot_private.interview_sessions
                   set state=%s, questions_asked=%s, revision=revision+1,
                       pending_request_id=null, pending_since=null, updated_at=now(),
                       completed_at=case when %s then now() else completed_at end
                   where id=%s""",
                (Jsonb(state), asked, state["completed"], row["id"]),
            )
            return _as_saved(self._select(conn, code))

    def export_for_teacher(self, group_name: str | None = None) -> list[dict]:
        """Somente para o script local administrativo; inclui informações internas."""
        query = """select id,group_name,scenario_id,scenario_version,scenario_hash,
                          scenario_snapshot,state,questions_asked,max_questions,
                          created_at,updated_at,completed_at
                   from bot_private.interview_sessions"""
        params: tuple = ()
        if group_name:
            query += " where group_name=%s"
            params = (group_name,)
        query += " order by group_name"
        with self.pool.connection() as conn, conn.transaction():
            conn.execute("set transaction isolation level repeatable read, read only")
            groups = conn.execute(query, params).fetchall()
            for group in groups:
                group["requests"] = conn.execute(
                    """select id,question_number,stakeholder_id,question,status,response,
                              analysis,selected_facts,mood,elapsed_ms,error_type,metadata,
                              started_at,finished_at
                       from bot_private.interview_requests where session_id=%s
                       order by started_at,id""", (group["id"],),
                ).fetchall()
        return groups

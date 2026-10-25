from __future__ import annotations

import re
import unicodedata
from time import perf_counter
from collections import Counter
from collections.abc import Callable, Mapping

from app.domain.interview_state import AllowedFact, InterviewState
from app.domain.scenario import Scenario
from app.domain.conversation_context import interpreted_question, record_timing


MAX_FACTS_PER_RESPONSE = 3
LEVELS = ("none", "hint", "partial", "explicit")

TOPIC_PRIORITY = (
    "activities",
    "scheduling",
    "scores",
    "rooms",
    "session_choice",
    "learning_materials",
    "activity_sessions",
    "booking_details",
    "attendance",
    "score_validation",
    "feedback",
    "reports",
    "capacity",
    "cancellation",
    "notifications",
    "privacy",
    "accessibility",
    "authentication",
    "academic_context",
    "performance",
    "waiting_list",
)

TOPIC_FAMILIES = {
    "activities": "activities",
    "activity_sessions": "activities",
    "session_choice": "registration",
    "scores": "results",
    "score_validation": "results",
    "rooms": "spaces",
    "academic_context": "access",
    "scheduling": "agenda",
    "booking_details": "agenda",
    "capacity": "agenda",
    "cancellation": "agenda",
    "notifications": "agenda",
    "waiting_list": "agenda",
    "learning_materials": "learning",
    "feedback": "learning",
    "attendance": "supervision",
    "reports": "supervision",
    "privacy": "access",
    "authentication": "access",
    "accessibility": "quality",
    "performance": "quality",
}

TOPIC_WORDS = {
    "activities": r"\b(?:atividades?|testes?|provas?|exercicios?)\b",
    "activity_sessions": r"\b(?:aplicacoes|aplicacao|grupos?|dias? diferentes)\b",
    "session_choice": (
        r"\b(?:enquetes?|votos?|votar|escolha|escolher|inscricoes|inscricao)\b"
    ),
    "scores": r"\b(?:notas?|pontos?|pontuacao|pontuacoes|resultados?)\b",
    "score_validation": r"\b(?:validacao|validar|conferencia|conferir|devolucao)\b",
    "rooms": r"\b(?:salas?|mesas?|posicoes|posicao|alocacoes|alocacao)\b",
    "academic_context": r"\b(?:disciplinas?|vinculos?|periodos?|semestres?)\b",
    "scheduling": r"\b(?:horarios?|agendamentos?|agenda)\b",
    "booking_details": r"\b(?:assuntos?|duvidas?|observacoes)\b",
    "capacity": r"\b(?:vagas?|capacidade|limite|lotacao)\b",
    "waiting_list": r"\b(?:lista de espera|fila de espera)\b",
    "cancellation": r"\b(?:cancelar|cancelamentos?|desistencias?)\b",
    "notifications": r"\b(?:notificacoes|notificacao|avisos?|notificar)\b",
    "learning_materials": r"\b(?:materiais|material|arquivos?|links?|exercicios?)\b",
    "feedback": r"\b(?:feedback|satisfacao|qualidade do atendimento|opiniao)\b",
    "attendance": r"\b(?:presencas?|faltas?|comparecimento)\b",
    "reports": r"\b(?:relatorios?|indicadores?)\b",
    "authentication": r"\b(?:autenticacao|login|senha|entrar no sistema)\b",
    "privacy": r"\b(?:privacidade|dados pessoais|quem pode ver)\b",
    "performance": r"\b(?:desempenho|lentidao|tempo de resposta)\b",
    "accessibility": r"\b(?:acessibilidade|leitor de tela|teclado|celular)\b",
}

BROAD_REQUEST = re.compile(
    r"\b(?:o que mais|que mais|alem disso)\b"
    r"|\b(?:outr[oa]s?|mais) (?:funcoes|funcionalidades|necessidades|problemas|gargalos)\b"
    r"|\bquais (?:as |os )?(?:principais )?(?:funcoes|funcionalidades|problemas|gargalos)\b"
    r"|\bo que (?:o |esse |este )?sistema (?:deve|deveria|poderia|precisa)\b"
)

EXCLUDED_SUBJECT = re.compile(
    r"\b(?:alem (?:de|do|da|dos|das)|fora (?:de|do|da|dos|das)|"
    r"sem falar (?:de|do|da|dos|das)|sem voltar (?:a|ao|aos)|exceto)"
    r"\s+([^,;?.!]+?)(?=[,;?.!]|\s+(?:o que|quais|mas|quero|gostaria|poderia|explique|fale)\b|$)"
)


def create_select_facts_node(
    scenario: Scenario,
) -> Callable[[InterviewState], dict[str, object]]:
    def select_facts(state: InterviewState) -> dict[str, object]:
        started = perf_counter()
        analysis = state["question_analysis"]

        if analysis is None:
            raise ValueError("A pergunta ainda não foi analisada.")

        def empty_result() -> dict[str, object]:
            return {
                "allowed_fact": None,
                "allowed_facts": [],
                "unlocked_facts": list(state["unlocked_facts"]),
                "error": None,
                "question_analysis": record_timing(
                    analysis, "fact_selection_ms", round((perf_counter() - started) * 1000)
                ),
            }

        if (analysis["is_prompt_injection"] or analysis["relevance"] == "irrelevant"
                or analysis.get("needs_clarification")):
            return empty_result()

        stakeholder_id = state["stakeholder_id"]
        if stakeholder_id not in scenario.stakeholders:
            raise ValueError(f"Stakeholder inexistente: {stakeholder_id}")

        stakeholder = scenario.stakeholders[stakeholder_id]
        knowledge = stakeholder.knowledge
        topic = analysis["topic"]
        question = normalize_text(interpreted_question(state))
        progress = state["topic_progress"].get(stakeholder_id, {})
        broad = is_broad_request(question, topic)

        if broad:
            topics = choose_exploration_topics(state, knowledge, question, topic)
        else:
            topics = [topic] if topic in knowledge else []

        if not topics:
            return empty_result()

        facts: list[AllowedFact] = []
        for selected_topic in topics:
            level = progress.get(selected_topic, "none")

            if broad:
                # Exploration shares needs and context, without exposing detailed rules.
                asks_for_functions = re.search(
                    r"\b(?:funcoes|funcionalidades|necessidades|oferecer|"
                    r"precisa|precisaria|gostaria|sugere|requisitos)\b",
                    question,
                )
                level = "partial" if asks_for_functions or level in {"partial", "explicit"} else "hint"

            if level not in LEVELS[1:]:
                continue

            entry = knowledge[selected_topic]
            contents: list[str] = []
            normalized_contents: set[str] = set()
            for permitted_level in LEVELS[1:LEVELS.index(level) + 1]:
                content = getattr(entry.levels, permitted_level)
                if not isinstance(content, str) or not content.strip():
                    continue
                normalized = normalize_text(content)
                if normalized not in normalized_contents:
                    contents.append(content.strip())
                    normalized_contents.add(normalized)

            if not contents:
                continue

            fact: AllowedFact = {
                "fact_id": entry.fact_id,
                "topic": selected_topic,
                "disclosure_level": level,
                "content": "\n\n".join(contents),
                "fact_type": entry.type,
                "authority": entry.authority,
            }
            facts.append(fact)

        if not facts:
            return empty_result()

        primary = facts[0]
        unlocked_facts = list(state["unlocked_facts"])
        if primary["disclosure_level"] == "explicit" and primary["fact_id"] not in unlocked_facts:
            unlocked_facts.append(primary["fact_id"])

        updated_progress = {
            owner: dict(owner_progress)
            for owner, owner_progress in state["topic_progress"].items()
        }
        stakeholder_progress = updated_progress.setdefault(stakeholder_id, {})
        old_level = stakeholder_progress.get(primary["topic"], "none")
        if old_level not in LEVELS:
            old_level = "none"
        if LEVELS.index(primary["disclosure_level"]) > LEVELS.index(old_level):
            stakeholder_progress[primary["topic"]] = primary["disclosure_level"]

        return {
            "allowed_fact": primary,
            "allowed_facts": facts,
            "unlocked_facts": unlocked_facts,
            "topic_progress": updated_progress,
            "error": None,
            "question_analysis": record_timing(
                analysis, "fact_selection_ms", round((perf_counter() - started) * 1000)
            ),
        }

    return select_facts


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return " ".join(
        "".join(char for char in normalized if not unicodedata.combining(char)).split()
    )


def is_broad_request(question: str, topic: str | None) -> bool:
    if topic == "overview":
        return True

    if not BROAD_REQUEST.search(question):
        return False

    active_question = EXCLUDED_SUBJECT.sub(" ", question)
    if topic in TOPIC_WORDS and re.search(TOPIC_WORDS[topic], active_question):
        return False

    return True


def choose_exploration_topics(
    state: InterviewState,
    knowledge: Mapping[str, object],
    question: str,
    suggested_topic: str | None,
) -> list[str]:
    excluded: set[str] = set()
    for match in EXCLUDED_SUBJECT.finditer(question):
        for topic, pattern in TOPIC_WORDS.items():
            if re.search(pattern, match.group(1)):
                excluded.add(topic)

    if "scheduling" in excluded:
        excluded.update(topic for topic, family in TOPIC_FAMILIES.items() if family == "agenda")
    if "scores" in excluded:
        excluded.update(topic for topic, family in TOPIC_FAMILIES.items() if family == "results")

    candidates = [topic for topic in knowledge if topic != "overview" and topic not in excluded]
    if not candidates:
        return ["overview"] if "overview" in knowledge and not excluded else []

    counts = previous_exposure(state, knowledge)
    priority = [topic for topic in TOPIC_PRIORITY if topic in candidates]
    priority.extend(topic for topic in candidates if topic not in priority)
    if suggested_topic in priority:
        priority.remove(suggested_topic)
        priority.insert(0, suggested_topic)

    selected: list[str] = []
    families: set[str] = set()
    while candidates and len(selected) < MAX_FACTS_PER_RESPONSE:
        best = min(
            candidates,
            key=lambda candidate: (
                counts[candidate] > 0,
                TOPIC_FAMILIES.get(candidate, candidate) in families,
                counts[candidate],
                priority.index(candidate),
            ),
        )
        selected.append(best)
        families.add(TOPIC_FAMILIES.get(best, best))
        candidates.remove(best)

    return selected


def previous_exposure(
    state: InterviewState,
    knowledge: Mapping[str, object],
) -> Counter[str]:
    stakeholder_id = state["stakeholder_id"]
    counts: Counter[str] = Counter()
    fact_topics = {getattr(entry, "fact_id"): topic for topic, entry in knowledge.items()}

    for turn in state["conversation_history"]:
        if not isinstance(turn, Mapping) or turn.get("error"):
            continue
        owner = turn.get("stakeholder_id")
        if owner is not None and owner != stakeholder_id:
            continue

        turn_topics: set[str] = set()
        sources = turn.get("allowed_facts", [])
        if not isinstance(sources, list):
            sources = []
        primary = turn.get("allowed_fact")
        if isinstance(primary, Mapping):
            sources = [*sources, primary]
        for source in sources:
            if isinstance(source, Mapping) and source.get("fact_id") in fact_topics:
                turn_topics.add(fact_topics[source["fact_id"]])

        if not turn_topics and owner == stakeholder_id:
            previous_analysis = turn.get("analysis")
            if isinstance(previous_analysis, Mapping) and previous_analysis.get("topic") in knowledge:
                turn_topics.add(previous_analysis["topic"])
        counts.update(turn_topics)

    # Progress and supplied context guide variety; they do not prove what the LLM said.
    progress = state["topic_progress"].get(stakeholder_id, {})
    for topic, level in progress.items():
        if topic in knowledge and level in LEVELS[1:]:
            counts[topic] = max(counts[topic], 1)

    previous_facts = state.get("allowed_facts", [])
    if not isinstance(previous_facts, list):
        previous_facts = []
    previous_primary = state.get("allowed_fact")
    if isinstance(previous_primary, Mapping):
        previous_facts = [*previous_facts, previous_primary]
    for source in previous_facts:
        if isinstance(source, Mapping) and source.get("fact_id") in fact_topics:
            topic = fact_topics[source["fact_id"]]
            counts[topic] = max(counts[topic], 1)

    return counts

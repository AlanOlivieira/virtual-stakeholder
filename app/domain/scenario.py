from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Mood = Literal[
    "neutral",
    "collaborative",
    "impatient",
    "irritated"
]

DisclosureLevel = Literal[
    "none",
    "hint",
    "partial",
    "explicit"
]

FactType = Literal[
    "need",
    "business_rule",
    "preference",
    "constraint",
    "problem"
]

Authority = Literal[
    "stakeholder_experience",
    "official_rule",
    "stakeholder_preference"
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Personality(StrictModel):
    tone: str
    traits: list[str] = Field(min_length=1)
    response_style: str


class KnowledgeLevels(StrictModel):
    hint: str
    partial: str
    explicit: str


class TopicKnowledge(StrictModel):
    fact_id: str
    type: FactType
    authority: Authority
    levels: KnowledgeLevels


class Stakeholder(StrictModel):
    name: str
    role: str
    profile: str
    personality: Personality
    initial_mood: Mood
    unknown_response: str
    knowledge: dict[str, TopicKnowledge] = Field(min_length=1)


class Topic(StrictModel):
    label: str
    description: str


class InterviewConfig(StrictModel):
    max_questions: int = Field(gt=0)
    initial_stakeholder_id: str
    initial_mood: Mood
    disclosure_levels: list[DisclosureLevel]
    greeting: str


class Scenario(StrictModel):
    id: str
    title: str
    version: int = Field(ge=1)
    description: str
    interview_config: InterviewConfig
    topics: dict[str, Topic] = Field(min_length=1)
    stakeholders: dict[str, Stakeholder] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references(self) -> Scenario:
        stakeholder_id = self.interview_config.initial_stakeholder_id

        if stakeholder_id not in self.stakeholders:
            raise ValueError(
                f"O stakeholder inicial '{stakeholder_id}' não existe."
            )

        expected_levels = ["none", "hint", "partial", "explicit"]

        if self.interview_config.disclosure_levels != expected_levels:
            raise ValueError(
                "Os níveis de revelação devem seguir esta ordem: "
                "none, hint, partial, explicit."
            )

        valid_topics = set(self.topics)

        for current_id, stakeholder in self.stakeholders.items():
            unknown_topics = set(stakeholder.knowledge) - valid_topics

            if unknown_topics:
                raise ValueError(
                    f"O stakeholder '{current_id}' possui tópicos "
                    f"não cadastrados: {sorted(unknown_topics)}."
                )

        return self


def load_scenario(path: str | Path) -> Scenario:
    scenario_path = Path(path)

    if not scenario_path.exists():
        raise FileNotFoundError(
            f"Arquivo de cenário não encontrado: {scenario_path}"
        )

    try:
        content = scenario_path.read_text(encoding="utf-8")
        data = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"O arquivo contém um JSON inválido: {error}"
        ) from error

    return Scenario.model_validate(data)
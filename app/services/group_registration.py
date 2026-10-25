from __future__ import annotations

from dataclasses import dataclass, field
import hmac
import os
import unicodedata


@dataclass(frozen=True)
class RegistrationSettings:
    activity_name: str
    activity_code: str = field(repr=False)
    maximum_groups: int = 10

    @property
    def prefix(self) -> str:
        return self.activity_name + " / "


@dataclass(frozen=True)
class RegisteredGroup:
    session_id: str
    group_name: str
    access_code: str = field(repr=False)


class InvalidActivityCode(ValueError):
    pass


def clean_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def registration_settings() -> RegistrationSettings | None:
    # database.get_pool já carrega o .env antes de a tela chamar esta função.
    code = os.getenv("ACTIVITY_REGISTRATION_CODE", "").strip()
    if not code:
        return None
    activity = clean_name(os.getenv("ACTIVITY_NAME", "Monitoria"))
    limit = int(os.getenv("MAX_REGISTRATION_GROUPS", "10"))
    if not 1 <= len(activity) <= 36 or not 1 <= len(code) <= 200 or not 1 <= limit <= 100:
        raise ValueError("Configuração de cadastro da atividade inválida.")
    return RegistrationSettings(activity, code, limit)


def valid_activity_code(provided: str, settings: RegistrationSettings) -> bool:
    return hmac.compare_digest(
        provided.strip().encode("utf-8"), settings.activity_code.encode("utf-8")
    )


def register_group(repository, scenario, settings: RegistrationSettings,
                   group_name: str, activity_code: str) -> RegisteredGroup:
    if not valid_activity_code(activity_code, settings):
        raise InvalidActivityCode("Código da atividade inválido. Confira com o monitor.")
    name = clean_name(group_name)
    if not 1 <= len(name) <= 80:
        raise ValueError("Informe um nome de grupo com até 80 caracteres.")

    from app.domain.interview_state import create_initial_state

    full_name = settings.prefix + name
    state = create_initial_state(scenario)
    code = repository.create_group(
        full_name, scenario.model_dump(mode="json"), state,
        activity_prefix=settings.prefix, maximum_groups=settings.maximum_groups,
    )
    return RegisteredGroup(state["session_id"], full_name, code)

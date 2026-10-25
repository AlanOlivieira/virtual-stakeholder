from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI


# Este arquivo deve ficar em app/infrastructure/llm.py.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"

# Preserva variáveis já configuradas no ambiente de execução.
load_dotenv(ENV_PATH, override=False)

MODEL_NAME = (
    os.getenv("GEMINI_MODEL", "").strip()
    or "gemini-3.1-flash-lite"
)

# O Google recomenda temperatura 1.0 para os modelos Gemini 3.
# A classificação continua usando o schema no nó analyze_question.
TEMPERATURE = 1.0

# São tetos de geração, não tamanhos obrigatórios das respostas.
# Deixamos margem para tokens de raciocínio, quando utilizados.
ANALYZER_MAX_TOKENS = 2048
STAKEHOLDER_MAX_TOKENS = 4096

# Tempo limite por tentativa; as retentativas podem ampliar o total.
REQUEST_TIMEOUT_SECONDS = 60.0
MAX_RETRIES = 2


def validate_api_key() -> None:
    if not os.getenv("GOOGLE_API_KEY", "").strip():
        raise RuntimeError(
            "Configure GOOGLE_API_KEY no arquivo .env "
            "da raiz do projeto ou no ambiente de execução."
        )


@lru_cache(maxsize=1)
def get_analyzer_llm() -> ChatGoogleGenerativeAI:
    """Reutiliza o cliente que classifica as perguntas do estudante."""
    validate_api_key()

    return ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        temperature=TEMPERATURE,
        max_tokens=ANALYZER_MAX_TOKENS,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=MAX_RETRIES,
    )


@lru_cache(maxsize=1)
def get_stakeholder_llm() -> ChatGoogleGenerativeAI:
    """Reutiliza o cliente que redige as falas do personagem."""
    validate_api_key()

    return ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        temperature=TEMPERATURE,
        max_tokens=STAKEHOLDER_MAX_TOKENS,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=MAX_RETRIES,
    )

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from app.infrastructure.database import get_pool
from app.infrastructure.interview_repository import InterviewRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Exportação privada para monitor/professora.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--group", default=None, help="Se omitido, exporta todos os grupos.")
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("O arquivo de saída já existe. Escolha outro nome para preservá-lo.")
    groups = InterviewRepository(get_pool()).export_for_teacher(args.group)
    document = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Exportação privada da atividade; inclui informações internas do cenário.",
        "groups": groups,
    }
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2, default=str)
    print(f"{len(groups)} entrevista(s) exportada(s) para {args.output.resolve()}")
    print("Guarde uma cópia fora da hospedagem. Esta exportação é exclusiva da equipe docente.")


if __name__ == "__main__":
    main()

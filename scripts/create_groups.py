from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

from app.domain.interview_state import create_initial_state
from app.domain.scenario import load_scenario
from app.infrastructure.database import get_pool
from app.infrastructure.interview_repository import InterviewRepository


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Cria entrevistas e códigos de acesso dos grupos.")
    parser.add_argument("--prefix", required=True, help="Ex.: TESTE ou TURMA-A")
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Arquivo CSV novo, fora do Git.")
    parser.add_argument("--scenario", type=Path,
                        default=PROJECT_ROOT / "scenarios" / "monitoring_system.json")
    args = parser.parse_args()
    if not 1 <= args.count <= 100 or not 1 <= len(args.prefix.strip()) <= 110:
        parser.error("Use de 1 a 100 grupos e um prefixo com até 110 caracteres.")

    scenario = load_scenario(args.scenario)
    snapshot = scenario.model_dump(mode="json")
    repository = InterviewRepository(get_pool())
    created = 0
    try:
        # 'x' evita apagar os códigos de um arquivo que já existe.
        with args.output.open("x", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["grupo", "codigo_de_acesso", "perguntas"])
            for number in range(1, args.count + 1):
                name = f"{args.prefix.strip()}-{number:02d}"
                code = repository.create_group(name, snapshot, create_initial_state(scenario))
                writer.writerow([name, code, scenario.interview_config.max_questions])
                handle.flush()
                os.fsync(handle.fileno())
                created += 1
    except FileExistsError:
        raise SystemExit("O CSV já existe. Escolha outro nome de saída; o arquivo anterior foi preservado.") from None
    except Exception as error:
        raise SystemExit(
            f"Criação interrompida ({type(error).__name__}). {created} grupo(s) já criado(s). "
            "Preserve o CSV e confira se o prefixo já foi usado. Não apague os registros existentes."
        ) from None
    print(f"{created} grupo(s) criado(s), com {scenario.interview_config.max_questions} perguntas cada.")
    print(f"Códigos salvos em: {args.output.resolve()}")
    print("Compartilhe somente o código do próprio grupo. Este arquivo permite acessar as entrevistas.")


if __name__ == "__main__":
    main()

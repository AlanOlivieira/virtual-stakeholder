from __future__ import annotations

from app.infrastructure.database import get_pool


def main() -> None:
    try:
        with get_pool().connection() as conn:
            row = conn.execute(
                """select current_database() as database,
                   to_regclass('bot_private.interview_sessions') is not null as sessions,
                   to_regclass('bot_private.interview_requests') is not null as requests"""
            ).fetchone()
        print("Conexão com o banco funcionando.")
        if not row["sessions"] or not row["requests"]:
            raise SystemExit("Faltam tabelas. Execute supabase/01_create_tables.sql no SQL Editor.")
        print("Tabelas de entrevistas encontradas. Nenhuma chamada de IA foi feita.")
    except SystemExit:
        raise
    except Exception as error:
        # Não imprime a configuração que contém a senha.
        print(f"Não foi possível conectar ({type(error).__name__}).")
        raise SystemExit("Confira PGHOST, PGUSER, PGPASSWORD e a seção de erros do guia.") from None


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
los_calibrar.py — Calibrador do LOS Checker (grava na BD Postgres partilhada)

Versão Windows ligada à mesma base de dados do PC Linux (Nobara), conforme
temp/instrucoes_los_windows.md. Em vez de escrever no los_calibracao.json
local, insere a observação na tabela los_observacoes da BD 'ED' na LAN —
assim as observações das duas máquinas alimentam o mesmo modelo orbital.

Cada observação é marcada com origem='win' para se distinguir das do PC
Linux (origem='linux') e das automáticas (origem='auto-win') — é isso que
permite usar os registos quase-simultâneos das duas máquinas como prova de
que a oclusão é global e não por instância.

Configuração: ficheiro .env na pasta do projeto (ver .env.example).
A password NUNCA fica neste ficheiro.

Dependências: pip install psycopg2-binary python-dotenv
"""

import os
import sys
from datetime import datetime, timezone

from los_checker import obter_sistema_atual

try:
    from dotenv import load_dotenv
except ImportError:
    print("[CALIBRAR] Falta python-dotenv. Instala com: pip install python-dotenv")
    sys.exit(1)

try:
    import psycopg2
except ImportError:
    print("[CALIBRAR] Falta psycopg2. Instala com: pip install psycopg2-binary")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ED_LOG_DIR = os.path.expanduser('~') + r"\Saved Games\Frontier Developments\Elite Dangerous"

load_dotenv(os.path.join(SCRIPT_DIR, ".env"))


def ligar_db():
    """ Liga à BD partilhada usando as variáveis do .env (R2D2_DB_*).
        A password NÃO vem do .env — vem do pgpass.conf do Windows
        (%APPDATA%\\postgresql\\pgpass.conf), lido automaticamente pelo
        libpq quando psycopg2.connect() não recebe o argumento password. """
    host = os.environ.get("R2D2_DB_HOST")
    if not host:
        print("[CALIBRAR] .env incompleto: precisa de R2D2_DB_HOST (ver .env.example).")
        return None
    try:
        return psycopg2.connect(
            host=host,
            port=os.environ.get("R2D2_DB_PORT", "5432"),
            dbname=os.environ.get("R2D2_DB_NAME", "ED"),
            user=os.environ.get("R2D2_DB_USER", "r2d2"),
            connect_timeout=5,
        )
    except Exception as e:
        print(f"[CALIBRAR] Falha na ligação à BD ({host}): {e}")
        print("[CALIBRAR] Se for timeout/recusa: verificar firewall do Windows e se os dois PCs estão na mesma rede.")
        return None


def main():
    print("=" * 50)
    print("  LOS CALIBRADOR — grava na BD partilhada (LAN)")
    print("=" * 50)
    print()

    sistema = obter_sistema_atual(ED_LOG_DIR)
    if not sistema:
        print("[CALIBRAR] Não foi possível detetar o sistema actual (Journal ilegível ou sem StarSystem).")
        print("           Certifica-te que o jogo já escreveu um evento FSDJump/Location/CarrierJump.")
        return

    print(f"Sistema detetado: {sistema}")
    print()
    print("Estado actual do carrier no jogo:")
    print("  1 - Oclusos (carrier atrás do planeta, tracejado)")
    print("  2 - Visível (linha directa livre)")
    print()

    escolha = input("Estado actual (1/2): ").strip()

    if escolha == "1":
        estado = "oclusos"
    elif escolha == "2":
        estado = "visivel"
    else:
        print("Opção inválida.")
        return

    nota = input("Nota opcional (Enter para saltar): ").strip() or None

    agora = datetime.now(timezone.utc)

    conn = ligar_db()
    if conn is None:
        return

    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO los_observacoes (sistema, timestamp_utc, estado, nota, origem) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id;",
                (sistema, agora, estado, nota, "win"),
            )
            novo_id = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(*) FROM los_observacoes WHERE sistema = %s;", (sistema,)
            )
            total = cur.fetchone()[0]
    finally:
        conn.close()

    print()
    print(f"[CALIBRAR] Observação #{novo_id} guardada na BD: {sistema} | {estado} | {agora.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"[CALIBRAR] Total de observações de '{sistema}' na BD: {total}")
    print()
    print("Agora corre: python los_checker.py (em qualquer uma das máquinas)")


if __name__ == "__main__":
    main()

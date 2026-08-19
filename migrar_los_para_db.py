#!/usr/bin/env python3
"""
migrar_los_para_db.py — Migração ÚNICA das observações do los_calibracao.json
para a BD Postgres partilhada, antes de abandonar o ficheiro JSON.

Insere na tabela los_observacoes com origem='win' — os registos existentes
na BD ficaram marcados como origem='linux' pela migração de schema
(los_db_migracao_origem.sql, correr PRIMEIRO no lado Linux). Os pares
quase-simultâneos win/linux não são duplicados a evitar: são a prova de
que as duas instâncias do jogo veem a mesma oclusão ao mesmo tempo.

Idempotente: verifica com NOT EXISTS por (sistema, timestamp_utc, estado)
antes de inserir — correr duas vezes não duplica nada.

O JSON não é alterado nem apagado — só o abandonas depois de validares os
totais impressos no fim.

Uso (no portátil, com o .env configurado):
    python migrar_los_para_db.py
"""

import json
import os
import sys
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
except ImportError:
    print("[MIGRACAO] Falta python-dotenv. Instala com: pip install python-dotenv")
    sys.exit(1)

try:
    import psycopg2
except ImportError:
    print("[MIGRACAO] Falta psycopg2. Instala com: pip install psycopg2-binary")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CAMINHO_JSON = os.path.join(SCRIPT_DIR, "los_calibracao.json")

load_dotenv(os.path.join(SCRIPT_DIR, ".env"))


def main():
    if not os.path.exists(CAMINHO_JSON):
        print(f"[MIGRACAO] Ficheiro não encontrado: {CAMINHO_JSON}")
        sys.exit(1)

    with open(CAMINHO_JSON, "r", encoding="utf-8") as f:
        dados = json.load(f)

    sistemas = dados.get("sistemas", {})
    if not sistemas:
        print("[MIGRACAO] JSON sem 'sistemas' — nada para migrar.")
        sys.exit(1)

    host = os.environ.get("R2D2_DB_HOST")
    password = os.environ.get("R2D2_DB_PASSWORD")
    if not host or not password:
        print("[MIGRACAO] .env incompleto: precisa de R2D2_DB_HOST e R2D2_DB_PASSWORD (ver .env.example).")
        sys.exit(1)

    try:
        conn = psycopg2.connect(
            host=host,
            port=os.environ.get("R2D2_DB_PORT", "5432"),
            dbname=os.environ.get("R2D2_DB_NAME", "ED"),
            user=os.environ.get("R2D2_DB_USER", "r2d2"),
            password=password,
            connect_timeout=5,
        )
    except Exception as e:
        print(f"[MIGRACAO] Falha na ligação à BD ({host}): {e}")
        sys.exit(1)

    inseridas = saltadas = 0
    try:
        with conn, conn.cursor() as cur:
            for sistema, cfg in sistemas.items():
                for o in cfg.get("observacoes", []):
                    ts = o.get("timestamp_utc")
                    estado = o.get("estado")
                    if not ts or estado not in ("visivel", "oclusos"):
                        continue
                    # Timestamps do JSON são UTC naive — marcar como UTC explícito
                    ts_utc = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
                    cur.execute(
                        "INSERT INTO los_observacoes (sistema, timestamp_utc, estado, nota, origem) "
                        "SELECT %s, %s, %s, %s, %s "
                        "WHERE NOT EXISTS (SELECT 1 FROM los_observacoes "
                        "  WHERE sistema = %s AND timestamp_utc = %s AND estado = %s);",
                        (sistema, ts_utc, estado, o.get("nota"), "win",
                         sistema, ts_utc, estado),
                    )
                    if cur.rowcount == 1:
                        inseridas += 1
                    else:
                        saltadas += 1

            print(f"[MIGRACAO] Inseridas: {inseridas} | Já existiam (saltadas): {saltadas}")
            cur.execute(
                "SELECT origem, sistema, estado, COUNT(*) FROM los_observacoes "
                "GROUP BY origem, sistema, estado ORDER BY origem, sistema, estado;"
            )
            print("[MIGRACAO] Estado final na BD (por origem):")
            for origem, sistema, estado, n in cur.fetchall():
                print(f"[MIGRACAO]   {origem} / {sistema} / {estado}: {n}")
    finally:
        conn.close()

    print("[MIGRACAO] Concluído. O los_calibracao.json não foi alterado — "
          "valida os totais acima antes de o abandonar (as constantes orbitais continuam a viver nele).")


if __name__ == "__main__":
    main()

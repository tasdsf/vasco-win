#!/usr/bin/env python3
"""
discord_notify.py - Notificacoes de erro fatal para o Discord (via webhook).

Equivalente Windows da funcao ja implementada no lado Linux (vasco-r2d2
Nobara). Mesma assinatura e comportamento -- ver AGENTS.md/CLAUDE.md deste
projeto para a nomenclatura partilhada entre os dois lados:
    DISCORD_WEBHOOK_URL, VASCO_HOST_ID, notificar_erro_discord(),
    logs/erro_<timestamp>.png
"""

import json as _json
import os

try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except Exception:
    pass

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
HOST_ID = os.environ.get("VASCO_HOST_ID", "vasco-r2d2-win")

def notificar_erro_discord(origem, mensagem, imagem_path=None):
    """ Envia uma notificação de erro para o Discord via webhook (URL em
    DISCORD_WEBHOOK_URL, ver .env). Best-effort -- nunca deve derrubar o
    chamador: qualquer falha (webhook não configurado, sem rede, timeout)
    fica só registada na consola, nunca levanta exceção.

    origem       -- identifica o script/etapa que falhou (ex:
                     "supercruise_assist.py").
    mensagem     -- texto do erro.
    imagem_path  -- caminho opcional de um PNG a anexar; se não existir,
                     envia só o texto. """
    if not DISCORD_WEBHOOK_URL:
        print("[DISCORD] DISCORD_WEBHOOK_URL não definido -- notificação não enviada.")
        return False
    try:
        import requests
        payload = {"content": f"🔴 **[{HOST_ID}] {origem}**\n{mensagem}"}
        if imagem_path and os.path.exists(imagem_path):
            with open(imagem_path, "rb") as f:
                resp = requests.post(
                    DISCORD_WEBHOOK_URL,
                    data={"payload_json": _json.dumps(payload)},
                    files={"file": (os.path.basename(imagem_path), f, "image/png")},
                    timeout=10,
                )
        else:
            resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if resp.status_code not in (200, 204):
            print(f"[DISCORD] Falha ao enviar notificação: {resp.status_code} {resp.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"[DISCORD] Falha ao enviar notificação: {e}")
        return False

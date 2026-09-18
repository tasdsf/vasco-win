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

def _enviar_discord(content, imagem_path=None):
    """ Envia `content` (já formatado) para o webhook em DISCORD_WEBHOOK_URL.
    Best-effort -- nunca levanta exceção, qualquer falha fica só registada na
    consola. Usado por notificar_erro_discord() e notificar_sucesso_discord(). """
    if not DISCORD_WEBHOOK_URL:
        print("[DISCORD] DISCORD_WEBHOOK_URL não definido -- notificação não enviada.")
        return False
    try:
        import requests
        LIMITE_CONTENT_DISCORD = 2000  # limite rigido da API do Discord para "content"
        if len(content) > LIMITE_CONTENT_DISCORD:
            sufixo = "\n… (truncado)"
            content = content[:LIMITE_CONTENT_DISCORD - len(sufixo)] + sufixo
        payload = {"content": content}
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
    return _enviar_discord(f"🔴 **[{HOST_ID}] {origem}**\n{mensagem}", imagem_path)

def notificar_sucesso_discord(origem, mensagem):
    """ Envia uma notificação de sucesso para o Discord via webhook (mesmo
    canal/formato de notificar_erro_discord, com ✅ em vez de 🔴). Best-effort,
    mesmas garantias de não-exceção.

    origem       -- identifica o script/etapa (ex: "vender.py").
    mensagem     -- texto da confirmação. """
    return _enviar_discord(f"✅ **[{HOST_ID}] {origem}**\n{mensagem}")

def notificar_info_discord(origem, mensagem):
    """ Envia uma notificação informativa/neutra para o Discord via webhook
    (mesmo canal/formato de notificar_erro_discord, com ⏸️ em vez de 🔴) --
    para estados que não são erro nem sucesso, ex.: uma pausa planeada
    (espera pela janela de LOS). Best-effort, mesmas garantias de
    não-exceção.

    origem       -- identifica o script/etapa (ex: "vasco.py").
    mensagem     -- texto do aviso. """
    return _enviar_discord(f"⏸️ **[{HOST_ID}] {origem}**\n{mensagem}")

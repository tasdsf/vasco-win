#!/usr/bin/env python3
"""
leg_state.py - Estado partilhado "perna limpa" (undocking -> supercruise).

Só regista observações automáticas de LOS (registar_los_visivel_auto, em
supercruise_assist.py) quando a perna correu do início ao fim sem nenhum
erro/retry -- sem isto, um salto que só "passou" porque uma tentativa
anterior falhou e foi repetida (ou teve intervenção manual) contamina o
ajuste de fase/período em los_checker.py com um falso "visível".

Equivalente Windows do módulo já usado no lado Linux -- mesmos nomes de
função, mesmo comportamento (ver AGENTS.md/CLAUDE.md deste projeto). UMA
DIFERENÇA REAL face ao lado Linux: lá tudo corre no mesmo processo via
vasco.py, por isso um global em memória chega. Aqui vasco.py.executar_script
lança cada etapa como SUBPROCESSO separado (subprocess.Popen) -- um global
em memória neste módulo não atravessa essa fronteira (cada subprocesso via
Python fresco começa sempre com o valor por omissão). Por isso o estado é
persistido em logs/leg_state.json, lido/escrito por cada processo.
"""

import json
import os

_DIR = os.path.dirname(os.path.abspath(__file__))
_LOG_DIR = os.path.join(_DIR, "logs")
_STATE_FILE = os.path.join(_LOG_DIR, "leg_state.json")

def _gravar(limpa):
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"leg_limpa": limpa}, f)
    except Exception as e:
        print(f"[LEG_STATE] Falha ao gravar {_STATE_FILE}: {e}")

def reiniciar_leg_limpa():
    """ Chamado pelo orquestrador mesmo antes de cada UNDOCKING (início de
    perna) -- volta a dar o benefício da dúvida à próxima perna. """
    _gravar(True)

def marcar_leg_suja():
    """ Chamado pelo orquestrador sempre que uma etapa tem qualquer
    exceção/falha (mesmo que uma tentativa seguinte tenha sucesso) -- uma
    vez suja, fica suja até ao próximo reiniciar_leg_limpa(). """
    _gravar(False)

def leg_esta_limpa():
    """ Sem ficheiro (primeira etapa do processo, ou falha de leitura) ->
    benefício da dúvida (limpa), igual ao valor por omissão original. """
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("leg_limpa", True)
    except Exception:
        return True

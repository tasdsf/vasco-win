#!/usr/bin/env python3
"""
plano_fuga.py - Ciclo de fuga para quedas de Supercruise nao identificadas
como chegada (interdicao, mass lock inesperado, obstaculo, etc.).

Chamado por supercruise_assist.py::monitorar_viagem() quando a queda da
flag SUPERCRUISE nao vem acompanhada de um SupercruiseDestinationDrop no
Journal (ver esse ficheiro para o criterio de deteccao).

Ciclo de evasao portado do Vasco-Nobara/Linux (ja validado em producao la):
evasao incondicional (boost + heatsink) -> valida por telemetria se o FSD
esta disponivel -> tenta 'j', repete ate confirmar carga -> acelera e
espera confirmar Supercruise. NAO tenta alinhar nada durante a evasao/carga
-- com a nave a oscilar em velocidade nenhuma leitura de bussola/HUD e de
confiar, e entrar em Supercruise nao exige apontar a nada (so sair dela
para um alvo especifico e que precisa). A reentrada no Supercruise Assist
(menu + alinhamento) fica a cargo do chamador (monitorar_viagem), que ja
faz isso apos este modulo devolver o controlo.

O resto (logging, telemetria, abortar_com_erro) segue o mesmo padrao de
duplicacao local ja usado em todos os outros scripts do projeto.
"""

import os
import sys
import time
import json
import logging
import pydirectinput

# ==========================================
# 0. LOGGING E INFRAESTRUTURA
# ==========================================
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(PROJECT_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# Nota: quando importado por supercruise_assist.py (caso de uso real), este
# basicConfig e um no-op -- o logging.basicConfig so tem efeito na primeira
# chamada do processo, e supercruise_assist.py configura o logger antes de
# importar este modulo. Fica aqui na mesma para o caso deste ficheiro alguma
# vez ser executado/importado sozinho.
logging.basicConfig(
    filename=os.path.join(LOGS_DIR, "r2d2_combined.log"),
    level=logging.INFO,
    format='%(asctime)s - [PLANO_FUGA] - %(levelname)s - %(message)s'
)

_print_original = print
def print(*args, **kwargs):
    if args and isinstance(args[0], str):
        _texto = args[0]
        _prefixo_nl = ""
        while _texto.startswith("\n"):
            _prefixo_nl += "\n"
            _texto = _texto[1:]
        args = (f"{_prefixo_nl}[{time.strftime('%H:%M:%S')}] {_texto}",) + args[1:]
    _print_original(*args, **kwargs)

def abortar_com_erro(mensagem):
    print(f"\n[FATAL] {mensagem}")
    logging.error(mensagem)
    sys.exit(1)

# ==========================================
# 1. TELEMETRIA (copia local minima -- ver nota no topo do ficheiro)
# ==========================================
STATUS_FILE = os.path.join(os.environ['USERPROFILE'], 'Saved Games', 'Frontier Developments', 'Elite Dangerous', 'Status.json')
STATUS_FLAGS = {
    "SUPERCRUISE": 0x10,
    "HARDPOINTS_DEPLOYED": 0x40,
    "FSD_MASS_LOCKED": 0x10000,
    "FSD_CHARGING": 0x20000,
}

def ler_telemetria(debug=False):
    try:
        with open(STATUS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            flags = data.get("Flags", 0)
            if debug:
                ativas = [nome for nome, bit in STATUS_FLAGS.items() if flags & bit]
                print(f"    [FLAGS] {hex(flags)} -> {', '.join(ativas) if ativas else '(nenhuma flag conhecida ativa)'}")
            return flags
    except Exception as e:
        if debug:
            print(f"    [FLAGS] Falha a ler {STATUS_FILE}: {e}")
        return 0

# ==========================================
# 2. CICLO DE FUGA
# ==========================================
# Mesma ordem de grandeza do LIMITE_MANOBRA (180s) ja usado no olho.py
# standalone -- aqui ha boosts repetidos a gastar capacitor, por isso nao
# convem ser mais generoso sem dados reais que o justifiquem.
LIMITE_FUGA = 180.0

# Cooldown pos-boost: o impulso do boost deixa a nave a oscilar (arfagem/
# momentum) por um instante -- ler telemetria logo a seguir apanha o alvo
# instavel. Valor portado do Vasco-Nobara/Linux.
COOLDOWN_EVASIVO = 1.5

def _passo_evasivo():
    """ 'shiftright' (100% de aceleracao) + 'tab' (boost) + 'v' (heatsink --
    baixa o calor da nave, dificultando que o inimigo mantenha o alvo por
    eletronica), incondicional e ciclico. Nao tenta alinhar nada aqui -- com
    velocidade a nave oscila demais para qualquer leitura de bussola/HUD ser
    de confiar; entrar em Supercruise nao exige apontar a nada, por isso a
    fuga foca-se so em ganhar distancia e perder o lock de quem estiver a
    perseguir. Portado do Vasco-Nobara/Linux, ja validado em producao. """
    pydirectinput.press('shiftright')
    pydirectinput.press('tab')
    pydirectinput.press('v')
    time.sleep(COOLDOWN_EVASIVO)

def pode_saltar_agora(debug=False):
    """ Valida por telemetria se faz sentido tentar 'j' neste ciclo -- sem
    mass lock e sem hardpoints em baixo, as duas causas conhecidas de falha
    de salto ja usadas em supercruise_assist.py::iniciar_salto_seguro(). Se
    detetar hardpoints em baixo, recolhe-os logo ('u') e devolve False nesta
    volta -- da tempo a animacao de recolha antes de tentar o salto na volta
    seguinte. Mass lock nao tem remedio por tecla (so afastar-nos, o que o
    boost ja esta a fazer), por isso so e reportado, nao remediado. """
    flags = ler_telemetria(debug=debug)
    mass_locked = bool(flags & STATUS_FLAGS["FSD_MASS_LOCKED"])
    hardpoints = bool(flags & STATUS_FLAGS["HARDPOINTS_DEPLOYED"])

    if hardpoints:
        print("[PLANO_FUGA] Hardpoints em baixo -- a recolher (U)...")
        logging.info("Plano de fuga: hardpoints deployed detetados, a enviar 'u' para recolher.")
        pydirectinput.press('u')
        return False

    return not mass_locked

def aguardar_supercruise_confirmado(timeout=30):
    """ Copia local minima de supercruise_assist.py::aguardar_supercruise_confirmado
    -- mesmo padrao de duplicacao ja usado neste ficheiro (ver nota no
    topo). Devolve True/False em vez de abortar -- uma falha aqui significa
    'volta ao inicio do ciclo', nao 'morre'. """
    limite = time.time() + timeout
    while time.time() < limite:
        flags = ler_telemetria(debug=True)
        if bool(flags & STATUS_FLAGS["SUPERCRUISE"]):
            return True
        time.sleep(0.5)
    return False

def executar_fuga():
    """ Ponto de entrada chamado por supercruise_assist.py. Ciclo, em cada
    volta: evasao incondicional (_passo_evasivo) -> valida por telemetria se
    o FSD esta disponivel agora (pode_saltar_agora) -> se sim, tenta 'j' +
    'shiftright' e confirma se o FSD passou mesmo a carregar; se nao, so a
    evasao desta volta conta e repete. Depois de confirmar carga, espera a
    confirmacao de Supercruise pela telemetria antes de devolver o controlo.
    Devolve True em caso de sucesso; aborta o processo (180s) se nunca
    conseguir reentrar em Supercruise. """
    print("\n>>> PLANO DE FUGA: queda de Supercruise nao identificada como chegada. A iniciar ciclo de fuga.")
    logging.info("Plano de fuga acionado.")

    inicio = time.time()
    tentativas = 0

    while time.time() - inicio < LIMITE_FUGA:
        tentativas += 1
        print(f"\n[PLANO_FUGA] Ciclo {tentativas}: velocidade maxima + boost + heatsink (sobrevivencia)...")
        _passo_evasivo()

        if not pode_saltar_agora(debug=True):
            print("[PLANO_FUGA] FSD indisponivel agora (mass lock ou hardpoints) -- so evasao nesta volta, sem tentar 'j'.")
            continue

        print("[PLANO_FUGA] FSD disponivel -- a enviar 'j' + 'shiftright'...")
        pydirectinput.press('j')
        pydirectinput.press('shiftright')
        time.sleep(1.5)

        if bool(ler_telemetria(debug=True) & STATUS_FLAGS["FSD_CHARGING"]):
            print("[PLANO_FUGA] FSD a carregar -- a confirmar Supercruise pela telemetria...")
            logging.info(f"Plano de fuga: FSD confirmado a carregar na tentativa {tentativas}.")
            if aguardar_supercruise_confirmado():
                print("[PLANO_FUGA] Supercruise confirmado. Fuga bem sucedida.")
                logging.info(f"Plano de fuga: sucesso na tentativa {tentativas} ({time.time()-inicio:.1f}s).")
                return True
            print("[AVISO] Supercruise nao confirmado apesar do FSD a carregar -- a repetir o ciclo.")
        else:
            print("[AVISO] FSD nao confirmou carga apos 'j' -- a repetir o ciclo.")

    abortar_com_erro(f"Plano de fuga excedeu {LIMITE_FUGA}s sem conseguir reentrar em Supercruise ({tentativas} tentativas).")

if __name__ == "__main__":
    executar_fuga()

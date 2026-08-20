#!/usr/bin/env python3
"""
plano_fuga.py - Ciclo de fuga para quedas de Supercruise nao identificadas
como chegada (interdicao, mass lock inesperado, obstaculo, etc.).

Chamado por supercruise_assist.py::monitorar_viagem() quando a queda da
flag SUPERCRUISE nao vem acompanhada de um SupercruiseDestinationDrop no
Journal (ver esse ficheiro para o criterio de deteccao). Reaproveita as
funcoes de visao do olho.py (executar_passo_alinhamento) em vez de duplicar
a logica de alinhamento -- essa e a unica dependencia entre ficheiros aqui;
o resto (logging, telemetria, abortar_com_erro) segue o mesmo padrao de
duplicacao local ja usado em todos os outros scripts do projeto.
"""

import os
import sys
import time
import json
import logging
import pydirectinput
import mss

import olho

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

def confirmar_saida_supercruise(timeout=5):
    """ Confirma pela telemetria que SUPERCRUISE ja caiu antes de comecar o
    ciclo -- o chamador (monitorar_viagem) ja detetou a queda, isto e so a
    segunda confirmacao independente pedida explicitamente. Nao bloqueia o
    ciclo se o timeout esgotar (nao e critico o suficiente para abortar). """
    print("[PLANO_FUGA] A confirmar (telemetria) que saimos de Supercruise...")
    limite = time.time() + timeout
    while time.time() < limite:
        flags = ler_telemetria(debug=True)
        if not bool(flags & STATUS_FLAGS["SUPERCRUISE"]):
            print("[OK] Fora de Supercruise confirmado pela telemetria.")
            return True
        time.sleep(0.5)
    print(f"[AVISO] Nao foi possivel confirmar a saida de Supercruise em {timeout}s pela telemetria. A prosseguir na mesma.")
    return False

def pode_saltar_agora(debug=False):
    """ Valida por telemetria se faz sentido tentar 'j' neste ciclo -- sem
    mass lock e sem hardpoints em baixo, as duas causas conhecidas de falha
    de salto ja usadas em supercruise_assist.py::iniciar_salto_seguro(). Se
    detetar hardpoints em baixo, recolhe-os logo ('u') e devolve False nesta
    volta -- da tempo a animacao de recolha antes de tentar o salto na volta
    seguinte, em vez de tentar 'j' no mesmo instante em que 'u' foi enviado.
    Mass lock nao tem remedio por tecla (so afastar-nos, o que o boost ja
    esta a fazer), por isso so e reportado, nao remediado. Nao verifica
    FSD_CHARGING aqui: se ja estiver a carregar, o proprio
    tentar_saltar_com_alinhamento() trata disso (mantem o alinhamento em vez
    de reenviar 'j'). """
    flags = ler_telemetria(debug=debug)
    mass_locked = bool(flags & STATUS_FLAGS["FSD_MASS_LOCKED"])
    hardpoints = bool(flags & STATUS_FLAGS["HARDPOINTS_DEPLOYED"])

    if hardpoints:
        print("[PLANO_FUGA] Hardpoints em baixo -- a recolher (U)...")
        logging.info("Plano de fuga: hardpoints deployed detetados, a enviar 'u' para recolher.")
        pydirectinput.press('u')
        return False

    return not mass_locked

def tentar_saltar_com_alinhamento(sct, area_bussola, cx_neutro, cy_neutro, timeout=30):
    """ Pressiona 'j' + 'shiftright' para iniciar a carga do FSD e MANTEM o
    alinhamento com o olho.py durante toda a carga, ate confirmar por
    telemetria que entramos mesmo em Supercruise (nao so que a carga
    comecou) -- desviar o nariz a meio da carga pode cancelar o salto, por
    isso o alinhamento nao pode parar so porque a carga arrancou. 30s cobre a
    duracao tipica de uma carga de FSD para Supercruise com alguma margem --
    estimativa inicial, nao calibrada com dados reais. Devolve True/False em
    vez de abortar -- uma falha aqui significa 'volta ao inicio do ciclo',
    nao 'morre'. """
    print("[PLANO_FUGA] FSD disponível -- a enviar 'j' + 'shiftright' e a manter alinhamento até entrar em Supercruise...")
    pydirectinput.press('j')
    pydirectinput.press('shiftright')

    limite = time.time() + timeout
    flags = 0
    while time.time() < limite:
        flags = ler_telemetria(debug=True)
        if bool(flags & STATUS_FLAGS["SUPERCRUISE"]):
            print("[OK] Supercruise confirmado -- salto concluído.")
            logging.info(f"Plano de fuga: Supercruise confirmado após tentativa de salto (flags={hex(flags)}).")
            return True
        olho.executar_passo_alinhamento(sct, area_bussola, cx_neutro, cy_neutro)
        time.sleep(0.3)

    print(f"[AVISO] Supercruise não confirmado em {timeout}s apesar do alinhamento contínuo. Últimas flags: {hex(flags)}")
    logging.info(f"Plano de fuga: tentativa de salto sem confirmação de Supercruise em {timeout}s (flags={hex(flags)}).")
    return False

def executar_fuga():
    """ Ponto de entrada chamado por supercruise_assist.py. Ciclo, em cada
    volta: velocidade maxima + boost (imprescindivel para sobreviver,
    incondicional) -> valida por telemetria se o FSD esta disponivel agora
    (sem mass lock, sem hardpoints) -> se sim, tenta 'j' e mantem o
    alinhamento durante a carga; se nao, so o boost desta volta conta e
    repete. Devolve True em caso de sucesso; aborta o processo (180s) se
    nunca conseguir. A reentrada no Supercruise Assist (menu) fica a cargo
    do chamador (monitorar_viagem), que ja faz isso apos este retornar. """
    print("\n>>> PLANO DE FUGA: queda de Supercruise nao identificada como chegada. A iniciar ciclo de fuga.")
    logging.info("Plano de fuga acionado.")
    confirmar_saida_supercruise()

    nave_ativa = olho.obter_modelo_nave_atual()
    MONITOR_CONFIG, CX_NEUTRO, CY_NEUTRO = olho.carregar_dados_calibracao(nave_ativa)
    print(f"[PLANO_FUGA] Nave: {nave_ativa} | Calibracao: {MONITOR_CONFIG}")

    inicio = time.time()
    tentativas = 0

    with mss.mss() as sct:
        try:
            monitor_jogo = sct.monitors[1]
        except Exception:
            monitor_jogo = sct.monitors[0]

        area_bussola = {
            "top": monitor_jogo["top"] + MONITOR_CONFIG["top"],
            "left": monitor_jogo["left"] + MONITOR_CONFIG["left"],
            "width": MONITOR_CONFIG["width"], "height": MONITOR_CONFIG["height"]
        }

        while time.time() - inicio < LIMITE_FUGA:
            tentativas += 1
            print(f"\n[PLANO_FUGA] Ciclo {tentativas}: velocidade maxima + boost + heatsink (sobrevivência)...")
            pydirectinput.press('shiftright')
            pydirectinput.press('tab')
            # Heatsink ('v') -- baixa o calor da nave, dificultando que o
            # inimigo mantenha o alvo por eletrónica. Consumivel (a nave tem
            # 2 lançadores, ver Loadout) -- reposição fica para depois, por
            # agora dispara-se em todos os ciclos e o proprio jogo ignora se
            # estiver em cooldown ou sem carga.
            pydirectinput.press('v')

            # Cooldown pos-boost: o impulso do boost deixa a nave a oscilar
            # (arfagem/momentum) por um instante -- ler telemetria/alinhamento
            # logo a seguir apanha o alvo instavel. 1.5s e uma estimativa
            # inicial, nao calibrada com dados reais -- ajustar se os logs
            # mostrarem problemas.
            time.sleep(1.5)

            if pode_saltar_agora(debug=True):
                logging.info(f"Plano de fuga: FSD disponível na tentativa {tentativas}, a saltar.")
                if tentar_saltar_com_alinhamento(sct, area_bussola, CX_NEUTRO, CY_NEUTRO):
                    print("[PLANO_FUGA] Salto confirmado. Fuga bem sucedida.")
                    logging.info(f"Plano de fuga: sucesso na tentativa {tentativas} ({time.time()-inicio:.1f}s).")
                    return True
                print("[AVISO] Salto não confirmado apesar do FSD disponível -- a repetir o ciclo.")
            else:
                print("[PLANO_FUGA] FSD indisponível agora (mass lock ou hardpoints) -- só boost nesta volta, sem tentar 'j'.")

            time.sleep(0.5)

    abortar_com_erro(f"Plano de fuga excedeu {LIMITE_FUGA}s sem conseguir saltar ({tentativas} tentativas).")

if __name__ == "__main__":
    executar_fuga()

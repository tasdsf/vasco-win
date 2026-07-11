#!/usr/bin/env python3
"""
Supercruise Assist - Módulo Unificado (Mecânica Ótica + Telemetria)
Elite Dangerous Automation
"""

import os
import sys
import json
import time
import logging
import pydirectinput
import cv2
import mss
import numpy as np
import pyttsx3
import pygetwindow as gw
import time

# ==========================================
# 0. LOGGING E INFRAESTRUTURA
# ==========================================
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(PROJECT_DIR, "logs")
IMAGES_DIR = os.path.join(PROJECT_DIR, "images")
os.makedirs(LOGS_DIR, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(LOGS_DIR, "r2d2_combined.log"),
    level=logging.ERROR,
    format='%(asctime)s - [SUPERCRUISE] - %(levelname)s - %(message)s'
)

def abortar_com_erro(mensagem):
    print(f"\n[FATAL] {mensagem}")
    logging.error(mensagem)
    sys.exit(1)

# Voz
engine = pyttsx3.init()
def falar(texto):
    print(f"[VOZ] {texto}")
    engine.say(texto)
    engine.runAndWait()

NOME_JANELA = "Ocular do Bot - Supercruise"
VISUAL_DEBUG = False

def inicializar_infraestrutura():
    print("[SISTEMA] A configurar foco no jogo...")
    
    focar_jogo_seguro()
    time.sleep(0.5)
            
    if VISUAL_DEBUG:
        cv2.namedWindow(NOME_JANELA, cv2.WINDOW_NORMAL)
        with mss.mss() as sct:
            monitores = sct.monitors
            if len(monitores) > 2:
                ecra_secundario = monitores[2]
                cv2.moveWindow(NOME_JANELA, ecra_secundario["left"] + 50, ecra_secundario["top"] + 50)
            else:
                cv2.moveWindow(NOME_JANELA, 50, 50)
            cv2.setWindowProperty(NOME_JANELA, cv2.WND_PROP_TOPMOST, 1)

def focar_jogo_seguro():
    """ Foca o Elite Dangerous a nível de Sistema Operativo, sem enviar cliques de rato """
    print("[SISTEMA] A focar o Elite Dangerous via Windows API...")
    try:
        # Procura a janela pelo título (no Elite geralmente é "Elite - Dangerous (CLIENT)")
        janelas = gw.getWindowsWithTitle("Elite - Dangerous (CLIENT)")
        
        if janelas:
            janela_elite = janelas[0]
            # Traz a janela para a frente
            janela_elite.activate() 
            time.sleep(0.5)
            print("[OK] Jogo focado com sucesso e em segurança.")
            return True
        else:
            print("[ERRO] Janela do Elite Dangerous não encontrada!")
            return False
            
    except Exception as e:
        print(f"[AVISO] Falha ao forçar foco via OS: {e}")
        return False

# ==========================================
# 1. SETUP (TEMPLATES E TELEMETRIA)
# ==========================================
MONITOR_CENTER = {"top": 100, "left": 400, "width": 1100, "height": 800}
MONITOR_PANEL = {"top": 200, "left": 50, "width": 1000, "height": 1200}
STATUS_FILE = os.path.join(os.environ['USERPROFILE'], 'Saved Games', 'Frontier Developments', 'Elite Dangerous', 'Status.json')

STATUS_FLAGS = {
    "SUPERCRUISE": 0x10,
    "FSD_MASS_LOCKED": 0x10000,
    "FSD_CHARGING": 0x20000,
    "HARDPOINTS_DEPLOYED": 0x40,
    "INTERDICTION": 0x800000,
}

TEMPLATES_NOMES = {
    'nav_tab': 'NAVIGATION_SELECTED.png',
    'charging': 'CHARGING.png',
    'locked': 'LOCKED_DESTINATION.png',
    'unlocked': 'UNLOCKED_DESTINATION.png',
    'assist_active': 'SUPERCRUISE_ASSIST_ACTIVE.png',
    'align_warning': 'SUPERCRUISE_ASSIST_INACTIVE.png',
    'throttle_up': 'THROTTLE_UP.png'
}

templates = {}
try:
    for chave, nome_arq in TEMPLATES_NOMES.items():
        caminho = os.path.join(IMAGES_DIR, nome_arq)
        img = cv2.imread(caminho, cv2.IMREAD_COLOR)
        if img is None: raise FileNotFoundError(f"Falta imagem: {caminho}")
        templates[chave] = img
    print("[SISTEMA] Módulo Unified Supercruise carregado.")
except Exception as e:
    abortar_com_erro(f"Erro ao carregar templates visuais: {e}")

# ==========================================
# 2. MOTORES CORE (VISÃO E DADOS)
# ==========================================
def procurar_template(template, nome_label, monitor, threshold=0.75, debug=False):
    with mss.mss() as sct:
        img_bgra = np.array(sct.grab(monitor))
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
        res = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        encontrou = max_val >= threshold

        if debug:
            marca = "OK" if encontrou else "--"
            print(f"    [MATCH {marca}] {nome_label}: {max_val:.3f} (limiar {threshold:.2f})")

        if VISUAL_DEBUG:
            cor = (0, 255, 0) if encontrou else (0, 0, 255)
            if encontrou:
                h, w = template.shape[:2]
                cv2.rectangle(img_bgr, max_loc, (max_loc[0] + w, max_loc[1] + h), cor, 2)
            cv2.putText(img_bgr, f"{nome_label}: {max_val:.2f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, cor, 2)
            cv2.imshow(NOME_JANELA, img_bgr)
            cv2.waitKey(1)
            
        return encontrou

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
# 3. FASE 0: SALTO E TELEMETRIA
# ==========================================
def iniciar_salto_seguro():
    print("\n>>> FASE 0: Iniciar Salto (J)...")
    print("[LOG] A enviar 'j' (iniciar salto) + 'right shift' (acelerar)...")
    pydirectinput.press('j')
    pydirectinput.press('shiftright')

    # 'right shift' é um toque único (press), não uma tecla para segurar -
    # por isso já não há keyDown/keyUp nem watchdog visual (CHARGING/
    # THROTTLE_UP) a temporizar a aceleração. Em vez disso esperamos um tempo
    # fixo de 8s (carga + aceleração) antes de ir validar por telemetria.
    print("[LOG] A aguardar 8s antes de validar telemetria...")
    time.sleep(8)

    print("[TELEMETRIA] A validar telemetria do FSD ...")

    # Poll em vez de leitura única: evita falsos negativos por
    # (a) a leitura calhar mesmo na janela de transição entre "a carregar" e
    # "já em Supercruise" onde nenhuma das duas flags está ativa por um
    # instante, ou (b) apanhar o Status.json a meio de uma reescrita do jogo
    # (ler_telemetria devolve 0 silenciosamente nesse caso).
    flags = 0
    salto_confirmado = None
    for tentativa in range(7):
        print(f"[LOG] Poll telemetria {tentativa+1}/7...")
        flags = ler_telemetria(debug=True)
        if bool(flags & STATUS_FLAGS["FSD_CHARGING"]):
            salto_confirmado = "carga"
            break
        if bool(flags & STATUS_FLAGS["SUPERCRUISE"]):
            salto_confirmado = "supercruise"
            break
        time.sleep(0.5)

    # 1. Confirmou que está a carregar
    if salto_confirmado == "carga":
        print("[OK] Motor FSD em carga confirmada pela telemetria.")
        # Espera o salto acontecer
        pydirectinput.press('x')
        time.sleep(4.5)
        return True

    # 1b. Já não está a carregar porque o salto já teve sucesso entretanto
    if salto_confirmado == "supercruise":
        print("[OK] Já em Supercruise (a carga completou antes da leitura de telemetria).")
        pydirectinput.press('x')
        return True

    pydirectinput.press('x')

    print(f"[LOG] Nenhuma flag de sucesso confirmada. Ultimas flags lidas: {hex(flags)}. A testar causas conhecidas...")

    # 2. Se não está a carregar nem em supercruise, usa as regras do Hermes para descobrir o porquê
    if bool(flags & STATUS_FLAGS["FSD_MASS_LOCKED"]):
        pydirectinput.press('x')
        abortar_com_erro("Nave bloqueada por Mass Lock da estação/planeta.")

    if bool(flags & STATUS_FLAGS["HARDPOINTS_DEPLOYED"]):
        pydirectinput.press('x')
        abortar_com_erro("Armas ou Trem de Aterragem abertos. Impossível saltar.")

    if procurar_template(templates['align_warning'], "ALIGN", MONITOR_CENTER, 0.82, debug=True):
        pydirectinput.press('x')
        abortar_com_erro("Vetor de proa totalmente desalinhado do destino.")

    pydirectinput.press('x')
    abortar_com_erro("Falha desconhecida ao iniciar o salto: FSD não confirma carga nem Supercruise, e nenhuma causa conhecida (Mass Lock / Hardpoints / Alinhamento) foi detetada.")

# ==========================================
# 4. FASE 1: NAVEGAÇÃO MECÂNICA NO MENU
# ==========================================
def engatar_assistencia_menu():
    print("\n>>> FASE 1: Navegação no Painel Esquerdo...")
    
    # Reduzir velocidade antes de mexer nos menus
    pydirectinput.press('x')     
    pydirectinput.press('1')
    pydirectinput.press('x') 
    time.sleep(1)

    # 1. Achar a ABA NAV
    nav_found = False
    for _ in range(6):
        if procurar_template(templates['nav_tab'], "NAV TAB", MONITOR_PANEL, 0.80, debug=True):
            nav_found = True
            break
        pydirectinput.press('q')
        time.sleep(0.5)
        
    if not nav_found:
        pydirectinput.press('x') 
        pydirectinput.press('1')
        abortar_com_erro("Falha crítica ao tentar focar na aba de navegação.")

    # 2. A lógica que notaste faltar: SPACE -> D -> SPACE
    print(">>> Focando no destino pré-selecionado (Space)...")
    pydirectinput.press('space')
    time.sleep(0.8)
    
    print(">>> Movendo para o botão Supercruise Assist (D)...")
    pydirectinput.press('d')
    time.sleep(0.5)
    
    print(">>> Ativando Assistência (Space)...")
    pydirectinput.press('space')
    time.sleep(1.0)
    
    pydirectinput.press('1') # Fecha painel
    print(">>> Painel fechado. Voltando ao Cockpit.")

# ==========================================
# 5. FASE 2: VIAGEM E CHEGADA
# ==========================================
def monitorar_viagem():    
    print("\n>>> FASE 2: Viagem em Supercruise...")
    falar("Supercruise assist engaged. Monitoring flight path.")
    
    # Watchdog: Confirmar HUD
    contagem_limpo = 0
    timeout_assist = time.time() + 60
    while contagem_limpo < 3:
        if time.time() > timeout_assist:
            abortar_com_erro("Timeout (60s). Supercruise Assist não apareceu no HUD.")
        if not procurar_template(templates['assist_active'], "ASSIST ACTIVE", MONITOR_CENTER, 0.75):
            contagem_limpo = 0 
        else:
            contagem_limpo += 1 
        time.sleep(1)

    # Viagem Longa
    print("A aguardar que o aviso de Assist desapareça (Chegada)...")
    contagem_limpo = 0
    timeout_viagem = time.time() + 1500 # 25 mins
    
    while contagem_limpo < 3:
        flags = ler_telemetria()
        if bool(flags & STATUS_FLAGS["INTERDICTION"]):
            abortar_com_erro("ALERTA CRÍTICO: Interdição detetada durante viagem!")
            
        if time.time() > timeout_viagem:
            abortar_com_erro("Timeout (25 mins). Viagem em supercruise excedeu o limite seguro.")

        if procurar_template(templates['assist_active'], "ASSIST ACTIVE", MONITOR_CENTER, 0.75):
            contagem_limpo = 0 
        else:
            contagem_limpo += 1 
        time.sleep(1)

    # Chegada
    print("\n>>> CHEGADA CONFIRMADA! A executar travagem e boost...")
    falar("Dropping from supercruise.")
    
    time.sleep(2.0)
    pydirectinput.press('tab') 
    time.sleep(15.0)
    # pydirectinput.press('tab') 
    # time.sleep(15.0)
    pydirectinput.press('x') 
    print(">>> Manobra concluída. A aguardar aproximação para docking.")

if __name__ == "__main__":
    inicializar_infraestrutura()

    print("Alinha o nariz da nave com o destino. Iniciando em 1s...")
    time.sleep(1)
    
    iniciar_salto_seguro()
    engatar_assistencia_menu()
    monitorar_viagem()
        
    if VISUAL_DEBUG:
        cv2.destroyAllWindows()
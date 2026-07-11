import os
import time
import pydirectinput
import cv2
import mss
import numpy as np
import pyttsx3

# ==========================================
# 1. SETUP E ÁREAS
# ==========================================
MONITOR_PANEL = {"top": 200, "left": 50, "width": 1000, "height": 1200}
MONITOR_MENU = {"top": 1100, "left": 1000, "width": 600, "height": 400}

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_imagens = os.path.join(diretorio_atual, 'images')

templates_nomes = {
    'nav_tab': 'NAVIGATION_SELECTED.png',
    'carrier': 'FLEET_CARRIER_NAME.png',
    'locked': 'LOCKED_DESTINATION.png',
    'unlocked': 'UNLOCKED_DESTINATION.png',
    'autolaunch': 'AUTO_LAUNCH.png',
    'noselection': 'NO_SELECTION.png'
}

templates = {}
try:
    for chave, nome_arq in templates_nomes.items():
        caminho = os.path.join(pasta_imagens, nome_arq)
        templates[chave] = cv2.imread(caminho, cv2.IMREAD_COLOR)
    print(f"[SISTEMA] Módulo de Voo Total carregado.")
except Exception as e:
    print(f"ERRO: {e}"); exit()

# --- Motor de Voz ---
engine = pyttsx3.init()
def falar(texto):
    print(f"[VOZ] {texto}")
    engine.say(texto)
    engine.runAndWait()

# ==========================================
# 2. MOTOR DE VISÃO
# ==========================================
def procurar_template(template, nome_label, monitor, threshold=0.80):
    with mss.mss() as sct:
        img_bgra = np.array(sct.grab(monitor))
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
        resultado = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(resultado)
        
        encontrou = max_val >= threshold
        cor = (0, 255, 0) if encontrou else (0, 0, 255)
        
        cv2.imshow("Ocular de Voo", img_bgr)
        cv2.moveWindow("Ocular de Voo", 1300, 50)
        cv2.waitKey(1)
        return encontrou

# ==========================================
# 3. ROTINAS DE VOO
# ==========================================

def marcar_destino():
    print("\n>>> FASE: Marcar Destino...")
    pydirectinput.press('1')
    time.sleep(1.2)
    
    # Navega para Nav Tab
    for _ in range(6):
        if procurar_template(templates['nav_tab'], "NAV", MONITOR_PANEL, 0.85): break
        pydirectinput.press('q'); time.sleep(0.5)
    
    pydirectinput.press('d'); time.sleep(0.5)
    
    # Procura Carrier
    achou = False
    for _ in range(30):
        if procurar_template(templates['carrier'], "ZAHIR", MONITOR_PANEL, 0.85):
            achou = True; break
        pydirectinput.press('s'); time.sleep(0.4)
    
    if achou:
        pydirectinput.press('space'); time.sleep(1.0)
        if procurar_template(templates['unlocked'], "UNLOCKED", MONITOR_PANEL, 0.80):
            pydirectinput.press('space'); time.sleep(0.5)
            print("[LOG] Destino trancado agora.")
        else:
            print("[LOG] Destino já estava trancado.")
    
    pydirectinput.press('1') # Fecha painel
    time.sleep(1.0)

def executar_auto_launch():
    print("\n>>> FASE: Auto-Launch...")
    # Garante que o menu está visível
    while not (procurar_template(templates['noselection'], "IDLE", MONITOR_MENU, 0.70) or
               procurar_template(templates['autolaunch'], "AL", MONITOR_MENU, 0.70)):
        time.sleep(0.5)
    
    for tecla in ['w', 'w', 's', 's', 's']:
        if procurar_template(templates['autolaunch'], "AUTO LAUNCH", MONITOR_MENU, 0.85):
            print(">>> Auto-Launch Ativado!")
            pydirectinput.press('space')
            return True
        pydirectinput.press(tecla)
        time.sleep(0.6)
    return False

def aguardar_saida_estacao():
    print("\n>>> FASE: Detetar saída da estação...")
    # O Auto-launch termina quando o HUD de menu desaparece por completo 
    # e voltamos a ver o cockpit limpo por vários segundos.
    contagem_limpo = 0
    while contagem_limpo < 10:
        # Se NÃO vir nenhum template de menu, a nave está a voar livre
        menu_aberto = (procurar_template(templates['noselection'], "HUD", MONITOR_MENU, 0.70) or 
                       procurar_template(templates['autolaunch'], "AL", MONITOR_MENU, 0.70))
        
        if not menu_aberto:
            contagem_limpo += 1
        else:
            contagem_limpo = 0 # Reset se ainda vir o menu
        time.sleep(1)
        print(f"A verificar estabilização de voo... {contagem_limpo}/10")

    falar("Auto launch terminated commander. please proceed to destination")

# ==========================================
# 4. SEQUÊNCIA DE ESPAÇO ABERTO
# ==========================================

def sequencia_salto():
    print("\n>>> FASE: Impulso e Salto...")
    
    print("Boost 1 (TAB)...")
    pydirectinput.press('tab')
    time.sleep(5)
    
    print("Boost 2 (TAB)...")
    pydirectinput.press('tab')
    time.sleep(3)
    
    print("A iniciar Salto (J)...")
    pydirectinput.press('j')

# ==========================================
# EXECUÇÃO PRINCIPAL
# ==========================================

if __name__ == "__main__":
    print("Bot pronto. Foca o jogo.")
    time.sleep(3)
    
    marcar_destino()
    if executar_auto_launch():
        aguardar_saida_estacao()
        sequencia_salto()
        print("\n>>> VIAGEM INICIADA! Boa sorte, Comandante. <<<")
    
    cv2.destroyAllWindows()
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

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_imagens = os.path.join(diretorio_atual, 'images')

templates_nomes = {
    'nav_tab': 'NAVIGATION_SELECTED.png',
    'carrier': 'FLEET_CARRIER_NAME.png',
    'locked': 'LOCKED_DESTINATION.png',
    'unlocked': 'UNLOCKED_DESTINATION.png'
}

templates = {}
try:
    for chave, nome_arq in templates_nomes.items():
        caminho = os.path.join(pasta_imagens, nome_arq)
        templates[chave] = cv2.imread(caminho, cv2.IMREAD_COLOR)
    print(f"[SISTEMA] Módulo: Selecionar Target (Carrier) carregado.")
except Exception as e:
    print(f"ERRO: {e}"); exit()

# --- Voz ---
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
        
        cv2.imshow("Ocular Navegacao", img_bgr)
        cv2.moveWindow("Ocular Navegacao", 1500, 50)
        cv2.waitKey(1)
        return encontrou

# ==========================================
# 3. LÓGICA DE MARCAÇÃO
# ==========================================
def marcar_destino_carrier():
    print("\n>>> FASE: Marcar Destino (Carrier)...")
    pydirectinput.press('1')
    time.sleep(1.2)
    
    for _ in range(6):
        if procurar_template(templates['nav_tab'], "NAV", MONITOR_PANEL, 0.85): break
        pydirectinput.press('q'); time.sleep(0.5)
    
    pydirectinput.press('d'); time.sleep(0.5)
    
    achou = False
    for _ in range(30):
        if procurar_template(templates['carrier'], "ZAHIR", MONITOR_PANEL, 0.9):
            print("\n>>> FASE: ACHOU (Carrier)...")
            time.sleep(2.4)
            achou = True; break
        pydirectinput.press('s'); time.sleep(0.4)
    
    if achou:
        print("\n>>> FASE: vai selecionar (Carrier)...")
        time.sleep(1.0)
        pydirectinput.press('space');
        print("\n>>> FASE: selecionou (Carrier)...")
        time.sleep(1.0)
        if procurar_template(templates['unlocked'], "UNLOCKED", MONITOR_PANEL, 0.80):
            pydirectinput.press('space'); time.sleep(0.5)
            falar("Carrier destination locked.")
        else:
            print("[LOG] Destino já estava trancado.")
            falar("Carrier already locked.")
    else:
        print("[ERRO] Carrier não encontrado na lista.")
    
    pydirectinput.press('1')
    time.sleep(1.0)

if __name__ == "__main__":
    time.sleep(3)
    marcar_destino_carrier()
    cv2.destroyAllWindows()
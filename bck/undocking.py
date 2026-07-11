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
MONITOR_MENU = {"top": 1100, "left": 1000, "width": 600, "height": 400}

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_imagens = os.path.join(diretorio_atual, 'images')

templates_nomes = {
    'autolaunch': 'AUTO_LAUNCH.png',
    'noselection': 'NO_SELECTION.png'
}

templates = {}
try:
    for chave, nome_arq in templates_nomes.items():
        caminho = os.path.join(pasta_imagens, nome_arq)
        templates[chave] = cv2.imread(caminho, cv2.IMREAD_COLOR)
    print(f"[SISTEMA] Módulo: Undocking e Salto carregado.")
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
def procurar_template(template, nome_label, monitor, threshold=0.70):
    with mss.mss() as sct:
        img_bgra = np.array(sct.grab(monitor))
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
        resultado = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(resultado)
        
        encontrou = max_val >= threshold
        
        cv2.imshow("Ocular Undocking", img_bgr)
        cv2.moveWindow("Ocular Undocking", 1300, 50)
        cv2.waitKey(1)
        return encontrou

# ==========================================
# 3. LÓGICA DE VOO
# ==========================================
def executar_auto_launch():
    print("\n>>> FASE: Auto-Launch...")
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
    contagem_limpo = 0
    while contagem_limpo < 10:
        menu_aberto = (procurar_template(templates['noselection'], "HUD", MONITOR_MENU, 0.70) or 
                       procurar_template(templates['autolaunch'], "AL", MONITOR_MENU, 0.70))
        
        if not menu_aberto:
            contagem_limpo += 1
        else:
            contagem_limpo = 0 
        time.sleep(1)
        print(f"A verificar estabilização de voo... {contagem_limpo}/10")

    falar("Auto launch terminated commander. Please proceed to destination.")

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
    falar("Frameshift drive charging.")

if __name__ == "__main__":
    time.sleep(3)
    if executar_auto_launch():
        aguardar_saida_estacao()
        sequencia_salto()
    cv2.destroyAllWindows()
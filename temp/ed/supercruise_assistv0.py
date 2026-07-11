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
MONITOR_CENTER = {"top": 100, "left": 400, "width": 1100, "height": 800}

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_imagens = os.path.join(diretorio_atual, 'images')

templates_nomes = {
    'nav_tab': 'NAVIGATION_SELECTED.png',
    'locked': 'LOCKED_DESTINATION.png',
    'assist_active': 'SUPERCRUISE_ASSIST_ACTIVE.png',
    'throttle_up': 'THROTTLE_UP.png' # A TUA NOVA ÂNCORA DE ACELERAÇÃO
}

templates = {}
try:
    for chave, nome_arq in templates_nomes.items():
        caminho = os.path.join(pasta_imagens, nome_arq)
        templates[chave] = cv2.imread(caminho, cv2.IMREAD_COLOR)
    print(f"[SISTEMA] Módulo Supercruise com Ciclo de Aceleração ativo.")
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
def procurar_template(template, nome_label, monitor, threshold=0.75):
    if template is None: return False
    with mss.mss() as sct:
        img_bgra = np.array(sct.grab(monitor))
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
        resultado = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(resultado)
        encontrou = max_val >= threshold
        
        cv2.imshow("Ocular Supercruise", img_bgr)
        cv2.moveWindow("Ocular Supercruise", 0, 0)
        cv2.waitKey(1)
        return encontrou

# ==========================================
# 3. SEQUÊNCIA DE LANÇAMENTO (COM CICLO DE ACELERAÇÃO)
# ==========================================

def iniciar_salto_e_assist():
    print(">>> Iniciando sequência de salto (J)...")
    pydirectinput.press('j')
    time.sleep(1.0)

    # --- CICLO DE ACELERAÇÃO CONTÍNUO ---
    print(">>> Verificando necessidade de aceleração...")
    # Ele tenta acelerar enquanto vir a mensagem de "Throttle Up"
    for _ in range(30): # Tenta durante 10 segundos
        if procurar_template(templates['throttle_up'], "THROTTLE UP NEEDED", MONITOR_CENTER, 0.75):
            print("[LOG] Mensagem detectada! Acelerando (.)...")
            pydirectinput.press('.')
            time.sleep(0.5)
        else:
            # Se a mensagem sumiu, o salto provavelmente começou
            print("[LOG] Mensagem desapareceu. Salto em progresso.")
            break
    
    falar("Jumping to supercruise. Please align if necessary.")
    time.sleep(20) # Tempo do túnel de salto

    # --- ATIVAÇÃO DO ASSIST ---
    pydirectinput.press('1')
    time.sleep(1.2)

    for _ in range(6):
        if procurar_template(templates['nav_tab'], "NAV", MONITOR_PANEL, 0.85):
            print(">>> NAV!")
            break
        pydirectinput.press('q'); time.sleep(0.5)
        print(">>> NEXT TAB...")
    else:
        print(">>> searching tab fail...")
        pydirectinput.press('1')
        return False

    print(">>> Seleciona o Target!")
    pydirectinput.press('space') # Seleciona o Target
    time.sleep(0.8)

    if procurar_template(templates['locked'], "LOCKED", MONITOR_PANEL, 0.85):
        print(">>> achou o LOCKED!")
        pydirectinput.press('d'); time.sleep(0.3)
        pydirectinput.press('space')
        print(">>> Supercruise Assist ATIVADO!")
    else:
        print(">>> falhou o LOCKED...")
    
    pydirectinput.press('1')
    return True

# ==========================================
# 4. MONITORIZAÇÃO DE CHEGADA (IGUAL AO ANTERIOR)
# ==========================================

def monitorar_chegada():
    print("\n>>> Fase de Cruzeiro. Aguardando presença do Assist...")
    time.sleep(10)

    # Espera o painel azul aparecer
    while True:
        if procurar_template(templates['assist_active'], "ASSIST ACTIVE", MONITOR_CENTER, 0.75):
            print("[LOG] Supercruise Assist detectado no HUD.")
            break
        time.sleep(1)

    # Espera o painel azul desaparecer (Chegada)
    print(">>> Viagem em curso... Aguardando chegada ao destino.")
    contagem_limpo = 0
    while contagem_limpo < 3:
        if not procurar_template(templates['assist_active'], "ASSIST ACTIVE", MONITOR_CENTER, 0.70):
            contagem_limpo += 1
        else:
            contagem_limpo = 0
        time.sleep(1)

    print(">>> DESTINO ALCANÇADO! Travando e Boost.")
    falar("Arrived at destination. Disengaging now.")
    pydirectinput.press('x') # Travagem
    time.sleep(2.0)
    pydirectinput.press('tab') # Boost final
    print(">>> Operação concluída com sucesso.")

if __name__ == "__main__":
    time.sleep(3)
    if iniciar_salto_e_assist():
        monitorar_chegada()
    cv2.destroyAllWindows()
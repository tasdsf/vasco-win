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
MONITOR_CENTER = {"top": 200, "left": 400, "width": 1100, "height": 600}

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_imagens = os.path.join(diretorio_atual, 'images')

templates_nomes = {
    'autolaunch': 'AUTO_LAUNCH.png',
    'noselection': 'NO_SELECTION.png',
    'auto_progress': 'AUTO_LAUNCH_PROGRESS.png' 
}

templates = {}
try:
    for chave, nome_arq in templates_nomes.items():
        caminho = os.path.join(pasta_imagens, nome_arq)
        templates[chave] = cv2.imread(caminho, cv2.IMREAD_COLOR)
    print(f"[SISTEMA] Módulo: Undocking Inteligente Seguro carregado.")
except Exception as e:
    print(f"ERRO: {e}"); exit()

# --- Voz ---
engine = pyttsx3.init()
voices = engine.getProperty('voices')
for voice in voices:
    if "EN-US" in voice.id.upper() or "ZIRA" in voice.id.upper():
        engine.setProperty('voice', voice.id)
        break

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
        cor = (0, 255, 0) if encontrou else (0, 0, 255)
        
        if encontrou:
            h, w = template.shape[:2]
            cv2.rectangle(img_bgr, max_loc, (max_loc[0] + w, max_loc[1] + h), cor, 2)
        
        cv2.putText(img_bgr, f"{nome_label}: {max_val:.2f}", (10, 30), 1, 1.2, (255, 255, 255), 2)
        cv2.imshow("Ocular Undocking", img_bgr)
        cv2.moveWindow("Ocular Undocking", 50, 50)
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
    time.sleep(2.0)
    
    # 1. ESPERA OBRIGATÓRIA PELO APARECIMENTO DO PAINEL
    print("A aguardar que o painel de Auto-Launch surja no ecrã...")
    while True: # Loop infinito até ver a imagem
        if procurar_template(templates['auto_progress'], "PROGRESSO", MONITOR_CENTER, 0.75):
            print("[LOG] Painel de Auto-Launch detetado! A manobra começou.")
            break
        time.sleep(0.5)
    
    # 2. ESPERA OBRIGATÓRIA PELO DESAPARECIMENTO DO PAINEL
    print("A voar para o exterior... A aguardar que o painel desapareça.")
    contagem_limpo = 0
    while contagem_limpo < 3: 
        if procurar_template(templates['auto_progress'], "PROGRESSO", MONITOR_CENTER, 0.70):
            contagem_limpo = 0 # O painel continua lá, reseta a contagem
        else:
            contagem_limpo += 1 # Está limpo
        
        time.sleep(1)

    print("[LOG] Ecrã limpo de forma consistente. Estamos no espaço aberto!")
    falar("Auto launch terminated commander. Please proceed to destination.")

def sequencia_salto():
    print("\n>>> FASE: Impulso e Salto...")
    print("Boost 1 (TAB)...")
    pydirectinput.press('tab')
    time.sleep(10)
    
    print("Boost 2 (TAB)...")
    pydirectinput.press('tab')

if __name__ == "__main__":
    time.sleep(3)
    if executar_auto_launch():
        aguardar_saida_estacao()
        sequencia_salto()
    cv2.destroyAllWindows()
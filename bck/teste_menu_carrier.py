import os
import time
import cv2
import mss
import numpy as np
import pyttsx3

# ==========================================
# 1. SETUP E ÁREA DO COCKPIT
# ==========================================
# Certifica-te que esta área foca apenas a zona dos botões holográficos
MONITOR_MENU = {"top": 1100, "left": 1000, "width": 600, "height": 400}

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_imagens = os.path.join(diretorio_atual, 'images')

templates_nomes = {
    'servicos': 'CARRIER_SERVICES.png',
    'autolaunch': 'AUTO_LAUNCH.png'
}

templates = {}
for chave, nome_arq in templates_nomes.items():
    caminho = os.path.join(pasta_imagens, nome_arq)
    img = cv2.imread(caminho, cv2.IMREAD_COLOR)
    if img is not None:
        templates[chave] = img

# --- Motor de Voz (English) ---
engine = pyttsx3.init()
voices = engine.getProperty('voices')
for voice in voices:
    if "EN-US" in voice.id.upper() or "ZIRA" in voice.id.upper():
        engine.setProperty('voice', voice.id)
        break

def falar(texto):
    print(f"[LOG] {texto}")
    engine.say(texto)
    engine.runAndWait()

# ==========================================
# 2. MOTOR DE VISÃO (WINDOW AT 50, 50)
# ==========================================
def procurar_template(template, nome_label, threshold=0.80):
    if template is None: return False, 0
    
    with mss.mss() as sct:
        img_bgra = np.array(sct.grab(MONITOR_MENU))
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
        resultado = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(resultado)
        
        encontrou = max_val >= threshold
        
        # --- DESENHO DE DIAGNÓSTICO ---
        cor = (0, 255, 0) if encontrou else (0, 0, 255)
        if encontrou:
            h, w = template.shape[:2]
            cv2.rectangle(img_bgr, max_loc, (max_loc[0] + w, max_loc[1] + h), cor, 2)
        
        # Mostra o nome do que está a procurar e a confiança atual
        cv2.putText(img_bgr, f"Searching: {nome_label}", (10, 30), 1, 1.2, (255, 255, 255), 2)
        cv2.putText(img_bgr, f"Match: {max_val:.2f} / Min: {threshold}", (10, 60), 1, 1.2, cor, 2)
        
        nome_janela = "Bot Vision - Cockpit Diagnostics"
        cv2.imshow(nome_janela, img_bgr)
        cv2.moveWindow(nome_janela, 50, 50) 
        cv2.setWindowProperty(nome_janela, cv2.WND_PROP_TOPMOST, 1)
        cv2.waitKey(1)
        
        return encontrou, max_val

# ==========================================
# 3. LOOP ALTERNADO COM VOZ E PAUSA
# ==========================================

def monitor_sequencial():
    print("Sequential Diagnostics started. Window at (50, 50).")
    
    while True:
        # --- BUSCA 1: AUTO LAUNCH ---
        found_auto, val_auto = procurar_template(templates.get('autolaunch'), "AUTO LAUNCH", 0.85)
        if found_auto:
            falar(f"Auto launch detected. Match score {val_auto:.2f}")
            time.sleep(2.0) # Pausa de 2 segundos após encontrar
        else:
            print(f"Auto Launch not found (Match: {val_auto:.2f})")

        time.sleep(0.1)

        # --- BUSCA 2: CARRIER SERVICES ---
        found_serv, val_serv = procurar_template(templates.get('servicos'), "CARRIER SERVICES", 0.85)
        if found_serv:
            falar(f"Carrier services detected. Match score {val_serv:.2f}")
            time.sleep(2.0) # Pausa de 2 segundos após encontrar
        else:
            print(f"Carrier Services not found (Match: {val_serv:.2f})")
        
        # Se nenhum dos dois for encontrado (ambos abaixo do threshold)
        if not found_auto and not found_serv:
            # Opcional: descomentar para falar quando nada for detetado
            # falar("Nothing detected") 
            pass

        time.sleep(0.1)

if __name__ == "__main__":
    time.sleep(2)
    try:
        monitor_sequencial()
    except KeyboardInterrupt:
        cv2.destroyAllWindows()
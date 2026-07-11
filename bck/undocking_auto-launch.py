import os
import time
import pydirectinput
import cv2
import mss
import numpy as np

# ==========================================
# 1. SETUP E ÁREAS (Painel Lateral Esquerdo)
# ==========================================
MONITOR_PANEL = {"top": 200, "left": 50, "width": 1000, "height": 1200}

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_imagens = os.path.join(diretorio_atual, 'images')

templates_nomes = {
    'nav_tab': 'NAVIGATION_SELECTED.png',
    'carrier': 'FLEET_CARRIER_NAME.png',
    'locked': 'LOCKED_DESTINATION.png',   # NOVO
    'unlocked': 'UNLOCKED_DESTINATION.png' # NOVO
}

templates = {}
try:
    for chave, nome_arq in templates_nomes.items():
        caminho = os.path.join(pasta_imagens, nome_arq)
        img = cv2.imread(caminho, cv2.IMREAD_COLOR)
        if img is None: raise FileNotFoundError(f"Falta: {caminho}")
        templates[chave] = img
    print(f"[SISTEMA] Módulo de Navegação Inteligente carregado ({len(templates)} templates).")
except Exception as e:
    print(f"ERRO: {e}"); exit()

# ==========================================
# 2. MOTOR DE VISÃO
# ==========================================
def procurar_template(template, nome_label, threshold=0.80):
    with mss.mss() as sct:
        img_bgra = np.array(sct.grab(MONITOR_PANEL))
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
        resultado = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(resultado)
        
        encontrou = max_val >= threshold
        cor = (0, 255, 0) if encontrou else (0, 0, 255)
        
        # Feedback visual (Canto Superior Direito)
        cv2.putText(img_bgr, f"Alvo: {nome_label}", (10, 30), 1, 1.2, (255, 255, 255), 2)
        cv2.putText(img_bgr, f"Match: {max_val:.2f}", (10, 60), 1, 1.2, cor, 2)
        cv2.imshow("Ocular de Navegação", img_bgr)
        cv2.moveWindow("Ocular de Navegação", 1300, 50)
        cv2.setWindowProperty("Ocular de Navegação", cv2.WND_PROP_TOPMOST, 1)
        cv2.waitKey(1)
        return encontrou

# ==========================================
# 3. ROTINA INTELIGENTE
# ==========================================

def marcar_carrier_zahir():
    print("\n>>> Abrindo painel lateral (1)...")
    pydirectinput.press('1')
    time.sleep(3.0)

    # 1. Encontrar a aba Navigation
    for _ in range(6):
        if procurar_template(templates['nav_tab'], "ABA NAVIGATION", 0.85):
            print("[LOG] Aba Navigation confirmada.")
            break
        pydirectinput.press('q')
        time.sleep(0.5)
    else:
        print("[ERRO] Falha ao localizar aba Navigation.")
        return False

    # 2. Procurar Carrier na lista
    pydirectinput.press('d') # Foco na lista
    time.sleep(0.3)

    carrier_focado = False
    for i in range(30):
        if procurar_template(templates['carrier'], "ZAHIR", 0.9):
            print(f"[LOG] Fleet Carrier Zahir encontrado no passo {i}.")
            carrier_focado = True
            break
        pydirectinput.press('s')
        time.sleep(0.7)

    if not carrier_focado:
        print("[ERRO] Carrier Zahir não encontrado.")
        pydirectinput.press('1') # Fecha para não ficar preso
        return False

    # 3. Validar Estado do Lock
    print(">>> Abrindo menu de contexto...")
    pydirectinput.press('space')
    time.sleep(1.2) # Tempo para o menu de opções abrir

    if procurar_template(templates['locked'], "STATUS: LOCKED", 0.85):
        print("[LOG] O destino JÁ ESTÁ trancado. Nada a fazer.")
    
    elif procurar_template(templates['unlocked'], "STATUS: UNLOCKED", 0.85):
        print("[LOG] O destino está destrancado. A efectuar LOCK...")
        pydirectinput.press('space') # Pressiona para trancar
        time.sleep(0.5)
    
    else:
        print("[AVISO] Não foi possível determinar o estado (Locked/Unlocked).")

    # 4. Voltar ao Cockpit
    print(">>> A fechar painel (1)...")
    pydirectinput.press('1')
    return True

if __name__ == "__main__":
    time.sleep(2)
    marcar_carrier_zahir()
    cv2.destroyAllWindows()
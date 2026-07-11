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
    'locked': 'LOCKED_DESTINATION.png',
    'unlocked': 'UNLOCKED_DESTINATION.png'
}

templates = {}
try:
    for chave, nome_arq in templates_nomes.items():
        caminho = os.path.join(pasta_imagens, nome_arq)
        img = cv2.imread(caminho, cv2.IMREAD_COLOR)
        if img is None: raise FileNotFoundError(f"Falta: {caminho}")
        templates[chave] = img
    print(f"[SISTEMA] Módulo Supercruise Assist carregado.")
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
        
        # Ocular de Diagnóstico no canto superior direito
        cv2.putText(img_bgr, f"Alvo: {nome_label}", (10, 30), 1, 1.2, (255, 255, 255), 2)
        cv2.putText(img_bgr, f"Match: {max_val:.2f}", (10, 60), 1, 1.2, cor, 2)
        cv2.imshow("Ocular Supercruise", img_bgr)
        cv2.moveWindow("Ocular Supercruise", 1300, 50)
        cv2.setWindowProperty("Ocular Supercruise", cv2.WND_PROP_TOPMOST, 1)
        cv2.waitKey(1)
        return encontrou

# ==========================================
# 3. ROTINA DE ASSISTÊNCIA
# ==========================================

def ativar_supercruise_assist():
    print("\n>>> Cortando motores (X)...")
    pydirectinput.press('x')
    time.sleep(0.5)

    print(">>> Abrindo painel de navegação (1)...")
    pydirectinput.press('1')
    time.sleep(1.0)

    # 1. Garantir que estamos na aba Navigation
    for _ in range(6):
        if procurar_template(templates['nav_tab'], "ABA NAVIGATION", 0.85):
            print("[LOG] Aba Navigation confirmada.")
            break
        pydirectinput.press('q')
        time.sleep(0.5)
    else:
        print("[ERRO] Não encontrei a aba de Navegação.")
        pydirectinput.press('1')
        return False

    # 2. Selecionar o target (assume-se que o target desejado já é o selecionado na lista)
    # No Elite, ao abrir o painel 1, o foco já costuma estar no destino atual
    print(">>> Abrindo menu do destino...")
    pydirectinput.press('space')
    time.sleep(1.0)

    # 3. Verificar estado e ativar Assist
    if procurar_template(templates['locked'], "LOCKED", 0.85):
        print("[LOG] Destino já está LOCKED. Ativando Supercruise Assist (D + SPACE)...")
        # Move para a direita (Supercruise Assist) e confirma
        pydirectinput.press('d')
        time.sleep(0.3)
        pydirectinput.press('space')
        print(">>> Supercruise Assist ATIVADO!")
    
    elif procurar_template(templates['unlocked'], "UNLOCKED", 0.85):
        print("[AVISO] Destino não estava trancado. Trancando agora...")
        # Se está unlocked, o primeiro botão é o Lock. Pressionamos Space.
        pydirectinput.press('space')
        time.sleep(0.5)
        # Após trancar, o menu fecha ou atualiza. 
        # Geralmente é preciso re-entrar para o Assist, mas alguns setups permitem 'd' logo.
        # Por segurança, apenas trancamos.
        print(">>> Destino trancado. Ativa o Assist manualmente ou reinicia o script.")
    
    else:
        print("[ERRO] Não consegui determinar o estado do destino.")

    # 4. Voltar ao Cockpit
    print(">>> Fechando painel (1)...")
    pydirectinput.press('1')
    return True

if __name__ == "__main__":
    print("Prepara a nave em direção ao destino. Iniciando em 3s...")
    time.sleep(3)
    ativar_supercruise_assist()
    cv2.destroyAllWindows()
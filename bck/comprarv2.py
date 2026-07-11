import os
import time
import pydirectinput
import cv2
import mss
import numpy as np

# ==========================================
# 1. SETUP E CALIBRAÇÃO DE ÁREAS
# ==========================================
MONITOR_MENU = {"top": 1100, "left": 1000, "width": 600, "height": 400}
# Área expandida para ver a lista e o botão EXIT no fundo
MONITOR_MARKET = {"top": 200, "left": 0, "width": 800, "height": 1400} 

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_imagens = os.path.join(diretorio_atual, 'images')

templates_nomes = {
    'servicos': 'STARPORT_SERVICES.png',
    'noselection': 'NO_SELECTION.png',
    'disembark': 'DISEMBARK.png',
    'market_off': 'COMMODITIES_MARKET_OFF.png',
    'market_on': 'COMMODITIES_MARKET_ON.png',
    'buy_on': 'BUY_SELECTED.png',
    'rare_on': 'RARE_SELECTED.png',
    'exit_on': 'EXIT_SELECTED.png'
}

templates = {}

try:
    for chave, nome_arq in templates_nomes.items():
        caminho = os.path.join(pasta_imagens, nome_arq)
        img = cv2.imread(caminho, cv2.IMREAD_COLOR)
        if img is None: raise FileNotFoundError(f"Falta imagem: {caminho}")
        templates[chave] = img
    print(f"[SISTEMA] {len(templates)} templates carregados!")
except Exception as e:
    print(f"ERRO: {e}"); exit()

# ==========================================
# 2. MOTOR DE VISÃO (Com Janela de Diagnóstico)
# ==========================================

def procurar_template(template, nome_label, monitor, threshold=0.80):
    with mss.mss() as sct:
        img_bgra = np.array(sct.grab(monitor))
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
        resultado = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(resultado)
        encontrou = max_val >= threshold
        
        # Debug Visual
        cor = (0, 255, 0) if encontrou else (0, 0, 255)
        if encontrou:
            h, w = template.shape[:2]
            cv2.rectangle(img_bgr, max_loc, (max_loc[0] + w, max_loc[1] + h), cor, 2)
        
        cv2.putText(img_bgr, f"Alvo: {nome_label}", (10, 30), 1, 1.2, (255, 255, 255), 2)
        cv2.putText(img_bgr, f"Match: {max_val:.2f} / {threshold}", (10, 60), 1, 1.2, cor, 2)
        
        # --- A MUDANÇA ESTÁ AQUI ---
        nome_janela = "Ocular do Bot - Diagnostico"
        cv2.imshow(nome_janela, img_bgr)
        
        # Move a janela para o canto superior direito (ajusta o 1300 se o teu monitor for maior)
        # x = 1300 (direita), y = 50 (topo)
        cv2.moveWindow(nome_janela, 1300, 50) 
        
        cv2.setWindowProperty(nome_janela, cv2.WND_PROP_TOPMOST, 1)
        cv2.waitKey(1)
        return encontrou

# ==========================================
# 3. FASES DE NAVEGAÇÃO
# ==========================================

def fase_1_entrar_servicos():
    print("\n>>> FASE 1: Menu Holográfico...")
    while not (procurar_template(templates['noselection'], "IDLE", MONITOR_MENU, 0.75) or 
               procurar_template(templates['disembark'], "DISEMBARK", MONITOR_MENU, 0.75) or
               procurar_template(templates['servicos'], "SERVICES", MONITOR_MENU)):
        time.sleep(0.5)
    
    time.sleep(1.2)
    for tecla in ['s', 's', 'w', 'w']:
        if procurar_template(templates['servicos'], "SERVICES", MONITOR_MENU):
            pydirectinput.press('space')
            return True
        pydirectinput.press(tecla)
        time.sleep(0.6)
    return False

def fase_2_abrir_mercado():
    print("\n>>> FASE 2: Abrindo Mercado...")
    while not (procurar_template(templates['market_off'], "MARKET OFF", MONITOR_MARKET) or 
               procurar_template(templates['market_on'], "MARKET ON", MONITOR_MARKET)):
        time.sleep(0.5)

    for tecla in ['s', 's', 'w', 'w']:
        if procurar_template(templates['market_on'], "MARKET ON", MONITOR_MARKET):
            pydirectinput.press('space')
            return True
        pydirectinput.press(tecla)
        time.sleep(0.6)
    return False

def fase_3_comprar_item():
    print("\n>>> FASE 3: Abrindo Mercado...")
    while not procurar_template(templates['buy_on'], "BUY ON", MONITOR_MARKET):
        time.sleep(0.5)
        
    print("\n>>> FASE 3: Procurando Fujin Tea...")
    time.sleep(2.0)
    pydirectinput.press('d')
    time.sleep(0.5)
    
    for i in range(40): 
        # 1. ITEM RARO ENCONTRADO (Threshold alto para cor amarela)
        if procurar_template(templates['rare_on'], "RARE FOUND", MONITOR_MARKET, 0.92):
            print(">>> ITEM DETETADO! Comprando...")
            pydirectinput.press('space')
            time.sleep(1.0)
            pydirectinput.keyDown('d')
            time.sleep(2.5)
            pydirectinput.keyUp('d')
            pydirectinput.press('s')
            time.sleep(0.5)
            pydirectinput.press('space') # Efectivação
            time.sleep(1.5)
            
            # Saída para Auto-Launch
            for _ in range(3):
                pydirectinput.press('backspace')
                time.sleep(0.8)
            return "COMPRADO"
        
        # 2. BOTÃO EXIT (Threshold mais baixo para o fundo do ecrã)
        if procurar_template(templates['exit_on'], "EXIT BUTTON", MONITOR_MARKET, 0.75):
            print(">>> Fim da lista. Item não disponível.")
            return "NAO_ENCONTRADO"
            
        pydirectinput.press('s')
        time.sleep(0.4)
    return "TIMEOUT"

# ==========================================
# 4. LOOP DE PERSISTÊNCIA (20 MINUTOS MAX)
# ==========================================

def executar_ciclo_completo():
    tempo_limite = 20 * 60  # 20 minutos em segundos
    inicio_contagem = time.time()
    
    while True:
        tempo_decorrido = time.time() - inicio_contagem
        if tempo_decorrido > tempo_limite:
            print("\n[!] TEMPO LIMITE ATINGIDO (20 min). Desistindo da compra.")
            return False

        print(f"\n--- INICIANDO TENTATIVA (Tempo decorrido: {int(tempo_decorrido/60)} min) ---")
        
        if fase_1_entrar_servicos():
            if fase_2_abrir_mercado():
                resultado = fase_3_comprar_item()
                
                if resultado == "COMPRADO":
                    print("\n>>> OPERAÇÃO CONCLUÍDA COM SUCESSO! <<<")
                    return True
                
                elif resultado == "NAO_ENCONTRADO":
                    print("\n[REPETIR] Item esgotado. Saindo e aguardando 2 minutos...")
                    # Clica no Exit que já está selecionado
                    pydirectinput.press('space')
                    time.sleep(1.5)
                    # Garante que volta ao Cockpit para resetar menus
                    pydirectinput.press('backspace')
                    
                    time.sleep(120) # 2 Minutos
                    continue

        print("\n[ERRO] Falha na navegação. Resetando HUD em 10s...")
        pydirectinput.press('backspace')
        time.sleep(10)

if __name__ == "__main__":
    print("Bot activo. Foca o jogo.")
    time.sleep(3)
    executar_ciclo_completo()
    cv2.destroyAllWindows()
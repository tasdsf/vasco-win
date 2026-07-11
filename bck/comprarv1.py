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
MONITOR_MARKET = {"top": 800, "left": 0, "width": 800, "height": 800} # TEUS VALORES

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_imagens = os.path.join(diretorio_atual, 'images')

templates_nomes = {
    'servicos': 'STARPORT_SERVICES.png',
    'noselection': 'NO_SELECTION.png',
    'disembark': 'DISEMBARK.png',
    'market_off': 'COMMODITIES_MARKET_OFF.png',
    'market_on': 'COMMODITIES_MARKET_ON.png',
    'rare_on': 'RARE_SELECTED.png',    # NOVO: Item amarelo selecionado
    'exit_on': 'EXIT_SELECTED.png'     # NOVO: Botão sair selecionado
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
# 2. MOTOR DE VISÃO
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
        cv2.putText(img_bgr, f"{nome_label}: {max_val:.2f}", (10, 30), 1, 1.2, cor, 2)
        cv2.imshow("Ocular do Bot", img_bgr)
        cv2.waitKey(1)
        return encontrou

# ==========================================
# 3. LÓGICA DE EXECUÇÃO
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
    """
    Retorna True se comprou e saiu, False se não encontrou.
    """
    print("\n>>> FASE 3: Procurando Fujin Tea...")
    time.sleep(2.0)
    pydirectinput.press('d')
    time.sleep(0.5)
    
    for _ in range(30): 
        # 1. ITEM ENCONTRADO
        if procurar_template(templates['rare_on'], "RARE FOUND", MONITOR_MARKET, 0.92):
            print(">>> ITEM DETETADO! Iniciando processo de compra...")
            pydirectinput.press('space') # Abre detalhes
            time.sleep(1.0)
            
            pydirectinput.keyDown('d')   # Enche o porão (2.5 segundos)
            time.sleep(2.5)
            pydirectinput.keyUp('d')
            
            pydirectinput.press('s')     # Desce para o botão de confirmação
            time.sleep(0.5)
            
            # --- EFECTIVAÇÃO DA COMPRA ---
            print(">>> Confirmando compra (SPACE)...")
            pydirectinput.press('space') 
            time.sleep(1.5)              # Espera o servidor processar a transação
            
            # --- SAÍDA PARA AUTO-LAUNCH (Os 3 Backspaces) ---
            print(">>> Compra efectivada. A sair para o menu principal...")
            for i in range(3):
                pydirectinput.press('backspace')
                print(f"Retroceder... ({i+1}/3)")
                time.sleep(0.8)          # Pausa para a animação de saída de cada menu
            
            return "COMPRADO"
        
        # 2. BOTÃO EXIT (ITEM NÃO DISPONÍVEL)
        if procurar_template(templates['exit_on'], "EXIT BUTTON", MONITOR_MARKET, 0.85):
            print(">>> Fim da lista. Item não encontrado.")
            return "NAO_ENCONTRADO"
            
        pydirectinput.press('s')
        time.sleep(0.4)
        
    return "FALHA_TIMEOUT"

def executar_bloco_comprar():
    while True:
        print("\n" + "="*40)
        print("INICIANDO CICLO DE COMPRA")
        print("="*40)
        
        if fase_1_entrar_servicos():
            if fase_2_abrir_mercado():
                resultado = fase_3_comprar_item()
                
                if resultado == "COMPRADO":
                    print("\n[SUCESSO] Mercadoria a bordo e menu Auto-Launch pronto!")
                    break # TERMINA O SCRIPT AQUI
                
                elif resultado == "NAO_ENCONTRADO":
                    print("\n[REPETIR] A sair e aguardar 2 minutos para novo stock...")
                    # Sair do mercado para não ficar a bloquear a interface
                    for _ in range(2): pydirectinput.press('backspace')
                    
                    time.sleep(120) # 2 Minutos de espera
                    continue # Reinicia do zero (Fase 1)
        
        print("\n[ERRO] Falha na sequência. Tentando reset em 10s...")
        pydirectinput.press('backspace')
        time.sleep(10)

# ==========================================
# EXECUÇÃO
# ==========================================
if __name__ == "__main__":
    print("Iniciando Bot. Foca o jogo.")
    time.sleep(3)
    
    if fase_1_entrar_servicos():
        if fase_2_abrir_mercado():
            if fase_3_comprar_item():
                print("\n>>> OPERAÇÃO CONCLUÍDA COM SUCESSO! <<<")
            else:
                print("\n>>> ITEM NÃO DISPONÍVEL. <<<")
    
    cv2.destroyAllWindows()
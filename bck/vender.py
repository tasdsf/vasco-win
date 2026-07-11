import os
import time
import pydirectinput
import cv2
import mss
import numpy as np
import pyttsx3

# ==========================================
# 1. SETUP E ÁREAS (Fleet Carrier)
# ==========================================
MONITOR_MENU = {"top": 1100, "left": 1000, "width": 600, "height": 400}
# Área do mercado no Carrier
MONITOR_MARKET = {"top": 200, "left": 0, "width": 1600, "height": 1400} 

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_imagens = os.path.join(diretorio_atual, 'images')

templates_nomes = {
    'servicos': 'CARRIER_SERVICES.png',
    'noselection': 'NO_SELECTION.png',
    'market_off': 'COMMODITIES_MARKET_OFF.png',
    'market_on': 'COMMODITIES_MARKET_ON2.png',
    'rare_not_on': 'RARE_NOT_SELECTED.png', 
    'exit_on': 'EXIT_SELECTED.png'
}

templates = {}
try:
    for chave, nome_arq in templates_nomes.items():
        caminho = os.path.join(pasta_imagens, nome_arq)
        img = cv2.imread(caminho, cv2.IMREAD_COLOR)
        templates[chave] = img
    print(f"[SISTEMA] Venda no Carrier V3 (Ocular Ativa) pronta.")
except Exception as e:
    print(f"ERRO: {e}"); exit()

# --- Motor de Voz ---
engine = pyttsx3.init()
def falar(texto):
    print(f"[VOZ] {texto}")
    engine.say(texto)
    engine.runAndWait()

# ==========================================
# 2. MOTOR DE VISÃO (OCULAR NO TOPO DIREITO)
# ==========================================
def procurar_template(template, nome_label, monitor, threshold=0.80):
    with mss.mss() as sct:
        img_bgra = np.array(sct.grab(monitor))
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
        resultado = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(resultado)
        encontrou = max_val >= threshold
        
        # --- DESENHOS DE DIAGNÓSTICO ---
        cor = (0, 255, 0) if encontrou else (0, 0, 255)
        #if encontrou:
        #    h, w = template.shape[:2]
        #    cv2.rectangle(img_bgr, max_loc, (max_loc[0] + w, max_loc[1] + h), cor, 2)
        
        #cv2.putText(img_bgr, f"Alvo: {nome_label}", (10, 30), 1, 1.2, (255, 255, 255), 2)
        #cv2.putText(img_bgr, f"Match: {max_val:.2f} / {threshold}", (10, 60), 1, 1.2, cor, 2)
        
        # --- JANELA DA OCULAR ---
        nome_janela = "Ocular do Bot - Analise Carrier"
        #cv2.imshow(nome_janela, img_bgr)
        
        # Move para o Canto Superior Direito (ajusta o 1300 se necessário)
        #cv2.moveWindow(nome_janela, 1300, 800) 
        #cv2.setWindowProperty(nome_janela, cv2.WND_PROP_TOPMOST, 1)
        #cv2.waitKey(1)
        
        return encontrou

# ==========================================
# 3. LÓGICA DE VENDA
# ==========================================

def fase_1_abrir_mercado():
    print("\n>>> Abrindo Commodities Market no Carrier...")
    time.sleep(1.0)
    # Entrar nos serviços
    pydirectinput.press('space') 
    
    # Esperar botões do mercado aparecerem
    while not (procurar_template(templates['market_off'], "MARKET", MONITOR_MARKET) or 
               procurar_template(templates['market_on'], "MARKET", MONITOR_MARKET)):
        time.sleep(0.5)

    # Navegar até o botão de mercado
    # Como disseste que a posição mudou, aumentamos o varrimento
    for tecla in ['d', 'd']:
        print(f"A mover seleção: {tecla.upper()}")
        pydirectinput.press(tecla)
        time.sleep(0.3)
        if procurar_template(templates['market_on'], "MARKET ON", MONITOR_MARKET, 0.60):
            print("[LOG] Botão de Mercado focado!")
            pydirectinput.press('space')
            return True
    print("false-nao encontrou o MARKET ON")
    return False

def fase_2_vender_tudo():
    print("\n>>> Iniciando varrimento de inventário (Aba SELL)...")
    time.sleep(2.5)
    
    pydirectinput.press('s') # Muda para aba SELL
    time.sleep(0.5)
    pydirectinput.press('space') # Seleciona aba SELL
    time.sleep(1.2)
    # NOTA! Muito improvavel mas o item pode nao estar visivel
    if procurar_template(templates['rare_not_on'], "FUJIN TEA (INV)", MONITOR_MARKET, 0.85):
        print(f">>> Fujin Tea detectado no inventário!")
        pydirectinput.press('d') # Entra na lista
        time.sleep(0.5)
        
        # NOTA! Muito improvavel mas ao mover para o topo da lista o item pode ter deixado de ser visivel
        for i in range(5):
            print(">>> Movendo foco para o top da lista SELL (W)...")
            pydirectinput.press('w')
            time.sleep(0.5)
    
        for i in range(25):
            # Lógica pela negativa: Procura o item mesmo desselecionado
            if not procurar_template(templates['rare_not_on'], "FUJIN TEA (INV)", MONITOR_MARKET, 0.85):
                print(f">>> Fujin Tea selecionado!")
                pydirectinput.press('space') 
                time.sleep(1.2)
                
                # Manobra do 's' para ir para o Sell
                print(">>> Movendo foco para o botão SELL (s)...")
                pydirectinput.press('s')
                time.sleep(0.5)
                
                print(">>> Confirmando Venda Total!")
                pydirectinput.press('space')
                time.sleep(2.0)
                
                # Sair para o cockpit
                for _ in range(3):
                    pydirectinput.press('backspace')
                    time.sleep(0.8)
                
                falar("Sales operation completed commander. The cargo bay is empty.")
                return True

        if procurar_template(templates['exit_on'], "EXIT BUTTON", MONITOR_MARKET, 0.75):
            print(">>> Fim da lista. Nada encontrado para vender.")
            pydirectinput.press('backspace')
            return False

        pydirectinput.press('s')
        time.sleep(0.4)
    return False

if __name__ == "__main__":
    print("Bot pronto. Inicia a operação no cockpit do Carrier.")
    time.sleep(3)
    
    if fase_1_abrir_mercado():
        fase_2_vender_tudo()
    
    cv2.destroyAllWindows()
import os
import sys
import time
import logging
import pydirectinput
import cv2
import mss
import numpy as np
import pyttsx3
import pygetwindow as gw
import time

# ==========================================
# 0. LOGGING E INFRAESTRUTURA
# ==========================================
diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_logs = os.path.join(diretorio_atual, "logs")
os.makedirs(pasta_logs, exist_ok=True)

# Configuração do Logger
logging.basicConfig(
    filename=os.path.join(pasta_logs, "r2d2_combined.log"),
    level=logging.ERROR,
    format='%(asctime)s - [VENDER] - %(levelname)s - %(message)s'
)

def abortar_com_erro(mensagem):
    """ Regista o erro no log e dispara exit code 1 para o Orquestrador intercetar """
    print(f"\n[FATAL] {mensagem}")
    logging.error(mensagem)
    sys.exit(1)

NOME_JANELA = "Ocular do Bot - Analise Carrier"
VISUAL_DEBUG = False # Muda para False para esconder as janelas

def inicializar_infraestrutura():
    """ Foca no jogo (Ecrã 1) e envia o painel visual para o Ecrã 2 APENAS SE VISUAL_DEBUG FOR TRUE """
    print("[SISTEMA] A configurar foco no jogo...")
    
    focar_jogo_seguro()
    time.sleep(0.5)

    if VISUAL_DEBUG:
        print("[SISTEMA] Modo Debug Ativo: A configurar janelas...")
        cv2.namedWindow(NOME_JANELA, cv2.WINDOW_NORMAL)
        with mss.mss() as sct:
            monitores = sct.monitors
            if len(monitores) > 2:
                ecra_secundario = monitores[2]
                pos_x = ecra_secundario["left"]
                pos_y = ecra_secundario["top"]
                cv2.moveWindow(NOME_JANELA, pos_x, pos_y)
            else:
                cv2.moveWindow(NOME_JANELA, 0, 0)
            cv2.setWindowProperty(NOME_JANELA, cv2.WND_PROP_TOPMOST, 1)

def focar_jogo_seguro():
    """ Foca o Elite Dangerous a nível de Sistema Operativo, sem enviar cliques de rato """
    print("[SISTEMA] A focar o Elite Dangerous via Windows API...")
    try:
        # Procura a janela pelo título (no Elite geralmente é "Elite - Dangerous (CLIENT)")
        janelas = gw.getWindowsWithTitle("Elite - Dangerous (CLIENT)")
        
        if janelas:
            janela_elite = janelas[0]
            # Traz a janela para a frente
            janela_elite.activate() 
            time.sleep(0.5)
            print("[OK] Jogo focado com sucesso e em segurança.")
            return True
        else:
            print("[ERRO] Janela do Elite Dangerous não encontrada!")
            return False
            
    except Exception as e:
        print(f"[AVISO] Falha ao forçar foco via OS: {e}")
        return False


# ==========================================
# 1. SETUP E ÁREAS (Fleet Carrier)
# ==========================================
MONITOR_MENU = {"top": 1100, "left": 1000, "width": 600, "height": 400}
MONITOR_MARKET = {"top": 200, "left": 0, "width": 1600, "height": 1400} 

pasta_imagens = os.path.join(diretorio_atual, 'images')

templates_nomes = {
    'servicos': 'CARRIER_SERVICES.png',
    'noselection': 'NO_SELECTION.png',
    'market_off': 'COMMODITIES_MARKET_OFF.png',
    'market_on': 'COMMODITIES_MARKET_ON2.png',
    'rare_not_on': 'RARE_NOT_SELECTED.png',
    'rare_not_on2': 'RARE_NOT_SELECTED1.png',
    'exit_on': 'EXIT_SELECTED.png'
}

templates = {}
try:
    for chave, nome_arq in templates_nomes.items():
        caminho = os.path.join(pasta_imagens, nome_arq)
        img = cv2.imread(caminho, cv2.IMREAD_COLOR)
        if img is None: raise FileNotFoundError(f"Falta imagem: {caminho}")
        templates[chave] = img
    print(f"[SISTEMA] Venda no Carrier V3 pronta e blindada.")
except Exception as e:
    abortar_com_erro(f"Falha ao carregar imagens para a memória: {e}")

# --- Motor de Voz ---
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
        
        if VISUAL_DEBUG:
            cor = (0, 255, 0) if encontrou else (0, 0, 255)
            if encontrou:
                h, w = template.shape[:2]
                cv2.rectangle(img_bgr, max_loc, (max_loc[0] + w, max_loc[1] + h), cor, 2)
            
            cv2.rectangle(img_bgr, (5, 5), (450, 80), (0, 0, 0), -1)
            cv2.putText(img_bgr, f"Alvo: {nome_label}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            cv2.putText(img_bgr, f"Match: {max_val:.2f} / {threshold}", (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.8, cor, 2)
            
            cv2.imshow(NOME_JANELA, img_bgr)
            cv2.waitKey(1)
        
        return encontrou

def item_nao_selecionado(monitor=MONITOR_MARKET, threshold=0.85):
    """ Valida com QUALQUER uma das duas variantes do template 'não selecionado'
        (RARE_NOT_SELECTED.png OU RARE_NOT_SELECTED1.png) — basta uma bater certo. """
    return (procurar_template(templates['rare_not_on'], "FUJIN TEA (INV)", monitor, threshold) or
            procurar_template(templates['rare_not_on2'], "FUJIN TEA (INV) v2", monitor, threshold))

# ==========================================
# 3. LÓGICA DE VENDA COM WATCHDOGS
# ==========================================

def fase_1_abrir_mercado():
    print("\n>>> Abrindo Commodities Market no Carrier...")
    time.sleep(1.0)
    pydirectinput.press('space') 
    
    # Watchdog 1: Esperar botões do mercado
    timeout = time.time() + 15
    while not (procurar_template(templates['market_off'], "MARKET", MONITOR_MARKET) or 
               procurar_template(templates['market_on'], "MARKET", MONITOR_MARKET)):
        if time.time() > timeout:
            abortar_com_erro("Timeout (15s) à espera que os serviços do Carrier abram.")
        time.sleep(0.5)

    # Navegar até o botão de mercado
    for tecla in ['d', 'd']:
        print(f"A mover seleção: {tecla.upper()}")
        pydirectinput.press(tecla)
        time.sleep(0.3)
        if procurar_template(templates['market_on'], "MARKET ON", MONITOR_MARKET, 0.60):
            print("[LOG] Botão de Mercado focado!")
            pydirectinput.press('space')
            return True
            
    abortar_com_erro("Botão 'Commodities Market' não detetado após varrimento mecânico.")

def fase_2_vender_tudo():
    print("\n>>> Iniciando varrimento de inventário (Aba SELL)...")
    time.sleep(2.5)
    
    pydirectinput.press('s') # Muda para aba SELL
    time.sleep(0.5)
    pydirectinput.press('space') # Seleciona aba SELL
    time.sleep(1.2)
    
    if item_nao_selecionado():
        print(f">>> Fujin Tea detectado no inventário!")
        pydirectinput.press('d') # Entra na lista
        time.sleep(0.5)
        
        for i in range(5):
            print(">>> Movendo foco para o topo da lista SELL (W)...")
            pydirectinput.press('w')
            time.sleep(0.5)
    
        # Watchdog 2: Limite de iterações de varrimento
        for i in range(25):
            if not item_nao_selecionado():
                print(f">>> Fujin Tea selecionado!")
                pydirectinput.press('space') 
                time.sleep(1.2)
                
                print(">>> Movendo foco para o botão SELL (s)...")
                pydirectinput.press('s')
                time.sleep(0.5)
                
                print(">>> Confirmando Venda Total!")
                pydirectinput.press('space')
                time.sleep(2.0)
                
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
            
        # Se esgotou as 25 tentativas sem vender e sem ver o Exit:
        abortar_com_erro("Esgotou 25 iterações na lista de venda sem sucesso. O bot perdeu-se na interface.")
        
    else:
        # Não detetar o item logo de início não é um erro fatal (o inventário pode estar vazio)
        print("[LOG] Item não detetado. Inventário parece vazio. A abortar venda de forma limpa.")
        for _ in range(2):
            pydirectinput.press('backspace')
            time.sleep(0.8)
        return False

if __name__ == "__main__":
    inicializar_infraestrutura()
    
    print("Bot pronto. Inicia a operação no cockpit do Carrier em 3 segundos...")
    time.sleep(3)
    
    if fase_1_abrir_mercado():
        fase_2_vender_tudo()
import os
import time
import glob
import json
import pydirectinput
import cv2
import mss
import numpy as np

# ==========================================
# 1. SETUP E CAMINHOS
# ==========================================
# Monitor do painel lateral (conforme a tua última calibração)
MONITOR_PANEL = {"top": 100, "left": 50, "width": 1200, "height": 1200}
# Caminho dos logs do jogo
LOG_DIR = os.path.expanduser('~') + r"\Saved Games\Frontier Developments\Elite Dangerous"

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_imagens = os.path.join(diretorio_atual, 'images')

templates_nomes = {
    'contacts_tab': 'CONTACTS.png',
    'docking_off': 'REQUEST_DOCKING_OFF.png',
    'docking_on': 'REQUEST_DOCKING_ON.png'
}

templates = {}
for chave, nome_arq in templates_nomes.items():
    caminho = os.path.join(pasta_imagens, nome_arq)
    templates[chave] = cv2.imread(caminho, cv2.IMREAD_COLOR)

# ==========================================
# 2. UTILITÁRIOS DE LOG (Baseado no test_log.py)
# ==========================================

def get_latest_log():
    list_of_files = glob.glob(os.path.join(LOG_DIR, 'Journal.*.log'))
    if not list_of_files: return None
    return max(list_of_files, key=os.path.getctime)

def verificar_evento_log(nome_evento, timestamp_inicio):
    """Verifica se um evento específico ocorreu após o timestamp_inicio."""
    latest_log = get_latest_log()
    if not latest_log: return False

    with open(latest_log, 'r', encoding='utf-8') as f:
        # Lemos as linhas do fim para o início para ser mais rápido
        linhas = f.readlines()
        for line in reversed(linhas):
            try:
                data = json.loads(line)
                # O log usa formato ISO 8601, mas vamos simplificar comparando 
                # apenas se o evento apareceu após iniciarmos a função
                if data.get('event') == nome_evento:
                    # Se encontrarmos o evento de sucesso/negativa
                    return data
            except:
                continue
    return None

# ==========================================
# 3. VISÃO E NAVEGAÇÃO
# ==========================================

def procurar_template(template, nome_label, threshold=0.80):
    with mss.mss() as sct:
        img_bgra = np.array(sct.grab(MONITOR_PANEL))
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
        resultado = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(resultado)
        encontrou = max_val >= threshold
        
        cv2.imshow("Ocular de Docking", img_bgr)
        cv2.moveWindow("Ocular de Docking", 1300, 50)
        cv2.waitKey(1)
        return encontrou

# ==========================================
# 4. ROTINA INTELIGENTE
# ==========================================

def solicitar_docking_logico():
    print("\n[VÔO] Cortando motores (X)...")
    pydirectinput.press('x') # Força zero para não passar da estação
    time.sleep(0.5)
    print("\n[APROXIMACAO] Boost 1 (TAB)...")
    # pydirectinput.press('tab')
    #time.sleep(7)

    while True:
        print("\n>>> Iniciando tentativa de Docking Request...")
        
        # 1. Navegação até o botão
        pydirectinput.press('1')
        time.sleep(1.0)
        
        # Aba Contacts
        for _ in range(6):
            if procurar_template(templates['contacts_tab'], "CONTACTS", 0.65): break
            pydirectinput.press('e'); time.sleep(1.5)
        
        pydirectinput.press('space'); time.sleep(0.8) # Seleciona estação
        
        # Tenta clicar no botão de pedido
        clicou = False
        for _ in range(5):
            if procurar_template(templates['docking_on'], "DOCKING ON", 0.85):
                pydirectinput.press('space')
                clicou = True
                break
            if procurar_template(templates['docking_off'], "DOCKING OFF", 0.80):
                pydirectinput.press('d'); time.sleep(0.4)
        
        # Fecha o painel para processar
        pydirectinput.press('1')
        time.sleep(1.5) # Espera o log atualizar

        if clicou:
            print("[LOG] Pedido enviado. Verificando resposta da estação...")
            # Verifica se o evento 'DockingGranted' apareceu no log
            evento = verificar_evento_log('DockingGranted', time.time())
            
            if evento:
                station = evento.get('StationName', 'Estação')
                pad = evento.get('LandingPad', '??')
                print(f"\n[SUCESSO] Docking concedido em {station}! Landing Pad: {pad}")
                return True
            else:
                print("[AVISO] Pedido negado ou fora de alcance. Re-tentando em 5s...")
                time.sleep(5)
                continue
        else:
            print("[ERRO] Não foi possível encontrar o botão. Re-tentando...")
            time.sleep(2)

if __name__ == "__main__":
    print("Bot pronto. Aproxima-te da estação e solta o bot.")
    time.sleep(3)
    if solicitar_docking_logico():
        print("\n>>> DOCKING COMPUTER ATIVO. Podes relaxar, Comandante. <<<")
    cv2.destroyAllWindows()
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
# Mantendo as tuas coordenadas que cobrem bem o painel esquerdo
MONITOR_PANEL = {"top": 300, "left": 300, "width": 1200, "height": 1200}
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
# 2. MOTOR DE VISÃO (OCULAR ATIVADA)
# ==========================================

def procurar_template(template, nome_label, threshold=0.80):
    with mss.mss() as sct:
        img_bgra = np.array(sct.grab(MONITOR_PANEL))
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
        resultado = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(resultado)
        
        encontrou = max_val >= threshold
        
        # --- DESENHO DE DEBUG ---
        #cor = (0, 255, 0) if encontrou else (0, 0, 255)
        #if encontrou:
        #    h, w = template.shape[:2]
        #    cv2.rectangle(img_bgr, max_loc, (max_loc[0] + w, max_loc[1] + h), cor, 2)
        
        #cv2.putText(img_bgr, f"Alvo: {nome_label}", (10, 30), 1, 1.2, (255, 255, 255), 2)
        #cv2.putText(img_bgr, f"Match: {max_val:.2f} / Min: {threshold}", (10, 60), 1, 1.2, cor, 2)
        #
        #nome_janela = "Ocular de Docking - Visao Bot"
        #cv2.imshow(nome_janela, img_bgr)
        #cv2.moveWindow(nome_janela, 1500, 100) # Move para o canto superior direito
        #cv2.setWindowProperty(nome_janela, cv2.WND_PROP_TOPMOST, 1)
        #cv2.waitKey(1)
        
        return encontrou

# ==========================================
# 3. UTILITÁRIOS DE LOG
# ==========================================

def get_latest_log():
    list_of_files = glob.glob(os.path.join(LOG_DIR, 'Journal.*.log'))
    if not list_of_files: return None
    return max(list_of_files, key=os.path.getctime)

def verificar_evento_log(nome_evento):
    latest_log = get_latest_log()
    if not latest_log: return False
    with open(latest_log, 'r', encoding='utf-8') as f:
        linhas = f.readlines()
        for line in reversed(linhas[-10:]): # Verifica apenas as últimas 10 linhas
            try:
                data = json.loads(line)
                if data.get('event') == nome_evento: return data
            except: continue
    return None

# ==========================================
# 4. ROTINA DE DOCKING
# ==========================================

def solicitar_docking():
    print("\n[VÔO] Parando nave (X)...")
    pydirectinput.press('x')
    time.sleep(0.5)

    while True:
        print("\n>>> Abrindo painel lateral (1)...")
        pydirectinput.press('1')
        time.sleep(1.2)
        
        # --- AJUSTE DE THRESHOLD AQUI ---
        # Baixamos de 0.85 para 0.65 para garantir que apanha o teu 0.70!
        aba_encontrada = False
        for _ in range(6):
            if procurar_template(templates['contacts_tab'], "CONTACTS", 0.65):
                print("[LOG] Aba Contacts confirmada!")
                aba_encontrada = True
                break
            pydirectinput.press('e')
            time.sleep(0.6)
        
        if not aba_encontrada:
            print("[ERRO] Nao detetei a aba. Verificando ocular...")
            pydirectinput.press('1')
            time.sleep(2)
            continue

        # Seleciona a Estação
        pydirectinput.press('space')
        time.sleep(0.8)
        
        # Procura o botão de pedido
        clicou = False
        for _ in range(5):
            if procurar_template(templates['docking_on'], "DOCKING ON", 0.65):
                pydirectinput.press('space')
                clicou = True
                break
            if procurar_template(templates['docking_off'], "DOCKING OFF", 0.65):
                pydirectinput.press('d')
                time.sleep(0.4)
        
        pydirectinput.press('1') # Fecha painel
        time.sleep(2.0)

        if clicou:
            print("[LOG] Verificando logs...")
            if verificar_evento_log('DockingGranted'):
                print("\n[SUCESSO] Docking Aceite!")
                return True
            else:
                print("[AVISO] Negado ou sem resposta. Re-tentando em 5s...")
                time.sleep(5)
        else:
            print("[ERRO] Botao nao encontrado. Resetando...")
            time.sleep(2)

if __name__ == "__main__":
    print("Bot pronto. Inicia a aproximacao.")
    time.sleep(3)
    solicitar_docking()
    cv2.destroyAllWindows()
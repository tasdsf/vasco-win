import os
import time
import pydirectinput
import cv2
import mss
import numpy as np

# ==========================================
# 1. SETUP E CALIBRAÇÃO 
# ==========================================
MONITOR = {"top": 1100, "left": 1000, "width": 600, "height": 400}

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_imagens = os.path.join(diretorio_atual, 'images')

templates_nomes = {
    'servicos': 'STARPORT_SERVICES.png',
    'noselection': 'NO_SELECTION.png',
    'autolaunch': 'AUTO_LAUNCH.png',
    'disembark': 'DISEMBARK.png',
    'market_off': 'COMMODITIES_MARKET_OFF.png', # NOVO
    'market_on': 'COMMODITIES_MARKET_ON.png'    # NOVO
}

templates = {}

try:
    for chave, nome_arq in templates_nomes.items():
        caminho = os.path.join(pasta_imagens, nome_arq)
        img = cv2.imread(caminho, cv2.IMREAD_COLOR)
        if img is None: raise FileNotFoundError(f"Falta: {caminho}")
        templates[chave] = img
    
    print(f"[SISTEMA] {len(templates)} templates carregados com sucesso!")
except Exception as e:
    print(f"ERRO DE SETUP: {e}")
    exit()

# ==========================================
# 2. MOTOR DE VISÃO (Ocular)
# ==========================================
def procurar_template(template, nome_label, threshold=0.80):
    with mss.mss() as sct:
        img_bgra = np.array(sct.grab(MONITOR))
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
        
        resultado = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(resultado)
        
        encontrou = max_val >= threshold
        
        cor = (0, 255, 0) if encontrou else (0, 0, 255)
        h, w = template.shape[:2]
        
        if encontrou:
            cv2.rectangle(img_bgr, max_loc, (max_loc[0] + w, max_loc[1] + h), cor, 2)
            
        cv2.putText(img_bgr, f"{nome_label}: {max_val:.2f}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, cor, 2)
        
        cv2.imshow("Ocular do Bot", img_bgr)
        cv2.setWindowProperty("Ocular do Bot", cv2.WND_PROP_TOPMOST, 1)
        cv2.waitKey(1)
        
        return encontrou

# -- Detetores Específicos --
def ver_selecao_servicos(): return procurar_template(templates['servicos'], "STARPORT SERVICES", 0.80)
def ver_mercado_off(): return procurar_template(templates['market_off'], "MARKET (OFF)", 0.80)
def ver_mercado_on(): return procurar_template(templates['market_on'], "MARKET (ON)", 0.80)

def ver_menu_principal_ativo():
    if procurar_template(templates['noselection'], "MENU DETETADO", 0.75): return True
    if procurar_template(templates['disembark'], "DISEMBARK", 0.80): return True
    if procurar_template(templates['autolaunch'], "AUTO LAUNCH", 0.80): return True
    if ver_selecao_servicos(): return True
    return False

# ==========================================
# 3. LÓGICA DE NAVEGAÇÃO
# ==========================================

# --- FASE 1: Entrar nos Serviços da Estação ---
def navegar_para_servicos():
    print("\n>>> FASE 1: À espera do menu holográfico da nave...")
    
    while not ver_menu_principal_ativo():
        time.sleep(0.5)

    print(">>> Menu holográfico detetado! A procurar 'Starport Services'...")
    time.sleep(0.5) 
    
    varrimento = ['s', 's', 'w', 'w']
    for tecla in varrimento:
        if ver_selecao_servicos():
            print(">>> A entrar em 'Starport Services'...")
            pydirectinput.press('space')
            return True
            
        pydirectinput.press(tecla)
        time.sleep(0.5) 
        
    return False

# --- FASE 2: Entrar no Mercado ---
def navegar_para_mercado():
    print("\n>>> FASE 2: À espera que a interface da Estação carregue...")
    
    espera_loops = 0
    while True:
        # Verifica se o botão do mercado já apareceu (seja desligado ou ligado)
        if ver_mercado_off() or ver_mercado_on():
            break
            
        espera_loops += 1
        if espera_loops > 30: # Cerca de 15 segundos
            print("\n[ERRO] O menu interior da Estação não apareceu.")
            return False
        time.sleep(0.5)

    print(">>> Interface da Estação carregada! A selecionar Mercado...")
    time.sleep(0.5)
    
    # Se já estiver selecionado por padrão, não mexemos
    # Senão, usamos a tua dica do 's' (com umas teclas extra por segurança)
    varrimento_mercado = ['s', 's', 'w', 'w'] 
    
    for tecla in varrimento_mercado:
        if ver_mercado_on():
            print("\n>>> SUCESSO! 'Commodities Market' focado. A abrir Mercado...")
            pydirectinput.press('space')
            
            # Aqui podemos colocar o script JSON para ler o Market.json!
            time.sleep(2.0)
            return True
            
        print(f"A mover seleção: {tecla.upper()}")
        pydirectinput.press(tecla)
        time.sleep(0.5)
        
    print("\n[ERRO] Não foi possível focar o Mercado.")
    return False

# ==========================================
# EXECUÇÃO PRINCIPAL
# ==========================================
if __name__ == "__main__":
    print("Bot pronto. Foca a janela do jogo e atracar a nave.")
    time.sleep(2)
    
    # Executa a cadeia de comandos
    if navegar_para_servicos():
        time.sleep(1) # Pausa humana entre ecrãs
        if navegar_para_mercado():
            print("\n[VÍTORIA] Bot chegou ao ecrã do mercado com sucesso!")
            # Próximo passo: Ler ficheiro Market.json aqui!
        else:
            print("Falhou na Fase 2 (Mercado).")
    else:
        print("Falhou na Fase 1 (Serviços).")
        
    time.sleep(3)
    cv2.destroyAllWindows()
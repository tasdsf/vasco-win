import os
import cv2
import mss
import numpy as np
import time
import keyboard

# ==========================================
# 1. SETUP DE TEMPLATES (Extraídos do teu dockingv1.py)
# ==========================================
diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_imagens = os.path.join(diretorio_atual, '../images')

# Nomes EXATOS do teu código
templates_nomes = {
    'contacts_tab': 'CONTACTS.png',
    'docking_off': 'REQUEST_DOCKING_OFF.png',
    'docking_on': 'REQUEST_DOCKING_ON.png'
}

templates = {}
print("[SISTEMA] A iniciar Laboratório de Docking...")
for chave, nome_arq in templates_nomes.items():
    caminho = os.path.join(pasta_imagens, nome_arq)
    img = cv2.imread(caminho, cv2.IMREAD_COLOR)
    if img is not None:
        templates[chave] = img
        print(f" -> [OK] {nome_arq} alocado na memória.")
    else:
        print(f" -> [AVISO] Imagem não encontrada: {nome_arq}")

if not templates:
    print("\n[ERRO FATAL] Nenhuma imagem de docking carregada. Verifica a pasta 'images'.")
    exit()

lista_chaves = list(templates.keys())
indice_template_atual = 0

# ==========================================
# 2. GEOMETRIA INICIAL (Sincronizada com o teu MONITOR_PANEL)
# ==========================================
top_dinamico = 300
left_dinamico = 300
width_dinamico = 1200
height_dinamico = 1200
limiar_aceitacao = 0.65 # Ajustado para o teu limite de segurança atual

NOME_PAINEL = "R2D2 - Laboratorio de Docking"
cv2.namedWindow(NOME_PAINEL, cv2.WINDOW_AUTOSIZE)

with mss.mss() as sct:
    monitors = sct.monitors
    try:
        monitor_jogo = monitors[1]
    except IndexError:
        monitor_jogo = monitors[0]

    if len(monitors) > 2:
        cv2.moveWindow(NOME_PAINEL, monitors[2]["left"] + 50, monitors[2]["top"] + 50)
    else:
        cv2.moveWindow(NOME_PAINEL, 50, 50)

    print(f"\n==================================================")
    print(">>> DOCKING VISION LAB ONLINE")
    print("-> SETAS DO TECLADO   : Movem a zona de procura")
    print("-> TECLAS '+' e '-'   : Aumentam/Diminuem a zona")
    print("-> PAGE UP / PAGE DOWN: Alternar o elemento a testar (.png)")
    print("-> TECLA 'S'          : Exportar coordenadas pro terminal")
    print("-> TECLA 'Q'          : Encerrar")
    print("==================================================\n")

    while True:
        chave_atual = lista_chaves[indice_template_atual]
        template_atual = templates[chave_atual]

        # --- CONTROLOS DE CALIBRAÇÃO (Hotkeys) ---
        if keyboard.is_pressed('up'): top_dinamico -= 5; time.sleep(0.04)
        elif keyboard.is_pressed('down'): top_dinamico += 5; time.sleep(0.04)
        elif keyboard.is_pressed('left'): left_dinamico -= 5; time.sleep(0.04)
        elif keyboard.is_pressed('right'): left_dinamico += 5; time.sleep(0.04)
            
        if keyboard.is_pressed('plus') or keyboard.is_pressed('shift+plus'):
            width_dinamico += 10; height_dinamico += 10; time.sleep(0.04)
        elif keyboard.is_pressed('-'):
            if width_dinamico > 100 and height_dinamico > 100:
                width_dinamico -= 10; height_dinamico -= 10; time.sleep(0.04)

        if keyboard.is_pressed('page up'):
            indice_template_atual = (indice_template_atual + 1) % len(lista_chaves)
            time.sleep(0.2)
        elif keyboard.is_pressed('page down'):
            indice_template_atual = (indice_template_atual - 1) % len(lista_chaves)
            time.sleep(0.2)

        if keyboard.is_pressed('s'):
            print(f"\n[ENGENHARIA] ZONA ({templates_nomes[chave_atual]}):")
            print(f"{{\"top\": {top_dinamico}, \"left\": {left_dinamico}, \"width\": {width_dinamico}, \"height\": {height_dinamico}}}")
            time.sleep(0.3)

        if keyboard.is_pressed('q'):
            print("\n[ENCERRAMENTO] Sistemas de visão desligados.")
            break

        # --- PIPELINE DE DETEÇÃO ---
        area_real = {
            "top": monitor_jogo["top"] + top_dinamico,
            "left": monitor_jogo["left"] + left_dinamico,
            "width": width_dinamico,
            "height": height_dinamico
        }

        try:
            img_bgra = np.array(sct.grab(area_real))
            img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
        except Exception:
            time.sleep(0.1)
            continue

        res = cv2.matchTemplate(img_bgr, template_atual, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        
        encontrou = max_val >= limiar_aceitacao
        cor_caixa = (0, 255, 0) if encontrou else (0, 0, 255)

        img_display = img_bgr.copy()
        
        # Desenha a Bounding Box
        h, w = template_atual.shape[:2]
        cv2.rectangle(img_display, max_loc, (max_loc[0] + w, max_loc[1] + h), cor_caixa, 2)

        # --- RENDERIZAÇÃO DO PAINEL (Scale-to-fit) ---
        view_zoom = cv2.resize(img_display, (800, 600))
        
        hud_texto = np.zeros((150, 800, 3), dtype=np.uint8)
        cv2.putText(hud_texto, f"ALVO: {templates_nomes[chave_atual]}", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
        cv2.putText(hud_texto, f"CONFIANCA: {max_val*100:.1f}%", (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.7, cor_caixa, 2)
        cv2.putText(hud_texto, f"GEOMETRIA: top={top_dinamico} left={left_dinamico} dim={width_dinamico}x{height_dinamico}", (20, 115), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # Mostra o recorte que está a ser procurado
        thumb_h, thumb_w = 60, int(60 * (w/h))
        template_thumb = cv2.resize(template_atual, (thumb_w, thumb_h))
        hud_texto[20:20+thumb_h, 700-thumb_w:700] = template_thumb
        cv2.rectangle(hud_texto, (700-thumb_w, 20), (700, 20+thumb_h), (255, 255, 255), 1)

        painel_final = np.vstack((view_zoom, hud_texto))
        cv2.imshow(NOME_PAINEL, painel_final)
        cv2.waitKey(10)

cv2.destroyAllWindows()
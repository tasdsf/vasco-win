import os
import cv2
import mss
import numpy as np
import time
import keyboard

# ==========================================
# 1. SETUP E ZONAMENTO (ROIs)
# ==========================================
ZONES = {
    'panel': {"top": 200, "left": 50, "width": 1000, "height": 1200},
    'center': {"top": 100, "left": 400, "width": 1100, "height": 800}
}

TEMPLATES_CONFIG = {
    'nav_tab':       {'zone': ZONES['panel'], 'file':  'NAVIGATION_SELECTED.png'},
    'locked':        {'zone': ZONES['panel'], 'file':  'LOCKED_DESTINATION.png'},
    'unlocked':      {'zone': ZONES['panel'], 'file':  'UNLOCKED_DESTINATION.png'},
    'assist_active': {'zone': ZONES['center'], 'file': 'SUPERCRUISE_ASSIST_ACTIVE.png'},
    'throttle_up':   {'zone': ZONES['center'], 'file': 'THROTTLE_UP.png'}
}

# ==========================================
# 2. CARREGAMENTO DE IMAGENS E PREPARAÇÃO
# ==========================================
diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_imagens = os.path.join(diretorio_atual, '../images')

templates_carregados = {}
print("\n[SISTEMA] A carregar templates de visão...")
for chave, config in TEMPLATES_CONFIG.items():
    caminho_img = os.path.join(pasta_imagens, config['file'])
    img = cv2.imread(caminho_img, cv2.IMREAD_COLOR)
    if img is not None:
        templates_carregados[chave] = img
        print(f"[OK] {config['file']} carregado.")
    else:
        print(f"[ERRO] Imagem não encontrada: {caminho_img}")

NOME_JANELA = "R2D2 - Laboratorio de Supercruise"
cv2.namedWindow(NOME_JANELA, cv2.WINDOW_NORMAL)
cv2.resizeWindow(NOME_JANELA, 1280, 720) 

# ==========================================
# 3. INICIALIZAÇÃO DE ECRÃS E LOOP VISUAL
# ==========================================
with mss.mss() as sct:
    monitors = sct.monitors
    
    # Sincronização do Monitor do Jogo
    try: monitor_jogo = monitors[1]
    except IndexError: monitor_jogo = monitors[0]

    # --- LÓGICA DE MULTI-MONITOR ---
    # monitors[0] é o ecrã virtual global, [1] é o primário, [2] é o secundário
    if len(monitors) > 2:
        ecra_secundario = monitors[2]
        cv2.moveWindow(NOME_JANELA, ecra_secundario["left"] + 50, ecra_secundario["top"] + 50)
        print(f"[SISTEMA] Janela de diagnóstico redirecionada para o ecrã secundário.")
    else:
        cv2.moveWindow(NOME_JANELA, 50, 50)
        print(f"[AVISO] Ecrã secundário não detetado. Janela sobreposta ao jogo.")

    print(f"\n==================================================")
    print(">>> LAB SUPERCRUISE ONLINE")
    print("-> CAIXAS AZUIS  : Limites das Zonas de Procura (ROIs)")
    print("-> CAIXAS VERDES : Template Detetado (Match >= 75%)")
    print("-> TECLA 'Q'     : Fechar o laboratório")
    print("==================================================\n")

    while True:
        if keyboard.is_pressed('q'):
            print("[SISTEMA] A encerrar laboratório...")
            break

        area_total = {
            "top": monitor_jogo["top"], "left": monitor_jogo["left"],
            "width": monitor_jogo["width"], "height": monitor_jogo["height"]
        }
        
        try:
            img_bgra_full = np.array(sct.grab(area_total))
            img_bgr_full = cv2.cvtColor(img_bgra_full, cv2.COLOR_BGRA2BGR)
        except Exception:
            continue

        for nome_zona, dims in ZONES.items():
            pt1 = (dims["left"], dims["top"])
            pt2 = (dims["left"] + dims["width"], dims["top"] + dims["height"])
            cv2.rectangle(img_bgr_full, pt1, pt2, (255, 100, 0), 2)
            cv2.putText(img_bgr_full, f"ZONA: {nome_zona.upper()}", (dims["left"] + 5, dims["top"] + 20), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 100, 0), 2)

        y_texto = 30 
        cv2.putText(img_bgr_full, "TELEMETRIA DE CORRESPONDENCIA (THRESHOLD >= 0.75):", (20, y_texto), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        y_texto += 35

        for chave, config in TEMPLATES_CONFIG.items():
            if chave not in templates_carregados:
                continue
                
            zona = config['zone']
            template_img = templates_carregados[chave]
            th, tw = template_img.shape[:2]

            roi_bgr = img_bgr_full[zona['top']:zona['top']+zona['height'], zona['left']:zona['left']+zona['width']]
            
            res = cv2.matchTemplate(roi_bgr, template_img, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)

            cor_texto = (0, 0, 255) 
            estado = "AUSENTE"
            
            if max_val >= 0.50:
                cor_texto = (0, 165, 255) 
                estado = "VISIVEL (FRACO)"
                
            if max_val >= 0.75:
                cor_texto = (0, 255, 0) 
                estado = "TRANCADO"
                real_x = zona['left'] + max_loc[0]
                real_y = zona['top'] + max_loc[1]
                cv2.rectangle(img_bgr_full, (real_x, real_y), (real_x + tw, real_y + th), (0, 255, 0), 3)
                cv2.putText(img_bgr_full, f"{chave.upper()}", (real_x, real_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            linha_log = f"[{chave}] -> Match: {max_val*100:.1f}% | {estado}"
            cv2.putText(img_bgr_full, linha_log, (20, y_texto), cv2.FONT_HERSHEY_SIMPLEX, 0.6, cor_texto, 2)
            y_texto += 30

        cv2.imshow(NOME_JANELA, img_bgr_full)
        cv2.waitKey(40) 

cv2.destroyAllWindows()
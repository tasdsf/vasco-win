import os
import json
import time
import cv2
import mss
import numpy as np
import pydirectinput
import keyboard
from collections import deque

# ==========================================
# 1. SETUP E DETEÇÃO DE MONITORES
# ==========================================
pydirectinput.PAUSE = 0
BOT_ATIVO = False
ultimo_log_acao = "Aguardando..."
teclas_atuais = {"w": False, "s": False, "a": False, "d": False}

# Configurações do Alvo
MONITOR_CONFIG = {"top": 1180, "left": 970, "width": 80, "height": 90}
CX_ALVO, CY_ALVO, DEAD_ZONE = 42, 42, 4
LIMITE_AREA_CHEIA = 65

historico_coords = deque(maxlen=5)
historico_status = deque(maxlen=5)

def organizar_janelas():
    """Deteta monitores e organiza as janelas automaticamente."""
    with mss.mss() as sct:
        monitores = sct.monitors
        # monitors[0] é o conjunto, monitors[1] é o principal, monitors[2] o secundário
        has_second = len(monitores) > 2
        
        cv2.namedWindow("Bot Vision", cv2.WINDOW_NORMAL)
        cv2.namedWindow("Ocular Mask", cv2.WINDOW_NORMAL)
        cv2.namedWindow("Telemetria Pro", cv2.WINDOW_NORMAL)
        
        if has_second:
            # Segundo Monitor: Organização Vertical
            base_x = monitores[2]['left'] + 50
            base_y = monitores[2]['top'] + 50
            cv2.moveWindow("Bot Vision", base_x, base_y)
            cv2.moveWindow("Ocular Mask", base_x, base_y + 350)
            cv2.moveWindow("Telemetria Pro", base_x, base_y + 700)
            print(f"[SISTEMA] Dois monitores detetados. Janelas alinhadas VERTICALMENTE no Monitor 2.")
        else:
            # Monitor Único: Organização Horizontal
            base_x = 50
            base_y = 50
            cv2.moveWindow("Bot Vision", base_x, base_y)
            cv2.moveWindow("Ocular Mask", base_x + 350, base_y)
            cv2.moveWindow("Telemetria Pro", base_x + 700, base_y)
            print(f"[SISTEMA] Um monitor detetado. Janelas alinhadas HORIZONTALMENTE.")

# ==========================================
# 2. INTERFACE E TELEMETRIA (COM TIMESTAMPS)
# ==========================================
def draw_telemetry(status, area):
    img = np.zeros((450, 600, 3), dtype=np.uint8)
    cor_bot = (0, 255, 0) if BOT_ATIVO else (0, 0, 255)
    
    cv2.putText(img, f"BOT STATUS: {'ATIVO' if BOT_ATIVO else 'OFF'}", (20, 40), 1, 1.5, cor_bot, 2)
    
    # Mensagem de Alinhamento Central
    if "CENTER" in status and "FULL" in status:
        cv2.putText(img, ">> ALVO CENTRADO! <<", (20, 85), 1, 1.5, (0, 255, 0), 2)
    else:
        cv2.putText(img, f"ALVO: {status}", (20, 85), 1, 1.2, (255, 255, 255), 1)
    
    # Monitor de Teclas
    cv2.putText(img, "TECLAS ATIVAS:", (20, 130), 1, 1.0, (150, 150, 150), 1)
    for i, (k, v) in enumerate(teclas_atuais.items()):
        cor_k = (0, 255, 0) if v else (40, 40, 40)
        cv2.rectangle(img, (20 + (i*65), 140), (75 + (i*65), 195), cor_k, -1)
        cv2.putText(img, k.upper(), (38 + (i*65), 180), 1, 1.5, (255, 255, 255), 2)

    # Histórico de Ação com Hora
    cv2.rectangle(img, (20, 220), (580, 280), (30, 30, 30), -1)
    cv2.putText(img, "LOG DE COMANDO:", (30, 240), 1, 0.9, (150, 150, 150), 1)
    cv2.putText(img, ultimo_log_acao, (30, 265), 1, 1.0, (0, 255, 255), 1)

    cv2.imshow("Telemetria Pro", img)
    cv2.waitKey(1)

# ==========================================
# 3. VISÃO E CONTROLO PROPORCIONAL
# ==========================================
def analyze_compass(img_bgr, l_t, u_t):
    hsv = cv2.cvtColor(cv2.GaussianBlur(img_bgr, (3, 3), 0), cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, l_t, u_t)
    area = cv2.countNonZero(mask)
    M = cv2.moments(mask)
    
    status, pos, dists = "NO TARGET", None, (0, 0)
    if area > 5:
        tx = int(M["m10"] / M["m00"]) if M["m00"] > 0 else CX_ALVO
        ty = int(M["m01"] / M["m00"]) if M["m00"] > 0 else CY_ALVO
        historico_coords.append((tx, ty))
        avg_x = int(np.mean([p[0] for p in historico_coords]))
        avg_y = int(np.mean([p[1] for p in historico_coords]))
        
        dx, dy = avg_x - CX_ALVO, avg_y - CY_ALVO
        f_state = "FULL" if area > LIMITE_AREA_CHEIA else "EMPTY"
        h = "CENTER" if abs(dx) < DEAD_ZONE else ("LEFT" if dx < 0 else "RIGHT")
        v = "CENTER" if abs(dy) < DEAD_ZONE else ("TOP" if dy < 0 else "DOWN")
        status = f"{f_state}-{v}-{h}" if not (h=="CENTER" and v=="CENTER") else f"{f_state}-CENTER"
        dists = (abs(dx), abs(dy))
            
    return status, (tx, ty) if area > 5 else None, mask, area, dists

def press_key(key, state):
    global teclas_atuais
    if state:
        pydirectinput.keyDown(key)
        teclas_atuais[key] = True
    else:
        pydirectinput.keyUp(key)
        teclas_atuais[key] = False

def execute_maneuver(status, area, dists):
    global ultimo_log_acao
    if not BOT_ATIVO or ("CENTER" in status and "FULL" in status):
        for k in teclas_atuais: press_key(k, False)
        return

    dx, dy = dists
    dur_h = min(1.0, (dx / 40.0)) + 0.2
    dur_v = min(1.0, (dy / 40.0)) + 0.2
    if "EMPTY" in status or "NO TARGET" in status: dur_v = 1.0

    keys = []
    if "TOP" in status or "EMPTY" in status or "NO TARGET" in status: keys.append(('w', dur_v))
    elif "DOWN" in status: keys.append(('s', dur_v))
    if "LEFT" in status: keys.append(('a', dur_h))
    elif "RIGHT" in status: keys.append(('d', dur_h))

    if keys:
        timestamp = time.strftime("%H:%M:%S") # Timestamp adicionado
        ultimo_log_acao = f"[{timestamp}] " + " | ".join([f"{k.upper()} ({d:.1f}s)" for k, d in keys])
        
        for k, _ in keys: press_key(k, True)
        
        # Loop interno para atualizar as cores das teclas na janela
        start = time.time()
        max_dur = max([d for _, d in keys])
        while time.time() - start < max_dur:
            draw_telemetry(status, area) # Atualiza a janela ENQUANTO as teclas estão premidas[cite: 4]
            elapsed = time.time() - start
            for k, d in keys:
                if elapsed >= d: press_key(k, False)
            if keyboard.is_pressed('esc'): break
            time.sleep(0.01)
        
        for k, _ in keys: press_key(k, False)
        time.sleep(1.5)

# ==========================================
# 4. LOOP PRINCIPAL
# ==========================================
def run_bot():
    global BOT_ATIVO
    organizar_janelas()
    
    diretorio_atual = os.path.dirname(os.path.abspath(__file__))
    arquivo_memoria = os.path.join(diretorio_atual, "memoria_bussola.json")
    
    # Carrega memória de cor
    if os.path.exists(arquivo_memoria):
        with open(arquivo_memoria, 'r') as f:
            memoria = sorted(json.load(f), key=lambda x: x['usos'], reverse=True)
    else:
        memoria = [{"min": [79, 52, 71], "max": [108, 255, 255], "usos": 1}]

    with mss.mss() as sct:
        while True:
            # Correção COLOR_BGRA2BGR[cite: 4]
            img_raw = np.array(sct.grab(MONITOR_CONFIG))
            img_bgr = cv2.cvtColor(img_raw, cv2.COLOR_BGRA2BGR)
            
            if keyboard.is_pressed('space'):
                BOT_ATIVO = not BOT_ATIVO
                for k in teclas_atuais: press_key(k, False)
                time.sleep(0.3)
            
            if keyboard.is_pressed('esc'): break

            found = False
            for config in memoria:
                status, coords, mask, area, dists = analyze_compass(img_bgr, np.array(config['min']), np.array(config['max']))
                if area > 5:
                    found = True
                    historico_status.append(status)
                    status_suave = max(set(historico_status), key=historico_status.count)
                    
                    # Desenho HUD centralizado[cite: 4]
                    cv2.rectangle(img_bgr, (CX_ALVO-DEAD_ZONE, CY_ALVO-DEAD_ZONE), (CX_ALVO+DEAD_ZONE, CY_ALVO+DEAD_ZONE), (255,255,255), 1)
                    if coords: cv2.circle(img_bgr, coords, 4, (0, 255, 0), -1)
                    
                    cv2.imshow("Bot Vision", img_bgr)
                    cv2.imshow("Ocular Mask", mask)
                    
                    draw_telemetry(status_suave, area)
                    execute_maneuver(status_suave, area, dists)
                    BOT_ATIVO = False
                    break

            if not found and BOT_ATIVO:
                draw_telemetry("NO TARGET", 0)
                execute_maneuver("NO TARGET", 0, (40, 40))

            if cv2.waitKey(1) & 0xFF == ord('q'): break

    cv2.destroyAllWindows()

if __name__ == "__main__":
    run_bot()
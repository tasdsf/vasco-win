import mss
import cv2
import numpy as np
import time
import pydirectinput
import keyboard

# --- CONFIGURAÇÕES E ESTADOS ---
pydirectinput.PAUSE = 0
BOT_ATIVO = False
ultimo_tempo_centrado = time.time()
PRECISA_SOLTAR_TECLAS = True

def apply_clahe(img_bgr):
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    cl = clahe.apply(l)
    limg = cv2.merge((cl, a, b))
    return cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)

def analyze_compass(img_bgr):
    img_enhanced = apply_clahe(img_bgr)
    
    # Range mais robusto para evitar perder o alvo no centro
    lower_target = np.array([15, 40, 50]) 
    upper_target = np.array([115, 255, 255])
    
    cX_center, cY_center = 50, 55
    dead_zone = 12 # Espaço de folga no centro para evitar oscilação
    
    hsv = cv2.cvtColor(img_enhanced, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lower_target, upper_target)
    
    # Contagem de área e momentos
    area = cv2.countNonZero(mask)
    M = cv2.moments(mask)
    
    state_msg = "NO TARGET"
    target_pos = None
    
    if area > 5: # Se houver sinal mínimo
        if M["m00"] > 0:
            tx = int(M["m10"] / M["m00"])
            ty = int(M["m01"] / M["m00"])
        else:
            coords_p = np.column_stack(np.where(mask > 0))
            ty, tx = np.mean(coords_p, axis=0).astype(int)
            
        target_pos = (tx, ty)
        fill_state = "FULL" if area > 35 else "EMPTY"
        
        dx, dy = tx - cX_center, ty - cY_center
        
        # Lógica de Quadrantes
        h_dir = "CENTER" if abs(dx) < dead_zone else ("LEFT" if dx < 0 else "RIGHT")
        v_dir = "CENTER" if abs(dy) < dead_zone else ("TOP" if dy < 0 else "DOWN")
        
        if h_dir == "CENTER" and v_dir == "CENTER":
            state_msg = f"{fill_state} - CENTER_WAIT"
        else:
            state_msg = f"{fill_state} - {v_dir} {h_dir}"
            
    return state_msg, target_pos, mask, area, img_enhanced

def control_ship(status):
    global ultimo_tempo_centrado, PRECISA_SOLTAR_TECLAS
    
    if not BOT_ATIVO:
        for key in ['w', 's', 'a', 'd']: pydirectinput.keyUp(key)
        return

    # 1. EMERGÊNCIA: Se estiver centrado, PARAR TUDO e SAIR da função
    if "CENTER_WAIT" in status:
        if PRECISA_SOLTAR_TECLAS:
            for key in ['w', 's', 'a', 'd']: pydirectinput.keyUp(key)
            PRECISA_SOLTAR_TECLAS = False
        return # Impede que execute qualquer movimento abaixo

    # 2. BUSCA: Se perder alvo ou estiver atrás
    if "NO TARGET" in status or "EMPTY" in status:
        pydirectinput.keyDown('s') # Pitch Up
        pydirectinput.keyUp('w')
        PRECISA_SOLTAR_TECLAS = True
        return

    # 3. MOVIMENTO ATIVO (FULL e Fora do Centro)
    PRECISA_SOLTAR_TECLAS = True # Garante que soltará ao entrar no centro
    
    # Pitch
    if "TOP" in status:
        pydirectinput.keyDown('s')
        pydirectinput.keyUp('w')
    elif "DOWN" in status:
        pydirectinput.keyDown('w')
        pydirectinput.keyUp('s')
    else:
        pydirectinput.keyUp('w'); pydirectinput.keyUp('s')

    # Yaw
    if "LEFT" in status:
        pydirectinput.keyDown('a')
        pydirectinput.keyUp('d')
    elif "RIGHT" in status:
        pydirectinput.keyDown('d')
        pydirectinput.keyUp('a')
    else:
        pydirectinput.keyUp('a'); pydirectinput.keyUp('d')

def run_bot():
    global BOT_ATIVO
    monitor = {"top": 1200, "left": 905, "width": 100, "height": 110}
    
    print(">>> Script Iniciado. Pressione 'X' manualmente ou aguarde...")
    pydirectinput.press('x') 

    with mss.mss() as sct:
        while True:
            # Captura e conversão
            img_bgra = np.array(sct.grab(monitor))
            img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
            
            # Toggle de Ativação
            if keyboard.is_pressed('space'):
                BOT_ATIVO = not BOT_ATIVO
                print(f"BOT STATUS: {BOT_ATIVO}")
                time.sleep(0.3)
            
            if keyboard.is_pressed('esc'): break

            # Processamento
            status, coords, mask, area_val, enhanced = analyze_compass(img_bgr)
            
            # Controlo da Nave
            control_ship(status)
            
            # --- VISUALS ---
            # Desenha a zona morta (Retângulo Cinza)
            cv2.rectangle(img_bgr, (38, 43), (62, 67), (150, 150, 150), 1)
            
            if coords:
                color = (0, 255, 0) if "CENTER_WAIT" in status else (0, 165, 255)
                cv2.circle(img_bgr, coords, 4, color, -1)
                cv2.putText(img_bgr, f"Area: {area_val}", (5, 40), 1, 0.8, (255,255,255), 1)

            cv2.putText(img_bgr, status, (5, 95), 1, 0.9, (0, 255, 0), 1)
            
            # Feedback de ON/OFF
            mode_txt = "ON" if BOT_ATIVO else "OFF"
            mode_col = (0, 255, 0) if BOT_ATIVO else (0, 0, 255)
            cv2.putText(img_bgr, f"BOT: {mode_txt}", (5, 20), 1, 1, mode_col, 2)

            cv2.imshow("Final Result", img_bgr)
            cv2.imshow("Mask Debug", mask)
            
            if cv2.waitKey(1) & 0xFF == ord('q'): break

    cv2.destroyAllWindows()

if __name__ == "__main__":
    run_bot()
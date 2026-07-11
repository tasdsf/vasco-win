import mss
import cv2
import numpy as np
import time
import pydirectinput
import keyboard

# --- CONFIGURAÇÕES ---
pydirectinput.PAUSE = 0
BOT_ATIVO = False
ultimo_alvo_visto = time.time()

def analyze_compass(img_bgr):
    # Imagem direta, apenas um blur leve para estabilidade
    img_smooth = cv2.GaussianBlur(img_bgr, (3, 3), 0)
    hsv = cv2.cvtColor(img_smooth, cv2.COLOR_BGR2HSV)
    
    # Filtro focado no Azul da Bússola (Hue 80-115)
    # Saturation 15 para não cegar no sol
    lower_target = np.array([80, 15, 50]) 
    upper_target = np.array([115, 255, 255])
    
    mask = cv2.inRange(hsv, lower_target, upper_target)
    
    # Limpeza de ruído
    kernel = np.ones((3,3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    
    cX_center, cY_center = 50, 55
    dead_zone = 12 
    
    area = cv2.countNonZero(mask)
    M = cv2.moments(mask)
    
    state_msg = "NO TARGET"
    target_pos = None
    
    if area > 3:
        if M["m00"] > 0:
            tx, ty = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
        else:
            coords_p = np.column_stack(np.where(mask > 0))
            ty, tx = np.mean(coords_p, axis=0).astype(int)
            
        target_pos = (tx, ty)
        fill_state = "FULL" if area > 30 else "EMPTY"
        
        dx, dy = tx - cX_center, ty - cY_center
        h_dir = "CENTER" if abs(dx) < dead_zone else ("LEFT" if dx < 0 else "RIGHT")
        v_dir = "CENTER" if abs(dy) < dead_zone else ("TOP" if dy < 0 else "DOWN")
        
        if h_dir == "CENTER" and v_dir == "CENTER":
            state_msg = f"{fill_state}-CENTER"
        else:
            state_msg = f"{fill_state}-{v_dir}-{h_dir}"
            
    return state_msg, target_pos, mask, area

def release_all():
    """Garante que nenhuma tecla de direção fica presa."""
    for key in ['w', 's', 'a', 'd']:
        pydirectinput.keyUp(key)

def control_ship(status):
    global ultimo_alvo_visto
    
    if not BOT_ATIVO:
        release_all()
        return

    # Se o alvo está visível, atualizamos o tempo
    if "NO TARGET" not in status:
        ultimo_alvo_visto = time.time()

    # 1. PRIORIDADE MÁXIMA: CENTRO
    if "CENTER" in status:
        release_all()
        return

    # 2. SE O ALVO ESTÁ ATRÁS (EMPTY) OU PERDIDO
    # Só faz Pitch Up (S) se realmente não houver comandos de alinhamento
    if "NO TARGET" in status or "EMPTY" in status:
        if (time.time() - ultimo_alvo_visto) > 0.7 or "EMPTY" in status:
            pydirectinput.keyDown('s')
            pydirectinput.keyUp('w')
            pydirectinput.keyUp('a')
            pydirectinput.keyUp('d')
        return

    # 3. ALINHAMENTO ATIVO (FULL)
    # Se chegamos aqui, o status é algo como "FULL-TOP-LEFT"
    
    # Eixo Vertical (Pitch)
    if "TOP" in status:
        pydirectinput.keyDown('s') # Puxa para cima
        pydirectinput.keyUp('w')
    elif "DOWN" in status:
        pydirectinput.keyDown('w') # Empurra para baixo
        pydirectinput.keyUp('s')
    else:
        pydirectinput.keyUp('w')
        pydirectinput.keyUp('s')

    # Eixo Horizontal (Yaw)
    if "LEFT" in status:
        pydirectinput.keyDown('a')
        pydirectinput.keyUp('d')
    elif "RIGHT" in status:
        pydirectinput.keyDown('d')
        pydirectinput.keyUp('a')
    else:
        pydirectinput.keyUp('a')
        pydirectinput.keyUp('d')

def run_bot():
    global BOT_ATIVO
    monitor = {"top": 1200, "left": 905, "width": 100, "height": 110}
    pydirectinput.press('x') # Motor a zero

    with mss.mss() as sct:
        while True:
            img_raw = np.array(sct.grab(monitor))
            img_bgr = cv2.cvtColor(img_raw, cv2.COLOR_BGRA2BGR)
            
            if keyboard.is_pressed('space'):
                BOT_ATIVO = not BOT_ATIVO
                release_all() # Limpa teclas ao desligar
                print(f"BOT: {BOT_ATIVO}")
                time.sleep(0.3)
            
            if keyboard.is_pressed('esc'): 
                release_all()
                break

            status, coords, mask, area_val = analyze_compass(img_bgr)
            control_ship(status)
            
            # Desenho da UI de Debug
            cv2.rectangle(img_bgr, (38, 43), (62, 67), (255, 255, 255), 1)
            if coords:
                color = (0, 255, 0) if "CENTER" in status else (0, 165, 255)
                cv2.circle(img_bgr, coords, 4, color, -1)
            
            cv2.putText(img_bgr, status, (5, 95), 1, 0.8, (255, 255, 255), 1)
            cv2.imshow("Bot Vision", img_bgr)
            cv2.imshow("Mask", mask)
            
            if cv2.waitKey(1) & 0xFF == ord('q'): break

    cv2.destroyAllWindows()

if __name__ == "__main__":
    run_bot()
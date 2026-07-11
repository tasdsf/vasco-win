import mss
import cv2
import numpy as np
import time
import pydirectinput
import keyboard

# Configurações
pydirectinput.PAUSE = 0
BOT_ATIVO = False

def apply_clahe(img_bgr):
    # O CLAHE precisa de imagem em tons de cinza ou canal de brilho (LAB)
    # Vamos usar o canal V do HSV ou converter para LAB para preservar cores
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    
    # clipLimit maior = mais contraste, tileGridSize = tamanho da vizinhança
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    cl = clahe.apply(l)
    
    limg = cv2.merge((cl, a, b))
    return cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)

def analyze_compass(img_bgr):
    # 1. APLICAR CLAHE antes de converter para HSV
    img_enhanced = apply_clahe(img_bgr)
    
    lower_target = np.array([22, 52, 71])
    upper_target = np.array([108, 255, 255])
    cX_center, cY_center = 50, 55
    dead_zone = 8
    
    hsv = cv2.cvtColor(img_enhanced, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lower_target, upper_target)
    
    # Limpeza leve para evitar que reflexos minúsculos somem área
    kernel = np.ones((2,2), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    
    area = cv2.countNonZero(mask)
    M = cv2.moments(mask)
    
    state_msg = "NO TARGET"
    target_pos = None
    
    if M["m00"] > 0:
        tx = int(M["m10"] / M["m00"])
        ty = int(M["m01"] / M["m00"])
        target_pos = (tx, ty)
        
        # Com CLAHE, o EMPTY deve ficar muito mais ténue que o FULL
        fill_state = "FULL" if area > 40 else "EMPTY"
        
        dx, dy = tx - cX_center, ty - cY_center
        h_dir = "CENTER" if abs(dx) < dead_zone else ("LEFT" if dx < 0 else "RIGHT")
        v_dir = "CENTER" if abs(dy) < dead_zone else ("TOP" if dy < 0 else "DOWN")
        
        state_msg = f"{fill_state} - {v_dir} {h_dir}"
        if h_dir == "CENTER" and v_dir == "CENTER":
            state_msg = f"{fill_state} - CENTERED"

    return state_msg, target_pos, mask, area, img_enhanced

def control_ship(status):
    if not BOT_ATIVO:
        for key in ['w', 's', 'a', 'd']: pydirectinput.keyUp(key)
        return

    # Se perder o sinal ou estiver atrás: Pitch Up (Busca)
    if "NO TARGET" in status or "EMPTY" in status:
        pydirectinput.keyDown('s')
        pydirectinput.keyUp('w')
        return

    # Alinhamento Vertical
    if "TOP" in status:
        pydirectinput.keyDown('s')
        pydirectinput.keyUp('w')
    elif "DOWN" in status:
        pydirectinput.keyDown('w')
        pydirectinput.keyUp('s')
    else:
        pydirectinput.keyUp('w'); pydirectinput.keyUp('s')

    # Alinhamento Horizontal (Yaw)
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
    pydirectinput.press('x') # Para motor
    
    with mss.mss() as sct:
        while True:
            raw_img = np.array(sct.grab(monitor))
            img_bgr = cv2.cvtColor(raw_img, cv2.COLOR_BGRA2BGR)
            
            if keyboard.is_pressed('space'):
                BOT_ATIVO = not BOT_ATIVO
                print(f"BOT: {BOT_ATIVO}")
                time.sleep(0.3)
            
            if keyboard.is_pressed('esc'): break

            status, coords, mask, area_val, enhanced = analyze_compass(img_bgr)
            control_ship(status)
            
            # Debug Visual
            cv2.imshow("Original vs Enhanced", np.hstack([img_bgr, enhanced]))
            cv2.imshow("Mask (CLAHE Ativo)", mask)
            
            if cv2.waitKey(1) & 0xFF == ord('q'): break

    cv2.destroyAllWindows()

if __name__ == "__main__":
    run_bot()
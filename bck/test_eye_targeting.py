import mss
import cv2
import numpy as np
import time
import pydirectinput
import keyboard  # Nova biblioteca para o Toggle

# Configurações Iniciais
pydirectinput.PAUSE = 0
BOT_ATIVO = False

def initialize_ship():
    print(">>> A inicializar: Motor a ZERO (X)")
    pydirectinput.press('x')
    time.sleep(0.5)

def control_ship(status):
    # Se o bot estiver desligado, garante que nenhuma tecla fica presa
    if not BOT_ATIVO:
        for key in ['w', 's', 'a', 'd']:
            pydirectinput.keyUp(key)
        return

    # 1. Lógica de Busca: Se não há sinal, faz Pitch Up para procurar
    if "NO TARGET" in status:
        pydirectinput.keyDown('s') # Pitch Up
        pydirectinput.keyUp('w')
        pydirectinput.keyUp('a')
        pydirectinput.keyUp('d')
        return

    # 2. Se o alvo está atrás (EMPTY), continua Pitch Up
    if "EMPTY" in status:
        pydirectinput.keyDown('s')
        pydirectinput.keyUp('w')
        return

    # 3. Alinhamento (FULL)
    # Pitch (Vertical)
    if "TOP" in status:
        pydirectinput.keyDown('s')
        pydirectinput.keyUp('w')
    elif "DOWN" in status:
        pydirectinput.keyDown('w')
        pydirectinput.keyUp('s')
    else:
        pydirectinput.keyUp('w')
        pydirectinput.keyUp('s')

    # Yaw (Horizontal)
    if "LEFT" in status:
        pydirectinput.keyDown('a')
        pydirectinput.keyUp('d')
    elif "RIGHT" in status:
        pydirectinput.keyDown('d')
        pydirectinput.keyUp('a')
    else:
        pydirectinput.keyUp('a')
        pydirectinput.keyUp('d')

    # Se estiver centrado, solta as teclas de direção
    if "CENTERED" in status:
        for key in ['w', 's', 'a', 'd']:
            pydirectinput.keyUp(key)

def analyze_compass(img_bgr):
    lower_target = np.array([22, 52, 71])
    upper_target = np.array([108, 255, 255])
    cX_center, cY_center = 50, 55
    dead_zone = 8
    
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lower_target, upper_target)
    
    M = cv2.moments(mask)
    area = cv2.countNonZero(mask)
    
    state_msg = "NO TARGET"
    target_pos = None
    
    if M["m00"] > 0:
        tx = int(M["m10"] / M["m00"])
        ty = int(M["m01"] / M["m00"])
        target_pos = (tx, ty)
        fill_state = "FULL" if area > 15 else "EMPTY"
        dx, dy = tx - cX_center, ty - cY_center
        h_dir = "CENTER" if abs(dx) < dead_zone else ("LEFT" if dx < 0 else "RIGHT")
        v_dir = "CENTER" if abs(dy) < dead_zone else ("TOP" if dy < 0 else "DOWN")

        if h_dir == "CENTER" and v_dir == "CENTER":
            state_msg = f"{fill_state} - CENTERED"
        else:
            state_msg = f"{fill_state} - {v_dir} {h_dir}"

    return state_msg, target_pos, mask, area

def run_bot():
    global BOT_ATIVO
    monitor = {"top": 1200, "left": 905, "width": 100, "height": 110}
    initialize_ship()
    
    with mss.mss() as sct:
        print("\n[CONTROLO] Pressione 'ESPAÇO' para LIGAR/DESLIGAR o movimento.")
        print("[SISTEMA] Pressione 'ESC' para fechar o script.")
        
        while True:
            # Captura
            raw_img = np.array(sct.grab(monitor))
            img_bgr = cv2.cvtColor(raw_img, cv2.COLOR_BGRA2BGR)
            
            # Atalhos de teclado
            if keyboard.is_pressed('space'):
                BOT_ATIVO = not BOT_ATIVO
                print(f">>> BOT {'LIGADO' if BOT_ATIVO else 'DESLIGADO'}")
                time.sleep(0.3) # Debounce para não flipar várias vezes
            
            if keyboard.is_pressed('esc'):
                break

            # Processamento
            status, coords, debug_mask, area_val = analyze_compass(img_bgr)
            
            # Executar Movimento
            control_ship(status)
            
            # Feedback Visual
            mode_color = (0, 255, 0) if BOT_ATIVO else (0, 0, 255)
            cv2.putText(img_bgr, f"BOT: {'ON' if BOT_ATIVO else 'OFF'}", (5, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, mode_color, 1)
            cv2.putText(img_bgr, status, (5, 95), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            
            cv2.imshow("Navegador Elite", img_bgr)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cv2.destroyAllWindows()

if __name__ == "__main__":
    run_bot()
import mss
import cv2
import numpy as np
import time

def analyze_compass(img_bgr):
    # --- Novos valores solicitados ---
    lower_target = np.array([22, 52, 71]) # Início do ajuste solicitado
    upper_target = np.array([108, 255, 255])
    
    cX_center, cY_center = 50, 55
    dead_zone = 8
    
    # 1. Conversão para HSV (sem blur para não perder pixels finos)
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    
    # 2. Criar Máscara
    mask = cv2.inRange(hsv, lower_target, upper_target)
    
    # --- Remoção de Contornos e Morphologia ---
    # Calculamos o centro de massa de todos os pixels brancos na máscara
    M = cv2.moments(mask)
    area = cv2.countNonZero(mask) # Conta quantos pixels passaram no filtro
    
    state_msg = "NO TARGET"
    target_pos = None
    
    if M["m00"] > 0: # Se houver pelo menos 1 pixel branco
        # Centro de massa (X, Y)
        tx = int(M["m10"] / M["m00"])
        ty = int(M["m01"] / M["m00"])
        target_pos = (tx, ty)

        # Lógica de FULL vs EMPTY baseada na contagem total de pixels
        # Ajuste o '20' conforme necessário olhando o "Area" no ecrã
        fill_state = "FULL" if area > 35 else "EMPTY"

        # Lógica de Direção
        dx = tx - cX_center
        dy = ty - cY_center
        
        h_dir = "CENTER" if abs(dx) < dead_zone else ("LEFT" if dx < 0 else "RIGHT")
        v_dir = "CENTER" if abs(dy) < dead_zone else ("TOP" if dy < 0 else "DOWN")

        if h_dir == "CENTER" and v_dir == "CENTER":
            state_msg = f"{fill_state} - CENTERED"
        else:
            state_msg = f"{fill_state} - {v_dir} {h_dir}"

    return state_msg, target_pos, mask, area

def run_bot_vision():    
    monitor = {"top": 1200, "left": 905, "width": 100, "height": 110}
    
    with mss.mss() as sct:
        print("Bot Vision Ativado (Modo Ultra-Sensível).")
        last_time = time.time()
        
        while True:
            raw_img = np.array(sct.grab(monitor))
            img_bgr = cv2.cvtColor(raw_img, cv2.COLOR_BGRA2BGR)
            
            # Processamento
            status, coords, debug_mask, area_val = analyze_compass(img_bgr)
            
            # --- Feedback Visual ---
            # Mira central
            cv2.drawMarker(img_bgr, (50, 55), (255, 255, 255), cv2.MARKER_CROSS, 15, 1)
            
            if coords:
                # Desenha o ponto onde o bot "acha" que o alvo está
                color = (0, 255, 0) if "CENTERED" in status else (0, 165, 255)
                cv2.circle(img_bgr, coords, 3, color, -1)
                cv2.putText(img_bgr, f"Area: {area_val}", (5, 40), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, (200, 200, 200), 1)
            
            cv2.putText(img_bgr, status, (5, 95), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            
            fps = 1 / (time.time() - last_time)
            last_time = time.time()
            cv2.putText(img_bgr, f"FPS: {int(fps)}", (5, 15), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 255, 0), 1)

            cv2.imshow("Bot Vision (Moments Mode)", img_bgr)
            cv2.imshow("Mask (Sem Filtros)", debug_mask)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                cv2.destroyAllWindows()
                break

if __name__ == "__main__":
    run_bot_vision()
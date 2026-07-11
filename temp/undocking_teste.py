import os
import time
import pydirectinput
import cv2
import mss
import numpy as np
import pyttsx3
import ctypes  # Para ler o SHIFT físico global do Windows

# ==========================================
# 1. SETUP DE ÁREAS (CALIBRADAS 350x300)
# ==========================================
MONITOR_MENU = {"top": 1100, "left": 1100, "width": 350, "height": 300}
MONITOR_CENTER = {"top": 200, "left": 400, "width": 1100, "height": 600}

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_imagens = os.path.join(diretorio_atual, 'images')

templates_nomes = {
    'autolaunch': 'AUTO_LAUNCH.png',
    'noselection': 'NO_SELECTION.png',
    'auto_progress': 'AUTO_LAUNCH_PROGRESS.png' 
}

templates = {}
try:
    for chave, nome_arq in templates_nomes.items():
        caminho = os.path.join(pasta_imagens, nome_arq)
        templates[chave] = cv2.imread(caminho, cv2.IMREAD_COLOR)
    print(f"[SISTEMA] Módulo: Undocking Determinístico carregado.")
except Exception as e:
    print(f"ERRO ASSINATURA: {e}"); exit()

# --- Voz ---
engine = pyttsx3.init()
def falar(texto):
    print(f"[VOZ] {texto}")
    engine.say(texto)
    engine.runAndWait()

# ==========================================
# 2. MOTOR DE VISÃO (2º ECRÃ + JANELA AMPLIADA)
# ==========================================
def procurar_template(template, nome_label, monitor, threshold=0.90, msg_hud=""):
    if template is None: return False
    
    with mss.mss() as sct:
        monitors = sct.monitors
        try:
            monitor_jogo = monitors[1] # Jogo focado no Monitor 1
        except IndexError:
            monitor_jogo = monitors[0]
            
        area_real = {
            "top": monitor_jogo["top"] + monitor["top"],
            "left": monitor_jogo["left"] + monitor["left"],
            "width": monitor["width"],
            "height": monitor["height"]
        }
        
        img_bgra = np.array(sct.grab(area_real))
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
        resultado = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(resultado)
        
        encontrou = max_val >= threshold
        cor = (0, 255, 0) if encontrou else (0, 0, 255)
        
        if encontrou:
            h, w = template.shape[:2]
            cv2.rectangle(img_bgr, max_loc, (max_loc[0] + w, max_loc[1] + h), cor, 2)
        
        # HUD de Debug na Janela
        cv2.rectangle(img_bgr, (0, 0), (350, 60), (0, 0, 0), -1)
        cv2.putText(img_bgr, f"{nome_label}: {max_val*100:.1f}% (Min: {threshold*100:.0f}%)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        if msg_hud:
            cv2.putText(img_bgr, msg_hud, (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
        
        # Projeta a janela com o dobro do tamanho (Ampliada)
        img_show = cv2.resize(img_bgr, (700, 600))
        nome_janela = "R2D2 - Ocular de Auditoria"
        cv2.imshow(nome_janela, img_show)
        
        # Envia para o segundo monitor se ele existir
        if len(monitors) >= 3:
            cv2.moveWindow(nome_janela, monitors[2]["left"] + 50, monitors[2]["top"] + 50)
        else:
            cv2.moveWindow(nome_janela, 50, 50)
            
        cv2.waitKey(1)
        return encontrou

# ==========================================
# 3. LÓGICA DO TEU ALGORITMO CORRIGIDA
# ==========================================
def executar_auto_launch():
    print("\n==================================================")
    print(">>> INICIANDO MANOBRA DE UNDOCKING LOGIC")
    print("==================================================")
    
    # 0. Aguarda o Menu abrir
    print("A aguardar renderização do menu inicial...")
    while not (procurar_template(templates['noselection'], "MENU_INIT", MONITOR_MENU, 0.70) or
               procurar_template(templates['autolaunch'], "MENU_INIT", MONITOR_MENU, 0.70)):
        time.sleep(0.2)
        
    time.sleep(0.5) # Estabilização de frames

    # 1. Pressiona 3 vezes 'w' sem travar por inputs manuais
    print("\nA enviar inputs mecânicos: 3x 'w'...")
    for _ in range(3):
        pydirectinput.press('w')
        time.sleep(0.2)
        
    # 2. Valida NO_SELECTION a 90%
    print("\nA validar 'NO_SELECTION' no teto do menu...")
    time.sleep(0.3) # Tempo para o foco assentar
    if not procurar_template(templates['noselection'], "VAL_NO_SELECTION", MONITOR_MENU, 0.90, "Validando teto..."):
        print("[SISTEMA] Falha: 'NO_SELECTION' não atingiu 90%. Abortando execução.")
        return False
        
    print("[OK] 'NO_SELECTION' validado com sucesso (>= 90%).")

    # 3. Carrega duas vezes no 's'
    print("\nA navegar para o alvo: 2x 's'...")
    for _ in range(2):
        pydirectinput.press('s')
        time.sleep(0.25)

    # 4. Valida AUTO_LAUNCH a 90%
    print("\nA auditar o foco do botão Auto-Launch...")
    time.sleep(0.3) # Tempo para o foco assentar
    if not procurar_template(templates['autolaunch'], "VAL_AUTO_LAUNCH", MONITOR_MENU, 0.90, "Validando botão alvo..."):
        print("não detetou o auto-launch") # Erro exato exigido
        return False

    print("[OK] 'AUTO_LAUNCH' validado com sucesso (>= 90%).")

    # 5. Espera pela tecla física 'SHIFT' para autorizar disparo final
    print("\n==================================================")
    print(">>> VALIDAÇÕES OK. AVISO: A aguardar SHIFT para lançar nave!")
    print("==================================================")
    falar("Sequence verified. Press Shift to launch.")
    
    VK_SHIFT = 0x10 # Código virtual da tecla SHIFT no Windows
    while ctypes.windll.user32.GetAsyncKeyState(VK_SHIFT) & 0x8000:
        time.sleep(0.05) # Limpa pressões residuais
        
    while True:
        procurar_template(templates['autolaunch'], "AGUARDANDO_SHIFT", MONITOR_MENU, 0.90, ">>> PRESSIONA SHIFT PARA LANÇAR <<<")
        if ctypes.windll.user32.GetAsyncKeyState(VK_SHIFT) & 0x8000:
            print("\n[AUTORIZADO] Gatilho detetado. Enviando SPACE!")
            pydirectinput.press('space')
            return True
        time.sleep(0.05)

def aguardar_saida_estacao():
    print("\n>>> FASE: Detetar saída da estação...")
    time.sleep(1.5)
    while True: 
        if procurar_template(templates['auto_progress'], "PROG_CENTRO", MONITOR_CENTER, 0.55, "Em manobra automática..."):
            break
        time.sleep(0.4)
    
    contagem_limpo = 0
    while contagem_limpo < 3: 
        if procurar_template(templates['auto_progress'], "PROG_CENTRO", MONITOR_CENTER, 0.55, "Saindo da Estação..."):
            contagem_limpo = 0 
        else:
            contagem_limpo += 1 
        time.sleep(1)

    print("[SUCESSO] Espaço aberto detetado.")
    falar("Auto launch terminated commander.")

def sequencia_salto():
    print("\n>>> FASE: Impulso de Saída...")
    pydirectinput.press('tab')

if __name__ == "__main__":
    print("Foca a janela do jogo. Sequência arranca em 3 segundos...")
    time.sleep(3)
    if executar_auto_launch():
        aguardar_saida_estacao()
        sequencia_salto()
    cv2.destroyAllWindows()
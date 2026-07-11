import os
import time
import pydirectinput
import cv2
import mss
import numpy as np
import pyttsx3
import ctypes  # API Nativa do Windows para Pop-ups Gráficos

# ==========================================
# 1. SETUP DE GEOMETRIA (CALIBRADA 350x300)
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
    print(f"[SISTEMA] Módulo: Undocking Ótico Closed-Loop Carregado.")
except Exception as e:
    print(f"ERRO ASSINATURA: {e}"); exit()

# --- Motor de Voz (pyttsx3) ---
engine = pyttsx3.init()
def falar(texto):
    print(f"[VOZ] {texto}")
    engine.say(texto)
    engine.runAndWait()

# --- Pop-up Nativo do Windows (ctypes) ---
def lancar_popup_erro(titulo, mensagem):
    # 0x10 aplica o ícone de Erro Crítico do Windows
    ctypes.windll.user32.MessageBoxW(0, mensagem, titulo, 0x10)

# ==========================================
# 2. MOTOR DE VISÃO COMPUTACIONAL
# ==========================================
def procurar_template(template, nome_label, monitor, threshold=0.85):
    if template is None: return False, 0.0
    
    with mss.mss() as sct:
        monitors = sct.monitors
        try:
            monitor_jogo = monitors[1] # Garante foco no Monitor Principal do Jogo
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
        
        # Desenhar HUD de diagnóstico na janela de visualização ampliada
        cv2.rectangle(img_bgr, (0, 0), (350, 45), (0, 0, 0), -1)
        cv2.putText(img_bgr, f"{nome_label}: {max_val*100:.1f}% (Min: {threshold*100:.0f}%)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        img_show = cv2.resize(img_bgr, (700, 600))
        nome_janela = "R2D2 - Ocular de Auditoria"
        cv2.imshow(nome_janela, img_show)
        
        # Projeta no segundo ecrã se detetado para não tapar o simulador
        if len(monitors) >= 3:
            cv2.moveWindow(nome_janela, monitors[2]["left"] + 50, monitors[2]["top"] + 50)
        else:
            cv2.moveWindow(nome_janela, 50, 50)
            
        cv2.waitKey(1)
        return encontrou, max_val

# ==========================================
# 3. MÁQUINA DE ESTADOS DETERMINÍSTICA
# ==========================================
def executar_auto_launch():
    print("\n==================================================")
    print(">>> CODE EXECUTION: MANOBRA DE UNDOCKING SEQUENCIAL")
    print("==================================================")
    
    # Passo 0: Estabilização do HUD do Menu
    print("A aguardar estabilização do menu...")
    while True:
        m1, _ = procurar_template(templates['noselection'], "ESTABILIZACAO", MONITOR_MENU, 0.85)
        m2, _ = procurar_template(templates['autolaunch'], "ESTABILIZACAO", MONITOR_MENU, 0.85)
        if m1 or m2: break
        time.sleep(0.2)
    
    time.sleep(0.5) # Buffer para animação holográfica de fade-in

    # Passo 1: Subida Mecânica Cega para o Teto
    print("\nA enviar comandos mecânicos: 3x 'w'...")
    for _ in range(3):
        pydirectinput.press('w')
        time.sleep(0.2)
        
    # Passo 2: Validação de Segurança do Teto (NO_SELECTION >= 85%)
    print("\nA validar 'NO_SELECTION' no topo do menu...")
    time.sleep(0.3) # Tempo para o cursor assentar graficamente
    
    sucesso_idle, score_idle = procurar_template(templates['noselection'], "VAL_NO_SELECTION", MONITOR_MENU, 0.85)
    if not sucesso_idle:
        msg_erro = f"Falha crítica de calibração ótica no teto.\nMatch real: {score_idle*100:.1f}% (Exigia: 85.0%)"
        print(f"[ABORT] {msg_erro}")
        falar("Error. Validation failed at menu top. Aborting sequence.")
        lancar_popup_erro("R2D2 - Erro de Validação", msg_erro)
        return False
        
    print(f"[OK] 'NO_SELECTION' validado com {score_idle*100:.1f}%.")

    # Passo 3: Descida Mecânica Cega até ao Alvo
    print("\nA navegar para a posição do botão: 2x 's'...")
    for _ in range(2):
        pydirectinput.press('s')
        time.sleep(0.25)

    # Passo 4: Validação de Segurança do Alvo (AUTO_LAUNCH >= 85%)
    print("\nA auditar foco do botão Auto-Launch...")
    time.sleep(0.3) # Tempo para o cursor assentar graficamente
    
    sucesso_al, score_al = procurar_template(templates['autolaunch'], "VAL_AUTO_LAUNCH", MONITOR_MENU, 0.85)
    if not sucesso_al:
        msg_critica = "não detetou o auto-launch"
        print(f"[ABORT] {msg_critica.upper()} (Match real: {score_al*100:.1f}% / Exigia 85.0%)")
        falar(msg_critica)
        lancar_popup_erro("R2D2 - Falha de Deteção", msg_critica)
        return False

    print(f"[OK] 'AUTO_LAUNCH' validado com {score_al*100:.1f}%.")

    # Passo 5: Execução Limpa (Sem pausas manuais)
    print("\n>>> TUDO VALIDADO! A disparar comando SPACE...")
    pydirectinput.press('space')
    return True

def aguardar_saida_estacao():
    print("\n>>> FASE: Detetar saída da estação...")
    time.sleep(1.5)
    
    # 1. Espera o aparecimento do painel central de progresso
    while True: 
        encontrou, _ = procurar_template(templates['auto_progress'], "PROG_CENTRO", MONITOR_CENTER, 0.55)
        if encontrou:
            print("[LOG] Nave capturada pelo feixe de Auto-Launch. Em trânsito.")
            break
        time.sleep(0.4)
    
    # 2. Monitoriza até o ecrã central ficar limpo por 3 segundos seguidos
    print("A voar para o exterior... A aguardar que o painel de progresso desapareça.")
    contagem_limpo = 0
    while contagem_limpo < 3: 
        encontrou, _ = procurar_template(templates['auto_progress'], "PROG_CENTRO", MONITOR_CENTER, 0.55)
        if encontrou:
            contagem_limpo = 0 # Reinicia porque o painel ainda lá está
        else:
            contagem_limpo += 1 # Frame limpo detetado
        time.sleep(1)

    print("[SUCESSO] Ecrã limpo de forma consistente. Estamos no espaço aberto!")
    falar("Auto launch terminated commander.")

def sequencia_salto():
    print("\n>>> FASE: Impulso de Saída...")
    pydirectinput.press('tab')
    time.sleep(3.0)
    pydirectinput.press('tab') # Boost na direção da estação/carrier
    time.sleep(3.0)

# ==========================================
# 4. EXECUÇÃO PRINCIPAL
# ==========================================
if __name__ == "__main__":
    print("Entra na janela do jogo. O script arranca em 3 segundos...")
    time.sleep(3)
    if执行 = executar_auto_launch()
    if if执行:
        aguardar_saida_estacao()
        sequencia_salto()
    cv2.destroyAllWindows()
    
import os
import json
import time
import cv2
import mss
import numpy as np
import pydirectinput
import keyboard
import glob
from collections import deque
import sys

# ==========================================
# 1. SETUP DE CONFIGURAÇÃO E ABSTRACÇÃO
# ==========================================
pydirectinput.PAUSE = 0.01
BOT_ATIVO = True
NOME_JANELA_PROD = "R2D2 - Painel de Voo da Bussola"

# Afinações de Precisão e Proporcionalidade
DEAD_ZONE = 2
RAIO_AJUSTE_FINO = 15
IMPULSO_AJUSTE_FINO = 0.2
TOLERANCIA_BOLA = 3.5

# Histórico para suavização da BOLA
historico_bola_x = deque(maxlen=5)
historico_bola_y = deque(maxlen=5)

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
caminho_memoria = os.path.join(diretorio_atual, "memoria_bussola.json")
caminho_coordenadas = os.path.join(diretorio_atual, "coordenadas_bussola.json")

try:
    with open(caminho_memoria, "r") as f:
        memoria = json.load(f)
    print(f"[SISTEMA] Matriz de assinaturas HSV online ({len(memoria)} perfis activos).")
except Exception as e:
    print(f"[ERRO CRÍTICO] Falha ao ler memoria_bussola.json: {e}"); exit()

# ==========================================
# 2. FUNÇÕES DE INFRAESTRUTURA DINÂMICA
# ==========================================
def obter_modelo_nave_atual():
    try:
        caminho_logs = os.path.join(os.environ['USERPROFILE'], 'Saved Games', 'Frontier Developments', 'Elite Dangerous')
        if not os.path.exists(caminho_logs): return "Desconhecido"
        
        lista_logs = glob.glob(os.path.join(caminho_logs, "Journal.*.log"))
        if not lista_logs: return "Desconhecido"
        
        ultimo_log = max(lista_logs, key=os.path.getmtime)
        modelo_nave = "Desconhecido"
        
        with open(ultimo_log, 'r', encoding='utf-8') as f:
            for linha in f:
                try:
                    log_data = json.loads(linha)
                    if log_data.get("event") in ["LoadGame", "ShipyardSwap", "Location", "Commander"]:
                        if "Ship_Localised" in log_data:
                            modelo_nave = log_data["Ship_Localised"]
                        elif "Ship" in log_data:
                            modelo_nave = log_data["Ship"].title()
                except json.JSONDecodeError:
                    continue
        return modelo_nave
    except Exception:
        return "Desconhecido"

def carregar_dados_calibracao(nave_atual):
    config_default = {"top": 1180, "left": 970, "width": 80, "height": 90}
    cx_default, cy_default = 42, 42
    
    if os.path.exists(caminho_coordenadas):
        try:
            with open(caminho_coordenadas, "r") as f:
                cfg = json.load(f)
            
            if cfg.get("Nave") == nave_atual:
                print(f"[CONFIG] Perfil geométrico acoplado para '{nave_atual}'.")
                return cfg["MONITOR_CONFIG"], cfg["CX_NEUTRO"], cfg["CY_NEUTRO"]
            else:
                print(f"[AVISO] Perfil pertence a '{cfg.get('Nave')}'. Usando defaults para '{nave_atual}'.")
        except Exception as e:
            print(f"[AVISO] Erro na leitura do JSON ({e}). Aplicando defaults.")
    else:
        print(f"[AVISO] Ficheiro coordenadas_bussola.json ausente. Aplicando defaults.")
        
    return config_default, cx_default, cy_default

# ==========================================
# 3. PIPELINE ÓTICO FOCADO NA BOLA
# ==========================================
def localizar_bola(img_bgr, cx, cy):
    img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    mascara_final = np.zeros(img_hsv.shape[:2], dtype=np.uint8)
    
    bola_encontrada = False
    px, py = 0, 0
    is_hollow = False
    
    for perfil in memoria:
        mask = cv2.inRange(img_hsv, np.array(perfil['min']), np.array(perfil['max']))
        contornos, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if contornos:
            ponto_contorno = max(contornos, key=cv2.contourArea)
            if cv2.contourArea(ponto_contorno) > 2:
                M = cv2.moments(ponto_contorno)
                if M["m00"] != 0:
                    px = int(M["m10"] / M["m00"])
                    py = int(M["m01"] / M["m00"])
                    
                    # ---------------------------------------------
                    # NOVA LÓGICA: AUDITORIA DA BOLA VAZIA (ATÁS)
                    # ---------------------------------------------
                    try:
                        pixel_central = mask[py, px]
                        is_hollow = (pixel_central == 0)
                    except IndexError:
                        is_hollow = False
                    
                    bola_encontrada = True
                    mascara_final = mask
                    break
                    
    if bola_encontrada:
        if is_hollow:
            # Alvo está nas costas. Ignoramos cálculos de X/Y e devolvemos manobra imediata.
            return "ALVO_ATRAS", (px, py), mascara_final, True, 0, 0, 0, 0

        historico_bola_x.append(px)
        historico_bola_y.append(py)
        
        if len(historico_bola_x) >= 3:
            delta_x = max(historico_bola_x) - min(historico_bola_x)
            delta_y = max(historico_bola_y) - min(historico_bola_y)
            bola_sossegada = (delta_x <= TOLERANCIA_BOLA) and (delta_y <= TOLERANCIA_BOLA)
            
            dx = px - cx
            dy = py - cy
            
            if abs(dx) <= DEAD_ZONE and abs(dy) <= DEAD_ZONE:
                return "ALINHADO", (px, py), mascara_final, bola_sossegada, delta_x, delta_y, abs(dx), abs(dy)
                
            passos = []
            if dy < -DEAD_ZONE: passos.append("W")
            elif dy > DEAD_ZONE: passos.append("S")
            if dx < -DEAD_ZONE: passos.append("A")
            elif dx > DEAD_ZONE: passos.append("D")
            
            return " + ".join(passos), (px, py), mascara_final, bola_sossegada, delta_x, delta_y, abs(dx), abs(dy)
            
        return "AQUECENDO_SENSOR", (px, py), mascara_final, False, 0, 0, 0, 0
        
    historico_bola_x.clear()
    historico_bola_y.clear()
    return "NÃO_DETETADO", None, mascara_final, False, 0, 0, 0, 0

# ==========================================
# 4. CONTROLADOR DINÂMICO PROPORCIONAL
# ==========================================
def largar_todas_as_teclas():
    for t in ["w", "s", "a", "d"]:
        pydirectinput.keyUp(t)

def aplicar_manobra(comando, dist_x, dist_y):
    if comando in ["NÃO_DETETADO", "ALINHADO", "AQUECENDO_SENSOR"]:
        largar_todas_as_teclas()
        return
        
    # ---------------------------------------------
    # NOVA LÓGICA: EXECUÇÃO DO PITCH UP (BOLA VAZIA)
    # ---------------------------------------------
    if comando == "ALVO_ATRAS":
        for t in ["w", "a", "d"]:
            pydirectinput.keyUp(t)
        pydirectinput.keyDown('s')
        print("[VOO] Alvo nas costas (bola vazia) -> PITCH UP")
        time.sleep(IMPULSO_AJUSTE_FINO)
        return

    teclas_necessarias = []
    if "W" in comando: teclas_necessarias.append("w")
    if "S" in comando: teclas_necessarias.append("s")
    if "A" in comando: teclas_necessarias.append("a")
    if "D" in comando: teclas_necessarias.append("d")
    
    for t in ["w", "s", "a", "d"]:
        if t not in teclas_necessarias: pydirectinput.keyUp(t)
        
    dist_max = max(dist_x, dist_y)
    
    if dist_max > RAIO_AJUSTE_FINO:
        for t in teclas_necessarias: pydirectinput.keyDown(t)
        time.sleep(4*IMPULSO_AJUSTE_FINO)
        print(f"[VOO] Energia MÁXIMA ({dist_max}px) -> {comando}")
    else:
        for t in teclas_necessarias: pydirectinput.keyDown(t)
        time.sleep(IMPULSO_AJUSTE_FINO)
        for t in teclas_necessarias: pydirectinput.keyUp(t)
        print(f"[VOO] Ajuste Fino ({dist_max}px) -> {comando}")

# ==========================================
# 5. EXECUÇÃO PRINCIPAL
# ==========================================
nave_ativa = obter_modelo_nave_atual()
MONITOR_CONFIG, CX_NEUTRO, CY_NEUTRO = carregar_dados_calibracao(nave_ativa)

# ---------------------------------------------
# NOVA LÓGICA: VARIÁVEIS DE ESTABILIDADE
# ---------------------------------------------
tempo_inicio_centrado = None
TEMPO_ESTABILIDADE = 15.0  # segundos
SCRIPT_TERMINADO = False
printed_rota_perfeita = False

with mss.mss() as sct:
    monitors = sct.monitors
    try:
        monitor_jogo = monitors[1]
    except IndexError:
        monitor_jogo = monitors[0]
        
    area_real = {
        "top": monitor_jogo["top"] + MONITOR_CONFIG["top"],
        "left": monitor_jogo["left"] + MONITOR_CONFIG["left"],
        "width": MONITOR_CONFIG["width"],
        "height": MONITOR_CONFIG["height"]
    }
    
    cv2.namedWindow(NOME_JANELA_PROD, cv2.WINDOW_AUTOSIZE)
    if len(monitors) > 2:
        cv2.moveWindow(NOME_JANELA_PROD, monitors[2]["left"] + 50, monitors[2]["top"] + 50)
    else:
        cv2.moveWindow(NOME_JANELA_PROD, 50, 50)
        
    print(f"\n==================================================")
    print(f"[R2D2 COGNITIVE V5] Piloto da Nave: '{nave_ativa}'")
    print(f"-> Força de Ajuste Fino definida para: {IMPULSO_AJUSTE_FINO}s")
    print("-> TECLA '<'     : LIGA / DESLIGA o Piloto Automático")
    print("-> TECLA 'Q'     : Encerra o script com segurança")
    print("==================================================\n")
    print("Entra na janela do jogo. O script arranca em 3 segundos...")
    time.sleep(3)
    
    while True:
        if keyboard.is_pressed('<'):
            BOT_ATIVO = not BOT_ATIVO
            print(f"\n[SISTEMA] PILOTO AUTOMÁTICO = {BOT_ATIVO}")
            historico_bola_x.clear()
            historico_bola_y.clear()
            largar_todas_as_teclas()
            tempo_inicio_centrado = None
            printed_rota_perfeita = False
            time.sleep(0.4)
            
        if keyboard.is_pressed('q'):
            print("\n[SISTEMA] Encerramento solicitado...")
            largar_todas_as_teclas()
            break
            
        if BOT_ATIVO:
            img_bgra = np.array(sct.grab(area_real))
            img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
            img_hud = img_bgr.copy()
            
            comando, coords_bola, mascara_hsv, estavel, delta_x, delta_y, dist_x, dist_y = localizar_bola(img_bgr, CX_NEUTRO, CY_NEUTRO)
            
            cv2.rectangle(img_hud, (CX_NEUTRO-DEAD_ZONE, CY_NEUTRO-DEAD_ZONE), 
                                   (CX_NEUTRO+DEAD_ZONE, CY_NEUTRO+DEAD_ZONE), (255, 255, 255), 1)
            cv2.circle(img_hud, (CX_NEUTRO, CY_NEUTRO), 1, (0, 165, 255), -1)
            
            view_zoom = cv2.resize(img_hud, (300, 350), interpolation=cv2.INTER_NEAREST)
            mask_zoom = cv2.cvtColor(cv2.resize(mascara_hsv, (300, 350), interpolation=cv2.INTER_NEAREST), cv2.COLOR_GRAY2BGR)
            divisor = np.ones((350, 10, 3), dtype=np.uint8) * 80
            
            comando_display = comando
            
            if not coords_bola:
                cv2.putText(view_zoom, "PROCURANDO ALVO", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)
                cv2.imshow(NOME_JANELA_PROD, np.hstack((view_zoom, divisor, mask_zoom)))
                largar_todas_as_teclas()
                cv2.waitKey(1)
                time.sleep(0.05)
                tempo_inicio_centrado = None
            else:
                cv2.circle(img_hud, coords_bola, 3, (0, 255, 0), -1)
                view_zoom = cv2.resize(img_hud, (300, 350), interpolation=cv2.INTER_NEAREST)
                
                if not estavel and comando not in ["AQUECENDO_SENSOR", "ALVO_ATRAS"]:
                    cv2.putText(view_zoom, "ALVO OSCILANDO - SUSPENSO", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 165, 255), 1)
                    largar_todas_as_teclas()
                    tempo_inicio_centrado = None
                else:
                    if comando == "ALINHADO":
                        # ---------------------------------------------
                        # NOVA LÓGICA: CRONÓMETRO DE ESTABILIDADE
                        # ---------------------------------------------
                        if tempo_inicio_centrado is None:
                            tempo_inicio_centrado = time.time()
                        
                        tempo_decorrido = time.time() - tempo_inicio_centrado
                        comando_display = f"ALINHADO ({tempo_decorrido:.1f}s/{TEMPO_ESTABILIDADE}s)"
                        
                        if not printed_rota_perfeita:
                            print("[VOO] Rota Perfeita! Centralizado no milímetro. A estabilizar...")
                            printed_rota_perfeita = True
                            
                        if tempo_decorrido >= TEMPO_ESTABILIDADE:
                            print(f"\n[SISTEMA] Alvo bloqueado e estável por {TEMPO_ESTABILIDADE} segundos.")
                            print("[SUCESSO] Manobra de alinhamento concluída.")
                            SCRIPT_TERMINADO = True
                            largar_todas_as_teclas()
                            break
                    else:
                        # Se saiu do alinhamento, reinicia o cronómetro e aplica manobra
                        tempo_inicio_centrado = None
                        printed_rota_perfeita = False
                        aplicar_manobra(comando, dist_x, dist_y)

                cv2.putText(view_zoom, f"CORRECAO: {comando_display}", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
                cv2.imshow(NOME_JANELA_PROD, np.hstack((view_zoom, divisor, mask_zoom)))
                cv2.waitKey(1)
            
        time.sleep(0.04)

cv2.destroyAllWindows()

try:
    with open(os.path.join(diretorio_atual, "script_terminado.flag"), "w") as f:
        f.write("true" if SCRIPT_TERMINADO else "false")
except Exception:
    pass

if SCRIPT_TERMINADO:
    sys.exit(0)
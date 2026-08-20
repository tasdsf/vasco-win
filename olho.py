import os
import json
import time
import logging
import cv2
import mss
import numpy as np
import pydirectinput
import keyboard
import glob
from collections import deque
import sys
import pyttsx3
import winsound
import pygetwindow as gw  # <-- DEPENDÊNCIA PARA FOCO SEGURO AO NÍVEL DO S.O.
from datetime import datetime as _dt_hora

# Todos os prints passam a ter timestamp HH:MM:SS (preserva "\n" iniciais
# usados para espaçamento visual no terminal).
_print_original = print
def print(*args, **kwargs):
    if args and isinstance(args[0], str):
        _texto = args[0]
        _prefixo_nl = ""
        while _texto.startswith("\n"):
            _prefixo_nl += "\n"
            _texto = _texto[1:]
        args = (f"{_prefixo_nl}[{_dt_hora.now().strftime('%H:%M:%S')}] {_texto}",) + args[1:]
    _print_original(*args, **kwargs)

# ==========================================
# 0. LOGGING, SOM E INFRAESTRUTURA
# ==========================================
diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_logs = os.path.join(diretorio_atual, "logs")
pasta_imagens = os.path.join(diretorio_atual, "images")
os.makedirs(pasta_logs, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(pasta_logs, "r2d2_combined.log"),
    level=logging.ERROR,
    format='%(asctime)s - [OLHO_PILOTO] - %(levelname)s - %(message)s'
)

engine = pyttsx3.init()
def falar(texto):
    print(f"[VOZ] {texto}")
    engine.say(texto)
    engine.runAndWait()

def tocar_alarme_erro():
    winsound.Beep(1200, 300)
    time.sleep(0.1)
    winsound.Beep(1200, 600)

def tocar_alarme_sucesso():
    winsound.Beep(600, 200)
    winsound.Beep(800, 200)
    winsound.Beep(1000, 400)

def largar_todas_as_teclas():
    for t in ["w", "s", "a", "d"]:
        pydirectinput.keyUp(t)

def abortar_com_erro(mensagem):
    largar_todas_as_teclas()
    print(f"\n[FATAL] {mensagem}")
    logging.error(mensagem)
    tocar_alarme_erro()
    falar("Navigation error. Manual control required.")
    sys.exit(1)

def abortar_por_utilizador():
    largar_todas_as_teclas()
    print("\n[AVISO] Intervenção manual solicitada.")
    logging.warning("Operação cancelada via teclado (tecla ESC).")
    winsound.Beep(800, 300)
    falar("Manual override engaged. Yielding controls.")
    sys.exit(1)

NOME_JANELA_PROD = "R2D2 Sniper v11 - Dual-Stage Core"
VISUAL_DEBUG = True

def focar_jogo_seguro():
    """ Traz a janela do jogo para a frente pelo PID/Handle sem injetar comandos de rato """
    print("[SISTEMA] A invocar processo do Elite Dangerous via API do Windows...")
    try:
        janelas = gw.getWindowsWithTitle("Elite - Dangerous (CLIENT)")
        if not janelas:
            janelas = gw.getWindowsWithTitle("Elite Dangerous")
            
        if janelas:
            janela_elite = janelas[0]
            janela_elite.activate() 
            time.sleep(1.0) # Tempo vital para o DWM renderizar a janela à frente
            print("[OK] Acesso biométrico ao cockpit estabelecido.")
            return True
        else:
            print("[ERRO] Processo do Elite não encontrado no renderizador de janelas.")
            return False
    except Exception as e:
        print(f"[AVISO] Exceção na API do Windows (O foco terá de ser manual): {e}")
        return False

def inicializar_infraestrutura():
    print("[SISTEMA] A instanciar hooks de visão computacional...")
    
    if VISUAL_DEBUG:
        # Permite redimensionar manualmente e previne o esmagamento de DPI
        cv2.namedWindow(NOME_JANELA_PROD, cv2.WINDOW_NORMAL) 
        cv2.resizeWindow(NOME_JANELA_PROD, 860, 350) # Força o tamanho interno
        
    focar_jogo_seguro()
    
    with mss.mss() as sct:
        monitores = sct.monitors
        if VISUAL_DEBUG:
            if len(monitores) > 2:
                ecra_secundario = monitores[2]
                cv2.moveWindow(NOME_JANELA_PROD, ecra_secundario["left"] + 20, ecra_secundario["top"] + 50)
            else:
                cv2.moveWindow(NOME_JANELA_PROD, 20, 50)
            cv2.setWindowProperty(NOME_JANELA_PROD, cv2.WND_PROP_TOPMOST, 1)

# ==========================================
# 1. SETUP DE CONFIGURAÇÃO (BÚSSOLA E HUD)
# ==========================================
pydirectinput.PAUSE = 0.01
BOT_ATIVO = True

DEAD_ZONE_BUSSOLA = 2
RAIO_AJUSTE_FINO = 12
IMPULSO_BUSSOLA = 0.2
IMPULSO_BUSSOLA_GIGANTE = 8 * IMPULSO_BUSSOLA  # ALVO_ATRAS precisa de guinada grande (~180°)
COOLDOWN_GIGANTE = 3.5  # tempo extra pós-guinada gigante para a nave estabilizar antes da próxima leitura
TOLERANCIA_BOLA = 3.5

# Mantidos os teus valores de calibração fina atualizados:
MONITOR_HUD = {"top": 500, "left": 1050, "width": 400, "height": 500}
DEAD_ZONE_HUD = 15
IMPULSO_HUD = 0.11

# --- Recuperacao por ROLL (planeta ou brilho a tapar a leitura do HUD/bussola) ---
# Rodar a nave sobre o eixo longitudinal nao altera a direcao do nariz, por isso
# nao estraga o alinhamento ja conseguido - apenas muda o que esta "por tras" do HUD.
# O abort manual passou de 'q' para ESC para libertar as teclas Q/E (roll default do Elite).
TECLA_ROLL = 'e'              # roll para a direita (default Elite: Q esquerda / E direita)
TEMPO_ROLL_45 = 0.6           # segundos de tecla premida - comecar curto e ajustar apos teste em jogo (depende do roll rate da nave)
MAX_ROLLS_RECUPERACAO = 3     # tentativas de roll antes de desistir e abortar
TEMPO_CEGO_ANTES_ROLL = 8.0   # segundos sem leitura antes de tentar um roll

historico_bola_x = deque(maxlen=5)
historico_bola_y = deque(maxlen=5)

caminho_memoria = os.path.join(diretorio_atual, "memoria_bussola.json")
caminho_coordenadas = os.path.join(diretorio_atual, "coordenadas_bussola.json")

try:
    with open(caminho_memoria, "r") as f: memoria = json.load(f)
except Exception as e:
    abortar_com_erro(f"Falha ao ler memoria_bussola.json: {e}")

# Dois templates do alvo: o normal e o "low" (alvo com menos brilho/contraste).
# Em cada frame testa-se ambos e usa-se o que tiver o melhor match.
TEMPLATES_ALVO_NOMES = ["TARGET.png", "target_low.png"]
templates_alvo_hud = {}
try:
    for nome_arq in TEMPLATES_ALVO_NOMES:
        img_tpl = cv2.imread(os.path.join(pasta_imagens, nome_arq), cv2.IMREAD_COLOR)
        if img_tpl is None: raise FileNotFoundError(f"{nome_arq} ausente")
        templates_alvo_hud[nome_arq] = img_tpl
except Exception as e:
    abortar_com_erro(f"Erro de I/O nas imagens do alvo ({', '.join(TEMPLATES_ALVO_NOMES)}): {e}")

# ==========================================
# 2. TELEMETRIA
# ==========================================
def obter_modelo_nave_atual():
    try:
        caminho_logs = os.path.join(os.environ['USERPROFILE'], 'Saved Games', 'Frontier Developments', 'Elite Dangerous')
        lista_logs = glob.glob(os.path.join(caminho_logs, "Journal.*.log"))
        if not lista_logs: return "Desconhecido"
        
        ultimo_log = max(lista_logs, key=os.path.getmtime)
        modelo_nave = "Desconhecido"
        with open(ultimo_log, 'r', encoding='utf-8') as f:
            for linha in f:
                try:
                    log_data = json.loads(linha)
                    if log_data.get("event") in ["LoadGame", "ShipyardSwap", "Loadout", "ShipyardBuy", "Location"]:
                        if "Ship_Localised" in log_data:
                            modelo_nave = log_data["Ship_Localised"]
                        elif "Ship" in log_data:
                            # Mesma normalizacao do zolho-teste.py: alguns eventos so tem o
                            # "Ship" bruto (sem Ship_Localised), e sem isto "cobramkv".title()
                            # dava "Cobramkv" em vez de "Cobra Mk V", perdendo a calibracao.
                            nome_cru = log_data["Ship"].lower()
                            if "cobramk3" in nome_cru: modelo_nave = "Cobra Mk III"
                            elif "cobramk4" in nome_cru: modelo_nave = "Cobra Mk IV"
                            elif "cobramkv" in nome_cru: modelo_nave = "Cobra Mk V"
                            else: modelo_nave = log_data["Ship"].title()
                except: continue
        return modelo_nave
    except: return "Desconhecido"

def carregar_dados_calibracao(nave_atual):
    """ ARQUITETURA MULTI-NAVE ATUALIZADA """
    if os.path.exists(caminho_coordenadas):
        try:
            with open(caminho_coordenadas, "r") as f: 
                cfg = json.load(f)
            
            # Formato Novo: Procura a sub-chave direta da nave ativa (Evita que o Hauler seja esmagado)
            if nave_atual in cfg:
                dados_nave = cfg[nave_atual]
                cfg_pos = {k: int(v) for k, v in dados_nave["MONITOR_CONFIG"].items()}
                return cfg_pos, int(dados_nave["CX_NEUTRO"]), int(dados_nave["CY_NEUTRO"])
            
            # Formato Antigo: Retrocompatibilidade se o ficheiro ainda for do tipo flat
            if cfg.get("Nave") == nave_atual:
                cfg_pos = {k: int(v) for k, v in cfg["MONITOR_CONFIG"].items()}
                return cfg_pos, int(cfg["CX_NEUTRO"]), int(cfg["CY_NEUTRO"])
                
            print(f"[AVISO] Nenhuma calibração encontrada para '{nave_atual}'. A usar perfil genérico de emergência.")
        except Exception as e:
            print(f"[ERRO] Falha ao processar a matriz de calibração: {e}")
            
    return {"top": 1210, "left": 918, "width": 90, "height": 100}, 47, 48

# ==========================================
# 3. PIPELINE DE VISÃO: BÚSSOLA E HUD
# ==========================================
def localizar_bola(img_bgr, cx, cy):
    img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    mascara_final = np.zeros(img_hsv.shape[:2], dtype=np.uint8)
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
                    try: is_hollow = (mask[py, px] == 0)
                    except: is_hollow = False
                    
                    if is_hollow: return "ALVO_ATRAS", (px, py), mask, 0, 0
                    
                    historico_bola_x.append(px)
                    historico_bola_y.append(py)
                    if len(historico_bola_x) >= 3:
                        dx = px - cx
                        dy = py - cy
                        if abs(dx) <= DEAD_ZONE_BUSSOLA and abs(dy) <= DEAD_ZONE_BUSSOLA:
                            return "ALINHADO_MACRO", (px, py), mask, abs(dx), abs(dy)
                        
                        passos = []
                        if dy < -DEAD_ZONE_BUSSOLA: passos.append("W")
                        elif dy > DEAD_ZONE_BUSSOLA: passos.append("S")
                        if dx < -DEAD_ZONE_BUSSOLA: passos.append("A")
                        elif dx > DEAD_ZONE_BUSSOLA: passos.append("D")
                        return " + ".join(passos), (px, py), mask, abs(dx), abs(dy)
                    return "AQUECENDO", (px, py), mask, 0, 0
                    
    historico_bola_x.clear()
    historico_bola_y.clear()
    return "NÃO_DETETADO", None, mascara_final, 0, 0

def localizar_alvo_hud(sct):
    img_bgra = np.array(sct.grab(MONITOR_HUD))
    img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)

    cx_hud = MONITOR_HUD["width"] // 2
    cy_hud = MONITOR_HUD["height"] // 2

    # ==========================================
    # 1. TENTATIVA PRINCIPAL (TARGET.png)
    # ==========================================
    res_high = cv2.matchTemplate(img_bgr, templates_alvo_hud["TARGET.png"], cv2.TM_CCOEFF_NORMED)
    _, val_high, _, loc_high = cv2.minMaxLoc(res_high)

    # Se o High for aceitável, abortamos a pesquisa do Low. Histerese ativada.
    if val_high >= 0.68:
        h, w = templates_alvo_hud["TARGET.png"].shape[:2]
        tx = loc_high[0] + (w // 2)
        ty = loc_high[1] + (h // 2)

        dx = tx - cx_hud
        dy = ty - cy_hud
        return True, dx, dy, img_bgr, val_high, "TARGET"

    # ==========================================
    # 2. FALLBACK (target_low.png)
    # ==========================================
    res_low = cv2.matchTemplate(img_bgr, templates_alvo_hud["target_low.png"], cv2.TM_CCOEFF_NORMED)
    _, val_low, _, loc_low = cv2.minMaxLoc(res_low)

    if val_low >= 0.65:
        h, w = templates_alvo_hud["target_low.png"].shape[:2]
        tx = loc_low[0] + (w // 2)
        ty = loc_low[1] + (h // 2)

        # CORREÇÃO DO OFFSET GEOMÉTRICO (O TEU CÁLCULO)
        # Como o target_low foi recortado mais "abaixo e à direita", o centro dele dá um "salto" para a frente.
        # Ajusta estas duas variáveis para cravar os dois centros no mesmo píxel exato.
        OFFSET_DIREITA = 2  # Subtrai X píxeis do eixo X
        OFFSET_ABAIXO = 2   # Subtrai Y píxeis do eixo Y

        tx -= OFFSET_DIREITA
        ty -= OFFSET_ABAIXO

        dx = tx - cx_hud
        dy = ty - cy_hud
        return True, dx, dy, img_bgr, val_low, "target_low"

    # Se ambos falharem, devolve o maior score para efeitos de telemetria visual
    max_val_falha = max(val_high, val_low)
    melhor_nome = "TARGET" if val_high > val_low else "target_low"
    
    return False, 0, 0, img_bgr, max_val_falha, melhor_nome

# ==========================================
# 4. CONTROLADORES DE VOO CX_NEUTRO
# ==========================================
def aplicar_manobra_bussola(comando, dist_x, dist_y):
    if comando in ["NÃO_DETETADO", "ALINHADO_MACRO", "AQUECENDO"]:
        largar_todas_as_teclas()
        return
        
    if comando == "ALVO_ATRAS":
        for t in ["w", "a", "d"]: pydirectinput.keyUp(t)
        print(f"[INFO] ALVO_ATRAS -> IMPULSO GIGANTE (8x IMPULSO_BUSSOLA): ['s']")
        pydirectinput.keyDown('s')
        time.sleep(IMPULSO_BUSSOLA_GIGANTE)
        pydirectinput.keyUp('s')
        time.sleep(COOLDOWN_GIGANTE)
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
        print(f"[INFO] 4 * IMPULSO_BUSSOLA: {teclas_necessarias}") 
        for t in teclas_necessarias: pydirectinput.keyDown(t)
        time.sleep(4 * IMPULSO_BUSSOLA)
        pydirectinput.keyUp(t)
        time.sleep(2.0)
    else:
        print(f"[INFO] IMPULSO_BUSSOLA: {teclas_necessarias}") 
        for t in teclas_necessarias: pydirectinput.keyDown(t)
        time.sleep(IMPULSO_BUSSOLA)
        for t in teclas_necessarias: pydirectinput.keyUp(t)
        
    largar_todas_as_teclas()
    time.sleep(3.0)

def aplicar_manobra_hud(dx, dy):
    teclas = []
    if dy < -DEAD_ZONE_HUD: teclas.append('w') 
    elif dy > DEAD_ZONE_HUD: teclas.append('s') 
    if dx < -DEAD_ZONE_HUD: teclas.append('a') 
    elif dx > DEAD_ZONE_HUD: teclas.append('d') 

    for t in ["w", "s", "a", "d"]:
        if t not in teclas: pydirectinput.keyUp(t)

    if teclas:
        print(f"[INFO] IMPULSO_HUD: {teclas}") # CORRIGIDO: Agora lista os inputs corretos
        for t in teclas: pydirectinput.keyDown(t)
        time.sleep(IMPULSO_HUD) 
        for t in teclas: pydirectinput.keyUp(t)
        time.sleep(2.0) # Mantidos os 2 segundos estruturais de estabilização

def executar_roll_recuperacao(tentativa):
    """ Roda a nave ~45 graus sobre o eixo longitudinal para tirar um planeta
    ou um brilho da frente do HUD/alvo. Nao mexe na direcao do nariz. """
    largar_todas_as_teclas()
    print(f"[RECUPERACAO] Leitura bloqueada (planeta/brilho?). ROLL ~45 graus - tentativa {tentativa}/{MAX_ROLLS_RECUPERACAO}...")
    logging.warning(f"Roll de recuperacao {tentativa}/{MAX_ROLLS_RECUPERACAO} (tecla '{TECLA_ROLL}', {TEMPO_ROLL_45}s)")
    pydirectinput.keyDown(TECLA_ROLL)
    time.sleep(TEMPO_ROLL_45)
    pydirectinput.keyUp(TECLA_ROLL)
    time.sleep(2.0)  # estabilizar antes da proxima leitura

def executar_passo_alinhamento(sct, area_bussola, cx_neutro, cy_neutro):
    """ Executa um UNICO frame do pipeline de alinhamento (le bussola+HUD e
    aplica no maximo uma manobra corretiva). Devolve um dict com a leitura
    bruta e 'alinhado_frame' -- True quando o alvo do HUD está centrado
    nesse frame, OU quando a bússola (macro) já está perto do centro
    (ALINHADO_MACRO), sem esperar pelo travamento fino do HUD. Decisões de
    estabilidade, rolls de recuperação e timeouts ficam a cargo de quem
    chama — o loop principal abaixo usa 3s de estabilidade + rolls de
    recuperação; o plano_fuga.py usa uma leitura única, sem essas políticas. """
    img_bussola = cv2.cvtColor(np.array(sct.grab(area_bussola)), cv2.COLOR_BGRA2BGR)
    cmd_bussola, coords_bola, mask_hsv, dist_x, dist_y = localizar_bola(img_bussola, cx_neutro, cy_neutro)

    encontrou_hud, dx_hud, dy_hud, img_hud, max_val_hud, nome_tpl_hud = localizar_alvo_hud(sct)

    alvo_nas_costas = (cmd_bussola == "ALVO_ATRAS")

    resultado = {
        "img_bussola": img_bussola, "mask_hsv": mask_hsv, "coords_bola": coords_bola,
        "cmd_bussola": cmd_bussola, "dist_x": dist_x, "dist_y": dist_y,
        "encontrou_hud": encontrou_hud, "dx_hud": dx_hud, "dy_hud": dy_hud,
        "img_hud": img_hud, "max_val_hud": max_val_hud, "nome_tpl_hud": nome_tpl_hud,
        "alvo_nas_costas": alvo_nas_costas,
        "alinhado_frame": False, "comando_display": "",
    }

    if encontrou_hud and not alvo_nas_costas:
        if abs(dx_hud) <= DEAD_ZONE_HUD and abs(dy_hud) <= DEAD_ZONE_HUD:
            resultado["comando_display"] = "ALVO BLOQUEADO NO HUD!"
            resultado["alinhado_frame"] = True
            largar_todas_as_teclas()
        else:
            resultado["comando_display"] = f"MICRO-AJUSTE HUD (DX:{dx_hud} DY:{dy_hud})"
            aplicar_manobra_hud(dx_hud, dy_hud)
    elif cmd_bussola == "ALINHADO_MACRO":
        # Alinhado macro (bola perto do centro) passa a contar como alinhado
        # por si só -- já não fica à espera do HUD travar o alvo com
        # precisão antes de avançar (era o comportamento antigo, via
        # aplicar_manobra_bussola/"espera pelo HUD"). Nota: a recuperação por
        # roll para "bola centrada mas sem HUD visível" no loop standalone
        # abaixo fica agora inatingível a partir daqui -- desligada de
        # propósito, não é um esquecimento.
        resultado["comando_display"] = "MACRO: ALINHADO_MACRO (aceite como alinhado, sem esperar pelo HUD)"
        resultado["alinhado_frame"] = True
        largar_todas_as_teclas()
    else:
        if not coords_bola:
            resultado["comando_display"] = "MACRO: NÃO_DETETADO"
            largar_todas_as_teclas()
        else:
            resultado["comando_display"] = f"MACRO: {cmd_bussola}"
            aplicar_manobra_bussola(cmd_bussola, dist_x, dist_y)

    return resultado

# ==========================================
# 5. EXECUÇÃO PRINCIPAL
# ==========================================
if __name__ == "__main__":
    nave_ativa = obter_modelo_nave_atual()
    print(f"[INFO] Nave Actual: {nave_ativa}")
    MONITOR_CONFIG, CX_NEUTRO, CY_NEUTRO = carregar_dados_calibracao(nave_ativa)
    print(f"[INFO] Dados Calibracao: MONITOR_CONFIG: {MONITOR_CONFIG}\n    CX_NEUTRO: {CX_NEUTRO} CY_NEUTRO: {CY_NEUTRO}")

    tempo_inicio_centrado = None
    TEMPO_ESTABILIDADE_FINAL = 3.0 
    tempo_cego = None
    LIMITE_CEGO = 30.0
    rolls_recuperacao = 0   # rolls de ~45 graus ja gastos nesta manobra
    tempo_sem_hud = None    # bola ALINHADO_MACRO mas alvo do HUD invisivel (possivel brilho)
    tempo_inicio_manobra = time.time()
    LIMITE_MANOBRA = 180.0

    inicializar_infraestrutura()
    
    print(f"\n==================================================")
    print(f"R2D2 Sniper v11 - Pipeline de Orientação")
    print(f"Módulo de Prioridade Dinâmica | Nave: {nave_ativa}")
    print("==================================================\n")
    print("Abort manual: tecla ESC | Roll de recuperacao: tecla E (~45 graus)")
    print("Armando loop fechado em 1 segundo...")
    time.sleep(1)
    
    with mss.mss() as sct:
        try: monitor_jogo = sct.monitors[1]
        except: monitor_jogo = sct.monitors[0]
            
        area_bussola = {
            "top": monitor_jogo["top"] + MONITOR_CONFIG["top"],
            "left": monitor_jogo["left"] + MONITOR_CONFIG["left"],
            "width": MONITOR_CONFIG["width"], "height": MONITOR_CONFIG["height"]
        }
        
        while True:
            if keyboard.is_pressed('esc'):
                abortar_por_utilizador()
                
            if BOT_ATIVO:
                if time.time() - tempo_inicio_manobra > LIMITE_MANOBRA:
                    abortar_com_erro(f"Bloqueio de timeout. Manobra demorou mais de {LIMITE_MANOBRA}s.")

                passo = executar_passo_alinhamento(sct, area_bussola, CX_NEUTRO, CY_NEUTRO)
                img_bussola = passo["img_bussola"]
                coords_bola = passo["coords_bola"]
                cmd_bussola = passo["cmd_bussola"]
                encontrou_hud = passo["encontrou_hud"]
                dx_hud, dy_hud = passo["dx_hud"], passo["dy_hud"]
                img_hud = passo["img_hud"]
                max_val_hud, nome_tpl_hud = passo["max_val_hud"], passo["nome_tpl_hud"]
                alvo_nas_costas = passo["alvo_nas_costas"]
                comando_display = passo["comando_display"]

                if passo["alinhado_frame"]:
                    tempo_cego = None
                    tempo_sem_hud = None
                    rolls_recuperacao = 0  # leitura recuperada; futuras perdas tem direito a novos rolls

                    if tempo_inicio_centrado is None:
                        tempo_inicio_centrado = time.time()

                    if time.time() - tempo_inicio_centrado >= TEMPO_ESTABILIDADE_FINAL:
                        print("\n[SUCESSO] Vetor trancado. Coordenadas estáveis.")
                        tocar_alarme_sucesso()
                        falar("Alignment successful. Vector locked.")
                        sys.exit(0)
                elif encontrou_hud and not alvo_nas_costas:
                    # HUD encontrado mas ainda nao centrado (micro-ajuste ja aplicado
                    # dentro de executar_passo_alinhamento) - mesma limpeza de estado
                    # de recuperacao que o caso alinhado, so sem o timer de estabilidade.
                    tempo_cego = None
                    tempo_sem_hud = None
                    rolls_recuperacao = 0
                    tempo_inicio_centrado = None
                else:
                    tempo_inicio_centrado = None

                    if not coords_bola:
                        if tempo_cego is None: tempo_cego = time.time()
                        elif (time.time() - tempo_cego > TEMPO_CEGO_ANTES_ROLL
                              and rolls_recuperacao < MAX_ROLLS_RECUPERACAO):
                            # Grande parte destes casos e um planeta/brilho a tapar a
                            # bussola - rodar ~45 graus costuma resolver sem abortar.
                            rolls_recuperacao += 1
                            executar_roll_recuperacao(rolls_recuperacao)
                            tempo_cego = None  # reinicia a janela de observacao apos o roll
                        elif time.time() - tempo_cego > LIMITE_CEGO:
                            abortar_com_erro(f"Perda prolongada de telemetria visual da bússola ({rolls_recuperacao} rolls de recuperação sem efeito).")
                    else:
                        tempo_cego = None
                        if cmd_bussola == "ALINHADO_MACRO" and not encontrou_hud:
                            # Bola centrada mas o alvo do HUD nao aparece: brilho/planeta
                            # a tapar o target. O roll nao desalinha o nariz, so limpa a vista.
                            if tempo_sem_hud is None: tempo_sem_hud = time.time()
                            elif (time.time() - tempo_sem_hud > TEMPO_CEGO_ANTES_ROLL
                                  and rolls_recuperacao < MAX_ROLLS_RECUPERACAO):
                                rolls_recuperacao += 1
                                executar_roll_recuperacao(rolls_recuperacao)
                                tempo_sem_hud = None
                        else:
                            tempo_sem_hud = None

                if VISUAL_DEBUG:
                    img_hud_bussola = img_bussola.copy()
                    cv2.rectangle(img_hud_bussola, (CX_NEUTRO-DEAD_ZONE_BUSSOLA, CY_NEUTRO-DEAD_ZONE_BUSSOLA), 
                                           (CX_NEUTRO+DEAD_ZONE_BUSSOLA, CY_NEUTRO+DEAD_ZONE_BUSSOLA), (255, 255, 255), 1)
                    cv2.circle(img_hud_bussola, (CX_NEUTRO, CY_NEUTRO), 1, (0, 165, 255), -1)
                    if coords_bola:
                        cv2.circle(img_hud_bussola, coords_bola, 3, (0, 255, 0), -1)
                        
                    view_zoom = cv2.resize(img_hud_bussola, (300, 350), interpolation=cv2.INTER_NEAREST)
                    divisor = np.ones((350, 10, 3), dtype=np.uint8) * 80
                    
                    cv2.putText(view_zoom, comando_display, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0) if encontrou_hud else (0, 165, 255), 1)

                    img_hud_debug = cv2.resize(img_hud, (550, 350))
                    cv2.putText(img_hud_debug, f"HUD MATCH: {max_val_hud*100:.1f}% ({nome_tpl_hud})", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0) if encontrou_hud else (0, 0, 255), 2)
                    
                    if encontrou_hud:
                        cv2.putText(img_hud_debug, f"Desvio Real: DX:{dx_hud} DY:{dy_hud}", (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

                    # CORRIGIDO: Removida a barra cinzenta duplicada (limpeza visual completa)
                    painel_final = np.hstack((view_zoom, divisor, img_hud_debug))
                    cv2.imshow(NOME_JANELA_PROD, painel_final)
                    cv2.waitKey(1)
                
            time.sleep(0.04)
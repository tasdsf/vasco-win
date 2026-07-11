import os
import json
import cv2
import mss
import numpy as np
import time
import keyboard
import glob

# ==========================================
# 1. API NATIVA DO ELITE (LEITURA DO JOURNAL)
# ==========================================
def obter_modelo_nave_atual():
    try:
        caminho_logs = os.path.join(os.environ['USERPROFILE'], 'Saved Games', 'Frontier Developments', 'Elite Dangerous')
        if not os.path.exists(caminho_logs): return "Desconhecido"
        lista_logs = glob.glob(os.path.join(caminho_logs, "Journal.*.log"))
        if not lista_logs: return "Desconhecido"

        ultimo_log = max(lista_logs)
        modelo_nave = "Desconhecido"
        with open(ultimo_log, 'r', encoding='utf-8') as f:
            for linha in f:
                try:
                    log_data = json.loads(linha)
                    if log_data.get("event") in ["LoadGame", "ShipyardSwap", "Loadout", "ShipyardBuy", "Location"]:
                        if "Ship_Localised" in log_data:
                            modelo_nave = log_data["Ship_Localised"]
                        elif "Ship" in log_data:
                            nome_cru = log_data["Ship"].lower()
                            if "cobramk3" in nome_cru: modelo_nave = "Cobra Mk III"
                            elif "cobramk4" in nome_cru: modelo_nave = "Cobra Mk IV"
                            elif "cobramkv" in nome_cru: modelo_nave = "Cobra Mk V"
                            else: modelo_nave = log_data["Ship"].title()
                except: continue
        return modelo_nave
    except: return "Desconhecido"

# ==========================================
# 2. CARREGAMENTO INICIAL DINÂMICO
# ==========================================
nave_identificada = obter_modelo_nave_atual()

top_dinamico = 1180
left_dinamico = 970
width_dinamico = 80
height_dinamico = 90

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
# CORRIGIDO: Uso de "../" para evitar erros de Escape Sequence no Windows
caminho_memoria = os.path.join(diretorio_atual, "../memoria_bussola.json")
caminho_saida_config = os.path.join(diretorio_atual, "../coordenadas_bussola.json")

NOME_PAINEL = "R2D2 - Laboratorio de Calibracao da Bussola"

if os.path.exists(caminho_saida_config):
    try:
        with open(caminho_saida_config, "r") as f_in:
            cfg_persistente = json.load(f_in)

        if nave_identificada in cfg_persistente:
            mc = cfg_persistente[nave_identificada]["MONITOR_CONFIG"]
            top_dinamico = mc["top"]
            left_dinamico = mc["left"]
            width_dinamico = mc["width"]
            height_dinamico = mc["height"]

        elif cfg_persistente.get("Nave") == nave_identificada:
            mc = cfg_persistente["MONITOR_CONFIG"]
            top_dinamico = mc["top"]
            left_dinamico = mc["left"]
            width_dinamico = mc["width"]
            height_dinamico = mc["height"]
    except Exception: pass

try:
    with open(caminho_memoria, "r") as f:
        memoria = json.load(f)
except Exception: exit()

# ==========================================
# 3. INICIALIZAÇÃO E ALOCAÇÃO DE ECRÃS
# ==========================================
cv2.namedWindow(NOME_PAINEL, cv2.WINDOW_AUTOSIZE)

DEAD_ZONE = 4
salvar_dados = False

with mss.mss() as sct:
    monitors = sct.monitors
    try: monitor_jogo = monitors[1]
    except IndexError: monitor_jogo = monitors[0]

    print(f"\n==================================================")
    print(f">>> LAB AUTOMÁTICO ONLINE | NAVE: '{nave_identificada}'")
    print("==================================================\n")

    if len(monitors) > 2:
        cv2.moveWindow(NOME_PAINEL, monitors[2]["left"] + 50, monitors[2]["top"] + 50)
    else:
        cv2.moveWindow(NOME_PAINEL, 50, 50)

    centro_real_x = width_dinamico // 2
    centro_real_y = height_dinamico // 2

    # ==========================================
    # 4. LOOP DE PROCESSAMENTO ÓTICO
    # ==========================================
    while True:
        estado_acao = "SISTEMA: A aguardar interacção do Piloto..."

        if keyboard.is_pressed('up'): top_dinamico -= 1; time.sleep(0.04)
        elif keyboard.is_pressed('down'): top_dinamico += 1; time.sleep(0.04)
        elif keyboard.is_pressed('left'): left_dinamico -= 1; time.sleep(0.04)
        elif keyboard.is_pressed('right'): left_dinamico += 1; time.sleep(0.04)

        if keyboard.is_pressed('plus') or keyboard.is_pressed('shift+plus'):
            width_dinamico += 2; height_dinamico += 2; time.sleep(0.04)
        elif keyboard.is_pressed('-'):
            if width_dinamico > 40 and height_dinamico > 40:
                width_dinamico -= 2; height_dinamico -= 2; time.sleep(0.04)

        if keyboard.is_pressed('s'):
            print("\n[ENCERRAMENTO] A salvar centro ótico real da bússola...")
            salvar_dados = True
            break

        if keyboard.is_pressed('q'):
            salvar_dados = False
            break

        # Sem deteção automática de rebordo: o centro gravado é sempre o
        # centro geométrico da caixa (o quadrado branco) que alinhas
        # manualmente com as setas / +/- em cima do anel da bússola.
        cx_neutro = width_dinamico // 2
        cy_neutro = height_dinamico // 2
        centro_real_x = cx_neutro
        centro_real_y = cy_neutro

        area_real = {
            "top": monitor_jogo["top"] + top_dinamico,
            "left": monitor_jogo["left"] + left_dinamico,
            "width": width_dinamico,
            "height": height_dinamico
        }

        try:
            img_bgra = np.array(sct.grab(area_real))
            img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
        except Exception: continue

        img_analise = img_bgr.copy()

        bola_detetada = False
        mascara_vencedora = np.zeros(img_bgr.shape[:2], dtype=np.uint8)

        for perfil in memoria:
            img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(img_hsv, np.array(perfil['min']), np.array(perfil['max']))
            contornos_ponto, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if contornos_ponto:
                maior_ponto = max(contornos_ponto, key=cv2.contourArea)
                if cv2.contourArea(maior_ponto) > 1:
                    bola_detetada = True
                    mascara_vencedora = mask
                    M_p = cv2.moments(maior_ponto)
                    if M_p["m00"] != 0:
                        px = int(M_p["m10"] / M_p["m00"])
                        py = int(M_p["m01"] / M_p["m00"])
                        cv2.circle(img_analise, (px, py), 3, (0, 255, 0), -1)
                    break

        cv2.rectangle(img_analise, (cx_neutro-DEAD_ZONE, cy_neutro-DEAD_ZONE),
                                   (cx_neutro+DEAD_ZONE, cy_neutro+DEAD_ZONE), (255, 255, 255), 1)

        view_zoom = cv2.resize(img_analise, (400, 450), interpolation=cv2.INTER_NEAREST)
        mask_zoom = cv2.cvtColor(cv2.resize(mascara_vencedora, (400, 450), interpolation=cv2.INTER_NEAREST), cv2.COLOR_GRAY2BGR)

        divisor = np.ones((450, 10, 3), dtype=np.uint8) * 50
        top_row = np.hstack((view_zoom, divisor, mask_zoom))

        hud_texto = np.zeros((220, 810, 3), dtype=np.uint8)
        cv2.putText(hud_texto, f"SITUACAO ATUAL: {estado_acao}", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 255, 255), 1)
        cv2.putText(hud_texto, f"COORDENADAS: top={top_dinamico} | left={left_dinamico} | dim={width_dinamico}x{height_dinamico}px", (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        cv2.putText(hud_texto, f"BOLA RECONHECIDA: {'SIM' if bola_detetada else 'NAO'}", (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0) if bola_detetada else (0, 0, 255), 1)
        cv2.putText(hud_texto, f"CENTRO OTICO DA NAVE: X={centro_real_x} Y={centro_real_y}", (20, 145), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

        painel_final = np.vstack((top_row, hud_texto))
        cv2.imshow(NOME_PAINEL, painel_final)
        cv2.waitKey(10)

cv2.destroyAllWindows()

# ==========================================
# EXPORTAÇÃO DOS DADOS (CENTRO DE MASSA REAL)
# ==========================================
if salvar_dados:
    banco_coordenadas = {}
    if os.path.exists(caminho_saida_config):
        try:
            with open(caminho_saida_config, "r") as f_in:
                conteudo = json.load(f_in)
                if "Nave" in conteudo:
                    nave_antiga = conteudo["Nave"]
                    banco_coordenadas[nave_antiga] = {
                        "MONITOR_CONFIG": conteudo["MONITOR_CONFIG"],
                        "CX_NEUTRO": conteudo["CX_NEUTRO"],
                        "CY_NEUTRO": conteudo["CY_NEUTRO"]
                    }
                else: banco_coordenadas = conteudo
        except Exception: pass

    banco_coordenadas[nave_identificada] = {
        "MONITOR_CONFIG": {
            "top": top_dinamico,
            "left": left_dinamico,
            "width": width_dinamico,
            "height": height_dinamico
        },
        "CX_NEUTRO": int(centro_real_x),
        "CY_NEUTRO": int(centro_real_y)
    }

    try:
        with open(caminho_saida_config, "w") as f_out:
            json.dump(banco_coordenadas, f_out, indent=4)
        print(f"\n[SUCESSO] Calibração trancada. Centro real registado em X:{int(centro_real_x)} Y:{int(centro_real_y)}")
    except Exception as e: print(f"\n[ERRO] {e}")

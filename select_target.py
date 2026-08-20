import os
import sys
import time
import glob
import json
import logging
import pydirectinput
import cv2
import mss
import numpy as np
import pyttsx3
import pygetwindow as gw
import time
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
# 0. LOGGING E INFRAESTRUTURA
# ==========================================
diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_logs = os.path.join(diretorio_atual, "logs")
os.makedirs(pasta_logs, exist_ok=True)

# Configuração do Logger
logging.basicConfig(
    filename=os.path.join(pasta_logs, "r2d2_combined.log"),
    level=logging.ERROR,
    format='%(asctime)s - [SELECT_TARGET] - %(levelname)s - %(message)s'
)

def abortar_com_erro(mensagem):
    """ Regista o erro no log e dispara exit code 1 para o Orquestrador intercetar """
    print(f"\n[FATAL] {mensagem}")
    logging.error(mensagem)
    pydirectinput.press('backspace')
    sys.exit(1)

NOME_JANELA = "Ocular do Bot - Navegacao"
VISUAL_DEBUG = False # Muda para False para esconder as janelas

def inicializar_infraestrutura():
    """ Foca no jogo (Ecrã 1) e envia o painel visual para o Ecrã 2 APENAS SE VISUAL_DEBUG FOR TRUE """
    print("[SISTEMA] A configurar foco no jogo...")
    
    focar_jogo_seguro()
    time.sleep(0.5)
            
    if VISUAL_DEBUG:
        print("[SISTEMA] Modo Debug Ativo: A configurar janelas...")
        cv2.namedWindow(NOME_JANELA, cv2.WINDOW_NORMAL)
        with mss.mss() as sct:
            monitores = sct.monitors
            if len(monitores) > 2:
                ecra_secundario = monitores[2]
                cv2.moveWindow(NOME_JANELA, ecra_secundario["left"] + 50, ecra_secundario["top"] + 50)
            else:
                cv2.moveWindow(NOME_JANELA, 50, 50)
            cv2.setWindowProperty(NOME_JANELA, cv2.WND_PROP_TOPMOST, 1)

def focar_jogo_seguro():
    """ Foca o Elite Dangerous a nível de Sistema Operativo, sem enviar cliques de rato """
    print("[SISTEMA] A focar o Elite Dangerous via Windows API...")
    try:
        # Procura a janela pelo título (no Elite geralmente é "Elite - Dangerous (CLIENT)")
        janelas = gw.getWindowsWithTitle("Elite - Dangerous (CLIENT)")
        
        if janelas:
            janela_elite = janelas[0]
            # Traz a janela para a frente
            janela_elite.activate() 
            time.sleep(0.5)
            print("[OK] Jogo focado com sucesso e em segurança.")
            return True
        else:
            print("[ERRO] Janela do Elite Dangerous não encontrada!")
            return False
            
    except Exception as e:
        print(f"[AVISO] Falha ao forçar foco via OS: {e}")
        return False

# ==========================================
# 1. SETUP E ÁREAS
# ==========================================
MONITOR_PANEL = {"top": 200, "left": 50, "width": 1000, "height": 1200}
LOG_DIR = os.path.expanduser('~') + r"\Saved Games\Frontier Developments\Elite Dangerous"

pasta_imagens = os.path.join(diretorio_atual, 'images')

templates_nomes = {
    'nav_tab': 'NAVIGATION_SELECTED.png',
    'carrier': 'FLEET_CARRIER_NAME.png',
    'station': 'STATION.png',
    'station2': 'STATION1.png',
    'locked': 'LOCKED_DESTINATION.png',
    'unlocked': 'UNLOCKED_DESTINATION.png',
    'zahir_confirm': 'zahir_target_confirm.png',
    'futen_confirm': 'futen_target_confirm.png'
}

templates = {}
try:
    for chave, nome_arq in templates_nomes.items():
        caminho = os.path.join(pasta_imagens, nome_arq)
        img = cv2.imread(caminho, cv2.IMREAD_COLOR)
        if img is None: raise FileNotFoundError(f"Falta imagem: {caminho}")
        templates[chave] = img
    print(f"[SISTEMA] Módulo Dinâmico de Navegação Blindado carregado.")
except Exception as e:
    
    abortar_com_erro(f"Falha ao carregar assinaturas visuais: {e}")

# --- Voz ---
engine = pyttsx3.init()
def falar(texto):
    print(f"[VOZ] {texto}")
    engine.say(texto)
    engine.runAndWait()

# ==========================================
# 2. MOTOR DE CONTEXTO (LOGS DO ELITE)
# ==========================================
def obter_alvo_contextual_log():
    """ 
    Lê o Journal e decide o destino com base no ESTADO ATUAL (docked ou undocked).
    Retorna o DESTINO ALVO para marcar.
    """
    try:
        list_of_files = glob.glob(os.path.join(LOG_DIR, 'Journal.*.log'))
        if not list_of_files: 
            return "carrier" # Fallback de segurança
            
        latest_log = max(list_of_files, key=os.path.getctime)
        
        with open(latest_log, 'r', encoding='utf-8') as f:
            linhas = f.readlines()
            # Procurar o último evento para saber o estado atual
            ultimo_evento = None
            for linha in reversed(linhas):
                try:
                    data = json.loads(linha)
                    if 'StationType' in data:
                        ultimo_evento = data
                        # Prioridade: Docked/Undocked > Location > fallback
                        if 'Docked' in data.get('event', '') or 'Undocked' in data.get('event', ''):
                            break  # Usa o Docked/Undocked mais recente
                        # Event Location também indica onde está
                        elif data.get('event') == 'Location':
                            break  # Usa Location como fallback
                except json.JSONDecodeError:
                    continue
            
            # Verifica o evento encontrado
            if ultimo_evento and ultimo_evento.get('event') in ['Docked', 'Undocked', 'Location']:
                tipo = ultimo_evento['StationType']
                evento = ultimo_evento['event']
                
                print(f"[CONTEXTO] Localização: {evento} - Tipo: {tipo}")
                
                if evento == 'Undocked':
                    # Descolou recentemente: quer ir ao OPPOSTO
                    if tipo == 'FleetCarrier':
                        print("[CONTEXTO] Descolou de Carrier. Destino: ESTAÇÃO.")
                        return "station"
                    else:
                        print("[CONTEXTO] Descolou de Station. Destino: CARRIER.")
                        return "carrier"
                elif evento == 'Docked':
                    # Estacionado: quer ir ao OPPOSTO para descolar
                    if tipo == 'FleetCarrier':
                        print("[CONTEXTO] Dentro do carrier. Destino para descolar: ESTAÇÃO.")
                        return "station"
                    else:
                        print("[CONTEXTO] Dentro da estação. Destino para descolar: CARRIER.")
                        return "carrier"
                elif evento == 'Location':
                    # Último evento Location: assume que está no tipo
                    # Se Location Carrier -> descolar para estação
                    # Se Location Station -> descolar para carrier
                    if tipo == 'FleetCarrier':
                        print("[CONTEXTO] Location Carrier. Quer descolar e ir à ESTAÇÃO.")
                        return "station"
                    else:
                        print("[CONTEXTO] Location Station. Quer descolar e ir ao CARRIER.")
                        return "carrier"
            
            # Fallback total
            print("[CONTEXTO] Sem eventos válidos. A assumir: CARRIER.")
            return "carrier"
                    
    except Exception as e:
        print(f"[AVISO] Falha ao ler o log para contexto dinâmico ({e}).")
        
    print("[CONTEXTO] Sem eventos válidos. A assumir: CARRIER.")
    return "carrier"

# ==========================================
# 3. MOTOR DE VISÃO
# ==========================================
def procurar_template(template, nome_label, monitor, threshold=0.80, debug=False):
    if template is None: return False

    with mss.mss() as sct:
        img_bgra = np.array(sct.grab(monitor))
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
        resultado = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(resultado)

        encontrou = max_val >= threshold

        if debug:
            marca = "OK" if encontrou else "--"
            print(f"    [MATCH {marca}] {nome_label}: {max_val:.3f} (limiar {threshold:.2f})")

        if VISUAL_DEBUG:
            cor = (0, 255, 0) if encontrou else (0, 0, 255)
            if encontrou:
                h, w = template.shape[:2]
                cv2.rectangle(img_bgr, max_loc, (max_loc[0] + w, max_loc[1] + h), cor, 2)
            
            cv2.rectangle(img_bgr, (5, 5), (350, 80), (0, 0, 0), -1)
            cv2.putText(img_bgr, f"Alvo: {nome_label}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            cv2.putText(img_bgr, f"Match: {max_val:.2f} / {threshold:.2f}", (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.8, cor, 2)
            
            cv2.imshow(NOME_JANELA, img_bgr)
            cv2.waitKey(1)
        
        return encontrou

LIMIAR_STATION1 = 0.83  # STATION1.png é mais limpo/específico que o STATION.png,
                         # por isso aguenta um threshold mais alto sem perder deteções.
                         # Nunca aparecem os dois ao mesmo tempo, por isso cada um usa
                         # o seu próprio limiar em vez de partilharem o mesmo valor.

def procurar_alvo_dinamico(tipo_alvo, monitor, threshold, debug=False):
    """ Para 'station' valida com QUALQUER uma das duas variantes
        (STATION.png OU STATION1.png) — basta uma bater certo, cada uma
        com o seu próprio threshold. """
    if tipo_alvo == "station":
        return (procurar_template(templates['station'], "STATION", monitor, threshold, debug=debug) or
                procurar_template(templates['station2'], "STATION v2", monitor, LIMIAR_STATION1, debug=debug))
    return procurar_template(templates['carrier'], "CARRIER", monitor, threshold, debug=debug)

# ==========================================
# 4. LÓGICA DE MARCAÇÃO INTELIGENTE
# ==========================================
def marcar_destino_dinamico():
    tipo_alvo = obter_alvo_contextual_log()
    label_alvo = "STATION" if tipo_alvo == "station" else "CARRIER"
    
    # Define threshold baseado ao tipo de alvo
    # Carrier: medido ao vivo no scan real -> match real ~0.868, ruído das outras
    # linhas ~0.79-0.83. 0.88 era demasiado apertado e ficava acima do próprio
    # carrier (falhava por pouco, ~0.012); 0.85 mantém margem segura acima do
    # ruído mais alto visto (0.83) sem ultrapassar o match real.
    threshold_matching = 0.85 if tipo_alvo == "carrier" else 0.80
    
    print(f"\n>>> FASE: Marcar Destino ({label_alvo})...")
    pydirectinput.press('1')
    time.sleep(1.2)
    
    # Watchdog: Encontrar a aba NAVIGATION
    nav_found = False
    for tentativa_scan in range(8):
        # Usa hardcoded 0.85 para NAV TAB (consistente entre carriers e stations)
        if procurar_template(templates['nav_tab'], "NAV TAB", MONITOR_PANEL, 0.85):
            nav_found = True
            break
        if tentativa_scan == 3:
            # Metade das tentativas sem encontrar a aba -- o painel pode nunca
            # ter chegado a abrir (o '1' inicial pode ter falhado por race de
            # foco), e continuar a mandar 'q' as cegas roda a nave para a
            # esquerda em vez de ciclar separadores (nao ha aqui outro
            # template para confirmar "painel aberto, aba errada" como no
            # docking.py). Reenvia '1' uma vez antes de esgotar as restantes
            # tentativas.
            print("[AVISO] Painel lateral pode não ter aberto -- a reenviar '1' antes de continuar a varrer.")
            pydirectinput.press('1')
            time.sleep(1.2)
        pydirectinput.press('q'); time.sleep(0.5)

    if not nav_found:
        abortar_com_erro("Falha ao focar na aba de navegação do painel esquerdo após varrimento.")
    
    pydirectinput.press('d'); time.sleep(0.5)
    
    # Watchdog: Varrer a lista em busca do alvo (Máximo de 25 tentativas / scrolls)
    achou = False
    for i in range(25):
        print(f"[SCAN {i+1}/25]")
        # Usa threshold dinâmico baseado no tipo de alvo. debug=True imprime os
        # valores reais de match no terminal durante o próprio varrimento.
        if procurar_alvo_dinamico(tipo_alvo, MONITOR_PANEL, threshold_matching, debug=True):
            print(f"\n>>> FASE: ACHOU ({label_alvo})...")
            time.sleep(2.4) # Dá tempo ao menu do painel pop-up para renderizar
            achou = True
            break
        pydirectinput.press('s')
        time.sleep(0.7)  # Antes 0.4s: tempo curto a mais fazia saltar por cima da
                          # linha antes da seleção/scroll do painel acabar de renderizar
    
    if not achou:
        abortar_com_erro(f"Alvo dinâmico '{label_alvo}' não encontrado na lista de navegação após 25 varrimentos.")
    
    print(f"\n>>> FASE: Selecionando ({label_alvo})...")
    time.sleep(1.0)
    pydirectinput.press('space')
    time.sleep(1.0)

    # Validação de alvo: confirma pelo título do popup que abriu que o alvo
    # é mesmo o esperado (Zahir para carrier, Futen Spaceport para estação),
    # antes de fazer lock. Calibrado com images/find_area.png (ecrã real de
    # Futen Spaceport): o template correto (futen_target_confirm) bate a
    # 0.976 nesse ecrã, o template errado (zahir_target_confirm) fica a
    # 0.451 no mesmo ecrã -- margem ampla acima do limiar de 0.80. Falta
    # calibração equivalente no sentido inverso (ecrã real do Zahir); assume-se
    # por semelhança visual da UI (mesmo estilo de caixa/ícone/texto).
    template_confirm = 'zahir_confirm' if tipo_alvo == "carrier" else 'futen_confirm'
    nome_confirm = "ZAHIR" if tipo_alvo == "carrier" else "FUTEN SPACEPORT"
    if not procurar_template(templates[template_confirm], f"CONFIRM {nome_confirm}", MONITOR_PANEL, 0.80, debug=True):
        abortar_com_erro(f"Validação de alvo falhou: o popup aberto não confirma '{nome_confirm}' ({label_alvo}). Pode ter aberto o alvo errado -- lock cancelado.")

    # Verificação de Bloqueio (Lock)
    if procurar_template(templates['unlocked'], "UNLOCKED", MONITOR_PANEL, 0.80):
        pydirectinput.press('space')
        time.sleep(0.5)
        falar(f"{label_alvo} destination locked.")
    elif procurar_template(templates['locked'], "LOCKED", MONITOR_PANEL, 0.80):
        print("[LOG] Destino já estava trancado.")
        falar(f"{label_alvo} already locked.")
    else:
        # Não lança erro fatal aqui porque o jogo às vezes ofusca o botão com partículas holográficas
        print(f"[AVISO] Não foi possível validar visualmente o Lock no {label_alvo}. Assumindo sucesso cego.")
        pydirectinput.press('space')
        
    pydirectinput.press('1') # Fecha o painel
    time.sleep(1.0)
    return True

if __name__ == "__main__":
    inicializar_infraestrutura()
    
    print("O R2D2 assume os comandos em 1 segundos...")
    time.sleep(1)
    
    marcar_destino_dinamico()
    
    if VISUAL_DEBUG:
        cv2.destroyAllWindows()
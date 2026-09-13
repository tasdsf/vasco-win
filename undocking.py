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
log_test = os.path.join(pasta_logs, "undocking_test.png")
os.makedirs(pasta_logs, exist_ok=True)

# Configuração do Logger
logging.basicConfig(
    filename=os.path.join(pasta_logs, "r2d2_combined.log"),
    level=logging.ERROR,
    format='%(asctime)s - [UNDOCKING] - %(levelname)s - %(message)s'
)

def abortar_com_erro(mensagem):
    """ Regista o erro no log e dispara exit code 1 para o Orquestrador intercetar """
    print(f"\n[FATAL] {mensagem}")
    logging.error(mensagem)
    sys.exit(1)

NOME_JANELA = "R2D2 - Ocular de Auditoria"
VISUAL_DEBUG = False # Muda para False para esconder a janela

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
                pos_x = ecra_secundario["left"] + 50
                pos_y = ecra_secundario["top"] + 50
                cv2.moveWindow(NOME_JANELA, pos_x, pos_y)
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
# 1. SETUP DE GEOMETRIA E TEMPLATES
# ==========================================
MONITOR_MENU = {"top": 1100, "left": 1080, "width": 420, "height": 400}
MONITOR_CORNER = {"top": 100, "left": 1900, "width": 370, "height": 280}

STATUS_FILE = os.path.join(os.environ['USERPROFILE'], 'Saved Games', 'Frontier Developments', 'Elite Dangerous', 'Status.json')
ED_LOG_DIR = os.path.join(os.environ['USERPROFILE'], 'Saved Games', 'Frontier Developments', 'Elite Dangerous')

FSD_MASS_LOCKED_FLAG = 0x10000
MASS_LOCK_CONFIRMACOES = 2  # detecoes consecutivas exigidas antes de aceitar o sinal (evita 1 leitura a meio da escrita do ficheiro)

pasta_imagens = os.path.join(diretorio_atual, 'images')

templates_nomes = {
    'repair': 'repair.png',
    'autolaunch': 'AUTO_LAUNCH.png',
    'noselection': 'NO_SELECTION.png',
    'auto_complete': 'AUTO_LAUNCH_COMPLETE.png',
    'need_repair': 'NEED-REPAIR.png',
    'no_ammo': 'no_ammo.png'
}

templates = {}
try:
    for chave, nome_arq in templates_nomes.items():
        caminho = os.path.join(pasta_imagens, nome_arq)
        img = cv2.imread(caminho, cv2.IMREAD_COLOR)
        if img is None: raise FileNotFoundError(f"Falta a imagem: {caminho}")
        templates[chave] = img
    print(f"[SISTEMA] Módulo: Undocking Ótico Closed-Loop Carregado.")
except Exception as e:
    abortar_com_erro(f"Falha de Assinatura Visual ao arrancar: {e}")

# --- Motor de Voz ---
engine = pyttsx3.init()
def falar(texto):
    print(f"[VOZ] {texto}")
    engine.say(texto)
    engine.runAndWait()

# ==========================================
# 2. MOTOR DE VISÃO COMPUTACIONAL
# ==========================================
def procurar_template(template, nome_label, monitor, threshold=0.85, debug=False):
    if template is None: return False, 0.0
    
    with mss.mss() as sct:
        monitors = sct.monitors
        try:
            monitor_jogo = monitors[1]
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
        # teste begin
        cv2.imwrite(log_test, img_bgr) 
        # teste end
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
            
            cv2.rectangle(img_bgr, (0, 0), (350, 45), (0, 0, 0), -1)
            cv2.putText(img_bgr, f"{nome_label}: {max_val*100:.1f}% (Min: {threshold*100:.0f}%)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            img_show = cv2.resize(img_bgr, (700, 600))
            cv2.imshow(NOME_JANELA, img_show)
            cv2.waitKey(1)
        
        return encontrou, max_val

# ==========================================
# 2b. TELEMETRIA E CONTEXTO (JOURNAL/STATUS)
# ==========================================
def ler_cargo_telemetria():
    try:
        with open(STATUS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f).get("Cargo", 0)
    except Exception:
        return 0

def ler_telemetria_flags():
    try:
        with open(STATUS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f).get("Flags", 0)
    except Exception:
        return 0

def get_latest_log():
    lista_logs = glob.glob(os.path.join(ED_LOG_DIR, 'Journal.*.log'))
    if not lista_logs: return None
    return max(lista_logs, key=os.path.getctime)

def obter_tamanho_atual_log():
    latest_log = get_latest_log()
    if not latest_log: return 0
    try:
        return os.path.getsize(latest_log)
    except Exception:
        return 0

def ler_novos_eventos(posicao_ancora):
    latest_log = get_latest_log()
    if not latest_log: return []
    try:
        tamanho_atual = os.path.getsize(latest_log)
        if tamanho_atual <= posicao_ancora:
            return []
        with open(latest_log, 'r', encoding='utf-8') as f:
            f.seek(posicao_ancora)
            linhas_novas = f.readlines()
        eventos = []
        for linha in linhas_novas:
            try:
                data = json.loads(linha)
                if 'event' in data:
                    eventos.append(data)
            except json.JSONDecodeError:
                continue
        return eventos
    except Exception as e:
        print(f"[ERRO] Falha ao ler stream de logs: {e}")
        return []

def obter_tipo_estacao_atual():
    """ Le o Journal para tras a procura do ultimo evento Docked/Undocked/
    Location com 'StationType' -- mesma deteccao ja usada em
    select_target.py::obter_alvo_contextual_log(), so que aqui so interessa
    o tipo de estacao onde estamos agora, nao o proximo alvo. Devolve
    'FleetCarrier', outro valor de StationType, ou None se nao encontrar
    nenhum evento valido. """
    latest_log = get_latest_log()
    if not latest_log: return None
    try:
        with open(latest_log, 'r', encoding='utf-8') as f:
            linhas = f.readlines()
        for linha in reversed(linhas):
            try:
                data = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if 'StationType' in data and data.get('event') in ('Docked', 'Undocked', 'Location'):
                return data['StationType']
        return None
    except Exception as e:
        print(f"[AVISO] Falha ao ler o Journal para contexto de estacao: {e}")
        return None

def validar_carga_antes_de_descolar():
    """ So vale a pena descolar do carrier SEM carga a bordo (a venda ja
    aconteceu) e so vale a pena descolar da estacao COM carga a bordo (a
    compra ja aconteceu) -- sem isto a nave descolava as cegas e so se
    descobria a compra/venda falhada no fim de uma viagem inteira de
    supercruise (ver ESTACAO_ORIGEM em supercruise_assist.py, que fazia
    esta validacao tarde demais, ja a meio do salto). Aborta antes de
    qualquer tecla de descolagem se a carga nao bater com o local onde
    estamos. Se o tipo de estacao nao for determinavel (sem evento
    Docked/Location no Journal), nao bloqueia -- so avisa. """
    tipo_estacao = obter_tipo_estacao_atual()
    cargo_atual = ler_cargo_telemetria()
    print(f"[CONTEXTO] Local atual: {tipo_estacao or 'desconhecido'} | Carga a bordo: {cargo_atual}")

    if tipo_estacao == 'FleetCarrier' and cargo_atual and cargo_atual > 0:
        abortar_com_erro(
            f"Ainda ha carga a bordo ({cargo_atual}) no Fleet Carrier -- a venda nao foi "
            f"confirmada. A parar antes de descolar sem vender."
        )
    elif tipo_estacao is not None and tipo_estacao != 'FleetCarrier' and not cargo_atual:
        abortar_com_erro(
            "Sem carga a bordo na estacao -- a compra nao foi confirmada. "
            "A parar antes de descolar sem comprar."
        )
    elif tipo_estacao is None:
        print("[AVISO] Tipo de estacao atual desconhecido (sem evento Docked/Location no Journal) -- validacao de carga saltada.")

def aguardar_no_fire_zone_exit(ancora_log, timeout=60):
    """ Gate final apos o boost de saida (sequencia_salto): confirma que a
    nave saiu mesmo da no-fire-zone da estacao/carrier antes de entregar o
    controlo ao supercruise_assist.py. Duplo sinal, portado do
    Vasco-Nobara/Linux (ja validado em producao la): o evento 'No fire zone
    exited' do Journal (autoritativo, mas pode nao chegar a tempo se a
    sessao do Journal ficar presa) OU, em alternativa, a flag
    FSD_MASS_LOCKED da telemetria (Status.json) a desligar-se -- sinal de
    estado em tempo real e direto do jogo, sem depender de escrita no
    Journal. Exige duas leituras seguidas sem Mass Lock para nao confiar
    numa unica leitura a meio da escrita do ficheiro. Assim que qualquer um
    dos dois confirma, o supercruise pode arrancar de imediato. """
    print(f"\n>>> FASE: A confirmar saída da no-fire-zone via Journal + Telemetria (timeout {timeout}s)...")
    timeout_real = time.time() + timeout
    confirmacoes_mass_lock = 0

    while time.time() < timeout_real:
        for evento in ler_novos_eventos(ancora_log):
            if evento.get('event') == 'ReceiveText' and evento.get('Message') == '$STATION_NoFireZone_exited;':
                print("[OK] 'No fire zone exited' confirmado pelo Journal.")
                logging.info("No fire zone exited confirmado (Journal) -- handoff para supercruise autorizado.")
                return True

        flags = ler_telemetria_flags()
        if not bool(flags & FSD_MASS_LOCKED_FLAG):
            confirmacoes_mass_lock += 1
            if confirmacoes_mass_lock >= MASS_LOCK_CONFIRMACOES:
                print("[OK] 'No fire zone exited' confirmado pela telemetria (FSD_MASS_LOCKED desligado) -- Journal não confirmou a tempo.")
                logging.info("No fire zone exited confirmado (Telemetria FSD_MASS_LOCKED) -- handoff para supercruise autorizado.")
                return True
        else:
            confirmacoes_mass_lock = 0

        time.sleep(0.5)

    falar("Warning. Still inside station no fire zone.")
    abortar_com_erro("Timeout à espera de 'No fire zone exited' no Journal/Telemetria. A nave pode estar presa/bloqueada perto da estação.")

# ==========================================
# 3. MÁQUINA DE ESTADOS DETERMINÍSTICA
# ==========================================
def executar_auto_launch():
    print("\n==================================================")
    print(">>> CODE EXECUTION: MANOBRA DE UNDOCKING SEQUENCIAL")
    print("==================================================")
    
    # Passo 0: Estabilização do HUD do Menu
    print("A aguardar estabilização do menu...")
    timeout_menu = time.time() + 15  # Watchdog de 15 segundos
    while True:
        if time.time() > timeout_menu:
            falar("Error. Interface stabilization timeout.")
            abortar_com_erro("Timeout (15s) à espera que o botão 'Repair' estabilize no menu da estação.")
            
        m1, _ = procurar_template(templates['repair'], "ESTABILIZACAO", MONITOR_MENU, 0.70)
        if m1: break
        time.sleep(0.3)

    time.sleep(0.5)

    # Passo 0.5: Reabastecimento (combustível + reparação/munições) antes de
    # descolar. A gota (fuel) está sempre ativa ao aterrar (chegar gasta
    # combustível, falta sempre alguma coisa) -- corre sempre às cegas, sem
    # template calibrado para a validar visualmente.
    #
    # CRÍTICO: valida NEED-REPAIR e no_ammo ANTES de premir qualquer tecla,
    # não depois do fuel -- NEED-REPAIR.png é o par gota+chave AMBOS ativos.
    # Assim que se clica no fuel a gota muda de estado visualmente, e checar
    # depois disso faz o match falhar mesmo com a chave ainda ativa (ver
    # diagnóstico desta conversa: "a gota é validada e o need-repair falha").
    # need_repair a 0.70 (match real de 0.96 num print de jogo, pré-fuel) --
    # MATCH = precisa reparar.
    #
    # no_ammo.png é o INVERSO: captura o ícone de munições no estado
    # INATIVO (não precisa reabastecer) -- por isso MATCH = não repor, e só
    # se repõe munições quando este template NÃO dá match. Threshold 0.65 --
    # match real de 0.68 num print onde o ícone do lápis (indicador de
    # heatsinks, incluído no mesmo recorte) também estava inativo, o que
    # baixa o score; 0.65 dá margem para esse estado sem deixar de exigir
    # um match real.
    print("\nA validar estado do painel (NEED-REPAIR / no_ammo) antes de qualquer tecla...")
    need_repair, _ = procurar_template(templates['need_repair'], "NEED_REPAIR", MONITOR_MENU, 0.70, debug=True)
    ammo_inativo, _ = procurar_template(templates['no_ammo'], "NO_AMMO (inativo = não precisa)", MONITOR_MENU, 0.65, debug=True)
    # Snapshot dedicado (nao sobrescrito pelas chamadas seguintes de
    # procurar_template, ao contrario de log_test) -- sem isto, uma corrida
    # bem sucedida nao deixava nenhuma evidencia visual de que
    # NEED_REPAIR/NO_AMMO leram bem (ou mal) neste instante -- so se via em
    # jogo real, tarde demais, com a nave ja a descolar sem reabastecer
    # (ver diagnostico desta conversa). Best-effort, nunca pode travar o
    # undocking.
    try:
        cv2.imwrite(os.path.join(pasta_logs, "undocking_reabastecimento.png"), cv2.imread(log_test))
    except Exception as e:
        print(f"[AVISO] Falha ao gravar snapshot de reabastecimento: {e}")

    print("\nA reabastecer combustível: 3x 'w' + space...")
    for _ in range(3):
        pydirectinput.press('w')
        time.sleep(0.2)
    pydirectinput.press('space')
    time.sleep(0.5)

    if need_repair:
        print("A reparar (NEED-REPAIR detetado antes do fuel): 'd' + space...")
        pydirectinput.press('d')
        time.sleep(0.2)
        pydirectinput.press('space')
        time.sleep(0.5)

        if not ammo_inativo:
            print("A repor munições (detetado antes do fuel, após reparação): 'd' + space...")
            pydirectinput.press('d')
            time.sleep(0.2)
            pydirectinput.press('space')
            time.sleep(0.5)
        else:
            # Sem munições a repor -- não pode ficar a terminar no botão
            # Repair (fica selecionado/iluminado e o NO_SELECTION deixa de
            # validar mais à frente). 'd' extra só para sair dele.
            print("Sem reposição de munições -- 'd' extra para sair do botão Repair...")
            pydirectinput.press('d')
            time.sleep(0.2)
    else:
        if not ammo_inativo:
            print("A repor munições (detetado antes do fuel, sem reparação): 2x 'd' + space...")
            for _ in range(2):
                pydirectinput.press('d')
                time.sleep(0.2)
            pydirectinput.press('space')
            time.sleep(0.5)

    # Passo 1: Subida Mecânica
    print("\nA enviar comandos mecânicos: 3x 'w' + 1x 'space'...")
    for _ in range(3):
        pydirectinput.press('w')
        time.sleep(0.2)
    pydirectinput.press('space')
    time.sleep(0.3)
    
    # Passo 2: Validação Cega
    print("\nA validar 'NO_SELECTION' no topo do menu...")
    time.sleep(0.3) 
    noselect_val = 0.55#0.69 previous
    sucesso_idle, score_idle = procurar_template(templates['noselection'], "VAL_NO_SELECTION", MONITOR_MENU, noselect_val)
    if not sucesso_idle:
        falar("Error. Validation failed at menu top. Aborting sequence.")
        abortar_com_erro(f"Falha crítica ótica no teto. Match real: {score_idle*100:.1f}% (Exigia: {noselect_val*100}%)")
        
    print(f"[OK] 'NO_SELECTION' validado com {score_idle*100:.1f}%.")

    # Passo 3: Descida Mecânica
    print("\nA navegar para a posição do botão: 2x 's'...")
    for _ in range(2):
        pydirectinput.press('s')
        time.sleep(0.25)
    
    # Passo 4: Validação do Alvo
    print("\nA auditar foco do botão Auto-Launch...")
    time.sleep(0.3) 
    autolaunch_val = 0.61#0.9 previous
    sucesso_al, score_al = procurar_template(templates['autolaunch'], "VAL_AUTO_LAUNCH", MONITOR_MENU, autolaunch_val)
    if not sucesso_al:
        falar("Auto launch not detected.")
        abortar_com_erro(f"Botão Auto-Launch não detetado (Match real: {score_al*100:.1f}% / Exigia {autolaunch_val*100}%)")

    # Passo 5: Execução Limpa
    print("\n>>> TUDO VALIDADO! A disparar comando SPACE...")
    pydirectinput.press('space')
    return True

def aguardar_saida_estacao():
    print("\n>>> FASE: Detetar saída da estação...")
    print("[VISÃO] A monitorizar o HUD para a notificação 'AUTO LAUNCH COMPLETE'...")
    
    # Watchdog de 3 Minutos (A estação pode ter fila de trânsito)
    timeout_saida = time.time() + 180  
    
    while True: 
        if time.time() > timeout_saida:
            falar("Warning. Auto launch timeout exceeded.")
            abortar_com_erro("Timeout (180s) à espera de sair da estação. A nave está presa no trânsito?")

        encontrou, score = procurar_template(templates['auto_complete'], "AUTO_COMPLETE", MONITOR_CORNER, 0.7)
        if encontrou:
            print(f"\n>>> [VISÃO] Notificação detetada com {score*100:.1f}% de precisão!")
            print("[LOG] Saída da estação confirmada.")
            break
        time.sleep(0.4)
    
    print("[SUCESSO] Estamos no espaço aberto!")
    falar("Auto launch terminated commander.")

def sequencia_salto():
    print("\n>>> FASE: Impulso de Saída...")
    pydirectinput.keyDown('.')
    time.sleep(5)
    pydirectinput.keyUp('.')
    pydirectinput.press('tab')
    time.sleep(15.0)
    time.sleep(8.0)

# ==========================================
# 4. EXECUÇÃO PRINCIPAL
# ==========================================
if __name__ == "__main__":
    inicializar_infraestrutura()

    print("O R2D2 assume os comandos em 1 segundos...")
    time.sleep(1)

    validar_carga_antes_de_descolar()
    ancora_log = obter_tamanho_atual_log()

    sucesso_execucao = executar_auto_launch()
    if sucesso_execucao:
        aguardar_saida_estacao()
        sequencia_salto()
        aguardar_no_fire_zone_exit(ancora_log)

    if VISUAL_DEBUG:
        cv2.destroyAllWindows()
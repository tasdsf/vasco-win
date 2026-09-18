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
    """ Regista o erro no log e dispara exit code 1 para o Orquestrador intercetar.
    3x Backspace antes de sair -- sem isto a nave ficava presa a meio do
    painel (Starport Services/fila de ícones) onde a falha aconteceu, em
    vez de voltar ao ecrã principal para o próximo retry/etapa começar de
    um estado conhecido. Mesmo padrão já usado em comprar.py (que tem uma
    profundidade de menu semelhante); nem o Windows nem o Vasco-Nobara/
    Linux tinham isto aqui -- gap confirmado nos dois lados, não é
    regressão. """
    print(f"\n[FATAL] {mensagem}")
    logging.error(mensagem)
    for _ in range(3):
        pydirectinput.press('backspace')
        time.sleep(0.8)
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

# Fila de ícones (fuel/repair/ammo/farol de docagem) dentro do MONITOR_MENU
# -- coordenadas relativas medidas ao vivo (2026-09-16, carrier Zahir).
# Ícone do farol (4º) é para descer para o pad do carrier -- não interessa
# aqui. Repair é o 2º, ammo é o 3º.
FILA_ICONES_TOP_REL = 30
FILA_ICONES_HEIGHT = 90
ICONE_REPAIR_X_REL = (105, 210)
ICONE_AMMO_X_REL = (210, 315)

# Saturação HSV média medida ao vivo nos 4 ícones da fila (2026-09-16,
# carrier Zahir): ~73 no ícone cinzento (repair, OK, não precisa reparar)
# vs ~144-202 nos ícones coloridos/castanhos (ammo a precisar de reposição,
# farol). Separação limpa -- generaliza estação/carrier sem depender de um
# template de "estado" específico que pode ficar desatualizado: caso real
# confirmado nesta conversa, o antigo 'no_ammo.png' (calibrado como "ícone
# inativo, não precisa repor") batia a 0.944 num ícone de munição que na
# verdade precisava de reposição -- o template validava o estado errado
# para o render deste carrier.
ICONE_SATURACAO_LIMIAR = 110

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

def _icone_precisa_atencao(nome_label, x0_rel, x1_rel, debug=False):
    """ Lê a fila de ícones (fuel/repair/ammo/farol) no MONITOR_MENU e
    devolve True se o ícone na coluna [x0_rel:x1_rel] estiver colorido
    (precisa de atenção -- Space depois de selecionado) em vez de cinzento
    (OK, não precisa). Deteção por saturação HSV em vez de um template de
    "estado" específico -- generaliza estação/carrier sem depender de uma
    imagem calibrada só para um render (ver ICONE_SATURACAO_LIMIAR acima
    para o caso real que motivou isto: 'no_ammo.png' tinha o estado
    invertido para o carrier). """
    with mss.mss() as sct:
        monitors = sct.monitors
        try:
            monitor_jogo = monitors[1]
        except IndexError:
            monitor_jogo = monitors[0]
        area_real = {
            "top": monitor_jogo["top"] + MONITOR_MENU["top"] + FILA_ICONES_TOP_REL,
            "left": monitor_jogo["left"] + MONITOR_MENU["left"] + x0_rel,
            "width": x1_rel - x0_rel,
            "height": FILA_ICONES_HEIGHT,
        }
        img_bgra = np.array(sct.grab(area_real))
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)

    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    saturacao_media = float(hsv[:, :, 1].mean())
    precisa_atencao = saturacao_media > ICONE_SATURACAO_LIMIAR

    if debug:
        marca = "COLORIDO" if precisa_atencao else "CINZENTO"
        msg = f"[COR {marca}] {nome_label}: saturação média {saturacao_media:.1f} (limiar {ICONE_SATURACAO_LIMIAR})"
        print(f"    {msg}")
        logging.info(msg)

    return precisa_atencao

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
    # CRÍTICO: valida o estado de repair/ammo ANTES de premir qualquer
    # tecla, não depois do fuel -- assim que se clica no fuel a gota muda
    # de estado visualmente, e ler depois disso pode confundir-se com o
    # ícone do fuel a mudar (ver diagnóstico desta conversa: "a gota é
    # validada e o need-repair falha").
    #
    # Repair e ammo são lidos por COR (saturação HSV do próprio ícone,
    # ICONE_SATURACAO_LIMIAR acima) em vez de um template de "estado"
    # fixo -- cinzento = OK, colorido/castanho = precisa de Space depois
    # de selecionado. Substitui os antigos templates NEED-REPAIR.png/
    # no_ammo.png para esta decisão: caso real confirmado nesta conversa
    # (2026-09-16, carrier Zahir) em que 'no_ammo.png' (calibrado como
    # "ícone inativo, não precisa repor") batia a 0.944 num ícone de
    # munição que na verdade precisava de reposição -- o template validava
    # o estado errado para este render (carrier, não estação). A deteção
    # por cor generaliza aos dois contextos sem depender de recalibrar um
    # template por cada variante de UI.
    print("\nA validar estado do painel (repair/ammo por cor) antes de qualquer tecla...")
    need_repair = _icone_precisa_atencao("REPAIR", *ICONE_REPAIR_X_REL, debug=True)
    ammo_inativo = not _icone_precisa_atencao("AMMO", *ICONE_AMMO_X_REL, debug=True)
    # Mantido só para confirmar que estamos no ecrã certo mais abaixo (ver
    # comentário nesse bloco) -- não decide mais nada sobre reparação.
    need_repair_template, _ = procurar_template(templates['need_repair'], "NEED_REPAIR (só confirmação de ecrã)", MONITOR_MENU, 0.70, debug=True)
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

    # Confirma que estamos mesmo no ecrã certo (fila de ícones fuel/repair/
    # ammo) antes de avançar às cegas com o 3x 'w' + space -- portado do
    # Vasco-Nobara/Linux. NEED_REPAIR (chave-inglesa+gota em laranja, já
    # detetado acima) OU repair.png (chave-inglesa normal) têm de bater um
    # dos dois; se nenhum bater, não há garantia de estarmos no ecrã certo.
    if not need_repair_template:
        repair_normal_ok, score_nao_reparar = procurar_template(templates['repair'], "REPAIR (validação ecrã)", MONITOR_MENU, 0.80, debug=True)
        if not repair_normal_ok:
            abortar_com_erro(f"Nem NEED-REPAIR nem repair.png detetados ({score_nao_reparar*100:.1f}%) -- ecrã errado, a rotina não deve prosseguir às cegas.")

    print("\nA reabastecer combustível: 3x 'w' + space...")
    for _ in range(3):
        pydirectinput.press('w')
        time.sleep(0.2)
    pydirectinput.press('space')
    time.sleep(0.5)

    if need_repair:
        print("A reparar (NEED-REPAIR detetado antes do fuel): 'd' + space...")
        # 0.4s (era 0.2s) -- bug real já documentado e corrigido no
        # Vasco-Nobara/Linux: com 0.2s entre o 'd' e o 'space', o cursor
        # não tinha tido tempo de mudar de ícone (fuel -> repair) e o space
        # confirmava fuel outra vez em vez de reparar.
        pydirectinput.press('d')
        time.sleep(0.4)
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

    # Passo 5: Execução Limpa, com confirmação de que o botão desapareceu --
    # portado do Vasco-Nobara/Linux: um pydirectinput.press pode falhar em
    # silêncio, e sem confirmar que o botão reagiu nunca saberíamos. Até 3
    # tentativas de Space, confirmando entre cada uma que o Auto-Launch
    # deixou de estar visível.
    print("\n>>> TUDO VALIDADO! A disparar comando SPACE...")
    for tentativa in range(3):
        pydirectinput.press('space')
        time.sleep(1.0)
        ainda_visivel, _ = procurar_template(templates['autolaunch'], "VAL_AUTO_LAUNCH_POS", MONITOR_MENU, autolaunch_val, debug=True)
        if not ainda_visivel:
            break
        print(f"[AVISO] Botão Auto-Launch ainda visível após o SPACE (tentativa {tentativa+1}/3). A repetir...")
    else:
        print("[AVISO] Auto-Launch pode não ter disparado após 3 tentativas -- a prosseguir mesmo assim.")

    return True

def aguardar_saida_estacao():
    print("\n>>> FASE: Detetar saída da estação...")
    print("[VISÃO] A monitorizar o HUD para a notificação 'AUTO LAUNCH COMPLETE'...")

    # Watchdog de 9 Minutos (era 3 -- portado do Vasco-Nobara/Linux, que
    # documenta 180s como curto demais e a dar timeout em falso com a nave
    # ainda genuinamente em fila de trânsito).
    timeout_saida = time.time() + 540

    while True:
        if time.time() > timeout_saida:
            falar("Warning. Auto launch timeout exceeded.")
            abortar_com_erro("Timeout (540s) à espera de sair da estação. A nave está presa no trânsito?")

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
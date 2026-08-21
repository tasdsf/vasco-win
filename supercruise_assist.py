#!/usr/bin/env python3
"""
Supercruise Assist - Módulo Unificado (Mecânica Ótica + Telemetria)
Elite Dangerous Automation
"""

import os
import sys
import json
import glob
import time
import logging
import pydirectinput
import cv2
import mss
import numpy as np
import pyttsx3
import pygetwindow as gw
import time

# ==========================================
# 0. LOGGING E INFRAESTRUTURA
# ==========================================
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(PROJECT_DIR, "logs")
IMAGES_DIR = os.path.join(PROJECT_DIR, "images")
os.makedirs(LOGS_DIR, exist_ok=True)
# Ultima captura de procurar_template(), sobrescrita a cada chamada -- da
# evidencia forense de qualquer falha sem depender de VISUAL_DEBUG (mesmo
# padrao ja usado em undocking.py).
LOG_TEST = os.path.join(LOGS_DIR, "supercruise_test.png")

logging.basicConfig(
    filename=os.path.join(LOGS_DIR, "r2d2_combined.log"),
    level=logging.INFO,
    format='%(asctime)s - [SUPERCRUISE] - %(levelname)s - %(message)s'
)

# Importados DEPOIS do basicConfig acima de propósito: logging.basicConfig só
# tem efeito na primeira chamada do processo, e tanto plano_fuga.py como
# olho.py (importado por sua vez dentro de plano_fuga.py) também chamam
# logging.basicConfig -- importar aqui garante que é esta configuração (tag
# [SUPERCRUISE], nível INFO) que fica ativa.
import plano_fuga
import olho
from leg_state import leg_esta_limpa

def _capturar_screenshot_erro():
    """ Grava o ecrã inteiro do jogo em logs/erro_<timestamp>.png -- dá
    contexto visual ao anexar-se automaticamente à notificação do Discord
    (ver discord_notify.notificar_erro_discord). Best-effort: uma falha
    aqui não pode impedir o abort em curso. """
    try:
        caminho = os.path.join(LOGS_DIR, f"erro_{int(time.time())}.png")
        with mss.mss() as sct:
            try:
                monitor_jogo = sct.monitors[1]
            except Exception:
                monitor_jogo = sct.monitors[0]
            img_bgra = np.array(sct.grab(monitor_jogo))
            cv2.imwrite(caminho, cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR))
        print(f"[SCREENSHOT] Erro gravado em {caminho}")
    except Exception as e:
        print(f"[AVISO] Falha ao gravar screenshot de erro: {e}")

def abortar_com_erro(mensagem):
    print(f"\n[FATAL] {mensagem}")
    logging.error(mensagem)
    _capturar_screenshot_erro()
    sys.exit(1)

# Voz
engine = pyttsx3.init()
def falar(texto):
    print(f"[VOZ] {texto}")
    engine.say(texto)
    engine.runAndWait()

NOME_JANELA = "Ocular do Bot - Supercruise"
VISUAL_DEBUG = False

def inicializar_infraestrutura():
    print("[SISTEMA] A configurar foco no jogo...")

    focar_jogo_seguro()
    time.sleep(0.5)

    if VISUAL_DEBUG:
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
# 1. SETUP (TEMPLATES E TELEMETRIA)
# ==========================================
MONITOR_CENTER = {"top": 100, "left": 400, "width": 1100, "height": 800}
MONITOR_PANEL = {"top": 200, "left": 50, "width": 1000, "height": 1200}
STATUS_FILE = os.path.join(os.environ['USERPROFILE'], 'Saved Games', 'Frontier Developments', 'Elite Dangerous', 'Status.json')
ED_LOG_DIR = os.path.join(os.environ['USERPROFILE'], 'Saved Games', 'Frontier Developments', 'Elite Dangerous')

STATUS_FLAGS = {
    "SUPERCRUISE": 0x10,
    "FSD_MASS_LOCKED": 0x10000,
    "FSD_CHARGING": 0x20000,
    "HARDPOINTS_DEPLOYED": 0x40,
    "INTERDICTION": 0x800000,
}

# Leituras seguidas de "fora de Supercruise" exigidas antes de confiar na
# flag e ir verificar o Journal -- mesmo padrao do MASS_LOCK_CONFIRMACOES em
# undocking.py. ler_telemetria() devolve flags=0 (silenciosamente) em
# qualquer falha de leitura do Status.json, o que por si so já parecia
# "fora de Supercruise" -- uma única leitura a meio de uma reescrita do
# ficheiro não pode valer como confirmação.
CONFIRMACOES_FORA_SUPERCRUISE = 2

TEMPLATES_NOMES = {
    'nav_tab': 'NAVIGATION_SELECTED.png',
    'charging': 'CHARGING.png',
    'locked': 'LOCKED_DESTINATION.png',
    'unlocked': 'UNLOCKED_DESTINATION.png',
    'assist_active': 'SUPERCRUISE_ASSIST_ACTIVE.png',
    'align_warning': 'SUPERCRUISE_ASSIST_INACTIVE.png',
    # 'Dois triangulos azuis' que aparecem um pouco acima do aviso de
    # desalinhamento quando o alvo fica travado -- carregado mas ja nao
    # usado por nenhuma funcao (engatar_assist_e_alinhar deixou de depender
    # deste marcador, ver essa funcao). Mantido caso volte a ser util.
    'assist_locked': 'SUPERCRUISE_ASSIST_LOCKED.png',
    'throttle_up': 'THROTTLE_UP.png',
    # Reaproveitados de select_target.py (mesmas imagens, mesmo MONITOR_PANEL)
    # -- usados em engatar_assistencia_menu() para confirmar o alvo certo.
    'zahir_confirm': 'zahir_target_confirm.png',
    'futen_confirm': 'futen_target_confirm.png',
}

templates = {}
try:
    for chave, nome_arq in TEMPLATES_NOMES.items():
        caminho = os.path.join(IMAGES_DIR, nome_arq)
        img = cv2.imread(caminho, cv2.IMREAD_COLOR)
        if img is None: raise FileNotFoundError(f"Falta imagem: {caminho}")
        templates[chave] = img
    print("[SISTEMA] Módulo Unified Supercruise carregado.")
except Exception as e:
    abortar_com_erro(f"Erro ao carregar templates visuais: {e}")

# ==========================================
# 2. MOTORES CORE (VISÃO E DADOS)
# ==========================================
def procurar_template(template, nome_label, monitor, threshold=0.75, debug=False, sct=None):
    # sct opcional -- reutiliza uma sessão mss já aberta em vez de abrir e
    # fechar uma nova a cada chamada. Criar/destruir sessões mss repetidas
    # vezes por segundo (como em engatar_assist_e_alinhar, que faz 2-3
    # chamadas por tick durante até 60s) pode bloquear a API de captura de
    # ecrã do Windows por vários segundos de cada vez -- suspeito de causar
    # os hangs observados em jogo real (ver diagnóstico desta conversa).
    def _procurar(sessao):
        img_bgra = np.array(sessao.grab(monitor))
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
        cv2.imwrite(LOG_TEST, img_bgr)
        res = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        encontrou = max_val >= threshold

        if debug:
            marca = "OK" if encontrou else "--"
            print(f"    [MATCH {marca}] {nome_label}: {max_val:.3f} (limiar {threshold:.2f})")

        if VISUAL_DEBUG:
            cor = (0, 255, 0) if encontrou else (0, 0, 255)
            if encontrou:
                h, w = template.shape[:2]
                cv2.rectangle(img_bgr, max_loc, (max_loc[0] + w, max_loc[1] + h), cor, 2)
            cv2.putText(img_bgr, f"{nome_label}: {max_val:.2f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, cor, 2)
            cv2.imshow(NOME_JANELA, img_bgr)
            cv2.waitKey(1)

        return encontrou

    if sct is not None:
        return _procurar(sct)
    with mss.mss() as _sct:
        return _procurar(_sct)

def ler_telemetria(debug=False):
    try:
        with open(STATUS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            flags = data.get("Flags", 0)
            if debug:
                ativas = [nome for nome, bit in STATUS_FLAGS.items() if flags & bit]
                print(f"    [FLAGS] {hex(flags)} -> {', '.join(ativas) if ativas else '(nenhuma flag conhecida ativa)'}")
            return flags
    except Exception as e:
        if debug:
            print(f"    [FLAGS] Falha a ler {STATUS_FILE}: {e}")
        return 0

def ler_destino_telemetria(debug=False):
    try:
        with open(STATUS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            destino = data.get("Destination")
            if debug:
                print(f"    [DESTINO] {destino if destino else '(sem destino de navegacao gravado)'}")
            return destino
    except Exception as e:
        if debug:
            print(f"    [DESTINO] Falha a ler {STATUS_FILE}: {e}")
        return None

def _registar_los_se_perna_limpa():
    """ Só regista a observação automática de LOS se a perna atual
    (undocking->supercruise, ver leg_state.py) não teve nenhum erro/retry
    até agora -- um salto que só "passou" porque uma tentativa anterior
    falhou (ou teve ajuda manual) não é uma medição independente, e
    contaminaria o ajuste de fase/período em los_checker.py. """
    if leg_esta_limpa():
        registar_los_visivel_auto()
    else:
        print("[LOS-AUTO] Perna com erro/retry -- observação não registada "
              "(evita contaminar o ajuste com um salto que pode ter tido ajuda).")

def get_latest_log():
    lista_logs = glob.glob(os.path.join(ED_LOG_DIR, 'Journal.*.log'))
    if not lista_logs: return None
    return max(lista_logs, key=os.path.getmtime)

def obter_tamanho_atual_log():
    """ Posição (bytes) no fim do Journal atual, neste instante -- usada
    como âncora em confirmar_chegada_por_journal() para que essa função só
    veja eventos escritos DEPOIS deste ponto, nunca de uma perna anterior. """
    latest_log = get_latest_log()
    if not latest_log: return 0
    try:
        return os.path.getsize(latest_log)
    except Exception:
        return 0

def confirmar_chegada_por_journal(ancora_log=None):
    """ Confirma se a queda de Supercruise mais recente foi mesmo uma chegada
    intencional ao destino trancado. Percorre o Journal para trás a partir do
    'SupercruiseExit' mais recente e vê qual destes aparece primeiro:
    'SupercruiseDestinationDrop' (chegada, dentro desta perna de supercruise)
    ou 'SupercruiseEntry'/'StartJump' (início desta perna sem nunca ter havido
    drop de destino -- não foi chegada). Não depende de adjacência estrita
    entre as duas linhas (uma versão anterior desta função dependia) --
    aguenta eventos irrelevantes (Music, ReceiveText, etc.) pelo meio. Devolve
    False para qualquer causa que não seja chegada (interdição, mass lock
    inesperado, obstáculo) sem as distinguir -- só precisamos de saber se foi
    ou não foi chegada.

    ancora_log (opcional, posição em bytes de obter_tamanho_atual_log()):
    se dado, ignora tudo o que foi escrito no Journal ANTES desta posição --
    sem isto, "o SupercruiseExit mais recente no ficheiro" podia ser de uma
    perna anterior (uma chegada legítima já confirmada há minutos), e um
    'em_supercruise' falsamente False por um instante (Status.json a meio de
    reescrita) confirmava "chegada" com base em dados completamente
    desatualizados -- foi isto que aconteceu num caso real (ver diagnóstico
    desta conversa: chegada_curta declarada no mesmo segundo em que o
    alinhamento arrancou, sem a nave ter chegado a lado nenhum). """
    EVENTOS_FRONTEIRA = {"SupercruiseDestinationDrop", "SupercruiseEntry", "StartJump"}
    try:
        ultimo_log = get_latest_log()
        if not ultimo_log:
            print("[AVISO] Sem ficheiros de Journal encontrados -- a assumir que NÃO foi chegada.")
            return False

        with open(ultimo_log, 'r', encoding='utf-8') as f:
            if ancora_log:
                f.seek(ancora_log)
            linhas = [linha for linha in f.readlines() if linha.strip()]

        idx_exit = None
        for i in range(len(linhas) - 1, -1, -1):
            try:
                dados = json.loads(linhas[i])
            except json.JSONDecodeError:
                continue
            if dados.get("event") == "SupercruiseExit":
                idx_exit = i
                break

        if idx_exit is None or idx_exit == 0:
            print("[AVISO] Sem SupercruiseExit localizável no Journal -- a assumir que NÃO foi chegada.")
            return False

        evento_fronteira = None
        for i in range(idx_exit - 1, -1, -1):
            try:
                dados = json.loads(linhas[i])
            except json.JSONDecodeError:
                continue
            if dados.get("event") in EVENTOS_FRONTEIRA:
                evento_fronteira = dados.get("event")
                break

        confirmado = evento_fronteira == "SupercruiseDestinationDrop"
        msg = f"SupercruiseExit -> evento fronteira mais recente antes dele: '{evento_fronteira}' -> chegada_confirmada={confirmado}"
        print(f"[JOURNAL] {msg}")
        logging.info(msg)
        return confirmado
    except Exception as e:
        print(f"[AVISO] Falha ao ler Journal para confirmar chegada: {e}")
        return False

# ==========================================
# 2b. REGISTO AUTOMÁTICO DE OBSERVAÇÃO LOS
# ==========================================
def registar_los_visivel_auto():
    """ Regista na BD partilhada (ver .env.example) uma observação LOS
    'visivel' automática: um salto de supercruise iniciado com sucesso
    implica que o alvo estava visível (sem o planeta no meio), e a nave
    ainda está junto à estação/carrier de partida.

    origem='auto-win': distingue estas observações automáticas das manuais
    ('win' neste portátil, 'linux' no PC Nobara) — permite filtrá-las na
    regressão se um dia levantarem suspeitas.

    NUNCA pode partir o voo: dependências em falta, .env por configurar,
    BD inacessível ou qualquer outra falha são apenas reportadas e
    ignoradas — o supercruise continua na mesma. """
    try:
        from datetime import datetime, timezone
        from dotenv import load_dotenv
        import psycopg2
        from los_checker import obter_sistema_atual

        load_dotenv(os.path.join(PROJECT_DIR, ".env"))
        host = os.environ.get("R2D2_DB_HOST")
        password = os.environ.get("R2D2_DB_PASSWORD")
        if not host or not password:
            return  # .env não configurado nesta máquina — segue sem registar

        ed_log_dir = os.path.join(os.environ['USERPROFILE'], 'Saved Games',
                                  'Frontier Developments', 'Elite Dangerous')
        sistema = obter_sistema_atual(ed_log_dir)
        if not sistema:
            print("[LOS-AUTO] Sistema desconhecido — observação não registada.")
            return

        conn = psycopg2.connect(
            host=host,
            port=os.environ.get("R2D2_DB_PORT", "5432"),
            dbname=os.environ.get("R2D2_DB_NAME", "ED"),
            user=os.environ.get("R2D2_DB_USER", "r2d2"),
            password=password,
            connect_timeout=4,
        )
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO los_observacoes (sistema, timestamp_utc, estado, nota, origem) "
                    "VALUES (%s, %s, %s, %s, %s);",
                    (sistema, datetime.now(timezone.utc), "visivel",
                     "automatica: salto supercruise iniciado com sucesso em modo auto "
                     "(pelo sim pelo nao: pode ter tido ajuda do utilizador)",
                     "auto-win"))
        finally:
            conn.close()
        print(f"[LOS-AUTO] Observação 'visivel' registada na BD para '{sistema}'.")
    except Exception as e:
        print(f"[LOS-AUTO] Falha ao registar observação (ignorada, o voo continua): {e}")

# ==========================================
# 3. FASE 0: SALTO E TELEMETRIA
# ==========================================
def iniciar_salto_seguro():
    print("\n>>> FASE 0: Iniciar Salto (J)...")

    destino = ler_destino_telemetria(debug=True)
    destino_nome = destino.get("Name") if destino else None
    match_locked = procurar_template(templates['locked'], "LOCKED_DESTINATION", MONITOR_CENTER, 0.75, debug=True)
    match_unlocked = procurar_template(templates['unlocked'], "UNLOCKED_DESTINATION", MONITOR_CENTER, 0.75, debug=True)
    msg_diag = (f"Pre-salto -> destino telemetria: {destino_nome}, "
                f"template LOCKED_DESTINATION={match_locked}, UNLOCKED_DESTINATION={match_unlocked}")
    print(f"[DIAGNOSTICO] {msg_diag}")
    logging.info(msg_diag)

    # Trava de carga a bordo movida para undocking.py::validar_carga_antes_de_descolar()
    # -- so vale a pena descolar do carrier sem carga (venda confirmada) ou
    # descolar da estacao com carga (compra confirmada). Detetar isso aqui,
    # ja a meio do salto, era tarde demais.

    # Se um retry anterior já deixou a nave em Supercruise (ex.: o salto teve
    # sucesso mas engatar_assistencia_menu falhou a seguir, o processo abortou,
    # e o vasco.py relançou este script do zero), voltar a carregar em 'j' às
    # cegas não faz sentido -- e foi isto que causou os "Falha desconhecida
    # ao iniciar o salto" repetidos e uma queda real de Supercruise sem
    # motivo (ver diagnóstico desta conversa). Confirma o estado atual antes
    # de decidir se há salto para iniciar.
    flags_antes = ler_telemetria(debug=True)
    if bool(flags_antes & STATUS_FLAGS["SUPERCRUISE"]):
        msg_ja_cruise = "Já em Supercruise antes de qualquer tecla -- a saltar a iniciação do salto (provável retry pós-falha)."
        print(f"[OK] {msg_ja_cruise}")
        logging.info(msg_ja_cruise)
        return True

    print("[LOG] A enviar 'j' (iniciar salto) + 'right shift' (acelerar)...")
    pydirectinput.press('j')
    pydirectinput.press('shiftright')

    # 'right shift' é um toque único (press), não uma tecla para segurar -
    # por isso já não há keyDown/keyUp nem watchdog visual (CHARGING/
    # THROTTLE_UP) a temporizar a aceleração. Em vez disso esperamos um tempo
    # fixo de 8s (carga + aceleração) antes de ir validar por telemetria.
    print("[LOG] A aguardar 8s antes de validar telemetria...")
    time.sleep(8)

    print("[TELEMETRIA] A validar telemetria do FSD ...")

    # Poll em vez de leitura única: evita falsos negativos por
    # (a) a leitura calhar mesmo na janela de transição entre "a carregar" e
    # "já em Supercruise" onde nenhuma das duas flags está ativa por um
    # instante, ou (b) apanhar o Status.json a meio de uma reescrita do jogo
    # (ler_telemetria devolve 0 silenciosamente nesse caso).
    flags = 0
    salto_confirmado = None
    for tentativa in range(7):
        print(f"[LOG] Poll telemetria {tentativa+1}/7...")
        flags = ler_telemetria(debug=True)
        if bool(flags & STATUS_FLAGS["FSD_CHARGING"]):
            salto_confirmado = "carga"
            break
        if bool(flags & STATUS_FLAGS["SUPERCRUISE"]):
            salto_confirmado = "supercruise"
            break
        time.sleep(0.5)

    # 1. Confirmou que está a carregar
    if salto_confirmado == "carga":
        print("[OK] Motor FSD em carga confirmada pela telemetria.")
        _registar_los_se_perna_limpa()
        # Espera o salto acontecer
        pydirectinput.press('x')
        time.sleep(4.5)
        return True

    # 1b. Já não está a carregar porque o salto já teve sucesso entretanto
    if salto_confirmado == "supercruise":
        print("[OK] Já em Supercruise (a carga completou antes da leitura de telemetria).")
        _registar_los_se_perna_limpa()
        pydirectinput.press('x')
        return True

    pydirectinput.press('x')

    print(f"[LOG] Nenhuma flag de sucesso confirmada. Ultimas flags lidas: {hex(flags)}. A testar causas conhecidas...")

    # 2. Se não está a carregar nem em supercruise, usa as regras do Hermes para descobrir o porquê
    if bool(flags & STATUS_FLAGS["FSD_MASS_LOCKED"]):
        pydirectinput.press('x')
        abortar_com_erro("Nave bloqueada por Mass Lock da estação/planeta.")

    if bool(flags & STATUS_FLAGS["HARDPOINTS_DEPLOYED"]):
        pydirectinput.press('x')
        abortar_com_erro("Armas ou Trem de Aterragem abertos. Impossível saltar.")

    if procurar_template(templates['align_warning'], "ALIGN", MONITOR_CENTER, 0.82, debug=True):
        pydirectinput.press('x')
        abortar_com_erro("Vetor de proa totalmente desalinhado do destino.")

    pydirectinput.press('x')
    abortar_com_erro("Falha desconhecida ao iniciar o salto: FSD não confirma carga nem Supercruise, e nenhuma causa conhecida (Mass Lock / Hardpoints / Alinhamento) foi detetada.")

def aguardar_supercruise_confirmado(timeout=30):
    """Confirma pela telemetria (Status.json, flag SUPERCRUISE=0x10) que ja
    estamos mesmo em supercruise antes de abrir o menu do assist -- sem isto
    o menu pode ser aberto ainda em espaco normal/transicao."""
    print("\n>>> A confirmar entrada em Supercruise pela telemetria...")
    limite = time.time() + timeout
    while time.time() < limite:
        flags = ler_telemetria()
        if bool(flags & STATUS_FLAGS["SUPERCRUISE"]):
            print("[OK] Supercruise confirmado pela telemetria.")
            return True
        time.sleep(0.5)
    abortar_com_erro(f"Timeout ({timeout}s). Supercruise nunca foi confirmado pela telemetria.")


# ==========================================
# 4. FASE 1: NAVEGAÇÃO MECÂNICA NO MENU
# ==========================================
def confirmar_aba_navigation(tentativas_q=6):
    """ Confirma que a aba NAVIGATION está visível, ciclando 'q' se
    necessário. Não abre nem fecha o painel -- assume que quem chama já
    tratou disso. Usada tanto na abertura inicial do painel como para
    recuperar dentro do passo 2 (ver engatar_assistencia_menu). """
    for _ in range(tentativas_q):
        if procurar_template(templates['nav_tab'], "NAV TAB", MONITOR_PANEL, 0.80, debug=True):
            return True
        pydirectinput.press('q')
        time.sleep(0.5)
    return False

def fechar_painel_se_aberto():
    """ '1' é um toggle -- só faz sentido premir para fechar se o painel
    estiver mesmo aberto neste momento (confirmado pelo nav_tab). Premir às
    cegas depois de vários Backspace arrisca ABRIR um painel que já estava
    fechado, em vez de o fechar -- foi isto que deixou o painel preso aberto
    depois de uma falha em jogo real (ver diagnóstico desta conversa). """
    if procurar_template(templates['nav_tab'], "NAV TAB (verificação antes de fechar)", MONITOR_PANEL, 0.80, debug=True):
        pydirectinput.press('1')

def assist_ja_ativo():
    """ Confirma no HUD (painel fechado) se o Supercruise Assist já está
    ligado -- 'assist_active' (ligado e a apontar para o alvo) ou
    'align_warning'/SUPERCRUISE_ASSIST_INACTIVE.png (ligado mas ainda
    desalinhado do alvo -- apesar do nome do ficheiro, esta imagem só
    aparece com o assist LIGADO, não desligado). Só a ausência de ambas
    significa que o assist está mesmo desligado. """
    return (procurar_template(templates['assist_active'], "ASSIST ACTIVE (pré-toggle)", MONITOR_CENTER, 0.75, debug=True)
            or procurar_template(templates['align_warning'], "ASSIST LIGADO MAS DESALINHADO (pré-toggle)", MONITOR_CENTER, 0.82, debug=True))

def engatar_assistencia_menu():
    print("\n>>> FASE 1: Navegação no Painel Esquerdo...")

    # Reduzir velocidade ANTES de qualquer leitura de HUD -- a nave oscila em
    # velocidade de supercruise, e nenhuma leitura de bússola/HUD (nem os
    # templates assist_active/align_warning usados por assist_ja_ativo()
    # abaixo) é de confiar sem isto. O 'x' por si só não chega -- a nave não
    # trava instantaneamente, por isso a pausa a seguir é essencial (sem
    # ela, assist_ja_ativo() lia o ecrã quase ao mesmo tempo do 'x', com a
    # nave ainda a oscilar -- confirmado em jogo real: rolls de recuperação
    # a disparar por leitura de bússola pouco fiável logo à entrada).
    pydirectinput.press('x')
    time.sleep(1.5)

    # 'já está ligado, não mexer' -- D+Space lá dentro do painel é um
    # TOGGLE, não um "ligar": se esta função for chamada outra vez (retry
    # depois de uma falha mais à frente no fluxo, com o Assist já a
    # funcionar), abrir o painel e voltar a D+Space desligava o que já
    # estava a funcionar. assist_ja_ativo() já cobre os dois sub-estados
    # (ativo a apontar, ou ativo mas ainda à espera de alinhamento) -- só se
    # avança para o toggle quando NENHUM dos dois aparece. Padrão adotado do
    # Vasco-Nobara/Linux: sai logo aqui em vez de só saltar o D+Space mais à
    # frente -- mais simples e mais seguro.
    if assist_ja_ativo():
        print(">>> Assistência já parece ligada (ativa, ou ativa mas ainda não alinhada) -- nada a fazer.")
        return True

    # Alvo esperado (para validar visualmente o passo 2) -- reaproveita a
    # mesma logica/templates de select_target.py, lido fresco da telemetria
    # em vez de receber por parametro (mantem a funcao autonoma, como as
    # outras deste ficheiro).
    destino = ler_destino_telemetria(debug=True)
    destino_nome = (destino.get("Name") if destino else None) or ""
    if "ZAHIR" in destino_nome.upper():
        template_alvo, nome_alvo = templates['zahir_confirm'], "ZAHIR"
    elif "FUTEN" in destino_nome.upper():
        template_alvo, nome_alvo = templates['futen_confirm'], "FUTEN SPACEPORT"
    else:
        template_alvo, nome_alvo = None, None
        print(f"[AVISO] Destino '{destino_nome}' não reconhecido (nem Zahir nem Futen) -- validação de alvo desativada nesta fase.")

    # 1. Abrir o painel e confirmar a aba NAVIGATION -- 3 tentativas; dentro
    # de cada uma, cicla com 'q' à procura da aba (o painel pode não abrir
    # sempre diretamente em Navigation); se mesmo ciclando não aparecer,
    # recupera com Backspace (UI Back) e volta a tentar do zero.
    nav_found = False
    for tentativa in range(1, 4):
        pydirectinput.press('1')
        time.sleep(1.2)

        nav_found = confirmar_aba_navigation()
        if nav_found:
            break

        print(f"[AVISO] Aba NAVIGATION não apareceu (tentativa {tentativa}/3) -- Backspace x2 e nova tentativa.")
        pydirectinput.press('backspace')
        time.sleep(0.3)
        pydirectinput.press('backspace')
        time.sleep(0.5)

    if not nav_found:
        pydirectinput.press('x')
        fechar_painel_se_aberto()
        logging.error("engatar_assistencia_menu: aba NAVIGATION não apareceu após 3 tentativas.")
        abortar_com_erro("Falha crítica: aba NAVIGATION não apareceu após 3 tentativas.")

    # 2. Selecionar o destino pré-selecionado (Space) e validar visualmente
    # que é mesmo o alvo esperado -- 3 tentativas, recuperação por Backspace.
    # Antes de cada 'space', reconfirma que a aba NAVIGATION ainda está
    # visível -- o Backspace da tentativa anterior pode ter fechado o painel
    # por completo em vez de só recuar um nível dentro dele, e mandar
    # 'space' às cegas sem painel nenhum aberto não faz sentido.
    alvo_confirmado = (template_alvo is None)  # sem template conhecido -> nao bloqueia, so nao valida
    for tentativa in range(1, 4):
        if not procurar_template(templates['nav_tab'], "NAV TAB (antes do space, painel ainda aberto?)", MONITOR_PANEL, 0.80, debug=True):
            print("[AVISO] Painel não está visível antes do 'space' -- a reabrir e renavegar para NAVIGATION.")
            pydirectinput.press('1')
            time.sleep(1.2)
            confirmar_aba_navigation()

        print(">>> Focando no destino pré-selecionado (Space)...")
        pydirectinput.press('space')
        time.sleep(0.8)

        if template_alvo is None:
            alvo_confirmado = True
            break
        if procurar_template(template_alvo, f"CONFIRM {nome_alvo}", MONITOR_PANEL, 0.80, debug=True):
            print(f"[OK] Alvo confirmado: {nome_alvo}.")
            alvo_confirmado = True
            break

        print(f"[AVISO] Painel de confirmação do alvo '{nome_alvo}' não apareceu (tentativa {tentativa}/3) -- Backspace x2 e nova tentativa.")
        pydirectinput.press('backspace')
        time.sleep(0.3)
        pydirectinput.press('backspace')
        time.sleep(0.5)

    if not alvo_confirmado:
        pydirectinput.press('x')
        fechar_painel_se_aberto()
        logging.error(f"engatar_assistencia_menu: painel de confirmação do alvo '{nome_alvo}' não apareceu após 3 tentativas.")
        abortar_com_erro(f"Falha crítica: painel de confirmação do alvo '{nome_alvo}' não apareceu após 3 tentativas.")

    # 3. Selecionar o Supercruise Assist (D -> Space). Chega-se aqui sempre
    # com o Assist desligado -- o early return de assist_ja_ativo() no topo
    # da função já tratou o caso "já ligado, não mexer" (D+Space é um
    # toggle: enviá-lo com o assist já ligado desliga-o em vez de o ligar --
    # foi isto que desligou o assist com o alvo já trancado num caso real,
    # ver diagnóstico desta conversa).
    print(">>> Movendo para o botão Supercruise Assist (D)...")
    pydirectinput.press('d')
    time.sleep(0.5)

    print(">>> Ativando Assistência (Space)...")
    pydirectinput.press('space')
    time.sleep(1.0)

    # Fecha o painel -- Backspace (UI Back) em vez de '1', que também é um
    # toggle e podia reabrir o painel em vez de o fechar se o estado do menu
    # não fosse o esperado. Confirma pelo NAV TAB que o painel fechou mesmo
    # antes de prosseguir -- foi a falta desta confirmação que deixou o
    # painel preso aberto a receber as teclas de direção do alinhamento
    # (olho.py) em vez do jogo, num caso real (ver diagnóstico desta
    # conversa).
    #
    # 2x Backspace por tentativa (mesmo padrão já usado nos passos 1 e 2
    # desta função) -- um só Backspace pode só recuar do sub-ecrã de
    # confirmação do D+Space para OUTRO sub-ecrã do mesmo painel (ainda
    # aberto), onde a aba NAVIGATION também não bate; isso já fez o código
    # declarar "fechado" cedo demais com o painel ainda aberto por baixo
    # (ver diagnóstico desta conversa). Um combinado com assist_ja_ativo()
    # foi tentado a seguir a esse bug, mas revelou-se um erro diferente:
    # confundia "painel fechado" com "Assist ligou" -- quando o D+Space
    # falhava em ativar o Assist (bug separado, ver abaixo), o painel
    # fechava normalmente mas o código continuava a reportar "painel não
    # fechou", um diagnóstico errado (confirmado em jogo real: 3 screenshots
    # de erro seguidos, todos com o cockpit limpo e o painel genuinamente
    # fechado). Por isso esta verificação volta a ser só sobre o painel.
    painel_fechado = False
    for _ in range(3):
        pydirectinput.press('backspace')
        time.sleep(0.3)
        pydirectinput.press('backspace')
        time.sleep(0.5)
        if not procurar_template(templates['nav_tab'], "NAV TAB (a confirmar fecho do painel)", MONITOR_PANEL, 0.80, debug=True):
            painel_fechado = True
            break

    if not painel_fechado:
        fechar_painel_se_aberto()
        logging.error("engatar_assistencia_menu: painel não fechou após 3 tentativas de Backspace.")
        abortar_com_erro("Falha crítica: painel não fechou após ativar o Supercruise Assist -- a parar antes de mandar teclas de alinhamento para um menu ainda aberto.")

    # Confirma que o Assist REALMENTE ligou -- D+Space (passo 3, acima) é às
    # cegas, sem nenhum template dentro do painel a confirmar o toggle; só
    # dá para confirmar já com o painel fechado, pelos templates do HUD
    # central (assist_ja_ativo(), os mesmos usados no early-return do topo
    # desta função). Sem isto, um D+Space que por qualquer razão não tenha
    # acertado no botão (ex.: painel ainda a assentar) passava despercebido
    # -- o processo avançava para o alinhamento sem o Assist estar
    # realmente ativo, e só falhava bem mais tarde, no timeout do
    # engatar_assist_e_alinhar(), sem apontar à causa real. Poll com
    # margem (até 2s) em vez de uma leitura única -- o banner pode demorar
    # um instante a aparecer mesmo com o toggle já aplicado.
    assist_confirmado = False
    for _ in range(4):
        if assist_ja_ativo():
            assist_confirmado = True
            break
        time.sleep(0.5)

    if not assist_confirmado:
        logging.error("engatar_assistencia_menu: painel fechou mas Supercruise Assist não mostrou nenhum sinal de estar ativo (nem ASSIST_ACTIVE nem align_warning) após D+Space.")
        abortar_com_erro("Falha crítica: Supercruise Assist não ativou -- painel fechou normalmente mas D+Space não teve o efeito esperado no HUD.")

    logging.info(f"engatar_assistencia_menu: sequência concluída (NAV confirmado, alvo={nome_alvo or 'N/D'} confirmado, D+Space enviado, Assist confirmado ativo).")
    print(">>> Painel fechado. Assist confirmado. Voltando ao Cockpit.")

def engatar_assist_e_alinhar(timeout=150, ancora_log=None):
    """ Sequência padrão ao entrar em Supercruise -- usada tanto no arranque
    normal (executar) como depois de plano_fuga.executar_fuga() confirmar
    reentrada: reengata o Supercruise Assist do jogo (engatar_assistencia_menu,
    que já começa com 'x' para estabilizar antes de mexer nos menus, e já
    tem a sua própria validação/recuperação, incluindo o "já está ligado,
    não mexer") e corrige o alinhamento (olho.py) até confirmar por DOIS
    caminhos independentes -- o que confirmar primeiro (padrão adotado do
    Vasco-Nobara/Linux, já validado em produção; substitui a versão anterior
    desta função + aguardar_assist_no_hud, que dependia do marcador "dois
    triângulos azuis" -- assist_locked -- e nunca chegou a confirmar com
    fiabilidade em jogo real):

      (a) TELEMETRIA + BANNER: supercruise ligado + banner ASSIST_ACTIVE
          visível no HUD, sustentados 3s SEGUIDOS -- não depende da
          calibração da bússola (CX_NEUTRO/CY_NEUTRO), só de dois sinais
          diretos do jogo. Enquanto este caminho estiver a progredir, não
          se manda nenhum impulso manual (olho.py) por cima -- o Assist já
          está a "puxar" a nave sozinho, e um impulso extra pode ultrapassar
          a janela apertada de alinhamento e reacender o aviso do jogo.
      (b) BÚSSOLA/HUD + SEM AVISO DO JOGO: olho.executar_passo_alinhamento()
          reporta 'alinhado_frame' (bússola ALINHADO_MACRO ou retículo do
          HUD travado) E o aviso nativo do jogo ("ALIGN WITH TARGET
          DESTINATION", template align_warning) NÃO está visível,
          sustentados 3s SEGUIDOS. O aviso do jogo prevalece sobre a
          bússola/HUD -- só a bússola/HUD já deu falsos positivos com o
          aviso do jogo ainda bem visível no ecrã.

    Devolve True quando confirmado, ou a string "chegada_curta" se a nave
    chegar ao destino (telemetria + Journal confirmam, ANCORADOS a
    ancora_log -- ver confirmar_chegada_por_journal) antes de qualquer um
    dos dois caminhos confirmar -- saltos curtos (estação perto do ponto de
    entrada em Supercruise) podem terminar em menos do que este watchdog
    demora a confirmar, e isso NÃO é uma falha (a nave chegou mesmo). A
    deteção de "chegada_curta" exige, por esta ordem: (1) CONFIRMACOES_FORA_SUPERCRUISE
    leituras seguidas da flag SUPERCRUISE desligada -- uma leitura única
    pode ser só um glitch do Status.json a meio de reescrita; (2) o aviso
    'ALIGN WITH TARGET DESTINATION' (template align_warning) NÃO estar
    visível -- se ainda estiver, é impossível ter havido chegada, mais
    barato e mais rápido de verificar do que ir ao Journal; (3) só depois
    disso confirma pelo Journal, ancorado a ancora_log para nunca
    reaproveitar um SupercruiseDestinationDrop de uma perna anterior (bug
    real confirmado em produção: chegada_curta declarada no mesmo segundo
    em que o alinhamento arrancou, sem a nave ter chegado a lado nenhum --
    ver diagnóstico desta conversa).
    Aborta (timeout, default 150s -- mesmo valor ja validado em producao no
    Vasco-Nobara/Linux) se nenhum dos dois caminhos confirmar. """
    engatar_assistencia_menu()

    logging.info("engatar_assist_e_alinhar: a obter modelo da nave e calibração...")
    nave_ativa = olho.obter_modelo_nave_atual()
    MONITOR_CONFIG, CX_NEUTRO, CY_NEUTRO = olho.carregar_dados_calibracao(nave_ativa)

    TEMPO_ESTABILIDADE = 3.0
    limite = time.time() + timeout
    tempo_confirmado_telemetria = None
    tempo_confirmado_bussola = None
    ultimo_heartbeat = 0.0
    confirmacoes_fora_supercruise = 0
    # Recuperacao por roll quando a bussola fica cega (planeta/brilho a
    # tapar a leitura) -- executar_passo_alinhamento() e deliberadamente sem
    # estado (ver a sua docstring: "rolls de recuperacao ficam a cargo de
    # quem chama"), por isso este estado vive aqui.
    rolls_recuperacao = 0

    with mss.mss() as sct:
        try:
            monitor_jogo = sct.monitors[1]
        except Exception:
            monitor_jogo = sct.monitors[0]
        area_bussola = {
            "top": monitor_jogo["top"] + MONITOR_CONFIG["top"],
            "left": monitor_jogo["left"] + MONITOR_CONFIG["left"],
            "width": MONITOR_CONFIG["width"], "height": MONITOR_CONFIG["height"]
        }
        logging.info(f"engatar_assist_e_alinhar: sessão de captura aberta -- a iniciar loop de deteção (timeout {timeout}s).")

        while True:
            # Heartbeat a cada ~10s -- se isto parar de aparecer no log mas o
            # processo continuar "vivo" no Gestor de Tarefas, o bloqueio está
            # dentro de uma única iteração (procurar_template/olho), não
            # entre iterações.
            if time.time() - ultimo_heartbeat > 10:
                ultimo_heartbeat = time.time()
                logging.info(f"engatar_assist_e_alinhar: heartbeat (restam {limite - time.time():.0f}s de timeout).")

            if time.time() > limite:
                abortar_com_erro(f"Timeout ({timeout}s). Alinhamento pós-assist nunca confirmado (nem telemetria+banner, nem bússola/HUD+sem aviso do jogo).")

            flags = ler_telemetria()
            em_supercruise = bool(flags & STATUS_FLAGS["SUPERCRUISE"])
            if em_supercruise:
                confirmacoes_fora_supercruise = 0
            else:
                confirmacoes_fora_supercruise += 1

            if confirmacoes_fora_supercruise >= CONFIRMACOES_FORA_SUPERCRUISE:
                # Veto barato antes de ir ao Journal: 'ALIGN WITH TARGET
                # DESTINATION' só aparece com o Assist ligado e ainda em
                # Supercruise -- se ainda estiver visível, a leitura da
                # flag só pode ter sido um glitch (Status.json a meio de
                # reescrita), não uma chegada real.
                ainda_avisa_chegada = procurar_template(templates['align_warning'], "ALIGN WARNING (veto de chegada_curta)", MONITOR_CENTER, 0.82, debug=True, sct=sct)
                if ainda_avisa_chegada:
                    print("[AVISO] Telemetria sugere fora de Supercruise, mas 'ALIGN WITH TARGET DESTINATION' ainda visível -- não é chegada, provável glitch de leitura.")
                    confirmacoes_fora_supercruise = 0
                elif confirmar_chegada_por_journal(ancora_log=ancora_log):
                    msg = "Chegada confirmada (telemetria+Journal, ancorados a este salto) antes do alinhamento confirmar -- salto curto de mais para este watchdog."
                    print(f"[OK] {msg}")
                    logging.info(f"engatar_assist_e_alinhar: {msg}")
                    olho.fechar_debug_visual()
                    return "chegada_curta"

            # Caminho (a): telemetria + banner ASSIST_ACTIVE, sustentados 3s.
            banner_ativo = procurar_template(templates['assist_active'], "ASSIST ACTIVE", MONITOR_CENTER, 0.75, debug=True, sct=sct)
            if em_supercruise and banner_ativo:
                if tempo_confirmado_telemetria is None:
                    tempo_confirmado_telemetria = time.time()
                    print("[LOG] Telemetria + banner ASSIST ACTIVE confirmam -- a validar estabilidade (3s)...")
                elif time.time() - tempo_confirmado_telemetria >= TEMPO_ESTABILIDADE:
                    print("[OK] Confirmado por telemetria + banner ASSIST ACTIVE, estável 3s seguidos.")
                    logging.info("engatar_assist_e_alinhar: confirmado via telemetria+banner.")
                    olho.fechar_debug_visual()
                    return True
                # Assist já a puxar visivelmente -- sem impulso manual por
                # cima (ver docstring). Print explícito (em vez de só a
                # ausência de "[INFO] ... IMPULSO_*" do olho.py) para tornar
                # isto visível linha a linha no log, sem ter de inferir pela
                # falta de output.
                print("[LOG] Assist a puxar -- sem correção manual.")
                tempo_confirmado_bussola = None
                time.sleep(0.2)
                continue

            tempo_confirmado_telemetria = None

            # Caminho (b): bússola/HUD (olho.py) + sem aviso do jogo,
            # sustentados 3s. Corrige ativamente enquanto não confirma.
            passo = olho.executar_passo_alinhamento(sct, area_bussola, CX_NEUTRO, CY_NEUTRO)
            olho.mostrar_debug_visual(passo, CX_NEUTRO, CY_NEUTRO)

            # Bussola cega (coords_bola None -- "NÃO_DETETADO"): tenta um
            # roll de recuperação JÁ NO PRIMEIRO frame, sem esperar
            # TEMPO_CEGO_ANTES_ROLL (8s, valor do loop standalone em
            # olho.py, pensado para um contexto diferente). O roll em si é
            # "pequeno" -- só ~45 graus de orientação (TECLA_ROLL/
            # TEMPO_ROLL_45 já calibrados em olho.py), não muda o rumo, por
            # isso reagir de imediato é mais barato do que ficar 8s parado
            # sem fazer nada à espera que se resolva sozinho (foi isto que
            # esgotou os 150s inteiros num caso real, ver diagnóstico desta
            # conversa). MAX_ROLLS_RECUPERACAO (3) continua a limitar o
            # número de tentativas, e executar_roll_recuperacao() já tem o
            # seu próprio cooldown (2s) antes da leitura seguinte.
            if passo["coords_bola"] is None:
                if rolls_recuperacao < olho.MAX_ROLLS_RECUPERACAO:
                    rolls_recuperacao += 1
                    olho.executar_roll_recuperacao(rolls_recuperacao)
                else:
                    print(f"[AVISO] Bússola cega e já sem rolls de recuperação disponíveis ({olho.MAX_ROLLS_RECUPERACAO}/{olho.MAX_ROLLS_RECUPERACAO} usados) -- a continuar a ler na mesma.")

            ainda_avisa = procurar_template(templates['align_warning'], "ALIGN WARNING (jogo)", MONITOR_CENTER, 0.82, debug=True, sct=sct)

            if passo["alinhado_frame"] and not ainda_avisa:
                rolls_recuperacao = 0  # leitura recuperada; futuras perdas tem direito a novos rolls
                if tempo_confirmado_bussola is None:
                    tempo_confirmado_bussola = time.time()
                    print("[LOG] Bússola/HUD alinhados e sem aviso do jogo -- a validar estabilidade (3s)...")
                elif time.time() - tempo_confirmado_bussola >= TEMPO_ESTABILIDADE:
                    print("[OK] Confirmado por bússola/HUD, sem aviso do jogo, estável 3s seguidos.")
                    logging.info("engatar_assist_e_alinhar: confirmado via bússola/HUD.")
                    olho.fechar_debug_visual()
                    return True
            else:
                tempo_confirmado_bussola = None

            time.sleep(0.2)

# ==========================================
# 5. FASE 2: VIAGEM E CHEGADA
# ==========================================
def monitorar_viagem(resultado_assist, ancora_log=None):
    print("\n>>> FASE 2: Viagem em Supercruise...")

    if resultado_assist == "chegada_curta":
        # Salto curto de mais para o watchdog do icone -- ja chegamos, avanca
        # direto para a fase de chegada sem passar pela Viagem Longa.
        falar("Arrived before assist could be confirmed visually.")
    else:
        # Assist confirmado visualmente (3 detecoes limpas) -- so agora anuncia.
        falar("Supercruise assist engaged. Monitoring flight path.")

        # Viagem Longa
        print("A aguardar confirmação de saída de Supercruise (telemetria)...")
        timeout_viagem = time.time() + 1500 # 25 mins

        chegada_confirmada = False
        confirmacoes_fora_supercruise = 0
        while not chegada_confirmada:
            if time.time() > timeout_viagem:
                abortar_com_erro("Timeout (25 mins). Viagem em supercruise excedeu o limite seguro.")

            flags = ler_telemetria()

            if bool(flags & STATUS_FLAGS["SUPERCRUISE"]):
                confirmacoes_fora_supercruise = 0
                time.sleep(1)
                continue

            # Fora de Supercruise pela telemetria -- exige 2 leituras
            # seguidas (mesmo padrão de engatar_assist_e_alinhar) antes de
            # reagir: uma leitura única pode ser só um glitch do Status.json
            # a meio de reescrita, e reagir a isso aqui é bem mais caro
            # (chama plano_fuga.executar_fuga() se o Journal não confirmar
            # chegada) do que ali.
            confirmacoes_fora_supercruise += 1
            if confirmacoes_fora_supercruise < CONFIRMACOES_FORA_SUPERCRUISE:
                time.sleep(1)
                continue

            # Veto barato antes de ir ao Journal ou acionar o plano de fuga:
            # se 'ALIGN WITH TARGET DESTINATION' ainda estiver visível, o
            # HUD de Supercruise ainda está ativo -- não pode ter havido
            # queda real, a leitura da flag é que estava errada.
            if procurar_template(templates['align_warning'], "ALIGN WARNING (veto de queda)", MONITOR_CENTER, 0.82, debug=True):
                print("[AVISO] Telemetria sugere fora de Supercruise, mas 'ALIGN WITH TARGET DESTINATION' ainda visível -- provável glitch de leitura, a continuar a viagem.")
                confirmacoes_fora_supercruise = 0
                time.sleep(1)
                continue

            print("\n[LOG] Queda de Supercruise detetada pela telemetria (confirmada 2x seguidas). A verificar causa...")
            if bool(flags & STATUS_FLAGS["INTERDICTION"]):
                print("[AVISO] Flag INTERDICTION estava ativa -- provável causa da queda.")
                logging.info("Queda de Supercruise com INTERDICTION ativa.")

            if confirmar_chegada_por_journal(ancora_log=ancora_log):
                chegada_confirmada = True
            else:
                # plano_fuga.executar_fuga() ja confirma Supercruise
                # internamente antes de devolver (nao so FSD_CHARGING) --
                # aguardar_supercruise_confirmado() aqui seria redundante.
                plano_fuga.executar_fuga()
                print("[LOG] Plano de fuga concluído (Supercruise confirmado).")
                engatar_assist_e_alinhar(ancora_log=ancora_log)
                timeout_viagem = time.time() + 1500  # nova janela de 25 min pos-fuga
                confirmacoes_fora_supercruise = 0

            time.sleep(1)

    # Chegada
    print("\n>>> CHEGADA CONFIRMADA! A executar travagem e boost...")
    falar("Dropping from supercruise.")

    print("[LOG] A aguardar queda da flag SUPERCRUISE antes do boost...")
    timeout_drop = time.time() + 10
    while time.time() < timeout_drop:
        flags_drop = ler_telemetria()
        if not bool(flags_drop & STATUS_FLAGS["SUPERCRUISE"]):
            print("[OK] Flag SUPERCRUISE caiu -- fora de Supercruise confirmado.")
            break
        time.sleep(0.5)
    else:
        print("[AVISO] Timeout (10s) a aguardar queda da flag SUPERCRUISE. A prosseguir na mesma.")

    time.sleep(1.5)
    flags_pre_boost = ler_telemetria(debug=True)
    msg_pre_boost = f"Pre-boost -> ainda em Supercruise: {bool(flags_pre_boost & STATUS_FLAGS['SUPERCRUISE'])} (flags={hex(flags_pre_boost)})"
    print(f"[TELEMETRIA] {msg_pre_boost}")
    logging.info(msg_pre_boost)
    pydirectinput.press('tab')
    time.sleep(15.0)
    flags_pos_boost = ler_telemetria(debug=True)
    msg_pos_boost = f"Pos-boost -> ainda em Supercruise: {bool(flags_pos_boost & STATUS_FLAGS['SUPERCRUISE'])} (flags={hex(flags_pos_boost)})"
    print(f"[TELEMETRIA] {msg_pos_boost}")
    logging.info(msg_pos_boost)
    # pydirectinput.press('tab')
    # time.sleep(15.0)
    pydirectinput.press('x')
    print(">>> Manobra concluída. A aguardar aproximação para docking.")

def executar():
    inicializar_infraestrutura()

    print("Alinha o nariz da nave com o destino. Iniciando em 1s...")
    time.sleep(1)

    # Âncora no Journal (posição em bytes), capturada ANTES do salto --
    # confirmar_chegada_por_journal() só vê eventos escritos depois deste
    # ponto, para nunca confundir uma chegada desta perna com uma de uma
    # perna anterior já concluída nesta mesma sessão de jogo (ver
    # confirmar_chegada_por_journal e diagnóstico desta conversa).
    ancora_log = obter_tamanho_atual_log()

    iniciar_salto_seguro()
    aguardar_supercruise_confirmado()
    resultado_assist = engatar_assist_e_alinhar(ancora_log=ancora_log)
    monitorar_viagem(resultado_assist, ancora_log=ancora_log)

    if VISUAL_DEBUG:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    executar()

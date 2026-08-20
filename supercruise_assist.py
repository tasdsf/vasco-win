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

def abortar_com_erro(mensagem):
    print(f"\n[FATAL] {mensagem}")
    logging.error(mensagem)
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

STATUS_FLAGS = {
    "SUPERCRUISE": 0x10,
    "FSD_MASS_LOCKED": 0x10000,
    "FSD_CHARGING": 0x20000,
    "HARDPOINTS_DEPLOYED": 0x40,
    "INTERDICTION": 0x800000,
}

TEMPLATES_NOMES = {
    'nav_tab': 'NAVIGATION_SELECTED.png',
    'charging': 'CHARGING.png',
    'locked': 'LOCKED_DESTINATION.png',
    'unlocked': 'UNLOCKED_DESTINATION.png',
    'assist_active': 'SUPERCRUISE_ASSIST_ACTIVE.png',
    'align_warning': 'SUPERCRUISE_ASSIST_INACTIVE.png',
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
def procurar_template(template, nome_label, monitor, threshold=0.75, debug=False):
    with mss.mss() as sct:
        img_bgra = np.array(sct.grab(monitor))
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
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

def ler_cargo_telemetria(debug=False):
    try:
        with open(STATUS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            cargo = data.get("Cargo", 0)
            if debug:
                print(f"    [CARGA] {cargo}")
            return cargo
    except Exception as e:
        if debug:
            print(f"    [CARGA] Falha a ler {STATUS_FILE}: {e}")
        return 0

# Estacao de origem do ciclo comprar->vender (ver vasco.py SEQUENCE) -- se
# houver carga a bordo e o destino do salto for esta, a venda no carrier
# falhou nalgures e a nave esta prestes a regressar sem vender.
ESTACAO_ORIGEM = "Futen Spaceport"

def confirmar_chegada_por_journal():
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
    ou não foi chegada. """
    EVENTOS_FRONTEIRA = {"SupercruiseDestinationDrop", "SupercruiseEntry", "StartJump"}
    try:
        ed_log_dir = os.path.join(os.environ['USERPROFILE'], 'Saved Games',
                                  'Frontier Developments', 'Elite Dangerous')
        lista_logs = glob.glob(os.path.join(ed_log_dir, 'Journal.*.log'))
        if not lista_logs:
            print("[AVISO] Sem ficheiros de Journal encontrados -- a assumir que NÃO foi chegada.")
            return False

        ultimo_log = max(lista_logs, key=os.path.getmtime)
        with open(ultimo_log, 'r', encoding='utf-8') as f:
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

    # Trava de segurança: se há carga a bordo e o destino é a estação de
    # origem, a venda no carrier falhou nalgures (ou o destino trocou por
    # engano entre tentativas) e a nave está prestes a regressar sem vender.
    # Mais vale parar aqui e pedir intervenção do que voltar com carga.
    cargo_atual = ler_cargo_telemetria(debug=True)
    if cargo_atual and cargo_atual > 0 and destino_nome == ESTACAO_ORIGEM:
        abortar_com_erro(
            f"Carga a bordo ({cargo_atual:.0f}) mas o destino do salto é a estação de origem "
            f"('{ESTACAO_ORIGEM}') -- a venda não foi confirmada e a nave estava prestes a "
            f"regressar sem vender. A parar para intervenção manual em vez de prosseguir."
        )

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
        registar_los_visivel_auto()
        # Espera o salto acontecer
        pydirectinput.press('x')
        time.sleep(4.5)
        return True

    # 1b. Já não está a carregar porque o salto já teve sucesso entretanto
    if salto_confirmado == "supercruise":
        print("[OK] Já em Supercruise (a carga completou antes da leitura de telemetria).")
        registar_los_visivel_auto()
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

def engatar_assistencia_menu():
    print("\n>>> FASE 1: Navegação no Painel Esquerdo...")

    # Reduzir velocidade antes de mexer nos menus
    pydirectinput.press('x')

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

    # 3. Selecionar o Supercruise Assist (D -> Space)
    print(">>> Movendo para o botão Supercruise Assist (D)...")
    pydirectinput.press('d')
    time.sleep(0.5)

    print(">>> Ativando Assistência (Space)...")
    pydirectinput.press('space')
    time.sleep(1.0)

    pydirectinput.press('1') # Fecha painel
    logging.info(f"engatar_assistencia_menu: sequência concluída (NAV confirmado, alvo={nome_alvo or 'N/D'} confirmado, D+Space enviados).")
    print(">>> Painel fechado. Voltando ao Cockpit.")

def engatar_assist_e_alinhar(timeout=20):
    """ Sequência padrão ao entrar em Supercruise -- usada tanto no arranque
    normal (executar) como depois de plano_fuga.executar_fuga() confirmar
    reentrada: reengata o Supercruise Assist do jogo (engatar_assistencia_menu,
    que já começa com 'x' para estabilizar antes de mexer nos menus, e já
    tem a sua própria validação/recuperação), e só depois ativa o olho.py a
    alinhar -- com o assist já ligado o alvo "atrai" e centra rápido. Não
    aborta se não alinhar dentro do timeout: o assist do jogo, uma vez
    ligado, continua a corrigir por conta própria -- isto é só um empurrão
    inicial, não uma garantia. A validação de que o assist ficou mesmo ativo
    fica a cargo de quem chama a seguir (aguardar_assist_no_hud, que já usa
    o template assist_active/SUPERCRUISE_ASSIST_ACTIVE.png para isso). """
    engatar_assistencia_menu()

    nave_ativa = olho.obter_modelo_nave_atual()
    MONITOR_CONFIG, CX_NEUTRO, CY_NEUTRO = olho.carregar_dados_calibracao(nave_ativa)
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
        limite = time.time() + timeout
        while time.time() < limite:
            passo = olho.executar_passo_alinhamento(sct, area_bussola, CX_NEUTRO, CY_NEUTRO)
            if passo["alinhado_frame"]:
                print("[OK] Alvo centrado -- Supercruise Assist assume a partir daqui.")
                return
            time.sleep(0.2)
    print(f"[AVISO] Alvo não centrou em {timeout}s -- a seguir na mesma, o Assist continua a corrigir sozinho.")

# ==========================================
# 5. FASE 2: VIAGEM E CHEGADA
# ==========================================
def aguardar_assist_no_hud():
    """ Espera o icone ASSIST_ACTIVE aparecer de forma estavel no HUD (3
    deteccoes seguidas). Usado ao ligar o assist pela primeira vez e outra vez
    depois de um plano de fuga bem sucedido reengatar o assist a meio da
    viagem (ver monitorar_viagem).

    Devolve True quando o icone confirma normalmente, ou a string
    "chegada_curta" se a nave chegar ao destino (telemetria + Journal
    confirmam) antes mesmo de o icone alguma vez estabilizar 3x seguidas --
    saltos curtos (estacao perto do ponto de entrada em Supercruise) podem
    terminar em menos de 60s, e isso NAO e uma falha (a nave chegou mesmo),
    so um falso alarme deste watchdog. Confirmado em jogo real: chegada as
    ~35s depois de engatar o assist, watchdog abortou aos 60s na mesma. """
    contagem_limpo = 0
    timeout_assist = time.time() + 60
    while contagem_limpo < 3:
        if time.time() > timeout_assist:
            abortar_com_erro("Timeout (60s). Supercruise Assist não apareceu no HUD.")

        flags = ler_telemetria()
        if not bool(flags & STATUS_FLAGS["SUPERCRUISE"]) and confirmar_chegada_por_journal():
            msg = "Chegada confirmada (telemetria+Journal) antes do ícone ASSIST_ACTIVE alguma vez estabilizar -- salto curto de mais para este watchdog."
            print(f"[OK] {msg}")
            logging.info(f"aguardar_assist_no_hud: {msg}")
            return "chegada_curta"

        if not procurar_template(templates['assist_active'], "ASSIST ACTIVE", MONITOR_CENTER, 0.75):
            contagem_limpo = 0
        else:
            contagem_limpo += 1
        time.sleep(1)
    return True

def monitorar_viagem():
    print("\n>>> FASE 2: Viagem em Supercruise...")
    resultado_assist = aguardar_assist_no_hud()

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
        while not chegada_confirmada:
            if time.time() > timeout_viagem:
                abortar_com_erro("Timeout (25 mins). Viagem em supercruise excedeu o limite seguro.")

            flags = ler_telemetria()

            if not bool(flags & STATUS_FLAGS["SUPERCRUISE"]):
                print("\n[LOG] Queda de Supercruise detetada pela telemetria. A verificar causa...")
                if bool(flags & STATUS_FLAGS["INTERDICTION"]):
                    print("[AVISO] Flag INTERDICTION estava ativa -- provável causa da queda.")
                    logging.info("Queda de Supercruise com INTERDICTION ativa.")

                if confirmar_chegada_por_journal():
                    chegada_confirmada = True
                else:
                    # plano_fuga.executar_fuga() ja confirma Supercruise
                    # internamente antes de devolver (nao so FSD_CHARGING) --
                    # aguardar_supercruise_confirmado() aqui seria redundante.
                    plano_fuga.executar_fuga()
                    print("[LOG] Plano de fuga concluído (Supercruise confirmado).")
                    engatar_assist_e_alinhar()
                    aguardar_assist_no_hud()
                    timeout_viagem = time.time() + 1500  # nova janela de 25 min pos-fuga

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

    iniciar_salto_seguro()
    aguardar_supercruise_confirmado()
    engatar_assist_e_alinhar()
    monitorar_viagem()

    if VISUAL_DEBUG:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    executar()

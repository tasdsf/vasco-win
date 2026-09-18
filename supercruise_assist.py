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
import subprocess
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
from leg_state import leg_esta_limpa, marcar_leg_suja

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

# ==========================================
# 0b. DIAGNÓSTICO PASSO-A-PASSO (engatar_assistencia_menu)
# ==========================================
# Pasta por sessão (uma subpasta por chamada a engatar_assistencia_menu()),
# nomeada pelo timestamp -- screenshot numerado a CADA passo, desde o '1'
# que abre o painel até à confirmação final do Assist. Ao contrário de
# erro_*.png (só o instante do abort), isto dá o trajeto visual completo,
# incluindo os passos que correram bem -- essencial quando o mesmo "Assist
# não ativou" volta a falhar depois de várias correções já aplicadas e já
# não há teoria óbvia por testar (ver diagnóstico desta conversa). Estado
# em globals (mesmo padrão de _janela_debug_iniciada em olho.py) -- só uma
# sessão de diagnóstico ativa de cada vez, não precisa de mais que isso.
DIAG_ASSIST_DIR = os.path.join(LOGS_DIR, "diag_assist")
_diag_dir = None
_diag_contador = 0

def _diag_iniciar_sessao():
    """ Abre uma nova subpasta de diagnóstico para esta chamada de
    engatar_assistencia_menu() -- chamar uma vez no início da função. """
    global _diag_dir, _diag_contador
    _diag_dir = os.path.join(DIAG_ASSIST_DIR, time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(_diag_dir, exist_ok=True)
    _diag_contador = 0
    print(f"[DIAG] Sessão de diagnóstico: {_diag_dir}")

def _diag_passo(nome):
    """ Grava o ecrã inteiro do jogo, numerado e nomeado, dentro da sessão
    de diagnóstico atual. Best-effort -- nunca pode travar o fluxo
    principal nem impedir o abort em curso. """
    global _diag_contador
    if _diag_dir is None:
        return
    try:
        _diag_contador += 1
        caminho = os.path.join(_diag_dir, f"{_diag_contador:02d}_{nome}.png")
        with mss.mss() as sct:
            try:
                monitor_jogo = sct.monitors[1]
            except Exception:
                monitor_jogo = sct.monitors[0]
            img_bgra = np.array(sct.grab(monitor_jogo))
            cv2.imwrite(caminho, cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR))
        print(f"[DIAG] {_diag_contador:02d} {nome} -> {caminho}")
    except Exception as e:
        print(f"[AVISO] Falha ao gravar diagnóstico '{nome}': {e}")

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
MONITOR_PANEL = {"top": 200, "left": 50, "width": 1150, "height": 1200}
# width 1000 -> 1150: recorte antigo cortava o "> " final de linhas longas
# ("< FUTEN SPACEPORT >" acaba em x=1073, fora dos x=1050 do recorte de
# 1000px), fazendo o template *_selected falhar por falta do fecho do
# template mesmo com a linha visivelmente destacada em jogo (match caía de
# 0.853 no ecrã completo para 0.789 no recorte, abaixo do limiar 0.80).
# "ZAHIR W6G-26N" é curto e sempre coube nos 1000px, por isso só afetava
# Futen. 1150 dá margem folgada acima dos 1073px necessários.
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
    # Banner "MOVE TO OBTAIN LINE OF SIGHT TO TARGET" -- oclusão de LOS real
    # vista a meio do voo (não é o pré-undocking, esse já é tratado por
    # los_checker.calcular_espera_los() em vasco.py antes de descolar). Ver
    # _tratar_los_detetado_em_voo(). Recorte (texto + triângulo vermelho) de
    # images/line_of_sight.png (screenshot de referência original, mantido
    # intacto) -- o ficheiro original é o ecrã inteiro, inutilizável como
    # template de matchTemplate diretamente.
    'line_of_sight': 'line_of_sight_banner.png',
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
    # Título "NAV BEACON" do popup -- rejeição EXPLÍCITA, não só "não é
    # Zahir/Futen" (título ambíguo, ex.: 0.42 podia ser qualquer coisa).
    # Diz sem ambiguidade qual foi o alvo errado, e dispara uma recuperação
    # diferente (ver engatar_assistencia_menu(), Fase B). Separação limpa
    # confirmada: 1.000/0.998 no Nav Beacon genuíno, 0.389 no Futen.
    'nav_beacon_confirm': 'nav_beacon_confirm.png',
    # Nome do alvo destacado NA LISTA, entre '< >' (ex.: "< ZAHIR W6G-26N >")
    # -- confirma que a linha certa está mesmo selecionada ANTES de premir
    # 'space' para abrir o popup de confirmação. Padrão adotado depois de
    # "painel de confirmação do alvo não apareceu" continuar a falhar
    # mesmo com mais tempo de espera pelo popup (ver diagnóstico desta
    # conversa) -- apanha o problema mais cedo, antes de gastar uma
    # tentativa inteira à espera de um popup que nunca ia abrir com a
    # linha errada (ou nenhuma) selecionada.
    'zahir_selected': 'carrier_selected.png',
    'futen_selected': 'futen_selected.png',
    # Terceira aparência real da linha do Zahir: destaque AMARELO cheio,
    # mas SEM '< >' (diferente do cursor com brackets E do "trancado sem
    # cursor" em tom oliva) -- visto ao vivo quando a lista reordena por
    # distância e o Zahir passa a ser a linha mais próxima. Testado: 1.000
    # no estado certo, 0.85-0.86 contra os OUTROS dois estados do Zahir
    # (esperado, são todos "é o Zahir"), 0.55-0.56 contra Futen/Nav Beacon
    # (bem separado). Só temos o recorte do Zahir por agora.
    'zahir_highlight_sem_cursor': 'zahir_highlight_sem_cursor.png',
    # Quarta aparência real: cursor COM '< >' mas fundo VERDE em vez de
    # amarelo (visto ao vivo 2026-09-15 22:5x, lista reordenada de novo,
    # Zahir na última linha). O template 'zahir_selected' (fundo amarelo)
    # só bate a 0.796 aqui -- abaixo do limiar -- confirmando que a cor de
    # fundo muda por si só e não é coberta pelo template amarelo. Testado
    # em escala de cinza também (0.791, sem melhoria -- não é só questão
    # de cor, a própria renderização difere o suficiente para precisar de
    # recorte próprio). Separação limpa: 1.000 no estado certo, 0.53-0.57
    # em Futen/Nav Beacon.
    'zahir_verde_brackets': 'zahir_verde_com_brackets.png',
    # Nome do alvo JÁ TRANCADO na lista, mas SEM o cursor lá (sem '< >',
    # fundo em tom diferente do amarelo do cursor -- ex.: "ZAHIR W6G-26N"
    # verde/oliva enquanto o cursor está noutra linha). Estado distinto do
    # anterior: '< NOME >' confirma "o cursor está aqui", isto confirma "o
    # destino já está trancado", independente de onde o cursor esteja.
    # Testado contra os dois: match ~0.64 no estado com cursor (não é o
    # mesmo estado, por isso não confunde os dois), ~1.0 no estado
    # correto, ~0.46-0.50 nas outras linhas da lista (Futen/Nav Beacon).
    # Só temos o recorte do Zahir por agora -- 'futen_locked' fica por
    # calibrar até haver um print real desse estado para a estação.
    'zahir_locked': 'zahir_locked_sem_cursor.png',
    # Ícone '<>' do botão lock/unlock, recortado só ao ícone (sem o texto
    # "LOCK DESTINATION"/"UNLOCK DESTINATION" ao lado, que muda consoante o
    # destino já estar trancado ou não -- confirmado em jogo real que tanto
    # faz qual dos dois estados, a posição do ícone é igual). Usado duas
    # vezes: (a) para confirmar que o popup abriu com o foco no botão certo,
    # (b) para confirmar, depois do 'D', que o foco realmente saiu daqui --
    # foi a falta desta segunda confirmação que causou "Assist não ativou"
    # em jogo real: o 'D' às vezes não movia o foco, e o 'space' seguinte
    # ia parar a ESTE botão (fazia lock/unlock) em vez do Supercruise
    # Assist (ver diagnóstico desta conversa, screenshots 'apos_d').
    'lock_unlock_toggle': 'lock_unlock_togle_button.png',
    # Botão "SUPERCRUISE ASSIST" em foco (destacado a amarelo) -- usado para
    # confirmar POSITIVAMENTE que o 'D' moveu o foco para o sítio certo, em
    # vez de só confirmar a ausência do botão lock/unlock anterior (uma
    # confirmação negativa não garante que o foco foi parar ao botão certo,
    # só que saiu do errado).
    'assist_toggle': 'assist_togle_button.png',
    # Legenda "DEACTIVATE SUPERCRUISE ASSIST" (só a palavra "DEACTIVATE",
    # que fica em branco no estado desligado) -- verdade do jogo sobre o
    # estado do toggle, sem ambiguidade de foco/banner. Ver uso em
    # engatar_assistencia_menu() -- decide se o Space ativa ou desativa, e
    # confirma o resultado a seguir.
    'deactivate_assist': 'deactivate_supercruise_assist.png',
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
            # Inclui max_loc (onde o match aterrou) -- sem isto não dava
            # para saber se um match alto estava mesmo em cima do texto
            # esperado ou coincidia por acaso noutro sítio da imagem.
            # Pedido direto do utilizador desta conversa depois de um
            # falso positivo nunca ter sido confirmado visualmente (só se
            # testaram screenshots de outro instante, não o frame real do
            # match).
            msg_match = f"[MATCH {marca}] {nome_label}: {max_val:.3f} (limiar {threshold:.2f}) em {max_loc}"
            print(f"    {msg_match}")
            # Persiste no r2d2_combined.log, não só na consola -- os scores
            # de debug=True só existiam ao vivo no terminal e desapareciam
            # com o processo, tornando impossível analisar depois um caso
            # de falha real sem repetir a corrida. Pedido explícito do
            # utilizador desta conversa após um caso de ambiguidade na
            # legenda do Assist sem evidência suficiente para diagnosticar.
            logging.info(msg_match)

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

def ler_cargo_telemetria(debug=False):
    try:
        with open(STATUS_FILE, 'r', encoding='utf-8') as f:
            cargo = json.load(f).get("Cargo", 0)
            if debug:
                print(f"    [CARGA] {cargo}")
            return cargo
    except Exception as e:
        if debug:
            print(f"    [CARGA] Falha a ler {STATUS_FILE}: {e}")
        return 0

def obter_sistema_atual():
    """ Lê o Journal mais recente e devolve o StarSystem atual -- mesma
    deteção já usada em los_checker.py::obter_sistema_atual(), duplicada
    aqui por convenção do projeto (scripts Windows não partilham imports
    entre si). Usada só como fallback quando a telemetria de destino falha
    (ver ausência de 'Destination' em engatar_assistencia_menu()). """
    ultimo_log = get_latest_log()
    if not ultimo_log:
        return None
    try:
        sistema = None
        with open(ultimo_log, 'r', encoding='utf-8') as f:
            for linha in f:
                try:
                    data = json.loads(linha)
                    if data.get("event") in ("FSDJump", "Location", "CarrierJump") and "StarSystem" in data:
                        sistema = data["StarSystem"]
                except Exception:
                    continue
        return sistema
    except Exception:
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
        if not host:
            return  # .env não configurado nesta máquina — segue sem registar

        ed_log_dir = os.path.join(os.environ['USERPROFILE'], 'Saved Games',
                                  'Frontier Developments', 'Elite Dangerous')
        sistema = obter_sistema_atual(ed_log_dir)
        if not sistema:
            print("[LOS-AUTO] Sistema desconhecido — observação não registada.")
            return

        # A password NÃO vem do .env — vem do pgpass.conf do Windows
        # (%APPDATA%\postgresql\pgpass.conf), lido automaticamente pelo
        # libpq quando psycopg2.connect() não recebe o argumento password.
        conn = psycopg2.connect(
            host=host,
            port=os.environ.get("R2D2_DB_PORT", "5432"),
            dbname=os.environ.get("R2D2_DB_NAME", "ED"),
            user=os.environ.get("R2D2_DB_USER", "r2d2"),
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
# 2c. OCLUSÃO DE LOS DETETADA A MEIO DO VOO
# ==========================================
# Duplicado de vasco.py::EXIT_CODE_ESTADO_SOBRESCRITO (mesmo valor, mesmo
# significado) -- convenção do projeto de duplicar constantes/pequenos
# helpers partilhados em vez de importar entre scripts Windows (ver
# comentários "duplicada aqui por convenção do projeto" já usados neste
# ficheiro). O main() de vasco.py trata este exit code como "o filho já
# reescreveu vasco_state.json sozinho", não como sucesso nem falha normal.
EXIT_CODE_ESTADO_SOBRESCRITO = 42

LOS_DIAG_DIR = os.path.join(PROJECT_DIR, "logs", "los")
VASCO_STATE_FILE = os.path.join(PROJECT_DIR, "logs", "vasco_state.json")

def _capturar_screenshot_los():
    """ Grava o ecrã inteiro do jogo em logs/los/<timestamp>.png -- prova
    visual de cada deteção real do banner "MOVE TO OBTAIN LINE OF SIGHT TO
    TARGET" a meio do voo (pasta nova pedida pelo utilizador, separada de
    logs/diag_assist/ e de logs/erro_*.png porque isto não é um erro nem um
    passo de engatar_assistencia_menu()). Best-effort. """
    try:
        os.makedirs(LOS_DIAG_DIR, exist_ok=True)
        caminho = os.path.join(LOS_DIAG_DIR, f"{time.strftime('%Y%m%d_%H%M%S')}.png")
        with mss.mss() as sct:
            try:
                monitor_jogo = sct.monitors[1]
            except Exception:
                monitor_jogo = sct.monitors[0]
            img_bgra = np.array(sct.grab(monitor_jogo))
            cv2.imwrite(caminho, cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR))
        print(f"[LOS-VOO] Screenshot gravado em {caminho}")
        return caminho
    except Exception as e:
        print(f"[LOS-VOO] Falha ao gravar screenshot (ignorada): {e}")
        return None

def _registar_los_ocluso_auto(sistema):
    """ Regista na BD partilhada uma observação 'oclusos' automática --
    mesma ligação/tabela de registar_los_visivel_auto(), mas origem
    'auto-win' (fica de fora do ajuste de fase/período em los_checker.py,
    tal como as 'visivel' automáticas -- decisão do utilizador: só
    observações manuais 'win'/'linux' calibram o modelo). Serve para
    auditoria/histórico, não para recalibrar sozinha.
    NUNCA pode parir o voo -- qualquer falha é só reportada. """
    try:
        from datetime import datetime, timezone
        from dotenv import load_dotenv
        import psycopg2

        load_dotenv(os.path.join(PROJECT_DIR, ".env"))
        host = os.environ.get("R2D2_DB_HOST")
        if not host:
            return

        conn = psycopg2.connect(
            host=host,
            port=os.environ.get("R2D2_DB_PORT", "5432"),
            dbname=os.environ.get("R2D2_DB_NAME", "ED"),
            user=os.environ.get("R2D2_DB_USER", "r2d2"),
            connect_timeout=4,
        )
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO los_observacoes (sistema, timestamp_utc, estado, nota, origem) "
                    "VALUES (%s, %s, %s, %s, %s);",
                    (sistema, datetime.now(timezone.utc), "oclusos",
                     "automatica: banner 'MOVE TO OBTAIN LINE OF SIGHT TO TARGET' visto "
                     "a meio do voo em modo auto, perna limpa (sem erros/retries)",
                     "auto-win"))
        finally:
            conn.close()
        print(f"[LOS-VOO] Observação 'oclusos' registada na BD para '{sistema}'.")
    except Exception as e:
        print(f"[LOS-VOO] Falha ao registar observação (ignorada, o voo continua): {e}")

def _voltar_para_origem_por_oclusao_los():
    """ Chamada quando o banner de LOS foi visto a meio do voo E
    los_checker.calcular_espera_los() confirma oclusão agora -- vira a nave
    para trás em vez de continuar rumo a um destino que sabemos estar
    bloqueado.

    Direção: lida de VASCO_STEP_NUMBER (posta por vasco.py no ambiente do
    subprocesso, ver executar_script()) -- '4' = a caminho do carrier
    (voltar para a ESTAÇÃO), '9' = a caminho da estação (voltar para o
    CARRIER). Sem esta variável (ex.: script corrido à mão, fora do vasco.py)
    não há como saber a direção em segurança -- aborta em vez de adivinhar.

    Reescreve vasco_state.json com o 'last_step' que faz o PRÓXIMO passo
    (o mesmo script SUPERCRUISE, com o alvo já trocado) apontar para a
    origem, e sai com EXIT_CODE_ESTADO_SOBRESCRITO para o vasco.py recarregar
    o estado em vez de tratar isto como sucesso ou falha normal:
      - a caminho do carrier (step 4) -> volta à ESTAÇÃO -> last_step=8
        (o próximo passo reaproveita o SUPERCRUISE da etapa 9, que já
        termina em DOCKING(estação), etapa 10 -- é o mesmo raciocínio do
        step 9 original, só que sem ter passado por VENDER/SELECT_STATION;
        o porão continua com o item comprado, por isso o ciclo seguinte a
        partir da etapa 1 (COMPRAR) já salta a compra -- ver
        comprar.py::validar_porao_antes_de_comprar()).
      - a caminho da estação (step 9) -> volta ao CARRIER -> last_step=3
        (reaproveita o SUPERCRUISE da etapa 4, termina em DOCKING(carrier),
        etapa 5; o porão continua vazio do item, undocking.py::
        validar_carga_antes_de_descolar() já exige isso para descolar do
        carrier, por isso o fluxo normal de VENDER na etapa 6 segue sem
        alterações -- não há nada para vender ainda, mas essa etapa não
        assume que há). """
    passo_atual = os.environ.get("VASCO_STEP_NUMBER")
    if passo_atual == "4":
        alvo_regresso, novo_last_step, nome_alvo = "station", 8, "ESTAÇÃO"
    elif passo_atual == "9":
        alvo_regresso, novo_last_step, nome_alvo = "carrier", 3, "CARRIER"
    else:
        abortar_com_erro(
            f"Oclusão de LOS confirmada a meio do voo, mas VASCO_STEP_NUMBER "
            f"('{passo_atual}') não é '4' nem '9' -- não é seguro adivinhar a "
            f"direção do regresso. Intervenção manual necessária."
        )

    print(f"\n>>> LOS-VOO: a virar a nave para trás, rumo a {nome_alvo}...")
    logging.info(f"LOS-VOO: oclusao confirmada, a voltar para {nome_alvo} (VASCO_STEP_NUMBER={passo_atual}).")

    # Troca o alvo de navegação para a origem -- select_target.py corrido
    # como subprocesso (mesmo padrão de invocação usado por vasco.py),
    # forçado via VASCO_FORCE_TARGET porque a deteção dinâmica normal desse
    # script olha para o Undocked/Docked mais recente e aponta sempre para a
    # FRENTE (a mesma direção de onde a nave já vem) -- nunca para trás.
    env_alvo = os.environ.copy()
    env_alvo["VASCO_FORCE_TARGET"] = alvo_regresso
    resultado_alvo = subprocess.run(
        [sys.executable, "-u", os.path.join(PROJECT_DIR, "select_target.py")],
        env=env_alvo, timeout=60,
    )
    if resultado_alvo.returncode != 0:
        abortar_com_erro(
            f"Falha ao trocar o alvo de navegação para {nome_alvo} durante o "
            f"regresso por oclusão de LOS (select_target.py saiu com código "
            f"{resultado_alvo.returncode}). Intervenção manual necessária."
        )

    # Reescreve vasco_state.json -- só o 'last_step', mantém
    # 'completed_steps' como está (é só um contador de exibição, e as
    # etapas já percorridas nesta viagem para a frente continuam
    # genuinamente concluídas).
    try:
        with open(VASCO_STATE_FILE, 'r', encoding='utf-8') as f:
            estado = json.load(f)
    except Exception:
        estado = {"completed_steps": []}
    estado["last_step"] = novo_last_step
    estado["success"] = True
    estado["error"] = f"Regresso a {nome_alvo} por oclusao de LOS confirmada a meio do voo."
    with open(VASCO_STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(estado, f, indent=2)
    print(f"[LOS-VOO] vasco_state.json atualizado: last_step={novo_last_step} (próximo passo reaproveita o SUPERCRUISE rumo a {nome_alvo}).")
    logging.info(f"LOS-VOO: vasco_state.json last_step={novo_last_step}.")

    sys.exit(EXIT_CODE_ESTADO_SOBRESCRITO)

def _tratar_los_detetado_em_voo():
    """ Chamada quando o template 'line_of_sight' bate no HUD durante
    engatar_assist_e_alinhar() -- uma oclusão de LOS REAL vista a meio do
    voo (distinto do gate pré-undocking em vasco.py, que usa
    calcular_espera_los() antes de sequer descolar).

    Só regista/age se a perna atual estiver limpa (leg_esta_limpa(), ver
    leg_state.py) -- sem erros/retries, sem intervenção manual, sem plano de
    fuga acionado nesta perna -- para não contaminar a prova com um caso
    ambíguo. Cruza com los_checker.calcular_espera_los() (o mesmo modelo
    orbital usado no gate pré-undocking):
      - Se o modelo TAMBÉM prevê oclusão agora -> confirmado, regista a
        observação e vira a nave para trás.
      - Se o modelo prevê livre -> divergência do modelo real vs previsto,
        aborta e pede ajuda humana em vez de tentar adivinhar/corrigir
        sozinho. """
    if not leg_esta_limpa():
        print("[LOS-VOO] Banner de LOS visto, mas perna com erro/retry -- não é uma "
              "medição independente, a ignorar (sem registo nem regresso automático).")
        return

    print("\n[LOS-VOO] Banner 'MOVE TO OBTAIN LINE OF SIGHT TO TARGET' detetado a meio do voo (perna limpa).")
    logging.warning("LOS-VOO: banner de oclusao detetado a meio do voo (perna limpa).")
    _capturar_screenshot_los()

    sistema = obter_sistema_atual()
    if not sistema:
        abortar_com_erro("Banner de oclusão de LOS visto a meio do voo, mas sistema atual "
                          "desconhecido (Journal ilegível) -- não é seguro cruzar com "
                          "los_checker nem decidir a direção do regresso. Intervenção manual necessária.")

    _registar_los_ocluso_auto(sistema)

    from los_checker import calcular_espera_los
    espera_prevista = calcular_espera_los(sistema=sistema)
    if espera_prevista and espera_prevista > 0:
        print(f"[LOS-VOO] los_checker CONFIRMA oclusão agora (espera prevista {espera_prevista:.0f}s) -- modelo e realidade batem certo.")
        logging.info(f"LOS-VOO: los_checker confirma oclusao (espera={espera_prevista:.0f}s).")
        _voltar_para_origem_por_oclusao_los()
    else:
        abortar_com_erro(
            "Banner de oclusão de LOS visto ao vivo a meio do voo, mas "
            "los_checker.calcular_espera_los() NÃO prevê oclusão agora para "
            f"'{sistema}' -- divergência entre o modelo e a realidade "
            "(possível falha de calibração). Intervenção manual necessária, "
            "NÃO a corrigir sozinho às cegas."
        )

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
    aparece com o assist LIGADO, não desligado). É importante não confiar só
    num dos dois templates aqui: D+Space dentro do painel é um TOGGLE, e um
    falso negativo neste early-return (assist já ligado, mas nenhum destes
    sinais detetado nesse instante) manda o código abrir o painel e
    DESLIGAR o que já estava a funcionar.

    NÃO usar o retículo do HUD (olho.localizar_alvo_hud) aqui como terceiro
    sinal -- foi tentado e revertido: prova real em log (2026-09-16 03:16:04)
    mostrou os dois templates acima a falhar (0.400 e 0.683, ambos abaixo do
    limiar) e mesmo assim este early-return disparou, saltando a FASE 1
    inteira (nunca abriu o menu 1, nunca tentou o D+Space) e entrando direto
    no loop de alinhamento a acreditar que o Assist já estava ligado quando
    na verdade nunca tinha sido ativado -- confirmado pelo IMPULSO_HUD nos
    logs do utilizador (o retículo aparece sempre que há alvo trancado no
    HUD, LIGADO ou DESLIGADO o Assist, não é um sinal exclusivo do Assist
    como se assumiu antes). """
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

    if not destino_nome:
        # Telemetria não reportou nenhum destino trancado -- glitch real
        # confirmado em produção (2026-09-15 20:19): o campo 'Destination'
        # do Status.json apareceu vazio já em Supercruise, mesmo tendo
        # sido trancado antes do salto para lá chegarmos. Em vez de
        # avançar sem sequer saber que alvo esperar, infere pelo mesmo
        # critério de negócio já usado em
        # undocking.py::validar_carga_antes_de_descolar(): com carga a
        # bordo vamos para o carrier (a venda ainda não aconteceu); sem
        # carga vamos para a estação (a compra já aconteceu) -- Futen se o
        # sistema atual for Fujin, Hammel Terminal se for Kamitra.
        cargo_atual = ler_cargo_telemetria(debug=True)
        sistema_atual = obter_sistema_atual()
        if cargo_atual and cargo_atual > 0:
            destino_nome = "ZAHIR"
        elif sistema_atual == "Kamitra":
            destino_nome = "HAMMEL TERMINAL"
        else:
            destino_nome = "FUTEN SPACEPORT"  # default: Fujin, ou sistema desconhecido
        msg_inferido = (f"Destino ausente da telemetria -- inferido por contexto "
                         f"(carga={cargo_atual}, sistema={sistema_atual or 'desconhecido'}) -> '{destino_nome}'.")
        print(f"[AVISO] {msg_inferido}")
        logging.info(f"engatar_assistencia_menu: {msg_inferido}")

    if "ZAHIR" in destino_nome.upper():
        template_alvo, nome_alvo = templates['zahir_confirm'], "ZAHIR"
        template_selecionado = templates['zahir_selected']
        # A linha em destaque com '< >' parece alternar (pulsar?) entre
        # fundo amarelo (zahir_selected) e fundo verde -- confirmado ao
        # vivo (2026-09-15 22:5x): carrier_selected.png bate a 0.92 num
        # instante e só 0.796 segundos depois, na MESMA linha, só porque a
        # cor de fundo mudou. Lista de variantes extra em vez de um único
        # 'alt' -- já vamos em duas, mais fácil de continuar a somar do
        # que trocar a estrutura outra vez da próxima vez que aparecer uma
        # variante nova.
        templates_selecionado_extra = [templates['zahir_highlight_sem_cursor'], templates['zahir_verde_brackets']]
        template_locked_sem_cursor = templates['zahir_locked']
    elif "FUTEN" in destino_nome.upper():
        template_alvo, nome_alvo = templates['futen_confirm'], "FUTEN SPACEPORT"
        template_selecionado = templates['futen_selected']
        templates_selecionado_extra = []  # ainda sem recortes calibrados para estes estados na estação
        template_locked_sem_cursor = None  # ainda sem recorte calibrado para este estado na estação
    else:
        template_alvo, nome_alvo = None, None
        template_selecionado = None
        templates_selecionado_extra = []
        template_locked_sem_cursor = None
        print(f"[AVISO] Destino '{destino_nome}' não reconhecido (nem Zahir nem Futen) -- validação de alvo desativada nesta fase.")

    # Sessão de diagnóstico (logs/diag_assist/<timestamp>/) -- passos 1
    # (abrir painel/NAV TAB) e a fase de seleção na lista já confirmados
    # fiáveis em jogo real (ver diagnóstico desta conversa); o registo
    # passo-a-passo só começa a partir do popup de confirmação, que é onde
    # a falha real acontecia.
    _diag_iniciar_sessao()

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
        _diag_passo("FALHA_nav_tab")
        print(f"[DIAG] Pasta de diagnóstico desta tentativa: {_diag_dir}")
        logging.error("engatar_assistencia_menu: aba NAVIGATION não apareceu após 3 tentativas.")
        abortar_com_erro("Falha crítica: aba NAVIGATION não apareceu após 3 tentativas.")

    # 2. Selecionar o destino pré-selecionado (Space) e validar visualmente
    # que é mesmo o alvo esperado -- duas fases com orçamentos de retry
    # PRÓPRIOS (ver diagnóstico desta conversa, screenshots em
    # logs/diag_assist/):
    #   Fase A (lista): confirma a linha certa destacada ('< NOME >') antes
    #     de premir 'space'. Até 3 falhas -- à 3ª, 1x Backspace e aborta.
    #   Fase B (popup): confirma o TÍTULO do popup (nome certo) E o ÍCONE
    #     do botão lock/unlock em foco (confirma que abriu no sítio certo,
    #     independente de estar em estado LOCK ou UNLOCK -- confirmado em
    #     jogo real que tanto faz qual dos dois para o passo seguinte). Se
    #     qualquer um dos dois falhar, volta à Fase A (1x Backspace) --
    #     orçamento próprio, até 5 falhas -- à 5ª, 2x Backspace e aborta.
    falhas_lista = 0
    falhas_popup = 0
    MAX_FALHAS_LISTA = 3
    MAX_FALHAS_POPUP = 5

    if template_alvo is None:
        # Sem template conhecido para validar visualmente (nome não
        # reconhecido, ex.: Hammel Terminal em Kamitra, ainda sem
        # templates calibrados) -- não dá para confirmar o título nem a
        # linha da lista, mas o 'Space' que seleciona o destino
        # pré-realçado continua a ser necessário. Sem isto,
        # 'alvo_confirmado' ficava True de imediato e o código avançava
        # direto para o loop do 'D' sem NUNCA ter aberto o ecrã de info de
        # nenhum destino -- bug real confirmado em produção (2026-09-15
        # 20:19, destino ausente da telemetria antes deste fallback
        # existir): 3x 'D' enviados para a lista genérica, nunca para o
        # ecrã certo, painel fechou-se sozinho.
        print(f"[AVISO] Sem template para validar '{nome_alvo or destino_nome}' -- a selecionar (Space) sem confirmar visualmente.")
        pydirectinput.press('space')
        time.sleep(1.0)
        alvo_confirmado = True
    elif template_locked_sem_cursor is not None and procurar_template(template_locked_sem_cursor, f"{nome_alvo} JÁ TRANCADO (sem cursor)", MONITOR_PANEL, 0.85, debug=True):
        # O destino já aparece trancado na lista (nome sem '< >', cor
        # diferente do cursor) mesmo sem o cursor estar em cima dele --
        # sinal direto do próprio painel de que já está selecionado, mais
        # fiável do que a telemetria (Destination) que falhou e nos trouxe
        # até aqui. Não faz sentido navegar o cursor até lá e premir
        # 'Space' outra vez: 'Space'/'D'+'Space' são TOGGLE, e mexer no que
        # já está trancado corretamente arrisca desfazê-lo. Salta direto
        # para o loop do 'D' (ativar o Assist).
        print(f"[OK] '{nome_alvo}' já aparece trancado na lista (sem cursor lá) -- a saltar seleção/Space, direto para o Assist.")
        logging.info(f"engatar_assistencia_menu: '{nome_alvo}' já trancado (detetado sem cursor na lista) -- seleção saltada de propósito.")
        alvo_confirmado = True
    else:
        alvo_confirmado = False

    while not alvo_confirmado:
        time.sleep(1)
        if not procurar_template(templates['nav_tab'], "NAV TAB (antes do space, painel ainda aberto?)", MONITOR_PANEL, 0.80, debug=True):
            print("[AVISO] Painel não está visível antes do 'space' -- a reabrir e renavegar para NAVIGATION.")
            pydirectinput.press('1')
            time.sleep(1.2)
            confirmar_aba_navigation()

        # Fase A: confirma que a linha certa está mesmo destacada na lista
        # (nome entre '< >', ex.: "< ZAHIR W6G-26N >") ANTES de premir
        # 'space' -- ver comentário nos templates *_selected em
        # TEMPLATES_NOMES. 1s de assentamento antes de ler -- a lista podia
        # ainda estar a assentar do passo anterior (reabertura do painel ou
        # Backspace da tentativa anterior).
        if template_selecionado is not None:
            time.sleep(1.5)
            # 0.85 (era 0.80) -- caso real confirmado (2026-09-15 21:22,
            # diag_assist): com 0.80, o template ("< ZAHIR W6G-26N >")
            # deu falsos positivos de 0.799-0.833 numa linha que NÃO era o
            # Zahir (abriu FUTEN SPACEPORT e depois NAV BEACON a seguir ao
            # 'Space'). Match genuíno medido em jogo real: 0.886 (linha
            # selecionada) / 0.873 (mesma linha, momento diferente) --
            # 0.85 fica acima de todo o ruído observado sem se aproximar
            # do match real.
            LIMIAR_SELECIONADO = 0.85

            def _linha_alvo_destacada(sufixo_label=""):
                # Várias aparências possíveis da linha em destaque -- com
                # '< >' fundo amarelo (template_selecionado), com '< >'
                # fundo verde, sem '< >' fundo amarelo, sem '< >' fundo
                # oliva (templates_selecionado_extra, só calibrados para o
                # Zahir por agora) -- parece alternar/pulsar entre cores ao
                # vivo. Qualquer uma confirma que a linha certa está em
                # destaque; para no primeiro que bater.
                if procurar_template(template_selecionado, f"{nome_alvo} SELECIONADO NA LISTA{sufixo_label}", MONITOR_PANEL, LIMIAR_SELECIONADO, debug=True):
                    return True
                for i, tpl_extra in enumerate(templates_selecionado_extra, 1):
                    if procurar_template(tpl_extra, f"{nome_alvo} DESTACADO variante {i}{sufixo_label}", MONITOR_PANEL, LIMIAR_SELECIONADO, debug=True):
                        return True
                return False

            # Screenshot da LISTA neste instante, antes do 'Space' -- sem
            # isto nunca tínhamos o frame real de um falso positivo/negativo
            # para inspecionar depois, só screenshots de OUTRO instante
            # (o popup que abriu a seguir). Pedido direto do utilizador
            # desta conversa.
            _diag_passo(f"lista_falhas_lista{falhas_lista}")
            linha_selecionada = _linha_alvo_destacada()
            if not linha_selecionada:
                # Antes de desistir desta tentativa (Backspace + reabrir),
                # tenta "caçar" a linha certa com 'w' -- mesma ideia do
                # varrimento já usado em select_target.py (lá com 's'), só
                # que aqui a lista pode ter ficado com o cursor num sítio
                # diferente do esperado (ex.: voltou ao topo depois de
                # reabrir o painel) em vez de precisar de reabrir tudo outra
                # vez. Até 5 tentativas de 'w', uma checagem a cada uma.
                for tentativa_w in range(1, 6):
                    pydirectinput.press('w')
                    # 1.5s (era 0.7s) -- pedido do utilizador para despistar
                    # se a lista precisa de mais tempo para assentar entre
                    # cada 'w' antes da leitura seguinte.
                    time.sleep(1.5)
                    _diag_passo(f"lista_falhas_lista{falhas_lista}_apos_w{tentativa_w}")
                    linha_selecionada = _linha_alvo_destacada(f" (apos 'w' {tentativa_w}/5)")
                    if linha_selecionada:
                        print(f"[OK] Linha '{nome_alvo}' encontrada com 'w' (tentativa {tentativa_w}/5).")
                        break

            if not linha_selecionada:
                falhas_lista += 1
                if falhas_lista >= MAX_FALHAS_LISTA:
                    fechar_painel_se_aberto()
                    _diag_passo("FALHA_selecionado_lista")
                    print(f"[DIAG] Pasta de diagnóstico desta tentativa: {_diag_dir}")
                    logging.error(f"engatar_assistencia_menu: linha '{nome_alvo}' nunca ficou destacada na lista após {MAX_FALHAS_LISTA} falhas.")
                    abortar_com_erro(f"Falha crítica: linha '{nome_alvo}' nunca ficou destacada na lista após {MAX_FALHAS_LISTA} falhas.")
                print(f"[AVISO] Linha '{nome_alvo}' não está destacada na lista (falha {falhas_lista}/{MAX_FALHAS_LISTA}) -- Backspace x2 e nova tentativa.")
                pydirectinput.press('backspace')
                time.sleep(0.3)
                pydirectinput.press('backspace')
                time.sleep(0.5)
                continue

        print(">>> Focando no destino pré-selecionado (Space)...")
        pydirectinput.press('space')
        time.sleep(1.5)

        if template_alvo is None:
            alvo_confirmado = True
            break

        # Fase B: título do popup + ícone do botão lock/unlock em foco.
        _diag_passo(f"confirm_popup_falhas_lista{falhas_lista}_popup{falhas_popup}")
        titulo_ok = procurar_template(template_alvo, f"CONFIRM {nome_alvo}", MONITOR_PANEL, 0.80, debug=True)
        toggle_ok = procurar_template(templates['lock_unlock_toggle'], "LOCK/UNLOCK TOGGLE (popup)", MONITOR_PANEL, 0.80, debug=True)

        if titulo_ok and toggle_ok:
            print(f"[OK] Alvo confirmado: {nome_alvo} (título + botão lock/unlock em foco).")
            alvo_confirmado = True
            break

        # Diagnóstico direto: confirma explicitamente SE abriu o NAV BEACON
        # (não só "não é o Zahir/Futen", título ambíguo a 0.42) -- caso
        # real repetido (2026-09-15 22:45-22:46): a caça com 'w' aterrava
        # sempre no Nav Beacon. Template dedicado ('nav_beacon_confirm.png',
        # recortado do próprio popup), separação limpa confirmada (1.000
        # no Nav Beacon genuíno, 0.389 no Futen). Se for mesmo o Nav
        # Beacon, tenta 's' (direção oposta ao 'w') antes da próxima volta
        # à Fase A -- 'w' sozinho já mostrou ficar preso a aterrar sempre
        # aqui.
        e_nav_beacon = procurar_template(templates['nav_beacon_confirm'], "CONFIRM NAV BEACON (é mesmo este o errado?)", MONITOR_PANEL, 0.80, debug=True)
        if e_nav_beacon:
            print(f"[AVISO] Confirmado: abriu NAV BEACON em vez de '{nome_alvo}'.")
            logging.info(f"engatar_assistencia_menu: popup confirmado como NAV BEACON em vez de '{nome_alvo}' -- a tentar 's' antes de repetir 'w'.")

        falhas_popup += 1
        if falhas_popup >= MAX_FALHAS_POPUP:
            pydirectinput.press('x')
            fechar_painel_se_aberto()
            _diag_passo("FALHA_confirmacao_popup")
            print(f"[DIAG] Pasta de diagnóstico desta tentativa: {_diag_dir}")
            logging.error(f"engatar_assistencia_menu: popup de '{nome_alvo}' (título={titulo_ok}, botão={toggle_ok}, nav_beacon={e_nav_beacon}) não confirmou após {MAX_FALHAS_POPUP} falhas.")
            abortar_com_erro(f"Falha crítica: popup de confirmação do alvo '{nome_alvo}' não validou (título ou botão) após {MAX_FALHAS_POPUP} falhas.")

        print(f"[AVISO] Popup de '{nome_alvo}' não validou (título={titulo_ok}, botão={toggle_ok}) -- falha {falhas_popup}/{MAX_FALHAS_POPUP}, a voltar à lista.")
        pydirectinput.press('backspace')
        time.sleep(0.5)
        if e_nav_beacon:
            # NÃO usar um número fixo de 's' -- caso real confirmado
            # (2026-09-16, diag_assist 20260916_032611): com a lista desta
            # sessão a ter exatamente 3 linhas (Zahir/Futen/Nav Beacon), um
            # "3x 's'" fixo dá a volta completa e aterra sempre de volta no
            # MESMO Nav Beacon de onde partiu -- confirmado com 4 ciclos
            # seguidos, todos com o mesmo match exato (0.853-0.854 em
            # (732, 543)), nunca escapando dali. O número certo de passos
            # depende de quantas linhas a lista tem e da posição de cada
            # uma (que pode reordenar por distância), por isso testa 's' um
            # de cada vez e verifica logo a seguir com
            # _linha_alvo_destacada() -- mesmo padrão já usado na caça com
            # 'w' da Fase A -- em vez de disparar às cegas.
            for tentativa_s in range(1, 3):
                pydirectinput.press('s')
                time.sleep(0.5)
                if _linha_alvo_destacada(f" (apos 's' {tentativa_s}/2)"):
                    print(f"[OK] Linha '{nome_alvo}' encontrada com 's' (tentativa {tentativa_s}/2).")
                    break

    # 3. Selecionar o Supercruise Assist (D -> Space). Chega-se aqui sempre
    # com o Assist desligado -- o early return de assist_ja_ativo() no topo
    # da função já tratou o caso "já ligado, não mexer" (D+Space é um
    # toggle: enviá-lo com o assist já ligado desliga-o em vez de o ligar --
    # foi isto que desligou o assist com o alvo já trancado num caso real,
    # ver diagnóstico desta conversa).
    #
    # 'D' às vezes não move o foco (confirmado em jogo real: screenshot
    # 'apos_d' idêntico ao anterior, ainda no botão lock/unlock, "space"
    # seguinte ia fazer lock/unlock em vez de ativar o Assist -- ver
    # diagnóstico desta conversa). Cada ícone da barra de baixo tem a sua
    # própria legenda na lista "Local Activities" quando está em foco (o
    # lock/unlock mostra "UNLOCK DESTINATION", por exemplo) -- por isso só
    # sai deste loop quando a legenda for EXATAMENTE uma das duas do botão
    # do Assist: "SUPERCRUISE ASSIST" (desligado) ou "DEACTIVATE
    # SUPERCRUISE ASSIST" (ligado). Qualquer outra coisa (incluindo
    # nenhuma das duas) significa que o foco ainda não chegou lá -- continua
    # a tentar em vez de decidir às cegas. Confirmado com screenshots reais
    # dos dois estados (temp/ desta conversa).
    MAX_TENTATIVAS_D = 3
    assist_on_lido = False
    assist_off_lido = False
    for tentativa_d in range(1, MAX_TENTATIVAS_D + 1):
        print(f">>> Movendo para o botão Supercruise Assist (D), tentativa {tentativa_d}/{MAX_TENTATIVAS_D}...")
        pydirectinput.press('d')
        time.sleep(1.5)
        _diag_passo(f"apos_d_tentativa{tentativa_d}")
        assist_on_lido = procurar_template(templates['deactivate_assist'], "DEACTIVATE SUPERCRUISE ASSIST (legenda)", MONITOR_PANEL, 0.85, debug=True)
        assist_off_lido = (not assist_on_lido) and procurar_template(templates['assist_toggle'], "SUPERCRUISE ASSIST (legenda, sem DEACTIVATE)", MONITOR_PANEL, 0.80, debug=True)
        if assist_on_lido or assist_off_lido:
            break
        print(f"[AVISO] Legenda ainda não é 'SUPERCRUISE ASSIST' nem 'DEACTIVATE SUPERCRUISE ASSIST' (tentativa {tentativa_d}/{MAX_TENTATIVAS_D}).")

    if not (assist_on_lido or assist_off_lido):
        pydirectinput.press('backspace')
        time.sleep(0.3)
        pydirectinput.press('backspace')
        time.sleep(0.5)
        _diag_passo("FALHA_legenda_nao_confirmada")
        print(f"[DIAG] Pasta de diagnóstico desta tentativa: {_diag_dir}")
        logging.error(f"engatar_assistencia_menu: legenda do Assist não confirmada (nem ativo nem inativo) após {MAX_TENTATIVAS_D} tentativas de 'D'.")
        abortar_com_erro(f"Falha crítica: legenda do Supercruise Assist não confirmada após {MAX_TENTATIVAS_D} tentativas de 'D'.")

    if assist_on_lido:
        print(">>> Legenda já diz 'DEACTIVATE SUPERCRUISE ASSIST' -- Assist já está ligado, a NÃO premir Space (desligava-o).")
        logging.info("engatar_assistencia_menu: legenda confirma Assist já ligado antes do Space -- toggle saltado de propósito.")
    else:
        print(">>> Legenda diz 'SUPERCRUISE ASSIST' (desligado) -- a ativar (Space)...")

        # Repete o próprio Space (não só a releitura) até 3 vezes -- caso
        # real confirmado (2026-09-15 19:16-19:17, diag_assist): a legenda
        # ficou EXATAMENTE igual ("SUPERCRUISE ASSIST", mesmo ícone em
        # foco) antes e depois do Space -- o toggle não reagiu de todo,
        # não foi só a legenda a demorar a re-renderizar. Um único Space
        # que se perca (pydirectinput, como qualquer envio de tecla, pode
        # falhar em silêncio) deixava o Assist genuinamente desligado.
        # Mesmo padrão já portado do Vasco-Nobara/Linux para o Space final
        # do undocking.py.
        #
        # IMPORTANTE (confirmado pelo utilizador): quando o Space faz mesmo
        # efeito e ativa o Assist, o jogo sai deste ecrã de info e VOLTA
        # PARA A LISTA (o mesmo ecrã do '1', com as linhas < FUTEN
        # SPACEPORT >/ZAHIR W6G-26N/NAV BEACON) -- não fica aqui à espera
        # que a legenda mude para "DEACTIVATE SUPERCRUISE ASSIST" no MESMO
        # ecrã, porque esse ecrã deixa de existir. Isto explica por que
        # nenhuma captura automática alguma vez viu a legenda mudar: a
        # confirmação por legenda estava a olhar para um ecrã que já não
        # estava lá. A confirmação certa é a linha do alvo
        # (template_selecionado, já usado na Fase A) voltar a aparecer na
        # lista -- prova positiva de que voltámos a ela.
        #
        # NÃO usar assist_ja_ativo() aqui -- tentado e revertido (caso real
        # confirmado 2026-09-15 19:40, diag_assist
        # 04_confirmacao_apos_space_tentativa1_confirmou.png): o
        # MONITOR_HUD (left=1050) sobrepõe-se à zona onde o ecrã de info
        # fica aberto (~430-1260), e o retículo do HUD deu falso positivo
        # em cima do próprio painel. Só é um sinal válido a partir da
        # vista de cabine, com o painel todo fechado.
        ligou_confirmado = False
        for tentativa_space in range(1, 4):
            pydirectinput.press('space')
            time.sleep(2.5)
            _diag_passo(f"apos_dspace_tentativa{tentativa_space}")

            # Poll com margem (até 2s) em vez de uma leitura única.
            for _ in range(4):
                ligou_confirmado = procurar_template(template_selecionado, f"{nome_alvo} DE VOLTA NA LISTA (confirma ativação)", MONITOR_PANEL, 0.80, debug=True)
                if ligou_confirmado:
                    break
                time.sleep(0.5)
            _diag_passo(f"confirmacao_apos_space_tentativa{tentativa_space}_{'confirmou' if ligou_confirmado else 'nao_confirmou'}")
            if ligou_confirmado:
                break
            print(f"[AVISO] Nem a legenda nem o HUD confirmaram o Assist ligado após o Space (tentativa {tentativa_space}/3).")

        # Se mesmo após 3 tentativas de Space (com tempo de sobra e dois
        # sinais possíveis) nenhum dos dois confirmar, é sinal real de
        # falha -- aborta e pede intervenção manual, em vez de seguir às
        # cegas com o Assist possivelmente desligado.
        if not ligou_confirmado:
            print(f"[DIAG] Pasta de diagnóstico desta tentativa: {_diag_dir}")
            logging.error("engatar_assistencia_menu: Space não confirmou ativação (nem legenda nem HUD) após 3 tentativas.")
            abortar_com_erro("Falha crítica: Supercruise Assist não confirmou ativação após 3 tentativas de Space -- intervenção manual necessária.")

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
    for i in range(1, 4):
        pydirectinput.press('backspace')
        time.sleep(0.3)
        pydirectinput.press('backspace')
        # 1.0s (era 0.5s) -- visto falhar em jogo real: o segundo Backspace
        # ainda não tinha assentado quando o NAV TAB foi verificado, dando
        # um falso "ainda aberto" (ver diagnóstico desta conversa).
        time.sleep(1.0)
        painel_fechado = not procurar_template(templates['nav_tab'], "NAV TAB (a confirmar fecho do painel)", MONITOR_PANEL, 0.80, debug=True)
        _diag_passo(f"fecho_painel_tentativa{i}_{'ok' if painel_fechado else 'falhou'}")
        if painel_fechado:
            break

    if not painel_fechado:
        fechar_painel_se_aberto()
        _diag_passo("FALHA_fecho_painel")
        print(f"[DIAG] Pasta de diagnóstico desta tentativa: {_diag_dir}")
        logging.error("engatar_assistencia_menu: painel não fechou após 3 tentativas de Backspace.")
        abortar_com_erro("Falha crítica: painel não fechou após ativar o Supercruise Assist -- a parar antes de mandar teclas de alinhamento para um menu ainda aberto.")

    # NÃO se confirma "Assist ativo" aqui -- nem ASSIST_ACTIVE nem
    # align_warning aparecem já neste instante, mesmo com o toggle a
    # funcionar perfeitamente: essa lição já tinha sido aprendida (e
    # documentada) no Vasco-Nobara/Linux -- "essa mensagem só aparece
    # depois do alvo estar alinhado (o toggle liga-se já, mas fica 'à
    # espera' até _alinhar_com_olho() apontar a nave). Confirmar isto aqui
    # abortava sempre, mesmo com o toggle a funcionar bem." Tínhamos essa
    # verificação aqui do lado Windows e ela reproduziu exatamente esse
    # falso-abort em produção (3 falhas seguidas na mesma noite, todas com
    # o D+Space aparentemente bem-sucedido pelos screenshots de
    # diagnóstico -- ver diagnóstico desta conversa). A proteção contra um
    # 'D' que não acerta no botão já existe mais acima (o loop de
    # confirmação de foco via template 'assist_toggle' antes do Space); a
    # confirmação real de que o Assist está mesmo a funcionar é feita a
    # seguir, em engatar_assist_e_alinhar() / monitorar_viagem(), já depois
    # do alinhamento começar -- exatamente onde o Linux também a faz.
    logging.info(f"engatar_assistencia_menu: sequência concluída (NAV confirmado, alvo={nome_alvo or 'N/D'} confirmado, D+Space enviado, painel fechado).")
    print(">>> Painel fechado. Assistência ligada. Voltando ao Cockpit.")

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
      (b) BÚSSOLA + HUD + SEM AVISO DO JOGO: olho.executar_passo_alinhamento()
          reporta 'alinhado_frame' (bússola ALINHADO_MACRO ou retículo do
          HUD travado) E o retículo do HUD confirma independentemente
          (dentro de olho.DEAD_ZONE_HUD -- 'alinhado_frame' sozinho pode vir
          só da bússola, sem o HUD ter confirmado nada) E o aviso nativo do
          jogo ("ALIGN WITH TARGET DESTINATION", template align_warning)
          NÃO está visível, sustentados 3s SEGUIDOS. O aviso do jogo
          prevalece sobre bússola/HUD -- só a bússola sozinha já deu falsos
          positivos, tanto com o aviso do jogo ainda bem visível no ecrã
          como (mais grave) com o Assist completamente desligado e a nave
          calhada de já estar virada para o alvo (nesse caso nem o
          align_warning aparece -- só aparece com o Assist ligado -- por
          isso a exigência extra do HUD, portada do Vasco-Nobara/Linux).

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
    ultimo_x = 0.0
    INTERVALO_X = 5.0  # segundos entre repeticoes do 'x' durante a correcao manual
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
            #
            # 'x' (estabilizar/acelerador a zero) repetido a cada
            # INTERVALO_X enquanto este caminho estiver ativo -- caso real
            # confirmado (2026-09-15 22:20-22:29): 150s inteiros neste
            # caminho sem NENHUM 'x' a seguir ao primeiro (só enviado uma
            # vez, no início de engatar_assistencia_menu(), antes de abrir
            # qualquer painel), a nave a acelerar continuamente em
            # Supercruise, e o 'ALIGN WITH TARGET DESTINATION' nunca saiu
            # do ecrã -- manobrabilidade em Supercruise cai com a
            # velocidade, por isso deixar a nave acelerar à vontade durante
            # os pequenos impulsos corretivos do olho.py torna cada vez
            # mais difícil (ou impossível) completar a curva. Não se aplica
            # ao caminho (a) -- aí o Assist já está a puxar sozinho, e o
            # próprio código já evita mandar qualquer input manual por cima
            # (ver comentário acima).
            if time.time() - ultimo_x >= INTERVALO_X:
                ultimo_x = time.time()
                pydirectinput.press('x')
                print("[LOG] 'x' (estabilizar) -- mantém a manobrabilidade durante a correção manual.")

            passo = olho.executar_passo_alinhamento(sct, area_bussola, CX_NEUTRO, CY_NEUTRO)
            olho.mostrar_debug_visual(passo, CX_NEUTRO, CY_NEUTRO)

            # Bussola cega (coords_bola None -- "NÃO_DETETADO"): se já houve
            # alguma leitura válida nesta sessão, executar_passo_alinhamento()
            # já tratou disto sozinho (desloca-se fortemente na direção do
            # último comando conhecido -- ver obter_ultimo_comando_valido()/
            # aplicar_manobra_bussola(forcar_forte=True) em olho.py); nada a
            # fazer aqui nesse caso, só chamar de novo duplicava o impulso.
            # Pedido direto do utilizador (caso real: log de 03:16 desta
            # conversa, "Bússola cega e já sem rolls" repetido, alvo sabia-se
            # estar ACIMA mas o código não fazia nada com essa informação).
            #
            # Se a bola NUNCA foi vista nesta sessão (sem última posição
            # nenhuma), não há para onde se deslocar -- aí sim rodar até
            # MAX_ROLLS_NUNCA_ADQUIRIDO (8) vezes; se mesmo assim continuar
            # sem leitura, último recurso: impulso forte 'w' a 16x
            # IMPULSO_BUSSOLA (executar_impulso_nunca_adquirido()). Pedido
            # direto do utilizador.
            if passo["coords_bola"] is None and olho.obter_ultimo_comando_valido() is None:
                if rolls_recuperacao < olho.MAX_ROLLS_NUNCA_ADQUIRIDO:
                    rolls_recuperacao += 1
                    olho.executar_roll_recuperacao(rolls_recuperacao, max_tentativas=olho.MAX_ROLLS_NUNCA_ADQUIRIDO)
                else:
                    olho.executar_impulso_nunca_adquirido()

            ainda_avisa = procurar_template(templates['align_warning'], "ALIGN WARNING (jogo)", MONITOR_CENTER, 0.82, debug=True, sct=sct)

            # Oclusão de LOS real vista no HUD a meio do voo -- distinto do
            # align_warning ("ALIGN WITH TARGET DESTINATION", desalinhamento
            # normal). _tratar_los_detetado_em_voo() decide sozinha se
            # regista/age (só com a perna limpa) e nunca devolve controlo
            # normalmente: ou vira a nave para trás (sys.exit com o código
            # especial que o vasco.py reconhece) ou aborta a pedir ajuda
            # humana.
            if procurar_template(templates['line_of_sight'], "LINE OF SIGHT (oclusão real, meio do voo)", MONITOR_CENTER, 0.82, debug=True, sct=sct):
                _tratar_los_detetado_em_voo()

            # 'alinhado_frame' fica True só pela bússola (ALINHADO_MACRO),
            # sem o HUD confirmar nada -- ver docstring de
            # olho.executar_passo_alinhamento(): "já não fica à espera do
            # HUD travar o alvo com precisão". Isso basta para PARAR de
            # corrigir o rumo, mas não chega para confirmar que o Assist
            # está mesmo ligado: se o Assist estiver desligado e a nave
            # calhar de já estar virada para o alvo, a bússola diz
            # "alinhado" e o align_warning nunca aparece (só aparece com o
            # Assist ligado) -- falso positivo confirmado em produção
            # (2026-09-14/15: "confirmado via bússola/HUD" com o Assist
            # realmente desligado, ver diagnóstico desta conversa). O
            # Vasco-Nobara/Linux já tinha este exato problema e corrige-o
            # exigindo também o retículo do HUD centrado (hud_confirma),
            # nunca só a bússola -- porta-se aqui a mesma exigência, com o
            # DEAD_ZONE_HUD que já existe (e já está calibrado) neste
            # projeto, em vez de inventar uma tolerância nova.
            hud_confirma = (passo["encontrou_hud"] and not passo["alvo_nas_costas"]
                            and abs(passo["dx_hud"]) <= olho.DEAD_ZONE_HUD
                            and abs(passo["dy_hud"]) <= olho.DEAD_ZONE_HUD)

            if passo["alinhado_frame"] and hud_confirma and not ainda_avisa:
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
                # Marca a perna como suja ANTES de acionar o plano de fuga --
                # sem isto, se executar_fuga() recuperar com sucesso (o
                # processo acaba por sair com código 0), leg_esta_limpa()
                # ficava a mentir "perna limpa" para quem vem a seguir (ex.:
                # _tratar_los_detetado_em_voo(), que exige "sem
                # interferências humanas ou piratas/queda do supercruise"
                # antes de registar/agir) -- marcar_leg_suja() só era chamada
                # em vasco.py, nunca aqui, para uma queda recuperada dentro
                # do mesmo processo.
                marcar_leg_suja()
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

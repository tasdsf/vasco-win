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

# Logger proprio (nao usa logging.basicConfig -- com varios scripts no mesmo
# processo, so o primeiro basicConfig chamado ganha, e todos os outros ficam
# com o prefixo errado no log partilhado).
_logger = logging.getLogger("vender")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    _fh = logging.FileHandler(os.path.join(pasta_logs, "r2d2_combined.log"), encoding='utf-8')
    _fh.setFormatter(logging.Formatter('%(asctime)s - [VENDER] - %(levelname)s - %(message)s'))
    _logger.addHandler(_fh)
    _logger.propagate = False

def abortar_com_erro(mensagem):
    """ Regista o erro no log e dispara exit code 1 para o Orquestrador intercetar """
    print(f"\n[FATAL] {mensagem}")
    _logger.error(mensagem)
    sys.exit(1)

NOME_JANELA = "Ocular do Bot - Analise Carrier"
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
                pos_x = ecra_secundario["left"]
                pos_y = ecra_secundario["top"]
                cv2.moveWindow(NOME_JANELA, pos_x, pos_y)
            else:
                cv2.moveWindow(NOME_JANELA, 0, 0)
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
# 1. SETUP E ÁREAS (Fleet Carrier)
# ==========================================
MONITOR_MENU = {"top": 1100, "left": 1000, "width": 600, "height": 400}
MONITOR_MARKET = {"top": 200, "left": 0, "width": 1600, "height": 1400}
LOG_DIR = os.path.expanduser('~') + r"\Saved Games\Frontier Developments\Elite Dangerous"

pasta_imagens = os.path.join(diretorio_atual, 'images')

templates_nomes = {
    'servicos': 'CARRIER_SERVICES.png',
    'noselection': 'NO_SELECTION.png',
    'market_off': 'COMMODITIES_MARKET_OFF.png',
    'market_on': 'COMMODITIES_MARKET_ON2.png',
    'rare_not_on': 'RARE_NOT_SELECTED.png',
    'rare_not_on2': 'RARE_NOT_SELECTED1.png',
    'exit_on': 'EXIT_SELECTED.png',
    'sell_confirm_fujin': 'RARE_2_SELL_CONFIRM.png',
}

templates = {}
try:
    for chave, nome_arq in templates_nomes.items():
        caminho = os.path.join(pasta_imagens, nome_arq)
        img = cv2.imread(caminho, cv2.IMREAD_COLOR)
        if img is None: raise FileNotFoundError(f"Falta imagem: {caminho}")
        templates[chave] = img
    print(f"[SISTEMA] Venda no Carrier V3 pronta e blindada.")
except Exception as e:
    abortar_com_erro(f"Falha ao carregar imagens para a memória: {e}")

# --- Motor de Voz ---
engine = pyttsx3.init()
def falar(texto):
    print(f"[VOZ] {texto}")
    engine.say(texto)
    engine.runAndWait()

# ==========================================
# 2. MOTOR DE VISÃO
# ==========================================
def procurar_template(template, nome_label, monitor, threshold=0.80, debug=False):
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
            
            cv2.rectangle(img_bgr, (5, 5), (450, 80), (0, 0, 0), -1)
            cv2.putText(img_bgr, f"Alvo: {nome_label}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            cv2.putText(img_bgr, f"Match: {max_val:.2f} / {threshold}", (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.8, cor, 2)
            
            cv2.imshow(NOME_JANELA, img_bgr)
            cv2.waitKey(1)
        
        return encontrou

def item_nao_selecionado(monitor=MONITOR_MARKET, threshold=0.85, debug=False):
    """ Valida com QUALQUER uma das duas variantes do template 'não selecionado'
        (RARE_NOT_SELECTED.png OU RARE_NOT_SELECTED1.png) — basta uma bater certo. """
    return (procurar_template(templates['rare_not_on'], "FUJIN TEA (INV)", monitor, threshold, debug=debug) or
            procurar_template(templates['rare_not_on2'], "FUJIN TEA (INV) v2", monitor, threshold, debug=debug))

# ==========================================
# 2b. CONFIRMAÇÃO DA VENDA VIA JOURNAL DO JOGO
# ==========================================
# Tipos internos confirmados no journal real (evento MarketSell -> "Type"):
# fujintea = Fujin Tea, kamitracigars = Kamitra Cigars. Só um dos dois está
# disponível para venda de cada vez, por isso aceitamos qualquer um dos dois
# sem sermos mais específicos.
TIPOS_RARE_ACEITES = {"fujintea", "kamitracigars"}

def get_latest_log():
    list_of_files = glob.glob(os.path.join(LOG_DIR, 'Journal.*.log'))
    if not list_of_files: return None
    return max(list_of_files, key=os.path.getctime)

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
            except Exception:
                continue
        return eventos
    except Exception:
        return []

def obter_cargo_atual():
    """ Lê o snapshot atual do porão (Cargo.json, escrito pelo próprio jogo
    sempre que o porão muda) -- serve para cruzar com a deteção visual antes
    de aceitar "nada para vender". Uma única leitura visual pontual pode
    apanhar o menu a meio de renderizar/scrollar e concluir vazio quando na
    verdade há carga por vender. """
    caminho = os.path.join(LOG_DIR, 'Cargo.json')
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('Count', 0)
    except Exception:
        return None  # desconhecido -- não bloquear o fluxo por causa disto

def aguardar_confirmacao_venda(posicao_ancora, timeout=30):
    """ Confirma a venda pelo evento MarketSell real do journal, em vez de
    confiar só na sequência visual de teclas/templates. """
    print("[LOG] A confirmar a venda pelo journal do jogo...")
    limite = time.time() + timeout
    while time.time() < limite:
        for evento in ler_novos_eventos(posicao_ancora):
            if evento.get('event') == 'MarketSell' and evento.get('Type', '').lower() in TIPOS_RARE_ACEITES:
                print(f"[OK] Venda confirmada pelo journal: {evento.get('Type_Localised')} "
                      f"x{evento.get('Count')} por {evento.get('TotalSale')} CR")
                _logger.info(f"Venda confirmada (MarketSell): {evento.get('Type_Localised')} "
                             f"x{evento.get('Count')} por {evento.get('TotalSale')} CR")
                return True
        time.sleep(0.5)
    print("[AVISO] Venda não confirmada pelo journal dentro do tempo limite.")
    _logger.warning("Venda NAO confirmada pelo journal dentro do tempo limite (MarketSell nao apareceu).")
    return False

# ==========================================
# 3. LÓGICA DE VENDA COM WATCHDOGS
# ==========================================

def fase_1_abrir_mercado():
    print("\n>>> Abrindo Commodities Market no Carrier...")
    time.sleep(1.0)
    pydirectinput.press('space') 
    
    # Watchdog 1: Esperar botões do mercado
    timeout = time.time() + 15
    while not (procurar_template(templates['market_off'], "MARKET", MONITOR_MARKET) or 
               procurar_template(templates['market_on'], "MARKET", MONITOR_MARKET)):
        if time.time() > timeout:
            abortar_com_erro("Timeout (15s) à espera que os serviços do Carrier abram.")
        time.sleep(0.5)

    # Navegar até o botão de mercado
    for tecla in ['d', 'd']:
        print(f"A mover seleção: {tecla.upper()}")
        pydirectinput.press(tecla)
        time.sleep(0.3)
        if procurar_template(templates['market_on'], "MARKET ON", MONITOR_MARKET, 0.60):
            print("[LOG] Botão de Mercado focado!")
            pydirectinput.press('space')
            return True
            
    abortar_com_erro("Botão 'Commodities Market' não detetado após varrimento mecânico.")

def fase_2_vender_tudo():
    print("\n>>> Iniciando varrimento de inventário (Aba SELL)...")
    time.sleep(2.5)
    
    pydirectinput.press('s') # Muda para aba SELL
    time.sleep(0.5)
    pydirectinput.press('space') # Seleciona aba SELL
    time.sleep(1.2)
    
    item_visivel = item_nao_selecionado(debug=True)

    if not item_visivel:
        # Antes de aceitar "nada para vender", cruzar com o porão real -- foi
        # isto que faltou num incidente em que o journal tinha unidades de
        # Fujin Tea e o bot declarou VAZIO por uma leitura visual falhada.
        cargo_atual = obter_cargo_atual()
        if cargo_atual:
            print(f"[AVISO] Ecrã não mostra nada para vender, mas o porão real tem "
                  f"Cargo={cargo_atual} unidades. A repetir a deteção visual antes de desistir...")
            time.sleep(1.5)
            item_visivel = item_nao_selecionado(debug=True)
            if not item_visivel:
                abortar_com_erro(f"Porão tem Cargo={cargo_atual} unidades no journal mas a interface não "
                                  f"mostra nada para vender -- menu dessincronizado. Intervenção manual necessária.")

    if item_visivel:
        print(f">>> Fujin Tea detectado no inventário!")
        pydirectinput.press('d') # Entra na lista
        time.sleep(0.5)

        for i in range(5):
            print(">>> Movendo foco para o topo da lista SELL (W)...")
            pydirectinput.press('w')
            time.sleep(0.5)

        # Watchdog 2: Limite de iterações de varrimento
        for i in range(25):
            if not item_nao_selecionado(debug=True):
                print(f">>> Fujin Tea aparenta estar selecionado, a confirmar...")
                pydirectinput.press('space')
                time.sleep(1.2)

                # A ausência de 'rare_not_on'/'rare_not_on2' só diz que a linha
                # atual não mostra nenhum dos dois por vender -- não confirma
                # que é mesmo Fujin Tea (podia ser outro item qualquer da
                # lista). Confirmar pelo nome no ecrã "SELL COMMODITY" antes
                # de vender às cegas.
                if not procurar_template(templates['sell_confirm_fujin'], "SELL CONFIRM FUJIN", MONITOR_MARKET, 0.85, debug=True):
                    print("[AVISO] Ecrã de venda não confirma Fujin Tea -- a cancelar e continuar a varrer.")
                    pydirectinput.press('backspace')
                    time.sleep(0.8)
                    pydirectinput.press('s')
                    time.sleep(0.4)
                    continue

                print(">>> Fujin Tea confirmado no ecrã de venda!")
                print(">>> Movendo foco para o botão SELL (s)...")
                pydirectinput.press('s')
                time.sleep(0.5)

                print(">>> Confirmando Venda Total!")
                ancora_journal = obter_tamanho_atual_log()
                pydirectinput.press('space')
                time.sleep(2.0)

                venda_confirmada = aguardar_confirmacao_venda(ancora_journal)

                for _ in range(3):
                    pydirectinput.press('backspace')
                    time.sleep(0.8)

                if not venda_confirmada:
                    return "FALHA_CONFIRMACAO"

                _logger.info("Venda concluida com sucesso -- VENDIDO (confirmada pelo journal).")
                falar("Sales operation completed commander. The cargo bay is empty.")
                return "VENDIDO"

            if procurar_template(templates['exit_on'], "EXIT BUTTON", MONITOR_MARKET, 0.75):
                # Chegar ao Exit a meio do varrimento NAO prova que o porao esta
                # vazio -- so prova que o bot nunca detetou a linha do item como
                # "selecionada" enquanto percorria a lista (pode ter perdido o
                # alinhamento visual a meio). Antes de aceitar "vazio" aqui,
                # cruzar com o Cargo.json real -- o mesmo cuidado que ja existe
                # no caminho "item nunca detetado à entrada" (mais acima).
                cargo_atual = obter_cargo_atual()
                if cargo_atual:
                    print(f"[AVISO] Chegou ao fim da lista sem vender, mas o porão real "
                          f"tem Cargo={cargo_atual} unidades -- o bot perdeu o alinhamento "
                          f"com a linha do item a meio do varrimento. NAO aceitar 'vazio' às "
                          f"cegas. A abortar para intervenção manual.")
                    for _ in range(2):
                        pydirectinput.press('backspace')
                        time.sleep(0.8)
                    return "FALHA_CONFIRMACAO"

                print(">>> Fim da lista. Nada encontrado para vender.")
                _logger.info("Venda: nada para vender (porao confirmado vazio pelo Cargo.json) -- VAZIO.")
                # Mesma profundidade de menu que o caminho "item nunca detetado à
                # entrada" (ainda dentro da lista SELL, sem ter aberto nenhum
                # dialogo de confirmação) -- por isso o MESMO número de backspaces
                # (2x), em vez do 1x que aqui estava antes e deixava o jogo um
                # nível "mais dentro" do que o resto do fluxo esperava.
                for _ in range(2):
                    pydirectinput.press('backspace')
                    time.sleep(0.8)
                return "VAZIO"

            pydirectinput.press('s')
            time.sleep(0.4)

        abortar_com_erro("Esgotou 25 iterações na lista de venda sem sucesso. O bot perdeu-se na interface.")

    print("[LOG] Item não detetado e porão confirmado vazio. A abortar venda de forma limpa.")
    for _ in range(2):
        pydirectinput.press('backspace')
        time.sleep(0.8)
    return "VAZIO"


def executar():
    inicializar_infraestrutura()

    print("Bot pronto. Inicia a operação no cockpit do Carrier em 3 segundos...")
    time.sleep(3)

    for tentativa in range(3):
        if fase_1_abrir_mercado():
            resultado = fase_2_vender_tudo()

            if resultado in ("VENDIDO", "VAZIO"):
                return

            print(f"[AVISO] Venda não confirmada pelo journal (tentativa {tentativa + 1}/3). "
                  f"A voltar ao menu da nave e tentar de novo...")
            time.sleep(2.0)

    abortar_com_erro("Venda não confirmada pelo journal após 3 tentativas completas.")


if __name__ == "__main__":
    executar()
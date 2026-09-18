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
_logger = logging.getLogger("comprar")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    _fh = logging.FileHandler(os.path.join(pasta_logs, "r2d2_combined.log"), encoding='utf-8')
    _fh.setFormatter(logging.Formatter('%(asctime)s - [COMPRAR] - %(levelname)s - %(message)s'))
    _logger.addHandler(_fh)
    _logger.propagate = False

def abortar_com_erro(mensagem):
    """ Regista o erro no log e dispara exit code 1 para o Orquestrador intercetar """
    print(f"\n[FATAL] {mensagem}")
    _logger.error(mensagem)
    for _ in range(3):
        pydirectinput.press('backspace')
        time.sleep(0.8)
    sys.exit(1)

NOME_JANELA = "Ocular do Bot - Diagnostico"
VISUAL_DEBUG = False # Muda para False para esconder as janelas

def inicializar_infraestrutura():
    """ Foca no jogo (Ecrã 1) e envia o painel visual para o Ecrã 2 """
    print("[SISTEMA] A focar no jogo...")
    
    focar_jogo_seguro()
    time.sleep(0.5)
            
    if VISUAL_DEBUG:
        print("[SISTEMA] A configurar janelas de diagnóstico...")
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
# 1. SETUP E CALIBRAÇÃO DE ÁREAS
# ==========================================
MONITOR_MENU = {"top": 1100, "left": 1000, "width": 600, "height": 400}
MONITOR_MARKET = {"top": 200, "left": 0, "width": 800, "height": 1400}
LOG_DIR = os.path.expanduser('~') + r"\Saved Games\Frontier Developments\Elite Dangerous"

pasta_imagens = os.path.join(diretorio_atual, 'images')

templates_nomes = {
    'servicos': 'STARPORT_SERVICES.png',
    'noselection': 'NO_SELECTION.png',
    'disembark': 'DISEMBARK.png',
    'market_off': 'COMMODITIES_MARKET_OFF.png',
    'market_on': 'COMMODITIES_MARKET_ON.png',
    'buy_on': 'BUY_SELECTED.png',
    'rare_on': 'RARE_SELECTED.png',
    'exit_on': 'EXIT_SELECTED.png'
}

templates = {}
try:
    for chave, nome_arq in templates_nomes.items():
        caminho = os.path.join(pasta_imagens, nome_arq)
        img = cv2.imread(caminho, cv2.IMREAD_COLOR)
        if img is None: raise FileNotFoundError(f"Falta imagem: {caminho}")
        templates[chave] = img
    print(f"[SISTEMA] {len(templates)} templates carregados!")
except Exception as e:
    abortar_com_erro(f"Falha ao carregar imagens para a memória: {e}")

# ==========================================
# 1b. CONFIRMAÇÃO DA COMPRA VIA JOURNAL DO JOGO
# ==========================================
# Mesmos tipos internos aceites pelo vender.py -- só um dos dois está
# disponível para compra de cada vez.
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

def aguardar_confirmacao_compra(posicao_ancora, timeout=30):
    """ Confirma a compra pelo evento MarketBuy real do journal, em vez de
    confiar só na sequência visual de teclas/templates -- sem isto, um menu
    dessincronizado ou compra recusada fica por detetar e a nave segue com
    o porão vazio. """
    print("[LOG] A confirmar a compra pelo journal do jogo...")
    limite = time.time() + timeout
    while time.time() < limite:
        for evento in ler_novos_eventos(posicao_ancora):
            if evento.get('event') == 'MarketBuy' and evento.get('Type', '').lower() in TIPOS_RARE_ACEITES:
                print(f"[OK] Compra confirmada pelo journal: {evento.get('Type_Localised')} "
                      f"x{evento.get('Count')} por {evento.get('TotalCost')} CR")
                _logger.info(f"Compra confirmada (MarketBuy): {evento.get('Type_Localised')} "
                             f"x{evento.get('Count')} por {evento.get('TotalCost')} CR")
                return True
        time.sleep(0.5)
    print("[AVISO] Compra não confirmada pelo journal dentro do tempo limite.")
    _logger.warning("Compra NAO confirmada pelo journal dentro do tempo limite (MarketBuy nao apareceu).")
    return False

# ==========================================
# 1c. VALIDAÇÃO DO PORÃO ANTES DE COMPRAR
# ==========================================
# Nomes internos do journal (evento Cargo -> Inventory[].Name), mesmos
# aceites em MarketBuy/MarketSell -- ver TIPOS_RARE_ACEITES acima.
ITEM_POR_ESTACAO = {
    "FUTEN": "fujintea",
    "HAMMEL": "kamitracigars",
}

def obter_cargo_inventario():
    """ Lê o snapshot atual do porão (Cargo.json, escrito pelo próprio jogo
    sempre que o porão muda) -- devolve (count_total, lista Inventory[]).
    Duplicado de vender.py::obter_cargo_atual() por convenção do projeto
    (scripts Windows não partilham imports entre si), estendido para
    devolver também o Inventory (nome de cada item a bordo), não só o
    total. """
    caminho = os.path.join(LOG_DIR, 'Cargo.json')
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('Count', 0), data.get('Inventory', [])
    except Exception:
        return None, []  # desconhecido -- não bloquear o fluxo por causa disto

def obter_estacao_atual():
    """ Lê o Journal para trás à procura do último 'StationName' (evento
    Docked/Location) -- mesma ideia de obter_tipo_estacao_atual() em
    undocking.py, só que aqui interessa o NOME da estação (para saber qual
    dos dois itens raros esperar), não o tipo. """
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
            if 'StationName' in data and data.get('event') in ('Docked', 'Location'):
                return data['StationName']
        return None
    except Exception:
        return None

def item_esperado_para_estacao(nome_estacao):
    """ Futen Spaceport -> Fujin Tea, Hammel Terminal -> Kamitra Cigars --
    mesmo critério de negócio já usado em supercruise_assist.py (cargo/
    sistema -> destino). None se a estação não for nenhuma das duas
    conhecidas. """
    if not nome_estacao:
        return None
    nome_upper = nome_estacao.upper()
    for chave, item in ITEM_POR_ESTACAO.items():
        if chave in nome_upper:
            return item
    return None

def validar_porao_antes_de_comprar():
    """ Só vale a pena comprar com o porão VAZIO do item em questão -- se já
    tiver o item a bordo (compra já confirmada antes, ex.: retry pós-falha
    depois de MarketBuy já ter disparado), a compra é saltada em vez de
    comprar a mais/duplicar. Devolve False (saltar) quando o item esperado
    para esta estação já está no porão com Count > 0; True (prosseguir)
    caso contrário -- incluindo quando a estação/item não é reconhecível,
    para não bloquear o fluxo às cegas. """
    cargo_total, inventario = obter_cargo_inventario()
    nome_estacao = obter_estacao_atual()
    item_esperado = item_esperado_para_estacao(nome_estacao)
    print(f"[CONTEXTO] Estação atual: {nome_estacao or 'desconhecida'} | "
          f"Item esperado: {item_esperado or 'desconhecido'} | Porão: {cargo_total}")

    if item_esperado:
        for entrada in (inventario or []):
            if entrada.get('Name', '').lower() == item_esperado and entrada.get('Count', 0) > 0:
                nome_bonito = entrada.get('Name_Localised', item_esperado)
                print(f"[OK] Já há {entrada.get('Count')}x {nome_bonito} no porão -- compra já feita, a saltar.")
                _logger.info(f"Porao ja tem {item_esperado} (x{entrada.get('Count')}) -- compra saltada, comprar.py sai sem executar.")
                return False
    elif cargo_total:
        print(f"[AVISO] Estação atual não reconhecida (nem Futen nem Hammel) mas há carga a bordo "
              f"({cargo_total}) -- a prosseguir sem saltar, validação de item não é possível.")

    return True

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

# ==========================================
# 3. FASES DE NAVEGAÇÃO COM WATCHDOGS
# ==========================================
def fase_1_entrar_servicos():
    print("\n>>> FASE 1: Menu Holográfico...")
    timeout = time.time() + 15
    while not (procurar_template(templates['noselection'], "IDLE", MONITOR_MENU, 0.75) or 
               procurar_template(templates['disembark'], "DISEMBARK", MONITOR_MENU, 0.75) or
               procurar_template(templates['servicos'], "SERVICES", MONITOR_MENU)):
        
        if time.time() > timeout:
            abortar_com_erro("Timeout (15s) à espera que o painel principal da estação estabilize.")
        time.sleep(0.5)
    
    time.sleep(1.2)
    for tecla in ['s', 's', 'w', 'w']:
        if procurar_template(templates['servicos'], "SERVICES", MONITOR_MENU):
            pydirectinput.press('space')
            return True
        pydirectinput.press(tecla)
        time.sleep(0.6)
        
    abortar_com_erro("Botão 'Starport Services' não detetado após a sequência mecânica de focagem.")

def fase_2_abrir_mercado():
    print("\n>>> FASE 2: Abrindo Mercado...")
    timeout = time.time() + 15
    while not (procurar_template(templates['market_off'], "MARKET OFF", MONITOR_MARKET) or 
               procurar_template(templates['market_on'], "MARKET ON", MONITOR_MARKET)):
        
        if time.time() > timeout:
            abortar_com_erro("Timeout (15s) à espera que a interface interna dos Serviços carregue.")
        time.sleep(0.5)

    for tecla in ['s', 's', 'w', 'w']:
        if procurar_template(templates['market_on'], "MARKET ON", MONITOR_MARKET):
            print("\n>>> FASE 2 : Market on, will be selected")
            time.sleep(1)
            pydirectinput.press('space')
            print("\n>>> FASE 2 : Market selected")
            return True
        pydirectinput.press(tecla)
        time.sleep(2.6)
        
    abortar_com_erro("Botão 'Commodities Market' não detetado na lista após varrimento mecânico.")

def fase_3_comprar_item():
    print("\n>>> FASE 3: Acedendo ao Mercado...")
    timeout = time.time() + 15
    while not procurar_template(templates['buy_on'], "BUY ON", MONITOR_MARKET):
        if time.time() > timeout:
            abortar_com_erro("Timeout (15s) à espera que o menu do Mercado estabeleça o botão BUY.")
        time.sleep(0.5)
        
    print("\n>>> FASE 3: Procurando rare goods...")
    time.sleep(2.0)
    pydirectinput.press('d')
    time.sleep(0.5)
    
    for i in range(40):
        if procurar_template(templates['rare_on'], "RARE FOUND", MONITOR_MARKET, 0.92, debug=True):
            print(">>> ITEM DETETADO! Comprando...")
            _logger.info("Detetou o item (Fujin Tea / Kamitra Cigars) no mercado.")
            pydirectinput.press('space')
            time.sleep(1.0)
            pydirectinput.keyDown('d')
            time.sleep(2.5)
            pydirectinput.keyUp('d')
            pydirectinput.press('s')
            time.sleep(0.5)

            ancora_journal = obter_tamanho_atual_log()
            pydirectinput.press('space')
            _logger.info("Comprou -- carregou no SPACE para confirmar a compra.")
            time.sleep(1.5)

            compra_confirmada = aguardar_confirmacao_compra(ancora_journal)

            for _ in range(3):
                pydirectinput.press('backspace')
                time.sleep(0.8)

            if not compra_confirmada:
                return "FALHA_CONFIRMACAO"
            return "COMPRADO"

        # Este template é válido de falhar se o item estiver esgotado (lógica de negócio normal)
        if procurar_template(templates['exit_on'], "EXIT BUTTON", MONITOR_MARKET, 0.75, debug=True):
            print(">>> Fim da lista. Item não disponível no momento.")
            _logger.info("Item nao disponivel no mercado (volume a 0): restock bloqueado enquanto houver "
                         "stock no porao ou < ~10 min desde a ultima compra -- comportamento normal do jogo. NAO_ENCONTRADO.")
            return "NAO_ENCONTRADO"

        pydirectinput.press('s')
        time.sleep(0.4)
        
    abortar_com_erro("Passou 40 iterações na lista sem encontrar o RARE nem o botão de EXIT. Bot perdeu-se.")

# ==========================================
# 4. LOOP DE PERSISTÊNCIA (20 MINUTOS MAX)
# ==========================================
def executar_ciclo_completo():
    tempo_limite = 20 * 60  
    inicio_contagem = time.time()
    
    while True:
        tempo_decorrido = time.time() - inicio_contagem
        if tempo_decorrido > tempo_limite:
            abortar_com_erro("Tempo limite operacional da rotina de compra (20 min) excedido.")

        print(f"\n--- INICIANDO TENTATIVA (Tempo decorrido: {int(tempo_decorrido/60)} min) ---")
        
        # A lógica passa automaticamente para a frente ou morre de imediato por erro nas fases
        if fase_1_entrar_servicos():
            if fase_2_abrir_mercado():
                resultado = fase_3_comprar_item()
                
                if resultado == "COMPRADO":
                    print("\n>>> OPERAÇÃO CONCLUÍDA COM SUCESSO! <<<")
                    return True

                elif resultado == "FALHA_CONFIRMACAO":
                    print("\n[REPETIR] Compra não confirmada pelo journal (menu dessincronizado?). "
                          "A tentar de novo...")
                    time.sleep(5.0)
                    continue

                elif resultado == "NAO_ENCONTRADO":
                    print("\n[REPETIR] Item esgotado. Saindo e aguardando 1 minuto...")
                    # Clica no Exit que já está selecionado
                    pydirectinput.press('space')
                    time.sleep(1.5)
                    # Garante que volta ao Cockpit para resetar menus -- mesmos
                    # 3x backspace do caminho "COMPRADO" acima; 1x não chegava
                    # para desfazer Commodities Market -> BUY tab -> lista.
                    for _ in range(3):
                        pydirectinput.press('backspace')
                        time.sleep(0.8)

                    time.sleep(60) # 1 Minuto
                    continue

if __name__ == "__main__":
    inicializar_infraestrutura()

    print("O R2D2 assume os comandos em 1 segundos...")
    time.sleep(1)

    if validar_porao_antes_de_comprar():
        executar_ciclo_completo()
    else:
        print("\n>>> COMPRA SALTADA -- porão já tem o item desta estação. <<<")

    if VISUAL_DEBUG:
        cv2.destroyAllWindows()
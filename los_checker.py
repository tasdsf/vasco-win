#!/usr/bin/env python3
"""
los_checker.py — Line-of-Sight Checker com AUTO-FIT de fase + período.

Deteta o sistema estelar actual pelo Journal do Elite Dangerous e usa
apenas as constantes orbitais e observações desse sistema — nunca mistura
registos/constantes de sistemas diferentes (ex.: Fujin vs Kamitra).

As OBSERVAÇÕES vêm da BD Postgres partilhada na LAN (a mesma que o PC
Linux usa — ver .env.example); se a BD estiver inacessível, cai para as
observações locais do los_calibracao.json como plano B. As CONSTANTES
orbitais vivem no JSON, mas o periodo_carrier_s do JSON passa a ser apenas
o PALPITE INICIAL: o checker ajusta simultaneamente a FASE e o PERÍODO do
carrier contra as observações a cada corrida.

Porquê ajustar o período: uma medição manual do período do carrier com um
erro de 1% desloca a previsão ~17 min por semana. Com dezenas de
observações espalhadas por dias, a regressão encontra o período que
realmente encaixa os dados — e, como muitos períodos vizinhos encaixam
igualmente bem (um 'planalto'), escolhe o CENTRO desse planalto, que é
estável de corrida para corrida (ao contrário do argmax, que salta pelas
bordas). À medida que a BD cresce, o planalto estreita e o ajuste afina-se
sozinho.

Fluxo:
  1. Deteta o sistema actual (StarSystem no Journal mais recente)
  2. Lê sistemas[<sistema>] do los_calibracao.json (constantes/palpite)
  3. Se não houver constantes completas, salta a verificação
  4. Vai buscar as observações do sistema à BD partilhada (fallback: JSON)
  5. Ajusta fase + período por varrimento; usa o período central do planalto
  6. Simula a partir de agora e devolve segundos de espera

API:
    from los_checker import calcular_espera_los
    espera = calcular_espera_los(ed_log_dir=ED_LOG_DIR)
    # 0.0 = livre (ou sistema sem calibração); N > 0 = aguarda N segundos
"""

import math
import json
import os
import glob
from datetime import datetime, timedelta, timezone

PASSO_SIMULACAO        = 10     # segundos
LIMITE_SIMULACAO_HORAS = 24

# --- Auto-fit do período do carrier ---
FIT_VARIACAO   = 0.12   # varre o período do carrier em ±12% à volta do palpite do JSON
FIT_PASSO_FRAC = 0.002  # resolução do varrimento de período: 0.2%
FIT_PASSOS_FASE = 360   # resolução de fase: 1 grau


def _agora_utc_naive():
    """ UTC 'naive' (sem tzinfo), como o antigo datetime.utcnow() mas sem o
        DeprecationWarning. Mantém compatibilidade com os timestamps naive
        das observações. """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ==========================================
# VETORES
# ==========================================
class Vec3:
    def __init__(self, x, y, z):
        self.x = x; self.y = y; self.z = z
    def sub(self, o):    return Vec3(self.x-o.x, self.y-o.y, self.z-o.z)
    def add(self, o):    return Vec3(self.x+o.x, self.y+o.y, self.z+o.z)
    def mult(self, s):   return Vec3(self.x*s,   self.y*s,   self.z*s)
    def dot(self, o):    return self.x*o.x + self.y*o.y + self.z*o.z
    def magnitude(self): return math.sqrt(self.x**2 + self.y**2 + self.z**2)


# ==========================================
# ORBITAL
# ==========================================
class EntidadeOrbital:
    def __init__(self, a, T, M0, epoch):
        self.a = a; self.T = T; self.M0 = M0; self.epoch = epoch

    def pos(self, t):
        dt  = (t - self.epoch).total_seconds()
        ang = (self.M0 + (2 * math.pi / self.T) * dt) % (2 * math.pi)
        return Vec3(self.a * math.cos(ang), self.a * math.sin(ang), 0.0)

    def distancia(self, outro, t):
        p1 = self.pos(t)
        p2 = outro.pos(t)
        return p1.sub(p2).magnitude()


# ==========================================
# OCLUSÃO (ray-sphere)
# ==========================================
def tem_los(p_est, p_car, raio_bloqueio):
    d   = p_car.sub(p_est)
    o   = Vec3(-p_est.x, -p_est.y, -p_est.z)
    ddd = d.dot(d)
    if ddd == 0: return True
    t = o.dot(d) / ddd
    if t < 0 or t > 1: return True
    return p_est.add(d.mult(t)).magnitude() > raio_bloqueio


# ==========================================
# AUTO-FIT: FASE + PERÍODO DO CARRIER
# ==========================================
def _calibrar_fase_periodo(observacoes, cfg, raio_bloqueio,
                           var=FIT_VARIACAO, passo_frac=FIT_PASSO_FRAC,
                           passos_fase=FIT_PASSOS_FASE):
    """
    Ajusta SIMULTANEAMENTE a fase e o período do carrier por varrimento em
    grelha contra as observações. Devolve:
        (epoch, fase_est=0.0, fase_car, periodo_car, score, n, (Tlo, Thi))
    ou None se não houver observações utilizáveis.

    De entre TODOS os períodos que atingem o melhor score (o 'planalto'),
    escolhe o período CENTRAL (mediana) — mais estável de corrida para
    corrida do que o argmax, que salta pelas bordas do planalto.

    Inner loop otimizado: a posição da estação é pré-calculada uma vez (não
    depende de período nem fase), e a rotação por fase usa a fórmula de
    adição de ângulos (sem trigonometria dentro do laço mais interno).
    """
    parsed, ts = [], []
    for o in observacoes:
        est = o.get('estado')
        if est not in ('visivel', 'oclusos'):
            continue
        # Só observações manuais ('linux'/'win') calibram o ajuste -- as
        # automáticas ('auto-linux'/'auto-win') já não são inseridas na BD
        # (ver supercruise_assist.py/leg_state.py), mas registos antigos
        # ainda podiam lá estar. origem ausente = fallback local do JSON,
        # que só contém observações manuais por construção (los_calibrar.py)
        # -- não descartar essas.
        origem = o.get('origem')
        if origem is not None and origem not in ('linux', 'win'):
            continue
        try:
            t = datetime.fromisoformat(o['timestamp_utc'])
        except Exception:
            continue
        parsed.append((t, est == 'visivel'))
        ts.append(t)
    if not parsed:
        return None

    epoch = min(ts)
    a_est = cfg['semi_eixo_estacao_m']; T_est = cfg['periodo_estacao_s']
    a_car = cfg['semi_eixo_carrier_m']; T0 = cfg['periodo_carrier_s']
    raio2 = raio_bloqueio * raio_bloqueio
    n = len(parsed)

    dt = [(t - epoch).total_seconds() for (t, _) in parsed]
    vis = [v for (_, v) in parsed]

    # Posição da estação em cada observação (independente de T e fase)
    w_est = 2.0 * math.pi / T_est
    ex = [a_est * math.cos((w_est * d) % (2 * math.pi)) for d in dt]
    ey = [a_est * math.sin((w_est * d) % (2 * math.pi)) for d in dt]

    # Tabela de cos/sin da fase (calculada uma vez)
    fcos = [math.cos(2 * math.pi * i / passos_fase) for i in range(passos_fase)]
    fsin = [math.sin(2 * math.pi * i / passos_fase) for i in range(passos_fase)]

    resultados = []  # (score, T, fase)
    n_passos = int(round(2 * var / passo_frac)) + 1
    for k in range(n_passos):
        frac = -var + passo_frac * k
        T = T0 * (1.0 + frac)
        w = 2.0 * math.pi / T
        # Ângulo base do carrier (fase 0) em cada observação, já escalado por a_car
        ccos = [a_car * math.cos((w * d) % (2 * math.pi)) for d in dt]
        csin = [a_car * math.sin((w * d) % (2 * math.pi)) for d in dt]

        melhor_s, melhor_f = -1, 0.0
        for i in range(passos_fase):
            cf = fcos[i]; sf = fsin[i]
            s = 0
            for j in range(n):
                # Carrier: roda o ângulo base pela fase (adição de ângulos)
                cx = ccos[j] * cf - csin[j] * sf
                cy = csin[j] * cf + ccos[j] * sf
                # tem_los inline (raio-esfera, planeta na origem)
                dx = cx - ex[j]; dy = cy - ey[j]
                ddd = dx * dx + dy * dy
                if ddd == 0.0:
                    livre = True
                else:
                    tt = (-ex[j] * dx - ey[j] * dy) / ddd
                    if tt < 0.0 or tt > 1.0:
                        livre = True
                    else:
                        px = ex[j] + dx * tt; py = ey[j] + dy * tt
                        livre = (px * px + py * py) > raio2
                if livre == vis[j]:
                    s += 1
            if s > melhor_s:
                melhor_s, melhor_f = s, 2 * math.pi * i / passos_fase
        resultados.append((melhor_s, T, melhor_f))

    best = max(r[0] for r in resultados)
    planalto = sorted(((T, f) for (s, T, f) in resultados if s == best), key=lambda x: x[0])
    Ts = [T for (T, f) in planalto]
    T_med = Ts[len(Ts) // 2]
    fase_med = next(f for (T, f) in planalto if T == T_med)
    return epoch, 0.0, fase_med, T_med, best, n, (Ts[0], Ts[-1])


# ==========================================
# DETEÇÃO DO SISTEMA ACTUAL (JOURNAL)
# ==========================================
def obter_sistema_atual(ed_log_dir):
    """ Lê o Journal mais recente e devolve o nome do StarSystem actual.
        Eventos usados só disparam DEPOIS de já estarmos no sistema
        (nunca o destino de um salto ainda a decorrer). """
    try:
        if not ed_log_dir or not os.path.exists(ed_log_dir):
            return None
        lista_logs = glob.glob(os.path.join(ed_log_dir, "Journal.*.log"))
        if not lista_logs:
            return None

        ultimo_log = max(lista_logs, key=os.path.getmtime)
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


# ==========================================
# OBSERVAÇÕES — BD PARTILHADA (fallback: JSON local)
# ==========================================
def _obter_observacoes_db(script_dir, sistema):
    """ Vai buscar as observações do sistema à BD Postgres partilhada
        (configurada no .env — ver .env.example). Devolve lista de dicts
        no MESMO formato do JSON ({'timestamp_utc': iso, 'estado': ...}),
        com timestamps convertidos para UTC naive. Devolve None se a BD não
        estiver acessível/configurada — o chamador cai para o JSON local. """
    try:
        from dotenv import load_dotenv
        import psycopg2
    except ImportError:
        return None

    load_dotenv(os.path.join(script_dir, ".env"))
    host = os.environ.get("R2D2_DB_HOST")
    password = os.environ.get("R2D2_DB_PASSWORD")
    if not host or not password:
        return None

    try:
        conn = psycopg2.connect(
            host=host,
            port=os.environ.get("R2D2_DB_PORT", "5432"),
            dbname=os.environ.get("R2D2_DB_NAME", "ED"),
            user=os.environ.get("R2D2_DB_USER", "r2d2"),
            password=password,
            connect_timeout=4,
        )
    except Exception as e:
        print(f"[LOS] BD partilhada inacessível ({e.__class__.__name__}) — a usar observações locais.")
        return None

    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "SELECT timestamp_utc, estado, nota, origem FROM los_observacoes "
                "WHERE sistema = %s ORDER BY timestamp_utc;",
                (sistema,),
            )
            linhas = cur.fetchall()
    finally:
        conn.close()

    observacoes = []
    for ts, estado, nota, origem in linhas:
        if ts.tzinfo is not None:
            ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
        observacoes.append({
            "timestamp_utc": ts.strftime("%Y-%m-%dT%H:%M:%S"),
            "estado": estado,
            "nota": nota,
            "origem": origem,
        })
    return observacoes


# ==========================================
# CARREGAR CALIBRAÇÃO DO SISTEMA
# ==========================================
def _carregar_sistema(script_dir, sistema):
    """ Devolve o dict de configuração do sistema pedido, ou None se não
        existir ou tiver constantes orbitais por preencher (nesse caso NUNCA
        usamos as constantes de outro sistema — é melhor saltar a verificação). """
    caminho = os.path.join(script_dir, 'los_calibracao.json')
    if not os.path.exists(caminho):
        print("[LOS] Sem los_calibracao.json.")
        return None

    try:
        with open(caminho, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[LOS] Falha a ler los_calibracao.json: {e}")
        return None

    cfg = data.get('sistemas', {}).get(sistema)
    if not cfg:
        return None

    obrigatorios = ['raio_planeta_m', 'semi_eixo_estacao_m', 'semi_eixo_carrier_m',
                     'periodo_estacao_s', 'periodo_carrier_s']
    if any(cfg.get(k) is None for k in obrigatorios):
        return None

    return cfg


# ==========================================
# SIMULAÇÃO
# ==========================================
def _simular(estacao, carrier, agora, raio_bloqueio):
    if tem_los(estacao.pos(agora), carrier.pos(agora), raio_bloqueio):
        return 0.0

    passo  = timedelta(seconds=PASSO_SIMULACAO)
    limite = agora + timedelta(hours=LIMITE_SIMULACAO_HORAS)
    t      = agora

    while t < limite:
        t += passo
        if tem_los(estacao.pos(t), carrier.pos(t), raio_bloqueio):
            return (t - agora).total_seconds()

    return LIMITE_SIMULACAO_HORAS * 3600.0


# ==========================================
# API PÚBLICA
# ==========================================
def calcular_espera_los(ed_log_dir=None, sistema=None) -> float:
    """
    Retorna segundos de espera até a estação e o carrier terem LOS livre,
    NO SISTEMA ACTUAL (detetado pelo Journal, a menos que 'sistema' seja
    passado explicitamente). 0.0 = pode descolar imediatamente, ou não há
    calibração para este sistema (nesse caso não bloqueia, só não verifica).
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))

    if sistema is None:
        sistema = obter_sistema_atual(ed_log_dir)

    if not sistema:
        print("[LOS] Sistema actual desconhecido (sem Journal/StarSystem legível) — a saltar verificação.")
        return 0.0

    cfg = _carregar_sistema(script_dir, sistema)
    if cfg is None:
        print(f"[LOS] Sem constantes orbitais calibradas para o sistema '{sistema}' — "
              f"a saltar verificação (não vamos usar os números de outro sistema).")
        return 0.0

    raio_bloqueio = cfg['raio_planeta_m'] + cfg.get('margem_atmosfera_m', 50000)

    # Observações: primeiro a BD partilhada, depois o JSON local como plano B
    observacoes = _obter_observacoes_db(script_dir, sistema)
    if observacoes is None:
        observacoes = cfg.get('observacoes', [])
        if observacoes:
            print(f"[LOS] A usar {len(observacoes)} observações locais do JSON (BD indisponível).")
    else:
        print(f"[LOS] {len(observacoes)} observações de '{sistema}' carregadas da BD partilhada.")

    periodo_car = cfg['periodo_carrier_s']  # palpite inicial (JSON)

    if observacoes:
        fit = _calibrar_fase_periodo(observacoes, cfg, raio_bloqueio)
        if fit is not None:
            epoch, fase_est, fase_car, periodo_car, score, nobs, (Tlo, Thi) = fit
            T0 = cfg['periodo_carrier_s']
            desvio = (periodo_car - T0) / T0 * 100.0
            banda = (Thi - Tlo) / T0 * 100.0
            print(f"[LOS] Auto-fit fase+periodo: {score}/{nobs} obs correctas | "
                  f"periodo={periodo_car:.0f}s ({desvio:+.2f}% vs constante JSON) | "
                  f"fase={math.degrees(fase_car):.1f} graus")
            print(f"[LOS] (planalto de periodos equivalentes: largura {banda:.2f}% -> "
                  f"incerteza; estreita com mais observacoes)")
        else:
            print("[LOS] Observações ilegíveis — a assumir fase_carrier=180° (pior caso).")
            epoch, fase_car = _agora_utc_naive(), math.pi
    else:
        print(f"[LOS] Sistema '{sistema}': sem observações ainda — a assumir fase_carrier=180° (pior caso).")
        epoch, fase_car = _agora_utc_naive(), math.pi

    agora = _agora_utc_naive()
    estacao = EntidadeOrbital(cfg['semi_eixo_estacao_m'], cfg['periodo_estacao_s'], 0.0, epoch)
    carrier = EntidadeOrbital(cfg['semi_eixo_carrier_m'], periodo_car, fase_car, epoch)

    return _simular(estacao, carrier, agora, raio_bloqueio)


# ==========================================
# STANDALONE
# ==========================================
if __name__ == "__main__":
    ED_LOG_DIR = os.path.expanduser('~') + r"\Saved Games\Frontier Developments\Elite Dangerous"
    agora_utc = datetime.now(timezone.utc)

    sistema_atual = obter_sistema_atual(ED_LOG_DIR)

    print("=" * 54)
    print(f"  LOS CHECKER — Sistema: {sistema_atual or 'DESCONHECIDO'}")
    print("=" * 54)
    print(f"  UTC actual:      {agora_utc.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Portugal:        {(agora_utc + timedelta(hours=1)).strftime('%H:%M:%S')}")
    print()

    espera = calcular_espera_los(ed_log_dir=ED_LOG_DIR, sistema=sistema_atual)

    if espera == 0.0:
        print("🟢 LINHA DE VISÃO LIMPA (ou sistema sem calibração) — podes descolar imediatamente.")
    else:
        h, resto = divmod(int(espera), 3600)
        m, s     = divmod(resto, 60)
        partida_utc = agora_utc + timedelta(seconds=espera)
        partida_pt  = partida_utc + timedelta(hours=1)
        print(f"🔴 BLOQUEIO DETETADO — planeta no meio.")
        print(f"⏳ Espera:         {h}h {m}m {s}s")
        print(f"⏰ Partida UTC:    {partida_utc.strftime('%H:%M:%S')}")
        print(f"⏰ Partida PT:     {partida_pt.strftime('%H:%M:%S')}")
        print()
        print(f"Para adicionar observações a este sistema: corre los_calibrar.py")

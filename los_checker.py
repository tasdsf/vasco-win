#!/usr/bin/env python3
"""
los_checker.py — Line-of-Sight Checker com calibração automática, por sistema.

Deteta o sistema estelar actual pelo Journal do Elite Dangerous e usa
apenas as constantes orbitais e observações desse sistema — nunca mistura
registos/constantes de sistemas diferentes (ex.: Fujin vs Kamitra).

Fluxo:
  1. Deteta o sistema actual (StarSystem no Journal mais recente)
  2. Lê sistemas[<sistema>] do los_calibracao.json
  3. Se não houver constantes completas para esse sistema, salta a
     verificação (não usa as constantes de outro sistema por engano)
  4. Ajusta fase_carrier por regressão a partir de observacoes[]
  5. Simula a partir de agora e devolve segundos de espera

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
# REGRESSÃO — ajusta fase_carrier
# ==========================================
def _estado_modelo(fase_est, fase_car, epoch, t_obs, semi_eixo_estacao, periodo_estacao,
                    semi_eixo_carrier, periodo_carrier, raio_bloqueio):
    """Devolve True se o modelo prevê visibilidade em t_obs."""
    est = EntidadeOrbital(semi_eixo_estacao, periodo_estacao, fase_est, epoch)
    car = EntidadeOrbital(semi_eixo_carrier, periodo_carrier, fase_car, epoch)
    return tem_los(est.pos(t_obs), car.pos(t_obs), raio_bloqueio)


def _score(fase_car, observacoes, epoch, semi_eixo_estacao, periodo_estacao,
           semi_eixo_carrier, periodo_carrier, raio_bloqueio):
    """
    Conta quantas observações o modelo acerta.
    Observações com estado 'visivel' devem ter LOS=True,
    'oclusos' devem ter LOS=False.
    """
    acertos = 0
    for obs in observacoes:
        try:
            t = datetime.fromisoformat(obs['timestamp_utc'])
            estado = obs['estado']
            if estado not in ('visivel', 'oclusos'):
                continue
            previsto = _estado_modelo(0.0, fase_car, epoch, t, semi_eixo_estacao, periodo_estacao,
                                       semi_eixo_carrier, periodo_carrier, raio_bloqueio)
            real = (estado == 'visivel')
            if previsto == real:
                acertos += 1
        except Exception:
            continue
    return acertos


def _calibrar_fase(observacoes, semi_eixo_estacao, periodo_estacao,
                    semi_eixo_carrier, periodo_carrier, raio_bloqueio):
    """
    Varre fase_carrier de 0 a 2π em passos de 1°,
    devolve a fase que maximiza o score.
    Usa a observação mais antiga como epoch.
    """
    if not observacoes:
        return None, 0.0, math.pi

    timestamps = []
    for obs in observacoes:
        try:
            timestamps.append(datetime.fromisoformat(obs['timestamp_utc']))
        except Exception:
            continue
    if not timestamps:
        return None, 0.0, math.pi

    epoch = min(timestamps)
    obs_validas = [o for o in observacoes
                   if o.get('estado') in ('visivel', 'oclusos')]

    if not obs_validas:
        return epoch, 0.0, math.pi

    melhor_score  = -1
    melhor_fase   = math.pi
    passos        = 360  # resolução de 1°

    for i in range(passos):
        fase_car = (2 * math.pi * i) / passos
        s = _score(fase_car, obs_validas, epoch, semi_eixo_estacao, periodo_estacao,
                   semi_eixo_carrier, periodo_carrier, raio_bloqueio)
        if s > melhor_score:
            melhor_score = s
            melhor_fase  = fase_car

    total = len(obs_validas)
    print(f"[LOS] Regressão: {melhor_score}/{total} observações correctas "
          f"com fase_carrier={math.degrees(melhor_fase):.1f}°")

    return epoch, 0.0, melhor_fase


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
        return None  # constantes ainda por preencher para este sistema

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
    observacoes = cfg.get('observacoes', [])

    if observacoes:
        epoch, fase_est, fase_car = _calibrar_fase(
            observacoes, cfg['semi_eixo_estacao_m'], cfg['periodo_estacao_s'],
            cfg['semi_eixo_carrier_m'], cfg['periodo_carrier_s'], raio_bloqueio)
        if epoch is None:
            epoch = datetime.utcnow()
    else:
        print(f"[LOS] Sistema '{sistema}': sem observações ainda — a assumir fase_carrier=180° (pior caso).")
        epoch, fase_est, fase_car = datetime.utcnow(), 0.0, math.pi

    agora = datetime.utcnow()
    estacao = EntidadeOrbital(cfg['semi_eixo_estacao_m'], cfg['periodo_estacao_s'], fase_est, epoch)
    carrier = EntidadeOrbital(cfg['semi_eixo_carrier_m'], cfg['periodo_carrier_s'], fase_car, epoch)

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

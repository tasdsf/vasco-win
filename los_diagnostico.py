#!/usr/bin/env python3
"""
los_diagnostico.py — Diagnóstico do modelo LOS contra a BD partilhada.

Motivação: o los_checker ajusta SÓ a fase do carrier e confia no
periodo_carrier_s medido à mão. Um erro pequeno no período acumula com os
dias e o modelo pode acertar as observações agrupadas do passado e falhar
o presente (foi o que aconteceu: "linha limpa" com o carrier ocluso).

Este script varre fase × período do carrier em grelha, e reporta:
  1. o melhor ajuste com o período FIXO atual (como o checker faz hoje)
  2. o melhor ajuste deixando o período variar (janela larga ±20%)
  3. um perfil dos 5 melhores períodos (para detetar alias/ambiguidade)
  4. quais observações cada modelo falha (com nota)
  5. o estado previsto para AGORA por ambos
  6. as janelas de oclusão das próximas 48h segundo o modelo melhorado

DETEÇÃO DE FRONTEIRA: se o melhor período cair no bordo da janela de busca,
avisa que a janela é curta e que o verdadeiro ótimo pode estar mais além.

Só lê (BD e los_calibracao.json). Não escreve nada em lado nenhum.

Uso: python los_diagnostico.py
"""

import math
import os
import sys
from datetime import datetime, timedelta, timezone

from los_checker import (EntidadeOrbital, tem_los, _obter_observacoes_db,
                         _carregar_sistema, obter_sistema_atual)

ED_LOG_DIR = os.path.expanduser('~') + r"\Saved Games\Frontier Developments\Elite Dangerous"

PASSOS_FASE = 360          # resolução de 1 grau
VARIACAO_PERIODO = 0.20    # ±20% à volta do periodo_carrier_s atual (janela larga)
PASSOS_PERIODO = 401       # 401 passos sobre ±20% -> resolução de ~0.1%


def _agora_utc_naive():
    # datetime.utcnow() está deprecado; isto dá o mesmo (UTC naive) sem o aviso
    return datetime.now(timezone.utc).replace(tzinfo=None)


def avaliar(fase_car, periodo_car, observacoes, epoch, cfg, raio_bloqueio):
    """ Devolve (acertos, lista_de_falhas) deste modelo contra as observações. """
    est = EntidadeOrbital(cfg['semi_eixo_estacao_m'], cfg['periodo_estacao_s'], 0.0, epoch)
    car = EntidadeOrbital(cfg['semi_eixo_carrier_m'], periodo_car, fase_car, epoch)
    acertos, falhas = 0, []
    for o in observacoes:
        try:
            t = datetime.fromisoformat(o['timestamp_utc'])
            real_visivel = (o['estado'] == 'visivel')
        except Exception:
            continue
        previsto_visivel = tem_los(est.pos(t), car.pos(t), raio_bloqueio)
        if previsto_visivel == real_visivel:
            acertos += 1
        else:
            falhas.append(o)
    return acertos, falhas


def melhor_fase(T, observacoes, epoch, cfg, raio_bloqueio):
    """ Para um período T fixo, devolve (melhor_acertos, melhor_fase, falhas). """
    melhor = (-1, math.pi, [])
    for i in range(PASSOS_FASE):
        fase = (2 * math.pi * i) / PASSOS_FASE
        acertos, falhas = avaliar(fase, T, observacoes, epoch, cfg, raio_bloqueio)
        if acertos > melhor[0]:
            melhor = (acertos, fase, falhas)
    return melhor


def janelas_48h(fase_car, periodo_car, epoch, cfg, raio_bloqueio, agora):
    est = EntidadeOrbital(cfg['semi_eixo_estacao_m'], cfg['periodo_estacao_s'], 0.0, epoch)
    car = EntidadeOrbital(cfg['semi_eixo_carrier_m'], periodo_car, fase_car, epoch)
    janelas, dentro, inicio = [], False, None
    t = agora
    fim = agora + timedelta(hours=48)
    while t <= fim:
        ocluso = not tem_los(est.pos(t), car.pos(t), raio_bloqueio)
        if ocluso and not dentro:
            dentro, inicio = True, t
        elif not ocluso and dentro:
            dentro = False
            janelas.append((inicio, t))
        t += timedelta(seconds=60)
    if dentro:
        janelas.append((inicio, fim))
    return janelas


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sistema = obter_sistema_atual(ED_LOG_DIR) or "Fujin"
    print(f"[DIAG] Sistema: {sistema}")

    cfg = _carregar_sistema(script_dir, sistema)
    if cfg is None:
        print("[DIAG] Sem constantes orbitais para este sistema no los_calibracao.json.")
        sys.exit(1)

    observacoes = _obter_observacoes_db(script_dir, sistema)
    if not observacoes:
        print("[DIAG] Sem observações da BD (BD inacessível ou vazia). Diagnóstico precisa da BD.")
        sys.exit(1)
    n = len(observacoes)
    print(f"[DIAG] {n} observações carregadas da BD.")

    raio_bloqueio = cfg['raio_planeta_m'] + cfg.get('margem_atmosfera_m', 50000)
    timestamps = [datetime.fromisoformat(o['timestamp_utc']) for o in observacoes]
    epoch = min(timestamps)
    T0 = cfg['periodo_carrier_s']
    agora = _agora_utc_naive()

    # --- 1. Modelo atual (período fixo, só fase — o que o los_checker faz) ---
    ac_fixo, fase_fixo, falhas_fixo = melhor_fase(T0, observacoes, epoch, cfg, raio_bloqueio)
    print()
    print(f"[DIAG] MODELO ATUAL (período fixo {T0:.0f}s):")
    print(f"[DIAG]   {ac_fixo}/{n} corretas | fase={math.degrees(fase_fixo):.1f}°")

    # --- 2. Varrimento de período (janela larga) ---
    Tmin = T0 * (1 - VARIACAO_PERIODO)
    Tmax = T0 * (1 + VARIACAO_PERIODO)
    resultados = []  # (acertos, fase, T)
    for k in range(PASSOS_PERIODO):
        T = Tmin + (Tmax - Tmin) * k / (PASSOS_PERIODO - 1)
        ac, fase, _ = melhor_fase(T, observacoes, epoch, cfg, raio_bloqueio)
        resultados.append((ac, fase, T))

    ac_livre, fase_livre, T_livre = max(resultados, key=lambda r: r[0])
    _, _, falhas_livre = melhor_fase(T_livre, observacoes, epoch, cfg, raio_bloqueio)
    desvio = (T_livre - T0) / T0 * 100
    print()
    print(f"[DIAG] MODELO COM PERÍODO LIVRE (janela ±{VARIACAO_PERIODO*100:.0f}%):")
    print(f"[DIAG]   {ac_livre}/{n} corretas | fase={math.degrees(fase_livre):.1f}° | "
          f"período={T_livre:.0f}s ({desvio:+.2f}% vs atual)")

    # --- Deteção de fronteira: o ótimo caiu no bordo da janela? ---
    margem = (Tmax - Tmin) / (PASSOS_PERIODO - 1) * 2  # 2 passos de tolerância
    if T_livre <= Tmin + margem or T_livre >= Tmax - margem:
        print(f"[DIAG]   ⚠️  ATENÇÃO: o melhor período está no BORDO da janela de busca "
              f"({Tmin:.0f}..{Tmax:.0f}s).")
        print(f"[DIAG]   O verdadeiro ótimo pode estar mais além — alarga VARIACAO_PERIODO e volta a correr.")

    # --- 3. Perfil dos 5 melhores períodos (detetar alias/ambiguidade) ---
    print()
    print("[DIAG] Top-5 períodos por nº de acertos (para ver se há um ótimo claro ou ambiguidade):")
    top = sorted(resultados, key=lambda r: (-r[0], abs(r[2] - T0)))[:5]
    for ac, fase, T in top:
        print(f"[DIAG]   {ac}/{n} | período={T:.0f}s ({(T-T0)/T0*100:+.2f}%) | fase={math.degrees(fase):.1f}°")

    # --- 4. Falhas de cada modelo ---
    for nome, falhas in (("ATUAL", falhas_fixo), ("PERÍODO LIVRE", falhas_livre)):
        print()
        print(f"[DIAG] Observações que o modelo {nome} falha ({len(falhas)}):")
        for o in falhas:
            print(f"[DIAG]   {o['timestamp_utc']} | real={o['estado']} | nota={o.get('nota') or '-'}")

    # --- 5. Estado previsto para AGORA ---
    print()
    for nome, fase, T in (("ATUAL", fase_fixo, T0), ("PERÍODO LIVRE", fase_livre, T_livre)):
        est = EntidadeOrbital(cfg['semi_eixo_estacao_m'], cfg['periodo_estacao_s'], 0.0, epoch)
        car = EntidadeOrbital(cfg['semi_eixo_carrier_m'], T, fase, epoch)
        visivel = tem_los(est.pos(agora), car.pos(agora), raio_bloqueio)
        print(f"[DIAG] AGORA ({agora.strftime('%H:%M:%S')} UTC) segundo o modelo {nome}: "
              f"{'VISÍVEL' if visivel else 'OCLUSO'}")

    # --- 6. Próximas janelas de oclusão (modelo melhorado) ---
    print()
    print("[DIAG] Janelas de oclusão nas próximas 48h (modelo com período livre, hora UTC):")
    janelas = janelas_48h(fase_livre, T_livre, epoch, cfg, raio_bloqueio, agora)
    if not janelas:
        print("[DIAG]   (nenhuma nas próximas 48h)")
    for ini, fim in janelas:
        dur = (fim - ini).total_seconds() / 3600
        print(f"[DIAG]   {ini.strftime('%m-%d %H:%M')} -> {fim.strftime('%m-%d %H:%M')}  (~{dur:.1f}h)")

    print()
    if ac_livre > ac_fixo:
        print(f"[DIAG] CONCLUSÃO: o período livre explica melhor os dados ({ac_livre} vs {ac_fixo}).")
        print(f"[DIAG] Próximo passo: se o período NÃO estiver no bordo, atualizar periodo_carrier_s")
        print(f"[DIAG] para {T_livre:.0f} no los_calibracao.json — ou integrar o ajuste de período")
        print(f"[DIAG] no próprio los_checker (fit de 2 parâmetros: fase + período).")
    else:
        print("[DIAG] CONCLUSÃO: o período livre não melhorou — o problema estará noutro lado")
        print("[DIAG] (inclinação 3D das órbitas? período da estação? margem do raio?).")

    # ASSUNÇÕES: órbitas circulares coplanares (herdadas do los_checker);
    # período da estação e semi-eixos tomados como corretos; só o período
    # do carrier é posto em causa neste diagnóstico.


if __name__ == "__main__":
    main()

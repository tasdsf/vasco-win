#!/usr/bin/env python3
"""
capturar_orbitas.py - Sessão dedicada de captura de dados orbitais.

Motivação: los_checker.py infere as órbitas de estação/carrier por
regressão sobre observações BINÁRIAS (visível/ocluso) acumuladas ao longo
de meses -- método barato (não exige atenção dedicada) mas de baixa
densidade de informação; mesmo com auto-fit de fase+período, o modelo
atual só acerta ~82% (70/85) das observações manuais existentes (ver
diagnóstico desta conversa, 2026-09-18).

Este script troca esse método por MEDIÇÃO DIRETA E DENSA: com a nave
parada num ponto fixo (o utilizador posiciona-a acima do plano orbital,
"acima do planeta"), alterna o alvo de navegação entre CARRIER e ESTAÇÃO
a um intervalo fixo, e regista uma captura de ecrã completa a cada troca
-- o painel de navegação/HUD mostra a distância a cada corpo no momento
exato da captura. Cada screenshot + timestamp UTC fica registado num
manifesto CSV (logs/orbitas/manifest.csv) para processamento posterior
(leitura manual das distâncias, ou OCR/template de dígitos a construir
depois -- este script não faz OCR, só regista a matéria-prima).

NÃO correr ao mesmo tempo que vasco.py/supercruise_assist.py -- ambos
disputariam o alvo de navegação e o foco do painel esquerdo.

Reaproveita select_target.py::marcar_destino_dinamico() via
VASCO_FORCE_TARGET (mesmo mecanismo já usado por supercruise_assist.py
para o regresso por oclusão de LOS) -- não reinventa o scan/confirmação/
lock, que já está validado em produção.

Uso: python capturar_orbitas.py [duracao_horas]
    duracao_horas (opcional) -- ao fim deste tempo o script para sozinho.
    Sem argumento, corre indefinidamente até Ctrl+C.
"""

import os
import sys
import csv
import time
import logging
from datetime import datetime, timezone

import cv2
import mss
import numpy as np

import select_target as st

# ==========================================
# CONFIGURAÇÃO
# ==========================================
# Intervalo entre trocas de alvo -- cada ciclo completo (carrier + estação)
# cobre 2x este valor. Escolhido para dar densidade alta face aos períodos
# orbitais envolvidos (~12h estação, ~19h carrier segundo o último auto-fit)
# sem sobrecarregar o jogo com scans de painel constantes: a 90s, uma volta
# orbital do carrier (o corpo mais lento) já rende ~760 amostras -- muito
# acima do necessário para um ajuste de curva com 2-3 parâmetros por corpo.
INTERVALO_S = 90

DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))
PASTA_ORBITAS = os.path.join(DIRETORIO_ATUAL, "logs", "orbitas")
MANIFESTO = os.path.join(PASTA_ORBITAS, "manifest.csv")

_logger = logging.getLogger("capturar_orbitas")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    os.makedirs(os.path.join(DIRETORIO_ATUAL, "logs"), exist_ok=True)
    _fh = logging.FileHandler(os.path.join(DIRETORIO_ATUAL, "logs", "r2d2_combined.log"), encoding='utf-8')
    _fh.setFormatter(logging.Formatter('%(asctime)s - [CAPTURAR_ORBITAS] - %(levelname)s - %(message)s'))
    _logger.addHandler(_fh)
    _logger.propagate = False


def capturar_screenshot(alvo):
    """ Grava o ecrã inteiro do jogo (não só um recorte -- sem coordenadas
    calibradas para o bloco exato de distância no HUD, o ecrã inteiro
    garante que a informação fica lá para processar depois, mesmo que o
    recorte certo só venha a ser decidido mais tarde) e regista uma linha
    no manifesto CSV. Devolve o caminho do ficheiro gravado. """
    os.makedirs(PASTA_ORBITAS, exist_ok=True)
    agora = datetime.now(timezone.utc)
    nome_ficheiro = f"{agora.strftime('%Y%m%dT%H%M%SZ')}_{alvo}.png"
    caminho = os.path.join(PASTA_ORBITAS, nome_ficheiro)

    with mss.mss() as sct:
        try:
            monitor_jogo = sct.monitors[1]
        except Exception:
            monitor_jogo = sct.monitors[0]
        img_bgra = np.array(sct.grab(monitor_jogo))
        cv2.imwrite(caminho, cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR))

    ficheiro_novo = not os.path.exists(MANIFESTO)
    with open(MANIFESTO, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if ficheiro_novo:
            writer.writerow(["timestamp_utc", "alvo", "screenshot"])
        writer.writerow([agora.strftime("%Y-%m-%dT%H:%M:%S"), alvo, nome_ficheiro])

    print(f"[CAPTURA] {alvo.upper()} @ {agora.strftime('%H:%M:%S')} UTC -> {nome_ficheiro}")
    _logger.info(f"Captura {alvo} -> {nome_ficheiro}")
    return caminho


def main():
    duracao_horas = None
    if len(sys.argv) > 1:
        try:
            duracao_horas = float(sys.argv[1])
        except ValueError:
            print(f"[AVISO] Argumento de duração inválido ('{sys.argv[1]}') -- a ignorar, corre indefinidamente.")

    st.inicializar_infraestrutura()

    print("=" * 60)
    print("  R2D2 - CAPTURA DE ÓRBITAS (carrier/estação alternados)")
    print("=" * 60)
    print(f"  Intervalo entre trocas de alvo: {INTERVALO_S}s")
    print(f"  Duração: {'indefinida (Ctrl+C para parar)' if duracao_horas is None else f'{duracao_horas:.1f}h'}")
    print(f"  Screenshots + manifesto em: {PASTA_ORBITAS}")
    print("=" * 60)
    print("\nO R2D2 assume os comandos em 3 segundos -- confirma que a nave")
    print("está parada e livre de obstáculos antes de continuar...")
    time.sleep(3)

    inicio = time.time()
    limite = (inicio + duracao_horas * 3600) if duracao_horas else None
    alvo_atual = "carrier"
    ciclo = 0

    while limite is None or time.time() < limite:
        ciclo += 1
        decorrido_h = (time.time() - inicio) / 3600
        print(f"\n--- Ciclo {ciclo} ({decorrido_h:.2f}h decorridas) -- alvo: {alvo_atual.upper()} ---")

        os.environ["VASCO_FORCE_TARGET"] = alvo_atual
        try:
            st.marcar_destino_dinamico()
        except SystemExit:
            # marcar_destino_dinamico() aborta (sys.exit) se o scan falhar
            # (painel não abriu, alvo não encontrado, etc.) -- numa sessão
            # de horas isto não pode matar a captura inteira, só salta este
            # ciclo e tenta o próximo like normal. abortar_com_erro() já
            # fez o seu próprio backspace de recuperação antes de sair.
            print(f"[AVISO] Falha ao marcar '{alvo_atual}' neste ciclo -- a saltar (sem captura).")
            _logger.warning(f"Falha ao marcar '{alvo_atual}' no ciclo {ciclo} -- captura saltada.")
        else:
            time.sleep(1.5)  # deixa o HUD assentar no novo alvo antes de fotografar
            capturar_screenshot(alvo_atual)

        alvo_atual = "station" if alvo_atual == "carrier" else "carrier"
        time.sleep(INTERVALO_S)

    print(f"\n[FIM] Duração de {duracao_horas:.1f}h atingida. {ciclo} ciclos completados.")
    print(f"[FIM] Manifesto: {MANIFESTO}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[PARADO] Captura interrompida pelo utilizador (Ctrl+C).")
        print(f"[PARADO] Manifesto até agora: {MANIFESTO}")

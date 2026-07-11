#!/usr/bin/env python3
"""
check_station_match.py - Diagnostico rapido de match ao vivo
Mostra a percentagem de match de STATION.png, STATION1.png e
FLEET_CARRIER_NAME.png contra o MONITOR_PANEL, em tempo real, sem enviar
nenhuma tecla. Fecha com 'q'.
"""
import os
import time
import cv2
import mss
import numpy as np
import keyboard

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_imagens = os.path.join(diretorio_atual, '..\images')

MONITOR_PANEL = {"top": 200, "left": 50, "width": 1000, "height": 1200}

templates = {}
for chave, nome_arq in [("STATION", "STATION.png"), ("STATION1", "STATION1.png"), ("CARRIER", "FLEET_CARRIER_NAME.png")]:
    caminho = os.path.join(pasta_imagens, nome_arq)
    img = cv2.imread(caminho, cv2.IMREAD_COLOR)
    if img is None:
        print(f"[ERRO] Nao encontrei {caminho}")
    templates[chave] = img

print("A monitorizar match ao vivo. Abre o painel de navegacao no jogo.")
print("Pressiona 'q' para sair.\n")

with mss.mss() as sct:
    while True:
        if keyboard.is_pressed('q'):
            break

        img_bgra = np.array(sct.grab(MONITOR_PANEL))
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)

        linha = []
        for nome, template in templates.items():
            if template is None:
                continue
            resultado = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(resultado)
            linha.append(f"{nome}: {max_val:.3f}")

        print("\r" + " | ".join(linha) + "   ", end="", flush=True)
        time.sleep(0.2)

print("\n\nEncerrado.")

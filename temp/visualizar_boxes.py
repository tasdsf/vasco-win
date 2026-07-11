import os
import time
import cv2
import mss
import numpy as np

# Configurações
pasta_imagens = r'C:\Users\tasds\vasco-r2d2\images'
template_name = 'STATION.png'
nome_monitor = 1  # Monitor principal
threshold = 0.75

# Carregar template
caminho = os.path.join(pasta_imagens, template_name)
try:
    template = cv2.imread(caminho, cv2.IMREAD_COLOR)
    print(f"[INFO] Template carregado: {caminho}")
except Exception as e:
    print(f"[ERRO] {e}")
    input("Pressione ENTER para sair...")
    exit(1)

print(f"[INFO] Template size: {template.shape[1]}x{template.shape[0]}")

# Setup mss
monitors = mss.monitors()
monitor = monitors[nome_monitor]

# Loop de procura
print("\n[INFO] Procurando... Pressione CTRL para parar\n")

cont = 0
while True:
    cont += 1
    try:
        screen = sct.grab(monitor)
    except:
        screen = sct.grab(monitor)
    
    # Converter
    img = cv2.cvtColor(screen, cv2.COLOR_RGB2BGR)
    
    # Match
    resultado = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(resultado)
    
    if max_val >= threshold:
        h, w = template.shape[:2]
        cv2.rectangle(img, max_loc, (max_loc[0] + w, max_loc[1] + h), (0, 255, 0), 3)
        cv2.putText(img, f'{template_name} - {round(max_val*100)}%', (5, 25), 1, 0.7, (255, 255, 255), 2)
        print(f"[LOG] Encontrado: {round(max_val*100)}%")
    else:
        print(f"[LOG] Tentativa {cont}")
    
    time.sleep(0.15)

print("\n[INFO] --- FIM ---")
input("Pressione ENTER...")

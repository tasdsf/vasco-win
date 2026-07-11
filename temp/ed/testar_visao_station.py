import os
import cv2
import mss
import numpy as np

# A área original que o teu script usa
MONITOR_PANEL = {"top": 200, "left": 50, "width": 1000, "height": 1200}
THRESHOLD_ORIGINAL = 0.85 

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_imagens = os.path.join(diretorio_atual, 'images')
caminho_template = os.path.join(pasta_imagens, 'STATION.png')

print(f"[SISTEMA] A iniciar Ocular de Diagnóstico Multi-Monitor...")

try:
    template = cv2.imread(caminho_template, cv2.IMREAD_COLOR)
    h_temp, w_temp = template.shape[:2]
except Exception as e:
    print(f"[ERRO] Não encontrei a STATION.png: {e}")
    exit()

with mss.mss() as sct:
    # 1. Imprimir a topologia dos monitores para debug
    print("\n[TOPOLOGIA DE MONITORES DETETADA]")
    for i, m in enumerate(sct.monitors):
        if i == 0:
            print(f"Monitor {i} (Tela Virtual Global) : {m}")
        else:
            print(f"Monitor {i} (Ecrã Físico)         : {m}")
    
    # 2. Ancorar ao Monitor Principal (Índice 1 no mss)
    monitor_jogo = sct.monitors[1] 
    
    # 3. Recalcular a área somando o "offset" do monitor
    area_real = {
        "top": monitor_jogo["top"] + MONITOR_PANEL["top"],
        "left": monitor_jogo["left"] + MONITOR_PANEL["left"],
        "width": MONITOR_PANEL["width"],
        "height": MONITOR_PANEL["height"]
    }
    
    print(f"\n>>> ÁREA RECALCULADA PARA O JOGO: {area_real}")
    print(">>> Pressiona 'q' na janela de imagem para sair.\n")
    
    while True:
        # Captura usando as coordenadas absolutas corrigidas
        img_bgra = np.array(sct.grab(area_real))
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
        
        # Match Template
        resultado = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(resultado)
        
        # Lógica visual
        if max_val >= THRESHOLD_ORIGINAL:
            cor = (0, 255, 0) # Verde = Sucesso
            texto_estado = f"SUCESSO! Match: {max_val*100:.1f}%"
            espessura_caixa = 2
        else:
            cor = (0, 0, 255) # Vermelho = Falha
            texto_estado = f"FALHA: {max_val*100:.1f}% (Min: 85%)"
            espessura_caixa = 1

        # Desenhar
        cv2.rectangle(img_bgr, max_loc, (max_loc[0] + w_temp, max_loc[1] + h_temp), cor, espessura_caixa)
        cv2.putText(img_bgr, texto_estado, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, cor, 2)
        cv2.putText(img_bgr, "Area de Procura Vigiada", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        # Redimensionar para não ocupar o ecrã todo (metade do tamanho original para o debug)
        img_show = cv2.resize(img_bgr, (500, 600)) 
        
        cv2.imshow("Ocular Diagnostico", img_show)
        cv2.imshow("Template STATION.png Original", template)
        
        if cv2.waitKey(100) & 0xFF == ord('q'):
            break

cv2.destroyAllWindows()
import os
import cv2
import mss
import numpy as np

# ==========================================
# 1. SETUP DE CONFIGURAÇÃO E GEOMETRIA PAR COORDENADAS REAIS
# ==========================================
GEO_AREAS = {
    # Menu da Estação 
    "menu": {"top": 1100, "left": 1100, "width": 400, "height": 400},
    
    # CORNER
    "corner": {"top": 100, "left": 1900, "width": 370, "height": 280} 
}

ALVOS = {
    'AUTO_LAUNCH': {
        'ficheiro': 'AUTO_LAUNCH.png', 
        'threshold': 0.75, 
        'cor': (255, 0, 0),      
        'area_id': 'menu'
    },
    'NO_SELECTION': {
        'ficheiro': 'NO_SELECTION.png', 
        'threshold': 0.75, 
        'cor': (0, 255, 255),    
        'area_id': 'menu'
    },
    'REPAIR': {
        'ficheiro': 'repair.png', 
        'threshold': 0.75, 
        'cor': (0, 255, 0),      
        'area_id': 'menu'
    },
    'COMPLETE': {
        'ficheiro': 'AUTO_LAUNCH_COMPLETE.png', 
        'threshold': 0.65, 
        'cor': (0, 0, 255),      # Vermelho para o alvo principal
        'area_id': 'corner'      
    }
}

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_imagens = os.path.join(diretorio_atual, '../images')
log_test = os.path.join(diretorio_atual, '../logs/testar_visao_undocking.png')

print("[SISTEMA] A carregar templates...")
for nome_alvo, dados in ALVOS.items():
    caminho = os.path.join(pasta_imagens, dados['ficheiro'])
    img = cv2.imread(caminho, cv2.IMREAD_COLOR)
    if img is not None:
        dados['template'] = img
        dados['h'], dados['w'] = img.shape[:2]
    else:
        print(f" -> [ERRO] Não encontrei o ficheiro: {dados['ficheiro']}")
        exit()

# ==========================================
# 2. LOOP DE EXECUÇÃO
# ==========================================
with mss.mss() as sct:
    monitors = sct.monitors
    monitor_jogo = monitors[1] if len(monitors) > 1 else monitors[0]

    areas_reais = {}
    for chave, geo in GEO_AREAS.items():
        areas_reais[chave] = {
            "top": monitor_jogo["top"] + geo["top"],
            "left": monitor_jogo["left"] + geo["left"],
            "width": geo["width"],
            "height": geo["height"]
        }

    while True:
        img_menu_raw = np.array(sct.grab(areas_reais["menu"]))
        # teste begin
        img_bgr = cv2.cvtColor(img_menu_raw, cv2.COLOR_BGRA2BGR)
        cv2.imwrite(log_test, img_bgr) 
        # teste end
        img_corner_raw = np.array(sct.grab(areas_reais["corner"]))
        
        frames = {
            "menu": cv2.cvtColor(img_menu_raw, cv2.COLOR_BGRA2BGR),
            "corner": cv2.cvtColor(img_corner_raw, cv2.COLOR_BGRA2BGR) # Dicionário usa 'corner'
        }
        
        # Desenhar painéis de fundo baseados no tamanho real das áreas
        cv2.rectangle(frames["menu"], (5, 5), (450, 85), (0, 0, 0), -1)
        cv2.rectangle(frames["corner"], (5, 5), (450, 55), (0, 0, 0), -1)
        
        y_texto_menu = 30
        y_texto_center = 30
        
        for nome_alvo, dados in ALVOS.items():
            area_alvo = dados['area_id']
            frame_trabalho = frames[area_alvo]
            
            res = cv2.matchTemplate(frame_trabalho, dados['template'], cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            percentagem = max_val * 100
            
            if max_val >= dados['threshold']:
                cor_render = dados['cor']
                texto = f"[{nome_alvo}]: OK ({percentagem:.1f}%)"
                espessura = 2
                cv2.rectangle(frame_trabalho, max_loc, (max_loc[0] + dados['w'], max_loc[1] + dados['h']), cor_render, espessura)
            else:
                cor_render = (50, 50, 130)
                texto = f"[{nome_alvo}]: Falha ({percentagem:.1f}% / Min: {dados['threshold']*100:.0f}%)"
                espessura = 1
            
            # CORREÇÃO: Escrita de texto utilizando as chaves corretas do dicionário frames
            if area_alvo == "menu":
                cv2.putText(frames["menu"], texto, (10, y_texto_menu), cv2.FONT_HERSHEY_SIMPLEX, 0.55, cor_render, 1)
                y_texto_menu += 25
            else:
                cv2.putText(frames["corner"], texto, (10, y_texto_center), cv2.FONT_HERSHEY_SIMPLEX, 0.55, cor_render, 1) # Corrigido para 'corner'
                y_texto_center += 25

        menu_show = cv2.resize(frames["menu"], (450, 300))
        center_show = cv2.resize(frames["corner"], (550, 300)) # Corrigido para 'corner'

        cv2.imshow("R2D2 - Visao do Menu", menu_show)
        cv2.imshow("R2D2 - Visao do Canto Superior", center_show)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

cv2.destroyAllWindows()
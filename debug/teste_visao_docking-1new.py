import os
import cv2
import mss
import numpy as np
import time

# ==========================================
# 1. SETUP DE CONFIGURAÇÃO E GEOMETRIA
# ==========================================
# ATENÇÃO: Garante que estas áreas são rigorosamente iguais às declaradas no teu docking.py de produção.
GEO_AREAS = {
    # Painel Esquerdo (Onde navegas na tab "Contacts" e fazes "Request Docking")
    "painel_esquerdo": {"top": 200, "left": 50, "width": 800, "height": 1000},
    
    # Canto de Informações (Onde surge o aviso azul de "Docking Granted")
    "info_panel": {"top": 100, "left": 1900, "width": 370, "height": 280} 
}

# Define as imagens alvo do teu docking e os seus limiares rigorosos
ALVOS = {
    'REQUEST_DOCKING': {
        'ficheiro': 'REQUEST_DOCKING.png', 
        'threshold': 0.75, 
        'cor': (0, 255, 0),      
        'area_id': 'painel_esquerdo'
    },
    'DOCKING_GRANTED': {
        'ficheiro': 'DOCKING_GRANTED.png', 
        'threshold': 0.75, 
        'cor': (255, 255, 0),    
        'area_id': 'info_panel'
    },
    'CONTACTS_TAB': {
        'ficheiro': 'CONTACTS_TAB.png', 
        'threshold': 0.75, 
        'cor': (0, 255, 255),    
        'area_id': 'painel_esquerdo'
    }
    # Podes adicionar mais dicionários aqui se tiveres um "DOCKING_DENIED.png", por exemplo.
}

# ==========================================
# 2. CARREGAMENTO DOS TEMPLATES
# ==========================================
diretorio_atual = os.path.dirname(os.path.abspath(__file__))
# Verifica se a tua pasta de imagens está na mesma raiz ou se precisas de subir um nível ('../images')
pasta_imagens = os.path.join(diretorio_atual, '../images')

templates_carregados = {}
print("\n[SISTEMA] A carregar matrizes óticas para validação de Atracagem...")
for chave, dados in ALVOS.items():
    caminho = os.path.join(pasta_imagens, dados['ficheiro'])
    img = cv2.imread(caminho, cv2.IMREAD_COLOR)
    if img is not None:
        templates_carregados[chave] = img
        print(f"[OK] Template validado em memória: {dados['ficheiro']}")
    else:
        print(f"[ERRO] I/O Exception. Ficheiro ausente em: {caminho}")

# ==========================================
# 3. ALOCAÇÃO DE ECRÃS (Modo Headless/Debug)
# ==========================================
NOME_PAINEL = "R2D2 - Ocular de Atracagem (Docking Lab)"
cv2.namedWindow(NOME_PAINEL, cv2.WINDOW_NORMAL)
cv2.resizeWindow(NOME_PAINEL, 1200, 800)

with mss.mss() as sct:
    monitores = sct.monitors
    
    # Proteção de foco: Empurra a janela para o ecrã secundário para não tapar o HUD do Elite
    if len(monitores) > 2:
        ecra_secundario = monitores[2]
        cv2.moveWindow(NOME_PAINEL, ecra_secundario["left"] + 50, ecra_secundario["top"] + 50)
    else:
        cv2.moveWindow(NOME_PAINEL, 50, 50)

    print("\n==================================================")
    print(">>> DOCKING VISION LAB EM MODO DE VARRIMENTO")
    print("-> Pressione 'Q' na janela das câmaras para Sair")
    print("==================================================\n")

    # ==========================================
    # 4. LOOP DE INSPEÇÃO
    # ==========================================
    while True:
        if cv2.waitKey(40) & 0xFF == ord('q'):
            print("\n[ENCERRAMENTO] Conexão ótica terminada.")
            break

        frames = {}
        
        # 1. Grab absoluto blindado (Elimina desvios de subprocesso do Windows)
        for nome_area, coords in GEO_AREAS.items():
            try:
                area_absoluta = {
                    "top": int(coords["top"]),
                    "left": int(coords["left"]),
                    "width": int(coords["width"]),
                    "height": int(coords["height"])
                }
                img_bgra = np.array(sct.grab(area_absoluta))
                img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
                frames[nome_area] = img_bgr.copy()
            except Exception as e:
                print(f"[ERRO] Violação de limites no ecrã para a área '{nome_area}': {e}")
                frames[nome_area] = np.zeros((coords["height"], coords["width"], 3), dtype=np.uint8)

        y_textos = {chave: 30 for chave in GEO_AREAS.keys()}

        # 2. Match de Formatos Geométricos
        for nome_alvo, dados in ALVOS.items():
            if nome_alvo not in templates_carregados: continue
                
            area_id = dados['area_id']
            frame_trabalho = frames[area_id]
            template = templates_carregados[nome_alvo]
            th, tw = template.shape[:2]

            res = cv2.matchTemplate(frame_trabalho, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            percentagem = max_val * 100
            
            if max_val >= dados['threshold']:
                cor_render = dados['cor']
                texto = f"[{nome_alvo}]: OK ({percentagem:.1f}%)"
                espessura = 2
                cv2.rectangle(frame_trabalho, max_loc, (max_loc[0] + tw, max_loc[1] + th), cor_render, espessura)
            else:
                cor_render = (50, 50, 130) # Vermelho apagado (A não passar na validação matemática)
                texto = f"[{nome_alvo}]: Falha ({percentagem:.1f}% / Exige: {dados['threshold']*100:.0f}%)"
                espessura = 1
            
            # Print em ecrã do resultado de cada alvo
            cv2.putText(frames[area_id], texto, (10, y_textos[area_id]), cv2.FONT_HERSHEY_SIMPLEX, 0.55, cor_render, 1)
            y_textos[area_id] += 25

        # 3. Composição de Painel (Pipelines de Renderização)
        # Redimensiona os frames em bruto para caberem de forma limpa na mesma janela
        view_painel = cv2.resize(frames["painel_esquerdo"], (600, 750), interpolation=cv2.INTER_NEAREST)
        view_info = cv2.resize(frames["info_panel"], (550, 410), interpolation=cv2.INTER_NEAREST)
        
        # Fundo preto para montar as duas câmaras
        canvas_final = np.zeros((800, 1200, 3), dtype=np.uint8)
        
        # Colagem do pipeline esquerdo
        canvas_final[25:775, 20:620] = view_painel
        cv2.putText(canvas_final, "CÂMARA 1: PAINEL ESQUERDO (NAVEGACAO)", (20, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # Colagem do pipeline direito (Info)
        canvas_final[25:435, 640:1190] = view_info
        cv2.putText(canvas_final, "CÂMARA 2: PAINEL SUPERIOR DIREITO (COMMS)", (640, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        cv2.imshow(NOME_PAINEL, canvas_final)

cv2.destroyAllWindows()
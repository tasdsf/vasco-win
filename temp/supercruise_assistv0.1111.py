import os
import time
import pydirectinput
import cv2
import mss
import numpy as np
import pyttsx3

# ==========================================
# 1. SETUP E ÁREAS
# ==========================================
MONITOR_PANEL = {"top": 200, "left": 50, "width": 1000, "height": 1200}
# Área central/superior para apanhar o aviso de Supercruise Assist no HUD
MONITOR_CENTER = {"top": 100, "left": 400, "width": 1100, "height": 800}

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_imagens = os.path.join(diretorio_atual, 'images')

templates_nomes = {
    'menu': 'menu.png',
    'nav_tab': 'NAVIGATION_SELECTED.png',
    'station': 'STATION.png',
    'carrier': 'FLEET_CARRIER_NAME.png',
    'locked': 'LOCKED_DESTINATION.png',
    'unlocked': 'UNLOCKED_DESTINATION.png',
    'assist_active': 'SUPERCRUISE_ASSIST_ACTIVE.png', # A tua nova imagem!
    'throttle_up': 'THROTTLE_UP.png'
}

templates = {}
try:
    for chave, nome_arq in templates_nomes.items():
        caminho = os.path.join(pasta_imagens, nome_arq)
        templates[chave] = cv2.imread(caminho, cv2.IMREAD_COLOR)
    print(f"[SISTEMA] Módulo Supercruise Inteligente carregado.")
except Exception as e:
    print(f"ERRO: {e}"); exit()

# --- Voz ---
engine = pyttsx3.init()
voices = engine.getProperty('voices')
for voice in voices:
    if "EN-US" in voice.id.upper() or "ZIRA" in voice.id.upper():
        engine.setProperty('voice', voice.id)
        break

def falar(texto):
    print(f"[VOZ] {texto}")
    engine.say(texto)
    engine.runAndWait()

# ==========================================
# 2. MOTOR DE VISÃO
# ==========================================
def procurar_template(template, nome_label, monitor, threshold=0.75):
    if template is None: return False
    
    with mss.mss() as sct:
        img_bgra = np.array(sct.grab(monitor))
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
        resultado = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(resultado)
        
        encontrou = max_val >= threshold
        cor = (0, 255, 0) if encontrou else (0, 0, 255)
        
        if encontrou:
            h, w = template.shape[:2]
            #cv2.rectangle(img_bgr, max_loc, (max_loc[0] + w, max_loc[1] + h), cor, 2)
        
        #cv2.putText(img_bgr, f"{nome_label}: {max_val:.2f}", (10, 30), 1, 1.2, (255, 255, 255), 2)
        #cv2.imshow("Ocular Supercruise", img_bgr)
        #cv2.moveWindow("Ocular Supercruise", 50, 50)
        #cv2.waitKey(1)
        return encontrou

# ==========================================
# 3. ATIVAÇÃO DO ASSIST
# ==========================================

def ativar_supercruise_assist():    
    print("\n>>> FASE 0: JUMP!")
    pydirectinput.press('j')
    pydirectinput.keyDown('.')
    time.sleep(5)
    pydirectinput.keyUp('.')
    
    contagem_limpo = 0 # O aviso ainda está lá, reset à contagem
    while contagem_limpo < 3:
        # Procuramos o aviso na área central do HUD
        if procurar_template(templates['throttle_up'], "THROTTLE_UP ACTIVE", MONITOR_CENTER, 0.70):
            contagem_limpo = 0 # O aviso ainda está lá, reset à contagem
        else:
            contagem_limpo += 1 # Não vimos o aviso, incrementa
            
        pydirectinput.keyDown('.')
        time.sleep(1)
        pydirectinput.keyUp('.')    

    
    print("\n>>> FASE 1: Ativar Assistência...x")
    pydirectinput.press('x')
    time.sleep(0.5)
   
    print("\n>>> FASE 1: Ativar Assistência...1")
    pydirectinput.press('1')
    time.sleep(2.5)
    # print(">>> vai selecionar com a tecla space!")
    # pydirectinput.press('space')
    # time.sleep(1.0)
    # print(">>> selecionou o TARGET!")
    # pydirectinput.press('d')
    # time.sleep(0.5)
    # print(">>> andou para o lado!")
    # pydirectinput.press('space')
    # print(">>> Supercruise Assist ATIVADO!")

    
    contagem_limpo = 0 # reset à contagem
    while contagem_limpo < 8:
        if procurar_template(templates['menu'], "menu", MONITOR_PANEL, 0.85):
            print(">>> achou o menu!")
            time.sleep(1.0)
            break
        else:
            contagem_limpo += 1 # Não vimos o templates, incrementa e anda para o lado
            print(">>> press 1!")
            pydirectinput.press('1'); time.sleep(0.5)
           
          
    if contagem_limpo >=8:       
        print(">>> falhou o menu...")
        pydirectinput.press('1')
        pydirectinput.press('x')
        #pydirectinput.press('j')
        return False
        
        
    contagem_limpo = 0 # reset à contagem
    while contagem_limpo < 8:
        if procurar_template(templates['nav_tab'], "NAV", MONITOR_PANEL, 0.85):
            print(">>> achou a NAV tab!")
            time.sleep(1.0)
            break
        else:
            contagem_limpo += 1 # Não vimos o templates, incrementa e anda para o lado
            print(">>> press q!")
            pydirectinput.press('q'); time.sleep(0.5)
           
          
    if contagem_limpo >=8:       
        print(">>> falhou a NAV tab...")
        pydirectinput.press('1')
        pydirectinput.press('x')
        #pydirectinput.press('j')
 
    # contagem_limpo = 0 # reset à contagem
    # while contagem_limpo < 18:
        # # Lista dos alvos que queres verificar
        # alvos = ['station', 'carrier']
        # encontrado = False

        # # Iteramos pela lista de alvos
        # for alvo in alvos:
            # # Verificamos cada um individualmente
            # if procurar_template(templates[alvo], "target", MONITOR_PANEL, 0.85):
                # print(f"[SUCESSO] Detetado: {alvo}")
                # break # Paramos de procurar se já encontrámos um
        # else:
            # print(">>> press s!")
            # contagem_limpo += 1 # Não vimos o templates, incrementa e anda para o lado
            # pydirectinput.press('s'); time.sleep(0.3)
           
          
    # if contagem_limpo >=18:       
        # print(">>> falhou o target...")
        # pydirectinput.press('1')
        # pydirectinput.press('x')
        # pydirectinput.press('j')
        # return False 

   
    pydirectinput.press('space')
    print(">>> selecionou o TARGET!")
    time.sleep(1.0)
    
    if procurar_template(templates['locked'], "LOCKED", MONITOR_PANEL, 0.85):
       print(">>> achou o LOCKED!")
       pydirectinput.press('d'); time.sleep(0.3)
       print(">>> andou para o lado!")
       pydirectinput.press('space')
       print(">>> Supercruise Assist ATIVADO!")
    elif procurar_template(templates['unlocked'], "UNLOCKED", MONITOR_PANEL, 0.85):
       print(">>> achou o ###UNLOCKED###")
       pydirectinput.press('space')
       print(">>> Destino trancado. É necessário ativar manualmente.")
     
    pydirectinput.press('1')
    print(">>> BACK TO MAIN!")
    time.sleep(1.0)
    return True

# ==========================================
# 4. MONITORIZAÇÃO DE VIAGEM E CHEGADA
# ==========================================

def monitorar_viagem():    
    print("\n>>> FASE 2: Viagem em Supercruise...")
    falar("Supercruise assist engaged. Monitoring flight path.")
    
    # 1. Espera de Segurança
    #print("A aguardar 15 segundos iniciais...")
    #time.sleep(15)
    
    print("A analisar HUD. À espera que o aviso de Assist !apareça...")
    contagem_limpo = 0
    while contagem_limpo < 3:
        # Procuramos o aviso na área central do HUD
        if not procurar_template(templates['assist_active'], "ASSIST ACTIVE", MONITOR_CENTER, 0.75):
            contagem_limpo = 0 # O aviso não está lá, reset à contagem
        else:
            contagem_limpo += 1 # vimos o aviso, incrementa
            
        time.sleep(1)

    # 2. Monitorizar Ausência do Painel
    print("A analisar HUD. À espera que o aviso de Assist desapareça...")
    contagem_limpo = 0
    # Queremos 3 verificações limpas seguidas para garantir que fizemos o drop
    while contagem_limpo < 3:
        # Procuramos o aviso na área central do HUD
        if procurar_template(templates['assist_active'], "ASSIST ACTIVE", MONITOR_CENTER, 0.75):
            contagem_limpo = 0 # O aviso ainda está lá, reset à contagem
        else:
            contagem_limpo += 1 # Não vimos o aviso, incrementa
            
        time.sleep(1)

    # 3. Manobra de Chegada
    print("\n>>> CHEGADA CONFIRMADA! A executar travagem e boost...")
    falar("Dropping from supercruise. Engaging approach maneuver.")
    
    time.sleep(2.0)
    pydirectinput.press('tab') # Boost na direção da estação/carrier
    time.sleep(15.0)
    pydirectinput.press('tab') # Boost na direção da estação/carrier
    time.sleep(10.0)
    pydirectinput.press('x') # Cortar motor (Força Zero)
    print(">>> Manobra concluída. A aguardar aproximação para docking.")

if __name__ == "__main__":
    print("Prepara a nave em direção ao destino. Iniciando em 3s...")
    time.sleep(3)
    
    if ativar_supercruise_assist():
        monitorar_viagem()
        
    cv2.destroyAllWindows()
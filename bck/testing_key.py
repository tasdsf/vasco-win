import pydirectinput
import time

def test_key_press():
    print("Mude o foco para a janela do Elite Dangerous agora!")
    print("Enviando comando em 5 segundos...")
    time.sleep(5)
    
    # No Elite, o Espaço é usado para confirmar seleções no menu 
    # ou para o "Boost" (se configurado).
    print("Pressionando 'Espaço' (SPACE)...")
    
    pydirectinput.keyDown('space')
    time.sleep(0.1) 
    pydirectinput.keyUp('space')
    
    print("Comando enviado!")

if __name__ == "__main__":
    test_key_press()
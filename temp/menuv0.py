import os
import subprocess
import sys

# Mapeamento estrito dos scripts aos números de 1 a 8
SCRIPTS = {
    "1": "comprarv2.py",
    "2": "select_target_carrier.py",
    "3": "vender.py",
    "4": "select_target_station.py",
    "5": "undocking.py",
    "6": "olho.py",
    "7": "supercruise_assist.py",
    "8": "dockingv1.py"
}

def exibir_menu():
    # Limpa o terminal para manter o visual limpo a cada retorno
    os.system('cls' if os.name == 'nt' else 'clear')
    
    print("="*45)
    print("      R2D2 - COCKPIT DE AUTOMACAO")
    print("="*45)
    
    # Bloco Inicial
    print("1 - comprarv2.py")
    print("2 - select_target_carrier.py")
    
    # Separador 1
    print('==== move to target ======')
    
    # Bloco de Venda
    print("3 - vender.py")
    print("4 - select_target_station.py")
    
    # Separador 2
    print('==== move to target ======')
    
    # Separador de Cabeçalho para Navegação (O teu Segundo Menu)
    print("\n>>move to target (Execução via PowerShell com Auto-Retorno):")
    
    # Bloco de Voo
    print("5 - undocking.py")
    print("6 - olho.py")
    print("7 - supercruise_assist.py")
    print("8 - dockingv1.py")
    
    print("\n" + "-"*45)
    print("0 - SAIR")
    print("-" * 45)

def executar_script(opcao, script_name):
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), script_name)
    
    if not os.path.exists(script_path):
        print(f"\n[ERRO] Alvo falhou: O ficheiro '{script_name}' não existe.")
        input("\nPressione Enter para continuar...")
        return

    print(f"\n[POWERSHELL] Passando controlo para: {script_name}")
    print("[INFO] O menu irá retornar assim que encerrar o script.")
    print("-" * 50)
    
    try:
        # Execução Síncrona inline via PowerShell. O menu congela e aguarda o fim do script.
        subprocess.run(["powershell", "-Command", f'python "{script_path}"'], check=True)
    except subprocess.CalledProcessError:
        print(f"\n[AVISO] Script {script_name} terminou com um código de saída diferente de zero.")
    except KeyboardInterrupt:
        print("\n[AVISO] Execução interrompida pelo utilizador.")
        
    print("\n" + "-" * 50)
    print("[SISTEMA] Script concluído. Retornando ao menu principal...")
    time_sleep_visual = 1.5
    import time
    time.sleep(time_sleep_visual)

def main():
    while True:
        exibir_menu()
        escolha = input("Escolha > ")
        
        if escolha == '0':
            print("\nDesligando painel de controlo. Boa caça, Comandante.")
            break
        elif escolha in SCRIPTS:
            executar_script(escolha, SCRIPTS[escolha])
        else:
            print("\n[AVISO] Código inválido. Introduz um número de 1 a 8.")
            import time
            time.sleep(1)

if __name__ == "__main__":
    main()
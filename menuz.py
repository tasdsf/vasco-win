#!/usr/bin/env python3
"""
menUZ - Menú de Sequências Automáticas
Workflow: Comprar → Vender → Viajar
"""

import os
import sys
import subprocess
import logging
import time
from datetime import datetime as _dt_hora

# Todos os prints passam a ter timestamp HH:MM:SS (preserva "\n" iniciais
# usados para espaçamento visual no terminal).
_print_original = print
def print(*args, **kwargs):
    if args and isinstance(args[0], str):
        _texto = args[0]
        _prefixo_nl = ""
        while _texto.startswith("\n"):
            _prefixo_nl += "\n"
            _texto = _texto[1:]
        args = (f"{_prefixo_nl}[{_dt_hora.now().strftime('%H:%M:%S')}] {_texto}",) + args[1:]
    _print_original(*args, **kwargs)

# ============== Infra-estrutura ==============
# Mapeamento de scripts

SCRIPTS = {
    "comprar": "comprar.py",
    "vender": "vender.py",
    "select_target": "select_target.py",  # Selecionar origem
    "undocking": "undocking.py",
    "olho": "olho.py",
    "supercruise": "supercruise_assist.py",
    "docking": "docking.py"
}

# Sequência completa de viagem
VIAGEM = [
    "select_target",
    "undocking",
    "olho",
    "supercruise",
    "docking"
]

# Configura logger
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "r2d2_menuz.log")

logger = None

def configurar_logger():
    global logger
    logger = logging.getLogger("r2d2_menuz_logger")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
        fh.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        logger.propagate = False
    return logger

def exibir_menu():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("="*60)
    print("      VASCO - AUTOMATION ORCHESTRATOR - MENUZ")
    print("="*60)
    print()
    print("1 - Comprar    → comprar.py")
    print("2 - Vender     → vender.py")
    print("3 - Viajar     → select_target → undocking → olho → supercruise → docking")
    print("0 - Sair")
    print("-"*60)

def executar_script(script_name, timeout=600):
    """Executa um script individual"""
    if script_name not in SCRIPTS:
        logger.error(f"Script não encontrado: {script_name}")
        print(f"\n[ERRO] Script não encontrado: {script_name}")
        input("Pressione Enter para continuar...")
        return False
    
    script_path = SCRIPTS[script_name]
    if not os.path.exists(script_path):
        logger.error(f"Ficheiro não encontrado: {script_path}")
        print(f"\n[ERRO] Ficheiro não encontrado: {script_path}")
        return False
    
    logger.info(f"Executando: {script_name}")
    print(f"\n[ETAPA] Executando: {script_name}")
    print(f"  Caminho: {script_path}")
    
    cmd = [sys.executable, script_path]
    
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Leitura linha a linha em tempo real
        full_output = ""
        for line in iter(proc.stdout.readline, ""):
            stripped = line.rstrip("\n")
            logger.info(stripped)
            print(stripped)
            full_output += line
        
        proc.stdout.close()
        returncode = proc.wait(timeout=timeout)
        
        if returncode == 0:
            logger.info(f"{script_name} concluído com sucesso (exit: {returncode})")
            print(f"\n[OK] {script_name} terminou bem!")
        else:
            error_msg = f"Exit code: {returncode}\nOutput: {full_output[:2000]}"
            logger.error(f"{script_name} falhou: {error_msg}")
            print(f"\n[ERRO] {script_name} falhou com retorno {returncode}")
        
        return returncode == 0
    except subprocess.TimeoutExpired:
        proc.kill()
        logger.error(f"Timeout em {script_name}")
        print(f"\n[ERRO] Timeout em {script_name}")
        return False
    except Exception as e:
        logger.exception(f"Erro em {script_name}: {e}")
        print(f"\n[ERRO] {e}")
        return False

def executar_viagem():
    """Executa a sequência completa de viagem"""
    logger.info("Iniciando sequência de viagem")
    print("\n" + "="*60)
    print("      VIAGEM COMPLETA (select_target → undocking → olho → supercruise → docking)")
    print("="*60)
    print("="*60)
    
    for i, step_name in enumerate(VIAGEM, 1):
        print(f"\n--- [{i}/{len(VIAGEM)}] {step_name.upper()} ---")
        
        sucesso = executar_script(step_name)
        
        if not sucesso:
            print(f"\n[ALERTA] Sequência interrompida em {step_name}")
            print("[OPÇÕES]")
            print("  1 - Retry a etapa falhada")
            print("  2 - Continuar com próximo")
            print("  3 - Cancelar sequência")
            
            try:
                choice = input("\nEscolha (1-3): ").strip()
                if choice == "1":
                    print(f"\n[RETRY] Retentar {step_name}...")
                    sucesso = executar_script(step_name)
                    if not sucesso:
                        print(f"[ERRO] Retry falhou. Continuar?")
                        print("  1 - Sim")
                        print("  2 - Não (CANCELAR)")
                        choice = input("Escolha: ").strip()
                        if choice != "1":
                            return False
                elif choice == "3":
                    print("Cancelando sequência...")
                    return False
            except KeyboardInterrupt:
                print("\nCancelado!")
                return False
    
    logger.info("Sequência de viagem concluída com sucesso!")
    print("\n" + "="*60)
    print("[SUCESSO] Sequência de viagem concluída!")
    print("="*60)
    time.sleep(2)

def main():
    print_header()
    configurar_logger()
    
    while True:
        exibir_menu()
        escolha = input("\nOpção: ").strip()
        
        if escolha == "1":
            print("\n[1] Comprar")
            print("  Executa: comprar.py")
            comprar = executar_script("comprar")
            if not comprar:
                input("[ERRO] comprar.py falhou. Pressione Enter...")
        
        elif escolha == "2":
            print("\n[2] Vender")
            print("  Executa: vender.py")
            vender = executar_script("vender")
            if not vender:
                input("[ERRO] vender.py falhou. Pressione Enter...")
        
        elif escolha == "3":
            print("\n[3] Viajar")
            print("  Sequência automática:")
            print("    → select_target_station.py")
            print("    → undocking.py")
            print("    → olho.py")
            print("    → supercruise_assist.py")
            print("    → docking.py")
            
            print("\n[INICIANDO] Sequência de viagem automática...")
            executar_viagem()
            
        elif escolha == "0":
            print("\n[SAIR]")
            break
        
        else:
            print("[ERRO] Opção inválida.")

def print_header():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("="*60)
    print("      VASCO - AUTOMATION ORCHESTRATOR - MENUZ")
    print("="*60)
    print()
    print("1 - Comprar    → comprar.py")
    print("2 - Vender     → vender.py")
    print("3 - Viajar     → select_target → undocking → olho → supercruise → docking")
    print("0 - Sair")
    print("-"*60)

if __name__ == "__main__":
    print("\n[INFO] Carregando menuz.py...")
    time.sleep(1)
    main()

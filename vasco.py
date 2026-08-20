#!/usr/bin/env python3
"""
VASCO - Vasco Automation Orchestrator
Elite Dangerous Automation with intelligent sequence handling
"""

import os
import sys
import time
import subprocess
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
import keyboard

# ADICIONADO: Importar a função do verificador de linha de visão
from los_checker import calcular_espera_los
from discord_notify import notificar_erro_discord
from leg_state import reiniciar_leg_limpa, marcar_leg_suja

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
        args = (f"{_prefixo_nl}[{datetime.now().strftime('%H:%M:%S')}] {_texto}",) + args[1:]
    _print_original(*args, **kwargs)

# Set up logging
SCRIPT_DIR = Path(__file__).parent
LOG_DIR = SCRIPT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "vasco_automated.log"
STATE_FILE = LOG_DIR / "vasco_state.json"
ED_LOG_DIR = os.path.expanduser('~') + r"\Saved Games\Frontier Developments\Elite Dangerous"

def setup_logger():
    logger = logging.getLogger("vasco")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        fh = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(fh)
        logger.propagate = False
    return logger

def print_header():
    print("\n\n" + "="*60)
    print("     VASCO - ORQUESTRADOR DE AUTOMACAO ELITE DANGEROUS")
    print("="*60)
    print("Sequencia: Compra -> Carrier -> Venda -> Estacao")
    print("="*60 + "\n")

def load_state():
    if not STATE_FILE.exists():
        return {"last_step": -1, "completed_steps": []}
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"last_step": -1, "completed_steps": []}

def save_state(step, success, error=None, completed_steps=None):
    state = {
        "last_step": step,
        "success": success,
        "error": error,
        "completed_steps": completed_steps or []
    }
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)

SCRIPTS = {
    "comprar": "comprar.py",
    "target_carrier": "select_target.py",
    "undocking": "undocking.py",
    "olho": "olho.py",
    "supercruise": "supercruise_assist.py",
    "docking": "docking.py",
    "vender": "vender.py",
    "station": "select_target.py"
}

SEQUENCE = {
    1: {"name": "COMPRAR", "script": SCRIPTS["comprar"], "desc": "Comprar Fujin Tea na estacao atual"},
    2: {"name": "TARGET_CARRIER", "script": SCRIPTS["target_carrier"], "desc": "Selecionar Zahir como destino"},
    3: {"name": "UNDOCKING", "script": SCRIPTS["undocking"], "desc": "Undock da estacao"},
    4: {"name": "OLHO", "script": SCRIPTS["olho"], "desc": "Verificar status da mira/reticule"},
    5: {"name": "SUPERCRUISE", "script": SCRIPTS["supercruise"], "desc": "Supercruise assistido"},
    6: {"name": "DOCKING", "script": SCRIPTS["docking"], "desc": "Dock no fleet carrier"},
    7: {"name": "VENDER", "script": SCRIPTS["vender"], "desc": "Vender Fujin Tea no Zahir"},
    8: {"name": "SELECT_STATION", "script": SCRIPTS["station"], "desc": "Selecionar estacao de origem"},
    9: {"name": "UNDOCKING", "script": SCRIPTS["undocking"], "desc": "Undock da estacao"},
    10: {"name": "OLHO", "script": SCRIPTS["olho"], "desc": "Verificar status da mira/reticule"},
    11: {"name": "SUPERCRUISE", "script": SCRIPTS["supercruise"], "desc": "Supercruise assistido"},
    # Corrigido: esta etapa faz dock na estacao de origem (fim do ciclo), nao no fleet carrier.
    12: {"name": "DOCKING", "script": SCRIPTS["docking"], "desc": "Dock na estacao de origem"},
}

def _notificar_falha_discord(script_name, error_msg):
    """ Notifica o Discord só quando uma etapa esgota TODOS os retries.
    Único ponto de integração para todas as etapas -- em vez de mexer em
    cada script individual.

    Anexa o screenshot de erro mais recente (logs/erro_*.png) se tiver
    menos de 30s -- só se for mesmo desta falha, não de uma anterior.
    Best-effort: nunca pode impedir o orquestrador de continuar. """
    try:
        candidatos = sorted(LOG_DIR.glob("erro_*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
        imagem_path = str(candidatos[0]) if candidatos and (time.time() - candidatos[0].stat().st_mtime) < 30 else None
        notificar_erro_discord(script_name, error_msg, imagem_path)
    except Exception as e:
        print(f"[AVISO] Falha ao notificar Discord: {e}")

def executar_script(script_name, timeout=600, retry_count=3, retry_delay=5):
    script_path = SCRIPT_DIR / script_name
    if not script_path.exists():
        return False, f"Script nao encontrado: {script_name}", "FILE_NOT_FOUND"
    
    logger = setup_logger()
    logger.info(f"Executando: {script_name}")
    
    print(f"\n[ETAPA] Executando: {script_name}")
    print(f"    Descricao: {script_name}")
    print(f"    Timeout: {timeout}s | Retry: {retry_count}x")
    
    # "-u": forca stdout/stderr sem buffer no processo filho. Sem isto, quando
    # o stdout esta ligado a um pipe (como aqui), o Python muda para block
    # buffering e os prints do script ficam presos ate o buffer encher ou o
    # processo terminar - dava a sensacao de "nao acontece nada" mesmo com o
    # script a correr por baixo.
    cmd = [sys.executable, "-u", str(script_path)]
    
    max_retries = retry_count
    for attempt in range(max_retries):
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            with proc.stdout:
                full_output = ""
                for line in iter(proc.stdout.readline, ""):
                    line = line.strip()
                    full_output += line + "\n"
                    if line:
                        print(line)
            
            returncode = proc.wait(timeout=timeout)
            proc.stdout.close()
            
            if returncode == 0:
                full_output = full_output[:5000] if full_output else ""
                logger.info(f"Etapa {script_name} concluida com sucesso (attempt: {attempt+1})")
                return True, "Sucesso", "OK"
            else:
                error_msg = f"Exit code: {returncode}\nOutput: {full_output[:5000]}"
                logger.error(f"Etapa {script_name} falhou: retorno {returncode}")
                marcar_leg_suja()
                if attempt < max_retries - 1:
                    print(f"\n[AVISO] Retry {attempt+1}/{max_retries} falhou. Esperando {retry_delay}s...")
                    time.sleep(retry_delay)
                else:
                    print(f"\n[ERRO] Max retries atingido. Falha: {error_msg[:200]}")
                    return False, error_msg, returncode
                    
        except subprocess.TimeoutExpired:
            proc.kill()
            error_msg = f"Timeout: {timeout} segundos excedidos"
            logger.error(f"Timeout em {script_name}")
            marcar_leg_suja()
            if attempt < max_retries - 1:
                print(f"\n[AVISO] Timeout. Retry {attempt+1}/{max_retries}...")
                time.sleep(retry_delay)
            else:
                print(f"\n[ERRO] Timeout atingido")
                return False, error_msg, "TIMEOUT"
        except subprocess.SubprocessError as e:
            error_msg = str(e)
            logger.exception(f"Erro subprocess: {e}")
            marcar_leg_suja()
            if attempt < max_retries - 1:
                print(f"\n[AVISO] Erro subprocess. Retry...")
                time.sleep(retry_delay)
            else:
                return False, error_msg, "SUBPROCESS_ERROR"
        except Exception as e:
            logger.exception(f"Erro inesperado: {e}")
            marcar_leg_suja()
            return False, f"Excecao: {e}", "EXCEPTION"

    marcar_leg_suja()
    return False, "Falha maxima atingida", "MAX_RETRIES"

def main():
    # Verifica os argumentos passados na linha de comandos:
    # Se 'a' estiver no primeiro argumento (sys.argv[1]), inicia auto=1.
    auto = 1 if len(sys.argv) > 1 and sys.argv[1].lower() == 'a' else 0
    
    print_header()
    logger = setup_logger()
    logger.info("Vasco iniciado")
    if auto == 1:
        print("[INFO] Modo AUTO-CICLICO ativado via linha de comandos.")
    
    while True:
        state = load_state()
        current_step = state.get("last_step", -1) + 1
        completed_steps = state.get("completed_steps", [])
        
        # VALIDAR LOS PARA DESCOLAR SOMENTE SE VALER A PENA
        if current_step in (3, 9):
            espera = calcular_espera_los(ed_log_dir=ED_LOG_DIR)
            if espera and espera > 0:
                h, resto = divmod(int(espera), 3600)
                m, s = divmod(resto, 60)
                agora_utc_los = datetime.now(timezone.utc)
                partida_utc = agora_utc_los + timedelta(seconds=espera)
                partida_pt = partida_utc + timedelta(hours=1)
                print(f"[LOS] Destino obscurecido pelo planeta.\n A aguardar {h}h {m}m {s}s... "
                      f"Partida UTC {partida_utc.strftime('%H:%M:%S')} / PT {partida_pt.strftime('%H:%M:%S')}")
                time.sleep(espera)

        # Verifica se o ciclo já terminou anteriormente para limpar o ficheiro
        # (SEQUENCE é indexado de 1 a len(SEQUENCE); só reinicia quando current_step
        # ULTRAPASSA a última etapa válida, senão a última etapa nunca corre)
        if current_step > len(SEQUENCE):
            current_step = 0
            completed_steps = []
            print("[INFO] Ciclo anterior detetado como completo. Reiniciando...")
       
        if current_step <= 0:
            print("Iniciando automacao do zero...")
            current_step = 1  # Comecar em 1, nao 0
            state["completed_steps"] = []
            # Grava 0 (nenhuma etapa concluida ainda), nao 1 — "1" aqui confundia-se
            # com "etapa 1 ja concluida" e fazia saltar o comprar.py se o processo
            # fosse interrompido logo a seguir a esta gravacao inicial.
            save_state(0, success=True, error="Init", completed_steps=[])
        else:
            print(f"Retornando da interrupcao na etapa: {current_step}")
            logger.info(f"Resumindo da etapa: {current_step}")

        # Só fica True se o utilizador cancelar explicitamente (opção 5) ou Ctrl+C.
        # A finalização usa isto (e não len(completed_steps)) para decidir se o
        # ciclo foi bem sucedido — ver comentário na secção "Finalizacao".
        abortado = False

        while current_step <= len(SEQUENCE):
            print_header()
            step_info = SEQUENCE[current_step]

            if step_info["name"] == "UNDOCKING":
                reiniciar_leg_limpa()

            print(f"[ETAPA {current_step}] {step_info['name']}: {step_info['desc']}")
            print()

            success, error_msg, error_code = executar_script(
                step_info["script"],
                timeout=step_info.get("timeout", 600),
                retry_count=step_info.get("retry_count", 3),
                retry_delay=step_info.get("retry_delay", 5)
            )
            
            if success:
                print(f"[SUCESSO] Etapa {step_info['name']} concluida!")
                completed_steps.append(current_step)
                save_state(current_step, success=True, completed_steps=completed_steps)
                
                # Verifica se 'p' foi pressionado durante a etapa — pausa até Enter
                if keyboard.is_pressed('p'):
                    print("\n[PAUSA] Tecla 'p' detetada. A aguardar Enter para continuar...")
                    input()
                    print("[PAUSA] A retomar automação...")
                
                current_step += 1
                
            else:
                # Falha - requer intervencao
                print(f"\n[FALHA DETETADA] Etapa {current_step} ({step_info['name']}): {error_msg}")
                _notificar_falha_discord(step_info["script"], error_msg)
                print(f"Opcoes:")
                print("  1 - Retry manual (ignora erros anteriores)")
                print("  2 - Fallback (operação cega, executada manualmente)")
                print("  3 - Menu Manual (executar via menu.py)")
                print("  4 - Skip (pular, continuar)")
                print("  5 - Cancelar (abortar)")
                
                try:
                    choice = input(f"\nEscolha (1-5): ").strip()
                    logger.info(f"User choice: {choice} for step {current_step}")
                    
                    if choice == "1":
                        print("Retry manual solicitado...")
                        success, _, _ = executar_script(step_info["script"])
                        if success:
                            print(f"[SUCESSO] Retry manual bem sucedido!")
                        else:
                            print("[AVISO] Retry manual falhou, mas continuamos")
                        completed_steps.append(current_step)
                        save_state(current_step, success=True, completed_steps=completed_steps)
                        current_step += 1
                        
                    elif choice == "2":
                        print("Fallback manual. Abra (script).py manualmente.")
                        print("Esta vende sem identificar o item.")
                        time.sleep(3)
                        completed_steps.append(current_step)
                        save_state(current_step, success=True, completed_steps=completed_steps)
                        current_step += 1
                        
                    elif choice == "3":
                        print("Execucao via menu solicitada. Use menu.py normalmente.")
                        print("Pressione Enter quando terminar...")
                        input()
                        # Corrigido: faltava marcar esta etapa como concluída (igual às
                        # outras opções). Sem isto, completed_steps ficava sempre um
                        # passo abaixo de len(SEQUENCE) sempre que esta opção era usada,
                        # e o ciclo era erradamente reportado como "interrompido" no
                        # fim mesmo depois de chegar à estação com sucesso.
                        completed_steps.append(current_step)
                        save_state(current_step, success=True, completed_steps=completed_steps)
                        current_step += 1

                    elif choice == "4":
                        print(f"[SKIP] Etapa {step_info['name']} pulada.")
                        completed_steps.append(current_step)
                        save_state(current_step, success=True, completed_steps=completed_steps)
                        current_step += 1

                    elif choice == "5": # Abort solicitado pelo utilizador
                        print("[VASCO] A cancelar automação. A abater subprocessos ativos...")
                        abortado = True
                        break

                    else:
                        print("Opcao invalida. Tente novamente.")

                except KeyboardInterrupt:
                    print("\nCancelado por Ctrl+C")
                    abortado = True
                    break
                except ValueError:
                    print("Opcao invalida.")
                except EOFError:
                    # input() sem terminal interativo ligado (ex.: processo lancado
                    # por outro agente/script sem stdin real) lanca EOFError, que
                    # nao era apanhado -- o processo rebentava com traceback nao
                    # tratado, ou ficava preso, sem se saber ao certo o que
                    # aconteceu. Abortar em seguranca, de forma explicita e visivel
                    # no log, e melhor do que qualquer uma dessas duas hipoteses.
                    print("\n[VASCO] EOF ao ler a escolha (sem terminal interativo "
                          "ligado a este processo). A abortar em seguranca em vez de "
                          "ficar preso ou rebentar sem aviso.")
                    logger.error(f"EOFError ao pedir escolha na etapa {current_step} "
                                 f"({step_info['name']}) - stdin nao interativo.")
                    abortado = True
                    break
        
        # Finalizacao
        print_header()
        print(f"="*60)
        print("     AUTOMACAO CONCLUIDA!")
        print(f"     Etapas concluidas: {len(completed_steps)}/{len(SEQUENCE)}")
        print(f"     Estado salvo em: {STATE_FILE}")
        print(f"     Log completo: {LOG_FILE}")
        print(f"="*60)

        # Corrigido: usar len(completed_steps) == len(SEQUENCE) como critério de
        # sucesso era frágil — qualquer caminho que avançasse current_step sem
        # adicionar a completed_steps (como a opção 3 tinha) fazia o ciclo ser
        # reportado como "interrompido" mesmo com todas as etapas concluídas
        # (ex.: "11/12" depois do dock na estação com sucesso). O sinal fiável é:
        # o loop esgotou current_step até passar de len(SEQUENCE) (percorreu
        # todas as etapas) E não houve cancelamento explícito (opção 5 / Ctrl+C).
        ciclo_completo = (not abortado) and (current_step > len(SEQUENCE))

        if ciclo_completo:
            print("\n[*] Automacao concluida com sucesso!")
            if auto == 0:
                choice = input("\nPressione Enter para continuar ou 'a' para entrar em auto: ")
                if choice.strip().lower() == 'a':
                    auto = 1 
            else:
                print(f"\n ====> pressione 'a' para desativar auto-ciclico ")
                cont = 5
                # Loop corrigido para funcionar como um countdown real de 5 segundos
                while cont > 0:
                    print(f"---- Automacao vai recomeçar em {cont} ")
                    step_start = time.time()
                    while time.time() - step_start < 1:
                        if keyboard.is_pressed("a"):
                            auto = 0
                            break
                    if auto == 0:
                        print("\n[!] Modo auto-ciclico desativado.")
                        break
                    cont -= 1
            
            # Limpa o ficheiro de estado para o próximo ciclo
            try:
                os.remove(STATE_FILE)
            except:
                pass
            continue # Volta ao topo do 'while True' e recomeça
        else:
            print(f"\n[AVISO] Automacao interrompida. Revisa logs.")       
            break
    
    input("\nPressione Enter para sair...")

if __name__ == "__main__":
    main()
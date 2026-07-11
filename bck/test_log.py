import os
import glob
import time
import json

# Caminho padrão dos logs do E:D
LOG_DIR = os.path.expanduser('~') + r"\Saved Games\Frontier Developments\Elite Dangerous"

def get_latest_log():
    list_of_files = glob.glob(os.path.join(LOG_DIR, 'Journal.*.log'))
    if not list_of_files:
        raise Exception("Nenhum log encontrado!")
    return max(list_of_files, key=os.path.getctime)

def monitor_log():
    latest_log = get_latest_log()
    print(f"Monitorando log: {latest_log}")
    
    with open(latest_log, 'r', encoding='utf-8') as f:
        # Pula para o final do arquivo
        f.seek(0, 2)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.5)
                continue
            
            # Extrai o JSON e imprime o evento
            try:
                data = json.loads(line)
                event = data.get('event')
                print(f"[EVENTO DETECTADO]: {event}")
                
                # Exemplo de trigger:
                if event == "SupercruiseEntry":
                    print("--> Bot sabe que entramos em Supercruise!")
            except json.JSONDecodeError:
                pass

if __name__ == "__main__":
    monitor_log()
#!/usr/bin/env python3
"""
los_calibrar.py — Calibrador do LOS Checker (por sistema)

Corre este script quando tiveres informação visual do jogo sobre
o estado actual (oclusos ou visíveis). Deteta automaticamente o
sistema estelar actual (via Journal) e guarda a observação dentro
de sistemas[<sistema>]["observacoes"] em los_calibracao.json —
nunca mistura observações de sistemas diferentes (ex.: Fujin vs
Kamitra).
"""

import json, os
from datetime import datetime, timezone

from los_checker import obter_sistema_atual

ED_LOG_DIR = os.path.expanduser('~') + r"\Saved Games\Frontier Developments\Elite Dangerous"

OBRIGATORIOS = ['raio_planeta_m', 'semi_eixo_estacao_m', 'semi_eixo_carrier_m',
                'periodo_estacao_s', 'periodo_carrier_s']


def main():
    print("=" * 50)
    print("  LOS CALIBRADOR — por sistema")
    print("=" * 50)
    print()

    sistema = obter_sistema_atual(ED_LOG_DIR)
    if not sistema:
        print("❌ Não foi possível detetar o sistema actual (Journal ilegível ou sem StarSystem).")
        print("   Certifica-te que o jogo já escreveu pelo menos um evento FSDJump/Location/CarrierJump.")
        return

    print(f"Sistema detetado: {sistema}")
    print()
    print("Estado actual do carrier no jogo:")
    print("  1 - Oclusos (carrier atrás do planeta, tracejado)")
    print("  2 - Visível (linha directa livre)")
    print()

    escolha = input("Estado actual (1/2): ").strip()

    if escolha == "1":
        estado = "oclusos"
    elif escolha == "2":
        estado = "visivel"
    else:
        print("Opção inválida.")
        return

    agora = datetime.now(timezone.utc)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    caminho = os.path.join(script_dir, "los_calibracao.json")

    if os.path.exists(caminho):
        try:
            with open(caminho, "r") as f:
                dados = json.load(f)
        except Exception as e:
            print(f"❌ Falha a ler {caminho}: {e}")
            return
    else:
        dados = {"sistemas": {}}

    dados.setdefault("sistemas", {})

    if sistema not in dados["sistemas"]:
        print(f"⚠️  Sistema '{sistema}' ainda não existe em los_calibracao.json — a criar entrada nova (sem constantes orbitais).")
        dados["sistemas"][sistema] = {
            "raio_planeta_m": None,
            "margem_atmosfera_m": 50000,
            "semi_eixo_estacao_m": None,
            "semi_eixo_carrier_m": None,
            "periodo_estacao_s": None,
            "periodo_carrier_s": None,
            "nota": "TODO: por preencher (raio do planeta e orbitas da estacao/carrier).",
            "observacoes": []
        }

    cfg = dados["sistemas"][sistema]
    cfg.setdefault("observacoes", [])

    em_falta = [k for k in OBRIGATORIOS if cfg.get(k) is None]
    if em_falta:
        print()
        print(f"⚠️  Atenção: o sistema '{sistema}' ainda tem constantes orbitais por preencher: {', '.join(em_falta)}.")
        print("   A observação vai ser guardada na mesma, mas o los_checker.py vai continuar a SALTAR")
        print("   a verificação neste sistema até essas constantes serem preenchidas manualmente.")

    observacao = {
        "timestamp_utc": agora.strftime("%Y-%m-%dT%H:%M:%S"),
        "estado": estado,
        "nota": f"Observado manualmente em {agora.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    }
    cfg["observacoes"].append(observacao)

    with open(caminho, "w") as f:
        json.dump(dados, f, indent=4)

    print()
    print(f"✅ Observação guardada em '{sistema}': {caminho}")
    print(json.dumps(observacao, indent=2))
    print()
    print("Agora corre: python3 los_checker.py")


if __name__ == "__main__":
    main()

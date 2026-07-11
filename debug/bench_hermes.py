#!/usr/bin/env python3
"""
bench_hermes.py — Bancada de teste para escolher o modelo local default.

Corre o mesmo conjunto de tarefas REAIS do projeto vasco-r2d2 contra dois
(ou mais) modelos servidos pelo Ollama e valida automaticamente o codigo
gerado (executa e faz asserts). No fim imprime um resumo e grava
bench_results.json para analise.

Uso (a partir de qualquer maquina com acesso ao servidor Ollama na LAN):
    py bench_hermes.py                          # usa OLLAMA_HOST ou localhost
    py bench_hermes.py http://192.168.x.x:11434 # host explicito

Nao precisa de pip install nenhum — so standard library.
"""

import json
import os
import re
import sys
import time
import urllib.request

MODELS = ["qwen3.5:9b", "qwen2.5-coder:14b"]

HOST = (sys.argv[1] if len(sys.argv) > 1
        else os.environ.get("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")

NUM_PREDICT = 1500      # tecto de tokens por resposta
TIMEOUT_S   = 600       # o primeiro load do modelo pode demorar


# ==========================================
# CHAMADA AO OLLAMA
# ==========================================
def gerar(modelo, prompt):
    payload = json.dumps({
        "model": modelo,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": NUM_PREDICT, "temperature": 0.2},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{HOST}/api/generate", data=payload,
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    wall = time.time() - t0
    eval_count = data.get("eval_count", 0)
    eval_dur_s = data.get("eval_duration", 0) / 1e9
    toks = (eval_count / eval_dur_s) if eval_dur_s > 0 else 0.0
    return data.get("response", ""), wall, toks


def extrair_codigo(texto):
    """ Extrai o primeiro bloco ```...``` (ou devolve o texto todo se nao
        houver fences). Remove <think>...</think> de modelos reasoning. """
    texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL)
    m = re.search(r"```(?:python)?\s*(.*?)```", texto, flags=re.DOTALL)
    return (m.group(1) if m else texto).strip()


def executar_e_validar(codigo, validador):
    """ Executa o codigo gerado num namespace isolado e corre o validador.
        Devolve (passou: bool, detalhe: str). """
    ns = {}
    try:
        exec(compile(codigo, "<gerado>", "exec"), ns)
    except Exception as e:
        return False, f"nao compila/executa: {e}"
    try:
        validador(ns)
        return True, "ok"
    except AssertionError as e:
        return False, f"assert falhou: {e}"
    except Exception as e:
        return False, f"erro na validacao: {e}"


# ==========================================
# TAREFAS (retiradas de trabalho real do projeto)
# ==========================================
def v_normalizar(ns):
    f = ns["normalizar_nave"]
    assert f("cobramk3") == "Cobra Mk III", f("cobramk3")
    assert f("CobraMkV") == "Cobra Mk V", f("CobraMkV")
    assert f("cobramk4") == "Cobra Mk IV", f("cobramk4")
    assert f("hauler") == "Hauler", f("hauler")


def v_matches(ns):
    f = ns["extrair_matches"]
    log = ("[MATCH OK] CHARGING: 0.867 (limiar 0.75)\n"
           "lixo qualquer\n"
           "[MATCH --] THROTTLE UP ACTIVE: 0.578 (limiar 0.75)\n"
           "[MATCH OK] NAV TAB: 0.987 (limiar 0.80)\n")
    res = f(log)
    assert len(res) == 3, res
    assert res[0][0] == "CHARGING" and abs(res[0][1] - 0.867) < 1e-9, res[0]
    assert res[1][0] == "THROTTLE UP ACTIVE" and abs(res[1][1] - 0.578) < 1e-9, res[1]
    assert res[2][0] == "NAV TAB" and abs(res[2][1] - 0.987) < 1e-9, res[2]


def v_perfil(ns):
    f = ns["obter_perfil"]
    cfg = {"Cobra Mk V": {"CX_NEUTRO": 48, "CY_NEUTRO": 53}}
    assert f(cfg, "Cobra Mk V") == {"CX_NEUTRO": 48, "CY_NEUTRO": 53}
    assert f(cfg, "Mandalay") is None
    assert f({}, "Cobra Mk V") is None


def v_flags(ns):
    f = ns["flags_ativas"]
    tabela = {"SUPERCRUISE": 0x10, "FSD_MASS_LOCKED": 0x10000, "FSD_CHARGING": 0x20000}
    assert sorted(f(0x30010, tabela)) == ["FSD_CHARGING", "FSD_MASS_LOCKED", "SUPERCRUISE"]
    assert f(0x0, tabela) == []
    assert f(0x10, tabela) == ["SUPERCRUISE"]


TAREFAS = [
    {
        "id": "normalizar_nave",
        "validador": v_normalizar,
        "prompt": (
            "Escreve UMA funcao Python chamada normalizar_nave(nome_cru) que recebe o nome "
            "interno de uma nave do Elite Dangerous e devolve o nome legivel. Regras exatas: "
            "converte nome_cru para minusculas; se contiver 'cobramk3' devolve 'Cobra Mk III'; "
            "se contiver 'cobramk4' devolve 'Cobra Mk IV'; se contiver 'cobramkv' devolve "
            "'Cobra Mk V'; caso contrario devolve nome_cru.title(). "
            "Devolve APENAS o codigo Python num bloco ```python```, sem exemplos de uso."
        ),
    },
    {
        "id": "extrair_matches",
        "validador": v_matches,
        "prompt": (
            "Escreve UMA funcao Python chamada extrair_matches(texto) que recebe um log "
            "multi-linha e devolve uma lista de tuplos (label, valor_float) para cada linha "
            "no formato '[MATCH OK] LABEL: 0.867 (limiar 0.75)' ou '[MATCH --] LABEL: ...'. "
            "O label pode ter espacos (ex.: 'THROTTLE UP ACTIVE'). O valor e o primeiro "
            "numero a seguir aos dois pontos, nao o limiar. Mantem a ordem das linhas. "
            "Devolve APENAS o codigo Python num bloco ```python```."
        ),
    },
    {
        "id": "obter_perfil",
        "validador": v_perfil,
        "prompt": (
            "Escreve UMA funcao Python chamada obter_perfil(config, nave) que recebe um dict "
            "de calibracoes por nave e o nome de uma nave, e devolve config[nave] se existir "
            "ou None caso contrario. Nao uses excepcoes, usa .get(). "
            "Devolve APENAS o codigo Python num bloco ```python```."
        ),
    },
    {
        "id": "flags_ativas",
        "validador": v_flags,
        "prompt": (
            "Escreve UMA funcao Python chamada flags_ativas(flags, tabela) que recebe um "
            "inteiro de bitmask 'flags' e um dict {nome: bit} e devolve a lista de nomes cujo "
            "bit esta ativo em flags (usando AND bit a bit). A ordem pode ser qualquer. "
            "Devolve APENAS o codigo Python num bloco ```python```."
        ),
    },
    {
        "id": "resumo_log",
        "validador": None,  # revisao manual
        "prompt": (
            "Resume em 3 frases, em portugues, o que aconteceu neste log de automacao:\n\n"
            "[ETAPA 11] SUPERCRUISE: Supercruise assistido\n"
            "[LOG] A enviar 'j' (iniciar salto) + 'right shift' (acelerar)...\n"
            "[MATCH OK] CHARGING: 0.899 (limiar 0.75)\n"
            "[FLAGS] 0x49020008 -> FSD_CHARGING\n"
            "[OK] Motor FSD em carga confirmada pela telemetria.\n"
            "[MATCH OK] NAV TAB: 0.987 (limiar 0.80)\n"
            ">>> Ativando Assistencia (Space)...\n"
            ">>> CHEGADA CONFIRMADA! A executar travagem e boost...\n"
            "[SUCESSO] Etapa SUPERCRUISE concluida!\n"
        ),
    },
]


# ==========================================
# EXECUCAO
# ==========================================
def main():
    print("=" * 60)
    print(f"  BENCH HERMES — host: {HOST}")
    print(f"  modelos: {', '.join(MODELS)}")
    print("=" * 60)

    resultados = []
    for modelo in MODELS:
        print(f"\n### MODELO: {modelo}")
        for tarefa in TAREFAS:
            print(f"  - {tarefa['id']} ... ", end="", flush=True)
            try:
                resposta, wall, toks = gerar(modelo, tarefa["prompt"])
            except Exception as e:
                print(f"ERRO de rede/servidor: {e}")
                resultados.append({"modelo": modelo, "tarefa": tarefa["id"],
                                   "passou": None, "detalhe": f"erro rede: {e}"})
                continue

            if tarefa["validador"] is None:
                passou, detalhe = None, "revisao manual"
            else:
                codigo = extrair_codigo(resposta)
                passou, detalhe = executar_e_validar(codigo, tarefa["validador"])

            estado = {True: "PASSA", False: "FALHA", None: "manual"}[passou]
            print(f"{estado} ({wall:.1f}s, {toks:.1f} tok/s) {'' if passou else '- ' + detalhe}")
            resultados.append({
                "modelo": modelo, "tarefa": tarefa["id"], "passou": passou,
                "detalhe": detalhe, "segundos": round(wall, 1),
                "tokens_por_segundo": round(toks, 1), "resposta": resposta,
            })

    # Resumo
    print("\n" + "=" * 60)
    print("  RESUMO")
    print("=" * 60)
    for modelo in MODELS:
        do_modelo = [r for r in resultados if r["modelo"] == modelo]
        autos = [r for r in do_modelo if r["passou"] is not None]
        passa = sum(1 for r in autos if r["passou"])
        vels = [r["tokens_por_segundo"] for r in do_modelo if r.get("tokens_por_segundo")]
        vel_media = sum(vels) / len(vels) if vels else 0
        print(f"  {modelo}: {passa}/{len(autos)} tarefas automaticas, "
              f"~{vel_media:.0f} tok/s medio")

    saida = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bench_results.json")
    with open(saida, "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False)
    print(f"\nDetalhe completo (incluindo respostas para revisao manual): {saida}")


if __name__ == "__main__":
    main()

# AGENTS.md — vasco-r2d2

Contexto fixo para qualquer LLM local (Hermes / `hermes -z`) chamado para tarefas
neste projeto. O objetivo é reduzir alucinação: preferimos "não sei, falta-me
contexto" a uma resposta inventada. Um erro aqui não é cosmético — controla
automação em tempo real dentro do Elite Dangerous, e um bug mau custa uma
sessão de jogo.

## O que é este projeto

vasco-r2d2 é uma suite de automação de **navegação/autopilot** para o Elite
Dangerous, em Python, usando captura de ecrã (`mss`), template matching
(`cv2`/OpenCV), teclas simuladas (`pydirectinput`), deteção de teclas
(`keyboard`) e leitura do Journal/`Status.json` do jogo. Replica automações
que **já existem no próprio jogo** (Supercruise Assist, Auto-Docking,
Auto-Launch) — **não é** automação de combate/mira, e qualquer tarefa que
pareça ir nessa direção deve ser recusada e sinalizada, não silenciosamente
ignorada nem "interpretada".

## Mapa dos ficheiros principais

- `vasco.py` — orquestrador. Uma `SEQUENCE` de 12 passos (1-indexed) corre
  cada script como subprocesso, com estado persistido em
  `logs/vasco_state.json` (`last_step`, `completed_steps`). Modo `a`
  (auto-cíclico) recomeça o ciclo sozinho ao terminar com sucesso.
- `olho.py` / `debug/zolho-teste.py` — centragem da bússola/HUD via cor
  (HSV mask) e correção por impulsos de teclas. `zolho-teste.py` é a
  ferramenta de calibração manual (não tem deteção automática de rebordo —
  removida de propósito, a centragem é sempre feita à mão).
- `coordenadas_bussola.json` — calibração por nave (`MONITOR_CONFIG`,
  `CX_NEUTRO`/`CY_NEUTRO`), chave = nome normalizado da nave.
- `supercruise_assist.py` — inicia o salto FSD e ativa o Supercruise Assist
  do menu do jogo, validado por polling de `Status.json` (flags de bitmask),
  não por sleeps cegos.
- `docking.py`, `undocking.py`, `vender.py`, `select_target.py`,
  `comprar.py` — cada um automatiza uma ação pontual do jogo.
- `los_checker.py` / `los_calibrar.py` / `los_calibracao.json` — simulação
  orbital para prever janelas de linha-de-visão estação↔carrier, **chaveada
  por sistema estelar** (`sistemas.<nome>`). Nunca aplicar constantes
  orbitais de um sistema a outro.

## Convenções a preservar

- Prints/logs de utilizador ficam em **português**, com prefixos `[TAG]`
  (`[INFO]`, `[LOG]`, `[SUCESSO]`, `[AVISO]`, `[ERRO]`, `[MATCH OK/--]`,
  etc.) — segue o estilo já existente no ficheiro, não inventes um novo.
- Template matching passa sempre por uma função `procurar_template(...)`
  com um parâmetro `debug` que imprime `[MATCH OK/--] {label}: {valor:.3f}
  (limiar {threshold:.2f})`. Novos matches seguem o mesmo padrão.
- Thresholds de matching são **calibrados empiricamente** (ver
  `debug/check_station_match.py`), nunca adivinhados. Não alteres um
  threshold existente sem dados a justificar.
- Ficheiros de calibração/estado são JSON simples, chaveados por
  nave/sistema/etc. — segue a estrutura já usada no ficheiro em vez de
  propor um esquema novo.
- `subprocess.Popen` para scripts filhos usa sempre `sys.executable "-u"`
  (stdout sem buffer) — já corrigimos um bug real de buffering; não remover.

## Regras rígidas

1. **Não inventes nomes de função, ficheiro ou API que não estejam no
   prompt.** Se a tarefa referir algo que não vês, diz explicitamente que
   falta contexto — não adivinhes a assinatura.
2. **Só tocas no que te foi pedido.** Devolve a função/diff pedido, não o
   ficheiro inteiro reescrito, a menos que seja explicitamente pedido.
3. **Não alteres keybinds, thresholds, timings ou constantes orbitais**
   sem que estejam explicitamente no prompt como algo a mudar — estes
   valores vêm de calibração real em jogo, não são arbitrários.
4. Se a tarefa pedida exigir memória de decisões anteriores da conversa
   (ex.: "porque é que isto falhou da última vez", diagnóstico cruzando
   vários ficheiros/subprocessos), **não tentes resolver sozinho** — devolve
   uma resposta curta a dizer que isto excede o âmbito de uma chamada sem
   contexto histórico, para ser escalado ao Claude.
5. Termina sempre a resposta com uma linha `ASSUNÇÕES:` a listar o que
   assumiste (ex.: nome exato de uma variável, tipo de retorno) para que
   seja fácil verificar antes de aplicar o código.

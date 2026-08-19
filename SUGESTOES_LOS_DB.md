# Sugestões de melhoramentos — LOS partilhado via BD (Claude, 2026-07-11)

Notas deixadas depois de aplicar as instruções de `temp/instrucoes_los_windows.md`
e de migrar as 18 observações do JSON para a BD. Nenhuma é urgente; estão por
ordem de valor.

## 1. Índice único na tabela (dedup ao nível da BD)

O schema atual usa `id SERIAL` como chave, por isso nada impede duas linhas
iguais (ex.: correr a migração noutra máquina, ou dois registos no mesmo
segundo). O `migrar_los_para_db.py` protege-se com `WHERE NOT EXISTS`, mas o
mais robusto é a própria BD garantir:

    CREATE UNIQUE INDEX IF NOT EXISTS ux_los_obs
        ON los_observacoes (sistema, timestamp_utc, estado);

Correr uma vez no lado Linux. Depois disto, os INSERTs duplicados falham
sozinhos e o código pode simplificar-se para `ON CONFLICT DO NOTHING`.

## 2. Identificar o carrier (invalidação quando ele salta)

A oclusão é entre a estação e UM carrier específico num slot orbital
específico. Se o Zahir saltar (mesmo dentro de Fujin, para outro slot),
todas as observações anteriores ficam inválidas — mas a BD não tem como
saber. Sugestão: coluna `carrier TEXT` (nome ou callsign) e, no futuro, um
listener do evento `CarrierJump` no Journal que marque as observações
antigas como `invalidada = true` em vez de as apagar.

## 3. Observações de TRANSIÇÃO valem 10x mais

Um "visivel" avulso quase não restringe a fase (a janela de oclusão é
estreita, ~±10°); um par oclusos→visivel com minutos de intervalo (como o
de 2026-07-11 08:39→08:52) fixa a fase quase sozinho. Sugestão: opção
"3 - Transição (mudou agora mesmo)" no los_calibrar.py, guardada com estado
'transicao' + nota do sentido. A regressão pode dar-lhe peso extra (o CHECK
da tabela precisa de aceitar o valor novo).

## 4. Registo automático de observações (zero esforço humano)

O olho.py e o supercruise_assist.py já "veem" o alvo: quando o target do
HUD aparece tracejado (oclusos) ou nítido (visível) com o carrier
selecionado, podiam inserir a observação na BD sozinhos, com nota
'automatica'. Cada viagem do vasco passaria a calibrar o modelo sem ninguém
carregar em nada. (Cuidado: validar com threshold alto para não envenenar a
BD com falsos positivos — talvez exigir N frames consecutivos.)

## 5. Constantes orbitais também na BD

As constantes (raio do planeta, semi-eixos, períodos) continuam no
los_calibracao.json local de cada máquina — podem divergir entre PCs sem
ninguém dar conta. Uma tabela `los_sistemas` na mesma BD (sistema PK,
constantes, estacao, carrier, nota) tornava a BD a única fonte de verdade e
o JSON desaparecia de vez. O los_checker.py já só precisaria do .env.

## 6. Deriva do período do carrier

O periodo_carrier_s=74431 foi medido empiricamente; um erro de 1% desloca a
previsão ~17 min/semana com época fixa na observação mais antiga. Com as
duas máquinas a alimentar a BD isto quase se resolve sozinho (a regressão
re-ancora), mas se as observações antigas começarem a "não bater certo" com
as novas, o suspeito é o período — vale a pena re-medir no system map ou
ajustar também o período na regressão (2 parâmetros: fase + período).

## 7. Modelo 3D (só se o 2D começar a falhar)

O modelo assume órbitas coplanares. Se estação e carrier tiverem
inclinações diferentes, o 2D prevê oclusões que não acontecem (a linha de
visão passa "por cima" do planeta). Sinal de alarme: observações 'visivel'
sistematicamente erradas pelo modelo nas janelas previstas de oclusão. A
correção é acrescentar inclinação/nó ascendente às EntidadeOrbital — mais 2
parâmetros por corpo, só justificável com muitas observações na BD.

## 8. utcnow() deprecado

`datetime.utcnow()` está deprecado desde o Python 3.12. Quando fizerem
upgrade, trocar por `datetime.now(timezone.utc)` — mas atenção que isso
torna os datetimes "aware" e obriga a rever as comparações com os
timestamps naive (o _obter_observacoes_db já converte para naive UTC de
propósito, para manter tudo consistente).

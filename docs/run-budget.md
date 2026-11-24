# Orçamento de execuções de campanhas pré-registadas

`scripts/run_budget.py` impede que um erro de um agente ou da orquestração ultrapasse o orçamento aprovado de uma campanha pré-registada. O limite é verificado **antes** de cada lançamento, sobre o **tamanho do plano**, e acumula entre invocações, pastas de saída e worktrees. Nasceu do incidente descrito em [`docs/incidents/2026-11-23-m10-run-cap.md`](incidents/2026-11-23-m10-run-cap.md).

## Âmbito

- Aplica-se às campanhas pré-registadas, cada uma com um identificador (`campaign_id`) e um limite total.
- Não altera `scripts/run_campaign.py` nem os outros scripts limitados por invocação. `tests/test_run_budget.py` mantém uma lista de ficheiros de `scripts/` autorizados a lançar processos sem passar por `run_budget`, cada um com a razão. Um script novo que lance processos tem de usar `run_budget` ou entrar nessa lista numa alteração revista.
- Não altera `crates/` nem `exec/`, por isso não afeta os hashes canónicos.
- O ramo `research/m10-redesign` é anterior a esta salvaguarda e não foi migrado.

## Declarar um orçamento

Criar `budgets/<campaign_id>.json` (identificador em minúsculas, dígitos, `-` e `_`), registado em commit e sem alterações pendentes:

```json
{
  "schema": "vvlab-run-budget/1",
  "campaign_id": "exemplo-m20",
  "max_runs": 45000,
  "allowed_seeds": [[5000, 5099]],
  "preregistration": {"path": "docs/exemplo-preregisto.md", "commit": "abc1234"},
  "created": "2026-11-24"
}
```

`reserve` recusa quando:

- o manifesto não existe em HEAD ou não é byte a byte igual ao blob de HEAD (alteração por registar em commit);
- falta um campo, há um campo desconhecido ou um valor inválido;
- uma semente está fora de `allowed_seeds`, ou dentro de um intervalo protegido: os de `exec/src/seeds.rs` (lidos do texto do ficheiro; se não se encontrar nenhum, recusa) mais 44000 a 44999 (reserva M13), 50000 a 59999 (M14, gasta) e 81000 a 81999 (bloco candidato do G3). Um intervalo permitido que cubra um protegido não o liberta;
- o total já reservado mais o pedido excede `max_runs`.

## Como os scripts o usam

Preferir `run_budgeted`, que reserva e só depois chama a função de lançamento injetada, uma vez por execução reservada:

```python
import run_budget

plan = [{"seed": s, "arm": a} for s in range(5000, 5100) for a in arms]   # n = len(plan)
outcomes = run_budget.run_budgeted("exemplo-m20", plan, spawn_one, label="etapa 2", jobs=8)
```

`n` é sempre o tamanho do plano; não existe parâmetro para um número escrito à mão. Cada elemento do plano é uma semente inteira ou um dicionário com a chave `seed`. Uma exceção de `spawn_one` fica em `Outcome.error`; a execução continua a contar. Quem precisar de lançar fora do `run_budgeted` tem de chamar `run_budget.reserve(campaign_id, plan, label)` antes de qualquer lançamento e lançar apenas o que reservou.

Regras:

- **Sem reembolsos.** Execuções falhadas, descartadas ou repetidas contam.
- **Registo fora das pastas de saída.** O registo JSONL de só acréscimo fica em `<git-common-dir>/vvlab-budget/<campaign_id>.jsonl`, partilhado por todas as worktrees, sob um bloqueio exclusivo entre processos. Cada linha encadeia o hash da anterior; uma linha alterada, truncada ou incompleta faz o registo falhar fechado.
- **Sem opção nem variável de ambiente** para mudar a localização do registo; só os testes a indicam, por argumento de função.
- **Determinismo.** O registo (incluindo data e `pid`) nunca entra em artefactos com hash nem em identificadores de execução.

## Adendas

Para subir o limite, fazer um novo commit do manifesto com `max_runs` maior e uma entrada em `amendments`:

```json
"max_runs": 50000,
"amendments": [{"max_runs": 50000, "reason": "razão concreta", "date": "2026-11-25"}]
```

Os `max_runs` das adendas têm de crescer, o último tem de coincidir com `max_runs` e a razão não pode estar vazia. Subir `max_runs` sem adenda é recusado assim que o registo já tiver visto um limite menor. O total acumulado transita; só o teto muda. O responsável pode proteger `budgets/**` com uma regra de permissões ou com proteção de ramo; esta salvaguarda **não consegue verificar** que o commit de uma adenda foi aprovado por ele.

## Contagem a partir dos artefactos

Antes de escrever um relatório, chamar:

```python
run_budget.guard_report("exemplo-m20", [raiz_a, raiz_b], declared_unrecorded=0)
```

Conta um ficheiro `verification.json` por execução (outro nome com `marker=`) e recusa se a contagem exceder `max_runs` ou se contagem mais `declared_unrecorded` for diferente do total do registo. `declared_unrecorded` é o número de execuções reservadas sem artefacto (falhadas, descartadas, apagadas); fica visível no relatório. É um controlo detetivo, na linha da regra do repositório de recalcular em vez de confiar em conclusões guardadas. Pastas sobrepostas, ou que contenham o registo, são recusadas.

## O que não protege

- Um agente que edite `scripts/run_budget.py`, os testes, o registo ou a pasta `vvlab-budget`, ou que lance `vv-rocket` e outros binários diretamente, sem passar por `run_budget`. A lista de lançamento do teste só vê importações e chamadas diretas na árvore `scripts/`; não vê `desktop/`, comandos de shell nem execuções à mão.
- A aprovação de um manifesto ou de uma adenda: o commit prova que o ficheiro existe, não quem o aprovou.
- A contagem a partir dos artefactos não vê execuções cujos artefactos foram apagados, a menos que sejam declaradas; só deteta.
- Uma máquina diferente tem o seu próprio registo (o registo vive no repositório local, não é publicado).

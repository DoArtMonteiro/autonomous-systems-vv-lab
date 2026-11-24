# Orçamento de execuções de campanhas pré-registadas

`scripts/run_budget.py` impede que um erro de um agente ou da orquestração ultrapasse o orçamento aprovado de uma campanha pré-registada. O limite é verificado **antes** de cada lançamento, sobre o **tamanho do plano**, e acumula entre invocações, pastas de saída e worktrees. Nasceu do incidente descrito em [`docs/incidents/2026-11-23-m10-run-cap.md`](incidents/2026-11-23-m10-run-cap.md).

## Âmbito

- Aplica-se às campanhas pré-registadas, cada uma com um identificador (`campaign_id`) e um limite total.
- Não altera `scripts/run_campaign.py` nem os outros scripts limitados por invocação. `tests/test_run_budget.py` mantém uma lista de ficheiros de `scripts/` autorizados a lançar processos sem passar por `run_budget`, cada um com a razão. Um script novo que lance processos tem de usar `run_budget` ou entrar nessa lista numa alteração revista.
- Não altera `crates/` nem `exec/`, por isso não afeta os hashes canónicos.
- O ramo `research/m10-redesign` é anterior a esta salvaguarda e não foi migrado.

## Declarar um orçamento

Criar `budgets/<campaign_id>.json` (identificador em minúsculas, dígitos, `-` e `_`), registado em commit e sem alterações pendentes. `.gitattributes` fixa `*.json` com `eol=lf`, por isso a comparação byte a byte resiste a `core.autocrlf` (há um teste):

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

A reserva recusa quando:

- o manifesto não existe em HEAD ou não é byte a byte igual ao blob de HEAD (alteração por registar em commit);
- falta um campo, há um campo desconhecido ou um valor inválido;
- outro manifesto em `budgets/` (em HEAD) tem o mesmo `preregistration.path` ou intervalos de sementes que se sobrepõem. Cada entrada do registo guarda o caminho do pré-registo, os intervalos de sementes e o número de adendas, e a reserva recusa um identificador cujo pré-registo ou sementes coincidam com os de outro registo do mesmo diretório. Um histórico que apague ou renomeie qualquer `budgets/*.json` (`git log --full-history`) recusa todas as campanhas, sem exceção prevista: um identificador novo não repõe o registo de outra campanha. Campanhas que partilham sementes são uma só campanha, alterada por adenda. Um manifesto ou registo vizinho ilegível também recusa;
- uma semente está fora de `allowed_seeds`, ou dentro de um intervalo protegido. Os intervalos de `exec/src/seeds.rs` são lidos do blob em HEAD, por análise estrita: todos os literais `Protected { start, end, reason }` têm de ter inteiros decimais com `start <= end`; um formato diferente (hexadecimal, expressão, campos trocados), nenhum literal ou a falta de 3000-3099, 6000-6099 ou 44000-44999 recusa. A isto juntam-se 3000-3099, 6000-6099, 44000-44999 (reserva M13), 50000-59999 (M14, gasta) e 81000-81999 (bloco candidato do G3), fixos no módulo. Um intervalo permitido que cubra um protegido não o liberta;
- o total já reservado mais o pedido excede `max_runs`.

As variáveis `GIT_*` são retiradas do ambiente de todas as chamadas a `git`, para que não redirecionem o repositório lido.

## Como os scripts o usam

Usar `run_budgeted`, que reserva e só depois chama a função de lançamento injetada, uma vez por execução reservada:

```python
import subprocess
import run_budget

plan = [{"seed": s, "arm": a} for s in range(5000, 5100) for a in arms]   # n = len(plan)

def spawn_one(item):
    return subprocess.run([...], capture_output=True)   # todo o lançamento fica aqui

outcomes = run_budget.run_budgeted("exemplo-m20", plan, spawn_one, label="etapa 2", jobs=8)
```

`n` é sempre o tamanho do plano; não existe parâmetro para um número escrito à mão. Cada elemento do plano é uma semente inteira ou um dicionário com a chave `seed`. Uma exceção de `spawn_one` fica em `Outcome.error`; a execução continua a contar.

A API pública (`reserve`, `run_budgeted`, `ledger_total`, `recount`, `guard_report`) **não aceita** repositório nem diretório do registo, e não há opção nem variável de ambiente para os mudar. As funções com prefixo `_` existem só para os testes (há um teste das assinaturas).

O teste de lançamento exige que um script que importe `run_budget` chame `run_budgeted` e que todo o lançamento (`subprocess`, `os.system`, `os.spawn*`, `os.exec*`, `multiprocessing`, `ProcessPoolExecutor`, `importlib`, `__import__`) fique dentro da função passada em `spawn=`. Quem só use `reserve` e lance por fora falha esse teste, salvo entrada justificada na lista.

Regras:

- **Sem reembolsos.** Execuções falhadas, descartadas ou repetidas contam.
- **Registo fora das pastas de saída.** O registo JSONL de só acréscimo fica em `<git-common-dir>/vvlab-budget/<campaign_id>.jsonl`, partilhado por todas as worktrees, sob um bloqueio exclusivo entre processos. Cada linha encadeia o hash da anterior; o diretório é sincronizado quando o registo é criado, onde o sistema o permite.
- **Registo de ponta.** Um segundo ficheiro de só acréscimo, `<campaign_id>.tip`, guarda o `seq` e o hash de cada linha escrita. Uma reserva é recusada se o registo estiver atrás da ponta (linhas finais ou ficheiro apagados) ou divergir dela.
- **Determinismo.** O registo (incluindo data e `pid`) nunca entra em artefactos com hash nem em identificadores de execução.

## Adendas

Para subir o limite, fazer um novo commit do manifesto com `max_runs` maior e uma entrada nova em `amendments`:

```json
"max_runs": 50000,
"amendments": [{"max_runs": 50000, "reason": "razão concreta", "date": "2026-11-25"}]
```

Os `max_runs` das adendas têm de crescer, o último tem de coincidir com `max_runs` e a razão não pode estar vazia. O histórico git do ficheiro (`--full-history`) é verificado em cada reserva, e o último registo guarda `max_runs` e o número de adendas: um `max_runs` maior só é aceite com mais adendas do que as registadas, o que cobre históricos órfãos, superficiais ou reescritos. Em cada reserva: cada versão anterior tem de ser prefixo da seguinte, `max_runs` não pode descer e só pode subir com uma adenda nova. Apagar e recriar o manifesto, ou reescrever uma adenda, é recusado. O total acumulado transita; só o teto muda. O responsável pode proteger `budgets/**` com uma regra de permissões ou com proteção de ramo; esta salvaguarda **não consegue verificar** que o commit de uma adenda foi aprovado por ele.

## Contagem a partir dos artefactos

Antes de escrever um relatório, chamar:

```python
run_budget.guard_report("exemplo-m20", [raiz_a, raiz_b],
                        declared_unrecorded=2, unrecorded_run_ids=["r-0041", "r-0042"])
```

Conta um ficheiro `verification.json` por execução (outro nome com `marker=`) e recusa se a contagem exceder `max_runs` ou se contagem mais `declared_unrecorded` for diferente do total do registo. `unrecorded_run_ids` lista os identificadores das execuções reservadas sem artefacto (falhadas, descartadas, apagadas); o seu tamanho tem de ser igual a `declared_unrecorded`, sem repetidos, e ambos ficam no relatório. É um controlo **detetivo**: deteta um excesso líquido de execuções face ao registo, não identifica qual execução ficou fora dele. Pastas sobrepostas, ou que contenham o registo, são recusadas.

## Recuperação manual de uma linha final truncada

Uma falha a meio da escrita pode deixar a última linha do registo ou da ponta sem `\n`; a reserva recusa então com «linha final incompleta». A reserva é escrita e sincronizada **antes** de qualquer lançamento, por isso uma linha truncada significa que essas execuções não chegaram a ser lançadas. Recuperação, com decisão do responsável: confirmar que nenhum processo da campanha está a correr, cortar o ficheiro afetado até ao último `\n` (registo e ponta, se ambos estiverem truncados), e voltar a correr `guard_report`. Uma ponta que tenha ficado atrás do registo (a falha deu-se entre as duas escritas) é aceite e reposta na reserva seguinte.

## O que não protege

- Um agente que edite `scripts/run_budget.py`, os testes, o registo ou a pasta `vvlab-budget`, ou que lance `vv-rocket` e outros binários diretamente, sem passar por `run_budget`.
- **Apagar o registo e a ponta, os dois, repõe o orçamento sem aviso.** O mesmo vale para truncar as mesmas linhas finais do registo e da ponta, ou apagar a ponta e depois truncar o registo; só a contagem nos artefactos o pode apanhar. Apagar só as linhas finais ou só um dos ficheiros é detetado pela ponta; reescrever o meio é detetado pela cadeia de hashes. Qualquer destas alterações também só se vê pela contagem nos artefactos, se `guard_report` for chamado.
- A aprovação de um manifesto ou de uma adenda: o commit prova que o ficheiro existe, não quem o aprovou. Alargar `allowed_seeds` num commit posterior só é visível na revisão.
- A contagem nos artefactos não vê execuções cujos artefactos foram apagados, a menos que sejam declaradas com os seus identificadores, e a lista declarada é dita pelo chamador.
- O teste de lançamento só vê importações e chamadas diretas em `scripts/` (com propagação por importação de módulos locais). Não vê `desktop/`, comandos de shell, execuções à mão, `getattr` ou strings avaliadas com `exec`/`eval`, nem as chamadas feitas dentro de módulos locais importados por quem usa `run_budget`.
- O registo vive no repositório local: outra máquina ou clone tem o seu próprio.
- Uma história git reescrita (por exemplo com `push --force` e novo clone) apaga as versões anteriores do manifesto que a verificação de adendas usa.

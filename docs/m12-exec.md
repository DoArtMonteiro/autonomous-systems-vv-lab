# Motor de experiências `vv-exec` (M12)

Estado: **em desenvolvimento**, no ramo `feat/m12-vv-exec`, sobre a auditoria do M12 (PR 17). Nada foi integrado em `main`. Este documento descreve o que está implementado e medido. Não altera o modelo, as sementes protegidas, as configurações aprovadas nem as evidências do M6 e do M10.

## O que existe

`exec/` é um espaço de trabalho Rust separado, como `crates/vv-rocket` e `desktop/`. Liga `vv-rocket` como biblioteca e chama só as suas funções públicas, as mesmas que a linha de comandos usa. O pacote raiz, o seu `Cargo.lock`, os hashes do M1 e o `source_sha256` de `vv-rocket` não mudam.

| Componente | Ficheiro | Função |
|---|---|---|
| Especificação `vv-experiment.v1` | `exec/src/spec.rs` | Esquema com `deny_unknown_fields`; validação de nomes, unidades, intervalos, sementes e limites antes de qualquer execução |
| Sementes | `exec/src/seeds.rs` | Lista, intervalo ou derivação SplitMix64 a partir da identidade da experiência; recusa a experiência inteira se uma semente tocar 3000 a 3099 ou 6000 a 6099 |
| Planeador | `exec/src/plan.rs` | Desenhos único, fatorial, hipercubo latino e Saltelli; braços como substituições de ponteiros JSON; validação canónica de cada caso; ordem total e `plan_sha256` |
| Motor | `exec/src/engine.rs` | Execução em processo, registo `log.jsonl` com hash por linha, retoma, `records.jsonl` ordenado por índice, retenção por política, bloqueio de escritor único e verificação completa por recálculo |
| Agendador | `exec/src/sched.rs` | Número de trabalhadores em função da memória disponível, dos processadores e dos limites; reavaliado durante a execução |
| Portão de equivalência | `exec/src/equiv.rs` | Amostra fixa reescrita pela linha de comandos canónica e pelo escritor em processo; bytes iguais exigidos |
| Estatística | `exec/src/stats.rs` | Wilson, Clopper-Pearson, McNemar exato, Holm, momentos e índices de Sobol com intervalos por bootstrap |
| Convergência | `exec/src/converge.rs` | Passo a metade, ordem observada e estimativa de Richardson |
| Relatório | `exec/src/report.rs` | Recalculado dos registos; resultado da missão separado dos invariantes; fração dentro do envelope |

Domínios em processo: `rocket-landing` (M9 e M10, `vv-rocket land`) e `rocket-rigid-body` (M8, `vv-rocket run`). O domínio terrestre ainda não tem caminho em processo.

## Comandos

```sh
cargo build --release --manifest-path exec/Cargo.toml
exec/target/release/vv-exec plan exec/examples/m12-dev-throughput.json
exec/target/release/vv-exec run exec/examples/m12-dev-throughput.json --output exec/target/m12-dev/throughput --threads 16
cargo build --release --manifest-path crates/vv-rocket/Cargo.toml --target-dir exec/target/vv-rocket-cli
exec/target/release/vv-exec equiv exec/target/m12-dev/throughput --cli exec/target/vv-rocket-cli/release/vv-rocket --sample 24
exec/target/release/vv-exec report exec/target/m12-dev/throughput
exec/target/release/vv-exec verify exec/target/m12-dev/throughput --threads 16
exec/target/release/vv-exec converge crates/vv-rocket/cases/propulsive_descent.json --levels 4 --tolerance-m 0.001
```

Estado de saída: 0 concluído; 1 portão ou verificação falhou; 3 entrada recusada; 5 execução interrompida (repetir o mesmo comando retoma). O primeiro Ctrl+C pára `run` depois das execuções em curso, que ficam registadas; o segundo termina o processo. O motor recusa qualquer saída dentro de um diretório chamado `runs`, onde estão as execuções históricas do laboratório. A verificação é feita pelo motor, não só pela linha de comandos, e resolve primeiro o antepassado existente mais próximo, por isso um caminho relativo, uma ligação simbólica ou uma junção para `runs` também são recusados.

## Especificação `vv-experiment.v1`

Um ficheiro define a experiência: domínio, caso base, braços, parâmetros, desenho, sementes, envelope, retenção, limites e análise. Exemplo: `exec/examples/m12-dev-throughput.json`.

Validação na fronteira:

- Campos desconhecidos, esquema errado e nomes inválidos são recusados.
- A unidade declarada de um parâmetro tem de coincidir com o sufixo do campo (`_n` N, `_kg` kg, `_m` m, `_mps2` m/s^2, `_s` s, entre outros). Um campo sem unidade no nome, como `faults/0/magnitude`, exige `"unit": "model"`: a unidade e o intervalo são os do modelo.
- Cada caso que o plano vai executar é construído e passa pela validação canónica do domínio (`prepare_landing` ou `model::prepare`) antes de qualquer simulação. A mensagem identifica o braço, a célula, o parâmetro e o campo recusado.
- Tetos fixos: 2 000 000 execuções, 200 000 células, 20 000 diretórios retidos, 16 GiB de artefactos e 24 h. A especificação declara limites iguais ou menores; um desenho com mais execuções do que `limits.max_runs` é recusado.

## Determinismo e retoma

- A ordem total é (braço, célula, réplica). Os trabalhadores tiram trabalho de um contador atómico; cada registo leva o seu índice.
- `log.jsonl` guarda uma linha por execução concluída, na ordem de conclusão: `<sha256> <registo JSON>`, com o hash calculado sobre os bytes do registo. Uma linha final cortada é descartada e executada de novo. Uma linha alterada, repetida ou fora do plano recusa a retoma.
- `records.jsonl` é escrito quando o registo está completo, com as mesmas linhas copiadas por ordem de índice. Os bytes não dependem do número de trabalhadores, de interrupções nem de retomas. Os testes verificam isto com 1, 3, 4 e 8 trabalhadores, com interrupção a meio e com uma linha cortada.
- Uma saída existente só aceita o mesmo `plan_sha256`. O plano inclui o hash da especificação, do caso base, do `source_sha256` do domínio e de cada caso e semente.
- Cada registo chega ao `log.jsonl` numa única escrita, sem memória intermédia, e o ficheiro é sincronizado com o disco no fim. Uma interrupção perde no máximo as execuções em curso.
- Um único escritor por diretório: `run` obtém um bloqueio exclusivo em `.lock`. O sistema operativo liberta-o quando o processo termina, por isso uma falha nunca deixa o diretório bloqueado. Um segundo `run` sobre a mesma saída é recusado antes de escrever.
- Uma inicialização interrompida antes de `plan.json` deixa só as entradas e os seus temporários. Um novo `run` com o mesmo plano aceita esse diretório, confirma que as entradas presentes são byte a byte as do plano e completa-o. Qualquer outro ficheiro, ou uma entrada diferente, é recusado.
- Os hashes por linha detetam danos acidentais, não uma falsificação coerente: quem altera um registo e recalcula o hash passa a leitura. `vv-exec verify <dir>` recalcula em processo todos os registos e rejeita qualquer registo que não se reproduza. Com 16 trabalhadores, as 14 400 execuções da experiência de desenvolvimento verificaram-se em 10,4 s (uma execução), sem diferenças. O teste `a_record_edited_and_rehashed_passes_the_hashes_but_fails_full_verification` falsifica um veredicto com hash recalculado e confirma a rejeição.
- Escritas de `plan.json`, `records.jsonl`, `retained.json` e `report.json`: ficheiro temporário sincronizado com o disco e depois renomeado.
- Os valores reais são lidos pelo `serde_json` sem `float_roundtrip`. Essa funcionalidade tem de ficar desligada: ligada, mudaria a forma como o `vv-rocket` lê os casos neste binário. Por isso, a comparação de um registo recalculado aceita um desvio relativo de 1e-15 nas métricas e exige igualdade exata em hashes, veredictos e erros.

## Agendamento adaptativo

Trabalhadores = mínimo de (processadores lógicos, `--threads`, `limits.max_threads`, (memória disponível menos 1024 MB) a dividir por 40 MB), no mínimo 1. A memória disponível é a menor de física e de compromisso (`GlobalMemoryStatusEx` no Windows, `MemAvailable` no Linux), limitada por `limits.memory_budget_mb`. O trabalhador que conclui cada 256.ª execução reavalia o valor; os trabalhadores acima do valor ficam parados até a memória voltar. Os valores de 40 MB por trabalhador e de 1024 MB de reserva são fixos e não foram medidos sob pressão real de memória; o teste usa uma sonda programada. O teste `memory_pressure_parks_workers_without_changing_records` reduz a memória a meio da execução e confirma que os registos não mudam.

## Retenção

Todas as execuções ficam com hashes, veredictos e métricas em `records.jsonl`. Os artefactos completos só ficam para a política declarada (`failures`, `sample`, `failures_and_sample`). A seleção corre depois de todas as execuções, por ordem de índice, até `max_retained` ou `max_artifact_bytes`, e usa o escritor canónico (`write_landing` ou `write_run`). O hash do traço escrito tem de coincidir com o do registo. Um diretório que ultrapassaria o limite de bytes não chega a ser criado.

## Portão de equivalência

A linha de comandos de cada domínio continua a ser a referência. Para uma amostra fixa (pontas, pontos espaçados e a primeira falha), o portão:

1. escreve os artefactos pela linha de comandos canónica e pelo escritor em processo;
2. compara cada ficheiro byte a byte e indica o primeiro deslocamento diferente;
3. confirma que o registo coincide com os artefactos e que uma nova execução em processo o reproduz;
4. pede à linha de comandos `replay` do diretório em processo e exige `verified`;
5. exige que o `source_sha256` da linha de comandos seja o da biblioteca ligada.

Uma diferença falha o portão. O relatório indica `equivalence_status`: `verified`, `failed`, `not_run` ou `other_plan`. `verified` significa paridade de bytes com a linha de comandos na amostra. Não é uma aceitação científica.

## Estatística verificada de forma independente

- `scripts/m12_stats_reference.py` calcula os valores de referência só com a biblioteca padrão de Python e com algoritmos diferentes dos do motor: Clopper-Pearson por bisseção sobre caudas binomiais em aritmética decimal de 60 dígitos, Wilson com o quantil de `statistics.NormalDist`, McNemar com aritmética racional exata e Holm pela definição.
- `exec/tests/stats_reference.rs` compara o motor com esses valores: 39 intervalos de Clopper-Pearson até 1e-11 relativo (o erro do motor fica abaixo de 5e-13 relativo nestes casos), 39 de Wilson até 1e-8 (limite da aproximação de Acklam), funções de distribuição e McNemar até 1e-12 relativo, Holm até 1e-15. A CI corre estes testes em Linux e Windows (passo `Check, lint and test vv-exec`).
- Independência parcial: Clopper-Pearson, a função de distribuição e McNemar usam algoritmos diferentes dos do motor. Wilson usa a mesma fórmula com outro quantil. Holm segue a mesma definição passo a passo, por isso confirma a implementação, não a definição.
- A exatidão do motor para n grande não está testada: o fixture vai até n = 1000. Numa reprodução do algoritmo do motor feita na revisão independente, o erro relativo da função de distribuição chegou a 2e-9 em n = 1 000 000, pelo cancelamento entre termos de lnΓ. Não muda decisões, mas a tolerância de 1e-12 só está demonstrada até n = 1000.
- `tests/test_m12_stats_reference.py` confirma que o ficheiro de referência é exatamente o que o script produz e que a referência coincide com `scripts/m10_stats.py`, escrito antes e em separado.
- Índices de Sobol: o teste `sobol_indices_recover_the_analytic_ishigami_solution` usa o desenho Saltelli do próprio planeador com N = 16 384 e recupera os seis índices analíticos da função de Ishigami (a = 7, b = 0,1) com erro menor que 0,03. Os valores analíticos vêm das fórmulas fechadas e são confirmados contra os valores publicados (0,3139, 0,4424, 0, 0,5576, 0,4424, 0,2437).

Comparações emparelhadas: mesma célula, mesma réplica e, por isso, mesma semente em dois braços; McNemar exato e correção de Holm sobre todas as comparações do relatório. Não há paragem sequencial.

O relatório declara a natureza da inferência:

- `inference`: sempre exploratória. O motor recusa as sementes de avaliação e de reserva, por isso nenhum valor-p de um relatório `vv-exec` é confirmatório. Os intervalos por braço e por célula são marginais, não simultâneos: num mapa com muitas células, cerca de 5 % dos intervalos a 95 % falham o valor verdadeiro.
- `error_policy`: `errors_count_as_failures`. Uma execução que terminou em erro não cumpriu nenhum requisito e conta como falha nas taxas e nos testes emparelhados. O pré-registo do M10 (secção 10.6) conta-as como erros de execução fora das taxas, por isso um relatório com `errors` maior que zero não é comparável com esse protocolo.
- O bootstrap dos índices de Sobol usa um fluxo SplitMix64 separado do fluxo do desenho com a mesma semente. Os índices são calculados sobre as médias por variante: descrevem E[Y|X], dependem do número de réplicas e o bootstrap não inclui o ruído dentro de cada variante. A cobertura do bootstrap não está testada.

### Contratos do fixture

O fixture tem três contratos separados, cada um com o seu critério.

1. Bytes exatos. `stats-reference.json` é byte a byte a saída de `scripts/m12_stats_reference.py`. Para Clopper-Pearson, a função de distribuição, McNemar e Holm, isto vale em qualquer plataforma e versão de Python por construção: as caudas binomiais usam `decimal` com 60 dígitos e o valor binário exato de cada argumento, sem `log`, `exp` nem `lgamma` da libm e sem somas de floats; McNemar usa `Fraction`; Holm usa só produtos e máximos IEEE, determinísticos. O bloco de Wilson é exceção (ver dependência residual abaixo): os bytes coincidiram em Linux e Windows na CI, mas não são garantidos por construção.
2. Tolerância numérica. `exec/tests/stats_reference.rs` compara o motor com o fixture com as tolerâncias acima, cada uma justificada pelo algoritmo do motor (Acklam para Wilson, inversão da beta incompleta para Clopper-Pearson). A tolerância de Clopper-Pearson passou de 1e-10 absoluto para 1e-11 relativo, mais exigente; as outras não mudaram.
3. Correção matemática. `tests/test_m12_stats_reference.py` verifica que a função de distribuição é o arredondamento correto do valor racional exato, que cada extremo de Clopper-Pearson deixa alpha/2 na cauda, que a referência coincide com `scripts/m10_stats.py` e que os índices de Ishigami satisfazem a decomposição da variância.

Causa da falha de CI corrigida no PR #18 (execução 41642576840): a versão anterior somava em espaço logarítmico com `lgamma`, `log1p`, `exp` e `sum()`. O fixture tinha sido gerado em Windows com Python 3.14. Em Windows, a CI (Python 3.10) divergia porque `sum()` de floats passou a ser compensada no Python 3.12; a divergência foi reproduzida localmente substituindo `sum` por uma soma ingénua. Em Linux, a primeira divergência vinha da libm: glibc e a CRT de Windows arredondam o último bit de forma diferente e a bisseção amplifica essa diferença na fronteira de decisão. Não era um defeito do motor: a versão antiga da referência tinha erro relativo até 3,8e-13 na função de distribuição (por exemplo, P(X <= 250) com n = 1000 e p = 0,25), dentro da tolerância de 1e-12 do teste Rust. A versão decimal coincide com o valor racional exato arredondado. O fixture foi regenerado por mudança documentada do algoritmo, não para absorver a divergência.

Dependência residual: Wilson usa `statistics.NormalDist().inv_cdf`, implementada em C, que chama `log` e `sqrt` da libm. Os testes que substituem funções de `math` não cobrem esta chamada. As duas plataformas da CI produziram os mesmos bytes neste bloco (execução 41648098573); se isso mudar, o teste de bytes exatos falha e a correção é calcular o quantil em decimal, não alargar o contrato.

## Envelopes de validade e convergência

- O envelope declarado é uma lista de intervalos por ponteiro, cada um com a sua origem (`basis`). Cada caso é avaliado no planeamento; as execuções fora do envelope são marcadas e o relatório indica `envelope_declared`, `in_envelope_fraction` e `extrapolated_runs`. Sem envelope declarado, as duas últimas são `null`: nenhuma execução é dada como dentro de um envelope que não existe. Na versão anterior, a ausência de envelope dava 100 % dentro, como em `docs/evidence/m12-exec/report.json`, que foi gerado antes desta correção e não foi reescrito. As taxas agregadas misturam execuções dentro e fora do envelope.
- Convergência por passo a metade no modelo de corpo rígido: o mesmo caso com dt, dt/2, dt/4 e dt/8, posição comparada no último passo grosso comum (velocidade, atitude e massa não são comparadas). O veredicto usa `base_error_estimate_m`, a estimativa de Richardson do erro no passo base, o passo que a experiência executa. `error_estimate_m` é a do passo mais fino e fica só como informação. A versão anterior decidia sobre o erro do passo mais fino, que num método de ordem 4 é cerca de 2^12 vezes menor do que o erro do passo usado. A estimativa usa a ordem esperada 4, mesmo quando a observada é 3,5; nesse caso subestima o erro até cerca de 1,45 vezes. No caso acoplado do estudo de convergência do M8 (dt = 0,04 s), as ordens observadas ficam entre 3,5 e 4,5, como se espera do RK4. No caso `propulsive_descent.json`, as diferenças estão ao nível do arredondamento (abaixo de 1e-12 vezes a posição) e não se calcula ordem; passa pelo limite de erro.
- Com `analysis.convergence_tolerance_m`, o relatório verifica até quatro variantes do plano.

## Resultados medidos

Máquina, sistema e carga externa como na auditoria (`docs/m12-performance-audit.md`): Ryzen 7 7800X3D, 16 fios, 32 GB, Windows 11 Pro 10.0.26300, Rust 1.99.0, sessão de trabalho normal com cerca de 5 GB de memória física livre. Medição com `spikes/m12-perf/jobrun.py`, teto de 4096 MB por job, 3 de novembro de 2026.

Comando: `python spikes/m12-perf/jobrun.py --label vv-exec-14400-t16 --cap-mb 4096 --out exec/target/m12-dev/jobrun-t16.json -- <repo>/exec/target/release/vv-exec.exe run <repo>/exec/examples/m12-dev-throughput.json --output <repo>/exec/target/m12-dev/throughput --threads 16`, e o mesmo com `--threads 1` e `--threads 8`.

Experiência: `m10-nominal.json` (B+) sob seis condições de falha, sementes de desenvolvimento 7000 a 9399, 14 400 execuções; retenção de falhas e de uma amostra, até 200 diretórios.

| Trabalhadores | Ponta a ponta | CPU | Pico de memória | Execuções/s (ponta a ponta) |
|---:|---:|---:|---:|---:|
| 1 | 55,5 s | 54,5 s | 61 MB | 259 |
| 8 | 11,7 s | 67,3 s | 64 MB | 1 226 |
| 16 | 8,4 s | 72,0 s | 67 MB | 1 712 |

- «Ponta a ponta» inclui planeamento e validação dos casos, escrita de `records.jsonl` e retenção de 200 diretórios pelo escritor canónico. Com 16 trabalhadores, a fase de execução mediu 5,6 s (2 567 execuções/s), segundo o resumo do próprio motor.
- A campanha atual pela linha de comandos mediu 117 execuções/s com 16 trabalhadores na auditoria; o motor em processo faz cerca de 15 vezes mais, de ponta a ponta.
- `records.jsonl` tem o mesmo SHA-256 com 1, 8 e 16 trabalhadores (`docs/evidence/m12-exec/records-sha256.txt`).
- Nova medição depois do endurecimento (commit `efa463a`: registo sem memória intermédia, sincronização no fim, bloqueio), mesmo comando e mesma máquina, 3 de novembro de 2026: 16 trabalhadores, 8,3 s ponta a ponta, 5,5 s na fase de execução, 71,9 s de CPU, pico de 67 MB; 1 trabalhador, 52,8 s, pico de 61 MB. O custo do registo sem memória intermédia não se distingue da variação entre execuções. `records.jsonl` mantém o SHA-256 `078b80f0…` registado. A tabela acima é a medição de `e1a2a71`.
- A verificação completa (`vv-exec verify`, 16 trabalhadores) das 14 400 execuções mediu 10,4 s numa execução, fora de `jobrun.py`.
- Portão de equivalência: 25 execuções da amostra, incluindo execuções com veredicto falhado (código de saída 2 da linha de comandos), 0 diferenças, `source_sha256` igual, `replay` verificado (`docs/evidence/m12-exec/equivalence.json`).
- Critério do roteiro (frente 1): campanha de 14 400 execuções em 6 braços em menos de 30 s, com pico abaixo de 1 GB, e amostra de equivalência sem diferenças. Cumprido nesta máquina. A comparação dos agregados com `m10_campaign.py` nas mesmas sementes não foi feita: o script usa as suas grelhas e sementes do M10, que este trabalho não executa.

**Os veredictos em `docs/evidence/m12-exec/report.json` são evidência de paridade do motor em sementes de desenvolvimento. Não são resultados do M10 e não implicam qualquer aceitação.** A decisão sobre o M10 (PR 15) continua com o responsável.

## Limitações materiais

- **O modelo de aterragem fixa o veículo, o ambiente, as condições iniciais, a dispersão, os sensores, os requisitos e dt.** `prepare_landing` recusa qualquer outro valor. Varreduras físicas (massa, empuxo, atmosfera, condições iniciais) só são possíveis no modelo de corpo rígido. No modelo de aterragem, os parâmetros livres são as falhas (tipo, magnitude, início, duração), a política, os ganhos e a navegação. Varrer parâmetros físicos da aterragem exige uma estratégia de compatibilidade validada à parte, que mude o modelo sem invalidar as execuções guardadas do M10.
- **A convergência só se aplica ao corpo rígido.** O passo da aterragem é um valor registado; o relatório indica «não aplicável» e a razão.
- O domínio terrestre ainda não tem caminho em processo.
- Desenho Saltelli com amostragem pseudoaleatória (SplitMix64), não com uma sequência de Sobol de baixa discrepância. Uma sequência de Sobol teria de ser um novo `design.kind`, para não mudar os hashes dos planos existentes.
- Ctrl+C: o tratamento em Linux é testado na CI com `SIGINT` enviado ao processo (`sigint_stops_the_command_line_with_a_whole_log`). Em Windows, o tratador `SetConsoleCtrlHandler` não tem teste automático, porque um evento de consola só chega a um processo filho que partilhe a consola; a lógica de paragem que esse tratador ativa é testada pelo indicador do motor.
- Uma linha final danificada que termina em mudança de linha, ou um final preenchido com zeros, não é reparado: a retoma falha com erro de hash e o diretório tem de ser reparado à mão.
- `equiv` recusa correr se `equivalence/` já existir; uma interrupção a meio do portão obriga a apagar esse diretório. A amostra do portão não inclui execuções terminadas em erro, e só o domínio de aterragem tem teste de paridade automático.
- Uma máquina e uma sessão com outras aplicações abertas; os tempos absolutos variam com a carga.
- Pontos em aberto da segunda revisão independente (03/11/2026, sobre `8d7afce`):
  - `read_records`, `report` e `equiv` não recalculam todos os registos; só `verify` o faz, e nada regista que `verify` correu. O registo não tem cadeia de hashes nem cabeçalho ligado ao plano.
  - `equivalence.json` é escrito sem ficheiro temporário; a pasta-mãe não é sincronizada com o disco depois de um `rename`; o registo não é sincronizado por linha, por isso um corte de energia pode perder execuções contadas como feitas (uma interrupção do processo não perde).
  - Um trabalhador que entre em pânico envenena os mutexes partilhados e termina os outros.
  - O tratador de interrupção cobre Ctrl+C e Ctrl+Break no Windows e `SIGINT` em Unix, não o fecho da consola, `SIGTERM` nem `SIGHUP`; nesses casos o registo fica válido, mas falta o resumo e o código 5.
  - `guard_output` também recusa um checkout dentro de um diretório chamado `runs` (falso positivo assumido) e não tem teste com ligação simbólica ou junção.
  - `retain` obtém o bloqueio do diretório; `equiv` ainda não.
  - O intervalo 100 a 129 (ciclo de cronometragem terrestre, que inclui as sementes reservadas 101 a 112 do M6) não é recusado por `seeds.rs`. O motor só executa domínios do foguetão, por isso o risco é baixo, mas a recusa tem de existir antes do domínio terrestre em processo.

## Portões científicos preservados

- Nenhuma semente de avaliação (3000 a 3099) ou de reserva (6000 a 6099) do M10 foi executada; o motor recusa-as no planeamento.
- O desvio declarado na auditoria (sementes 100 a 129 do ciclo de cronometragem terrestre, que incluem as reservadas 101 a 112 do M6) continua em aberto. Este trabalho não executa o domínio terrestre.
- `crates/vv-rocket`, o pacote raiz, os casos e as evidências do M6 e do M10 não foram alterados. Os testes do pacote raiz, a campanha do M1 e os testes Python passam.
- As saídas do motor ficam em `exec/target/` (ignorado pelo Git); nada é escrito em `runs/`.

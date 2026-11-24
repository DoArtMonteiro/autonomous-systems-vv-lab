# M19.1: duas propostas que mudam hashes, fora do PR de honestidade

Estado: proposta para decisão do responsável. Nenhuma das duas está implementada nem neste ramo nem na PR da M19.1, que só altera a interface (Studio e Cinematic), testes e documentação e deixa idênticos os 542 valores do conjunto que não pode mudar (`docs/evidence/m19/honesty/hash-comparison.json`). Origem: defeitos 2 e 9 de `docs/m19-1-honesty.md` e achados F03 e F09 da passagem de especialistas sobre a 0.18.1 (`docs/usability/expert-walkthrough.md` no ramo da M19.0).

Nota sobre a numeração: o achado F12 dessa passagem (frases de sucesso sem base) já foi corrigido só na interface (defeitos 7 e 8) e não depende destas propostas.

## Mecanismo comum: porque mudam hashes

A identidade de uma corrida é `sha256(canónico{domain, host_sha256, request})[..16]` (`desktop/platform/src/service.rs`, `run_id`, linhas 271 a 279), e `host_sha256` é o SHA-256 do ficheiro executável do anfitrião do domínio, lido no arranque (linhas 153 a 155). Qualquer alteração a um ficheiro compilado no anfitrião, incluindo texto de catálogo, muda o executável e, com ele, os identificadores de todas as corridas desse domínio. As propostas tocam em dois anfitriões:

| Proposta | Anfitrião afetado | Texto de registo muda? |
| --- | --- | --- |
| 1. Frases `expectation` | `vv-domain-rocket` e `vv-domain-ground` | Não (o texto vem do catálogo `describe`, não do registo) |
| 2. Cláusula de `mission_completion` | `vv-domain-ground` | Sim, nas corridas terrestres com resultado `incomplete` |

`vv-domain-ascent` e `vv-domain-reference` não mudam em nenhuma das duas.

## Proposta 1: «safe» e «unsafe» nas frases de demonstração

### Alteração exata

Substituir, nas frases `expectation` (e no texto de `look_at` que repete a mesma expressão), «safe» por «no safety rule broken» e «unsafe» por «a safety rule broken». Antes e depois:

| Ficheiro e linha | Antes | Depois |
| --- | --- | --- |
| `desktop/domain-rocket/src/demos.rs:94` | «The baseline run has no contact and is unsafe (S5_no_powered_ascent fails); ...» | «The baseline run has no contact and breaks a safety rule (S5_no_powered_ascent fails); ...» |
| `demos.rs:125` | «Baseline: hard landing, safe, R1 vertical speed and R2 horizontal speed fail. ...» | «Baseline: hard landing, no safety rule broken, R1 vertical speed and R2 horizontal speed fail. ...» |
| `demos.rs:140` | «Registered bias: hard landing, safe, only R5 position fails. Smaller later bias: hard landing, safe, only R1 vertical speed fails.» | «Registered bias: hard landing, no safety rule broken, only R5 position fails. Smaller later bias: hard landing, no safety rule broken, only R1 vertical speed fails.» |
| `demos.rs:155` | «Threshold 3 m: hard landing, unsafe, R1 vertical speed and S5 no powered ascent fail. Threshold 1 m: hard landing, safe, only R5 position fails.» | «Threshold 3 m: hard landing, a safety rule broken, R1 vertical speed and S5 no powered ascent fail. Threshold 1 m: hard landing, no safety rule broken, only R5 position fails.» |
| `demos.rs:167` | «Hard landing, safe, only R5 position fails.» | «Hard landing, no safety rule broken, only R5 position fails.» |
| `demos.rs:91, 123, 151, 165` (`look_at`) | «... is also unsafe», «Safety stays safe in both runs: ...», «unsafe with the default threshold (S5, powered ascent), safe with 1 m», «Safety stays safe: ...» | «... also breaks a safety rule», «No safety rule is broken in either run: ...», «a safety rule broken with the default threshold (S5, powered ascent), none with 1 m», «No safety rule is broken: ...» |
| `desktop/domain-ground/src/catalog.rs:439` | «... at tick 7, safety safe, all 7 temporal contracts and all 4 safety invariants pass.» | «... at tick 7, no safety rule broken, all 7 temporal contracts and all 4 safety invariants pass.» |
| `catalog.rs:449` (narrativa) | «... a stalled mission and an unsafe run are different results.» | «... a stalled mission and a run that breaks a safety rule are different results.» |
| `catalog.rs:457-458` | «dominant_axis: completed at tick 5, safe, ... safety stays safe, ...» | «dominant_axis: completed at tick 5, no safety rule broken, ... no safety rule is broken, ...» |
| `catalog.rs:469` | «It is safe but cannot reach the waypoint in 14 ticks, so the unsafe motion comes from the faults, ...» | «No safety rule is broken, but it cannot reach the waypoint in 14 ticks, so the motion that breaks a rule comes from the faults, ...» |
| `catalog.rs:480-483` | «... mission incomplete, safety unsafe. ... safety safe, no fallback, ...» | «... mission incomplete, a safety rule broken. ... no safety rule broken, no fallback, ...» |
| `catalog.rs:513-515` | «Exact GPS: mission completed at tick 17, safe. 1 mm of noise: mission incomplete, unsafe, ... completed at tick 16, safe.» | «Exact GPS: mission completed at tick 17, no safety rule broken. 1 mm of noise: mission incomplete, a safety rule broken, ... completed at tick 16, no safety rule broken.» |

Os estados `safe` e `unsafe` dos registos (`safety.status`) não mudam: são vocabulário do contrato (`desktop/platform/src/contract.rs`) e os testes dos anfitriões comparam-nos. Nenhum teste existente compara o texto de `expectation`, só que não está vazio (`desktop/domain-ground/tests/host.rs:656`, `desktop/domain-rocket/tests/demos.rs:34`); os testes de `demos.rs` verificam resultados, não palavras. O texto de `look_at` e `expectation` segue para a Studio por `describe`.

### Valor para o utilizador

Remove a leitura de «safe» como veredicto global ao lado de requisitos falhados («Baseline: hard landing, safe, R1 ... and R2 ... fail»), achado F03 (defeito 9 da M19.1), citado pela Compare como «Expected, stated by the domain», em Run e em Prepare. Hoje a interface acrescenta por baixo a frase «"safe" here means only that no safety rule was broken, and "unsafe" that one was; requirements are separate verdicts.» (`expectationGloss`), que corrige a leitura sem tocar no texto do domínio.

### Impacto na reprodutibilidade

- `host_sha256` do anfitrião do foguetão e do terrestre muda; os dos anfitriões de subida e de referência, de `vv-lab` e de `vv-exec` não mudam.
- Os identificadores mudam para todas as corridas dos domínios `rocket-landing` e `ground-vehicle`: 13 execuções de demonstração do foguetão e 8 das terrestres, e todas as que o utilizador tenha guardado, sempre que o mesmo pedido for corrido de novo.
- Os registos (`record.json`) e os ficheiros nativos não mudam, porque o texto está no catálogo e não no registo; o `record_sha256` das 21 execuções de demonstração fica igual (`hash_set.py` compara-o).
- Hashes de simulador: `source_sha256` de `vv-rocket` e de `vv-ascent` não são afetados (a lista de ficheiros de `source_sha256()` só inclui `crates/vv-rocket` e `crates/vv-ascent`, não `desktop/`); os hashes canónicos do M1 (`scenarios/sha256.json`, `canonical-seed-42.json`) e os golden de `crates/*/tests` e `desktop/domain-*/tests/golden` não são afetados, nem `docs/evidence/m13` a `m18` nem `exec/claims` (as investigações do `vv-exec` usam as bibliotecas, não os anfitriões). Confirmado por pesquisa: `host_sha256` só aparece no código da plataforma, em `provenance.js`/`library.js`, em `desktop/domain-rocket/tests/earlier_build.rs` (calcula a identidade dinamicamente) e como texto narrativo em `docs/evidence/m18/installed-0.18.1/README.md`.

### Migração

- As corridas guardadas mantêm os identificadores antigos e continuam a abrir (o registo está guardado). Um pedido igual corrido depois da atualização cria uma segunda corrida na Library com outro identificador, porque a reutilização (`has_run`) é por identificador; a Compare e o Lab não reconhecem a corrida antiga como «a mesma» e voltam a calcular.
- O replay de uma corrida antiga: o registo é idêntico byte a byte, por isso o replay estrito passa; o relatório indica «recomputed by a different host build» (`service.rs`, verificação da identidade), sem rejeição.
- Comparações guardadas referem identificadores antigos e continuam a abrir.
- Sem commit de rebaseline de evidência: nada de versionado embute estes hashes além de texto narrativo e dos factos de captura de `docs/evidence/m19/honesty` (correspondem a uma compilação e não são reproduzíveis com outro anfitrião, o que já é verdade hoje). Os testes dos anfitriões não fixam hashes. Não é necessário regenerar fixtures.

## Proposta 2: nomear a cláusula falhada de `mission_completion`

### Alteração exata

O registo terrestre diz, para a corrida «1 mm of GPS noise» (corredor, semente 5002): `observed` = «incomplete; 1 of 1 waypoint(s) reached; 0 mm from the goal at the end» e `explanation` = «1 of 1 waypoint(s) were reached when the run ended after 32 ticks; the vehicle was 0 mm (Manhattan) from the goal after 0 tick(s) in fallback.» (`desktop/domain-ground/src/record.rs`, ramo `"incomplete"` das linhas 549 a 555, e requisito das linhas 613 a 634). A análise de missão do simulador dá `incomplete` com todos os pontos alcançados quando o controlador nunca declarou conclusão (`src/mission_analysis.rs`, `completion_tick` nulo e nenhum ponto em falta, linhas 349 a 366); a cláusula falhada é essa. Proposta, só no texto de `explanation` (o texto `observed` não muda, porque `completionFacts` em `requirements.js` o lê e um teste Python o liga a `record.rs`):

| Caso | Antes | Depois |
| --- | --- | --- |
| Todos os pontos alcançados, sem conclusão (`done == total`) | «{done} of {total} waypoint(s) were reached when the run ended after {ticks} ticks; the vehicle was {d} mm (Manhattan) from the goal after {f} tick(s) in fallback.» | «All {total} waypoint(s) were reached, but the controller never declared completion before the run ended after {ticks} ticks, so the requirement needs a completion confirmed on the true position and has none; the vehicle was {d} mm (Manhattan) from the goal after {f} tick(s) in fallback.» |
| Faltam pontos (`done < total`), sem paragem | idem | «{done} of {total} waypoint(s) were reached when the run ended after {ticks} ticks, so the requirement needs {total - done} more; the vehicle was ...» |

`done` e `total` já existem em `mission_result` (linhas 533 e 534); a diferença é uma ramificação nova de `format!` no mesmo ramo. Efeito direto: `outcome.explanation` e `requirements[mission_completion].explanation` (as duas usam a mesma variável `explanation`).

### Valor para o utilizador

Elimina a leitura de «To goal 0.00 mm» ao lado de «Mission incomplete» como contradição (achado F09, defeito 2 da M19.1): o registo passa a dizer que cláusula falhou, para qualquer consumidor (Studio, Library, exportações de evidência, Cinematic), não só para a Studio atual, que já mostra «Recorded: ... The record does not say which part ... failed» a partir do texto observado.

### Impacto na reprodutibilidade

- `host_sha256` do anfitrião terrestre muda (e só ele); o do foguetão não muda por esta proposta.
- Registos: mudam as 3 execuções de demonstração terrestres com resultado `incomplete` (as duas de «delayed-command-after-fallback» e a segunda de «corridor-gps-noise»); as outras 5 mantêm o `record_sha256`. Os ficheiros nativos (`events.json`, `mission.json`, `m4.json`, ...) não mudam, logo os golden de `desktop/domain-ground/tests/golden` (gerados pelo adaptador Python a partir do simulador) não mudam.
- Os identificadores das corridas terrestres mudam todos (mecanismo comum), as completas incluídas.
- Hashes de simulador: sem efeito em `source_sha256` de `vv-rocket`/`vv-ascent`, nos hashes canónicos do M1, em `exec/claims` e em `docs/evidence` (o `exec` corre o simulador terrestre sem passar por `record.rs`).
- Não alterar a versão em `desktop/domain-ground/domain.json` (`0.15.0`): `record.domain.version` faz parte de todos os registos, e mudá-la alteraria também as corridas completas; o hash do anfitrião já distingue as compilações.

### Migração

- As corridas terrestres guardadas com resultado `incomplete` mantêm o texto antigo. O replay estrito de uma delas falha (o texto recomputado difere) e o platform recorre ao replay de «compilação anterior» (`host_sdk::replay_earlier_build`), que compara resultado, segurança, veredictos, telemetria, eventos e métricas e declara que «texts, the scene and the native files are not compared»; o estado passa a «verified against its own record», não «rejected». As corridas completas e paradas repetem-se byte a byte.
- Library e Compare mostram as corridas antigas e novas lado a lado, com textos diferentes para o mesmo pedido; a interface continua a fazer a leitura factual por `completionFacts`, que funciona nas duas.
- Sem rebaseline de evidência versionada. Fixtures a rever: nenhum teste compara `explanation` de `incomplete` (os testes de `host.rs` verificam `outcome.code`, estados e ticks), por isso nada precisa de ser regenerado; acrescentar um teste que verifique a frase nova.

## Alternativas sem impacto nos hashes

- A nota `expectationGloss` (proposta 1) e `completionFacts` com a nota de «To goal» (proposta 2), já implementadas na PR da M19.1: reduzem a leitura errada na Studio, mas não corrigem o texto que a Library, as exportações de evidência e qualquer outro cliente do registo mostram.
- Reescrever o texto só na Studio (substituir «safe» antes de o mostrar) foi rejeitado: a Studio passaria a alterar texto citado como «stated by the domain».

## Recomendação

Fazer as duas num único PR separado, junto com a próxima alteração que já mude os anfitriões, para pagar uma só vez a mudança de identificadores e a nota de migração, e não numa versão dedicada. Se só se puder fazer uma, a proposta 2 tem o melhor valor: corrige o registo para qualquer cliente e só altera três registos de demonstração, enquanto a proposta 1 muda o hash de dois anfitriões para mexer em texto de catálogo que a interface já glosa. Antes de implementar: declarar o impacto nos hashes (esta nota), correr `hash_set.py` antes e depois para confirmar que só mudam `host_sha256` dos anfitriões tocados, os identificadores e, na proposta 2, os três registos nomeados, e acrescentar um teste da frase nova.

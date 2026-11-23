**CORRECTED CANDIDATE — NOT HUMAN-REVIEWED — NOT APPROVED FOR EXECUTION**

# Protocolo de confirmação do G3 com viés GNSS tardio (candidato corrigido M19)

## Estado

**Candidato corrigido. Não congelado, não executado, não aprovado, não revisto por pessoas.** Corrige `docs/m15-g3-onset-protocol.md`, que fica inalterado, tal como o pacote `docs/review/g3-onset/` (os hashes de ambos estão fixados abaixo e o teste `tests/test_m19_g3_power.py` verifica-o). Este documento é uma proposta nova: as decisões marcadas «padrão provisório» não estão tomadas.

O critério G3 do M9.1 não muda. Foi registado e suportado com o viés presente desde 0 s; este protocolo testa hipóteses novas sobre inícios posteriores. Todos os resultados sobre o instante de início continuam **exploratórios** até haver aprovação, execução e um congelamento anterior à primeira simulação.

Nenhuma simulação foi corrida para escrever este documento, e nenhuma semente de 44000 a 44999 foi usada. Não se correu `vv-rocket`, `vv-exec` nem `cargo`. Os números vêm de leitura de código, de evidência guardada e de aritmética exata em `scripts/m19_g3_power.py` (só biblioteca padrão), cuja saída está em `docs/evidence/m19/g3-candidate/calculations.json`.

- sha256 de `scripts/m19_g3_power.py` (bytes do blob, fim de linha LF): `2dfdad80d2e265ca8cf070ad754cfb73a25f0e8e5ffed6dca169fdbe7959e1af`
- sha256 de `docs/evidence/m19/g3-candidate/calculations.json`: `199913e9ddafe49b8c9e63decd397165bcc885cb61d1e98ea243230aadb4b944`
- Reprodução: `python scripts/m19_g3_power.py --check docs/evidence/m19/g3-candidate/calculations.json` (não escreve nada, devolve 0 se os bytes coincidirem).

**Revisão por agentes não é revisão humana por pares.** Recomenda-se a leitura por um engenheiro que não participou no M13, no M14, no M15 nem no M19.

## Resumo das correções

1. **Inícios.** Em T, 0,01 s e 0,1 s são a mesma condição física. T passa de 8 para 7 inícios.
2. **«63 sementes».** O valor 63 é o certo para o nível 0,01/7, que é o nível que S4 e S5 precisam. O texto M15 atribuía-o a 0,01/14 (que dá 69). Corrige-se o texto, o nível e o limiar do McNemar.
3. **Potência de H1.** O valor de 0,064 vem de um exemplo hipotético (taxa de 0,93 a 0 s), não de evidência guardada. A evidência guardada tem 0 falhas em 294 execuções a 0 s. Mesmo assim, o desenho M15 deixa H1 com potência baixa se a taxa a 0 s for 0,95 ou menos, porque junta duas afirmações numa só. Propõem-se opções, com números, na secção «Opções de desenho para H1».
4. **Classificação.** Só H3 é uma previsão feita antes dos dados. H1 e H2, que o M15 chamava preditivas, são generalizações a posteriori.
5. **Mapas de sementes, famílias, limiares e orçamentos** recalculados para 7 inícios. A etapa D passa de 10 para 11 repetições, porque com 10 o orçamento de invariantes não se pode cumprir mesmo com zero eventos.
6. **Hash do simulador.** `12b276cb...` fica obsoleto; vale `295a45b2...`. Ver «Fontes fixadas».

## Diferenças face ao candidato M15

| # | Tema | Candidato M15 | Candidato corrigido | Razão |
| --- | --- | --- | --- | --- |
| 1 | Estado | «Candidato a protocolo congelado» | «Candidato corrigido», etiqueta no topo | Não há congelamento nem aprovação. |
| 2 | Inícios T | {0,01; 0,1; 1; 2; 5; 10; 15; 20} s (8) | {0,1; 1; 2; 5; 10; 15; 20} s (7) | O GNSS mede a cada 10 passos; um início em (0; 0,1] s só se vê na medida do passo 10. 0,01 e 0,1 dão a mesma história de sensores. |
| 3 | Texto das «63 sementes» | «seriam precisas 63» ao nível 0,01/14 | 63 ao nível 0,01/7; 69 ao nível 0,01/14 | 0,9^63 = 0,00131 ≤ 0,01/7 = 0,00143; 0,9^69 = 0,00070 ≤ 0,01/14 = 0,00071. |
| 4 | Nível de S4 e S5 | McNemar a 0,01/14 por condição | 0,01/7 por condição | S4 (e S5) é um teste da família secundária; exige as duas condições (teste de interseção-união), logo cada condição usa o nível total do teste. Dividir outra vez conta a multiplicidade duas vezes. |
| 5 | McNemar de S4 e S5 | pelo menos 11 pares discordantes | pelo menos 10 | 0,5^10 = 0,00098 < 0,01/7. |
| 6 | Palavra para S4 e S5 | «confirmada» | «suportada pela regra do motor», sem inferência | Com 60 sementes um teste binomial contra 0,9 é impossível ao nível 0,01/7 (mínimo 63) e ao nível 0,01/14 (mínimo 69). A regra «54 de 60» aceita 0,18 das vezes se a taxa for 0,85. |
| 7 | H1 | Conjunção: R1 cumpre-se a 0 s **e** falha no início tardio, n = 160, limiar 154 | H1a (falha no início tardio, n = 168, ≥ 162) com H1b (R1 cumpre-se a 0 s) como controlo positivo declarado. Outras opções na secção própria | A conjunção tem potência 0,064 (n = 160) ou 0,047 (n = 168) se a taxa a 0 s for 0,93 e a falha tardia for total, e 0,12 (n = 168) se a taxa for 0,95 e a falha tardia 0,99; depende de uma propriedade do G3 já registado. |
| 8 | Origem de 0,93 | Tabela de potência com «π» único | 0,93 é um exemplo hipotético; a evidência guardada dá 0 falhas em 294 execuções a 0 s | `docs/review/g3-onset/reviewer-questions.md` (pergunta 25, «por exemplo») e `independent-checks.md` (secção 3). |
| 9 | Classificação | H1 e H2 «preditivas», H3 preditiva, S1, S2, S6, S7 «corolários» | Só H3 é preditiva; H1, H2, S1, S2, S6, S7, M1 e M2 são a posteriori | A evidência que as sugere (M14, fragilidade, 2026-11-03 17:07; envelope M13) é anterior a este protocolo. |
| 10 | Banda baixa (H1) | 160 sementes (8 × 4 × 5) | 168 sementes (7 × 4 × 6) | Menos um início; seis repetições por célula. |
| 11 | Banda alta (H2, S3, S6) | 160 sementes | 140 sementes (7 × 4 × 5); limiar H2 136 de 140; S3 136 de 140 | Menos um início; o orçamento de sementes não chega para 6 repetições (ver «Desenho»). |
| 12 | Etapa D | 8 inícios × 4 magnitudes × 10 repetições = 320 | 7 × 4 × 11 = 308 | Com 7 × 4 × 10 = 280 haveria 440 pares e o limite a 99 % com 0 eventos seria 1,04 %, acima do orçamento de 1 %; são precisos 459 pares. |
| 13 | M1, M2, S7 | n = 240, 80, 80; limiares 228, 79, 80 | n = 231, 77, 77; limiares 220, 76, 77 | 7 inícios, 11 repetições. |
| 14 | Pares do orçamento | 480 por mitigação (D tardio 320 + E 160) | 468 (D tardio 308 + E 160) | Idem. Eventos máximos: invariantes 0 (0,98 %); R2 a R6 12 (era 13); R1 a 0 s 1 em 308 pares (era 1 em 320). |
| 15 | Sementes e execuções | 920 sementes, 5800 execuções, 0 por atribuir | 896 sementes, 5704 execuções, 24 sementes por atribuir (44896 a 44919) | Menos inícios. As 24 não são reserva: ver «Sementes». |
| 16 | Mapas das etapas | A 44000 a 44319, B 44320 a 44379, C 44380 a 44439, D 44440 a 44759, E 44760 a 44919 | A 44000 a 44307, B 44308 a 44367, C 44368 a 44427, D 44428 a 44735, E 44736 a 44895 | Fórmulas novas para A e D; B, C e E mantêm o conteúdo e deslocam-se. |
| 17 | Sementes protegidas | «as sementes protegidas do foguetão em `exec/src/seeds.rs`» | 3000 a 3099 e 6000 a 6099 (M10) | `ROCKET_PROTECTED` também lista 44000 a 44999; à letra, proibia as sementes do protocolo. |
| 18 | `source_sha256` do `vv-rocket` | `12b276cb...` «hoje» | `295a45b2...`; `12b276cb...` fica como valor do M13 | Só `landing_model.rs` mudou. Ver «Fontes fixadas». |
| 19 | Citações de linha | `landing_model.rs:414-418` e `:238` (também nas secções do M15 incluídas por referência) | Nomes de função e hashes de ficheiro; as duas frases em causa ficam reescritas em «Mecanismo» | As linhas mudaram (agora 426 a 431 e 250). |
| 20 | Janela do mediador | [início; início + 1,0 s] | [início efetivo; início efetivo + 1,0 s] | Início efetivo = primeiro passo de GNSS não anterior ao início. É igual a T em todos os inícios de T. |
| 21 | Verificação do código antes de correr | Não existe | Passo de equivalência de bytes (por correr, depois de aprovado) | `run.json` embute `source_sha256`, por isso difere por construção; `trace.json` e `verification.json` têm de coincidir com o registo M13. |
| 22 | Nível do achado conjunto | Bonferroni 0,01/3 sem discussão | Mantém-se; alternativa de 0,01 por teste descrita com números | A conjunção H1 e H2 e H3 é um teste de interseção-união (pergunta 11 do pacote de revisão). |
| 23 | Scripts | `scripts/m15_g3_confirm.py`, `scripts/m15_g3_analyse.py`, `docs/m15-g3-onset-freeze.json` | `scripts/m19_g3_confirm.py`, `scripts/m19_g3_analyse.py`, `docs/m19-g3-onset-freeze.json` | Nenhum existe; os nomes seguem o candidato. |
| 24 | Potência | n = 160, π único | Potência e efeito mínimo detetável de cada teste, por cenário, em `calculations.json` | Ver «Análise» e «Opções de desenho para H1». |
| 25 | Sementes não monótonas (etapa B) | «contadas e reportadas», sem dizer se entram na mediana | entram na mediana com o seu b_s | Pergunta 13(d) do pacote de revisão. |
| 26 | Etapa inválida | inválida e sem substituição, sem regra para as hipóteses | as hipóteses da etapa ficam inconclusivas | Pergunta 18. |
| 27 | S6 | n cerca de 160 | limiar recalculado com o n observado (cerca de 140); inconclusiva abaixo de 63 | n depende de quantas execuções tardias rejeitam. |
| 28 | Palavras do veredicto | «achado M14 confirmado», «mecanismo confirmado» | «achado M14 replicado», com a frase a declarar que só a fronteira foi prevista; «mecanismo suportado» | Classificação corrigida; pergunta 22. |
| 29 | Sementes já vistas | sem o G3 do M9.1 | acrescenta 2000 a 2029 | São sementes onde o G3 se registou. |
| 30 | Decisão do responsável | uma só: aprovar ou rejeitar | por ordem: escolher a opção de H1 e as escolhas de desenho, ler o texto corrigido, só depois aprovar ou rejeitar | Há escolhas de desenho por tomar. |
| 31 | H1b e a multiplicidade | não existia | declarado: quatro testes com afirmação se H1b licenciar «G3 replicado», alternativa 0,01/4 | Evita um erro de família de até 0,0133 sem o dizer. |
| 32 | Distribuição de b_s em S1 | implícita | declarada como pressuposto (reutiliza a de 5 s) | S1 mede-se a 15 s. |

**Não tratado aqui.** Os restantes pontos do pacote de revisão (por exemplo as perguntas 1, 2, 5 a 7, 9, 14, 15, 17 a 19, 21 a 24) ficam como no M15. Em particular: a proporção agregada tolera a falha de uma célula inteira (H1a: 6 falhas, uma célula tem 6 sementes), os denominadores do orçamento de regressão incluem pares em que a mitigação não pode atuar, e não há controlo global entre famílias (até 0,03 no conjunto das três).

## Mecanismo, segundo o código

Tudo o que o candidato M15 diz sobre o mecanismo (viés, inicialização, rejeição, regra 1, componente lateral, políticas, registo) mantém-se; ver `docs/m15-g3-onset-protocol.md`, secção «Mecanismo, segundo o código». Acrescenta-se a geometria do início, que o M15 só escrevia em parte. Duas citações de linha desse texto ficam substituídas por identificadores: o máximo aceite de `ascent_abort_vz_mps` (100) está em `validate_gains` e o mínimo de 5 m do viés do altímetro em `FaultKind::magnitude_range` (`AltimeterBias`), ambos em `crates/vv-rocket/src/landing_model.rs`.

### Geometria do início

Fontes (identificadores, não linhas): `crates/vv-rocket/src/landing_sim.rs` (`step % period == 0`, `gnss_cycle`, `f.start_step <= step && step < f.end_step`), `landing_sensors.rs` (`observe`, `gnss_bias_m`), `landing_model.rs` (`validate_faults`) e `model.rs` (`steps_of`).

- `dt_s` = 0,01; `control_period_steps` = 2; `gnss_period_cycles` = 5. O GNSS mede nos passos que são múltiplos de 2 × 5 = 10, isto é, a cada 0,1 s.
- `start_step` = `round(início / dt)`. A comparação é **inclusiva no início** (`start_step <= step`) e exclusiva no fim (`step < end_step`).
- O viés só entra na posição GNSS (`observe`, ramo `gnss_cycle`). O ruído de GNSS é sorteado em cada ciclo de GNSS, com ou sem viés; o viés soma-se depois. Logo, duas execuções cujo primeiro passo de GNSS enviesado é o mesmo têm a mesma história de sensores e o mesmo estado real.
- O primeiro passo de GNSS enviesado é o menor múltiplo de 10 não inferior a `start_step`.

| Início (s) | `start_step` | Primeiro passo de GNSS enviesado | No ciclo de GNSS? |
| --- | --- | --- | --- |
| 0 | 0 | 0 (inicialização enviesada) | sim |
| 0,01; 0,02; 0,05 | 1; 2; 5 | 10 (0,1 s) | não |
| 0,1 | 10 | 10 (0,1 s) | sim (inclusivo) |
| 1; 2; 5; 10; 15; 20 | 100; 200; 500; 1000; 1500; 2000 | igual a `start_step` | sim |

Conclusões:

- **0,01 s e 0,1 s são a mesma condição** (e 0,02 s e 0,05 s também). O M15 contava-as como duas; T tem 7 condições distintas. O teste `tests/test_m19_g3_power.py` verifica o agrupamento.
- Os outros inícios de T coincidem com um ciclo de GNSS, por isso são distintos entre si e o início efetivo é igual a T. O início 0 s é diferente de todos (inicializa o estimador enviesado).
- **Os artefactos diferem, o estado não.** Entre 0,01 s e 0,1 s mudam o evento `fault_start` (passo e instante) e o `start_s` configurado, logo `trace.json` e `verification.json` não são idênticos byte a byte; o estado real, as observações, as estimativas, R1 a R6 e os invariantes são os mesmos. Diz-se «mesma história de sensores», não «mesmos bytes».
- Os dados anteriores confirmam-no onde se mediu: no teste do M14 (`docs/evidence/m14/masking/test.json`), 0,01, 0,02 e 0,1 s a 8 m dão 0 de 20 com as mesmas sementes. Essas três linhas contam como **uma** observação, não como três.
- O início a 20 s deixa cerca de 3 s até ao contacto nominal (23,3 a 23,6 s, de `docs/m9-powered-landing.md`, caso nominal de outros controladores); não se mediu o tempo até ao contacto nas sementes dispersas do `guarded`. O teste do M14 dá 0 de 20 a 8 m com início a 20 s, por isso o viés ainda atua a essa altura.
- **Remover ou substituir.** Este candidato remove 0,01 s sem substituição. Substituir por um início distinto (por exemplo 0,2 s, a segunda medida de GNSS, ou 3 s) restaura as 8 condições e o desenho M15 de sementes, mas é uma escolha de desenho que não se faz aqui.

### Janela do mediador

A janela de decisão é [início efetivo; início efetivo + 1,0 s]. Para o início 0 s é [0; 1,0] s. Em todos os inícios de T o início efetivo é T. `altimeter_rejected_first` grava o passo exato de um ciclo de controlo (a cada 2 passos).

## Fontes fixadas

Referência: commit `47771609c030d8705eca867f4185f45427f8ae2b` (`4777160`). Cada hash é o sha256 do blob guardado (`git cat-file blob <commit>:<caminho> | sha256sum`; `core.autocrlf` está ativo, por isso nunca se usam os ficheiros da cópia de trabalho). A lista completa, 34 caminhos mais os 20 ficheiros do `vv-rocket`, está em `calculations.json` (`provenance`).

| Fonte | sha256 do blob em `4777160` |
| --- | --- |
| `docs/m15-g3-onset-protocol.md` (igual em `bec7b3f`) | `e85387a6b37c42d864cd5a70ff459a1618e0493ecfeada96f68d01054402d999` |
| `exec/claims/m13/g3-onset.json` | `f9e6154c8df0a9288cd2eea6ab634cd735a83e1feee0689525cabb93d6d6d319` |
| `exec/cases/m13/g3-registered.json` | `4f30b68094f4b7ff30039509b4362b47d513063c7e4b87c1348fdfeb87bc88f7` |
| `docs/evidence/m14/masking/prediction.json` | `9a67d22e1c9d620d4a3d1d762b44919ea724378f5b1b7634ea9878f81468d9b1` |
| `docs/evidence/m14/masking/test.json` | `29b1066d0763c7f763ef53e31afde4ef5c379f19a2d40f79cfdcd4be255ce3e2` |
| `docs/evidence/m13/g3-onset/investigation.json` | `c98f96388b4a4b9b556fa8a47bbf326dda958f583a4400d3f7703f452d502b12` |
| `docs/evidence/m14/fragility/fragility.json` | `5490e156f44dd969fc48ed77bdf590cf83f678bcb8e1e19ecfb60e1a1378472e` |
| `scripts/m14_masking_model.py` | `c6cbdc29fd01ffd38d7686f32d1df5fa9037af045bc4594ecd4e518f74f1add5` |
| `exec/src/seeds.rs` | `a2affe4ca1e709608c958c67eb9fbc0abbc52230da8f5e78f097c4ca70f1f47a` |
| `exec/src/investigate.rs` | `dafdf1bfd946a3c8cdb4fb043a61143b700f396d81ffee3713ec4ba12183cb92` |
| `source_sha256` do `vv-rocket` (recalculado sobre os blobs) | `295a45b26370e0390294b5a1cdbe975e7b8d0b77cbb7e07d4c2fae76a8612976` |
| `source_sha256` do `vv-rocket` registado no M13 | `12b276cb182b62ee3ecda602fe5f82edec2f40163afddaa12513fdc54edcbc05` |

Os oito ficheiros de famílias, `sources.json`, `scripts/m14_stats.py`, `scripts/m12_stats_reference.py`, `exec/src/search.rs`, os ficheiros do `vv-rocket` que o protocolo cita e os seis ficheiros de `docs/review/g3-onset/` estão na mesma lista.

### O `source_sha256` e o que muda nas saídas

- **Como se calcula.** `source_sha256()` em `crates/vv-rocket/src/lib.rs`: sha256 sobre 20 ficheiros (`Cargo.lock`, `Cargo.toml` e 18 de `src/`), cada um com o nome, um byte 0, o conteúdo com `\r\n` trocado por `\n` e outro byte 0. Recalculado em Python sobre os blobs, sem compilar; a reprodução dá `12b276cb...` em `3962482` e `295a45b2...` em `4777160` e em `bec7b3f`.
- **O que difere.** Só `crates/vv-rocket/src/landing_model.rs` (+152 linhas, −3), por dois commits (`3baa1c1`, `04de572`). Os outros 19 ficheiros têm o mesmo blob.
- **O que o diff faz.** Acrescenta o esquema `vv-rocket-landing.v2` e `check_exploratory`, que só corre para casos v2; `prepare_landing` passa a ramificar por esquema (v2 para `check_exploratory`, o resto para `check_registered`, que não mudou); `prepare_unpinned` alarga a verificação do esquema para aceitar v2; e uma constante nova só usada por `check_exploratory`. Para um caso v1 (o `g3-registered.json` é v1) a sequência de operações de `sensors`, `controller`, `sim` e `verify` é a mesma, e esses ficheiros têm blobs idênticos.
- **Conclusão.** Por leitura do diff, as saídas de simulação de casos v1 **não devem diferir**; isto **não está demonstrado por execução**. Há duas consequências certas: (a) `run.json` embute `source_sha256` (`landing_run.rs`, `manifest_for`), por isso muda por construção; `trace.json` e `verification.json` não o embutem; (b) `vv-rocket replay <pasta>` de um pacote construído com `12b276cb...` regista «built from the same sources» como falhado, e o manifesto como diferente, com o código atual (`landing_run.rs`, `replay`); não afeta a simulação.
- **Passo de equivalência (por correr, depois da aprovação e antes do congelamento).** Os ficheiros `case.json`, `trace.json` e `verification.json` dos cinco artefactos da semente 42879 (registado, contraexemplo, gémeo e as duas mitigações) **não estão no repositório**: `docs/evidence/m13/g3-onset/` só tem `investigation.json`, `manifest.json` e `verification.json`, que guardam os sha256 (`artifacts.<nome>.files`). Por isso o passo é: (1) reconstruir cada `case.json` a partir de `exec/cases/m13/g3-registered.json` e dos valores guardados (`findings.counterexample.minimised`, `registered`, e o ponteiro do limiar de cada mitigação) e conferir o sha256 com `files.case.json`; (2) se coincidir, compilar o `vv-rocket` do commit a fixar, correr `vv-rocket land` com a semente 42879 e comparar o sha256 de `trace.json` e de `verification.json` com os guardados (`run.json` difere por construção); (3) se um `case.json` não se reconstruir byte a byte, esse artefacto fica fora do passo, e o passo tem de ser substituído por outra comparação aprovada. Os artefactos guardados vieram do `vv-exec 0.12.0` em processo; uma diferença pode vir da linha de comandos em vez do código-fonte (a equivalência entre os dois só foi verificada numa amostra pequena, `docs/m14-evidence-robustness.md`). Qualquer diferença suspende o protocolo até se perceber a causa. Não se corre com sementes 44000 a 44999.
- **Referência.** O hash a fixar é o do commit de congelamento; hoje é `295a45b2...`. A evidência de desenvolvimento do M13 refere-se a `12b276cb...`.

## Hipóteses

### Observações exploratórias anteriores (já vistas, não confirmam nada)

| Origem | Data do commit (UTC) | Sementes | O que se viu |
| --- | --- | --- | --- |
| M9.1, critério G3 | 2026-10-28 e 29 | 2000 a 2029 | R1 cumprido em 30 de 30 com início 0 s (`docs/m9-powered-landing.md`, quadro de resultados). |
| M14, fragilidade, braços por início | 2026-11-03 17:07 a 17:43 | 32000 a 32029 (a fragilidade completa usa 32000 a 32099) | Início 0 s: R1 cumprido em 180 de 180 (6 magnitudes de 5 a 30 m). Inícios 2, 5 e 10 s: R1 falha em 30 de 30 a 5 e 10 m e cumpre-se a 15 m ou mais. Primeira vez que se viu o mascaramento e a recuperação. |
| M13, investigação | dados de 2026-11-03; evidência no commit de 21:31 | 42000 a 43999 | Envelope 16 × 16 com 4 sementes: linha de 0 s com 64 de 64; 240 de 240 falhas com início tardio a 10 m ou menos; 660 de 660 cumprimentos a 13,3 m ou mais. Contraexemplo reduzido (0,02 s, 9,72 m). Limiar 1 m: 280 pares corrigidos e 35 compromissos. |
| M14, previsão e teste | 20:20 e 20:25 | 47000 a 47019 | P1: b50 = 11,89 m contra b* = 11,99 m. P2: a 8 m, só o início 0 s evita o mascaramento (0,01, 0,02 e 0,1 s são uma só condição). |
| M14, revisão independente | 2026-11-03 | 33500 a 33529 | Inícios 0,5 e 1 s: R1 em 0 de 30 a 5 e 10 m. |
| Desenvolvimento e ensaios | | 41000 a 41999 (41000 a 41009 à mão), 45000 a 46999 (45000 a 45003 na revisão), 30001, 30017 | Gastas. |

Nenhuma destas sementes volta a servir de confirmação. A previsão P1 foi fixada (`73c9ff5`, 20:20) antes do teste (`1195c1b`, 20:25); o autor já tinha visto a transição grosseira entre 10 e 15 m (fragilidade F6: 12,5 m é o único nível com execuções que cumprem todos os requisitos, 24 de 100).

### Classificação corrigida

«A posteriori» quer dizer: a hipótese, os níveis ou o limiar foram escritos depois de ver dados de desenvolvimento sobre as mesmas condições. Uma hipótese a posteriori confirmada com sementes novas e regras fixadas à partida confirma o efeito; não é uma previsão cumprida.

| Hipótese | Classe no M15 | Classe corrigida | Razão |
| --- | --- | --- | --- |
| H1 (mascaramento) | preditiva («P2 generalizada») | **a posteriori** | P2 só previa a 8 m e só dizia «inícios de 0,01 a 20 s mascaram». As magnitudes {5; 7; 9; 10,5} e os 7 inícios vêm da fragilidade M14 e do envelope M13, anteriores ao protocolo. |
| H2 (recuperação) | preditiva («P1») | **a posteriori** | P1 previa só a posição b* a 5 s. «R1 cumpre-se acima de 13,5 m em qualquer início» resume o envelope M13 (660 de 660) e a fragilidade M14. |
| H3 (fronteira a 5 s) | preditiva | **preditiva, já testada uma vez** | P1 foi fixada antes do teste com 47000 a 47019 (dados gastos). Aqui é uma replicação com sementes novas; o valor foi previsto, a existência da fronteira não. |
| S1 (invariância, 15 s) | corolário | a posteriori | O envelope M13 já mostrava a variação com o início. |
| S2 (precisão 0,5 m) | corolário | a posteriori | A tolerância de 0,5 m foi escolhida conhecendo o desvio de 0,1 m. |
| S3 (R5 falha a 0 s) | a posteriori | a posteriori | `baseline_violations` do M13 (R5 em 30 de 30). |
| S4, S5 (mecanismo) | a posteriori | a posteriori | M13 e sementes 41000 a 41009. |
| S6 (cronologia) | corolário | a posteriori | O teste M14 já registou a concordância rejeição e R1 em 29 células. |
| S7 (limiar de 2 m) | corolário | a posteriori | O M13 já correu o limiar de 2 m no envelope. |
| M1 (limiar 1 m) | sem classe | a posteriori | O M13 já a apoiou (30 de 30; 280 corrigidos). |
| M2 (limiar 2 m) | sem classe | a posteriori | Mistura o modelo e resultados M13. |

**Previsões genuínas neste protocolo: H3, e só H3.** Todas as outras hipóteses são confirmação de efeito. A frase de confirmação (ver «Regras de decisão») diz-o.

### Família primária (erro de família 0,01, Bonferroni, 0,01/3 por teste)

- **H1a, mascaramento (a posteriori).** Com início tardio em T e magnitude na banda baixa {5; 7; 9; 10,5} m, R1 **falha** (avaliado e não cumprido). Teste binomial exato de π ≤ 0,9, n = 168, rejeita com 162 de 168 ou mais.
- **H1b, controlo positivo (a posteriori; padrão provisório, ver as opções).** Com início 0 s e a mesma banda, R1 cumpre-se (o G3 registado replica-se). Mesmo teste e mesmo limiar, n = 168. **Não entra na regra conjunta**; reporta-se sempre, com o limite inferior de Clopper-Pearson a 99 %, e decide a frase de confirmação (ver «Regras de decisão»).
- **H2, recuperação (a posteriori).** Com início tardio em T e magnitude na banda alta {13,5; 17; 22; 30} m, R1 cumpre-se. n = 140, rejeita com 136 de 140 ou mais.
- **H3, fronteira (preditiva).** Com início a 5 s, a magnitude mediana de transição b50 está a menos de 1 m de b* = 11,99 m. Intervalo da mediana por estatísticas de ordem, n = 60, posições 20 e 41. A tolerância de 1 m foi fixada em `prediction.json` e não é exigente.

### Família secundária (erro de família 0,01, Bonferroni, 0,01/7 por teste)

S1 a S7 como no M15 (S1: H3 com início a 15 s, posições 19 e 42; S2: H3 a 5 s com tolerância 0,5 m; S3: R5 falha a 0 s na banda alta; S4: `guarded` sem regra 2 cumpre R1 e `robust` falha; S5: limiar 1000 m faz R1 falhar onde o `guarded` registado cumpre; S6: primeira rejeição dentro da janela; S7: limiar 2 m falha a 5 m e cumpre a 10,5 m), todas a posteriori. As alterações são de contagens e de palavras:

- **S4 e S5, nível.** São duas hipóteses da família de 7, cada uma confirmada só se **as duas** condições (0 s e 15 m; 5 s e 15 m) rejeitarem. Numa regra de interseção-união cada condição é testada ao nível total do teste, 0,01/7; o M15 aplicava 0,01/14, o que conta a multiplicidade duas vezes.
- **S4 e S5, o que se pode concluir com 60 sementes.** Um teste binomial contra 0,9 só rejeita com n sucessos em n se 0,9^n ≤ α. A 0,01/7 isso exige n ≥ 63 (0,9^63 = 0,00131; 0,9^62 = 0,00146 > 0,00143). A 0,01/14 exigiria 69. Com 60 sementes nenhum dos dois é possível. Mantém-se a regra do motor (fração de sementes no sentido previsto ≥ 0,9, mais McNemar exato com p < 0,01/7, isto é, pelo menos 10 pares discordantes no sentido previsto), mas **como regra, não como inferência**: a fração ≥ 54 de 60 implica um p de McNemar de 4,9 × 10⁻¹¹ no pior caso, por isso o McNemar nunca decide, e a regra aceita taxas verdadeiras de 0,85 com probabilidade 0,185 e de 0,90 com probabilidade 0,606. O veredicto escreve-se «suportada pela regra do motor, sem inferência», nunca «confirmada». Com mais sementes por condição, o teste binomial a 0,01/7 passa a ser possível (63, 70, 77, 84: tolera 0 falhas; 100: 1 falha; 150: 4 falhas); a potência é baixa mesmo assim (n = 150, π = 0,97: 0,531). Ver `calculations.json`, `s4_s5`.
- **S4 e S5, definição de sucesso.** São conjunções de dois braços na mesma semente (S4: G0 cumpre R1 e `robust` falha; S5: o `guarded` registado cumpre R1 e o braço de 1000 m falha), como H1; os valores de π dependem das duas taxas.
- **S6.** n é o número de execuções tardias da etapa A com rejeição (cerca de 140, banda alta); o limiar recalcula-se com o n observado ao nível 0,01/7 e, abaixo de 63, S6 é inconclusiva por construção.

### Família de mitigação (erro de família 0,01, Bonferroni, 0,01/2 por teste)

M1 (limiar 1 m; n = 231; rejeita com 220 de 231 ou mais) e M2 (limiar 2 m a 10,5 m; n = 77; rejeita com 76 de 77 ou mais). Ambas a posteriori.

**Verificações estruturais.** Iguais às do M15 (determinísticas; uma exceção suspende a leitura do código e S4).

## Desenho

Caso base: `exec/cases/m13/g3-registered.json` (política `guarded`, `gnss_bias` de 0 a 40 s, esquema v1). Cada execução altera só os ponteiros indicados. **Inícios tardios: T = {0,1; 1; 2; 5; 10; 15; 20} s** (7). Mesma semente em braços diferentes é emparelhamento intencional; etapas diferentes usam sementes disjuntas.

| Etapa | Sementes | Mapa semente para condição | Braços por semente | Execuções |
| --- | --- | --- | --- | --- |
| A, banda baixa | 44000 a 44167 (168) | 44000 + 24·i + 6·j + r; i = 0 a 6 (índice do início em T), j = 0 a 3 (magnitude em {5; 7; 9; 10,5}), r = 0 a 5 | início tardio; início 0 s | 336 |
| A, banda alta | 44168 a 44307 (140) | 44168 + 20·i + 5·j + r; i = 0 a 6, j = 0 a 3 (magnitude em {13,5; 17; 22; 30}), r = 0 a 4 | início tardio; início 0 s | 280 |
| B, fronteira | 44308 a 44367 (60) | cada semente em todos os níveis | magnitudes 10,0 a 14,0 m, passo 0,25 (17), com início 5 s e 15 s | 2040 |
| C, mecanismo | 44368 a 44427 (60) | cada semente nas 3 condições | condições (0 s, 15 m), (5 s, 15 m), (5 s, 8 m) × braços G registado, G0 sem regra 2, R `robust`, N limiar 1000 m | 720 |
| D, mitigação | 44428 a 44735 (308) | 44428 + 44·i + 11·j + r; i = 0 a 6, j = 0 a 3 (magnitude em {5; 8; 10,5; 15}), r = 0 a 10 | {início tardio; 0 s} × {sem; 1 m; 2 m} | 1848 |
| E, famílias | 44736 a 44895 (160) | 44736 + 20·f + k; f = família pela ordem de `g3-onset.json` (0 a 7), k = ponto Halton 0 a 19 | {sem; 1 m; 2 m} | 480 |
| Por atribuir | 44896 a 44919 (24) | nenhuma | | 0 |
| Reserva | 44920 a 44999 (80) | intocada | | 0 |

Total: **896 sementes atribuídas, 5704 execuções**. Verificado por enumeração em `scripts/m19_g3_power.py` (`seed_map`, `seed_checks`) e pelo teste: cada semente tem uma só condição; todas estão em 44000 a 44919; nenhuma está em 44920 a 44999, em 3000 a 3099, 6000 a 6099, 50000 a 59999 nem nas faixas já vistas; as faixas das etapas são contíguas e disjuntas; as células de A e D têm 6, 5 e 11 sementes cada.

**Porque não 6 repetições na banda alta.** Seriam 168 sementes em A_high e 924 no total, quatro acima de 920. Com 19 pontos Halton por família em E (152 sementes) caberia (916), e o limiar de H2 passaria de 136 de 140 para 162 de 168. É uma escolha de desenho alternativa (potência de H2 com π = 0,97: 0,589 para 0,758); não se faz aqui.

**Porque 11 repetições em D.** O orçamento de invariantes exige limite a 99 % ≤ 1 % com 0 eventos, o que pede pelo menos 459 pares por mitigação. D tardio com 10 repetições dá 280 + 160 = 440 pares (limite 1,04 %, impossível); com 11, 308 + 160 = 468 pares (limite 0,98 %).

As 24 sementes por atribuir **não são reserva**: não podem ser usadas para repetir, completar ou substituir nada desta execução. Servem só de folga de numeração e ficam, como a reserva, para um protocolo futuro.

Os pontos Halton da etapa E (bases 2 e 3, ou 2 numa família de um parâmetro, a partir do índice 1, quantizados como em `exec/src/search.rs`) e as gamas de `g3-onset.json` mantêm-se como no M15.

## Resultados medidos

Como no M15: por execução o executor grava semente, condição, braço, `outcome`, R1 a R6 (`evaluated`, `pass`, `value`), invariantes S1 a S5, `altimeter_rejected_first`, `sensor_disagreement_first` e os sha256 de `verification.json` e `trace.json`. Nada se lê do traço amostrado. Mediador: rejeição na janela [início efetivo; início efetivo + 1,0 s]; tardia: depois da janela. Transição por semente (etapa B): b_s é o menor nível a partir do qual R1 se cumpre nesse e em todos os seguintes; b50 é a mediana de b_s; sementes não monótonas contam-se, reportam-se e **entram** na mediana com o seu b_s.

## Análise

### Testes, níveis, limiares e potência

Testes binomiais exatos unilaterais de H0: π ≤ 0,9 (unidade: a semente). Potência por π verdadeiro (assumindo independência entre sementes); o efeito mínimo detetável (MDE) é o menor π, em passos de 0,001, com potência 0,8. Os valores M15 estão em `calculations.json` (`tests`, chaves `M15_*`) e coincidem com o pacote de revisão.

| Teste | Nível | n | Rejeita com | Falhas toleradas | Potência com π = 0,95 / 0,97 / 0,99 | MDE |
| --- | --- | --- | --- | --- | --- | --- |
| H1a (e H1b) | 0,01/3 | 168 | 162 de 168 | 6 | 0,260 / 0,758 / 0,998 | 0,972 |
| H2 | 0,01/3 | 140 | 136 de 140 | 4 | 0,166 / 0,589 / 0,986 | 0,978 |
| S3 | 0,01/7 | 140 | 136 de 140 | 4 | 0,166 / 0,589 / 0,986 | 0,978 |
| S6 (n aproximado) | 0,01/7 | 140 | 136 de 140 | 4 | 0,166 / 0,589 / 0,986 | 0,978 |
| S7 (cada proporção) | 0,01/7 | 77 | 77 de 77 | 0 | 0,019 / 0,096 / 0,461 | 0,998 |
| M1 | 0,01/2 | 231 | 220 de 231 | 11 | 0,512 / 0,952 / 1,000 | 0,961 |
| M2 | 0,01/2 | 77 | 76 de 77 | 1 | 0,097 / 0,324 / 0,820 | 0,990 |

Com o nível total (0,01) o limiar de H1a e de H1b passa a 161 de 168. Em M15, com n = 160: H1 e H2 154 de 160 (potência 0,307 / 0,793 / 0,999), S3 155 de 160, M1 228 de 240, M2 79 de 80, S7 80 de 80.

S7 só se confirma se as duas proporções derem 77 de 77; com π = 0,99 em cada uma a potência conjunta é cerca de 0,21 (0,461 ao quadrado). É um teste exigente.

### Fronteira (H3, S1, S2)

Intervalo da mediana sem distribuição: [X(l) − 0,25; X(u)], com n = 60 e posições (20; 41) ao nível 0,01/3 (H3) e (19; 42) ao nível 0,01/7 (S1, S2). S1 reutiliza a distribuição de b_s de 5 s para o início de 15 s, o que é um pressuposto, não um dado. Confirma-se se o intervalo cabe dentro de b* ± tolerância (1 m em H3 e S1; 0,5 m em S2); refuta-se se ficar inteiramente fora.

Potência exata (distribuição de b_s reconstruída de `test.json`, supondo R1 monótono em cada semente, o que o ficheiro não permite verificar; o deslocamento move a distribuição inteira). Cruzamento Monte Carlo: gerador SplitMix64, semente 20261123 (do script, sem relação com sementes do simulador), 5000 repetições; a 0,75 m dá 0,674 contra 0,669 exato.

| Deslocamento da fronteira real (m) | H3 confirma | H3 refuta | S1 confirma | S2 confirma | S2 refuta |
| --- | --- | --- | --- | --- | --- |
| 0 | 1,000 | 0 | 1,000 | 1,000 | 0 |
| 0,25 | 1,000 | 0 | 1,000 | 0,563 | 0 |
| 0,50 | 1,000 | 0 | 1,000 | 0 | 0 |
| 0,75 | 0,669 | 0 | 0,563 | 0 | 0,851 |
| 1,00 | 0 | 0 | 0 | 0 | 1,000 |
| 1,25 | 0 | 0,908 | 0 | 0 | 1,000 |

Com tolerância de 1 m, H3 só deteta um deslocamento de 1,25 m ou mais (refutação com probabilidade 0,908); entre 0,75 e 1,0 m fica inconclusiva com alta probabilidade. S2 (0,5 m) já distingue 0,25 m.

### Erros, repetições e paragem

Iguais às do M15: uma execução que falha repete-se uma vez com a mesma semente e conta contra a hipótese se falhar outra vez; mais de 1 % de falhas numa etapa torna-a inválida, sem substituição; sem análise intermédia nem paragem antecipada (não há espreitar); o executor só escreve um registo com hashes e a análise lê-o uma vez, depois de completo; uma retoma usa as mesmas sementes e confirma que as execuções feitas dão os mesmos bytes. Uma etapa inválida deixa as suas hipóteses «inconclusivas».

### Controlo de multiplicidade

Bonferroni dentro de cada família (0,01/3, 0,01/7, 0,01/2). Entre famílias não há correção: o erro máximo agregado é 0,03. Os limites de Clopper-Pearson do orçamento de regressão não têm correção. O achado conjunto (H1a, H2, H3) é um teste de interseção-união; ver a alternativa de nível 0,01 em «Opções de desenho para H1».

**H1b e a multiplicidade no padrão provisório.** H1b é testado ao nível 0,01/3 fora da família de três, mas uma confirmação sua autoriza a frase «G3 replicado». Há então quatro testes com afirmação (H1a, H1b, H2, H3) e, com 0,01/3 cada, o erro de família pode chegar a 4 × 0,01/3 = 0,0133. Alternativa: família de quatro a 0,01/4 = 0,0025. Os limiares binomiais não mudam (H1a e H1b 162 de 168; H2 136 de 140, porque os testes são discretos); só mudam as posições de H3, de (20; 41) para (19; 42), e a potência de H3 a 0,75 m, de 0,669 para 0,563. Na regra conjunta do padrão, a potência com 0,01/4 é 1,000 / 0,985 / 0,588 / 0,331 nos quatro cenários (com 0,01/3: 1,000 / 0,985 / 0,588 / 0,394).

## Opções de desenho para H1

### O problema

O sucesso de H1 no M15 é uma conjunção na mesma semente: R1 cumpre-se a 0 s **e** falha com início tardio. Com π = p0 · q (p0: taxa de R1 a 0 s; q: taxa de falha tardia; braços independentes dada a semente) e H0: π ≤ 0,9, a potência é pequena sempre que p0 não é quase 1: com n = 160 e q = 1, π = 0,93 dá 0,064 (o valor citado no pacote de revisão); com n = 168, 0,047.

### De onde vem 0,93

**Não vem de evidência guardada.** Aparece só como exemplo hipotético, compatível com o piso do G3 (27 de 30 = 0,9), em `docs/review/g3-onset/reviewer-questions.md` (pergunta 25, «por exemplo») e em `independent-checks.md` (secção 3). Nenhum conjunto de execuções guardado mede uma taxa de 0,93 a 0 s. O que a evidência guardada diz de p0, de q e de H2 (de `calculations.json`, `evidence`; os limites são de Clopper-Pearson unilateral a 99 %):

| Grandeza | Fontes | Cumpridas | Limite inferior (execuções) | Limite inferior (sementes distintas) |
| --- | --- | --- | --- | --- |
| p0, 0 s, 5 a 30 m | M9.1 30; fragilidade 180; envelope 64; teste 47000 20 | 294 de 294 | 0,984 | 0,947 (84 sementes) |
| p0, 0 s, banda baixa (10,5 m ou menos) | fragilidade 60; envelope 16; teste 20 | 96 de 96 | 0,953 | 0,918 (54 sementes) |
| q, início tardio, banda baixa, R1 falha | fragilidade 180; envelope 240; teste 100 (5 condições distintas) | 520 de 520 | 0,991 | 0,918 (54 sementes) |
| H2, início tardio, banda alta, R1 cumpre | fragilidade 360; envelope 660; teste 140 | 1160 de 1160 | 0,996 | 0,918 (54 sementes) |

As execuções partilham sementes entre células (30 na fragilidade, 4 no envelope), por isso os limites por execução são otimistas; a última coluna conta cada semente uma vez, supondo que todas cumpriram em todas as células em que entraram. O limite de 0,918 para p0 na banda baixa mostra que **a evidência guardada não exclui p0 entre 0,90 e 0,92**; excluir 0,93 (e aceitar a conjunção como realista) só com os dados que o protocolo vai produzir.

### Cenários e opções (n = 168, nível 0,01/3)

Cenários (p0; q): (1,00; 1,00), (0,99; 0,99), (0,97; 0,99), (0,95; 0,99), (0,93; 0,99), (0,93; 1,00), (0,90; 1,00, o piso do G3), (1,00; 0,93, equivalente a um início em sete a falhar metade das vezes). Todas as potências são exatas, sob independência entre os dois braços da mesma semente; no ficheiro de cálculos há também os limites de Fréchet das opções 1 e 2 (a diferença não passa de 0,002).

| Opção | O que testa (testes com afirmação; nível) | (0,99; 0,99) | (0,97; 0,99) | (0,95; 0,99) | (0,93; 0,99) | (0,93; 1,00) | (1,00; 0,93) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0. Conjunção M15 | π = p0 · q > 0,9 (3: H1, H2, H3; 0,01/3) | 0,948 | 0,498 | 0,123 | 0,018 | 0,047 | 0,047 |
| 1. Separar, ambas exigidas | H1a: q > 0,9 e H1b: p0 > 0,9, ambos a rejeitar (3 compostos: H1, H2, H3; 0,01/3 cada) | 0,997 | 0,757 | 0,260 | 0,046 | 0,047 | 0,047 |
| 2. Condicional | H1b, e q > 0,9 entre as sementes com R1 cumprido a 0 s (3 compostos; 0,01/3) | 0,997 | 0,757 | 0,260 | 0,046 | 0,047 | 0,047 |
| 3. Emparelhado (McNemar exato) | a falha tardia é mais provável do que a de 0 s (3; 0,01/3) | 1,000 | 1,000 | 1,000 | 1,000 | 1,000 | 1,000 |
| 4. Separar, H1b só controlo | H1a: q > 0,9 (H1b reportado) (3 mais o controlo, que conta como quarto se licenciar «G3 replicado»; 0,01/3, ou 0,01/4 com quatro) | 0,998 | 0,998 | 0,998 | 0,998 | 1,000 | 0,047 |
| 5. Separar, nula 0,8 em H1b | q > 0,9 e p0 > 0,8 (3 compostos; 0,01/3 cada) | 0,998 | 0,998 | 0,998 | 0,984 | 0,986 | 0,047 |
| 6. Agrupar braços de A e D (n = 399) | opção 1 com 168 + 231 sementes (3 compostos; 0,01/3 cada) | 1,000 | 0,999 | 0,852 | 0,255 | 0,255 | 0,255 |

Notas:

- **A opção 1 não resolve o problema de fundo.** Separa as duas afirmações, mas H1b continua a ser um teste de p0 > 0,9 com 168 sementes, com potência igualmente baixa quando p0 é 0,95 ou menos (0,260 com p0 = 0,95). O que a separação ganha é que H1a deixa de depender de p0 (0,998 em todos os cenários com q = 0,99).
- **Opção 2** dá o mesmo que a opção 1 (os braços são independentes no modelo); é útil quando a pergunta é «entre as sementes em que o G3 registado cumpre, o início tardio falha?», não para a potência.
- **Opção 3** tem potência 1,000 em todos os cenários, mesmo a 0,90, porque o teste de sinais só compara quem difere. Suporta a afirmação **mais fraca** «um início tardio piora R1 em relação a 0 s», sem níveis absolutos; não suporta «falha em 90 % ou mais» nem «cumpre em 90 % ou mais».
- **Opção 4** separa de facto as duas afirmações: o resultado sobre o mascaramento deixa de depender do G3 a 0 s; H1b fica como controlo positivo com uma regra de palavras (ver «Regras de decisão»). Custo: a frase de confirmação só pode incluir «com o viés desde 0 s, R1 cumpre-se» se H1b for confirmado.
- **Opção 5** (H1b contra 0,8, limiar 149 de 168) altera a afirmação para «não substancialmente pior do que o G3 registado»; o 0,8 não está justificado por nenhum critério existente.
- **Opção 6** (H1 e H2 com os braços sem mitigação de A e de D agrupados: 168 + 231 = 399 sementes na banda baixa, 140 + 77 = 217 na alta; limiares 375 de 399 e 207 de 217) é a que mais potência dá (MDE 0,948) sem sementes novas. Custo: as realizações de ruído de D passam a servir H1 e M1/M2, perde-se a independência entre a conclusão sobre o mascaramento e a conclusão sobre mitigações, e a alta e a baixa deixam de ser «bandas de A». Está dentro das 896 sementes.
- **Mais sementes para a opção 0:** com p0 = 0,93 e q = 1,00 são precisas cerca de 1130 sementes (900 ao nível 0,01); com p0 = 0,95 e q = 0,99, 610 (500). Fora do orçamento (a banda baixa tem 168 de 896).
- **Efeito mínimo detetável simétrico (p0 = q, potência 0,8):** 0,986 para a opção 0 e 0,977 para a opção 1 com n = 168; 0,974 e 0,953 com n = 399.

### Regra conjunta «achado confirmado», potência

H1 (banda baixa), H2 (banda alta) e H3 (etapa B) usam sementes disjuntas, por isso a potência conjunta é o produto. Dentro de H1 os dois braços partilham sementes; as opções 1 e 2 estão sob independência. Cenários (p0; q; π de H2; deslocamento de b* em m): otimista (1; 1; 1; 0), tipo desenvolvimento (0,99; 0,99; 0,99; 0), moderado (0,97; 0,99; 0,97; 0,25), pessimista (0,95; 0,99; 0,97; 0,75).

| Regra conjunta (nível 0,01/3) | Otimista | Tipo desenvolvimento | Moderado | Pessimista |
| --- | --- | --- | --- | --- |
| Opção 0: H1 conjunção, H2, H3 | 1,000 | 0,935 | 0,293 | 0,048 |
| Opção 1: H1a, H1b, H2, H3 | 1,000 | 0,983 | 0,446 | 0,102 |
| Opção 4: H1a, H2, H3 (H1b controlo) | 1,000 | 0,985 | 0,588 | 0,394 |
| Opção 3: H1 emparelhado, H2, H3 | 1,000 | 0,986 | 0,589 | 0,394 |
| Opção 6: braços agrupados, H1a e H1b, H2, H3 | 1,000 | 1,000 | 0,935 | 0,533 |
| Opção 4 com família de quatro (0,01/4) | 1,000 | 0,985 | 0,588 | 0,331 |
| Opção 4 com nível 0,01 por teste | 1,000 | 0,997 | 0,755 | 0,575 |
| Opção 6 com nível 0,01 por teste | 1,000 | 1,000 | 0,968 | 0,685 |

O limite da regra conjunta com as opções 3 e 4 é H2 (n = 140: potência 0,589 com π = 0,97), não H1.

**Nível do achado conjunto.** Como o achado exige H1, H2 e H3 todas confirmadas, o erro de afirmar o conjunto sem que seja verdade não passa de 0,01 se cada teste usar 0,01 (interseção-união). O ganho é grande (moderado: 0,588 para 0,755 na opção 4). O custo é que as três hipóteses deixam de ter controlo de família 0,01 quando lidas isoladamente (até 0,03). O padrão mantém Bonferroni; a escolha pertence a quem decide.

### Padrão provisório (não é uma decisão)

**Opção 4 com Bonferroni 0,01/3 e as camadas A e D separadas:** H1a confirmatório, H1b controlo positivo, regra conjunta H1a e H2 e H3. Razões: (a) é a única que desliga o mascaramento do G3 a 0 s sem mudar a pergunta (a opção 3) nem a nula (a opção 5); (b) não perde a independência entre A e D (opção 6); (c) a evidência guardada dá q ≈ 1 com grande folga e p0 ≈ 1 sem folga na banda baixa. O que fica por decidir: a opção 6 (mais potência, mais acoplamento), o nível 0,01 por teste, a substituição do início removido e as 6 repetições em A_high (ver «Desenho»).

## Orçamento de regressão das mitigações

Mesma definição do M15: um evento é um par em que a mitigação **acrescenta** uma violação que a execução sem mitigação não tinha, sobre os pares em que a mitigação pode atuar (D com início tardio e E). Pares por mitigação: 308 (D tardio) + 160 (E) = 468; os 308 pares de D com início 0 s formam a categoria de verificação. Limite superior de Clopper-Pearson unilateral a 99 %.

| Categoria | Pares | Orçamento | Eventos máximos | Limite com o máximo |
| --- | --- | --- | --- | --- |
| Invariantes S1 a S5 | 468 | ≤ 1 % | 0 | 0,98 % |
| R2 a R6 (compromissos) | 468 | ≤ 5 % | 12 | 4,82 % |
| R1 com início 0 s (território do G3 registado) | 308 | ≤ 2,5 % | 1 | 2,14 % |

O orçamento de invariantes só pode cumprir-se com pelo menos 459 pares: com 440 o limite a 99 % com 0 eventos é 1,04 %. Uma segunda ocorrência em R1 a 0 s dá 2,70 %, acima do orçamento. A previsão M15 mantém-se: o orçamento de compromissos provavelmente será excedido (nos dados de desenvolvimento, 35 compromissos em 1024 pares do envelope, 3,4 %, limite 4,98 %, e 6 em 30 no contraexemplo); a taxa com todos os pares reporta-se ao lado, identificada como diluída. As palavras do veredicto mantêm-se («eficaz para R1 no envelope declarado», «dentro do orçamento», «candidata a adoção» só com as duas).

## Regras de decisão

Para cada hipótese de proporção:

- **Confirmada:** H0 rejeitada ao nível da família.
- **Refutada:** fração observada no sentido previsto ≤ 0,1, ou, em H3, S1 e S2, intervalo inteiramente fora de b* ± tolerância.
- **Inconclusiva:** qualquer outro caso, com a contagem e o intervalo de Clopper-Pearson a 99 %.
- **S4 e S5:** «suportada pela regra do motor» se as duas condições passarem a regra e o McNemar a 0,01/7; nunca «confirmada».

Leitura conjunta (padrão provisório, opção 4):

- **Achado M14 replicado** se H1a, H2 e H3 forem confirmadas. A frase é: «com o viés a começar depois da primeira medida GNSS, R1 falha abaixo de cerca de 12 m e volta a cumprir-se acima disso; resultado de simulação idealizada, hipótese formulada depois de ver dados de desenvolvimento (só a posição da fronteira foi prevista antes), replicado com sementes novas», sempre com o perfil de R5.
- Se H1b também for confirmada, acrescenta-se «com o viés desde 0 s, R1 cumpre-se (G3 replicado)». Se H1b for inconclusiva ou refutada, a frase diz «o contraste com o início 0 s não foi reconfirmado nesta execução», com a contagem e o limite inferior.
- **Refutado** se H1a ou H2 for refutada.
- **Mecanismo suportado** só se S4, S5 e as verificações estruturais passarem.
- Nenhum resultado altera o registo do G3 nem o grau dos pacotes M13 e M14.

## Sementes

- **Atribuídas:** 44000 a 44895, pela ordem das etapas A (banda baixa, banda alta), B, C, D, E e, dentro de cada etapa, por semente crescente e pela ordem dos braços da tabela.
- **Por atribuir:** 44896 a 44919 (24), não usáveis.
- **Reserva:** 44920 a 44999 (80), intocada; não pode repetir, completar nem substituir nada.
- **Proibidas:** 50000 a 59999 (divisão do M14, gasta); 3000 a 3099 e 6000 a 6099 (M10). O executor **não** pode importar `ROCKET_PROTECTED` de `exec/src/seeds.rs` tal como está, porque essa lista inclui 44000 a 44999; tem a sua própria lista, com 44000 a 44999 recusado sem `--freeze <commit>` válido.
- **Já vistas, não utilizáveis como confirmação:** 41000 a 41999, 42000 a 43999, 45000 a 46999, 47000 a 47019, 32000 a 32099, 33500 a 33529, 30001, 30017, e as do G3 do M9.1 (2000 a 2029).
- **Independência entre etapas.** Blocos disjuntos. Com a opção 6 as etapas A e D deixam de ser evidência independente para H1 e para as mitigações.

## Execução e congelamento

1. Escrever o executor `scripts/m19_g3_confirm.py` e a análise `scripts/m19_g3_analyse.py`; recusam 50000 a 59999 sempre, 44000 a 44999 sem `--freeze <commit>` válido (antepassado de `HEAD`, árvore limpa, hashes iguais) e sementes fora do mapa acima. Testam-se só com sementes 41900 a 41999 e sem ler hipóteses. A análise implementa as funções de `scripts/m19_g3_power.py` (limiares exatos, McNemar, intervalos por estatísticas de ordem, Clopper-Pearson); o teste `tests/test_m19_g3_power.py` é a especificação numérica.
2. Passo de equivalência de bytes (ver «Fontes fixadas»), antes do congelamento.
3. Criar `docs/m19-g3-onset-freeze.json` com o sha256 dos blobs de: este protocolo; os ficheiros da tabela de fontes; `scripts/m19_g3_power.py`, `calculations.json` e os dois scripts do passo 1; o `source_sha256` do `vv-rocket` (hoje `295a45b2...`), o sha256 do binário, a versão do `rustc` e o comando de compilação; a versão do Python; o commit da árvore fixada.
4. O congelamento é um commit só com esse ficheiro, enviado para o repositório público antes da primeira execução. O registo da execução grava o commit de congelamento, a máquina e o comando.
5. Publicar o protocolo, o congelamento, o registo e a análise, qualquer que seja o resultado.

## Cálculos de preparação

Nenhum usou o simulador nem sementes do simulador. Tudo é exato (aritmética inteira sobre um denominador comum), exceto o cruzamento Monte Carlo de H3.

- **Reprodução do M15.** Limiares 154, 155, 228, 79 e 80; potências 0,307, 0,793 e 0,999 (H1 e H2, π = 0,95; 0,97; 0,99); 0,064 para π = 0,93 com n = 160; posições 20 e 41 e 19 e 42; limites de Clopper-Pearson (0 de 480: 0,95 %; 13 de 480: 4,97 %).
- **Tamanho mínimo para n sucessos em n rejeitarem H0: π ≤ 0,9:** 44 (0,01), 51 (0,01/2), 55 (0,01/3), 63 (0,01/7), 69 (0,01/14). Pares discordantes mínimos do McNemar: 10 (0,01/7) e 11 (0,01/14).
- **Modelo do estimador.** `scripts/m14_masking_model.py`, inalterado: b* = 11,989 m para qualquer início em (0; 20] s; os valores do M15 mantêm-se.
- **Corolário do modelo.** Com 7 inícios, a banda baixa {5; 7; 9; 10,5} está abaixo de b* e a alta {13,5; 17; 22; 30} acima, em todos.

## Ameaças à validade

As do M15 (construção, interna, exploração prévia, externa, estatística, revisão) mantêm-se. Acrescentam-se:

- **Contagens de evidência.** Os limites de p0, q e H2 contam execuções que partilham sementes; o limite por semente distinta é mais baixo.
- **Independência dos braços.** As potências das opções 1 e 2 supõem braços independentes dada a semente; não se mediu a dependência.
- **Reconstrução de b_s.** A potência de H3, S1 e S2 usa uma distribuição reconstruída de 20 sementes e deslocamentos escolhidos aqui.
- **Estado dos dados.** O M9.1 (2000 a 2029) e o M14 (32000 a 32099) estão fora das faixas deste protocolo, mas os resultados sugeriram as hipóteses.
- **Equivalência do simulador** assente em leitura do diff, não em execução.

## Decisão do responsável

Este documento não pede aprovação de execução. Pede, por esta ordem: (1) escolher a opção de H1 (e, com ela, o nível do achado conjunto, a substituição ou não do início removido e a afetação das sementes por atribuir); (2) ler o texto corrigido, de preferência por um engenheiro externo; (3) só então decidir se aprova ou rejeita. A aprovação autoriza a escrita e o teste dos dois scripts em sementes de desenvolvimento, o passo de equivalência, o commit de congelamento e o uso das sementes 44000 a 44895 só para esta execução. Qualquer alteração produz um novo candidato.

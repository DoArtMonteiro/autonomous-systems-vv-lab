**CORRECTED CANDIDATE — NOT HUMAN-REVIEWED — NOT APPROVED FOR EXECUTION**

# Protocolo de confirmação do G3 com viés GNSS tardio (candidato corrigido M19)

## Estado

**Candidato corrigido. Não congelado, não executado, não aprovado, não revisto por pessoas.** Corrige `docs/m15-g3-onset-protocol.md`, que fica inalterado, tal como o pacote `docs/review/g3-onset/` (os hashes de ambos estão fixados abaixo e o teste `tests/test_m19_g3_power.py` verifica-o). Todas as escolhas de desenho deste documento são **propostas pelo autor do candidato, não decididas pelo responsável**; o que o responsável tem de decidir está em «Por decidir pelo responsável».

O critério G3 do M9.1 não muda. Foi registado e suportado com o viés presente desde 0 s; este protocolo testa hipóteses novas sobre inícios posteriores. Todos os resultados sobre o instante de início continuam **exploratórios** até haver aprovação, execução e um congelamento anterior à primeira simulação.

Nenhuma simulação foi corrida para escrever este documento, nem com as sementes 44000 a 44999 nem com as de 80904 a 81999. Para 80904 a 81999 só se fez aritmética de estado inicial e de posição, e nenhuma palavra de saída foi gerada. Para 44000 a 44999 gerou-se, em testes e numa verificação interativa, um número pequeno de palavras de saída de quatro fluxos, o que a regra do responsável não autoriza: está registado em «Operações de RNG já realizadas», e é uma das razões por que essas sementes saem do conjunto confirmatório. Não se correu `vv-rocket`, `vv-exec` nem `cargo`. Os números vêm de leitura de código, de evidência guardada e de aritmética exata em `scripts/m19_g3_power.py` (só biblioteca padrão), cuja saída está em `docs/evidence/m19/g3-candidate/calculations.json`.

- sha256 de `scripts/m19_g3_power.py` (bytes do blob, fim de linha LF): `49c7aeed709b3df874a3579416d1ddefd361af52e0ded83e477b1ec430a0c41a`
- sha256 de `docs/evidence/m19/g3-candidate/calculations.json`: `543dacb8582c660441157e3c9228cb29b0f38ee60f9a831f7e18900a0ed1160a`
- Reprodução: `python scripts/m19_g3_power.py --check docs/evidence/m19/g3-candidate/calculations.json` (não escreve nada, devolve 0 se os bytes coincidirem).

**Escolhas do responsável, só para a preparação do protocolo.** O responsável prefere mover a execução confirmatória para o bloco **81000 a 81919** e usar a alocação **B**. Ambas estão aplicadas aqui **apenas à preparação** (sem congelamento nem execução), sujeitas a verificação metodológica e a revisão humana. 44000 a 44999 continuam protegidas e sem uso. Regra do responsável para a análise do gerador: só é permitida análise estrutural ou matemática que não exponha nem explore sequências protegidas; gerar ou inspecionar palavras de saída de sementes protegidas (44000 a 44999, 3000 a 3099, 6000 a 6099, 50000 a 59999 e o novo bloco, depois de atribuído) e escolher sementes com base em resultados não são autorizados.

**Achado que motivou a mudança.** Na versão anterior (44000 a 44919), 258 sementes partilhavam palavras de saída com fluxos de sementes já vistas (288 pares, sempre fontes diferentes). A causa é estrutural: o estado inicial é `seed ^ (fonte × G)`, logo, para duas fontes e um desvio de k saídas, a semente parceira fica fixada por uma máscara XOR constante; o mesmo acontece entre as próprias faixas já vistas, em todo o repositório. Para o bloco 81000 a 81919 a verificação por aritmética de posição não encontra sobreposição (ver «Independência entre sementes»).

A etiqueta do topo contém duas vezes o carácter U+2014 por **exceção explícita, mandatada pelo responsável, à regra de `AGENTS.md`**; é o único uso neste documento.

**Revisão por agentes não é revisão humana por pares.** Recomenda-se a leitura por um engenheiro que não participou no M13, no M14, no M15 nem no M19.

## Diferenças face ao candidato M15

| # | Tema | Candidato M15 | Este candidato |
| --- | --- | --- | --- |
| 1 | Estado | «Candidato a protocolo congelado» | Candidato corrigido, não congelado; etiqueta no topo (U+2014 por exceção mandatada) |
| 2 | Inícios T | 8, com 0,01 s e 0,1 s | 7 ({0,1; 1; 2; 5; 10; 15; 20} s): um início em (0; 0,1] s só se vê no passo 10 do GNSS, logo 0,01 s e 0,1 s têm a mesma história de sensores |
| 3 | n mínimo com n sucessos em n | «63» ao nível 0,01/14 | 63 ao nível 0,01/7; 69 ao nível 0,01/14 |
| 4 | S4 e S5 | McNemar a 0,01/14 mais fração ≥ 0,9; «confirmada» | teste de sinais exato unilateral sobre os pares discordantes a 0,01/7, mínimo 10 pares discordantes (interseção-união entre as duas condições); veredicto «direção confirmada»; nível 0,9 só descritivo |
| 5 | H1 | Conjunção (0 s cumpre e tardio falha), n = 160 | H1a «R1 falha com início tardio», n = 168, 162 de 168 a 0,01/3 |
| 6 | Família primária | Bonferroni 0,01/3 | Holm sobre {H1a, H2, H3} (0,01/3, 0,01/2, 0,01) |
| 7 | Palavras licenciadas | «achado confirmado», «mecanismo confirmado» | «R1 falha com início tardio» (família); «R1 pior com início tardio do que com início 0 s, na mesma semente» (porta McNemar); «G3 replicado no conjunto das bandas testadas» (porta H1b); «mascaramento» só com a porta McNemar e S4, S5 e S6; perfil de R5 descritivo, troca R1 por R5 exige S3 |
| 8 | H1b | não existia | braços de 0 s de A_low e A_high agrupados (n = 336), 316 de 336 a 0,01 |
| 9 | Classificação | H1, H2 e H3 preditivas | só H3 preditiva; as restantes a posteriori |
| 10 | Tamanhos e limiares | n = 160 (H1, H2, S3), 240 (M1), 80 (M2, S7) | A_low e A_high 168; H2 162 de 168; S3 e S6 163 de 168; M1 220 de 231; M2 76 de 77; S7 77 de 77 |
| 11 | Etapas D e E | D 320 sementes (10 repetições), E 160 | D 308 (11 repetições), E 152 (19 pontos por família): 460 pares, o mínimo para o orçamento de invariantes é 459 |
| 12 | Bloco e mapas | 44000 a 44999 (a guarda do repositório protege-o) | 81000 a 81919: atribuídas 81000 a 81915 (916 sementes, 5736 execuções), 4 por atribuir; reserva 80904 a 80983; 44000 a 44999 protegidas e sem uso |
| 13 | Orçamento de regressão | 480 pares; R2 a R6 13 eventos | 460 pares; invariantes 0 eventos (0,996 %); R2 a R6 12 eventos; R1 a 0 s 1 evento em 308 |
| 14 | Estimando e células | proporção agregada | média da grelha; célula com maioria contrária nomeada, retira «qualquer início»; tabela de tolerância a células inteiras |
| 15 | Exposição mínima e resultados não avaliados | sem regra | exposição de pelo menos 11 medidas de GNSS enviesadas (1,0 s) por par de sementes, exclusão ao nível do par, teto de 5 %; tratamento de `no_contact` e `evaluated = false` por teste |
| 16 | Etapa inválida | inválida e sem substituição | fecha todas as portas a jusante |
| 17 | H3 e b_s | veredicto sem aviso; b_s indefinido nos extremos | declara confirmação com probabilidade ≈ 1 até 0,5 m; convenção: +infinito acima de 14,0 m e «no máximo 10,0» abaixo |
| 18 | Cenários de potência | π único, taxas de 100 % possíveis | cenários ancorados na incerteza: limites de Clopper-Pearson e posteriori de Jeffreys por semente e por execução, grelha de taxas e potência média a posteriori exata |
| 19 | Independência entre sementes | assumida | aritmética de posição sobre o SplitMix64: sem sobreposição dentro do bloco, contra um inventário do repositório e contra todas as sementes até 2^24 |
| 20 | Operações de RNG | não aplicável | secção «Operações de RNG já realizadas»; sem geração de palavras para sementes protegidas ou confirmatórias |
| 21 | Sementes protegidas e execução | lista própria do executor | a guarda do repositório, alterada por commit aprovado pelo responsável; sem lista privada |
| 22 | Reserva e sementes por atribuir | reserva intocada | qualquer uso posterior é um novo confirmatório, com nível próprio, que conta esta execução como vista |
| 23 | `source_sha256` do `vv-rocket` | `12b276cb...` | `295a45b2...`; passo de equivalência de bytes por correr |
| 24 | Citações de linha | números de linha | identificadores e hashes |
| 25 | Janela do mediador | [início; início + 1,0 s] | [início efetivo; início efetivo + 1,0 s] |
| 26 | Ameaças à validade | as do M15 | acrescenta binomial agrupado sobre células heterogéneas (Hoeffding), desenho Halton fixo, exposição pós-tratamento, tempo até ao contacto como inferência, limites do inventário de sementes |

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
- **Inferência, não medição.** O início a 20 s deixa cerca de 3 s até ao contacto nominal (23,3 a 23,6 s, de `docs/m9-powered-landing.md`, caso nominal de outros controladores). O tempo até ao contacto nas sementes dispersas do `guarded` **não foi medido**; o teste do M14 (0 de 20 a 8 m com início a 20 s) é compatível com o viés a atuar, não o prova para todas as sementes. Por isso há regras de exposição mínima (ver «Regras de decisão»).
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
| M14, fragilidade, braços por início | 2026-11-03 17:07 a 17:43 | 32000 a 32029 (a fragilidade completa usa 32000 a 32099) | Início 0 s: R1 cumprido em 180 de 180 (6 magnitudes de 5 a 30 m). Inícios 2, 5 e 10 s: R1 falha em 30 de 30 a 5 e 10 m e cumpre-se a 15 m ou mais. Primeira vez que se viu R1 a falhar com início tardio e a cumprir-se acima de 15 m. |
| M13, investigação | dados de 2026-11-03; evidência no commit de 21:31 | 42000 a 43999 | Envelope 16 × 16 com 4 sementes: linha de 0 s com 64 de 64; 240 de 240 falhas com início tardio a 10 m ou menos; 660 de 660 cumprimentos a 13,3 m ou mais. Contraexemplo reduzido (0,02 s, 9,72 m). Limiar 1 m: 280 pares corrigidos e 35 compromissos. |
| M14, previsão e teste | 20:20 e 20:25 | 47000 a 47019 | P1: b50 = 11,89 m contra b* = 11,99 m. P2: a 8 m, só o início 0 s evita que R1 falhe com início tardio (0,01, 0,02 e 0,1 s são uma só condição). |
| M14, revisão independente | 2026-11-03 | 33500 a 33529 | Inícios 0,5 e 1 s: R1 em 0 de 30 a 5 e 10 m. |
| Desenvolvimento e ensaios | | 41000 a 41999 (41000 a 41009 à mão), 45000 a 46999 (45000 a 45003 na revisão), 30001, 30017 | Gastas. |

Nenhuma destas sementes volta a servir de confirmação. A previsão P1 foi fixada (`73c9ff5`, 20:20) antes do teste (`1195c1b`, 20:25); o autor já tinha visto a transição grosseira entre 10 e 15 m (fragilidade F6: 12,5 m é o único nível com execuções que cumprem todos os requisitos, 24 de 100).

### Classificação corrigida

«A posteriori» quer dizer: a hipótese, os níveis ou o limiar foram escritos depois de ver dados de desenvolvimento sobre as mesmas condições. Uma hipótese a posteriori confirmada com sementes novas e regras fixadas à partida confirma o efeito; não é uma previsão cumprida.

| Hipótese | Classe no M15 | Classe corrigida | Razão |
| --- | --- | --- | --- |
| H1a (R1 falha com início tardio) | preditiva («P2 generalizada») | **a posteriori** | P2 só previa a 8 m e só dizia «inícios de 0,01 a 20 s mascaram». As magnitudes {5; 7; 9; 10,5} e os 7 inícios vêm da fragilidade M14 e do envelope M13, anteriores ao protocolo. |
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

### Família primária (erro de família 0,01, Holm)

- **H1a, R1 falha com início tardio (a posteriori).** Com início tardio em T e magnitude na banda baixa {5; 7; 9; 10,5} m, R1 **falha** (avaliado e não cumprido). Teste binomial exato de π ≤ 0,9, n = 168; limiares 162 de 168 (a 0,01/3), 161 de 168 (a 0,01/2 e a 0,01).
- **H2, recuperação (a posteriori).** Com início tardio em T e magnitude na banda alta {13,5; 17; 22; 30} m, R1 cumpre-se. n = 168; limiares 162 de 168 (a 0,01/3), 161 de 168 (a 0,01/2 e a 0,01).
- **H3, fronteira (preditiva).** Com início a 5 s, a magnitude mediana de transição b50 está a menos de 1 m de b* = 11,99 m. Intervalo da mediana por estatísticas de ordem, n = 60; posições (20; 41) a 0,01/3 e a 0,01/2, (21; 40) a 0,01. A tolerância de 1 m foi fixada em `prediction.json` e não é exigente.

**Holm de passo descendente.** Ordenam-se os p valores exatos, p(1) ≤ p(2) ≤ p(3). Rejeita-se a hipótese de p(1) se p(1) ≤ 0,01/3; depois a de p(2) se p(2) ≤ 0,01/2; depois a de p(3) se p(3) ≤ 0,01; pára-se na primeira que falhe. Em testes discretos o p valor de H1a e de H2 vem dos limiares das três colunas; em H3 vale a posição do intervalo ao nível correspondente. Não se mistura com uma cadeia Bonferroni 0,01/3 à parte.

**Portas em série (ordem fixa).** Só depois de H1a, H2 e H3 estarem rejeitadas pelo Holm:

1. **Porta McNemar.** Teste exato emparelhado, unilateral, ao nível 0,01, sobre as sementes da banda baixa de A (168 antes de exclusões): par a favor = R1 cumpre-se a 0 s e falha no início tardio, na mesma semente; par contra = o inverso, e também qualquer par com R1 não avaliado num dos braços. Rejeita se o teste de sinais exato sobre os pares discordantes der p < 0,01 (o mínimo natural é 7 pares discordantes). **Licencia só a frase «R1 pior com início tardio do que com início 0 s, na mesma semente».**
2. **Porta H1b.** Só se a porta 1 rejeitar: R1 cumpre-se a 0 s, π > 0,9, ao nível 0,01, com os braços de 0 s de **ambas as bandas** (A_low 168 e A_high 168, n = 336), 316 de 336 ou mais. **Licencia «G3 replicado no conjunto das bandas testadas»** (5 a 10,5 m e 13,5 a 30 m); as taxas de cada banda reportam-se descritivamente, ao lado.
3. **Porta de mecanismo.** A palavra **«mascaramento»** só se pode usar se a porta McNemar **e** S4, S5 e S6 forem confirmadas, cada uma ao seu nível da família secundária (0,01/7). S4, S5 e S6 são testadas em qualquer caso; a porta só lê o resultado.

**Controlo de erro da palavra «mascaramento».** É uma conjunção de componentes (Holm, McNemar a 0,01, S4, S5 e S6 a 0,01/7 cada), isto é, um teste de interseção-união: só se afirma se todos rejeitarem, logo o erro de a afirmar sem que seja verdade não passa do nível do componente falso, no máximo 0,01. A contabilidade da família secundária (0,01/7 por teste) não muda, porque S4, S5 e S6 não são testadas outra vez.

**Perfil de R5.** O perfil de R5 reporta-se sempre, descritivamente, com R1. Qualquer afirmação de que um viés tardio ou grande troca R1 por R5 exige que S3 seja confirmada.

Descritivamente, e sem critério, reporta-se também a regra própria do G3 (fração de sementes a 0 s com R1 cumprido, e se é pelo menos 0,9, o equivalente a 27 de 30) e uma estimativa agrupada dos braços sem mitigação de A e de D (só descritiva).

### Família secundária (erro de família 0,01, Bonferroni, 0,01/7 por teste)

S1 a S7 como no M15 (S1: H3 com início a 15 s, posições 19 e 42; S2: H3 a 5 s com tolerância 0,5 m; S3: R5 falha a 0 s na banda alta; S4: `guarded` sem regra 2 cumpre R1 e `robust` falha; S5: limiar 1000 m faz R1 falhar onde o `guarded` registado cumpre; S6: primeira rejeição dentro da janela; S7: limiar 2 m falha a 5 m e cumpre a 10,5 m), todas a posteriori. As alterações são de contagens e de palavras:

- **S4 e S5, nível.** São duas hipóteses da família de 7, cada uma confirmada só se **as duas** condições (0 s e 15 m; 5 s e 15 m) rejeitarem. Numa regra de interseção-união cada condição é testada ao nível total do teste, 0,01/7; o M15 aplicava 0,01/14, o que conta a multiplicidade duas vezes.
- **S4 e S5, o que se pode concluir com 60 sementes.** Um teste binomial contra 0,9 só rejeita com n sucessos em n se 0,9^n ≤ α. A 0,01/7 isso exige n ≥ 63 (0,9^63 = 0,00131; 0,9^62 = 0,00146 > 0,00143); a 0,01/14 exigiria 69. Com 60 sementes nenhum dos dois é possível, e a regra «54 de 60» do M15 aceita taxas verdadeiras de 0,85 com probabilidade 0,185. **Uma só regra em todo o documento:** teste de sinais exato unilateral sobre os pares discordantes, a 0,01/7 em cada condição, com um mínimo de 10 pares discordantes; os pares com R1 não avaliado em qualquer braço contam como discordantes no sentido contrário; confirma-se com as duas condições. Com 1 % de pares contrários a potência por condição é pelo menos 0,9999 se a taxa prevista for 0,5 ou mais. O **nível 0,9 só se descreve**: fração observada e limite inferior de Clopper-Pearson a 99 % (54 de 60: 0,774; 57 de 60: 0,842; 60 de 60: 0,926). Veredicto: «direção confirmada (teste exato emparelhado a 0,01/7, mínimo 10 pares discordantes); nível 0,9 descritivo, com limite de Clopper-Pearson». Fica por afirmar que a taxa seja pelo menos 0,9. Um teste binomial a 0,01/7 exigiria mais sementes (63, 70, 77, 84: tolera 0 falhas; 100: 1 falha; 150: 4 falhas, potência 0,531 com π = 0,97); não se propõe.
- **S4 e S5, definição de sucesso.** O par é a favor se o primeiro braço cumpre R1 e o segundo falha, na mesma semente (S4: G0 contra `robust`; S5: o `guarded` registado contra o braço de 1000 m), e é contra no caso inverso; a taxa prevista de pares a favor só entra na descrição e na potência, não no critério.
- **S6.** O denominador é o conjunto das sementes tardias de A (banda alta) com a exposição mínima, cerca de 168, **fixo**: o sucesso é a primeira rejeição dentro da janela; as sementes **sem rejeição contam como não sucesso** (e reportam-se, tal como as rejeições tardias). Assim o denominador não depende do resultado e a potência não muda (163 de 168 ao nível 0,01/7; abaixo de 63 sementes expostas, S6 é inconclusiva por construção). S3, S6, H1b e a porta McNemar usam as mesmas exclusões ao nível do par de sementes que H1a e H2.

### Família de mitigação (erro de família 0,01, Bonferroni, 0,01/2 por teste)

M1 (limiar 1 m; n = 231; rejeita com 220 de 231 ou mais) e M2 (limiar 2 m a 10,5 m; n = 77; rejeita com 76 de 77 ou mais). Ambas a posteriori.

**Verificações estruturais.** Iguais às do M15 (determinísticas; uma exceção suspende a leitura do código e S4).

## Desenho

Caso base: `exec/cases/m13/g3-registered.json` (política `guarded`, `gnss_bias` de 0 a 40 s, esquema v1). Cada execução altera só os ponteiros indicados. **Inícios tardios: T = {0,1; 1; 2; 5; 10; 15; 20} s** (7). Mesma semente em braços diferentes é emparelhamento intencional (os braços de uma semente usam os mesmos fluxos); etapas diferentes usam sementes disjuntas.

| Etapa | Sementes | Mapa semente para condição | Braços por semente | Execuções |
| --- | --- | --- | --- | --- |
| A, banda baixa | 81000 a 81167 (168) | 81000 + 24·i + 6·j + r; i = 0 a 6 (índice do início em T), j = 0 a 3 (magnitude em {5; 7; 9; 10,5}), r = 0 a 5 | início tardio; início 0 s | 336 |
| A, banda alta | 81168 a 81335 (168) | 81168 + 24·i + 6·j + r; i = 0 a 6, j = 0 a 3 (magnitude em {13,5; 17; 22; 30}), r = 0 a 5 | início tardio; início 0 s | 336 |
| B, fronteira | 81336 a 81395 (60) | cada semente em todos os níveis | magnitudes 10,0 a 14,0 m, passo 0,25 (17), com início 5 s e 15 s | 2040 |
| C, mecanismo | 81396 a 81455 (60) | cada semente nas 3 condições | condições (0 s, 15 m), (5 s, 15 m), (5 s, 8 m) × braços G registado, G0 sem regra 2, R `robust`, N limiar 1000 m | 720 |
| D, mitigação | 81456 a 81763 (308) | 81456 + 44·i + 11·j + r; i = 0 a 6, j = 0 a 3 (magnitude em {5; 8; 10,5; 15}), r = 0 a 10 | {início tardio; 0 s} × {sem; 1 m; 2 m} | 1848 |
| E, famílias | 81764 a 81915 (152) | 81764 + 19·f + k; f = família pela ordem de `g3-onset.json` (0 a 7), k = ponto Halton 0 a 18 | {sem; 1 m; 2 m} | 456 |
| Por atribuir | 81916 a 81919 (4) | nenhuma | | 0 |
| Reserva proposta | 80904 a 80983 (80) | intocada | | 0 |

Total: **916 sementes atribuídas, 5736 execuções**. Verificado por enumeração em `scripts/m19_g3_power.py` (`seed_map`, `seed_checks`) e pelo teste: cada semente tem uma só condição; todas estão em 81000 a 81919; nenhuma está na reserva, em 44000 a 44999, em 3000 a 3099, 6000 a 6099, 50000 a 59999 nem nas faixas já vistas; as faixas das etapas são contíguas e disjuntas; as células de A e D têm 6 e 11 sementes cada.

**Alocação.** É a opção B do responsável (A_high com 6 repetições, E com 19 pontos Halton por família); a opção A anterior (A_high com 5 repetições, E com 20 pontos) fica custeada em «Por decidir pelo responsável».

**Porque 11 repetições em D.** O orçamento de invariantes exige limite a 99 % ≤ 1 % com 0 eventos, o que pede pelo menos 459 pares por mitigação. D tardio com 10 repetições dá 280 + 152 = 432 pares, impossível; com 11, 308 + 152 = 460 pares (limite 0,996 %).

As 4 sementes 81916 a 81919 **estão por atribuir** e a reserva proposta 80904 a 80983 não pode repetir, completar ou substituir nada desta execução (ver «Sementes»).

Os pontos Halton da etapa E (bases 2 e 3, ou 2 numa família de um parâmetro, a partir do índice 1, quantizados como em `exec/src/search.rs`, 19 por família) e as gamas de `g3-onset.json` mantêm-se como no M15.

## Resultados medidos

Como no M15: por execução o executor grava semente, condição, braço, `outcome`, R1 a R6 (`evaluated`, `pass`, `value`), invariantes S1 a S5, `altimeter_rejected_first`, `sensor_disagreement_first` e os sha256 de `verification.json` e `trace.json`. Nada se lê do traço amostrado. Mediador: rejeição na janela [início efetivo; início efetivo + 1,0 s]; tardia: depois da janela. Transição por semente (etapa B): b_s é o menor nível a partir do qual R1 se cumpre nesse e em todos os seguintes; b50 é a mediana de b_s; sementes não monótonas contam-se, reportam-se e **entram** na mediana com o seu b_s. **Convenção nos extremos:** uma semente em que R1 não se cumpre no nível mais alto (14,0 m) tem b_s = +infinito, conta acima de todos os valores finitos e nunca fica abaixo de b* + tolerância (um limite superior infinito não confirma); uma semente em que R1 já se cumpre em todos os níveis, incluindo 10,0 m, tem b_s «no máximo 10,0 m», registado como 10,0 m com a marca «no máximo» e contado no limite inferior como não superior ao nível mais baixo. Um nível sem R1 avaliado conta como R1 não cumprido nesse nível. `scripts/m19_g3_power.py` (`b_s_per_seed`) implementa-a.

## Análise

### Testes, níveis, limiares e potência

Testes binomiais exatos unilaterais de H0: π ≤ 0,9 (unidade: a semente). Potência por π verdadeiro (assumindo independência entre sementes); o efeito mínimo detetável (MDE) é o menor π, em passos de 0,001, com potência 0,8. Os valores M15 estão em `calculations.json` (`tests`, chaves `M15_*`) e coincidem com o pacote de revisão.

| Teste | Nível | n | Rejeita com | Falhas toleradas | Potência com π = 0,95 / 0,97 / 0,99 | MDE |
| --- | --- | --- | --- | --- | --- | --- |
| H1a (Holm; a porta H1b usa 0,01) | 0,01/3; 0,01/2 e 0,01 | 168 | 162 de 168; 161 de 168 | 6; 7 | 0,260 / 0,758 / 0,998 (a 0,01/3) | 0,972 |
| H2 (Holm) | 0,01/3; 0,01/2 e 0,01 | 168 | 162 de 168; 161 de 168 | 6; 7 | 0,260 / 0,758 / 0,998 (a 0,01/3) | 0,972 |
| H1b (porta; 0 s, bandas baixa e alta agrupadas) | 0,01 | 336 | 316 de 336 | 20 | 0,825 / 0,999 / 1,000 | 0,949 |
| S3 | 0,01/7 | 168 | 163 de 168 | 5 | 0,150 / 0,609 / 0,993 | 0,977 |
| S6 (n = sementes expostas) | 0,01/7 | 168 | 163 de 168 | 5 | 0,150 / 0,609 / 0,993 | 0,977 |
| S7 (cada proporção) | 0,01/7 | 77 | 77 de 77 | 0 | 0,019 / 0,096 / 0,461 | 0,998 |
| M1 | 0,01/2 | 231 | 220 de 231 | 11 | 0,512 / 0,952 / 1,000 | 0,961 |
| M2 | 0,01/2 | 77 | 76 de 77 | 1 | 0,097 / 0,324 / 0,820 | 0,990 |

Em M15, com n = 160: H1 e H2 154 de 160 (potência 0,307 / 0,793 / 0,999), S3 155 de 160, M1 228 de 240, M2 79 de 80, S7 80 de 80.

S7 só se confirma se as duas proporções derem 77 de 77; com π = 0,99 em cada uma a potência conjunta é cerca de 0,21 (0,461 ao quadrado). É um teste exigente.

### Fronteira (H3, S1, S2)

Intervalo da mediana sem distribuição: [X(l) − 0,25; X(u)], com n = 60 e posições (20; 41) ao nível 0,01/3 (H3) e (19; 42) ao nível 0,01/7 (S1, S2). S1 reutiliza a distribuição de b_s de 5 s para o início de 15 s, o que é um pressuposto, não um dado (a potência de S1 é ilustrativa). Confirma-se se o intervalo cabe dentro de b* ± tolerância (1 m em H3 e S1; 0,5 m em S2); refuta-se se ficar inteiramente fora.

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

- **Família primária:** Holm sobre {H1a, H2, H3} ao nível 0,01. Depois, portas em série (McNemar, H1b), cada uma ao nível 0,01 e só se a anterior e a família rejeitarem; uma sequência fixa depois de uma família com erro 0,01 não aumenta o erro do título. A porta de mecanismo (palavra «mascaramento») é uma interseção-união de componentes já contabilizados: o erro não passa de 0,01.
- **Família secundária:** Bonferroni 0,01/7. **Mitigação:** Bonferroni 0,01/2. **Entre famílias não há correção:** o erro máximo agregado é 0,03; os limites do orçamento de regressão também não têm correção.
- **Potência baixa arrisca uma execução inconclusiva, não uma afirmação falsa.** O erro de afirmar sem que seja verdade fica controlado pelo procedimento; a potência só diz com que probabilidade a execução chega a uma conclusão.

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

### Opções consideradas (n = 168, um só teste ao nível 0,01/3)

Cenários (p0; q): (1,00; 1,00), (0,99; 0,99), (0,97; 0,99), (0,95; 0,99), (0,93; 0,99), (0,93; 1,00), (0,90; 1,00, o piso do G3), (1,00; 0,93, equivalente a um início em sete a falhar metade das vezes). Todas as potências são exatas, sob independência entre os dois braços da mesma semente; no ficheiro de cálculos há também os limites de Fréchet das opções 1 e 2 (a diferença não passa de 0,002).

| Opção | O que testa | (0,99; 0,99) | (0,97; 0,99) | (0,95; 0,99) | (0,93; 0,99) | (0,93; 1,00) | (1,00; 0,93) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0. Conjunção M15 | π = p0 · q > 0,9 | 0,948 | 0,498 | 0,123 | 0,018 | 0,047 | 0,047 |
| 1. Separar, ambas exigidas | H1a: q > 0,9 e H1b: p0 > 0,9, ambos a rejeitar | 0,997 | 0,757 | 0,260 | 0,046 | 0,047 | 0,047 |
| 2. Condicional | H1b, e q > 0,9 entre as sementes com R1 cumprido a 0 s | 0,997 | 0,757 | 0,260 | 0,046 | 0,047 | 0,047 |
| 3. Emparelhado (McNemar exato) | a falha tardia é mais provável do que a de 0 s | 1,000 | 1,000 | 1,000 | 1,000 | 1,000 | 1,000 |
| 4. Separar, H1b só controlo | H1a: q > 0,9, com H1b e McNemar como portas depois da família | 0,998 | 0,998 | 0,998 | 0,998 | 1,000 | 0,047 |
| 5. Separar, nula 0,8 em H1b | q > 0,9 e p0 > 0,8 | 0,998 | 0,998 | 0,998 | 0,984 | 0,986 | 0,047 |
| 6. Agrupar braços de A e D (n = 399) | opção 1 com 168 + 231 sementes | 1,000 | 0,999 | 0,852 | 0,255 | 0,255 | 0,255 |

Notas:

- **A opção 1 não resolve o problema de fundo.** Separa as duas afirmações, mas H1b continua a ser um teste de p0 > 0,9 com 168 sementes, com potência igualmente baixa quando p0 é 0,95 ou menos (0,260 com p0 = 0,95). O que a separação ganha é que H1a deixa de depender de p0 (0,998 em todos os cenários com q = 0,99).
- **Opção 2** dá o mesmo que a opção 1 (os braços são independentes no modelo); é útil quando a pergunta é «entre as sementes em que o G3 registado cumpre, o início tardio falha?», não para a potência.
- **Opção 3** tem potência 1,000 em todos os cenários, mesmo a 0,90, porque o teste de sinais só compara quem difere. Suporta a afirmação **mais fraca** «um início tardio piora R1 em relação a 0 s», sem níveis absolutos; não suporta «falha em 90 % ou mais» nem «cumpre em 90 % ou mais».
- **Opção 4** separa de facto as duas afirmações: o resultado «R1 falha com início tardio» deixa de depender do G3 a 0 s. É a base do desenho proposto, com a porta McNemar da opção 3 e a porta H1b a seguir.
- **Opção 5** (H1b contra 0,8, limiar 149 de 168) altera a afirmação para «não substancialmente pior do que o G3 registado»; o 0,8 não está justificado por nenhum critério existente.
- **Opção 6** (agrupar os braços sem mitigação de A e de D: 168 + 231 = 399 sementes na banda baixa, 168 + 77 = 245 na alta; limiares 375 de 399 e 233 de 245) dá a maior potência sem sementes novas (MDE 0,948), mas as realizações de ruído de D passariam a servir H1 e M1 e M2, e perder-se-ia a independência entre a conclusão sobre H1a e a conclusão sobre mitigações. **Não proposta como teste; usa-se só como estimativa agrupada descritiva** (a porta H1b agrupa só os braços de 0 s de A).
- **Mais sementes para a opção 0:** com p0 = 0,93 e q = 1,00 são precisas cerca de 1130 sementes (900 ao nível 0,01); com p0 = 0,95 e q = 0,99, 610 (500). Fora do orçamento (a banda baixa tem 168 de 916).
- **Efeito mínimo detetável simétrico (p0 = q, potência 0,8):** 0,986 para a opção 0 e 0,977 para a opção 1 com n = 168; 0,974 e 0,953 com n = 399.

### Desenho proposto: Holm e portas em série

**Nenhuma taxa se toma como exatamente 100 %.** As execuções guardadas (294 de 294 a 0 s, 520 de 520, 1160 de 1160) não provam taxa 1: só limitam a taxa por baixo. A potência avalia-se por isso (i) numa grelha de taxas, (ii) em limites coerentes com a evidência e (iii) em média a posteriori, exata (beta-binomial, posteriori de Jeffreys Beta(x + 1/2, 1/2)). Todos os valores são **ilustrativos**, com os pressupostos: n = 168 em H1a e em H2, n = 336 na porta H1b, n = 60 em H3; sementes disjuntas entre H1a, H2 e H3; taxas de 0 s das duas bandas e posterioris independentes; braços de uma semente independentes dadas as taxas; distribuição de b_s reconstruída de 20 sementes; deslocamento da fronteira 0,25 m ou 0,75 m (ou uniforme em 0; 0,25; 0,5; 0,75 m). Dizem com que probabilidade a execução conclui, não o risco de afirmação falsa, que o procedimento controla.

Evidência guardada e posterioris (limites de Clopper-Pearson a 99 % e quantis de Jeffreys; por semente conta cada semente distinta uma vez, por execução conta as execuções, que partilham sementes e por isso são otimistas):

| Taxa | Por semente | CP 99 % inferior | Jeffreys 5 % | Jeffreys 50 % | Por execução | CP 99 % inferior | Jeffreys 5 % | Jeffreys 50 % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p0: R1 cumpre-se a 0 s | 84 de 84 sementes | 0,947 | 0,978 | 0,997 | 294 de 294 execuções | 0,984 | 0,994 | 0,999 |
| q: R1 falha tardio, banda baixa | 54 de 54 sementes | 0,918 | 0,965 | 0,996 | 520 de 520 execuções | 0,991 | 0,996 | 1,000 |
| π de H2: R1 cumpre-se tardio, banda alta | 54 de 54 sementes | 0,918 | 0,965 | 0,996 | 1160 de 1160 execuções | 0,996 | 0,998 | 1,000 |

Grelha de taxa comum (p0 = q = π de H2 = p), exata, deslocamento 0,25 m; última coluna com deslocamento 0,75 m. «Holm» é a probabilidade de a família rejeitar as três; a porta McNemar tem potência 1,000 sempre que a família rejeita, por isso «R1 pior com início tardio do que com início 0 s» coincide com o Holm; «G3 replicado» inclui a porta H1b agrupada; os limites de Fréchet são os de «mascaramento» (S4 e S5 com taxa prevista 0,80, S6 com π de H2):

| p | Holm | G3 replicado | «Mascaramento», limites | Holm com deslocamento 0,75 m |
| --- | --- | --- | --- | --- |
| 0,90 | 0,000 | 0,000 | 0,000 a 0,000 | 0,000 |
| 0,93 | 0,009 | 0,002 | 0,000 a 0,009 | 0,006 |
| 0,95 | 0,155 | 0,128 | 0,000 a 0,150 | 0,117 |
| 0,97 | 0,749 | 0,748 | 0,358 a 0,609 | 0,570 |
| 0,98 | 0,959 | 0,959 | 0,837 a 0,878 | 0,731 |
| 0,99 | 0,999 | 0,999 | 0,992 a 0,993 | 0,762 |
| 0,995 | 1,000 | 1,000 | 1,000 a 1,000 | 0,762 |
| 0,999 | 1,000 | 1,000 | 1,000 a 1,000 | 0,762 |

Média a posteriori (exata; deslocamento fixo ou uniforme):

| Posteriori; deslocamento | Holm | G3 replicado | «Mascaramento», limites |
| --- | --- | --- | --- |
| Por semente; 0,25 m | 0,930 | 0,930 | 0,860 a 0,929 |
| Por semente; 0,75 m | 0,709 | 0,709 | 0,638 a 0,709 |
| Por semente; uniforme | 0,875 | 0,875 | 0,804 a 0,875 |
| Por execução; 0,25 m | 1,000 | 1,000 | 1,000 a 1,000 |
| Por execução; 0,75 m | 0,762 | 0,762 | 0,762 a 0,762 |
| Por execução; uniforme | 0,941 | 0,941 | 0,941 a 0,941 |

Taxas nos quantis da posteriori (p0; q; π de H2), deslocamento 0,25 m:

| Cenário | Taxas | Holm | G3 replicado | «Mascaramento», limites |
| --- | --- | --- | --- | --- |
| Por semente, mediana | 0,997; 0,996; 0,996 | 1,000 | 1,000 | 1,000 a 1,000 |
| Por semente, 5 % | 0,978; 0,965; 0,965 | 0,589 | 0,589 | 0,057 a 0,468 |
| Por semente, CP 99 % inferior | 0,947; 0,918; 0,918 | 0,001 | 0,001 | 0,000 a 0,001 |
| Por execução, 5 % | 0,994; 0,996; 0,998 | 1,000 | 1,000 | 1,000 a 1,000 |
| Por execução, CP 99 % inferior | 0,984; 0,991; 0,996 | 1,000 | 1,000 | 1,000 a 1,000 |

Leitura: com os dados por semente, a potência média é cerca de 0,93 (0,25 m) e 0,71 (0,75 m), mas a evidência não exclui taxas de 0,92 a 0,95, onde a potência é praticamente nula; o risco é uma execução **inconclusiva**, não uma afirmação falsa. O deslocamento 0,75 m limita a regra a cerca de 0,76 por causa de H3.

**Tolerância a células inteiras.** O estimando de H1a e H2 é a média da grelha, não cada célula. Falhas toleradas (células de 6 sementes em H1a e em H2, que podem falhar por inteiro; «maioria contrária» é 4 de 6):

| Hipótese | Nível | Rejeita com | Falhas toleradas | Células inteiras toleradas | Células com maioria contrária toleradas |
| --- | --- | --- | --- | --- | --- |
| H1a e H2 (n = 168) | 0,01/3 | 162 | 6 | 1 | 1 |
| H1a e H2 | 0,01/2 e 0,01 | 161 | 7 | 1 | 1 |

Por isso uma célula com maioria contrária pode não impedir a confirmação; as regras de decisão exigem nomeá-la e retiram nesse caso a palavra «qualquer início».

## Orçamento de regressão das mitigações

Mesma definição do M15: um evento é um par em que a mitigação **acrescenta** uma violação que a execução sem mitigação não tinha, sobre os pares em que a mitigação pode atuar (D com início tardio e E). Pares por mitigação: 308 (D tardio) + 152 (E) = 460; os 308 pares de D com início 0 s formam a categoria de verificação. Limite superior de Clopper-Pearson unilateral a 99 %.

| Categoria | Pares | Orçamento | Eventos máximos | Limite com o máximo |
| --- | --- | --- | --- | --- |
| Invariantes S1 a S5 | 460 | ≤ 1 % | 0 | 0,996 % |
| R2 a R6 (compromissos) | 460 | ≤ 5 % | 12 | 4,90 % |
| R1 com início 0 s (território do G3 registado) | 308 | ≤ 2,5 % | 1 | 2,14 % |

Os pares excluídos por exposição insuficiente (ver «Regras de decisão») saem do denominador; acima de 5 % o veredicto do orçamento é inconclusivo. O orçamento de invariantes só pode cumprir-se com pelo menos 459 pares: com 432 pares o limite a 99 % com 0 eventos seria acima de 1 %. Uma segunda ocorrência em R1 a 0 s dá 2,70 %, acima do orçamento. A previsão M15 mantém-se: o orçamento de compromissos provavelmente será excedido (nos dados de desenvolvimento, 35 compromissos em 1024 pares do envelope, 3,4 %, limite 4,98 %, e 6 em 30 no contraexemplo); a taxa com todos os pares reporta-se ao lado, identificada como diluída. As palavras do veredicto mantêm-se («eficaz para R1 no envelope declarado», «dentro do orçamento», «candidata a adoção» só com as duas).

## Regras de decisão

Para cada hipótese de proporção:

- **Confirmada:** H0 rejeitada ao nível que o procedimento da família lhe atribui (Holm na primária, Bonferroni nas outras).
- **Refutada:** fração observada no sentido previsto ≤ 0,1, ou, em H3, S1 e S2, intervalo inteiramente fora de b* ± tolerância.
- **Inconclusiva:** qualquer outro caso, com a contagem e o intervalo de Clopper-Pearson a 99 %.
- **S4 e S5:** «direção confirmada (teste exato emparelhado a 0,01/7, mínimo 10 pares discordantes); nível 0,9 descritivo, com limite de Clopper-Pearson». Nunca «taxa pelo menos 0,9 confirmada».

**Título, por ordem de portas.**

- Se H1a, H2 e H3 forem rejeitadas pelo Holm: «R1 falha com início tardio abaixo de cerca de 12 m e volta a cumprir-se acima disso» (resultado de simulação idealizada; hipótese formulada depois de ver dados de desenvolvimento, só a posição da fronteira foi prevista antes; replicado com sementes novas). O perfil de R5 reporta-se ao lado, descritivamente; não se escreve que o viés troca R1 por R5 sem S3 confirmada.
- Se a porta McNemar também rejeitar, e só então, acrescenta-se «R1 é pior com início tardio do que com início 0 s, na mesma semente».
- Se a porta H1b também rejeitar, e só então, acrescenta-se «G3 replicado no conjunto das bandas testadas: com o viés desde 0 s, R1 cumpre-se», com as taxas de cada banda (baixa e alta) ao lado, descritivamente.
- A palavra «mascaramento» só aparece se a porta McNemar e S4, S5 e S6 forem confirmadas. Sem isso, nenhuma hipótese, tabela de resultados ou título a usa. Exceção: as linhas de potência, que a nomeiam só para dizer com que probabilidade seria licenciada.
- **Refutado** se H1a ou H2 for refutada. **Mecanismo suportado** só se S4, S5 e as verificações estruturais passarem.
- Nenhum resultado altera o registo do G3 nem o grau dos pacotes M13 e M14.

**Regras fixadas antes da execução.**

- **(a) Estimando e células.** O estimando de H1a e de H2 é a média da grelha. Toda a célula (início × magnitude) com maioria de sementes contrárias (4 de 6 em H1a e em H2) é nomeada no relatório e retira a palavra «qualquer início» do título, que passa a dizer «nos inícios e nas magnitudes testados, exceto (células)». A tabela de tolerância a células inteiras está em «Opções de desenho para H1».
- **(b) Exposição mínima.** Uma execução tardia tem exposição suficiente se houve pelo menos **11 medidas de GNSS enviesadas antes do contacto** (a do início e mais dez, isto é, 1,0 s). Justificação, do modelo do estimador (`scripts/m14_masking_model.py`, sem simulador): o resíduo atinge o máximo 0,3 s depois do início e a primeira rejeição acontece 0,58 s depois com 11,99 e 12 m (o mais lento), 0,38 s com 12,5 m, 0,28 s com 13,5 m, 0,18 s com 15 m e 0,08 s com 22 e 30 m; 1,0 s cobre o caso mais lento com folga e coincide com a janela do mediador. É um valor do modelo, não uma medição do simulador. Na banda baixa (abaixo de b*) não se espera rejeição; aí a exposição só garante que o viés atuou durante pelo menos 1,0 s antes do contacto. Uma execução sem essa exposição (por exemplo, contacto antes do início a 20 s, ou `acted = false` do `gnss_bias` em `verification.json`) não testa nenhuma hipótese sobre o início tardio.
- **(c) Exclusão ao nível do par de sementes.** Se o braço tardio de uma semente não tem exposição suficiente, a **semente inteira (os dois braços)** sai de todos os testes derivados de A (H1a, H2, porta McNemar, porta H1b, S3 e S6), e o par correspondente sai dos pares de mitigação de D e E. Os números excluídos reportam-se por início. O limiar recalcula-se com o n restante, ao mesmo nível. Se as exclusões forem mais de 5 % dos pares de um teste (mais de 8 em A_low, 8 em A_high, 16 no H1b agrupado, 15 por mitigação em D, 7 em E), contam todas **contra** a hipótese com o n original: como não sucessos em H1a, H2, H1b, S3 e S6; como discordantes no sentido contrário na porta McNemar; e, nos orçamentos, o veredicto fica inconclusivo. 5 % é da ordem das falhas que os testes já toleram (6 em 168, 4 em 140). A exclusão depende do instante do contacto, que é pós-tratamento (ver «Ameaças à validade»). **Etapas B e C:** a mesma exposição mínima aplica-se por execução; uma semente de B ou de C com alguma execução sem exposição sai inteira da etapa (todas as suas execuções), com teto de 5 % (3 sementes de 60), acima do qual conta contra. **Etapa E e falhas que não são de GNSS** (perda de impulso, falhas de altímetro, viés do acelerómetro): a exposição é a falha ter atuado (`acted = true` em `verification.json`, para a falha da família) na execução sem mitigação; o par em que não atuou sai do denominador, com teto de 5 % (7 de 152). As famílias de viés de GNSS usam também a regra de 1,0 s.
- **(d) Contacto ausente e R1 não avaliado, por teste.**

| Teste ou porta | Execução sem contacto (`no_contact`) ou com R1 não avaliado |
| --- | --- |
| H1a (R1 falha) | Conta **contra** (não é falha de R1): sem contacto avaliado não há aterragem dura que apoie a hipótese; é a leitura conservadora. |
| H2 (R1 cumpre-se), H1b, S3 | Conta contra: sem contacto, R1 não está cumprido (nem R5 falhado) segundo a definição do G3. |
| Porta McNemar, S4, S5 | Par com R1 não avaliado em qualquer braço: discordante no sentido contrário. |
| S6 | Usa `altimeter_rejected_first`, que não depende do contacto; vale a exclusão por exposição. |
| Etapa B | Nível sem R1 avaliado: R1 não cumprido nesse nível. |
| M1, M2, orçamento | R1 não avaliado no braço mitigado quando o braço sem mitigação cumpre: evento de R1. |

- **(e) Etapa inválida.** Uma etapa inválida fecha todas as portas a jusante: A inválida deixa H1a, H2, as portas McNemar, H1b e de mecanismo inconclusivas; B inválida deixa H3 inconclusiva e, com ela, o Holm sem título; C inválida deixa S4, S5 e o mecanismo inconclusivos; D ou E inválidas deixam inconclusivas as mitigações e o orçamento.
- **(f) Veredicto de H3.** A frase de H3 diz que confirma com probabilidade ≈ 1 para qualquer deslocamento da fronteira até 0,5 m (1,000 a 0,25 m; 0,999999 a 0,5 m, na distribuição reconstruída), portanto a confirmação de H3 não distingue b* de b* ± 0,5 m; a discriminação cabe a S2.

## Sementes

- **Bloco proposto:** 81000 a 81919 (920 sementes). **Atribuídas** (alocação B): 81000 a 81915, pela ordem das etapas A (banda baixa, banda alta), B, C, D, E e, dentro de cada etapa, por semente crescente e pela ordem dos braços da tabela. **Por atribuir:** 81916 a 81919 (4).
- **Reserva proposta:** 80904 a 80983 (80 sementes), sem sobreposição consigo nem com o bloco nem com nenhuma semente inventariada. 81920 a 81999 não serve (405 pares sobrepostos entre si) e 80920 a 80999 foi rejeitada (sobreposição com a semente 83017, a final do M6). Não pode repetir, completar nem substituir nada desta execução.
- **44000 a 44999 permanecem protegidas e sem uso.** Deixam de ser o bloco confirmatório (ver «Operações de RNG já realizadas»).
- **Proibidas:** 50000 a 59999 (divisão do M14, gasta); 3000 a 3099 e 6000 a 6099 (M10); 44000 a 44999 (guarda do repositório); e o bloco e a reserva propostos até à alteração da guarda do repositório por commit aprovado pelo responsável (ver «Execução e congelamento»).
- **Já vistas, não utilizáveis como confirmação:** 41000 a 41999, 42000 a 43999, 45000 a 46999, 47000 a 47019, 32000 a 32099, 33500 a 33529, 30001, 30017, e as do G3 do M9.1 (2000 a 2029).
- **Caminhos de análise ramificados.** Qualquer uso posterior da reserva, das 4 sementes por atribuir ou de 44000 a 44999 é um **novo confirmatório**, com o seu protocolo e o seu nível, e conta esta execução como vista; não completa, repete nem corrige esta.
- **Independência entre etapas.** Blocos disjuntos. A agregação de A com D é só descritiva, por isso as etapas continuam a ser evidência independente.

### Independência entre sementes

Cada fluxo é um SplitMix64 de estado inicial `seed ^ (fonte × G)` e avanço `G = 0x9E3779B97F4A7C15` (`crates/vv-rocket/src/prng.rs`). Os estados de todos os fluxos estão numa só sequência, de passo `G` (inversível módulo 2^64); a posição de um fluxo é `estado_inicial × G^-1` e a saída k ocupa a posição + k. Dois fluxos partilham palavras de saída se e só se os intervalos de posições se intersetam. **Método: só aritmética de estado inicial e de posição, com os números de saídas usadas; nenhuma palavra de saída de nenhuma semente protegida ou confirmatória é gerada** (`scripts/m19_g3_power.py`, `block_verification`). A aritmética valida-se em testes com palavras geradas apenas para sementes sintéticas, não protegidas nem confirmatórias (bloco 90000 a 99999).

- **Saídas realmente usadas por execução** (de `landing_model.rs` e `landing_sensors.rs`): fontes 1 a 3, 3 saídas; 4 a 6, 1; altímetro 4 por ciclo de controlo; GNSS (posição, velocidade) 12 por medida; IMU (atitude, taxa, aceleração) 12 por ciclo de controlo. No caso de 40 s: 3, 3, 3, 1, 1, 1, 8000, 4800, 4800, 24 000, 24 000, 24 000. No limite do código (200 000 passos): até 1 200 000 nas fontes de IMU.
- **Dentro do bloco 81000 a 81919** (11 040 fluxos): **nenhuma sobreposição** nas saídas usadas, com o caso de 40 s e com o limite do código (folga mínima superior a 5 × 10^13 saídas). Idem na reserva 80904 a 80983 (960 fluxos) e entre a reserva e o bloco. Isto inclui pares de fontes diferentes da mesma semente.
- **Emparelhamento intencional e dependência não intencional.** Os braços de uma mesma semente usam exatamente os mesmos fluxos: é o emparelhamento dentro de uma experiência, deliberado (`mesma semente em braços diferentes`). As verificações acima comparam **sementes diferentes** (e fontes diferentes), isto é, a dependência entre experiências ou entre sementes do mesmo desenho, que não é intencional e que se mostra ausente.
- **Contra as faixas declaradas** (16 439 sementes: as do protocolo, 100 a 129, 201 a 212, as treze sementes finais do M6, as de campanha 42, 1337 e 2026, e 44000 a 44999): nenhuma sobreposição, nem do bloco nem da reserva.
- **Inventário do repositório.** Construído de forma mecânica sobre os blobs de `4777160` (789 ficheiros de texto, 2832 linhas com «seed» ou «semente»): 469 inteiros distintos e 123 intervalos (de `a a b`, `a-b`, `a..b` e de dicionários JSON com `first`/`count`, `low`/`high`, `start`/`end` sob uma chave com «seed»). É um **majorante**: qualquer inteiro numa linha com a palavra conta como semente possível.
- **Varrimento exaustivo.** Para **todas as sementes de 0 a 16 777 215** (2^24), com o limite do código (o pior caso) para os fluxos de ambos os lados: 25 160 sementes fora do bloco e da reserva têm algum fluxo com posições partilhadas com o bloco ou a reserva (237 intervalos). **Nenhum inteiro nem intervalo do inventário, nem semente declarada, está nesse conjunto.** Os 4 inteiros do inventário acima de 2^24 (20 261 111, 67 108 864, 536 870 912, 4 294 967 295) verificam-se um a um e não são parceiros.
- **Não estabelecido.** Sementes derivadas no código a partir de outros números e que não aparecem em nenhuma linha com a palavra; sementes em ficheiros não versionados (por exemplo `runs/`), noutros ramos ou árvores de trabalho, em texto de pull requests ou em notas; ficheiros binários; sementes de 2^24 ou mais que não sejam inteiros numa linha com a palavra. A conclusão vale para o inventário e para as sementes até 2^24, não para um uso desconhecido.
- Isto prova ausência de palavras de saída partilhadas, não independência estatística entre fluxos: essa continua assumida.

## Operações de RNG já realizadas

Regra do responsável: só é permitida análise estrutural ou matemática que não exponha nem explore sequências protegidas. Registo exato do que se fez nas versões anteriores deste candidato (commits `aaf0934`, `44dc8ee`, `dc1f18c`, `e3ffbef`, `031edb9`) e nesta.

| Operação | Sementes e fontes | Palavras de saída | Impresso, guardado ou inspecionado |
| --- | --- | --- | --- |
| Vetor de referência SplitMix64 (estado 0, público) e gerador de amostragem do cruzamento Monte Carlo de H3 (semente 20261123) em testes | nenhuma semente do simulador | as dos próprios testes | não aplicável: não são sementes protegidas |
| Aritmética de estado inicial e de posição, ordenação e folgas | 44000 a 44919 e 44000 a 44999, 12 fontes; faixas vistas e protegidas; blocos candidatos a partir de 60000 | nenhuma | só contagens e folgas guardadas |
| Geração explícita (`dc1f18c`) | (44000, fonte 2) e (44128, fonte 6) | 12 palavras numa verificação interativa; 8 por execução do teste | **6 e 2 palavras foram impressas na consola da sessão de trabalho**, logo constam do registo dessa sessão; nenhum ficheiro as guarda |
| Geração explícita (`031edb9`) | (44000, fonte 1) e (42016, fonte 3); (44804, fonte 10) e (41212, fonte 12) | 16 por execução do teste (3 e 1; 7 e 5) | comparadas por igualdade; não impressas nem guardadas |
| Esta versão | 81000 a 81999, 80904 a 80983 e blocos candidatos: só aritmética de posição | nenhuma | só contagens |

O teste de 44000 e 44128 correu várias vezes e o de `031edb9` pelo menos uma; o número exato de execuções não foi registado. Os dois testes foram **removidos** e substituídos por demonstrações em sementes sintéticas 90000 a 99999. `calculations.json` e os testes versionados não contêm nenhuma palavra de saída de sementes protegidas (só sementes, fontes, contagens e diferenças de posição; um teste verifica que o JSON não tem sequências hexadecimais de 16 ou mais dígitos); o histórico do git mantém os testes anteriores, que geravam palavras mas não as continham.

**Implicações.** Não houve simulação, não se observou nenhum resultado e nenhuma semente foi escolhida com base em resultados (o bloco 81000 foi escolhido por um critério aritmético de não sobreposição, sem resultados). Mesmo assim, foram geradas e, em 8 casos, impressas palavras de saída de fluxos das sementes 44000, 44128 e 44804, o que a regra do responsável não autoriza. Por isso essas sementes ficam **fora do conjunto confirmatório**: a mudança para 81000 a 81919 retira-as, e elas permanecem protegidas e sem uso. Para 81000 a 81999 e 80904 a 80983 não foi gerada nenhuma palavra.

## Execução e congelamento

1. Escrever o executor `scripts/m19_g3_confirm.py` e a análise `scripts/m19_g3_analyse.py`. O executor **recusa** 50000 a 59999, 3000 a 3099, 6000 a 6099 e 44000 a 44999 sempre, e recusa o bloco 81000 a 81919 **a menos que a guarda do repositório (`ROCKET_PROTECTED` em `exec/src/seeds.rs` e qualquer outra lista de sementes protegidas do repositório) tenha sido alterada por um commit aprovado pelo responsável, citado no congelamento**. Proposta para esse commit: primeiro proteger 81000 a 81999 e 80904 a 80983 (antes de qualquer execução), depois, para a execução, estreitar a guarda a 81000 a 81919 mantendo a reserva 80904 a 80983 e 44000 a 44999 protegidas. Nenhuma lista privada do executor pode destrancar estas sementes; o executor lê a guarda do repositório no commit congelado. Recusa também sementes fora do mapa acima, árvore não limpa, hash fixado diferente, ou commit de congelamento que não seja antepassado de `HEAD`. Grava, de cada execução, o campo `acted` do `gnss_bias`, o número de medidas enviesadas antes do contacto e o instante do contacto. Testa-se só com sementes 41900 a 41999 e sem ler hipóteses. A análise implementa as funções de `scripts/m19_g3_power.py` (limiares exatos, Holm, portas, teste de sinais, intervalos por estatísticas de ordem, Clopper-Pearson, `b_s_per_seed`); o teste `tests/test_m19_g3_power.py` é a especificação numérica. Nenhum destes scripts gera palavras de saída de sementes protegidas.
2. Passo de equivalência de bytes (ver «Fontes fixadas»), antes do congelamento.
3. Criar `docs/m19-g3-onset-freeze.json` com o sha256 dos blobs de: este protocolo; os ficheiros da tabela de fontes; `scripts/m19_g3_power.py`, `calculations.json` e os dois scripts do passo 1; o `source_sha256` do `vv-rocket` (hoje `295a45b2...`), o sha256 do binário, a versão do `rustc` e o comando de compilação; a versão do Python; o commit da árvore fixada; e a referência (e o sha256) da **aprovação escrita do responsável**.
4. O congelamento é um commit só com esse ficheiro, ou uma etiqueta assinada, que **cita a aprovação escrita do responsável**; sem ela não há congelamento. Envia-se para o repositório público antes da primeira execução. O registo da execução grava o commit de congelamento, a máquina e o comando.
5. Publicar o protocolo, o congelamento, o registo e a análise, qualquer que seja o resultado.

## Cálculos de preparação

Nenhum usou o simulador nem sementes do simulador. Tudo é exato (aritmética inteira sobre um denominador comum), exceto o cruzamento Monte Carlo de H3.

- **Reprodução do M15.** Limiares 154, 155, 228, 79 e 80; potências 0,307, 0,793 e 0,999 (H1 e H2, π = 0,95; 0,97; 0,99); 0,064 para π = 0,93 com n = 160; posições 20 e 41 e 19 e 42; limites de Clopper-Pearson (0 de 480: 0,95 %; 13 de 480: 4,97 %).
- **Tamanho mínimo para n sucessos em n rejeitarem H0: π ≤ 0,9:** 44 (0,01), 51 (0,01/2), 55 (0,01/3), 63 (0,01/7), 69 (0,01/14). Pares discordantes mínimos do McNemar: 10 (0,01/7) e 11 (0,01/14).
- **Potência com incerteza.** Beta-binomial exata (razões de fatoriais ascendentes racionais) para a média a posteriori; grelha de taxas e quantis de Jeffreys (integração numérica em t, com p = 1 − t²) em `power_scenarios`; nenhuma taxa é tomada como 1.
- **Inventário e varrimento de sementes.** `inventory_scan`, `partner_scan` (intervalos de posições por fonte, exatos; numpy só aqui).
- **Portas e H1b agrupada.** A porta H1b soma, sobre o número de cumprimentos de 0 s da banda baixa (partilhados com a porta McNemar), a cauda binomial da banda alta; ver `holm_design`.
- **Holm e portas.** Probabilidades de classe (rejeita a 0,01/3; a 0,01/2; só a 0,01; nunca) por hipótese; o Holm conjunto é a soma exata sobre as classes que cumprem p(1) ≤ 0,01/3, p(2) ≤ 0,01/2, p(3) ≤ 0,01. As portas somam, sobre o número de falhas tardias f e de cumprimentos a 0 s r, a hipergeométrica dos pares com ambos (braços independentes).
- **S4 e S5.** Potência do teste exato emparelhado a 0,01/7 e limites de Clopper-Pearson (`s4_s5_mcnemar`).
- **Tolerância a células, sementes, exposição e opção B.** `cell_tolerance`, `seed_independence`, `exposure_rule`, `layout_previous_allocation_A`.
- **Modelo do estimador.** `scripts/m14_masking_model.py`, inalterado: b* = 11,989 m para qualquer início em (0; 20] s; os valores do M15 mantêm-se.
- **Corolário do modelo.** Com 7 inícios, a banda baixa {5; 7; 9; 10,5} está abaixo de b* e a alta {13,5; 17; 22; 30} acima, em todos.

## Ameaças à validade

As do M15 (construção, interna, exploração prévia, externa, estatística, revisão) mantêm-se. Acrescentam-se:

- **Contagens de evidência.** Os limites de p0, q e H2 contam execuções que partilham sementes; o limite por semente distinta é mais baixo.
- **Independência dos braços.** As potências das portas e das opções supõem braços independentes dada a semente; não se mediu a dependência (os limites de Fréchet não a supõem).
- **Independência estatística entre fluxos.** Verificou-se só a ausência de palavras de saída partilhadas (ver «Independência entre sementes»).
- **Reconstrução de b_s.** A potência de H3, S1 e S2 usa uma distribuição reconstruída de 20 sementes e deslocamentos escolhidos aqui.
- **Estado dos dados.** O M9.1 (2000 a 2029) e o M14 (32000 a 32099) estão fora das faixas deste protocolo, mas os resultados sugeriram as hipóteses.
- **Equivalência do simulador** assente em leitura do diff, não em execução.
- **Binomial agrupado sobre células heterogéneas.** Os testes binomiais somam sementes de células com probabilidades de sucesso diferentes; a condição de Hoeffding (1956) garante que a cauda binomial limita a da soma heterogénea quando o limiar excede n × 0,9 + 1. Verifica-se em todos os limiares confirmatórios propostos, lidos de `calculations.json` pelo teste: H1a e H2 162 e 161 de 168; H1b 316 de 336; S3 e S6 163 de 168; S7 77 de 77; M1 220 de 231; M2 76 de 77. S4 e S5 usam o teste de sinais e não esta condição. A hipótese nula é então «média da grelha ≤ 0,9».
- **Desenho Halton fixo.** Os pontos da etapa E e os da grelha de A e D são um desenho fixo, não uma amostra de uma população de condições; o estimando é a média desse desenho e a inferência é só sobre o ruído e a dispersão.
- **Exposição pós-tratamento.** A exclusão por exposição depende do instante do contacto, que o tratamento pode alterar; o teto de 5 % e a contagem contra a hipótese acima dele limitam o efeito, mas não o eliminam.
- **Inventário de sementes.** A ausência de sobreposição vale para o inventário mecânico e para as sementes até 2^24; usos desconhecidos (ver «Independência entre sementes») não estão excluídos.
- **Tempo até ao contacto** nas sementes dispersas e a margem do início a 20 s são inferências, não medições.

## Escolhas de desenho propostas pelo autor do candidato

Não decididas pelo responsável: H1a como primária com portas em série (McNemar, H1b agrupada, mecanismo); Holm na família primária; S4 e S5 com a direção como critério e 60 sementes; 7 inícios sem substituição do início removido; as regras (a) a (f) de «Regras de decisão» (exposição mínima de 1,0 s, teto de 5 %, tratamento de resultados não avaliados); a reserva 80904 a 80983.

## Por decidir pelo responsável

**Alocação de sementes e bloco: preferidos pelo responsável, pendentes de verificação metodológica e de revisão humana.** O responsável prefere o bloco 81000 a 81919 e a alocação B. A tabela compara com a alocação A anterior (valores exatos; cenários e pressupostos de «Desenho proposto»; potências ilustrativas).

| | Alocação B (preferida) | Alocação A (anterior) |
| --- | --- | --- |
| Banda alta, A_high | 168 sementes (6 repetições), 81168 a 81335 | 140 sementes (5 repetições) |
| Etapa E | 19 pontos por família, 152 sementes, 81764 a 81915 | 20 pontos, 160 sementes |
| Sementes atribuídas e por atribuir | 916; 4 por atribuir (81916 a 81919) | 896; 24 por atribuir |
| Execuções | 5736 | 5704 |
| Limiar de H2 (0,01/3) | 162 de 168 | 136 de 140 |
| Potência de H2 com π = 0,95 / 0,97 / 0,99 | 0,260 / 0,758 / 0,998 | 0,166 / 0,589 / 0,986 |
| Limiar de S3 e S6 (0,01/7) | 163 de 168 | 136 de 140 |
| Limiar de H1b agrupada (0,01) | 316 de 336 | 290 de 308 |
| Pares de mitigação por mitigação | 460 | 468 |
| Limite a 99 % dos invariantes com 0 eventos (orçamento 1 %) | 0,996 % | 0,98 % |
| R2 a R6 (orçamento 5 %): eventos máximos | 12 (4,90 %) | 12 (4,82 %) |
| R1 a 0 s (orçamento 2,5 %) | 308 pares, 1 evento | 308 pares, 1 evento |

**Por decidir ainda.** (1) Confirmar a preferência depois da verificação metodológica independente do bloco e da revisão humana. (2) Os commits que alteram a guarda do repositório (proteger primeiro, estreitar depois). (3) A reserva proposta 80904 a 80983 em vez de uma adjacente (81920 a 81999 não serve). (4) Se o inventário de sementes, que tem lacunas declaradas, basta.

**Aprovação.** Este documento não pede aprovação de execução.

## Decisão do responsável

Pede-se, por esta ordem: (1) ler o texto corrigido, de preferência por um engenheiro externo, incluindo «Independência entre sementes» e «Operações de RNG já realizadas»; (2) confirmar ou alterar o bloco e a alocação; (3) só então decidir se aprova ou rejeita. A aprovação autoriza a escrita e o teste dos dois scripts em sementes de desenvolvimento, o passo de equivalência, o commit de congelamento que a cita e, com a guarda do repositório estreitada a 81000 a 81919 por commit aprovado (a reserva e 44000 a 44999 continuam protegidas), o uso das sementes atribuídas só para esta execução. Qualquer alteração produz um novo candidato.

# M10: pré-registo da reformulação do isolamento (tentativa única)

Estado: **pré-registo, fase 1. Não foi corrida nenhuma experiência e não há alterações de código neste commit.** O ramo é `research/m10-redesign`, a partir de `b733d14` (cabeça da PR #15). O M10 continua isolado como investigação: sem integração em `main` nem no Studio, sem fusão da PR #15 e sem a arquitetura C. Usam-se só as sementes de desenvolvimento 5000 a 5099. As sementes 3000 a 3099 e 6000 a 6099 (avaliação e reserva) e os intervalos 44000 a 44999 e 50000 a 59999 não são usados, e `m10-freeze.json` não existe nem é criado.

Este documento fixa, antes de qualquer execução, a hipótese, a alteração de código, a matriz, os critérios de sucesso e de paragem e o orçamento. Depois de iniciada a fase 2 (a primeira execução da etapa 1 da matriz, ver secção 5), alterar qualquer limiar, constante, célula ou critério conta como uma segunda tentativa, que a decisão do responsável não permite. Um resultado negativo é um resultado válido.

Fontes: `docs/m10-implementation.md` (iteração M10.3, secção 12), `docs/m10-decision-dossier.md`, `docs/m10-independent-review.md`, `docs/evidence/m10-dev/` e a secção «Porta de decisão do M10» de `docs/m19-programme-strategy.md` (ramo `docs/m19-programme`).

## 1. Revisão das decisões A e C propostas

Lê-se aqui a evidência registada, sem a repetir nem a corrigir. Todos os ficheiros estão em `docs/evidence/m10-dev/independent-review/` salvo indicação. As contagens de C da tabela de sondas foram recalculadas a partir de `probe-chase-summary.txt`.

### 1.1 Decisão A: paridade no domínio das taxas, ancorada

| Evidência registada | Suporta a rejeição? | Lacuna |
| --- | --- | --- |
| `probe-ignition-summary.txt`, `ramp0.5`: 186 isolamentos errados em 1 020 execuções, 186 falhas de alerta `hv`, U 773. `probe-ramp-summary.txt`: 0,5 m/s 14 errados em 100 e 8 `hv`; 0,3 m/s 4 errados e 0 `hv`; 0,8 m/s 2 errados e 1 `hv`. `probe-rampbase-summary.txt`, 0,5 m/s: B+ 6 errados em 80 e 4 `hv`. | **Sim.** Há isolamento errado e falha `hv` com rampas abaixo do envelope declarado (cerca de 0,8 m/s). | «Todo o isolamento errado termina em falha `hv`» só vale na sonda `ignition` (186 em 186). Em `ramp` são 14 contra 8 (0,5 m/s) e 4 contra 0 (0,3 m/s); em `rampbase` 6 contra 4. |
| `probe-rampbase-summary.txt`: a 0,5 m/s, B+ tem R 10, T 6, U 64 em 80; B tem R 9, T 65, U 6; `robust` e `guarded` têm U 80 em 80. A 0,3 m/s, todos os braços têm U 80 em 80. | **Sim**, para a cláusula «U de B+ excede U de B em mais de 2» (64 contra 6). | **Só 6 dos 64 U de B+ têm isolamento errado.** Os restantes 58 são isolamento correto tardio ou ausência de isolamento, e nenhum ficheiro os decompõe. Abster-se de isolar, sozinho, não pode explicar a diferença para B. |
| `val-ramp-summary.md` (800 execuções, mesmo binário): `gnss_coherent_ramp` B+ 57/29/14 contra B 20/69/11; `altimeter_stuck` 91 contra 94; `altimeter_delay` 78 contra 82; `altimeter_outliers` 94 contra 94. | **Parcial.** O ganho de B+ concentra-se em rampas de pelo menos 0,8 m/s (`m10-independent-review.md`, decisão A). Não é motivo de rejeição, é o que há a preservar. | Nenhuma estratificação por magnitude na campanha registada. |
| Limite pela união (`1,9e-4` por tentativa, impl., M10.3, secção 3); 0 isolamentos em 1 900 execuções sem falha de taxa; 0 errados em 5 700 do varrimento de início (`onset-sweep.json`, rampas só de 1 m/s). | **Não refuta.** | Vale só com resíduos bem calibrados e ruído igual ao modelado. O varrimento só regista a falha vertical e só usa 1 m/s. |
| Isolamento errado perto da ignição (texto de `m10-independent-review.md`): início de 3,0 a 3,95 s, 124 em 400 (31 %); de 4,0 a 5,5 s, 62 em 620 (10 %). | **Sim.** | O resumo commitado só agrega por falha (186 em 1 020); a divisão por janela vem do texto, e as saídas completas (3,7 MB) só estão presentes pelo SHA-256. |

Estado dos testes da revisão que esta tentativa tem de correr (1, 2, 3, 9 e 10):

| Teste | Estado em `b733d14` |
| --- | --- |
| 1, grelha de rampas coerentes | Não corrido na grelha pedida. Hoje 10 a 31 % de isolamento errado e 186 falhas `hv` (sondas parciais). |
| 2, varrimento com os três canais | Não existe: `scripts/m10_onset_sweep.py` só regista a falha vertical. A sonda `scripts/m10_adversarial_probe.py` já regista os três canais. |
| 3, U de B+ contra B entre 0,2 e 0,8 m/s | Parcial: 12 contra 6 em 18 (estrato da campanha), 64 contra 6 em 80 a 0,5 m/s. |
| 9, paridade com ruído 1,5 vezes o modelado | **Nunca executado.** Nenhum ficheiro de evidência varia o ruído dos sensores. |
| 10, janela da ignição | Parcial: só B+, sem comparação dentro e fora da janela na mesma grelha. |

Lacunas gerais que enfraquecem a evidência sem a anular:

- **Binários misturados.** A tabela de desenvolvimento junta `a82ca967…`, `45c9ee25…` e `e7165ec1…` (dossiê, «Binários misturados»); as sondas e as validações da revisão usam um só binário (`9a3f4776…`), por isso as comparações B, B+, `robust` e `guarded` dentro de `probe-rampbase-summary.txt` são coerentes. Não existe uma reexecução de todos os braços num único binário. Esta tentativa faz essa reexecução e não cita números desses binários como base de comparação (só como porta de reprodutibilidade, secção 5).
- **Rastreabilidade.** Só há resumos; sem registos por semente, não se verificam as trocas R, T e U por execução.
- **Mecanismo.** A causa (ponto de mudança do CUSUM estimado depois do início verdadeiro, âncora tardia) foi lida no código e não foi verificada com traços.
- **Amostra.** As sondas usam 20 sementes por ponto, e todas as sementes de desenvolvimento serviram para afinar B+ à mão (dossiê, «Justiça da afinação»).

Conclusão: a rejeição de A **tal como proposta** está suportada (isolamento errado, falha `hv` e U excessivo fora do envelope), mas a evidência regista o sintoma e não decompõe o excesso de U de B+ sobre B.

### 1.2 Decisão C: perseguição limitada em `untrusted`

| Evidência registada | Suporta a rejeição? | Lacuna |
| --- | --- | --- |
| `val-approved-summary.md` e `val-bounded-summary.md`: nos dois pares com `gnss_dropout`, B+ 41/32/27 passa a 85/0/15. Texto da revisão: T para R 27, U para R 17, **T para U 5** (sementes 5044, 5049, 5067, 5084, 5088). | **Parcial.** No agregado registado a variante é melhor (U 27 para 15); o dano é a troca T para U. | As trocas por semente não estão commitadas. As duas células `gnss_dropout` são a mesma experiência e os agregados globais contam-na duas vezes. |
| `probe-chase-summary.txt`, `late_drop` com início de 12 s ou mais (10 pontos, 200 execuções): B+ aprovado R 153, T 32, U 15; variante R 169, T 0, U 31; `robust` e `guarded` R 178, U 22. | **Sim**, para «não aceitar com base no 41 para 85»: a variante tem mais U do que B+ aprovado (+16) e do que `robust` (+9), e menos R do que `robust` (−9). | 20 sementes por ponto, sem intervalo emparelhado (as sementes são as mesmas entre modelos, mas as saídas não estão commitadas). O excesso de U está **repartido** pelos 10 pontos (+1 a +3 em cada), não concentrado em 16 s mais 6 s. A 8 s a variante é muito melhor (U 3 contra 18 em 20 com perda de 3 s, mesmo ficheiro). |
| `probe-chase-summary.txt`, `imudrift0.03+drop`: aprovado T 14, R 6; variante R 17, U 3. | **Sim**, para a qualidade da covariância. | O limite de deriva `σ_h + ½·b_h·t²` não tem termo `σ_vh·t` (`nav_filter.rs:390-392`, lido pela revisão). |
| Residual contra `robust` no par registado: 15 U contra 8 (dossiê, tabela de regressões). | **Sim.** | Sem lacuna. |

Conclusão: a rejeição de C é suportada como «não adotar com esta evidência», não como «pior em geral». C **fica rejeitada e fora desta tentativa**: a variante `bounded_chase_when_untrusted` fica a `false` em todos os braços (secção 3), e os testes 4 a 6 e 8 da revisão ficam fora.

## 2. Hipótese

**H.** Em rampas coerentes do recetor de 0,2 a 0,8 m/s, o isolamento errado de B+ e o excesso de U sobre B têm duas causas separáveis no código:

1. **Exoneração indevida do recetor.** A testemunha da IMU, ancorada a 0,2 s antes do ponto de mudança do CUSUM, pode ter o degrau de velocidade do recetor já no passado e então «concorda» com o GNSS; o radar é culpado e o recetor errado continua em uso (`nav_filter.rs:891`). Isto produz o isolamento errado e a falha `hv`.
2. **Ausência da rejeição por inovação de B.** Sem isolamento (ou com isolamento tardio), B+ continua a assimilar o recetor errado, enquanto B o rejeita por NIS e termina em T. A diferença de 58 U que o isolamento errado não explica (secção 1.1) é compatível com isto, mas não está demonstrada.

Se H é verdadeira, uma única política que (1) só isole quando a exoneração resiste a uma estimativa de início 1 s mais cedo e (2) em alarme não isolado rejeite por NIS como B, elimina as falhas `hv` e reduz U ao nível de B nessas rampas, sem desligar o isolamento das falhas grandes. H é falsificada pelas cláusulas de paragem da secção 7. Não é possível atribuir o resultado a (1) ou a (2) em separado: isso exigiria um braço adicional, que seria uma segunda tentativa.

## 3. A reformulação: porta de ambiguidade (uma só)

Uma só bandeira, `controller.nav.ambiguity_gate`, por omissão `false`. Com `false`, o comportamento tem de ser byte a byte o de `b733d14` (secção 5, porta 0). A bandeira só atua no braço B+ (`m10_b_plus`); os outros braços ignoram-na.

Princípio: «não isolado» é uma declaração por omissão. Só há isolamento quando a evidência resiste a uma estimativa de início mais antiga; sem isso, o episódio é ambíguo e o braço comporta-se como B (rejeição por NIS) até o alarme limpar. Com a bandeira ligada, o conjunto de isolamentos é um subconjunto do conjunto sem bandeira (a porta só converte isolamentos em não-isolamentos).

### 3.1 O que muda

| Ficheiro | Alteração |
| --- | --- |
| `crates/vv-rocket/src/landing_types.rs` | Campo `pub ambiguity_gate: bool` em `NavParams`, `false` em `Default`. A estrutura já tem `#[serde(default)]`, por isso os casos existentes continuam a ler-se e `m10-nominal.json` (SHA-256 `c28a258c…`) **não muda**. A variante ligada gera-se num ficheiro fora do repositório com só este campo alterado. |
| `crates/vv-rocket/src/landing_model.rs` | `validate_nav` recusa `ambiguity_gate = true` sem `anchored_imu_witness = true`. |
| `crates/vv-rocket/src/nav_filter.rs`, constantes | `FAR_ANCHOR_S = 1.0` (igual ao recuo de 1 s do reprocessamento, `reprocess`) e `GATE_FRACTION = 0.25` (a mesma fração `h/4` já usada para o ponto de mudança). Ficam fixadas aqui e **não se afinam**. |
| `nav_filter.rs`, `anchored_imu_witness` | Passa a receber a margem da âncora; a chamada atual usa `ANCHOR_MARGIN_S` (0,2 s) e não muda. |
| `nav_filter.rs`, `rate_pattern` | Com a bandeira ligada, calcula-se também a testemunha com margem `FAR_ANCHOR_S`. Toda a exoneração pela IMU (`ok(d_ig)`) exige `ok` nas duas âncoras: o ramo «radar culpado» e o ramo «GNSS culpado» por `bad(d_gg) && ok(d_rg) && ok(d_ig)`. O ramo «GNSS culpado» por `bad(d_rg) && bad(d_ig) && ok(d_gg)` não muda. Sem época anterior a `change_t − FAR_ANCHOR_S` no histórico, a testemunha distante não existe e não há exoneração (mesma regra que já vale para a âncora próxima). |
| `nav_filter.rs`, `radar_sample` e `gnss_sample` (ramo B+) | Com a bandeira ligada e em **episódio ambíguo**, a amostra é rejeitada (não se assimila) se `y² > nis_reject · S`, com o mesmo `nis_reject` (15,14) que B usa. Episódio ambíguo: as duas fontes de altitude em uso, `episode_isolated` falso e algum CUSUM vertical (radar, GNSS z, GNSS vz) acima de `GATE_FRACTION · cusum_h`. O CUSUM continua a ser calculado antes da decisão. |
| `scripts/m10_adversarial_probe.py` | Planos novos `ramps` e `onset` (secção 5) com a mesma proteção de sementes; sem alterar os planos existentes. |
| `scripts/m10_redesign_analysis.py` (novo) | Agregação e critérios desta secção, só biblioteca padrão. |
| `crates/vv-rocket/tests/m10.rs` | Testes: com a bandeira desligada os traços fixados não mudam; com ela ligada, uma rampa coerente de 0,5 m/s que hoje isola o radar passa a «não isolado»; `validate_nav` recusa a combinação inválida. |

Nada mais muda: `bounded_chase_when_untrusted` fica `false`, nenhum parâmetro afinado de B+ é tocado, o estimador de B, A, `robust` e `guarded` não muda.

### 3.2 O que a reformulação não toca

- O par `altimeter_bias` mais `gnss_dropout` não tem isolamentos (0 em 100, `m10-implementation.md`, secção 10) e a causa registada é lateral (regra `untrusted`, decisão 8). A reformulação **não o altera**; prevê-se resultado idêntico semente a semente (verificação da secção 6, S7).
- As regressões de `gnss_bias` (+99 U e +86 U contra `guarded`) são um limite de observabilidade de `E0`, sem isolamento.
- As três falhas de invariante de B+ em `gnss_horizontal_bias` não envolvem isolamento (0 em 100). A reformulação não as explica; esta tentativa só regista os identificadores dos invariantes (secção 8).

### 3.3 Alternativas descartadas (não testadas)

Persistência do padrão por N épocas; limiares `RATE_BAD` e `RATE_OK` mais largos; chão de magnitude para isolar; reposição por reprocessamento com NIS ligado. Todas ficam por testar e não entram nesta tentativa.

## 4. Braços e binário único

Um só binário de `vv-rocket`, construído uma vez a partir do commit da fase 2 (cabeça de `research/m10-redesign` com o código da secção 3), com `cargo build --release --manifest-path crates/vv-rocket/Cargo.toml`. Regista-se o commit, o `source_sha256` e o SHA-256 do binário. Todos os braços correm com esse binário; só mudam a política e, para B+G, um campo do modelo de caso.

| Rótulo | `controller.policy` | `controller.nav` |
| --- | --- | --- |
| B | `m10_b` | `m10-nominal.json` |
| B+ | `m10_b_plus` | `m10-nominal.json` (`ambiguity_gate` desligada) |
| B+G | `m10_b_plus` | igual, com `ambiguity_gate = true` |
| `robust` | `robust` | `m10-nominal.json` (o bloco `nav` não é usado) |
| `guarded` | `guarded` | `m10-nominal.json` (idem) |

O modelo de B+G é um ficheiro gerado fora do repositório; o seu SHA-256 e o do modelo desligado ficam em cada resumo. O script de análise **recusa** misturar resumos com `binary_sha256` diferentes. Não há braço «B+ sem paridade»: exigiria uma segunda bandeira; B é a referência sem paridade.

## 5. Matriz experimental

Só sementes 5000 a 5099. Todos os scripts recusam sementes protegidas antes de correr.

### 5.1 Porta 0: o braço desligado reproduz o registado (sem novas execuções além da fase 2)

Na fase 2, antes da matriz, correm-se `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings` e `cargo test` (incluindo os hashes de `tests/m10.rs`, `tests/landing.rs` e `tests/reference.rs`), e os resultados do braço desligado da fase 2 (B e B+) têm de reproduzir **exatamente** as contagens R/T/U registadas pela revisão com o binário `9a3f4776…` (só como verificação de que a bandeira não vaza para o caminho desligado, não como base de comparação):

| Célula (100 sementes) | B+ | B |
| --- | --- | --- |
| par `altimeter_bias` + `gnss_dropout` e par `altimeter_bias_low` + `gnss_dropout` | 41/32/27 em ambas | |
| par `gnss_bias` + `altimeter_dropout` | 0/0/100 | |
| par `altimeter_bias±` + `imu_accel_bias` | 89/0/11 | |
| par `gnss_bias_low` + `imu_accel_bias` | 0/0/100 | |
| par `altimeter_bias±` + `gnss_bias±` | 0/0/100 | |
| `gnss_coherent_ramp` | 57/29/14 | 20/69/11 |
| `altimeter_stuck` | 91/3/6 | 94/0/6 |
| `altimeter_delay` | 78/4/18 | 82/0/18 |
| `altimeter_outliers` | 94/0/6 | 94/0/6 |

Se alguma contagem diferir, a execução para antes da etapa 1 da matriz e reporta-se «bandeira desligada não equivalente»; corrigir só é permitido se restaurar a equivalência sem tocar na lógica da bandeira ligada, e antes de qualquer resultado da matriz.

### 5.2 Fases e células

Execução por etapas, para poder parar cedo (secção 7). Cada etapa é um conjunto de invocações; o limite por invocação é o das ferramentas (campanha 2 500 execuções, sonda 6 000, 8 tarefas).

| Etapa | Código | Falhas, magnitudes e inícios | Sementes | Braços | Execuções |
| --- | --- | --- | --- | --- | --- |
| **1. Grelha de rampas (G1)** | sonda, plano novo `ramps` | `gnss_coherent_ramp` até 40 s; magnitude {0,2; 0,3; 0,5; 0,8} m/s; início {3,00; 3,25; …; 6,00} (13 valores), 8,0, 10,0, 12,0 s (16 inícios); 64 células | 5020 a 5059 (40) | B, B+, B+G | 3 × 2 560 = 7 680 |
| **2. Campanha de desenvolvimento (M1)** | `scripts/m10_campaign.py` | famílias F1 (11), F2 (7, sem `altimeter_drift`), F3 (6 pares): 24 células de 100 sementes, sorteios do código existente | 5000 a 5099 | B, B+, B+G, `robust`, `guarded` | 5 × 2 400 = 12 000 |
| **3. Ruído 1,5 vezes (M3)** | `m10_campaign.py` com modelo derivado | as 24 células de M1; `sensors.altimeter_sigma_m` 0,15, `gnss_position_sigma_m` 0,75, `gnss_velocity_sigma_mps` 0,075, `imu_accel_sigma_mps2` 0,03; `controller.nav` **não muda** | 5000 a 5099 | B+, B+G | 2 × 2 400 = 4 800 |
| **4. Varrimento de início (M4)** | sonda, plano novo `onset` | as cinco falhas de `m10_onset_sweep.py` (`altimeter_stuck` 3 s, `altimeter_delay` 0,1 s, `gnss_coherent_ramp` 1 m/s, `gnss_dropout` 5 s, `imu_accel_drift` 0,05), início de 2 a 20 s em passos de 1 s; mesmos fins (`fault_at`) | 5020 a 5039 (20) | B, B+, B+G, `robust`, `guarded` | 5 × 1 900 = 9 500 |
| **5. Completar G1** | sonda, `ramps` | como a etapa 1 | 5020 a 5059 | `robust`, `guarded` | 2 × 2 560 = 5 120 |

Total planeado: **39 100 execuções.**

Razões das escolhas:

- G1 e M4 usam as sementes 5020 a 5059 e 5020 a 5039 porque as sondas da revisão só usaram 5000 a 5019; assim as sondas que motivaram a reformulação não são reutilizadas. As sementes de desenvolvimento são todas conhecidas do desenvolvimento de B+: não há independência, e os resultados não generalizam.
- Os inícios de G1 são os do teste 1 da revisão (3 a 6 s em passos de 0,25 s, 8 e 12 s), com 10 s acrescentado para coincidir com os inícios de `rampbase` (4,5; 6; 8; 10 s).
- **Unidades de 80 execuções** (cláusula 2 por magnitude): início {4,5; 6,0; 8,0; 10,0} × sementes 5020 a 5039, para cada magnitude, o mesmo tamanho (80) das contagens registadas.
- **Estrato da campanha** (cláusula 2): a célula `gnss_coherent_ramp` de M1 restrita às 18 sementes de 5000 a 5099 cuja magnitude sorteada está em [0,2; 0,8] m/s (5001, 5004, 5011, 5012, 5027, 5029, 5031, 5033, 5041, 5042, 5048, 5056, 5062, 5063, 5074, 5076, 5078, 5081; sorteio de `sample_new_fault`, sem simular).
- **Janela da ignição** (teste 10): grelha de inícios absoluta (a de G1). Cada execução classifica-se «dentro» se `|início − instante de ignição da própria execução| ≤ 0,5 s` e «fora» caso contrário. O instante de ignição é o `ignition_t_s` da simulação (`landing_sim.rs`); a fase 2 identifica onde está exportado (traço ou verificação) e fixa o campo antes de correr; se não for legível, o plano `ramps` acrescenta-o ao registo sem alterar a simulação. Sem estatística calculada depois de ver os resultados.
- A célula de ruído 1,5 vezes confirma-se com uma execução de ensaio (a validação de `sensors` não liga os sigmas do sensor aos de `controller.nav`: `landing_model.rs`, `validate_nav` só verifica gamas de `nav`). Se o simulador recusar o modelo, é uma alteração extra de código que se regista antes de correr.
- `robust` e `guarded` não têm bloco `navigation`; a classe física deles lê-se pelos requisitos e invariantes (`physical_class` de `m10_campaign.py` e da sonda, que coincidem).

### 5.3 Retenção e rastreabilidade

M1 e M3 usam `--keep-sample 2 --keep-failures 5` (valores por omissão) e a reprodução de uma execução por célula e braço com `vv-rocket replay`; as de B+G são todas verificadas. A sonda não retém traços. Em todas as etapas grava-se um registo compacto por execução (célula, braço, semente, classe física, requisitos e invariantes falhados com identificador, veredicto e eventos de isolamento, falhas de alerta dos três canais, instante de ignição), comprimido, para commit na fase 2. Isto fecha a lacuna de rastreabilidade da secção 1.

## 6. Métricas

- **Classe física R, T, U** (estado real): R sem requisitos falhados; T só com R5 falhado; U caso contrário. U é a métrica de segurança; R a de recuperação.
- **Isolamento errado**: veredicto `wrong` **ou** `before_onset` em `navigation.isolation_events` (leitura mais estrita do que só `wrong`: ambos são isolamentos sem falha do mesmo grupo a justificá-los). O resumo reporta também cada veredicto em separado.
- **Falhas de alerta** `vertical`, `horizontal_velocity` (`hv`) e `horizontal_position`, por canal, do bloco `navigation`.
- **Invariantes falhados** por identificador, instante lógico e condição observada (contrato de falhas de `AGENTS.md`).
- **Isolamentos corretos** (veredicto `correct`) e o seu atraso.
- **Troca emparelhada por semente** entre B+ e B+G e entre B e B+G: R→U, T→U, U→R, T→R, e a decomposição do U de B+ e de B+G a 0,5 m/s por veredicto de isolamento (nenhum, correto, errado), que fecha a lacuna dos 58 U.
- **Regressão material** (dossiê, e `m10-implementation.md`, secção 10): mais de 2 U acima da base, ou 5 ou mais recuperações perdidas em 100.

## 7. Critérios

Os limiares estão fixados antes de qualquer execução. As células «distintas» contam os dois pares com `gnss_dropout` uma só vez (são a mesma experiência, resultados iguais semente a semente): 23 células distintas em M1 e M3.

### 7.1 Regra de paragem (verbatim, `m19-programme-strategy.md`)

> voltar à secção 6.3 se, depois da reformulação, restar alguma falha de alerta da velocidade horizontal, se `U` de B+ exceder `U` de B em mais de 2 entre 0,2 e 0,8 m/s, ou se surgir um isolamento errado com ruído 1,5 vezes o modelado.

Operacionalização, sem enfraquecer nenhuma cláusula. Qualquer uma dá «não avançar» e a execução para nessa etapa:

| Cláusula | Operacionalização | Onde |
| --- | --- | --- |
| 1. Falha `hv` restante | **Zero** falhas de alerta `hv` em **todas** as execuções de B+G com ruído nominal (G1, M1, M4). Se B tiver `hv` numa célula (a evidência registada indica 0), reporta-se ao orquestrador como regra mal calibrada e **não** se considera cumprida. | Etapas 1, 2, 4 |
| 2. U de B+ contra U de B | Com B+ lido como B+G: em cada uma das 4 unidades de 80 execuções (uma por magnitude 0,2; 0,3; 0,5; 0,8) e no estrato de 18 sementes da campanha, `U(B+G) − U(B) ≤ 2`. Reportam-se também o conjunto da grelha e B+ aprovado, sem efeito no veredicto. | Etapas 1 e 2 |
| 3. Isolamento errado com ruído 1,5 vezes | **Zero** isolamentos errados (secção 6) nas 2 400 execuções de B+G em M3 (limite superior de Clopper-Pearson a 95 % de 0,15 % com 0 em 2 400). | Etapa 3 |

### 7.2 Sucesso

Todos têm de se verificar, e nenhuma cláusula de paragem pode ter disparado. «Melhoria material» é definida por S2 e S3, não por impressão.

| Id | Critério |
| --- | --- |
| S1 | Cláusula 1 cumprida (zero `hv`). |
| S2 | Em G1, magnitudes 0,3 e 0,5, 16 inícios, 1 280 execuções de B+G: **no máximo 5 isolamentos errados** (0,39 %, limite superior a 95 % de 0,91 %; este é o «limite declarado» do teste 1), **e** pelo menos 90 % menos do que B+ na mesma grelha. Condição de validade: B+ tem pelo menos 60 isolamentos errados na mesma grelha (hoje 10 a 31 %); se tiver menos, a premissa não se reproduziu e o resultado é «inconclusivo», não «sucesso». |
| S3 | Cláusula 2 cumprida (5 unidades). |
| S4 | Teste 10: a taxa de isolamento errado de B+G «dentro» da janela de ignição não excede a «fora», na grelha G1 completa. |
| S5 | Cláusula 3 cumprida. |
| S6 | **O isolamento não está desligado.** (a) Em M1, `altimeter_stuck` e `altimeter_delay`: `R(B+G) ≥ R(B+) − 4` em cada. (b) Em M1, `gnss_coherent_ramp`: `R(B+G) ≥ R(B) + 0,5 · (R(B+) − R(B))`. (c) Em G1 a 0,8 m/s (640 execuções): `R(B+G) ≥ R(B)` e `R(B+G) ≥ R(B+) − 32` (5 %). (d) Isolamentos corretos de B+G nas três células de M1 (`altimeter_stuck`, `altimeter_delay`, `gnss_coherent_ramp`, 300 execuções) pelo menos 70 % dos de B+ (hoje 98 + 99 + 84 = 281; é o mesmo binário a medir). |
| S7 | **Sem regressão contra B+ no mesmo binário**, em cada célula distinta de M1: `U(B+G) ≤ U(B+) + 2`, `R(B+G) ≥ R(B+) − 4` (a recuperação de `gnss_coherent_ramp` fica regida por S6b), e invariantes falhados de B+G não superiores aos de B+. Nas células sem isolamento (todas menos `altimeter_stuck`, `altimeter_delay`, `altimeter_outliers` e `gnss_coherent_ramp`), prevê-se resultado idêntico semente a semente; qualquer diferença é reportada e investigada. |

### 7.3 Limites de regressão contra `robust` e `guarded` (leitura estrita, por omissão)

Em cada célula distinta de M1, B+G não pode ter regressão material contra `robust` nem contra `guarded` (mais de 2 U acima, ou 5 ou mais recuperações perdidas). Isto inclui o par `altimeter_bias` mais `gnss_dropout` e `gnss_bias`.

**Previsão registada antes de correr:** este limite **falha a priori** em três grupos herdados, que a reformulação não toca (secção 3.2): o par com `gnss_dropout` (B+ 27 U contra 8 de `robust` e `guarded`, +19), `gnss_bias` (100 U contra 1 de `guarded`, +99) e o par `gnss_bias` mais `altimeter_dropout` (100 U contra 14 de `guarded`, +86). Na leitura estrita, o veredicto global só pode ser «não avançar», qualquer que seja o resultado dos eixos S1 a S7.

Para que o resultado seja informativo, o relatório dá **dois veredictos separados**: (V1) eixo do isolamento, S1 a S7; (V2) limites de regressão contra `robust` e `guarded`, com os três grupos herdados mostrados sempre em U contra as duas bases. «Avançar» exige V1 e V2.

**Decisão pendente** (secção 12): o responsável pode, antes da etapa 1 da matriz, optar pela leitura delimitada, em que os três grupos herdados só têm de cumprir `U(B+G) ≤ U(B+) + 2` e `R(B+G) ≥ R(B+) − 4`, e continuam a ser mostrados contra as bases. Sem essa decisão por escrito, vale a leitura estrita.

### 7.4 Previsões (não são critérios)

Escritas antes de correr, para que o resultado possa contradizê-las: o autor espera S2 e S4 satisfeitos; considera **a cláusula 2 a 0,5 m/s a mais provável de falhar** (a rejeição por NIS só entra depois do alarme, com as primeiras épocas já assimiladas); e espera V2 falhado na leitura estrita.

## 8. Plano de análise

- Contagens R/T/U, falhas de alerta e isolamentos por célula e braço, com intervalos de Clopper-Pearson a 95 % por célula. Comparações emparelhadas por semente com `python scripts/m10_stats.py compare` para R e, no script novo, para U. Sem valores-p: as decisões são regras de limiar sobre contagens; os intervalos são só informativos e não ajustados (dados de desenvolvimento, exploratórios).
- Verificações de integridade antes de calcular: um só `binary_sha256`; modelos desligado (`c28a258c…`) e ligado registados; nenhuma semente fora de 5000 a 5099; contagem de execuções igual à da matriz; reprodução das execuções retidas.
- Decomposição por veredicto de isolamento (secção 6), incluindo os 58 U de B+ a 0,5 m/s.
- `gnss_horizontal_bias`: lista das falhas de invariante de B+ e B+G com identificador, instante lógico, estado, causa, condição esperada e observada (a partir das execuções retidas). Continua por explicar enquanto não houver explicação escrita; **bloqueia o congelamento** mesmo com «avançar».
- Resultado global: V1, V2 e o veredicto («avançar» ou «não avançar»), com o critério que decidiu. Um «não avançar» por cláusula de paragem encerra o M10 como investigação e devolve a decisão à secção 6.3.

## 9. Orçamento

| Limite | Valor |
| --- | --- |
| Execuções | máximo 40 000 (planeadas 39 100) |
| Tempo de simulação | máximo 45 minutos de relógio, em 8 tarefas (estimativa 11 a 12 minutos: a revisão mediu 11 700 execuções em 200 s) |
| Por invocação | campanha: 2 500 execuções e 1 800 s; sonda: 6 000 execuções (limites das ferramentas) |
| Artefactos | menos de 1 GB fora do repositório; no repositório só resumos e registos compactos comprimidos, na ordem de 1 a 5 MB |
| Paragem antecipada | a primeira cláusula de paragem que dispare encerra as etapas seguintes. Se a etapa 1 (G1, 7 680 execuções) disparar a cláusula 1 ou 2, o total fica em 7 680 |
| Código | só o descrito na secção 3.1 |

O tempo e o número de execuções medem-se fora da simulação, com máquina, comando e limites publicados no resumo.

## 10. O que fica por testar

- **Atribuição** entre a exoneração robusta e a rejeição por NIS: um só braço, sem fatores separados.
- Os testes 4 a 8 e 11 a 13 da revisão (perseguição limitada, `detector_flag`, F5, rastreabilidade dos parâmetros, estatística da P1 a P4).
- Rampas com início antes do primeiro instantâneo certificado (até cerca de 6 s) só estão cobertas na parte de G1 com início de 3 a 6 s.
- Falhas combinadas com rampa lenta, perda de GNSS depois do isolamento e outros pares fora de F3.
- Outros sensores, outras gamas de ruído (só 1,5 vezes e só quatro desvios-padrão), outros veículos ou perfis de descida.
- Generalização: as sementes são de desenvolvimento e B+ foi afinado nelas. Nenhum resultado desta tentativa é uma avaliação do M10 e nenhuma semente de avaliação ou de reserva foi consultada.
- A causa do excesso de U de B+ sobre B continua a ser uma hipótese; os traços por execução da fase 2 podem confirmá-la ou não.

## 11. Integridade

- Uma só tentativa. Depois da primeira execução da etapa 1 da matriz, qualquer alteração às constantes `FAR_ANCHOR_S` e `GATE_FRACTION`, ao `nis_reject`, aos limiares, à matriz, às sementes ou à leitura dos critérios é uma segunda tentativa e não é feita.
- Nenhum ficheiro de congelação, nenhuma semente protegida, nenhum envio, nenhuma PR e nenhum comentário; o commit desta fase só adiciona este documento.
- A fase 2 (implementação e execução) só começa depois de este documento ser revisto e de o responsável decidir a leitura de 7.3.

## 12. Decisões pedidas

1. Leitura dos limites de regressão (secção 7.3): estrita (por omissão, previsão de falha a priori) ou delimitada.
2. Aprovar a alteração de código da secção 3.1 antes da fase 2, em particular a rejeição por NIS no episódio ambíguo, que acrescenta ao isolamento um comportamento de B.

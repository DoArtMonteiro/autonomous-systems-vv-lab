# M10: dossiê de decisão do proprietário para a porta final

Estado: **análise, sem decisões tomadas.** Este dossiê recomenda; o proprietário decide. Usa só a evidência commitada de desenvolvimento (sementes 5000 a 5099) e cálculo leve sobre ela. Nenhuma semente de avaliação (3000 a 3099) ou de reserva (6000 a 6099) foi lida ou executada; `m10-freeze.json` não existe e não foi criado. Nenhuma simulação nova foi corrida para este dossiê.

## Resumo

- B+ é, nas sementes de desenvolvimento, o braço com mais recuperações (1 406 `R` em 2 400; 1 494 com a perseguição limitada) e menos `U` entre os braços do M10, com 1 isolamento errado em 2 400 e 0 transições inseguras.
- Há **regressões de segurança materiais** face a `guarded` e a `robust` que nenhuma decisão anterior aceitou. A maior está subavaliada no documento de implementação: em `gnss_bias`, `guarded` tem 1 `U` e B+ tem 100 (+99 `U`), não apenas −21 recuperações.
- A configuração **não está pronta para congelar.** Faltam o script de agregação, os varrimentos F5, o plano de chunks sem C, a ligação do manifesto ao binário e uma reexecução de todos os braços num único binário. A secção "Prontidão para congelar" dá a lista.
- Defeitos de método encontrados: nenhum no que os scripts calculam (o teste de Tango e Nam, os limiares de P1 e P2 e o intervalo de Bonferroni estão corretos). As lacunas estão no que não existe (P1, P2, P4 e Holm não estão implementados) e em regras do pré-registo que se contradizem (secção "Estatística").

## Índice da evidência

| Etiqueta | Ficheiro | Binário (SHA-256) | Modelo de caso (SHA-256) |
| --- | --- | --- | --- |
| campanha | `docs/evidence/m10-dev/campaign/*.json` | `a82ca967…` (M9, A, B); `45c9ee25…` (B+) | `c28a258c…` |
| perseguição | `docs/evidence/m10-dev/campaign-bounded-chase/*.json` | `a82ca967…` (A*, B*); `45c9ee25…` (B+*) | `fdd7b9ba…` (não commitado) |
| PR 15 | `docs/evidence/m10-dev/campaign-pr15/m10_b_plus.json` | `e7165ec1…` | `86417497…` |
| afinação | `docs/evidence/m10-dev/tuning/*.json` | `a82ca967…` | `c28a258c…` |
| varrimento | `docs/evidence/m10-dev/onset-sweep.json` | `45c9ee25…` | `c28a258c…` |
| P3 | `docs/evidence/m10-dev/p3-size.json`, `paired-*.json` | | |

Documentos: `docs/m10-resilient-navigation.md` (desenho, "desenho" abaixo) e `docs/m10-implementation.md` (implementação, "impl." abaixo). As contagens R/T/U, a contenção e as falhas de alerta vêm dos campos `classes`, `contained` e `navigation` dos resumos.

## Configuração recomendada

Uma só, condicionada às recomendações das decisões 1 a 4:

| Elemento | Valor |
| --- | --- |
| Código | `crates/vv-rocket` de `HEAD` (o código do simulador não muda desde `ca04cc6`; os commits seguintes só tocam em `scripts/` da bancada e em documentação) |
| Braços | `baseline` (só nominal), `robust`, `guarded`, `m10_a`, `m10_b`, `m10_b_plus`; **sem C** |
| Sensores | `E0` |
| Sementes | avaliação 3000 a 3099; reserva 6000 a 6099 fechada |
| Células | F1 (11), F2 (7, sem `altimeter_drift`), F3 (6 pares); F5 a definir (ver lista) |
| Pares por braço | `guarded`, B, B+ nos 6; A só nos pares 1, 2 e 4 (regra de 10.3: A recupera pelo menos 50% nas duas componentes: `altimeter_bias` 92, `altimeter_bias_low` 92, `gnss_dropout` 91, `imu_accel_bias` 89; falha `gnss_bias` e `gnss_bias_low`, 0); `robust` nos pares 1 e 2 (emenda recomendada na decisão 3; o pré-registo tira-o dos pares) |
| Retenção | `--keep-sample 5 --keep-failures 50` (pré-registo 10.3: sementes 3000 a 3004 e até 50 falhas por célula e braço; os valores por omissão são 2 e 5) |
| `controller.nav`, modelos e ruídos | `radar_sigma_m` 0.1, `gnss_position_sigma_m` 0.5, `gnss_velocity_sigma_mps` 0.05, `radar_lever_sigma_m` 0.05, `accel_process_sigma_mps2` 0.1, `bias_walk_sigma_mps2_per_sqrt_s` 0.03, `bias_prior_sigma_mps2` 0.3 |
| `controller.nav`, deteção e admissão | `cusum_k` 0.5, `cusum_h` 12.0, `suspect_cusum_fraction` 1.0, `admission_cycles` 5, `admission_gate_m` 3.0, `readmission_samples` 10, `readmission_sigma` 3.0, `gnss_readmission_epochs` 10, `nis_reject` 15.14, `vote_threshold_m` 3.0, `suspect_after_s` 0.2, `exclude_after_s` 0.5 |
| `controller.nav`, integridade e modos | `k_ff` 5.33, `al_v_floor_m` 1.0, `al_v_fraction` 0.02, `al_hv_mps` 0.5, `al_h_m` 10.0, `b_h_m` 30.0, `n_in_cycles` 3, `t_hold_s` 2.0, `t_max_s` 2.0, `t_safe_s` 5.0, `h_commit_m` 50.0 |
| `controller.nav`, lei e monitor | `dead_reckoning_tilt` 0.2, `monitor_gnss_gain` 0.25, `monitor_radar_gain` 0.1, `anchored_imu_witness` **true**, `bounded_chase_when_untrusted` **true** (decisão 3) |
| Constantes no código | `RATE_BAD` 4.0, `RATE_OK` 3.0, `ISOLATION_WINDOW_S` 1.0, `CONSISTENCY_SIGMA` 4.0, `COLD_FLAG_S` 1.0, `SUSPECT_CLEAR_S` 1.0, `ANCHOR_MARGIN_S` 0.2, `GNSS_HISTORY` 40, `RING` 300, `SNAPS` 12 (`crates/vv-rocket/src/nav_filter.rs`; cobertas só pelo `source_sha256`) |

Os 35 valores de `controller.nav` são os de `crates/vv-rocket/landing/m10-nominal.json` (SHA-256 `c28a258c94a17b6ce1e8eb5a1442d977b4c951a0913375661ec3dddf8d05784a`), com uma única alteração: `bounded_chase_when_untrusted` passa a `true`. Os valores de A, B e B+ são os partilhados de partida (afinação, decisão 5). Os pins atuais (`c28a258c…`, `45c9ee25…`) são de desenvolvimento e ficam substituídos pela reexecução no binário e no modelo congelados.

## As cinco decisões

### 1. Paridade no domínio das taxas (desvio a 6.3)

- **A favor.** B+ recupera 91, 78 e 57 em `altimeter_stuck`, `altimeter_delay` e `gnss_coherent_ramp`, com isolamento correto em 98, 99 e 84 (campanha). Isolamentos errados: 1 em 2 400 (semente 5001, rampa de 0,5 m/s) e 0 nas 1 900 execuções sem falha de taxa. Nenhum isolamento errado nas 5 700 execuções do varrimento. O limite pela união (`3 · P(|Z| > 4) ≈ 1,9e-4` por tentativa) não precisa de independência (impl., iteração M10.3, secção 3).
- **Contra.** B, sem paridade e só com rejeição por NIS, recupera mais em `altimeter_stuck` (94 contra 91) e em `altimeter_delay` (82 contra 78), com os mesmos `U` (6 e 18). A paridade só se distingue claramente em `gnss_coherent_ramp` (57 contra 20 de B; `U` 14 contra 11). O contrafactual "sem paridade, 8, 0 e 0" (impl., desvio 1) não tem ficheiro de evidência commitado. Os limiares são constantes do código, não campos do caso como pede 10.1. O pior caso continua a ser a rampa precoce: 2 em 20 com início a 2 s (varrimento).
- **Recomendação: aceitar, com a testemunha ancorada**, como emenda escrita a 6.3 e com as constantes listadas no manifesto pelo `source_sha256`.
- **Alternativas.** (b) Vetar: B+ perde o isolamento das falhas de taxa e a comparação com B passa a ser só deteção sequencial contra NIS; as recuperações caem para o contrafactual não verificado. (c) Aceitar mas passar as constantes para `NavParams`: exige mais código, nova reexecução e refixação dos hashes antes da congelação.

### 2. Não construir C (decisão 12)

- **A favor.** A experiência de lacuna disparou por uma única falha de alerta vertical em 600 execuções de pares (célula `pair_altimeter_bias±+gnss_bias±`, B+ com 1; A com 3, B com 2). O sorteio da semente 5082, recalculado com `faults_for` (sem simular), dá `altimeter_bias` de 5,93 m e `gnss_bias` de 6,17 m, com o mesmo sinal: as fontes concordam a 0,24 m, abaixo da porta de admissão de 3 m. É modo comum: a separação de soluções não o vê. Nas 100 sementes de desenvolvimento há 3 sorteios desta célula com o mesmo sinal e diferença abaixo de 3 m (5030, 5057, 5082); a avaliação deverá ter 0 a 3. A P4 exige pelo menos 3 pontos percentuais agrupados (18 execuções em 600); B+ tem 1. A P4 não é cumprível.
- **Contra.** A decisão 12 aprovada diz "com lacuna, C é construída". Não construir é uma emenda a uma decisão aprovada. O argumento a priori de C (limite de integridade sob falha não detetada) fica sem teste. Construir C e deixar a P4 falhar é o caminho pré-registado e também é um resultado científico legítimo.
- **Recomendação: não construir C**, com emenda escrita à decisão 12 e a 6.6, e a P4 classificada como **não avaliável (C não construída)**. Manter a correção de Holm com m = 4, com a P4 a valor-p 1: os limiares de P1 a P3 não mudam (P1: 22 em 700 a 0,0125; P2: 90 em 100) e nada se reajusta.
- **Alternativas.** (b) Construir C: custo de implementação e de afinação com o mesmo orçamento; P4 prevista falsificada. (c) Não construir e re-registar a família com m = 3: limiares mais permissivos (P1 22, P2 89 no primeiro degrau 0,0167), alterados depois de ver dados de desenvolvimento; legítimo antes da congelação, mas menos conservador.
- **Consequência obrigatória em qualquer opção sem C.** O desenho refere C em 10.3 (braços de F1 a F5 e chunks `F1c`, `F2b`, `F3b`, `F5`), em H-H ("C não o deteta"), em H-F2 ("600 execuções de C"), em "A contra C" e em 10.7. Cada referência tem de passar a B+ ou sair, por escrito, antes da congelação.

### 3. Perseguição limitada em `untrusted` (emenda a 8.3 e à decisão 8)

- **A favor.** Nos dois pares com `gnss_dropout`, B+ passa de 41/32/27 (R/T/U) a 85/0/15; contenção de 98 a 100. Global de B+: `R` 1 406 para 1 494, `T` 281 para 217, `U` 713 para 689 (perseguição). Causa diagnosticada: lateral (22 de 27 `U` falham `R2`; impl., "Leitura"). A regra só atua quando `untrusted` vem de dados em falta e o detetor nunca implicou o recetor.
- **Contra.** Muda a semântica aprovada de `untrusted` ("sem perseguição lateral"). O campo é partilhado: muda também A e B (A: `altimeter_stuck` 62 para 72, `altimeter_outliers` 56 para 90, global `U` 954 para 922; B: pares 41 para 85). A regra foi desenhada a olhar para estas sementes e estas células. Fica uma regressão residual face a `robust`: 15 `U` contra 8 (+7). "Nenhuma outra célula muda" é verdade nas classes, não nas trajetórias: o NEES médio de `altimeter_outliers` difere (6,5501 contra 6,5498). O modelo de caso da variante (`fdd7b9ba…`) não está commitado.
- **Recomendação: adotar**, como emenda escrita a 8.3 para todos os braços do M10, com o residual de +7 `U` face a `robust` reportado como regressão **não aceite por omissão** (regra 4 de 9.1).
- **Lacuna de medição.** O pré-registo (10.3) tira `robust` das células de pares. A regressão face a `robust` só é visível porque o desenvolvimento correu `robust` nos pares; na avaliação não seria medida. Recomenda-se acrescentar `robust` aos pares 1 e 2 (200 execuções) por emenda antes da congelação.
- **Alternativas.** (a) Manter a regra aprovada: 27 `U` contra 8 de `robust` e de `guarded` no primeiro par (+19), regressão material. (c) Aceitar a regressão de +19 explicitamente: contraria o princípio "uma regressão prevista não é aceite como segura".

### 4. Limite de `E0` em `gnss_bias` (decisão 15)

- **Evidência.** Por classe física: `guarded` 21/78/1 contra B+ 0/0/100 em `gnss_bias` (+99 `U`); no par `gnss_bias` + `altimeter_dropout`, `guarded` 19/67/14 contra B+ 0/0/100 (+86 `U`). `robust` tem 0/0/100 nas duas. A regra "menor altitude" acerta pelo sinal e perde o espelho: em `altimeter_bias_low`, `guarded` 0/0/100 contra B+ 94/0/6, e no par `altimeter_bias_low` + `gnss_dropout`, `guarded` 100 `U` contra B+ 27 (15 com a perseguição). Soma de `U` nas quatro células de sinal (`altimeter_bias`, `altimeter_bias_low`, `gnss_bias`, `gnss_bias_low`): B+ 212, `guarded` 209. É uma aposta no sinal, não uma diferença de capacidade. A ambiguidade não é observável em `E0` e o envelope de atuação exige erro de cerca de 1 m perto do solo (impl., iteração M10.3, secção 6).
- **Recomendação: aceitar como limite de `E0`**, reportado à parte e **com a classe física** (+99 e +86 `U` face a `guarded`) em todas as tabelas, não só a recuperação. A aceitação do custo é do proprietário; este dossiê não a dá por adquirida.
- **Alternativas.** (b) Regra "menor altitude" dentro de B+: troca +99 `U` em `gnss_bias` por cerca de +94 `U` em `altimeter_bias_low`. (c) O braço com prior da decisão 7, prometido na decisão 15 como mitigação reportada: **não foi construído**; o proprietário decide se `guarded` serve de comparação ou se o braço é necessário.

### 5. Conteúdo do manifesto de congelação

Ver a configuração recomendada e a lista abaixo. Mínimo, além do pedido em 10.1 (desenho, `m10-nominal.json`, script de campanha, agregação, `spikes/m10-nav-feasibility/power_thresholds.py`, `source_sha256`): `scripts/m9_campaign.py` e `scripts/m91_campaign.py` (geram os sorteios das falhas das famílias F1 e F3), `scripts/m10_stats.py`, o script F5 e este dossiê, se o proprietário o quiser como registo das decisões.

- **Recomendação: manifesto alargado**, com a correção de `check_freeze` para verificar `source_sha256` e um conjunto mínimo de ficheiros. Consequência: trabalho de código e uma reexecução de desenvolvimento antes da congelação.
- **Alternativa.** Só o mínimo de 10.1: os sorteios de F1 e F3 e o binário ficam fora da imposição, e `check_freeze` aceita a avaliação com qualquer binário.

## Regressões de segurança de B+ face às bases (sementes 5000 a 5099)

Critério do documento de implementação (iteração M10.3, secção 10): material quando há mais de 2 `U` acima da base ou 5 ou mais recuperações perdidas. "Cont." é a contagem de execuções contidas (`S1` a `S5` cumpridos e contacto).

| Célula | Base | Base R/T/U, cont. | B+ R/T/U, cont. | B+* R/T/U | Material |
| --- | --- | --- | --- | --- | --- |
| `gnss_bias` | `guarded` | 21/78/1, 100 | 0/0/100, 100 | 0/0/100 | **sim, +99 U** (prevista, decisão 4) |
| `pair_gnss_bias+altimeter_dropout` | `guarded` | 19/67/14, 100 | 0/0/100, 100 | 0/0/100 | **sim, +86 U** (mesmo mecanismo) |
| `pair_altimeter_bias+gnss_dropout` | `robust`, `guarded` | 92/0/8, 100 | 41/32/27, 98 | 85/0/15 | **sim, +19 U**; +7 com perseguição |
| `pair_altimeter_bias_low+gnss_dropout` | `robust` | 92/0/8, 100 | 41/32/27, 98 | 85/0/15 | **sim, +19 U**; +7 com perseguição |
| `pair_altimeter_bias+gnss_dropout` | A | 43/34/23, 98 | 41/32/27, 98 | 85/0/15 (A* 89/0/11) | limite: +4 U; +4 com perseguição |
| `gnss_horizontal_bias` | `robust`, `guarded` | 10/75/15, 100 | 15/82/3, 97 | igual | não em `U` (3 contra 15); **3 falhas de invariante** contra 0, a explicar |
| `gnss_horizontal_bias` | B | 15/83/2, 98 | 15/82/3, 97 | igual | não (+1 U) |
| `gnss_dropout` | `robust`, `guarded` | 93/0/7, 100 | 92/0/8, 100 | igual | não (+1 U) |
| `gnss_coherent_ramp` | B | 20/69/11, 96 | 57/29/14, 100 | igual | não (+3 U, mas +37 R e +4 contidas); 1 falha de alerta `hv` contra 0 |
| `imu_accel_drift` | B | 79/0/21, 100 | 74/8/18, 100 | igual | não em `U` (18 contra 21); −5 R por `T`: regressão de recuperação, não de segurança |
| `altimeter_stuck` | `robust`, `guarded`, B | 94/0/6, 100 | 91/3/6, 100 | igual | não: −3 R por `T`, sem `U` a mais (`altimeter_delay` contra B: −4 R, sub-limiar) |

Nenhuma transição insegura nem violação do limite de transições (MD1, MD2) em B+. Falhas de alerta verticais: B+ 1, B 2, A 3 (todas no par de modo comum). As bases do M9 não têm bloco `navigation`, por isso I1v não é comparável com elas.

## Configuração experimental: o que fica por fixar

- **Binários misturados.** A tabela de desenvolvimento junta `a82ca967…` (M9, A, B, afinação) e `45c9ee25…` (B+). A diferença entre `3499f51` e `ca04cc6` está confinada à testemunha ancorada em `nav_filter.rs` (reposição do histórico num ciclo sem IMU; sem âncora, sem isolamento), que só serve o isolamento de B+. É plausível que A, B e as bases não mudem, mas não está medido. Bloqueia a congelação até haver uma reexecução de todos os braços num só binário.
- **O manifesto não prende o binário.** `check_freeze` em `scripts/m10_campaign.py` só verifica os ficheiros listados, não exige um conjunto mínimo e não compara `binary_sha256` nem `source_sha256` (o M9 registava e verificava `source_sha256`). `--binary` aceita qualquer executável. É um defeito de imposição, não de cálculo.
- **Sorteios fora do script de campanha.** `faults_for` usa `m91_campaign.sample_fault` e `m9_campaign.sample_fault`; sem estes ficheiros no manifesto, os casos de F1 e F3 podem mudar sem que o manifesto o detete.
- **Plano de chunks não codificado.** Os oito chunks de 10.3, o corte de `baseline` ao nominal, `robust` sem pares e A só nos pares 1, 2 e 4 não existem no script; os chunks com C têm de ser redefinidos.
- **F5 não implementado.** O pré-registo pede varrimentos do início de `altimeter_bias` e de `gnss_bias`, da magnitude de `altimeter_bias` (0,5 a 5 m) e da taxa de `altimeter_drift` (0,03 a 0,3 m/s). `scripts/m10_onset_sweep.py` é outra experiência (início de cinco falhas novas).
- **Valores por omissão diferentes do caso.** `NavParams::default()` tem `suspect_cusum_fraction` 0.5 e `anchored_imu_witness` false; o modelo de caso fixa 1.0 e true. Sem efeito na campanha (o JSON fixa os 35 campos e `deny_unknown_fields` recusa o resto), mas os testes que usam o valor por omissão não exercitam a configuração congelada.
- **Rastreabilidade por semente.** Só os resumos estão commitados. As afirmações por semente (5082 com falha de alerta, 22 de 27 `U` por `R2`, a semente 5001) não se verificam a partir da evidência; os sorteios sim.

## Justiça da afinação

- **Protocolo igual no formato.** Os três manifestos têm orçamento 30, sementes `5000-5099`, células F1, métrica de recuperação média com no máximo 2 de 100 degradações espúrias no nominal, `search_seed` 10 e o mesmo binário e modelo de partida.
- **Liberdade desigual.** 5, 6 e 8 parâmetros (432, 1 728 e 10 368 combinações). B+ partiu de um ponto afinado à mão nas mesmas sementes (impl., desvio 5) e recebeu duas alterações de desenho (testemunha ancorada, perseguição) avaliadas nas mesmas sementes e nas células F2 e F3. A e B não tiveram iteração equivalente. Os números de desenvolvimento de B+ estão, por isso, otimistas face a A e B. Não há fuga para a avaliação: nenhum ficheiro de afinação ou de campanha contém sementes protegidas e `m10_stats.py` e `m10_tune.py` recusam-nas.
- **Desvio à regra de seleção.** `scripts/m10_tune.py` escolhe "a melhor avaliação admissível". Para B é a avaliação 2 (0,7455 contra 0,7427 de partida; +3 execuções em 1 100). O documento propõe congelar os valores de partida nos três braços. Com um único bloco `controller.nav` partilhado, adotar o ponto de B mudaria B+ e A (`accel_process_sigma_mps2`, `bias_walk_sigma_mps2_per_sqrt_s`, `t_hold_s`, `readmission_samples`). É um desvio ao protocolo de 10.4 que o proprietário aceita ou não; a alternativa exige blocos de parâmetros por braço.
- **A métrica de afinação não vê A.** Os 30 pontos de A dão 0,7364; F1 não tem falhas que a votação decida.

## Estatística

- **Correto.** `tango_p` (MLE restrito, variância `n(2q + δ − δ²)`, valor-p unilateral à esquerda) corresponde a Tango e Nam. A dimensão exata está abaixo de 1,10 vezes o alfa em toda a grelha (pior rácio 0,997, monotonia verificada em cada `c`; `p3-size.json`). Recalculados aqui: P1 suportada com no máximo 25, 23, 22 e 22 falhas em 700 aos quatro alfas de Holm; P2 com pelo menos 87, 89, 89 e 90 em 100; 0 em 700 dá 0,43%. O intervalo de `compare` (quatro caudas de 0,0125) tem cobertura conjunta de pelo menos 95%.
- **Em falta.** Nenhum script calcula P1, P2, o valor-p primário da P3 sobre os oito chunks, a P4 ou a ordenação de Holm. É trabalho do script de agregação, que não existe.
- **Contradição no pré-registo.** P1 e P2 dizem "falsificada" abaixo do limiar; 10.6 diz "inconclusivo" quando o intervalo de Clopper-Pearson contém o limiar. Com 85 em 100 na P2, uma regra dá falsificada e a outra inconclusiva. O proprietário tem de fixar a precedência antes da congelação.
- **P1 pouco discriminante.** Das 700 execuções das sete células de P1 (`vertical_declaration_applicable`): em 497 o erro vertical nunca passa o limite de alerta, e a P1 não pode falhar; em 200 (`gnss_bias` e `gnss_bias_low`) passa sempre, mas B+ nunca está `Trusted` porque a regra de arranque de 8.4 não admite o radar, um mecanismo pré-registado; só 3 (2 em `altimeter_stuck`, 1 em `altimeter_delay`) discriminam. A conclusão de P1 deve ser reportada com estes três grupos.
- **Poder com 100 sementes de avaliação** (cálculo exato com as taxas de desenvolvimento). P2 com taxa verdadeira de 94%: 0,96 a 0,997; com 90%: 0,58 a 0,88. P3 a 0,0125 com `p_b` 0,25% e `p_c` 0,875%: cerca de 1,00; com `p_b` 2% e `p_c` 1%: 0,74; com 3% e 1%: 0,16. P1 com taxa de 2%: pelo menos 0,98. As células partilham sementes; os agrupamentos são otimistas, como o desenho já avisa.
- **Comparações múltiplas.** A família fechada (P1 a P4, Holm) está bem definida; tudo o resto é reportado sem valor-p, como em `paired-*.json`. Sem C, ver a decisão 2.
- **H-F2.** Nas 600 execuções das seis células de H-F2, B+ tem 4 com degradação espúria (uma em cada: nominal, `gimbal_stuck`, `altimeter_dropout`, `gnss_dropout`; a quinta, em `altimeter_stuck`, está fora de H-F2); limite superior de 95% de 1,52%, abaixo de 2% mas perto do limiar de 6 em 600. A e B têm 0.
- **N2.** NEES médio de B+ de 48,8 em `thrust_loss` e 13,1 em `ignition_delay` (7 estados): N2 deverá falhar nestas células. Só `thrust_loss` está documentado.

## Prontidão para congelar

| Item | Estado | Bloqueia |
| --- | --- | --- |
| Decisões 1 a 4 registadas como emendas escritas ao desenho (6.3, 6.6, 8.3, decisões 8, 12 e 15) | proprietário | sim |
| Referências a C retiradas ou passadas a B+ (10.3, H-H, H-F2, 10.7, "A contra C") | em falta | sim |
| Precedência entre "falsificada" (P1, P2) e "inconclusivo" (10.6); tratamento de Holm sem C | proprietário | sim |
| Script de agregação dos chunks com P1, P2, P3, P4 e Holm | em falta | sim |
| Varrimentos F5 implementados, ou retirados por emenda | em falta | sim |
| Plano de chunks e braços por família codificado (sem C, A nos pares 1, 2, 4, `robust` nos pares 1 e 2 se aprovado) | em falta | sim |
| `check_freeze` a verificar `source_sha256` ou o binário e um conjunto mínimo de ficheiros | em falta | sim |
| Manifesto com `m9_campaign.py`, `m91_campaign.py`, `m10_stats.py` e o script F5 | em falta | sim |
| `m10-nominal.json` com a decisão 3 aplicada e reexecução de todos os braços num só binário | em falta | sim |
| Hashes do M10 refixados em `crates/vv-rocket/tests/m10.rs` sobre a configuração congelada | em falta | sim |
| Bandeiras de retenção fixadas no comando (`--keep-sample 5 --keep-failures 50`) | em falta | sim |
| Desvio à seleção da afinação de B aceite ou blocos por braço | proprietário | sim |
| Braço com prior da decisão 15: construir ou dispensar por escrito | proprietário | sim |
| Constantes da paridade em `NavParams` ou declaradas fixas no código | proprietário | não |
| Explicação das 3 falhas de invariante de B+ em `gnss_horizontal_bias` | em falta | não |
| Dimensão exata da P3 com script commitado | feito | |
| Recusa das sementes protegidas na campanha, na afinação e nas estatísticas | feito | |
| Regra de arranque a frio verificada contra `robust` (M10.2) | feito | |

## O que o proprietário tem de fazer a seguir

1. Decidir 1 a 4 (recomendação: 1a, 2a com Holm m = 4, 3b, 4a com a classe física reportada) e as duas regras estatísticas em aberto.
2. Pedir as emendas ao desenho e o trabalho em falta da tabela anterior; nada disto toca nas sementes protegidas.
3. Depois da reexecução de desenvolvimento no binário único, rever as diferenças face a este dossiê e autorizar o commit de `m10-freeze.json`.
4. Só então autorizar `--evaluation` nas sementes 3000 a 3099.

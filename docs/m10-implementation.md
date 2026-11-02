# M10: implementação da navegação resiliente

Estado: **em desenvolvimento (M10.1 a M10.4, iteração M10.3 incluída), sementes de desenvolvimento apenas.** Nada aqui é resultado de avaliação. A configuração final não está congelada (`crates/vv-rocket/landing/m10-freeze.json` não existe) e nenhuma semente de avaliação (3000 a 3099) ou de reserva (6000 a 6099) foi executada. O desenho aceite é o de `docs/m10-resilient-navigation.md` (PR #13); este documento descreve o que está construído, como se executa, os desvios ao desenho e as medições de desenvolvimento.

## Autorização

Em 02/11/2026 o proprietário aceitou o M10.0 (PR #13 integrada) e autorizou a execução do M10 com os pacotes M10.1 a M10.5 como trabalho interno, sem portas intermédias. Ficam com o proprietário: alterar hipóteses aprovadas ou aceitar regressões de segurança materiais, congelar a configuração de avaliação, aceder às sementes de avaliação e de reserva, integrar PR grandes em `main` e operações destrutivas.

## O que está construído

| Componente | Ficheiro | Estado |
| --- | --- | --- |
| Matriz quadrada de tamanho fixo (Joseph, simetrização, Cholesky) | `crates/vv-rocket/src/math.rs` (`Mat<N>`) | feito, testado |
| Esquema `vv-rocket-landing.v2` (políticas M10, bloco `controller.nav`, sete falhas novas) | `landing_model.rs`, `landing_sensors.rs`, `landing_sim.rs` | feito; um ficheiro `v1` rejeita tudo o que é do M10 |
| Braços A, B e B+ | `crates/vv-rocket/src/nav_filter.rs` (`NavSystem`) | feitos; B+ com isolamento por paridade de taxas e reprocessamento; C não construída (decisão 12) |
| Gestor de modos, saúde por grupo, integridade por canal, monitor de segurança | `nav_filter.rs` | feitos |
| Lei lateral degradada | `landing_controller.rs` | feita, com o termo de posição por estima de 8.2 |
| Verificador `vv-rocket-landing-verification.v3` (aditivo) | `crates/vv-rocket/src/nav_verify.rs` | feito; só para as políticas M10 |
| Campanha com recusa das sementes de avaliação | `scripts/m10_campaign.py` | feita; recusa testada em `tests/test_m10_campaign.py` |
| Modelo de caso do M10 | `crates/vv-rocket/landing/m10-nominal.json` | valores de desenvolvimento, não congelado |

Os traços e as verificações de `baseline`, `robust`, `guarded` e `baseline_guarded` não mudaram: os campos novos são `Option` e não se serializam nessas políticas, e os hashes fixados em `tests/landing.rs` e `tests/reference.rs` continuam a passar. A mesma política do M9 num caso `v2` dá os mesmos bytes que no `v1` (teste `a_v1_case_keeps_its_meaning_and_rejects_every_m10_addition`). O módulo `nav_filter` está sujeito ao teste de isolamento do controlador (importações exatas e palavras proibidas) e ao teste de aritmética sem funções transcendentes.

## Esquema v2: falhas novas

Os efeitos são aplicados pelos sensores; as falhas antigas não mudam. As gamas são validadas pelo simulador; as janelas são sorteadas pela campanha (`sample_new_fault`, gerador `random.Random(seed * 100 + 50 + índice)`).

| Falha | Efeito | Gama | Janela na campanha |
| --- | --- | --- | --- |
| `altimeter_stuck` | o altímetro repete o último valor entregue antes da janela | sem magnitude; janela de 1 a 10 s | duração de 1 a 10 s dentro de 5 a 23 s |
| `altimeter_delay` | o altímetro mede a altitude de `magnitude` segundos antes, em ciclos de controlo inteiros (até 10) | 0,02 a 0,2 s | início de 2 a 12 s, até ao fim |
| `altimeter_outliers` | cada amostra é um ponto fora com probabilidade `magnitude`; amplitude de 5 a 50 σ e sinal sorteados num fluxo próprio (`source::ALTIMETER_OUTLIER = 13`) | 0,001 a 0,01 | todo o voo |
| `altimeter_drift` | soma `magnitude · (t − início)` ao altímetro | 0,03 a 0,3 m/s | início de 2 a 12 s (varrimento F5) |
| `gnss_horizontal_bias` | soma a magnitude à posição GNSS em x e y (não em z) | 5 a 30 m | desde 0 s (`_t0`) e início de 4 a 12 s |
| `gnss_coherent_ramp` | a posição em x e z cresce `magnitude · (t − início)` e a velocidade em x e z soma `magnitude` | 0,1 a 3 m/s | início de 4 a 12 s |
| `imu_accel_drift` | o viés ao longo de `x_B` cresce `magnitude · (t − início)` | 0,01 a 0,1 m/s² por s | início de 2 a 12 s |

O fluxo de pontos fora só é consumido enquanto a janela está aberta, e nenhum outro fluxo muda (teste `m10_outliers_draw_from_their_own_stream_and_stay_in_their_amplitude_range`). `acted` de `altimeter_outliers` diz que a janela esteve aberta, não que saiu um ponto fora.

## Como executar

```sh
cargo build --release --manifest-path crates/vv-rocket/Cargo.toml
crates/vv-rocket/target/release/vv-rocket land crates/vv-rocket/landing/m10-nominal.json --seed 4000 --output runs/m10-demo
crates/vv-rocket/target/release/vv-rocket replay runs/m10-demo
python scripts/m10_campaign.py --seeds 5000-5099 --scenarios F1 --arms guarded,m10_b_plus --output-root runs/m10-dev-f1
```

O `verification.json` de uma execução M10 tem o bloco `navigation`: classe física R, T ou U; erro verdadeiro e falhas de alerta por canal (vertical, velocidade horizontal, posição horizontal); NEES médio; transições de modo; transições inseguras (MD1); limite de transições (MD2); degradações fora das janelas de falha (F2); atraso da primeira declaração por falha. Em cada amostra do traço, `estimate.nav` tem o modo, a saúde dos grupos, o estado de cada canal, os desvios-padrão, o viés estimado, a velocidade do monitor e os CUSUM.

## Desvios ao desenho (pré-congelação)

Cada desvio tem a razão medida. Nenhum altera hipóteses, células, braços ou critérios pré-registados. O primeiro é uma decisão que o proprietário pode vetar antes da congelação.

1. **Isolamento por paridade no domínio das taxas (decisão a confirmar pelo proprietário).** A secção 6.3 isola por paridade no domínio das medidas e conclui que, em `E0`, "só se deteta". A conclusão continua certa para um viés constante: com duas fontes de altitude, "radar errado" e "GNSS z errado" dão o mesmo resíduo. A própria taxonomia (secção 5, linhas 8 e 9) prevê, porém, o isolamento de um valor preso ("sim se a fonte tem alternativas") e de um atraso ("por correlação do resíduo com v"). As alternativas são as testemunhas da velocidade vertical: o declive do radar, a velocidade vertical do GNSS e a integração da IMU. B+ compara-as aos pares numa janela de 0,5 s alinhada no tempo: declive do radar contra a velocidade GNSS média, declive da altitude GNSS contra a mesma velocidade, e variação da velocidade pela IMU contra a do GNSS. Sob a hipótese de falha única, uma fonte só é isolada quando é inconsistente (acima de 4 σ) com as outras duas e estas são consistentes entre si (abaixo de 3 σ). Qualquer outro padrão é "não isolado" e segue a decisão 7 (declarar e manter a solução principal). O isolamento só é tentado no primeiro segundo de um alarme vertical do CUSUM, uma vez por episódio. Um viés constante não muda nenhuma taxa e nunca é isolado: teste `constant_biases_and_accelerometer_drift_are_never_isolated` e células `gnss_bias`, `altimeter_bias` e `gnss_horizontal_bias_t0` (0 isolamentos em 300 execuções). O verificador compara cada isolamento com a falha injetada (F3), pelo grupo e pelo instante: desde o commit `b27bd5e`, um isolamento só é correto se uma falha do mesmo grupo já tiver começado (ver "Iteração M10.3"). Sem este desvio, B+ recuperava 8 de 100 em `altimeter_stuck`, 0 de 100 em `altimeter_delay` e 0 de 100 em `gnss_coherent_ramp`.
2. **Exclusão e reprocessamento (6.4).** Uma isolação exclui o grupo, repõe o instantâneo certificado mais recente anterior ao início estimado menos 1 s e reprocessa o anel de entradas sem o grupo, de uma só vez. Os instantâneos são tirados a cada 0,5 s, 12 no anel, e certificados quando todos os CUSUM estão abaixo de `h/2`; o anel de entradas guarda 300 ciclos (6 s). O limite do reprocessamento é constante (300 ciclos), não os 25 ciclos por ciclo do desenho, e a correção tem latência nula em vez de distribuída. Sem instantâneo certificado, a covariância vertical é inflacionada. Depois de uma exclusão pelo detetor, a readmissão exige `T_hold` limpo contra a solução.
3. **Readmissão do GNSS depois de perda de dados.** O desenho testa a readmissão contra a solução sem o grupo. Com o teste normalizado contra a estimativa por estima, a covariância não cobre a deriva real e o recetor nunca voltava (53 de 100 recuperações em `gnss_dropout`, contra 93 de 100 de `robust`). A perda de dados não é uma corrupção: o recetor volta quando é consistente consigo próprio (incremento de posição contra velocidade média, a 4 σ, durante 10 épocas), e a covariância de posição e velocidade volta ao nível do recetor.
4. **Termo de posição por estima na lei lateral (8.2, alínea 3).** Com o recetor fora só por falta de dados, ou isolado a partir do instantâneo reposto, a lei continua a perseguir a plataforma com a posição por estima enquanto `σ_h + ½ b_h t²` for inferior a um quarto da distância. Um recetor suspeito pelo detetor e ainda em uso nunca guia o veículo.
5. **Afinação nas sementes de desenvolvimento (10.4).** Métrica: recuperação média nas 11 células de F1, com no máximo 2 de 100 degradações espúrias no nominal.
   - Limiar de `Suspect`: o valor inicial `h/2` dá, pela aproximação de Siegmund, um ARL0 de cerca de 2,6e3 amostras por lado, ou seja uma a duas suspeitas falsas por execução (medido: 40 de 100 execuções nominais com degradação espúria). As frações 0,5, 0,75 e 1,0 deram médias de 69,5, 73,4 e 73,7, com 40, 2 e 1 espúrias; escolhida 1,0. O espaço foi limitado a frações até 1,0, para que a suspeita nunca venha depois do alarme.
   - Passeio aleatório do viés do acelerómetro: 0,002, 0,01, 0,03 e 0,1 m/s²/√s deram médias de 73,7, 74,2, 74,5 e 74,4; escolhido 0,03. Este valor também elimina a regressão de `ignition_delay` (de 74 para 82) e sobe `imu_accel_drift` de 17 para 74.
   - Épocas de readmissão do GNSS: 2, 3, 5 e 10 deram 74,27, 74,27, 74,36 e 74,45; mantidas 10.
   - Só B+ foi afinado; A e B usam os mesmos valores partilhados, sem o orçamento de 10.4 (ver "Limitações abertas").

## Medições de desenvolvimento (sementes 5000 a 5099, 100 por célula)

Tabela do estado da PR 15, mantida como registo. A tabela atual, com a testemunha ancorada e os nove braços e variantes, está na iteração M10.3, secção 10.

Recuperações (`landed` com `S1` a `S5`), com o binário e o modelo de caso deste commit (SHA-256 de `m10-nominal.json`: `86417497572048c2e45b84750a26e63e5c0d83a4feb80cc425e3086f6ec9f461`). Comando, por braço e família: `python scripts/m10_campaign.py --seeds 5000-5099 --scenarios F1 --arms <braço> --jobs 8`, e o mesmo com `--scenarios F2,F3`. Máquina: Windows 11, AMD64 Family 25 Model 97, Python 3.14.6; cerca de 10 s por 1 100 execuções com 8 tarefas. Em cada célula e braço uma execução foi reproduzida com `vv-rocket replay`, e todas foram verificadas. **São números de desenvolvimento, não de avaliação.**

| Célula | `robust` | `guarded` | A | B | B+ | B+: isolamento correto / errado / nenhum | B+: I1v | B+: T / U |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nominal | 94 | 94 | 94 | 94 | 94 | 0 / 0 / 100 | 0 | 0 / 6 |
| `thrust_loss` | 87 | 87 | 87 | 88 | 88 | 0 / 0 / 100 | 0 | 0 / 12 |
| `ignition_delay` | 81 | 81 | 81 | 80 | 82 | 0 / 0 / 100 | 0 | 0 / 18 |
| `gimbal_stuck` | 90 | 90 | 90 | 92 | 92 | 0 / 0 / 100 | 0 | 0 / 8 |
| `altimeter_bias` | 92 | 92 | 92 | 94 | 94 | 0 / 0 / 100 | 0 | 0 / 6 |
| `altimeter_dropout` | 94 | 94 | 94 | 94 | 94 | 0 / 0 / 100 | 0 | 0 / 6 |
| `gnss_dropout` | 93 | 93 | 91 | 92 | 92 | 0 / 0 / 100 | 0 | 0 / 8 |
| `gnss_bias` (desde 0 s) | 0 | 21 | 0 | 0 | 0 | 0 / 0 / 100 | 0 | 0 / 100 |
| `imu_accel_bias` | 89 | 89 | 89 | 89 | 89 | 0 / 0 / 100 | 0 | 0 / 11 |
| `altimeter_bias_low` | 92 | 0 | 92 | 94 | 94 | 0 / 0 / 100 | 0 | 0 / 6 |
| `gnss_bias_low` (desde 0 s) | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 100 | 0 | 0 / 100 |
| `altimeter_stuck` | 94 | 94 | 62 | 94 | 92 | 100 / 0 / 0 | 0 | 2 / 6 |
| `altimeter_delay` | 1 | 1 | 0 | 82 | 79 | 100 / 0 / 0 | 0 | 4 / 17 |
| `altimeter_outliers` | 93 | 93 | 56 | 94 | 94 | 96 / 1 / 3 | 0 | 0 / 6 |
| `gnss_horizontal_bias_t0` | 6 | 6 | 6 | 7 | 7 | 0 / 0 / 100 | 0 | 91 / 2 |
| `gnss_horizontal_bias` | 10 | 10 | 10 | 15 | 15 | 0 / 0 / 100 | 0 | 82 / 3 |
| `gnss_coherent_ramp` | 2 | 2 | 13 | 20 | 53 | 77 / 8 / 15 | 0 | 26 / 21 |
| `imu_accel_drift` | 58 | 58 | 59 | 79 | 74 | 0 / 0 / 100 | 0 | 8 / 18 |
| par `altimeter_bias` + `gnss_dropout` | 92 | 92 | 43 | 41 | 41 | 0 / 0 / 100 | 0 | 32 / 27 |
| par `altimeter_bias_low` + `gnss_dropout` | 92 | 0 | 43 | 41 | 41 | 0 / 0 / 100 | 0 | 32 / 27 |
| par `gnss_bias` + `altimeter_dropout` | 0 | 19 | 0 | 0 | 0 | 0 / 0 / 100 | 0 | 0 / 100 |
| par `altimeter_bias±` + `imu_accel_bias` | 61 | 31 | 61 | 89 | 89 | 0 / 0 / 100 | 0 | 0 / 11 |
| par `gnss_bias_low` + `imu_accel_bias` | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 100 | 0 | 0 / 100 |
| par `altimeter_bias±` + `gnss_bias±` | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 100 | 1 | 0 / 100 |

Avaliação global de segurança (as 24 células, 2 400 execuções por braço; classe física pelo estado real):

| Braço | R | T | U | Falhas de alerta verticais | Execuções com degradação espúria |
| --- | --- | --- | --- | --- | --- |
| `robust` | 1 321 | 167 | 912 | n/a | n/a |
| `guarded` | 1 147 | 312 | 941 | n/a | n/a |
| A | 1 163 | 283 | 954 | 3 | 0 |
| B | 1 379 | 307 | 714 | 2 | 0 |
| B+ | 1 404 | 277 | 719 | 1 | 5 |

Leitura:

- B+ cumpre as previsões de 8.4. Recupera `altimeter_bias_low` por prior (94 contra 0 de `guarded`), falha `gnss_bias` e `gnss_bias_low` desde 0 s e declara-o (estado vertical nunca `trusted`, 0 falhas de alerta). A regressão prevista em `gnss_bias` face a `guarded` (0 contra 21) está à vista e **não está aceite** (decisão 15).
- Nas oito células M9 da P3, B+ não fica abaixo de `guarded` em nenhuma por mais de 2 pontos. A P3 só se decide com as sementes de avaliação.
- **Regressão nova, por resolver ou aceitar:** nos pares `altimeter_bias` ou `altimeter_bias_low` com `gnss_dropout`, B+ recupera 41 de 100, contra 92 de `robust` (e de `guarded` no primeiro par). O radar nunca é admitido (viés desde 0 s) e, na perda do GNSS, os dois grupos de altitude ficam fora. O modo passa a `untrusted`, que pelo desenho (8.3) deixa de perseguir a plataforma: 32 toques fora da plataforma. **Correção (iteração M10.3):** a explicação anterior das 27 execuções `U` (deriva vertical do estado de viés) estava errada. Das 27, 22 falham `R2` (velocidade horizontal no toque) e só 5 falham `R1`; o erro vertical final tem mediana de 0,05 m e máximo de 0,71 m. A causa dominante é lateral: sem perseguição durante a perda do GNSS, o veículo afasta-se e a perseguição retomada tarde, quando o recetor volta, deixa velocidade horizontal no toque.
- `gnss_coherent_ramp`: 8 isolamentos errados em 100 (o radar é acusado quando o início da rampa escapa à janela da paridade). Resolvido em 7 de 8 pela testemunha ancorada da IMU (ver "Iteração M10.3").
- A deteção é rápida e declarada; é o isolamento que separa a recuperação da declaração.

## Experiência de lacuna (decisão 12)

Pré-escrita no documento de desenho. B+ fixado pelo modelo de caso acima (SHA-256 começado por `86417497`) e pelo binário do commit 8d0894a; as correções da revisão do commit 93bf8ee foram depois reexecutadas nas 24 células de B+ sem nenhuma diferença. Comando: `python scripts/m10_campaign.py --seeds 5000-5099 --scenarios altimeter_bias,altimeter_bias_low,gnss_bias,gnss_bias_low,imu_accel_bias,altimeter_stuck,altimeter_delay,F3 --arms m10_b_plus`.

- Células de falha única detetável (7 × 100): 0 falhas de alerta verticais em 700; limite superior unilateral de 95%: 0,43%, abaixo de 5%.
- Células de pares (6 × 100): 1 falha de alerta vertical, no par `altimeter_bias±` com `gnss_bias±`, que viola a hipótese de falha única.
- **Critério:** "limite superior de 95% acima de 5% agrupado, **ou** pelo menos uma falha de alerta numa célula de pares em que a hipótese de falha única é violada". A segunda condição cumpre-se, com uma única execução. Pela decisão 12 e pelo roteiro, a construção de C passa a ser uma decisão do proprietário, com base neste relatório.

## Verificação da regra de arranque a frio (critério de saída do M10.2)

Comparação em células já publicadas, sem afinação (secção 8.4): `python scripts/m10_campaign.py --seeds 2000-2029 --scenarios altimeter_bias,altimeter_bias_low --arms robust,m10_b_plus`. `robust` reproduz os números publicados do M9.1 (28 de 30 nas duas células). B+ recupera 29 de 30 nas duas, dentro de 2 em 30 de `robust`, com 0 falhas de alerta verticais. **Critério cumprido.** A previsão de 8.4 ("sem vantagem de recuperação sobre `robust`", 80% a 100%) mantém-se.

## Desfasamento da força específica (critério de saída do M10.1)

Medido no teste `the_specific_force_lag_is_measured_and_bounded_by_the_actuator` (nominal, semente 4000), a partir do registo da verdade. O erro da aceleração usada na propagação é `|T(k) + T(k+1) − 2 T(k−1)| / (2 m)`. Na ignição é de 11,4 m/s² durante um período de controlo (0,02 s, cerca de 0,23 m/s de erro de velocidade). Nas rampas do acelerador é no máximo 0,48 m/s². O filtro absorve-o no ruído de processo (0,1 m/s² por ciclo) e no detetor; não há compensação pelo comando conhecido.

## Iteração M10.3: revisão crítica de B+ (sementes de desenvolvimento)

Nesta iteração, B+ foi tratada como referência a contestar, não como desenho fechado. Cada alteração tem uma medição emparelhada nas sementes 5000 a 5099 (as mesmas 24 células, 2 400 execuções por variante) e um teste de regressão em `crates/vv-rocket/tests/m10.rs`. Nenhuma semente de avaliação ou de reserva foi usada.

### 1. Contabilidade do isolamento (F3)

O veredicto F3 olhava só para o grupo isolado: um isolamento do grupo certo **antes** do início da falha contava como correto. Agora cada isolamento sai em `navigation.isolation_events` com o instante e um veredicto próprio (`correct`, `before_onset`, `wrong`), e a execução só é `correct` se todos os isolamentos seguirem o início de uma falha do mesmo grupo. Teste: `an_isolation_before_the_fault_onset_is_not_credited` (a mesma execução julgada contra uma falha deslocada para depois do isolamento, e contra uma falha de outro grupo). Na campanha de desenvolvimento as contagens não mudaram: nenhum isolamento anterior ao início tinha acontecido. O defeito era real, mas não tinha inflacionado os números publicados.

### 2. Testemunha da IMU ancorada antes do ponto de mudança

**Causa dos isolamentos errados em `gnss_coherent_ramp`.** Os 8 isolamentos errados acontecem 0,4 a 1 s depois do início, com magnitudes de 0,5 a 1,2 m/s. Uma rampa coerente soma a magnitude à velocidade GNSS e faz crescer a posição ao mesmo ritmo: a testemunha GNSS z contra GNSS vz fica consistente, o radar fica inconsistente com o GNSS, e a testemunha da IMU, que compara variações de velocidade dentro da janela de 0,5 s, só vê o degrau de velocidade se a janela contiver o início. Quando a janela já cai toda depois do início, a IMU parece concordar com o GNSS e o padrão aponta o radar. As 8 execuções acabaram `U`.

**Alteração.** A testemunha da IMU passa a comparar a variação da velocidade vertical GNSS desde a última época pelo menos 0,2 s anterior ao ponto de mudança estimado (o último zero do CUSUM das fontes verticais que se moveram) com o integral da IMU no mesmo intervalo. A variância soma o ruído das duas velocidades, o ruído de processo integrado e a incerteza do viés vezes a duração (`sqrt(P_bb) · T`). Guarda-se um histórico de 40 épocas (4 s). Parâmetro `controller.nav.anchored_imu_witness` (`false` mantém o comportamento da PR 15); ligado no modelo de caso de desenvolvimento.

| Célula (B+) | Isolamento correto / errado / nenhum, antes | Depois | Recuperadas, antes / depois | `U`, antes / depois |
| --- | --- | --- | --- | --- |
| `gnss_coherent_ramp` | 77 / 8 / 15 | 85 / 1 / 14 | 53 / 58 | 21 / 13 |
| `altimeter_outliers` | 96 / 1 / 3 | 97 / 0 / 3 | 94 / 94 | 6 / 6 |
| `altimeter_stuck` | 100 / 0 / 0 | 100 / 0 / 0 | 92 / 92 | 6 / 6 |
| `altimeter_delay` | 100 / 0 / 0 | 100 / 0 / 0 | 79 / 79 | 17 / 17 |

As outras 20 células não mudaram. Global de B+: `R` de 1 404 para 1 409, `U` de 719 para 711. Fica um isolamento errado (semente 5001, rampa de 0,5 m/s): o degrau de velocidade é pequeno face à incerteza acumulada da testemunha. Testes: `the_anchored_imu_witness_stops_blaming_the_radar_for_a_coherent_receiver_ramp` (semente 5019: radar acusado com a janela, recetor isolado com a âncora) e os testes de isolamento anteriores.

### 3. Independência estatística da paridade

Os três resíduos de paridade não são independentes: o declive do radar e o declive da altitude GNSS são comparados com a mesma velocidade GNSS média, e a testemunha da IMU também usa a velocidade GNSS. Os limiares de 4 σ e 3 σ não podem ser lidos como probabilidades de um produto de testes independentes. O que se pode afirmar sem independência:

- **Limite pela união.** Um isolamento falso exige que pelo menos um resíduo passe 4 σ sem falha. Com resíduos gaussianos bem calibrados, a probabilidade por tentativa é no máximo `3 · P(|Z| > 4) ≈ 1,9e-4`, qualquer que seja a correlação. O isolamento só é tentado no primeiro segundo de um alarme vertical (50 ciclos), uma vez por episódio: no máximo cerca de 1% por alarme, e os alarmes nominais são raros (1 em 100 execuções nominais).
- **Medição.** Em 1 900 execuções das células sem falha de taxa (nominal, falhas do M9, vieses constantes, perdas de dados, viés horizontal), 0 isolamentos.
- **O que o limite não cobre.** Erros do modelo de variância: o desfasamento da força específica na ignição (11 m/s² durante um ciclo), o braço de alavanca do radar com o centro de massa estimado e a deriva do viés do acelerómetro. São estes, e não a correlação, que explicam o isolamento errado que resta e os 3 "não isolados" de `altimeter_outliers`.

A paridade no domínio das taxas continua a ser um desvio ao desenho (secção 6.3) que o proprietário pode vetar; os números acima são a evidência para essa decisão.

### 4. Regressão do par `altimeter_bias` com `gnss_dropout`: causa e uma política exploratória

O diagnóstico corrigido está em "Leitura", acima: a perda é lateral. A regra aprovada (8.3) faz `untrusted` amortecer só a velocidade lateral. Nesta célula, `untrusted` nasce de dados em falta (o radar nunca admitido e o recetor sem dados), não de um desacordo, e a posição horizontal por estima continua boa durante 2 a 10 s (o mesmo limite de deriva `sigma_h + ½ b_h t²` que a lei degradada de 8.2 já usa).

**Política exploratória, não aceite** (`controller.nav.bounded_chase_when_untrusted`, desligada no modelo de caso): em `untrusted`, mantém a perseguição limitada da plataforma **só** quando nenhum desacordo está ativo e o detetor nunca implicou o recetor; caso contrário, a regra aprovada aplica-se.

| Célula (B+) | Regra aprovada: recuperadas, `T`, `U` | Variante: recuperadas, `T`, `U` | `robust`: recuperadas |
| --- | --- | --- | --- |
| par `altimeter_bias` + `gnss_dropout` | 41, 32, 27 | 85, 0, 15 | 92 |
| par `altimeter_bias_low` + `gnss_dropout` | 41, 32, 27 | 85, 0, 15 | 92 |
| as outras 22 células | sem diferença em nenhuma execução | | |

Global de B+: `R` de 1 409 para 1 497, `T` de 280 para 216, `U` de 711 para 687. Das 15 `U` que restam, 10 falham `R2` e 5 `R1` (perdas longas que acabam perto do toque); no nominal, B+ falha `R2` em 6 de 100. É uma alteração da semântica aprovada de `untrusted` e fica para decisão do proprietário. Teste: `the_exploratory_bounded_chase_keeps_the_pad_when_untrusted_comes_from_missing_data` (semente 5004: `T` com a regra aprovada, `R` com a variante).

### 5. Arquitetura C: a lacuna que a disparou não está ao alcance de C

A experiência de lacuna disparou com uma única falha de alerta vertical em 600 execuções de pares (célula `altimeter_bias±` + `gnss_bias±`, semente 5082). Nessa execução o viés do radar é de 5,93 m e o do GNSS z de 6,17 m, com o mesmo sinal: as duas fontes concordam a 0,24 m. O radar é admitido pela regra de arranque (diferença abaixo de 3 m) e as duas fontes erram juntas por cerca de 6 m. É uma falha de modo comum.

A separação de soluções de C (secção 6.5) compara o filtro completo com o subfiltro sem cada grupo. Com as duas fontes deslocadas da mesma quantidade, os subfiltros e o filtro completo concordam a cerca de 0,24 m; `PL_v = max(K_ff σ_0, K_fa σ_Δ + K_md σ_i)` fica perto de 2 m com os valores do protótipo, abaixo de `AL_v` a qualquer altitude acima de 100 m, e o estado vertical continuaria `trusted`. C falharia esta execução pela mesma razão que B+. Além disso, a P4 exige uma melhoria agrupada de pelo menos 3 pontos percentuais na taxa de falhas de alerta das células de pares, e B+ está em 0,17% (1 em 600): a P4 não pode ser cumprida com estes dados, qualquer que seja C.

**Conclusão de engenharia.** C, tal como foi pré-registada, não tem nestas células uma falha que consiga reduzir. Não foi construída nesta iteração; a recomendação está em "Decisões do proprietário". A falha de modo comum é uma limitação de `E0`: só uma terceira fonte independente de altitude (o barómetro de `E1` ou um sensor relativo à plataforma) a pode revelar.

### 6. `gnss_bias` desde 0 s: limite de observabilidade e de atuação

Com o radar e o GNSS z a discordar de 5 a 30 m desde o primeiro instante e vieses constantes, nenhuma taxa difere entre as hipóteses "radar errado" e "GNSS errado": a diferença não é observável em `E0`. Também não é contornável pela lei vertical: com o acelerador mínimo de 0,4 o veículo não paira (cerca de 12,8 m/s² de força específica mínima a 26 t, contra 9,81 m/s²). Se o veículo estiver Δ acima do que estima, chega a 1,5 m/s em `ĥ = 0`, trava a pelo menos 3 m/s², sobe, a regra dos 15 m corta o motor e cai de cerca de Δ − 0,4 m: `R1` (3 m/s) exige Δ ≤ 0,8 m. Se estiver Δ abaixo, toca antes de travar: `R1` exige Δ de cerca de 1 m no máximo. Uma ambiguidade de 5 m ou mais é fatal para a escolha errada. A regra "menor altitude" de `guarded` acerta 21 de 100 em `gnss_bias` por apostar no sinal e perde as 94 de `altimeter_bias_low`; B+ aposta no GNSS (regra de arranque, um prior declarado) e declara. Informação adicional necessária: uma terceira fonte independente de altitude com erro abaixo de cerca de 1 m perto do solo (barómetro de `E1` calibrado na plataforma, ou um sensor relativo à plataforma). Fica fora da comparação `E0` aceite.

### 7. NEES alto com `thrust_loss`

Medido: NEES médio de 48,8 com `thrust_loss` contra 6,6 no nominal (7 estados). A causa é a do registo anterior: o modelo de propelente do controlador integra o acelerador comandado com o empuxo nominal, a perda de empuxo reduz também o caudal, e o centro de massa estimado desloca-se cerca de 0,3 m, que entra na medida do radar pelo braço de alavanca. Uma correção pela força específica medida não separa, só com a IMU, perda de empuxo, massa e arrasto (cerca de 17% do empuxo a 130 m/s), e mexe num estado partilhado pelas políticas do M9 (`propellant_est`). Não foi alterado. O efeito é de consistência e não de resultado: B+ recupera 88 de 100, `robust` 87. Candidato identificado: um estado de desvio do radar com passeio lento, que absorve o erro do braço de alavanca e dá ajuda de velocidade pelo radar enviesado durante perdas do GNSS.

### 8. Dimensão exata da P3, agora com script commitado

`python scripts/m10_stats.py size` enumera o modelo multinomial completo com n = 800 na fronteira `p_b = p_c + 0,03`, `p_c` de 0,5% a 8%, aos quatro alfas de Holm. A região de rejeição de cada `c` é `b ≤ b_max(c)`; a monotonia foi verificada em todos os pontos (`--monotone-step 1`, 27 s). Resultado: dimensão de 0,0094 a 0,0122 a alfa 0,0125 e de 0,046 a 0,050 a alfa 0,05; o pior rácio entre dimensão e alfa é 0,997. O critério pré-registado (excesso relativo de no máximo 10%) é cumprido: o teste de score é conservador e continua a ser o valor-p primário da P3. O resultado reproduz o relato do verificador do M10.0. Testes em `tests/test_m10_stats.py`, incluindo a igualdade da enumeração com a força bruta para n = 40.

### 9. Afinação com o mesmo protocolo para A, B e B+ (10.4)

`scripts/m10_tune.py` aplica o protocolo de 10.4 a cada braço: as 11 células de F1, sementes 5000 a 5099, métrica igual à média da recuperação, restrição de no máximo 2 de 100 nominais com degradação espúria, 30 avaliações por braço. A avaliação 0 é a configuração de partida; as outras 29 são sorteadas sem repetição com `random.Random(10 * 1000 + índice do braço)` sobre os espaços de `SPACES` (registados em cada manifesto). Manifestos em `docs/evidence/m10-dev/tuning/`.

| Braço | Parâmetros afinados | Partida | Melhor (índice) | Gama das 30 | Admissíveis |
| --- | --- | --- | --- | --- | --- |
| A | 5 | 0,7364 | 0,7364 (0) | 0,7364 a 0,7364 | 30 |
| B | 6 | 0,7427 | 0,7455 (2) | 0,7264 a 0,7455 | 24 |
| B+ | 8 | 0,7445 | 0,7445 (0) | 0,0982 a 0,7445 | 17 |

Leitura: a métrica de F1 de A não depende de nenhum dos seus parâmetros (F1 não tem falhas que a votação decida). O melhor ponto de B ganha 3 execuções em 1 100 sobre a partida, abaixo da resolução de 100 sementes por célula e dentro do otimismo que a própria seleção introduz. B+ não melhora sobre a configuração de partida, que já tinha sido afinada à mão (desvio 5); as 13 avaliações inadmissíveis são as de `cusum_h` baixo ou `cusum_k` baixo, com falsos alarmes nominais. **Consequência para a justiça da comparação:** com o mesmo orçamento, nenhum braço muda de forma mensurável; a diferença entre A, B e B+ não vem de afinação desigual. Proposta de congelação: os valores partilhados de partida para os três braços (ver "Decisões do proprietário").

### 10. Tabela de desenvolvimento desta iteração

Binário deste commit e modelo de caso com `anchored_imu_witness` ligado (SHA-256 `c28a258c94a17b6ce1e8eb5a1442d977b4c951a0913375661ec3dddf8d05784a`). Comando por braço: `python scripts/m10_campaign.py --seeds 5000-5099 --scenarios F1,F2,F3 --arms <braço> --jobs 8 --output-root runs/m10-dev/<braço>`; com `*`, o mesmo modelo com `bounded_chase_when_untrusted` ligado (`--template`). Resumos em `docs/evidence/m10-dev/campaign/` e `campaign-bounded-chase/`. Máquina: Windows 11, AMD64 Family 25 Model 97, Python 3.14.6; cerca de 15 s por 2 400 execuções com 8 tarefas. Uma execução retida por célula e braço foi reproduzida com `vv-rocket replay`, todas verificadas. As políticas do M9 dão os mesmos números da tabela anterior. **Números de desenvolvimento, não de avaliação.**

Recuperações em 100:

| Célula | `baseline` | `robust` | `guarded` | A | B | B+ | A* | B* | B+* | B+: isolamento c / e / n | B+: I1v |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nominal | 96 | 94 | 94 | 94 | 94 | 94 | 94 | 94 | 94 | 0/0/100 | 0 |
| `thrust_loss` | 89 | 87 | 87 | 87 | 88 | 88 | 87 | 88 | 88 | 0/0/100 | 0 |
| `ignition_delay` | 85 | 81 | 81 | 81 | 80 | 82 | 81 | 80 | 82 | 0/0/100 | 0 |
| `gimbal_stuck` | 89 | 90 | 90 | 90 | 92 | 92 | 90 | 92 | 92 | 0/0/100 | 0 |
| `altimeter_bias` | 0 | 92 | 92 | 92 | 94 | 94 | 92 | 94 | 94 | 0/0/100 | 0 |
| `altimeter_dropout` | 34 | 94 | 94 | 94 | 94 | 94 | 94 | 94 | 94 | 0/0/100 | 0 |
| `gnss_dropout` | 26 | 93 | 93 | 91 | 92 | 92 | 91 | 92 | 92 | 0/0/100 | 0 |
| `gnss_bias` | 21 | 0 | 21 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0/100 | 0 |
| `imu_accel_bias` | 89 | 89 | 89 | 89 | 89 | 89 | 89 | 89 | 89 | 0/0/100 | 0 |
| `altimeter_bias_low` | 0 | 92 | 0 | 92 | 94 | 94 | 92 | 94 | 94 | 0/0/100 | 0 |
| `gnss_bias_low` | 23 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0/100 | 0 |
| `altimeter_stuck` | 40 | 94 | 94 | 62 | 94 | 92 | 72 | 94 | 92 | 100/0/0 | 0 |
| `altimeter_delay` | 19 | 1 | 1 | 0 | 82 | 79 | 0 | 82 | 79 | 100/0/0 | 0 |
| `altimeter_outliers` | 96 | 93 | 93 | 56 | 94 | 94 | 90 | 94 | 94 | 97/0/3 | 0 |
| `gnss_horizontal_bias_t0` | 7 | 6 | 6 | 6 | 7 | 7 | 6 | 7 | 7 | 0/0/100 | 0 |
| `gnss_horizontal_bias` | 9 | 10 | 10 | 10 | 15 | 15 | 10 | 15 | 15 | 0/0/100 | 0 |
| `gnss_coherent_ramp` | 14 | 2 | 2 | 13 | 20 | 58 | 13 | 20 | 58 | 85/1/14 | 0 |
| `imu_accel_drift` | 91 | 58 | 58 | 59 | 79 | 74 | 59 | 79 | 74 | 0/0/100 | 0 |
| par `altimeter_bias` + `gnss_dropout` | 1 | 92 | 92 | 43 | 41 | 41 | 89 | 85 | 85 | 0/0/100 | 0 |
| par `altimeter_bias_low` + `gnss_dropout` | 0 | 92 | 0 | 43 | 41 | 41 | 89 | 85 | 85 | 0/0/100 | 0 |
| par `gnss_bias` + `altimeter_dropout` | 11 | 0 | 19 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0/100 | 0 |
| par `altimeter_bias±` + `imu_accel_bias` | 0 | 61 | 31 | 61 | 89 | 89 | 61 | 89 | 89 | 0/0/100 | 0 |
| par `gnss_bias_low` + `imu_accel_bias` | 21 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0/100 | 0 |
| par `altimeter_bias±` + `gnss_bias±` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0/100 | 1 |

Avaliação global de segurança (24 células, 2 400 execuções por braço; classe pelo estado real):

| Braço | R | T | U | Falhas de alerta verticais | Degradações espúrias |
| --- | --- | --- | --- | --- | --- |
| `baseline` | 861 | 406 | 1 133 | n/a | n/a |
| `robust` | 1 321 | 167 | 912 | n/a | n/a |
| `guarded` | 1 147 | 312 | 941 | n/a | n/a |
| A | 1 163 | 283 | 954 | 3 | 0 |
| B | 1 379 | 307 | 714 | 2 | 0 |
| B+ | 1 409 | 280 | 711 | 1 | 5 |
| A* | 1 299 | 179 | 922 | 3 | 0 |
| B* | 1 467 | 243 | 690 | 2 | 0 |
| B+* | 1 497 | 216 | 687 | 1 | 5 |

Comparações emparelhadas por semente (`python scripts/m10_stats.py compare <registos> --first guarded --second m10_b_plus`), reportadas sem valor-p: nas oito células da P3, `b` = 2 pares em que só `guarded` recupera e `c` = 7 em que só B+ recupera, em 800. É um ensaio da maquinaria da P3 em sementes de desenvolvimento, não um resultado da P3. Diferenças de pelo menos 5 pontos entre B+ e `guarded` por célula: a favor de B+ em `altimeter_bias_low` (+94), `altimeter_delay` (+78), `gnss_coherent_ramp` (+56), `pair altimeter_bias± + imu_accel_bias` (+58), `pair altimeter_bias_low + gnss_dropout` (+41), `imu_accel_drift` (+16), `gnss_horizontal_bias` (+5); contra B+ em `gnss_bias` (−21, regressão prevista), `pair gnss_bias + altimeter_dropout` (−19, o mesmo mecanismo) e `pair altimeter_bias + gnss_dropout` (−51 com a regra aprovada; −7 com a variante `*`). Contra `robust`, a única regressão de B+ acima de 5 pontos é esse par (−51; −7 com a variante).

**Regressões de segurança.** Em 22 das 24 células, B+ não tem mais de 2 execuções `U` acima de `robust` nem perde 5 ou mais recuperações. As exceções são os dois pares com `gnss_dropout`: 27 `U` contra 8 de `robust` com a regra aprovada, 15 com a variante. Este par continua a ser uma regressão material de segurança face a `robust` com a regra aprovada; não está aceite.

### 11. Tempo adverso: varrimento do instante de início

`python scripts/m10_onset_sweep.py --arms m10_a,m10_b,m10_b_plus --seeds 5000-5019` fixa o início de cinco falhas em 2, 3, ..., 20 s (20 sementes por ponto, 5 700 execuções; `docs/evidence/m10-dev/onset-sweep.json`). Recuperações de B+ em 20, pior instante:

| Falha (parâmetro) | B+: pior instante, recuperadas | B+: gama | B: gama | A: gama |
| --- | --- | --- | --- | --- |
| `altimeter_stuck` (3 s) | qualquer, 18 | 18 a 18 | 18 a 18 | 2 (8 s) a 20 |
| `altimeter_delay` (0,1 s) | 11 s, 17 | 17 a 18 | 15 a 17 | 0 a 0 |
| `gnss_coherent_ramp` (1 m/s) | 2 s, 2 | 2 a 20 | 1 a 20 | 0 a 13 |
| `gnss_dropout` (5 s) | 6 s, 17 | 17 a 19 | 17 a 19 | 17 a 19 |
| `imu_accel_drift` (0,05 m/s² por s) | 2 s, 16 | 16 a 17 | 16 a 17 | 3 a 17 |

Nenhum isolamento errado e nenhuma falha de alerta vertical em todo o varrimento. O ponto fraco de B+ é uma rampa coerente do recetor que começa cedo (2 a 6 s, antes ou logo depois da ignição a cerca de 4,2 s): 2 de 20 a 2 s, 12 de 20 a 6 s, pelo menos 13 de 20 a partir de 7 s. Com um início tão cedo não há instantâneo certificado anterior ao início menos 1 s no anel, e a correção recai na inflação da covariância vertical, sem reposição do estado (6.4). A valor preso e o atraso do radar são indiferentes ao instante.

### 12. Decisões do proprietário

Cada decisão tem a evidência acima. Nenhuma foi tomada por mim; as recomendações estão marcadas.

1. **Paridade no domínio das taxas (desvio 1).** Alternativas: (a) aceitar, com a testemunha ancorada; (b) vetar e voltar à paridade de 6.3 (só deteta em `E0`). Evidência: sem ela, B+ recupera 8, 0 e 0 em `altimeter_stuck`, `altimeter_delay` e `gnss_coherent_ramp`; com ela, 92, 79 e 58, com 1 isolamento errado em 2 400 execuções e 0 em 1 900 sem falha de taxa; o limite pela união não depende de independência. **Recomendação: (a).**
2. **Arquitetura C (decisão 12).** Alternativas: (a) não construir C e registar a experiência de lacuna como disparada por uma falha de modo comum fora do modelo de falhas de C; (b) construir C para a avaliação, sabendo que a P4 não é cumprível com B+ em 0,17% de I1v nos pares. **Recomendação: (a).** O que reduziria esta falha é uma terceira fonte de altitude, não um nível de proteção.
3. **Semântica de `untrusted` (decisão 8) e o par com `gnss_dropout`.** Alternativas: (a) manter a regra aprovada (B+ 41 contra `robust` 92, regressão de segurança material não aceite); (b) adotar a perseguição limitada só quando `untrusted` vem de dados em falta (B+ 85, 15 `U` contra 8 de `robust`, nenhuma outra célula muda em 2 400 execuções); (c) aceitar a regressão. **Recomendação: (b)**, como emenda escrita a 8.3 antes da congelação, com o par ainda reportado como regressão residual de 7 pontos face a `robust`.
4. **Regressão prevista em `gnss_bias` (decisão 15).** Alternativas: (a) aceitar como limite de `E0` (secção 6 acima: ambiguidade não observável e incompatível com o envelope de atuação); (b) voltar à regra "menor altitude" de `guarded` (21 em `gnss_bias`, 0 em `altimeter_bias_low`). **Recomendação: (a)**, reportada à parte como já pré-registado.
5. **Congelação.** Pronto para congelar: o código deste commit, o modelo de caso de desenvolvimento (com `anchored_imu_witness` ligado e a decisão 3 aplicada), os valores partilhados de partida para A, B e B+ (secção 9), `scripts/m10_campaign.py`, `scripts/m10_stats.py`, os testes e o documento de desenho com as emendas aprovadas. Falta antes da avaliação: as decisões 1 a 4; o manifesto `m10-freeze.json`, que só o proprietário autoriza; refixar os hashes do M10 em `tests/m10.rs` sobre a configuração congelada; e o script de agregação dos oito chunks.

## Limitações abertas

- Com `thrust_loss`, o modelo de propelente do controlador sobrestima o consumo, e o braço de alavanca do radar fica com cerca de 0,3 m de erro no centro de massa. O guiamento atua no plano da tubeira, onde o erro se cancela, mas o NEES dessas execuções sobe para cerca de 40.
- C não está construída: a recomendação é não a construir ("Decisões do proprietário", decisão 2).
- A, B e B+ foram afinados com o mesmo protocolo e orçamento de 10.4 (secção 9 da iteração M10.3); B+ teve também a afinação manual anterior, declarada no desvio 5.
- A enumeração da dimensão da P3 tem script commitado (`scripts/m10_stats.py size`). O manifesto de congelação (porta do proprietário), o script de agregação dos chunks de avaliação e os varrimentos F5 de `altimeter_drift` ficam por fazer.
- A rampa coerente do recetor que começa antes de haver um instantâneo certificado (início até cerca de 6 s) continua a ser o pior caso de B+ (2 de 20 com início a 2 s).
- Os limiares da paridade e da readmissão (`RATE_BAD`, `RATE_OK`, `ISOLATION_WINDOW_S`, `CONSISTENCY_SIGMA`, `COLD_FLAG_S`, `SUSPECT_CLEAR_S`) são constantes do código, cobertas por `source_sha256`, e não campos do caso como pede 10.1. No M10.4 passam a `NavParams` ou ficam documentadas como fixadas no código.
- Identidade entre plataformas: os traços e as verificações do M10 (nominal e radar preso, semente 4000) estão fixados por SHA-256 em `tests/m10.rs` e verificados na CI em Linux e Windows. Os hashes seguem a configuração de desenvolvimento e são refixados a cada afinação, até à congelação.

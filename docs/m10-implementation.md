# M10: implementação da navegação resiliente

Estado: **em desenvolvimento (M10.1 a M10.4), sementes de desenvolvimento apenas.** Nada aqui é resultado de avaliação. A configuração final não está congelada (`crates/vv-rocket/landing/m10-freeze.json` não existe) e nenhuma semente de avaliação (3000 a 3099) ou de reserva (6000 a 6099) foi executada. O desenho aceite é o de `docs/m10-resilient-navigation.md` (PR #13); este documento descreve o que está construído, como se executa, os desvios ao desenho e as medições de desenvolvimento.

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

1. **Isolamento por paridade no domínio das taxas (decisão a confirmar pelo proprietário).** A secção 6.3 isola por paridade no domínio das medidas e conclui que, em `E0`, "só se deteta". A conclusão continua certa para um viés constante: com duas fontes de altitude, "radar errado" e "GNSS z errado" dão o mesmo resíduo. A própria taxonomia (secção 5, linhas 8 e 9) prevê, porém, o isolamento de um valor preso ("sim se a fonte tem alternativas") e de um atraso ("por correlação do resíduo com v"). As alternativas são as testemunhas da velocidade vertical: o declive do radar, a velocidade vertical do GNSS e a integração da IMU. B+ compara-as aos pares numa janela de 0,5 s alinhada no tempo: declive do radar contra a velocidade GNSS média, declive da altitude GNSS contra a mesma velocidade, e variação da velocidade pela IMU contra a do GNSS. Sob a hipótese de falha única, uma fonte só é isolada quando é inconsistente (acima de 4 σ) com as outras duas e estas são consistentes entre si (abaixo de 3 σ). Qualquer outro padrão é "não isolado" e segue a decisão 7 (declarar e manter a solução principal). O isolamento só é tentado no primeiro segundo de um alarme vertical do CUSUM, uma vez por episódio. Um viés constante não muda nenhuma taxa e nunca é isolado: teste `constant_biases_and_accelerometer_drift_are_never_isolated` e células `gnss_bias`, `altimeter_bias` e `gnss_horizontal_bias_t0` (0 isolamentos em 300 execuções). O verificador compara cada isolamento com a falha injetada (F3); o veredicto olha para o grupo, não para o instante, pelo que um isolamento do grupo certo antes do início da falha também conta como correto. Sem este desvio, B+ recuperava 8 de 100 em `altimeter_stuck`, 0 de 100 em `altimeter_delay` e 0 de 100 em `gnss_coherent_ramp`.
2. **Exclusão e reprocessamento (6.4).** Uma isolação exclui o grupo, repõe o instantâneo certificado mais recente anterior ao início estimado menos 1 s e reprocessa o anel de entradas sem o grupo, de uma só vez. Os instantâneos são tirados a cada 0,5 s, 12 no anel, e certificados quando todos os CUSUM estão abaixo de `h/2`; o anel de entradas guarda 300 ciclos (6 s). O limite do reprocessamento é constante (300 ciclos), não os 25 ciclos por ciclo do desenho, e a correção tem latência nula em vez de distribuída. Sem instantâneo certificado, a covariância vertical é inflacionada. Depois de uma exclusão pelo detetor, a readmissão exige `T_hold` limpo contra a solução.
3. **Readmissão do GNSS depois de perda de dados.** O desenho testa a readmissão contra a solução sem o grupo. Com o teste normalizado contra a estimativa por estima, a covariância não cobre a deriva real e o recetor nunca voltava (53 de 100 recuperações em `gnss_dropout`, contra 93 de 100 de `robust`). A perda de dados não é uma corrupção: o recetor volta quando é consistente consigo próprio (incremento de posição contra velocidade média, a 4 σ, durante 10 épocas), e a covariância de posição e velocidade volta ao nível do recetor.
4. **Termo de posição por estima na lei lateral (8.2, alínea 3).** Com o recetor fora só por falta de dados, ou isolado a partir do instantâneo reposto, a lei continua a perseguir a plataforma com a posição por estima enquanto `σ_h + ½ b_h t²` for inferior a um quarto da distância. Um recetor suspeito pelo detetor e ainda em uso nunca guia o veículo.
5. **Afinação nas sementes de desenvolvimento (10.4).** Métrica: recuperação média nas 11 células de F1, com no máximo 2 de 100 degradações espúrias no nominal.
   - Limiar de `Suspect`: o valor inicial `h/2` dá, pela aproximação de Siegmund, um ARL0 de cerca de 2,6e3 amostras por lado, ou seja uma a duas suspeitas falsas por execução (medido: 40 de 100 execuções nominais com degradação espúria). As frações 0,5, 0,75 e 1,0 deram médias de 69,5, 73,4 e 73,7, com 40, 2 e 1 espúrias; escolhida 1,0. O espaço foi limitado a frações até 1,0, para que a suspeita nunca venha depois do alarme.
   - Passeio aleatório do viés do acelerómetro: 0,002, 0,01, 0,03 e 0,1 m/s²/√s deram médias de 73,7, 74,2, 74,5 e 74,4; escolhido 0,03. Este valor também elimina a regressão de `ignition_delay` (de 74 para 82) e sobe `imu_accel_drift` de 17 para 74.
   - Épocas de readmissão do GNSS: 2, 3, 5 e 10 deram 74,27, 74,27, 74,36 e 74,45; mantidas 10.
   - Só B+ foi afinado; A e B usam os mesmos valores partilhados, sem o orçamento de 10.4 (ver "Limitações abertas").

## Medições de desenvolvimento (sementes 5000 a 5099, 100 por célula)

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
- **Regressão nova, por resolver ou aceitar:** nos pares `altimeter_bias` ou `altimeter_bias_low` com `gnss_dropout`, B+ recupera 41 de 100, contra 92 de `robust` (e de `guarded` no primeiro par). O radar nunca é admitido (viés desde 0 s) e, na perda do GNSS, os dois grupos de altitude ficam fora. O modo passa a `untrusted`, que pelo desenho (8.3) deixa de perseguir a plataforma: 32 toques fora da plataforma. A estimativa vertical por estima deriva cerca de 1 m em 10 s, porque o estado de viés, com o passeio aleatório afinado, integra ruído quando o viés real é nulo: 27 aterragens duras. `robust` não estima o viés e, com viés real nulo, deriva menos.
- `gnss_coherent_ramp`: 8 isolamentos errados em 100 (o radar é acusado quando o início da rampa escapa à janela da paridade).
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

## Limitações abertas

- Com `thrust_loss`, o modelo de propelente do controlador sobrestima o consumo, e o braço de alavanca do radar fica com cerca de 0,3 m de erro no centro de massa. O guiamento atua no plano da tubeira, onde o erro se cancela, mas o NEES dessas execuções sobe para cerca de 40.
- C não está construída (decisão do proprietário, acima).
- A e B não foram afinados com o orçamento de 10.4 (30 avaliações por braço); só B+ foi afinado. A comparação entre A, B e B+ ainda não é justa no sentido de 10.4.
- O manifesto de congelação, a enumeração da dimensão da P3 com script commitado e os varrimentos F5 ficam para o M10.4.
- Os limiares da paridade e da readmissão (`RATE_BAD`, `RATE_OK`, `ISOLATION_WINDOW_S`, `CONSISTENCY_SIGMA`, `COLD_FLAG_S`, `SUSPECT_CLEAR_S`) são constantes do código, cobertas por `source_sha256`, e não campos do caso como pede 10.1. No M10.4 passam a `NavParams` ou ficam documentadas como fixadas no código.
- Identidade entre plataformas: os traços e as verificações do M10 (nominal e radar preso, semente 4000) estão fixados por SHA-256 em `tests/m10.rs` e verificados na CI em Linux e Windows. Os hashes seguem a configuração de desenvolvimento e são refixados a cada afinação, até à congelação.

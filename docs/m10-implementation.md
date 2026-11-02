# M10: implementação da navegação resiliente

Estado: **em desenvolvimento (M10.1 a M10.4), sementes de desenvolvimento apenas.** Nada aqui é resultado de avaliação. A configuração final não está congelada (`crates/vv-rocket/landing/m10-freeze.json` não existe) e nenhuma semente de avaliação (3000 a 3099) ou de reserva (6000 a 6099) foi executada. O desenho aceite é o de `docs/m10-resilient-navigation.md` (PR #13); este documento descreve o que está construído, como se executa, os desvios ao desenho e as medições de desenvolvimento.

## Autorização

Em 02/11/2026 o proprietário aceitou o M10.0 (PR #13 integrada) e autorizou a execução do M10 com os pacotes M10.1 a M10.5 como trabalho interno, sem portas intermédias. Ficam com o proprietário: alterar hipóteses aprovadas ou aceitar regressões de segurança materiais, congelar a configuração de avaliação, aceder às sementes de avaliação e de reserva, integrar PR grandes em `main` e operações destrutivas.

## O que está construído

| Componente | Ficheiro | Estado |
| --- | --- | --- |
| Matriz quadrada de tamanho fixo (Joseph, simetrização, Cholesky) | `crates/vv-rocket/src/math.rs` (`Mat<N>`) | feito, testado |
| Esquema `vv-rocket-landing.v2` (políticas M10, bloco `controller.nav`, sete falhas novas) | `landing_model.rs`, `landing_sensors.rs`, `landing_sim.rs` | feito; um ficheiro `v1` rejeita tudo o que é do M10 |
| Braços A, B e B+ | `crates/vv-rocket/src/nav_filter.rs` (`NavSystem`) | feitos; C não construída (decisão 12) |
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

1. **Readmissão do GNSS depois de perda de dados.** O desenho testa a readmissão contra a solução sem o grupo. Com o teste normalizado contra a estimativa por estima, a covariância não cobre a deriva real e o recetor nunca voltava (medido: 53 de 100 recuperações em `gnss_dropout`, contra 93 de 100 de `robust`). A perda de dados não é uma corrupção: o recetor volta quando é consistente consigo próprio (incremento de posição contra velocidade média, 10 épocas), e a covariância de posição e velocidade volta ao nível do recetor.
2. **Termo de posição por estima na lei lateral (8.2, alínea 3).** Com o recetor fora só por falta de dados, a lei continua a perseguir a plataforma com a posição por estima enquanto `σ_h + ½ b_h t²` for inferior a um quarto da distância. Um recetor suspeito pelo detetor nunca guia o veículo.
3. **Limiar de `Suspect`.** O valor inicial `h/2` dá, pela aproximação de Siegmund, um ARL0 de cerca de 2,6e3 amostras por lado; com cerca de 2,5e3 inovações por execução, prevê uma a duas suspeitas falsas por execução. Medido: 40 de 100 execuções nominais com degradação espúria. Varrimento nas sementes 5000 a 5099 (F1, B+), métrica de 10.4: a fração 0,5 dá recuperação média 69,5 e 40 espúrias; 0,75 dá 73,4 e 2; 1,0 dá 73,7 e 1. Escolhida 1,0 (`Suspect` ao nível do alarme `h`). O espaço foi limitado a frações até 1,0, para que a suspeita nunca venha depois do alarme.
4. **Reprocessamento (6.4) não implementado.** No estado atual, em `E0`, as exclusões vêm só de falta de dados; ver "Limitações abertas".

## Medições de desenvolvimento (sementes 5000 a 5099, 100 por célula)

Recuperações (`landed` com `S1` a `S5`). Comando: `python scripts/m10_campaign.py --seeds 5000-5099 --scenarios <família> --arms <braço> --jobs 8`. Máquina: Windows 11, AMD64 Family 25 Model 97, Python 3.14.6. As 1 100 execuções de uma família levam cerca de 10 s com 8 tarefas.

| Célula | `robust` | `guarded` | A | B | B+ |
| --- | --- | --- | --- | --- | --- |
| nominal | 94 | 94 | 94 | 94 | 94 |
| `thrust_loss` | 87 | 87 | 87 | 88 | 88 |
| `ignition_delay` | 81 | 81 | 81 | 79 | 74 |
| `gimbal_stuck` | 90 | 90 | 90 | 92 | 92 |
| `altimeter_bias` | 92 | 92 | 92 | 94 | 94 |
| `altimeter_dropout` | 94 | 94 | 94 | 94 | 94 |
| `gnss_dropout` | 93 | 93 | 91 | 92 | 92 |
| `gnss_bias` (desde 0 s) | 0 | 21 | 0 | 0 | 0 |
| `imu_accel_bias` | 89 | 89 | 89 | 89 | 89 |
| `altimeter_bias_low` | 92 | 0 | 92 | 94 | 94 |
| `gnss_bias_low` (desde 0 s) | 0 | 0 | 0 | 0 | 0 |
| `altimeter_stuck` | n/a | 94 | 62 | 94 | 8 |
| `altimeter_delay` | n/a | 1 | 0 | 81 | 0 |
| `altimeter_outliers` | n/a | 93 | 56 | 94 | 94 |
| `gnss_horizontal_bias_t0` | n/a | 6 | 6 | 7 | 7 |
| `gnss_horizontal_bias` | n/a | 10 | 10 | 15 | 15 |
| `gnss_coherent_ramp` | n/a | 2 | 13 | 20 | 0 |
| `imu_accel_drift` | n/a | 58 | 59 | 15 | 17 |

Falhas de alerta verticais (I1v) de B+: zero em todas as células de falha única; 1 de 100 no par `altimeter_bias±` com `gnss_bias±` (A: 3, B: 2), que viola a hipótese de falha única. Degradações espúrias de B+ no nominal: 1 de 100.

Leitura: B+ cumpre as previsões de 8.4. Recupera `altimeter_bias_low` por prior, falha `gnss_bias` e `gnss_bias_low` desde 0 s e declara-o. Tem, porém, lacunas graves em `altimeter_stuck`, `altimeter_delay`, `gnss_coherent_ramp` e `imu_accel_drift`. A causa é a do desenho: sem rejeição por amostra e sem isolamento em `E0`, B+ continua a fundir uma fonte que o detetor já acusou. `ignition_delay` regride 7 pontos face a `guarded`, numa célula da P3, ainda por diagnosticar.

## Limitações abertas

- Em `E0` só há isolamento no arranque a frio (regra de admissão). O isolamento por paridade no domínio das taxas (declive do radar, velocidade vertical GNSS, integração da IMU) está em estudo; é uma decisão a apresentar ao proprietário antes da congelação.
- Com `thrust_loss`, o modelo de propelente do controlador sobrestima o consumo e o braço de alavanca do radar fica com cerca de 0,3 m de erro no centro de massa. O guiamento atua no plano da tubeira, onde o erro se cancela, mas o NEES dessas execuções sobe para cerca de 40.
- C não está construída. A experiência de lacuna (decisão 12) ainda não correu com B+ congelado.

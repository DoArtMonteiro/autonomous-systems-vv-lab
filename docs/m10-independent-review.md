# Revisão independente do M10 antes do congelamento

Data: 3 de novembro de 2026. Objeto: o ramo `feat/m10-resilient-nav` (PR #15) no commit `d3118f2`, em particular B+ (`m10_b_plus`, testemunha da IMU ancorada) e a variante exploratória `bounded_chase_when_untrusted`. A revisão foi feita por um revisor de controlo e segurança que não escreveu o M10, com o objetivo de refutar as quatro decisões propostas ao proprietário (A a D). Este documento regista o que a revisão encontrou. Não altera o estimador, os parâmetros, as hipóteses nem os critérios.

## Fronteiras

- Só sementes de desenvolvimento 5000 a 5099. Nenhuma semente de avaliação (3000 a 3099), de reserva (6000 a 6099) ou do intervalo 100 a 129 foi executada. `scripts/m10_adversarial_probe.py` recusa-as antes de correr.
- `crates/vv-rocket`, os documentos do M10 e `docs/evidence/m10-dev/` são iguais em `d3118f2` e no ramo onde a revisão correu.
- O binário usado foi construído pela revisão (SHA-256 `9a3f477650fc069401f1283fd10fba9f7f186e4f0c4c441c1a5f9a955642c80e`), não o binário das evidências do M10 (`45c9ee25…`). Reproduz exatamente as células de pares já registadas: 41/32/27 com B+ aprovado e 85/0/15 com a variante, nas duas células `gnss_dropout`, e 0/0/100 na célula de modo comum.
- Cerca de 11 700 execuções, 200 s de relógio com 8 processos.

## Comandos e resultados guardados

```sh
python scripts/m10_campaign.py --binary <vv-rocket> --seeds 5000-5099 --scenarios F3 --arms m10_b_plus --jobs 8 --keep-sample 0 --keep-failures 0 --output-root <saída>/val-approved
python scripts/m10_campaign.py --binary <vv-rocket> --template <m10-nominal.json com controller.nav.bounded_chase_when_untrusted = true> --seeds 5000-5099 --scenarios F3 --arms m10_b_plus --jobs 8 --keep-sample 0 --keep-failures 0 --output-root <saída>/val-bounded
python scripts/m10_campaign.py --binary <vv-rocket> --seeds 5000-5099 --scenarios gnss_coherent_ramp,altimeter_stuck,altimeter_delay,altimeter_outliers --arms m10_b,m10_b_plus --jobs 8 --keep-sample 0 --keep-failures 0 --output-root <saída>/val-ramp
python scripts/m10_adversarial_probe.py {ignition|ramp|rampbase|steps|chase} --binary <vv-rocket> --output <saída>/probe-<plano>.json --seeds 5000-5019
python scripts/m10_adversarial_probe.py summary <saída>/probe-<plano>.json
```

Os resumos estão em `docs/evidence/m10-dev/independent-review/`: `probe-<plano>-summary.txt` (gerados pelo comando `summary`) e `val-<nome>-summary.md` (gerados por `m10_campaign.py`). As saídas completas das sondas (3,7 MB) não estão no repositório; os seus SHA-256:

| Plano | Execuções | SHA-256 |
| --- | ---: | --- |
| `ignition` | 5 100 | `2250f335187aaa3165cbdfba62853402f3156036a1585e0fa33a042b8e3bdf3b` |
| `ramp` | 500 | `f0b913f93355577dfba8a6db4d5e22e79170255b2a89b924f1277a093ea32442` |
| `rampbase` | 640 | `ede574bd7797459edccbcc3cab4282e4032350665dbf0332a18ddbb653952e26` |
| `steps` | 1 680 | `e55981205d2a4d3405206317569e6f66b75791ce14ef6a415d0e7afcdb5f5ddb` |
| `chase` | 1 680 | `c1d62dfb10168e9cfc8843bcc5dc9056a27f326c2aab8913dcfb7e132457e20a` |

As sondas foram corridas primeiro por um script provisório do revisor. `scripts/m10_adversarial_probe.py` é a sua versão parametrizada, com os mesmos planos. Voltou a correr `ramp` e `chase` e deu, execução a execução, a mesma classe física, os mesmos requisitos falhados, o mesmo isolamento e os mesmos alertas (500 e 1 680 execuções, 0 diferenças).

## Decisão A: paridade no domínio da taxa, ancorada

Veredicto: **não suportada tal como proposta**. É sólida para falhas de taxa grandes, não para rampas lentas.

Pressupostos no código: uma falha de cada vez e três testemunhas da taxa vertical, todas comparadas com a vz do GNSS (declive do radar, declive do z do GNSS e integral da IMU, `nav_filter.rs:878-897`). As testemunhas não são independentes. As variâncias usam só os sigmas configurados (`nav_filter.rs:877-879`), iguais aos do simulador por construção; o ruído simulado é Irwin-Hall branco, limitado a ±3,46σ (`prng.rs:60-73`). O isolamento é tentado em cada ciclo até 1 s depois de um alarme.

Cobertura: bloqueado, atraso, degraus a meio do voo e rampas coerentes de pelo menos cerca de 0,8 m/s. Fora: polarizações constantes, falhas da IMU e `altimeter_drift`. O menor erro de taxa isolável é cerca de `RATE_BAD·σ_rg ≈ 4 × 0,20 ≈ 0,8 m/s`; uma deriva de 0,03 a 0,3 m/s nunca é isolada (B+ 43/60, 60/60 e 58/60 U, perto de `robust` e `guarded`). `altimeter_drift` não entra na F2 e a F5 não existe.

Termos não modelados: o atraso da força específica na ignição é 0,23 m/s, cerca de 3,0σ da testemunha da IMU quando `P_bb` é pequeno, o que consome todo o `RATE_OK`. O limite da união (`m10-implementation.md:159`) só limita o isolamento falso sem falha presente; com falha, os resíduos têm um desvio fixo e nada o limita.

Isolamento errado medido (B+, 20 sementes por ponto):

| Sonda | Isolamentos errados | Notas |
| --- | --- | --- |
| Bloqueado, atraso 0,1 e 0,2, início 3,0 a 5,5 s | 0 / 3 060 | isolamento correto 95 a 97 % |
| Rampa 2 m/s, início 3,0 a 5,5 s | 0 / 1 020 | |
| Rampa 0,5 m/s, início 3,0 a 3,95 s | 124 / 400 (31 %) | |
| Rampa 0,5 m/s, início 4,0 a 5,5 s | 62 / 620 (10 %) | dentro da janela de início da campanha |
| Rampa 0,5 m/s, início 6 a 12 s | 14 / 100 | |
| Rampa 0,3 m/s, início 6 a 12 s | 4 / 100 | |
| Degraus do altímetro ou do GNSS (5 e 15 m) a meio do voo | 0 / 480 | |

Consequência de segurança: na sonda `ignition`, os 186 isolamentos errados terminaram todos em U e todos produziram uma falha de alerta da velocidade horizontal; nenhuma execução sem isolamento errado a teve. É um caminho de confiança falsa, não só uma recuperação perdida. O varrimento de início registado ("0 errados em 5 700") usou só rampas de 1 m/s, e `m10_onset_sweep.py` só regista a falha de alerta vertical, por isso não podia ver este modo.

Mecanismo provável, lido no código e não verificado: o radar só é culpado se `ok(d_ig)` (`nav_filter.rs:891`); a âncora é a última época pelo menos 0,2 s antes de `change_t`, e `change_t` é o último zero do CUSUM. Uma rampa lenta move o CUSUM devagar, o ponto de mudança estimado cai depois do início verdadeiro e a testemunha não vê o degrau de velocidade.

Regressão estratificada contra B, escondida pelo total da célula: com magnitudes de 0,2 a 0,8 m/s, B+ tem 12/18 U contra 6/18 de B; a 0,5 m/s, 64/80 contra 6/80 (`robust` e `guarded`: 80/80). Os totais da célula (57 R contra 20) vêm das rampas de pelo menos 0,8 m/s.

Consistência do estimador: NEES médio 6,6 no nominal (7 estados), 48,8 com `thrust_loss`, 13,1 com `ignition_delay` e 652 em `gnss_coherent_ramp`. Não há teste com ruído real diferente do modelado.

Recomendação: não aceitar A como está. Uma versão emendada tem de passar os testes 1, 2, 3, 9 e 10 da lista abaixo.

## Decisão B: não construir C para a experiência original

Veredicto: **suportada**, com dois valores do documento errados.

- A falha da semente 5082, recalculada com `faults_for`: `altimeter_bias` +5,93 m e `gnss_bias` +6,17 m, ambos constantes desde 0 s. `gnss_bias` é injetado em x e em z (`landing_sensors.rs:138-142`). No conjunto E0 nenhum subconjunto tem uma referência independente de altitude ou de x, por isso nenhuma solução de subconjunto expõe uma polarização do mesmo sinal.
- No traço, o erro de altitude estimado é cerca de 5,95 m durante todo o voo, com σ_z = 0,015 m e o canal vertical declarado de confiança 93,5 % do tempo. A falha de alerta acontece a 16,46 s, a cerca de 290 m.
- "PL_v ≈ 2 m" (`m10-implementation.md:183`) não tem suporte. Com o ruído do caso, σ0 = 0,015 m e PL_v ≈ 0,34 m. A conclusão fica mais forte: C, com nível de proteção só de covariância, continua de confiança e falha.
- Um teste de separação com estatística ficaria no limite (K_fa·σ_Δ ≈ 0,19 m contra uma separação de cerca de 0,22 m). Um alarme aí viria de uma discordância aleatória, não de limitar o erro de 6 m; a frase "C não o deteta" deve dizer isto.
- A contagem esperada de "0 a 3" casos na avaliação parece alta: as sementes 5030 e 5057 (discordâncias de 0,45 e 1,55 m) foram declaradas sem falha de alerta.

Recomendação: registar C como adiado para a experiência original e propor uma hipótese separada com sensor independente (E1).

## Decisão C: perseguição limitada quando não há confiança

Veredicto: **não aceitar com base no 41 para 85 em 100**.

- Troca por célula de pares (sementes 5000 a 5099): T para R 27, U para R 17, **T para U 5**. As sementes 5044, 5049, 5067, 5084 e 5088 passam a toques duros, todas a falhar R2, com início da perda do GNSS entre 11,6 e 16,2 s. Dos 15 U restantes, 5 são causados pela variante.
- As duas células `gnss_dropout` são a mesma experiência: o radar nunca é admitido, o sinal não importa e os resultados são iguais semente a semente. Todas as somas globais contam esta célula duas vezes.
- Início tardio da perda (`altimeter_bias` 10 m desde 0 s mais `gnss_dropout`, 20 sementes por ponto):

| Início da perda | B+ aprovado U | Variante U | `robust` U | `guarded` U |
| --- | --- | --- | --- | --- |
| 8 s | 36/40 | 6/40 | 4/40 | 4/40 |
| 12 s ou mais | 15/200 | 31/200 | 22/200 | 22/200 |
| 12 s ou mais, altímetro também perdido | 14/200 | 32/200 | sem dados | sem dados |

  A partir de 12 s, a variante é pior do que B+ aprovado e do que `robust`. A célula registada sorteia inícios de 5 a 23 s e mistura os dois regimes.
- Qualidade da covariância: com `imu_accel_drift` 0,03 e perda do GNSS, 3 T para U. O limite de deriva `σ_h + ½·b_h·t²` (`nav_filter.rs:390-392`) não tem termo `σ_vh·t`.
- Confiança falsa: o texto diz que a perseguição só é permitida se "o detetor nunca implicou o recetor" (histórico); o código verifica o indicador atual, limpo quando o grupo fica desatualizado (`nav_filter.rs:1095-1100`) e na passagem de Suspect a Healthy (`:1121`). A sonda não mostrou U novo por esta via; é uma diferença entre texto e código.
- Discordância seguida de perda (radar bloqueado e depois GNSS perdido): U 16 para 1. Rampa coerente seguida de perda: sem mudança. Sem transições inseguras nem invariantes falhados; todos os U novos são falhas de R2 ou R1 no toque.

Recomendação: não adotar a emenda à 8.3. Uma versão nova tem de passar os testes 4, 5, 6 e 8.

## Decisão D: polarização do GNSS sob E0

Veredicto: **a inobservabilidade é suportada; a regressão está escondida nos agregados do documento de implementação**.

- Uma polarização constante desde 0 s não muda nenhuma taxa; x também é polarizado e não tem segunda fonte. Está fora da P3 por pré-registo (`m10-resilient-navigation.md:787`).
- Onde fica escondida: as tabelas de implementação mostram só recuperações (0 contra 21); a tabela global mostra B+ com U 713 contra 941 de `guarded`, o que cobre +99 U em `gnss_bias` e +86 no par; o parágrafo de regressões de segurança compara só com `robust`; `paired-*.json` e `m10_stats.py compare` usam a métrica de recuperação, por isso +99 U aparece como −21 pp. Só a tabela de regressões do dossiê o mostra em U.
- A regressão limita-se ao início em 0 s: um degrau do GNSS a 6, 10 ou 14 s dá 51/60 R a B+ com isolamento correto, contra 60/60 U de `guarded` a 5 m. É o que a F5 pré-registada (não implementada) mostraria.

Recomendação: aceitar o limite de observabilidade como limitação explícita, nunca como "resolvido", e mostrar a regressão em U contra `guarded` e `robust` em todos os agregados.

## Potência da P4

Revisão estatística independente, no mesmo dia: a P4 só passa se o McNemar rejeitar e a diferença agregada observada for pelo menos 3 pp. `mcnemar_power` em `spikes/m10-nav-feasibility/power_thresholds.py` conta só o McNemar. Com as duas condições (discordância 3,5 % contra 0,5 %), a potência com 600 pares é 0,53, não 0,90; com 300 pares efetivos, 0,45. Com a alternativa igual à margem, o critério de efeito sozinho falha cerca de metade das vezes. Corrigir exige uma decisão do proprietário: baixar o critério de efeito ou desenhar para uma alternativa maior.

## Parâmetros sem derivação documentada

- Sem menção no documento de desenho: `radar_lever_sigma_m`, `monitor_radar_gain`, `suspect_after_s`, `exclude_after_s`, `vote_threshold_m`.
- Mencionados sem derivação: `accel_process_sigma_mps2` (0,1, cinco vezes os 0,02 da IMU), `bias_prior_sigma_mps2` (0,3 para um intervalo injetado de 0,05 a 0,5), `monitor_gnss_gain`, `n_in_cycles`, `t_hold_s`, `t_max_s`, `t_safe_s`, `h_commit_m` e os AL ("incerta, a rever com varrimento de sensibilidade", sem varrimento).
- Afinados nas mesmas sementes de desenvolvimento: `cusum_k` e `cusum_h` (em parte), `suspect_cusum_fraction`, `bias_walk_sigma_mps2_per_sqrt_s`, `gnss_readmission_epochs`.
- Constantes do código cobertas só pelo `source_sha256`: `RATE_BAD` 4, `RATE_OK` 3, `ISOLATION_WINDOW_S`, `CONSISTENCY_SIGMA`, `COLD_FLAG_S`, `SUSPECT_CLEAR_S`, `ANCHOR_MARGIN_S`, `GNSS_HISTORY`, `GNSS_WINDOW`, `SLOPE_WINDOW`, `RING`, `SNAPS` e os fatores h/2, h/4, 2h, início menos 1 s e 0,25 na inflação de vz.

## Testes refutáveis antes do congelamento

Todos em sementes de desenvolvimento.

1. Grelha de rampas coerentes: magnitude {0,3, 0,5} m/s × início {3 a 6 s em passos de 0,25 s, 8, 12}. Passa se a taxa de isolamento errado não exceder o limite declarado e houver 0 falhas de alerta `hv`. Hoje: 10 a 31 % e 186.
2. O varrimento de início regista as falhas de alerta dos três canais.
3. Comparação por magnitude: na faixa de 0,2 a 0,8 m/s, U de B+ ≤ U de B + 2. Hoje 12 contra 6, e 64 contra 6 a 0,5 m/s.
4. Perseguição limitada, emparelhada: não converte nenhum R ou T em U na F3. Hoje 5 por célula.
5. Perseguição limitada com início tardio: para inícios de 12 s ou mais, U da variante não excede o de B+ aprovado nem o de `robust`. Hoje 31 contra 15 e 22.
6. As duas células de pares `gnss_dropout` passam a ser uma só em todos os agregados, ou são declaradas idênticas.
7. PL_v recalculado a partir do ruído do caso, substituindo "≈ 2 m"; dizer se C usaria uma estatística de separação.
8. Semântica de `detector_flag`: manter o histórico de implicação, ou emendar o texto da 8.3 para "estado atual".
9. Paridade com ruído real 1,5 vezes o modelado: 0 isolamentos errados nas células sem falha.
10. Janela da ignição: falhas de taxa com início a ±0,5 s da ignição; o isolamento errado não pode ser maior do que fora dela. A rampa de 0,5 m/s falha hoje (31 % contra 10 a 14 %).
11. F5 implementada (`altimeter_drift` e varrimentos de início de `gnss_bias` e `altimeter_bias`) ou retirada por emenda escrita.
12. Rastreabilidade: os parâmetros e constantes acima passam para `NavParams` ou ficam no manifesto com uma linha de derivação.
13. P1, P2, P4 e a decisão de Holm sobre a família primária implementadas em código revisto, com a potência da P4 calculada para a regra registada.

## Estado

Nada disto foi corrigido no estimador. As decisões A e C precisam de uma emenda do desenho e de nova evidência de desenvolvimento antes de qualquer proposta de congelamento. B e D podem ser aceites como estão escritas acima. A aceitação, o congelamento e o acesso às sementes de avaliação continuam com o proprietário.

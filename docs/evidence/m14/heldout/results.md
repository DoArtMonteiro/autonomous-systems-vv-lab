# Resultados do benchmark M14: divisão `heldout`

Orçamento de 200 avaliações por repetição, 30 repetições por estratégia. Gerado por `scripts/m14_benchmark.py`; não editar à mão.

## H1-ground-stop-actuator-delay

Referência exaustiva: 700 violações em 2916 avaliações (prevalência 0.2401, IC 95 % 0.2246 a 0.2560). Propriedades de referência: contract:command_applied, contract:command_resolution, contract:stop_response. Paridade com a linha de comandos: aprovada (9 casos, 0 diferenças).

| Estratégia | Repetições com violação | Mediana até à 1.ª violação | Revocação média de propriedades | Desvio mínimo mediano | Recalculada |
| --- | --- | --- | --- | --- | --- |
| random | 30/30 | 3.0 | 1.00 | 0.301 | sim |
| halton | 30/30 | 3.0 | 1.00 | 0.302 | sim |
| extremes | 30/30 | 7.0 | 1.00 | 0.302 | sim |
| adaptive | 30/30 | 4.5 | 1.00 | 0.301 | sim |

Cantos e centro (9 avaliações) sem violação em 0 de 30 repetições.

## H2-ground-overshoot-actuator-loss

Referência exaustiva: 412 violações em 676 avaliações (prevalência 0.6095, IC 95 % 0.5715 a 0.6464). Propriedades de referência: contract:command_applied. Paridade com a linha de comandos: aprovada (8 casos, 0 diferenças).

| Estratégia | Repetições com violação | Mediana até à 1.ª violação | Revocação média de propriedades | Desvio mínimo mediano | Recalculada |
| --- | --- | --- | --- | --- | --- |
| random | 30/30 | 1.0 | 1.00 | 0.059 | sim |
| halton | 30/30 | 2.0 | 1.00 | 0.061 | sim |
| extremes | 30/30 | 3.0 | 1.00 | 0.055 | sim |
| adaptive | 30/30 | 1.0 | 1.00 | 0.057 | sim |

Cantos e centro (5 avaliações) sem violação em 0 de 30 repetições.

## H3-rocket-gnss-bias

Referência exaustiva: 512 violações em 900 avaliações (prevalência 0.5689, IC 95 % 0.5358 a 0.6015). Propriedades de referência: invariant:S5_no_powered_ascent, outcome:hard_landing, requirement:R1_vertical_speed, requirement:R2_horizontal_speed, requirement:R3_tilt, requirement:R5_position. Paridade com a linha de comandos: aprovada (8 casos, 0 diferenças).
Só a pesquisa encontrou: requirement:R3_tilt.

| Estratégia | Repetições com violação | Mediana até à 1.ª violação | Revocação média de propriedades | Desvio mínimo mediano | Recalculada |
| --- | --- | --- | --- | --- | --- |
| random | 30/30 | 1.0 | 0.83 | 0.233 | sim |
| halton | 30/30 | 1.0 | 0.83 | 0.252 | sim |
| extremes | 30/30 | 2.0 | 0.83 | 0.223 | sim |
| adaptive | 30/30 | 1.0 | 0.84 | 0.251 | sim |

Cantos e centro (5 avaliações) sem violação em 0 de 30 repetições.

## H4-rocket-imu-accel-bias

Referência exaustiva: 2 violações em 900 avaliações (prevalência 0.0022, IC 95 % 0.0003 a 0.0080). Propriedades de referência: outcome:hard_landing, requirement:R1_vertical_speed, requirement:R2_horizontal_speed, requirement:R5_position. Paridade com a linha de comandos: aprovada (8 casos, 0 diferenças).
Só a pesquisa encontrou: requirement:R1_vertical_speed, requirement:R5_position.

| Estratégia | Repetições com violação | Mediana até à 1.ª violação | Revocação média de propriedades | Desvio mínimo mediano | Recalculada |
| --- | --- | --- | --- | --- | --- |
| random | 30/30 | 10.5 | 0.54 | 0.000 | sim |
| halton | 30/30 | 13.0 | 0.54 | 0.000 | sim |
| extremes | 30/30 | 17.5 | 0.56 | 0.000 | sim |
| adaptive | 30/30 | 17.0 | 0.63 | 0.000 | sim |

Cantos e centro (5 avaliações) sem violação em 22 de 30 repetições.

## Análise primária (pré-registada)

| Problema | Estado | p (Mann-Whitney) | p Holm | Mediana controlo menos tratamento [IC 95 %] |
| --- | --- | --- | --- | --- |
| H1-ground-stop-actuator-delay | eligible | 0.0360 | 0.1439 | -1.5 [-4.5; 1.0] |
| H2-ground-overshoot-actuator-loss | eligible | 0.9361 | 1.0000 | 0.0 [-0.5; 0.5] |
| H3-rocket-gnss-bias | eligible | 0.9671 | 1.0000 | 0.0 [-1.0; 1.0] |
| H4-rocket-imu-accel-bias | eligible | 0.1664 | 0.4991 | -6.5 [-25.0; 4.0] |

Alegação de generalização (adaptive contra random): **not supported** (0 melhores, 0 piores, 4 elegíveis).

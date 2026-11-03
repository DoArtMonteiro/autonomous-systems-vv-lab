# Resultados do benchmark M14: divisão `development`

Orçamento de 200 avaliações por repetição, 30 repetições por estratégia. Gerado por `scripts/m14_benchmark.py`; não editar à mão.

## D1-ground-zone-sensors

Referência exaustiva: 2295 violações em 2916 avaliações (prevalência 0.7870, IC 95 % 0.7717 a 0.8018). Propriedades de referência: contract:fallback_response, contract:restricted_zone_clear, invariant:restricted_zone. Paridade com a linha de comandos: aprovada (9 casos, 0 diferenças).
Só a pesquisa encontrou: contract:fallback_response.

| Estratégia | Repetições com violação | Mediana até à 1.ª violação | Revocação média de propriedades | Desvio mínimo mediano | Recalculada |
| --- | --- | --- | --- | --- | --- |
| random | 30/30 | 1.0 | 0.78 | 0.060 | sim |
| halton | 30/30 | 1.0 | 0.79 | 0.073 | sim |
| extremes | 30/30 | 2.0 | 0.80 | 0.089 | sim |
| adaptive | 30/30 | 1.0 | 0.76 | 0.043 | sim |

Cantos e centro (9 avaliações) sem violação em 0 de 30 repetições.

## D2-rocket-thrust-loss

Referência exaustiva: 12 violações em 900 avaliações (prevalência 0.0133, IC 95 % 0.0069 a 0.0232). Propriedades de referência: outcome:hard_landing, requirement:R1_vertical_speed, requirement:R2_horizontal_speed, requirement:R5_position. Paridade com a linha de comandos: aprovada (8 casos, 0 diferenças).
Só a pesquisa encontrou: requirement:R5_position.

| Estratégia | Repetições com violação | Mediana até à 1.ª violação | Revocação média de propriedades | Desvio mínimo mediano | Recalculada |
| --- | --- | --- | --- | --- | --- |
| random | 30/30 | 14.0 | 0.65 | 0.128 | sim |
| halton | 30/30 | 6.0 | 0.70 | 0.535 | sim |
| extremes | 30/30 | 9.0 | 0.66 | 0.668 | sim |
| adaptive | 30/30 | 18.0 | 0.68 | 0.306 | sim |

Cantos e centro (5 avaliações) sem violação em 20 de 30 repetições.

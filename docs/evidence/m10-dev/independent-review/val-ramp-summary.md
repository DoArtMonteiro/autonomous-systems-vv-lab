# Campanha M10 (resumo gerado)

Comando: `python scripts/m10_campaign.py --binary <vv-rocket> --seeds 5000-5099 --scenarios gnss_coherent_ramp,altimeter_stuck,altimeter_delay,altimeter_outliers --arms m10_b,m10_b_plus --jobs 8 --keep-sample 0 --keep-failures 0 --output-root <saída>/val-ramp`
Máquina: Windows-11-10.0.26300-SP0; AMD64 Family 25 Model 97 Stepping 2, AuthenticAMD; Python 3.14.6; duração 11.0 s; execuções 800.
Sementes: desenvolvimento (5000 a 5099). Avaliação: não.
Reprodução: 0 de 0 verificadas.

| Célula | Braço | n | Recuperou (IC 95%) | R / T / U | I1v | Declaração aplicável | Atraso mediano (s) | Degradações espúrias | NEES |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| altimeter_stuck | m10_b | 100 | 94 (0.87 a 0.98) | 94 / 0 / 6 | 0 | 0 | 0.01 | 0 | 6.26 |
| altimeter_stuck | m10_b_plus | 100 | 91 (0.84 a 0.96) | 91 / 3 / 6 | 0 | 2 | 0.01 | 1 | 255836.70 |
| altimeter_delay | m10_b | 100 | 82 (0.73 a 0.89) | 82 / 0 / 18 | 0 | 0 | 0.00 | 0 | 7.32 |
| altimeter_delay | m10_b_plus | 100 | 78 (0.69 a 0.86) | 78 / 4 / 18 | 0 | 1 | 0.00 | 0 | 17350.30 |
| altimeter_outliers | m10_b | 100 | 94 (0.87 a 0.98) | 94 / 0 / 6 | 0 | 0 | 0.00 | 0 | 6.57 |
| altimeter_outliers | m10_b_plus | 100 | 94 (0.87 a 0.98) | 94 / 0 / 6 | 0 | 0 | 0.00 | 0 | 6.55 |
| gnss_coherent_ramp | m10_b | 100 | 20 (0.13 a 0.29) | 20 / 69 / 11 | 0 | 3 | 0.04 | 0 | 603.87 |
| gnss_coherent_ramp | m10_b_plus | 100 | 57 (0.47 a 0.67) | 57 / 29 / 14 | 0 | 2 | 0.05 | 0 | 652.32 |

## Avaliação global de segurança

| Braço | n | R | T | U | U (IC 95%) |
| --- | --- | --- | --- | --- | --- |
| m10_b | 400 | 290 | 69 | 41 | 0.075 a 0.137 |
| m10_b_plus | 400 | 320 | 36 | 44 | 0.081 a 0.145 |

## Pares emparelhados contra `guarded`

| Célula | Braço | pares | só guarded | só braço | diferença |
| --- | --- | --- | --- | --- | --- |

Resultados condicionais às dispersões e às gamas assumidas, num modelo idealizado. Com sementes de desenvolvimento ou de teste, não são uma avaliação do M10.

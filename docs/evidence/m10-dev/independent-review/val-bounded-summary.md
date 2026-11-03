# Campanha M10 (resumo gerado)

Comando: `python scripts/m10_campaign.py --binary <vv-rocket> --template <m10-nominal.json com controller.nav.bounded_chase_when_untrusted = true> --seeds 5000-5099 --scenarios F3 --arms m10_b_plus --jobs 8 --keep-sample 0 --keep-failures 0 --output-root <saída>/val-bounded`
Máquina: Windows-11-10.0.26300-SP0; AMD64 Family 25 Model 97 Stepping 2, AuthenticAMD; Python 3.14.6; duração 7.3 s; execuções 600.
Sementes: desenvolvimento (5000 a 5099). Avaliação: não.
Reprodução: 0 de 0 verificadas.

| Célula | Braço | n | Recuperou (IC 95%) | R / T / U | I1v | Declaração aplicável | Atraso mediano (s) | Degradações espúrias | NEES |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pair_altimeter_bias+gnss_dropout | m10_b_plus | 100 | 85 (0.76 a 0.91) | 85 / 0 / 15 | 0 | 3 | 0.00 | 0 | 4.68 |
| pair_altimeter_bias_low+gnss_dropout | m10_b_plus | 100 | 85 (0.76 a 0.91) | 85 / 0 / 15 | 0 | 3 | 0.00 | 0 | 4.68 |
| pair_gnss_bias+altimeter_dropout | m10_b_plus | 100 | 0 (0.00 a 0.04) | 0 / 0 / 100 | 0 | 100 | 0.00 | 0 | 210260.36 |
| pair_altimeter_bias±+imu_accel_bias | m10_b_plus | 100 | 89 (0.81 a 0.94) | 89 / 0 / 11 | 0 | 0 | 0.00 | 0 | 5.22 |
| pair_gnss_bias_low+imu_accel_bias | m10_b_plus | 100 | 0 (0.00 a 0.04) | 0 / 0 / 100 | 0 | 100 | 0.00 | 0 | 219541.61 |
| pair_altimeter_bias±+gnss_bias± | m10_b_plus | 100 | 0 (0.00 a 0.04) | 0 / 0 / 100 | 1 | 100 | 0.00 | 0 | 256232.74 |

## Avaliação global de segurança

| Braço | n | R | T | U | U (IC 95%) |
| --- | --- | --- | --- | --- | --- |
| m10_b_plus | 600 | 259 | 0 | 341 | 0.528 a 0.608 |

## Pares emparelhados contra `guarded`

| Célula | Braço | pares | só guarded | só braço | diferença |
| --- | --- | --- | --- | --- | --- |

Resultados condicionais às dispersões e às gamas assumidas, num modelo idealizado. Com sementes de desenvolvimento ou de teste, não são uma avaliação do M10.

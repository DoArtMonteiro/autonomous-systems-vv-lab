# Resultados da reformulação do M10 (gerado por `scripts/m10_redesign_analysis.py`)

Binário: `['918479ef364e02800dfc2fda349f948f09ae80b5ac425a572053c24dd0126713']`; um só binário: True; sementes de desenvolvimento apenas: True; contagens da matriz: True.

**V1 (S1 a S7, sem cláusula de paragem disparada): False. V2 (limites contra `robust` e `guarded`): False. Avançar: False.**

| Critério | Cumprido |
| --- | --- |
| S1 | False |
| S2 | False |
| S3 | True |
| S4 | True |
| S5 | False |
| S6 | True |
| S7 | True |

Cláusulas de paragem disparadas: {"clause1_hv": true, "clause2_U": false, "clause3_noise": true}

## Cláusula 1 (falhas hv)
`{"B+G": {"G1": 4, "M1": 0, "M3": 0, "G1_noise": 2, "M4": 0}, "B": {"G1": 0, "M1": 0, "M3": 0, "G1_noise": 0, "M4": 0}, "B+": {"G1": 60, "M1": 1, "M3": 0, "G1_noise": 5, "M4": 0}, "ok": false, "B_has_hv_rule_miscalibrated": false}`

## Cláusula 2 (U de B+G contra U de B)
| Magnitude | unidade de 80: U B / B+ / B+G | vácua | ok | grelha: U B / B+ / B+G (limite 16) | vácua | ok |
| --- | --- | --- | --- | --- | --- | --- |
| 0.2 | 66 / 79 / 65 | False | True | 499 / 636 / 495 | False | True |
| 0.3 | 80 / 80 / 80 | True | True | 640 / 639 / 639 | True | True |
| 0.5 | 0 / 67 / 1 | False | True | 54 / 544 / 47 | False | True |
| 0.8 | 0 / 3 / 0 | False | True | 36 / 41 / 7 | False | True |

Estrato de 18 sementes: `{"classes": {"B": {"R": 3, "T": 9, "U": 6}, "B+": {"R": 3, "T": 3, "U": 12}, "B+G": {"R": 6, "T": 5, "U": 7}}, "ok": true}`

## S2, S4, S6c, cláusula 3
- S2: `{"n": 1280, "wrong_B+": 110, "wrong_B+G": 33, "cp_upper_B+G": 0.036, "reduction": 0.7, "validity_B+_at_least_60": true, "ok": false}`
- S4: `{"windows": {"B+": {"inside_n": 639, "inside_wrong": 34, "outside_n": 1921, "outside_wrong": 89, "no_ignition_runs": 0, "rate_inside": 0.053208137715179966, "rate_outside": 0.0463300364393545}, "B+G": {"inside_n": 644, "inside_wrong": 7, "outside_n": 1916, "outside_wrong": 33, "no_ignition_runs": 0, "rate_inside": 0.010869565217391304, "rate_outside": 0.01722338204592902}}, "ok": true}`
- S6c: `{"R_B": 88, "R_B+": 285, "R_B+G": 293, "ok": true}`
- clause3: `{"M3_B+G_wrong": 26, "M3_n": 2400, "M3_cp_upper": 0.0158, "G1noise_B+G_wrong": 23, "G1noise_n": 640, "G1noise_cp_upper": 0.0534, "ok": false}`

## S6 (M1) e S7 por célula
`{"altimeter_stuck": {"R_B+": 91, "R_B+G": 94, "ok": true}, "altimeter_delay": {"R_B+": 78, "R_B+G": 89, "ok": true}, "gnss_coherent_ramp": {"R_B+": 57, "R_B+G": 61, "ok": true}, "correct_isolations": {"B+": 281, "B+G": 282, "ok": true}}`

| Célula | U B+ | U B+G | R B+ | R B+G | inv B+ | inv B+G | S7 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| nominal | 6 | 6 | 94 | 94 | 0 | 0 | True |
| thrust_loss | 12 | 12 | 88 | 88 | 0 | 0 | True |
| ignition_delay | 18 | 18 | 82 | 82 | 0 | 0 | True |
| gimbal_stuck | 8 | 8 | 92 | 92 | 0 | 0 | True |
| altimeter_bias | 6 | 6 | 94 | 94 | 0 | 0 | True |
| altimeter_dropout | 6 | 6 | 94 | 94 | 0 | 0 | True |
| gnss_dropout | 8 | 8 | 92 | 92 | 0 | 0 | True |
| gnss_bias | 100 | 100 | 0 | 0 | 0 | 0 | True |
| imu_accel_bias | 11 | 11 | 89 | 89 | 0 | 0 | True |
| altimeter_bias_low | 6 | 6 | 94 | 94 | 0 | 0 | True |
| gnss_bias_low | 100 | 100 | 0 | 0 | 0 | 0 | True |
| altimeter_stuck | 6 | 6 | 91 | 94 | 0 | 0 | True |
| altimeter_delay | 18 | 10 | 78 | 89 | 0 | 0 | True |
| altimeter_outliers | 6 | 6 | 94 | 94 | 0 | 0 | True |
| gnss_horizontal_bias_t0 | 2 | 2 | 7 | 7 | 0 | 0 | True |
| gnss_horizontal_bias | 3 | 3 | 15 | 15 | 3 | 3 | True |
| gnss_coherent_ramp | 14 | 8 | 57 | 61 | 0 | 0 | True |
| imu_accel_drift | 18 | 18 | 74 | 74 | 0 | 0 | True |
| pair_altimeter_bias+gnss_dropout | 27 | 27 | 41 | 41 | 2 | 2 | True |
| pair_gnss_bias+altimeter_dropout | 100 | 100 | 0 | 0 | 0 | 0 | True |
| pair_altimeter_bias±+imu_accel_bias | 11 | 11 | 89 | 89 | 0 | 0 | True |
| pair_gnss_bias_low+imu_accel_bias | 100 | 100 | 0 | 0 | 0 | 0 | True |
| pair_altimeter_bias±+gnss_bias± | 100 | 100 | 0 | 0 | 0 | 0 | True |

Diferenças semente a semente (B+G contra B+) nas células previstas idênticas: `{"pair_altimeter_bias+gnss_dropout": 0, "pair_altimeter_bias_low+gnss_dropout": 0, "pair_gnss_bias+altimeter_dropout": 0, "pair_altimeter_bias\u00b1+imu_accel_bias": 0, "pair_gnss_bias_low+imu_accel_bias": 0, "pair_altimeter_bias\u00b1+gnss_bias\u00b1": 0, "altimeter_bias": 0, "altimeter_bias_low": 0, "gnss_bias": 0, "gnss_bias_low": 0}`

## V2: regressões materiais contra `robust` e `guarded` (U acima em mais de 2, ou 5 ou mais R perdidas)
| Célula | base | U base | U B+G | R base | R B+G | material |
| --- | --- | --- | --- | --- | --- | --- |
| nominal | robust | 6 | 6 | 94 | 94 | False |
| nominal | guarded | 6 | 6 | 94 | 94 | False |
| thrust_loss | robust | 13 | 12 | 87 | 88 | False |
| thrust_loss | guarded | 13 | 12 | 87 | 88 | False |
| ignition_delay | robust | 19 | 18 | 81 | 82 | False |
| ignition_delay | guarded | 19 | 18 | 81 | 82 | False |
| gimbal_stuck | robust | 10 | 8 | 90 | 92 | False |
| gimbal_stuck | guarded | 10 | 8 | 90 | 92 | False |
| altimeter_bias | robust | 8 | 6 | 92 | 94 | False |
| altimeter_bias | guarded | 8 | 6 | 92 | 94 | False |
| altimeter_dropout | robust | 6 | 6 | 94 | 94 | False |
| altimeter_dropout | guarded | 6 | 6 | 94 | 94 | False |
| gnss_dropout | robust | 7 | 8 | 93 | 92 | False |
| gnss_dropout | guarded | 7 | 8 | 93 | 92 | False |
| gnss_bias | robust | 100 | 100 | 0 | 0 | False |
| gnss_bias | guarded | 1 | 100 | 21 | 0 | True |
| imu_accel_bias | robust | 11 | 11 | 89 | 89 | False |
| imu_accel_bias | guarded | 11 | 11 | 89 | 89 | False |
| altimeter_bias_low | robust | 8 | 6 | 92 | 94 | False |
| altimeter_bias_low | guarded | 100 | 6 | 0 | 94 | False |
| gnss_bias_low | robust | 100 | 100 | 0 | 0 | False |
| gnss_bias_low | guarded | 100 | 100 | 0 | 0 | False |
| altimeter_stuck | robust | 6 | 6 | 94 | 94 | False |
| altimeter_stuck | guarded | 6 | 6 | 94 | 94 | False |
| altimeter_delay | robust | 99 | 10 | 1 | 89 | False |
| altimeter_delay | guarded | 99 | 10 | 1 | 89 | False |
| altimeter_outliers | robust | 7 | 6 | 93 | 94 | False |
| altimeter_outliers | guarded | 7 | 6 | 93 | 94 | False |
| gnss_horizontal_bias_t0 | robust | 2 | 2 | 6 | 7 | False |
| gnss_horizontal_bias_t0 | guarded | 2 | 2 | 6 | 7 | False |
| gnss_horizontal_bias | robust | 15 | 3 | 10 | 15 | False |
| gnss_horizontal_bias | guarded | 15 | 3 | 10 | 15 | False |
| gnss_coherent_ramp | robust | 98 | 8 | 2 | 61 | False |
| gnss_coherent_ramp | guarded | 98 | 8 | 2 | 61 | False |
| imu_accel_drift | robust | 42 | 18 | 58 | 74 | False |
| imu_accel_drift | guarded | 42 | 18 | 58 | 74 | False |
| pair_altimeter_bias+gnss_dropout | robust | 8 | 27 | 92 | 41 | True |
| pair_altimeter_bias+gnss_dropout | guarded | 8 | 27 | 92 | 41 | True |
| pair_gnss_bias+altimeter_dropout | robust | 100 | 100 | 0 | 0 | False |
| pair_gnss_bias+altimeter_dropout | guarded | 14 | 100 | 19 | 0 | True |
| pair_altimeter_bias±+imu_accel_bias | robust | 39 | 11 | 61 | 89 | False |
| pair_altimeter_bias±+imu_accel_bias | guarded | 69 | 11 | 31 | 89 | False |
| pair_gnss_bias_low+imu_accel_bias | robust | 100 | 100 | 0 | 0 | False |
| pair_gnss_bias_low+imu_accel_bias | guarded | 100 | 100 | 0 | 0 | False |
| pair_altimeter_bias±+gnss_bias± | robust | 100 | 100 | 0 | 0 | False |
| pair_altimeter_bias±+gnss_bias± | guarded | 100 | 100 | 0 | 0 | False |

## Tabelas
- U_decomposition_0.5: `{"B+": {"U": 544, "iso": {"none": 473, "wrong": 71}, "fail": {"R1,R5": 421, "R1": 71, "R1,R2": 10, "R1,R2,R5": 42}}, "B+G": {"U": 47, "iso": {"none": 41, "wrong": 6}, "fail": {"R5": 41, "R1,R2,R5": 3, "R1": 2, "R1,R5": 1}}}`
- gate_streaks: `{"G1": {"runs": 2560, "max_streak_max": 731, "max_streak_median": 1, "max_active_max": 1083, "max_active_median": 857, "runs_with_rejections": 2557, "runs_streak_open_at_end": 820}, "G1_noise": {"runs": 640, "max_streak_max": 810, "max_streak_median": 2, "max_active_max": 1106, "max_active_median": 896, "runs_with_rejections": 640, "runs_streak_open_at_end": 349}, "M4": {"runs": 1900, "max_streak_max": 1060, "max_streak_median": 0, "max_active_max": 1080, "max_active_median": 21, "runs_with_rejections": 737, "runs_streak_open_at_end": 5}}`
- gate_streaks_campaign: `{"M1": {"nominal": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "thrust_loss": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "ignition_delay": {"max_streak_max": 1, "max_streak_median": 0, "runs_with_rejections": 3, "runs_streak_open_at_end": 0, "runs": 100}, "gimbal_stuck": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "altimeter_bias": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "altimeter_dropout": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "gnss_dropout": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "gnss_bias": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "imu_accel_bias": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "altimeter_bias_low": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "gnss_bias_low": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "altimeter_stuck": {"max_streak_max": 9, "max_streak_median": 2, "runs_with_rejections": 80, "runs_streak_open_at_end": 0, "runs": 100}, "altimeter_delay": {"max_streak_max": 1006, "max_streak_median": 2, "runs_with_rejections": 97, "runs_streak_open_at_end": 1, "runs": 100}, "altimeter_outliers": {"max_streak_max": 433, "max_streak_median": 0, "runs_with_rejections": 40, "runs_streak_open_at_end": 0, "runs": 100}, "gnss_horizontal_bias_t0": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "gnss_horizontal_bias": {"max_streak_max": 1, "max_streak_median": 1, "runs_with_rejections": 99, "runs_streak_open_at_end": 1, "runs": 100}, "gnss_coherent_ramp": {"max_streak_max": 682, "max_streak_median": 1, "runs_with_rejections": 97, "runs_streak_open_at_end": 6, "runs": 100}, "imu_accel_drift": {"max_streak_max": 1, "max_streak_median": 0, "runs_with_rejections": 2, "runs_streak_open_at_end": 0, "runs": 100}, "pair_altimeter_bias+gnss_dropout": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "pair_altimeter_bias_low+gnss_dropout": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "pair_gnss_bias+altimeter_dropout": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "pair_altimeter_bias\u00b1+imu_accel_bias": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "pair_gnss_bias_low+imu_accel_bias": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "pair_altimeter_bias\u00b1+gnss_bias\u00b1": {"max_streak_max": 1, "max_streak_median": 0, "runs_with_rejections": 2, "runs_streak_open_at_end": 0, "runs": 100}}, "M3": {"nominal": {"max_streak_max": 1, "max_streak_median": 1, "runs_with_rejections": 100, "runs_streak_open_at_end": 0, "runs": 100}, "thrust_loss": {"max_streak_max": 2, "max_streak_median": 1, "runs_with_rejections": 100, "runs_streak_open_at_end": 0, "runs": 100}, "ignition_delay": {"max_streak_max": 1, "max_streak_median": 1, "runs_with_rejections": 100, "runs_streak_open_at_end": 0, "runs": 100}, "gimbal_stuck": {"max_streak_max": 1, "max_streak_median": 1, "runs_with_rejections": 100, "runs_streak_open_at_end": 0, "runs": 100}, "altimeter_bias": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "altimeter_dropout": {"max_streak_max": 1, "max_streak_median": 1, "runs_with_rejections": 97, "runs_streak_open_at_end": 0, "runs": 100}, "gnss_dropout": {"max_streak_max": 1, "max_streak_median": 1, "runs_with_rejections": 94, "runs_streak_open_at_end": 0, "runs": 100}, "gnss_bias": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "imu_accel_bias": {"max_streak_max": 1, "max_streak_median": 1, "runs_with_rejections": 100, "runs_streak_open_at_end": 0, "runs": 100}, "altimeter_bias_low": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "gnss_bias_low": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "altimeter_stuck": {"max_streak_max": 476, "max_streak_median": 3, "runs_with_rejections": 100, "runs_streak_open_at_end": 0, "runs": 100}, "altimeter_delay": {"max_streak_max": 1046, "max_streak_median": 7, "runs_with_rejections": 100, "runs_streak_open_at_end": 2, "runs": 100}, "altimeter_outliers": {"max_streak_max": 1122, "max_streak_median": 1, "runs_with_rejections": 98, "runs_streak_open_at_end": 1, "runs": 100}, "gnss_horizontal_bias_t0": {"max_streak_max": 1, "max_streak_median": 1, "runs_with_rejections": 100, "runs_streak_open_at_end": 0, "runs": 100}, "gnss_horizontal_bias": {"max_streak_max": 2, "max_streak_median": 1, "runs_with_rejections": 100, "runs_streak_open_at_end": 10, "runs": 100}, "gnss_coherent_ramp": {"max_streak_max": 569, "max_streak_median": 1, "runs_with_rejections": 100, "runs_streak_open_at_end": 18, "runs": 100}, "imu_accel_drift": {"max_streak_max": 2, "max_streak_median": 1, "runs_with_rejections": 100, "runs_streak_open_at_end": 1, "runs": 100}, "pair_altimeter_bias+gnss_dropout": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "pair_altimeter_bias_low+gnss_dropout": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "pair_gnss_bias+altimeter_dropout": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "pair_altimeter_bias\u00b1+imu_accel_bias": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "pair_gnss_bias_low+imu_accel_bias": {"max_streak_max": 0, "max_streak_median": 0, "runs_with_rejections": 0, "runs_streak_open_at_end": 0, "runs": 100}, "pair_altimeter_bias\u00b1+gnss_bias\u00b1": {"max_streak_max": 1, "max_streak_median": 0, "runs_with_rejections": 4, "runs_streak_open_at_end": 1, "runs": 100}}}`
- M3: `{"B": {"n": 2400, "classes": {"R": 513, "T": 839, "U": 1048}, "wrong": 0, "hv": 0, "av": 1, "ap": 0}, "B+": {"n": 2400, "classes": {"R": 982, "T": 611, "U": 807}, "wrong": 46, "hv": 0, "av": 0, "ap": 0}, "B+G": {"n": 2400, "classes": {"R": 1018, "T": 690, "U": 692}, "wrong": 26, "hv": 0, "av": 0, "ap": 0}}`
- M3_wrong_by_cell: `{"B+": {"nominal": 4, "thrust_loss": 5, "ignition_delay": 3, "gimbal_stuck": 4, "altimeter_dropout": 4, "gnss_dropout": 4, "imu_accel_bias": 4, "altimeter_stuck": 2, "altimeter_delay": 1, "altimeter_outliers": 1, "gnss_horizontal_bias_t0": 4, "gnss_horizontal_bias": 3, "gnss_coherent_ramp": 3, "imu_accel_drift": 4}, "B+G": {"nominal": 2, "thrust_loss": 2, "ignition_delay": 2, "gimbal_stuck": 2, "altimeter_dropout": 2, "gnss_dropout": 2, "imu_accel_bias": 2, "altimeter_stuck": 1, "altimeter_delay": 1, "altimeter_outliers": 2, "gnss_horizontal_bias_t0": 2, "gnss_horizontal_bias": 2, "gnss_coherent_ramp": 2, "imu_accel_drift": 2}}`
- G1_noise: `{"B": {"n": 640, "classes": {"R": 34, "T": 286, "U": 320}, "wrong": 0, "hv": 0, "av": 0}, "B+": {"n": 640, "classes": {"R": 1, "T": 48, "U": 591}, "wrong": 71, "hv": 5, "av": 0}, "B+G": {"n": 640, "classes": {"R": 42, "T": 273, "U": 325}, "wrong": 23, "hv": 2, "av": 0}}`
- gnss_horizontal_bias_invariants: `{"B+": [[5084, "S2"], [5086, "S2"], [5093, "S2"]], "B+G": [[5084, "S2"], [5086, "S2"], [5093, "S2"]], "robust": [], "guarded": [], "B": [[5084, "S2"], [5086, "S2"]]}`

### G1 por braço e magnitude (completa e unidade de 80)
| Braço | m/s | R/T/U grelha | R/T/U unidade | isolamento errado | hv | av | ap |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B | 0.2 | 35/106/499 | 4/10/66 | 0 | 0 | 0 | 0 |
| B | 0.3 | 0/0/640 | 0/0/80 | 0 | 0 | 0 | 0 |
| B | 0.5 | 78/508/54 | 15/65/0 | 0 | 0 | 0 | 0 |
| B | 0.8 | 88/516/36 | 17/63/0 | 0 | 0 | 0 | 0 |
| B+ | 0.2 | 2/2/636 | 0/1/79 | 8 | 0 | 0 | 0 |
| B+ | 0.3 | 1/0/639 | 0/0/80 | 39 | 0 | 0 | 0 |
| B+ | 0.5 | 42/54/544 | 5/8/67 | 71 | 55 | 0 | 0 |
| B+ | 0.8 | 285/314/41 | 45/32/3 | 5 | 5 | 0 | 0 |
| B+G | 0.2 | 18/127/495 | 0/15/65 | 7 | 0 | 0 | 0 |
| B+G | 0.3 | 1/0/639 | 0/0/80 | 27 | 0 | 0 | 0 |
| B+G | 0.5 | 133/460/47 | 23/56/1 | 6 | 4 | 0 | 0 |
| B+G | 0.8 | 293/340/7 | 46/34/0 | 0 | 0 | 0 | 0 |
| robust | 0.2 | 45/0/595 | 3/0/77 | 0 | 0 | 0 | 0 |
| robust | 0.3 | 0/0/640 | 0/0/80 | 0 | 0 | 0 | 0 |
| robust | 0.5 | 0/0/640 | 0/0/80 | 0 | 0 | 0 | 0 |
| robust | 0.8 | 0/0/640 | 0/0/80 | 0 | 0 | 0 | 0 |
| guarded | 0.2 | 45/0/595 | 3/0/77 | 0 | 0 | 0 | 0 |
| guarded | 0.3 | 0/0/640 | 0/0/80 | 0 | 0 | 0 | 0 |
| guarded | 0.5 | 0/0/640 | 0/0/80 | 0 | 0 | 0 | 0 |
| guarded | 0.8 | 0/37/603 | 0/7/73 | 0 | 0 | 0 | 0 |

### M4 (varrimento de início)
| Braço e falha | R/T/U | errado | hv | av | pior início (R, início) |
| --- | --- | --- | --- | --- | --- |
| B|altimeter_delay | 360/0/20 | 0 | 0 | 0 | (18, 2.0) |
| B|altimeter_stuck | 380/0/0 | 0 | 0 | 0 | (20, 2.0) |
| B|gnss_coherent_ramp | 194/186/0 | 0 | 0 | 0 | (3, 2.0) |
| B|gnss_dropout | 380/0/0 | 0 | 0 | 0 | (20, 2.0) |
| B|imu_accel_drift | 369/0/11 | 0 | 0 | 0 | (17, 2.0) |
| B+|altimeter_delay | 372/0/8 | 0 | 0 | 0 | (15, 2.0) |
| B+|altimeter_stuck | 374/3/3 | 0 | 0 | 0 | (19, 2.0) |
| B+|gnss_coherent_ramp | 280/85/15 | 0 | 0 | 0 | (2, 2.0) |
| B+|gnss_dropout | 380/0/0 | 0 | 0 | 0 | (20, 2.0) |
| B+|imu_accel_drift | 375/0/5 | 0 | 0 | 0 | (18, 2.0) |
| B+G|altimeter_delay | 363/7/10 | 0 | 0 | 0 | (13, 2.0) |
| B+G|altimeter_stuck | 380/0/0 | 0 | 0 | 0 | (20, 2.0) |
| B+G|gnss_coherent_ramp | 283/97/0 | 0 | 0 | 0 | (2, 2.0) |
| B+G|gnss_dropout | 380/0/0 | 0 | 0 | 0 | (20, 2.0) |
| B+G|imu_accel_drift | 375/0/5 | 0 | 0 | 0 | (18, 2.0) |
| robust|altimeter_delay | 0/0/380 | 0 | 0 | 0 | (0, 2.0) |
| robust|altimeter_stuck | 379/0/1 | 0 | 0 | 0 | (19, 20.0) |
| robust|gnss_coherent_ramp | 14/0/366 | 0 | 0 | 0 | (0, 2.0) |
| robust|gnss_dropout | 380/0/0 | 0 | 0 | 0 | (20, 2.0) |
| robust|imu_accel_drift | 320/0/60 | 0 | 0 | 0 | (4, 2.0) |
| guarded|altimeter_delay | 0/0/380 | 0 | 0 | 0 | (0, 2.0) |
| guarded|altimeter_stuck | 379/0/1 | 0 | 0 | 0 | (19, 20.0) |
| guarded|gnss_coherent_ramp | 14/0/366 | 0 | 0 | 0 | (0, 2.0) |
| guarded|gnss_dropout | 380/0/0 | 0 | 0 | 0 | (20, 2.0) |
| guarded|imu_accel_drift | 320/0/60 | 0 | 0 | 0 | (4, 2.0) |

### M1 por célula (R/T/U; isolamento errado; hv)
| Célula | B | B+ | B+G | robust | guarded |
| --- | --- | --- | --- | --- | --- |
| nominal | 94/0/6 w0 h0 | 94/0/6 w0 h0 | 94/0/6 w0 h0 | 94/0/6 w0 h0 | 94/0/6 w0 h0 |
| thrust_loss | 88/0/12 w0 h0 | 88/0/12 w0 h0 | 88/0/12 w0 h0 | 87/0/13 w0 h0 | 87/0/13 w0 h0 |
| ignition_delay | 80/0/20 w0 h0 | 82/0/18 w0 h0 | 82/0/18 w0 h0 | 81/0/19 w0 h0 | 81/0/19 w0 h0 |
| gimbal_stuck | 92/0/8 w0 h0 | 92/0/8 w0 h0 | 92/0/8 w0 h0 | 90/0/10 w0 h0 | 90/0/10 w0 h0 |
| altimeter_bias | 94/0/6 w0 h0 | 94/0/6 w0 h0 | 94/0/6 w0 h0 | 92/0/8 w0 h0 | 92/0/8 w0 h0 |
| altimeter_dropout | 94/0/6 w0 h0 | 94/0/6 w0 h0 | 94/0/6 w0 h0 | 94/0/6 w0 h0 | 94/0/6 w0 h0 |
| gnss_dropout | 92/0/8 w0 h0 | 92/0/8 w0 h0 | 92/0/8 w0 h0 | 93/0/7 w0 h0 | 93/0/7 w0 h0 |
| gnss_bias | 0/0/100 w0 h0 | 0/0/100 w0 h0 | 0/0/100 w0 h0 | 0/0/100 w0 h0 | 21/78/1 w0 h0 |
| imu_accel_bias | 89/0/11 w0 h0 | 89/0/11 w0 h0 | 89/0/11 w0 h0 | 89/0/11 w0 h0 | 89/0/11 w0 h0 |
| altimeter_bias_low | 94/0/6 w0 h0 | 94/0/6 w0 h0 | 94/0/6 w0 h0 | 92/0/8 w0 h0 | 0/0/100 w0 h0 |
| gnss_bias_low | 0/0/100 w0 h0 | 0/0/100 w0 h0 | 0/0/100 w0 h0 | 0/0/100 w0 h0 | 0/0/100 w0 h0 |
| altimeter_stuck | 94/0/6 w0 h0 | 91/3/6 w0 h0 | 94/0/6 w0 h0 | 94/0/6 w0 h0 | 94/0/6 w0 h0 |
| altimeter_delay | 82/0/18 w0 h0 | 78/4/18 w0 h0 | 89/1/10 w0 h0 | 1/0/99 w0 h0 | 1/0/99 w0 h0 |
| altimeter_outliers | 94/0/6 w0 h0 | 94/0/6 w0 h0 | 94/0/6 w0 h0 | 93/0/7 w0 h0 | 93/0/7 w0 h0 |
| gnss_horizontal_bias_t0 | 7/91/2 w0 h0 | 7/91/2 w0 h0 | 7/91/2 w0 h0 | 6/92/2 w0 h0 | 6/92/2 w0 h0 |
| gnss_horizontal_bias | 15/83/2 w0 h0 | 15/82/3 w0 h0 | 15/82/3 w0 h0 | 10/75/15 w0 h0 | 10/75/15 w0 h0 |
| gnss_coherent_ramp | 20/69/11 w0 h0 | 57/29/14 w1 h1 | 61/31/8 w0 h0 | 2/0/98 w0 h0 | 2/0/98 w0 h0 |
| imu_accel_drift | 79/0/21 w0 h0 | 74/8/18 w0 h0 | 74/8/18 w0 h0 | 58/0/42 w0 h0 | 58/0/42 w0 h0 |
| pair_altimeter_bias+gnss_dropout | 41/32/27 w0 h0 | 41/32/27 w0 h0 | 41/32/27 w0 h0 | 92/0/8 w0 h0 | 92/0/8 w0 h0 |
| pair_altimeter_bias_low+gnss_dropout | 41/32/27 w0 h0 | 41/32/27 w0 h0 | 41/32/27 w0 h0 | 92/0/8 w0 h0 | 0/0/100 w0 h0 |
| pair_gnss_bias+altimeter_dropout | 0/0/100 w0 h0 | 0/0/100 w0 h0 | 0/0/100 w0 h0 | 0/0/100 w0 h0 | 19/67/14 w0 h0 |
| pair_altimeter_bias±+imu_accel_bias | 89/0/11 w0 h0 | 89/0/11 w0 h0 | 89/0/11 w0 h0 | 61/0/39 w0 h0 | 31/0/69 w0 h0 |
| pair_gnss_bias_low+imu_accel_bias | 0/0/100 w0 h0 | 0/0/100 w0 h0 | 0/0/100 w0 h0 | 0/0/100 w0 h0 | 0/0/100 w0 h0 |
| pair_altimeter_bias±+gnss_bias± | 0/0/100 w0 h0 | 0/0/100 w0 h0 | 0/0/100 w0 h0 | 0/0/100 w0 h0 | 0/0/100 w0 h0 |

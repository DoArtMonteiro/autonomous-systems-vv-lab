# Fragilidade de pressupostos do M14 (exploratório)

Cada nível corre 100 sementes de desenvolvimento (32000 a 32099). Veredicto por nível com limites unilaterais de Clopper-Pearson a 95 % contra 0.95. Gerado por `scripts/m14_fragility.py`; não editar à mão.

## F1: ruído GPS

Alegação: Corredor junto à zona: o veículo não viola a segurança, com probabilidade de pelo menos 0.95. Caso `exec/cases/m14/ground-zone-corridor.json`. Recalculado: sim.
Margem: último nível que se mantém 0 mm; primeiro refutado 1 mm. Não monótona: sim.

| ruído GPS (mm) | Passam | Limite inferior | Limite superior | Veredicto |
| --- | --- | --- | --- | --- |
| 0 | 100/100 | 0.970 | 1.000 | holds |
| 1 | 61/100 | 0.523 | 0.692 | refuted |
| 2 | 30/100 | 0.225 | 0.384 | refuted |
| 3 | 23/100 | 0.163 | 0.310 | refuted |
| 4 | 26/100 | 0.189 | 0.342 | refuted |
| 5 | 16/100 | 0.103 | 0.233 | refuted |
| 6 | 20/100 | 0.137 | 0.277 | refuted |
| 7 | 16/100 | 0.103 | 0.233 | refuted |
| 8 | 19/100 | 0.128 | 0.266 | refuted |
| 9 | 12/100 | 0.071 | 0.187 | refuted |
| 10 | 21/100 | 0.145 | 0.288 | refuted |

## F2: atraso máximo de observação

Alegação: Corredor junto à zona: o veículo não viola a segurança, com probabilidade de pelo menos 0.95. Caso `exec/cases/m14/ground-zone-corridor.json`. Recalculado: sim.
Margem: último nível que se mantém 1 ticks; primeiro refutado 2 ticks. Não monótona: não.

| atraso máximo de observação (ticks) | Passam | Limite inferior | Limite superior | Veredicto |
| --- | --- | --- | --- | --- |
| 0 | 100/100 | 0.970 | 1.000 | holds |
| 1 | 100/100 | 0.970 | 1.000 | holds |
| 2 | 71/100 | 0.626 | 0.784 | refuted |
| 3 | 71/100 | 0.626 | 0.784 | refuted |

## F3: ruído GPS

Alegação: Paragem nominal: o veículo não viola a segurança, com probabilidade de pelo menos 0.95. Caso `exec/cases/m14/ground-nominal-stop.json`. Recalculado: sim.
Margem: último nível que se mantém 200 mm; primeiro refutado None mm. Não monótona: não.

| ruído GPS (mm) | Passam | Limite inferior | Limite superior | Veredicto |
| --- | --- | --- | --- | --- |
| 0 | 100/100 | 0.970 | 1.000 | holds |
| 20 | 100/100 | 0.970 | 1.000 | holds |
| 40 | 100/100 | 0.970 | 1.000 | holds |
| 60 | 100/100 | 0.970 | 1.000 | holds |
| 80 | 100/100 | 0.970 | 1.000 | holds |
| 100 | 100/100 | 0.970 | 1.000 | holds |
| 120 | 100/100 | 0.970 | 1.000 | holds |
| 140 | 100/100 | 0.970 | 1.000 | holds |
| 160 | 100/100 | 0.970 | 1.000 | holds |
| 180 | 100/100 | 0.970 | 1.000 | holds |
| 200 | 100/100 | 0.970 | 1.000 | holds |

## F4: atraso máximo de observação

Alegação: Paragem nominal: o veículo não viola a segurança, com probabilidade de pelo menos 0.95. Caso `exec/cases/m14/ground-nominal-stop.json`. Recalculado: sim.
Margem: último nível que se mantém 3 ticks; primeiro refutado None ticks. Não monótona: não.

| atraso máximo de observação (ticks) | Passam | Limite inferior | Limite superior | Veredicto |
| --- | --- | --- | --- | --- |
| 0 | 100/100 | 0.970 | 1.000 | holds |
| 1 | 100/100 | 0.970 | 1.000 | holds |
| 2 | 100/100 | 0.970 | 1.000 | holds |
| 3 | 100/100 | 0.970 | 1.000 | holds |

## F5: viés do acelerómetro a partir de 5 s

Alegação: M9.1 guarded: aterra e cumpre todos os requisitos, com probabilidade de pelo menos 0.95. Caso `exec/cases/m14/rocket-imu-accel-bias.json`. Recalculado: sim.
Margem: último nível que se mantém None model; primeiro refutado None model. Não monótona: não.

| viés do acelerómetro a partir de 5 s (model) | Passam | Limite inferior | Limite superior | Veredicto |
| --- | --- | --- | --- | --- |
| 0.05 | 96/100 | 0.911 | 0.986 | inconclusive |
| 0.1 | 96/100 | 0.911 | 0.986 | inconclusive |
| 0.15 | 95/100 | 0.898 | 0.980 | inconclusive |
| 0.2 | 95/100 | 0.898 | 0.980 | inconclusive |
| 0.25 | 95/100 | 0.898 | 0.980 | inconclusive |
| 0.3 | 93/100 | 0.873 | 0.967 | inconclusive |
| 0.35 | 93/100 | 0.873 | 0.967 | inconclusive |
| 0.4 | 92/100 | 0.860 | 0.960 | inconclusive |
| 0.45 | 92/100 | 0.860 | 0.960 | inconclusive |
| 0.5 | 91/100 | 0.848 | 0.952 | inconclusive |

## F6: viés GNSS a partir de 5 s

Alegação: M9.1 guarded: aterra e cumpre todos os requisitos, com probabilidade de pelo menos 0.95. Caso `exec/cases/m14/rocket-gnss-bias.json`. Recalculado: sim.
Margem: último nível que se mantém None model; primeiro refutado 5.0 model. Não monótona: sim.

| viés GNSS a partir de 5 s (model) | Passam | Limite inferior | Limite superior | Veredicto |
| --- | --- | --- | --- | --- |
| 5.0 | 0/100 | 0.000 | 0.030 | refuted |
| 7.5 | 0/100 | 0.000 | 0.030 | refuted |
| 10.0 | 0/100 | 0.000 | 0.030 | refuted |
| 12.5 | 24/100 | 0.171 | 0.321 | refuted |
| 15.0 | 0/100 | 0.000 | 0.030 | refuted |
| 17.5 | 0/100 | 0.000 | 0.030 | refuted |
| 20.0 | 0/100 | 0.000 | 0.030 | refuted |
| 22.5 | 0/100 | 0.000 | 0.030 | refuted |
| 25.0 | 0/100 | 0.000 | 0.030 | refuted |
| 27.5 | 0/100 | 0.000 | 0.030 | refuted |
| 30.0 | 0/100 | 0.000 | 0.030 | refuted |

## F7: perda de impulso a partir de 5 s

Alegação: M9.1 guarded: aterra e cumpre todos os requisitos, com probabilidade de pelo menos 0.95. Caso `exec/cases/m14/rocket-thrust-loss.json`. Recalculado: sim.
Margem: último nível que se mantém None model; primeiro refutado 0.3 model. Não monótona: não.

| perda de impulso a partir de 5 s (model) | Passam | Limite inferior | Limite superior | Veredicto |
| --- | --- | --- | --- | --- |
| 0.05 | 96/100 | 0.911 | 0.986 | inconclusive |
| 0.075 | 96/100 | 0.911 | 0.986 | inconclusive |
| 0.1 | 96/100 | 0.911 | 0.986 | inconclusive |
| 0.125 | 95/100 | 0.898 | 0.980 | inconclusive |
| 0.15 | 95/100 | 0.898 | 0.980 | inconclusive |
| 0.175 | 93/100 | 0.873 | 0.967 | inconclusive |
| 0.2 | 93/100 | 0.873 | 0.967 | inconclusive |
| 0.225 | 93/100 | 0.873 | 0.967 | inconclusive |
| 0.25 | 92/100 | 0.860 | 0.960 | inconclusive |
| 0.275 | 91/100 | 0.848 | 0.952 | inconclusive |
| 0.3 | 85/100 | 0.778 | 0.905 | refuted |

## Início do viés GNSS e o critério G3 do M9.1

Especificação `exec/examples/m14-gnss-bias-onset.json`. Recalculado: sim. O G3 foi registado com o viés presente desde 0 s.

| Início | Magnitude (m) | R1 cumprido | Aterra |
| --- | --- | --- | --- |
| onset-0s | 5 | 30/30 | 29/30 |
| onset-0s | 10 | 30/30 | 22/30 |
| onset-0s | 15 | 30/30 | 0/30 |
| onset-0s | 20 | 30/30 | 0/30 |
| onset-0s | 25 | 30/30 | 0/30 |
| onset-0s | 30 | 30/30 | 0/30 |
| onset-2s | 5 | 0/30 | 0/30 |
| onset-2s | 10 | 0/30 | 0/30 |
| onset-2s | 15 | 30/30 | 0/30 |
| onset-2s | 20 | 30/30 | 0/30 |
| onset-2s | 25 | 30/30 | 0/30 |
| onset-2s | 30 | 30/30 | 0/30 |
| onset-5s | 5 | 0/30 | 0/30 |
| onset-5s | 10 | 0/30 | 0/30 |
| onset-5s | 15 | 30/30 | 0/30 |
| onset-5s | 20 | 30/30 | 0/30 |
| onset-5s | 25 | 30/30 | 0/30 |
| onset-5s | 30 | 30/30 | 0/30 |
| onset-10s | 5 | 0/30 | 0/30 |
| onset-10s | 10 | 0/30 | 0/30 |
| onset-10s | 15 | 30/30 | 6/30 |
| onset-10s | 20 | 30/30 | 0/30 |
| onset-10s | 25 | 30/30 | 0/30 |
| onset-10s | 30 | 30/30 | 0/30 |

# Protótipo de viabilidade do M10: navegação vertical e horizontal em 1D

Brinquedos para verificar ordens de grandeza do documento `docs/m10-resilient-navigation.md`. **Não são a implementação do M10 e não são evidência para nenhuma hipótese do M10.** Não usam o simulador Rust, o perfil de voo do M9 nem o SplitMix64 do repositório. Só biblioteca padrão de Python.

## Ficheiros

| Ficheiro | O que faz | Duração |
| --- | --- | --- |
| `feasibility.py` | filtro de Kalman 1D sem rejeição, CUSUM por fonte, isolamento por paridade, separação de soluções, arranque a frio, canal horizontal | cerca de 25 s |
| `baro_gate.py` | porta de decisão do barómetro: orçamento de erro e bandas de isolamento por altitude | menos de 1 s |
| `power_thresholds.py` | limiares efetivos de Clopper-Pearson e potência dos testes do pré-registo (secção 10) | cerca de 30 s |

## `feasibility.py`

- Canal vertical: descida de 2000 m a -1,5 m/s com desaceleração constante (13,22 m/s²), 865 ciclos de 0,02 s. Sensores com os desvios do repositório (radar 0,1 m a 50 Hz; GNSS z 0,5 m e vz 0,05 m/s a 10 Hz; acelerómetro 0,02 m/s²) e um barómetro proposto (25 Hz, 0,5 m, desvio inicial de 2 m, deriva 0,05 m/√s), que é a **variante otimista** do documento (sem erro estático, escala, latência nem jato). Ruído de Irwin-Hall limitado, como em `crates/vv-rocket/src/prng.rs` (o recorte a `±2√3 σ` não atua).
- Filtro de Kalman linear de 4 estados (altitude, velocidade, viés do acelerómetro, desvio do barómetro), forma de Joseph, **sem rejeição de medidas** e sem passeio aleatório do viés do acelerómetro (o viés verdadeiro é constante). Mais um subfiltro por fonte de altitude excluída (radar, GNSS, barómetro), usado para a separação de soluções e para o nível de proteção.
- Deteção: CUSUM bilateral por fonte sobre as inovações normalizadas (`k_ref` 0,5, `h` 12), para o filtro com barómetro (E1) e sem barómetro (E0).
- Isolamento: paridade no domínio das medidas (radar menos GNSS z, radar menos barómetro compensado, GNSS z menos barómetro compensado), com limiar de 3 desvios-padrão; a frio só com o prior do desvio do barómetro. A regra "maior separação normalizada" e o NIS dos subfiltros ficam como regras rejeitadas, para comparação.
- Como o filtro nunca rejeita medidas, a covariância não depende dos dados: calcula-se uma vez por filtro e os ganhos são reutilizados em cada semente. O script verifica na primeira semente que o resultado é igual ao do filtro com covariância completa (diferença 0 m).
- Canal horizontal só com GNSS: degrau, rampa só de posição e rampa coerente (posição e velocidade) de um recetor; testes de uma época, de janela de 20 e CUSUM.
- Arranque a frio (altitude inicial com incerteza de 50 m) com falha desde o instante 0, o caso das janelas de 0 a 40 s do M9.
- Também calcula, analiticamente, as caudas de Irwin-Hall sem recorte e o desfasamento de meio ciclo da força específica numa rampa do acelerador.

```sh
python spikes/m10-nav-feasibility/feasibility.py > resumo.json
```

Determinista: duas execuções dão o mesmo JSON, exceto os campos `cost` e `timing_s`.

## `baro_gate.py`

Calcula, ao longo de uma descida aproximada do M9 e do perfil de brinquedo, o orçamento de erro do barómetro (RSS e pior caso) e as bandas de altitude em que uma falha de 5, 10, 20 e 30 m é isolável com margem 3, para as variantes otimista, pessimista (coeficiente estático de 3% da pressão dinâmica, latência como incerteza da compensação, jato junto ao solo) e algumas sensibilidades. Reproduz os valores da revisão independente com o conjunto antigo. O perfil "m9like" é um integrador 1D local, não o simulador.

```sh
python spikes/m10-nav-feasibility/baro_gate.py > porta_barometro.json
```

## `power_thresholds.py`

Aritmética exata sobre binomiais: contagens efetivas em 100 execuções sob a regra do intervalo bilateral de Clopper-Pearson, limites do critério agrupado P1, potência do McNemar exato (H-C), potência não emparelhada de Fisher e exemplos de não inferioridade agrupada.

```sh
python spikes/m10-nav-feasibility/power_thresholds.py > potencia.json
```

## Sementes

`feasibility.py` usa `random.Random` (Mersenne Twister) com as sementes 9000 a 9099 (nominal e falhas). É o bloco do **protótipo**: não são sementes de avaliação e não podem ser usadas como tal. As sementes 0 a 40, 1000 a 1029 e 2000 a 2029 do repositório já foram usadas. Os blocos pré-registados do `vv-rocket` (4000 a 4009 teste e demonstrações, 5000 a 5099 desenvolvimento, 3000 a 3099 avaliação, 6000 a 6099 reserva) estão no documento, secção 10.1. Os outros dois scripts não usam aleatoriedade.

## Limitações

- Perfil, barómetro e prior inicial são supostos do brinquedo. O barómetro do `feasibility.py` não tem o erro de pressão estática que cresce com `v²` nem a perturbação do jato junto ao solo: é otimista. `baro_gate.py` calcula o efeito desses termos, mas os parâmetros são supostos.
- Sem erros não modelados (braço de alavanca do radar, atraso da força específica, modelo de massa). Os desvios-padrão de posterior (centímetros) são do modelo ideal e não são previsões para o M10.
- O brinquedo não distingue B+ de C nas falhas de alerta: o CUSUM deteta antes de o erro exceder o limite de alerta.
- O custo por atualização é de Python e não é o custo em Rust.

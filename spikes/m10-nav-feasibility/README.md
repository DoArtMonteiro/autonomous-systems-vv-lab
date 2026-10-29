# Protótipo de viabilidade do M10: navegação vertical e horizontal em 1D

Brinquedo para verificar ordens de grandeza do documento `docs/m10-resilient-navigation.md`. **Não é a implementação do M10 e não é evidência para nenhuma hipótese do M10.** Não usa o simulador Rust, o perfil de voo do M9 nem o SplitMix64 do repositório.

## O que faz

- Canal vertical: descida de 2000 m a -1,5 m/s com desaceleração constante (13,22 m/s²), 865 ciclos de 0,02 s. Sensores com os desvios do repositório (radar 0,1 m a 50 Hz; GNSS z 0,5 m e vz 0,05 m/s a 10 Hz; acelerómetro 0,02 m/s²) e um barómetro proposto (25 Hz, 0,5 m, desvio inicial de 2 m, deriva 0,05 m/√s). Ruído de Irwin-Hall limitado, como em `crates/vv-rocket/src/prng.rs`.
- Filtro de Kalman linear de 4 estados (altitude, velocidade, bias do acelerómetro, desvio do barómetro), forma de Joseph, mais um subfiltro por fonte de altitude excluída (radar, GNSS, barómetro): separação de soluções com limiar de 4 desvios-padrão, nível de protecção, isolamento por NIS dos subfiltros.
- Como o filtro nunca rejeita medidas em malha fechada, a covariância não depende dos dados: calcula-se uma vez por filtro e os ganhos são reutilizados em cada semente. O script verifica na primeira semente que o resultado é igual ao do filtro com covariância completa (diferença 0 m).
- Canal horizontal só com GNSS: degrau, rampa só de posição e rampa coerente (posição e velocidade) de um receptor.
- Arranque a frio (altitude inicial com incerteza de 50 m) com falha desde o instante 0, o caso das janelas de 0 a 40 s do M9.

## Como correr

```sh
python spikes/m10-nav-feasibility/feasibility.py > resumo.json
```

Biblioteca padrão apenas; cerca de 21 s (Python 3.14.6, Windows 11, AMD64 Family 25 Model 97). Determinista: duas execuções dão o mesmo JSON, exceto os campos `cost` e `timing_s`.

## Sementes

`random.Random` (Mersenne Twister) com as sementes 9000 a 9099 (nominal e falhas). É um bloco de **desenvolvimento**: não são sementes de avaliação e não podem ser usadas como tal. As sementes 0 a 40, 1000 a 1029 e 2000 a 2029 do repositório já foram usadas.

## Limitações

- Perfil, barómetro e prior inicial são supostos do brinquedo. O barómetro não tem o erro de pressão estática que cresce com `v²` nem a perturbação do jato junto ao solo (ver o documento, secção 4); é, por isso, otimista.
- Sem erros não modelados (braço de alavanca do radar, atraso da força específica, modelo de massa). Os desvios-padrão de posterior (centímetros) são do modelo ideal e não são previsões para o M10.
- O custo por atualização é de Python e não é o custo em Rust.

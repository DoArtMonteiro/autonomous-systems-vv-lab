# M10: resultados da reformulação do isolamento (tentativa única)

Estado: **tentativa executada; veredicto «não avançar».** Só sementes de desenvolvimento 5000 a 5099, um só binário, sem `m10-freeze.json`, sem envio. Esta é uma experiência de fecho só de V1 (adenda 1, secção 13.2 de `docs/m10-redesign-preregistration.md`): nenhum resultado aqui altera, por si, uma decisão do responsável. Todos os números vêm de `docs/evidence/m10-redesign/results/analysis.md` e `analysis.json` (gerados por `scripts/m10_redesign_analysis.py`); os registos por execução estão em `records.jsonl.gz` (colunas: etapa, célula, braço, semente, classe física, requisitos e invariantes falhados, isolamento, falhas de alerta vertical, `hv` e posição, `gate`, instante de ignição).

## 1. Veredicto

| | Resultado |
| --- | --- |
| **V1** (S1 a S7, nenhuma cláusula de paragem disparada) | **Não cumprido** |
| **V2** (limites de regressão estritos contra `robust` e `guarded`) | **Não cumprido**, como previsto |
| Veredicto global | **Não avançar.** Volta-se à secção 6.3 do desenho |

Cláusulas de paragem, pela ordem das etapas:

1. **Cláusula 1 disparou na etapa 1.** Falhas `hv` de B+G: 4 em G1 (nominal), 2 em G1 com ruído 1,5 vezes; 0 em M1, M3 e M4. As 6 são execuções com isolamento errado. B tem 0 em todas as etapas (a salvaguarda «B tem `hv`, regra mal calibrada» não se aplica); B+ tem 60 em G1, 1 em M1 e 5 em G1 com ruído.
2. **Cláusula 2 não disparou.** Ver secção 3.
3. **Cláusula 3 disparou na etapa 3.** Execuções de B+G com isolamento errado a 1,5 vezes: 26 em 2 400 (M3) e 23 em 640 (G1 com ruído); o pré-registo exigia zero.

## 2. Critérios de sucesso

| Id | Cumprido | Números |
| --- | --- | --- |
| S1 (zero `hv`, M3 incluída) | **não** | 4 + 2 execuções, todas com isolamento errado |
| S2 (isolamento errado em G1 a 0,3 e 0,5 m/s) | **não** | B+G 33 em 1 280 (limite superior a 95 % de 3,6 %; exigido: no máximo 5); B+ 110; redução de 70 % (exigido: 90 %); premissa de validade cumprida (B+ pelo menos 60) |
| S3 (cláusula 2) | sim | secção 3 |
| S4 (janela da ignição) | sim | B+G: 7 em 644 dentro (1,1 %), 33 em 1 916 fora (1,7 %); B+: 34 em 639 (5,3 %) e 89 em 1 921 (4,6 %) |
| S5 (cláusula 3) | **não** | 26 em 2 400 e 23 em 640 |
| S6 (isolamento não desligado, recuperação) | sim | R em M1 de B+G contra B+: `altimeter_stuck` 94 contra 91, `altimeter_delay` 89 contra 78, `gnss_coherent_ramp` 61 contra 57; isolamentos corretos 282 contra 281; G1 a 0,8 m/s R 293 contra 285 (B 88) |
| S7 (sem regressão contra B+, 23 células) | sim | nenhuma célula piora; `altimeter_delay` U 18 para 10, `gnss_coherent_ramp` U 14 para 8 |

Verificações de integridade: um só binário (SHA-256 `918479ef…`), construído do commit `6419587` (código de `crates/vv-rocket`; os commits seguintes só tocam em scripts, testes e documentação), com `source_sha256` `973400ab98cda5f9cb85cf9a7d85adb0cda93673afb66de0e12367f96c70b8ff` (campo de `run.json`), 44 820 execuções da matriz mais 4 800 de repetição (secção 6), contagens da matriz iguais às planeadas, sementes de 5000 a 5099, B+ e B desligados da etapa 0 iguais aos da etapa 2 (comparação por semente só da **classe física**: 0 diferenças em 1 400), repetição de B+G com os comprimentos de rejeição igual à original (comparação por semente da **classe, do veredicto de isolamento e da falha `hv`**: 0 diferenças em 4 800; os requisitos e invariantes não foram comparados semente a semente). Nas dez células em que se previa resultado idêntico (cinco pares distintos de F3 e as quatro de viés constante de F1), 0 diferenças entre B+G e B+ (classe e isolamento). Verificações de código obtidas: `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings` e `cargo test` (58, 30, 20 e 7 testes) sem falhas; `python -m unittest discover -s tests -p "test_*.py"` 403 testes, OK (3 ignorados); `cargo build --release` e a campanha `scripts/run_campaign.py --seeds 42,1337,2026` passaram.

## 3. Cláusula 2 e o efeito da porta nas rampas lentas

Unidades de 80 execuções (inícios 4,5; 6; 8; 10 s, sementes 5020 a 5039) e grelha completa (640 por magnitude):

| Magnitude (m/s) | U unidade B / B+ / B+G | U grelha B / B+ / B+G | Cláusula 2 |
| --- | --- | --- | --- |
| 0,2 | 66 / 79 / 65 | 499 / 636 / 495 | cumprida |
| 0,3 | 80 / 80 / 80 | 640 / 639 / 639 | vácua (B saturado) |
| 0,5 | 0 / 67 / 1 | 54 / 544 / 47 | cumprida |
| 0,8 | 0 / 3 / 0 | 36 / 41 / 7 | cumprida |

A cláusula 2 é **vácua a 0,3 m/s** (B tem U em 640 de 640), mas nessa magnitude B+G mantém **27 isolamentos errados em 640 execuções** (B+ 39); a cláusula 2 não vê esse problema. Estrato de 18 sementes da campanha: U de B 6, B+ 12, B+G 7 (cumprida). A porta remove quase todo o excesso de U de B+ sobre B a 0,5 m/s: dos 544 U de B+ a 0,5 m/s, 473 não tinham isolamento e 71 tinham isolamento errado; com a porta, os 47 U restantes são 41 sem isolamento (falham R5, sem R1) e 6 com isolamento errado. Isto é compatível com a hipótese H.2 do pré-registo (assimilação do recetor errado sem isolamento), mas **não prova** a causa: não há ablação entre a exoneração robusta e a rejeição por NIS.

## 4. O que a porta não resolve

- **O isolamento errado persiste** com a exoneração em duas âncoras: 33 em 1 280 execuções em G1 (7 a 0,2 m/s, 27 a 0,3 m/s, 6 a 0,5 m/s, 0 a 0,8 m/s). Os 6 de 0,5 m/s são as 4 falhas `hv` de G1 (sementes 5054, 5023, 5042).
- **A paridade não é robusta ao ruído 1,5 vezes**, mesmo sem falha de taxa: B+ tem 46 execuções com isolamento errado em 2 400 (M3), repartidas por 14 células (nominal 4 em 100); B+G tem 26 (2 por célula na maioria). B não isola e tem 0. O teste 9 da revisão falha para B+ e a porta só reduz o problema.
- **A porta não tem saída senão a decadência do CUSUM ou o isolamento** (comprimentos em ciclos de 0,02 s). G1: em 820 de 2 560 execuções a rejeição ainda estava aberta no toque, mediana do maior período com a porta ativa 857 ciclos (17 s), maior sequência de rejeição consecutiva 731 ciclos. G1 com ruído: 349 de 640 abertas no toque. M4: 5 de 1 900. Em M1 as sequências são nulas ou de 1 a 9 ciclos nas restantes células, com exceções: `altimeter_delay` (máximo 1 006 ciclos, 1 aberta), `altimeter_outliers` (433), `gnss_coherent_ramp` (682, 6 abertas).
- **Regressões herdadas (V2).** Fora do alcance da reformulação, como previsto: `gnss_bias` contra `guarded` (U 100 contra 1), o par `gnss_bias` mais `altimeter_dropout` contra `guarded` (100 contra 14) e o par `altimeter_bias` mais `gnss_dropout` contra `robust` e `guarded` (27 contra 8). A aceitação do limite de `E0` em `gnss_bias` não é uma decisão aprovada, por isso conta. As restantes 20 células distintas não têm regressão material contra nenhuma base; `altimeter_delay` e `gnss_coherent_ramp` melhoram muito contra `robust` e `guarded`.
- **`gnss_horizontal_bias`: três falhas de invariante (S2, semente 5084, 5086 e 5093) em B+ e em B+G; B tem duas (5084 e 5086), `robust` e `guarded` nenhuma.** Os identificadores são iguais em B+ e B+G: a porta não as causa nem as corrige. Continuam por explicar, o que bloqueia qualquer congelamento.

## 5. Varrimento de início e rampas a 0,8 m/s

M4 (5 falhas, 19 inícios, 20 sementes): B+G sem isolamento errado, sem falha `hv` nem vertical em 1 900 execuções; recuperações de B+G contra B+: `altimeter_delay` 363 contra 372 (U 10 contra 8), `gnss_coherent_ramp` 283 contra 280 (U 0 contra 15), `altimeter_stuck` 380 contra 374, `imu_accel_drift` 375 contra 375. O pior caso continua a ser a rampa coerente com início a 2 s (2 de 20 recuperadas). Em G1 a 0,8 m/s B+G tem R 293 e U 7 (B+ 285 e 41; B 88 e 36).

## 6. Desvios ao pré-registo e limitações

- **O orçamento de 45 000 execuções foi excedido.** A matriz planeada somou 44 820; repeti as 4 800 execuções de B+G das etapas 2 e 3 (etapas «2g» e «3g», `scripts/m10_redesign_run.py`) para gravar os comprimentos de rejeição nos registos da campanha, o que levou o total a **49 620**; contando as 2 800 execuções da etapa 0 descartadas (abaixo), as 64 do ensaio das sondas e a de ensaio do ruído, foram cerca de **52 500** (o diagnóstico de 160 execuções é à parte). Os resultados repetidos são idênticos aos originais; não alteram nenhum veredicto, mas o limite foi ultrapassado e não houve autorização prévia. Descoberto à posteriori: a repetição era evitável (os comprimentos já vinham das sondas).
- A adenda 2 (alteração de `landing_model.rs` para aceitar o ruído 1,5 vezes) estava prevista em 5.2 e foi registada antes da etapa 3. Para gravar os comprimentos na campanha alterei `scripts/m10_campaign.py` (campo `gate` só quando existe) **depois de as etapas 1 a 5 terminarem** (ficheiro alterado às 19:13:16; a última saída da etapa 5 é das 19:12:21). Só as repetições «2g» e «3g» usaram a versão com a linha, que não altera nenhum outro campo; as etapas 0 a 5 usaram a versão anterior.
- Foram descartadas duas execuções da etapa 0, **ambas com a bandeira desligada**: (a) a primeira, com o binário `8b6a259c…`, anterior à adenda 2 (a validação do ruído 1,5 vezes mudou o código, por isso o binário final tem outro SHA-256 e todos os braços têm de usar o mesmo); (b) a segunda, com o binário final mas com um modelo gerado com `ambiguity_gate: false` escrito explicitamente, o que dava um SHA-256 diferente do modelo `m10-nominal.json` pré-registado. Ambas reproduziram as contagens registadas; ficaram de fora por identidade de binário e de modelo, não por resultado; a etapa 0 válida usa o binário final e o modelo `m10-nominal.json` (SHA-256 `c28a258c…`). Também houve uma execução de teste (`smoke`, 64 execuções) das sondas novas.
- As adendas 1 e 2 foram commitadas antes da primeira execução com a bandeira ligada, testes unitários incluídos (sementes fixadas 5090 e 5091). O diagnóstico anterior à reformulação (`docs/evidence/m10-redesign/diagnostic/`, 160 execuções, sementes 5000 a 5019) e o desvio aos passos 1 e 2 da estratégia estão em 13.1 do pré-registo: o passo 2 («B+ sem paridade») não foi feito.
- Dados de desenvolvimento, sementes todas conhecidas do desenvolvimento de B+: sem generalização, sem valores-p; os intervalos de Clopper-Pearson são informativos e não ajustados. O número de sementes por célula (40 em G1, 20 em M4) limita a resolução de diferenças pequenas.

## 7. O que fica por testar

- A atribuição entre a exoneração em duas âncoras e a rejeição por NIS (um só braço; uma ablação seria uma segunda tentativa).
- As alternativas descartadas em 3.3 (persistência por N épocas, limiares de paridade mais largos, chão de magnitude, reprocessamento com NIS).
- Porque é que o isolamento errado persiste com a exoneração em duas âncoras, e porque é que a paridade isola em ruído 1,5 vezes sem falha (só se pode ler o mecanismo no código; nenhum traço por execução foi analisado).
- A saída da porta: 32 % das execuções de G1 terminam com a rejeição aberta.
- Os testes 4 a 8 e 11 a 13 da revisão; falhas combinadas com rampa lenta; ruídos que não sejam 1,5 vezes; outros veículos e perfis.
- As regressões herdadas e as três falhas de invariante de `gnss_horizontal_bias`.

## 8. Reprodução

```sh
cargo build --release --manifest-path crates/vv-rocket/Cargo.toml
python scripts/m10_redesign_run.py --binary crates/vv-rocket/target/release/vv-rocket --root runs/m10-run --stages 0
python scripts/m10_redesign_run.py --binary crates/vv-rocket/target/release/vv-rocket --root runs/m10-run --stages 1,2,3,3b,4,5
python scripts/m10_redesign_run.py --binary crates/vv-rocket/target/release/vv-rocket --root runs/m10-run --stages 2g,3g
python scripts/m10_redesign_analysis.py --root runs/m10-run --output docs/evidence/m10-redesign/results
```

Máquina: Windows-11-10.0.26300-SP0, AMD64 Family 25 Model 97 Stepping 2 (AuthenticAMD), Python 3.14.6; comando `python scripts/m10_redesign_run.py` acima, 8 tarefas. Tempos registados em `stages.log` (fora do repositório): 2 560 execuções de sonda em 15,8 a 16,4 s, 2 400 execuções de campanha em 11,5 a 15,1 s, 1 000 execuções da etapa 0 em 4,6 s. Modelos geradores em `docs/evidence/m10-redesign/templates/` (SHA-256 em `analysis.json`).

## 9. Estado final

**Não avançar.** O M10 fica fechado como investigação sem resultado positivo: o ramo `research/m10-redesign` continua isolado, não é para fusão, não houve envio e não se fazem mais execuções nem código novo. A decisão de encerrar e o excesso de orçamento (secção 6) foram reconhecidos pelo orquestrador como desvio declarado.

Fica por testar: a ablação do mecanismo (exoneração em duas âncoras contra rejeição por NIS); as três falhas de invariante S2 de `gnss_horizontal_bias` (sementes 5084, 5086 e 5093), por explicar; o mecanismo do isolamento errado com ruído 1,5 vezes sem falha de taxa; e as sementes de avaliação (3000 a 3099) e de reserva (6000 a 6099), que nunca foram usadas.

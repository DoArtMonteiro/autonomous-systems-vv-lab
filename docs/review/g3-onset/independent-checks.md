# Verificações independentes

Contas do protocolo (`docs/m15-g3-onset-protocol.md`, commit `bec7b3f`) refeitas sem simular. Usou-se só Python 3.14 com a biblioteca padrão (`fractions`, `math`, `json`, `subprocess`, `importlib`). Não se correu simulador, campanha, `vv-exec`, `vv-rocket` nem `cargo`, e não se usou nenhuma semente do protocolo como entrada de um simulador. Os números de semente que aparecem abaixo são só aritmética sobre intervalos.

**Convenção das colunas.** «Declarado» é o que o protocolo diz. «Recalculado» é o resultado do programa do apêndice. «Veredicto»: **coincide** quer dizer apenas que a aritmética bate certo; não valida nenhuma hipótese. **Discrepância** quer dizer que o protocolo e o recálculo diferem. Nenhuma discrepância foi corrigida no protocolo.

O programa completo está no apêndice e imprime os valores recalculados citados abaixo. Os números lidos dos ficheiros de evidência (taxas do simulador, 280 pares corrigidos, 26 em R2 e 9 em R5) não se recalculam e estão assinalados como lidos. O cálculo do modelo (secção 7) importa `scripts/m14_masking_model.py`, que só contém aritmética.

## Resumo

| # | Item | Linha do protocolo | Veredicto |
| --- | --- | --- | --- |
| 1 | Totais por etapa, 920 sementes, 5 800 execuções | 87 a 96 | coincide |
| 2 | Mapas semente para condição, disjunção das etapas e das sementes gastas | 89 a 93, 150 a 155 | coincide (ver nota sobre a l. 153) |
| 3 | Limiares binomiais e potências | 180 a 187 | coincide |
| 4 | «Seriam precisas 63» sementes para um teste ao nível 0,01/14 | 115 | **discrepância** (69; 63 vale para 0,01/7) |
| 5 | McNemar de S4 e S5 e a regra «fração ≥ 0,9» | 115 | coincide nos números; achado: o McNemar é redundante |
| 6 | Posições por estatística de ordem (20, 41 e 19, 42) | 116 | coincide |
| 7 | Modelo do estimador: b*, picos, primeira rejeição, planalto | 25 | coincide; achado sobre «−5,09 m/s» |
| 8 | Precisão de H3 (1,00; 0,67; 1,00) | 176 a 179 | coincide (cálculo exato, não a reamostragem) |
| 9 | Limites de Clopper-Pearson e eventos máximos | 187 | coincide |
| 10 | 35 + 6 = 41 compromissos; 1 024 pares | 131; `docs/m13-discovery-lab.md` l. 52 | coincide |
| 11 | Contas do rascunho que o protocolo critica (300, 480, 400, 1 400) | 43 | coincide |
| 12 | Hash `12b276cb...` do `source_sha256` | 166 | **discrepância** (ver `source-commitments.md`) |
| 13 | Citações `landing_model.rs:414-418` e `:238` | 33, 133 | **discrepância** (desatualizadas) |

## 1. Totais por etapa

Fórmula: execuções = sementes × braços por semente. Etapa A: 2 braços. Etapa B: 17 magnitudes × 2 inícios = 34. Etapa C: 3 condições × 4 braços = 12. Etapa D: 2 inícios × 3 mitigações = 6. Etapa E: 3 braços.

| Etapa | Sementes declaradas | Recalculado | Execuções declaradas | Recalculado | Veredicto |
| --- | --- | --- | --- | --- | --- |
| A | 44000 a 44319 (320) | 320 | 640 | 640 | coincide |
| B | 44320 a 44379 (60) | 60 | 2 040 | 2 040 | coincide |
| C | 44380 a 44439 (60) | 60 | 720 | 720 | coincide |
| D | 44440 a 44759 (320) | 320 | 1 920 | 1 920 | coincide |
| E | 44760 a 44919 (160) | 160 | 480 | 480 | coincide |
| Reserva | 44920 a 44999 (80) | 80 | 0 | 0 | coincide |
| **Total** | **920** | **920** | **5 800** | **5 800** | coincide |

As cinco faixas são contíguas, sem lacunas nem sobreposições (verificado com uma asserção). Tamanhos de banda e de células: banda baixa 4 × 8 × 5 = 160; banda alta 160; M1 3 × 8 × 10 = 240; M2 e cada nível de S7 8 × 10 = 80; pares de D com início tardio por mitigação 4 × 8 × 10 = 320; pares de E por mitigação 8 × 20 = 160.

## 2. Mapas de sementes e disjunção

- A: 44000 + 40·i + 5·j + r (i = 0 a 7, j = 0 a 7, r = 0 a 4) gera 320 sementes distintas, de 44000 a 44319.
- D: 44440 + 40·i + 10·j + r (i = 0 a 7, j = 0 a 3, r = 0 a 9) gera 320 sementes distintas, de 44440 a 44759.
- E: 44760 + 20·f + k (f = 0 a 7, k = 0 a 19) gera 160 sementes distintas, de 44760 a 44919.
- Sobreposição das etapas com as faixas já vistas ou proibidas (41000 a 41999, 42000 a 43999, 45000 a 46999, 47000 a 47019, 32000 a 32099, 33500 a 33529, 30001, 30017, 50000 a 59999, 3000 a 3099, 6000 a 6099): **nenhuma**.

**Nota sobre a linha 153.** O protocolo proíbe «as sementes protegidas do foguetão em `exec/src/seeds.rs`». A lista `ROCKET_PROTECTED` desse ficheiro tem três intervalos: 3000 a 3099, 6000 a 6099 e **44000 a 44999**. Lida à letra, a frase proíbe as próprias sementes do protocolo. A intenção é clara (proíbem-se as sementes M10 e as da reserva fora desta execução), mas o executor, quando for escrito, não pode simplesmente importar a lista. Ver pergunta 16.

## 3. Limiares binomiais e potências

Teste binomial exato unilateral de H0: π ≤ 0,9. O limiar é o menor k tal que P(X ≥ k | n, 0,9) ≤ α, calculado com aritmética racional (`fractions.Fraction`).

| Teste | n | α | Declarado | Recalculado | Tamanho real | Veredicto |
| --- | --- | --- | --- | --- | --- | --- |
| H1, H2 | 160 | 0,01/3 | 154 | 154 | 0,00281 | coincide |
| S3 | 160 | 0,01/7 | 155 | 155 | 0,00091 | coincide |
| M1 | 240 | 0,01/2 | 228 | 228 | 0,00382 | coincide |
| M2 | 80 | 0,01/2 | 79 | 79 | 0,00216 | coincide |
| S7 (cada proporção) | 80 | 0,01/7 | 80 de 80 | 80 | 0,00022 | coincide |

Potências de H1 e H2 (n = 160, rejeita com ≥ 154):

| π verdadeiro | Declarado | Recalculado | Veredicto |
| --- | --- | --- | --- |
| 0,95 | 0,31 | 0,3071 | coincide |
| 0,97 | 0,79 | 0,7934 | coincide |
| 0,99 | 0,999 | 0,9988 | coincide |

M2 com π = 0,99: declarado 0,81, recalculado 0,8092, coincide. Valor não declarado: S7 com π = 0,99 tem potência 0,4475 para cada proporção (80 de 80 é o único resultado que rejeita); se as duas proporções tiverem π = 0,99 e tiverem de rejeitar ambas, a potência conjunta é cerca de 0,20 (0,4475 ao quadrado, com independência entre as duas). Isto é consistente com a frase do protocolo «pode ficar inconclusivo com uma única exceção».

**Nota sobre H1: o sucesso é uma conjunção.** O sucesso de H1 é «R1 cumpre-se a 0 s e falha no início tardio» (l. 109), logo π = p0 × q, com p0 a taxa de R1 a 0 s e q a taxa de falha de R1 no início tardio. O G3 registado só exige p0 ≥ 0,9 (27 de 30). A tabela acima trata π como uma taxa única. Cálculo adicional (n = 160, rejeita com ≥ 154, mesma função `sf`):

| π = p0 × q | Potência de H1 |
| --- | --- |
| 0,90 (p0 = 0,90, q = 1) | 0,0028 (é o tamanho do teste) |
| 0,93 (p0 = 0,93, q = 1) | 0,064 |
| 0,9405 (p0 = 0,95, q = 0,99) | 0,155 |
| 0,9603 (p0 = 0,97, q = 0,99) | 0,549 |

Ou seja, se a taxa a 0 s for 0,93, o mascaramento perfeito no início tardio só dá potência 0,064; com p0 = 0,95 e q = 0,99, 0,155. Os dados de desenvolvimento (30 de 30 a 0 s em todas as magnitudes) apontam para p0 ≈ 1, mas isso não é uma garantia do G3. Ver pergunta 25. (Estes quatro valores foram calculados à parte com a mesma fórmula; não estão no programa do apêndice.)

«Com α = 0,01/3, abaixo de 55 sementes nem 100 % rejeitaria H0»: 0,9^n ≤ 0,01/3 dá n ≥ 55. Coincide. Outros valores de n mínimo calculados: 51 para 0,01/2, 63 para 0,01/7, 69 para 0,01/14.

## 4. A discrepância das «63 sementes»

A linha 115 diz: «Com 60 sementes, um teste binomial contra 0,9 a este nível é impossível (seriam precisas 63)». «Este nível» é o p < 0,01/14 da frase anterior.

Fórmula: um teste binomial contra 0,9 com todos os sucessos só rejeita se 0,9^n ≤ α. Com α = 0,01/14 = 0,000714, n ≥ ln(α) / ln(0,9) = 68,8, isto é, **69**. O valor 63 corresponde a α = 0,01/7 (0,9^63 = 0,00131 ≤ 0,00143; 0,9^62 = 0,001456 > 0,001429).

| α | n mínimo | Declarado |
| --- | --- | --- |
| 0,01/7 | 63 | 63 |
| 0,01/14 | 69 | 63 |

A conclusão do protocolo (60 sementes não chegam) fica **mais** forte, não mais fraca. É um erro de texto, sem efeito no desenho, mas num documento que vai ser congelado merece correção.

## 5. McNemar de S4 e S5 e a regra «fração ≥ 0,9»

O protocolo pede, em cada condição, McNemar exato unilateral com p < 0,01/14 **e** fração de sementes com o resultado previsto ≥ 0,9 (l. 115, 139).

- Número mínimo de pares discordantes, todos no sentido previsto, para p < 0,01/14: 0,5^d < 0,000714 dá d = 11.
- Fração ≥ 0,9 com 60 sementes quer dizer pelo menos 54 pares no sentido previsto. Mesmo no pior caso, com os 6 restantes discordantes no sentido contrário, o p exato é P(Bin(60; 0,5) ≥ 54) = 4,9 × 10⁻¹¹, muito abaixo de 0,01/14. **Logo, o McNemar nunca é o critério que decide: se a regra da fração passa, o McNemar passa.**
- A regra da fração é uma estimativa pontual, não um teste. Probabilidade de a regra passar (X ≥ 54 em 60) conforme a taxa verdadeira π:

| π | P(X ≥ 54 de 60) |
| --- | --- |
| 0,95 | 0,970 |
| 0,90 | 0,607 |
| 0,85 | 0,185 |
| 0,80 | 0,031 |
| 0,75 | 0,003 |

- Limite inferior de Clopper-Pearson a 99 % (unilateral) para 54 de 60: 0,774; para 60 de 60: 0,926.

Ou seja, a regra aceitaria S4 ou S5 com 18 % de probabilidade se a taxa verdadeira fosse 0,85 e com 3 % se fosse 0,80. O protocolo diz (l. 115) que, com 60 sementes, o teste binomial é impossível e aplica «a regra do motor», que é esta. É uma escolha consciente, mas as consequências acima não estão escritas. Ver pergunta 12.

## 6. Posições por estatística de ordem (mediana de b_s, n = 60)

Intervalo sem distribuição para a mediana: [X(l), X(u)]. Se B é o número de observações abaixo da mediana, B ~ Bin(60; 0,5), a cobertura é 1 − P(B ≤ l − 1) − P(B ≥ u). Cada cauda deve ser ≤ α, para um intervalo a 1 − 2α.

| Uso | α | Posições declaradas | Cauda P(B ≤ l − 1) | Cobertura | Exigida (1 − 2α) | Posição mais apertada | Veredicto |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H3 | 0,01/3 = 0,003333 | 20 e 41 | 0,00311 | 0,99378 | 0,99333 | l = 20 | coincide |
| S1, S2 | 0,01/7 = 0,001429 | 19 e 42 | 0,00134 | 0,99733 | 0,99714 | l = 19 | coincide |

As margens de folga são pequenas (0,99378 contra 0,99333). Nota técnica: com b_s discreto (passo 0,25) há empates, e o intervalo continua válido (cobertura ≥ nominal), apenas conservador.

## 7. O modelo do estimador

`scripts/m14_masking_model.py`, importado como módulo, com os ganhos do caso lidos do blob em `bec7b3f`. Foram recalculados:

| Declarado (l. 25 e `prediction.json`) | Recalculado | Veredicto |
| --- | --- | --- |
| b* = 11,988676443422214 m (início 5 s) | 11,988676443422214 | coincide |
| b* = 11,989 m com 3, 5 e 10 ciclos de rejeição | 11,989; 11,989; 11,989 | coincide |
| b* = 3,996 m (1 m), 7,992 m (2 m), 11,989 m (3 m) | 3,996; 7,992; 11,989 | coincide |
| b* = 11,989 m para qualquer início de 0,01 a 20 s | 11,989 em 0,01; 0,1; 1; 2; 5; 10; 15; 20 s | coincide |
| P2 a 8 m: rejeita só com início 0 s | só 0 s | coincide |
| Pico do resíduo 0,3 s depois do início, 0,250 × magnitude (1,25; 2,00; 2,43; 2,88 m a 5; 8; 9,72; 11,5 m) | pico 0,250 × em +0,30 s: 1,251; 2,002; 2,432; 2,878 | coincide |
| Primeira rejeição a +0,58 s (12 m), +0,18 s (15 m), +0,08 s (30 m), sem readmissões | +0,58; +0,18; +0,08; sem readmissões | coincide |
| Planalto «cerca de 0,22 vezes a magnitude» | 0,219 | coincide |

Achado sobre `steady_state_at_8m` de `prediction.json` (valor `final_v_mps` = -5,0875, citado na linha 30 como «−5,09 m/s»): no modelo, a velocidade do estado estável **não é constante**; oscila com período de 5 ciclos (a cadência do GNSS). Nos últimos ciclos do modelo, v toma os valores -4,166; -4,464; -4,714; -4,921; -5,087 m/s, repetidos. O valor -5,09 é a fase final desse ciclo (o último ciclo do modelo calha nessa fase), não um valor médio. Idem `final_e_m` = 0,7485 (oscila entre 0,75 e 1,58 m). Não afeta b* nem o argumento do protocolo, mas «estado estável» e «-5,09 m/s» são imprecisos. A ordem de grandeza (alguns m/s) mantém-se.

O que este cálculo **não** verifica: que o modelo represente o simulador. A única evidência de que o faz é o teste de 20 sementes de `docs/evidence/m14/masking/test.json`.

## 8. Precisão de H3, calculada de forma exata

O protocolo (l. 176 a 179) reamostra, com n = 60 e 20 000 repetições, a distribuição de b_s obtida de `test.json`. Aqui calculou-se a mesma probabilidade **de forma exata** (multinomial), sem reamostrar; **é um cálculo diferente com os mesmos pressupostos, não uma repetição da reamostragem**.

Pressupostos: (a) as 20 sementes comuns a todos os níveis, com R1 monótona em cada semente; (b) distribuição de b_s a partir dos números de execuções com R1 cumprido por nível em `test.json`: 11,25: 1; 11,5: 2; 11,75: 5; 12,0: 14; 12,25: 18; 12,5: 20, o que dá b_s = 11,25 (1 semente), 11,5 (1), 11,75 (3), 12,0 (9), 12,25 (4), 12,5 (2) e mediana 12,0. Critério de confirmação de H3: limite inferior (X(20) − 0,25) acima de b* − 1 e X(41) abaixo de b* + 1.

| Fronteira real | Declarado | Recalculado (exato) | Veredicto |
| --- | --- | --- | --- |
| Distribuição de desenvolvimento | P(confirmar) = 1,00 | 1,0000 | coincide |
| 0,75 m acima | P(confirmar) = 0,67 | 0,6692 | coincide |
| 1,5 m acima | P(refutar) = 1,00 | 1,0 (e P(confirmar) = 0) | coincide |

Duas observações para o revisor. Primeiro, a distribuição de b_s foi inferida de proporções por nível, assumindo monotonia que `test.json` não permite verificar. Segundo, os cenários «0,75 m acima» e «1,5 m acima» são deslocamentos escolhidos pelo autor.

## 9. Orçamento de regressão: Clopper-Pearson

Limite superior unilateral a 99 % (bissecção sobre a função de distribuição binomial exata).

| Eventos/pares | Declarado | Recalculado | Veredicto |
| --- | --- | --- | --- |
| 0/480 | 0,95 % | 0,955 % (0,95482) | coincide |
| 1/480 | 1,37 % | 1,375 % (1,37490) | coincide |
| 13/480 | máximo a 5 % | 4,971 % (e 14/480 dá 5,238 %) | coincide |
| 1/320 | 2,06 % | 2,056 % | coincide |
| 2/320 | 2,60 % | 2,601 % | coincide |
| 35/1024 | 3,4 % e limite 4,98 % | 3,418 % e 4,980 % | coincide |

Eventos máximos dentro de cada orçamento, recalculados: invariantes (480 pares, ≤ 1 %) 0; R2 a R6 (480 pares, ≤ 5 %) 13; R1 com início 0 s (320 pares, ≤ 2,5 %) 1. Coincidem com a tabela do protocolo (l. 127 a 129).

Cálculo adicional, não declarado: 6 de 30 no contraexemplo dá limite 41,95 %. Os 35 compromissos do envelope são 26 em R2 e 9 em R5 (`docs/evidence/m13/g3-onset/investigation.json`, `findings.mitigations[0].envelope.new_violations`), e 35 + 6 = 41, o número citado no M13. O M13 descreve os 41 pares como «execuções que deixam de cair e passam a tocar fora da plataforma ou com velocidade horizontal excessiva» (`docs/m13-discovery-lab.md`, l. 52), isto é, pares em que a mitigação corrigiu R1. O código, porém, conta um compromisso sempre que o braço mitigado ganha uma violação de requisito sem regressão de R1 (`exec/src/investigate.rs:1165-1172`), incluindo pares dos 744 em que R1 não mudou. A taxa condicional fica entre 35/1 024 = 3,4 % (todos os 35 fora dos 280) e 35/280 = 12,5 % (todos dentro). **Isto é uma leitura, não um recálculo**: `investigation.json` dá as contagens (`fixed` 280, `neither` 744, `tradeoff` 35), mas não diz em que pares ocorrem os 35 (`envelope_cells` só tem as contagens de corrigidos por célula). Ver pergunta 14.

## 10. Contas do rascunho que o protocolo critica

`docs/m14-g3-onset-protocol-draft.md` (l. 21 a 23). Linha 43 do protocolo: «300 sementes para 480 execuções em C1, 300 para 480 em C3, 400 para 1400 pares».

| Item | Rascunho | Recalculado | Veredicto |
| --- | --- | --- | --- |
| C1 e C2 | 8 inícios × 2 bandas × 30 sementes = 480 execuções; sementes 44000 a 44299 | 480 execuções, 300 sementes | coincide: não fecham sem reutilização não especificada |
| C3, envelope | 480 execuções; sementes 44300 a 44599 | 480 e 300 | coincide |
| C3, famílias | 7 famílias × 200 pontos × 2 braços = 2 800 execuções; 1 400 pares; sementes 44600 a 44999 | 2 800; 1 400; 400 | coincide |

O rascunho dizia 7 famílias. `exec/claims/m13/g3-onset.json` tem 8 (`regression` tem 8 entradas). O protocolo corrige para 8: coincide.

## 11. Discrepâncias fora do aritmético

- **Hash do código do simulador.** Declarado `12b276cb...` «hoje» (l. 166). Recalculado em `bec7b3f`: `295a45b2...`. Discrepância. Detalhe em `source-commitments.md`.
- **Citações de linha.** `landing_model.rs:414-418` (l. 33) e `landing_model.rs:238` (l. 133) estavam certas em `3962482` e hoje são 426 a 431 e 250. Discrepância. Detalhe em `source-commitments.md`.
- **Prefixos de hash.** `f9e6154c...`, `4f30b680...` e `9a67d22e...` coincidem com os blobs em `bec7b3f`.
- **Datas de commit da previsão.** O protocolo diz que a previsão foi fixada no commit `73c9ff5` (20:20) antes do teste em `1195c1b` (20:25). `git log` dá 2026-11-03 20:20:38 e 20:25:07 (UTC), e ambos são antepassados de `bec7b3f`. A hora de um commit é escolhida por quem o cria; não é prova externa.

## O que não se verificou

- Nenhum número que dependa do simulador: taxas R1/R5 por célula, 35 compromissos, 30 de 30, 20 de 20, b50 = 11,89 m, etc. Foram lidos nos ficheiros de evidência, não recalculados.
- Se `vv-rocket land` com o hash atual do código dá os mesmos bytes que com `12b276cb...`.
- A implementação Halton e a quantização que o executor terá de reproduzir (`exec/src/investigate.rs:1485` e `exec/src/search.rs:342`). Lidas, não executadas.
- A independência estatística entre sementes vizinhas através de `SplitMix64::stream(seed, source)` = `seed ^ source × 0x9E3779B97F4A7C15` (`crates/vv-rocket/src/prng.rs`). Ver pergunta 15; não se avaliou.
- Se alguma semente de 44000 a 44999 já foi corrida: o repositório não o mostra, porque `vv-rocket land` não tem guarda.

## Apêndice: programa completo

Guardar como `check_all.py` fora do repositório e executar, a partir da raiz do repositório, `python -I /caminho/para/check_all.py` (Python 3.11 ou posterior; só biblioteca padrão). Usa o blob de `bec7b3f` para o caso base e importa `scripts/m14_masking_model.py`. Não escreve ficheiros.

```python
# Recalculation of the numbers in docs/m15-g3-onset-protocol.md. No simulator, no seed is run.
# Run from the repository root with: python -I /path/to/check_all.py   (Python 3.11 or later, standard library only)
import sys, json, subprocess, importlib.util
from math import comb, log, ceil
from fractions import Fraction as F
sys.dont_write_bytecode = True

# ---- A. run totals and seed map --------------------------------------------------------------
B_LEVELS = [10 + 0.25 * k for k in range(17)]
stages = {  # name: (first seed, last seed, runs per seed)
    "A": (44000, 44319, 2),
    "B": (44320, 44379, len(B_LEVELS) * 2),
    "C": (44380, 44439, 3 * 4),
    "D": (44440, 44759, 2 * 3),
    "E": (44760, 44919, 3),
}
seeds = runs = 0
for k, (a, b, per) in stages.items():
    n = b - a + 1
    seeds += n
    runs += n * per
    print(f"stage {k}: seeds {a}-{b} = {n}, runs/seed {per}, runs {n * per}")
print("total seeds", seeds, "total runs", runs, "reserve", 44999 - 44920 + 1)
ranges = sorted((a, b) for a, b, _ in stages.values())
assert all(ranges[i][1] + 1 == ranges[i + 1][0] for i in range(len(ranges) - 1)), "gap or overlap"
mapA = {44000 + 40 * i + 5 * j + r for i in range(8) for j in range(8) for r in range(5)}
mapD = {44440 + 40 * i + 10 * j + r for i in range(8) for j in range(4) for r in range(10)}
mapE = {44760 + 20 * f + k for f in range(8) for k in range(20)}
print("map A", len(mapA), min(mapA), max(mapA), "| map D", len(mapD), min(mapD), max(mapD),
      "| map E", len(mapE), min(mapE), max(mapE))
spent = {"41000-41999": (41000, 41999), "42000-43999": (42000, 43999), "45000-46999": (45000, 46999),
         "47000-47019": (47000, 47019), "32000-32099": (32000, 32099), "33500-33529": (33500, 33529),
         "30001": (30001, 30001), "30017": (30017, 30017), "50000-59999": (50000, 59999),
         "3000-3099": (3000, 3099), "6000-6099": (6000, 6099)}
for name, (lo, hi) in spent.items():
    hit = [k for k, (a, b, _) in stages.items() if a <= hi and lo <= b]
    print(f"overlap with {name}: {hit or 'none'}")
print("band sizes: low", 4 * 8 * 5, "high", 4 * 8 * 5, "| M1", 3 * 8 * 10, "| M2 or S7 level", 8 * 10,
      "| D late pairs per mitigation", 4 * 8 * 10, "| E pairs per mitigation", 8 * 20)
print("stage B levels", len(B_LEVELS), B_LEVELS[0], B_LEVELS[-1])


# ---- B. exact binomial thresholds and powers -------------------------------------------------
def sf(k, n, p):
    return sum(comb(n, i) * p**i * (1 - p)**(n - i) for i in range(k, n + 1))


def thr(n, a, p0=F(9, 10)):
    return next(k for k in range(n + 2) if sf(k, n, p0) <= a)


for name, n, a in [("H1/H2", 160, F(1, 300)), ("S3", 160, F(1, 700)), ("M1", 240, F(1, 200)),
                   ("M2", 80, F(1, 200)), ("S7", 80, F(1, 700))]:
    k = thr(n, a)
    print(f"{name}: n={n} alpha={float(a):.5f} reject if X>={k}; size {float(sf(k, n, F(9, 10))):.5f}")
for p in ("0.95", "0.97", "0.99"):
    print("power H1/H2 pi", p, round(float(sf(154, 160, F(p))), 4))
print("power M2 pi .99", round(float(sf(79, 80, F("0.99"))), 4), "| power S7 pi .99", round(float(sf(80, 80, F("0.99"))), 4))
for lab, a in (("0.01/2", 1 / 200), ("0.01/3", 1 / 300), ("0.01/7", 1 / 700), ("0.01/14", 1 / 1400)):
    print(f"smallest n where all successes reject H0 (0.9^n <= {lab}):", ceil(log(a) / log(0.9)))
print("0.9^62 =", 0.9**62, "| 0.9^63 =", 0.9**63, "| 0.01/7 =", 0.01 / 7, "| 0.9^68 =", 0.9**68, "| 0.9^69 =", 0.9**69, "| 0.01/14 =", 0.01 / 14)


# ---- C. McNemar and the 0.9 rule of S4 and S5 ------------------------------------------------
def cdf(x, n, p):
    return sum(comb(n, i) * p**i * (1 - p)**(n - i) for i in range(x + 1))


def cp_upper(x, n, conf=0.99):
    lo, hi = 0.0, 1.0
    for _ in range(100):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if cdf(x, n, m) > 1 - conf else (lo, m)
    return hi


def cp_lower(x, n, conf=0.99):  # P(X >= x | p) = 1 - conf
    lo, hi = 0.0, 1.0
    for _ in range(100):
        m = (lo + hi) / 2
        lo, hi = (lo, m) if sf(x, n, m) > 1 - conf else (m, hi)
    return lo


print("min discordant pairs, all in the predicted direction, for p < 0.01/14:",
      next(d for d in range(1, 60) if 0.5**d < 0.01 / 14))
print("McNemar p with 54 predicted and 6 opposite discordant pairs:", float(sf(54, 60, F(1, 2))))
for pi in ("0.95", "0.9", "0.85", "0.8", "0.75"):
    print(f"P(rule X>=54 of 60 | pi={pi}) =", round(float(sf(54, 60, F(pi))), 4))
print("Clopper-Pearson 99% one-sided lower bound, 54/60:", round(cp_lower(54, 60), 4), "| 60/60:", round(cp_lower(60, 60), 4))
print("H1 threshold 154/160 tolerates", 160 - 154, "failures; one cell (onset x magnitude) has 5 seeds")


# ---- D. order statistics for the median interval ---------------------------------------------
def tail(n, k):  # P(B <= k), B ~ Bin(n, 1/2)
    return sum(comb(n, i) for i in range(k + 1)) / 2**n


for lab, l, u, a in (("H3", 20, 41, 0.01 / 3), ("S1 and S2", 19, 42, 0.01 / 7)):
    cov = 1 - tail(60, l - 1) - tail(60, 60 - u)
    best = max(k for k in range(1, 31) if tail(60, k - 1) <= a)
    print(f"{lab}: positions {l},{u}; tail {tail(60, l - 1):.5f} <= alpha {a:.5f}; "
          f"coverage {cov:.5f} >= {1 - 2 * a:.5f}; tightest l = {best}")

# ---- E. exact version of the H3 precision calculation (not the 20 000-repetition resampling) -
holds = {11.25: 1, 11.5: 2, 11.75: 5, 12.0: 14, 12.25: 18, 12.5: 20}  # docs/evidence/m14/masking/test.json
prev, dist = 0, {}
for L in [10 + 0.25 * i for i in range(21)]:
    c = holds.get(L, 0 if L < 11.25 else 20)
    if c > prev:
        dist[L] = (c - prev) / 20
        prev = c
bstar = 11.988676443422214


def p_confirm(l, u, lo_excl, hi_excl, shift):
    pA = sum(v for k, v in dist.items() if k + shift <= lo_excl + 0.25 + 1e-9)
    pU = sum(v for k, v in dist.items() if k + shift < hi_excl - 1e-9)
    pB, pC = pU - pA, 1 - pU
    return sum(comb(60, a) * comb(60 - a, b) * pA**a * pB**b * pC**(60 - a - b)
               for a in range(l) for b in range(60 - a + 1) if a + b >= u)


for s in (0, 0.75, 1.5):
    print(f"shift {s}: P(confirm H3) = {p_confirm(20, 41, bstar - 1, bstar + 1, s):.4f}")
pa = sum(v for k, v in dist.items() if k + 1.5 < bstar + 1 + 0.25 - 1e-9)
print("shift 1.5: P(refute H3) =", round(sum(comb(60, i) * pa**i * (1 - pa)**(60 - i) for i in range(20)), 4))

# ---- F. Clopper-Pearson budgets ----------------------------------------------------------------
for x, n in [(0, 480), (1, 480), (13, 480), (14, 480), (1, 320), (2, 320), (35, 1024), (6, 30)]:
    print(f"CP 99% upper {x}/{n}: {cp_upper(x, n) * 100:.5f}%")
print("35/1024 =", 35 / 1024 * 100, "% ; 35 + 6 =", 35 + 6)
for n, b, lab in [(480, .01, "invariants 1%"), (480, .05, "R2-R6 5%"), (320, .025, "R1 at 0 s 2.5%")]:
    print(lab, "max events inside the budget:", max(x for x in range(60) if cp_upper(x, n) <= b))

# ---- G. the estimator model (scripts/m14_masking_model.py) -------------------------------------
spec = importlib.util.spec_from_file_location("mm", "scripts/m14_masking_model.py")
mm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mm)
raw = subprocess.run(["git", "cat-file", "blob", "bec7b3f:exec/cases/m13/g3-registered.json"],
                     capture_output=True, check=True).stdout
case = json.loads(raw)
g = dict(case["controller"]["gains"])
dt = case["dt_s"] * case["sensors"]["control_period_steps"]
ev = case["sensors"]["gnss_period_cycles"]


def bstar_of(onset, gg):
    lo, hi = 0.0, 200.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if mm.model(mid, onset, gg, dt, ev)["rejected_cycles"] > 0 else (mid, hi)
    return hi


print("b* at 5 s:", bstar_of(5.0, g))
print("b* by rejection cycles 3, 5, 10:", [round(bstar_of(5.0, {**g, "altimeter_rejection_cycles": c}), 3) for c in (3, 5, 10)])
print("b* by threshold 1, 2, 3:", [round(bstar_of(5.0, {**g, "altimeter_residual_threshold_m": t}), 3) for t in (1.0, 2.0, 3.0)])
print("b* by onset:", {o: round(bstar_of(o, g), 3) for o in (0.01, 0.1, 1, 2, 5, 10, 15, 20)})
print("P2, rejection at 8 m by onset:", {o: mm.model(8.0, o, g, dt, ev)["rejected_cycles"] > 0 for o in mm.ONSETS})


def trace(bias, onset, gg, cycles=3000):
    limit, need = gg["altimeter_residual_threshold_m"], gg["altimeter_rejection_cycles"]
    e = v = 0.0
    exceed = 0
    peak, t_peak, first, readmit, was, plateau = 0.0, None, None, False, False, None
    for k in range(1, cycles):
        t = k * dt
        b = bias if t >= onset else 0.0
        e += v * dt
        if k % ev == 0:
            e += gg["gnss_position_gain"] * (b - e)
            v += gg["gnss_velocity_gain"] * (0 - v)
        r = -e
        if t >= onset and abs(r) > peak and first is None:
            peak, t_peak = abs(r), t - onset
        if abs(r) > limit:
            exceed += 1
            if exceed >= need:
                first = t - onset if first is None else first
                was = True
        else:
            exceed = 0
            readmit = readmit or was
            e += gg["altimeter_position_gain"] * r
            v += gg["altimeter_velocity_gain"] * r / dt
        if abs(t - onset - 20) < 1e-9:
            plateau = abs(r) / bias
    return peak, t_peak, first, readmit, plateau


for b in (5, 8, 9.72, 11.5, 12, 15, 30):
    pk, tp, fr, ra, pl = trace(b, 5.0, g)
    first = "none" if fr is None else f"+{fr:.2f} s"
    print(f"b={b}: peak {pk:.3f} ({pk / b:.3f} b) at +{tp:.2f} s; first rejection {first}; readmitted {ra}; |r|/b at +20 s {pl:.3f}")

# Last cycles of the model at b = 8 m, onset 5 s: velocity and position error oscillate with the 5-cycle GNSS period.
e = v = 0.0
hist = []
for k in range(1, 3000):
    t = k * dt
    b = 8.0 if t >= 5.0 else 0.0
    e += v * dt
    if k % ev == 0:
        e += g["gnss_position_gain"] * (b - e)
        v += g["gnss_velocity_gain"] * (0 - v)
    r = -e
    e += g["altimeter_position_gain"] * r
    v += g["altimeter_velocity_gain"] * r / dt
    hist.append((k % ev, round(v, 3), round(e, 3)))
print("model at 8 m, last 5 cycles (phase, v, e):", hist[-5:], "| prediction.json final_v_mps:", mm.model(8.0, 5.0, g, dt, ev)["final_v_mps"])
```

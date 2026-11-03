# Pré-registo do benchmark de falsificação do M14

Estado: **congelado antes da execução da divisão reservada**. A prova de ordem é o histórico do Git: este ficheiro, `exec/benchmarks/m14/benchmark.json` e os scripts entram num commit, `exec/benchmarks/m14/freeze.json` guarda o sha256 de cada um nesse commit, e a divisão reservada só corre depois, com `scripts/m14_benchmark.py --split heldout`, que recusa correr se algum ficheiro congelado mudar.

## Contexto e âmbito

O M13 existe só como proposta (`docs/m13-proposal.md`, PR #19). Nada do M13 foi implementado. O M14 implementa o mínimo da capacidade 2 do M13 (pesquisa de contraexemplos) para ter algo que se possa avaliar, e avalia-o aqui. Nenhum resultado deste benchmark altera o estado de aceitação do M10, que continua por aceitar. As sementes de avaliação e de reserva do M6 e do M10 não são usadas: o motor recusa-as antes de qualquer execução (`exec/src/seeds.rs`).

Isto é evidência de simulação idealizada. Não é evidência sobre um veículo real nem sobre certificação.

## Perguntas

- **P1 (primária, eficiência fora da amostra de desenvolvimento):** a estratégia `adaptive` (pesquisa local guiada pela margem, com recomeços) encontra a primeira violação com menos avaliações do que a amostragem uniforme `random`, em problemas com mecanismos de falha que nenhum desenvolvimento do M14 exercitou?
- **P2 (secundária, exploratória):** que fração das propriedades violáveis cada estratégia encontra dentro do orçamento (revocação contra o conjunto de referência)?
- **P3 (secundária, exploratória):** o teste clássico de pior caso, só cantos e centro da caixa, deixa passar violações que existem? Mede-se com as primeiras 2^d + 1 avaliações da estratégia `extremes`.
- **P4 (secundária, exploratória):** qual a distância ao caso nominal dos contraexemplos depois da redução?
- **P5 (verificação):** todas as avaliações registadas se recalculam byte a byte e todas as pesquisas se refazem com o mesmo resumo? Os domínios em processo coincidem com as linhas de comandos canónicas?
- **P6 (secundária, exploratória):** comparações `halton` e `extremes` contra `random`.

Só P1 tem regra de decisão confirmatória. Nenhuma secundária será promovida a primária depois de ver resultados.

## Problemas

Definidos em `exec/benchmarks/m14/benchmark.json`; casos base gerados por `scripts/m14_cases.py` a partir de ficheiros existentes, com os sha256 das fontes em `exec/cases/m14/sources.json`.

| Id | Divisão | Domínio | Caso base | Parâmetros |
| --- | --- | --- | --- | --- |
| D1 | desenvolvimento | terrestre | corredor junto à zona (`scenarios/m2/f-zone-nominal.json`) | ruído GPS, perda GPS, perda de pacotes |
| D2 | desenvolvimento | foguetão | M9.1 com `thrust_loss` | magnitude, início |
| H1 | reservada | terrestre | paragem nominal (`scenarios/m3/nominal-stop.json`) com `delayed_movement` | tick de início, atraso, probabilidade |
| H2 | reservada | terrestre | ultrapassagem `x_first` (`scenarios/m4/x-first-overshoot.json`) com `lost_movement` | tick de início, probabilidade |
| H3 | reservada | foguetão | M9.1 com `gnss_bias` | magnitude, início |
| H4 | reservada | foguetão | M9.1 com `imu_accel_bias` | magnitude, início |

Alvo por domínio, fixado por semântica antes de qualquer execução reservada: no terrestre, `safety` (invariantes de segurança e contratos temporais; o resultado da missão fica de fora). No foguetão, `any` (requisitos de aterragem R1 a R6 e o resultado). A escolha do foguetão foi feita em desenvolvimento: com `thrust_loss`, nenhum invariante de segurança S1 a S5 falhou em 484 execuções, e 2 falharam requisitos de aterragem. Se um problema reservado vier vazio com este alvo, aplica-se a regra 2a e o alvo não muda.

Objetivo da estratégia `adaptive`, fixo por domínio: `margin.restricted_zone_mm` a minimizar no terrestre e `requirement.R1_vertical_speed` a maximizar no foguetão. Nos problemas reservados terrestres a falha esperada é temporal, não geométrica. Isto é deliberado: testa se uma estratégia guiada por uma margem escolhida num mecanismo transfere para outro.

### O que foi visto em desenvolvimento

Para que a fronteira se possa auditar, estas são todas as combinações (caso, eixo) executadas nesta sessão antes do congelamento:

- corredor junto à zona: ruído GPS (0 a 600 mm), atraso máximo de observação (0 a 3 ticks), perda de pacotes (0 a 500 por mil) e perda GPS (0 a 300 por mil), em grelhas e em quatro pesquisas de ensaio;
- M9.1 com `thrust_loss`: magnitude e início, em grelha e nas pesquisas de desenvolvimento;
- nenhuma execução sobre `nominal-stop`, `x-first-overshoot`, `gnss_bias` ou `imu_accel_bias`.

Limitação de cegueira: os casos de H1 e H2 já foram explorados com falhas de atuador pelo motor adversarial do M5 e pelo M6 (`docs/adversarial-engine.md`, `docs/m6-controller-repair.md`). O projeto sabe que aí existem falhas. Os mecanismos são novos para o desenvolvimento das estratégias do M14, não para o projeto. Uma só pessoa (um só agente) desenhou as estratégias, os problemas e as regras. Isto é **pré-registo sem ocultação**.

## Estratégias e orçamento

- `random`: pontos e sementes uniformes.
- `halton`: sequência de Halton com deslocamento aleatório por repetição.
- `extremes`: os 2^d cantos e o centro, depois pontos uniformes.
- `adaptive`: episódios de 20 pontos uniformes seguidos de uma estratégia evolutiva (1+1) a partir do melhor ponto, passo inicial 0,3 em coordenadas unitárias, regra de um quinto, recomeço após 6 passos sem melhoria ou numa classe nova. A semente de simulação do ponto de partida mantém-se durante o episódio.

Orçamento de 200 avaliações por repetição, 30 repetições por estratégia e problema, redução com 40 avaliações por classe (até 8 classes). As repetições usam fluxos pseudoaleatórios independentes, derivados do identificador da pesquisa, por isso as comparações entre estratégias são **não emparelhadas**.

Afinação: os hiperparâmetros de `adaptive` foram escolhidos só em D2. Primeiro foram usados 8, 0,2 e 12; em D2 a estratégia precisou de mais avaliações do que `random` (mediana 32,5 contra 14). Foram testadas três variantes; a escolhida (20, 0,3, 6) teve mediana 10 num fluxo e 18 noutro, com `random` em 14. A diferença entre fluxos mostra que a vantagem observada em desenvolvimento é ruído. Não houve mais afinação.

## Sementes e governação dos dados

| Uso | Sementes de simulação | Semente da pesquisa | Sementes da grelha |
| --- | --- | --- | --- |
| Desenvolvimento | 30000 a 39999 | 14001 | 31000 a 31003 |
| Reservada | 50000 a 59999 | 14002 | 51000 a 51003 |

Nenhuma destas sementes está nos conjuntos protegidos (foguetão 3000 a 3099 e 6000 a 6099; terrestre 100 a 129, 201 a 212 e as 12 sementes da confirmação final do M6). A divisão reservada corre uma vez, depois do congelamento. Qualquer nova execução, por defeito ou por alteração de um ficheiro congelado, fica declarada no relatório com o motivo, e o resultado da primeira execução também é publicado.

## Conjunto de referência

Para cada problema, uma grelha exaustiva (estratégia `grid`): 9 níveis por parâmetro nos problemas terrestres de três parâmetros, 13 em H2, 15 nos do foguetão, cada ponto com as quatro sementes da grelha da divisão. O conjunto de referência de propriedades é a união das propriedades violadas na grelha e em qualquer repetição de qualquer estratégia. A prevalência da grelha é reportada com intervalo de Clopper-Pearson a 95 %. A grelha corre como parte da avaliação, depois do congelamento.

## Métricas e análise

- **Métrica primária:** avaliações até à primeira violação em cada repetição, censuradas em 201 quando o orçamento não encontra nenhuma.
- **Teste primário:** Mann-Whitney bilateral, aproximação normal com correção de empates e sem correção de continuidade, `adaptive` contra `random`, em cada problema reservado elegível. Ajuste de Holm sobre esses problemas, alfa 0,05.
- **Efeito:** mediana de `random` menos mediana de `adaptive`, com intervalo bootstrap de percentis a 95 %, 10 000 reamostragens, semente 14003 (Mersenne Twister do Python).
- **Regra 2a:** um problema sem nenhuma violação na referência nem em nenhuma pesquisa é declarado nulo e fica fora da análise primária.
- **Regra 2b:** se mais de 90 % das repetições de ambas as estratégias violarem na avaliação 1, o problema é um empate declarado e fica fora do teste.
- **Decisão:** `adaptive` é melhor num problema se o p de Holm for menor do que 0,05 e o intervalo do efeito estiver todo acima de zero; pior se o p de Holm for menor do que 0,05 e o intervalo estiver todo abaixo de zero. A alegação «a pesquisa adaptativa generaliza para mecanismos não vistos» é **suportada** só se `adaptive` for melhor em pelo menos 3 dos 4 problemas reservados e pior em nenhum. Caso contrário é **não suportada**. Um resultado nulo é um resultado aceitável e será publicado como tal.
- **Potência:** com 30 repetições por braço, o teste de Mann-Whitney deteta, de forma aproximada, um deslocamento de cerca de 0,75 desvios-padrão com potência de 80 % a alfa 0,05 sem ajuste. Com Holm sobre quatro problemas a potência por problema é menor. Efeitos pequenos podem passar sem deteção.
- **Previsão registada:** com base no desenvolvimento, prevê-se que a alegação de generalização **não** seja suportada.

As funções estatísticas estão em `scripts/m14_stats.py` e são verificadas por `tests/test_m14_stats.py`: valores calculáveis à mão, o teste exato de permutação e os casos de Holm do ficheiro de referência que `exec/tests/stats_reference.rs` também verifica.

## Verificação

Cada diretório de pesquisa é recalculado por `vv-exec search-verify`: cada avaliação é executada de novo a partir do seu ponto e da sua semente e cada repetição é pesquisada de novo de raiz. Os pontos ficam numa grelha inteira (`q / 2^32`), para que um ponto registado seja lido de volta sem arredondamento. Para cada problema, uma pequena experiência factorial passa pelo portão de equivalência do `vv-exec` contra `vv-lab run-m4` ou `vv-rocket land`. Uma falha de verificação ou de paridade faz falhar a execução do benchmark.

## O que este benchmark não mostra

- Não compara com ferramentas externas (S-TaLiRo, Breach, Scenic, VerifAI). As estratégias são implementações próprias de famílias conhecidas.
- Os problemas têm 2 ou 3 dimensões. Em dimensões maiores o comportamento relativo pode mudar.
- O orçamento é pequeno porque as simulações são baratas; o benchmark não mede custo em modelos caros.
- A revocação depende de um conjunto de referência finito; uma propriedade que nem a grelha nem as pesquisas encontraram não conta.

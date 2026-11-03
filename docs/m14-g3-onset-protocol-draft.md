# Protocolo de confirmação do mascaramento sob viés GNSS tardio (rascunho)

Estado: **rascunho para decisão do responsável. Não congelado, não executado.** As sementes 44000 a 44999 continuam recusadas pelo motor (`INVESTIGATION_PROTECTED` em `exec/src/investigate.rs`) até o responsável aprovar este protocolo, o congelar e autorizar a alteração que as liberta.

Este protocolo não altera o critério G3 do M9.1. O G3 foi registado e suportado com o viés presente desde 0 s e continua como foi registado. Aqui formula-se uma hipótese nova e independente sobre o instante de início do viés.

## Origem

- A investigação M13 da alegação `g3-onset` (`exec/claims/m13/g3-onset.json`) refutou a extensão do G3 a inícios entre 0 e 20 s, com sementes de desenvolvimento 42000 a 43999, e apoiou o mecanismo de mascaramento (`docs/m13-discovery-lab.md`).
- Um modelo independente do erro vertical do estimador, sem parâmetros ajustados, previu a magnitude crítica b* = 11,99 m (`docs/evidence/m14/masking/prediction.json`, commit `73c9ff5`). O simulador, com as sementes 47000 a 47019, deu b50 = 11,89 m (`docs/evidence/m14/masking/test.json`).
- Tudo isto é exploratório. O autor viu a transição grosseira entre 10 e 15 m antes de escrever o modelo, e as hipóteses e as mitigações foram escritas depois de execuções manuais com as sementes 41000 a 41009.

## Hipóteses a confirmar

- **C1, mascaramento.** Com a política `guarded` do M9.1 e um viés GNSS de magnitude m que começa depois da primeira medida GNSS (início entre 0,01 e 20 s), R1 falha quando m está abaixo de b* − 1 m e cumpre-se quando m está acima de b* + 1 m, com b* = 11,99 m fixado antes da execução.
- **C2, mecanismo.** Em cada execução de C1, R1 cumpre-se se e só se o estimador rejeitou o altímetro em algum instante.
- **C3, mitigação.** Com o limiar de rejeição do altímetro a 1 m, R1 cumpre-se em todo o envelope de C1, e nenhuma família de regressão ganha uma violação de segurança nova face ao sistema sem mitigação nos mesmos pontos e sementes.

## Desenho

- Sementes: 44000 a 44999, nunca executadas. Divisão fixa: 44000 a 44299 para C1 e C2, 44300 a 44599 para C3 no envelope, 44600 a 44999 para as famílias de regressão de C3.
- C1 e C2: grelha de 8 inícios (0,01; 0,1; 1; 2; 5; 10; 15; 20 s) por 2 bandas de magnitude (m sorteada uniformemente em [5; b* − 1] e em [b* + 1; 30]), 30 sementes por célula: 480 execuções.
- C3: a mesma grelha com a mitigação, 30 sementes por célula, e as 7 famílias de regressão de `g3-onset.json` com 200 pontos Halton e uma semente cada, com e sem a mitigação: 480 + 2800 execuções.

## Critérios, fixados antes da execução

- C1 é suportada se R1 falhar em 30 de 30 execuções de cada célula da banda baixa e se cumprir em 30 de 30 de cada célula da banda alta. A hipótese é determinística, por isso uma única execução em sentido contrário refuta-a. O relatório dá ainda o intervalo de Clopper-Pearson a 95 % de cada célula (com 30 de 30, a taxa fica entre 0,884 e 1), que é o que estas 30 sementes permitem dizer sobre a taxa.
- C2 é suportada se não houver nenhuma execução com R1 cumprido sem rejeição, nem rejeição com R1 falhado.
- C3 é suportada se R1 se cumprir em todas as execuções mitigadas do envelope e o número de pares com violação de segurança nova nas famílias for 0, com o limite superior de Clopper-Pearson a 95 % da taxa reportado (com 1400 pares, cerca de 0,26 %).
- Qualquer outro resultado é registado como não suportado, com a contagem observada. Não há análise intermédia nem paragem antecipada.

## Congelamento proposto

Antes da execução, um ficheiro de congelamento com o sha256 deste protocolo, de `exec/claims/m13/g3-onset.json`, de `exec/cases/m13/*.json`, de `scripts/m14_masking_model.py`, da previsão e do executável `vv-exec` usado, e o commit. A execução só começa depois de o ficheiro estar num commit. O protocolo e o congelamento ficam públicos com o resultado, seja ele qual for.

## Limitações

- Simulação idealizada e um só veículo. Uma confirmação aqui não diz nada sobre um veículo real.
- O revisor deste protocolo foi um agente, não uma revisão humana independente. Antes de congelar, recomenda-se uma leitura por um engenheiro que não participou no desenvolvimento.

## Decisões do responsável

1. Aprovar, alterar ou rejeitar C1, C2 e C3.
2. Autorizar o congelamento e a libertação das sementes 44000 a 44999 para esta execução e só para ela.

# M10: encerramento da investigação da arquitetura de navegação

## Decisão

Em 2026-11-24 o responsável decidiu **encerrar a investigação atual da arquitetura M10 como «não avançar»**. Fica preservada toda a evidência, incluindo os critérios falhados, o excesso de orçamento e o passo omitido. Não se constrói a arquitetura C e não se inicia outra reformulação no âmbito do M19. O ramo `research/m10-redesign` continua isolado como investigação e não é para fusão. As revisões de agentes listadas abaixo são pareceres, não revisão humana.

## Cadeia de evidência

| Passo | Commit ou ficheiro | Conteúdo |
| --- | --- | --- |
| Revisão independente (decisões A e C) | `b733d14`, `docs/m10-independent-review.md`, `docs/evidence/m10-dev/independent-review/` | A (paridade de taxas) e C (perseguição limitada) refutadas como propostas; P4 com potência 0,53 |
| Dossiê de decisão | `d3118f2`, `docs/m10-decision-dossier.md` | Regressões de B+ face a `robust` e `guarded`, binários misturados |
| Pré-registo | `41a91c5`, `e4944e1` (correções), `docs/m10-redesign-preregistration.md` | Hipótese, porta de ambiguidade atrás de uma bandeira, matriz, critérios, orçamento |
| Diagnóstico (antes do código) | `d350177`, `docs/evidence/m10-redesign/diagnostic/` | 160 execuções, sementes 5000 a 5019: dos 64 U de B+ a 0,5 m/s, 58 sem isolamento, 6 com isolamento errado, 0 com isolamento correto tardio |
| Adenda 1 | `26ff91d` | Leitura estrita dos limites, ruído 1,5 vezes na cláusula 1, sementes de teste 5090 e 5091, cláusula 2 vinculativa onde B não está saturado, orçamento de 45 000 |
| Código da bandeira | `91c9981` | `ambiguity_gate`, desligada por omissão |
| Adenda 2 | `1ce8d60` | Validação do ruído 1,5 vezes (antes da etapa 3) |
| Simulador e planos | `6419587` | Aceita os quatro sigmas a 1,5 vezes em casos v2; planos `ramps`, `ramps15`, `onset` |
| Executor | `165995b` | `scripts/m10_redesign_run.py` |
| Resultados | `c02422a`, `72101ab` (correções), `docs/m10-redesign-results.md`, `docs/evidence/m10-redesign/results/` | Veredicto e tabelas |
| Pareceres de agentes | `01cd683`, `docs/evidence/m19/reviews/01-fable-m10-redesign-scope-decision.md`, `docs/evidence/m19/reviews/02-adversarial-review-of-m10-no-go-result.md` | Consulta ao Fable sobre o âmbito; revisão adversária do resultado |

## Resultado

Uma única reformulação (porta de ambiguidade: exoneração da IMU válida em duas âncoras mais rejeição por NIS enquanto um CUSUM vertical passa `h/4` sem isolamento), só com sementes de desenvolvimento, um só binário (SHA-256 `918479ef…`, `source_sha256` `973400ab…`), 44 820 execuções da matriz.

**V1 não cumprido; V2 não cumprido (previsto). Veredicto: não avançar.**

Critérios falhados:

- **S1 e cláusula 1:** 6 execuções de B+G com falha de alerta da velocidade horizontal (4 em G1, 2 em G1 com ruído 1,5 vezes), todas com isolamento errado. B tem 0; B+ tem 60 em G1, 1 em M1 e 5 em G1 com ruído.
- **S2:** 33 execuções com isolamento errado em 1 280 (G1 a 0,3 e 0,5 m/s), contra no máximo 5 exigidas; B+ tem 110, uma redução de 70 % contra 90 % exigidos.
- **S5 e cláusula 3:** 26 execuções com isolamento errado em 2 400 (M3, ruído 1,5 vezes) e 23 em 640 (G1 com ruído); exigido: zero. B+ tem 46 e 71.
- **V2:** `gnss_bias` e o par `gnss_bias` mais `altimeter_dropout` contra `guarded` (U 100 contra 1 e 14); o par `altimeter_bias` mais `gnss_dropout` contra `robust` e `guarded` (27 contra 8). Regressões herdadas, fora do alcance da reformulação.

Critérios cumpridos: cláusula 2 (não disparou; vácua a 0,3 m/s, onde B+G mantém 27 isolamentos errados em 640), S4, S6, S7. A porta reduz o U de B+ a 0,5 m/s de 544 para 47 em 640 (B: 54) e não perde recuperações, mas não elimina o isolamento errado, a rejeição fica aberta no toque em 820 de 2 560 execuções de G1, e a paridade isola mal com ruído 1,5 vezes mesmo sem falha de taxa (B+ 46 em 2 400).

Revisão adversária (`02-adversarial-review-of-m10-no-go-result.md`): **o resultado mantém-se, com correções ao texto**, aplicadas em `72101ab`. Recalculou o veredicto a partir de `records.jsonl.gz` e não encontrou alterações depois de ver resultados nem sementes fora de 5000 a 5099.

## Desvios, exatamente

1. **Orçamento.** O limite era 45 000 execuções e a matriz planeada somava 44 820. Foi excedido, no total cerca de **52 500**: 44 820 da matriz (etapa 0 com 1 400, etapas 1 a 5 com 43 420) mais 4 800 de repetição de B+G (etapas «2g» e «3g», para gravar os comprimentos de rejeição; evitável) mais 2 800 de duas execuções descartadas da etapa 0 (1 400 com o binário `8b6a259c…` anterior à adenda 2; 1 400 com um modelo com a bandeira escrita explicitamente) mais 64 de um ensaio das sondas. O diagnóstico de 160 execuções é à parte. Excesso sobre o limite: cerca de 7 500. O orquestrador reconheceu-o como desvio declarado.
2. **Alteração de `scripts/m10_campaign.py` depois das etapas 1 a 5** (às 19:13:16; a etapa 5 terminou às 19:12:21), para registar o campo `gate`. Só as repetições «2g» e «3g» a usaram; as repetições deram classe, isolamento e `hv` idênticos aos originais.
3. **Adenda 2 (alteração do simulador).** O simulador recusava sigmas de sensor diferentes dos registados. A validação passou a aceitar, em casos v2, os quatro sigmas todos iguais ao registado ou todos a 1,5 vezes. Prevista em 5.2 do pré-registo, registada antes da etapa 3; só aceita mais um caso.
4. **Passo 2 da estratégia («B+ sem paridade») não feito.** Não existe bandeira que desligue a paridade (o isolamento é chamado sempre no braço B+); produzi-lo exigiria nova alteração de código, fora do âmbito do diagnóstico. O passo 1 foi feito só para uma célula (0,5 m/s, 20 sementes) e um traço, não para as sondas `ramp` e `ignition` completas.
5. **Comparações de repetição limitadas:** a etapa 0 contra a etapa 2 comparou só a classe física; a repetição de B+G comparou classe, isolamento e `hv`.

## O que fica por testar

- A ablação do mecanismo: exoneração em duas âncoras contra rejeição por NIS (um só braço; uma ablação seria uma segunda tentativa).
- As três falhas de invariante S2 de `gnss_horizontal_bias` (sementes 5084, 5086, 5093), iguais em B+ e B+G (B tem duas), por explicar.
- O mecanismo do isolamento errado com ruído 1,5 vezes sem falha de taxa.
- A saída da rejeição da porta.
- As alternativas descartadas no pré-registo (persistência, limiares mais largos, chão de magnitude, reprocessamento com NIS), os testes 4 a 8 e 11 a 13 da revisão e outros ruídos, veículos e perfis.
- As sementes de avaliação (3000 a 3099) e de reserva (6000 a 6099), que nunca foram usadas.

## O que não está autorizado

- Construir a arquitetura C.
- Iniciar outra reformulação do M10 no âmbito do M19.
- Usar as sementes 3000 a 3099 e 6000 a 6099, e ainda 44000 a 44999 e 50000 a 59999.
- Congelar a configuração: `m10-freeze.json` não existe e não se cria.
- Integrar a PR #15 ou este ramo em `main` ou no Studio sem decisão nova do responsável. (O envio do ramo para o GitHub, como cópia de segurança, foi autorizado pelo responsável em 2026-11-24.)

## Ponteiros

- Resultados e relatório: `docs/m10-redesign-results.md`; pré-registo e adendas: `docs/m10-redesign-preregistration.md` (secções 13 e 14).
- Diagnóstico: `docs/evidence/m10-redesign/diagnostic/` (`summary.md`, `records.json`).
- Resultados: `docs/evidence/m10-redesign/results/` (`analysis.md`, `analysis.json`, `records.jsonl.gz`, `run-info-*.json`) e modelos em `docs/evidence/m10-redesign/templates/`.
- Código de execução e análise: `scripts/m10_redesign_run.py`, `scripts/m10_redesign_analysis.py`, `scripts/m10_redesign_diagnostic.py`, `scripts/m10_adversarial_probe.py`.
- Revisões: `docs/evidence/m19/reviews/01-fable-m10-redesign-scope-decision.md`, `docs/evidence/m19/reviews/02-adversarial-review-of-m10-no-go-result.md`; evidência anterior em `docs/evidence/m10-dev/` e `docs/m10-independent-review.md`.

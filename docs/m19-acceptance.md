# M19: matriz de aceitação

Data: 2026-11-23. Base: `main` em `bec7b3f` (fonte da Studio 0.18.1 instalada). Nada foi enviado, integrado, instalado ou publicado. Todos os ramos são locais.

As categorias desta matriz não são intercambiáveis:

- **Facto verificado:** resultado de um comando, teste ou recomputação que se pode repetir.
- **Juízo de especialista:** avaliação feita por agentes (revisores independentes, Fable 5.2). **Não é revisão humana nem estudo com pessoas.**
- **Alegação por resolver:** afirmação cuja confirmação exige execução protegida, revisão humana ou decisão do responsável.
- **Teste humano não realizado:** portão que só pessoas podem fechar.
- **Não verificado:** comportamento coberto só por testes estruturais ou por leitura de código, sem observação no ecrã nem execução.

Os relatórios finais de todas as revisões e consultas por agentes estão em `docs/evidence/m19/reviews/` de cada ramo.

## Ramos

| Trabalho | Ramo |
| --- | --- |
| Estratégia e pacotes M19 | `docs/m19-programme` |
| M19.1 honestidade | `fix/m19.1-honesty` |
| M19.2 crença contra verdade | `prototype/m19.2-belief-truth` |
| Candidato G3 corrigido | `research/g3-corrected-candidate` |
| Reformulação M10 | `research/m10-redesign` |

## 1. Estratégia e pacotes de documentos

| Item | Categoria | Estado | Evidência |
| --- | --- | --- | --- |
| Correções da primeira revisão (6 do pacote G3, 10 do conjunto de utilização) | Juízo de especialista | Aplicadas e conferidas por revisor | Re-revisão: G3 5 de 6 e 1 parcial, utilização 8 de 10 e 2 parciais; parciais corrigidas depois |
| 41 hashes fixados no pacote G3 conferem com os blobs | Facto verificado (repetível com `git cat-file`) | Feito | Recomputação independente |
| Segunda re-revisão independente | Juízo de especialista | ACCEPT WITH FIXES; correções aplicadas | Revisor novo |
| Estratégia regista as oito decisões do responsável | Facto verificado | Feito | `docs/m19-programme-strategy.md` |
| Conjunto de utilização centrado em engenheiros e revisores técnicos; acesso só presencial; aviso de privacidade antes da seleção | Facto verificado | Feito | `docs/usability/` |
| Revisão humana externa do pacote G3 | Teste humano não realizado | Aberto | Revisor indisponível |

## 2. M19.1 resultados honestos

| Item | Categoria | Estado | Evidência |
| --- | --- | --- | --- |
| Estado das regras de segurança neutro («held»), incluindo linhas de invariantes | Facto verificado no leitor, Library, Compare e pílulas do Lab; Não verificado no Flight console, tabela do Lab, Runs e Discover | Feito no código | Testes Node e Python; capturas antes e depois |
| Linha falhada ou não avaliada nunca contada como cumprida | Facto verificado | Feito | `noFailureSentence`, `missionTone`, testes |
| Cláusula falhada de `mission_completion` explicada na interface | Facto verificado | Feito na interface | `completionFacts`; registo terrestre inalterado |
| Pílulas a 1024x640 com nome completo e contagem exata de condições | Facto verificado | Feito | Captura a 1024x640 |
| Sem pluma depois da última amostra; velocidade de contacto com fonte declarada | Facto verificado | Feito | `plumeLengthAt` e teste |
| Integridade da evidência visualmente distinta do veredicto da alegação | Facto verificado | Feito | Seguimento do percurso de especialista |
| «To goal» e «Confidence» visíveis a 720 px ou menos de altura | Facto verificado | Feito | Captura a 1024x640 |
| 542 valores que não podem mudar (hashes de fonte, evidência, registos de demonstração) | Facto verificado | 542 de 542 idênticos | `docs/evidence/m19/honesty/hash-comparison.json` |
| Verificação de `AGENTS.md` | Facto verificado | Verde, com limites | fmt, clippy, `cargo test` (138 e 168), Python 468 OK com 92 testes saltados (45 com `VV_GODOT`), campanha (87 casos). Os percursos antigos da Studio não foram repetidos depois das correções das revisões |
| Texto «safe» das demonstrações e cláusula no registo terrestre | Alegação por resolver | Proposto, não feito | Muda hashes de anfitrião e identificadores de corridas |
| Lista do Discover, tabela de comparação do Lab, anel de foco das pílulas | Não verificado | Só testes estruturais | Precisam de investigação guardada ou de corrida de sementes |
| Revisões independentes (duas rondas: ramo e seguimento; as correções menores finais não tiveram revisão própria) | Juízo de especialista | ACCEPT WITH FIXES nas duas; correções aplicadas | `docs/evidence/m19/reviews/` do ramo M19.1 |
| **Quebra:** os percursos antigos da Studio, corridos com uma compilação que partilhava o identificador `org.vvlab.studio`, escreveram em todo o perfil WebView2 da 0.18.1 instalada (`%LOCALAPPDATA%\org.vvlab.studio\EBWebView`): 203 de 1302 entradas datadas de 23/11 entre 18:55 e 19:01, incluindo History, Preferences, Local State, Web Data, Local Storage, Session Storage e Code Cache | Facto verificado | Declarada; nada limpo; **decisão do responsável** | Não existe listagem anterior à quebra, por isso não há restauro possível: apagar `EBWebView` ou deixar. Inspeção só de leitura do `Local Storage`: só registos internos VERSION do Chromium, nenhuma chave da aplicação; a interface 0.18.1 não usa armazenamento web. Dano prático provavelmente baixo (juízo, não facto). As capturas seguintes usaram identificador próprio, com listagens antes e depois idênticas |
| Uso por pessoas, leitor de ecrã, contraste medido por ferramenta | Teste humano não realizado | Aberto | |

## 3. M19.2 crença contra verdade

| Item | Categoria | Estado | Evidência |
| --- | --- | --- | --- |
| Só dados gravados (semente 5002, `guarded`, `gnss_bias` 15 m); nada simulado de novo | Facto verificado | Feito | `extract.py` verifica o sha256 das entradas |
| Proveniência: a árvore em `3962482` reproduz o `source_sha256` `12b276cb`; só `landing_model.rs` difere da atual; o teste de reprodução por versão anterior passa | Facto verificado | Feito | `cargo-earlier-build.txt` |
| Cada número mostrado liga a um caminho do registo ou a uma derivação nomeada | Facto verificado | 73 testes | `tests/test_m19_belief_truth.py` |
| Observações nunca unidas; ligação entre amostras marcada como não-dado e quebrada no início da falha | Facto verificado | Feito | Testes |
| Ausência de covariância declarada; nenhum envelope inventado | Facto verificado | Feito | |
| Renderizador SVG 2D; Three.js sem vantagem material | Juízo de especialista | Decidido | Fable 5.2, três consultas com a mesma conclusão |
| Compreensão contra chave fixada antes de construir (sha256 `fc9993ef…`) | Juízo de especialista | Iteração 1: 15,5/20 (falha), armadilhas 12,5/16. Iteração 2: 19,5/20 (passa; 17,0 em leitura estrita), armadilhas 15,5/16. Zero armadilhas centrais | `docs/evidence/m19/belief-truth/evaluation/`. Um só respondente por iteração |
| Crítica Fable 5.2 da iteração 2 | Juízo de especialista | Adotar como candidato ao portão humano, sem instalar | |
| Passagem final de correções depois da avaliação da iteração 2 (velocidade horizontal no plano do bocal para R2, velocidade GNSS, reescrita dos cartões, etiquetas, CSS) | Alegação por resolver | **Decisão do responsável:** conta ou não como terceira iteração substantiva | Verificação por agentes do artefacto final: 18,5/20 (passa; 15,5 em leitura estrita, falha), armadilhas 14,5/16, zero armadilhas centrais, nenhuma afirmação errada; dois defeitos menores de rótulo deixados por limite de iterações (`evaluation/`) |
| **Recomendação final** | Juízo de especialista | **Não refutada; mantém-se candidata ao portão humano.** Não integrar na Studio antes do teste com pessoas | A estratégia diz que revisões por agentes só podem refutar ou manter a vista como candidata. Limites: um respondente por iteração; a iteração 2 foi construída sabendo que perguntas falharam; sem braço de comparação com a vista atual da Studio |
| Teste cego de compreensão com 2 de 3 revisores novos e participantes | Teste humano não realizado | Aberto | Critério de refutação da estratégia |

## 4. Candidato G3 corrigido

Rótulo: **CORRECTED CANDIDATE — NOT HUMAN-REVIEWED — NOT APPROVED FOR EXECUTION.** (O carácter U+2014 do rótulo é uma exceção imposta pelo responsável.)

| Item | Categoria | Estado | Evidência |
| --- | --- | --- | --- |
| Hash de fonte atual fixado (`295a45b2…`; o protocolo M15 tinha `12b276cb…`; só `landing_model.rs` difere) | Facto verificado | Feito | Recomputado por três revisores |
| 63 contra 69: 63 é o mínimo a 0,01/7 e 69 a 0,01/14; S4 e S5 usam 0,01/7 | Facto verificado | Resolvido | `calculations.json` |
| Inícios 0,01 s e 0,1 s com a mesma história de sensores; 0,01 s removido; 7 condições | Facto verificado por leitura de código | Feito | `landing_sim.rs:189,210-211` |
| Potência 0,064: a taxa 0,93 nunca foi registada; 294 de 294 execuções registadas a 0 s cumprem R1 | Facto verificado | Investigado | Evidência M9.1, M13, M14 |
| Novo desenho: Holm sobre {H1a, H2, H3}; portões em série (McNemar; mecanismo S4 a S6 para «mascaramento»; H1b agrupado com n = 308) | Juízo de especialista | Proposto | Fable 5.2 consultado |
| Potência conjunta no cenário moderado: 0,755 (alocação A) e 0,865 (alocação B) | Facto verificado (aritmética) | Ilustrativa | Recomputação independente |
| Mapa semente → condição: 896 sementes, sem sobreposição; reserva 44920 a 44999 intacta | Facto verificado | Feito | Enumeração independente |
| Sobreposição estrutural de fluxos SplitMix64: 288 pares entre 44000-44919 e sementes vistas, 258 sementes afetadas; propriedade de todo o repositório | Facto verificado (aritmética) | **Decisão do responsável** | Aceitar e declarar; bloco limpo 81000-81919; ou excluir (inviável para H1a) |
| Alocação de sementes A ou B | Alegação por resolver | **Decisão do responsável** | Secção «Por decidir» do candidato |
| Revisões metodológica, adversária e segunda revisão depois das correções | Juízo de especialista | ACCEPT WITH FIXES em todas; correções aplicadas | |
| Cálculos reproduzíveis sem simulador | Facto verificado | 44 testes; `--check` idêntico | `scripts/m19_g3_power.py` |
| Nenhuma simulação com 44000 a 44999 | Facto verificado | Cumprido | Só aritmética do PRNG; um teste gera saídas explícitas do gerador para os estados de duas sementes do intervalo. Se isto conta como «uso» é leitura do responsável |
| Revisão humana externa; aprovação para execução | Teste humano não realizado | Aberto | |

## 5. M10

| Item | Categoria | Estado | Evidência |
| --- | --- | --- | --- |
| Rejeição de A (paridade) suportada pela evidência; rejeição de C só como «não adotar» | Juízo de especialista | Revisto | `docs/m10-redesign-preregistration.md`, secção 1 |
| Diagnóstico antes da reformulação (160 execuções, 5000 a 5019): 58 de 64 falhas sem isolamento, ainda a assimilar o recetor | Facto verificado | Feito | `docs/evidence/m10-redesign/diagnostic/` |
| Pré-registo e adendas antes da primeira execução com o portão ligado | Facto verificado | Confirmado pela revisão adversária | Ordem dos commits |
| Uma reformulação (`ambiguity_gate`, desligada por omissão), um binário, só 5000 a 5099 | Facto verificado | Feito | `records.jsonl.gz` |
| Veredicto | Facto verificado | **Não avançar.** V1 falha (S1, S2, S5); V2 falha como previsto | Recomputado pela revisão adversária |
| Desvios: limite de execuções excedido (cerca de 52 500 contra 45 000), edição de script a meio, alteração ao simulador para ruído 1,5x; passo 2 da estratégia («B+ sem paridade») não feito porque o código não permite desligar a paridade | Facto verificado | Declarados | A revisão adversária considera-os desvios de orçamento e de plano, não ameaças à validade (juízo) |
| Por testar: ablação do mecanismo, 3 falhas S2 em `gnss_horizontal_bias` (5084, 5086, 5093), mecanismo dos isolamentos errados a 1,5x, sementes de avaliação | Alegação por resolver | Aberto | Nova tentativa exige novo mandato |
| PR #15 não integrado; sem `m10-freeze.json`; 3000 a 3099 e 6000 a 6099 intactas | Facto verificado | Cumprido | |

## 6. Utilização sem participantes

| Item | Categoria | Estado | Evidência |
| --- | --- | --- | --- |
| Tarefas, perguntas, chaves, rubricas e formulários prontos | Facto verificado | Feito | `docs/usability/` |
| Percurso cognitivo e avaliação heurística: 43 achados, 15 de gravidade 3 | Juízo de especialista | Feito | `docs/usability/expert-walkthrough.md` |
| Verificações automáticas (contraste por tokens, marcação, testes Node) | Facto verificado | Feito | `docs/evidence/m19/usability/` |
| Três chaves corrigidas (T7, Q5d, Q5b) | Facto verificado | Feito | `tasks.md` |
| Participantes, consentimentos, observações, taxas | Teste humano não realizado | **Nenhum inventado; portão aberto** | |

## 7. Segurança e execução

| Item | Categoria | Estado |
| --- | --- | --- |
| Studio 0.18.1 instalada: programa, módulos, registos, preferências e biblioteca não alterados | Facto verificado | Cumprido |
| Perfil WebView2 da 0.18.1 escrito por várias suítes durante cerca de seis minutos (ver secção 2) | Facto verificado | **Quebra declarada**; apagar ou deixar é decisão do responsável |
| Serviços, rede, acesso remoto, tarefas do sistema | Facto verificado | Não tocados |
| Sementes protegidas só aparecem como texto de proibição ou de intervalo. Sementes usadas em execuções: M10 5000 a 5099; M19.1 42, 5000, 5002, 5017; M19.2 5002 (registo existente); G3 nenhuma | Facto verificado | Cumprido |
| Envio, PR, integração, instalação, publicação | Facto verificado | Nada feito |

## Decisões pedidas ao responsável

1. Perfil WebView2 da 0.18.1: apagar `EBWebView` ou deixar.
2. M19.2: se a passagem final conta como terceira iteração; aceitar «não refutada, candidata ao portão humano».
3. Candidato G3: tratamento da sobreposição de fluxos; alocação A ou B; se a aritmética do PRNG sobre sementes protegidas é aceitável.
4. M10: fechar como «não avançar», reconhecendo o excesso de execuções e o passo saltado.
5. M19.1: abrir PR; propostas que mudam hashes (texto «safe», cláusula no registo terrestre).
6. Envio dos ramos locais e abertura de PRs.

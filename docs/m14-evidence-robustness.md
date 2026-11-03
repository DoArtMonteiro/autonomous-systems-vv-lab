# M14: robustez, generalização e reprodutibilidade das conclusões

Estado: **aceitação de engenharia proposta; aceitação científica não pedida**. Resultados de simulação idealizada, sementes de desenvolvimento e uma divisão reservada própria do M14. Nenhuma alegação sobre veículos reais ou certificação. O M10 continua por aceitar e nada aqui o altera.

## Resumo

O M13 ficou como proposta (`docs/m13-proposal.md`); não havia uma capacidade de descoberta de contraexemplos para avaliar. O M14 implementou o mínimo dessa capacidade dentro do `vv-exec` e pôs à prova três coisas: a arquitetura funciona fora do foguetão? A pesquisa guiada encontra falhas melhor do que a amostragem simples? As conclusões publicadas resistem quando se mexe num pressuposto?

- **Generalização da arquitetura: sim, com quatro correções.** O veículo terrestre do M1 a M6 corre em processo no `vv-exec` com bytes iguais aos de `vv-lab run-m4` (38 casos comparados, 0 diferenças). Para isso foi preciso tirar do código partilhado quatro pressupostos do foguetão (ver «Generalização»).
- **Pesquisa adaptativa: a alegação de generalização não é suportada.** No benchmark pré-registado, a pesquisa local guiada pela margem não foi melhor do que a amostragem uniforme em nenhum dos 4 problemas reservados (0 melhores, 0 piores, p de Holm entre 0,14 e 1). Era a previsão registada antes da execução.
- **O teste de cantos falha onde as falhas são raras.** Com prevalência de 0,2 % (H4), avaliar só os cantos e o centro da caixa não encontrou nenhuma violação em 22 de 30 repetições; em D2 (1,3 %), em 20 de 30.
- **A grelha «exaustiva» não é completa.** Em três problemas, a pesquisa aleatória encontrou propriedades violadas que a grelha de 900 pontos nunca atingiu, porque a grelha usa 4 sementes e a pesquisa sorteia entre 10 000.
- **Uma conclusão sem margem.** No corredor junto à zona restrita (`scenarios/m2/f-zone-nominal.json`), a segurança mantém-se com ruído GPS de 0 mm (100 de 100) e cai para 61 de 100 com 1 mm. A causa está identificada no código e num traço.
- **Uma conclusão publicada com âmbito mais estreito do que parece.** O critério G3 do M9.1 («`guarded` cumpre R1 com `gnss_bias` em pelo menos 27 de 30») foi registado com o viés presente desde 0 s. Com o mesmo viés de 5 ou 10 m a começar em 2, 5 ou 10 s, R1 falha em 30 de 30. Isto não refuta o G3 como foi registado; mostra que depende de um pressuposto sobre o instante da falha que ninguém tinha posto à prova.

## O problema

Uma campanha de simulação pode passar milhares de vezes e esconder um erro de modelação, porque só explora o que alguém se lembrou de variar. Um gerador de contraexemplos pode parecer bom porque foi afinado nos casos que o autor conhecia. Uma alegação pode parecer sólida porque o pressuposto de que depende nunca foi variado. O M14 ataca estes três riscos com instrumentos que se podem recalcular.

## O que foi construído

Tudo no espaço de trabalho `exec/` (motor `vv-exec`). O pacote raiz, o `vv-rocket`, os hashes canónicos do M1 e os resultados históricos não mudam.

| Peça | Ficheiro | O que faz |
| --- | --- | --- |
| Domínio terrestre em processo | `exec/src/ground.rs` | Chama a biblioteca pública do pacote raiz, serializa como `vv-lab run-m4`, exporta margens geométricas com sinal (`margin.restricted_zone_mm`, `margin.world_bounds_mm`) e o nome de cada propriedade violada. |
| Contrato de domínio sem física | `exec/src/domain.rs` | O sucesso da missão, os ficheiros, a reprodução pela linha de comandos e o estudo de convergência passam a ser do domínio. |
| Pesquisa de falsificação | `exec/src/search.rs` | Estratégias `random`, `halton`, `extremes`, `adaptive` e `grid`; registo com hash de cada avaliação; redução do contraexemplo em direção ao caso nominal mantendo a classe e a semente; `search-verify` recalcula tudo. |
| Benchmark | `exec/benchmarks/m14/benchmark.json`, `scripts/m14_benchmark.py` | Divisões de desenvolvimento e reservada, grelha de referência, paridade com as linhas de comandos, análise pré-registada. |
| Estatística | `scripts/m14_stats.py`, `tests/test_m14_stats.py` | Mann-Whitney, Holm, bootstrap e Clopper-Pearson, verificados contra valores exatos e contra o ficheiro de referência do `vv-exec`. |
| Fragilidade | `scripts/m14_fragility.py` | Margem de robustez de uma alegação ao longo de um eixo de pressupostos. |

## Generalização: o que o segundo domínio obrigou a mudar

A pergunta do M13 era: «é preciso mudar código partilhado para acrescentar um domínio?» A resposta medida é sim. Estas foram as quatro mudanças, cada uma um pressuposto do foguetão que estava no código comum:

1. `RunOutput::all_pass` comparava o resultado com a cadeia `"landed"`. Passou a ser `mission_success`, fornecido pelo domínio.
2. O portão de equivalência e a retenção supunham os ficheiros `trace.json`, `run.json` e `case.json` e o comando `replay <dir>`. Passaram a métodos do domínio (`trace_file`, `written_source_sha256`, `cli_replay_args`). O terrestre recebe três ficheiros de entrada; o domínio escreve-os antes de chamar a linha de comandos.
3. Os parâmetros só podiam variar campos de vírgula flutuante. O terrestre é todo inteiro (milímetros, ticks, por mil). Acrescentou-se `integer` e as unidades `mm`, `ticks`, `permille` e `ms`.
4. Os instantes de falha do foguetão têm de ser múltiplos de `dt`; um parâmetro contínuo dava casos recusados. Acrescentou-se `quantum`.

Os planos e os registos do foguetão não mudam: os campos novos são opcionais e não entram na serialização quando ausentes. Os 16 testes de integração do M12 continuam a passar sem alteração.

Paridade em processo contra linha de comandos, sempre com 0 diferenças: corredor terrestre (12 casos), e as pequenas experiências factoriais de cada problema do benchmark (17 casos em desenvolvimento, 33 na divisão reservada, dos dois domínios). A guarda de sementes do terrestre recusa 100 a 129 (inclui as reservadas 101 a 112 do M6 e fecha o desvio declarado no M12), 201 a 212 e as 12 sementes da confirmação final do M6. Numa pesquisa de ensaio a guarda recusou o intervalo 20000 a 29999 por conter 29581.

Não se construiu um terceiro domínio. O oscilador de referência do M11 já prova o contrato `vv-domain`; um terceiro simulador só aumentaria a contagem.

## Benchmark pré-registado

Desenho completo em `docs/m14-preregisto.md`. A ordem está no histórico: pré-registo e casos (`51d6b70`, `6619815`), congelamento (`fede9c7`), uma tentativa reservada que abortou na validação antes de qualquer simulação, correção e novo congelamento (`4098594`, `bcaa490`), execução reservada (`0bc9d95`).

| Problema | Mecanismo | Prevalência na grelha [IC 95 %] | Mediana até à 1.ª violação: random / adaptive | p Holm |
| --- | --- | --- | --- | --- |
| H1 | atraso do atuador na paragem | 0,240 [0,225; 0,256] | 3 / 4,5 | 0,14 |
| H2 | perda do atuador na ultrapassagem | 0,610 [0,572; 0,646] | 1 / 1 | 1,0 |
| H3 | viés GNSS no foguetão | 0,569 [0,536; 0,602] | 1 / 1 | 1,0 |
| H4 | viés do acelerómetro no foguetão | 0,0022 [0,0003; 0,0080] | 10,5 / 17 | 0,50 |

Alegação de generalização: **não suportada** (0 de 4). Em H1 o p bruto foi 0,036 com `adaptive` mais lento, mas não sobrevive ao ajuste de Holm. A potência é limitada: com 30 repetições por braço só se detetam, de forma aproximada, efeitos de cerca de 0,75 desvios-padrão.

Leitura: nestes problemas de 2 e 3 dimensões, uma margem escolhida para um mecanismo (a distância à zona, a velocidade vertical) não guia a pesquisa para outro (contratos temporais, requisitos de posição). A amostragem uniforme é uma linha de base difícil de bater e deve continuar a ser a referência.

Resultados secundários, exploratórios:

- Revocação de propriedades em H4: 0,54 com `random`, 0,63 com `adaptive`. Diferença não testada.
- Cantos e centro: violações perdidas em 22 de 30 repetições em H4 e em 20 de 30 em D2; 0 de 30 nos problemas densos.
- Propriedades só encontradas pela pesquisa: `requirement:R5_position` em D2, `requirement:R3_tilt` em H3, `requirement:R1_vertical_speed` e `requirement:R5_position` em H4.
- Em H4 o contraexemplo reduzido fica no próprio caso nominal (desvio 0): a falha vem da dispersão inicial da semente, não da magnitude da falha.

Reprodutibilidade: 52 447 avaliações de desenvolvimento e 114 822 reservadas, todas recalculadas por `search-verify`, mais cada repetição refeita de raiz; 0 diferenças. Tempo de pesquisa somado: 12,2 s e 21,8 s, com 16 linhas de execução.

## Fragilidade de pressupostos

Exploratório, sementes de desenvolvimento 32000 a 32099. Alegação do tipo «passa com probabilidade de pelo menos 0,95»; por nível, limites unilaterais de Clopper-Pearson a 95 %. Evidência em `docs/evidence/m14/fragility/`.

| Id | Alegação e eixo | Último nível que se mantém | Primeiro refutado | Notas |
| --- | --- | --- | --- | --- |
| F1 | corredor, ruído GPS (0 a 10 mm) | 0 mm | 1 mm (61/100) | não monótona |
| F2 | corredor, atraso de observação (0 a 3 ticks) | 1 tick | 2 ticks (71/100) | |
| F3 | paragem nominal, ruído GPS (0 a 200 mm) | 200 mm | nenhum | robusta em todo o envelope |
| F4 | paragem nominal, atraso (0 a 3 ticks) | 3 ticks | nenhum | robusta em todo o envelope |
| F5 | M9.1, viés do acelerómetro (0,05 a 0,5) | nenhum | nenhum | 96 a 91 de 100: inconclusiva em todos os níveis |
| F6 | M9.1, viés GNSS a partir de 5 s (5 a 30 m) | nenhum | 5 m (0/100) | não monótona: 24/100 a 12,5 m |
| F7 | M9.1, perda de impulso (0,05 a 0,30) | nenhum | 0,30 (85/100) | inconclusiva abaixo |

**F1, causa.** A missão do corredor tem `arrival_radius_mm: 0`: a chegada exige a posição exata. O controlador `dominant_axis` escolhe o eixo com maior erro (`src/controller.rs`, `desired_heading`). Com a posição verdadeira já no ponto de passagem (5000, 2000), uma observação com 1 mm de ruído (y = 2001) dá |Δy| > |Δx| = 0, e o controlador dá um passo de 250 mm para sul. A folga até à zona é 250 mm, por isso o veículo fica na aresta da zona (y = 1750), o que conta como violação. Traço: semente 32001, ticks 20 a 23. A alegação «o corredor é seguro» só vale para ruído exatamente nulo. O controlador não está errado no seu próprio modelo; o cenário depende de três igualdades exatas (raio nulo, passo igual à folga, observação sem ruído).

**F5 e F7.** Com a falha mínima registada, o `guarded` passa em 96 de 100. Com 100 sementes, nem «pelo menos 0,95» nem o contrário se podem afirmar. É um limite da amostra, não do controlador.

**F6 e o G3 do M9.1.** O quadro completo está em `docs/evidence/m14/fragility/fragility.md`. Com início a 0 s, R1 cumpre-se em 30 de 30 em todas as magnitudes, como o M9.1 publicou. Com início a 2, 5 ou 10 s, R1 falha em 30 de 30 a 5 e 10 m e volta a cumprir-se a partir de 15 m. O mecanismo não foi investigado. A explicação mais provável é a regra de desacordo do `guarded` (limiar de 3 m) a reagir a um salto a meio do voo de forma diferente de um desvio constante desde o início, mas isso é uma hipótese, não um resultado.

## Onde o método falha ou fica incerto

- **Sem ocultação.** O mesmo agente desenhou as estratégias, os problemas reservados e as regras. Os casos de H1 e H2 já tinham sido explorados com falhas de atuador no M5 e no M6.
- **Dimensão baixa.** 2 e 3 parâmetros. A comparação pode mudar em espaços maiores, onde a amostragem uniforme se degrada.
- **Sem comparação externa.** S-TaLiRo, Breach, Scenic e VerifAI não foram executados. As estratégias são implementações próprias das mesmas famílias.
- **Sensores do foguetão fixos.** `prepare_landing` fixa sensores, dispersões, condições iniciais e `dt` (decisão do M12). O desajuste de sensores só foi estudado no terrestre. Um domínio de extensão do foguetão que aceite sensores diferentes exige decisão do proprietário e validação própria.
- **Margens geométricas amostradas.** A margem à zona é calculada sobre os segmentos entre posições por tick; é um sinal auxiliar, o veredicto vem do invariante.
- **Fragilidade com 100 sementes.** Distingue 0,95 de 0,85, não 0,95 de 0,93.
- **Studio.** Nenhuma vista nova foi integrada no Studio do M11. A demonstração visual do M14 é um relatório HTML gerado a partir das evidências (ver abaixo).

## Interoperabilidade

Nenhum adaptador foi implementado. O que seria preciso, com valor real:

- **ASAM OpenSCENARIO:** exportar um contraexemplo terrestre como cenário exigiria um mapeamento validado do modelo cinemático inteiro em grelha para entidades e manobras OpenSCENARIO e um simulador de referência para comparar trajetórias. Sem isso, um ficheiro exportado seria só sintaxe.
- **Scenic:** os parâmetros de `vv-search.v1` (ponteiro, unidade, limites, quantum) são uma linguagem de cenário mínima; uma tradução de distribuições Scenic simples para essas caixas é viável, mas não foi feita.
- **SACM / GSN:** a proposta do M13 (capacidade 1) descreve o grafo. O M14 produz os nós de evidência que esse grafo usaria (plano, hash do registo, verificação recalculável), mas não o grafo.

Não se alega conformidade com nenhuma norma.

## Três aceitações separadas

- **Engenharia:** proposta. Formatação, lint e testes de `exec/` e do pacote raiz; testes Python; casos e evidências reproduzíveis; CI por correr no PR.
- **Produto:** não pedida para o Studio. O relatório HTML é um artefacto de demonstração, não uma funcionalidade do produto.
- **Científica:** não pedida. O benchmark tem um resultado confirmatório negativo; a fragilidade é exploratória. Uma confirmação exigiria sementes novas, governadas pelo proprietário, e uma revisão independente.

## Reproduzir

```sh
cargo build --release --bin vv-lab
cargo build --release --manifest-path crates/vv-rocket/Cargo.toml
cargo build --release --manifest-path exec/Cargo.toml
python scripts/m14_cases.py --check
python -m unittest discover -s tests -p "test_m14*.py"
python scripts/m14_benchmark.py --split development --output-root exec/out/m14-dev
python scripts/m14_benchmark.py --split heldout --output-root exec/out/m14-heldout
python scripts/m14_fragility.py --output-root exec/out/m14-fragility
python scripts/m14_report.py
```

A divisão reservada verifica `exec/benchmarks/m14/freeze.json` antes de correr e recusa qualquer ficheiro congelado alterado. As saídas vão para `exec/out/` (ignorado pelo Git); o motor recusa escrever sob uma pasta `runs`. Máquina das medições: Windows 11 (10.0.26300), 16 CPUs lógicos, Rust 1.99.0, Python 3.14.6.

## Decisões do proprietário

1. Aceitar a governação das sementes do M14 (desenvolvimento 30000 a 39999 e 32000 a 32099, reservada 50000 a 59999) e considerar a reservada gasta.
2. Decidir se o resultado F6 justifica reabrir o âmbito do G3 do M9.1 (instante da falha) com sementes novas.
3. Decidir se um domínio de extensão do foguetão com sensores variáveis deve existir, e com que validação.
4. Decidir se o cenário do corredor deve passar a ter raio de chegada positivo, ou ficar como exemplo documentado de uma alegação sem margem.

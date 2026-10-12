# Resultados do M4

## Proveniência e orçamento

A campanha foi executada a partir do commit `34223003c8fa16547a5a993a96f6b3d78ecd820a`, numa PR de rascunho baseada em `main` no commit `a22db7dee082e54bfccdabb171e39ae514ec6437`. O [workflow 38229072330](https://github.com/WhiteBlindness/autonomous-systems-vv-lab/actions/runs/38229072330) passou em Linux, Windows e na comparação canónica entre plataformas. O SHA-256 do código usado nos manifestos M4 foi `38039c255f6f60c8b1a5d50332c2280665df469a1a00ad43b06f5df47bf643cb`. Os resultados e artefactos completos estão associados a essa execução.

A matriz tem quatro cenários e as sementes 42, 1337 e 2026. Cada par executou duas políticas, repetiu ambas e reproduziu ambas de forma independente. A campanha validou o orçamento antes de iniciar os processos.

| Plataforma | Pares | Execuções de simulação | Invocações contabilizadas | Lançamentos de comandos | Tempo da campanha | Artefactos M4 retidos | Arquivo CI: bytes e SHA-256 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Linux | 12 | 72 | 84 de 90 | 60 | 1,4824 s | 3 946 625 bytes | 3 933 010 bytes, `5904100b631e1caec786f6e1d2c943eeebba694206f2b51b8d7b90e7f697e73b` |
| Windows | 12 | 72 | 84 de 90 | 60 | 4,657 s | 3 946 624 bytes | 3 936 200 bytes, `34134fe7694a695eccc90e920b5b9a6d8dd42d8f5c144ccbbb447b4b25574d59` |

As 72 execuções de simulação correspondem a duas execuções iniciais, duas repetições e duas reproduções por par. As 12 comparações também contam no total de operações orçamentadas, que ficou em 84. Os dois resultados ficaram abaixo do limite de 64 MiB retidos e do limite de 120 segundos. O tempo medido cobre a campanha de CI, não é um ensaio de desempenho controlado nem uma comparação de latência por controlador.

## Comparação dos controladores

Cada linha resume os três pares do cenário, um por semente. Os resultados foram iguais nas três sementes.

| Cenário | Ações diferentes | `DominantAxis`: segurança, missão e contratos | `XFirst`: segurança, missão e contratos | Observação |
| --- | --- | --- | --- | --- |
| `nominal` | 0 | `PASS`, concluída, `PASS` | `PASS`, concluída, `PASS` | Sem diferenças de ação ou resultado. |
| `x-first-overshoot` | 12 por par, desde o passo 1 | `PASS`, concluída, `PASS` | `PASS`, estagnada, `INCONCLUSIVE` | `DominantAxis` completou 1 ponto de passagem; `XFirst` completou 0. Os comandos de movimento foram 4 e 12, respetivamente. |
| `gps-fallback` | 0 | `PASS`, incompleta, `PASS` | `PASS`, incompleta, `PASS` | Ambas passaram 8 passos em *fallback* e conservaram 1 ponto de passagem por concluir. |
| `intermittent-actuation` | 0 | `PASS`, concluída, `FAIL` | `PASS`, concluída, `FAIL` | Cada execução registou uma falha do contrato temporal; os invariantes de segurança passaram. |

Não houve diferenças no estado de segurança em nenhum dos 12 pares. A diferença de progresso observada limita-se ao cenário `x-first-overshoot`: neste caso, a política X-first impede a conclusão dentro do horizonte configurado. `INCONCLUSIVE` indica que o contrato temporal ficou sem resolução até ao fim do traço; não representa uma falha de segurança. Os resultados mostram uma diferença neste modelo e nestes cenários, não uma superioridade geral de uma política.

## Calendários e hashes

Cada política foi executada e reproduzida a partir do mesmo cenário, semente e configuração. O comparador regenerou um calendário normalizado por execução, exigiu igualdade dos respetivos hashes e falhou o par se os calendários divergissem. Não reutilizou objetos `ExogenousTick` entre trajetórias.

O calendário V1 contém um registo por instante lógico, incluindo perda GPS, ruído GPS bruto X/Y, entrega ou perda e atraso de comunicação, e identificadores ordenados das falhas ativas do atuador, também quando a lista está vazia. Exclui posição real, coordenadas observadas derivadas, ações pedidas e efeitos físicos do atuador. Por isso, condições externas iguais não implicam observações iguais: cada observação continua a depender da posição real dessa execução.

Os hashes de entrada e do calendário foram iguais para os três pares de cada cenário:

| Cenário | SHA-256 do cenário | SHA-256 dos contratos | SHA-256 do atuador | SHA-256 do calendário externo |
| --- | --- | --- | --- | --- |
| `nominal` | `cbdfdbce7539c419735afa66d2e83d3e44629f60e372fc2350f940d722baa484` | `0bf466b6e39715382ded341b763c883d9982d61f12768c2a5e4d7b17a578cd31` | `0946f8c0c073b613e24593dc9bdeebf5225333df6038fd59004f7e0160de8a0d` | `3143eca16c16c026321eb203b045ea4c574663ed3ceca6871cbdd9a29530a37d` |
| `x-first-overshoot` | `028c0cdf58586f5358822d81c90d9a8b56519c2a291b7be4fc8cfa1fe7b442c7` | `0bf466b6e39715382ded341b763c883d9982d61f12768c2a5e4d7b17a578cd31` | `0946f8c0c073b613e24593dc9bdeebf5225333df6038fd59004f7e0160de8a0d` | `9fb9c5959c9a2838f922392bb76fa4fcc8213c9b5c6b975a7a5fd657e8a62224` |
| `gps-fallback` | `4d8d5e76dacf2b1861acc07e378ad119e91e0f5a68b1a56e9565a6b69f5ade70` | `6cda10b6f0ee24bb6ebc87bcff1320d90184ca6ffb1c46df87c018c55aef9195` | `0946f8c0c073b613e24593dc9bdeebf5225333df6038fd59004f7e0160de8a0d` | `b0217a4dc4cc217fd481ccc129288f0f910eadab006d4e594159ec3dbe57f8d9` |
| `intermittent-actuation` | `bdd66f52881b38bbd642738e1676be4e2fde34ad5f8d3c383922efc373373312` | `96ea65b371c4c38b2d874f6a335435c5fa24175806162a14b78ce2e3f3d9c807` | `e0bb6730217766c5247355b561ea07dd26b309d7743b6fe501fc248e096dc654` | `e5a36524b0bc70c333b3a057d3ce89238cd679fedd8529940df0ec0e6acba83a` |

Os manifestos `m4.json` guardam ainda a versão da interface e do comportamento, os hashes do código-fonte, cenário e configuração, e as referências e hashes dos artefactos de eventos, relatório de segurança, missão e verificação. `comparison.json` guarda as métricas e a proveniência do par. `m4-fingerprints.json` regista hashes de entrada, calendário, comparação e saídas repetidas. A comparação Linux/Windows validou as 12 entradas M4 e os respetivos hashes canónicos.

## Repetição, reprodução e compatibilidade

Todas as 12 repetições coincidiram byte a byte com as execuções iniciais para `events.json`, `report.json`, `mission.json`, `verification.json` e `m4.json`. As 24 reproduções recalcularam cada política e verificaram ações, eventos, resultado da missão, invariantes, contratos temporais e identidade do calendário.

Os testes de regressão rejeitam versões ou políticas desconhecidas, referências e hashes alterados, manifestos malformados e um hash de calendário falso mesmo quando o artefacto de comparação é recalculado. Os testes também verificam a fronteira observacional, as salvaguardas comuns, a divergência esperada entre políticas, os limites do cenário, a repetibilidade e a compatibilidade da linha de comandos.

Os resultados canónicos legados mantêm os valores publicados: o conjunto M1/M2 tem SHA-256 `430fa8fbb0a09ce8bf9b2ddd9f3e191270e96f5745bbcdf73dda3341ecab8c7c`; o conjunto M3 tem SHA-256 `e5a5af6e9bc1b0f5f5fc85ad9fee4574a4a8986860feed0431292524a6b85bbc`. As campanhas de regressão passaram em Linux e Windows: 58 casos e 216 invocações M1/M2, e 30 casos e 90 invocações M3. A comparação canónica também confirmou que os resultados dos dois sistemas coincidem. M4 não alterou os cenários, os hashes, os formatos nem os comandos de reprodução de M1, M2 ou M3.

## Verificações e limitações

O workflow passou formatação Rust, Clippy estrito, 98 testes unitários e de integração, um teste de documentação e 81 testes Python em cada plataforma. Também passou a compilação de lançamento, as campanhas de regressão, minimização, reprodução e comparação canónica. Em Linux, a cobertura de linhas foi 89,02% e `cargo audit` verificou 22 dependências. A cobertura e a auditoria são executadas apenas no job Linux.

M4 cobre duas políticas determinísticas no mesmo processo e dentro da fronteira de observações atual. Não usa ROS 2, processos externos, protocolos de rede, equipamento físico, interface gráfica ou integração com o Flight Systems Lab. A campanha mede duração total e espaço retido, mas não estima latência individual de cada controlador.

Uma política futura que consuma aleatoriedade do gerador partilhado pode alterar as falhas posteriores e invalidar o emparelhamento. Qualquer política estocástica exige um fluxo pseudoaleatório próprio, com semente explícita, e deve continuar a passar pela comparação do calendário normalizado.

Mantêm-se as limitações documentadas do M3: a semântica para conclusão da missão no mesmo instante do prazo de progresso não está definida; a reprodução com caminhos relativos depende do diretório atual; os caminhos UNC não foram testados; a existência de artefactos reduzidos não prova a sua validade semântica; e três amostras de benchmark não permitem concluir que exista uma regressão sustentada. Este resultado não altera essas semânticas nem faz alegações de segurança para equipamento real.

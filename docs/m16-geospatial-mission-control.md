# M16: vista geoespacial e Mission Control

O M16 acrescenta ao Studio duas formas de ver a mesma reprodução: uma vista geoespacial, que coloca uma aterragem do foguetão numa paisagem real a partir de dados públicos com licença, e o Mission Control, uma disposição de operações com telemetria específica do domínio, veredictos ao longo do tempo, eventos com evidência e uma faixa temporal com os ramos das execuções comparadas. O motor de simulação continua a ser a fonte de verdade; as vistas novas leem os registos e não mudam nenhum.

Estado: implementado, testado no Studio instalado nesta máquina e proposto num PR em rascunho, empilhado sobre o PR #24 (M15), que também não está integrado. Nada do M16 foi integrado em `main`. Nenhum resultado científico mudou: os anfitriões de domínio, os registos e os hashes canónicos são os do M15.

## O que mudou para quem abre o Studio

- **Três vistas no leitor de missões.** Engenharia (a cena 3D leve do M15, sem dados geográficos), Geoespacial (a mesma reprodução numa paisagem) e Mission Control. Mudar de vista não volta a correr nada, não relê as execuções e mantém o instante da reprodução; o teste compara o hash de cada registo antes e depois.
- **Duas paisagens instaladas.** A costa de Cabo Canaveral (Florida, plana) e a ilha de Santa Maria (Açores, com relevo). Cada uma tem terreno Copernicus DEM GLO-30 e uma imagem Sentinel-2 L2A, com fontes, licenças, atribuição, precisão e tamanho visíveis em Definições.
- **Na cena geoespacial**, a legenda separa o que é simulado (trajetória, atitude, acelerador, estimativa, eventos), o que é contexto geográfico (terreno e imagem) e o que é ilustração (corpo do andar, pluma, céu, sol, sombras). A atribuição das fontes está sempre no ecrã.
- **Mission Control** tem dois modos: cinematográfico (cena, relógio, quatro valores e faixa temporal) e técnico (grupos de telemetria, requisitos, invariantes, sensores, eventos, comparação e entradas para a análise). Cada valor indica a origem: T estado verdadeiro, E estimativa do controlador, O observação do sensor, C comando, D derivado, G colocação geográfica. A etiqueta vem do tipo do canal no registo, não de uma tabela da interface.
- **Faixa temporal.** Uma pista por execução com as fases derivadas do canal do motor, as falhas injetadas, as deteções, as violações, o contacto e o ponto onde as execuções se separam. Eventos coincidentes partilham um marcador. Clicar num evento pausa nesse instante e abre um cartão com a evidência e as ligações para Analisar nesse instante, Comparar e Desafiar a afirmação.
- **Domínio terrestre.** O Mission Control mostra telemetria de veículo terrestre (este, norte, comando, confiança, GPS); a vista geoespacial fica indisponível com a razão: uma grelha local em milímetros numa paisagem não acrescentaria nada verdadeiro.
- **Sem rede.** O Studio não faz nenhum pedido de rede. Os pacotes são construídos fora dele, de propósito, e instalados com o Studio ou importados de uma pasta.

## Decisão de arquitetura: o renderizador

A hipótese de partida era Three.js para a vista de engenharia e CesiumJS para a geoespacial. A decisão final é **Three.js para as duas, com uma camada de georreferência em Rust e pacotes de ambiente validados**. CesiumJS fica como adaptador futuro para missões à escala do globo (órbita, áreas grandes), numa janela isolada. A decisão assenta em medições e em fontes primárias, guardadas em `docs/evidence/m16/`.

**Protótipos.** Os dois renderizadores correram o mesmo pacote (Cabo Canaveral), o mesmo registo (aterragem nominal, semente 5000) e a mesma câmara, no Microsoft Edge 156 (motor Chromium e ANGLE, da mesma família do WebView2), com a CSP do Studio como cabeçalho, três execuções cada:

| Medida (3 execuções) | Three.js r170 | CesiumJS 1.147 |
| --- | --- | --- |
| Funciona com `freezePrototype` do Tauri | sim | não: `TypeError: Cannot assign to read only property 'toString'` ao importar |
| Funciona com a CSP do Studio | sim | não: precisa de `'unsafe-eval'` e `'wasm-unsafe-eval'` |
| Primeiro fotograma | 118 a 165 ms | 472 a 707 ms (terreno carregado) |
| Intervalo entre fotogramas p99 | 6,2 ms | 6,2 ms |
| Fotogramas acima de 33 ms em 10 s | 1 (compilação de shaders; resolvido no produto) | 5 a 6 |
| Memória privada do navegador | 435 a 444 MB | 856 a 882 MB |
| Processo GPU, memória privada | 270 a 277 MB | 513 a 526 MB |
| Tamanho a instalar | 0 (já incluído, 716 KB) | cerca de 23 MB (`Build/Cesium`) |

As duas cenas colocaram o andar no mesmo sítio da imagem, o que confirma a conversão ENU para ECEF do protótipo Cesium contra o plano tangente do Three.js. Uma pesquisa independente reproduziu a falha com `freezePrototype` fora do navegador e confirmou, a partir do código distribuído, que Draco, KTX2, meshopt e o terreno 3D Tiles precisam de WebAssembly.

**Porquê.** À escala destas missões (menos de 10 km de raio) a curvatura da Terra cabe nas alturas do plano tangente e um globo não traz informação. Usar CesiumJS obrigaria a tirar três proteções da janela principal, a duplicar a memória e a acrescentar 23 MB, sem ganho visual medido. O Three.js reaproveita a cena do M15, a mesma câmara, a mesma legenda e os mesmos testes.

**Alternativas avaliadas.**

- **MapLibre GL JS 6.16 com Three.js.** Licença BSD-3, sem `eval` nem WebAssembly, câmara até 180 graus de inclinação. Rejeitado para o M16: é um motor centrado no mapa, sem sombras do sol, e obrigaria a manter dois renderizadores sem ganho à escala da missão. Continua a ser a opção natural para mapas 2D de trajetos no solo.
- **Cesium for Unreal e Unreal Engine 5.** Plugin com licença Apache-2.0, mas o motor não corre dentro do WebView2: seria um processo à parte ou Pixel Streaming, com codificador de vídeo por hardware e servidor de sinalização. Um pacote mínimo para Windows ronda 200 a 320 MB segundo relatos da comunidade (não verificado numa fonte oficial). O EULA lido prevê 5 % de royalties acima de 1 milhão de dólares por produto; a taxa por posto para empresas fora dos jogos não foi verificada numa fonte primária. Desproporcionado para o produto.
- **`3d-tiles-renderer` para Three.js.** Licença Apache-2.0, carrega terreno quantized-mesh e imagens em mosaico com recentragem local. É o caminho para pacotes maiores dentro do mesmo renderizador, se um domínio futuro precisar.

**Caminho para o globo.** Quando houver um domínio orbital ou uma área grande, o CesiumJS entra como mais um renderizador da mesma reprodução, numa janela WebView separada sem `freezePrototype` e com uma CSP própria. A janela principal mantém as proteções atuais. O contrato entre a reprodução e os renderizadores (registo, cursor, cena com `{dispose, preset, redraw}`) já permite isso sem mudar o motor científico.

## Camada de georreferência

- **`desktop/geo` (crate `vv-geo`).** WGS84 geodésico para ECEF e de volta, referencial ENU num ponto de origem com rumo dos eixos do modelo, e validação dos pacotes. Os testes comparam com o PROJ 9.8.1 ao micrómetro (incluindo o exemplo publicado do GeographicLib `33.3 44.4 6000`), fazem a volta completa numa grelha de 2 485 pontos de -85 a 85 graus e de 0 a 400 km de altura, e verificam a ortonormalidade do ENU e o rumo.
- **Pacotes.** `scripts/geo/build_environment.py` constrói cada pacote com o PROJ. Para cada nó da grelha encontra, por iteração, o ponto da superfície cujas coordenadas ENU este e norte são exatamente as do nó, e guarda a componente vertical ENU; a curvatura da Terra e a inclinação da vertical local ficam nas alturas. A imagem usa a mesma construção, por isso fica registada no terreno. A origem fica na superfície do DEM; a altura elipsoidal é a altura EGM2008 mais a ondulação do geoide na origem, tratada como constante na extensão (a variação entre cantos vai no manifesto: 0,21 m em Cabo Canaveral, 0,84 m em Santa Maria).
- **Validação.** Antes de mostrar um pacote, o Studio verifica nomes de ficheiros fixos, tamanhos, SHA-256, a grelha centrada na origem, fontes com fornecedor, produto, licença e atribuição, e recalcula com o `vv-geo` os pontos de controlo que o PROJ calculou: dois programas independentes têm de concordar a 1 mm. Um pacote com a origem deslocada 10 m ou um byte alterado é rejeitado, com a razão em Definições. Cada ficheiro volta a ser verificado quando a interface o pede.
- **Registo de imagem e terreno.** O script compara a máscara de terra do DEM com a máscara de água da imagem: em Santa Maria a concordância é 96,5 % com deslocamento ótimo de 0 m; em Cabo Canaveral, costa baixa e plana, a medida é fraca (84 %) e não distingue deslocamentos de 120 m dentro de 0,5 %.
- **O registo não muda.** `geo_track` lê o registo e devolve coordenadas derivadas; o teste confirma que o registo serializado é igual antes e depois, e a jornada no Studio compara os hashes dos registos antes e depois de usar a paisagem.

## O que a paisagem não é

A simulação assume solo plano no plano da plataforma e não calcula nada contra este terreno. A colocação numa paisagem é uma visualização geográfica, não física sensível ao terreno. Onde o terreno sobe acima do plano, o percurso desenhado pode atravessá-lo; o Studio avisa a partir do instante em que isso acontece. O DEM é um modelo de superfície (inclui edifícios e copas), com precisão vertical absoluta declarada melhor que 4 m (90 %), e não resolve plataformas nem o estado do solo. A imagem tem 10 m por pixel. Em Cabo Canaveral, o centro da plataforma simulada foi posto num pavimento circular visível na imagem, com a posição lida da imagem (cerca de 10 m); a instalação não é modelada e a plataforma simulada não é essa instalação. Nada disto é um gémeo digital.

## Dados, licenças e atribuição

| Fonte | Licença | Atribuição mostrada |
| --- | --- | --- |
| Copernicus DEM GLO-30 (ESA, DLR, Airbus), AWS Open Data | Licence for the use of the Copernicus WorldDEM-30: gratuita, reprodução, distribuição e adaptação permitidas com os avisos do artigo 6 | «produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved», com a frase de exclusão de responsabilidade |
| Sentinel-2 L2A (Comissão Europeia, ESA), cópia COG da Element 84 | Aviso legal dos dados Sentinel: acesso livre, completo e aberto, incluindo adaptação | «Contains modified Copernicus Sentinel data 2025» |
| EGM2008 (NGA) pela grelha `us_nga_egm08_25` do PROJ | Domínio público (obra do governo dos EUA) | «EGM2008, NGA» |

Os textos das licenças foram lidos nas páginas e PDF oficiais (`docs/evidence/m16/renderer-research.md`, secção 6). Foram excluídos: as imagens EOX Sentinel-2 cloudless (uso comercial pago), os mosaicos do OpenStreetMap (proíbem uso offline e descarga em massa) e o NAIP no AWS (pagamento pelo requerente). Cada pacote ocupa cerca de 1,1 MB; os dois vão no instalador.

## Verificação

- `cargo test -p vv-geo` (14 testes) e `cargo test -p vv-studio` (2 testes de colocação de execuções).
- `--self-test` do Studio valida os pacotes instalados, além das demonstrações e das afirmações.
- `desktop/studio/tests/m16_journeys.py`: verificações na janela real. Vista geoespacial, câmaras, troca de vistas com o mesmo instante, hashes dos registos iguais, segunda paisagem, Mission Control do foguetão (grupos de telemetria, origem dos valores, requisitos pendentes antes do contacto e julgados no fim, duas pistas com o ponto de separação, evento com cartão de evidência, Analisar no mesmo instante), libertação da cena geoespacial ao sair do leitor e regresso ao mesmo instante, Mission Control terrestre sem métricas aeroespaciais, Definições com fontes e tamanho, três tamanhos de janela sem deslocamento horizontal e com todos os controlos com nome, Studio sem nenhum pacote e com um pacote adulterado (rejeitado com a razão; a vista de engenharia e o Mission Control continuam a funcionar).
- `desktop/studio/tests/m15_journeys.py` continua a passar.

Estes testes são verificações com guião do que o ecrã mostra. Não são observações de pessoas a usar o Studio.

## Desempenho

Medido fora da simulação com `desktop/studio/tests/perf_probe.py --flow m16` no Studio 0.16.0 instalado, na máquina de desenvolvimento (Ryzen 7 7800X3D, Radeon RX 7700 XT por ANGLE/Direct3D 11, 32 GB, Windows 11, ecrã a 165 Hz), janela de 1440x900. A linha de base 0.15.0 foi medida de novo antes de qualquer alteração (`docs/evidence/m16/baseline/`, três execuções). Do M16 há duas execuções completas: a terceira foi interrompida pelo ambiente de trabalho por falta de memória do sistema e não foi repetida (`docs/evidence/m16/installed/`).

| Medida | 0.15.0 (3 execuções) | 0.16.0 (2 execuções) |
| --- | --- | --- |
| Arranque até à plataforma pronta (primeira / seguintes) | 4,03 s / 1,09 a 1,18 s | 4,00 s / 1,14 s |
| Clique até à aterragem no ecrã | 0,50 a 0,57 s | 0,46 a 0,99 s |
| Vista de engenharia: intervalo entre fotogramas p99 | 6,2 ms | 6,2 ms |
| Vista de engenharia: memória privada da árvore de processos | 319 a 321 MB | 323 a 326 MB |
| Mudar para a vista geoespacial até o terreno estar na GPU | | 0,145 a 0,149 s |
| Vista geoespacial: p50 / p99, fotogramas acima de 33 ms | | 6,1 / 6,2 ms, 0 |
| Vista geoespacial: memória privada / GPU dedicada | | 487 a 492 MB / 197 a 199 MB |
| Vista de engenharia: GPU dedicada | | 115 a 120 MB |
| Mudar para o Mission Control (com paisagem) | | 0,149 a 0,156 s, p99 6,2 ms |
| Depois de sair do leitor: memória privada / GPU dedicada | | 404 a 422 MB / 77 a 83 MB |
| Sessão de 180 s em ciclo na vista geoespacial: memória privada no início / no fim, pior p99 | | 644 a 653 / 534 a 546 MB, 6,2 ms |
| Pedidos da vista web que saem da máquina | | 0 (13 pedidos, todos locais) |

O ecrã limita a 165 fotogramas por segundo, por isso o p99 de 6,2 ms é o limite do ecrã nas três vistas. A vista de engenharia não piorou. A vista geoespacial acrescenta cerca de 170 MB de memória privada e 80 MB de GPU; sair do leitor devolve a GPU a um valor inferior ao da vista de engenharia e a memória não cresce durante a sessão longa. Os valores de carga de CPU e de utilização 3D que o script também regista (por exemplo 56 a 64 % de um núcleo na vista de engenharia) variam muito entre janelas de medição e não foram usados para conclusões. O instalador passou de 6,5 MB para 7,8 MB; os dois pacotes de 1,1 MB explicam quase toda a diferença.

## Limitações

- Usabilidade não testada com pessoas.
- O sol, o céu e as sombras são ilustrativos: o modelo não tem data nem hora.
- Uma paisagem por missão, com extensão de 9 km à volta da origem; para lá dela, um plano neutro sem dados.
- A vista geoespacial só existe para registos num referencial ENU em metros (o foguetão).
- Os pacotes não são construídos dentro do Studio; o script precisa de Python, `rasterio` e `pyproj` e de acesso à Internet.
- Sem WebGL, as duas vistas 3D mostram uma mensagem; o Mission Control continua com telemetria, veredictos e faixa temporal.

## Instalação e reversão

O instalador `VV Lab Studio_0.16.0_x64-setup.exe` (sha256 `984f677f7ed831b2398826406c770a5b09e1c816d34faa119c40748333bda10d`) instala por utilizador por cima da 0.15.0; o `--self-test` passa, incluindo a validação dos pacotes, e as jornadas M16 (45 de 45) e M15 (48 de 48) passam no Studio instalado (`docs/evidence/m16/installed/`). Para voltar à 0.15.0, desinstalar e correr o instalador da 0.15.0 (sha256 `b76db8857a6b5f241860f2eda7672543fe821caa1272bfe911aa92c1dade30b7`, artefacto do PR #24). As bibliotecas, os pacotes importados e as preferências não são apagados.

## Revisões independentes

Quatro revisões por agentes (a quarta, visual e de acessibilidade, sobre as capturas do Studio instalado), as três primeiras sobre o código e não sobre as conclusões deste texto:

- **Geodésia e coerência com a física.** Confirmou as fórmulas WGS84 e ENU, o registo da imagem (sem desvio de meio texel nem inversão norte-sul), a orientação da grelha nas três linguagens e o datum; recalculou os pontos de controlo com o pipeline topocêntrico do PROJ (pior diferença 0,26 mm). Corrigido em `e907602`: pacotes com rumo diferente de zero recusados (o renderizador ainda não roda o referencial), interpolação nos triângulos desenhados, planos de recorte depois de mudar de câmara, extensões exatas, linha vertical abaixo de z = 0, falha do geoide no script.
- **Segurança e licenças.** Sem problema explorável. Corrigido em `da4f543`: tamanho real do JPEG igual ao declarado, nomes de dispositivos do Windows recusados, limpeza da importação falhada. Atribuições conferidas com o texto das licenças.
- **Arquitetura da interface.** Corrigido em `da4f543`: os painéis do Mission Control eram reconstruídos a cada 100 ms e perdiam cliques e foco; valores observados de requisitos pendentes apareciam nas dicas e as violações futuras eram nomeadas antes do tempo; libertação da cena durante o carregamento; outros problemas de ciclo de vida.

Uma revisão de agente não substitui um teste de usabilidade com pessoas, que não foi feito.

## Pendente

- A faixa de fases do leitor do M15 continua a marcar as violações desde o início; no Mission Control só são nomeadas quando a reprodução lá chega.
- Os grupos de rádio não têm navegação por setas (só Tab).
- Uma terceira execução de desempenho do M16.
- Revisão visual por agente (corrigida em grande parte depois): a 1024x640 os distintivos dos veredictos ficam cortados na margem do painel direito.
- As medições de desempenho foram feitas antes das últimas correções visuais (só CSS e o cartão de evidência); as jornadas e o `--self-test` foram repetidos no instalador final.

## Próxima expansão de domínio

Recomendação: **multicóptero autónomo em 3D com fusão de sensores**, como no M15. A camada de georreferência e o Mission Control já servem esse domínio sem alterações de arquitetura: registos num referencial ENU em metros podem ser colocados numa paisagem, e a telemetria passa a ter um grupo próprio por domínio. Requisitos de corredor e de geocerca, e um modelo de estimação com IMU, barómetro, GNSS e magnetómetro, tornam a vista geoespacial útil de forma mais direta do que no foguetão, onde o terreno é só contexto. Para aplicações de defesa, o âmbito continua a ser resiliência, deteção de falhas, navegação segura e segurança de campo de tiro; não entram orientação de armas nem otimização de empenhamento.

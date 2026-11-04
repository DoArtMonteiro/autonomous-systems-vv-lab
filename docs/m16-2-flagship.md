# M16.2: um mundo tridimensional na vista geoespacial

O responsável rejeitou o Studio 0.16.1: a paisagem continuava a ser uma fotografia aérea esticada sobre uma malha grosseira, e nem a resolução da imagem, nem o tamanho do andar, nem a câmara resolviam esse problema. O M16.2 muda o que a cena contém. Os pacotes de ambiente passam a trazer o que está de pé sobre o terreno (edifícios, estruturas e vegetação, cada um com a origem da sua altura) e o renderizador desenha-o com sombras, atmosfera e câmaras pensadas para o mostrar.

Estado: implementado no ramo `feat/m16-geospatial` (PR em rascunho #25, empilhado sobre o #24), Studio 0.16.2. Nada foi integrado. A aceitação visual cabe ao responsável; este documento descreve o que foi construído e medido, não declara a cena aceite.

## O diagnóstico

A falta de profundidade não vinha da resolução. Vinha de três ausências:

- **Nada estava de pé.** Um campo de alturas com uma fotografia só mostra relevo; num terreno plano como Cabo Canaveral, a cena é um plano pintado. De qualquer câmara baixa, a imagem achata.
- **A luz não ligava as coisas.** Não havia sombras de objetos no terreno, a névoa era linear e começava a 3 km, e o céu era pintado depois do mapeamento de tons, com cores diferentes das da névoa. A distância não se lia.
- **As câmaras olhavam para o vazio.** As poses do 0.16.1 enquadravam o andar contra o céu ou contra o pavimento branco, sem nada atrás que desse escala.

## Decisão de arquitetura

Mantém-se o Three.js (r170, já incluído) e a separação do M16: o motor de simulação é a autoridade; a cena só lê o registo e o pacote. Foram ponderadas três alternativas:

| Opção | Porque não |
| --- | --- |
| Google Photorealistic 3D Tiles | Exige chave e rede em cada sessão; os termos não permitem guardar nem redistribuir os mosaicos, o que contraria o funcionamento offline e a proveniência por ficheiro com SHA-256. |
| CesiumJS com 3D Tiles locais | Rejeitado no M16 com evidência (`docs/evidence/m16/renderer-research.md`): `unsafe-eval`, `freezePrototype` do Tauri e cerca do dobro da memória. Nada do que mudou o invalida. |
| Fotogrametria própria | Não há fotogrametria aberta para estes locais; inventá-la seria fingir precisão. |

A escolha foi pôr a geometria nos dados do pacote, construída fora do Studio a partir de fontes abertas com licenças compatíveis, e validada pelo `vv-geo` como o resto do pacote. Assim o Studio continua sem pedidos de rede, cada objeto desenhado tem uma origem rastreável e o renderizador não precisa de saber de onde os dados vieram.

## O que os pacotes passam a trazer (esquema v3)

O esquema `vv-geo-environment.v3` acrescenta ao v2 um bloco opcional `world` com dois ficheiros, validados em `desktop/geo/src/world.rs` (nomes fixos, tamanhos limitados, SHA-256, contagens iguais às do manifesto, campos desconhecidos recusados, coordenadas dentro do pacote, contornos no sentido anti-horário, origem da altura de uma lista fechada):

- **`features.json`** (`vv-geo-features.v1`): contornos de edifícios do OpenStreetMap extrudidos até uma altura; estruturas elevadas que nenhum contorno OSM cobre, delineadas a partir de células lidar de 1 m; e estruturas pontuais (torres, mastros, faróis). Cada registo indica a origem da altura: `lidar` (medida), `osm-height` ou `osm-levels` (etiquetas do mapa) ou `default` (estimativa por tipo).
- **`vegetation.bin`**: registos de 12 bytes (posição, altura, raio da copa, tipo, cor da imagem nesse ponto) de copas e tufos medidos no lidar.

Os pacotes v1 e v2 continuam a abrir. A importação copia os ficheiros novos. O painel de fontes e o catálogo dizem, para cada pacote, quantos edifícios tem, de onde vem cada altura e quanta vegetação tem.

### Como a camada é construída

`scripts/geo/build_features.py --env <id>`:

1. **OpenStreetMap** pela API Overpass num raio de 4,5 km, com o carimbo temporal da resposta guardado no manifesto.
2. **Lidar USGS 3DEP** pelas cópias Entwine Point Tile em `s3://usgs-lidar-public`: só os nós da octree sobre a camada de pormenor e até cerca de 1 m de espaçamento (398 nós e 17,1 milhões de pontos em Cabo Canaveral), lidos nó a nó para a memória ficar limitada. Os levantamentos usados só classificam solo e ruído, por isso a altura sobre o solo é a superfície mais alta de cada célula menos o solo do próprio levantamento: o datum vertical cancela-se.
3. **Separar vegetação de construções** com o NDVI das bandas vermelho e infravermelho próximo do NAIP, a rugosidade da copa em 3 x 3 células e a fração de retornos múltiplos. Uma estrutura lidar tem de ser lisa, de retorno único e não verde em pelo menos 60 % das células. Uma copa tem de encher as células à volta do topo e, com infravermelho próximo, ser verde: foram estas regras que impediram que uma linha elétrica em Spaceport America (1291 topos de fios e postes) fosse desenhada como árvores.

As definições dos ambientes saíram do código para `scripts/geo/catalogue.json`. Acrescentar um local é acrescentar uma entrada (origem, extensões, imagens, e no bloco `world` o projeto lidar e o ano do NAIP) e correr os dois comandos.

### O que cada pacote tem

| Ambiente | Edifícios OSM (origem da altura) | Estruturas lidar | Estruturas pontuais | Vegetação lidar | `features.json` + `vegetation.bin` |
| --- | --- | --- | --- | --- | --- |
| Cabo Canaveral | 687 (18 lidar, 1 etiqueta, 668 estimadas) | 8 | 39 | 8 248 árvores, 97 479 tufos | 0,1 + 1,3 MB |
| Spaceport America | 16 (16 estimadas) | 0 | 3 | 1 árvore, 2 455 tufos | 0,004 + 0,03 MB |
| Santa Maria | 4 081 (4 078 estimadas, 3 por etiqueta) | 0 | 14 | nenhuma: não há lidar aberto e nada é inventado | 0,6 MB |

A maior parte dos edifícios fica fora do quadrado lidar de 2 km e tem altura estimada; o painel de fontes di-lo com os números. Em Santa Maria a ausência de vegetação é uma limitação declarada, não um esquecimento.

## O que mudou no desenho

- **Edifícios e estruturas:** uma malha única com paredes de tom neutro e telhados com a cor da imagem por cima de cada contorno, com sombras próprias e projetadas.
- **Vegetação:** malhas instanciadas por mosaicos de 256 m. Perto da câmara (até 700 m) cada planta é um núcleo escuro com cartões de folhagem com transparência e normais arredondadas; mais longe, uma copa simples; para lá de 3,2 km, nada. A cor de cada planta tem o tom da imagem nesse ponto, levado à luminância de folhagem iluminada.
- **Luz e atmosfera:** sol mais baixo (27°), sombras num mapa de 4096 que segue o andar (cerca de 0,19 m por texel) ou cobre 2,8 km nas vistas largas; névoa aérea aplicada à luz linear antes do mapeamento de tons, com a mesma cor do céu, que passou a usar o mesmo mapeamento. A paisagem funde-se no céu sem a faixa de cor do 0.16.1.
- **Chão:** grão fino junto à câmara na camada de pormenor, para os texels de 0,5 m não se lerem como borrão, e albedo da fotografia trazido para valores de solo.
- **Andar:** fuligem ilustrativa a subir dos motores. Perto do solo, um brilho e uma nuvem de poeira ilustrativos onde a pluma toca o terreno, a partir só do acelerador aplicado e da altura do bocal.
- **Câmaras:** nova predefinição **Auto**, que escolhe o plano pela altura do andar sobre a plataforma (vista larga, perseguição, observador no solo, plataforma) e transita entre eles; **At the pad** passou a uma teleobjetiva baixa a 165 m que acompanha o andar até ao contacto, com a sombra atravessada no plano e a paisagem atrás; **From the ground** põe o observador acima da vegetação. As vistas continuam a ser regras do estado da reprodução.

Tudo o que é desenhado sem ser dado está na lista "Illustrative" do painel de fontes. Nada disto chega à simulação: o andar continua a aterrar em solo plano, e o terreno, os edifícios e a vegetação não entram em nenhum cálculo.

## Evidência visual

`docs/evidence/m16/after-0.16.2/` tem as capturas do Studio 0.16.2 instalado com os mesmos nomes de `docs/evidence/m16/after/` (0.16.1 instalado): mesma missão («A sensor that lies»), mesmo ambiente, mesmo instante, mesma predefinição e mesmo tamanho de janela. `docs/evidence/m16/comparison-0.16.2.md` põe-nas lado a lado. Duas diferenças tornam a comparação imperfeita, de propósito: as poses de «At the pad» e «From the ground» mudaram, e a predefinição «Auto» não existia.

## Revisões independentes

Duas revisões por agentes sobre as capturas do primeiro instalador 0.16.2, sem acesso às conclusões deste texto. Os resultados estão resumidos tal como vieram; o que foi corrigido antes do instalador final está indicado.

**Gráficos e direção de arte.** Veredicto: «não significativamente melhor» do que o 0.16.1; um passo real ao nível do solo e um passo atrás em altitude. Problemas apontados e o que foi feito:

- A névoa tirava cor e contraste a todas as vistas, incluindo a vista de cima. Corrigido: a névoa passou a depender da altura média do raio (ar mais fino em altitude) e a densidade baixou para cerca de 11 % a 10 km junto ao solo.
- «At the pad» a meio da descida mostrava quase só céu, e a 6 m de altura as sombras ficavam reduzidas a um fio (confirmado: as sombras existiam, mas a 2° de elevação não se viam). Corrigido: câmara a 20 m e 150 m, com a plataforma na metade inferior do plano até o andar chegar.
- Edifícios de altura estimada desenhados como caixas iguais de 5 m, como se fossem medidos. Corrigido: alturas estimadas desenhadas com no máximo 3,5 m e num tom mais pálido, e o painel de fontes diz quantas alturas são dados e quantas são estimativas.
- Árvores de 21 m em deserto aberto em Spaceport America: eram postes de uma linha elétrica. Corrigido: uma copa tem de ser verde no infravermelho próximo; ficou 1 árvore e 2 455 tufos.
- «From the ground» tapado por arbustos: o observador passou a 8 m acima da copa mais alta num raio de 40 m.
- Por corrigir: a fotografia do terreno continua a ter a luz e as sombras do voo e é iluminada de novo; o mar e o terreno acabam numa aresta visível nas vistas largas de Santa Maria; a forma das plantas continua simples.

**Experiência e honestidade.** O problema mais grave: no fim de uma execução falhada a cena mostrava o andar intacto, de pé, com o anel verde e a etiqueta «Touchdown», mais favorável do que os dados (contacto a 33 m/s). Corrigido: a etiqueta passou a «Contact at 33.0 m/s, requirements not met; impact not modelled» e o anel da plataforma toma a cor de falha. Também corrigido: a frase do painel de fontes que dizia que as alturas eram dados. Por corrigir: a 1024x640 a barra de câmaras tapa linhas do painel de telemetria e as ações do cabeçalho apertam-se; a 1280x720 a etiqueta de fase corta-se; a chave T/E/O/D desaparece em janelas baixas; o texto de créditos tem 9,5 px sobre terreno claro.

Uma revisão de agente não substitui o olhar do responsável, que continua a ser o critério de aceitação.

## Desempenho

Medido fora da simulação com `desktop/studio/tests/perf_probe.py --flow m16` no Studio 0.16.2 instalado (instalador final, sha256 `f5d8e2c66bb4f25d56cb3c11f18bf8f6ff3e9f3c26b1fde17d9f7d3608d6c52b`), na mesma máquina (AMD64 Family 25, Windows 11) e janela de 1440x900 do M16.1, três execuções cada (`docs/evidence/m16/installed-0.16.1/` e `installed-0.16.2/`):

| Medida | 0.16.1 | 0.16.2 |
| --- | --- | --- |
| Mudar para a vista geoespacial até o terreno estar na GPU | 0,44 a 0,55 s | 0,44 a 0,53 s |
| Vista geoespacial: p99 entre fotogramas, acima de 33 ms | 6,2 a 6,3 ms, 0 | 6,2 ms, 0 |
| Vista geoespacial: memória privada / GPU dedicada | 821 a 834 / 314 a 319 MB | 1049 a 1068 / 455 a 462 MB |
| Vista geoespacial: triângulos desenhados | 1 264 890 | 4 352 762 |
| Mudar para o Mission Control | 0,41 a 0,44 s | 0,42 a 0,45 s |
| Vista de engenharia: memória privada / GPU dedicada | 352 a 360 / 132 a 136 MB | 357 a 359 / 138 MB |
| Depois de sair do leitor: memória privada / GPU dedicada | 578 a 641 / 90 MB | 552 a 570 / 155 a 159 MB |
| Sessão de 180 s: memória privada no fim, pior p99 | 889 a 911 MB, 6,4 ms | 1067 a 1072 MB, 6,3 ms |
| Pedidos da vista web que saem da máquina | 0 | 0 |

O ecrã limita a 165 fotogramas por segundo e a fluidez não mudou. A camada do mundo custa cerca de 230 MB de memória privada e 140 MB de GPU na vista geoespacial; a vista de engenharia não mudou. Ponto em aberto: depois de sair do leitor ficam cerca de 65 MB de GPU a mais do que no 0.16.1. O valor coincide com o mapa de sombras de 4096 x 4096 (64 MB), que a cena não liberta explicitamente ao ser desmontada; a correção (`this.sun.shadow.dispose()` em `dispose`) não está neste instalador, para que a medição corresponda ao código medido.

## Verificação

- `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings` e `cargo test` na raiz e em `desktop/` (`vv-geo` 23 testes, 3 novos: camada do mundo v3 aberta e servida por hash, regras da camada do mundo, camadas dos pacotes instalados); `python -m unittest` (374 testes); `cargo build --release`; campanha `run_campaign.py --seeds 42,1337,2026` (87 casos, `passed`).
- No Studio 0.16.2 instalado: `--self-test` passa; `m16_journeys.py` 76 de 76 (4 novas: edifícios e vegetação no pacote de Cabo Canaveral, vegetação em pormenor junto à câmara «At the pad», câmara «Auto», painel de fontes com a origem dos edifícios e da vegetação); `m15_journeys.py` 48 de 48.
- Os registos, os vereditos e os hashes canónicos não mudaram: a jornada verifica que pôr a execução numa paisagem não altera nenhum registo.

## Instalação e reversão

`VV Lab Studio_0.16.2_x64-setup.exe` (sha256 `f5d8e2c6…6c52b`, 19,3 MB com os três pacotes) instala por utilizador por cima do 0.16.1. Os instaladores anteriores estão guardados em `Documentos\VV Lab Rollback` com `SHA256SUMS.txt`: 0.16.1 (`96db980e…a351`) e 0.16.0 (`984f677f…a10d`). Para voltar atrás, desinstalar e correr o instalador anterior. Bibliotecas, pacotes importados e preferências não são apagados.

## Limitações

- Física em solo plano, como antes. O terreno, os edifícios e a vegetação são contexto.
- A maior parte dos edifícios tem altura estimada (fora do quadrado lidar, ou sem etiqueta). As paredes, os telhados planos e as formas das plantas são desenhos; os contornos OSM têm a precisão com que foram mapeados.
- O lidar de Cabo Canaveral é de 2018 e a imagem de 2023: o que foi construído ou demolido entretanto não coincide. Em Santa Maria não há vegetação e em Spaceport America há pouca, porque só se desenha o que o lidar mede.
- Para lá do pacote de 18 km o chão continua sem dados; a junção ainda se vê em vistas muito largas.
- Não há fotorrealismo. É uma cena técnica com dados geográficos reais e geometria rastreável.
- Usabilidade não testada com pessoas.

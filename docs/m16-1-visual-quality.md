# M16.1: qualidade visual da vista geoespacial

O responsável inspecionou o Studio 0.16.0 instalado e concluiu que a interface era compreensível mas que a vista geoespacial ficava muito aquém do esperado: o andar era um ponto, a paisagem parecia uma textura de baixa resolução, o enquadramento não comunicava a escala de uma aterragem e o texto de atribuição ocupava o fundo da cena. O M16.1 responde a essa avaliação no mesmo ramo do M16, sem mudar o motor de simulação, os anfitriões de domínio, os registos ou os hashes canónicos.

Estado: implementado e verificado no Studio 0.16.1 instalado nesta máquina, no PR em rascunho #25, empilhado sobre o #24. Nada foi integrado. A aceitação visual cabe ao responsável.

## Porque é que a vista parecia pobre

A causa não era o renderizador. Eram duas decisões acopladas do 0.16.0:

- **A câmara afastava-se para esconder a imagem de 10 m.** A câmara «Seguir» ficava a cerca de 375 m do andar, de propósito, para que os texels de 10 m do Sentinel-2 parecessem paisagem e não borrão. A essa distância um corpo de 40 m por 3,7 m ocupa poucos píxeis.
- **A câmara subia com a reprodução.** A correção de altura sobre o terreno era guardada no deslocamento da câmara: em cada fotograma em que a câmara ficava abaixo do terreno, subia e não voltava. Numa descida sobre relevo, como em Santa Maria, a câmara acabava muito acima do andar, que é o que mostram as capturas do responsável.

Aproximar a câmara sem dados melhores só tornaria o borrão visível. A correção teve por isso duas partes que só funcionam juntas: dados de pormenor à volta da plataforma e uma câmara próxima, com um andar desenhado com cuidado.

## O que mudou para quem abre o Studio

- **O andar é o assunto da imagem.** Modelo ilustrativo de um primeiro andar de 42 m (sete tubeiras, saia, tanque pintado com juntas, interandar escuro, aletas em grelha e pernas recolhidas), com materiais iluminados pelo mesmo céu que se vê. Nada se move por conta própria: as pernas e as aletas nunca abrem, porque o modelo não tem trem nem superfícies de controlo; a pluma continua a vir só do acelerador aplicado. Na câmara «Seguir» o andar ocupa cerca de 41 % da altura da cena.
- **Câmaras por regra, não por acumulação.** Cada predefinição calcula a pose a partir do estado da reprodução: «Seguir» (perseguição a 190 m do lado do sol), «Do solo» (observador a 10 m de altura e 420 m da plataforma, teleobjetiva, no primeiro rumo com linha de vista livre), «Na plataforma» (nova: câmara elevada ao lado da área de aterragem, à escala real do contacto), «Descida completa» e «Vista de cima». A correção sobre o terreno aplica-se só à pose desenhada, por isso a câmara já não deriva. Mudar de predefinição faz uma transição de 0,7 s, que não acontece com movimento reduzido.
- **Paisagem com pormenor real.** Os pacotes passam a ter uma camada de pormenor de 2 km à volta da plataforma, com imagem de 0,5 m por pixel e, onde há dados abertos, terreno lidar. Fora dela fica a base de 18 km do M16. Para lá do pacote, o chão continua como extensão da borda (água ao nível do mar onde a borda é mar), em vez de um plano cinzento.
- **Três ambientes e um catálogo.** Cabo Canaveral, Santa Maria e, novo, Spaceport America. O botão «Environments» ao lado do seletor abre um catálogo com miniatura, resumo, nota do local, resolução de cada camada, relevo junto à plataforma, créditos e tamanho; escolher um cartão muda a cena. Definições, Environments mostra os mesmos cartões, a importação e o comando para construir mais pacotes.
- **Fontes discretas e completas.** O bloco de atribuição de cinco linhas deu lugar a um botão «Sources» com uma linha curta de créditos sempre visível. O painel abre ao passar o rato, com clique, com toque, com Enter ou Espaço, e fecha com Escape ou com um toque fora; diz o que é simulado, contexto e ilustração, a resolução de cada camada, a nota do local, a precisão e o texto integral de cada licença e atribuição. Uma etiqueta «Terrain is context only» lembra que a física não usa o terreno.
- **Nenhum resultado antes do tempo.** Na reprodução normal, as deteções, os avisos, as violações e o ponto onde as execuções se separam só aparecem na faixa temporal, no Mission Control e na lista de eventos quando a reprodução lá chega (antes, o Mission Control desenhava um círculo no sítio e o leitor mostrava tudo desde o início). O modo de análise, um botão no leitor e no Mission Control, mostra tudo de uma vez e o resultado.
- **Acessibilidade e janelas pequenas.** As setas percorrem as opções dos grupos de rádio (vistas, câmaras, execuções, densidade) e mantêm o foco quando a vista é reconstruída. A 1024x640 os distintivos dos veredictos do Mission Control já não ficam cortados.

## Pacotes de ambiente v2

O esquema `vv-geo-environment.v2` acrescenta ao v1 uma camada opcional `detail`: um quadrado mais pequeno centrado na origem com a sua grelha de alturas (`detail-height.u16`) e a sua imagem (`detail-image.jpg`), com as mesmas regras de validação da base (nomes fixos, tamanhos, SHA-256, grelha centrada e quadrada, tamanho real do JPEG), mais:

- **A origem fica na camada mais fina.** O zero do modelo é a superfície de pormenor na origem; o validador recusa um pacote em que não seja. A base continua com as suas alturas, que ali podem diferir de alguns metros (modelo de superfície contra terreno nu).
- **Uma só superfície para todos.** Onde a camada de pormenor cobre um ponto, é ela o terreno. Na margem `blend_m` junto à borda, as alturas passam linearmente para as da base. O `vv-geo` em Rust, a interface e a malha desenhada usam a mesma regra, por isso o aviso de trajeto abaixo do terreno, a linha vertical e a imagem concordam.
- **Pontos de controlo por camada.** Cada ponto indica a grelha a que pertence (`base` ou `detail`) e é recalculado com a geodesia do `vv-geo` a 1 mm.
- **Ajustes de apresentação declarados.** Na margem a imagem de pormenor funde-se com a imagem de base. A imagem de pormenor recebe curvas de tom por canal que lhe dão a distribuição da imagem de base em blocos de 10 m (`colour_fit` no manifesto), para que as duas se encontrem sem um quadrado visível. São as únicas alterações aos dados de contexto e estão escritas no manifesto e no painel de fontes.
- **Compatibilidade.** Pacotes v1 continuam a abrir (teste com um pacote sintético v1). A importação copia todos os ficheiros que o pacote declara.

| Ambiente | Pormenor (2 km) | Base (18 km) | Origem | Tamanho |
| --- | --- | --- | --- | --- |
| Cabo Canaveral, Florida | imagem NAIP 2023 (fonte 0,3 m) a 0,5 m; terreno lidar USGS 3DEP de 1 m, amostrado a 4 m | Copernicus GLO-30, Sentinel-2 2025 | centro de um pavimento circular, medido na imagem de 0,5 m (cerca de 2 m); 30 m a sul da origem do 0.16.0 | 4,9 MB |
| Santa Maria, Açores | ortofotomapa SRAAC 2024 (voo de 8 cm) a 0,5 m pelo WMS; alturas Copernicus GLO-30 amostradas a 8 m | Copernicus GLO-30, Sentinel-2 2025 | pastagem aberta nas terras altas a leste; cerca de 430 m da origem do 0.16.0, que estava em floresta | 3,5 MB |
| Spaceport America, Novo México | imagem NAIP 2022 a 0,5 m; terreno lidar USGS 3DEP de 1 m, amostrado a 4 m | Copernicus GLO-30, Sentinel-2 2025 | deserto aberto | 4,8 MB |

Cabo Canaveral e Spaceport America mostram instalações reais na imagem. O pacote di-lo numa nota do local, visível no catálogo e no painel de fontes: o veículo, a plataforma e a missão simulados são genéricos, não são essas instalações nem as suas operações e não implicam qualquer afiliação. Nenhuma área de aterragem ilustrativa é apresentada como infraestrutura verificada.

**Próximo ambiente estudado, não construído:** El Arenosillo (Huelva), com o ortofoto PNOA de 2025 (0,15 m, WMS do IGN) e o MDT05 (WCS da IDEE), CC BY 4.0. O IGN exige a atribuição «Obra derivada de … CC-BY 4.0 scne.es» visível ao pé da vista, o que a linha de créditos permite; falta escrever no script a leitura por WCS. Avaliados e excluídos por agora: Andøya (terreno de 1 m aberto, ortofoto licenciado), Esrange (precisa de conta e as condições do ortofoto podem incluir dados pessoais), SaxaVord (sem dados abertos confirmados), Portugal continental (a DGT não cobre os Açores e o centro de dados pede conta).

## Dados, licenças e lacunas

| Fonte | Licença | Atribuição |
| --- | --- | --- |
| USGS 3DEP, DEM lidar de 1 m | domínio público dos EUA: «USGS-authored or produced data and information are considered to be in the U.S. Public Domain.» | «Elevation: U.S. Geological Survey, 3D Elevation Program» |
| USDA NAIP (cópia do Planetary Computer) | domínio público pela política do FSA: «Public domain information may be freely distributed or copied, but use of appropriate byline/photo/image credits is requested.» | «Imagery: USDA Farm Production and Conservation Business Center, Geospatial Enterprise Operations, NAIP [ano]» |
| Ortofotomapa de Santa Maria 2024 (SRAAC, Governo dos Açores) | CC BY 4.0, segundo o registo ISO 3dbb1054-1690-43a5-b7d7-1835d5f64ef5 | «Ortofotomapa de Santa Maria 2024 © SRAAC/Governo dos Açores, CC BY 4.0, modified (resampled and colour-balanced)» |

Lacunas registadas sem as esconder:

- **NAIP:** não foi encontrado um documento de licença específico do NAIP; a evidência é a declaração geral de domínio público do sítio do FSA. Se as edições posteriores a 2019 têm alguma restrição adicional não está confirmado numa fonte primária.
- **Açores:** a licença CC BY 4.0 vem só do registo de metadados ISO; não foi encontrada outra página de condições, e a forma exata da atribuição pedida pela SRAAC não está confirmada. O registo vai no manifesto como evidência.

Os avisos obrigatórios do Copernicus WorldDEM-30 (art. 6.º, alíneas b e c, com a obrigação de os passar a quem redistribuir) e do Sentinel estão em `desktop/environments/NOTICE.md`, instalado com os pacotes, e por extenso no painel de fontes; a linha curta é um resumo. O IGN espanhol, quando o pacote existir, exige a atribuição visível ao pé da vista: é o que faz a linha de créditos.

## Comparação antes e depois

`docs/evidence/m16/comparison.md` junta as capturas do 0.16.0 instalado (`before/`) e do 0.16.1 instalado (`after/`) pelo mesmo nome: mesma missão («A sensor that lies»), mesmo ambiente, mesmo instante, mesma câmara e mesmo tamanho de janela. A comparação não é perfeitamente igual em dois pontos: as origens de Cabo Canaveral e de Santa Maria mudaram, e a câmara «Na plataforma» não existia antes.

## Desempenho

Medido fora da simulação com `desktop/studio/tests/perf_probe.py --flow m16` no Studio 0.16.1 instalado (instalador `6cb0ffdd…`, igual ao final salvo o texto do seletor e a densidade do nevoeiro), na mesma máquina e janela de 1440x900 do M16, três execuções (`docs/evidence/m16/installed-0.16.1/`):

| Medida | 0.16.0 (2 execuções) | 0.16.1 (3 execuções) |
| --- | --- | --- |
| Mudar para a vista geoespacial até o terreno estar na GPU | 0,145 a 0,149 s | 0,441 a 0,548 s |
| Vista geoespacial: p99 entre fotogramas, acima de 33 ms | 6,2 ms, 0 | 6,2 a 6,3 ms, 0 |
| Vista geoespacial: memória privada / GPU dedicada | 486 a 492 / 197 a 199 MB | 820 a 834 / 314 a 319 MB |
| Vista geoespacial: triângulos | 722 600 | 1 264 890 |
| Mudar para o Mission Control (com paisagem) | 0,149 a 0,156 s | 0,412 a 0,438 s |
| Vista de engenharia: memória privada / GPU dedicada | 323 a 326 / 115 a 120 MB | 352 a 360 / 132 a 136 MB |
| Depois de sair do leitor: memória privada / GPU dedicada | 404 a 422 / 77 a 83 MB | 578 a 641 / 90 MB |
| Sessão de 180 s: memória privada no início / no fim, pior p99 | 644 a 652 / 534 a 546 MB, 6,2 ms | 1049 a 1110 / 889 a 910 MB, 6,4 ms |
| Pedidos da vista web que saem da máquina | 0 | 0 (15 pedidos, todos locais) |

O ecrã limita a 165 fotogramas por segundo; a fluidez não mudou. A camada de pormenor custa cerca de 340 MB de memória privada e 120 MB de GPU, e a troca de vista passa de 0,15 s para cerca de 0,5 s. Numa variante de teste com a imagem de pormenor a 2048 texels (1 m), medida numa compilação local, a memória ficou em 680 MB e a GPU em 255 MB; a resolução é um parâmetro do pacote (`image_spacing_m`). Sair do leitor devolve a GPU a 90 MB e a memória não cresce durante a sessão longa.

## Verificação

- `cargo test -p vv-geo` (20 testes, 5 novos: pacote v1 sintético, camada de pormenor e mistura na margem, regras de esquema e aninhamento, ficheiro de pormenor adulterado, origem na camada mais fina) e `cargo test -p vv-studio` (3 testes, 1 novo: a importação copia os ficheiros de pormenor).
- `desktop/studio/tests/m16_journeys.py` no Studio 0.16.1 instalado: 72 de 72 (eram 45), com o controlo de fontes por rato, teclado e toque sintético, o modo de análise e a ocultação de resultados futuros no leitor e no Mission Control, e o catálogo. `m15_journeys.py`: 48 de 48.
- `desktop/studio/tests/m16_compare_shots.py`: as capturas de antes e depois.

## Limitações

- A física continua em solo plano: a paisagem é contexto. Santa Maria tem 79 m de relevo nos 500 m à volta da plataforma; o aviso de trajeto abaixo do terreno aparece quando se aplica.
- A camada de pormenor cobre 2 km. A base de 18 km continua a 10 m e, para lá dela, o chão é uma extensão da borda sem dados, ilustrativa; não há uma camada de horizonte com dados.
- O andar, a pluma, o céu, o sol, as sombras, a água e a superfície da plataforma nos pacotes sem pormenor são ilustrações. Não há fotorrealismo: é uma cena técnica com dados de contexto reais.
- Em Santa Maria a camada de pormenor só melhora a imagem; as alturas são as do Copernicus.
- Usabilidade não testada com pessoas; o toque foi exercitado com eventos de ponteiro sintéticos, porque a janela de teste não tem ecrã tátil.

## Instalação e reversão

O instalador `VV Lab Studio_0.16.1_x64-setup.exe` (sha256 `96db980e0a1f971ad1c05901d80a19d447f2e632047a66e1baa30a4a177ba351`, 18,5 MB com os três pacotes) instala por utilizador por cima do 0.16.0. Para voltar atrás, desinstalar e correr o instalador do 0.16.0 (sha256 `984f677f7ed831b2398826406c770a5b09e1c816d34faa119c40748333bda10d`). Os anfitriões de domínio continuam no 0.15.0; os registos não mudam.

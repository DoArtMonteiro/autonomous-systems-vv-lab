# M17: catálogo de ambientes geográficos instaláveis

Até ao M16.2 o Studio tinha três pacotes de ambiente, todos incluídos no instalador. O M17 acrescenta cinco locais com dados abertos de alta resolução e licença citável, e passa a distribuir os pacotes como ficheiros instaláveis em separado. O instalador base não muda: continua a trazer os três pacotes de sempre, com os mesmos bytes.

Estado: implementado no ramo `feat/m17-environments`, sobre `feat/m16-geospatial`. Nada foi integrado nem publicado. A instalação, a remoção e a navegação destes pacotes no Studio são de outro fluxo de trabalho, que consome o formato descrito abaixo. Este documento não altera a interface nem o código Rust do Studio.

## O formato do pacote instalável

`scripts/geo/package_environment.py --env <id>` (ou `--all`) escreve

- `dist/environments/<id>-<pack_version>.vvenv.zip`: um zip cuja raiz tem `environment.json`, os ficheiros que o manifesto nomeia (grelhas de alturas, imagens, camada do mundo) e `NOTICE.md`, e mais nada;
- `dist/environments/<id>-<pack_version>.vvenv.zip.sha256`: uma linha `<sha256>  <ficheiro>`;

e atualiza `scripts/geo/environment-index.json` (esquema `vv-geo-environment-index.v1`), com, para cada pacote, o identificador, o nome, o tipo de paisagem, o nível de dados, a versão do pacote, o esquema do manifesto, se vem no instalador, o nome do zip, o tamanho, o SHA-256, a lista de ficheiros, a origem, as licenças em resumo e o número de lacunas de licença declaradas.

Antes de empacotar, cada ficheiro é comparado com o tamanho e o SHA-256 do manifesto; um pacote que não validaria não chega a zip. O zip é determinístico (ordem fixa, data fixa de 1980-01-01, permissões fixas, DEFLATE nível 9): reconstruído a partir do mesmo pacote, dá os mesmos bytes. `NOTICE.md` é gerado a partir do manifesto e da entrada do catálogo: fontes, licenças e atribuições tal como estão no manifesto, lacunas de licença e, quando uma fonte o exige, o texto de licença reproduzido sem modificação.

Só o índice e o pipeline estão no git. `dist/` está no `.gitignore`. Os pacotes do catálogo são construídos em `dist/packs/<id>` e não são incluídos no instalador; os três pacotes incluídos continuam em `desktop/environments/` e são empacotados tal como estão.

## Níveis de dados

| Nível | Definição |
| --- | --- |
| A | Ortofotografia de 1 m ou melhor, terreno lidar de 1 a 2 m na camada de pormenor e camada do mundo com alturas e vegetação medidas numa nuvem de pontos lidar |
| B | Ortofotografia de 1 m ou melhor e terreno lidar ou de levantamento de 5 m ou melhor na camada de pormenor; camada do mundo só do OpenStreetMap, sem vegetação medida |
| C | Ortofotografia de 1 m ou melhor; o terreno de pormenor é a superfície de base de 30 m; camada do mundo só do OpenStreetMap |
| D | Só imagem Sentinel-2 (10 m) e superfície de base de 30 m |

Em todos os níveis a camada de base é a mesma: Copernicus DEM GLO-30 e uma imagem Sentinel-2 L2A de 10 m sobre um quadrado de 18 km, com a camada de pormenor de 2 km ao centro.

## Catálogo

Tamanhos dos zips construídos a 2026-11-05; os SHA-256 completos estão no índice.

| Pacote | Paisagem | Nível | Pormenor (2 km) | Licenças | Zip |
| --- | --- | --- | --- | --- | --- |
| `cape-canaveral` (incluído) | costa baixa de ilha-barreira | A | NAIP 2023 0,3 m, lidar USGS 1 m, lidar 3DEP | domínio público dos EUA, ODbL | 5,29 MB |
| `santa-maria-azores` (incluído) | ilha vulcânica | C | ortofotomapa 2024 8 cm (SRAAC), terreno de 30 m | CC BY 4.0, ODbL | 3,36 MB |
| `spaceport-america` (incluído) | bacia de deserto alto | A | NAIP 2022 0,6 m, lidar USGS 1 m, lidar 3DEP | domínio público dos EUA, ODbL | 4,62 MB |
| `wallops-island` | ilha-barreira atlântica, sapal e praia | A | NAIP 2023 0,6 m, lidar USGS 1 m, lidar 3DEP de 2015 (58 milhões de pontos) | domínio público dos EUA, ODbL | 3,46 MB |
| `mahia-peninsula` | península de pastagens com falésias | B | fotografia aérea LINZ 2023 0,25 m, lidar LINZ 1 m (NZVD2016) | CC BY 4.0 (NIWA, Hawke's Bay Regional Council), ODbL | 4,54 MB |
| `el-arenosillo` | planície arenosa costeira com dunas e pinhal | B | PNOA julho de 2025 0,15 m, MDT05 IGN 5 m (Alicante) | CC BY 4.0 (IGN, scne.es), ODbL | 5,67 MB |
| `goms-alpine-valley` | vale alpino | B | SWISSIMAGE 2023 0,1 m, swissALTI3D 2024 2 m (LN02) | condições OGD da swisstopo, ODbL | 5,36 MB |
| `adventdalen-svalbard` | vale e tundra do Ártico | B | ortofoto NPI de 2009 (20 cm), modelo de terreno NPI 2,5 m | CC BY 4.0 (Instituto Polar Norueguês), ODbL | 4,32 MB |

Todos os pacotes têm também a camada de base (Copernicus DEM GLO-30, licença do Copernicus WorldDEM-30; Sentinel-2 L2A, aviso legal dos dados Sentinel do Copernicus; EGM2008, domínio público dos EUA). Os pacotes novos usam o esquema `vv-geo-environment.v3`, uma camada de pormenor de 2 km com terreno a 4 m e imagem a 0,5 m, e uma camada do mundo.

| Pacote | Edifícios OSM | Vegetação medida |
| --- | --- | --- |
| `wallops-island` | 114 (28 com altura lidar, 86 estimadas) e 12 estruturas lidar | 544 árvores, 64 203 tufos (sobretudo sapal) |
| `mahia-peninsula` | 64 (21 com etiqueta, 43 estimadas) | nenhuma |
| `el-arenosillo` | 93 (46 com etiqueta, 47 estimadas) | nenhuma |
| `goms-alpine-valley` | 1603 (33 com etiqueta, 1570 estimadas) | nenhuma |
| `adventdalen-svalbard` | 730 (25 com etiqueta, 705 estimadas; a maioria na cidade, dentro do raio de 4,5 km do OpenStreetMap) | nenhuma |

## Origem da plataforma em cada local

Em todos os locais a origem foi escolhida sobre a imagem de pormenor e verificada no terreno de pormenor do próprio pacote (o campo `relief` do manifesto, variação da altura desenhada em relação a z = 0). Quando a primeira escolha não era plana, foi procurado na camada de pormenor o ponto aberto com menor variação num raio de 50 m e confirmado na imagem.

| Pacote | Origem | Onde | Relevo a 10 m | Relevo a 50 m |
| --- | --- | --- | --- | --- |
| `wallops-island` | 37,84090° N, 75,48428° W, 1,8 m | campo de areia e erva dentro de uma volta da estrada, a cerca de 85 m do edifício mais próximo e 400 m da praia | -0,07 a +0,15 m | -0,46 a +1,25 m (a berma da estrada) |
| `mahia-peninsula` | 39,24838° S, 177,86738° E, 113 m | pastagem extensa, a cerca de 1,5 km a norte das instalações de lançamento existentes | -0,25 a +0,16 m | -2,6 a +0,7 m (terreno ondulado) |
| `el-arenosillo` | 37,09606° N, 6,73142° W, 36 m | areia aberta com arbustos dispersos a sul de uma faixa de areia retilínea, a cerca de 300 m da praia | 0 a +0,46 m | -1,0 a +1,0 m |
| `goms-alpine-valley` | 46,49688° N, 8,29501° E, 1341 m | prado de feno no fundo do vale, a sul do rio, a cerca de 250 m do fim da pista de um antigo aeródromo | -0,06 a +0,08 m | -0,15 a +0,32 m |
| `adventdalen-svalbard` | 78,21263° N, 15,75957° E, 1,4 m | terraço baixo com tundra entre os canais do rio e uma lagoa, a cerca de 60 m da lagoa | -0,10 a +0,08 m | -0,32 a +0,30 m |

Os locais com uma instalação real dentro do pacote têm um `site_note` com a redação dos pacotes existentes: o veículo, a plataforma e a missão simulados são genéricos, não são essa instalação, as suas operações nem o seu operador, e não implicam qualquer afiliação. Adventdalen não tem instalação na camada de pormenor e não tem `site_note`.

Em Goms e Adventdalen o relevo ultrapassa os 655 m dentro do pacote: o fundo do vale é plano, mas as encostas e os planaltos estão a poucos quilómetros. A simulação continua a assumir solo plano, e o Studio já diz quando o terreno sobe acima de z = 0 junto à trajetória.

## O que mudou no pipeline

O pipeline continua a ser `build_environment.py` (terreno e imagem) seguido de `build_features.py` (camada do mundo), com as definições em `scripts/geo/catalogue.json`. Nenhum local ficou escrito no código: um local novo é uma entrada do catálogo. O renderizador e o validador não mudaram.

- **Fontes de pormenor novas** (`detail_sources.py`): `cog` para ortofotografias e modelos de terreno publicados como GeoTIFF em endereços conhecidos (LINZ, swisstopo, e um GeoTIFF dentro de um zip, no caso do Instituto Polar Norueguês); `wcs` para um modelo de terreno servido por WCS 2.0.1 (IGN); `arcgis` para uma ortofotografia servida por um `export` de ArcGIS (Instituto Polar Norueguês). As quadrículas de uma fonte (por exemplo as de 1 km da swisstopo) são fundidas num só mosaico antes da amostragem, para não ficar uma falha ao longo das juntas.
- **Datum vertical explícito**: cada modelo de terreno declara o seu CRS composto (por exemplo `EPSG:2193+7839`) e o CRS elipsoidal de chegada; o PROJ escolhe a grelha do geoide e a conversão falha se não houver grelha ou se nada mudar. O manifesto regista a operação que o PROJ usou de facto.
- **Licenças como dados**: as licenças das fontes novas estão no catálogo (chave `licences`), cada uma com uma frase de exatidão que vai para o manifesto.
- **Relevo de montanha**: o passo de quantização das alturas passou a ser configurável (`height_scale_m`, 1 cm por omissão; 5 cm na base e 2 cm no pormenor para Goms e Adventdalen), porque 16 bits a 1 cm só cobrem 655 m de relevo.
- **Copernicus acima de 50° de latitude**: o espaçamento em longitude do GLO-30 é maior do que em latitude (3" contra 1" a 78° N); a janela mantém os dois espaçamentos em vez de os reamostrar para pixels quadrados. Há um teste de regressão com mosaicos sintéticos.
- **Convergência em encostas**: o limite de iterações dos pontos de superfície subiu de 10 para 40; os pacotes que convergiam em 10 ficam iguais.

Os três pacotes incluídos não foram reconstruídos: os seus bytes são os do M16.2, e os zips são feitos a partir deles.

## O que é ilustrativo

Tudo o que já era ilustrativo no M16.2 continua a sê-lo: paredes, telhados planos e formas das plantas, a margem de transição entre camadas e as curvas de tom que levam a imagem de pormenor aos tons da imagem de base. Nos pacotes de nível B e C não há vegetação: não há nuvem de pontos e nada é inventado. As alturas dos edifícios do OpenStreetMap sem etiqueta são estimativas por tipo e o painel de fontes diz quantas são. A simulação continua a assumir solo plano em z = 0; o terreno, os edifícios e a vegetação não entram em nenhum cálculo.

## Locais considerados e não incluídos

| Local | Porque não |
| --- | --- |
| Vandenberg, Califórnia | O NAIP de 2012 e 2014 é o único no Planetary Computer para esta zona e tem a terra mascarada (pixels a preto) dentro da base; anos posteriores não existem. Sem imagem de pormenor da terra, o pacote não acrescentava nada. |
| Andøya, Noruega | A ortofotografia "Norge i bilder" está sob a licença Norge digitalt, não sob uma licença aberta citável; o modelo de terreno da Kartverket é CC BY 4.0, mas sozinho daria um pacote de nível D com relevo melhor. |
| Esrange, Suécia | Os dados abertos da Lantmäteriet exigem conta e chave de acesso; o pipeline só usa fontes sem conta. |
| Kourou, Guiana Francesa | Não foi tentado neste ciclo. |

## Lacunas

- **Sem nuvem de pontos fora dos EUA.** Mahia, El Arenosillo, Goms e Adventdalen não têm vegetação nem estruturas medidas: só edifícios do OpenStreetMap. Em Goms a floresta das encostas não está desenhada. O LINZ publica um modelo de superfície de 1 m que permitiria a vegetação de Mahia; não foi usado.
- **Datum vertical do Instituto Polar Norueguês.** Não está indicado; as alturas foram tratadas como acima do EGM2008 e a diferença medida contra o Copernicus fica no manifesto.
- **Atribuições.** A data do MDT05 do IGN não é conhecida, pelo que a atribuição exigida pela licença do IGN fica sem data. A licença do Instituto Polar Norueguês exige que o seu ficheiro de texto acompanhe os dados sem modificação: o texto está reproduzido no `NOTICE.md`, mas a instalação no Studio pode não copiar o `NOTICE.md` (ver abaixo).
- **`NOTICE.md` e a instalação.** O zip leva o `NOTICE.md` na raiz, ao lado dos ficheiros do manifesto. O validador ignora ficheiros que o manifesto não nomeia, e a importação de uma pasta no Studio 0.16.2 copia só os ficheiros do manifesto. Quem implementar a instalação a partir do zip deve guardar também o `NOTICE.md` com o pacote, para cumprir as condições das fontes.
- **Datas diferentes.** Em Wallops o lidar é de 2015 e a imagem de 2023; em Mahia o lidar é de 2020 e 2021 e a imagem de 2023; em Adventdalen a imagem é de 2009. O que mudou entretanto não coincide.
- **Datums horizontais nacionais lidos como WGS84**, com desvios da ordem de 1 a 2 m declarados em cada manifesto.
- **Verificação de registo da imagem de base.** O campo `registration` compara a máscara de terra do DEM com a água escura da imagem; em Goms dá o melhor desvio no limite da procura (300 m), porque não há mar e as sombras das encostas passam por água. Nesse pacote o número não mede o registo e não deve ser lido como erro de 300 m.
- **Sentinel-2 em Adventdalen e Goms** tem neve e sombras longas de verão ártico ou alpino; a imagem de base não foi editada.

## Evidência visual

`docs/images/m17-environments/` tem uma captura por pacote novo da vista geoespacial do Studio 0.16.2 instalado (missão «Land a rocket», T+6 s, câmara «Whole descent», janela de 1440x900), com os pacotes descompactados dos zips e indicados ao Studio por `VVLAB_ENVIRONMENTS`. Os oito pacotes foram validados pelo Studio e nenhum foi recusado. As capturas mostram que os pacotes abrem e se desenham; não são uma avaliação de qualidade visual.

## Pacotes incluídos no Studio

Os cinco pacotes novos (`wallops-island`, `mahia-peninsula`, `el-arenosillo`, `goms-alpine-valley`, `adventdalen-svalbard`) passam a ir em `desktop/environments`, como os três primeiros, e o instalador leva os oito. Antes só se instalavam por um diálogo nativo de ficheiros, a partir de zips fora do git, por isso um utilizador não os descobria. Acrescentam 26 909 526 bytes de ficheiros de pacote ao git (cerca de 23 MB nos zips, porque as imagens JPEG e as grelhas já estão comprimidas), de propósito. O `NOTICE.md` de `desktop/environments` reúne agora as fontes, as licenças e as atribuições dos oito, incluindo o texto de licença do Norwegian Polar Institute reproduzido sem modificação. Os pacotes são os mesmos bytes dos zips com os SHA-256 do índice; `bundled` está a `true` no catálogo e no índice, e o teste `indexed_packs_validate_with_the_indexed_schema_and_files` exige agora oito pacotes incluídos.

## Verificação

- `vv-geo`: o teste novo `indexed_packs_validate_with_the_indexed_schema_and_files` abre cada pacote do índice com o validador do Studio e confirma o esquema e a lista de ficheiros. Os pacotes do catálogo não estão no git; o teste valida-os a partir dos zips descompactados na pasta indicada por `VV_GEO_PACK_ROOT` e falha se faltar algum. Corrido com os oito: 3 incluídos e 5 do catálogo validados.
- `tests/test_geo_environment_packages.py`: o índice lista todas as entradas do catálogo com os campos documentados; os três pacotes incluídos reconstroem-se nos mesmos bytes e SHA-256 do índice; os zips presentes em `dist/` têm só o manifesto, os seus ficheiros e o aviso, com os hashes do manifesto; um ficheiro alterado não é empacotado.
- `tests/test_geo_pipeline.py` (só com as bibliotecas do construtor de pacotes; de outro modo é ignorado): janela do Copernicus com pixels não quadrados a 78° N, e entradas do catálogo com fontes e licenças conhecidas e grelhas que cobrem a camada exatamente.
- Em `desktop/`: `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings` e `cargo test` passam (`vv-geo` com 24 testes; o `cargo test` foi corrido com `VV_GEO_PACK_ROOT` e depois de `cargo build --release` na raiz, de que os testes dos domínios precisam). O `clippy` do Studio precisa das pastas de recursos `target/release/{domains,engines,discovery}`, que só existem depois de uma compilação de release do Studio; aqui foram criadas vazias.
- Na raiz: `python -m unittest discover -s tests -p "test_*.py"`, 377 testes, 96 ignorados (os que precisam das bibliotecas do construtor de pacotes ou de outros binários).
- O código Rust e a interface do Studio não mudaram.

## Como reconstruir

```sh
python -m venv .geovenv
.geovenv/Scripts/pip install rasterio pyproj numpy pillow shapely "laspy[lazrs]"
.geovenv/Scripts/python -I scripts/geo/build_environment.py --env goms-alpine-valley --out dist/packs --raw <pasta de cache>
.geovenv/Scripts/python -I scripts/geo/build_features.py --env goms-alpine-valley --pack dist/packs/goms-alpine-valley --raw <pasta de cache>/features
python scripts/geo/package_environment.py --env goms-alpine-valley
```

Uma reconstrução volta a descarregar os dados das fontes. Os dados do OpenStreetMap e as imagens servidas por WMS e ArcGIS podem ter mudado entretanto, por isso os bytes e o SHA-256 de um pacote reconstruído podem diferir dos do índice; o empacotamento de um mesmo pacote, esse, é determinístico.

# Avisos dos dados geográficos

Os pacotes de ambiente desta pasta contêm dados de terceiros, adaptados (reamostrados para uma grelha local este-norte-cima e comprimidos). Cada `environment.json` identifica as fontes, os itens usados, a licença e a atribuição. Este ficheiro acompanha os pacotes no repositório e no instalador.

Quem redistribuir estes pacotes, modificados ou não, fica obrigado às mesmas condições e deve manter este aviso e as atribuições de cada manifesto.

## Copernicus DEM GLO-30 (Copernicus WorldDEM-30)

Licença: Licence for the use of the Copernicus WorldDEM-30, https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf

Aviso obrigatório (art. 6.º, alínea b), para dados adaptados):

> produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved

Aviso de responsabilidade (art. 6.º, alínea c):

> The organisations in charge of the Copernicus programme by law or by delegation do not incur any liability for any use of the Copernicus WorldDEM-30

O uso destes dados não implica qualquer aprovação do V&V Lab pelas entidades responsáveis pelo programa Copernicus (art. 6.º, alínea d). Os utilizadores seguintes ficam vinculados às mesmas obrigações (art. 6.º, alínea e).

## Copernicus Sentinel-2

Aviso legal sobre o uso de dados Copernicus Sentinel, https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice

Aviso obrigatório para dados modificados: "Contains modified Copernicus Sentinel data [ano]", com o ano indicado no manifesto de cada pacote.

## EGM2008

Ondulação do geoide EGM2008, U.S. National Geospatial-Intelligence Agency, obtida através da grelha `us_nga_egm08_25` do PROJ. Obra do Governo dos Estados Unidos, domínio público.

## Camadas de pormenor

Os pacotes com camada de pormenor (`detail-height.u16`, `detail-image.jpg`) usam também as fontes seguintes. O manifesto de cada pacote indica os itens usados e o tratamento aplicado (reamostragem, curvas de tom ajustadas à imagem de base, margem de transição).

- USGS 3D Elevation Program, modelo digital de elevação lidar de 1 m (Cape Canaveral, Spaceport America, Wallops Island). Domínio público dos Estados Unidos: "USGS-authored or produced data and information are considered to be in the U.S. Public Domain." (https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits). Atribuição: "Elevation: U.S. Geological Survey, 3D Elevation Program".
- USDA National Agriculture Imagery Program (NAIP), ortoimagem (Cape Canaveral 2023, Spaceport America 2022, Wallops Island 2023). Domínio público segundo a política do FSA: "Public domain information may be freely distributed or copied, but use of appropriate byline/photo/image credits is requested." (https://www.fsa.usda.gov/help/policies-and-links). Não foi encontrado um documento de licença específico do NAIP. Atribuição: "Imagery: USDA Farm Production and Conservation Business Center, Geospatial Enterprise Operations, NAIP [ano]".
- Ortofotomapa de Santa Maria 2024, Secretaria Regional do Ambiente e Ação Climática, Governo dos Açores (SRAAC). CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), segundo o registo de metadados ISO 3dbb1054-1690-43a5-b7d7-1835d5f64ef5 do catálogo IDEiA; não foi encontrada outra página de condições e a forma exata da atribuição não está confirmada. Atribuição usada: "Ortofotomapa de Santa Maria 2024 © SRAAC/Governo dos Açores, CC BY 4.0, modified (resampled and colour-balanced)".

## Camada do mundo (esquema v3)

Os pacotes com camada do mundo (`features.json`, `vegetation.bin`) usam também as fontes seguintes. O manifesto de cada pacote indica, no bloco `world`, as contagens, a origem de cada altura, o carimbo temporal dos dados do OpenStreetMap e as regras de classificação.

- OpenStreetMap, contornos de edifícios e estruturas altas, obtidos pela API Overpass. © OpenStreetMap contributors. Licença Open Data Commons Open Database License (ODbL) 1.0, https://opendatacommons.org/licenses/odbl/1-0/ e https://www.openstreetmap.org/copyright. O ficheiro `features.json` de cada pacote é uma base de dados derivada de dados do OpenStreetMap e é disponibilizado nos termos da ODbL 1.0: quem o redistribuir, modificado ou não, deve manter esta atribuição, indicar a licença e disponibilizar nos mesmos termos qualquer base de dados derivada. Atribuição: "© OpenStreetMap contributors".
- USGS 3D Elevation Program, nuvens de pontos lidar (cópias Entwine Point Tile em `s3://usgs-lidar-public`): projeto FL_Peninsular_FDEM_Brevard_2018 (Cape Canaveral), NM_SouthCentral_B7_2018 (Spaceport America) e USGS_LPC_VA_Eastern_ShoreBAA_2015_LAS_2017 (Wallops Island). Domínio público dos Estados Unidos, como o modelo de elevação acima. Usadas apenas para alturas acima do solo do próprio levantamento, em células de 1 m. Atribuição: "Lidar: U.S. Geological Survey, 3D Elevation Program".
- USDA NAIP, bandas do vermelho e do infravermelho próximo, só para o índice de vegetação; não são desenhadas. Domínio público, como a ortoimagem acima.

As formas desenhadas (paredes, telhados planos, copas e folhas) são ilustrativas; as posições, os contornos e as alturas vêm dos dados, com a origem de cada altura indicada no ficheiro.

## Pacotes de ambiente do M17

Os cinco pacotes seguintes (`wallops-island`, `mahia-peninsula`, `el-arenosillo`, `goms-alpine-valley`, `adventdalen-svalbard`) usam também as fontes abaixo na camada de pormenor, além das fontes de base e da camada do mundo já descritas (Copernicus DEM GLO-30, Sentinel-2, EGM2008 e OpenStreetMap, em todos; USGS 3DEP e NAIP em Wallops Island). Este texto reúne o `NOTICE.md` de cada pacote; o `environment.json` de cada pacote indica os itens usados e o tratamento aplicado (reamostragem, curvas de tom, conversão para alturas elipsoidais).

Em cada local o veículo, a plataforma e a missão simulados são genéricos: não são a instalação, a operação ou a entidade que existe no local e não implicam qualquer afiliação. A imagem de pormenor de Wallops Island cobre parte de um campo de lançamento existente e dos seus edifícios; a de El Arenosillo cobre parte de um centro de lançamento e ensaio de foguetões; a de Goms cobre um antigo aeródromo militar; o pacote de Mahia cobre um local de lançamento existente, a cerca de 1,5 km a sul da origem da plataforma.

### Mahia Peninsula, Nova Zelândia (LINZ, CC BY 4.0)

- Hawke's Bay LiDAR 1m DEM (2020-2021), terreno nu, alturas em NZVD2016. Fornecedor: Toitū Te Whenua Land Information New Zealand (anfitrião e processador); Ocean Infinity (produtor); Hawke's Bay Regional Council (licenciante). Licença: CC BY 4.0, "Licensed for re-use under CC-BY-4.0" (https://registry.opendata.aws/nz-elevation), https://creativecommons.org/licenses/by/4.0/. Atribuição: "Hawke's Bay LiDAR 1m DEM (2020-2021), licensed by Hawke's Bay Regional Council for re-use under CC-BY-4.0; accessed on 2026-11-04 from https://registry.opendata.aws/nz-elevation; modified (resampled and converted to ellipsoidal heights)".
- Hawke's Bay 0.25m Rural Aerial Photos (2023-2025), bandas vermelha, verde e azul. Fornecedor: Toitū Te Whenua Land Information New Zealand (anfitrião e processador); Aerial Surveys (produtor); National Institute of Water and Atmospheric Research (licenciante). Licença: CC BY 4.0, "Licensed for re-use under CC-BY-4.0" (https://registry.opendata.aws/nz-imagery), https://creativecommons.org/licenses/by/4.0/. Atribuição: "Hawke's Bay 0.25m Rural Aerial Photos (2023-2025), licensed by National Institute of Water and Atmospheric Research for re-use under CC-BY-4.0; accessed on 2026-11-04 from https://registry.opendata.aws/nz-imagery; modified (resampled and colour-balanced)".
- Lacunas: a atribuição segue o modelo do registo AWS Open Data ("Licensed by (insert the licensor) for re-use under CC-BY-4.0") com o licenciante de cada coleção STAC; não foi encontrada outra forma prescrita. Sem nuvem de pontos lidar: a camada do mundo tem só edifícios do OpenStreetMap e nenhuma vegetação.

### El Arenosillo, Huelva, Espanha (IGN, CC BY 4.0, scne.es)

- MDT05, modelo digital do terreno de 5 m do lidar do PNOA (cobertura WCS Elevacion25830_5), alturas ortométricas (REDNAP, EPSG:5782). Fornecedor: Instituto Geográfico Nacional de España (IGN). Licença: CC BY 4.0 segundo a licença do IGN para os seus produtos e serviços de informação geográfica (Orden FOM/2807/2015); o WCS indica "CC BY 4.0 scne.es" em AccessConstraints. https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf. Atribuição: "Obra derivada de MDT05 CC-BY 4.0 scne.es".
- Mosaico de ortofotografia do PNOA, cobertura mais recente (camada WMS OI.OrthoimageCoverage; na origem da plataforma o elemento do mosaico é de julho de 2025, 0,15 m). Fornecedor: Instituto Geográfico Nacional de España (IGN) e as comunidades autónomas, Plan Nacional de Ortofotografía Aérea (PNOA). Licença: CC BY 4.0 segundo a licença do IGN (Orden FOM/2807/2015): "el uso de los productos y servicios de información geográfica del IGN [...] conlleva la aceptación por el usuario de una licencia CC-BY 4.0"; as obras derivadas acrescentam "Obra derivada de" à atribuição. O WMS indica "CC BY 4.0 scne.es" em AccessConstraints. Atribuição: "Obra derivada de PNOA 2025 CC-BY 4.0 scne.es".
- Lacunas: a licença do IGN pede a data do produto na atribuição («<identificador do produto> <data> CC-BY 4.0 <produtores>»); o WCS não indica a data da cobertura do MDT05 neste local, por isso a atribuição do MDT05 não tem data. A licença pede também que a expressão de reconhecimento conste dos metadados de um conjunto de dados derivado; aqui consta do campo `attribution` de cada fonte em `environment.json` e deste aviso. Sem nuvem de pontos lidar: a camada do mundo tem só edifícios do OpenStreetMap e nenhuma vegetação.

### Goms, Valais, Suíça (swisstopo, OGD)

- swissALTI3D 2024, modelo de elevação do terreno nu, quadrículas de 2 m, alturas em LN02 (EPSG:5728). Fornecedor: Federal Office of Topography swisstopo. Atribuição: "Source: Federal Office of Topography swisstopo (swissALTI3D, 2024), modified (resampled and converted to ellipsoidal heights)".
- SWISSIMAGE 10 cm, mosaico de ortofotografia, quadrículas de 2023 (GeoTIFF de 1 km, 0,1 m). Fornecedor: Federal Office of Topography swisstopo. Atribuição: "Source: Federal Office of Topography swisstopo (SWISSIMAGE 10 cm, 2023), modified (resampled and colour-balanced)".
- Licença de ambos: termos de uso dos geodados e geoserviços gratuitos da swisstopo (OGD), versão 1.3.2021: "The free geodata and geoservices of swisstopo may be used, distributed and made accessible. Furthermore, they may be enriched and processed and also used commercially. A reference to the source is mandatory." https://www.swisstopo.admin.ch/en/terms-of-use-free-geodata-and-geoservices
- Lacunas: o campo de licença das coleções STAC da swisstopo diz "proprietary"; as condições aplicáveis são as condições OGD citadas acima, ligadas como condições de uso na página de cada produto. Sem nuvem de pontos lidar: a camada do mundo tem só edifícios do OpenStreetMap e nenhuma vegetação, embora a floresta cubra boa parte das encostas.

### Adventdalen, Svalbard (Norwegian Polar Institute, CC BY 4.0)

- S0 Terrengmodell, modelo regional DTM2_5 2009, projeto 13835, zona de Longyearbyen (grelha de 2,5 m, sobretudo de modelos estereoscópicos de fotografias aéreas). Fornecedor: Norwegian Polar Institute (Norsk Polarinstitutt). Atribuição: "Terrain model © Norwegian Polar Institute (S0 Terrengmodell), CC BY 4.0, modified (resampled and converted to ellipsoidal heights)".
- NP Ortofoto Svalbard (fotografias aéreas de 2009, projeto 13835, 20 cm segundo o índice de cobertura do NPI), exportada pelo serviço ArcGIS do NPI. Atribuição: "Orthophoto © Norwegian Polar Institute, CC BY 4.0, modified (resampled and colour-balanced)".
- Licença de ambos: CC BY 4.0, https://creativecommons.org/licenses/by/4.0/ ("The map data is licensed under the Creative Commons Attribution 4.0 International License." "MAP DATA FROM THE NORWEGIAN POLAR INSTITUTE MUST BE CREDITED WHEN USED."). O ficheiro de licença do NPI exige que acompanhe sem modificação todas as cópias dos dados ou de dados derivados; o texto está reproduzido sem modificação abaixo, mas o ficheiro original não está nos pacotes.
- Lacunas: o datum vertical do modelo de terreno do NPI não é indicado; as alturas foram tratadas como altitudes acima do EGM2008, com a diferença medida indicada no manifesto. Sem nuvem de pontos lidar, e a tundra não tem árvores: a camada do mundo tem só edifícios do OpenStreetMap.

Texto de licença do Norwegian Polar Institute (`_Lisens_License.txt`, reproduzido sem modificação):

```text
Kartdata © Norsk Polarinstitutt
-------------------------------

Kartdataene er lisensiert under Creative Commons Navngivelse 4.0 Internasjonal-lisensen. For å se en kopi av denne lisensen, besøk http://creativecommons.org/licenses/by/4.0/ eller send et brev til Creative Commons, PO Box 1866, Mountain View, CA 94042, USA.

KARTDATA FRA NORSK POLARINSTITUTT SKAL KREDITERES VED BRUK. DELER AV KARTDATAENE ER AV ELDRE DATO OG IKKE EGNET FOR NAVIGASJON. Se også lisenstekstens kapittel 5. Garantier og ansvarsfraskrivelse.

For metadata og kartdatanedlastning, besøk https://data.npolar.no. Alternativt, og for Norge digitalt-parter, https://www.geonorge.no.

Denne tekstfilen skal følge umodifisert med alle kopier av kartdataene, deler av kartdataene eller avledede data.


- - - - -


Map data © Norwegian Polar Institute
------------------------------------

The map data is licensed under the Creative Commons Attribution 4.0 International License. To view a copy of this license, visit http://creativecommons.org/licenses/by/4.0/ or send a letter to Creative Commons, PO Box 1866, Mountain View, CA 94042, USA.

MAP DATA FROM THE NORWEGIAN POLAR INSTITUTE MUST BE CREDITED WHEN USED. PARTS OF THE MAP DATA ARE OF OLDER ORIGIN AND NOT SUITED FOR NAVIGATION. See also licence Section 5 – Disclaimer of Warranties and Limitation of Liability.

For metadata and map data downloads, visit https://data.npolar.no. Alternatively, and for Norway digital partners, https://www.geonorge.no.

This text file must follow unmodified with all copies of the map data, parts of the map data, or derived data.
```

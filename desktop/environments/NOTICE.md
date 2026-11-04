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

- USGS 3D Elevation Program, modelo digital de elevação lidar de 1 m (Cape Canaveral, Spaceport America). Domínio público dos Estados Unidos: "USGS-authored or produced data and information are considered to be in the U.S. Public Domain." (https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits). Atribuição: "Elevation: U.S. Geological Survey, 3D Elevation Program".
- USDA National Agriculture Imagery Program (NAIP), ortoimagem (Cape Canaveral 2023, Spaceport America 2022). Domínio público segundo a política do FSA: "Public domain information may be freely distributed or copied, but use of appropriate byline/photo/image credits is requested." (https://www.fsa.usda.gov/help/policies-and-links). Não foi encontrado um documento de licença específico do NAIP. Atribuição: "Imagery: USDA Farm Production and Conservation Business Center, Geospatial Enterprise Operations, NAIP [ano]".
- Ortofotomapa de Santa Maria 2024, Secretaria Regional do Ambiente e Ação Climática, Governo dos Açores (SRAAC). CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), segundo o registo de metadados ISO 3dbb1054-1690-43a5-b7d7-1835d5f64ef5 do catálogo IDEiA; não foi encontrada outra página de condições e a forma exata da atribuição não está confirmada. Atribuição usada: "Ortofotomapa de Santa Maria 2024 © SRAAC/Governo dos Açores, CC BY 4.0, modified (resampled and colour-balanced)".

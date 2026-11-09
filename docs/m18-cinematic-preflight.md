# M18: avaliação prévia do Unreal Engine 5 e do Cesium for Unreal para a Cinematic View

Estado: avaliação prévia só de leitura, feita em 2026-11-08. Nada foi instalado, nenhuma licença foi aceite, nenhuma conta ou ficha de acesso foi criada e nenhum período de teste foi iniciado. As únicas medições são as do próprio computador (secção 4). Tudo o resto vem de páginas públicas, com a data de acesso indicada, e o que não foi possível confirmar está assinalado como tal.

## 1. Resumo e recomendação

Recomendação: **não instalar o Unreal Engine 5 nem o Cesium for Unreal agora.** Manter a Cinematic View em Godot 4.7.2 e investir primeiro nos dados e nos modelos, que as duas avaliações independentes do M17 apontaram como o limite real da fidelidade. Detalhes na secção 7.

Razões curtas:

1. Mudar de motor não cria fotorrealismo. Os revisores do M17 disseram que o limite são o andar, as árvores e os edifícios (arte) e a resolução das imagens (dados). Com os mesmos dados e os mesmos modelos, o UE5 dá melhor céu, nuvens e sombras, mas não resolve estes dois pontos.
2. O custo em disco é grande e incerto (ver secção 3): relatos de mais de 110 GB para a instalação por omissão do UE 5.6, num disco C com 94,6 GB livres.
3. Os termos do EULA da Epic não puderam ser lidos na fonte (as páginas oficiais devolveram HTTP 403 a este agente). As conclusões sobre royalties e licenças por posto assentam em fontes secundárias.
4. O Cesium for Unreal, a parte que justificaria o UE5 para geografia, só funciona offline com dados locais; o Cesium World Terrain e os outros dados do Cesium ion não funcionam offline sem licença comercial. O produto já tem pacotes locais (`vv-geo`) de uma região de cerca de 18 km, para a qual não é preciso georreferência global.
5. O módulo atual aceita no máximo 1 GiB, 512 ficheiros e 512 MiB por ficheiro (`desktop/studio/src/modules.rs`). Uma compilação empacotada do UE5 com conteúdo ultrapassa provavelmente estes limites e exigiria alterar o ciclo de instalação.

## 2. Licenças

Data de acesso a todas as ligações: 2026-11-08.

### 2.1 Unreal Engine (EULA e termos para uso fora de jogos)

Fontes primárias que não foi possível abrir: `https://www.unrealengine.com/eula/unreal`, `https://www.unrealengine.com/license` e `https://www.unrealengine.com/eula-change-log/unreal` devolveram HTTP 403 (testado com o WebFetch e com `curl`). **Não foi lido o texto atual do EULA nem do Royalty Addendum.** O que se segue vem de resumos que citam a Epic e deve ser confirmado pelo responsável na fonte antes de qualquer aceitação.

| Ponto | O que as fontes dizem | Fonte | Confirmação |
| --- | --- | --- | --- |
| Royalties de jogos | 5 % sobre a receita bruta acima de 1 000 000 USD por produto; sem royalties nos primeiros 1 milhão | Resumo da pesquisa dirigida a `unrealengine.com`, que cita o FAQ da Epic ([`https://www.unrealengine.com/license`](https://www.unrealengine.com/license)); Engadget: "five percent royalty on software that earns over $1 million" ([artigo](https://www.engadget.com/epic-will-charge-non-game-developers-1850-per-seat-to-use-unreal-engine-162015997.html)) | Secundária |
| Produtos sem receita | Um produto que não gera receita, direta ou por benefícios dentro do produto, não paga royalties | Resumo da mesma pesquisa (Royalty Addendum) | Secundária; texto não lido |
| Produtos sem código do motor | Sem royalties se não incluir código do motor nem precisar dele para correr (exemplo: vídeo renderizado) | Idem | Secundária; não se aplica a nós, a aplicação empacotada inclui o motor |
| Uso fora de jogos | "Companies that make less than $1 million in annual gross revenue won't have to pay the fee." Estudantes, educadores e curiosos estão isentos. A taxa é de 1 850 USD por posto e por ano, a partir do UE 5.4 (abril de 2024) | [Engadget, 2024-03-12](https://www.engadget.com/epic-will-charge-non-game-developers-1850-per-seat-to-use-unreal-engine-162015997.html) | Secundária, de 2024; não confirmada para 2026. Vários sítios de 2026 repetem o valor sem citar a Epic |
| Quem paga a taxa por posto | Segundo a Cartoon Brew, aplica-se a quem não cria aplicações licenciadas a utilizadores finais de terceiros e usa código do motor em tempo de execução ([artigo](https://www.cartoonbrew.com/tools/epic-games-unveils-new-per-seat-pricing-for-non-game-developers-using-unreal-engine-238987.html)) | Cartoon Brew, via resumo | Secundária |
| Licenças personalizadas | Existe um Programa Enterprise com termos à medida; uma fonte de 2023 indica 1 500 USD por posto, valor anterior ao de 1 850 | Resumo da pesquisa | Desatualizada |
| Registo de lançamento | Antes de distribuir um produto sujeito a royalties é preciso notificar a Epic (formulário "Release Form"); uma atualização posterior fez da notificação uma condição da exclusão do primeiro milhão | Resumo da pesquisa dirigida | Secundária |
| Último registo de alterações visto | Junho de 2025 (resumo); o texto de 2026 não foi lido | [Registo de alterações do EULA](https://www.unrealengine.com/eula-change-log/unreal) | Não aberto (403) |

Sobre a distribuição de uma aplicação UE empacotada como módulo opcional: **não foi possível confirmar as condições de redistribuição** (notificação à Epic, cláusulas de código distribuível, avisos obrigatórios) por falta do texto do EULA. O que o próprio repositório e as fontes secundárias sugerem é que uma aplicação UE empacotada se distribui livremente quando o autor não ultrapassa o limiar de 1 milhão de USD, mas isto é uma inferência, não uma citação.

O PDF do EULA que o WebFetch conseguiu descarregar (`https://cdn2.unrealengine.com/unreal-engine-end-user-license-agreement-d2812e10c642.pdf`) é de 2022-03-24, anterior à reorganização em Royalty Addendum, e o texto não era extraível. Não foi usado.

Acesso à Epic: o fluxo normal exige o Epic Games Launcher, uma conta Epic e a aceitação do EULA na primeira utilização. Os dados de utilização anónimos do editor vêm ativos por omissão (afirmação já registada em `docs/m17-cinematic.md`, de um EULA antigo; não reconfirmada).

### 2.2 Cesium for Unreal

- Licença do plugin, fonte primária: "Cesium for Unreal is free for both commercial and non-commercial use." Licença Apache 2.0 ([repositório](https://github.com/CesiumGS/cesium-unreal); [FAQ](https://cesium.com/learn/unreal/unreal-faq/): "the Cesium for Unreal plugin is free and open source under the Apache 2.0 license").
- Versões do UE: "Cesium for Unreal's standard policy is to support the three most recent versions of Unreal Engine." A pesquisa encontrou a versão v2.31.0, que declara suporte para o UE 5.6, 5.7 e 5.8 ([notas da v2.31.0](https://github.com/CesiumGS/cesium-unreal/releases/tag/v2.31.0)); a data aparece como 29 de outubro na página e 2 de novembro de 2026 no registo de alterações. **A data não foi confirmada.** A página de FAQ ainda lista o UE 4.26 a 5.0 e está desatualizada.
- Cesium ion, fonte primária (página de preços, via WebFetch): plano Community "Personal and non-commercial use", 10 GB de armazenamento e 15 GB por mês de transmissão. Uma conta comercial é necessária se a empresa tiver "more than $50K in annual gross revenues" ou tiver angariado mais de 50 000 USD. Planos comerciais: 149 USD por mês (individual) e 524 USD por mês (equipa) ([preços do Cesium ion](https://cesium.com/platform/cesium-ion/pricing/)). O Cesium ion Self-Hosted é só por contacto comercial, sem preço público.
- **Os termos de serviço do Cesium ion não foram lidos na fonte.** Segundo a equipa do Cesium no fórum, descarregar tiles individuais "violates many data providers' terms of use" e não é possível no plugin ([fórum](https://community.cesium.com/t/does-cesium-for-unreal-work-offline/17271)).

### 2.3 Dados de terceiros (Google, Bing)

- Google, fonte primária ([políticas da Map Tiles API](https://developers.google.com/maps/documentation/tile/policies)): "you must not pre-fetch, index, store, or cache any Content except under the limited conditions stated in the terms" e é proibido "Offline uses". Os Google Photorealistic 3D Tiles ficam, portanto, fora de um produto que tem de correr offline.
- Bing e Cesium World Terrain: o FAQ do Cesium diz que "Cesium World Terrain and other Cesium ion tilesets are not currently available offline", e a equipa do Cesium diz no fórum que os dados do ion podem ser licenciados para uso offline contactando as vendas; Bing Maps e Google são "still not feasible" offline.

### 2.4 As nossas licenças de dados

Os pacotes locais (Copernicus DEM, ortofotos, vegetação lidar, edifícios OSM com ODbL, licenças CC BY e domínio público) são independentes do motor. Seja qual for o motor, os avisos de atribuição que já aparecem na Cinematic View (ODbL visível, tecla C para todas as atribuições) têm de ser mantidos.

## 3. Capacidade offline

| Pergunta | Resposta | Fonte |
| --- | --- | --- |
| O Cesium for Unreal carrega 3D Tiles locais sem Cesium ion? | Sim: "Tiles loaded in these ways will not need internet access to appear in Unreal." Aceita caminho em disco ou servidor local | [FAQ](https://cesium.com/learn/unreal/unreal-faq/) |
| Cesium World Terrain offline? | Não, sem licença comercial | [FAQ](https://cesium.com/learn/unreal/unreal-faq/) |
| Quantized-mesh e GeoTIFF locais? | **Não confirmado.** O FAQ só fala de tilesets locais. Não foi encontrada documentação oficial que diga que o plugin carrega terreno quantized-mesh ou GeoTIFF diretamente de disco sem o ion | Lacuna |
| Ferramentas abertas para converter MDT e ortofoto em 3D Tiles | O `3d-tiles-tools` (Apache-2.0) converte entre formatos de tileset e glTF/B3DM, mas **não** converte MDT nem imagens em tiles, segundo a sua página ([repositório](https://github.com/CesiumGS/3d-tiles-tools)). O `cesium-terrain-builder` com saída quantized-mesh vem de ramos e de um contentor Apache-2.0 da `tum-gis` ([contentor](https://github.com/tum-gis/cesium-terrain-builder-docker)); a licença do repositório original não foi confirmada. A licença do `py3dtiles` e a sua capacidade para malhas de terreno não foram confirmadas | Lacuna |

Consequência: com os dados que temos (grelhas `height.u16` e `image.jpg` de cerca de 18 km), a via mais curta no UE5 seria **sem Cesium**: gerar uma malha de terreno a partir dos ficheiros que o módulo já valida, com as mesmas regras de amostragem do `vv-geo`. O Cesium só traria valor se o produto precisasse de dados globais em streaming, o que a regra de funcionar offline com pacotes locais exclui. Se mesmo assim se quisesse 3D Tiles, seria preciso escrever um conversor próprio em Rust (malha glTF por tile mais um `tileset.json`), porque nenhuma das ferramentas abertas confirmadas faz a conversão.

## 4. Espaço em disco e tamanho

Os números de instalação são relatos de utilizadores, não valores oficiais; **a Epic não publica o tamanho da instalação do 5.6 a 5.8 na documentação consultada** (a página de requisitos do UE 5.8 não indica espaço em disco).

| Item | Valor | Fonte |
| --- | --- | --- |
| Motor UE 5.6 por omissão, no disco | Mais de 110 GB, segundo um utilizador; o lançador não mostrava o botão de opções no 5.6 | [Fórum Epic](https://forums.unrealengine.com/t/options-to-select-what-to-download-while-downloading-unreal-engine-5-6/2560580) |
| Motor UE5 só com a base, 2022 | Cerca de 32 GB, 35 a 40 GB com modelos e algumas plataformas; valor antigo | [Fórum Epic](https://forums.unrealengine.com/t/size-from-unreal-engine-5-post-launch-2022/550636) |
| Símbolos de depuração e do editor | Não encontrado | Lacuna |
| Derived Data Cache (DDC) | Não encontrado; vive na pasta do projeto e cresce com o conteúdo | Lacuna |
| Plugin Cesium for Unreal | Não encontrado | Lacuna |
| Projeto em branco empacotado (Windows, Shipping) | Cerca de 300 MB sem compressão; 340 MB com o modelo First Person; um blogue indica mais de 321 MB. Valores de versões não especificadas | [Fórum Epic](https://forums.unrealengine.com/t/community-tutorial-how-to-reduce-package-size-in-unreal-engine-5/1950640), [filfreire.com](https://filfreire.com/posts/unreal-file-size) |

Estimativa do responsável por esta avaliação, não medida: uma cena com terreno de 18 km, imagens de 10 m e 0,5 m, modelos e atmosfera ficaria entre 0,5 e 2 GB empacotada. Compare-se com o módulo Godot atual: 181 MB em disco, 87,8 MB comprimido.

Limites do ciclo de instalação atual (`desktop/studio/src/modules.rs`): `MAX_TOTAL_BYTES` 1 GiB, `MAX_FILES` 512, `MAX_FILE_BYTES` 512 MiB, margem de disco de 256 MiB. Uma compilação do UE5 empacotada tem normalmente milhares de ficheiros e um ficheiro `.pak` de centenas de MB. Seria preciso alargar estes limites, o que enfraquece uma verificação que hoje é estrita, ou distribuir o módulo de outra forma.

## 5. Este computador (medido em 2026-11-08, só leitura)

| Item | Valor medido |
| --- | --- |
| GPU | AMD Radeon RX 7700 XT |
| Memória de vídeo | 12 GB (`HardwareInformation.qwMemorySize` do registo; o `AdapterRAM` do WMI não foi usado) |
| Controlador | 32.0.31041.3013 |
| CPU | AMD Ryzen 7 7800X3D |
| RAM | 31,7 GB |
| Disco C | 835,9 GB usados, **94,6 GB livres** |
| Disco D | 671,8 GB usados, **259,8 GB livres** |
| Disco G | 840,6 GB usados, 89,9 GB livres |
| Comandos | `Get-PSDrive -PSProvider FileSystem`; `Get-ItemProperty` em `HKLM:\SYSTEM\ControlSet001\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0*`; `Get-CimInstance Win32_Processor` e `Win32_ComputerSystem` |

Leitura:

- Uma instalação de 110 GB não cabe no C com folga (94,6 GB livres). Só o D (259,8 GB) comporta o motor, o DDC e um projeto. Isto implica escolher a pasta de instalação no lançador.
- Requisitos oficiais do UE 5.8 ([documentação da Epic](https://dev.epicgames.com/documentation/en-us/unreal-engine/hardware-and-software-specifications-for-unreal-engine)): Windows 11 recomendado, 32 GB de RAM, 8 GB ou mais de memória de vídeo, DirectX 12. Para o Lumen: "AMD RX-6000 series or newer"; Nanite e sombras virtuais pedem "Latest graphics drivers" e SM6. A RX 7700 XT cumpre estes requisitos no papel.
- Vulkan e D3D12: o Vulkan do Godot falhou nesta máquina com VkResult -13 e o Studio já abre o módulo Godot em D3D12. O UE5 usa D3D12 como caminho principal em Windows (afirmação de memória, não confirmada nas fontes consultadas), pelo que o problema do Vulkan não deve afetar o UE5, mas **não foi testado**.
- Desempenho: **não foi encontrada nenhuma medição publicada de uma RX 7700 XT com Lumen e Nanite a 1440p numa cena comparável à nossa.** Os valores encontrados são médias de jogos (cerca de 98 a 99 FPS a 1440p em Ultra, [Nanoreview](https://nanoreview.net/en/gpu/radeon-rx-7700-xt), [KitGuru](https://www.kitguru.net/components/graphic-cards/dominic-moass/amd-rx-7700-xt-review/all/1/)) e uma estimativa por modelo para o Squad (51 FPS a 1440p em High) que não vale como medição. Qualquer número de desempenho do UE5 nesta máquina exigiria uma medição própria.

## 6. Arquitetura de integração

O princípio do repositório mantém-se: a Cinematic View só reproduz uma execução gravada (`trace.json` e registos de verificação, hoje `record.json` `vv-run.v1`) e nunca calcula nem altera resultados.

- Leitura do registo: processo separado, lançado pelo Studio com argumentos fixos (`--run <pasta>`, `--env <pasta>`), como o módulo Godot. O UE5 lê os ficheiros com C++ ou Blueprints (plugin JSON), só em leitura. Sem IPC nem rede.
- Fronteira de dados: o Studio resolve os dois caminhos; a interface web nunca envia caminhos. Isto reutiliza `launch_command` sem mudanças de fundo.
- Paridade de pose: o `tests/test_cinematic_pose.py` compara a pose desenhada com uma reimplementação independente em Python. Um módulo UE5 exigiria reimplementar `lowerIndex`, `sampleAt` e `slerp` em C++ e um modo sem janela que despeje a pose, mais a validação SHA-256 do pacote. É trabalho novo, com testes novos.
- Instalação, remoção e recuperação: o ciclo atual (zip, `.sha256`, manifesto, extração para `.staging-<pid>`, troca final, nova verificação em cada abertura) serve, mas os limites da secção 4 teriam de mudar ou o módulo teria de ser dividido.
- Assinatura e atualizações: o repositório não tem hoje assinatura de código documentada para o módulo (não verificado a fundo). Um executável UE5 não assinado dispara avisos do SmartScreen. Cada atualização do motor traz alterações grandes e o plugin Cesium só suporta as três versões mais recentes do UE.
- Escrita fora da pasta do módulo: o UE5 escreve registos, configuração e cache em `%LOCALAPPDATA%` por omissão, como já acontece com o Godot em `%APPDATA%`; a desinstalação teria de os tratar.
- Ativos necessários, qualquer que seja o motor: malha e materiais PBR do andar e dos motores; texturas de terreno; modelos de árvores (as plantas são hoje esferas deformadas com cartões); fachadas de edifícios (alturas OSM são estimativas); plataforma e infraestrutura de lançamento; pluma com partículas e fumo. No UE5 haveria acesso a SkyAtmosphere, nuvens volumétricas e a Nanite para malhas densas, que o Godot não tem, mas isso é motor, não arte.

## 7. Alternativas

1. **Melhorar o módulo Godot (recomendado, sem custo de licença).** O que o limita, segundo `docs/m17-cinematic.md`: resolução dos dados (imagem base de 10 m por texel, pormenor de 0,5 m; MDT de 30 m, pormenor de 4 m), modelos gerados por código, afinação de névoa, pluma e exposição, e a falta de nuvens volumétricas e céu atmosférico físico. As duas avaliações independentes disseram "modest improvement" e "a plume-and-props upgrade, not a fidelity upgrade". Trabalho concreto: modelos do andar e dos motores com materiais PBR, árvores modeladas, melhor pluma, afinação de luz e névoa, e capturas novas avaliadas por um revisor cego. Corrigir também as limitações já registadas: executável exportado em vez do binário do editor (os modelos de exportação têm 1,28 GB), medições com D3D12 (as atuais são com Vulkan).
2. **Manter o Three.js na vista técnica.** Não muda. É a vista de análise e continua a ser o padrão do produto.
3. **UE5 sem Cesium** (se o responsável quiser mesmo o UE5): custo de disco de 110 GB ou menos com opções, EULA a aceitar, trabalho de leitura do registo e de paridade em C++. Só compensa se, depois da arte e dos dados melhorados, o céu e as nuvens do Godot continuarem a ser o limite decisivo.
4. **UE5 com Cesium for Unreal:** só se o produto passar a precisar de terreno global em streaming com ligação à rede, o que contraria a regra offline do produto, ou de uma licença comercial do Cesium para uso offline de dados do ion (preço sob consulta).

Condições para reabrir a decisão do UE5: (a) a segunda ronda de arte e dados no Godot ter sido avaliada e continuar a ser descrita como limitada pelo motor; (b) o responsável ter lido o EULA e o Royalty Addendum atuais; (c) existir espaço em disco decidido (o D com 259,8 GB).

## 8. Riscos

| Risco | Efeito | Mitigação |
| --- | --- | --- |
| Termos do EULA lidos só em fontes secundárias | Aceitar condições de royalties, de registo de lançamento ou de posto que não correspondem ao texto atual | O responsável lê o EULA e o Royalty Addendum atuais antes de aceitar |
| Taxa de 1 850 USD por posto e por ano para uso fora de jogos | Aplica-se só acima de 1 milhão de USD de receita bruta anual, segundo as fontes de 2024; sem confirmação de 2026 | Confirmar a situação do responsável (indivíduo, estudante ou empresa) |
| Disco | Instalação por omissão superior a 110 GB, DDC e projetos; o C só tem 94,6 GB livres | Instalar no D; escolher componentes; limpar o DDC |
| Cesium World Terrain e Google fora de uso offline | Dados globais não podem ser usados offline | Usar só os pacotes locais, sem Cesium ion |
| Cesium ion Community não comercial, com 10 GB e 15 GB por mês | Uso comercial exige conta paga | Não usar o ion |
| Limites do ciclo de módulos (1 GiB, 512 ficheiros) | Compilação UE5 não cabe | Rever limites com testes, ou outro mecanismo de distribuição |
| Paridade de pose em C++ | Divergência com a vista técnica | Teste de paridade novo com o mesmo registo |
| Expectativa de fotorrealismo | Trocar de motor sem arte nem dados dá pouca melhoria | Fazer a arte e os dados primeiro |
| Desempenho desconhecido nesta máquina | Pode não atingir 1440p estável com Lumen | Medição própria com o procedimento do M17, só depois de aprovado |
| Atualizações do UE e do plugin | Compatibilidade com as três versões mais recentes do UE | Fixar versão e documentar |
| Comportamento do UE5 em D3D12 nesta máquina | Não testado | Verificar depois de aprovada a instalação |

## 9. O que não foi possível confirmar

- Texto atual do EULA e do Royalty Addendum da Epic (HTTP 403 nas páginas oficiais).
- Condições exatas de redistribuição de uma aplicação UE empacotada como módulo opcional.
- Se a taxa de 1 850 USD por posto se mantém em 2026 e a quem se aplica; as fontes de 2026 repetem o valor sem citação primária.
- Tamanho oficial da instalação do UE 5.6 a 5.8, símbolos de depuração, DDC e plugin Cesium.
- Tamanho de uma compilação empacotada com Cesium e terreno.
- Termos de serviço do Cesium ion, em particular o que o plano Community permite sobre cache.
- Se o Cesium for Unreal lê quantized-mesh ou GeoTIFF locais; licenças do `cesium-terrain-builder` original e do `py3dtiles`.
- Data de lançamento exata do Cesium for Unreal v2.31.0.
- Desempenho do Lumen e da Nanite na RX 7700 XT a 1440p numa cena como a nossa.
- Se o UE5 usa D3D12 por omissão em Windows (afirmação de memória).

## 10. Aprovação necessária

Recomendação: nada disto é necessário agora. Se o responsável decidir mesmo avançar com o UE5 (contra a recomendação da secção 1), tem de aprovar explicitamente cada ponto:

1. **Ler e aceitar o EULA da Epic e o Royalty Addendum atuais** (compromisso de licença em nome do responsável). Antes, confirmar o estatuto: indivíduo ou empresa; receita bruta anual abaixo ou acima de 1 milhão de USD; se o módulo gera receita. Custo previsto: 0 USD se os termos de 2024 se mantiverem e o responsável estiver abaixo do limiar; caso contrário, 1 850 USD por posto e por ano (a confirmar na fonte) ou royalties de 5 % acima de 1 milhão.
2. **Instalar o Epic Games Launcher** e **criar ou usar uma conta Epic** (acesso a dados pessoais e termos de conta da Epic). Aprovar também a recolha de dados de utilização do editor, ou a sua desativação.
3. **Instalar o UE 5.8 (ou a versão mais recente suportada pelo Cesium)** no **disco D**, com um orçamento de até **110 GB** para o motor (ou menos, sem outras plataformas e sem modelos, se o lançador o permitir) e mais **20 a 40 GB** reservados para DDC e projeto. Não instalar no C (94,6 GB livres).
4. **Cesium for Unreal (Apache 2.0, grátis):** sim ou não. Recomendação: **não**, usar os pacotes locais `vv-geo` com um terreno gerado a partir deles. Se sim, só com tilesets locais.
5. **Conta Cesium ion:** **não**. O plano Community é não comercial, não funciona offline com dados do ion, e o uso offline do Cesium World Terrain exige licença comercial (149 USD por mês, ou 524 USD por mês para equipa, ou preço sob consulta para offline e self-hosted).
6. **Dados do Google (Photorealistic 3D Tiles) e do Bing:** **não**. Cache e uso offline proibidos.
7. **Mudar o ciclo de módulos** (`MAX_TOTAL_BYTES`, `MAX_FILES`, `MAX_FILE_BYTES` em `desktop/studio/src/modules.rs`) ou aceitar outro mecanismo de distribuição, com testes de regressão.
8. **Orçamento de tempo** para: leitor de registo e paridade de pose em C++, modelos e materiais, medição de desempenho com D3D12 e nova avaliação visual independente.
9. **Distribuir o módulo UE5** como segundo artefacto com o seu ciclo de versões, assinatura de código e atualizações.

Custo total em dinheiro, se os termos de 2024 se mantiverem e o responsável estiver abaixo de 1 milhão de USD: 0 USD. Custo em disco: até cerca de 130 a 150 GB no D. Custo em tempo: várias iterações de arte, dados e testes.

Em alternativa, aprovar só o seguinte, sem instalar nada novo: **continuar no Godot 4.7.2 com trabalho de arte e dados** (modelos do andar, árvores, pluma, afinação, exportação do executável e medições com D3D12).

## Fontes e data de acesso

Todas acedidas em 2026-11-08.

- Engadget, 2024-03-12: https://www.engadget.com/epic-will-charge-non-game-developers-1850-per-seat-to-use-unreal-engine-162015997.html
- Cartoon Brew: https://www.cartoonbrew.com/tools/epic-games-unveils-new-per-seat-pricing-for-non-game-developers-using-unreal-engine-238987.html
- Epic, requisitos do UE 5.8: https://dev.epicgames.com/documentation/en-us/unreal-engine/hardware-and-software-specifications-for-unreal-engine
- Cesium for Unreal, repositório: https://github.com/CesiumGS/cesium-unreal
- Cesium for Unreal, v2.31.0: https://github.com/CesiumGS/cesium-unreal/releases/tag/v2.31.0
- Cesium for Unreal, FAQ: https://cesium.com/learn/unreal/unreal-faq/
- Cesium ion, preços: https://cesium.com/platform/cesium-ion/pricing/
- Cesium, fórum sobre uso offline: https://community.cesium.com/t/does-cesium-for-unreal-work-offline/17271
- `3d-tiles-tools`: https://github.com/CesiumGS/3d-tiles-tools
- `cesium-terrain-builder` (contentor `tum-gis`): https://github.com/tum-gis/cesium-terrain-builder-docker
- Google, políticas da Map Tiles API: https://developers.google.com/maps/documentation/tile/policies
- Epic, fórum, opções de transferência do UE 5.6: https://forums.unrealengine.com/t/options-to-select-what-to-download-while-downloading-unreal-engine-5-6/2560580
- Epic, fórum, tamanho do UE5 em 2022: https://forums.unrealengine.com/t/size-from-unreal-engine-5-post-launch-2022/550636
- Epic, fórum, tamanho de compilações: https://forums.unrealengine.com/t/community-tutorial-how-to-reduce-package-size-in-unreal-engine-5/1950640
- Nanoreview, RX 7700 XT: https://nanoreview.net/en/gpu/radeon-rx-7700-xt
- KitGuru, RX 7700 XT: https://www.kitguru.net/components/graphic-cards/dominic-moass/amd-rx-7700-xt-review/all/1/

# M17: Cinematic View, um renderizador opcional de alta fidelidade

Estado: protótipo no ramo `feat/m17-cinematic` (empilhado sobre `feat/m16-geospatial`, 9006e77). Nada foi enviado nem integrado. A aceitação visual cabe ao responsável; este documento descreve o que foi construído e medido.

## O que é

A Cinematic View é uma janela de reprodução separada, instalada como módulo opcional do Studio. Lê um registo de execução de uma aterragem (`record.json`, `vv-run.v1`) e um pacote de ambiente validado (`vv-geo-environment` v1 a v3) e desenha a descida com o motor Godot 4.7.2 (renderizador Forward+ sobre Vulkan). Não simula nada: a pose do andar no instante lógico t vem só dos estados gravados, interpolada exatamente como na vista técnica do Studio. Quem não instala o módulo continua com a vista técnica em Three.js, que não mudou.

## Arquitetura

```
Studio (Tauri, WebView2)                          Módulo (processo separado)
  ui/js/cinematic.js  -- botão e secção ---->       Godot 4.7.2 (binário oficial, MIT)
  src/modules.rs                                    desktop/cinematic/ (GDScript)
    cinematic_status            verifica tudo          record.gd   registo, interpolação
    cinematic_install_from_file zip + .sha256          pack.gd     pacote, SHA-256, terreno
    cinematic_uninstall                                terrain.gd  malhas base e de pormenor
    cinematic_launch(run_id, env_id) -- spawn -->      world.gd    edifícios, vegetação
                                                       stage.gd    andar e pluma ilustrativos
                                                       profiles.gd perfis gráficos
                                                       hud.gd      leitura, controlos, rótulos
```

- **Fronteira de dados.** O Studio resolve a pasta da execução (pelo identificador de 16 dígitos hexadecimais) e a pasta do pacote (pelo identificador de um pacote já validado pelo `vv-geo`). O módulo recebe só esses dois caminhos e `--profile auto`. A interface web nunca envia caminhos.
- **Validação no módulo.** Antes de usar qualquer ficheiro do pacote, o módulo compara o tamanho e o SHA-256 de cada ficheiro (`height.u16`, `image.jpg`, `detail-height.u16`, `detail-image.jpg`, `features.json`, `vegetation.bin`) com `environment.json` e recusa o pacote inteiro (código de saída 4) se algum diferir. Os nomes dos ficheiros são os fixos do esquema, nunca caminhos lidos do manifesto. Pacotes com `heading_deg` diferente de 0 são recusados, como no `vv-geo`.
- **Referencial.** O modelo usa x leste, y norte, z para cima, com a origem no centro da plataforma. O Godot usa y para cima, por isso o referencial desenhado é (x, y, z) = (leste, cima, −norte), uma rotação própria M. Um quaternião gravado (w, x, y, z) passa a `Quaternion(x, z, −y, w)` (M R Mᵀ). O eixo do andar, x_B, é o +X local do nó do andar.
- **Pose.** `record.gd` reimplementa `lowerIndex`, `sampleAt` (com a regra das lacunas) e o `slerp` do three.js r170 entre as amostras i e i + 1, com o mesmo f limitado a [0, 1]. A posição desenhada é a do plano de saída do bocal (`base_x`, `base_y`, `altitude`), como no Studio. Tudo em vírgula flutuante de 64 bits; só a transformação desenhada passa para os vetores de 32 bits do motor.
- **Terreno.** Os vértices ficam nos nós das grelhas e cada célula é dividida nos mesmos dois triângulos que `gridAt` amostra. A camada de pormenor usa as alturas misturadas na grelha base ao longo da margem (`terrainAt`), e a imagem de pormenor funde-se na imagem base com o mesmo peso. As células da base totalmente cobertas pelo pormenor não são geradas; nas da fronteira o sombreador descarta os fragmentos a 2 m do bordo, como em `geo.js`. Para lá do pacote o chão é uma continuação ilustrativa do bordo.
- **Câmaras.** As regras de `geo.js` foram portadas: Follow, From the ground (observador a 420 m e 10 m acima do solo ou da copa), At the pad, Wide, Overhead e Auto (escolhe o plano pela altura do andar sobre a plataforma). São funções do estado da reprodução; só a transição entre duas regras usa o relógio de parede (0,7 s, 1,1 s no Auto) e é desligada nas capturas e no banco de ensaio.

## Avaliação dos motores

Avaliação qualitativa com evidência onde existe. "Medido" quer dizer medido neste marco ou no M7/M16 nesta máquina; o resto vem de documentação pública e está assinalado.

| Critério | Unreal Engine 5 + Cesium for Unreal | Three.js avançado / WebGPU (vista atual) | Bevy 0.16 | Godot 4.7.2 (escolhido) |
| --- | --- | --- | --- | --- |
| Fidelidade visual | A mais alta das quatro (Lumen, Nanite, céu e nuvens volumétricas). Não medida. | Limitada pelo que se escreve à mão; sem GI nem névoa volumétrica prontas. Medida no M16 (capturas). | PBR, sombras em cascata, SSAO, névoa volumétrica, TAA. No M7, nesta máquina, os objetos 3D não apareceram em DX12. | PBR, sombras PSSM com PCSS, SSAO, SSIL, SSR, névoa volumétrica e perspetiva aérea, TAA/FSR2, brilho. Medido aqui (capturas). |
| Fidelidade geográfica | Nativa: georreferência WGS84, 3D Tiles, terreno do Cesium ion ou local. | Pacotes `vv-geo` validados (M16), já em produção. | A escrever. | Pacotes `vv-geo` com o mesmo terreno, a mesma amostragem e o mesmo referencial da vista técnica (medido: teste de pose). |
| Compatibilidade de hardware | Exige DX12 com SM6 ou Vulkan; a RX 7700 XT serve. Não testado. | Qualquer WebView2 com WebGL2; WebGPU não testado. | Falhou em Vulkan e OpenGL no M7 nesta máquina. | Vulkan funcionou à primeira. O comportamento sem Vulkan (recurso a D3D12 ou OpenGL) não foi testado. |
| Arranque | Compilação de sombreadores longa na primeira execução (não medido). | 0,44 a 0,53 s até o terreno estar na GPU (M16.2, medido). | 0,56 a 0,70 s até ao primeiro frame (M7, cena mínima). | Ver o quadro de desempenho. |
| Memória CPU/GPU | Tipicamente vários GB (não medido). | 1049 a 1068 MB privada, 455 a 462 MB GPU na vista geoespacial (M16.2, medido, processo do Studio inteiro). | Não medida com cenas reais. | Ver o quadro de desempenho. |
| Armazenamento | Motor de 50 a 70 GB num disco com 121 GB livres; aplicação empacotada de centenas de MB. | Nenhum adicional (já no instalador de 19,3 MB). | Executável de 59 MB, pasta de compilação de 2 GB (M7). | Módulo de 181 MB instalado, zip de 87,8 MB (medido). Modelos de exportação de 1,28 GB não descarregados (não são precisos). |
| Complexidade de instalação | Epic Games Launcher, conta, aceitação do EULA, plugin. | Nenhuma. | Compilação Rust de cerca de 11 minutos limpa (M7). | Um zip verificado pelo Studio; sem instalador nem registo do Windows. |
| Interoperabilidade | C++/Blueprints; lê JSON. Processo separado como aqui. | Mesmo processo, IPC já existente. | Rust: pode ligar diretamente às crates do laboratório. | Processo separado, só ficheiros de leitura; GDScript lê os formatos sem conversão. |
| Licença | EULA da Epic: 5 % de royalties acima de 1 milhão de USD por produto; taxa por posto para empresas não ligadas a jogos com mais de 1 milhão de USD de receita (fontes secundárias, ver `docs/evidence/m16/renderer-research.md`). Cesium for Unreal: Apache-2.0. | MIT. | MIT ou Apache-2.0. | MIT (texto no módulo). |
| Segurança | Recolha anónima de dados de utilização ativa por omissão (EULA antigo legível). Superfície grande. | CSP e `freezePrototype` atuais mantidos; CesiumJS falha com `freezePrototype` (M16). | Sem rede por omissão. | Sem rede: o projeto não usa nenhuma API de rede e só lê os dois diretórios (não foi feita captura de tráfego). Executa `reg.exe query` com argumentos fixos para ler a capacidade da memória de vídeo. |
| Funcionamento offline | Possível com mosaicos locais; o fluxo normal usa o Cesium ion. | Sim. | Sim. | Sim. |
| Manutenção | Motor enorme, atualizações grandes, C++. | Código próprio a manter, sem ajuda do motor. | API muda entre versões; 0.16 já não é a atual. | Versão estável recente; GDScript e sombreadores pequenos (cerca de 2 500 linhas). |
| Decisão | **Requer aprovação do responsável (EULA, disco).** Não instalado. | Mantém-se como vista técnica. | Não escolhido (falhas no M7). | **Protótipo.** |

## Decisão

O protótipo foi feito em Godot 4.7.2 porque é o único dos quatro que já mostrou nesta máquina um traço gravado com fidelidade verificada (M7), tem licença MIT, funciona sem rede e cabe num módulo de 181 MB. O UE5 com o Cesium for Unreal daria provavelmente mais fidelidade, mas exige a aceitação do EULA da Epic e 50 a 70 GB de disco, o que só o responsável pode aprovar. O Bevy falhou em dois dos três backends no M7. O Three.js continua a ser a vista técnica.

Recomendação: manter o módulo como protótipo e não o distribuir enquanto os defeitos visuais da avaliação independente não estiverem corrigidos e medidos de novo. A separação (processo próprio, instalação verificada, leitura só de ficheiros) e a paridade de pose estão prontas a ser reutilizadas por qualquer motor que venha a ser aprovado.

## O que é medido e o que é ilustrativo

| Na Cinematic View | Origem |
| --- | --- |
| Posição e atitude do andar em cada instante | Registo (`base_x`, `base_y`, `altitude`, `q_w` a `q_z`), interpolado só para desenhar |
| Comprimento da pluma | Regra da vista técnica sobre o acelerador aplicado gravado (6 + 22 × acelerador com o motor ligado) |
| t, amostra, altitude, velocidade, acelerador no ecrã | Valores da amostra no instante ou antes dele, como a leitura do Studio |
| Resultado e segurança no ecrã | Texto do registo copiado sem alterações (`outcome.label`, `outcome.explanation`, `safety.status`, `safety.explanation`) |
| Anéis R5 e S2 | Raios do registo, assentes no terreno desenhado |
| Terreno, imagem, contornos de edifícios, alturas com a sua origem, posições, alturas e raios das plantas | Pacote validado por SHA-256 |
| Geometria do andar (42 m, motores, aletas, pernas recolhidas), pluma, brilho e poeira no solo, cartões de folhagem e formas das copas, paredes e telhados, formas das estruturas, céu, névoa, acabamento da água, chão fora do pacote | **Ilustrativo.** Um rótulo permanente no ecrã diz isto |

O sol tem o azimute de 128° e a elevação de 27° da vista técnica; nenhuma data ou hora faz parte do modelo. A turbulência da pluma e a ondulação da água são funções do t do registo, não do relógio, por isso uma captura num dado t é sempre igual.

### Verificação da paridade

`tests/test_cinematic_pose.py` corre o projeto em modo sem janela com `--pose-dump` em todas as 235 amostras de uma aterragem gravada, nos 234 pontos médios e fora da execução, e compara com uma reimplementação independente em Python da interpolação da vista técnica:

- pose em 64 bits (posição, quaternião, eixo): diferença máxima admitida 1e-9;
- nó desenhado lido da cena (vetores de 32 bits): posição 2e-3 m numa descida de 3 km, eixo 2e-5;
- inclinação do eixo desenhado contra `tilt_deg` gravado, nas amostras: 2e-3°;
- um pacote com um byte alterado em `features.json` é recusado com o código 4;
- argumentos inválidos são recusados com o código 2.

O teste é ignorado se `VV_GODOT` não apontar para o executável de consola do Godot 4.7.2. O registo de ensaio, `tests/fixtures/cinematic/landing-run/record.json`, é o da aterragem com o altímetro enviesado («A sensor that lies», semente 5000), reduzido aos canais que a Cinematic View lê.

## Perfis gráficos

| Perfil | Sombras | Cascatas | PCSS | SSAO | SSIL | Névoa volumétrica | SSR | Escala | AA | MSAA | Vegetação | Perto / longe |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Performance | 2048 | 2 | não | não | não | não | não | 0,75 (FSR 1) | FXAA | 0 | 35 %, sem cartões nem sombras | 350 / 1500 m |
| Balanced | 4096 | 3 | sim | sim | não | não | não | 1,0 | TAA | 0 | 60 %, sem sombras | 500 / 2400 m |
| High | 4096 | 4 | sim | sim | sim | sim | sim | 1,0 | TAA | 2 | 100 % | 700 / 3200 m |
| Ultra | 8192 | 4 | sim | sim | sim | sim | sim | 1,0 | FSR 2 | 4 | 100 % | 1000 / 4500 m |
| Custom | parte do Balanced e aceita `--custom chave=valor,...` com limites | | | | | | | | | | | |

A densidade da vegetação escolhe um subconjunto determinista (hash da posição do registo); nenhum perfil muda onde as coisas estão.

**Escolha automática.** O Godot 4.7 não informa a capacidade da memória de vídeo: nesta máquina `RenderingDevice.get_device_total_memory()` devolveu 0 e `RENDERING_INFO_VIDEO_MEM_USED` só dá o que está em uso. A capacidade vem, por esta ordem, de `--vram-bytes`, do registo do Windows (`HardwareInformation.qwMemorySize` da classe de adaptadores de ecrã, lido com `reg.exe query` e argumentos fixos) ou fica desconhecida; nesse caso usa-se o Balanced com uma nota visível. Um adaptador integrado fica no Performance. Limiares: 2, 4, 8 e 11 GB. Nesta máquina o registo dá 12 868 124 672 bytes e a escolha automática é Ultra. Durante a execução, se a memória de vídeo em uso passar 85 % da capacidade, o perfil desce um nível e o ecrã diz porquê. O menu no ecrã permite escolher outro perfil a qualquer momento.

## Desempenho

Medido fora da simulação com `scripts/cinematic/bench.py`, um perfil de cada vez e nunca em paralelo com outro trabalho pesado (cada execução passou pelo bloqueio global da máquina). Máquina: AMD Ryzen 7 7800X3D (8 núcleos, 16 fios), 32 GB de RAM, AMD Radeon RX 7700 XT com 12 GB (12 868 124 672 bytes segundo o registo da classe de adaptadores de ecrã; o `AdapterRAM` do WMI fica limitado a 4 GB e foi ignorado), Windows 11 Pro, controlador 32.0.31041.3013, Godot 4.7.2-stable com Vulkan 1.4.349.

Comando (um por perfil):

```sh
python scripts/cinematic/bench.py --godot <Godot_v4.7.2-stable_win64_console.exe> --run tests/fixtures/cinematic/landing-run --env desktop/environments/cape-canaveral --out docs/evidence/m17/cinematic/bench --seconds 12
```

Cada execução abre uma janela de 1440x900, sem sincronização vertical, faz 120 frames de aquecimento e reproduz o registo do primeiro ao último instante em 12 s de relógio com a câmara Auto. Os tempos entre frames são de relógio de parede; a memória de vídeo é `RENDERING_INFO_VIDEO_MEM_USED` no fim; a memória do processo é o pico amostrado de 100 em 100 ms pelo `psutil` no processo do Godot. O arranque é o tempo desde o lançamento do processo até à linha `FIRST_FRAME` (primeiro frame da cena construída, incluindo a validação do pacote e a construção das malhas). Uma execução por perfil.

| Perfil | Arranque até ao primeiro frame | Frame p50 | Frame p99 | Frame máx. | Memória de vídeo em uso (texturas / buffers) | Working set (pico) | Bytes privados (pico) | Vegetação desenhada |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Performance | 4,77 s | 1,07 ms | 1,60 ms | 13,1 ms | 474 MB (206 / 49) | 966 MB | 1427 MB | 37 188 |
| Balanced | 5,89 s | 1,55 ms | 2,71 ms | 11,3 ms | 573 MB (279 / 74) | 1417 MB | 1862 MB | 63 401 |
| High | 6,09 s | 2,60 ms | 5,15 ms | 10,9 ms | 717 MB (405 / 89) | 1376 MB | 2021 MB | 105 727 |
| Ultra | 5,36 s | 3,30 ms | 7,55 ms | 57,7 ms | 980 MB (666 / 90) | 1421 MB | 2506 MB | 105 727 |

No quadro, as memórias estão em unidades de 2^20 bytes (como nas medições do M16); os tamanhos de ficheiros abaixo estão em MB decimais.

Instalação: zip de 87,8 MB (87 760 542 bytes), 181,3 MB em disco (181 250 844 bytes, 20 ficheiros), dos quais 180,9 MB são o binário do Godot.

Os resultados ficam em `docs/evidence/m17/cinematic/bench/` (um JSON por perfil, com as definições aplicadas, o adaptador, a origem da capacidade da memória de vídeo e as contagens da cena).

Limites desta medição: uma só máquina e uma só execução por perfil; o máximo do Ultra (57,7 ms) é um frame isolado, provavelmente compilação de um pipeline durante a reprodução, e não foi investigado; a sincronização vertical estava desligada, por isso os tempos não se comparam diretamente com os da vista técnica, que foram medidos com o limite de 165 Hz do ecrã. Para a vista técnica citam-se as medições do M16.2 (`docs/evidence/m16/installed-0.16.2/perf-m16-installed-*.json`, Studio 0.16.2 instalado, mesmo pacote, mesma janela): terreno na GPU 0,44 a 0,53 s depois de mudar de vista, p99 6,2 ms limitado pelo ecrã, 1049 a 1068 MB de memória privada e 455 a 462 MB de GPU dedicada para todo o Studio com a vista geoespacial. Não foram medidas de novo. As duas medições de memória não são iguais: a da vista técnica soma os processos do Studio e do WebView2; a da Cinematic View é só o processo do Godot.

## Comparação visual

`docs/evidence/m17/cinematic/` tem três pares de capturas de 1440x900 da mesma execução (missão «A sensor that lies», execução do controlador robusto, semente 5000) em Cabo Canaveral, no mesmo instante e com a mesma regra de câmara:

| Fase | t | Câmara | Vista técnica (Studio 0.16.2 instalado) | Cinematic View (perfil Ultra) |
| --- | --- | --- | --- | --- |
| Descida, cerca de 1500 m | 7,31 s | Follow | `technical-cape-canaveral-follow-7.31-1440x900.jpg` | `cinematic-cape-canaveral-follow-7.31-1440x900.png` |
| Queima, cerca de 300 m | 16,29 s | Follow | `technical-cape-canaveral-follow-16.29-1440x900.jpg` | `cinematic-cape-canaveral-follow-16.29-1440x900.png` |
| Contacto | 23,336 s | At the pad | `technical-cape-canaveral-closeup-23.336-1440x900.jpg` | `cinematic-cape-canaveral-closeup-23.336-1440x900.png` |

As capturas técnicas foram tiradas com `desktop/studio/tests/m17_tech_shots.py` (biblioteca e configuração temporárias; o registo da execução mostrada foi guardado e comparado com o de ensaio: mesma base de tempo, mesmo resultado, canais iguais com diferenças só no último bit da formatação decimal de `speed`, `tilt_deg` e de um valor de `altitude`). As da Cinematic View usam o registo de ensaio, `--shot` e 90 frames de espera para o TAA e as sombras assentarem. Os metadados estão em `technical-shots.json` e `cinematic-shots.json`. São imagens, não medições.

### Primeira avaliação independente (primeira iteração)

As capturas da primeira iteração estão em `docs/evidence/m17/cinematic/before-iteration/`. Um agente revisor só de leitura recebeu apenas as seis imagens e a pergunta (é uma melhoria substancial e visível, e onde é fraca), sem acesso ao código nem a este texto. Veredicto: **«modest improvement»**. Resumo do que disse:

- Ganhos: a pluma (núcleo, brilho e luz no solo, contra um triângulo amarelo rígido), o modelo do andar (aletas, juntas, pernas) e, junto à plataforma, a variedade de cor das copas.
- Iguais ou piores: o céu lê-se cinzento-claro e plano, com uma aresta reta onde acaba o chão para lá do pacote; uma mancha escura diagonal no mar a 7,31 s; árvores de tamanho uniforme e edifícios cinzentos sem textura que parecem uma camada de jogo e desfocam a fotografia a 16,29 s; a plataforma quase branca e as marcas de terra perdidas no contacto; a pluma não se vê no contacto apesar de o acelerador estar a 58 %; não há sombra de contacto sob o andar.
- A vista técnica dá uma pista de profundidade que esta não dá: a linha do percurso no solo. Sem ela, a 300 m o andar pode parecer pousado.
- O painel inferior e o bloco do canto tapam a ponta da pluma e a linha de créditos fica cortada na margem.
- Rotulagem honesta nos dois lados; os valores do ecrã coincidem com os da vista técnica nos três instantes.

Conclusão do revisor: «a plume-and-props upgrade, not a fidelity upgrade».

### Segunda iteração: o que mudou

Cada ponto da primeira avaliação foi tratado na sua origem:

| Problema | Causa encontrada | Correção |
| --- | --- | --- |
| Céu plano e faixa no horizonte | Céu procedimental de duas cores; a névoa tinha cor própria e, ao olhar para chão distante, a perspetiva aérea amostrava a parte «chão» do céu | Sombreador de céu próprio (gradiente, halo e disco do sol, nuvens estáticas); abaixo do horizonte o céu é a névoa do horizonte; `fog_aerial_perspective` 1, densidade 4,5e-5; chão fora do pacote até 200 km e câmara até 250 km |
| Aresta do pacote e faixas | O chão fora do pacote tinha outro material e outra cor | Usa o material do terreno; nos últimos 2,5 km da grelha base a imagem funde-se numa cor média de terra e mar calculada da própria imagem, e fora do pacote só essa cor neutra |
| «Bola» brilhante abaixo do andar | A coordenada axial da pluma estava invertida: a ponta do cone era a parte mais brilhante | Coordenada corrigida (verificada nas imagens) e ponta a desvanecer |
| Mar escurecido | Albedo da água multiplicado por 0,35 | Cor da imagem a 70 %, rugosidade 0,05, reflexo do céu e SSR |
| Árvores iguais | Uma forma por tipo e uma cor | Cinco arquétipos (copa redonda, cónica e em guarda-sol; dois arbustos) escolhidos pela altura lidar e por hash; variação determinista de matiz e luminância |
| Edifícios sem textura | Cor lisa | Sombreador com bandas de pisos, juntas, vidros e rodapé nas paredes; telhado com a cor da imagem e variação |
| Plataforma branca | Albedo da fotografia até 0,8 | Luminância limitada a cerca de 0,38, exposição 0,92, sol 1,7, limiar do brilho 3 |
| Sem pluma no contacto | O bocal está a 0,1 m: a pluma axial ficava dentro do terreno | Pluma axial cortada no solo, brilho do bocal sempre que o motor está ligado e brilho rasante no chão quando a pluma o alcança |
| HUD sobre a pluma, créditos cortados | Barra inferior larga | Leitura em cima à esquerda, veredictos em cima à direita, rótulo ilustrativo em baixo à esquerda, uma linha de crédito em baixo à direita (ODbL visível, C abre todas as atribuições), barra de reprodução oculta com H ou `--controls hidden` (usado nas capturas) |
| Sem pista de profundidade | Faltava o percurso no solo | Percurso do plano do bocal assente no terreno e linha vertical até ao solo, dados do registo |

Foi acrescentada uma câmara só da Cinematic View, «Low» (`lowwide`): observador a 12 m do solo, a pelo menos 900 m da plataforma, do lado do sol.

As novas capturas estão em `docs/evidence/m17/cinematic/cinematic-*.png` (mesmos três instantes e câmaras, perfil Ultra) e `cinematic-cape-canaveral-lowwide-16.29-1440x900.png`. As técnicas não mudaram.

O teste de paridade da pose voltou a passar (3 testes). Banco de ensaio repetido para Balanced e Ultra com o mesmo comando (`docs/evidence/m17/cinematic/bench-iteration-2/`):

| Perfil | Arranque | Frame p50 | Frame p99 | Frame máx. | Memória de vídeo | Working set | Bytes privados |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Balanced (1.ª → 2.ª) | 5,89 → 4,22 s | 1,55 → 2,50 ms | 2,71 → 3,82 ms | 11,3 → 14,5 ms | 573 → 551 MB | 1417 → 1376 MB | 1862 → 1791 MB |
| Ultra (1.ª → 2.ª) | 5,36 → 4,75 s | 3,30 → 4,44 ms | 7,55 → 8,97 ms | 57,7 → 14,4 ms | 980 → 958 MB | 1421 → 1302 MB | 2506 → 2297 MB |

O custo por frame subiu (sombreadores de céu, edifícios e terreno mais pesados, mais instâncias de vegetação); continua abaixo de 9 ms no p99 em Ultra. O arranque mais curto reflete a cache de sombreadores já preenchida e a carga da máquina, não uma otimização.

### Segunda avaliação independente

Um novo agente revisor só de leitura, sem contexto, recebeu as sete imagens. Veredicto: **«modest improvement»**, de novo. O que disse:

- Melhor: o céu (a vista técnica tem uma faixa escura acima do horizonte), o par de 16,29 s (cartões de árvores, edifícios, gradiente da água junto à costa, profundidade ao nível do solo) e a linha de árvores no contacto. «Nicer» em 5 s, «not realistic» em 10 s; «a mid-2000s game, not cinema».
- Fraco: a névoa a 1500 m tira contraste à zona da plataforma; a pluma em altitude lê-se como um disco branco saturado maior do que o andar, e na vista baixa o brilho é o assunto e o andar um ponto; a água a 7,31 s parece cinzenta e mate; copas como manchas com arestas de cartões visíveis; um edifício curvo como extrusão branca; a plataforma ainda um disco cinzento; não viu sombras projetadas no contacto; o modelo do andar é o mesmo da primeira iteração.
- Honestidade: o painel do resultado mostra «Landed» desde o início, quando a vista técnica o esconde até ao fim; a última linha do rótulo ilustrativo toca a margem; os anéis R5 e S2 não têm legenda.
- O que o limita, segundo o revisor: céu, sombras e luz são configuração do motor; o andar, as árvores e os edifícios são arte e precisariam de modelos novos; a nitidez do terreno é a resolução das imagens de origem.

Duas afirmações do revisor não correspondem à configuração: as sombras direcionais estão ligadas (o andar projeta uma sombra longa e estreita para a esquerda no contacto, pouco visível com o sol a 27° e este enquadramento) e o céu já não é de um só tom. As restantes observações ficam como estão.

### O que limita a fidelidade

A segunda iteração corrigiu os defeitos de configuração e de código. O que falta para uma melhoria substancial não é, na maior parte, do motor:

- **Resolução dos dados.** A imagem base tem 10 m por texel e a de pormenor 0,5 m; o modelo digital de superfície tem 30 m e o de pormenor 4 m. A meia altitude o chão é uma fotografia desfocada com a luz do voo, e nenhum sombreador acrescenta pormenor que não está nos dados.
- **Modelos.** O andar, as árvores e os edifícios são geometria gerada por código, sem modelos texturados nem fotogrametria. Um andar com materiais PBR feitos à mão, árvores com folhagem modelada e edifícios com fachadas reais exigem trabalho de arte que este marco não teve.
- **Direção de arte e afinação.** Névoa, brilho da pluma e exposição foram afinados em poucas passagens; a pluma em altitude ainda satura.
- **Motor.** O Godot 4.7 tem o que se usou (sombras PSSM com PCSS, SSAO, SSIL, SSR, névoa volumétrica, TAA/FSR2). Não tem nuvens volumétricas, céu atmosférico físico de qualidade de produção nem geometria virtualizada; o UE5 tem, mas exige a aprovação do EULA e do disco.

Conclusão: com os dados e a geometria atuais, a Cinematic View é uma melhoria modesta e não a melhoria substancial pedida.

## Instalação, verificação e remoção

1. `python scripts/cinematic/package_module.py --godot-dir <pasta com o Godot 4.7.2> --out <pasta>` produz `vv-cinematic-0.1.0.zip` e `vv-cinematic-0.1.0.zip.sha256`. O zip tem o manifesto `vv-cinematic-module.json` (esquema `vv-cinematic-module.v1`: versão do módulo, interface do Studio `vv-cinematic-launch.v1`, versão do Godot com o SHA-512 do zip oficial, ponto de entrada, tamanho em disco, memória de vídeo mínima, licenças e a lista de ficheiros com SHA-256), os dois executáveis oficiais do Godot, o projeto e as licenças (texto MIT do Godot e componentes de terceiros, extraídos do próprio binário, e a licença MIT do módulo).
   O Godot vem do zip oficial da release no GitHub, `Godot_v4.7.2-stable_win64.exe.zip` (86 013 866 bytes), descarregado para uma pasta vazia; o SHA-512 `83decd58fdf67b9d657958a1ae6bf1929c20785315a81effe245874cdc57acb709bf868e00778a96984338c1b29dafdb453c6847747694621c6ecf5da2259993` coincide com o de `SHA512-SUMS.txt` da mesma release. Nenhum binário está no git.
2. Em Definições, «Install from a module zip…» abre a escolha do ficheiro (em Rust). O Studio exige o `.sha256` ao lado e confere-o, lê o manifesto (esquema, interface, versão x.y.z, caminhos relativos simples, sem duplicados, tamanho total igual ao declarado, executável e projeto na lista), recusa qualquer entrada do zip que o manifesto não liste ou que seja uma ligação, verifica o espaço livre (tamanho do módulo mais 256 MB), extrai para `.staging-<pid>` calculando o SHA-256 de cada ficheiro e só depois renomeia para `<dados locais da aplicação>/modules/cinematic/<versão>/`. Qualquer falha apaga a pasta temporária e deixa a instalação anterior como estava até à troca final.
3. `cinematic_status` volta a calcular o SHA-256 de todos os ficheiros instalados. Um ficheiro alterado marca o módulo como não verificado e desativa o botão, com o motivo.
4. `cinematic_launch(run_id, env_id)` verifica de novo todo o módulo e só então inicia o executável do módulo com argumentos fixos (`--path <projeto> -- --run <pasta da execução> --env <pasta do pacote> --profile auto`), sem shell. Só uma janela de cada vez.
5. «Uninstall» termina a janela aberta e apaga `modules/cinematic`.

A política de segurança de conteúdo do Studio e as capacidades do Tauri não mudaram: os quatro comandos são comandos da aplicação. O espaço livre é lido com `GetDiskFreeSpaceExW` por uma declaração direta da `kernel32`, o único bloco `unsafe` do Studio, porque ler o espaço livre do volume é uma chamada nativa em qualquer crate. A extração usa a crate `zip` 2.6.1 que o lock já tinha (exportação de evidência), com as mesmas funcionalidades.

## Verificação executada

- Em `desktop/`: `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test` (todos passam; o `vv-studio` tem 4 testes novos em `modules.rs`) e `cargo build --release`.
- Na raiz: `cargo build --release` e `python -m unittest discover -s tests -p "test_*.py"` (377 testes, 42 ignorados; os 3 da Cinematic View correram com `VV_GODOT` definido).
- Não foram corridas de novo a campanha `run_campaign.py` nem a verificação completa da raiz (`cargo fmt`, `clippy`, `test`): este marco não altera o pacote da raiz nem os seus hashes canónicos.

## Aceitação no Studio instalado (0.17.0)

Em 2026-11-07 o módulo foi instalado no Studio 0.17.0 pelo próprio código de instalação do Studio (`install_zip`, teste opcional com `VV_CINEMATIC_INSTALL_TO`) e conduzido por `desktop/studio/tests/m17_cinematic_journey.py`: estado verificado, abertura a partir do leitor, registo do módulo com o pacote verificado e o primeiro fotograma, desinstalação e regresso ao botão desativado com a razão; 8 de 8 verificações. O diálogo nativo de ficheiros não foi conduzido por script: o Windows não entrega teclas a uma janela em segundo plano e a caixa do nome do ficheiro não aparece na árvore de UI Automation.

Nessa sessão o controlador Vulkan desta máquina falhou em todos os fotogramas ("Couldn't get Vulkan surface capabilities", VkResult -13) e a janela ficou preta, tanto aberta pelo Studio como à mão. Com Direct3D 12 a mesma cena desenha-se sem erros, pelo que o Studio passou a abrir o módulo com `--rendering-driver d3d12` no Windows. As medições de desempenho acima foram feitas com Vulkan em 2026-11-05 e não foram repetidas com Direct3D 12.

## Limitações conhecidas

- **O módulo corre o binário do editor do Godot** (181 MB) sobre a pasta do projeto, em vez de um executável exportado com um `.pck`. Os modelos de exportação têm 1,28 GB (tamanho do servidor, `Content-Length` do ficheiro oficial) e não foram descarregados. Um executável exportado seria mais pequeno e não teria o editor dentro.
- **O Godot escreve fora da pasta do módulo**: a cache de sombreadores e os dados do utilizador vão para `%APPDATA%\VV Lab Cinematic` (`use_custom_user_dir`). A desinstalação não apaga essa pasta.
- **Integração no Studio só testada por testes Rust.** Os quatro comandos têm testes (instalação, recusa de zips adulterados, travessia de caminhos, ficheiro não listado, verificação depois de instalado, desinstalação) e o zip real instala-se e verifica-se num teste opcional (`VV_CINEMATIC_ZIP`). O botão do leitor e a secção das Definições não foram exercitados num Studio compilado e instalado.
- **Escolha automática do perfil só vista nesta máquina.** A leitura do registo e a descida de perfil por memória de vídeo não foram exercitadas numa placa com pouca memória; o recurso do Godot a D3D12 ou OpenGL quando falta o Vulkan também não.
- **Menos camadas de análise do que a vista técnica.** Não há trajetória desenhada, estimativa de navegação, marcadores de eventos nem execuções de referência; o anel da plataforma não muda de cor no fim de uma execução falhada (o veredicto do registo está no ecrã). É uma vista de apresentação; a análise continua na vista técnica.
- **Sem órbita livre da câmara.** As câmaras são as regras portadas; não se pode arrastar.
- **O tempo até ao primeiro frame inclui a compilação dos sombreadores** na primeira execução; as seguintes usam a cache.
- **Defeitos que a segunda avaliação ainda aponta e que não foram afinados**: névoa a tirar contraste a 1500 m; pluma saturada em altitude e dominante na vista baixa; água mate a meia altitude; copas com arestas de cartões; plataforma cinzenta e plana.
- **Corrigido depois da segunda avaliação** (sem novas capturas de evidência): os veredictos do registo ficam escondidos até a reprodução chegar ao fim da execução, como na vista técnica, e a tecla V mostra-os antes; o rótulo ilustrativo subiu para dentro da margem e passou a ter a legenda dos anéis (R5 verde, S2 vermelho) e da linha do percurso no solo. As imagens em `docs/evidence/m17/cinematic/` ainda mostram o veredicto desde o início.
- **O zip foi gerado de novo no fim** com o código final: `vv-cinematic-0.1.0.zip`, 87 766 298 bytes, SHA-256 `20ee8cba9de29dc9cc5f3d4da2474fc38ba5d333920e6e44bee26161ef8ffa7d`. As medições de instalação acima são da primeira iteração.
- **Fidelidade ainda limitada pelos dados**: a fotografia tem a luz e as sombras do voo e é iluminada de novo; as alturas da maior parte dos edifícios são estimativas; as plantas são esferas deformadas com cartões; não há iluminação global (SDFGI ou VoxelGI) porque a escala de 18 km não lhe convém.

## O que requer aprovação do responsável

- Instalar o Unreal Engine 5 e o Cesium for Unreal: aceitação do EULA da Epic (compromisso de licença) e 50 a 70 GB de disco.
- Distribuir o módulo: o binário do Godot é MIT, mas o módulo passa a ser um segundo artefacto com o seu próprio ciclo de versões.
- A aceitação visual da cena.

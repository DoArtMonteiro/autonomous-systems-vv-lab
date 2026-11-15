# M15-M18: aceitação final dos requisitos face à evidência

Data: 2026-11-15. Base: as 150 linhas de requisitos da matriz de auditoria (estado de 2026-11-11, antes da recuperação), reavaliadas face a `main` em `66b30ca`, à evidência da Studio 0.18.1 instalada no ramo `release/0.18.1` (PR #35) e ao registo da recuperação. Nenhuma linha é promovida sem evidência executada, exceto as três linhas de integração (M16.2-R17, M17-R30, M18-R18), que passam a MET pela autorização do mandato de recuperação, descrita no registo de integração. As 11 linhas que estavam UNVERIFIED foram resolvidas para MET, PARTIAL ou BLOCKED-EXTERNAL.

Abreviaturas de evidência:

- **CI-main**: o fluxo `verification` do GitHub Actions foi concluído com êxito em cada commit de integração em `main` (ae7043d, 52bb135, f5db000, 57d1da1, 4301c1f, 66b30ca). Inclui o portão de reprodução M13 e o trabalho `vv-ascent`. O passo das jornadas da aplicação instalada no CI é informativo (`continue-on-error`, o executor alojado não controla a WebView2) e não conta como portão; as jornadas valem pela execução na máquina local (J18).
- **J18**: `docs/evidence/m18/installed-0.18.1/` (ramo `release/0.18.1`): jornadas no executável instalado: M15 48/48, M16 78/78, M17 Lab 34/34, M17 Cinematic 11/11, M18 72/72, verificação por amostragem do utilizador 44/44 e jornadas de UX (ux_journeys.py) 81/81 e jornadas de UX2 90/90, capturas de revisão 41/41 e ui_smoke 80/80; `perf/`; `verification.txt` (lista do AGENTS.md na raiz e em `desktop/`; 442 testes Python OK, com 6 ignorados, com `VV_GODOT`; `cargo test` do desktop com 37 suítes e 306 testes; campanha concluída com 87 casos). O instalador tem SHA-256 `0e37bbcf7228b7170ab392966b0cdc79b2e7446280e801cc9912c16bb0ebd0e1` (42 454 061 bytes). A pasta de reversão tem 22 ficheiros verificados contra a lista (19 instaladores, de 0.17.0 a 0.18.1, em SHA256SUMS.txt) (os builds 0.18.1 anteriores foram mantidos com sufixos). O hash da biblioteca e as 11 execuções não mudaram.
- Os identificadores de commit estão em `main`, salvo indicação em contrário. As 14 linhas contadas na coluna "UX" foram tocadas pela revisão de UX instalada. Seis passagens de correção foram feitas e verificadas (a última verificação independente não encontrou nenhum bloqueio de honestidade), mas essas linhas ficam PARTIAL: o objetivo de experiência não foi aceite sem graves, não houve teste com pessoas e as pendências estão listadas em "Restantes não cumpridos e motivos".

## Resumo das contagens

Antes = matriz de 2026-11-11 (inclui UNVERIFIED). Depois = este documento. UX = linhas PARTIAL tocadas pela revisão de UX instalada: M15-R03, M15-R13, M16-R14, M16.1-R05, M17-R01, M17-R13, M17-R27, M17-R28, M18-R11, M18-R13, M18-R22, M18-R23, M18-R24 e M18-R30.

| Milestone | Antes (MET / PARTIAL / NOT MET / BLOCKED / UNVERIFIED) | Depois (MET / PARTIAL / NOT MET / BLOCKED) | UX | Total |
|---|---|---|---|---|
| M15 | 16 / 7 / 1 / 1 / 4 | 18 / 9 / 0 / 2 | 2 | 29 |
| M16 | 27 / 16 / 2 / 1 / 2 | 29 / 16 / 2 / 1 | 2 | 48 |
| M17 | 10 / 19 / 6 / 1 / 2 | 19 / 16 / 3 / 0 | 4 | 38 |
| M18 | 11 / 11 / 9 / 1 / 3 | 17 / 13 / 5 / 0 | 6 | 35 |
| **Todos** | **64 / 53 / 18 / 4 / 11** | **83 / 54 / 10 / 3** | **14** | **150** |

## M15: experiência de missão, biblioteca de simulações e produtização

| id | requisito | estado final | evidência |
|---|---|---|---|
| M15-R01 | Resolver primeiro a pilha #21-#23; manter a reversão | MET | a23db64 é antecessor de `main`; #24 integrado em ae7043d; 19 instaladores de reversão (0.17.0 a 0.18.1, incluindo as construções intermédias da 0.18.1) verificados por hash (README J18, SHA256SUMS.txt) |
| M15-R02 | Preservar M9-M14; intervalos de sementes protegidos; evidência congelada inalterada | MET | scripts/compare_investigation.py (normaliza apenas source_sha256) repõe o portão de reprodução M13; CI-main verde, incluindo o passo 'Reproduce the M13 investigations'; docs/evidence/m13 e m14 inalterados; testes de intervalos de sementes (host.rs, exec/src/seeds.rs ead0a0a) |
| M15-R03 | Resultados identificados como exploratórios | PARTIAL | distintivos Demonstration/Exploratory/Reference case (#24); revisão de UX: a página inicial precisa de uma declaração explícita de exploração e de redação 'validated offline' |
| M15-R04 | Principiante abre, escolhe, lança, vê o resultado e o motivo | MET | m15_journeys 48/48 na 0.18.1 instalada (J18); 0,27 s do clique até à aterragem (perf J18); conclusões M15-1..11 da revisão de #24 corrigidas antes da integração |
| M15-R05 | Níveis Explorador/Analista/Investigador com divulgação progressiva | PARTIAL | apenas etiquetas de nível e agrupamento na navegação; a página inicial já não explica os níveis (página inicial M18) |
| M15-R06 | Integração por interação, sem tutorial | PARTIAL | sem sobreposição de tutorial; a compreensão nunca foi medida com pessoas; revisão da persona de agente (UX) GOOD WITH GAPS |
| M15-R07 | Biblioteca de simulações com campos e Run | MET | 13 missões; filtro da biblioteca na jornada m15 48/48 (J18) |
| M15-R08 | Missões curadas ancoradas em capacidades reais | MET | demos.rs verifica os números citados; suíte do desktop 37 suítes/306 testes, 0 falhas (J18 verification.txt); formulação sobre GNSS tardio limitada à evidência M13 (6987333, 8b8b090) |
| M15-R09 | Roteiro justificado de expansão de domínios | MET | docs/m15-mission-experience.md (entregável); nenhum domínio sem suporte foi construído |
| M15-R10 | Janela 3D em destaque, telemetria mínima, linha temporal, reprodução | MET | jornadas m15 48/48 (J18); correções de foco e aria-live na revelação do player (2387cbf) |
| M15-R11 | Visuais a partir dos resultados do simulador; etiquetas verdadeiro, estimado, observado, derivado | MET | legenda T/E/O/D no player; interpolação divulgada; segurança não avaliada mostrada de forma neutra (cc05839) |
| M15-R12 | Reprodução: velocidade, deslocação, predefinições, marcadores, sobreposições, gráficos sincronizados | MET | jornadas m15 e m16 (J18); marcadores desenhados apenas quando atingidos (4195b6b) |
| M15-R13 | Comparação com o momento de divergência, visual e numérica | PARTIAL | etiquetas indicam o parâmetro alterado (78f45c3; verificação por amostragem 44/44 em J18); revisão de UX: 'safe' verde isolado ao lado de um contacto a 60 m/s; o par de aterragem parece idêntico |
| M15-R14 | Medir o desempenho de renderização; alternativa WebGL; manter o determinismo | PARTIAL | J18 perf/perf-m16.json (p99 18,6 ms a cerca de 55 Hz, nenhum fotograma acima de 33 ms; 8,5 ms a 125 Hz na medição de 2026-11-12, não comparável); linhas de base docs/evidence/m15; a alternativa é uma mensagem de texto, não testada com WebGL desligado |
| M15-R15 | Identidade original, coerente entre ecrãs | PARTIAL | coerente nos ecrãs vistos; o contraste do texto cinzento pequeno e a consistência das cores dos chips foram assinalados pela revisão de UX; Settings e Records não foram reavaliados |
| M15-R16 | Inspecionar capturas reais em tamanhos realistas | MET | docs/images/m15-studio; as jornadas M18 medem o layout a 1024x640, 1440x900 e 1920x1080 (J18 m18-journeys.txt) |
| M15-R17 | 'Challenge this claim' apenas quando aceite; fluxo de Simulação para Verificação | PARTIAL | cartão de contestação e jornada m15; a cadeia de Observação para Verificação não foi percorrida de ponta a ponta; formulação corrigida para 'counterexample outside the registered conditions' (8b8b090) |
| M15-R18 | Nenhum veredicto favorável para um pacote que falha a recomputação | MET | ui-smoke.txt 80/80 na 0.18.1 instalada inclui "a tampered package fails recomputation in the app, naming the checks" (J18) |
| M15-R19 | Via B: protocolo de início do G3 defensável | BLOCKED-EXTERNAL | candidato em docs/m15-g3-onset-protocol.md; requer aprovação do proprietário e revisão humana; sementes 44000-44999 não gastas |
| M15-R20 | Não consumir 44000-44999 / 50000-59999 | MET | proteções de sementes em quatro domínios; teste de reserva idêntica em exec/src/seeds.rs (ead0a0a); CI-main |
| M15-R21 | Mostra curada A a E | MET | cinco missões mapeadas; demos.rs verifica os seus números |
| M15-R22 | Aceitação do explorador por tarefas realistas de utilização | BLOCKED-EXTERNAL | estudo com pessoas reais não é possível neste ambiente; apenas jornadas com guião e revisão por persona de agente (fable-ux-critic, GOOD WITH GAPS) |
| M15-R23 | Aceitação do analista: configurar, executar, comparar, exportar | MET | jornadas m15 e m17 com 48/48 e 34/34 (J18) |
| M15-R24 | Aceitação do investigador, incluindo retirada em caso de adulteração | MET | testes M13 de ui_smoke na 0.18.1 instalada: ui-smoke.txt 80/80, incluindo a retirada de um pacote adulterado (J18) |
| M15-R25 | Aceitação de engenharia: determinismo, proveniência, instalação, reversão, teclado, offline | PARTIAL | 0.18.1 instalada sobre a 0.17.0; hash SHA-256 da biblioteca idêntico (11 execuções, 89 ficheiros); reversão verificada por hash, mas não executada (README J18); sem instalação em máquina limpa, sem passagem por leitor de ecrã |
| M15-R26 | Linhas de base medidas e depois melhorias | MET | docs/evidence/m15 base face à instalada; perf J18 da 0.18.1 |
| M15-R27 | Revisões especializadas independentes | MET | revisões de #24, #25, #31 (ciência, segurança), #32 (ciência, UI), #33, #34 (ciência, integridade), 3 rondas gráficas cegas e revisão de UX instalada; conclusões corrigidas antes da integração (ver Veredictos das revisões independentes); relatórios brutos não submetidos |
| M15-R28 | Candidato instalado funcional e relatório final honesto | MET | instalador 0.18.1 0e37bbcf... instalado e verificado (J18); PR #35 |
| M15-R29 | Sem limpeza destrutiva, API paga nem integração silenciosa | PARTIAL | restrição de processo não verificável a partir do repositório; sem instalação do Unreal (pré-verificação), sem serviço pago; as integrações foram feitas pelo orquestrador durante a recuperação e estão registadas abaixo |

## M16, M16.1 e M16.2: mundos geoespaciais e Mission Control

| id | requisito | estado final | evidência |
|---|---|---|---|
| M16-R01 | Avaliar as pilhas de renderização com evidência | MET | docs/m16-geospatial-mission-control.md; docs/evidence/m16/renderer-research.md, spikes/*.json |
| M16-R02 | Arquitetura comum de reprodução nas três vistas | MET | m16_journeys 78/78 instalado (J18); hashes de registo inalterados |
| M16-R03 | Vista geoespacial opcional a funcionar | MET | jornadas m16 78/78 (J18); PR #25 integrado em 52bb135 |
| M16-R04 | Camada de georreferenciação testada | MET | testes desktop/geo wgs84.rs e environment.rs face às constantes PROJ; CI-main |
| M16-R05 | Ambientes indicam fonte, atribuição e exatidão; dados legítimos | PARTIAL | aplicação do crédito e créditos no mapa corrigidos (1c87416, 28b6b73, f3590c9); mantêm-se lacunas de licença (NAIP, Açores, IGN, NPI) e a justificação USGS no NOTICE; sem revisão jurídica |
| M16-R06 | UX geoespacial: predefinições, trajetórias, comparação, regresso | MET | jornadas m16 78/78 (J18) |
| M16-R07 | Sobreposições apenas a partir de dados registados | PARTIAL | trajetória, anéis, marcadores de eventos; sem envelope de incerteza nem sobreposição de observações de sensores |
| M16-R08 | Fidelidade visual da vista geoespacial | PARTIAL | o padrão do proprietário não foi atingido; renderizador geoespacial inalterado por M17 e M18; módulo Cinematic classificado 'modest' três vezes (rondas cegas) |
| M16-R09 | Funciona offline, sem tokens, sem pedidos ocultos | MET | J18 perf-m16.json: nenhum pedido WebView a sair da máquina; jornadas m16 sem pacote e com pacote adulterado |
| M16-R10 | Vista Mission Control (janela central, telemetria, eventos, requisitos) | MET | jornadas m16 78/78; modo do player renomeado para 'Flight console', 'Mission Control' designa apenas a página inicial (5cc7294) |
| M16-R11 | Telemetria específica do domínio com etiquetas de origem | MET | jornada 'ground Mission Control without aerospace metrics' (J18 m16-journeys.txt) |
| M16-R12 | Linha temporal como funcionalidade distintiva | MET | marcadores, falha, deteção e violação desenhados apenas quando atingidos (4195b6b); jornada m16 'event to evidence card' |
| M16-R13 | Percurso Missão até Evidência sem becos sem saída | PARTIAL | existem ligações para Compare e Challenge; nenhuma jornada atravessa Counterexample, Mitigation e Evidence |
| M16-R14 | Sistema de design, incluindo acessibilidade | PARTIAL | tokens.css e 6 ficheiros css; revisão de UX: contraste do texto cinzento pequeno e consistência das cores dos chips; sem documento de sistema de design nem auditoria de contraste |
| M16-R15 | Demonstração de 12 passos de ponta a ponta, incluindo execução offline | MET | jornadas m16 78/78 na 0.18.1 instalada (J18) |
| M16-R16 | Fundações para UAV, terrestre, nave espacial, multientidade | MET | registo de cenas, vv-run.v2, domain-reference (8 testes), Cinematic lê a v2 multientidade (#33 4301c1f, verificação por amostragem 44/44); nenhum domínio de nave espacial construído (não exigido) |
| M16-R17 | Medir o desempenho, incluindo sessão longa | MET | J18 perf: geo p99 18,7 ms; sessão de 180 s com conjunto de trabalho de 970 para 878 MB, p99 18,5 a 19,1 ms; execuções 0.16.x em evidence/m16 |
| M16-R18 | Preservar linhas de base e sementes; sem alegação de 'digital twin' | MET | hashes de registo iguais antes e depois nas jornadas; diff da evidência vazio; CI-main |
| M16-R19 | Segurança: recursos não confiáveis, proveniência, sem credenciais | MET | aprovação da revisão de segurança de #31 após correção dos problemas graves 1-6 (1b253cf..5057000, revisto quatro vezes); testes packages.rs e modules.rs; jornada de pacote adulterado |
| M16-R20 | Capturas de aceitação visual das oito cenas | MET | docs/images/m16-studio; capturas das jornadas (J18 m16-journeys.txt) |
| M16-R21 | Revisões independentes de M16 | MET | revisão de #25: approve, não bloqueante; correções (fugas de caminhos, validação de resumos, aplicação de créditos, limites); nova revisão approve |
| M16-R22 | PR sobre #24, instalador, reversão, limites honestos | MET | #25 integrado em 52bb135 (árvore == 9a26f7a); hashes de reversão (J18) |
| M16.1-R01 | Diagnosticar a vista subdesenvolvida da 0.16.0 | PARTIAL | docs/m16-1-visual-quality.md; o proprietário rejeitou a 0.16.1 seguinte |
| M16.1-R02 | Palco claramente visível e compreensível | MET | stage-model.js; planos próximos da plataforma da Cinematic lidos como 'substantial' na ronda cega 3 |
| M16.1-R03 | Ortofotos e elevação de maior resolução, com licença verificada | PARTIAL | camadas de detalhe de 0,5 m, lidar 3DEP; Portugal continental excluído, elevação de Santa Maria 30 m |
| M16.1-R04 | Catálogo para além de dois locais | MET | 8 pacotes; jornadas m18 verificam oito cartões (J18); recorte do texto dos cartões assinalado pela revisão de UX (ver M18-R13) |
| M16.1-R05 | Controlo compacto de proveniência, crédito obrigatório visível | PARTIAL | sources-info.js, linha de crédito no mapa (28b6b73); revisão de UX: colisão da atribuição a 1024x640; suficiência jurídica não revista |
| M16.1-R06 | Sem violações futuras na reprodução; modo de análise; vários tamanhos | MET | marcadores retidos até serem atingidos (4195b6b); caixas do cabeçalho medidas em três tamanhos (m18-journeys.txt) |
| M16.1-R07 | Manter Three.js; sem dependência de renderização não justificada | MET | vista web sem alterações nas dependências; módulo Godot separado e opcional |
| M16.1-R08 | Evidência instalada antes e depois | MET | docs/evidence/m16/before, after, after-0.16.2, installed-0.16.x |
| M16.1-R09 | O proprietário aceita o resultado visual | NOT MET | aceitação do proprietário nunca registada; renderizador geoespacial inalterado |
| M16.2-R01 | Questionar todo o pipeline de renderização | MET | docs/m16-2-flagship.md, tabela de alternativas; docs/m18-cinematic-preflight.md |
| M16.2-R02 | Mundos 3D genuínos: edifícios, vegetação, LOD | PARTIAL | funcionalidades do esquema v3 e vegetação instanciada (#25); pacotes B/C sem vegetação; alturas estimadas |
| M16.2-R03 | Pontos de referência, materiais do solo, transições de LOD | PARTIAL | junção em vistas amplas, foto reiluminada, bordas de mar e terreno listadas como abertas |
| M16.2-R04 | Distinguir levantado, estimado, ilustrativo | MET | origem da altura por registo; legenda simulado/contexto/ilustrativo |
| M16.2-R05 | Sistema de ambientes mundial extensível | PARTIAL | uma entrada de catálogo e dois scripts acrescentam um local; instalação por zip com SHA-256; sem navegação nem transferência, na aplicação, de pacotes ausentes; remoção apenas para os importados |
| M16.2-R06 | O instalador não deve crescer com cada local | NOT MET | instalador de 19,7 MB (0.17.0) para 42,4 MB (0.18.1): oito pacotes incluídos; alojar pacotes separadamente requer aprovação do proprietário (publicação externa) |
| M16.2-R07 | Acrescentar um ambiente não exige programação personalizada | MET | cinco pacotes construídos a partir de entradas de catálogo (docs/m17-environments.md); pacotes validados; NOTICE gerado e testado (497736d) |
| M16.2-R08 | Ambiente emblemático: o foguetão é o sujeito | PARTIAL | planos próximos da plataforma da Cinematic 'substantial', planos amplos 'modest' (ronda cega 3); renderizador geoespacial inalterado |
| M16.2-R09 | Não ocultar geometria pobre pelo enquadramento; sem alegação de fotorrealismo | PARTIAL | os documentos declaram não haver fotorrealismo; regras de câmara ajustadas aos dados; nem todos os ângulos foram avaliados |
| M16.2-R10 | Mission Control excecional; estado de reprodução unificado | PARTIAL | cabeçalho corrigido (4195b6b), renomeação, caixas medidas em 3 tamanhos (J18); lacunas da revisão de UX (navegação a 820 px, consistência dos chips) |
| M16.2-R11 | Arquitetura para várias etapas, veículos e domínios; física separada dos visuais | MET | registo de cenas, vv-run.v2, hashes de registo inalterados; leitor de subida da Cinematic (#33) |
| M16.2-R12 | Encontrar as causas reais de uma cena mais pesada; libertação de recursos | PARTIAL | J18: conjunto de trabalho geo 873 MB, 653 MB após sair do player, GPU 469 MB; sem compressão de texturas nem streaming |
| M16.2-R13 | Processo de aceitação visual com missão e câmara idênticas | PARTIAL | conjuntos emparelhados (evidence/m16) e protocolo cego congelado; sem iluminação variável |
| M16.2-R14 | Revisões independentes de design e gráficos; sem excelência por testes | MET | três rondas cegas (todas 'modest'), revisão de UX GOOD WITH GAPS, revisões anteriores 'not significantly better' |
| M16.2-R15 | A aceitação visual do proprietário é o portão de lançamento | BLOCKED-EXTERNAL | só o proprietário pode aceitar; PR #35 e estado do README (#36) indicam aceitação pendente |
| M16.2-R16 | Integrado de ponta a ponta na Studio instalada | MET | jornadas m16 78/78 na 0.18.1 instalada (J18) |
| M16.2-R17 | Publicar trabalho validado; não integrar M16 antes da aceitação do proprietário | MET | mandato de recuperação do proprietário de 2026-11-11 autorizou commit, push, PR e integração em `main` após passarem todas as revisões independentes e portões de qualidade aplicáveis; #25 integrado em 52bb135 após revisão independente e CI verde no SHA testado e fixado (CI-main); reversão presente |

## M17: experimentação, veículos, renderizador opcional, missões de vários estágios

| id | requisito | estado final | evidência |
|---|---|---|---|
| M17-R01 | Corrigir problemas conhecidos da vista técnica | PARTIAL | cabeçalho reconstruído (4195b6b); libertação e memória medidas (J18); revisão de UX: colisão da atribuição a 1024x640; junção do conjunto de dados por resolver |
| M17-R02 | Atribuição Copernicus compacta e juridicamente adequada | PARTIAL | controlo e linha de crédito no mapa entregues (28b6b73); suficiência do aviso WorldDEM/Sentinel não revista |
| M17-R03 | Catálogo extensível, níveis de qualidade, instalar e remover, evitar empacotar tudo | PARTIAL | níveis A-D, instalação por zip, página de atlas; todos os oito incluídos; sem instalação na aplicação de pacotes ausentes |
| M17-R04 | Variedade real de locais | MET | 8 pacotes (porto espacial, ilha, deserto, costa, montanha, polar) |
| M17-R05 | Módulo instalável separadamente; a base funciona sem ele | MET | m17_cinematic_journey 11/11 instalado (J18); correções de segurança de modules.rs (1b253cf, 3410b65) |
| M17-R06 | Arquitetura de investigação, protótipo avaliado | PARTIAL | protótipo Godot avaliado, agora em Direct3D 12 (J18 perf/bench-*.json; bench/third-iteration); WebGPU e UE5 não avaliados |
| M17-R07 | UE5/Cesium para Unreal avaliados separadamente | PARTIAL | docs/m18-cinematic-preflight.md; o proprietário delegou a escolha de bibliotecas, imagens e UE5; decisão: bibliotecas CC0 em Godot, UE5 não instalado; sem medição do UE5 |
| M17-R08 | Melhoria de fidelidade substancial e imediatamente visível | NOT MET | três rondas cegas, 9 veredictos de revisores, todos 'modest' no conjunto; planos próximos da plataforma 'substantial', planos amplos 'modest' ou 'marginal'; protocolo congelado antes das alterações (visual-protocol.md v1-v3) |
| M17-R09 | Perfis gráficos e avaliação adaptativa do hardware | PARTIAL | perfil automático limitado a High (547602b); primeiro fotograma em Auto (High) 13,9 s, p99 13,7 ms, 2,4 GB de VRAM (J18); caminhos de pouca VRAM e sem Vulkan não exercitados |
| M17-R10 | Renderizador consome estado autoritativo; mesma evidência nas duas vistas | MET | tests/test_cinematic_pose.py executado com VV_GODOT: 442 testes Python OK (J18 verification.txt); verificação por amostragem 44/44 usa a execução selecionada na Studio |
| M17-R11 | Ciclo de vida do módulo: somas de verificação, disco, instalação interrompida, recurso alternativo | PARTIAL | jornada 11/11, incl. adulteração, verificação de integridade no segundo arranque e desinstalação; correções de bloqueio de instalação e de reversão (24986e0, 1b253cf); sem caminho de transferência; cache fora do módulo não removida; sem assinatura de código |
| M17-R12 | A vista Cinematic cobre as missões do produto (aterragens, subidas) | MET | registos de aterragem e de subida reproduzem (ca5cb4b, c30c5f7, 3ebed9f); verificação por amostragem 44/44: primeiro fotograma entre 12,2 e 13,7 s, com ecrã de arranque a cerca de 0,9 s (J18); o robô terrestre não tem cena cinematográfica |
| M17-R13 | Fluxo do Laboratório de experiências | PARTIAL | m17_lab_journeys 34/34 (J18); revisão de UX: sem ação principal antes de uma alteração, deslocamento aninhado, sementes desativadas sem motivo indicado |
| M17-R14 | Apenas parâmetros com semântica definida e intervalos validados | MET | check_exploratory; T/W mínimo limitado (04de572); revisão científica APPROVE |
| M17-R15 | Alterar uma experiência gera um novo registo reprodutível | MET | lab 34/34; verificação por amostragem: novo registo com fator de impulso (J18) |
| M17-R16 | Exploração de engenharia com margens, sementes, sem alegações universais | PARTIAL | margens numéricas de subida (55247ea; verificação por amostragem '-329 Pa'); as influências são sugestões escritas à mão; UX: limites de dígitos longos, linhas com falha primeiro |
| M17-R17 | Aterragem suave, mas fora da plataforma: o que alterar | MET | demos.rs soft-but-off-pad (suíte do desktop 306 testes, J18 verification.txt) |
| M17-R18 | Várias arquiteturas de veículos, definição flexível | PARTIAL | 6 veículos; quatro fatores de conceção de aterragem; sem satélites, módulos de aterragem nem aeronaves; sem modelos licenciados |
| M17-R19 | Ciclo de vida completo da missão até à inserção orbital | MET | vv-ascent no CI (912e01a); revisões científicas APPROVE (#31, #34); referências independentes (7dfde34); ponto-massa 2D exploratório, declarado |
| M17-R20 | Recuperação e regresso do primeiro estágio | NOT MET | RTLS inviável (722 face a 2186 m/s, scripts/m18_booster_budget.py); portão downrange congelado em ab110d1, falhou no teste held-out 3deb85d: small 8/10, medium 9/10 (ramo recovery/booster, não integrado); booster balístico |
| M17-R21 | Operações de nave espacial para além da inserção | NOT MET | sem modelo; apenas voo livre (coast) de 600 s; hangar 'Not in this build' |
| M17-R22 | Transições de fase transportam estado e semântica de verificação | MET | testes vv-ascent no CI, incl. hash dourado do estado das entidades (0d487db); testes de resultado e veredicto (6feb147) |
| M17-R23 | Missões multientidade com esquema versionado | MET | vv-run.v2, fixture v1, reprodução de build anterior (domain 0.15.1 VERDICT_RULES, desktop/domain-ascent/tests/earlier_build.rs) |
| M17-R24 | Câmaras que seguem entidades | MET | câmaras por entidade da Cinematic com origem flutuante (3ebed9f, revisão #33 APPROVE); a cena 2D da Studio tem seletor de entidade |
| M17-R25 | Evidência M9-M16 legível e inalterada | MET | diff da evidência vazio; fixture v1; uma execução real 0.15.0 verifica por reprodução de build anterior |
| M17-R26 | Planear domínios futuros sem armamento | PARTIAL | roteiro e domain-reference; sem domínio de UAV nem de fusão de sensores |
| M17-R27 | Fluxo unificado de 10 passos | PARTIAL | verificação por amostragem 44/44 cobre página inicial, hangar, Lab, Compare, player e Cinematic (aterragem e subida); o passo Investigate e evidência não está na jornada; lacunas da revisão de UX |
| M17-R28 | Acessível sem perder profundidade | PARTIAL | revisão da persona de agente GOOD WITH GAPS; sem teste com pessoas |
| M17-R29 | Aceitação real instalada em todas as dimensões | PARTIAL | jornadas instaladas J18 48+78+34+11+72+44, desempenho, 442 testes Python, campanha de 87 casos; renderização não aceite; acessibilidade apenas automática |
| M17-R30 | PR revisíveis separadamente, ordem mantida, sem integração automática antes da aceitação | MET | #31 substitui #26-#30, cada unidade revista; mandato de recuperação do proprietário de 2026-11-11 autorizou a integração em `main` após revisões independentes e portões; #31 integrado em f5db000 após revisão independente e CI verde no SHA testado (CI-main) |
| M17-R31 | Fatias tangíveis, sem interfaces provisórias | PARTIAL | cada fatia tem código e jornada; renderizador refinado não está ao padrão do proprietário |
| M17-R32 | Integridade científica e disciplina de recursos | MET | proteções de sementes (ead0a0a), etiquetas exploratórias, trabalho pesado em série; portão do booster congelado antes da afinação |
| M17-R38 | Preservar evidência congelada; M13 reproduz-se no CI | MET | compare_investigation.py e passo do CI verde em `main` (CI-main); causa: caso v2 3baa1c1 alterou o hash da fonte, ciência idêntica |
| M17-R33 | Ambiente de investigação multiestágio reutilizável, com limites honestos | MET | docs/m17-ascent.md, limites de validade; artefacto da atmosfera acima de 300 km declarado |
| M17-R34 | Mission Control adapta-se a missões multientidade | MET | jornadas Lab e player em subida (J18); câmaras de entidade na Cinematic View |
| M17-R35 | Pressupostos, interfaces, invariantes, referências independentes | MET | testes de referência no CI; testes independentes de vis-viva, velocidade terminal e ponto de impacto (7dfde34); revisões APPROVE |
| M17-R36 | Arquitetura reutilizável para domínios futuros | PARTIAL | domain-reference e contrato; apenas arquitetura |
| M17-R37 | Corrigir M16 primeiro; base limpa para M17; sem domínios incompletos | MET | sequência seguida; M17 integrado em `main` após M16 |

## M18: página inicial do Mission Control, hangar, ambientes, investigação cinematográfica

| id | requisito | estado final | evidência |
|---|---|---|---|
| M18-R01 | Modo Engenharia rigoroso, rápido e leve | MET | J18 perf: arranque a frio 0,97 s, p99 18,6 ms (o controlo de página em branco dá 19,1 ms), nenhum fotograma acima de 33 ms |
| M18-R02 | Modo Cinematic visualmente extraordinário | NOT MET | rondas cegas 1-3 todas 'modest' (ver Veredictos das revisões independentes) |
| M18-R03 | Ambos os modos usam os mesmos registos autoritativos | MET | teste de paridade de pose executado (J18 verification.txt); Godot lançado sobre a execução selecionada na Studio (verificação por amostragem); UX: o ambiente cinematográfico difere do ambiente do player |
| M18-R04 | Veículo, ambiente e missão como um só produto | MET | página inicial, hangar, atlas, Lab e player ligados; jornadas m18 72/72 (J18) |
| M18-R05 | Arquiteturas de veículos com diferenças físicas reais | PARTIAL | quatro fatores de conceção escalam o veículo simulado (teste em case.rs); sem conceção ao nível de componentes |
| M18-R06 | Foguetões: lançamento, subida, separação de estágios, recuperação, estágio superior, operações orbitais | PARTIAL | lançamento até à inserção entregue; recuperação NOT MET (portão 8/10, 9/10); sem operações para além da inserção |
| M18-R07 | Validado, exploratório e ilustrativo distinguidos | MET | nível de evidência vem do catálogo de domínios; o desconhecido lê-se como exploratório (fff831f) |
| M18-R08 | Investigação UE5/Cesium com decisão de instalação | PARTIAL | pré-verificação; decisão registada (Godot com CC0, sem UE5); licença e desempenho a partir de fontes secundárias |
| M18-R09 | Sem instalação do Unreal nem serviços pagos sem aprovação | MET | nada instalado; pegada de ~110 GB indicada na pré-verificação |
| M18-R10 | Qualidade de arte e de dados do Godot para terreno, materiais e iluminação | NOT MET | recursos de autoria própria e CC0 integrados (e278b88, 3521c5a); resultado falhou nas rondas cegas; fraquezas dos planos amplos inalteradas |
| M18-R11 | Painel do Mission Control com três caminhos | PARTIAL | página inicial com três caminhos (jornadas m18 72/72); revisão de UX: a página inicial não tem declaração exploratória |
| M18-R12 | Vista geoespacial deixa de ser básica e artificial | NOT MET | renderizador geoespacial inalterado; sem melhoria medida |
| M18-R13 | Todos os ambientes facilmente visíveis | PARTIAL | oito cartões, imagens reais dos pacotes (verificação por amostragem); revisão de UX: texto do cartão cortado, estado do módulo preso em 'Checking' |
| M18-R14 | Alterar parâmetros e voltar a executar é óbvio | MET | Hangar 'Design and fly', Lab; verificação por amostragem 44/44 (J18) |
| M18-R15 | Novos veículos e missões de subida fáceis de encontrar | MET | ligação na página inicial e hangar (verificação por amostragem) |
| M18-R16 | Vista Cinematic mais do que uma melhoria modesta | NOT MET | rondas cegas todas 'modest'; planos próximos da plataforma 'substantial' |
| M18-R17 | Fluxo de ponta a ponta convincente | PARTIAL | a jornada inclui agora a Cinematic de subida; o passo Investigate e evidência não está incluído; lacunas de UX |
| M18-R18 | Integrar os PR M15-M17 com segurança após a aceitação do proprietário | MET | mandato de recuperação do proprietário de 2026-11-11 autorizou a integração após revisões independentes e portões; #24, #25, #31, #32, #33 e #34 integrados em ae7043d, 52bb135, f5db000, 57d1da1, 4301c1f e 66b30ca após revisão independente e CI verde no SHA testado (CI-main); a release #35 é integrada por esta PR (ver Registo de integração) |
| M18-R19 | Alterações genuínas guiadas pela simulação | MET | teste de conceção do veículo; verificação por amostragem: R1 1,66 face a 60,08 m/s, carga de 600 kg para Suborbital (J18) |
| M18-R20 | Missões multientidade coerentes, números independentes | MET | testes de referência no CI; verificações independentes (7dfde34); revisão científica de #34 APPROVE, revisão de integridade APPROVE após correção dos problemas graves |
| M18-R21 | Separar simulação, estimativa, derivado, ilustrativo | MET | legenda T/E/D, legendas, etiquetas 'Illustrative'; renderização não avaliada (cc05839) |
| M18-R22 | Laboratório facilmente encontrável e comparação excelente | PARTIAL | etiquetas e margens corrigidas; revisão de UX: 'safe' isolado num contacto a 60 m/s, par com aspeto idêntico, ação principal do Lab |
| M18-R23 | Catálogo de ambientes visível e utilizável | PARTIAL | atlas com 'Use for missions'; revisão de UX: texto do cartão cortado, chip 'Terrain is context only', estado preso |
| M18-R24 | Página inicial e navegação melhoradas | PARTIAL | renomeação feita; revisão de UX: transbordo da navegação a 820 px, sinónimos |
| M18-R25 | Melhoria visual convincente e mensurável | NOT MET | medida pelo protocolo cego congelado e não atingida |
| M18-R26 | Desempenho e degradação graciosa neste hardware | MET | J18 perf: p99 da Studio 18,6 ms (igual ao de uma página vazia na mesma janela); Cinematic Auto (High) p99 13,7 ms e primeiro fotograma 13,9 s, Balanced p99 5,4 ms e primeiro fotograma 11,6 s; outro hardware não medido |
| M18-R27 | Teste independente das jornadas de utilizador instaladas | MET | registos J18 na 0.18.1 instalada: M15 48/48, M16 78/78, Lab 34/34, Cinematic 11/11, M18 72/72, verificação por amostragem 44/44 (ramo release/0.18.1, PR #35) |
| M18-R28 | Instalação, remoção e recuperação de módulo fiáveis | MET | jornada cinematic 11/11, incl. adulteração, desinstalação e reabertura; módulo 0.2.8, SHA-256 do zip a8608a2d... |
| M18-R29 | Licenciamento e atribuição de dados geográficos | PARTIAL | NOTICE gerado e testado (497736d), crédito aplicado; lacunas de licença abertas |
| M18-R30 | Defeito: rótulos de Compare idênticos | PARTIAL | corrigido (78f45c3; verificação por amostragem: rótulos diferentes, não truncados); revisão de UX: o par de aterragem ainda parece idêntico |
| M18-R31 | Defeito: coluna de margem de subida vazia | MET | 55247ea; o Lab mostra alterações numéricas de margem, sem margem vazia (verificação por amostragem J18) |
| M18-R32 | Defeito: 'Mission Control' designava duas coisas | MET | modo do player é 'Flight console' (5cc7294); jornadas m18 |
| M18-R33 | Defeito: cabeçalho do player desordenado a 1440 px | MET | 4195b6b; caixas do cabeçalho medidas a 1024x640, 1440x900 e 1920x1080 (m18-journeys.txt) |
| M18-R34 | Entregáveis: antes e depois, números, desempenho, relatório de aceitação | PARTIAL | m18-numbers.json, evidência instalada, perf (J18); este documento; relatório final entregue ao proprietário; a experiência fica PARTIAL |
| M18-R35 | Sem integração prematura, reversão e instalador validado | PARTIAL | instaladores de reversão com hash; 0.18.1 construído por build.ps1 e instalado; reversão não executada |

## Veredictos das revisões independentes

Todos os revisores eram agentes novos, sem o raciocínio do autor. Os relatórios brutos não estão submetidos; registam-se as conclusões e os commits que as fecharam.

| Revisão | Veredicto | Resultado |
|---|---|---|
| Revisão de #24 (M15) | conclusões: 2 graves (reprodução de versão antiga, alegação GNSS tardia sem suporte) e 9 menores | corrigidas no percurso de integração; #24 integrado em ae7043d |
| Revisão e nova revisão de #25 (M16) | approve, não bloqueante; menores sobre fugas de caminhos, validação de resumos e aplicação de créditos | corrigidas; nova revisão approve; integrado em 52bb135 |
| Revisão científica de #31 (M17) | APPROVE com menores S1-S10 | S1-S10 corrigidos em #34 |
| Revisão de Studio e segurança de #31 (M17) (4 rondas) | APPROVE; graves 1-6 corrigidos (1b253cf..5057000) | integrado em f5db000 |
| Teste de pacotes com zlib (9aa73c7, 497736d) | APPROVE | integrado com #31 |
| Consulta Fable 5.2 n.º 1 (plano) | integrar em SHAs fixados; Godot com recursos de autoria própria; congelar primeiro o protocolo visual cego | seguido; a recuperação do booster foi mantida como tentativa com prazo, contrariando o conselho de a abandonar, porque o mandato proíbe a redução silenciosa |
| Primeira ronda gráfica cega (S2, S3, S4; 3 revisores) | modest, modest, modest | portão falhou |
| Consulta Fable 5.2 n.º 2 (graphics gate reachable?) | recomendou uma tentativa final, com prazo, no plano S3, com regra de paragem fixada antecipadamente | seguida; segunda ronda modest x3; regra de paragem aplicada |
| Segunda ronda gráfica cega (S3a, S3b; regra de paragem fixada antes) | modest, modest, modest (S3a classificado como substantial por um revisor, limítrofe por outro) | portão falhou; objetivo NOT MET |
| Delegação do proprietário de 2026-11-11 | escolha de bibliotecas CC0, imagens e UE5 | bibliotecas CC0 em Godot; sem UE5 |
| Terceira ronda gráfica cega (seis pares, protocolo v3, novos revisores) | modest, modest, modest; planos próximos da plataforma substantial, planos amplos modest ou marginal | NOT MET, final |
| Revisão científica e de UI de #32 (M18) | approve com graves (mesmo id de ambiente no player, foco do atlas, token do Lab) | corrigidas; nova revisão APPROVE; integrado em 57d1da1 |
| Revisão de código do ramo Cinematic | conclusões (limite automático do perfil, geração do NOTICE, fuga de caminho, inversão da pluma, limites da CLI, verificações de registo) | corrigidas; nova revisão APPROVE; integrado em 4301c1f |
| Consulta Fable 5.2 n.º 3 (booster) | opção A com portão (limiares fixados de 3,0 e 1,0 m/s, sementes held-out), alternativa C | portão falhou com 8/10 e 9/10; RTLS NOT MET |
| Revisão científica de #34 | APPROVE com um grave (execuções de subida de versões anteriores reproduziriam como não reproduzidas) | tabela de regras de veredicto, domínio 0.15.1 e fixture acrescentados |
| Revisão de integridade de #34 | APPROVE com graves (regra de resultado não ligada à mudança de requisito, eventos cobertos ignorados, faixa de proveniência exagerada) | corrigidas; integrado em 66b30ca |
| Revisão de UX instalada (fable-ux-critic, Studio 0.18.1) | GOOD WITH GAPS (1 bloqueante, cerca de 8 graves) | primeira passagem de correção (f01f87a) |
| Passagens 1 a 3: revisão de código (sonnet) e de UX (fable), agentes novos em cada ronda | código APPROVE WITH NITS em todas; UX GOOD WITH GAPS, depois 1 e 2 bloqueantes (pílulas cortadas; identidade da corrida; 'Safety: safe.' na Cinematic) | corrigidos nas passagens seguintes (3e81ec9, 52d435a, 24fd10b) |
| Consulta Fable 5.2 n.º 4 (regra de paragem das passagens de UX) | opção D: inventário fechado das superfícies, correção por classe, guardas determinísticas, conjunto de capturas congelado, uma verificação de bloqueios; recomendou perguntar ao proprietário se uma experiência PARTIAL pode ser integrada | D seguida; a pergunta ao proprietário não foi feita (o mandato autoriza a integração e o objetivo gráfico NOT MET já foi integrado com registo); esta divergência fica registada aqui e no relatório final |
| Passagem 4: código (sonnet) e bloqueios (fable) | código APPROVE WITH NITS; nenhum bloqueio de honestidade; 1 bloqueio de percurso (gráfico 2D com 55 px a 1024x640) | corrigido na passagem 5 (c94eeab) |
| Passagem 5: código (sonnet, 16 mutantes) e verificação dirigida (fable) | código APPROVE WITH NITS (guarda apanhava 9 de 16); nenhum bloqueio; U3 corrigido, U1, U2, U4 parciais | passagem 6 (2f0117d): 16 de 16 mutantes, qualificador exploratório em todas as corridas, estado final neutro quando as regras não foram avaliadas |
| Passagem 6: código (sonnet, com mutantes novos) e verificação dirigida (fable) | código APPROVE WITH NITS (apenas testes e documentação); nenhum bloqueio de honestidade; título da telemetria corrigido, restantes parciais | guarda reforçada no commit 3ee94c7, só de testes e documentação; pendências de produto registadas como backlog |
| Revisões anteriores (M17, M18) | Cinematic 'modest improvement' x2; geoespacial 'marginal' (Fable 5.1) | substituídas pelas rondas cegas |

## Restantes não cumpridos e motivos

- **Objetivo gráfico (M17-R08, M18-R02, R10, R16, R25, M16.1-R09, M18-R12).** Três rondas cegas sob um protocolo congelado antes de qualquer alteração, nove veredictos, todos 'modest' no conjunto. Os planos próximos da plataforma leem-se como 'substantial'; os planos amplos não. Fraquezas consensuais: resolução da imagem do terreno, árvores de baixa poligonagem, pluma plana, iluminação plana. A regra de paragem foi aplicada e não foi feita nova iteração. O renderizador geoespacial (Three.js) não foi alterado. A aceitação visual pelo proprietário fica fora deste documento (M16.2-R15).
- **Recuperação do primeiro estágio do booster (M17-R20).** O regresso ao local de lançamento é inviável com as reservas atuais (o booster transporta cerca de 722 m/s de delta-v; anular apenas a velocidade horizontal exige cerca de 2186 m/s). A aterragem downrange funciona em 1D (cerca de 4 m/s), mas o portão held-out congelado falhou: 8/10 small, 9/10 medium (variância de propelente MECO). O ramo `recovery/booster` contém a evidência e não está integrado; o booster mantém-se balístico.
- **Nave espacial e operações orbitais para além da inserção (M17-R21).** Sem modelo; apenas voo livre (coast) de 600 s.
- **Crescimento do instalador por local (M16.2-R06).** Oito pacotes incluídos (instalador de 42,4 MB). Alojar pacotes separadamente é publicação externa e requer aprovação do proprietário.
- **BLOCKED-EXTERNAL.** Estudo de utilização com pessoas reais (M15-R22), revisão humana do protocolo de início do G3 (M15-R19) e aceitação visual pelo proprietário (M16.2-R15).
- **Pendências abertas por trás de linhas parciais.** Distintivo da biblioteca para execuções guardadas com regras anteriores; defeitos geoespaciais e de Three.js (campos tipados do resumo de pacotes, limite de crédito, justificação USGS no NOTICE); primeiro fotograma da Cinematic: 13,9 s em Auto (High), 11,6 s em Balanced; um ecrã de arranque aparece por volta dos 0,9 s.

- **Pendências de experiência (UX PARTIAL).** A 1024x640 as pílulas não selecionadas mantêm o identificador curto mas cortam as condições; o painel da Cinematic da subida não diz que o impacto do booster não é modelado; o chip verde "No safety rule broken (5 checked)" aparece ao lado de requisitos falhados (verdadeiro e delimitado, mas devia ser neutro); o corredor mostra "To goal 0.00 mm" ao lado de "Mission incomplete" sem explicação (o registo do domínio não diz que cláusula de `mission_completion` falhou); a pluma continua desenhada depois do contacto; nomes de locais na Cinematic são só contexto; contraste sobre imagens, tecnologias de apoio e uso por pessoas não foram verificados.

## Registo de integração

| PR | Estado | Commit de integração em `main` | Integrado (UTC) |
|---|---|---|---|
| #24 M15 experiência de missão | integrado | ae7043d | 2026-11-11 14:09 |
| #25 M16 geoespacial e Mission Control | integrado | 52bb135 | 2026-11-11 16:33 |
| #31 M17 integrado (substitui #26-#30) | integrado | f5db000 | 2026-11-11 17:47 |
| #32 M18 Mission Control, hangar, ambientes e correções | integrado | 57d1da1 | 2026-11-12 00:16 |
| #33 Cinematic View 0.2.0 | integrado | 4301c1f | 2026-11-12 06:14 |
| #34 Verificação da subida, resultado do booster | integrado | 66b30ca | 2026-11-12 07:28 |
| #26, #27, #28, #29, #30 | fechados, substituídos por #31 | nenhum | n/d |
| #35 Release Studio 0.18.1, verificação instalada | integrado por esta PR (o commit de integração está no histórico de `main`) | ver `main` | 2026-11-15 (data da integração desta PR) |
| #36 estado do README M15-M18 | aberto | n/d | n/d |

Ponto de reversão antes da recuperação: a23db64. O fluxo de verificação foi concluído com êxito em cada commit de integração. As integrações foram feitas durante a recuperação ao abrigo do mandato de recuperação do proprietário de 2026-11-11, que autorizou commit, push, PR e integração em `main` assim que todas as revisões independentes e portões de qualidade aplicáveis passassem; cada integração seguiu revisão independente e CI verde no SHA testado e fixado (ids de commit mantidos). A aceitação visual pelo proprietário (M16.2-R15) não foi registada e continua pendente. A Studio 0.18.1 (SHA-256 do instalador `0e37bbcf7228b7170ab392966b0cdc79b2e7446280e801cc9912c16bb0ebd0e1`, 42 454 061 bytes; módulo Cinematic 0.2.8, SHA-256 do zip `a8608a2da3da61567520a4e927dbd25c8f5a13b29a0eb37223d2d6d7f90c3df8`) está instalada sobre a 0.17.0; o hash da biblioteca do utilizador foi idêntico antes e depois.

Nota sobre o desempenho da Studio: as linhas acima usam a medição final de 2026-11-15 (J18). Em 2026-11-12 o p99 foi de 8,5 ms; na medição final a cadência de fotogramas da WebView é de cerca de 18 ms (p99 cerca de 19 ms), e uma página de controlo vazia na mesma janela também dá 18 ms; a mudança vem da janela ou do compositor, não da Studio, e não foi investigada mais.

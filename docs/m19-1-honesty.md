# M19.1: correções de honestidade científica da Studio

Estado: concluído localmente no ramo `fix/m19.1-honesty`, criado a partir de `main` em `bec7b3f` (origem da Studio 0.18.1 instalada). Nada foi enviado, integrado nem instalado. As alterações corrigem o que a Studio mostra. Nenhuma simulação, registo, evidência guardada ou hash canónico mudou (ver «Conjunto que não pode mudar»).

## Defeitos de partida e classificação

Classes: (a) só texto ou apresentação da interface; (b) altera evidência registada ou hashes de execução (por exemplo, texto em `evidence.rs` muda o hash do anfitrião e os identificadores das corridas); (c) pode influenciar o comportamento da simulação. Regras do mandato: (a) implementa-se; (b) só se não tocar em evidência protegida, linhas de base ou hashes canónicos, senão propõe-se; (c) nunca se implementa. As linhas 1 a 8 foram escritas antes da implementação; a linha 9 foi acrescentada depois, ao procurar noutros sítios o mesmo defeito.

| n.º | Defeito (Studio 0.18.1) | Onde nasce | Classe | Decisão |
| --- | --- | --- | --- | --- |
| 1 | O chip verde «No safety rule broken (5 checked)» aparece ao lado de requisitos falhados | `requirements.js`, `model.js`, `views/player.js`, `views/control.js`, CSS | (a) | Implementado |
| 2 | A cláusula falhada de `mission_completion` não é mostrada; «To goal 0.00 mm» ao lado de «Mission incomplete» | O registo do domínio terrestre (`desktop/domain-ground/src/record.rs`) não diz que cláusula falhou; a interface mostra a distância sem contexto | (a) na interface; (b) no registo | Interface: implementado. Registo: **proposto, não implementado** |
| 3 | O painel Cinematic da subida não diz que o impacto do booster não é modelado | `desktop/cinematic/scripts/hud.gd` | (a) | Implementado |
| 4 | A pluma continua desenhada depois do contacto | `desktop/studio/ui/js/scenes/rocket.js` (as cenas de engenharia e geoespacial herdam-no) | (a) | Implementado |
| 5 | Velocidade no contacto contra o último ponto amostrado | `hud.gd`, `record.gd` | (a) | Implementado |
| 6 | A 1024x640 as pílulas não selecionadas cortam as condições da corrida | `css/mission.css`, `views/player.js` | (a) | Implementado |
| 7 | «Every requirement and safety rule met.» (player) e «Every requirement met.» (Lab) escritos sempre que nenhuma linha falha, mesmo com linhas não avaliadas | `views/player.js`, `views/lab.js` | (a) | Implementado (achado na pesquisa) |
| 8 | O chip «Mission» fica verde com «no mission requirement listed» | `views/player.js` | (a) | Implementado (achado na pesquisa) |
| 9 | As frases `expectation` das demonstrações dos domínios escrevem «safe» e «safety safe» ao lado de requisitos falhados (`desktop/domain-rocket/src/demos.rs`, `desktop/domain-ground/src/catalog.rs`) e a Compare cita-as como «Expected, stated by the domain» | Texto compilado nos anfitriões | (b): muda o hash dos anfitriões e todos os identificadores de corrida desses domínios | **Proposto, não implementado** |
| 10 | F01, F02: a nota de âmbito do chip de segurança fica no fim do cartão Result, abaixo da dobra | `views/player.js` | (a) | Implementado: a frase está junto ao chip, em cada execução com requisito falhado e nenhuma regra de segurança quebrada |
| 11 | F03: o banner da Compare cita «safe» ao lado de requisitos falhados | Texto `expectation` escrito em Rust (`demos.rs`, `catalog.rs`) | (b) para o texto; (a) para uma nota | O texto **não** foi alterado (defeito 9). Acrescentou-se uma nota por baixo nas três vistas que o mostram (Compare, Run, Prepare) |
| 12 | F10: com altura igual ou inferior a 720 px o CSS escondia as linhas 4 e 5 do HUD, no domínio terrestre «To goal» e «Confidence» | `css/mission.css`, `views/player.js` | (a) | Implementado: só se escondem as duas linhas menores do foguetão e a legenda do foguetão |
| 13 | F04, F06: «Recomputed» e «Verified» a verde ao lado de «Refuted» ou de uma execução com requisitos falhados | `views/discover.js`, `provenance.js`, CSS | (a) | Implementado: a integridade da evidência passa a neutra e com a etiqueta «Evidence integrity: ...»; uma falha continua vermelha |
| 14 | F07: o numeral grande «k/n» com a ressalva em texto pequeno por baixo | `views/lab.js`, `css/lab.css` | (a) | Implementado: a ressalva sobe de texto pequeno e esbatido para texto de 13,5 px a negrito, por cima do numeral (continua menor do que o numeral de 26 px, por isso não tem o mesmo peso visual), e o numeral diz «seeds» |
| 15 | F11: «Go there» não diz para onde vai | `views/player.js` | (a) | Implementado só a mudança de texto: «Go to 4.70 s» (ou «Go to tick N» nas cenas por ticks), derivado de `timeText(d.t, unidade)`, com `title`. A crença contra a verdade como ação em destaque não é uma mudança de texto e fica por fazer |

Nenhum defeito é da classe (c). Nenhuma alteração toca em `crates/`, `src/`, `exec/`, `scenarios/` nem em código Rust.

## O que mudou

1. **Chip de segurança neutro.** `safetyWording` devolve agora o veredicto `held` em vez de `pass` quando nenhuma regra falhou; `verdictOfSafety('safe')` também. `held` tem um escudo contornado e tons neutros (chips, vidro do Flight console, bloco de veredicto, tabela da Library, matriz da Compare, Lab). As linhas de regras de segurança que passam (`verdictOfRequirement` devolve `held` para a categoria `invariant`) são neutras também na secção «Safety rules» do registo, na matriz da Compare, nas células do Lab e na cena da subida, e já não verdes. O verde fica só para um requisito cumprido e para o resultado da missão. O texto não mudou, por isso o teste dos termos (`tests/test_honesty_wording.py`) e os percursos anteriores continuam válidos. Decisão tomada: o chip é neutro sempre, não só ao lado de requisitos falhados, porque «nenhuma regra falhou» é uma afirmação delimitada (regras listadas pelo domínio, estado verdadeiro) e nunca o resultado da missão.
2. **Cláusula de `mission_completion`.** O registo diz só «incomplete; 1 of 1 waypoint(s) reached; 0 mm from the goal at the end». A interface passou a mostrar sob os chips do resultado: «Recorded: 1 of 1 waypoint reached, 0 mm from the goal at the end, outcome incomplete. The record does not say which part of "Mission completion" failed (it expects ...). Reaching the goal is not the same as completing the mission.» (`completionFacts` em `requirements.js`, lido do texto observado que o anfitrião escreve; um teste Python compara-o com `record.rs`). A linha «To goal» do Flight console e do cartão de leitura diz que a distância não indica se a missão ficou completa. `completionFacts` devolve `null`, sem mensagem, se o anfitrião mudar o texto observado ou se a linha não falhou; nesse caso a interface deixa de mostrar a frase (volta ao comportamento antigo). O teste `test_the_reading_follows_the_text_the_ground_host_writes` liga a expressão regular ao texto de `record.rs` e falha se este mudar.
3. **Frase de impacto na subida.** O painel de resultado da Cinematic de uma subida acrescenta, para cada entidade que termina em impacto: «Booster impact: its recorded path ends at the surface (t 617.2 s). The impact itself is not modelled and nothing is drawn for it: no landing burn, break-up or recovery is simulated, and the booster is not drawn after its last sample.»
4. **Pluma depois do contacto.** Depois da última amostra de uma corrida (o contacto, numa aterragem) a reprodução de uma corrida mais longa continuava a desenhar a pluma da última amostra. O registo não diz nada sobre o motor depois dessa amostra, por isso a pluma deixa de ser desenhada; antes e no instante do contacto desenha-se como antes. Verificado no executável (`plumeM` 0 depois do fim e maior que 0 pouco antes).
5. **Velocidade no contacto.** A leitura da Cinematic no fim de uma aterragem já não apresenta a velocidade da última amostra como se fosse a do contacto. Quando o registo traz as velocidades do verificador no instante do contacto (`touchdown_vertical_speed`, `touchdown_horizontal_speed`) mostra-as e diz que são do verificador; senão diz «the record has no contact speed» e nomeia o número como o da última amostra. «-0.0 m» passa a «0.0 m».
6. **Pílulas a 1024x640.** As pílulas não selecionadas mostram o nome completo, o identificador curto e uma contagem exata das condições («2 conditions», «default conditions»); a lista completa fica no nome acessível (texto visualmente oculto, não `display: none`) e no `title`. Já não há reticências em pílulas; se os nomes forem mais largos do que a janela, a linha desloca-se.
7. **«Every requirement ... met».** Vem agora de `noFailureSentence`: só diz «met» quando todas as linhas passaram; com linhas não avaliadas diz «No requirement or safety rule failed, but N were not evaluated» e nomeia cada uma com a sua categoria (por exemplo «Mission starts and completes (requirement)»), em tom neutro.
8. **Chip «Mission».** O tom vem de `missionTone`, calculado a partir do estado de cada linha de requisito (falha, neutro se não houver linhas ou alguma não for avaliada, aprovado), e não de uma expressão regular sobre o texto.

## O que ficou por alterar e porquê

- **Registo do domínio terrestre (defeito 2, classe b).** Dizer qual a cláusula falhada exige que `record.rs` o escreva. Isso muda o hash do anfitrião terrestre e portanto os identificadores de todas as corridas terrestres, e mexe no domínio que o programa M19 marca como o mais sensível. Proposta: acrescentar ao texto `observed`/`explanation` de `mission_completion` a cláusula falhada (aqui: nenhuma conclusão declarada e confirmada no horizonte, com todos os pontos alcançados), com o impacto nos hashes declarado antes e confirmado depois. A interface já não depende disso.
- **Frases `expectation` das demonstrações (defeito 9, classe b).** Substituir «safe» por «no safety rule broken» em `demos.rs` e `catalog.rs` muda o hash dos anfitriões do foguetão e terrestre. Não foi feito; a Compare continua a atribuí-las ao domínio.
- `passes()` do Lab conta «success e safe» como cumprido. Um registo `safe` com a classe `not_evaluated` só existe quando o veículo nunca voou, e então o resultado não é `success`. Não há caso alcançável; não foi alterado.
- Na frase do impacto do booster, a afirmação «the booster vehicle is not drawn after its last sample (its recorded path line stays)» foi verificada no código: em `ascent.gd` o nó e o marcador de cada entidade só são visíveis enquanto `entity_active` (instante entre a primeira e a última amostra, `record.gd`), e `tests/test_cinematic_ascent.py` já verifica que o booster deixa de existir depois do impacto. A linha colorida do percurso registado continua desenhada.
- A pluma do instante do contacto (a última amostra) mantém-se: é o estado registado nesse instante.
- A cena Cinematic não foi tocada além dos textos. O pacote do módulo (zip e versão do manifesto) não foi reconstruído; qualquer lançamento exige reconstruí-lo e subir a versão do módulo.
- Contraste, tecnologias de apoio e uso por pessoas continuam por verificar (o `held` neutro usa os mesmos tokens de cor dos outros chips neutros).

## Conjunto que não pode mudar

Capturado antes de qualquer alteração e recapturado no fim com `docs/evidence/m19/honesty/hash_set.py`. Resultado em `hash-comparison.json` (repetido depois das correções da revisão): 542 valores comparados, 542 idênticos, 0 diferentes.

- `source_sha256` de `vv-rocket` (`295a45b2...`, 20 ficheiros) e de `vv-ascent` (`b11d38f3...`, 12 ficheiros), recalculados com a lista e a normalização de fim de linha das funções `source_sha256()`.
- SHA-256 dos 266 ficheiros versionados em `docs/evidence/` e `exec/claims/`, dos cenários M1 (incluindo `sha256.json` e `canonical-seed-42.json`) e de todos os fixtures e golden dos testes.
- SHA-256 dos anfitriões de domínio, de `vv-lab` e de `vv-exec` construídos por `desktop/build.ps1 -StageOnly`, depois de os reconstruir.
- Registo e ficheiros nativos de cada execução de demonstração dos quatro domínios (25 execuções; sementes distintas 42, 5000, 5002 e 5017, todas de demonstração do produto e nenhuma dentro dos intervalos protegidos de `exec/src/seeds.rs`, de 3000 a 3099, 6000 a 6099, 44000 a 44999 e 50000 a 59999) e os artefactos M1 da missão básica com a semente 42.

## Verificação

Comandos de `AGENTS.md`, na raiz do repositório, antes e depois (resultados guardados em `docs/evidence/m19/honesty/verification-before/` para o antes):

| Comando | Antes (`bec7b3f`) | Depois |
| --- | --- | --- |
| `cargo fmt --check` | sem diferenças | sem diferenças |
| `cargo clippy --all-targets -- -D warnings` | sem avisos | sem avisos |
| `cargo test` | 13 suítes, 138 aprovados, 0 falhados | 13 suítes, 138 aprovados, 0 falhados |
| `python -m unittest discover -s tests -p "test_*.py"` | 441 testes OK (135 ignorados) | 468 testes OK (92 ignorados) |
| o mesmo com `VV_GODOT` (Godot 4.7.2) | 443 testes OK (45 ignorados) | 468 testes OK (45 ignorados) |
| `cargo build --release` | concluído | concluído |
| `python scripts/run_campaign.py --seeds 42,1337,2026 --output-root runs/campaign` | 87 casos, 324 invocações, aprovada | 87 casos, 324 invocações, aprovada |
| `cargo fmt --check`, `cargo clippy ...`, `cargo test` em `desktop/` | 24 suítes, 168 aprovados (com a raiz, 37 suítes e 306 testes, como na 0.18.1); fmt e clippy limpos | idêntico |

A diferença de testes ignorados sem `VV_GODOT` (135 contra 92) não foi investigada na primeira corrida (sem `-v`); a explicação provável, não confirmada, é que a primeira corrida de Python precedeu o `cargo build --release` da raiz e a segunda já tinha o binário. Na segunda corrida os motivos são: 47 sem `VV_GODOT`, 39 por «vv-rocket release binary not built» (o `cargo build --release` do AGENTS.md não o constrói; estes testes não foram executados nem antes nem depois), 2 sem `VV_WORKBENCH_RUN`, 2 sem as bibliotecas do construtor de pacotes, 1 sem ligações simbólicas e 1 sem `CINEMATIC_CC0_STAGING`. O par comparável é o das corridas com `VV_GODOT`, 443 contra 468, ou seja, mais 25 testes novos (depois do seguimento) (22 de proteção em `tests/test_m191_honesty.py` e 3 de painéis da Cinematic em `tests/test_cinematic_cli.py`).

Testes acrescentados:

- `tests/ui_requirements.test.mjs` (Node, 31 testes antes, 41 depois). Comportamentais, sobre funções puras: `safetyWording`/`verdictOfSafety`/`verdictOfRequirement`/`statusClassOf` (`held`), `noFailureSentence`, `missionTone`, `completionFacts`, `conditionsBrief` e `plumeLengthAt` (comprimento da pluma antes, no e depois do último ponto). Corrido contra as fontes de `bec7b3f` (ficheiro de testes novo, fontes antigas): os testes 1 a 3, que não dependem do que mudou, passam; o 4 falha com `actual: 'pass', expected: 'held'` e o `node` termina aí (o ficheiro não é um executor que continue depois da primeira falha, por isso os restantes não chegam a correr; as funções novas ficariam `undefined` na desestruturação).
- `tests/test_m191_honesty.py` (Python, 22): **só verificações estruturais** sobre o texto das fontes, porque os ficheiros que desenham DOM (`verification.js`, `compare.js`, `lab.js`, `scenes/ascent.js`, `scenes/rocket.js`, o CSS) não se podem carregar em Node nem se pode lançar a Studio. Verificam que cada consumidor de linhas de requisitos usa `verdictOfRequirement`/`statusClassOf`, que a cena usa `plumeLengthAt`, que os estilos `held` existem e não usam `--pass`, que as pílulas compactas não têm reticências e têm preenchimento de bloco, e que `completionFacts` está ligado ao texto de `record.rs`. Corridos contra as fontes de `bec7b3f`, falham todos. A renderização das pílulas (contagem de condições em lugar da lista) só foi medida no executável, antes das correções da revisão (ver abaixo); em Node só se testa `conditionsBrief`.
- `tests/test_cinematic_cli.py::HonestPanels` (3, precisam de `VV_GODOT`): frase do impacto do booster, leitura do fim da aterragem com e sem velocidades do verificador.
- Percursos anteriores da Studio, contra um executável construído deste ramo (cópia `vv-studio-m191-after.exe`, biblioteca e configuração em pastas temporárias; **o perfil WebView2 não foi redirecionado**, ver «Quebra do passo 4»): m15 48/48, ux 67/67 (sem Cinematic), ux2 90/90, m18 72/72, m17 Lab 34/34, m16 78/78, ui_smoke 80/80 (`journeys-after.txt`). Os de «ux» e Lab pararam primeiro com um erro de codificação da consola (seta em cp1252) e foram repetidos com `PYTHONIOENCODING=utf-8`.
- `docs/evidence/m19/honesty/capture.py` regista factos do DOM e capturas; `evaluate-before.txt` e `evaluate-after.txt` aplicam-lhes as mesmas 12 verificações: 9 falham na 0.18.1 (uma delas, «a pluma ainda se desenha pouco antes do contacto», falha só porque o ponto de leitura não existe nessa versão) e as 12 passam agora. Esta captura usou, ela sim, um perfil WebView2 temporário.

## Evidência antes e depois

`docs/evidence/m19/honesty/before/` e `after/` (capturas e `*-facts.json`). Todas as capturas da Studio vêm de um executável construído neste ramo (antes: a partir de `bec7b3f`, depois: deste ramo), não do instalado. As capturas da Cinematic vêm do próprio módulo Godot a desenhar os mesmos registos (`--shot`), não da janela aberta pela Studio.

| Defeito | Antes | Depois |
| --- | --- | --- |
| 1 e 7 | `before-1-safety-chip-1440x900.png` | `after-1-safety-chip-1440x900.png` |
| 4 | `before-2-plume-past-end-1440x900.png` | `after-2-plume-past-end-1440x900.png`, `after-2-plume-before-contact-1440x900.png` |
| 2 | `before-3-corridor-completion-1440x900.png` | `after-3-corridor-completion-1440x900.png` |
| 6 | `before-3-corridor-pills-1024x640.png` | `after-3-corridor-pills-1024x640.png` |
| 5 | `before-5-cinematic-landing-end.png` | `after-5-cinematic-landing-end.png` |
| 3 | `before-6-cinematic-ascent-end.png` | `after-6-cinematic-ascent-end.png` |

## Limitações

- Sem teste com pessoas e sem passagem por leitor de ecrã; o `held` neutro e as pílulas não foram avaliados quanto a contraste.
- Não foram corridos `m17_cinematic_journey.py`, `review_captures.py` nem `installed_spotcheck.py` (precisam do módulo Cinematic instalado ou de um executável instalado). A Cinematic só foi exercitada pelos testes de `--policy-dump` e por capturas do Godot.
- O `held` neutro foi visto em capturas da Library, do player (chips), da Compare (`after-1c`) e das pílulas de veredicto do Lab (`after-1d`). Não foram vistos no ecrã: o Flight console, a tabela de comparação do Lab com linhas de regras, a página Runs e a lista «Investigations» do Discover; para estes só há verificação por classes CSS e por testes de código.
- 39 testes Python que precisam do binário `vv-rocket` de `crates/vv-rocket` ficam ignorados com o comando do AGENTS.md, antes e depois.
- A pílula selecionada a 1024x640 ocupa quatro linhas (antes três) e o gráfico 2D perde alguns píxeis de altura; os percursos que medem a altura do gráfico e as sobreposições passaram (`ux2` 90/90).
- Não foi construído nem testado o instalador, nem a reversão. A Studio 0.18.1 instalada não foi lançada nem alterada, mas ver «Quebra do passo 4».
- Os percursos anteriores (m15, ux, ux2, m18, m17 Lab, m16, ui_smoke) não foram repetidos depois das correções da revisão nem do seguimento; só se repetiu o `capture.py` isolado, com 20 verificações.
- Nenhuma revisão foi feita por pessoas. As revisões independentes descritas em «Revisões independentes por agentes» foram feitas por agentes de IA.

## Seguimento da passagem de especialistas (F01 a F04, F06, F07, F10, F11)

Classificação na tabela, linhas 10 a 15; tudo o que se implementou é da classe (a) e não toca em Rust. Alterações: `SAFETY_SCOPE` junto do chip e removida do fim do cartão (`player.js`); `expectationGloss` por baixo dos textos de demonstração dos domínios (`compare.js`, `run.js`, `prepare.js`), só quando o texto fala de safe, unsafe ou safety, com a frase «"safe" here means only that no safety rule was broken, and "unsafe" that one was; requirements are separate verdicts.»; HUD com a classe `is-minor` só para o foguetão, para que «To goal» e «Confidence» fiquem à vista a 720 px ou menos (a legenda T/E/O/D também fica no terrestre; o HUD já tem `max-height` com deslocamento); «Evidence integrity» neutra em `discover.js` (lista, peça) e `provenance.js`; ressalva do Lab por cima do numeral «k/n seeds»; botão «Go to <instante>». Os resultados de testes das secções anteriores foram repetidos no fim. Testes: 6 novos em `tests/test_m191_honesty.py` (estruturais, como os anteriores) e 1 em Node para as duas frases. Capturas isoladas (identificador `org.vvlab.studio.m191review`, perfil, biblioteca e configuração temporários; listagem de `%LOCALAPPDATA%\org.vvlab.studio`, `%APPDATA%\org.vvlab.studio`, biblioteca e Godot idêntica antes e depois): `after-1e-compare-banner`, `after-1f-replay-integrity` e as de HUD a 1024x640; `capture.py` tem agora 20 verificações (todas passam; 17 falham nos factos da 0.18.1). Ficaram só com testes estruturais, sem captura: a lista «Investigations» e as peças do Discover (exigem uma investigação guardada) e a ressalva do Lab (exige correr sementes).

## Correções da revisão independente

Aplicadas depois da revisão (veredicto «accept with fixes»): linhas de segurança neutras em todos os consumidores, testes comportamentais onde são possíveis, tom do chip «Mission» a partir dos estados, frase de «sem falhas» com categoria, preenchimento de bloco e `position: relative` nas pílulas (para o anel de foco não ser cortado pela linha deslocável), `completionFacts` documentado e frase do booster restringida ao verificado. Por regra nova da coordenação, os percursos anteriores (m15, ux, ux2, m18, m17 Lab, m16, ui_smoke) não foram repetidos; os resultados referidos acima são de antes destas correções. As capturas de `after/` e as 15 verificações de `capture.py` foram repetidas depois das correções, com um executável construído com outro identificador (`org.vvlab.studio.m191review`, por `TAURI_CONFIG`), biblioteca, configuração e perfil WebView2 temporários. A listagem recursiva (datas e tamanhos) de `%LOCALAPPDATA%\org.vvlab.studio`, `%APPDATA%\org.vvlab.studio`, da biblioteca em Documentos e de `app_userdata` do Godot ficou idêntica antes e depois (`app-data-isolation.txt`). Novas capturas: `after-1b-analyse-safety-rows`, `after-1c-compare-safety-rows` e `after-1d-lab-verdict-pills`; as 15 verificações passam (12 falham nos factos da 0.18.1). A tabela de comparação do Lab com linhas de regras (células `st-held`) exige executar uma experiência e continua coberta só por testes estruturais; o anel de foco das pílulas não foi visto.

## Revisões independentes por agentes

Foram feitas três rondas de revisão independente por agentes (revisão de agente, não revisão humana): a revisão do ramo, a revisão dos commits de seguimento e a das correções finais menores. Os relatórios das duas primeiras estão em `docs/evidence/m19/reviews/` (`01-independent-review-of-m19-1-honesty-branch.md`, `02-review-m19-1-follow-up-commits.md`), ambas com o veredicto «accept with fixes»; o relatório da terceira ronda não está nessa pasta. As correções da revisão e do seguimento foram, portanto, revistas por agentes. Continuam por fazer a revisão por pessoas e a verificação visual listada em «Limitações».

## Quebra do passo 4

**Factos.** Várias suítes de percursos anteriores da Studio (m15, ux, ux2, m18, m17 Lab, m16 e ui_smoke; sete, ver `journeys-after.txt`) correram, ao longo de cerca de seis minutos, contra um executável construído deste ramo. Criam a sua própria biblioteca e configuração temporárias, mas não redirecionam o perfil do WebView2. O executável tem o mesmo identificador (`org.vvlab.studio`) que a Studio instalada, por isso o WebView2 escreveu no perfil completo da instalação, a pasta de dados de utilizador `%LOCALAPPDATA%\org.vvlab.studio\EBWebView`. A escrita não se limitou a caches.

**O que se sabe.**

- A listagem mais antiga que existe (`appdata-before.txt`, fora do repositório) foi tirada **depois** da quebra. Não existe nenhuma listagem anterior.
- Dos 1302 registos dessa listagem, 203 têm data de 23/11 entre as 18:55 e as 19:01, incluindo `History`, `Preferences`, `Secure Preferences`, `Local State`, `Web Data`, `Local Storage\leveldb`, `Session Storage`, `Network` e `Code Cache\js`.
- Uma inspeção só de leitura de `Local Storage\leveldb\000003.log` (2671 bytes) mostra apenas registos de metadados internos do Chromium (`VERSION`) e nenhuma chave da aplicação. O código-fonte da interface da 0.18.1 não tem chamadas a armazenamento web.
- Não foram tocados: os ficheiros do programa, `modules` (15/11/2026 08:10:01), `logs` (02/11/2026 22:41:06), as preferências da Studio em `%APPDATA%\org.vvlab.studio` (06/11/2026 20:00:43), a pasta de dados do Godot (`app_userdata`, 04/11/2026) e a biblioteca de investigação em Documentos (`VVLAB_LIBRARY` apontou sempre para uma pasta temporária). A captura de `capture.py` e as capturas do Godot não escreveram aí.

**Julgamento (não verificado).** O impacto provável é nulo para os dados da Studio, porque a interface não guarda nada em armazenamento web e as preferências e a biblioteca ficam noutros sítios. É uma inferência a partir do que se leu, não uma medição.

**Decisão do responsável.** Como não há listagem anterior à quebra, repor o estado anterior é impossível. As opções são apagar `EBWebView` (o WebView2 volta a criá-lo no próximo arranque) ou deixá-lo como está. Nada foi apagado nem reposto.

**Quem repetir os percursos** deve definir antes `WEBVIEW2_USER_DATA_FOLDER` para uma pasta temporária (o `capture.py` e as capturas de revisão já o fazem, com o identificador `org.vvlab.studio.m191review`).

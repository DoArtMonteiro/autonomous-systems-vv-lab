# M19.1: correções de honestidade científica da Studio

Estado: concluído localmente no ramo `fix/m19.1-honesty`, criado a partir de `main` em `bec7b3f` (origem da Studio 0.18.1 instalada). Nada foi enviado, integrado nem instalado. As alterações corrigem o que a Studio mostra. Nenhuma simulação, registo, evidência guardada ou hash canónico mudou (ver «Conjunto que não pode mudar»).

## Defeitos de partida e classificação

Classes: (a) só texto ou apresentação da interface; (b) altera evidência registada ou hashes de execução (por exemplo, texto em `evidence.rs` muda o hash do anfitrião e os identificadores das corridas); (c) pode influenciar o comportamento da simulação. Regras do mandato: (a) implementa-se; (b) só se não tocar em evidência protegida, linhas de base ou hashes canónicos, senão propõe-se; (c) nunca se implementa. Esta tabela foi escrita antes da implementação.

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

Nenhum defeito é da classe (c). Nenhuma alteração toca em `crates/`, `src/`, `exec/`, `scenarios/` nem em código Rust.

## O que mudou

1. **Chip de segurança neutro.** `safetyWording` devolve agora o veredicto `held` em vez de `pass` quando nenhuma regra falhou; `verdictOfSafety('safe')` também. `held` tem um escudo contornado e tons neutros (chips, vidro do Flight console, bloco de veredicto, tabela da Library, matriz da Compare, Lab). O verde fica só para um requisito cumprido e para o resultado da missão. O texto não mudou, por isso o teste dos termos (`tests/test_honesty_wording.py`) e os percursos anteriores continuam válidos. Decisão tomada: o chip é neutro sempre, não só ao lado de requisitos falhados, porque «nenhuma regra falhou» é uma afirmação delimitada (regras listadas pelo domínio, estado verdadeiro) e nunca o resultado da missão.
2. **Cláusula de `mission_completion`.** O registo diz só «incomplete; 1 of 1 waypoint(s) reached; 0 mm from the goal at the end». A interface passou a mostrar sob os chips do resultado: «Recorded: 1 of 1 waypoint reached, 0 mm from the goal at the end, outcome incomplete. The record does not say which part of "Mission completion" failed (it expects ...). Reaching the goal is not the same as completing the mission.» (`completionFacts` em `requirements.js`, lido do texto observado que o anfitrião escreve; um teste Python compara-o com `record.rs`). A linha «To goal» do Flight console e do cartão de leitura diz que a distância não indica se a missão ficou completa.
3. **Frase de impacto na subida.** O painel de resultado da Cinematic de uma subida acrescenta, para cada entidade que termina em impacto: «Booster impact: its recorded path ends at the surface (t 617.2 s). The impact itself is not modelled and nothing is drawn for it: no landing burn, break-up or recovery is simulated, and the booster is not drawn after its last sample.»
4. **Pluma depois do contacto.** Depois da última amostra de uma corrida (o contacto, numa aterragem) a reprodução de uma corrida mais longa continuava a desenhar a pluma da última amostra. O registo não diz nada sobre o motor depois dessa amostra, por isso a pluma deixa de ser desenhada; antes e no instante do contacto desenha-se como antes. Verificado no executável (`plumeM` 0 depois do fim e maior que 0 pouco antes).
5. **Velocidade no contacto.** A leitura da Cinematic no fim de uma aterragem já não apresenta a velocidade da última amostra como se fosse a do contacto. Quando o registo traz as velocidades do verificador no instante do contacto (`touchdown_vertical_speed`, `touchdown_horizontal_speed`) mostra-as e diz que são do verificador; senão diz «the record has no contact speed» e nomeia o número como o da última amostra. «-0.0 m» passa a «0.0 m».
6. **Pílulas a 1024x640.** As pílulas não selecionadas mostram o nome completo, o identificador curto e uma contagem exata das condições («2 conditions», «default conditions»); a lista completa fica no nome acessível (texto visualmente oculto, não `display: none`) e no `title`. Já não há reticências em pílulas; se os nomes forem mais largos do que a janela, a linha desloca-se.
7. **«Every requirement ... met».** Vem agora de `noFailureSentence`: só diz «met» quando todas as linhas passaram; com linhas não avaliadas nomeia-as e fica neutra.
8. **Chip «Mission».** Fica neutro quando o registo não lista requisitos de missão.

## O que ficou por alterar e porquê

- **Registo do domínio terrestre (defeito 2, classe b).** Dizer qual a cláusula falhada exige que `record.rs` o escreva. Isso muda o hash do anfitrião terrestre e portanto os identificadores de todas as corridas terrestres, e mexe no domínio que o programa M19 marca como o mais sensível. Proposta: acrescentar ao texto `observed`/`explanation` de `mission_completion` a cláusula falhada (aqui: nenhuma conclusão declarada e confirmada no horizonte, com todos os pontos alcançados), com o impacto nos hashes declarado antes e confirmado depois. A interface já não depende disso.
- **Frases `expectation` das demonstrações (defeito 9, classe b).** Substituir «safe» por «no safety rule broken» em `demos.rs` e `catalog.rs` muda o hash dos anfitriões do foguetão e terrestre. Não foi feito; a Compare continua a atribuí-las ao domínio.
- `passes()` do Lab conta «success e safe» como cumprido. Um registo `safe` com a classe `not_evaluated` só existe quando o veículo nunca voou, e então o resultado não é `success`. Não há caso alcançável; não foi alterado.
- A pluma do instante do contacto (a última amostra) mantém-se: é o estado registado nesse instante.
- A cena Cinematic não foi tocada além dos textos. O pacote do módulo (zip e versão do manifesto) não foi reconstruído; qualquer lançamento exige reconstruí-lo e subir a versão do módulo.
- Contraste, tecnologias de apoio e uso por pessoas continuam por verificar (o `held` neutro usa os mesmos tokens de cor dos outros chips neutros).

## Conjunto que não pode mudar

Capturado antes de qualquer alteração e recapturado no fim com `docs/evidence/m19/honesty/hash_set.py`. Resultado em `hash-comparison.json`: 542 valores comparados, 542 idênticos, 0 diferentes.

- `source_sha256` de `vv-rocket` (`295a45b2...`, 20 ficheiros) e de `vv-ascent` (`b11d38f3...`, 12 ficheiros), recalculados com a lista e a normalização de fim de linha das funções `source_sha256()`.
- SHA-256 dos 266 ficheiros versionados em `docs/evidence/` e `exec/claims/`, dos cenários M1 (incluindo `sha256.json` e `canonical-seed-42.json`) e de todos os fixtures e golden dos testes.
- SHA-256 dos anfitriões de domínio, de `vv-lab` e de `vv-exec` construídos por `desktop/build.ps1 -StageOnly`, depois de os reconstruir.
- Registo e ficheiros nativos de cada execução de demonstração dos quatro domínios (25 execuções, sementes de demonstração do produto, nenhuma semente protegida) e os artefactos M1 da missão básica com a semente 42.

## Verificação

Comandos de `AGENTS.md`, na raiz do repositório, antes e depois (resultados guardados em `docs/evidence/m19/honesty/verification-before/` para o antes):

| Comando | Antes (`bec7b3f`) | Depois |
| --- | --- | --- |
| `cargo fmt --check` | sem diferenças | sem diferenças |
| `cargo clippy --all-targets -- -D warnings` | sem avisos | sem avisos |
| `cargo test` | 13 suítes, 138 aprovados, 0 falhados | 13 suítes, 138 aprovados, 0 falhados |
| `python -m unittest discover -s tests -p "test_*.py"` | 441 testes OK (135 ignorados) | 459 testes OK (92 ignorados) |
| o mesmo com `VV_GODOT` (Godot 4.7.2) | 443 testes OK (45 ignorados) | 459 testes OK (45 ignorados) |
| `cargo build --release` | concluído | concluído |
| `python scripts/run_campaign.py --seeds 42,1337,2026 --output-root runs/campaign` | 87 casos, 324 invocações, aprovada | 87 casos, 324 invocações, aprovada |
| `cargo fmt --check`, `cargo clippy ...`, `cargo test` em `desktop/` | 24 suítes, 168 aprovados (com a raiz, 37 suítes e 306 testes, como na 0.18.1); fmt e clippy limpos | idêntico |

A diferença de testes ignorados sem `VV_GODOT` (135 contra 92) vem de testes que só são recolhidos quando existe `target/release`, que na primeira corrida ainda não existia; o par comparável é o das corridas com `VV_GODOT`, 443 contra 459, ou seja, mais 16 testes novos (13 de proteção em `tests/test_m191_honesty.py` e 3 de painéis da Cinematic em `tests/test_cinematic_cli.py`).

Testes acrescentados:

- `tests/ui_requirements.test.mjs` (Node, 31 testes antes, 37 depois): veredicto `held`, frase de «sem falhas», `completionFacts`, `conditionsBrief`. Corridos contra as fontes de `bec7b3f`, falham logo no primeiro (`actual: 'pass', expected: 'held'`).
- `tests/test_m191_honesty.py` (Python, 13): chip neutro e estilos, sentenças «met» partilhadas, chip da missão, pluma, ligação ao texto que o anfitrião terrestre escreve, pílulas sem reticências. Corridos contra as fontes de `bec7b3f`, falham 13 em 13.
- `tests/test_cinematic_cli.py::HonestPanels` (3, precisam de `VV_GODOT`): frase do impacto do booster, leitura do fim da aterragem com e sem velocidades do verificador.
- Percursos anteriores da Studio, contra um executável construído deste ramo (cópia `vv-studio-m191-after.exe`, biblioteca, configuração e perfil WebView2 em pastas temporárias): m15 48/48, ux 67/67 (sem Cinematic), ux2 90/90, m18 72/72, m17 Lab 34/34, m16 78/78, ui_smoke 80/80 (`journeys-after.txt`). Os de «ux» e Lab pararam primeiro com um erro de codificação da consola (seta em cp1252) e foram repetidos com `PYTHONIOENCODING=utf-8`.
- `docs/evidence/m19/honesty/capture.py` regista factos do DOM e capturas; `evaluate-before.txt` e `evaluate-after.txt` aplicam-lhe as mesmas 11 verificações: 8 falham na 0.18.1 e 11 passam agora.

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
- A pílula selecionada a 1024x640 ocupa quatro linhas (antes três) e o gráfico 2D perde alguns píxeis de altura; os percursos que medem a altura do gráfico e as sobreposições passaram (`ux2` 90/90).
- Não foi construído nem testado o instalador, nem a reversão. A Studio 0.18.1 instalada não foi lançada nem alterada: as pastas de dados da instalação mantiveram a data da última escrita anterior à sessão.
- A revisão de UX independente das correções não foi feita.

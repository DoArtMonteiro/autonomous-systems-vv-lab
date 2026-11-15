# Studio 0.18.1 instalado: verificação no Windows

Esta pasta guarda a verificação do V&V Lab Studio 0.18.1 **instalado** (instalador NSIS, execução silenciosa por cima do 0.17.0), não do executável da pasta de compilação. Os percursos correram contra `%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe`, com o módulo Cinematic 0.2.7 instalado pelo código de instalação do próprio Studio. Nenhuma captura do ambiente de trabalho foi guardada: as imagens da pasta `cinematic/` foram desenhadas pelo módulo (`--shot`) ou são a janela do próprio módulo (`boot-splash-window.png`, da 0.2.1; a imagem de arranque não mudou), e só contêm a cena ou a imagem de arranque.

Em relação ao `main` (`66b30ca`) a versão 0.18.1 muda o número de versão do Studio, acrescenta o estado «Opening the Cinematic View...» e, depois da revisão independente das capturas do 0.18.1, passagens de correções de interface (secções «Passagem de correções de interface», «Segunda passagem», «Terceira passagem», «Quarta passagem» e «Quinta passagem»). O módulo passa de 0.2.0 a 0.2.7. Os testes mudaram: `m17_cinematic_journey.py` espera pelo primeiro frame e verifica o estado novo, `installed_spotcheck.py` automatiza o percurso de utilizador e `ux_journeys.py` verifica as correções.

## Máquina

AMD Ryzen 7 7800X3D (8 núcleos, 16 fios), 31,7 GB de RAM, AMD Radeon RX 7700 XT (controlador 32.0.31041.3013), Windows 11 Pro compilação 26300, WebView2 156.0.4314.58, Godot 4.7.2-stable, Python 3.14.6. O Microsoft Defender ficou ativo durante todo o trabalho e não foi alterado. Os números são desta máquina e não descrevem outras.

## Artefactos

| Artefacto | Tamanho | SHA-256 |
| --- | --- | --- |
| `VV Lab Studio_0.18.1_x64-setup.exe` (o instalado e verificado) | 42 455 962 bytes | `9ccb649818882decb77636c0961bb0857bc1f2035605738dd2b9e8b7f2a7b3c2` |
| `vv-cinematic-0.2.7.zip` (78 ficheiros, 449 770 502 bytes em disco) | 345 002 218 bytes | `4d0a0715a15fadba5eda364a6ab5a56c6da9aebff443cfc59538031d0b1d3afe` |

O instalador foi construído com `desktop/build.ps1` (compilação de lançamento completa): **código de saída 0**, capturado pelo invólucro que o executou (`BUILD EXIT 0`). Como o 0.18.1 ainda não foi publicado fora deste PC, o número de versão ficou e os instaladores anteriores deste número foram guardados na pasta de recuperação com nomes que dizem o que são: `...-setup-prebuild.exe` (a primeira versão), `...-setup-before-ux-pass.exe` (com o estado «Opening...», sem correções de interface), `...-setup-ux-pass-1.exe` a `-ux-pass-3.exe` (as três iterações da primeira passagem de interface), `...-setup-ux-round-1.exe` (o instalador final da primeira passagem, `e57f0af4...`, que a revisão de código e de interface avaliou) `...-setup-ux-round-2.exe` (a primeira iteração da segunda passagem, `c879688c...`, que ainda falhava a verificação a 820 px), `...-setup-ux-round-3.exe` (o instalador final da segunda passagem, `75eb3236...`, que a terceira revisão avaliou), `...-setup-ux-round-3b.exe` (a primeira iteração da terceira passagem, `b9927fb4...`, que ainda deixava a página Runs com deslocamento horizontal a 820 px), `...-setup-ux-round-4.exe` (o instalador final da terceira passagem, `29a4d131...`, que a quarta revisão avaliou) , `...-setup-ux-round-4b.exe` (a primeira iteração da quarta passagem, `9d4cb6c6...`, em que o gráfico 2D do corredor ainda ficava por baixo das pílulas a 1024x640 e 820 px) , `...-setup-ux-round-4c.exe` (a segunda iteração da quarta passagem, `d54b8e19...`, com o título de missão «Stalled but safe» e a frase «a nominal run» ainda por mudar) e `...-setup-ux-round-5.exe` (o instalador final da quarta passagem, `b7f21c83...`, que a quinta revisão avaliou) e `...-setup-ux-round-5b.exe` (a primeira iteração da quinta passagem, `e9288519...`, em que o gráfico 2D do corredor tinha 135 px a 820x900 e a página do leitor deslocava-se para o lado) e `...-setup-ux-round-5c.exe` (a segunda iteração da quinta passagem, `bda261a4...`, em que o seed da página Runs quebrava em duas linhas a 820 px e a coluna da data cortava a 1024 px). `SHA256SUMS.txt` (esta pasta) resume os hashes relevantes; a lista completa está na pasta de recuperação do proprietário, e os vinte e um ficheiros ali foram verificados contra ela.

## Instalação

- Antes da primeira instalação, o hash do instalador de recuperação 0.17.0 foi confirmado contra o `SHA256SUMS.txt`.
- O 0.18.1 foi instalado por cima do 0.17.0 e, depois, várias vezes por cima de si próprio à medida que o instalador mudou (dezasseis instaladores até ao final), sempre com `/S`: código de saída 0; a chave `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\VV Lab Studio` ficou com `DisplayVersion` 0.18.1 e o executável instalado declara a versão 0.18.1.
- Biblioteca do utilizador (`Documentos\VV Lab Library`): 11 corridas antes e depois de todas as instalações e de todos os percursos, mesma lista de identificadores, e o SHA-256 da lista ordenada dos 89 ficheiros da biblioteca é idêntico ao de antes da primeira instalação. Na quarta passagem o mesmo cálculo (SHA-256 da lista ordenada de «hash do ficheiro e caminho relativo» dos 89 ficheiros) deu `9b40386432e7786c681b274f7667b2db26bfbe58e9add8e6d798ecdefc6539c1` antes da primeira instalação da passagem e o mesmo valor depois da última instalação e de todos os percursos, com 11 corridas; na quinta passagem o valor foi o mesmo antes da instalação e depois dos percursos.
- Módulo Cinematic: instalado pelo teste opcional `real_module_zip_installs_when_given` de `desktop/studio/src/modules.rs` (`VV_CINEMATIC_ZIP`, `VV_CINEMATIC_INSTALL_TO` a apontar para a pasta real de módulos), porque o diálogo nativo não é automatizável. Substituiu as versões anteriores; o Studio instalado lê `installed: true, verified: true, version: 0.2.7`.
- O percurso `m17_cinematic_journey.py` desinstala o módulo no fim; por isso o módulo é reinstalado da mesma forma depois dele. No fim de tudo, o módulo 0.2.7 está instalado e verificado e não ficou nenhum processo do Studio nem do Godot.

## Percursos contra o executável instalado (instalador final, módulo 0.2.7)

| Percurso | Resultado | Registo |
| --- | --- | --- |
| `m15_journeys.py` | 48/48 | `m15-journeys.txt` |
| `m16_journeys.py` | 78/78 | `m16-journeys.txt` |
| `m17_lab_journeys.py` (porta 9273) | 34/34 | `m17-lab-journeys.txt` |
| `m17_cinematic_journey.py --preinstalled` | 11/11 | `m17-cinematic-journey.txt` |
| `m18_journeys.py` | 72/72 | `m18-journeys.txt`, `m18-numbers.json` |
| `installed_spotcheck.py` | 44/44 | `installed-spotcheck.txt`, `installed-spotcheck-facts.json` |
| `ux_journeys.py` (primeira passagem) | 81/81 | `ux-journeys.txt`, `ux-facts.json` |
| `ux2_journeys.py` (segunda a quinta passagens) | 84/84 | `ux2-journeys.txt`, `ux2-facts.json` |
| `review_captures.py` (quarta passagem, novo) | 37/37 | `review-captures.txt` |
| `ui_smoke.py` (o teste do CI, contra o instalado) | 80/80 | `ui-smoke.txt` |

Todos usam bibliotecas e configuração temporárias (`VVLAB_LIBRARY`, `VVLAB_CONFIG`), por isso não tocam na biblioteca do utilizador. Os caminhos temporários aparecem nos registos como `<temporary folder>`. Os dez correram numa só execução no instalador final; o guião reinstala o módulo no início e no fim (o percurso `m17_cinematic` desinstala-o). As execuções anteriores da segunda passagem tiveram falhas verdadeiras que levaram a duas reconstruções (ver «Segunda passagem»).

**Uma falha encontrada e corrigida (teste, não produto).** Na primeira execução com o módulo 0.2.0, `m17_cinematic_journey.py` deu 8/9: a verificação «o módulo desenhou o primeiro frame» falhou porque o percurso lia o registo do Godot após uma espera fixa de 12 s e o primeiro frame chega 12 a 16 s depois do clique. O processo estava a arrancar com Direct3D 12 sem erros; o percurso passou a esperar pela linha `FIRST_FRAME` (até 90 s) e a ignorar registos anteriores ao clique.

## Segunda passagem (revisão de código e de interface)

Uma revisão de código independente e uma segunda revisão das capturas (veredicto «boa, com lacunas», sem bloqueio) pediram o que segue. Os testes novos falharam antes das correções contra o instalador anterior (`ux2_journeys.py`: 7 de 23 verificações passavam) e passam depois.

**Revisão de código.**

1. `safetyWording` conta só as regras avaliadas, vê as regras quebradas antes do ramo «não avaliado» (uma regra quebrada nunca fica neutra) e escreve «No safety rule broken (C of T checked; S not evaluated)» quando há regras não avaliadas; sem regras avaliadas diz «Safety not evaluated».
2. Teste de unidade em Node (`tests/ui_requirements.test.mjs`, corrido por `tests/test_ui_requirements.py` no `unittest`, 14 casos: insegura com regras quebradas, insegura sem linhas, quebrada com classe «não avaliada», segura com linhas não avaliadas, todas não avaliadas, sem linhas, nota genérica, frase das falhas, inclinação em graus, leitura publicada, quatro algarismos, cabeçalho). O `ux2_journeys.py` verifica um caso inseguro real (a missão «corridor»: «k of N safety rules broken», cor de insegurança, e «A rule broken» na página Runs).
3. `indexNumbers` corre uma vez em `loadRecord` (`store.js`), por isso todas as vistas (leitor, Analyse, Compare, Lab) leem os números publicados; o cartão do leitor chama-o também.
4. Semente: o Rust (`modules.rs`) deixa de fora uma semente com mais de 18 algarismos; o módulo aceita 18; a leitura de reserva do registo mostra a semente só se for um inteiro exato abaixo de 2^53. Testes em Rust (`display_arguments_...`) e Python (`tests/test_cinematic_cli.py`).
5. Nota de segurança genérica: «Mission requirements are judged separately...», sem falar de aterragens.
6. Controlos de direção de texto (U+202A a U+202E, U+2066 a U+2069) são removidos nos rótulos, no Rust e no módulo (testados).

**Revisão de interface (o que foi feito).** Consola de voo: a frase de fim sobre um fundo, sem transparência, e as etiquetas das corridas descem abaixo dela; a fila de câmaras sai do caminho da linha do tempo a 1024x640. Leitor a 1024x640: objetivo dobrado numa janela baixa, e cada etiqueta de corrida mostra «k of N requirements failed · No safety rule broken (5 checked)» depois de mostrar o resultado (não antes); a 820 px a fila de câmaras fica à esquerda, acima das etiquetas, e o cartão de leituras rola em vez de ser tapado. Analyse: «2 mission requirements failed: Vertical speed at contact, Horizontal speed at contact.», sem cortes na frase do resultado, na linha de segurança e na validade do modelo, e a inclinação em graus (derivada do cosseno gravado, dito na dica). Runs: título e coluna «Safety rules» («None broken» / «A rule broken», sem contagem: o resumo da página não a tem), coluna «Failed» com nomes legíveis. Lab: tabela de resultados com colunas mais largas, valor e unidade sem quebra, margem numa só linha. Compare: uma etiqueta por corrida (a do Lab ou do leitor: «Baseline» e o que mudou) nos cabeçalhos das colunas, cartões «1 of 6 requirements failed», linhas que mudam de veredicto num grupo à cabeça. Nomes: «Runs» na navegação e no título, «Open the missions», «Show all findings now» (antes «Analysis mode»), «Open Cinematic View», «Run:» à frente do seletor. Home: o bloco de estatísticas já não sobrepõe «ENVIRONMENTS» e «DOMAINS». O chip «Reference case» passou a neutro. Módulo 0.2.5: legendas em palavras simples, controlos rotulados (Speed, Time, Quality, Camera), um só controlo de qualidade («Quality (auto)»), nomes de câmara do Studio, botão «Show result». Capturas claras (tema claro) de Home, hangar, Runs, Compare, Lab e Home a 820 px estão no conjunto de revisão.

**Não feito, com razão.**

- «Replay» para abrir uma corrida gravada: a palavra já nomeia, em Analyse, a ação de recomputar e verificar (o botão de repetição da plataforma); usá-la para duas coisas criaria a ambiguidade que a revisão apontou. Fica por decidir qual das duas muda de nome.
- A coluna «Safety rules» da página Runs sem contagem «(C checked)»: o resumo da lista não a traz e carregar cada registo para a calcular não foi feito; a contagem aparece em todas as vistas que têm o registo.
- Uma só etiqueta por corrida também na página Runs e na vista Analyse: a página Runs mostra o rótulo guardado da corrida (não reescrito) e a vista Analyse abre sem o rótulo do leitor.
- «Dry mass (multiplier)» e «Vehicle design · 4 parameters» (textos do catálogo do domínio, fora do âmbito pedido), «smaller margin» nas linhas ainda aprovadas, «below the surface: suborbital» no cabeçalho da subida, formato de tempo único, legenda dos símbolos da linha do tempo.
- A vista geoespacial e a faixa preta de El Arenosillo (corrigi o ajuste da imagem do cartão com `object-fit: cover`, mas não verifiquei a imagem desse pacote em separado).

**A tração de 438,3 kN a 57,16 %.** Lida do registo: a razão entre `thrust_n` e `act_throttle` é constante em todas as amostras (`ux2-facts.json`: 766,792 kN, dispersão relativa 3e-16), por isso o ecrã não mistura dois instantes: mostra 57,16 % do máximo que o próprio registo usa, 766,79 kN, que é 0,89 % acima dos 760 kN do modelo de partida. O mesmo fator (1,00894) aparece no andar de 22 t (852,55 kN contra 845 kN) com a mesma semente, o que é coerente com uma dispersão de empuxo do domínio nessa semente; não li o código do domínio para o confirmar. Nada a corrigir no ecrã.

## Terceira passagem (a última antes da integração)

**Obrigatório e de revisão (feito, com verificação no instalador).**

- **B1** Vista geoespacial a 1024x640 e 820 px: as etiquetas das corridas empilham-se e quebram linha, e nenhuma é cortada a meio de uma cláusula («failed · safety» já não aparece cortado). `ux2_journeys.py` verifica, no leitor de engenharia, no geoespacial e na consola de voo, a 1024x640 e a 820 px, que o texto de cada etiqueta cabe na sua caixa e na janela.
- **R1** O teste Node usa `fileURLToPath`; corre numa cópia em «v&v lab» (caminho com espaço e `&`): 14 testes passam, e o `unittest` também.
- **R2** As verificações de sobreposição devolvem quantas vezes cada par foi visto; um par que não está na página é uma falha (a consola de voo já não conta o `.mc-strip`, que não aparece).
- **R3** O teste dos controlos de direção lê o rótulo limpo («abc», «xy», semente 42) da linha `POLICY` do módulo, em vez de só o código de saída.
- **R4** e **R5** O estado vazio do Compare diz «Runs»; a dica da coluna de segurança da página Runs usa a nota genérica.
- **R6** Nenhuma vista escreve «all 0 requirements met» (a frase só existe quando há requisitos de missão).

**Estados e contagens.**

- **F1** «2 of 6 requirements failed · 5 of 5 safety rules held» (falhas primeiro; «held» = avaliadas e não quebradas) nas etiquetas do leitor, nos cartões do Compare e no Lab, onde a frase «judged separately» também aparece.
- **F2** Página Runs: «k of N safety rules broken» a negrito, com N das regras de segurança do catálogo; o teste compara o número com o registo real (o caso «corridor»: 1 de 4, igual ao registo) e a célula «Failed» separa «Safety:» de «Requirements:». Sem contagem «(N checked)» nas corridas seguras: o resumo da lista não a traz.
- **F3** Consola de voo: os chips «Your experiment» e «Exploratory» estão sob o título, que quebra linha em vez de cortar o qualificador.
- **F4** A legenda da consola diz «number = findings at this instant».
- **F5** A página Runs e a vista Analyse mostram para «Experiment from <id>» a etiqueta calculada que o leitor dá a uma corrida nova («Engine thrust 0.7 × (from cad03fec2f)»); a etiqueta guardada não foi reescrita e aparece na dica.
- **F6** No Lab da subida, os requisitos compostos ocupam uma linha própria; o seletor do controlador ocupa a largura toda.
- **F7** As margens que o Studio calcula (limite menos valor, ou cosseno em ângulo) levam o selo D e uma nota de rodapé no Lab e no Compare.
- **F8** Compare: mudanças de veredicto, «falhados em todas as corridas», regras de segurança, o resto; o painel da tabela tem altura mínima de meia janela (regra de CSS, sem teste); a tabela cabe no painel (colunas fixas, o texto quebra; verificado).
- **F9** Analyse: requisitos falhados primeiro; limite e pior valor da inclinação em graus com o cosseno gravado entre parênteses; os números das explicações do domínio com quatro algarismos (o texto completo na dica); legendas dos gráficos sem corte (regra de CSS, vista nas capturas, sem teste).
- **F10** A legenda do leitor tem fundo (CSS, vista nas capturas).
- **F11** «Safety rules» na lista de requisitos (o id fica em segundo plano) e «Clean | Technical» na consola.
- **F12 (em parte)** Módulo 0.2.5: «this view computes nothing. It draws the recorded run», a duração na leitura do tempo, um botão para esconder ou mostrar a legenda do que é desenhado.
- **F13** (vista nas capturas) O chip «Reference case» do hangar não é cortado e o cartão de referência diz «Simulated reference case, not a real vehicle.».
- **F14** Runs com o painel de detalhe: a 1440x900 não há deslocamento horizontal da página nem da tabela; a 820 px o painel passa para baixo da tabela (verificado em `ux2_journeys.py`).
- **F15** A segunda corrida deixou de ser âmbar (o âmbar é só das falhas).

**Não feito (fica como lista de pendentes), com razão.**

- F12: os nomes das opções de qualidade («Auto (now High)/High/Medium/Low») e manter o rótulo «Quality» fixo: exige mudar a lógica de perfis do módulo; o rótulo continua «Quality (auto)».
- F11: «Compare» como nome único das ações de comparação e a auditoria de «failed» para requisitos e «broken» para regras de segurança em todas as vistas (feito onde há contagens, não em todo o texto).
- F9: os rótulos dos raios (R5, S2) desenhados no gráfico.
- F2: «None broken (N checked)» na página Runs.
- F8: não há verificação automática da altura do painel da tabela do Compare.
- Pequenos: «contact dynamics not modelled» no cartão (o texto «impact not modelled» mantém-se), quatro colunas fixas nas estatísticas da Home (agora automáticas: quatro quando cabem), «Choose the backdrop for the replay.», «Largest margin change», a costura de fundo da página Runs.
- A 820 px a tabela do Lab continua a rolar na horizontal dentro do seu painel (a coluna «Margin change» fica fora da vista até rolar); nenhuma célula parte um número.
- Na página Runs a 1440x900 com o painel de detalhe e linhas muito longas, a coluna «Created (UTC)» pode ficar um pouco cortada pelo deslocamento interno da tabela.

**Capturas.** `D:\vvwt\shots-0.18.1-ux3\review\` (não no repositório; README próprio): Lab, Compare, Analyse e Runs a 1440x900, 1024x640 e 820x900; leitor de engenharia (1440 «end», 1024, 820), geoespacial e consola de voo nos três tamanhos; o estado final da corrida de 60 m/s; a missão «corridor» no leitor (uma regra de segurança quebrada), em Runs, em Analyse e em Compare; o painel de resultado da Cinematic View (da corrida de referência registada, com argumentos «Reference landing / 22 t landing stage» escritos para a captura); tema claro do leitor, de Analyse, de Ambientes, Home, hangar, Runs, Compare e Lab.

## Quarta passagem (honestidade das palavras e disposição)

A revisão da terceira passagem encontrou dois bloqueios de honestidade e um defeito de código. O painel de resultado do módulo Cinematic escrevia «Safety: safe» para uma corrida cujos requisitos falharam; a identidade de uma corrida dizia «no injected fault» com ruído de GPS configurado; e a contagem «all N requirements met» não olhava para as linhas não avaliadas. Em vez de corrigir cada frase, a passagem corrigiu as classes: uma só maneira de dizer a segurança, uma só função que dá nome a uma corrida, uma só leitura da contagem de requisitos, e um teste que falha se uma delas for contornada. Nenhum código de simulação, de domínio, de sementes ou de dados de corridas mudou; a única alteração na plataforma é `desktop/platform/src/evidence.rs` (o README do pacote de evidência), autorizada para esta passagem, sem tocar no esquema do registo, em `RunMeta` nem em `RunSummary`.

**Obrigatório (feito e verificado no instalador, salvo B1, que ficou em parte).**

- **B1, identidade de uma corrida (em parte).** `conditionsName` (`ui/js/model.js`) lista todos os parâmetros que não são os por omissão do catálogo e todas as falhas injetadas («GPS noise 1 mm · Arrival radius 250 mm»; «default conditions» só quando não há nenhum). Passou a ser usada nas páginas Runs (uma linha «Conditions» por corrida, lida do pedido do registo, em carregamento tardio), Compare (cartões e etiquetas), Analyse, leitor (uma linha por corrida), Lab, cartões de demonstração da página Prepare e etiqueta de procura da paleta de comandos (que não mostra «no fault» quando o resumo não traz parâmetros). O Compare diz o que as corridas partilham e em que só diferem («Both runs: GPS noise 1 mm; they differ only in Arrival radius.»; quando as corridas não têm nenhuma condição comum, «no non-default condition in common»). A identidade vem do pedido do registo, não de um campo novo do resumo. Falta uma só etiqueta de cabeçalho por corrida (ver «Decisões em aberto»): o que é igual em todas as superfícies é a linha «Conditions».
- **B2, o painel do módulo.** O painel do Cinematic (módulo 0.2.6) já não escreve «Safety: safe»: «Safety rules: none broken (5 checked, S1 to S5), judged on the true state; this does not mean the vehicle is safe.», ou «Safety rules: 1 of 5 broken (Climb under power).», com os requisitos que falharam antes («Requirements failed: ...») e a frase do próprio domínio citada por baixo («The record says: ...»). Está nas imagens `cinematic-panel-60ms-run.png` e `cinematic-panel-broken-rule-landing.png`, desenhadas pelo módulo instalado. A corrida do corredor é de um veículo terrestre, que o módulo não desenha; o painel da corrida com regra quebrada vem da missão `threshold-trade-off` (aterragem com S5 quebrada).
- **R1** `requirementWording` conta as três situações: «all N requirements met» só quando todas as linhas passam; senão «k of N requirements failed, n not evaluated, m met», com as falhas primeiro; as linhas de declaração do controlador não contam. `failureSentence` e o chip de missão do leitor seguem a mesma regra.
- **R2** A página Runs diz «k safety rules broken» e só escreve «de N» quando o resumo traz o número de regras avaliadas (não traz); um identificador desconhecido nunca é classificado como requisito (as linhas «Failed» agrupam «Safety rules:», «Requirements:», «Declarations:», pela categoria do próprio registo, lida em carregamento tardio).
- **R3** O teste Node tem 27 casos (eram 14): `requirementWording` (todos cumpridos, alguns falhados, alguns não avaliados, declarações), `statusLine`, `heldText`, `displayRunLabel`, `conditionsName`/`conditionsShared`, `marginDerived`, `headlineChange`, `shortText`.
- **R4** `shortText` só arredonda decimais com cinco ou mais algarismos significativos e nunca mexe em algarismos dentro de identificadores («R1_vertical_speed», «9e6edb2e», «v1.2.3»).

**Por classe (adenda da revisão estratégica).**

- O README do pacote de evidência (`evidence.rs`) já não escreve «Safety: safe»: «Safety rules: no safety rule broken (5 checked), judged on the true state.» e a linha do pedido lista todos os parâmetros e falhas do pedido. Limitação: a plataforma não conhece os valores por omissão do catálogo, por isso a linha lista todos os parâmetros do pedido e não só os que mudaram. Nenhum hash, ficheiro de referência nem teste dependia do texto do README; os testes `the_safety_phrase_counts_rules_and_never_writes_a_bare_status` e `the_request_line_lists_parameters_and_faults` fixam a frase.
- `tests/test_honesty_wording.py` (quatro testes, no `unittest` do repositório) lê `ui/js`, os scripts do módulo e `evidence.rs`: falha se `safety.status`, `safety_status` ou a classe de segurança forem escritos como texto fora das palavras partilhadas de `requirements.js` (comparações internas como `=== 'safe'` são permitidas), ou se aparecer uma cadeia «Safe»/«safe» como veredicto. Foi verificado com uma mutação: acrescentar `h('b', null, record.safety.status)` e `h('b', null, 'Safe')` a `player.js` fez falhar os dois testes de interface.
- `ux2_journeys.py` afirma no ecrã que nenhum nó de texto visível é «safe»/«Safe» (Runs, Compare, Analyse, leitor), que a mesma corrida tem as mesmas «Conditions» na página Runs, no Compare, em Analyse e no leitor, e que duas corridas com pedidos diferentes nunca partilham a etiqueta visível (Runs e Compare).
- O título da missão «Stalled but safe» (`experiences.js`) passou a «Stalled, no safety rule broken», e o formulário Prepare já não diz «No injected fault: a nominal run.» (ficou «No injected fault.», porque pode haver parâmetros alterados). O teste de guarda procura também a palavra «safe» sem distinguir maiúsculas em todo o código do Studio (comparações internas e opções de filtro permitidas): foi isto que apanhou o título da missão, que o teste exato de «Safe»/«safe» não via.
- As frases «Expected: ...» das demonstrações dos domínios dizem «safe»/«unsafe» nas palavras do domínio (por exemplo `desktop/domain-rocket/src/demos.rs`). Ficam como estão e aparecem rotuladas «Expected, stated by the domain» (Compare, Prepare e Analyse); não são um veredicto do Studio.

**Opcional (M1 a M7).**

- **M1 feito.** Leitor de engenharia a 1440x900 no estado final: as pílulas das corridas, a legenda e os botões de câmara ficam em zonas que não se sobrepõem (as pílulas e a câmara estão na mesma faixa, uma à esquerda e outra à direita, acima da legenda); verificado por sobreposição e por «nenhuma pílula cortada» em `ux2_journeys.py` e `review_captures.py`.
- **M2 feito.** Analyse a 820 px: a cena fica por cima da telemetria, cada uma com a largura da janela (acima de 900 px mantém-se a disposição em duas colunas); verificado por posições e por sobreposição.
- **M3 em parte.** O chip passou a «SAFETY RULES» e a nota diz «a requirement can fail without any safety rule being broken». O texto do chip final da aterragem falhada não mudou («Not met: Vertical speed at contact 60.08 m/s (limit <= 3 m/s), and 1 more not met; impact not modelled»): já nomeia o valor do pior requisito falhado e o limite.
- **M4 sem alteração, por falta do dado.** O registo `mission_completion` da corrida do corredor diz «incomplete; 1 of 1 waypoint(s) reached; 0 mm from the goal at the end», com o esperado «all 1 waypoint(s) reached, confirmed on the true position, with no stall of 8 ticks». O registo não diz qual das cláusulas falhou (o objetivo foi alcançado e a distância é 0 mm), por isso o Studio mostra as duas frases tal como estão e não inventa uma razão. A lacuna é do registo do domínio (ver «Decisões em aberto»).
- **M5 feito.** A corrida com uma regra de segurança quebrada tem a pílula com o ícone de aviso e as cores de falha; a linha do tempo mostra o marcador de violação de todas as corridas (não só da que está no ecrã, com o nome da corrida); a área do gráfico 2D acaba por cima das pílulas, por isso os rótulos do eixo não ficam tapados (verificado por sobreposição entre `.pl-viewport.is-2d` e `.pl-runs`, e nas capturas). Limitação: a 1024x640 as três pílulas do corredor deixam ao gráfico 2D cerca de 90 px de altura; fica legível nos eixos mas pequeno. A 820x900 a cena ganhou altura (a janela alta e estreita dá ao palco pelo menos 430 px), e o gráfico tem cerca de 170 px.
- **M6 feito.** Consola de voo: os chips «Your experiment» e «Exploratory» estão sobre o vidro forte, com contraste total; a pílula ativa tem fundo opaco e texto a negrito; «Show all findings now» tem o seu espaço no fim da legenda e não a cobre.
- **M7 feito.** Lab a 1440 e 820 px: «Margin change» fica à vista sem deslocamento lateral e a nota de rodapé quebra linha em vez de alargar a tabela (verificado por medição da tabela e do cabeçalho); a página Runs com o painel de detalhe a 1440x900 não corta «Safety rules» nem «Failed» (vista na captura).
- Extra: os chips de veredicto quebram dentro do próprio contorno; a cor do chip de segurança vem da mesma leitura que as palavras (uma regra quebrada nunca é verde; uma corrida sem avaliação nunca é «pass»); o chip de missão só conta os requisitos de missão.

**Verificação.** `ux2_journeys.py`: 71/71; `review_captures.py`: 16/16 (o 60 m/s e o corredor como corrida ativa a 1440x900, 1024x640 e 820x900, sem pílulas cortadas nem sobreposições). Na árvore desta passagem: `cargo fmt --check`, `clippy -D warnings`, `cargo test` na raiz e em `desktop/`, `unittest` (com `VV_GODOT`), teste Node (27 casos) e `node --check` de todos os ficheiros de `ui/js`.

**Inventário das superfícies que mostram segurança, resultado, contagens ou identidade de uma corrida.**

| Superfície | Onde está o texto | Verificada por |
| --- | --- | --- |
| Chips de resultado do leitor (missão, regras de segurança) | `views/player.js` (`runResult`) | `ux4-end-state-60ms-run-*`, `ux4-corridor-broken-rule-run-*`; `ux2_journeys.py` («Unsafe case: ...») |
| Pílulas das corridas do leitor (estado combinado, ícone de aviso) | `views/player.js` (`fillRunPills`) | mesmas capturas; `review_captures.py` (pílula de aviso, sem corte, sem sobreposição) |
| Chip do fim da corrida (requisito falhado, valor, limite) | `views/player.js` (`failedContactText`) | `ux4-end-state-60ms-run-*`; `review_captures.py` («the chip names the failing requirement») |
| Consola de voo (requisitos, regras «held», chips) | `views/player.js`, `views/control.js` | `ux3-flight-console-*`; `ux2_journeys.py` |
| Marcadores da linha do tempo | `views/player.js` (`drawBand`) | `review_captures.py` («a violation marker is on the timeline») |
| Linha «Conditions» do leitor | `views/player.js` | `ux2_journeys.py` («Player: each run has the same conditions...») |
| Painel de resultado do Cinematic | `desktop/cinematic/scripts/hud.gd` | `cinematic-panel-60ms-run.png`, `cinematic-panel-broken-rule-landing.png`; `tests/test_honesty_wording.py` |
| Analyse: veredictos, separador de verificação, linha «Conditions» | `views/run.js`, `verification.js` | `ux3-analyse-*`, `ux3-analyse-unsafe-dark`; `ux2_journeys.py` |
| Compare: cartões, legenda, matriz, mudanças de veredicto, linha «Both runs» | `views/compare.js` | `ux3-compare-*`, `ux3-compare-unsafe-dark`, `ux4-compare-identity-dark`, `ux4-compare-two-runs-dark`; `ux2_journeys.py` |
| Runs: coluna de segurança, célula «Failed», linha «Conditions» | `views/library.js` | `ux3-runs-*`, `ux3-runs-unsafe-dark`; `ux2_journeys.py` (a contagem contra o registo) |
| Lab: pílulas, estado combinado, tabela, margem | `views/lab.js` | `ux3-lab-*`; `ux2_journeys.py` (margem à vista) |
| Estatísticas da página inicial | `views/home.js` | `ux2_journeys.py` (`home_stats`) |
| Paleta de comandos (dica da corrida) | `main.js` | `tests/test_honesty_wording.py` (sem captura) |
| Cartões de demonstração da página Prepare e formulário de falhas | `views/prepare.js` (`demoCard`, secção «Faults») | `conditionsName` no teste Node (sem captura nem percurso) |
| Cartões das missões e da página inicial (títulos e texto das missões) | `views/missions.js`, `views/home.js`, `experiences.js` | `tests/test_honesty_wording.py` (palavra «safe» em todo o Studio); sem captura desta passagem |
| Investigate (Discovery Lab): estados e contagens de afirmações | `views/discover.js`, `claims.js` | não mudou: mostra o que o motor calculou sobre afirmações e corridas emparelhadas, não o estado de segurança de uma corrida; o guarda lê estes ficheiros |
| README do pacote de evidência | `desktop/platform/src/evidence.rs` | testes Rust `name_tests`; `tests/test_honesty_wording.py` |
| Frases «Expected» e textos do catálogo e dos registos dos domínios que contêm «safe» | texto do domínio, rotulado «stated by the domain» | não mudaram: são conteúdo do registo e do catálogo, não um veredicto do Studio |

**Decisões em aberto.**

- Os identificadores das corridas mudaram com esta compilação: o mesmo pedido (idêntico, `request.json` igual byte a byte) deu `9e6edb2e...` no executável intermédio e `d3c2d223...` no instalador final, porque o identificador inclui o hash do anfitrião do domínio e os anfitriões dependem da plataforma, onde `evidence.rs` mudou. O registo (`record.json`) é idêntico; só o `meta.json` difere (`host_sha256`, identificador, data e a etiqueta que cita a corrida de origem). Consequência prática: um pedido já guardado na biblioteca com o anfitrião anterior não é reutilizado por este instalador, e calcula-se de novo com identificador novo. As 11 corridas da biblioteca do utilizador não foram tocadas.
- A etiqueta de cabeçalho de uma corrida continua a não ser uma só: o leitor usa as etiquetas das próprias missões («Exact GPS», «1 mm of GPS noise»), o Compare usa o nome das condições («GPS noise 1 mm»). O que é igual em todas as superfícies é a linha «Conditions», e é isso que o percurso verifica; não se afirma uma só etiqueta de cabeçalho.
- O registo do domínio do veículo terrestre devia dizer qual cláusula de `mission_completion` falhou quando o resultado é «incomplete» com o objetivo alcançado (M4).
- A linha do pedido do README do pacote de evidência lista todos os parâmetros do pedido porque a plataforma não tem os valores por omissão do catálogo; se se quiser só os alterados, é preciso levar o catálogo para a plataforma.
- `ui_smoke.py`: três falhas anteriores a esta passagem (ver «O que não foi verificado»).

## Quinta passagem (residual, a última)

A revisão da quarta passagem deixou quatro bloqueios de percurso e quatro itens de código. Nenhum código de simulação, de domínio, da plataforma, de sementes ou de dados de corridas mudou; desta vez `evidence.rs` também não foi tocado, por isso os identificadores das corridas são os mesmos da quarta passagem (a corrida de 60 m/s continua `d3c2d223...`). O módulo Cinematic passa a 0.2.7.

**Obrigatório (feito e verificado no instalador).**

- **U1, gráficos com altura útil a 1024x640.** O leitor, em janelas até 1100 px de largura, é uma página que desce: o palco tem entre 390 px e 520 px (a altura da janela menos o cabeçalho e a barra de reprodução, dentro desses limites), as pílulas das corridas ficam numa só linha (a corrida mostrada por inteiro, as outras com o nome e o ícone de aviso), a legenda da linha do tempo ocupa uma só linha, o objetivo começa dobrado, o resumo fica por baixo do palco e a barra de reprodução fica presa ao fundo da janela. O relógio e o chip do fim da corrida partilham a linha e o gráfico 2D começa por baixo deles e acaba por cima das pílulas. Os eixos do corredor ajustam-se à zona restrita, ao percurso, ao início e ao objetivo (antes iam de -20000 a 30000 mm e o passo de 250 mm para dentro da zona ficava com 3 px; agora vai de 1000 a 5500 mm em x e de 1000 a 2000 mm em y). Em Analyse, a esta altura (e a 820 px) a cena fica por cima da telemetria, ambas com a largura da janela, e a página desce. `ux2_journeys.py` mede: a cena do leitor tem pelo menos 200 px de altura a 1024x640 e a 820x900 (1024x640: [413] px; 820x900: [520] px; gráfico 2D do corredor em `review_captures.py`, 1440x900: 368 px, 1024x640: 228 px, 820x900: 207 px) e cada gráfico da cena de Analyse (3D, perfil e vista de cima) tem pelo menos 200 px (1024x640: [296, 273, 273, 256, 256] px; 820x900: [434, 394, 394, 394, 394] px). Efeitos laterais tratados na mesma passagem e verificados por `review_captures.py` (a página do leitor não se desloca para o lado e o cabeçalho, a barra de reprodução e o cartão de leitura ficam dentro da janela a três tamanhos): o cartão de leitura passou de 232 a 244 px (a unidade «permille» é mais larga que «‰»), a lista «Run» fica com 200 px a 820 px, e a página Runs com o painel de detalhe a 820 px deixa de partir o seed em duas linhas (um número nunca se parte). Limitação: a 1024x640 o resumo do resultado só se vê descendo a página.
- **U2, identidade da corrida no leitor.** As pílulas das corridas e a lista «Run» do Cinematic levam a etiqueta da missão, as condições (`conditionsName`, não repetidas quando a etiqueta já as diz) e o identificador curto (os 8 primeiros caracteres; o completo está na dica); a consola de voo leva o identificador curto e as condições na dica. O percurso verifica, a 1024x640 e a 820x900, que cada pílula e cada opção da lista trazem as condições e o identificador da própria corrida.
- **U3, chip do fim da corrida.** «Not met: Vertical speed at contact 24.23 m/s (limit <= 3 m/s); safety rule broken: Climb under power; impact not modelled». A corrida do corredor já não diz só «End of run»: «End of run: Mission incomplete; requirements not met: ...; safety rule broken: Truth stays outside the restricted zone». Verificado em `review_captures.py` para a missão `threshold-trade-off` e para o corredor.
- **U4, cabeçalho e painel do Cinematic.** O Studio passa `--conditions` (limitado e limpo como a etiqueta: 160 caracteres, sem caracteres de controlo nem de direção de texto; o módulo aceita 200); o cabeçalho mostra «conditions: ...» e, nas corridas exploratórias, «(exploratory, not a real vehicle)». O painel do resultado diz «Impact is not modelled: the stage is drawn intact whatever the contact speed.» quando o registo tem contacto com o solo. As duas imagens (`cinematic-panel-60ms-run.png`, `cinematic-panel-broken-rule-landing.png`) foram desenhadas pelo módulo instalado com os argumentos que o próprio Studio lhe passou (lidos da linha de comandos do processo que o Studio lançou), e o percurso confirma que o rótulo, as condições e a marca exploratória desses argumentos são os do leitor.
- **R1, o teste de guarda.** `tests/test_honesty_wording.py` lê o ficheiro inteiro (comentários retirados), retira as comparações com um literal e exige que não sobre nenhuma leitura do estado ou da classe de segurança (`safety_status`, `safety_class`, `.safety.status`, `.safety.class`, desestruturação de `.safety`, `.safety` guardado numa variável), incluindo modelos de texto partidos por várias linhas. A lista de exceções é por ficheiro e cada entrada tem a sua razão (`class-badge`, `const hay =`, o filtro, a chave de agrupamento, o atributo de dados); `key:`, `dataset:`, `hay` e `verdictChip(` saíram da lista geral, e uma entrada que já não corresponde a nada faz o teste falhar. Prova com os mutantes do revisor mais três: numa cópia de trabalho, cada mutante como ficheiro novo em `views/` (`h('td', {key:1}, m.summary.safety_status)`, o ternário com `record.safety.status`, `verdictChip(record.safety.status)`, o modelo de texto partido, `const {status} = rec.safety`, `rec.safety.status + ' hay'`, `rec?.safety?.status`, `const s = rec.safety; ... s.status`, `s.safety_class`): **9 de 9 apanhados**; a cópia sem mutantes passa. Os mutantes não foram guardados; o teste `test_the_scan_catches_the_known_mutants` guarda os mesmos fragmentos como texto e exige que cada um seja apanhado e que quatro fragmentos limpos não sejam.
- **R2.** A dica das corridas na paleta de comandos usa a regra partilhada (`summarySafetyText` em `requirements.js`): uma corrida sem avaliação (`safety_class` `not_evaluated`) diz «safety not evaluated».
- **R3.** A linha deste README sobre a captura da Cinematic View diz o módulo verdadeiro (0.2.7).
- **R4, `ui_smoke.py`.** A contagem de domínios aceita quatro (o instalador traz o de subida), a verificação de «Verified» ignora maiúsculas (o ecrã escreve «VERIFIED») e o teste passou a descobrir o defeito do `Escape`. Era um defeito de teclado verdadeiro: com a ajuda de atalhos aberta, o foco estava num botão de navegação por trás do diálogo e o `Escape` (ouvido só dentro do diálogo) não fechava nada. Agora o diálogo leva o foco logo ao abrir, o `Escape` é tratado ao nível do documento enquanto o diálogo está aberto e o `Tab` traz o foco de volta ao diálogo (`ui/js/ui.js`). O teste regista onde estava o foco («Escape closes the shortcut help») e a navegação passou a clicar através da página quando o botão está no menu «More». Resultado no instalador: **80/80** (a contagem total subiu porque o teste já não pára na falha do diálogo; antes eram 44 de 47).

**Opcional.**

- Os marcadores de violação da linha do tempo têm a cor da corrida e uma forma que diz o que quebrou: quadrado para uma regra de segurança, círculo para um requisito; a legenda di-lo.
- «permille» em vez de «‰».
- O Compare diz primeiro a corrida que falha: «B fails it; A passes it. Largest change: ...» (verificado em `ux2_journeys.py`).
- A consola de voo diz «SAFETY RULES» (antes «Safety invariants»).
- Runs com o painel de detalhe: o painel desce para baixo da tabela até 1100 px (a 1024x640 já não corta Outcome, Safety rules nem Failed) e, a 820 px, a coluna da data sai, as células perdem um pouco de margem e o texto quebra linha; `ux2_journeys.py` confirma que as três colunas ficam à vista.

**Mapa das capturas** (pasta `review` da quinta passagem, fora do repositório).

| Captura | Itens |
| --- | --- |
| `ux4-corridor-broken-rule-run-1024x640-dark` | U1 (gráfico 2D, pílulas numa linha, eixos ajustados), U2, U3 (chip do corredor), marcadores |
| `ux4-corridor-broken-rule-run-1440x900-dark`, `-820x900-dark`, `-1440x900-light` | U1, U2, U3 nos outros tamanhos e no tema claro |
| `ux4-end-state-60ms-run-1024x640-dark`, `-1440x900-dark`, `-820x900-dark`, `-1440x900-light` | U1 (cena a 1024x640), U2 (pílulas e lista «Run»), U3 |
| `ux4-threshold-trade-off-player-dark` | U3 (requisito falhado e regra quebrada no chip) |
| `cinematic-panel-60ms-run`, `cinematic-panel-broken-rule-landing` | U4 (cabeçalho com condições, frase do impacto, painel por contagem de regras) |
| `ux3-analyse-1024x640-dark`, `ux3-analyse-820x900-dark` | U1 (Analyse com gráficos de pelo menos 200 px) |
| `ux3-runs-1024x640-dark`, `ux3-runs-820x900-dark`, `ux3-runs-detail-dark` | Runs com o painel de detalhe |
| `ux4-compare-identity-dark`, `ux4-compare-two-runs-dark` | frase do Compare e corrida que falha primeiro |
| `ux3-flight-console-1440x900-dark`, `ux2-flight-console-1024x640-dark` | «SAFETY RULES», identificador curto nas pílulas |

**Não feito, e decisões em aberto.** Continuam como na quarta passagem: uma só etiqueta de cabeçalho por corrida, a cláusula que falhou em `mission_completion`, o M3 e a linha do pedido do pacote de evidência. A 1024x640 o resumo do resultado do leitor só se vê descendo a página. Os textos do catálogo e dos registos dos domínios que contêm «safe» (por exemplo «Safe (not evaluated: ...)» e as frases «Expected» das demonstrações) são conteúdo do registo e não foram alterados.

## A espera pelo primeiro frame

O módulo descodifica os ativos CC0 ao arrancar, por isso passam 12 a 16 s entre o clique em «Cinematic view» e o primeiro frame (15,6 s na aterragem e 13,7 s na subida no percurso de utilizador final). Duas mudanças:

- Studio (`desktop/studio/ui/js/cinematic.js`): depois do lançamento aparece o estado «Opening the Cinematic View in its own window. The first frame takes about 15 seconds.» (`role="status"`), que fica 30 s ou até ser dispensado. O percurso verifica que existe logo a seguir ao clique e que ainda lá está 6 s depois. Não se verificou o que acontece se a janela do módulo for fechada antes dos 30 s (o estado continua até ao fim do prazo).
- Módulo 0.2.1 (`desktop/cinematic/project.godot`, `assets/boot-splash.png`): `boot_splash` com fundo escuro e o texto «Cinematic View. Opening the replay. The first frame takes about 15 seconds.», sem logótipos. O empacotador copia `assets/` e o manifesto lista o ficheiro com tamanho e SHA-256. Medido: a janela do Godot aparece 0,9 s depois do arranque do processo e mostra a imagem (`cinematic/boot-splash-window.png`, captura da própria janela do módulo com `PrintWindow`) enquanto a cena é construída, que demora cerca de 14 s; a janela respondia aos 14,6 s e aos 20 s. A primeira imagem gerada tinha 720x180 e o Godot ampliou-a até ficar cortada; a final tem 1440x900 e coincide com a janela. Não se mediu o aspeto em janelas de outros tamanhos.

## Passagem de correções de interface

Uma revisão independente das capturas do 0.18.1 instalado (veredicto «boa, com lacunas») levou a esta passagem. `ux_journeys.py` verifica cada ponto no executável instalado:

| Ponto da revisão | O que o percurso verifica |
| --- | --- |
| Segurança sem «safe» sozinho | Compare (legenda das corridas e linha «Safety rules»), Lab (as duas etiquetas de veredicto), Library (coluna), vista de execução e leitor dizem «No safety rule broken» (com «(5 checked)» onde há contagem); uma nota diz que a velocidade de contacto é um requisito da missão e que um aterrar duro falha um requisito sem quebrar uma regra de segurança |
| Duas corridas lêem-se como diferentes | cabeçalho «Largest change: Vertical speed at contact 1.658 → 60.08 m/s (limit <= 3 m/s)» em Compare e no Lab; cada célula tem valor observado e margem, e a linha tem o limite; «9 rows differ ... 1 in its verdict, the others in a value»; linhas que falham primeiro; 4 algarismos significativos com o valor completo na dica; inclinação em graus; nomes de requisitos repetidos da subida distinguidos pelo andar; na subida, a linha da apoapsis mostra a leitura publicada («1.903 km», limite «<= 15 km») e não a altitude da apoapsis |
| Cartão do leitor | «Not met: Horizontal speed at contact 1.584 m/s (limit <= 1 m/s); impact not modelled» na corrida de base e «Not met: Vertical speed at contact 60.08 m/s (limit <= 3 m/s), and 1 more not met; impact not modelled» na experiência |
| Cinematic View | com duas corridas o leitor deixa escolher qual abre (cada uma foi aberta: o `--run` da linha de comandos do processo é o identificador escolhido); o processo recebe `--run-label`, `--vehicle`, `--seed 5000` e `--exploratory`; o `--env` é o do ambiente que o leitor tinha (Wallops Island) nas duas corridas |
| Texto | declaração «Exploratory models, not real vehicles; nothing is validated against flight data.» em Mission Control e no hangar; sem «validated offline»; «recomputed model behaviour»; uma só etiqueta «Open in Experiment Lab» no hangar, no leitor e na vista de execução |
| Navegação a 820 px | sem barra de deslocamento; Configure, Analyse, Compare e Records no menu «More»; Enter abre, as setas e End movem, Escape fecha e devolve o foco, Enter em «Records» abre a Library; a 1440 px o menu não aparece |
| Lab | «Run experiment» visível desde o início, desligado com «Change one condition first» (descrito por `aria-describedby`); a coluna das condições sem deslocamento próprio; botões de sementes desligados com «Run an experiment first.» |
| Ambientes | 8 descrições sem corte, «Terrain is context only» em cada cartão, estado do módulo resolvido |
| Uma cor para Exploratory | o chip do Lab e o do hangar têm a mesma cor calculada; o leitor mostra «Reference case» ou «Exploratory» por corrida e o primeiro aterrar registado mostra «Reference case» |
| Tamanhos estreitos e tamanho do texto | a 1024x640 e a 820 px, no leitor de engenharia com duas corridas, a nota da cena não se sobrepõe à barra de câmaras nem às etiquetas das corridas; a 1024x640, na consola de voo, a atribuição não se sobrepõe à barra de câmaras, os nomes dos requisitos quebram linha e o título e as ferramentas não são empurrados; na vista geoespacial a atribuição e a barra de câmaras não se sobrepõem; nenhum texto abaixo de 12 px em Mission Control, hangar, ambientes, Lab, Compare, leitor, vista de execução e leitor a 1024x640 |

**Defeitos que a primeira versão desta passagem tinha e que a verificação ou a leitura das capturas encontrou antes do fecho.**

1. Na subida, as células do Lab misturavam o primeiro número do texto observado com o limite e a margem publicados: a linha da apoapsis mostrava «301.9 km» contra «<= 15 km» com margem «+13.1 km». Passou a ler a leitura observada que o domínio publica, e o sentido do limite deduz-se da margem. Verificado no instalador final.
2. O cartão de fim de aterragem, agora uma frase, esmagava o título e empurrava as ferramentas para fora da janela na consola de voo a 1024x640 (duas iterações: primeiro sobrepunha o título, depois ficava 5 px fora da janela).
3. A atribuição da consola de voo a 1024x640 passava por baixo da barra de câmaras; e a nota da cena de engenharia ficava por baixo das etiquetas das corridas a 820 px.
4. `safetyWording` podia escrever «1 of N safety rules broken» sem nenhuma linha de invariante falhada; a contagem só aparece agora quando as linhas do próprio registo a dão.
5. O rótulo dos gráficos do módulo ficava cortado («Graphics: High (Auto: 12.9 GE») e o rótulo da corrida com «×» aparecia estragado na captura de revisão (era a leitura da linha de comandos pelo teste; o Studio passa o texto certo).

**Sobre o ambiente da Cinematic View.** A revisão viu «Cape» na Cinematic View e «Wallops» no leitor. Não consegui reproduzir a diferença no produto: nas duas corridas abertas o `--env` do processo era `wallops-island`, o ambiente escolhido em Environments e mantido pelo leitor. Uma explicação possível, **não confirmada**: o percurso `installed_spotcheck.py` não escolhia nenhum ambiente, por isso as suas imagens da Cinematic View usavam o ambiente por omissão (Cape) enquanto as capturas do leitor do `m18` e do `ux_journeys.py` eram de Wallops. O percurso de utilizador escolhe agora Wallops antes de abrir a Cinematic View, e as imagens `cinematic-landing.png` e `cinematic-ascent.png` são de Wallops; `ux_journeys.py` verifica o `--env` de cada abertura.

Na vista da Cinematic View (módulo 0.2.7, `cinematic/cinematic-hud-experiment.png`, desenhada pelo módulo com os argumentos que o Studio lhe passou): linha da corrida («Engine thrust 0.7 × (9e6edb2e) | seed 5000 | 41 t heavy return stage (exploratory, not a real vehicle)»), «altitude», «speed |v|» (o comprimento do vetor de velocidade gravado), acelerador em percentagem, a linha «reads the recorded sample at t» mais discreta, e «Graphics: auto» sem corte (a razão completa fica na dica). Não se verificou a dica com o rato.

**Não verificado.** O contraste das sobreposições sobre imagens não foi medido; só as razões de luminância dos cinzentos de apoio sobre os fundos dos painéis (5,7:1 ou mais no tema escuro, calculadas dos tokens), e as atribuições do Studio passaram a ter fundo quase opaco (94 %) e a cor de texto forte, sem medição. Os botões e menus não foram observados com tecnologia de apoio.

## Percurso de utilizador no Studio instalado

`installed_spotcheck.py` percorre: Mission Control, hangar de veículos, «Open in Experiment Lab» do andar pesado (41 t) com o impulso × 0,7, Compare, leitor com a vista Engineering e Cinematic View para a corrida de **aterragem**; depois o lançador pequeno com carga útil de 600 kg, o leitor e a Cinematic View para a corrida de **subida**.

- Aterragem (semente 5000, controlador robusto): velocidade vertical no contacto 1,66 m/s (passa) contra 60,08 m/s (falha) com o impulso × 0,7; em Compare as etiquetas diferem («Engine thrust 1 × (default)» e «Engine thrust 0.7 ×») e nenhuma está truncada.
- Subida: a carga útil de 600 kg passa a corrida de «Orbit» para «Suborbital» (R4, R6 e R8 falham); o Lab mostra margens numéricas (por exemplo «-329 Pa» na pressão dinâmica máxima) e nenhum requisito com números mostra a margem vazia. As margens numéricas foram verificadas na tabela do Lab.
- Cinematic View, nos dois casos: o Studio iniciou o processo `Godot_v4.7.2-stable_win64.exe` com `--rendering-driver d3d12` (linha de comandos lida ao sistema operativo), o registo do módulo diz `D3D12 12_0 - Forward+ - AMD Radeon RX 7700 XT` sem `ERROR`, e a linha `FIRST_FRAME` apareceu 13,6 s (aterragem) e 12,1 s (subida) depois do clique (perfil Auto, que escolheu High).
- O Studio não passa `--shot` ao módulo. As imagens `cinematic/cinematic-landing.png` e `cinematic-ascent.png` (ambiente Wallops Island, escolhido pelo percurso) vêm de uma segunda execução, separada, do módulo instalado com os mesmos argumentos lidos do processo iniciado pelo Studio, `--t` a 55 % da duração do registo e `--shot`. Mostram só a cena do módulo.

## Desempenho (Direct3D 12 / WebView2)

Medido fora da simulação, no instalador final e no módulo 0.2.7, uma execução de cada (repetido na quarta passagem; os números das passagens anteriores não são comparáveis entre dias, ver o controlo abaixo).

Vista geoespacial e leitor, `python desktop/studio/tests/perf_probe.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --flow m16` (janela 1440x900, biblioteca temporária; `perf/perf-m16.json`):

| Medida | Valor |
| --- | --- |
| Arranque a frio até ao ecrã pronto | 0,96 s |
| Clique até à aterragem no ecrã | 0,26 s |
| Passagem à vista geoespacial até ao terreno na GPU | 0,470 s |
| Frames em reprodução (engenharia / geoespacial / Flight console) | p50 17,6 / 17,5 / 18,0 ms; p99 18,8 / 19,1 / 19,1 ms; nenhum acima de 33 ms |
| CPU em reprodução (de um núcleo) | 23 % / 31 % / 5 % |
| Memória (working set) em reprodução geoespacial | 872 MB; 650 MB depois de sair do leitor |
| Sessão de 180 s, p99 dos frames | 18,5 a 19,4 ms; working set de 1028 para 880 MB |
| GPU dedicada, utilização 3D na vista geoespacial | 467 MB, 24,1 % |
| Pedidos da WebView a fora da máquina | nenhum |

**A cadência dos frames é de cerca de 18 ms (55 Hz), contra 8 ms (125 Hz) na verificação de 12 de novembro, e o Studio não é a causa.** O controlo `perf/raf-control.json` mede `requestAnimationFrame` na mesma janela do Studio: na página inicial parada p50 18,1 ms (p99 19,1) e numa página em branco (`data:text/html`) p50 18,0 ms (p99 19,2). Uma página vazia tem o mesmo ritmo, por isso o ritmo é o da janela ou do compositor nesta sessão; o controlador continua a indicar 165 Hz. Não foi investigado e as séries de dias diferentes não são comparáveis entre si.

Cinematic View, módulo instalado, `python scripts/cinematic/bench.py --godot <Godot_v4.7.2-stable_win64_console.exe do módulo> --project <project do módulo> --run tests/fixtures/cinematic/landing-run --env <environments/cape-canaveral instalado> --out <pasta> --profiles auto,balanced --seconds 12 --driver d3d12` (1440x900, sem sincronização vertical, câmara Auto; `perf/bench-*.json`, `perf/summary.json`):

| Perfil | Arranque até ao primeiro frame | Frame p50 | Frame p99 | Memória de vídeo | Working set (pico) | Bytes privados (pico) |
| --- | --- | --- | --- | --- | --- | --- |
| Auto (escolheu High) | 13,9 s | 3,17 ms | 13,67 ms | 2386 MB | 748 MB | 3067 MB |
| Balanced | 11,4 s | 1,92 ms | 5,36 ms | 1336 MB | 715 MB | 1873 MB |

Os dois ficam dentro do orçamento de 16,7 ms (60 Hz) no p99.

## Verificação do repositório

Ver `verification.txt`: lista do `AGENTS.md` na raiz e em `desktop/`, testes Python com `VV_GODOT` definido (439 testes, 6 ignorados por dependências opcionais; o teste Node corre e não é ignorado, também numa cópia em «v&v lab») e a campanha `--seeds 42,1337,2026`. Na árvore da quinta passagem (e das anteriores) correram `cargo fmt --check`, `clippy -D warnings` e `cargo test` na raiz e em `desktop/` (37 suites, 306 testes) e o `unittest` (441 testes, OK, na quinta). A campanha e a compilação de lançamento da raiz não foram repetidas porque a raiz não mudou desde a verificação anterior. `ui_smoke.py` passou na quinta passagem contra o instalado (80/80); o passo do CI continua informativo.

Comandos do README: `cargo run -- run ...` falhava porque o pacote da raiz tem três binários. Acrescentar `default-run = "vv-lab"` ao `Cargo.toml` da raiz resolve-o, mas muda o `source_sha256` do `vv-lab` (calculado a partir do `Cargo.toml`) e a paridade do problema D1 do benchmark M14 deixa de passar. Por isso os comandos do README, de `docs/reproducibility.md` e de `docs/m2-results.md` passaram a `cargo run --bin vv-lab -- ...` e o `Cargo.toml` ficou como estava.

## O que não foi verificado

- Não houve observação de pessoas: são verificações automatizadas do que o ecrã e a lista de processos mostram.
- A reversão para o 0.17.0 não foi executada, só os hashes foram verificados. A compatibilidade do Studio 0.17.0 com o módulo 0.2.7 não foi testada.
- Não se capturou a janela do processo iniciado pelo Studio (evitam-se capturas do ambiente de trabalho); as imagens da cena vêm de uma segunda execução do mesmo módulo com os mesmos argumentos.
- A subida só foi medida no arranque; `bench.py` correu só sobre o registo de aterragem.
- A diferença de ambiente que a primeira revisão viu na Cinematic View não foi reproduzida (ver acima).
- O contraste de texto sobre imagens, a dica do rótulo de qualidade do módulo e o uso com tecnologia de apoio não foram verificados.
- `ui_smoke.py` passou por inteiro na quinta passagem (80/80) contra o instalado; o passo do CI é informativo (`continue-on-error`).
- O aspeto do novo painel de reprodução do módulo (rótulos, linhas que quebram) só foi visto a 1440x900 e 1100x700 com uma captura de cada, sem as regiões de erro de janelas muito estreitas.
- O módulo é 0.2.7: cada passagem do módulo pedia uma versão nova (0.2.2 e 0.2.3 foram intermédios).
- Itens da lista de revisão marcados «não feito» na secção da segunda passagem.

## Recuperação (rollback)

Instaladores e hashes (os mesmos de `SHA256SUMS.txt`):

| Versão | Ficheiro | SHA-256 |
| --- | --- | --- |
| 0.17.0 (a que estava instalada) | `VV Lab Studio_0.17.0_x64-setup.exe` | `ce9fa33a526518ea5438f7d2a30a9f6c71e5fbcca7cbd2fafef9251f9ddbc972` |
| 0.18.0 | `VV Lab Studio_0.18.0_x64-setup.exe` | `8ad87eba2f7223186a4a265eea06da6a88fef21878c1fb74bc630d554471fb46` |
| 0.18.1, primeira versão | `VV Lab Studio_0.18.1_x64-setup-prebuild.exe` | `b0c2cf4180219ec427e6157072d3291c2c71e6beda2a75d22b3f3d867a8597ee` |
| 0.18.1, antes da passagem de interface | `VV Lab Studio_0.18.1_x64-setup-before-ux-pass.exe` | `953c3f135ce581b97d5c3e96245c14064acc20a05e593cf20fc85ed3c394457d` |
| 0.18.1, primeira passagem, iterações 1 a 3 | `...-ux-pass-1.exe`, `...-ux-pass-2.exe`, `...-ux-pass-3.exe` | `a3663b5f...`, `a0fe74c0...`, `0e07f7df...` (completos em `SHA256SUMS.txt`) |
| 0.18.1, final da primeira passagem | `VV Lab Studio_0.18.1_x64-setup-ux-round-1.exe` | `e57f0af483eb12315dcc99226bae21f4172d05416c3de6f0a58d00f15a84d765` |
| 0.18.1, segunda passagem, 1.ª iteração | `VV Lab Studio_0.18.1_x64-setup-ux-round-2.exe` | `c879688c3798461d4b7258f0a7beb1cfffa1ed73eb37ace5368584e635d33406` |
| 0.18.1, final da segunda passagem | `VV Lab Studio_0.18.1_x64-setup-ux-round-3.exe` | `75eb323618c6f7992cfe5595a99178b23a1cd914936a5dc39114cbb279fdde2f` |
| 0.18.1, terceira passagem, 1.ª iteração | `VV Lab Studio_0.18.1_x64-setup-ux-round-3b.exe` | `b9927fb468e4fff870f7a6840fbab721f60357a96c24cbc292c54fb7cd696e7d` |
| 0.18.1, final da terceira passagem | `VV Lab Studio_0.18.1_x64-setup-ux-round-4.exe` | `29a4d131430be7440f8d90212f821c9920286486fcb0cd3220e9a8ab163a2c46` |
| 0.18.1, quarta passagem, 1.ª iteração | `VV Lab Studio_0.18.1_x64-setup-ux-round-4b.exe` | `9d4cb6c64102e461d72e6e37b9720c48b1979cc393e68f506858af7d590e1e08` |
| 0.18.1, quarta passagem, 2.ª iteração | `VV Lab Studio_0.18.1_x64-setup-ux-round-4c.exe` | `d54b8e194eafe81349973fa86ebed0f0c42aeab8aeeb95a9693111ea2aa455c4` |
| 0.18.1, final da quarta passagem | `VV Lab Studio_0.18.1_x64-setup-ux-round-5.exe` | `b7f21c8395ced32ef49b59048168a9a992ced99bef3fab3172971fd92c5fc0d5` |
| 0.18.1, quinta passagem, 1.ª iteração | `VV Lab Studio_0.18.1_x64-setup-ux-round-5b.exe` | `e928851928a58556a56e7e803b41ba72f795e0c190526b010f4d6e64b25dcf80` |
| 0.18.1, quinta passagem, 2.ª iteração | `VV Lab Studio_0.18.1_x64-setup-ux-round-5c.exe` | `bda261a4727a06575c5e8dce5d6510444856bcb27ae99ebd68ce11f3cbdad1ba` |
| 0.18.1 (instalado) | `VV Lab Studio_0.18.1_x64-setup.exe` | `9ccb649818882decb77636c0961bb0857bc1f2035605738dd2b9e8b7f2a7b3c2` |

Para voltar ao 0.17.0: confirmar o hash com `Get-FileHash "<pasta de recuperação>\VV Lab Studio_0.17.0_x64-setup.exe" -Algorithm SHA256`, fechar o Studio e executar o instalador com `/S`. A biblioteca em `Documentos\VV Lab Library` e o módulo em `%LOCALAPPDATA%\org.vvlab.studio\modules\cinematic` não pertencem ao instalador e ficam como estão.

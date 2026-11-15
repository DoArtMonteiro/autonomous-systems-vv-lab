# Studio 0.18.1 instalado: verificação no Windows

Esta pasta guarda a verificação do V&V Lab Studio 0.18.1 **instalado** (instalador NSIS, execução silenciosa por cima do 0.17.0), não do executável da pasta de compilação. Os percursos correram contra `%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe`, com o módulo Cinematic 0.2.5 instalado pelo código de instalação do próprio Studio. Nenhuma captura do ambiente de trabalho foi guardada: as imagens da pasta `cinematic/` foram desenhadas pelo módulo (`--shot`) ou são a janela do próprio módulo (`boot-splash-window.png`, da 0.2.1; a imagem de arranque não mudou), e só contêm a cena ou a imagem de arranque.

Em relação ao `main` (`66b30ca`) a versão 0.18.1 muda o número de versão do Studio, acrescenta o estado «Opening the Cinematic View...» e, depois da revisão independente das capturas do 0.18.1, uma passagem de correções de interface (secção «Passagem de correções de interface»). O módulo passa de 0.2.0 a 0.2.5. Os testes mudaram: `m17_cinematic_journey.py` espera pelo primeiro frame e verifica o estado novo, `installed_spotcheck.py` automatiza o percurso de utilizador e `ux_journeys.py` verifica as correções.

## Máquina

AMD Ryzen 7 7800X3D (8 núcleos, 16 fios), 31,7 GB de RAM, AMD Radeon RX 7700 XT (controlador 32.0.31041.3013), Windows 11 Pro compilação 26300, WebView2 156.0.4314.58, Godot 4.7.2-stable, Python 3.14.6. O Microsoft Defender ficou ativo durante todo o trabalho e não foi alterado. Os números são desta máquina e não descrevem outras.

## Artefactos

| Artefacto | Tamanho | SHA-256 |
| --- | --- | --- |
| `VV Lab Studio_0.18.1_x64-setup.exe` (o instalado e verificado) | 42 441 737 bytes | `29a4d131430be7440f8d90212f821c9920286486fcb0cd3220e9a8ab163a2c46` |
| `vv-cinematic-0.2.5.zip` (78 ficheiros, 449 766 891 bytes em disco) | 345 001 192 bytes | `6a191c64c50b83ad280e294052771dfa1f1882eef6a7da29940f677d9b176050` |

O instalador foi construído com `desktop/build.ps1` (compilação de lançamento completa): **código de saída 0**, capturado pelo invólucro que o executou (`BUILD EXIT 0`). Como o 0.18.1 ainda não foi publicado fora deste PC, o número de versão ficou e os instaladores anteriores deste número foram guardados na pasta de recuperação com nomes que dizem o que são: `...-setup-prebuild.exe` (a primeira versão), `...-setup-before-ux-pass.exe` (com o estado «Opening...», sem correções de interface), `...-setup-ux-pass-1.exe` a `-ux-pass-3.exe` (as três iterações da primeira passagem de interface), `...-setup-ux-round-1.exe` (o instalador final da primeira passagem, `e57f0af4...`, que a revisão de código e de interface avaliou) `...-setup-ux-round-2.exe` (a primeira iteração da segunda passagem, `c879688c...`, que ainda falhava a verificação a 820 px), `...-setup-ux-round-3.exe` (o instalador final da segunda passagem, `75eb3236...`, que a terceira revisão avaliou) e `...-setup-ux-round-3b.exe` (a primeira iteração da terceira passagem, `b9927fb4...`, que ainda deixava a página Runs com deslocamento horizontal a 820 px). `SHA256SUMS.txt` (esta pasta) resume os hashes relevantes; a lista completa está na pasta de recuperação do proprietário, e os quinze ficheiros ali foram verificados contra ela.

## Instalação

- Antes da primeira instalação, o hash do instalador de recuperação 0.17.0 foi confirmado contra o `SHA256SUMS.txt`.
- O 0.18.1 foi instalado por cima do 0.17.0 e, depois, várias vezes por cima de si próprio à medida que o instalador mudou (dez instaladores até ao final), sempre com `/S`: código de saída 0; a chave `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\VV Lab Studio` ficou com `DisplayVersion` 0.18.1 e o executável instalado declara a versão 0.18.1.
- Biblioteca do utilizador (`Documentos\VV Lab Library`): 11 corridas antes e depois de todas as instalações e de todos os percursos, mesma lista de identificadores, e o SHA-256 da lista ordenada dos 89 ficheiros da biblioteca é idêntico ao de antes da primeira instalação.
- Módulo Cinematic: instalado pelo teste opcional `real_module_zip_installs_when_given` de `desktop/studio/src/modules.rs` (`VV_CINEMATIC_ZIP`, `VV_CINEMATIC_INSTALL_TO` a apontar para a pasta real de módulos), porque o diálogo nativo não é automatizável. Substituiu as versões anteriores; o Studio instalado lê `installed: true, verified: true, version: 0.2.5`.
- O percurso `m17_cinematic_journey.py` desinstala o módulo no fim; por isso o módulo é reinstalado da mesma forma depois dele. No fim de tudo, o módulo 0.2.5 está instalado e verificado e não ficou nenhum processo do Studio nem do Godot.

## Percursos contra o executável instalado (instalador final, módulo 0.2.5)

| Percurso | Resultado | Registo |
| --- | --- | --- |
| `m15_journeys.py` | 48/48 | `m15-journeys.txt` |
| `m16_journeys.py` | 78/78 | `m16-journeys.txt` |
| `m17_lab_journeys.py` (porta 9273) | 34/34 | `m17-lab-journeys.txt` |
| `m17_cinematic_journey.py --preinstalled` | 11/11 | `m17-cinematic-journey.txt` |
| `m18_journeys.py` | 72/72 | `m18-journeys.txt`, `m18-numbers.json` |
| `installed_spotcheck.py` | 44/44 | `installed-spotcheck.txt`, `installed-spotcheck-facts.json` |
| `ux_journeys.py` (primeira passagem) | 81/81 | `ux-journeys.txt`, `ux-facts.json` |
| `ux2_journeys.py` (segunda e terceira passagens) | 52/52 | `ux2-journeys.txt`, `ux2-facts.json` |

Todos usam bibliotecas e configuração temporárias (`VVLAB_LIBRARY`, `VVLAB_CONFIG`), por isso não tocam na biblioteca do utilizador. Os caminhos temporários aparecem nos registos como `<temporary folder>`. Os oito correram numa só execução no instalador final; o guião reinstala o módulo no início e no fim (o percurso `m17_cinematic` desinstala-o). As execuções anteriores da segunda passagem tiveram falhas verdadeiras que levaram a duas reconstruções (ver «Segunda passagem»).

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

Na vista da Cinematic View (módulo 0.2.5, `cinematic/cinematic-hud-experiment.png`, desenhada pelo módulo com os argumentos que o Studio lhe passou): linha da corrida («Engine thrust 0.7 × (9e6edb2e) | seed 5000 | 41 t heavy return stage (exploratory, not a real vehicle)»), «altitude», «speed |v|» (o comprimento do vetor de velocidade gravado), acelerador em percentagem, a linha «reads the recorded sample at t» mais discreta, e «Graphics: auto» sem corte (a razão completa fica na dica). Não se verificou a dica com o rato.

**Não verificado.** O contraste das sobreposições sobre imagens não foi medido; só as razões de luminância dos cinzentos de apoio sobre os fundos dos painéis (5,7:1 ou mais no tema escuro, calculadas dos tokens), e as atribuições do Studio passaram a ter fundo quase opaco (94 %) e a cor de texto forte, sem medição. Os botões e menus não foram observados com tecnologia de apoio.

## Percurso de utilizador no Studio instalado

`installed_spotcheck.py` percorre: Mission Control, hangar de veículos, «Open in Experiment Lab» do andar pesado (41 t) com o impulso × 0,7, Compare, leitor com a vista Engineering e Cinematic View para a corrida de **aterragem**; depois o lançador pequeno com carga útil de 600 kg, o leitor e a Cinematic View para a corrida de **subida**.

- Aterragem (semente 5000, controlador robusto): velocidade vertical no contacto 1,66 m/s (passa) contra 60,08 m/s (falha) com o impulso × 0,7; em Compare as etiquetas diferem («Engine thrust 1 × (default)» e «Engine thrust 0.7 ×») e nenhuma está truncada.
- Subida: a carga útil de 600 kg passa a corrida de «Orbit» para «Suborbital» (R4, R6 e R8 falham); o Lab mostra margens numéricas (por exemplo «-329 Pa» na pressão dinâmica máxima) e nenhum requisito com números mostra a margem vazia. As margens numéricas foram verificadas na tabela do Lab.
- Cinematic View, nos dois casos: o Studio iniciou o processo `Godot_v4.7.2-stable_win64.exe` com `--rendering-driver d3d12` (linha de comandos lida ao sistema operativo), o registo do módulo diz `D3D12 12_0 - Forward+ - AMD Radeon RX 7700 XT` sem `ERROR`, e a linha `FIRST_FRAME` apareceu 13,6 s (aterragem) e 12,1 s (subida) depois do clique (perfil Auto, que escolheu High).
- O Studio não passa `--shot` ao módulo. As imagens `cinematic/cinematic-landing.png` e `cinematic-ascent.png` (ambiente Wallops Island, escolhido pelo percurso) vêm de uma segunda execução, separada, do módulo instalado com os mesmos argumentos lidos do processo iniciado pelo Studio, `--t` a 55 % da duração do registo e `--shot`. Mostram só a cena do módulo.

## Desempenho (Direct3D 12 / WebView2)

Medido fora da simulação, no instalador final e no módulo 0.2.5, uma execução de cada.

Vista geoespacial e leitor, `python desktop/studio/tests/perf_probe.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --flow m16` (janela 1440x900, biblioteca temporária; `perf/perf-m16.json`):

| Medida | Valor |
| --- | --- |
| Arranque a frio até ao ecrã pronto | 0,98 s |
| Clique até à aterragem no ecrã | 0,27 s |
| Passagem à vista geoespacial até ao terreno na GPU | 0,465 s |
| Frames em reprodução (engenharia / geoespacial / Flight console) | p50 17,8 / 17,8 / 17,8 ms; p99 18,9 / 18,9 / 18,8 ms; nenhum acima de 33 ms |
| CPU em reprodução (de um núcleo) | 23 % / 40 % / 4 % |
| Memória (working set) em reprodução geoespacial | 870 MB; 653 MB depois de sair do leitor |
| Sessão de 180 s, p99 dos frames | 18,6 a 19,1 ms; working set de 1014 para 883 MB |
| GPU dedicada, utilização 3D na vista geoespacial | 465 MB, 24,6 % |
| Pedidos da WebView a fora da máquina | nenhum |

**A cadência dos frames é de cerca de 18 ms (55 Hz), contra 8 ms (125 Hz) na verificação de 12 de novembro, e o Studio não é a causa.** O controlo `perf/raf-control.json` mede `requestAnimationFrame` na mesma janela do Studio: na página inicial parada p50 18,0 ms (p99 19,3) e numa página em branco (`data:text/html`) p50 18,1 ms (p99 19,2). Uma página vazia tem o mesmo ritmo, por isso o ritmo é o da janela ou do compositor nesta sessão; o controlador continua a indicar 165 Hz. Não foi investigado e as séries de dias diferentes não são comparáveis entre si.

Cinematic View, módulo instalado, `python scripts/cinematic/bench.py --godot <Godot_v4.7.2-stable_win64_console.exe do módulo> --project <project do módulo> --run tests/fixtures/cinematic/landing-run --env <environments/cape-canaveral instalado> --out <pasta> --profiles auto,balanced --seconds 12 --driver d3d12` (1440x900, sem sincronização vertical, câmara Auto; `perf/bench-*.json`, `perf/summary.json`):

| Perfil | Arranque até ao primeiro frame | Frame p50 | Frame p99 | Memória de vídeo | Working set (pico) | Bytes privados (pico) |
| --- | --- | --- | --- | --- | --- | --- |
| Auto (escolheu High) | 13,5 s | 3,20 ms | 13,57 ms | 2386 MB | 747 MB | 3066 MB |
| Balanced | 11,4 s | 1,90 ms | 5,36 ms | 1336 MB | 715 MB | 1872 MB |

Os dois ficam dentro do orçamento de 16,7 ms (60 Hz) no p99.

## Verificação do repositório

Ver `verification.txt`: lista do `AGENTS.md` na raiz e em `desktop/`, testes Python com `VV_GODOT` definido (434 testes, 6 ignorados por dependências opcionais; o teste Node corre e não é ignorado, também numa cópia em «v&v lab») e a campanha `--seeds 42,1337,2026`. Na árvore da terceira passagem (e da segunda) correram `cargo fmt --check`, `clippy -D warnings` e `cargo test` na raiz e em `desktop/` (37 suites, 304 testes) e o `unittest` (434 testes, OK). A campanha e a compilação de lançamento da raiz não foram repetidas porque a raiz não mudou desde a verificação anterior. As edições de `ui_smoke.py` (o texto de segurança da vista de execução) **não foram executadas**: esse teste só corre no CI com o instalador e continua informativo lá.

Comandos do README: `cargo run -- run ...` falhava porque o pacote da raiz tem três binários. Acrescentar `default-run = "vv-lab"` ao `Cargo.toml` da raiz resolve-o, mas muda o `source_sha256` do `vv-lab` (calculado a partir do `Cargo.toml`) e a paridade do problema D1 do benchmark M14 deixa de passar. Por isso os comandos do README, de `docs/reproducibility.md` e de `docs/m2-results.md` passaram a `cargo run --bin vv-lab -- ...` e o `Cargo.toml` ficou como estava.

## O que não foi verificado

- Não houve observação de pessoas: são verificações automatizadas do que o ecrã e a lista de processos mostram.
- A reversão para o 0.17.0 não foi executada, só os hashes foram verificados. A compatibilidade do Studio 0.17.0 com o módulo 0.2.5 não foi testada.
- Não se capturou a janela do processo iniciado pelo Studio (evitam-se capturas do ambiente de trabalho); as imagens da cena vêm de uma segunda execução do mesmo módulo com os mesmos argumentos.
- A subida só foi medida no arranque; `bench.py` correu só sobre o registo de aterragem.
- A diferença de ambiente que a primeira revisão viu na Cinematic View não foi reproduzida (ver acima).
- O contraste de texto sobre imagens, a dica do rótulo de qualidade do módulo e o uso com tecnologia de apoio não foram verificados.
- O contrato de `ui_smoke.py` foi atualizado mas não executado.
- O aspeto do novo painel de reprodução do módulo (rótulos, linhas que quebram) só foi visto a 1440x900 e 1100x700 com uma captura de cada, sem as regiões de erro de janelas muito estreitas.
- O módulo é 0.2.5: cada passagem do módulo pedia uma versão nova (0.2.2 e 0.2.3 foram intermédios).
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
| 0.18.1 (instalado) | `VV Lab Studio_0.18.1_x64-setup.exe` | `29a4d131430be7440f8d90212f821c9920286486fcb0cd3220e9a8ab163a2c46` |

Para voltar ao 0.17.0: confirmar o hash com `Get-FileHash "<pasta de recuperação>\VV Lab Studio_0.17.0_x64-setup.exe" -Algorithm SHA256`, fechar o Studio e executar o instalador com `/S`. A biblioteca em `Documentos\VV Lab Library` e o módulo em `%LOCALAPPDATA%\org.vvlab.studio\modules\cinematic` não pertencem ao instalador e ficam como estão.

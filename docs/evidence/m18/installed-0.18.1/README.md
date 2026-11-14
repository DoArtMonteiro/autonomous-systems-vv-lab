# Studio 0.18.1 instalado: verificação no Windows

Esta pasta guarda a verificação do V&V Lab Studio 0.18.1 **instalado** (instalador NSIS, execução silenciosa por cima do 0.17.0), não do executável da pasta de compilação. Os percursos correram contra `%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe`, com o módulo Cinematic 0.2.3 instalado pelo código de instalação do próprio Studio. Nenhuma captura do ambiente de trabalho foi guardada: as imagens da pasta `cinematic/` foram desenhadas pelo módulo (`--shot`) ou são a janela do próprio módulo (`boot-splash-window.png`, da 0.2.1; a imagem de arranque não mudou), e só contêm a cena ou a imagem de arranque.

Em relação ao `main` (`66b30ca`) a versão 0.18.1 muda o número de versão do Studio, acrescenta o estado «Opening the Cinematic View...» e, depois da revisão independente das capturas do 0.18.1, uma passagem de correções de interface (secção «Passagem de correções de interface»). O módulo passa de 0.2.0 a 0.2.3. Os testes mudaram: `m17_cinematic_journey.py` espera pelo primeiro frame e verifica o estado novo, `installed_spotcheck.py` automatiza o percurso de utilizador e `ux_journeys.py` verifica as correções.

## Máquina

AMD Ryzen 7 7800X3D (8 núcleos, 16 fios), 31,7 GB de RAM, AMD Radeon RX 7700 XT (controlador 32.0.31041.3013), Windows 11 Pro compilação 26300, WebView2 156.0.4314.58, Godot 4.7.2-stable, Python 3.14.6. O Microsoft Defender ficou ativo durante todo o trabalho e não foi alterado. Os números são desta máquina e não descrevem outras.

## Artefactos

| Artefacto | Tamanho | SHA-256 |
| --- | --- | --- |
| `VV Lab Studio_0.18.1_x64-setup.exe` (o instalado e verificado) | 42 439 712 bytes | `a3663b5f7332a873e1be7f70ad6208901230a4ba981dc80320d9ec11cb33d925` |
| `vv-cinematic-0.2.3.zip` (78 ficheiros, 449 763 694 bytes em disco) | 345 000 148 bytes | `1b021bf018e8bdb637d8c28f333ea063d435d9d6a237c18c444dd6f51c5da547` |

O instalador foi construído com `desktop/build.ps1` (compilação de lançamento completa): **código de saída 0**, capturado pelo invólucro que o executou (`BUILD EXIT 0`). Como o 0.18.1 ainda não foi publicado fora deste PC, o número de versão ficou e os instaladores anteriores deste número foram guardados na pasta de recuperação com nomes que dizem o que são: `VV Lab Studio_0.18.1_x64-setup-prebuild.exe` (a primeira versão, `b0c2cf41...`) e `VV Lab Studio_0.18.1_x64-setup-before-ux-pass.exe` (a que tinha o estado «Opening...» mas ainda não as correções de interface, `953c3f13...`). `SHA256SUMS.txt` (esta pasta) resume os hashes relevantes; a lista completa está na pasta de recuperação do proprietário, e os oito instaladores ali foram verificados contra ela.

## Instalação

- Antes da primeira instalação, o hash do instalador de recuperação 0.17.0 foi confirmado contra o `SHA256SUMS.txt`.
- O 0.18.1 foi instalado por cima do 0.17.0 e, depois, duas vezes por cima de si próprio à medida que o instalador mudou (primeira versão, versão com o estado «Opening...», versão final), sempre com `/S`: código de saída 0; a chave `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\VV Lab Studio` ficou com `DisplayVersion` 0.18.1 e o executável instalado declara a versão 0.18.1.
- Biblioteca do utilizador (`Documentos\VV Lab Library`): 11 corridas antes e depois de todas as instalações e de todos os percursos, mesma lista de identificadores, e o SHA-256 da lista ordenada dos 89 ficheiros da biblioteca é idêntico ao de antes da primeira instalação.
- Módulo Cinematic: instalado pelo teste opcional `real_module_zip_installs_when_given` de `desktop/studio/src/modules.rs` (`VV_CINEMATIC_ZIP`, `VV_CINEMATIC_INSTALL_TO` a apontar para a pasta real de módulos), porque o diálogo nativo não é automatizável. Substituiu as versões anteriores; o Studio instalado lê `installed: true, verified: true, version: 0.2.3`.
- O percurso `m17_cinematic_journey.py` desinstala o módulo no fim; por isso o módulo é reinstalado da mesma forma depois dele. No fim de tudo, o módulo 0.2.3 está instalado e verificado e não ficou nenhum processo do Studio nem do Godot.

## Percursos contra o executável instalado (instalador final, módulo 0.2.3)

| Percurso | Resultado | Registo |
| --- | --- | --- |
| `m15_journeys.py` | 48/48 | `m15-journeys.txt` |
| `m16_journeys.py` | 78/78 | `m16-journeys.txt` |
| `m17_lab_journeys.py` (porta 9273) | 34/34 | `m17-lab-journeys.txt` |
| `m17_cinematic_journey.py --preinstalled` | 11/11 | `m17-cinematic-journey.txt` |
| `m18_journeys.py` | 72/72 | `m18-journeys.txt`, `m18-numbers.json` |
| `installed_spotcheck.py` | 40/40 | `installed-spotcheck.txt`, `installed-spotcheck-facts.json` |
| `ux_journeys.py` (novo) | 70/70 | `ux-journeys.txt`, `ux-facts.json` |

Todos usam bibliotecas e configuração temporárias (`VVLAB_LIBRARY`, `VVLAB_CONFIG`), por isso não tocam na biblioteca do utilizador. Os caminhos temporários aparecem nos registos como `<temporary folder>`. Os mesmos percursos já tinham passado contra as versões anteriores do 0.18.1 (48, 78, 34, 11, 72 e 40), e o `ux_journeys.py` falhou 2 de 70 verificações na primeira execução contra o instalador final, por o teste esperar «Heavy return stage» quando o catálogo chama ao veículo «41 t heavy return stage» (o produto estava certo; o teste foi corrigido).

**Uma falha encontrada e corrigida (teste, não produto).** Na primeira execução com o módulo 0.2.0, `m17_cinematic_journey.py` deu 8/9: a verificação «o módulo desenhou o primeiro frame» falhou porque o percurso lia o registo do Godot após uma espera fixa de 12 s e o primeiro frame chega 12 a 16 s depois do clique. O processo estava a arrancar com Direct3D 12 sem erros; o percurso passou a esperar pela linha `FIRST_FRAME` (até 90 s) e a ignorar registos anteriores ao clique.

## A espera pelo primeiro frame

O módulo descodifica os ativos CC0 ao arrancar, por isso passam 12 a 16 s entre o clique em «Cinematic view» e o primeiro frame (15,6 s na aterragem e 13,7 s na subida no percurso de utilizador final). Duas mudanças:

- Studio (`desktop/studio/ui/js/cinematic.js`): depois do lançamento aparece o estado «Opening the Cinematic View in its own window. The first frame takes about 15 seconds.» (`role="status"`), que fica 30 s ou até ser dispensado. O percurso verifica que existe logo a seguir ao clique e que ainda lá está 6 s depois. Não se verificou o que acontece se a janela do módulo for fechada antes dos 30 s (o estado continua até ao fim do prazo).
- Módulo 0.2.1 (`desktop/cinematic/project.godot`, `assets/boot-splash.png`): `boot_splash` com fundo escuro e o texto «Cinematic View. Opening the replay. The first frame takes about 15 seconds.», sem logótipos. O empacotador copia `assets/` e o manifesto lista o ficheiro com tamanho e SHA-256. Medido: a janela do Godot aparece 0,9 s depois do arranque do processo e mostra a imagem (`cinematic/boot-splash-window.png`, captura da própria janela do módulo com `PrintWindow`) enquanto a cena é construída, que demora cerca de 14 s; a janela respondia aos 14,6 s e aos 20 s. A primeira imagem gerada tinha 720x180 e o Godot ampliou-a até ficar cortada; a final tem 1440x900 e coincide com a janela. Não se mediu o aspeto em janelas de outros tamanhos.

## Passagem de correções de interface

Uma revisão independente das capturas do 0.18.1 instalado (veredicto «boa, com lacunas») levou a esta passagem. `ux_journeys.py` verifica cada ponto no executável instalado:

| Ponto da revisão | O que o percurso verifica |
| --- | --- |
| Segurança sem «safe» sozinho | Compare (legenda das corridas e linha «Safety rules»), Lab, Library, vista de execução e leitor dizem «No safety rule broken (5 checked)»; uma nota diz que a velocidade de contacto é um requisito da missão e que um aterrar duro falha um requisito sem quebrar uma regra de segurança |
| Duas corridas lêem-se como diferentes | cabeçalho «Largest change: Vertical speed at contact 1.658 → 60.08 m/s (limit <= 3 m/s)» em Compare e no Lab; cada célula tem valor observado e margem, e a linha tem o limite; «9 rows differ ... 1 in its verdict, the others in a value»; linhas que falham primeiro; 4 algarismos significativos com o valor completo na dica; inclinação em graus; nomes de requisitos repetidos da subida distinguidos pelo andar |
| Cartão do leitor | «Not met: Horizontal speed at contact 1.584 m/s (limit <= 1 m/s); impact not modelled» na corrida de base e «Not met: Vertical speed at contact 60.08 m/s (limit <= 3 m/s), and 1 more not met; impact not modelled» na experiência |
| Cinematic View | com duas corridas o leitor deixa escolher qual abre (cada uma foi aberta: o `--run` da linha de comandos do processo é o identificador escolhido); o processo recebe `--run-label`, `--vehicle`, `--seed 5000` e `--exploratory`; o `--env` é o do ambiente que o leitor tinha (Wallops Island) nas duas corridas |
| Texto | declaração «Exploratory models, not real vehicles; nothing is validated against flight data.» em Mission Control e no hangar; sem «validated offline»; «recomputed model behaviour»; uma só etiqueta «Open in Experiment Lab» no hangar, no leitor e na vista de execução |
| Navegação a 820 px | sem barra de deslocamento; Configure, Analyse, Compare e Records no menu «More»; Enter abre, as setas e End movem, Escape fecha e devolve o foco, Enter em «Records» abre a Library; a 1440 px o menu não aparece |
| Lab | «Run experiment» visível desde o início, desligado com «Change one condition first» (descrito por `aria-describedby`); a coluna das condições sem deslocamento próprio; botões de sementes desligados com «Run an experiment first.» |
| Ambientes | 8 descrições sem corte, «Terrain is context only» em cada cartão, estado do módulo resolvido (ver o registo para o tempo) |
| Uma cor para Exploratory | o chip do Lab e o do hangar têm a mesma cor calculada; o leitor mostra «Reference case» ou «Exploratory» por corrida |
| 1024x640 e tamanho do texto | atribuição e barra de câmaras sem sobreposição na vista geoespacial; nenhum texto abaixo de 12 px em Mission Control, hangar, ambientes, Lab, Compare, leitor e leitor a 1024x640 |

**Sobre o ambiente da Cinematic View.** A revisão viu «Cape» na Cinematic View e «Wallops» no leitor. Não consegui reproduzir a diferença: nas duas corridas abertas o `--env` do processo era `wallops-island`, o ambiente escolhido em Environments e mantido pelo leitor. O percurso fica a verificar isto; se a diferença voltar, o primeiro suspeito é um leitor aberto antes de o ambiente ser escolhido, que usa o valor por omissão (Cape) até a preferência ser lida.

Na vista da Cinematic View (módulo 0.2.3, `cinematic/cinematic-hud-experiment.png`, desenhada pelo módulo com os argumentos que o Studio lhe passou): linha da corrida («Engine thrust 0.7 × (9e6edb2e) | seed 5000 | 41 t heavy return stage (exploratory, not a real vehicle)»), «altitude», «speed |v|» (o comprimento do vetor de velocidade gravado), acelerador em percentagem, a linha «reads the recorded sample at t» mais discreta, e «Graphics: auto» sem corte (a razão completa fica na dica). Não se verificou a dica com o rato.

**Não verificado.** O contraste das sobreposições sobre imagens (atribuições) não foi medido; só as razões de luminância dos cinzentos de apoio sobre os fundos dos painéis (5,7:1 ou mais no tema escuro, calculadas dos tokens). Os botões e menus não foram observados com tecnologia de apoio. Para a re-revisão guardaram-se, fora do repositório, capturas novas dos mesmos ecrãs da revisão (Mission Control, hangar, ambientes, Lab antes e depois da corrida, Compare, leitor, leitor geoespacial a 1024x640, navegação a 820 px com o menu aberto).

## Percurso de utilizador no Studio instalado

`installed_spotcheck.py` percorre: Mission Control, hangar de veículos, «Open in Experiment Lab» do andar pesado (41 t) com o impulso × 0,7, Compare, leitor com a vista Engineering e Cinematic View para a corrida de **aterragem**; depois o lançador pequeno com carga útil de 600 kg, o leitor e a Cinematic View para a corrida de **subida**.

- Aterragem (semente 5000, controlador robusto): velocidade vertical no contacto 1,66 m/s (passa) contra 60,08 m/s (falha) com o impulso × 0,7; em Compare as etiquetas diferem («Engine thrust 1 × (default)» e «Engine thrust 0.7 ×») e nenhuma está truncada.
- Subida: a carga útil de 600 kg passa a corrida de «Orbit» para «Suborbital» (R4, R6 e R8 falham); o Lab mostra margens numéricas (por exemplo «-329 Pa» na pressão dinâmica máxima) e nenhum requisito com números mostra a margem vazia. As margens numéricas foram verificadas na tabela do Lab.
- Cinematic View, nos dois casos: o Studio iniciou o processo `Godot_v4.7.2-stable_win64.exe` com `--rendering-driver d3d12` (linha de comandos lida ao sistema operativo), o registo do módulo diz `D3D12 12_0 - Forward+ - AMD Radeon RX 7700 XT` sem `ERROR`, e a linha `FIRST_FRAME` apareceu 14,7 s (aterragem) e 12,6 s (subida) depois do clique (perfil Auto, que escolheu High).
- O Studio não passa `--shot` ao módulo. As imagens `cinematic/cinematic-landing.png` e `cinematic-ascent.png` vêm de uma segunda execução, separada, do módulo instalado com os mesmos argumentos lidos do processo iniciado pelo Studio, `--t` a 55 % da duração do registo e `--shot`. Mostram só a cena do módulo.

## Desempenho (Direct3D 12 / WebView2)

Medido fora da simulação, no instalador final e no módulo 0.2.3; o `perf_probe` correu duas vezes (`perf/perf-m16.json` e `perf/perf-m16-second.json`), o `bench.py` uma.

Vista geoespacial e leitor, `python desktop/studio/tests/perf_probe.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --flow m16` (janela 1440x900, biblioteca temporária):

| Medida | 1.ª execução | 2.ª execução |
| --- | --- | --- |
| Arranque a frio até ao ecrã pronto | 0,94 s | 0,97 s |
| Clique até à aterragem no ecrã | 0,26 s | 0,29 s |
| Passagem à vista geoespacial até ao terreno na GPU | 0,469 s | 0,478 s |
| Frames em reprodução (engenharia / geoespacial / Flight console) | p50 17,7 a 18,0 ms; p99 18,7 a 19,0 ms; nenhum acima de 33 ms | p50 17,9 a 18,0 ms; p99 18,6 a 18,8 ms; nenhum acima de 33 ms |
| CPU em reprodução (de um núcleo) | 30 % / 36 % / 3 % | 24 % / 37 % / 29 % |
| Memória (working set) em reprodução geoespacial | 862 MB; 649 MB depois de sair do leitor | 852 MB |
| Sessão de 180 s, p99 dos frames | 18,5 a 19,0 ms; working set de 1024 para 881 MB | 18,6 a 19,1 ms; de 933 para 907 MB |
| GPU dedicada, utilização 3D na vista geoespacial | 461 MB, 24,3 % | 464 MB, 24,8 % |
| Pedidos da WebView a fora da máquina | nenhum | nenhum |

**A cadência dos frames mudou desde a verificação anterior** (8,0 ms, cerca de 125 Hz, na execução de 12 de novembro; agora 18 ms, cerca de 55 Hz, nas duas execuções de hoje, também com a janela parada: o `idle_frames` está nos 18 ms). O controlador continua a indicar 165 Hz para o ecrã. A causa não foi investigada (suspeita-se do ritmo do compositor ou do modo do ecrã, não do Studio, que não mudou o desenho), por isso nenhum destes números mede a capacidade máxima de desenho e as duas séries não são comparáveis entre si. A vista geoespacial gastou menos CPU (36 % contra 52 a 73 % da série anterior), mas isso também pode ser só a cadência.

Cinematic View, módulo instalado, `python scripts/cinematic/bench.py --godot <Godot_v4.7.2-stable_win64_console.exe do módulo> --project <project do módulo> --run tests/fixtures/cinematic/landing-run --env <environments/cape-canaveral instalado> --out <pasta> --profiles auto,balanced --seconds 12 --driver d3d12` (1440x900, sem sincronização vertical, câmara Auto; `perf/bench-*.json`, `perf/summary.json`):

| Perfil | Arranque até ao primeiro frame | Frame p50 | Frame p99 | Memória de vídeo | Working set (pico) | Bytes privados (pico) |
| --- | --- | --- | --- | --- | --- | --- |
| Auto (escolheu High) | 14,1 s | 3,25 ms | 13,64 ms | 2385 MB | 746 MB | 3065 MB |
| Balanced | 12,2 s | 1,94 ms | 5,36 ms | 1335 MB | 714 MB | 1872 MB |

Os dois ficam dentro do orçamento de 16,7 ms (60 Hz) no p99; os valores são os do módulo anterior (14,9 s e 12,3 s; p99 13,58 e 5,39 ms) dentro do ruído de uma execução.

## Verificação do repositório

Ver `verification.txt`: lista do `AGENTS.md` na raiz e em `desktop/`, testes Python com `VV_GODOT` definido (432 testes, 6 ignorados por dependências opcionais) e a campanha `--seeds 42,1337,2026`. A lista foi repetida na árvore da passagem de interface (`cargo fmt --check`, `clippy -D warnings`, `cargo test` na raiz e em `desktop/`, e `unittest`); a campanha e a compilação de lançamento da raiz não foram repetidas depois de a passagem tocar só em interface, módulo, testes e documentação (a raiz não mudou desde a verificação anterior).

Comandos do README: `cargo run -- run ...` falhava porque o pacote da raiz tem três binários. Acrescentar `default-run = "vv-lab"` ao `Cargo.toml` da raiz resolve-o, mas muda o `source_sha256` do `vv-lab` (calculado a partir do `Cargo.toml`) e a paridade do problema D1 do benchmark M14 deixa de passar. Por isso os comandos do README, de `docs/reproducibility.md` e de `docs/m2-results.md` passaram a `cargo run --bin vv-lab -- ...` e o `Cargo.toml` ficou como estava.

## O que não foi verificado

- Não houve observação de pessoas: são verificações automatizadas do que o ecrã e a lista de processos mostram.
- A reversão para o 0.17.0 não foi executada, só os hashes foram verificados. A compatibilidade do Studio 0.17.0 com o módulo 0.2.3 não foi testada.
- Não se capturou a janela do processo iniciado pelo Studio (evitam-se capturas do ambiente de trabalho); as imagens da cena vêm de uma segunda execução do mesmo módulo com os mesmos argumentos.
- A subida só foi medida no arranque; `bench.py` correu só sobre o registo de aterragem.
- A causa da cadência de frames da WebView não foi investigada (ver o desempenho).
- A lista do `AGENTS.md` foi repetida em parte depois das últimas alterações (ver acima).
- A diferença de ambiente que a revisão viu na Cinematic View não foi reproduzida.

## Recuperação (rollback)

Instaladores e hashes (os mesmos de `SHA256SUMS.txt`):

| Versão | Ficheiro | SHA-256 |
| --- | --- | --- |
| 0.17.0 (a que estava instalada) | `VV Lab Studio_0.17.0_x64-setup.exe` | `ce9fa33a526518ea5438f7d2a30a9f6c71e5fbcca7cbd2fafef9251f9ddbc972` |
| 0.18.0 | `VV Lab Studio_0.18.0_x64-setup.exe` | `8ad87eba2f7223186a4a265eea06da6a88fef21878c1fb74bc630d554471fb46` |
| 0.18.1, primeira versão | `VV Lab Studio_0.18.1_x64-setup-prebuild.exe` | `b0c2cf4180219ec427e6157072d3291c2c71e6beda2a75d22b3f3d867a8597ee` |
| 0.18.1, antes da passagem de interface | `VV Lab Studio_0.18.1_x64-setup-before-ux-pass.exe` | `953c3f135ce581b97d5c3e96245c14064acc20a05e593cf20fc85ed3c394457d` |
| 0.18.1 (instalado) | `VV Lab Studio_0.18.1_x64-setup.exe` | `a3663b5f7332a873e1be7f70ad6208901230a4ba981dc80320d9ec11cb33d925` |

Para voltar ao 0.17.0: confirmar o hash com `Get-FileHash "<pasta de recuperação>\VV Lab Studio_0.17.0_x64-setup.exe" -Algorithm SHA256`, fechar o Studio e executar o instalador com `/S`. A biblioteca em `Documentos\VV Lab Library` e o módulo em `%LOCALAPPDATA%\org.vvlab.studio\modules\cinematic` não pertencem ao instalador e ficam como estão.

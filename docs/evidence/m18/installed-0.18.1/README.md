# Studio 0.18.1 instalado: verificação no Windows

Esta pasta guarda a verificação do V&V Lab Studio 0.18.1 **instalado** (instalador NSIS, execução silenciosa por cima do 0.17.0), não do executável da pasta de compilação. Os percursos correram contra `%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe`, com o módulo Cinematic 0.2.1 instalado pelo código de instalação do próprio Studio. Nenhuma captura do ambiente de trabalho foi guardada: as imagens da pasta `cinematic/` foram desenhadas pelo módulo (`--shot`) ou são a janela do próprio módulo (`boot-splash-window.png`), e só contêm a cena ou a imagem de arranque.

Em relação ao `main` (`66b30ca`) a versão 0.18.1 muda o número de versão do Studio (`desktop/studio/Cargo.toml`, `tauri.conf.json`, `desktop/Cargo.lock`) e acrescenta o estado «Opening the Cinematic View...» (ver «A espera pelo primeiro frame»). O módulo passa de 0.2.0 a 0.2.1 (só uma imagem de arranque). Os testes mudaram: `m17_cinematic_journey.py` espera pelo primeiro frame e verifica o estado novo, e `installed_spotcheck.py` automatiza o percurso de utilizador descrito abaixo.

## Máquina

AMD Ryzen 7 7800X3D (8 núcleos, 16 fios), 31,7 GB de RAM, AMD Radeon RX 7700 XT (controlador 32.0.31041.3013), Windows 11 Pro compilação 26300, WebView2 156.0.4314.58, Godot 4.7.2-stable, Python 3.14.6. O Microsoft Defender ficou ativo durante todo o trabalho e não foi alterado. Os números são desta máquina e não descrevem outras.

## Artefactos

| Artefacto | Tamanho | SHA-256 |
| --- | --- | --- |
| `VV Lab Studio_0.18.1_x64-setup.exe` (o instalado e verificado) | 42 431 773 bytes | `953c3f135ce581b97d5c3e96245c14064acc20a05e593cf20fc85ed3c394457d` |
| `vv-cinematic-0.2.1.zip` (78 ficheiros, 449 759 631 bytes em disco) | 344 998 893 bytes | `34b17290791aac5f62a0f95f9ae8371bb0a39fc9807311c0b37eeefc021892f1` |

O instalador foi construído com `desktop/build.ps1` (compilação de lançamento completa): **código de saída 0**, capturado pelo invólucro que o executou (`BUILD EXIT 0`). Uma versão anterior do 0.18.1, sem o estado «Opening the Cinematic View...» e sem o módulo 0.2.1 (42 429 115 bytes, SHA-256 `b0c2cf4180219ec427e6157072d3291c2c71e6beda2a75d22b3f3d867a8597ee`), foi a primeira instalada e verificada; como o 0.18.1 ainda não foi publicado fora deste PC, o número de versão ficou e o ficheiro foi renomeado na pasta de recuperação para `VV Lab Studio_0.18.1_x64-setup-prebuild.exe`. `SHA256SUMS.txt` (esta pasta) resume os hashes relevantes; a lista completa está na pasta de recuperação do proprietário, e os sete instaladores ali foram verificados contra ela.

## Instalação

- Antes da primeira instalação, o hash do instalador de recuperação 0.17.0 foi confirmado contra o `SHA256SUMS.txt`.
- Primeira instalação (versão anterior do 0.18.1) por cima do 0.17.0 e, depois, a do instalador final por cima desta, ambas com `/S`: código de saída 0; a chave `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\VV Lab Studio` ficou com `DisplayVersion` 0.18.1 e o executável instalado declara a versão 0.18.1.
- Biblioteca do utilizador (`Documentos\VV Lab Library`): 11 corridas antes e 11 depois das duas instalações e de todos os percursos, mesma lista de identificadores, e o SHA-256 da lista ordenada dos 89 ficheiros da biblioteca é idêntico ao de antes da primeira instalação.
- Módulo Cinematic: instalado pelo teste opcional `real_module_zip_installs_when_given` de `desktop/studio/src/modules.rs` (`VV_CINEMATIC_ZIP`, `VV_CINEMATIC_INSTALL_TO` a apontar para a pasta real de módulos), porque o diálogo nativo não é automatizável. Substituiu as versões 0.1.0 e 0.2.0; o Studio instalado lê `installed: true, verified: true, version: 0.2.1`.
- O percurso `m17_cinematic_journey.py` desinstala o módulo no fim; por isso o módulo é reinstalado da mesma forma depois dele. No fim de tudo, o módulo 0.2.1 está instalado e a pasta de módulos só tem essa versão.

## Percursos contra o executável instalado (instalador final, módulo 0.2.1)

| Percurso | Resultado | Registo |
| --- | --- | --- |
| `m15_journeys.py` | 48/48 | `m15-journeys.txt` |
| `m16_journeys.py` | 78/78 | `m16-journeys.txt` |
| `m17_lab_journeys.py` (porta 9273) | 34/34 | `m17-lab-journeys.txt` |
| `m17_cinematic_journey.py --preinstalled` | 11/11 | `m17-cinematic-journey.txt` |
| `m18_journeys.py` | 72/72 | `m18-journeys.txt`, `m18-numbers.json` |
| `installed_spotcheck.py` | 40/40 | `installed-spotcheck.txt`, `installed-spotcheck-facts.json` |

Os mesmos percursos já tinham passado contra a versão anterior do 0.18.1 com o módulo 0.2.0 (48, 78, 34, 9, 72 e 40, depois da correção ao teste descrita a seguir). Todos usam bibliotecas e configuração temporárias (`VVLAB_LIBRARY`, `VVLAB_CONFIG`), por isso não tocam na biblioteca do utilizador. Os caminhos temporários aparecem nos registos como `<temporary folder>`.

**Uma falha encontrada e corrigida (teste, não produto).** Na primeira execução com o módulo 0.2.0, `m17_cinematic_journey.py` deu 8/9: a verificação «o módulo desenhou o primeiro frame» falhou porque o percurso lia o registo do Godot após uma espera fixa de 12 s e o primeiro frame chega 12 a 16 s depois do clique. O processo estava a arrancar com Direct3D 12 sem erros; o percurso passou a esperar pela linha `FIRST_FRAME` (até 90 s) e a ignorar registos anteriores ao clique.

## A espera pelo primeiro frame

O módulo descodifica os ativos CC0 ao arrancar, por isso passam 12 a 16 s entre o clique em «Cinematic view» e o primeiro frame (15,6 s na aterragem e 13,7 s na subida no percurso de utilizador final). Duas mudanças:

- Studio (`desktop/studio/ui/js/cinematic.js`): depois do lançamento aparece o estado «Opening the Cinematic View in its own window. The first frame takes about 15 seconds.» (`role="status"`), que fica 30 s ou até ser dispensado. O percurso verifica que existe logo a seguir ao clique e que ainda lá está 6 s depois. Não se verificou o que acontece se a janela do módulo for fechada antes dos 30 s (o estado continua até ao fim do prazo).
- Módulo 0.2.1 (`desktop/cinematic/project.godot`, `assets/boot-splash.png`): `boot_splash` com fundo escuro e o texto «Cinematic View. Opening the replay. The first frame takes about 15 seconds.», sem logótipos. O empacotador copia `assets/` e o manifesto lista o ficheiro com tamanho e SHA-256. Medido: a janela do Godot aparece 0,9 s depois do arranque do processo e mostra a imagem (`cinematic/boot-splash-window.png`, captura da própria janela do módulo com `PrintWindow`) enquanto a cena é construída, que demora cerca de 14 s; a janela respondia aos 14,6 s e aos 20 s. A primeira imagem gerada tinha 720x180 e o Godot ampliou-a até ficar cortada; a final tem 1440x900 e coincide com a janela. Não se mediu o aspeto em janelas de outros tamanhos.

## Percurso de utilizador no Studio instalado

`installed_spotcheck.py` percorre: Mission Control, hangar de veículos, «Design and fly» do andar pesado (41 t) com o impulso × 0,7, Compare, leitor com a vista Engineering e Cinematic View para a corrida de **aterragem**; depois o lançador pequeno com carga útil de 600 kg, o leitor e a Cinematic View para a corrida de **subida**.

- Aterragem (semente 5000, controlador robusto): velocidade vertical no contacto 1,66 m/s (passa) contra 60,08 m/s (falha) com o impulso × 0,7; em Compare as etiquetas diferem («Engine thrust 1 × (default)» e «Engine thrust 0.7 ×») e nenhuma está truncada.
- Subida: a carga útil de 600 kg passa a corrida de «Orbit» para «Suborbital» (R4, R6 e R8 falham); o Lab mostra margens numéricas (por exemplo «-329 Pa» na pressão dinâmica máxima) e nenhum requisito com números mostra a margem vazia. As margens numéricas foram verificadas na tabela do Lab, não na vista Compare.
- Cinematic View, nos dois casos: o Studio iniciou o processo `Godot_v4.7.2-stable_win64.exe` com `--rendering-driver d3d12` (linha de comandos lida ao sistema operativo), o registo do módulo diz `D3D12 12_0 - Forward+ - AMD Radeon RX 7700 XT` sem `ERROR`, e a linha `FIRST_FRAME` apareceu (perfil Auto, que escolheu High).
- O Studio não passa `--shot` ao módulo. As imagens `cinematic/cinematic-landing.png` e `cinematic-ascent.png` vêm de uma segunda execução, separada, do módulo instalado com os mesmos argumentos `--run` e `--env` lidos do processo iniciado pelo Studio, `--t` a 55 % da duração do registo e `--shot`. Mostram só a cena do módulo.

## Desempenho (Direct3D 12 / WebView2)

Medido fora da simulação, uma execução de cada, no instalador final e no módulo 0.2.1.

Vista geoespacial e leitor, `python desktop/studio/tests/perf_probe.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --flow m16` (janela 1440x900, biblioteca temporária; `perf/perf-m16.json`):

| Medida | Valor |
| --- | --- |
| Arranque a frio até ao ecrã pronto | 1,39 s |
| Clique até à aterragem no ecrã | 0,98 s |
| Passagem à vista geoespacial até ao terreno na GPU | 0,467 s |
| Frames em reprodução (engenharia / geoespacial / Flight console) | p50 8,0 ms; p99 8,5 ms nas três; nenhum frame acima de 33 ms |
| CPU em reprodução (de um núcleo) | 31 % / 73 % / 56 % |
| Memória (working set) em reprodução geoespacial | 874 MB; 797 MB depois de sair do leitor |
| Sessão de 180 s, p99 dos frames | 8,1 a 8,8 ms; working set de 927 para 933 MB |
| Pedidos da WebView a fora da máquina | nenhum |
| GPU dedicada e utilização 3D | os contadores devolveram 0 nesta execução (inválido); na execução anterior do 0.18.1, 467 MB e 42,7 % na vista geoespacial |

Os frames de 8 ms (cerca de 125 Hz) ficam abaixo dos 165 Hz que o controlador indica para o ecrã. **A causa desse limite de cadência não foi investigada**, por isso estes números não medem a capacidade máxima de desenho.

Cinematic View, módulo instalado, `python scripts/cinematic/bench.py --godot <Godot_v4.7.2-stable_win64_console.exe do módulo> --project <project do módulo> --run tests/fixtures/cinematic/landing-run --env <environments/cape-canaveral instalado> --out <pasta> --profiles auto,balanced --seconds 12 --driver d3d12` (1440x900, sem sincronização vertical, câmara Auto; `perf/bench-*.json`, `perf/summary.json`):

| Perfil | Arranque até ao primeiro frame | Frame p50 | Frame p99 | Memória de vídeo | Working set (pico) | Bytes privados (pico) |
| --- | --- | --- | --- | --- | --- | --- |
| Auto (escolheu High) | 14,9 s | 3,24 ms | 13,58 ms | 2411 MB | 741 MB | 3064 MB |
| Balanced | 12,3 s | 1,94 ms | 5,39 ms | 1356 MB | 709 MB | 1871 MB |

Os dois ficam dentro do orçamento de 16,7 ms (60 Hz) no p99. Os valores do módulo 0.2.0 foram praticamente iguais (13,9 s e 11,6 s; p99 13,55 e 5,38 ms), como esperado: a imagem de arranque não acelera o arranque, só o torna visível.

## Verificação do repositório

Ver `verification.txt`: lista do `AGENTS.md` na raiz e em `desktop/`, testes Python com `VV_GODOT` definido (427 testes, 6 ignorados por dependências opcionais) e a campanha `--seeds 42,1337,2026`. Esta verificação foi feita na árvore do commit `chore: Studio 0.18.1`; as alterações posteriores tocam em JavaScript do Studio, um ficheiro de projeto do módulo, testes de percurso e documentação, e foram cobertas pelos percursos acima e pela compilação do instalador, mas a lista completa do `AGENTS.md` não foi repetida depois delas.

Comandos do README: `cargo run -- run ...` falhava porque o pacote da raiz tem três binários. Acrescentar `default-run = "vv-lab"` ao `Cargo.toml` da raiz resolve-o, mas muda o `source_sha256` do `vv-lab` (calculado a partir do `Cargo.toml`) e a paridade do problema D1 do benchmark M14 deixa de passar (`python scripts/m14_benchmark.py --split development` saiu com código 1, «parity False»). Por isso os comandos do README, de `docs/reproducibility.md` e de `docs/m2-results.md` passaram a `cargo run --bin vv-lab -- ...` e o `Cargo.toml` ficou como estava. Depois disso saíram com código 0: `cargo run --bin vv-lab -- run` e `replay` do cenário básico, `cargo build --release --manifest-path exec/Cargo.toml`, `python scripts/m14_benchmark.py --split development --output-root exec/out/m14-dev` e `python scripts/m14_fragility.py --output-root exec/out/m14-fragility` (os comandos `vv-rocket` do README já tinham saído com 0). Os restantes comandos de `docs/reproducibility.md` (`analyze`, `run-m4`, `compare-m4`, `replay-m4`) foram só reescritos, não executados.

## O que não foi verificado

- Não houve observação de pessoas: são verificações automatizadas do que o ecrã e a lista de processos mostram.
- A reversão para o 0.17.0 não foi executada, só os hashes foram verificados. A compatibilidade do Studio 0.17.0 com o módulo 0.2.1 não foi testada.
- Não se capturou a janela do processo iniciado pelo Studio (evitam-se capturas do ambiente de trabalho); as imagens da cena vêm de uma segunda execução do mesmo módulo.
- A subida só foi medida no arranque; `bench.py` correu só sobre o registo de aterragem.
- A lista do `AGENTS.md` não foi repetida depois das últimas alterações (ver acima).

## Recuperação (rollback)

Instaladores e hashes (os mesmos de `SHA256SUMS.txt`):

| Versão | Ficheiro | SHA-256 |
| --- | --- | --- |
| 0.17.0 (a que estava instalada) | `VV Lab Studio_0.17.0_x64-setup.exe` | `ce9fa33a526518ea5438f7d2a30a9f6c71e5fbcca7cbd2fafef9251f9ddbc972` |
| 0.18.0 | `VV Lab Studio_0.18.0_x64-setup.exe` | `8ad87eba2f7223186a4a265eea06da6a88fef21878c1fb74bc630d554471fb46` |
| 0.18.1 anterior (sem o estado «Opening...») | `VV Lab Studio_0.18.1_x64-setup-prebuild.exe` | `b0c2cf4180219ec427e6157072d3291c2c71e6beda2a75d22b3f3d867a8597ee` |
| 0.18.1 (instalado) | `VV Lab Studio_0.18.1_x64-setup.exe` | `953c3f135ce581b97d5c3e96245c14064acc20a05e593cf20fc85ed3c394457d` |

Para voltar ao 0.17.0: confirmar o hash com `Get-FileHash "<pasta de recuperação>\VV Lab Studio_0.17.0_x64-setup.exe" -Algorithm SHA256`, fechar o Studio e executar o instalador com `/S`. A biblioteca em `Documentos\VV Lab Library` e o módulo em `%LOCALAPPDATA%\org.vvlab.studio\modules\cinematic` não pertencem ao instalador e ficam como estão.

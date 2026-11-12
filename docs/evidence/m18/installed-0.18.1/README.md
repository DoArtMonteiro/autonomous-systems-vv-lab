# Studio 0.18.1 instalado: verificação no Windows

Esta pasta guarda a verificação do V&V Lab Studio 0.18.1 **instalado** (instalador NSIS, execução silenciosa por cima do 0.17.0), não do executável da pasta de compilação. Os percursos correram contra `%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe`, com o módulo Cinematic 0.2.0 instalado pelo código de instalação do próprio Studio. Nenhuma captura do ambiente de trabalho foi guardada: as duas imagens da pasta `cinematic/` foram desenhadas pelo módulo (`--shot`) e só contêm a cena.

A 0.18.1 muda apenas o número de versão do Studio (`desktop/studio/Cargo.toml`, `tauri.conf.json`, `desktop/Cargo.lock`) em relação ao `main` (`66b30ca`). Duas alterações de testes acompanham-na: o percurso `m17_cinematic_journey.py` espera pelo primeiro frame em vez de dormir 12 s, e o novo `installed_spotcheck.py` automatiza o percurso de utilizador descrito abaixo.

## Máquina

AMD Ryzen 7 7800X3D (8 núcleos, 16 fios), 31,7 GB de RAM, AMD Radeon RX 7700 XT (controlador 32.0.31041.3013), Windows 11 Pro compilação 26300, WebView2 156.0.4314.58, Godot 4.7.2-stable, Python 3.14.6. O Microsoft Defender ficou ativo durante todo o trabalho e não foi alterado. Os números são desta máquina e não descrevem outras.

## Artefactos

| Artefacto | Tamanho | SHA-256 |
| --- | --- | --- |
| `VV Lab Studio_0.18.1_x64-setup.exe` | 42 429 115 bytes | `b0c2cf4180219ec427e6157072d3291c2c71e6beda2a75d22b3f3d867a8597ee` |
| `vv-cinematic-0.2.0.zip` (77 ficheiros, 449 745 721 bytes em disco) | 344 991 820 bytes | `bbfb1ebe54d7fe66998d16769b1ef91e6df5a144f75c1802f89d256e1bbaea5d` |

Os hashes de todos os instaladores de recuperação estão em `SHA256SUMS.txt` (esta pasta) e na pasta de recuperação do proprietário. O instalador foi construído com `desktop/build.ps1` (compilação de lançamento completa).

## Instalação

- Antes de instalar, o hash do instalador de recuperação 0.17.0 foi confirmado contra o `SHA256SUMS.txt`.
- `VV Lab Studio_0.18.1_x64-setup.exe /S`: código de saída 0; a chave `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\VV Lab Studio` passou de `DisplayVersion` 0.17.0 para 0.18.1 e o executável instalado declara a versão 0.18.1.
- Biblioteca do utilizador (`Documentos\VV Lab Library`): 11 corridas antes e 11 depois, mesma lista de identificadores, e o SHA-256 da lista ordenada dos 89 ficheiros da biblioteca é idêntico antes e depois.
- Módulo Cinematic 0.2.0: instalado pelo teste opcional `real_module_zip_installs_when_given` de `desktop/studio/src/modules.rs` (`VV_CINEMATIC_ZIP`, `VV_CINEMATIC_INSTALL_TO` a apontar para a pasta real de módulos), porque o diálogo nativo não é automatizável. O estado lido pelo Studio instalado foi `installed: true, verified: true, version: 0.2.0`. A instalação substituiu a 0.1.0.
- O percurso `m17_cinematic_journey.py` desinstala o módulo no fim; o módulo foi reinstalado da mesma forma antes do percurso de utilizador e das medições, e fica instalado e verificado. No fim de todas as execuções (incluindo a repetição final desse percurso e a nova reinstalação), confirmou-se outra vez: `DisplayVersion` 0.18.1, módulo `installed: true, verified: true, version: 0.2.0` lido pelo Studio instalado, biblioteca com o mesmo SHA-256 e a mesma lista de 11 corridas, e nenhum processo do Studio ou do Godot ativo.

## Percursos contra o executável instalado

| Percurso | Resultado | Registo |
| --- | --- | --- |
| `m15_journeys.py` | 48/48 | `m15-journeys.txt` |
| `m16_journeys.py` | 78/78 | `m16-journeys.txt` |
| `m17_lab_journeys.py` (porta 9273) | 34/34 | `m17-lab-journeys.txt` |
| `m17_cinematic_journey.py --preinstalled` | 9/9 | `m17-cinematic-journey.txt` |
| `m18_journeys.py` | 72/72 | `m18-journeys.txt`, `m18-numbers.json` |
| `installed_spotcheck.py` | 40/40 | `installed-spotcheck.txt`, `installed-spotcheck-facts.json` |

Todos usam bibliotecas e configuração temporárias (`VVLAB_LIBRARY`, `VVLAB_CONFIG`), por isso não tocam na biblioteca do utilizador. Os caminhos temporários aparecem nos registos como `<temporary folder>`.

**Uma falha encontrada e corrigida (teste, não produto).** Na primeira execução, `m17_cinematic_journey.py` deu 8/9: a verificação «o módulo desenhou o primeiro frame» falhou. O percurso lia o registo do Godot após uma espera fixa de 12 s, mas com o módulo 0.2.0 o primeiro frame chega 12 a 15 s depois do clique (ver abaixo; a descodificação dos ativos CC0 ao arrancar, com a cache do Godot apagada em cada lançamento). O processo estava a arrancar e a usar Direct3D 12 sem erros; o percurso passou a esperar pela linha `FIRST_FRAME` (até 90 s) e deu 9/9.

## Percurso de utilizador no Studio instalado

`installed_spotcheck.py` percorre: Mission Control, hangar de veículos, «Design and fly» do andar pesado (41 t) com o impulso × 0,7, Compare, leitor com a vista Engineering e Cinematic View para a corrida de **aterragem**; depois o lançador pequeno com carga útil de 600 kg, o leitor e a Cinematic View para a corrida de **subida**.

- Aterragem (semente 5000, controlador robusto): velocidade vertical no contacto 1,66 m/s (passa) contra 60,08 m/s (falha) com o impulso × 0,7; em Compare as etiquetas diferem («Engine thrust 1 × (default)» e «Engine thrust 0.7 ×») e nenhuma está truncada.
- Subida: a carga útil de 600 kg passa a corrida de «Orbit» para «Suborbital» (R4, R6 e R8 falham); o Lab mostra margens numéricas (por exemplo «-329 Pa» na pressão dinâmica máxima) e nenhum requisito com números mostra a margem vazia.
- Cinematic View, nos dois casos: o Studio iniciou o processo `Godot_v4.7.2-stable_win64.exe` com `--rendering-driver d3d12` (linha de comandos lida ao sistema operativo), o registo do módulo diz `D3D12 12_0 - Forward+ - AMD Radeon RX 7700 XT` sem `ERROR`, e a linha `FIRST_FRAME` apareceu 14,7 s (aterragem) e 12,4 s (subida) depois do clique (perfil Auto, que escolheu High).
- O Studio não passa `--shot` ao módulo. As imagens `cinematic/cinematic-landing.png` e `cinematic-ascent.png` vêm de uma segunda execução, separada, do módulo instalado com os mesmos argumentos `--run` e `--env` lidos do processo iniciado pelo Studio, `--t` a 55 % da duração do registo e `--shot`. Mostram só a cena do módulo.

## Desempenho (Direct3D 12 / WebView2)

Medido fora da simulação, uma execução de cada.

Vista geoespacial e leitor, `python desktop/studio/tests/perf_probe.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --flow m16` (janela 1440x900, biblioteca temporária; `perf/perf-m16.json`):

| Medida | Valor |
| --- | --- |
| Arranque a frio até ao ecrã pronto | 1,04 s |
| Clique até à aterragem no ecrã | 0,25 s |
| Passagem à vista geoespacial até ao terreno na GPU | 0,455 s |
| Frames em reprodução (engenharia / geoespacial / Flight console) | p50 8,0 ms; p99 8,5 ms nas três; nenhum frame acima de 33 ms |
| CPU em reprodução (de um núcleo) | 37 % / 52 % / 61 % |
| Geoespacial: GPU dedicada, utilização 3D | 467 MB, 42,7 % |
| Memória (working set) em reprodução geoespacial | 879 MB; 801 MB depois de sair do leitor |
| Sessão de 180 s, p99 dos frames | 8,4 a 8,7 ms; working set de 905 para 939 MB |
| Pedidos da WebView a fora da máquina | nenhum |

Os frames de 8 ms (cerca de 125 Hz) ficam abaixo do ritmo de 165 Hz que o controlador indica para o ecrã; a causa do limite não foi determinada, por isso estes números não medem a capacidade máxima de desenho.

Cinematic View, módulo instalado, `python scripts/cinematic/bench.py --godot <Godot_v4.7.2-stable_win64_console.exe do módulo> --project <project do módulo> --run tests/fixtures/cinematic/landing-run --env <environments/cape-canaveral instalado> --out <pasta> --profiles auto,balanced --seconds 12 --driver d3d12` (1440x900, sem sincronização vertical, câmara Auto; `perf/bench-*.json`, `perf/summary.json`):

| Perfil | Arranque até ao primeiro frame | Frame p50 | Frame p99 | Memória de vídeo | Working set (pico) | Bytes privados (pico) |
| --- | --- | --- | --- | --- | --- | --- |
| Auto (escolheu High) | 13,9 s | 3,22 ms | 13,55 ms | 2411 MB | 726 MB | 3034 MB |
| Balanced | 11,6 s | 1,93 ms | 5,38 ms | 1356 MB | 709 MB | 1870 MB |

Os dois ficam dentro do orçamento de 16,7 ms (60 Hz) no p99. O arranque de 12 a 15 s é lento para quem clica; não foi verificado se o Studio ou o módulo mostram algum progresso nesse intervalo.

## Verificação do repositório

Ver `verification.txt`: lista do `AGENTS.md` na raiz e em `desktop/`, testes Python com `VV_GODOT` definido (427 testes, 6 ignorados por dependências opcionais) e a campanha `--seeds 42,1337,2026`. Um defeito de documentação encontrado (comandos `cargo run --` do README, ambíguos por haver três binários) não foi corrigido.

## O que não foi verificado

- Não houve observação de pessoas: são verificações automatizadas do que o ecrã e a lista de processos mostram.
- A reversão para o 0.17.0 não foi executada, só os hashes foram verificados. A compatibilidade do Studio 0.17.0 com o módulo 0.2.0 não foi testada.
- Não se capturou a janela do processo iniciado pelo Studio (evitam-se capturas do ambiente de trabalho); a imagem vem de uma segunda execução do mesmo módulo.
- A subida só foi medida no arranque (12,4 s); `bench.py` correu só sobre o registo de aterragem.

## Recuperação (rollback)

Instaladores e hashes (os mesmos de `SHA256SUMS.txt`):

| Versão | Ficheiro | SHA-256 |
| --- | --- | --- |
| 0.17.0 (a que estava instalada) | `VV Lab Studio_0.17.0_x64-setup.exe` | `ce9fa33a526518ea5438f7d2a30a9f6c71e5fbcca7cbd2fafef9251f9ddbc972` |
| 0.18.0 | `VV Lab Studio_0.18.0_x64-setup.exe` | `8ad87eba2f7223186a4a265eea06da6a88fef21878c1fb74bc630d554471fb46` |
| 0.18.1 | `VV Lab Studio_0.18.1_x64-setup.exe` | `b0c2cf4180219ec427e6157072d3291c2c71e6beda2a75d22b3f3d867a8597ee` |

Para voltar ao 0.17.0: confirmar o hash com `Get-FileHash "<pasta de recuperação>\VV Lab Studio_0.17.0_x64-setup.exe" -Algorithm SHA256`, fechar o Studio e executar o instalador com `/S`. A biblioteca em `Documentos\VV Lab Library` e o módulo em `%LOCALAPPDATA%\org.vvlab.studio\modules\cinematic` não pertencem ao instalador e ficam como estão.

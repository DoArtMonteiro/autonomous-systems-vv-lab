# M11: guia de instalação e aceitação

Para o dono do projeto. Descreve como instalar o V&V Lab Studio, o que verificar e o que já foi verificado, com os comandos e os limites de cada verificação. A arquitetura está em [m11-desktop.md](m11-desktop.md).

Este ramo integra o M11 em `main` sem o M10 (que fica no PR #15). As verificações registadas abaixo foram feitas no ramo `feat/m11-desktop` (PR #16), que incluía o M10; neste ramo ainda não foram repetidas, salvo indicação em contrário.

## Instalar

1. Obter o instalador `VV Lab Studio_0.11.0_x64-setup.exe`: o artefacto `vv-lab-studio-installer` do job `installer` da CI, com o ficheiro `.sha256` ao lado, ou uma construção local com `desktop\build.ps1` (em `desktop\target\release\bundle\nsis\`). Duas construções da mesma fonte não são iguais byte a byte (o NSIS e o empacotamento incluem datas); comparar o SHA-256 com o do artefacto que se instala. O instalador não é assinado: o SmartScreen mostra "O Windows protegeu o computador"; escolher "Mais informações" e "Executar mesmo assim".
2. Correr o instalador. A instalação é por utilizador (sem pedido de administrador) em `%LOCALAPPDATA%\VV Lab Studio\`, com atalho no menu Iniciar e no ambiente de trabalho. O WebView2 já vem no Windows 11; se faltar, o instalador traz o instalador de arranque do WebView2.
3. Abrir "VV Lab Studio" no menu Iniciar. Não abre nenhuma consola.

Instalação silenciosa: `"VV Lab Studio_0.11.0_x64-setup.exe" /S`. Desinstalação: Definições do Windows, Aplicações, ou `%LOCALAPPDATA%\VV Lab Studio\uninstall.exe` (`/S` para silenciosa). A desinstalação não apaga `Documentos\VV Lab Library`.

## Percurso de aceitação (cerca de 15 minutos)

1. **Arranque.** O indicador no canto superior direito passa a "2 domains ready" (veículo terrestre e foguetão). Settings mostra os domínios, a versão do contrato `vv-domain 1.0`, a pasta da biblioteca e nenhum domínio recusado.
2. **Missão terrestre nominal.** Prepare, Ground vehicle, demonstração "Nominal drive": a missão termina no tick 7, segura, com os 12 resultados aprovados.
3. **Missão terrestre com falha.** Demonstração "A delayed command moves the vehicle in fallback": a execução "as built" fica incompleta e insegura; `safe_fallback` falha no tick 7. Clicar nesse requisito leva o cursor e a cena a esse tick.
4. **Aterragem nominal.** Rocket powered landing, demonstração "Nominal powered landing": `robust` aterra, segura, com todos os requisitos aprovados; o toque fica a cerca de 3 m do centro da plataforma, a cerca de 1,7 m/s. Rodar a cena 3D, usar os modos Follow, Pad e Side, arrastar a linha de tempo e confirmar que os gráficos e a cena seguem o mesmo cursor.
5. **Duas falhas geridas.** Demonstração "Two faults: biased altimeter and a GNSS outage" (altímetro com viés de 20 m e GNSS ausente de 8 s a 14 s): `robust` e `guarded` aterram, seguros, com os mesmos valores de toque; os dois rejeitam o altímetro a 0,1 s e só `guarded` regista `sensor_disagreement`.
6. **Duas falhas com resultado inseguro.** Demonstração "Two faults and an unsafe outcome" (altímetro com viés de 50 m e GNSS ausente de 8 s a 18 s): `baseline` deixa de descer a cerca de 380 m, sobe com motor e não toca o solo; é insegura (S5_no_powered_ascent falha). `robust` e `guarded` aterram, seguros. O resultado da missão e a segurança aparecem em blocos separados.
7. **Sementes protegidas.** Numa missão de foguetão, escrever a semente 3000: o campo recusa-a com a razão (sementes reservadas para a avaliação do M10) e o botão de execução fica bloqueado; o mesmo para 6000 (reserva). No veículo terrestre, 101 a 112 (conjunto de aceitação do M6).
8. **Reprodução e evidência.** Numa execução, Replay: todas as verificações passam e o veredicto é "verified". Provenance, Export evidence: escolher onde guardar o zip e abrir com "Show in Explorer".
9. **Biblioteca.** Library: procurar por semente ou controlador, editar etiqueta e notas, abrir uma comparação guardada.
10. **Domínio de referência.** Settings, "Show developer domains": aparece o oscilador de referência, que corre, compara, reproduz e exporta pelos mesmos ecrãs.
11. **Desinstalar e reinstalar.** Desinstalar, confirmar que `Documentos\VV Lab Library` continua com as execuções, reinstalar e ver as execuções outra vez na Library.

## O que foi verificado

### Neste ramo, sem o M10

O teste de interface `desktop/studio/tests/ui_smoke.py` foi reduzido aos percursos que existem neste ramo: missão terrestre nominal (J1), missão terrestre com falha injetada (J2), aterragem nominal do foguetão (J3) e duas falhas com resultado inseguro (J5), além das verificações transversais (semente protegida, reprodução, comparação, biblioteca, evidência, tema, domínio de referência e tamanhos de janela). Em 3/11/2026, contra o executável construído por `desktop/build.ps1` neste ramo e com os domínios preparados em `desktop/target/release/domains` (sem instalar), passaram 60 de 60 verificações, em janelas reais de 1024x640, 1366x768, 1440x900 e 1920x1080. O autoteste `vv-studio --self-test` passou nos três domínios. Os testes do espaço de trabalho `desktop/` passam (52), com `cargo fmt`, `cargo clippy -D warnings` e `--locked`. O teste com o instalador instalado e o CI ainda não correram neste ramo.

Os 365 testes Python da raiz passam neste ramo (3 ignorados).

### No ramo `feat/m11-desktop` (PR #16, com o M10), não repetido neste ramo

#### Verificação num checkout limpo (CI, 03/11/2026)

Job `installer (windows-latest)` do workflow `verification`, no PR #16, sobre o commit `b815bb5`: checkout limpo, Rust 1.99.0, Node 22, `desktop\build.ps1`, instalação silenciosa, verificação dos ficheiros instalados e de `VCRUNTIME140.dll`, `vv-studio.exe --self-test` instalado e desinstalação silenciosa. Resultado do instalador: `VV Lab Studio_0.11.0_x64-setup.exe`, 5 697 238 bytes, SHA-256 `f3ac143685963d4a9b0ff1a73651b9afc853f211f6173259b3b7a57906ee2e82`. Os jobs `ubuntu-latest`, `windows-latest` (verificações da raiz) e `desktop (windows-latest)` passaram no mesmo run.

No runner, o teste de interface não corre: a aplicação arranca e fica em execução, com WebView2 156.0.4314.50, mas o WebView2 não abre o endpoint de depuração. Por isso esse passo é informativo na CI, e o teste de interface foi feito nesta máquina contra o artefacto da CI:

- SHA-256 do artefacto descarregado igual ao registado no job;
- instalação silenciosa com código 0, nove ficheiros instalados, nenhum executável importa `VCRUNTIME140.dll`;
- `--self-test` com `PATH=C:\Windows\System32;C:\Windows`: código 0, quatro verificações aprovadas;
- `python desktop/studio/tests/ui_smoke.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --domains ""`: todas as verificações aprovadas na versão de então, com os percursos do M10 e a janela real a 1024x640, 1366x768, 1440x900 e 1920x1080.

#### Verificação local (02/11/2026, antes das correções da revisão de aceitação)

Máquina: Windows 11 Pro 10.0.26300, x64, 16 processadores lógicos, 32 GB, WebView2 156.0.4314.58. Data: 02/11/2026.

| Verificação | Comando ou método | Resultado |
| --- | --- | --- |
| Verificações da raiz (AGENTS.md) | `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test`, `python -m unittest discover -s tests -p "test_*.py"`, `cargo build --release`, `python scripts/run_campaign.py --seeds 42,1337,2026 --output-root runs/campaign` | 138 testes Rust e 400 testes Python (3 ignorados) passam; campanha `passed` (87 casos, 324 invocações) |
| Espaço de trabalho `desktop/` | `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test` | limpo; 44 testes passam (47 depois das correções de 03/11/2026, também na CI) |
| Paridade com o CLI | anfitrião do foguetão contra `vv-rocket land` (um caso do M10, semente 5000); anfitrião terrestre contra `vv-lab run-m4` (`delayed_after_fallback`) | `case`, `trace`, `verification` e `run` iguais byte a byte; as cinco saídas terrestres iguais |
| Instalação silenciosa | `setup.exe /S` | código 0; executáveis, domínios, atalhos no menu Iniciar e no ambiente de trabalho e entrada de desinstalação em HKCU |
| Sem ambientes de desenvolvimento | `vv-studio.exe --self-test` instalado, com `PATH=C:\Windows\System32;C:\Windows` e sem variáveis de Rust, Python ou Node, observando os processos filhos | passa (veículo terrestre e foguetão correm e reproduzem como "verified"); processos filhos: só os anfitriões, `vv-lab.exe` e `conhost.exe` |
| Dependências nativas | procura de `VCRUNTIME140.dll` nos executáveis instalados | nenhum o importa; só a UCRT do sistema (`api-ms-win-crt-*`) |
| Desinstalação | `uninstall.exe /S` | aplicação, atalhos e entrada de desinstalação removidos; ficheiro de teste na biblioteca mantido |
| Interface real | `python desktop/studio/tests/ui_smoke.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --domains ""` contra a aplicação instalada (instalador local de 02/11/2026; repetido a 03/11/2026 contra o instalador da CI, acima), com biblioteca e preferências em pastas temporárias | todas as verificações passam na versão de então: os cinco percursos de demonstração dessa versão, incluindo os do M10, semente protegida recusada, clique num requisito falhado move o cursor, reprodução verificada, comparação, pesquisa na biblioteca, cenário e comparação guardados e reabertos, exportação de evidência, tema, domínio de referência escondido por omissão e utilizável quando ativado, ausência de nome de utilizador no ecrã, e janela real redimensionada para 1024x640, 1366x768, 1440x900 e 1920x1080 sem deslocamento horizontal |

## Limites destas verificações

- **Computador limpo: só o runner da CI.** O runner é uma máquina virtual nova, onde a construção, a instalação e o auto-teste passam, mas tem ferramentas de desenvolvimento instaladas e o teste de interface não corre lá. Não há Windows Sandbox nem máquina virtual nesta máquina. Aqui, a aproximação foi a aplicação instalada, com o `PATH` reduzido às pastas do Windows, a observação dos processos filhos e a procura de dependências do runtime de Visual C++. Uma máquina sem WebView2 ou com políticas de grupo restritivas não foi testada.
- O instalador não é assinado; não foi testado com SmartScreen num computador sem histórico.
- A janela "Guardar como" do Windows e o "Show in Explorer" não fazem parte do teste automático.

## Estado científico, separado do estado do produto

- **Produto:** as verificações acima e o percurso de aceitação.
- **Ciência:** este ramo não inclui o M10, que continua no PR #15 (rascunho) e não foi aceite cientificamente. O M11 não altera o estimador nem os modelos, não congela nenhuma configuração e não corre sementes de avaliação (3000 a 3099) nem de reserva (6000 a 6099). Os resultados das demonstrações do M9 e do M9.1 são de desenvolvimento (sementes 5000 a 5099).

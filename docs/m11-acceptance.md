# M11: guia de instalação e aceitação

Para o dono do projeto. Descreve como instalar o V&V Lab Studio, o que verificar e o que já foi verificado, com os comandos e os limites de cada verificação. A arquitetura está em [m11-desktop.md](m11-desktop.md).

## Instalar

1. Obter o instalador `VV Lab Studio_0.11.0_x64-setup.exe` (construído por `desktop\build.ps1`, em `desktop\target\release\bundle\nsis\`; 5 697 742 bytes). O instalador não é assinado: o SmartScreen mostra "O Windows protegeu o computador"; escolher "Mais informações" e "Executar mesmo assim".
2. Correr o instalador. A instalação é por utilizador (sem pedido de administrador) em `%LOCALAPPDATA%\VV Lab Studio\`, com atalho no menu Iniciar e no ambiente de trabalho. O WebView2 já vem no Windows 11; se faltar, o instalador traz o instalador de arranque do WebView2.
3. Abrir "VV Lab Studio" no menu Iniciar. Não abre nenhuma consola.

Instalação silenciosa: `"VV Lab Studio_0.11.0_x64-setup.exe" /S`. Desinstalação: Definições do Windows, Aplicações, ou `%LOCALAPPDATA%\VV Lab Studio\uninstall.exe` (`/S` para silenciosa). A desinstalação não apaga `Documentos\VV Lab Library`.

## Percurso de aceitação (cerca de 15 minutos)

1. **Arranque.** O indicador no canto superior direito passa a "2 domains ready" (veículo terrestre e foguetão). Settings mostra os domínios, a versão do contrato `vv-domain 1.0`, a pasta da biblioteca e nenhum domínio recusado.
2. **Missão terrestre nominal.** Prepare, Ground vehicle, demonstração "Nominal drive": a missão termina no tick 7, segura, com os 12 resultados aprovados.
3. **Missão terrestre com falha.** Demonstração "A delayed command moves the vehicle in fallback": a execução "as built" fica incompleta e insegura; `safe_fallback` falha no tick 7. Clicar nesse requisito leva o cursor e a cena a esse tick.
4. **Aterragem nominal.** Rocket powered landing, demonstração "Nominal powered landing": `robust` e `m10_b_plus` aterram, seguras, classe R. Rodar a cena 3D, usar os modos Follow, Pad e Side, arrastar a linha de tempo e confirmar que os gráficos e a cena seguem o mesmo cursor.
5. **Falha de sensor gerida.** Demonstração "Sensor fault with successful fault management": B+ aterra (R) com um isolamento correto do radar; B aterra; A toca duro (U, R2 e R5 falham), sem invariante falhado. Na comparação, a matriz marca as divergências.
6. **Duas falhas com resultado inseguro.** Demonstração "Two faults and an unsafe outcome": `baseline` não toca o solo e é insegura (S5, subida com motor, primeira falha a 20,85 s); `robust` e `guarded` aterram; B+ toca fora da plataforma (classe T) e permanece segura. O resultado da missão e a segurança aparecem em blocos separados.
7. **Sementes protegidas.** Numa missão de foguetão, escrever a semente 3000: o campo recusa-a com a razão (avaliação do M10) e o botão de execução fica bloqueado; o mesmo para 6000 (reserva). No veículo terrestre, 101 a 112 (conjunto de aceitação do M6).
8. **Reprodução e evidência.** Numa execução, Replay: todas as verificações passam e o veredicto é "verified". Provenance, Export evidence: escolher onde guardar o zip e abrir com "Show in Explorer".
9. **Biblioteca.** Library: procurar por semente ou controlador, editar etiqueta e notas, abrir uma comparação guardada.
10. **Domínio de referência.** Settings, "Show developer domains": aparece o oscilador de referência, que corre, compara, reproduz e exporta pelos mesmos ecrãs.
11. **Desinstalar e reinstalar.** Desinstalar, confirmar que `Documentos\VV Lab Library` continua com as execuções, reinstalar e ver as execuções outra vez na Library.

## O que foi verificado

Máquina: Windows 11 Pro 10.0.26300, x64, 16 processadores lógicos, 32 GB, WebView2 156.0.4314.58. Data: 02/11/2026.

| Verificação | Comando ou método | Resultado |
| --- | --- | --- |
| Verificações da raiz (AGENTS.md) | `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test`, `python -m unittest discover -s tests -p "test_*.py"`, `cargo build --release`, `python scripts/run_campaign.py --seeds 42,1337,2026 --output-root runs/campaign` | 138 testes Rust e 400 testes Python (3 ignorados) passam; campanha `passed` (87 casos, 324 invocações) |
| Espaço de trabalho `desktop/` | `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test` | limpo; 44 testes passam |
| Paridade com o CLI | anfitrião do foguetão contra `vv-rocket land` (altímetro preso, B+, semente 5000); anfitrião terrestre contra `vv-lab run-m4` (`delayed_after_fallback`) | `case`, `trace`, `verification` e `run` iguais byte a byte; as cinco saídas terrestres iguais |
| Instalação silenciosa | `setup.exe /S` | código 0; executáveis, domínios, atalhos no menu Iniciar e no ambiente de trabalho e entrada de desinstalação em HKCU |
| Sem ambientes de desenvolvimento | `vv-studio.exe --self-test` instalado, com `PATH=C:\Windows\System32;C:\Windows` e sem variáveis de Rust, Python ou Node, observando os processos filhos | passa (veículo terrestre e foguetão correm e reproduzem como "verified"); processos filhos: só os anfitriões, `vv-lab.exe` e `conhost.exe` |
| Dependências nativas | procura de `VCRUNTIME140.dll` nos executáveis instalados | nenhum o importa; só a UCRT do sistema (`api-ms-win-crt-*`) |
| Desinstalação | `uninstall.exe /S` | aplicação, atalhos e entrada de desinstalação removidos; ficheiro de teste na biblioteca mantido |
| Interface real | `python desktop/studio/tests/ui_smoke.py` contra a janela WebView2 da aplicação, pelo protocolo de depuração | `python desktop/studio/tests/ui_smoke.py --exe "%LOCALAPPDATA%\VV Lab Studio\vv-studio.exe" --domains ""` contra a aplicação instalada (instalador SHA-256 `d3404ebb4e33cdea2cc44274cf3064f85061d7e17995cd33ca9b96520f6b6e0c`), com biblioteca e preferências em pastas temporárias | 66 de 66 verificações passam: os cinco percursos de demonstração, semente protegida recusada, clique num requisito falhado move o cursor, reprodução verificada, comparação, pesquisa na biblioteca, cenário e comparação guardados e reabertos, exportação de evidência, tema, domínio de referência escondido por omissão e utilizável quando ativado, ausência de nome de utilizador no ecrã, e janela real redimensionada para 1024x640, 1366x768, 1440x900 e 1920x1080 sem deslocamento horizontal |

## Limites destas verificações

- **Não foi testado num computador limpo.** Não há Windows Sandbox nem máquina virtual nesta máquina. A aproximação foi a aplicação instalada, com o `PATH` reduzido às pastas do Windows, a observação dos processos filhos e a procura de dependências do runtime de Visual C++. Uma máquina sem WebView2 ou com políticas de grupo restritivas não foi testada.
- O instalador não é assinado; não foi testado com SmartScreen num computador sem histórico.
- A janela "Guardar como" do Windows e o "Show in Explorer" não fazem parte do teste automático.

## Estado científico, separado do estado do produto

- **Produto:** as verificações acima e o percurso de aceitação.
- **Ciência:** o M10 continua em desenvolvimento no PR #15 (rascunho). O M11 não alterou o estimador, não congelou nenhuma configuração, não correu sementes de avaliação (3000 a 3099) nem de reserva (6000 a 6099) e não integrou nada em `main`. Os resultados das demonstrações M10 são de desenvolvimento e podem mudar. A decisão de congelar e a avaliação final continuam a ser do dono.

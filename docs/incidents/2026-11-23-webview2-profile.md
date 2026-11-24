# Incidente de 2026-11-23: perfil do WebView2 da Studio instalada

## Resumo

Em 2026-11-23, entre as 18:55 e as 19:01, suítes de percursos da interface correram contra um executável de desenvolvimento da Studio que tinha o mesmo identificador de aplicação (`org.vvlab.studio`) que a Studio 0.18.1 instalada. As suítes redirecionavam a biblioteca e a configuração da Studio, mas não o perfil do WebView2. O WebView2 escreveu por isso na pasta de dados da instalação, `%LOCALAPPDATA%\org.vvlab.studio\EBWebView`. Este documento regista os factos, as causas, as salvaguardas introduzidas e os riscos que ficam.

## Factos

Os factos vêm da secção «Quebra do passo 4» de `docs/m19-1-honesty.md` do ramo do M19.1 e de uma verificação só de leitura feita em 2026-11-24.

- Correram sete suítes (m15, ux, ux2, m18, m17 Lab, m16 e `ui_smoke`) ao longo de cerca de seis minutos, contra um executável construído a partir do ramo do M19.1.
- Cada suíte criava uma biblioteca (`VVLAB_LIBRARY`) e uma configuração (`VVLAB_CONFIG`) temporárias. Nenhuma definia `WEBVIEW2_USER_DATA_FOLDER`.
- O identificador do executável era `org.vvlab.studio`. As pastas de dados do Tauri e o perfil do WebView2 derivam do identificador, pelo que o executável de desenvolvimento usou as mesmas pastas que a instalação.
- Não existe nenhuma listagem anterior ao incidente. A mais antiga (`appdata-before.txt`, fora do repositório) foi tirada depois. Não foi possível, por isso, medir exatamente o que mudou.
- Dos 1302 registos dessa listagem, 203 têm data de 2026-11-23 entre as 18:55 e as 19:01. Incluem `History`, `Preferences`, `Secure Preferences`, `Local State`, `Web Data`, `Local Storage\leveldb`, `Session Storage`, `Network` e `Code Cache\js`. A escrita não se limitou a caches.
- Uma inspeção só de leitura de `Local Storage\leveldb\000003.log` (2671 bytes) mostra apenas registos internos do Chromium e nenhuma chave da aplicação. O código da interface da 0.18.1 não usa armazenamento web.
- Não foram tocados (datas anteriores ao incidente): os ficheiros do programa, `modules`, `logs`, as preferências da Studio em `%APPDATA%\org.vvlab.studio`, a pasta de dados do Godot (`app_userdata`) e a biblioteca em Documentos.
- Verificação só de leitura de 2026-11-24: a escrita mais recente no perfil instalado tem data de 2026-11-23T19:01:22 e nenhum ficheiro foi escrito depois das 19:02.

A conclusão de que o impacto nos dados da Studio é provavelmente nulo é uma inferência do que se leu, não uma medição.

## Decisão do responsável

Em 2026-11-24 o responsável decidiu deixar `EBWebView` como está: nada é apagado e nada é reposto. Repor era, de qualquer modo, impossível sem listagem anterior. 

## Causas

1. **Identificador partilhado.** Uma construção de desenvolvimento e a versão instalada tinham o mesmo identificador, logo o mesmo perfil. Nada na configuração distinguia as duas.
2. **Suítes que não redirecionavam o perfil.** Cada percurso lançava o executável por conta própria (cinco pontos de lançamento diretos, os outros por `m16_journeys.launch`) e cada um decidia que pastas redirecionar. Faltava a variável do WebView2, e nada o verificava.
3. **Mortes por nome de imagem, um perigo relacionado.** Quatro lançadores (m15, m16, `perf_probe`, `ui_smoke`) começavam por `taskkill /F /IM vv-studio.exe`. A Studio instalada tem o mesmo nome de imagem e seria terminada. Não está registado se isto chegou a acontecer no incidente; o perigo é o mesmo tipo de confusão entre uma construção de teste e a instalada.

## Salvaguardas

Três camadas. A identidade e o lançamento impedem, cada uma por si, uma escrita no perfil instalado; a terceira impede que os testes terminem o processo errado; os testes mantêm as três.

**Identidade.** `desktop/studio/tauri.conf.json` tem agora o identificador `org.vvlab.devstudio` e o nome de produto `VV Lab Studio (dev)`. O identificador de lançamento, `org.vvlab.studio`, existe só em `desktop/studio/tauri.release.conf.json`, que `desktop/build.ps1 -Release` aplica com `tauri build --config`. O identificador de desenvolvimento não contém o de lançamento (não é uma extensão por sufixo), para que procurar um no outro nunca confunda os dois. O script confirma o identificador antes de compilar e confirma depois que o `vv-studio.exe` compilado só contém o esperado; recusa-se a correr com `TAURI_CONFIG` herdado do ambiente.

**Lançamento.** Todos os percursos lançam o executável por `desktop/studio/tests/studio_launch.py`. A função pura `plan_launch(exe, environ, local_appdata, appdata)`:

- põe em pastas temporárias `WEBVIEW2_USER_DATA_FOLDER`, `VVLAB_LIBRARY`, `VVLAB_CONFIG` e `VVLAB_MODULES`, quando o chamador não as definiu (`VVLAB_MODULES` só vale em construções de depuração; numa construção em modo de lançamento com o identificador de desenvolvimento a pasta do módulo Cinematic fica em `%LOCALAPPDATA%\org.vvlab.devstudio`, nunca no perfil instalado);
- recusa, depois de normalizar (maiúsculas, barras, separador final, `..`, prefixo `\\?\`, pontos e espaços finais, `%VAR%`), qualquer valor de qualquer variável de ambiente que aponte para `%LOCALAPPDATA%\org.vvlab.studio`, `%APPDATA%\org.vvlab.studio` ou `Documentos\VV Lab Library`, e qualquer `--user-data-dir` nos argumentos do navegador;
- recusa um executável dentro de `%LOCALAPPDATA%\VV Lab Studio`, um que contenha o identificador de lançamento e um de origem desconhecida (sem nenhum dos dois identificadores), lendo o identificador compilado no próprio ficheiro;
- só levanta as recusas sobre o executável com a opção `--owner-allow-release-exe`, reservada ao responsável. As recusas sobre caminhos nunca se levantam. Nesse modo, o executável de lançamento ignora `VVLAB_MODULES` (só de depuração) e a pasta do módulo Cinematic continua a ser a do perfil instalado.

O lançamento recusa-se a arrancar se o mesmo executável já está em execução (o *plugin* de instância única entregar-lhe-ia o arranque) e nunca o termina. O fim de cada teste termina apenas o processo lançado, por PID. Foram removidas todas as mortes por nome de imagem; o `m18_journeys.py` deixou de terminar todos os processos `Godot*` e termina só os filhos da Studio que lançou.

**Testes.** `tests/test_studio_isolation.py`, no comando de testes Python do `AGENTS.md`, sem lançar a aplicação:

- o identificador base difere do de lançamento e não o contém; a sobreposição é exatamente `org.vvlab.studio` e só altera esse identificador e o nome de produto; nenhum código Rust nem outro JSON da Studio tem o identificador de lançamento;
- `build.ps1` só aplica a sobreposição com `-Release`, o ramo sem `-Release` não a usa nem produz instalador, e o identificador é verificado antes e depois da compilação; a CI usa `-Release`;
- `plan_launch`, com pastas de perfil inventadas (nunca as reais): recusa em todas as variantes de caminho acima, com `WEBVIEW2_USER_DATA_FOLDER` pré-definida e hostil, com `--user-data-dir`, com o executável instalado, de lançamento ou de origem desconhecida; aceita nomes vizinhos como `org.vvlab.studio.m191review`; e mantém as recusas sobre caminhos mesmo com a opção do responsável;
- uma verificação sobre a árvore sintática dos *scripts* de `desktop/studio/tests` falha se um deles chamar `Popen`, lançar um executável por `subprocess`, `os.system` ou `os.startfile` fora do auxiliar, ou se alguma chamada a `launch` não passar a opção do responsável; outra falha se aparecer `taskkill /IM`, `Stop-Process`, `pkill`, `killall` ou `taskkill /FI` em `desktop`, `scripts` ou `.github/workflows`, ou um `taskkill` sem `/F /PID`.

## Mudança no procedimento de lançamento de uma versão

`desktop/build.ps1` sem argumentos deixou de construir o instalador: constrói uma versão de desenvolvimento com o identificador `org.vvlab.devstudio`, sem instalador. O instalador de lançamento constrói-se com `desktop\build.ps1 -Release`, e a CI já o faz. Quem construir um instalador sem `-Release` obtém uma construção que não toca no perfil instalado. Descrição em `docs/m11-desktop.md`.

## Verificação ao vivo

Uma construção de desenvolvimento foi lançada três vezes pelo auxiliar, com a Studio instalada fechada: uma primeira tentativa, uma repetição com outro método de listagem e a execução final de `live_check.py`, cujo resultado está no repositório. As listagens (caminho, tamanho dos ficheiros, data) de `%LOCALAPPDATA%\org.vvlab.studio` e de `%APPDATA%\org.vvlab.studio` ficaram idênticas antes e depois, com um controlo de duas listagens idênticas sem lançamento. O arranque criou `%LOCALAPPDATA%\org.vvlab.devstudio`, vazia. Detalhes, limitações e a nota sobre a primeira tentativa em `docs/evidence/m19/isolation/README.md`. Esta verificação mostra que um arranque e um encerramento não tocam no perfil instalado; não cobre os percursos longos.

## Riscos que ficam

- **Edição do auxiliar.** Um agente ou uma pessoa pode editar `studio_launch.py`, `tauri.conf.json` ou `build.ps1` e remover uma salvaguarda. Os testes detetam as edições que mudam o que testam, não uma edição acompanhada da remoção do próprio teste. A revisão do diff destes ficheiros continua a ser necessária.
- **Caminhos de lançamento fora da análise.** A análise sintática cobre `desktop/studio/tests/*.py`. Um lançamento por outra via (PowerShell, `.cmd`, um *script* noutra pasta, um comando escrito à mão) não é visto. Um comando manual do executável de lançamento, ou de um executável antigo com o identificador de lançamento, continua a escrever no perfil instalado.
- **Executáveis antigos.** Construções feitas antes desta alteração têm o identificador de lançamento e são recusadas pelo auxiliar, mas nada impede que alguém as lance diretamente.
- **Opção do responsável.** Com `--owner-allow-release-exe` o auxiliar lança o executável instalado ou de lançamento: o perfil do WebView2, as preferências e a biblioteca ficam em pastas temporárias, mas o módulo Cinematic resolve para o perfil instalado. A CI usa a opção num executor descartável.
- **Perfil do Godot.** O Godot guarda dados em `%APPDATA%\Godot\app_userdata` e o módulo Cinematic arranca-o a partir da Studio. O auxiliar não redireciona esta pasta. Os percursos que abrem o módulo, e `m17_cinematic_journey.py` em particular, continuam a poder escrever aí.
- **Dependência do comportamento do WebView2 e do Tauri.** A salvaguarda por `WEBVIEW2_USER_DATA_FOLDER` pressupõe que a variável tem precedência sobre a pasta que o Tauri indica, e a leitura do identificador pressupõe que o Tauri o compila como texto UTF-8 no executável. A segunda foi confirmada nas construções de desenvolvimento e de lançamento feitas para este trabalho. Quanto à primeira, no lançamento ao vivo o perfil do WebView2 foi criado dentro da pasta temporária; serve de defesa em profundidade, porque a identidade já separa os perfis.
- **`build.ps1` não foi executado de ponta a ponta.** Foi executado até à guarda de `TAURI_CONFIG` (com e sem `-Release`), e a CLI do Tauri foi chamada à mão com os mesmos argumentos (`--no-bundle`, `--config`) e deu o identificador esperado em cada caso. O empacotamento do instalador com `-Release` e a verificação do identificador no fim do script não foram executados; a primeira vez que alguém construir um instalador será a primeira vez que correm.
- **Procedimento de lançamento.** Quem construir um instalador sem `-Release` entrega um produto com nome e pastas de desenvolvimento. O `build.ps1` e a CI estão ajustados, mas é uma mudança de hábito.

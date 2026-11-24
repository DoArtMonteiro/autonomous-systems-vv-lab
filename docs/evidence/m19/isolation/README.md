# Verificação ao vivo do isolamento

Uma construção de desenvolvimento (`cargo build -p vv-studio` em `desktop/`, identificador `org.vvlab.devstudio`) foi lançada uma vez, por `desktop/studio/tests/studio_launch.py`, com a Studio instalada fechada. Os perfis da instalação foram listados antes e depois, só com metadados (caminho, tipo, tamanho dos ficheiros, data de modificação em ns). Resultado completo em `result.json`; o programa que o produziu é `live_check.py`.

## Resultado

| Verificação | Resultado |
| --- | --- |
| Identificadores no executável (`embedded_identifiers`) | só `org.vvlab.devstudio` |
| Duas listagens de controlo, com 5 s de intervalo, sem lançamento | idênticas |
| `%LOCALAPPDATA%\org.vvlab.studio`, antes e depois | idêntica: 914 entradas, SHA-256 `cd81f5b0...2917` |
| `%APPDATA%\org.vvlab.studio`, antes e depois | idêntica: 1 entrada, SHA-256 `d9c0a437...0a829` |
| Ponto de ligação das DevTools do WebView2 | abriu; a aplicação ficou viva cerca de 8 s |
| Fim do processo | por PID próprio; nenhum processo ficou ligado à pasta temporária |
| Perfil do WebView2 | foi criado dentro da pasta temporária (`EBWebView`) |
| `%LOCALAPPDATA%\org.vvlab.devstudio` | criada pelo arranque, **vazia** (0 ficheiros); `%APPDATA%\org.vvlab.devstudio` não existe |

As somas completas estão em `result.json`. As listagens em si não são publicadas.

## Também verificado

- Compilar a mesma árvore com a sobreposição de lançamento (`TAURI_CONFIG` com o conteúdo de `desktop/studio/tauri.release.conf.json`) dá um executável que contém só `org.vvlab.studio`; voltar a compilar sem ela volta a dar só `org.vvlab.devstudio`. Cada compilação voltou a compilar o `vv-studio` (4 s), por isso uma alteração do identificador não deixa um executável antigo.

## Limitações e história da medição

- Uma máquina (Windows 11 Pro 10.0.26300, Python 3.14.6), um lançamento, cerca de 14 s, sem domínios nem ficheiros de missão. Não prova que nenhum percurso longo escreve fora das pastas temporárias; prova que o arranque e o encerramento não tocam no perfil instalado.
- Uma primeira tentativa, antes do controlo, deu somas diferentes em `%LOCALAPPDATA%\org.vvlab.studio`. A diferença eram só 27 diretorias vazias a mudar de 0 para 4096 no campo «tamanho», sem nenhuma data de modificação alterada e em pastas que o lançamento não podia ter tocado (por exemplo `modules\cinematic`). É um artefacto da leitura do tamanho de diretorias. O método foi alterado para não registar o tamanho de diretorias, e a verificação repetida desde o início, com o controlo, deu as listagens idênticas acima. A tentativa original não faz parte do resultado.
- O executável instalado não foi lido, lançado nem alterado; nenhuma listagem escreveu em nenhuma pasta de dados.
- O encerramento foi pelo PID do processo lançado. O executável instalado tem o mesmo nome de imagem, por isso nenhum comando usou o nome da imagem.

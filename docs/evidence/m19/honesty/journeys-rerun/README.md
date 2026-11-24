# Percursos repetidos com isolamento do perfil

Os percursos da interface e as capturas de superfícies nunca vistas foram repetidos depois das correções da revisão e do seguimento, contra uma Studio de **desenvolvimento** (identificador `org.vvlab.devstudio`), lançada por `desktop/studio/tests/studio_launch.py`. Esta é a repetição que faltava depois da quebra do perfil do WebView2 descrita em `docs/m19-1-honesty.md` («Quebra do passo 4»).

## Origem

- Ramo de verificação descartável `verify/m19.1-with-isolation`: `fix/m19.1-honesty` (`dde0620`) com `feat/m19-studio-isolation` (`51882b1`) integrado, sem conflitos. Não foi enviado. O código-fonte da Studio e dos anfitriões é o de `fix/m19.1-honesty`; do ramo de isolamento vêm a configuração do Tauri, o auxiliar de lançamento, os percursos adaptados e o `build.ps1`.
- Construção: `desktop\build.ps1` (desenvolvimento, sem instalador); o script confirmou `vv-studio.exe carries: org.vvlab.devstudio`. `vv-studio.exe` com SHA-256 `d0ee8494...0580`.
- Máquina: Windows 11 Pro 10.0.26300, Python 3.14.6. Cada percurso arrancou a Studio uma vez, pelo auxiliar, com biblioteca, configuração e perfil do WebView2 temporários, e terminou-a pelo PID.

## Resultados

| Percurso | Resultado | Antes (`journeys-after.txt`, perfil não isolado) |
| --- | --- | --- |
| `ui_smoke.py` | 80/80 | 80/80 |
| `m15_journeys.py` | 48/48 | 48/48 |
| `m16_journeys.py` | 78/78 | 78/78 |
| `m17_lab_journeys.py` | 34/34 | 34/34 |
| `m18_journeys.py` | 71/71 | 72/72 |
| `ux_journeys.py` (`--no-cinematic`) | 67/67 | 67/67 |
| `ux2_journeys.py` | 90/90 | 90/90 |
| `surfaces.py` (novo, superfícies nunca vistas) | 14/14 | não existia |

Saída de cada um em `suites/`. O `m18` tem menos uma verificação porque o módulo Cinematic não está instalado nesta construção (o perfil de desenvolvimento não tem módulos) e o percurso segue o ramo «não disponível», com o mesmo resultado esperado; antes, o executável usava o perfil instalado, que tinha o módulo.

Não foram corridos: `m17_cinematic_journey.py` (precisa do ficheiro zip do módulo e da janela de ficheiros nativa, e numa construção em modo de lançamento `VVLAB_MODULES` não se aplica: o módulo ficaria na pasta `%LOCALAPPDATA%\org.vvlab.devstudio`, não numa pasta temporária), `review_captures.py` e `installed_spotcheck.py` (precisam do módulo Cinematic instalado ou da Studio instalada, que não se tocou).

## Superfícies que nunca tinham sido vistas

`surfaces.py` corre sobre a mesma construção e escreve `surfaces-facts.json` e as capturas `surf-*`. Resultado em `surfaces-results.txt`.

| Superfície | Captura | Facto verificado |
| --- | --- | --- |
| Flight console, regras de segurança `held` | `surf-1-flight-console-held-1440x900.png`, `...1024x640.png` | cinco regras «held» com a classe neutra, nenhuma verde |
| Tabela de comparação do Lab, linhas de segurança | `surf-2-lab-comparison-table-1440x900.png` | células de invariantes com a classe `st-held`; nenhuma linha de segurança com a classe de requisito cumprido |
| Página Runs | `surf-3-runs-page-1440x900.png`, `...1024x640.png` | «None broken» com a classe neutra; sem deslocamento horizontal a 1024x640 |
| Discover, lista «Investigations» e peças | `surf-4-discover-investigation-1440x900.png` | a investigação aparece na lista; «Evidence integrity: recomputed» neutra; peças «Recomputed, every check passed» |
| Anel de foco da pílula | `surf-5-pill-focus-ring-1024x640.png` | `:focus-visible`, contorno de 2 px, dentro da linha de pílulas |

Também copiadas, vindas dos percursos: `m17-lab-seeds-dark.png` (ressalva «estimate on 8 development seeds» e «k/n seeds»), `m17-lab-experiment-dark.png`, `m13-g3-overview-dark.png` e `m13-tampered-dark.png`.

## Observação, não defeito dos percursos

Na tabela do Lab, as células de segurança mostram o sinal ✓ com a cor neutra; o resto da interface usa o escudo para `held`. Não é uma falha de nenhuma verificação e não foi alterado.

## Perfil instalado

Listagens só de leitura (caminho, tipo, tamanho dos ficheiros, data de modificação em ns) antes e depois de todos os percursos e capturas: `%LOCALAPPDATA%\org.vvlab.studio` 914 entradas, SHA-256 `cd81f5b033bc...2917`; `%APPDATA%\org.vvlab.studio` 1 entrada, SHA-256 `d9c0a4377b57...0a829`. **Idênticas antes e depois**, e iguais às da verificação de isolamento (`docs/evidence/m19/isolation/`). A Studio instalada estava fechada e não foi tocada.

## Limitações

- Uma máquina, uma execução de cada percurso. Verificações programadas do que o ecrã mostra, não observação de pessoas, nem leitor de ecrã, nem avaliação de contraste.
- A Studio é de desenvolvimento em modo de lançamento (perfil de compilação `release`, identificador de desenvolvimento): não é o executável instalado nem o instalador.
- As capturas de `surf-*` são de um conjunto de execuções criado na hora (biblioteca vazia no início).

# Verificação das guardas de execução

Ramo `feat/m20-runtime-guards`. Todas as verificações ao vivo usaram a identidade de desenvolvimento, pastas temporárias e o lançador; nenhuma tocou na Studio instalada 0.18.1, que estava fechada.

## Resultados

| Verificação | Resultado |
| --- | --- |
| `cargo test -p vv-studio` em `desktop/` | 56 passam, 21 deles de `guard::tests` |
| `tests/test_studio_guard.py` (executável de desenvolvimento em `desktop/target/debug`, `--guard-only` e arranque real, ambientes descartáveis) | 22 passam |
| `tests/test_cinematic_guard.py` com `VV_GODOT` (decisão de `guard.gd` em Godot 4.7.2, através de `godot_launch`) | 10 passam, incluindo 15 casos da decisão |
| Os 55 testes `tests/test_cinematic_*.py` com o projeto de desenvolvimento e a guarda, através de `godot_launch` | passam |
| `python -m unittest discover -s tests -p "test_*.py"` | 556 testes, OK, 90 ignorados (os de Godot sem `VV_GODOT` e os do binário `vv-rocket`) |
| `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test`, `cargo build --release` na raiz e em `desktop/`; campanha com as sementes 42, 1337 e 2026 | passam; campanha `passed`, 87 casos |

## Lançamento ao vivo

`result.json`: a Studio de desenvolvimento lançada uma vez por `studio_launch.launch` (ficheiro de arranque, pasta própria, `APPDATA` e `LOCALAPPDATA` redirecionadas). O ponto de ligação das DevTools abriu, a guarda consumiu o ficheiro (`launch.json.used`), o processo terminou pelo PID próprio, nenhum processo ficou ligado à pasta do arranque e a pasta foi removida. Também se confirmou o arranque direto sem ficheiro: recusa com o código 78, sem escrever nada e sem `studio.log` (teste `test_a_direct_launch_refuses_before_writing_anything`).

## Sonda do primeiro `autoload` do Godot

Projeto Godot 4.7.2 mínimo, com o seu próprio nome de pasta de utilizador e um `autoload` que lista a pasta de dados em `_init`, corrido só por `godot_launch` (`APPDATA` temporária): quando o primeiro `autoload` corre, a pasta de dados **já existe** e contém `logs/godot.log` (`--headless`). O Godot cria o registo antes de qualquer *script*. Por isso o nome de desenvolvimento do projeto é a proteção estrutural e o `autoload` é defesa em profundidade. Não se mediu o que se escreve ao desenhar (caches).

## Perfis instalados

Listagens só de leitura (caminho, tipo, tamanho dos ficheiros, data de modificação em ns) antes e depois de todos os testes e lançamentos acima, **idênticas**:

| Pasta | Entradas | SHA-256 da listagem |
| --- | --- | --- |
| `%LOCALAPPDATA%\org.vvlab.studio` | 914 | `cd81f5b033bc...2917` |
| `%APPDATA%\org.vvlab.studio` | 1 | `d9c0a4377b57...0a829` |
| `%APPDATA%\VV Lab Cinematic` | 528 (ficheiros e pastas) | `bb8da076b15e...f5f8` |

## Não verificado

- Não se correu nenhum percurso longo da interface (`ui_smoke`, `m15` a `m18`, `ux`) com a guarda: precisam dos anfitriões de domínio preparados por `build.ps1`, e o ramo só foi construído em modo de desenvolvimento do Tauri sem eles. A Studio arrancou pelo lançador (`result.json`) e as alterações dos percursos são de leitura da biblioteca e da configuração a partir do plano do lançamento (`ui_smoke.py`).
- Não se construiu o instalador nem o executável de lançamento neste ramo; o `build.ps1 -Release` verifica o identificador compilado e o teste de `guard::tests` confirma que a constante é igual ao identificador de `tauri.release.conf.json`.
- Uma máquina (Windows 11 Pro 10.0.26300, Python 3.14.6, Rust 1.99.0).

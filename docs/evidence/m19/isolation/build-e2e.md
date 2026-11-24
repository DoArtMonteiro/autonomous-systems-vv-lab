# Construção de ponta a ponta com as verificações de identidade

Executada em 2026-11-24, numa cópia de trabalho do repositório, `<worktree>` (ramo `feat/m19-studio-isolation`), numa máquina Windows 11 Pro 10.0.26300, com PowerShell 5.1 e Node 24.18.0 (npm 12.0.2). `TAURI_CONFIG` não estava definida. Nenhum executável nem instalador produzido foi lançado ou instalado; a Studio instalada estava fechada e não foi tocada.

## Comandos e resultados

| # | Comando | Código de saída |
| --- | --- | --- |
| 1 | `npm ci --no-audit --no-fund` em `desktop/studio` | 0 (`added 2 packages`) |
| 2 | `powershell -NoProfile -ExecutionPolicy Bypass -File desktop/build.ps1` | 0 |
| 3 | `powershell -NoProfile -ExecutionPolicy Bypass -File desktop/build.ps1 -Release` | 0 |

## Saída das verificações de identidade

Construção de desenvolvimento (2):

```
==> Build identity: org.vvlab.devstudio (development)
...
==> Tauri build, development identity, no installer
    Finished `release` profile [optimized] target(s) in 2m 31s
       Built application at: <worktree>\desktop\target\release\vv-studio.exe
    vv-studio.exe carries: org.vvlab.devstudio
==> Development build: <worktree>\desktop\target\release\vv-studio.exe (no installer; use -Release for one)
```

Construção de lançamento (3):

```
==> Build identity: org.vvlab.studio (release)
...
==> Tauri bundle (NSIS installer), release identity from tauri.release.conf.json
    Finished `release` profile [optimized] target(s) in 2m 08s
        Info Patching <worktree>\desktop\target\release\vv-studio.exe with bundle type information: nsis
     Running makensis to produce <worktree>\desktop\target\release\bundle\nsis\VV Lab Studio_0.18.1_x64-setup.exe
    vv-studio.exe carries: org.vvlab.studio
==> Installer:
    <worktree>\desktop\target\release\bundle\nsis\VV Lab Studio_0.18.1_x64-setup.exe
    sha256 05e4bc0e1d1cacbd301f04ebaedc15fe2770c11cd132a4d8b35db0063e37981b
```

As verificações do nome de produto (antes da construção, sobre a configuração fundida; depois, sobre o executável compilado) não escrevem nada quando passam; só lançam um erro quando falham. Nos dois casos o script terminou com código 0, logo passaram. Esta é a primeira execução do `build.ps1` de ponta a ponta com as verificações novas.

## Artefactos

- `desktop\target\release\vv-studio.exe`: 13 015 040 bytes (versão de lançamento, identificador `org.vvlab.studio`, SHA-256 `5102191a...029b2`). Na execução 2 foi a versão de desenvolvimento (`org.vvlab.devstudio`), substituída na execução 3.
- `desktop\target\release\bundle\nsis\VV Lab Studio_0.18.1_x64-setup.exe`: 42 465 733 bytes, SHA-256 `05e4bc0e1d1cacbd301f04ebaedc15fe2770c11cd132a4d8b35db0063e37981b`. Não foi executado.
- O instalador é de uma construção de desenvolvimento do ramo, não é um lançamento: não foi assinado nem publicado, e duas construções da mesma fonte não são idênticas byte a byte.

## Perfil instalado

Listagens só de leitura (caminho, tipo, tamanho dos ficheiros, data de modificação em ns) de `%LOCALAPPDATA%\org.vvlab.studio` e `%APPDATA%\org.vvlab.studio`, antes do `npm ci` e depois da execução 3:

| Pasta | Entradas | SHA-256 da listagem | Antes e depois |
| --- | --- | --- | --- |
| `%LOCALAPPDATA%\org.vvlab.studio` | 914 | `cd81f5b0...2917` | idêntica |
| `%APPDATA%\org.vvlab.studio` | 1 | `d9c0a437...0a829` | idêntica |

## Limitações

- O NSIS e o instalador de arranque do WebView2 foram descarregados pelo Tauri durante a execução 3 (rede só para descarga de pacotes).
- Não se verificou o conteúdo do instalador; a verificação do identificador e do nome de produto é sobre o `vv-studio.exe` que entra nele.
- Uma máquina, uma execução de cada.

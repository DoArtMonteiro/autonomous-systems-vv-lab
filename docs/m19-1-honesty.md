# M19.1: correções de honestidade científica da Studio

Estado: em curso. Base: `main` em `bec7b3f` (origem da Studio 0.18.1 instalada). Ramo local `fix/m19.1-honesty`, sem envio. As alterações corrigem o que a Studio mostra; não alteram nenhuma simulação, nenhum registo e nenhuma evidência guardada.

## Defeitos de partida e classificação

Classes: (a) só texto ou apresentação da interface; (b) altera evidência registada ou hashes de execução (por exemplo, texto em `evidence.rs` muda o hash do anfitrião e os identificadores das corridas); (c) pode influenciar o comportamento da simulação. Regras do mandato: (a) implementa-se; (b) só se não tocar em evidência protegida, linhas de base ou hashes canónicos, senão propõe-se; (c) nunca se implementa.

| n.º | Defeito (Studio 0.18.1) | Onde nasce | Classe | Decisão |
| --- | --- | --- | --- | --- |
| 1 | O chip verde «No safety rule broken (5 checked)» aparece ao lado de requisitos falhados | `desktop/studio/ui/js/requirements.js`, `model.js`, `views/player.js`, CSS | (a) | Implementado: veredicto `held`, tom neutro e ícone próprio, nunca verde; o texto não muda |
| 2 | A cláusula falhada de `mission_completion` não é mostrada; «To goal 0.00 mm» ao lado de «Mission incomplete» | O registo do domínio terrestre (`desktop/domain-ground/src/record.rs`) não diz que cláusula falhou; a interface mostra a distância sem contexto | (a) para a interface; (b) para o registo | Interface: implementado (factos do registo, o que o registo não diz, nota na linha «To goal»). Registo: **proposto, não implementado** (muda o hash do anfitrião terrestre e o texto de todos os registos terrestres que falham) |
| 3 | O painel Cinematic da subida não diz que o impacto do booster não é modelado | `desktop/cinematic/scripts/hud.gd` | (a) | Implementado: frase de impacto quando um registo de subida tem uma entidade que termina em impacto |
| 4 | A pluma continua desenhada depois do contacto | `desktop/studio/ui/js/scenes/rocket.js` (cena de engenharia e geoespacial) | (a) | Implementado: sem pluma depois da última amostra de uma corrida; o registo não diz nada sobre o motor depois do contacto |
| 5 | Velocidade no contacto contra o último ponto amostrado | `desktop/cinematic/scripts/hud.gd` | (a) | Implementado: no fim de uma aterragem a leitura mostra as velocidades de contacto do verificador (registo) e diz que as outras são da última amostra |
| 6 | A 1024x640 as pílulas não selecionadas cortam as condições da corrida | `desktop/studio/ui/css/mission.css`, `views/player.js` | (a) | Implementado: resumo exato das condições (nunca texto cortado) e nome completo em `title` e `aria-label` |
| 7 | «Every requirement and safety rule met.» (player) e «Every requirement met.» (Lab) escritos quando só não há requisitos falhados, mesmo com linhas não avaliadas | `views/player.js`, `views/lab.js` | (a) | Implementado (defeito encontrado na pesquisa) |
| 8 | O chip «Mission» fica verde com «no mission requirement listed» | `views/player.js` | (a) | Implementado: neutro |

O que não pertence a nenhuma classe acima ficou registado nas secções seguintes.

## Linha de base antes de qualquer alteração

Capturada com `docs/evidence/m19/honesty/hash_set.py` (mesmo código antes e depois). Ficheiros: `hashes-before.json` e `verification-before/`.

- `source_sha256` de `vv-rocket` (20 ficheiros) e `vv-ascent` (12 ficheiros), recalculado com a mesma lista e a mesma normalização de fim de linha das funções `source_sha256()`.
- SHA-256 de todos os 266 ficheiros versionados em `docs/evidence/` e `exec/claims/`, dos cenários M1 (`scenarios/`, incluindo `sha256.json` e `canonical-seed-42.json`) e de todos os fixtures e golden dos testes.
- SHA-256 dos anfitriões de domínio, de `vv-lab` e de `vv-exec` construídos por `desktop/build.ps1 -StageOnly` (o hash do anfitrião de que dependem os identificadores das corridas).
- Registo e ficheiros nativos de cada execução de demonstração dos quatro domínios (25 execuções, sementes de demonstração do produto) e os artefactos M1 da missão básica com a semente 42.
- Comandos de verificação do repositório (resultados em `verification-before/`).

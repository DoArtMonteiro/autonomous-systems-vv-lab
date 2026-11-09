# M18: plano de integração das PR #24 a #30

Estado: proposta para decisão do responsável. Nada foi integrado, enviado ou alterado nas PR. As verificações abaixo foram feitas em 2026-11-08 só com leitura (`git fetch`, `gh pr view`, `git merge-base`, uma árvore de trabalho descartável para as fusões de ensaio, já removida).

## Estado das PR

Todas as PR estão abertas e em rascunho. Nenhuma tem commits locais por enviar; as cabeças locais e remotas coincidem.

| PR | Ramo | Base | Cabeça (local = remota) | Em `m17-integration` | Natureza |
| --- | --- | --- | --- | --- | --- |
| #24 | `feat/m15-mission-experience` | `main` | `c4179a0` | sim | experiência de missão, biblioteca, Studio 0.15.0 |
| #25 | `feat/m16-geospatial` | #24 | `0626b75` | sim | vista geoespacial, camada do mundo (esquema v3), Studio 0.16.x |
| #26 | `feat/m17-experiment-lab` | #25 | `52d69e3` | sim | Experiment Lab, caso de aterragem v2, veículos, pacotes de ambiente |
| #27 | `feat/m17-ascent` | #25 | `51345aa` | sim | subida de dois andares, `vv-run.v2` |
| #28 | `feat/m17-environments` | #25 | `865472f` | sim | cinco pacotes de ambiente instaláveis |
| #29 | `feat/m17-cinematic` | #25 | `c30b26e` | **não** (ver abaixo) | módulo opcional Cinematic View (Godot) |
| #30 | `m17-integration` | #26 | `c119d5d` | é a própria | integração dos quatro fluxos, Studio 0.17.0 |

- `origin/main` é `a23db64` (fusão das PR #21 a #23) e está contido em `m17-integration`. O ramo local `main` está desatualizado (`70e5435`): não o usar como base; atualizar a partir de `origin/main`.
- `m17-integration` local e `origin/m17-integration` são ambos `c119d5d`.
- O #29 tem três commits que não estão em `m17-integration` pelo SHA: `c30b26e` (documento de aceitação do Cinematic View) tem o mesmo patch que `c119d5d` da integração (`git cherry`). `7a7ef4b` e `5d7edfe` têm as mesmas mensagens que `332d1c9` e `6e8a3c7` da integração, mas patches diferentes (a integração resolveu-os sobre o #26). Comparar estas diferenças antes de qualquer fusão do #29.
- Existe também o ramo local `feat/m18-booster-recovery` (árvore de trabalho bloqueada, em `c119d5d`), sem commits próprios; não faz parte deste plano.
- Nota: a árvore de trabalho desta verificação tinha alterações não confirmadas de outra sessão (`desktop/domain-rocket/src/case.rs`, `catalog.rs`, `docs/m18-cinematic-preflight.md`). Não foram tocadas e não pertencem a nenhuma PR acima.

## Ensaio de conflitos

Base de ensaio: `origin/main`. Fusões `--no-ff` sem confirmar, em árvore descartável.

Ordem A (#24, #25, #26, #27, #28, #29, #30):

| Passo | Resultado |
| --- | --- |
| #24, #25, #26, #27, #28 | limpo |
| #29 | **conflito** em `desktop/Cargo.lock`, `desktop/studio/src/main.rs`, `desktop/studio/ui/js/views/player.js` |
| #30 | não executado (a ordem A para no conflito) |

Verificações complementares:

- #29 sobre #25 sozinho: limpo. #29 depois de #27 ou de #28: limpo. #29 depois de #26: **conflito** nos mesmos três ficheiros. O conflito é, portanto, entre o Experiment Lab (#26) e o Cinematic View (#29), e é o que `m17-integration` já resolveu.
- Ordem B (#24, #25, #26, #27, #28, depois #30): limpa, e a árvore resultante é idêntica à de `m17-integration` (`1735c7d`, `git diff --stat` vazio).
- Consequência: a fusão do #29 em separado exige uma resolução manual dos três ficheiros que ainda não existe fora da integração.

## Âmbito científico, exploratório e visual por PR

Segundo os documentos em `m17-integration` (`docs/m15-mission-experience.md`, `docs/m16-2-flagship.md`, `docs/m17-*.md`, `docs/evidence/m17*`). Nenhum resultado científico destes documentos tem revisão humana independente; todos descrevem verificação por testes e revisão por agentes.

| PR | Verificado por testes e reprodução | Exploratório | Interface e visual | Decisões em aberto do responsável |
| --- | --- | --- | --- | --- |
| #24 | determinismo, reprodução, biblioteca de simulações | missões curadas ilustram padrões numa semente; não confirmam o que o M13 mediu em 30 sementes | Studio 0.15.0; cena que não muda num contacto falhado (deliberado) | protocolo candidato `docs/m15-g3-onset-protocol.md` (rever por humano antes de correr as sementes 44000 a 44999); itens «Pendente depois das revisões» |
| #25 | pacotes `vv-geo` validados por SHA-256 e contagens; esquema v3 | camada do mundo: paredes, telhados, formas de plantas, alturas estimadas dos edifícios | renderizador, névoa, câmaras, painel de fontes; ~230 MB de memória e 140 MB de GPU na vista geoespacial | aceitação visual do 0.16.2; ponto em aberto de memória; defeitos «por corrigir» (iluminação da fotografia, aresta mar/terreno) |
| #26 | caso v1 recusa valores movidos; v2 com valores registados simula como o v1; reprodução do Lab | veículos de aterragem («exploratório»); verificação em várias sementes é só estimativa sobre sementes de desenvolvimento | ciclo de experimentação no Studio; instalação de pacotes | nenhuma própria documentada além das limitações |
| #27 | SplitMix64 com fluxo por fonte; entidades filhas arrancam do estado do `stack`; ordem total de eventos; recusa de campos desconhecidos; `vv-run.v2` | **todo o caso**: veículos «exploratory, not a real vehicle», valores só de ordem de grandeza | cenários `launch-ascent` no domínio | limites de validade (secção «Limites de validade») |
| #28 | validação do pacote com o validador do Studio, zip determinístico | níveis de dados B e C sem vegetação; datums nacionais lidos como WGS84 | capturas por pacote | lacunas: atribuição do IGN sem data, datum vertical do Instituto Polar Norueguês, instalação a partir do zip ainda não copia o `NOTICE.md` |
| #29 | paridade de pose com o leitor técnico em 235 amostras; instalação, adulteração, desinstalação por testes Rust | nada científico | **tudo é visual**: perfis gráficos, defeitos apontados pela segunda avaliação, Vulkan falha nesta máquina (usa Direct3D 12), módulo corre o binário do editor (181 MB), escreve em `%APPDATA%` | recomendação do próprio documento: manter como protótipo e não distribuir; aceitar a cena; distribuir o módulo como segundo artefacto; Unreal Engine 5 (EULA, 50 a 70 GB) |
| #30 | integração dos quatro fluxos; evidência instalada 0.17.0: Lab 34/34, ciclo do Cinematic 8/8, M16 77/77, M15 48/48 | herdado das PR acima | herdado | herdado |

## Estratégia recomendada

Duas fases, com o Cinematic View fora do caminho crítico.

**Fase 1: ciência e produto sem o renderizador.** Fundir por ordem, com commits de fusão fixados aos SHA testados, #24, #25, #26, #27, #28. A ordem A limpa até #28 confirma que não há conflitos. Cada fusão é um commit `--no-ff` com mensagem `merge: PR #N ...` e é verificada antes de avançar.

**Fase 2: Cinematic View, separado e opcional.** Decidir o #29 à parte, depois de a Fase 1 estar em `main`. Duas variantes, a escolher pelo responsável:

1. Aceitar o módulo como opcional: reabrir o #29 e a resolução dos três ficheiros partilhados com o #26 (a partir de `m17-integration`), sobre `main` já com a Fase 1, com o botão do leitor desativado quando o módulo não está instalado (já é o comportamento documentado).
2. Deixar o módulo em protótipo: manter o ramo `feat/m17-cinematic` e o #29 em rascunho, sem integração. É o que o documento do módulo recomenda enquanto os defeitos visuais não forem corrigidos.

**Porquê esta escolha e não fundir o #30 numa só vez.** O #30 inclui o #29 e arrasta a aceitação visual e o conflito para dentro da integração da ciência validada, contra a regra de que o renderizador cinematográfico não bloqueia a aceitação da ciência. A ordem A limpa até #28 mostra que as quatro primeiras PR se integram sem o #29. O #30 continua útil como referência: a ordem B dá a árvore exata do Studio 0.17.0 instalado (`1735c7d`), contra a qual se compara o resultado da Fase 1 mais a variante 1.

**Condição.** A Fase 1 deixa o Studio sem o botão do Cinematic View. Antes de fundir o #28 e o #26, confirmar que os testes das PR não dependem de ficheiros do #29; o ensaio mostra que compilam em conjunto, mas os percursos `m17_lab_journeys.py` só foram executados com a integração completa.

## Verificação em cada passo

Depois de cada fusão (e antes da seguinte), na árvore de ensaio, sem usar a árvore com alterações de outras sessões:

```sh
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
python -m unittest discover -s tests -p "test_*.py"
cargo build --release
python scripts/run_campaign.py --seeds 42,1337,2026 --output-root runs/campaign
```

Mais os cenários e a campanha documentados no `README`. Depois do passo #24 e seguintes, nos fluxos de interface (Studio compilado e instalado, executados um de cada vez, sem trabalho pesado em paralelo):

| Passo | Percurso adicional |
| --- | --- |
| #24 | `desktop/studio/tests/m15_journeys.py` |
| #25 | `m15_journeys.py` e `m16_journeys.py` |
| #26 | os anteriores e `m17_lab_journeys.py` |
| #27, #28 | os anteriores; testes Rust do `vv-rocket` (ascensão) e do `vv-geo` (pacotes indexados) |
| #29 (Fase 2) | os anteriores e `m17_cinematic_journey.py` (instalação, abertura, desinstalação) |

Preservar os hashes canónicos do M1 e acrescentar testes de regressão se uma fusão mudar geometria, confiança, ordem de eventos ou reprodução. Critério de paragem: qualquer falha dos testes ou dos percursos interrompe a sequência; uma violação deliberada de um cenário é um resultado esperado e não conta.

Resultados esperados de referência (do #30 instalado): Lab 34/34, ciclo do Cinematic 8/8, M16 77/77, M15 48/48. Repetir na máquina antes de os citar.

## Reversão

- Instaladores anteriores em `C:\Users\Duarte\Documents\VV Lab Rollback`: Studio 0.16.0, 0.16.1, 0.16.2 e 0.17.0, com `SHA256SUMS.txt`. Verificar os hashes antes de reinstalar.
- Os ramos `feat/m15-...`, `feat/m16-geospatial`, `feat/m17-*` e `m17-integration` ficam preservados (nunca apagados nem reescritos) e as PR continuam abertas até decisão.
- Cada fusão da Fase 1 é um commit de fusão isolado: reverter com `git revert -m 1 <fusão>`, por ordem inversa, em `main`. Sem reescrita de história nem envio forçado.
- Antes de começar, registar o SHA de `origin/main` (`a23db64`) como ponto de regresso.
- O módulo Cinematic escreve em `%APPDATA%\VV Lab Cinematic`; a desinstalação não apaga essa pasta e deve ser removida à mão se necessário.

## Aceitação exata pedida ao responsável

Respostas por escrito, uma por linha:

1. Autorizar a Fase 1: fundir #24, #25, #26, #27, #28 por esta ordem, com commits de fusão nos SHA `c4179a0`, `0626b75`, `52d69e3`, `51345aa`, `865472f`, só se a verificação de cada passo passar. Sem a palavra «autorizo», nada é fundido.
2. Confirmar que aceita os resultados científicos como **exploratórios** (a subida de dois andares, os veículos de aterragem, o caso v2, as missões curadas), sem revisão humana independente, e que o protocolo `docs/m15-g3-onset-protocol.md` fica por rever antes de correr novas sementes.
3. Aceitação visual da vista geoespacial do 0.16.2 e 0.17.0 (#25, #28), ou lista das correções exigidas.
4. Decisão sobre o #29: variante 1 (integrar como opcional, depois da Fase 1) ou variante 2 (manter como protótipo). Se variante 1: aceitação visual da cena, decisão de distribuir o módulo como segundo artefacto, e confirmação de que o Unreal Engine 5 não é instalado.
5. Confirmar que o #30 é fechado sem fusão, ou fundido só depois de a Fase 1 e a variante 1 estarem em `main` (nesse caso, deve ficar sem diferenças contra a árvore `1735c7d`).

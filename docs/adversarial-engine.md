# Motor de verificação adversarial

O binário `vv-adversary` procura falhas do controlador sem cenários de falha predefinidos. Gera configurações de falhas a partir de uma semente, avalia cada candidato com as duas políticas `ControllerPolicyV1` através de `run_controller_evaluation`, reduz cada falha encontrada e grava casos que `vv-lab replay-m4` reproduz.

O motor usa apenas a API pública da biblioteca. Não altera nenhum ficheiro incluído em `source_sha256()`, nem cenários, esquemas, scripts ou resultados do M1 a M4.

## Execução

```sh
cargo build --release
target/release/vv-adversary campaign --base scenarios/m3/nominal-stop.json --contracts scenarios/m3/contracts-nominal.json --campaign-seed 1337 --sim-seed 1337 --budget 32 --max-failures 4 --output runs/adversary
target/release/vv-adversary replay runs/adversary/campaign.json
target/release/vv-lab replay-m4 runs/adversary/cases/01-dominant_axis-fallback_response/minimized/m4.json
python scripts/adversarial_campaign.py --output-root runs/adversarial
python scripts/adversarial_ablation.py --output-root runs/adversarial-ablation
```

`campaign` grava `campaign.json`, `report.md`, as entradas exatas em `inputs/` e, por falha mantida, `cases/<NN>-<política>-<propriedade>/{original,minimized}/` com o conjunto completo de artefactos M4. `replay` volta a gerar a campanha inteira em memória, exige os mesmos bytes em todos os ficheiros, rejeita ficheiros a mais, ligações simbólicas e nomes terminados em ponto ou espaço ou com `:`, e executa `replay_controller_evaluation` sobre os bytes de cada caso já verificados, sem voltar a ler o disco. Só aceita um argumento cujo nome seja exatamente `campaign.json`, o que exclui fluxos alternativos NTFS como `campaign.json:x`. Recusa `campaign.json` acima de 32 MiB antes de o analisar. O tamanho cresce com o orçamento e com o número e o comprimento dos contratos: com os contratos do repositório e orçamento 512, o maior medido tinha 872 KB; com 128 contratos de 64 bytes, 5,6 a 9,4 MB; o máximo derivado dos limites das entradas ronda 12 MB. Antes da verificação, `replay` só lê `prng`, `limits` e `inputs`; as falhas são lidas dos bytes regenerados, depois de `campaign.json` coincidir com eles. A campanha recusa-se a gravar um `campaign.json` acima do limite. Os nomes dos casos dependem da semente; o nome usado acima é o da semente 1337 nesta versão.

## Falhas injetadas

O motor só altera a configuração de falhas. Não gera geometria nem altera `safety.*`, que pertence ao sistema sob teste.

| Falha pedida | Parâmetro do modelo |
| --- | --- |
| Perda do sensor | `gps.dropout_windows`, `gps.dropout_permille` |
| Observações atrasadas | `communication.delay_min_ticks` e `delay_max_ticks` |
| Perda de observações | `communication.packet_loss_windows`, `packet_loss_permille` |
| Latência do atuador | `DelayedMovement` com `delay_ticks` |
| Perda ou continuação do movimento | `LostMovement`, `ContinuedMovement` |
| Fronteiras temporais | Valores próximos de `fallback_after_ticks`, `max_observation_age_ticks`, `within_ticks` dos contratos, tick 1, tick `steps` e ticks onde o controlo muda de ação (estratégias `guided` e `biased`) |
| Entradas contraditórias | Não existe no modelo, que tem um só sensor. `gps.noise_max_mm` elevado serve apenas como aproximação: a observação contradiz a posição real. |

As falhas já presentes na base ficam como fundo fixo. Os átomos gerados juntam-se a esse fundo.

## Violação, identidade e redução

Uma violação é um invariante de segurança com `passed = false` ou um contrato temporal com resultado `FAIL`. `INCONCLUSIVE` é contado à parte e nunca é violação. Uma violação cuja identidade não se consegue extrair não é descartada: fica em `metrics.unidentified_violations` e a campanha Python falha se esse valor for maior do que zero.

Uma classe de falha que já ocorre no controlo, sem átomos gerados, é marcada `inherited_from_control`. As classes novas ocupam primeiro as vagas de `--max-failures`, e `metrics` separa `novel_classes_found` de `inherited_classes_found`.

A identidade de uma falha segue a regra do M3 (`scripts/m3_failure_signature.py`): política, contrato, versão, tipo de propriedade, tick de ativação, prazo, primeiro tick de violação e mecanismo observado no atuador. Para um invariante de segurança: política, invariante, primeiro tick de falha e tipo do evento que a desencadeou.

A redução tem um orçamento de avaliações por falha. Aplica, por esta ordem, `ddmin` sobre os átomos, truncagem do horizonte, substituição de taxas pelas janelas realizadas, `ddmin`, simplificação de cada átomo, nova truncagem e uma verificação final: retirar qualquer átomo restante altera a identidade. Um passo só é aceite se a identidade completa, incluindo os ticks, e a semente de simulação se mantiverem. O registo de redução guarda cada passo aceite.

A minimalidade verificada é apenas sobre átomos, não sobre cada tick de uma janela, e não é um mínimo global.

## Verificação independente

Para propriedades que se podem recalcular a partir da telemetria (`restricted_zone`, `world_bounds`, movimento em *fallback*, contratos `always`, `never` e `bounded_response` sem correlação de comandos), o motor recalcula a violação sem usar o resultado do monitor da biblioteca. O resultado é `agree`, `disagree` ou `not_applicable`; `agree` exige o mesmo tick de violação. Os contratos correlacionados por comando e os invariantes `safe_fallback` e `valid_state_transitions` ficam `not_applicable`. O recálculo de `restricted_zone` usa as mesmas funções de geometria da biblioteca, por isso não deteta um erro nessas funções. Um `disagree` faz falhar a campanha Python.

## Resultados medidos

Máquina: Windows 11 (10.0.26300), Python 3.14.6, 16 CPUs, Rust 1.99.0. Linux: WSL2 Ubuntu 24.04, kernel 6.18.33.2, Python 3.12.3, Rust 1.99.0. Comando: `python scripts/adversarial_campaign.py`, com orçamento 32, redução 96 e 4 falhas por campanha, sementes 42, 1337 e 2026, estratégia `uniform`.

| Caso | Controlo | Classes encontradas por semente (novas, herdadas do controlo) | Determinismo | Reprodução |
| --- | --- | --- | --- | --- |
| `nominal-stop` (base limpa) | 0 violações | 8, 14, 16 (todas novas) | 69 de 69 ficheiros iguais em cada semente | `replay` 3 de 3; `replay-m4` 24 de 24 |
| `delayed-after-fallback` (base com falha conhecida) | 8 violações | 10, 10, 10 (2 novas e 8 herdadas em cada semente) | idem | `replay` 3 de 3; `replay-m4` 24 de 24 |
| `x-first-overshoot` | 0 violações | 13, 16, 13 (todas novas) | idem | `replay` 3 de 3; `replay-m4` 24 de 24 |

- Falsos positivos: o controlo limpo não teve violações. Nenhum recálculo independente discordou do monitor (0 `disagree`) e não houve violações sem identidade. Os casos `not_applicable` não têm verificação independente.
- Redução total na base limpa: átomos 34 para 17, ticks de falha ativos 242 para 72, passos 192 para 78. Uma falha global (taxa, ruído, atraso de comunicações) conta `steps` ticks ativos, por isso parte desta redução vem da truncagem do horizonte.
- Custo em Windows: 9 campanhas, 99 invocações e 15,8 s no total, entre 0,0011 e 0,0013 s por avaliação, incluindo o arranque do processo.
- Plataformas: a campanha da base limpa nas três sementes produziu 207 ficheiros iguais byte a byte em Windows e em Linux. Em Linux passaram também `cargo fmt --check`, Clippy, 118 testes Rust, 127 testes Python, as campanhas M1 a M4 e a campanha adversarial.

### Falhas encontradas

- `fallback_response`: com atraso de comunicações de 1 a 3 ticks, ou ruído GPS elevado, o controlador entra em *fallback* depois do prazo de 2 ticks do contrato. A base usa o valor predefinido `fallback_after_ticks = 3`. O recálculo independente concorda.
- `command_applied` e `command_resolution`: um único `DelayedMovement` de 3 ticks viola os contratos de 2 ticks.
- `safe_fallback`: um comando atrasado executado depois de uma perda de GPS move o veículo durante o *fallback*.
- `world_bounds`, só com `XFirst` (semente 1337 em `x-first-overshoot`): `ContinuedMovement` no tick 10 com ruído GPS de 2000 mm leva o veículo para fora dos limites. Com as mesmas entradas reduzidas, `DominantAxis` não viola esta propriedade. O recálculo independente concorda.

A matriz de políticas de cada campanha conta os candidatos em que só uma política falha. Em `x-first-overshoot` houve, por semente, 10 a 12 pares candidato-propriedade violados só por `XFirst` e 0 a 1 só por `DominantAxis`. Na base limpa as duas políticas não divergiram, porque a missão é unidimensional.

### Ablação da estratégia de pesquisa

`--search guided` combina o enviesamento para fronteiras com uma segunda fase que muta os candidatos sem violações de maior risco. `--search biased` mantém só o enviesamento. `--search uniform` não usa nenhum dos dois. Comando: `python scripts/adversarial_ablation.py`, sementes 1 a 20, semente de simulação 42, orçamento 32, 120 campanhas em 48,5 s.

| Base | `guided` | `biased` | `uniform` |
| --- | --- | --- | --- |
| `nominal-stop`, classes (média, mínimo a máximo) | 11,7 (6 a 18) | 12,9 (6 a 18) | 15,1 (12 a 20) |
| `x-first-overshoot`, classes | 12,25 (6 a 17) | 14,0 (8 a 18) | 15,35 (10 a 21) |

Por semente, `uniform` encontrou mais classes do que `guided` em 13 e 15 das 20 sementes, e menos em 3 e 4. A fase de mutação e o enviesamento para fronteiras, tal como estão implementados, não melhoraram a descoberta de classes com este orçamento e este modelo. A fase de mutação não gerou candidatos duplicados. Por isso a predefinição é `uniform`; as outras estratégias continuam disponíveis para comparação. Vinte sementes não sustentam uma conclusão geral sobre estas heurísticas.

## Limitações

- O motor encontra violações de contratos e invariantes definidos no laboratório. Não prova ausência de falhas nem mede uma probabilidade de falha.
- A truncagem do horizonte usa pesquisa binária e pressupõe monotonia. Pode não chegar ao horizonte mínimo, mas nunca aceita uma identidade diferente.
- As probabilidades do atuador não são reduzidas na simplificação; só as taxas dos sensores.
- O traço causal de uma violação de segurança não inclui eventos do atuador; a ação realizada é inferida do movimento real.
- Os tempos medidos incluem o arranque dos processos e não são um ensaio de desempenho controlado.
- O limite de 512 MiB de saída só é verificado depois de a campanha ser gerada em memória, e é independente do limite de 32 MiB de leitura de `campaign.json`. A memória cresce com o volume gerado: com `x-first-overshoot` a 10000 passos, `--search guided --budget 128 --minimize-budget 16 --max-failures 16`, uma campanha de cerca de 763 MB recusada atingiu cerca de 811 MB de memória residente e 1,46 GB de memória comprometida antes da recusa; uma revisão independente com orçamento 512 mediu 721 MB recusados, 773 MB residentes e 1,34 GB comprometidos. Só quem executa a campanha controla estes parâmetros. `replay` de uma campanha válida grande custa o mesmo que gerá-la.
- Um `campaign.json` hostil de 32 MiB (milhões de `[]` em `failures[0].identity` ou numa chave desconhecida, ou milhões de entradas em `limits.policies`) não é materializado: as medições ficaram entre 21 e 69 MB de memória residente quando as entradas faltavam, e em 199 MB quando a campanha inteira foi regenerada, perto dos 182 a 186 MB da reprodução válida da mesma campanha. Antes desta correção, o mesmo ficheiro de 32 MiB ocupava 580 MB e um de 256 MiB ocupava 6,4 GB. Acima de 32 MiB é recusado antes da análise, com 4 MB.
- `replay` verifica apenas o fluxo principal de cada ficheiro. Fluxos alternativos NTFS e pastas vazias dentro da campanha não são lidos nem recusados; nunca entram nos dados verificados.
- A estratégia predefinida `uniform` não usa os valores de fronteira; para os explorar, usar `--search biased` ou `--search guided`.
- Cobertura com `cargo llvm-cov --locked --all-targets --fail-under-lines 80` (cargo-llvm-cov 0.9.1): 89,43% das linhas em Windows. A CI aplica o mesmo limite em Linux; no commit anterior mediu 89,42%.

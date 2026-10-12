# Reprodução e compatibilidade

## Contratos preservados

O M2 mantém a versão 1 dos cenários, eventos e relatórios de invariantes. A sequência de sorteios, a ordem de entrega de mensagens e a serialização do M1 continuam a fazer parte do contrato. Os ficheiros de referência em `scenarios/sha256.json` e `scenarios/canonical-seed-42.json` permanecem fixados.

Os códigos de saída também se mantêm:

| Comando | Código | Condição |
| --- | --- | --- |
| `run` | 0 | Todos os invariantes de segurança passam |
| `run` | 2 | Pelo menos um invariante falha |
| `run` | 1 | Erro de configuração ou execução |
| `replay` | 0 | Reconstrução exata, incluindo violações existentes |
| `replay` | 1 | Registo inválido ou resultado divergente |

Uma missão estagnada com segurança PASS mantém código 0. Consultar sempre `mission.json` quando a conclusão da missão for relevante.

## Reconstruir a análise da missão

```sh
cargo run -- run scenarios/basic-mission.json --seed 42 --output runs/basic
cargo run -- replay runs/basic/events.json
cargo run -- analyze runs/basic/events.json --output runs/basic/mission-replayed.json
```

`analyze` reproduz os eventos antes de recalcular a análise. Não lê as conclusões de `mission.json`. Os dois relatórios de missão devem ter bytes iguais quando usam a mesma política de progresso. A referência `source_final_hash` identifica a sequência de eventos analisada.

A política de progresso tem parâmetros explícitos, independentes do cenário v1:

```sh
cargo run -- run scenarios/m2/d-safe-held-stall.json --seed 42 --output runs/hold --stall-window-ticks 8 --min-progress-mm 1
cargo run -- analyze runs/hold/events.json --output runs/hold/mission-replayed.json --stall-window-ticks 8 --min-progress-mm 1
```

Alterar a política pode mudar a classificação da missão; não muda os eventos nem os invariantes. Para reproduzir a classificação, conservar também a política indicada no relatório.

## Limites das garantias

A reprodução rejeita eventos corrompidos, ausentes ou fora de ordem. Reexecuta movimento, decisões e verificações, compara todo o resultado e confirma as entradas geradas pela semente.

A integração contínua compara saídas canónicas de Linux e Windows. Os tempos de execução, diretórios de campanha e orçamentos de tempo real pertencem às ferramentas externas; não entram na evolução da simulação. Um limite de tempo atingido pode interromper a pesquisa de reduções mais cedo numa máquina lenta. A ordem dos candidatos e a decisão de aceitação permanecem determinísticas para a mesma entrada, semente e política.

SHA-256 deteta alterações, mas não autentica a origem. Um registo reconstruído com novos hashes representa outro artefacto; a proveniência exige uma soma de controlo independente ou assinatura.

## Execução e comparação M4

Uma execução M4 exige a política, os contratos e, opcionalmente, a configuração do atuador. O exemplo usa o cenário que torna visível o efeito de X-first quando um passo fixo ultrapassa a coordenada X do destino:

```sh
cargo run -- run-m4 scenarios/m4/x-first-overshoot.json --seed 42 --controller dominant_axis --output runs/m4/dominant --contracts scenarios/m3/contracts-nominal.json --actuator scenarios/m3/actuator-none.json
cargo run -- run-m4 scenarios/m4/x-first-overshoot.json --seed 42 --controller x_first --output runs/m4/x-first --contracts scenarios/m3/contracts-nominal.json --actuator scenarios/m3/actuator-none.json
cargo run -- compare-m4 runs/m4/dominant/m4.json runs/m4/x-first/m4.json --output runs/m4/comparison.json
cargo run -- replay-m4 runs/m4/dominant/m4.json
cargo run -- replay-m4 runs/m4/x-first/m4.json
```

`run-m4` grava os artefactos habituais da execução e um `m4.json` estrito com as versões, política, hashes de fonte/configuração, referências e métricas. `compare-m4` volta a executar e verificar cada política antes de comparar os calendários externos regenerados. Exige cenários, sementes e configurações iguais. `replay-m4` usa a política identificada no manifesto e verifica novamente a execução e os resultados. Estes comandos não alteram `events.json`, `report.json`, `verification.json` nem a reprodução legada.

A campanha M4 predefinida valida o plano antes de iniciar processos. Executa quatro cenários com as sementes 42, 1337 e 2026. Cada par tem seis execuções do simulador: duas iniciais, duas repetições determinísticas e duas reproduções independentes feitas por `compare-m4`. O comando de comparação também produz o artefacto do par. O plano contabiliza 84 invocações lógicas e respeita os limites de 90 invocações, 64 MiB retidos e 120 segundos.

```sh
python scripts/m4_campaign.py --binary target/release/vv-lab --seeds 42,1337,2026 --max-invocations 90 --max-pairs 30 --max-artifact-bytes 67108864 --time-budget-seconds 120 --output-root runs/m4-campaign
```

No Windows, usar `target/release/vv-lab.exe`. `results.json` regista métricas, hashes, repetibilidade, reproduções e consumo de recursos. `m4-fingerprints.json` contém os hashes canónicos usados para a comparação entre plataformas.

Os resultados da campanha aprovada em Linux e Windows, incluindo os calendários, as métricas por política, os hashes de proveniência e os limites medidos, estão em [resultados do M4](m4-results.md). Os artefactos completos ficam associados à execução de CI indicada nesse documento.

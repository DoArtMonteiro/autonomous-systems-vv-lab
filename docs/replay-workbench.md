# Bancada de reprodução visual (v1)

A bancada gera uma página HTML local, só de leitura, a partir de uma execução M6 gravada. Mostra o que aconteceu num contraexemplo, porque falhou uma propriedade e como reproduzir o caso. Não simula nada, não interpola posições e não é uma interface de voo PX4.

O M6 já está integrado em `main` (PR #6, commit de merge `eec47d9`). A bancada lê o formato de evidência do `vv-repair` introduzido no M6.

Manifestos M4 e M5 históricos, gravados com `source_sha256` `38039c255f6f60c8b1a5d50332c2280665df469a1a00ad43b06f5df47bf643cb`, só se reproduzem com uma compilação da revisão `d491b4a`. A compilação atual recusa-os com `M4 source_sha256 does not match this build`, e a bancada mostra essa recusa como falha de reprodução.

## Executar

```sh
cargo build --release --locked
python scripts/replay_workbench.py --run runs/m6-cancel-confirm --output runs/workbench/m6-cancel-confirm.html \
  --case corpus/delayed_after_fallback/07 --candidate watchdog_2_fast_recovery_cancel
python -m http.server 8765 --bind 127.0.0.1 --directory runs/workbench
```

Abrir `http://127.0.0.1:8765/m6-cancel-confirm.html`. A página é um único ficheiro sem dependências externas; o servidor local só serve para navegadores que bloqueiam `file://` (a abertura direta do disco não foi testada). `--run` aponta para a raiz de uma execução de `scripts/m6_repair_lab.py` (com `summary.json`, `analysis.json` e `run/`). A saída não pode ficar dentro de `run/`, porque `vv-repair replay` recusa ficheiros inesperados nessa pasta. `--no-replay` gera a página sem chamar o simulador; nesse caso nenhum caso aparece como verificado.

## O que a página mostra

- **Veredicto**, tal como está em `analysis.json`: decisão, eixos de segurança e progresso, notas, cada critério fixo, os pares reservados e de controlo (corrigidos, quebrados, diferença estrita, missões perdidas por mil, distância) e, por suite, a diferença de risco estrita e o p exato, com a suite que falha a regra a vermelho.
- **Resumo em linguagem corrente** no topo do veredicto: alteração testada (`overrides` de `analysis.json`), pares corrigidos e quebrados e decisão.
- **Seletor de cenário**: os casos agrupados por suite, com a descrição da suite gravada em `evidence.json`.
- **Aviso de origem do traço**: a faixa "Trace shown: BASELINE run" e uma nota com o estado da candidata nesse caso e as violações que mantém. A página diz que não há traço da candidata e que o veredicto assenta nos pares da campanha.
- **Arena e vista ampliada**: a arena mostra o mundo gravado (limites, zona restrita, partida, ponto de passagem) e a caixa da vista ampliada. A vista ampliada mostra os deslocamentos gravados (tracejados em *fallback*), a direção gravada, a observação usada, a ligação entre observação e posição verdadeira, a perda de amostra GPS e o estado de *fallback*. Nada é interpolado entre ticks.
- **Ação realizada**: para os ticks dentro das janelas de falha, a ação pedida, a ação realizada e o comportamento do atuador gravados em `verification.json failures[].counterexample_ticks`; fora dessas janelas a página diz que não foram gravados.
- **Traço do contraexemplo**, de um caso reduzido do corpus ou de uma classe nova: resumo do que o traço contém, mapa 2D com os deslocamentos gravados por tick (`truth_from` para `truth_position` em `tick_result`), a observação usada pelo controlador, linha temporal (estado de *fallback*, amostras GPS perdidas, pacotes perdidos, janela de falha do atuador configurada, eventos do atuador gravados, movimento comandado, movimento real e violações), avanço passo a passo e reprodução automática, e os resultados dos contratos com o gatilho, o prazo e a violação da instância que falhou (de `verification.json failures[]`) e as condições esperada e observada gravadas. A geometria vem do cenário embebido em `events.json` e a janela do atuador de `actuator_config` em `verification.json`, ambos cobertos pelos hashes.
- **Mesmo caso nas outras configurações**: estado (`persisted`, `resolved`, ...), violações e missão, tal como estão em `evidence.json`.
- **Pares quebrados** pela candidata, recontados a partir das linhas de `evidence.json`. Estes pares não têm traço por tick gravado; a página di-lo.
- **Proveniência**: diretório do caso, sha256 de `m4.json` e de cada artefacto, `source_sha256` da biblioteca, `evidence_sha256`, `experiment_sha256`, sementes, comandos de reprodução e a saída de `replay-m4`.

## Validação

Dois níveis, separados na página:

1. **Integridade**: os bytes de `events.json`, `report.json`, `mission.json` e `verification.json` coincidem com os sha256 em `m4.json`; `m4.json` coincide com `evidence.json`; a cadeia de hashes dos eventos liga (só a ligação, os hashes não são recalculados); `scenario.json` e `actuator.json` são iguais às cópias embebidas nos artefactos com hash; `case_dir` fica dentro de `run/`; `evidence_sha256` e `source_sha256` coincidem com `summary.json`; os critérios de aceitação são iguais na evidência e na análise; os pares corrigidos e quebrados recontados coincidem com `analysis.json`.
2. **Verificado**: `vv-lab replay-m4` recalcula o caso com a compilação indicada e termina com 0. Só este nível usa a palavra "verificado".

O cabeçalho mostra quantos casos foram verificados e quais têm problemas. Um ficheiro alterado, em falta ou de outra revisão da biblioteca aparece a vermelho com o motivo (por exemplo `M4 source_sha256 does not match this build`). O traço de um caso que falha a integridade ou a reprodução continua visível, marcado como não sendo evidência.

## Resultados medidos

Máquina Windows 11, Python 3.14, compilação `release` de `efad24e`:

- `runs/m6-cancel-confirm-final2`: 8 verificações de execução passaram; 37 casos, 37 verificados por `replay-m4`, 0 problemas de integridade; 15 pares quebrados por `watchdog_2_fast_recovery_cancel` (8, 4 e 3 por suite), iguais a `analysis.json`.
- `runs/m6-main-final2`: 40 casos, 40 verificados.
- Cópia com um byte alterado em `corpus/delayed_after_fallback/07/events.json`: o caso aparece com `events.json sha256 mismatch` e falha a reprodução; `vv-repair replay` também a recusa.
- Um manifesto M4 histórico (revisão `d491b4a`) dá `M4 source_sha256 does not match this build` com esta compilação.
- `tests/test_replay_workbench.py`: 19 testes com um caso real gerado por `vv-lab run-m4` (ficheiro alterado, ficheiro em falta, hash de `m4.json` diferente da evidência, manifesto editado, `actuator.json` alterado, cadeia de eventos partida, `case_dir` fora de `run/`, sem binário, `summary.json` diferente, recontagem dos pares, traço igual aos `tick_result` gravados, gatilho e prazo da instância violada, eventos do atuador gravados, escape do HTML, saída dentro de `run/`) e 2 testes sobre uma execução real, ativados com `VV_WORKBENCH_RUN=<raiz da execução>`.

## Limitações

- Evidência de simulação num modelo cinemático 2D com aritmética inteira. Não diz nada sobre um veículo real. Nada foi executado em PX4/SITL; o Gate 1A é um fluxo separado e não aceite.
- Só os casos reduzidos têm traço por tick, cada um numa única configuração (aquela onde foi reduzido). As outras configurações têm apenas a linha de estado; os pares da campanha não têm traço.
- O traço completo de eventos do atuador só está gravado como hash (`actuator_trace_sha256`). A página mostra os eventos do atuador gravados dentro da janela de cada falha (`verification.json failures[].fault_events`) e, à parte, a janela configurada, que é configuração e não observação.
- Os números do veredicto vêm de `analysis.json`; só os pares corrigidos e quebrados por suite são recontados a partir das linhas.
- As frases do resumo são calculadas a partir dos campos gravados (por exemplo, o deslocamento é a distância entre `truth_from` e `truth_position`).
- A página é gerada uma vez: a verificação vale para a compilação e o momento indicados na proveniência.
- Em ecrãs estreitos o texto dentro da vista ampliada fica pequeno; os mesmos valores aparecem na ficha do tick. Em casos com percurso vertical, alguns rótulos da vista ampliada podem sobrepor-se.
- Os controlos de passo, reprodução e deslizador e os dois seletores mantêm o foco do teclado; a reprodução avança tick a tick, sem animação, por isso não depende de `prefers-reduced-motion`.
- A página não é totalmente acessível. Limitações conhecidas:
  - na linha temporal só a primeira faixa de cada tick recebe foco do teclado; as outras sete não são alcançáveis por teclado;
  - a 390 px a linha temporal exige deslocamento horizontal para ver os últimos ticks, sem indicação visível;
  - o texto dentro da arena e da vista ampliada fica pequeno em ecrãs estreitos;
  - não foi feito nenhum teste com leitor de ecrã; os rótulos ARIA foram verificados só no código e no navegador.

## Próximos passos

1. Comparação lado a lado de um mesmo par: gravar, numa pasta fora de `run/`, os traços da base e da candidata para os pares quebrados, regenerados com as mesmas sementes já usadas, sem gastar sementes novas.
2. Gravar o traço completo de eventos do atuador (hoje só o hash e os eventos dentro das janelas de falha).
3. Adaptador PX4 externo: ler o pedido `vv-repair.px4-replay-request.v1` e, só depois de aprovação do responsável do Gate 1A, mostrar telemetria SITL no mesmo formato, sempre separada da evidência M6.

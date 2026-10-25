# M7: fundações do Mission Control

O M7 cria a base mínima de uma experiência única de Mission Control sem tocar no núcleo determinístico em Rust. O núcleo, os critérios, a evidência histórica e o Gate 1A do PX4 ficam como estavam. Nenhum ficheiro de `src/` foi alterado.

## Estado: implementado, demonstrável, investigado e futuro

| Item | Estado | Evidência |
| --- | --- | --- |
| Contrato de adaptador `vv-sim-adapter.v1` e adaptador do veículo terrestre (`scripts/sim_adapter.py`) | Implementado e testado | `tests/test_sim_adapter.py`, `tests/test_sim_adapter_concurrency.py` |
| Mission Control local no navegador (`scripts/mission_control.py`), modo Simple completo, Advanced e Research mínimos | Implementado e demonstrável | `tests/test_mission_control.py`; capturas de ecrã locais, fora do repositório |
| Avaliação de Godot 4 (com Rust por GDExtension) e Bevy | Investigado com protótipos medidos | `docs/m7-engine-assessment.md` |
| Recuperação de primeiro andar de foguete | Especificação técnica; nenhuma simulação | `docs/m7-rocket-recovery-spec.md` |
| Aplicação de ambiente de trabalho em 3D | Futuro | depende da decisão de motor |

## Contrato de adaptador `vv-sim-adapter.v1`

O contrato não tenta descrever a física de forma universal. Cada modelo declara o que suporta e recusa tudo o resto. Três esquemas:

- **Descrição** (`describe()`, esquema `vv-sim-adapter.v1`): identidade do modelo (`id`, descrição da física, número de dimensões, `six_dof`, unidades) e capacidades declaradas (missões, controladores, sensores, substituições aceites com os seus intervalos, tipos de falha, requisitos, determinismo, reprodução e limites de execução).
- **Pedido** (`vv-sim-run-request.v1`): `schema`, `model`, `mission`, `seed`, `controller` e `overrides`. Campos desconhecidos são recusados. O adaptador valida cada valor contra a descrição antes de chamar o simulador; a biblioteca Rust volta a validar.
- **Resultado** (`vv-sim-run-result.v1`): `run_id` (sha256 do pedido normalizado e do binário), estados por tick tipados, transições, contratos, falhas de invariantes, eventos do atuador gravados, missão, proveniência (`source_sha256`, `manifest_sha256`, sha256 do binário, das entradas e de cada artefacto), integridade, reprodução e `verdict` (`verified` ou `rejected`, com as razões). `sim_adapter.check_result` valida este contrato; o servidor não envia como sucesso uma resposta que o falhe, e a página recusa uma resposta sem `run_id`.

Regras do contrato:

- Execução limitada: missões com no máximo 200 ticks, 30 s de tempo de execução e 16 MiB de artefactos.
- As entradas são copiadas para a pasta da execução e alteradas aí; os cenários de origem nunca são escritos.
- O mesmo pedido com o mesmo binário dá o mesmo `run_id` e os mesmos bytes em todos os ficheiros da execução.
- Publicação: cada execução escreve numa pasta temporária própria (`.partial-<run_id>-<pid>-<aleatório>`) e só é renomeada para `<run_id>` depois de o simulador terminar com um resultado. Processos diferentes, incluindo dois servidores sobre a mesma pasta, serializam-se num bloqueio por `run_id` (`.locks/<run_id>.lock`, `msvcrt.locking` em Windows e `flock` em POSIX). O sistema operativo liberta o bloqueio se o processo morrer; quem obtém o bloqueio a seguir apaga as pastas temporárias abandonadas desse `run_id`.
- A pasta de execuções tem de estar num disco local: em partilhas de rede o bloqueio pode não excluir outros computadores. Uma execução guardada que fique `rejected` não é reparada automaticamente; para a refazer, apagar à mão a pasta `<run_id>` e repetir o pedido.
- Reutilização: com `reuse`, uma execução guardada não é aceite por si. O adaptador volta a executar o pedido numa pasta temporária e exige que cada ficheiro guardado (entradas, artefactos e manifesto `m4.json`) seja igual byte a byte à regeneração. Assim, um valor por omissão inserido pelo simulador e depois editado, um artefacto de outra execução ou um ficheiro a mais são recusados, mesmo quando os hashes do manifesto foram acertados.
- `verdict` é `verified` só quando `vv-lab replay-m4` recalculou a execução e terminou com 0 e não há problemas de integridade; caso contrário é `rejected` e indica as razões.

### Adaptador do veículo terrestre (`ground-vehicle-2d`)

- Física: modelo cinemático 2D com posições inteiras em milímetros e ticks fixos; sem dinâmica nem modelo de ambiente. `six_dof: false`.
- Missões: as três suites do M6 (`nominal_stop`, `x_first_overshoot`, `delayed_after_fallback`), com as descrições gravadas em `scenarios/m6/experiment.json`.
- Substituições suportadas: semente, política do controlador (`dominant_axis`, `x_first`), uma janela de perda de GPS e uma falha do atuador (`lost_movement`, `delayed_movement`, `continued_movement`).
- Executa `vv-lab run-m4` e lê os artefactos com o código da bancada de reprodução (`trace`, `case_integrity`, `replay_check`).

O que o contrato não cobre: modelos 3D ou 6-DOF, integração contínua no tempo, ambientes (vento, atmosfera), co-simulação e simuladores externos. Esses casos precisam de versões novas do contrato com campos próprios; ver a estratégia de adaptadores externos em `docs/m7-rocket-recovery-spec.md`.

## Mission Control

```sh
cargo build --release --locked
python scripts/mission_control.py --port 8780
```

Abrir `http://127.0.0.1:8780/`.

- **Simple**: escolher uma das três missões, escolher o que falha (padrão da missão, sem falhas, perda de GPS, comando atrasado, comandos perdidos) e correr. O resultado mostra a conclusão da missão, os invariantes de segurança, os contratos temporais, se a evidência foi verificada por reprodução, um resumo do que aconteceu calculado dos registos, a vista 2D de cima com avanço tick a tick e a ficha de cada tick (comando, ação realizada, posição verdadeira, observação, GPS, violações).
- **Advanced**: semente, controlador, janela de GPS e falha do atuador com todos os parâmetros suportados. Valores fora dos intervalos são recusados com uma mensagem.
- **Research**: o pedido normalizado, a proveniência, os sha256 das entradas e dos artefactos, a saída de `replay-m4`, a integridade e os resultados dos contratos.
- A página diz em todos os modos que o modelo é cinemático 2D e que não é uma simulação 3D nem 6-DOF.

Segurança: o servidor só escuta em `127.0.0.1`, recusa pedidos cujo `Host` ou `Origin` não seja ele próprio, aceita só JSON até 16 KiB, ocupa a porta em exclusivo (em Windows, `SO_EXCLUSIVEADDRUSE`; sem isso um segundo servidor podia escutar na mesma porta e responder a parte dos pedidos), corre uma simulação de cada vez, substitui nas respostas os caminhos da pasta de execuções, do binário e do repositório e envia uma Content Security Policy que só permite scripts do próprio servidor (os estilos inline continuam permitidos); a página constrói o DOM sem `innerHTML`.

## Arquitetura do produto

1. **Núcleo determinístico** (Rust, `src/`): simulação, sensores, falhas, invariantes, contratos e reprodução. Não muda no M7.
2. **Contrato de adaptador**: a fronteira entre o produto e cada modelo. Hoje há um adaptador (`ground-vehicle-2d`); o próximo domínio terá o seu, com campos próprios.
3. **Arquivo de execuções** (`runs/`): pedidos, entradas e artefactos com hashes; reverificáveis.
4. **Mission Control**: hoje no navegador local, porque funciona já e sem dependências novas. A aplicação de ambiente de trabalho em 3D virá depois da decisão de motor e consumirá o mesmo contrato.
5. **Bancada de reprodução** (M6): continua a ler as execuções M6 arquivadas.

Distribuição em núcleo aberto (proposta, não decidida): núcleo, contrato, CLI e Mission Control local abertos; funcionalidades de equipa (partilha de execuções, revisão, campanhas em servidor) como possível camada comercial futura.

## Roteiro

| Marco | Conteúdo | Estado |
| --- | --- | --- |
| M7 | Contrato `vv-sim-adapter.v1`, adaptador terrestre, Mission Control local, protótipos de motor, especificação de foguete | Este marco, por integrar |
| M8 | Decisão de motor com mais medições; visualizador de ambiente de trabalho a ler resultados do contrato; modo Simple acessível com leitor de ecrã | Futuro |
| M9 | Contrato v2 para dinâmica contínua; adaptador para um simulador 6-DOF externo verificado contra casos de referência | Futuro |
| M10 | Missão de recuperação de foguete com requisitos e taxonomia de falhas da especificação | Futuro |

## Limitações

- O modelo terrestre é cinemático 2D; a vista 2D e os protótipos 3D mostram posições gravadas, não física 3D.
- O Mission Control é uma aplicação local de navegador, não uma aplicação de ambiente de trabalho.
- Largura de 390 px verificada no Edge em modo headless com emulação de dispositivo pelo protocolo DevTools (`Emulation.setDeviceMetricsOverride`, 390 x 844): `innerWidth`, `clientWidth` e `scrollWidth` iguais a 390 nos modos Simple, Advanced, Research e com resultado, sem deslocamento horizontal. Só com teclado: a tecla Tab passa pelo separador, missão, falha e botão de execução, Enter corre a simulação e põe o foco no título do resultado, as setas mudam de separador e os botões de tick avançam; o erro de semente fica associado ao campo (`aria-invalid`) com o foco nele. A 390 px os rótulos dentro do desenho 2D ficam pequenos (cerca de 7 px); a ficha do tick repete a mesma informação em texto.
- Não foi feito teste com leitor de ecrã real.

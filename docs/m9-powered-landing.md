# M9: aterragem propulsiva em malha fechada

O M9 fecha a malha sobre o andar de foguete do M8. Um controlador recebe apenas observações de sensores com ruído e falhas, comanda acelerador e vetorização do impulso (TVC) e tenta aterrar numa plataforma. Um verificador independente avalia, a partir do estado real, requisitos de contacto e invariantes de voo. A reprodução recalcula estados, observações, comandos e veredictos.

É um demonstrador de verificação num modelo idealizado. Não é software de voo, não foi validado contra dados de voo e não tem modelo de contacto: o "contacto" é o instante em que o plano de saída da tubeira atinge o solo, e os requisitos de contacto substituem a dinâmica das pernas (ver `docs/m7-rocket-recovery-spec.md`).

Este documento fixa as convenções, os limites, as dispersões e os requisitos **antes** da implementação. Os valores dos requisitos, das dispersões e das gamas de falhas não são ajustados depois para que um cenário passe. Os ganhos do controlador são decisões de projeto do controlador e podem mudar; os requisitos não. A primeira versão deste documento foi revista de forma independente antes de qualquer código; as correções dessa revisão estão incorporadas aqui.

## Fronteira e compatibilidade

- O código fica em `crates/vv-rocket`. Os três casos M8 (`ballistic`, `propulsive_descent`, `attitude_dynamics`), os hashes de traço fixados em `tests/reference.rs` e os doze casos de `vv-rocket verify` ficam iguais byte a byte.
- Novo esquema de entrada `vv-rocket-landing.v1`, lido por um comando novo (`vv-rocket land`). O esquema `vv-rocket-case.v1` não muda.
- Novos ficheiros de código entram em `source_sha256`. As execuções M8 guardadas antes desta alteração deixam de passar a verificação "built from the same sources", como já acontecia com qualquer alteração do código; os hashes dos traços M8 mantêm-se.

## Determinismo e aritmética

- Passo fixo `dt = 0,01 s`, tempo `t = k·dt`, integração RK4 do M8 sem alterações. O comando aplicado é mantido constante durante cada passo (retenção de ordem zero).
- No caminho que determina os artefactos (sensores, estimador, controlador, atuadores, verificador) usam-se apenas `+ - * /`, `sqrt` e a função `exp` do crate. Não se usam `sin`, `cos`, `atan2`, `ln`, `powf` nem `mul_add` da biblioteca padrão. Ângulos limite são dados como cossenos ou tangentes literais. Erros de atitude usam o produto vetorial (`sin θ`) e o produto interno (`cos θ`), nunca o ângulo. Graus só aparecem na apresentação em Python.
- Gerador pseudoaleatório: SplitMix64. Cada fonte de aleatoriedade tem um fluxo próprio, com semente `semente ⊕ (identificador da fonte · 0x9E3779B97F4A7C15)`, para que acrescentar uma fonte não altere as outras. Ruído com desvio-padrão `σ`: `σ·√3·(u1 + u2 + u3 + u4 − 2)`, com `u` uniformes em `[0, 1)` (Irwin-Hall); limitado a `±2√3·σ`.

## Plataforma e geometria

- O centro da plataforma é a origem de N, no solo (`z = 0`). A zona de segurança (`S2`) é centrada no mesmo ponto.
- O ponto de contacto é o centro do plano de saída da tubeira, estação 0: `p_base = r + R(q)·(−s_cm, 0, 0)`, com velocidade `v_base = v + R(q)·(ω_B × (−s_cm, 0, 0))`.
- O contacto ocorre no primeiro passo em que `p_base,z ≤ 0`. O estado de contacto é interpolado linearmente entre os estados no início e no fim do passo, na fração em que `p_base,z` cruza zero; o quaternião é interpolado e normalizado. O erro de posição desta interpolação é da ordem de `|a|·dt²/8` (cerca de 1e-4 m). A simulação termina no contacto. Não há rebote, tombamento nem dinâmica das pernas.

## Veículo, atuadores e limites

Veículo do caso `propulsive_descent` do M8 (22 t secos, 8 t de propelente, 845 kN, Isp 282 s). Acrescenta:

| Parâmetro | Valor | Justificação |
| --- | --- | --- |
| Acelerador com o motor aceso | `[0,40, 1,0]` | Motores de grande impulso não reduzem até zero; obriga a uma queima sem pairar. |
| Taxa máxima do acelerador | 1,0 /s, só depois da ignição | Na ignição o acelerador passa diretamente a 0,40. Valor assumido. |
| Corte do motor | comando 0 depois da ignição; irreversível | Sem reacendimento. |
| Fim do propelente | o motor apaga no primeiro passo em que o propelente não chega para o passo completo; evento `flameout` | O M8 rejeita queimas que excedem o propelente; em malha fechada é um resultado possível. |
| Deflexão máxima do TVC | tangente 0,1405408347 (8°) | Valor assumido típico de tubeiras com cardan. |
| Taxa máxima do TVC | 0,35 /s em tangente (cerca de 20°/s) | Valor assumido. |

A direção do impulso no corpo é `normalize(1, g_y, g_z)`, com `(g_y, g_z)` as tangentes da deflexão e `|(g_y, g_z)| ≤ 0,1405408347`. Não há RCS nem momentos aerodinâmicos: antes da ignição a atitude não é controlada.

## Ciclo de controlo, sensores e ordem dos eventos

- Ciclo de controlo: cada 2 passos (50 Hz), nos passos `k` múltiplos de 2, a começar em `k = 0`. GNSS a cada 5 ciclos (10 Hz), a começar em `k = 0`. Sem latência: uma observação no passo `k` mede o estado real no passo `k`.
- Ordem total dentro de cada passo `k`:
  1. abrir e fechar as janelas de falha com `início ≤ k·dt < fim` (eventos `fault_start` e `fault_end`); uma falha que começa em `k` afeta as observações e o atuador desse passo;
  2. se `k` é um passo de controlo: gerar as observações a partir do estado real no passo `k`, atualizar o estimador e calcular o comando;
  3. aplicar o atuador ao comando: ignição com atraso, limites e taxas, TVC preso, perda de impulso, corte; eventos `ignition`, `cutoff`;
  4. integrar o passo com RK4;
  5. verificar o fim do propelente (`flameout`), o contacto (`touchdown`) e os invariantes;
  6. gravar a amostra.

| Sensor | Mede | Ruído (1σ, assumido) | Taxa |
| --- | --- | --- | --- |
| Altímetro radar | `p_base,z` | 0,1 m | cada ciclo |
| GNSS | posição e velocidade do centro de massa | 0,5 m e 0,05 m/s por eixo | 10 Hz |
| IMU | atitude, velocidade angular, aceleração específica em B | 1e-4 rad, 1e-4 rad/s, 0,02 m/s² por eixo | cada ciclo |

Atitude medida: `δθ` com três amostras de ruído de `σ = 1e-4 rad`, `δq = normalize(1, δθ/2)`, `q_med = q ⊗ δq`. Uma observação em falta é registada como ausente, não como zero.

## Configuração conhecida pelo controlador

O controlador recebe as observações e apenas esta configuração: `dt`, período de controlo, gravidade, modelo de massa nominal (`m_dry`, `m_p0`, `s_dry`, `s_p`), `Isp` e `T_max` nominais, limites do acelerador e do TVC, posição da plataforma, velocidade vertical alvo no contacto (−1,5 m/s) e limite de carga axial `S3`. Os valores reais dispersos (abaixo) não lhe são dados.

## Controladores

Duas políticas determinísticas, no mesmo ciclo de controlo:

- **`baseline`**: usa a última observação de cada sensor. Durante uma perda mantém o último valor recebido. Confia no altímetro para a altitude.
- **`robust`**: estimador de navegação próprio. Propaga posição e velocidade com a aceleração específica da IMU e a gravidade, corrige com o GNSS quando disponível e compara o altímetro com a altitude GNSS da base (calculada com `s_cm` nominal). Rejeita o altímetro quando o resíduo excede um limiar durante ciclos consecutivos.

As duas usam a mesma lei de guiamento: ignição quando a desaceleração necessária para atingir a velocidade alvo no contacto ultrapassa uma fração de projeto do impulso nominal; depois, acelerador em malha fechada sobre essa desaceleração, limitado por `S3`; correção lateral por inclinação do impulso, com limite de inclinação comandada; atitude por TVC sobre o erro `x_B × x_desejado`. Podem cortar o motor (por exemplo, se a velocidade vertical estimada ficar positiva perto do solo).

## Dispersões (pré-registadas)

Por semente, uniformes e independentes, aplicadas ao estado real e ao veículo real:

| Grandeza | Nominal | Dispersão |
| --- | --- | --- |
| Posição inicial | (80, 0, 3000) m | ±30 m em x e y; ±50 m em z |
| Velocidade inicial | (−12, 0, −200) m/s | ±3 m/s em x e y; ±10 m/s em z |
| Velocidade angular inicial | (0; 0,004; 0) rad/s | ±0,004 rad/s em y e z |
| Propelente | 8000 kg | ±2% |
| Impulso máximo real | 845 kN | ±2% |
| Isp real | 282 s | ±1% |

A semente 0 é reservada para o caso nominal sem dispersões.

## Falhas e gamas pré-registadas

Cada falha tem tipo, janela no tempo lógico e magnitude, e é registada como evento quando começa e termina. As campanhas usam apenas estas gamas.

| Falha | Efeito | Gama da campanha | Expectativa |
| --- | --- | --- | --- |
| `thrust_loss` | impulso real multiplicado por `1 − magnitude` | 0,05 a 0,30, desde 1 s depois da ignição nominal | recuperável até uma fronteira a medir |
| `ignition_delay` | ignição efetiva `magnitude` s depois do comando | 0,1 a 1,0 s | recuperável até uma fronteira a medir |
| `gimbal_stuck` | TVC fixo na deflexão real do início da janela (zero antes da ignição) | 0,5 a 3 s durante a queima | não recuperável sem RCS para janelas longas |
| `altimeter_bias` | soma `magnitude` m à medida do altímetro | +5 a +50 m | hipótese H1 |
| `altimeter_dropout` | sem medidas do altímetro | janelas de 2 a 10 s | hipótese H1 |
| `gnss_dropout` | sem medidas do GNSS | janelas de 2 a 10 s | hipótese H1 |
| `gnss_bias` | soma `magnitude` m à posição GNSS em x e z | 5 a 30 m | hipótese H3 |
| `imu_accel_bias` | soma `magnitude` m/s² à aceleração específica em `x_B` | 0,05 a 0,5 m/s² | a medir |

Hipóteses, registadas antes da campanha:

- **H1**: em falhas do altímetro e perda do GNSS, `robust` cumpre os requisitos em pelo menos tantos casos como `baseline`.
- **H2**: em falhas de atuador (`thrust_loss`, `ignition_delay`, `gimbal_stuck`), as duas políticas têm resultados semelhantes, porque partilham o guiamento.
- **H3**: com `gnss_bias`, `robust` pode rejeitar um altímetro correto e falhar onde `baseline` aterra. É o modo de falha conhecido da política `robust`.

## Campanha (pré-registada depois da implementação e antes de qualquer execução da campanha)

As sementes 0 a 40 do caso nominal serviram para escolher os ganhos. A campanha usa apenas sementes de reserva, nunca usadas antes: **1000 a 1029** (30 sementes).

- Matriz: o caso nominal e as oito falhas, cada um com as duas políticas e as 30 sementes (540 execuções).
- Para cada par (falha, semente), a magnitude e a janela são sorteadas uniformemente dentro das gamas acima, com `random.Random` do Python (Mersenne Twister) e semente `semente · 100 + índice da falha`. As duas políticas recebem exatamente o mesmo caso: a comparação é emparelhada.
- Cada execução é reproduzida (`vv-rocket replay`); uma execução não verificada é um erro da campanha, não um resultado.
- Varrimento de fronteira: `thrust_loss` e `ignition_delay` em seis magnitudes igualmente espaçadas de cada gama, com as duas políticas e as sementes 1000 a 1009. Se não houver falhas dentro da gama, o resultado é "nenhuma fronteira dentro da gama pré-registada", não uma extrapolação.
- Critério de cada hipótese, por família de falhas: contagem de `landed` com todos os invariantes por política e contagem dos pares discordantes (uma política aterra, a outra não). H1 é **apoiada** se `robust ≥ baseline` em cada uma das três falhas da família; H2 é **apoiada** se, em cada falha de atuador, os pares discordantes forem no máximo 3 de 30; H3 é **observada** se houver pelo menos um par em que `baseline` aterra e `robust` não. Não se calculam valores-p: 30 sementes com dispersões assumidas não sustentam uma inferência estatística sobre um veículo real.

### Janelas das falhas na campanha (pré-registadas antes de executar a matriz)

A gama de magnitudes está na tabela de falhas. As janelas seguem a cronologia do voo nominal (ignição por volta de 4,3 s, contacto por volta de 23,5 s) e não dependem de nenhum resultado da campanha. Todos os tempos são múltiplos de 0,01 s. A ordem dos sorteios com `random.Random(semente · 100 + índice da falha)` é: magnitude (se a falha tem magnitude), duração (se a falha é definida pela duração) e início (se o início é sorteado). Cada sorteio é `a + (b - a) · random()`, arredondado a 0,01 s para tempos e à precisão completa para magnitudes. O índice segue a ordem da tabela de falhas (`thrust_loss` 0 a `imu_accel_bias` 7).

| Falha | Magnitude | Início | Fim |
| --- | --- | --- | --- |
| `thrust_loss` | sorteada em 0,05 a 0,30 | 5,26 s (ignição nominal mais 1 s) | 40,0 s (resto do voo) |
| `ignition_delay` | sorteada em 0,1 a 1,0 s | 0 s | 10,0 s (contém o comando de ignição, que ocorre por volta de 4 s, para qualquer semente) |
| `gimbal_stuck` | 0 | sorteado em 5,0 a 20,0 s (durante a queima) | início mais a duração, sorteada em 0,5 a 3,0 s (termina antes de 23,0 s) |
| `altimeter_bias` | sorteada em 5 a 50 m | 0 s | 40,0 s (voo inteiro) |
| `altimeter_dropout` | 0 | sorteado em 5,0 s a (23,0 s menos a duração), durante a queima | início mais a duração, sorteada em 2 a 10 s |
| `gnss_dropout` | 0 | sorteado em 5,0 s a (23,0 s menos a duração), durante a queima | início mais a duração, sorteada em 2 a 10 s |
| `gnss_bias` | sorteada em 5 a 30 m | 0 s | 40,0 s (voo inteiro) |
| `imu_accel_bias` | sorteada em 0,05 a 0,5 m/s² | 0 s | 40,0 s (voo inteiro) |

Cada janela é construída para atuar: a ignição fica dentro de `ignition_delay`, a perda de impulso começa depois da ignição, os desvios cobrem o voo todo e os cortes e o `gimbal_stuck` ficam dentro da queima. Uma execução cuja falha tenha `acted: false` em `verification.json` é um erro de sorteio da campanha (registado, contado e a campanha falha), não um resultado; a ausência do campo `acted` também é um erro. Esta alteração das janelas de `ignition_delay` e dos cortes foi feita antes de qualquer execução da matriz.

O caso base da campanha é `crates/vv-rocket/landing/nominal.json` (os ganhos do controlador estão nesse ficheiro; a política e o nome são os únicos campos que o script altera por execução, e as falhas são as sorteadas). O script recusa-se a correr se o SHA-256 deste ficheiro não for o seguinte, para o controlador ficar congelado durante a campanha:

| Ficheiro | SHA-256 |
| --- | --- |
| `crates/vv-rocket/landing/nominal.json` | `58b19ff7a85455d4feb0d9c47e9098b21dcb4660416bbfaf822bf433576f1830` |

No varrimento de fronteira a magnitude é a da grelha (seis valores de `low + i · (high - low) / 5`, `i = 0 … 5`, extremos incluídos) e a janela é a da tabela, que nestas duas falhas não é sorteada. A duração do voo nos casos é 40 s; a simulação termina no contacto.

## Requisitos de contacto (assumidos para este demonstrador)

Avaliados no estado real interpolado do contacto, no ponto `p_base`. Valores assumidos para o demonstrador, não especificações de um veículo real.

| Id | Requisito | Limite | Justificação |
| --- | --- | --- | --- |
| `R1_vertical_speed` | `|v_base,z|` no contacto | ≤ 3,0 m/s | capacidade de absorção assumida das pernas |
| `R2_horizontal_speed` | `|(v_base,x, v_base,y)|` no contacto | ≤ 1,0 m/s | evitar escorregamento e tombamento lateral |
| `R3_tilt` | cosseno da inclinação de `x_B` em relação a `z_N` | ≥ 0,9961946981 (5°) | estabilidade estática assumida no contacto |
| `R4_angular_rate` | `|ω_B|` | ≤ 0,1 rad/s | evitar momento de tombamento no contacto |
| `R5_position` | `|(p_base,x, p_base,y)|` | ≤ 10 m | raio útil assumido da plataforma |
| `R6_propellant_margin` | propelente restante | ≥ 1% da carga inicial real | reserva mínima assumida; não é limitativo no caso nominal, só com queimas longas ou perda de impulso |

## Invariantes de voo (segurança)

Avaliados a partir do estado real:

| Id | Invariante | Limite | Quando |
| --- | --- | --- | --- |
| `S1_tilt_envelope` | cosseno da inclinação com o motor aceso | ≥ 0,8660254038 (30°) | cada passo com impulso |
| `S2_keep_out` | `|(p_base,x, p_base,y)|` no contacto | ≤ 50 m | só no contacto |
| `S3_axial_load` | `|impulso + arrasto| / m` | ≤ 3,0 g0 | cada passo; limite estrutural assumido que obriga a reduzir o acelerador com o andar quase vazio (3,9 g0 a impulso máximo e massa seca) |
| `S4_no_relight` | número de ignições | ≤ 1 | cada passo |

Como `R5` (10 m) é mais restrito do que `S2` (50 m), uma violação de `S2` implica uma falha de `R5`.

## Resultado da missão

Separado dos requisitos e dos invariantes, como no veículo terrestre:

- `landed`: contacto com `R1` a `R6` cumpridos;
- `hard_landing`: contacto com pelo menos um de `R1` a `R6` falhado;
- `no_contact`: fim da duração sem contacto (por exemplo, motor aceso a subir ou corte acima do solo seguido do fim da duração).

Uma violação de segurança não é apagada por um resultado `landed`, nem o contrário. Cada falha de requisito ou invariante identifica o identificador, o instante lógico, o estado real, a causa (falhas ativas) e as condições esperada e observada.

## O que não se afirma

- Que o modelo representa um veículo real ou que os requisitos são os de um veículo real.
- Que uma taxa de sucesso numa campanha é uma estimativa de fiabilidade: as dispersões são assumidas e limitadas.
- Que os controladores são ótimos ou adequados para voo.

## Implementação

Esta secção descreve o que foi implementado em `crates/vv-rocket`. Não altera nenhum limite, dispersão, gama de falhas ou requisito das secções anteriores. Tem um desvio explícito de uma convenção: o `flameout` é avaliado ao aplicar o atuador (passo 3 da ordem dos eventos) e não depois da integração (passo 5 da ordem pré-registada). O desvio é necessário porque, avaliado depois da integração, o passo já teria consumido mais propelente do que existe (propelente real negativo), o que o simulador rejeita como estado não físico; avaliado antes, o motor apaga nesse passo e o passo integra sem impulso. O instante do evento é o do passo em que o motor apaga, e o resto da ordem (falhas, controlo, atuador, integração, contacto, registo) mantém-se.

### Módulos

| Ficheiro | Conteúdo |
| --- | --- |
| `prng.rs` | SplitMix64 e ruído de Irwin-Hall; identificadores das fontes: posição inicial 1, velocidade inicial 2, velocidade angular inicial 3, propelente 4, impulso 5, `Isp` 6, altímetro 7, posição GNSS 8, velocidade GNSS 9, atitude da IMU 10, velocidade angular da IMU 11, aceleração da IMU 12. Teste com o vetor de referência da semente 0 (primeira saída `0xe220a8397b1dcdaf`). |
| `landing_types.rs` | Observação, comando, estimativa, ganhos e configuração conhecida pelo controlador. Não importa nada do lado real. |
| `landing_controller.rs` | Navegação (`baseline` e `robust`), guiamento, acelerador e TVC. Só importa `landing_types`, `math` e `G0`; um teste confirma as importações e que o código não menciona `dynamics`, `State` nem `Vehicle`. A entrada é `Controller::step(&Observation) -> (Command, Estimate)`. |
| `landing_model.rs` | Esquema `vv-rocket-landing.v1`, validação estrita (valores pré-registados fixos, ver "Esquema" abaixo) e dispersões por semente. |
| `landing_actuator.rs` | Ignição, taxas e limites, TVC preso, perda de impulso, corte irreversível e `flameout`. |
| `landing_sensors.rs` | Observações com ruído e falhas. |
| `landing_truth.rs` | Ponto de contacto, inclinação, interpolação do contacto e registo por passo para o verificador (inclui o estado no fim do passo do contacto e a ignição comandada e efetiva). |
| `landing_verify.rs` | Verificador independente: `R1` a `R6`, `S1` a `S4`, resultado da missão e `acted` de cada falha, só a partir do registo do estado real; recalcula o contacto. |
| `landing_sim.rs` | Simulação em malha fechada; reutiliza `dynamics::rk4` do M8 sem alterações, com um `Segment` por passo. |
| `landing_run.rs` | Escrita dos artefactos e repetição (`replay`). |

### Comandos e artefactos

```sh
vv-rocket land <landing.json> --seed <u64> --output <pasta>
vv-rocket replay <pasta>
```

`land` escreve, sem nunca sobrescrever, `case.json` (bytes do pedido), `trace.json` (`vv-rocket-landing-trace.v1`), `verification.json` (`vv-rocket-landing-verification.v1`) e `run.json` (`vv-rocket-landing-run.v1`, com `source_sha256`, nome, semente, política, referências com SHA-256, resumo e resultado). Código de saída: 0 se o resultado for `landed` e todos os invariantes passarem; 2 se algum requisito ou invariante falhar ou o resultado não for `landed` (os artefactos são escritos); 3 em erro de entrada ou de uso (inclui um caso rejeitado pela validação); 4 em erro de simulação (um estado não finito ou não físico durante a simulação de uma entrada válida; é distinto de 3 porque o utilizador não pode corrigi-lo com uma opção de linha de comandos, e nenhuma entrada conhecida o provoca, pelo que só o mapeamento do código é testado). `replay` deteta uma aterragem pelo esquema de `run.json`, recalcula o traço, a verificação e o manifesto a partir de `case.json` e da semente guardada e compara-os byte a byte; termina com 0 se verificado e 1 se falhar. A repetição de execuções M8 não mudou.

`trace.json` e `verification.json` não contêm hash do código nem dados da plataforma: dependem só do caso e da semente. O `source_sha256` fica em `run.json`.

### Escolhas que a especificação deixava em aberto

- **Esquema.** O ficheiro de entrada repete os valores pré-registados, para a evidência ser autodescritiva, e a validação rejeita, com uma mensagem que nomeia o campo, qualquer valor diferente do pré-registado em: requisitos e invariantes, dispersões, sensores (desvios-padrão, período de controlo e período do GNSS), veículo (todos os campos de `vehicle`, incluindo os limites e as taxas do acelerador e do TVC), ambiente (gravidade e atmosfera), estado inicial nominal, passo `dt_s` (0,01 s) e velocidade vertical alvo no contacto (-1,5 m/s). As gamas das falhas também são impostas na validação: magnitude dentro da gama, duração da janela de `gimbal_stuck` e dos cortes de sensores dentro de 0,5 a 3 s e 2 a 10 s, no máximo uma falha de cada tipo, no máximo 8 falhas (10 desde o M9.1, que acrescenta dois tipos de falha; ver a implementação M9.1 abaixo). Ficam livres: o nome, `duration_s`, `record_every`, a política e os ganhos do controlador e do estimador (`controller.gains`, que são limitados e são decisões de projeto do controlador) e as falhas dentro das gamas. A validação do M8 continua a correr sobre o caso (limites de passos e de amostras, geometria). `record_every` é múltiplo do período de controlo (2 passos); os casos usam 10 passos (0,1 s). Os testes que precisam de um veículo ou de um estado inicial diferentes (um tanque quase vazio, um início perto do solo) usam o caminho interno sem os valores fixos, que não é exposto pela interface pública.
- **Semente 0.** Não faz sorteios de dispersão (caso nominal), mas o ruído dos sensores continua ligado, com os fluxos da semente 0. Uma execução com a semente 0 não é, por isso, uma execução sem ruído.
- **Fluxos.** Os sensores sorteiam sempre, haja ou não falha, para que uma falha não desloque o ruído das outras amostras. O GNSS só sorteia nos ciclos em que há amostra.
- **Propelente disperso.** Altera `propellant_mass_kg` do veículo real e escala a inércia do propelente na mesma proporção (inércia por quilograma constante). O controlador mantém os valores nominais.
- **Ordem do passo.** Seguida como no documento, com a exceção do `flameout` (ver o início desta secção). A amostra do passo `k` guarda o estado real em `k` com a observação, o estimador, o comando e a saída do atuador aplicada de `k` a `k + 1`. Contacto: evento `touchdown` com `step = k + 1` (o passo em que foi detetado) e `t_s` igual ao instante interpolado; a amostra `touchdown` guarda o estado interpolado. Uma amostra `final` fecha as execuções sem contacto.
- **Aceleração específica da IMU.** No passo `k` é o impulso aplicado no passo anterior (o atuador ainda não foi atualizado) mais o arrasto no estado `k`, a dividir pela massa em `k`, em B.
- **Taxas dos atuadores.** Aplicadas em cada passo (0,01 s) enquanto o comando fica constante durante o ciclo. A ignição leva o acelerador a 0,40 no passo da ignição; o TVC só se move com o motor aceso.
- **`ignition_delay`.** Só atrasa uma ignição comandada com a janela ativa; o atraso é arredondado ao passo mais próximo e fixado quando a ignição é comandada.
- **Janelas abertas no fim.** O evento `fault_end` só é emitido quando a janela fecha dentro dos passos simulados. Uma janela que ainda está aberta no contacto ou no fim da duração (`end_s` maior ou igual à duração, ou uma simulação que termina antes de `end_s`) não tem `fault_end`: o traço termina com o evento `end`, e `active_faults` das amostras mostra o que estava ativo.
- **`acted`.** Cada elemento de `faults` em `verification.json` repete a falha configurada e acrescenta `acted`, que diz se a falha mudou alguma coisa nesta execução. É calculado pelo verificador a partir do registo por passo (falhas ativas, impulso aplicado, calendário de controlo e ignição comandada e efetiva) e recalculado na repetição: `thrust_loss` e `gimbal_stuck` precisam de pelo menos um passo com impulso dentro da janela; `ignition_delay` de uma ignição efetiva depois da comandada (ou ainda pendente no fim); um desvio ou corte de sensor de pelo menos um ciclo de controlo dentro da janela (para o GNSS, um ciclo de GNSS), sem contar o desvio que um corte do mesmo sensor esconde. Uma janela com `acted: false` (por exemplo, uma perda de impulso antes da ignição, ou uma janela que abre depois do contacto) é um caso que não diz nada sobre essa falha.
- **`flameout`.** Desvio da ordem pré-registada (passo 3 em vez do 5). Avaliado ao aplicar o atuador: se o propelente real não chega para o passo completo com o impulso desse passo, o motor apaga nesse passo, com `Isp` e `T_max` reais. O evento regista esse passo.
- **Contacto.** Fração linear de `p_base,z` entre os dois extremos do passo; os restantes componentes interpolam-se linearmente e o quaternião é normalizado depois. O primeiro passo com `p_base,z <= 0` no fim termina a simulação. A simulação calcula esta interpolação para parar e para o traço; o verificador não a lê: recalcula-a com a mesma função a partir do estado no início do passo (no registo) e do estado integrado no fim (guardado no registo do contacto), e avalia `R1` a `R6`, `S1` (no contacto) e `S2` sobre o seu próprio resultado, tal como a fração, o instante e o relatório `touchdown` de `verification.json`. Um registo cujos estados não cruzam o solo não tem contacto para o verificador, e um teste confirma que uma interpolação adulterada no registo não altera nenhum veredicto.
- **Verificador.** `S1` avalia o cosseno da inclinação nos estados de início e de fim de cada passo com impulso (no contacto, o estado interpolado pelo verificador). `S3` avalia `|impulso + arrasto| / m` no início de cada passo, com o impulso desse passo, usando `dynamics::forces`. `S4` conta as subidas de impulso de zero a positivo; como o atuador torna o corte irreversível, só um registo construído à mão o pode violar, e é isso que o teste faz. `S2` só é avaliado no contacto. Sem contacto, os seis requisitos aparecem com `evaluated: false` e `pass: false`. A causa de uma falha são as falhas ativas no passo (para o contacto, o passo em que ocorre).
- **Estimador `baseline`.** Último valor de cada sensor. A posição horizontal e a velocidade são as do último GNSS; a altitude do centro de massa vem do último altímetro (`z = altímetro + s_cm · (x_B)_z`).
- **Estimador `robust`.** Propaga posição e velocidade com a aceleração específica da IMU rodada pela atitude medida e a gravidade, a 50 Hz. Cada medida GNSS corrige a posição com ganho 0,15 e a velocidade com ganho 0,25. O altímetro é comparado com a altitude da base do próprio estimador (GNSS corrigido, propagado pela IMU, `s_cm` nominal): se o resíduo excede 3 m, o altímetro não é usado nesse ciclo e, após 5 ciclos consecutivos, `altimeter_rejected` fica verdadeiro até haver um resíduo abaixo do limiar. Um resíduo aceite corrige a altitude (ganho 0,1) e a velocidade vertical (ganho 0,004 por ciclo, a dividir pelo período). A comparação é, portanto, com a altitude GNSS filtrada e não com a amostra GNSS bruta; com `gnss_bias` o altímetro correto é rejeitado, como previsto em H3.
- **Guiamento.** Partilhado. Desaceleração necessária `a = (v_z² - v_t²) / (2 h)` na base, com `h` limitado inferiormente a 0,5 m. Ignição quando `g + a >= 0,75 · T_max / m` (massa nominal estimada). Depois, a aceleração específica vertical pretendida é `g + a`, limitada a `3 g0 - 0,1 g0`; o acelerador é o do modelo do controlador no ciclo anterior mais a correção do erro de aceleração específica vertical medida (ganho 0,8 por ciclo), o que absorve o arrasto, que o controlador não conhece, e os erros de impulso e de massa. Lateral: velocidade lateral pretendida proporcional ao desvio da base ao centro da plataforma (ganho 0,12 por segundo), limitada pela curva de travagem (1 m/s²) e a desvanecer nos últimos 3 s de descida; aceleração lateral proporcional ao erro de velocidade (0,5 por segundo); a inclinação comandada (tangente) tem o limite 0,2 longe do solo e `0,02 + 0,004 · h` perto dele. Atitude: erro `x_B × x_desejado` em B, controlo PD (0,3 por rad, 0,5 por rad/s) sobre a deflexão, escalado pelo acelerador de referência 0,6. Corte se a velocidade vertical estimada for positiva abaixo de 15 m.
- **`neglected_jet_ratio`.** O resumo do traço regista o máximo de `ε` (M8) amostrado nos dois extremos de cada passo com impulso; só é reportado.

### Resultados medidos

Compilação `--release`, Windows 11, Rust 1.99.0, `vv-rocket land landing/<caso>.json --seed <s>`.

Semente 0, caso nominal. `baseline`: `landed`; ignição aos 4,26 s; contacto aos 23,63 s; `v_base,z` = -1,346 m/s; `|v_base,xy|` = 0,278 m/s; cosseno da inclinação superior a 0,9999; `|ω|` = 0,0064 rad/s; `|p_base,xy|` = 0,516 m; propelente restante 4328,5 kg; pior `S3` 2,195 g0. `robust`: `landed`; contacto aos 23,27 s; `v_base,z` = -1,691 m/s; `|v_base,xy|` = 0,178 m/s; `|ω|` = 0,0041 rad/s; `|p_base,xy|` = 0,483 m; propelente restante 4367,0 kg; pior `S3` 2,367 g0. Os quatro invariantes passam nas duas. `ε` máximo 7,4e-4 (reportado).

Os casos de demonstração em `crates/vv-rocket/landing/` usam magnitudes e janelas fixadas antes de qualquer execução com falhas: ponto médio das gamas pré-registadas (`altimeter_bias` +20 m, `gnss_bias` 15 m, `imu_accel_bias` 0,25 m/s², `thrust_loss` 0,15 a partir de 1 s depois da ignição nominal, `ignition_delay` 0,5 s, `gimbal_stuck` 2 s, `gnss_dropout` 6 s) e o corte do altímetro de 6 s sobre a descida final (18 a 24 s). Cada caso existe com `baseline` e com `robust` (`<nome>-robust.json`). Resultado com as sementes 0 e 1, tal como medido (resultado da missão; requisitos falhados):

| Caso | `baseline` | `robust` |
| --- | --- | --- |
| nominal | `landed`, `landed` | `landed`, `landed` |
| `altimeter_bias` | `hard_landing` (R1 20,4 m/s), `hard_landing` (R1) | `landed`, `landed` |
| `altimeter_dropout` | `hard_landing` (R1 37 m/s), `hard_landing` (R1) | `landed`, `landed` |
| `gnss_dropout` | `hard_landing` (R2, R5), `landed` | `landed`, `landed` |
| `gnss_bias` | `hard_landing` (R5 12,7 m), `hard_landing` (R5) | `hard_landing` (R1 18,4 m/s, R5), `hard_landing` (R1, R2) |
| `imu_accel_bias` | `landed`, `landed` | `landed`, `landed` |
| `thrust_loss` | `landed`, `landed` | `landed`, `landed` |
| `ignition_delay` | `landed`, `landed` | `landed`, `landed` |
| `gimbal_stuck` | `landed`, `landed` | `landed`, `landed` |

Nenhum invariante falhou nestas 36 execuções. Duas sementes não são uma campanha: o quadro mostra apenas que a implementação reproduz o sentido de H1 (as falhas do altímetro e a perda do GNSS prejudicam o `baseline`, não o `robust`) e de H3 (o `gnss_bias` faz o `robust` rejeitar um altímetro correto e falhar com uma velocidade vertical de cerca de 18 m/s), e que as falhas de atuador testadas (H2) tiveram o mesmo resultado nas duas políticas nestas sementes. A taxa de sucesso e as fronteiras de recuperação ficam para a campanha em Python.

**Como os ganhos foram escolhidos.** Os ganhos do controlador foram escolhidos primeiro com o caso nominal e a semente 0. Os casos de demonstração com falhas (magnitudes do ponto médio das gamas, fixadas antes) foram executados com um conjunto de ganhos anterior ao final. Só depois, o limite de inclinação e os ganhos laterais foram reafinados com as sementes 1 a 40 do caso nominal. O quadro acima é o da configuração final. Quer isto dizer que os ganhos finais foram escolhidos depois de se terem visto os resultados de algumas falhas, embora a reafinação tenha usado só o caso nominal. Durante a afinação não houve sementes de reserva: as sementes 0 a 40 do caso nominal serviram todas para afinar. A campanha usa as sementes 1000 a 1029, que não entraram na afinação. As sementes de reserva põem à prova a generalização para outros sorteios das dispersões e para magnitudes e janelas de falhas sorteadas ao acaso; não eliminam o facto de os ganhos terem sido escolhidos depois de se ver o resultado de algumas falhas, nem tornam mais realistas as dispersões e os requisitos, que são assumidos.

Com a configuração final, o caso nominal com sementes de 0 a 40 aterra (`landed` com todos os invariantes) em 41 de 41 execuções com `baseline` e em 40 de 41 com `robust` (semente 28, que falha `R2`). É uma indicação do funcionamento do controlador, não uma estimativa de fiabilidade; estas sementes são as da afinação, pelo que o resultado é otimista.

### Mission Control

O Mission Control serve a página `/landing`, que corre o modelo `rocket-landing` através do adaptador `scripts/landing_adapter.py`. O pedido da página é um objeto `vv-sim-run-request.v3` e a resposta é um `vv-sim-run-result.v3`, que só este modelo usa. **Compatibilidade:** os contratos `vv-sim-adapter.v1` e `vv-sim-adapter.v2`, os respetivos modelos e `/api/describe` ficam iguais; `/api/models` continua a anunciar `vv-sim-adapter.v2` e cada modelo declara o seu contrato (`rocket-landing` declara `vv-sim-adapter.v3`); `sim_adapter.check_result` valida os três e um resultado de um contrato não é aceite por outro. A versão 3 existe porque o pedido precisa de entradas categóricas, que os `overrides` numéricos da versão 2 não exprimem.

- **Pedido v3.** `{schema, model: "rocket-landing", policy, seed, fault}`: `policy` é `baseline` ou `robust`; `seed` é um inteiro em `[0, 2^32 - 1]` (0 é o caso nominal sem dispersões, com o ruído dos sensores ligado); `fault` é `null` ou `{kind, magnitude, start_s, end_s}`. O adaptador valida o tipo, a magnitude e a duração da janela contra as gamas pré-registadas acima (a biblioteca Rust impõe as mesmas), exige tempos múltiplos de 0,01 s dentro de 0 a 40 s e rejeita uma magnitude diferente de zero nas falhas que não a têm (`gimbal_stuck`, `altimeter_dropout`, `gnss_dropout`). As mensagens de erro começam pelo caminho do campo (`fault.magnitude`, `seed`). O caso é gerado a partir de `landing/nominal.json`, só com `name`, `controller.policy` e `faults` alterados; um teste confirma que os valores de demonstração do adaptador reproduzem os 16 ficheiros de falhas `landing/<falha>[-robust].json`.
- **Identidade e integridade.** O identificador da execução é o SHA-256 do pedido canónico, do caso gerado e do binário `vv-rocket`. O diretório guarda `inputs/request.json`, `inputs/case.json` e os quatro artefactos de `vv-rocket land`. `vv-rocket land` termina com 2 quando o resultado não é `landed` ou um invariante falha, e o adaptador trata-o como resultado. A verificação por `vv-rocket replay` recalcula traço, veredictos e manifesto; o adaptador rejeita ainda uma execução cujo nome não é o identificador do pedido guardado, cujo `case.json` não é o que o pedido produz, cuja semente ou política em `run.json` difere do pedido, ou que tenha ficheiros a mais ou ligações simbólicas. O resultado separa `verification` (resultado da missão, `R1` a `R6`, `S1` a `S4`), `replay` e `integrity` e não tem `physics_reference`.
- **Página.** Três afirmações separadas: resultado da missão, invariantes de segurança e evidência (reprodução e integridade). Os veredictos só aparecem de uma execução cuja reprodução foi verificada; uma execução não verificada mostra os dados guardados numa caixa tracejada marcada como não verificada. Mostra a tabela dos requisitos com o limite, o valor observado e a nota de que são requisitos assumidos, a tabela dos invariantes com o pior valor e a primeira falha, o estado no contacto e gráficos SVG sem bibliotecas: altitude (verdade, altímetro e estimativa do controlador), erro da estimativa menos a verdade, velocidade vertical com o limite de `R1`, acelerador, deflexão do TVC e trajetória no solo com os círculos de `R5` (10 m) e `S2` (50 m). As falhas ativas aparecem sombreadas e os eventos numa lista. A estimativa do controlador é do centro de massa e é deslocada para o plano de saída da tubeira com o desvio real de cada amostra, para que a distância à verdade seja só o erro do estimador.
- **Comparar políticas.** Corre `baseline` e `robust`, uma a seguir à outra, com a mesma semente e a mesma falha, e mostra os veredictos lado a lado com as diferenças. Com `altimeter_bias` de 20 m a partir de 10 s e a semente 0, `baseline` termina em `hard_landing` com `R1` de 20,4 m/s e `robust` aterra com 2,35 m/s; os invariantes passam nas duas.
- **Campanha.** O painel lê `runs/m9-campaign/summary.json` (esquema `vv-m9-campaign.v1`), por `GET /api/campaign`, e diz que o ficheiro é lido do disco: as contagens, os veredictos das hipóteses e a lista de execuções são mostrados como estão guardados. O servidor limita o ficheiro a 8 MiB, não segue ligações simbólicas, devolve só os campos conhecidos e nunca o caminho de cada execução. Ficheiro em falta ou inválido dá "no campaign evidence found; run `python scripts/m9_campaign.py`". Clicar numa execução envia-a de novo ao adaptador: é executada e reproduzida nessa altura e a página mostra os veredictos recalculados, ao lado do resultado guardado no ficheiro.
- **Limitações da página.** O modelo é o mesmo demonstrador idealizado e a página repete o que não se afirma (painel "What is claimed"). Os testes do repositório cobrem as rotas, os contratos, o leitor da campanha e as execuções através do servidor; não executam o JavaScript da página num navegador, só confirmam que o ficheiro compila (`node --check`, quando existe) e que não usa `innerHTML`.

### Limitações materiais

- O controlador não conhece o arrasto nem a inércia; compensa o arrasto através da aceleração específica medida e usa ganhos fixos de atitude escalados pelo acelerador. Com o motor desligado não há controlo de atitude, como pré-registado.
- O guiamento lateral é limitado pela inclinação comandada e pela ausência de RCS; desvios iniciais extremos não são recuperáveis.
- O `baseline` mantém a última velocidade GNSS (até 0,1 s de idade) e não usa a IMU para a velocidade; é intencional, e é uma fonte de erro nos últimos segundos.
- O modelo continua sem dinâmica de contacto: `landed` significa que o plano de saída da tubeira atingiu o solo com os seis requisitos cumpridos.

### Resultados da campanha

Campanha pré-registada completa (`preregistered: true` em `summary.json`), executada uma única vez depois da correção do verificador e do campo `acted`, sem alterar a matriz, as gamas, as janelas nem as hipóteses depois de ver resultados. Cada uma das 780 execuções foi reproduzida com `vv-rocket replay` e verificada; não houve erros de sorteio (`acted == false`) nem erros de reprodução.

Contagem das 780 execuções: a matriz tem 9 cenários (nominal e 8 falhas) × 2 políticas × 30 sementes = 540 execuções, que são as do quadro por célula; o varrimento de fronteira tem 2 falhas (`thrust_loss` e `ignition_delay`) × 6 magnitudes × 2 políticas × 10 sementes = 240 execuções, apresentadas à parte. 540 + 240 = 780. As 2 repetições deterministas não entram nesta contagem.

```sh
cargo build --release --manifest-path crates/vv-rocket/Cargo.toml
python scripts/m9_campaign.py
```

Os valores por omissão são a matriz pré-registada (`--seeds 1000..1029`, todas as falhas), `--max-runs 800`, `--max-artifact-bytes 536870912`, `--time-budget-seconds 1800` e `--jobs 4`; o comando expandido fica em `runs/m9-campaign/summary.json`.

- Máquina: Windows-11-10.0.26300-SP0; AMD64 Family 25 Model 97 Stepping 2, AuthenticAMD; 16 logical CPUs; Python 3.14.6.
- Duração medida pelo relógio, fora da simulação: 17,4 s para 780 execuções, 780 reproduções e 2 repetições (`--jobs 4`).
- Artefactos: cerca de 290 MB em `runs/m9-campaign` (pasta ignorada pelo Git).
- `source_sha256` do código: `85f9614d023a6b0c35317ccf5d1e18430773254e40c54b47185f7dcda0aad5b1`; SHA-256 do binário: `9b84be67dcfa1f8491667f0bb6e1d16822ca112c8b50365e496673839a0af14d`.
- Repetição determinista: as execuções `runs/nominal/baseline/seed-1000` e `runs/imu_accel_bias/robust/seed-1029` foram repetidas para uma segunda pasta e `case.json`, `trace.json`, `verification.json` e `run.json` ficaram idênticos byte a byte.
- `summary.json` pode ser regenerado com `python scripts/m9_campaign.py --summarize-only runs/m9-campaign`, que reproduz todas as execuções guardadas antes de recalcular as tabelas.

#### Resultados por célula

`Aterrou` conta `landed` com os quatro invariantes cumpridos. Cada célula tem 30 execuções. As colunas `R1` a `R6` contam execuções em que o requisito foi avaliado e falhou.

| Falha | Política | Aterrou | `hard_landing` | `no_contact` | Invariantes falhados | R1 | R2 | R3 | R4 | R5 | R6 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `nominal` | `baseline` | 29 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| `nominal` | `robust` | 28 | 2 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| `thrust_loss` | `baseline` | 27 | 3 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 |
| `thrust_loss` | `robust` | 28 | 2 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| `ignition_delay` | `baseline` | 26 | 4 | 0 | 0 | 0 | 4 | 0 | 0 | 1 | 0 |
| `ignition_delay` | `robust` | 26 | 4 | 0 | 0 | 0 | 4 | 0 | 0 | 1 | 0 |
| `gimbal_stuck` | `baseline` | 28 | 2 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| `gimbal_stuck` | `robust` | 27 | 3 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 |
| `altimeter_bias` | `baseline` | 0 | 30 | 0 | 0 | 30 | 5 | 0 | 0 | 1 | 0 |
| `altimeter_bias` | `robust` | 27 | 3 | 0 | 0 | 1 | 2 | 0 | 0 | 0 | 0 |
| `altimeter_dropout` | `baseline` | 7 | 23 | 0 | 0 | 22 | 8 | 0 | 0 | 1 | 0 |
| `altimeter_dropout` | `robust` | 28 | 2 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| `gnss_dropout` | `baseline` | 7 | 3 | 20 | 2 | 1 | 3 | 0 | 0 | 2 | 0 |
| `gnss_dropout` | `robust` | 28 | 2 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| `gnss_bias` | `baseline` | 8 | 22 | 0 | 0 | 0 | 0 | 0 | 0 | 22 | 0 |
| `gnss_bias` | `robust` | 0 | 30 | 0 | 0 | 30 | 4 | 0 | 0 | 22 | 0 |
| `imu_accel_bias` | `baseline` | 28 | 2 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| `imu_accel_bias` | `robust` | 28 | 2 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |

#### Pares emparelhados

O mesmo caso (magnitude, janela e semente) foi dado às duas políticas. Cada linha tem 30 pares.

| Falha | Ambas aterram | Só `baseline` | Só `robust` | Nenhuma |
| --- | --- | --- | --- | --- |
| `nominal` | 28 | 1 | 0 | 1 |
| `thrust_loss` | 27 | 0 | 1 | 2 |
| `ignition_delay` | 26 | 0 | 0 | 4 |
| `gimbal_stuck` | 26 | 2 | 1 | 1 |
| `altimeter_bias` | 0 | 0 | 27 | 3 |
| `altimeter_dropout` | 7 | 0 | 21 | 2 |
| `gnss_dropout` | 7 | 0 | 21 | 2 |
| `gnss_bias` | 0 | 8 | 0 | 22 |
| `imu_accel_bias` | 28 | 0 | 0 | 2 |

#### Veredictos das hipóteses

Aplicados os critérios pré-registados, tal como medidos:

- **H1 apoiada.** `robust` aterra mais do que `baseline` nas três falhas: `altimeter_bias` 27 contra 0 de 30, `altimeter_dropout` 28 contra 7, `gnss_dropout` 28 contra 7.
- **H2 apoiada, com um critério fraco.** Pares discordantes: `thrust_loss` 1, `ignition_delay` 0, `gimbal_stuck` 3 (limite pré-registado: 3 em 30; `gimbal_stuck` cumpre no limite exato). O critério só compara as políticas entre si: as duas políticas perdem 2 a 4 execuções de 30 em cada falha de atuador, perto do piso nominal (1 a 2, ver abaixo; `ignition_delay` está um pouco acima), e o critério não mostra que as falhas de atuador sejam recuperáveis.
- **H3 observada, e pior do que o previsto.** Em 8 de 30 pares com `gnss_bias`, `baseline` aterra e `robust` não. Mas `robust` não aterrou em nenhuma das 30 execuções (30 falhas de `R1`, `|v_base,z|` entre 11,3 e 26,1 m/s, mediana 21,6 m/s) e `baseline` aterrou em 8 de 30 (22 falhas de `R5`, a posição fora do raio de 10 m). Nenhum dos dois controladores é robusto a `gnss_bias` nestas gamas.

Os resultados do caso nominal fixam o piso da comparação: com as sementes de reserva, `baseline` aterra em 29 de 30 e `robust` em 28 de 30, sempre por falha de `R2` (velocidade horizontal no contacto). As sementes 1002 (`robust`) e 1018 (as duas políticas) falham `R2` sem qualquer falha injetada. É pior do que as 41 de 41 e 40 de 41 observadas nas sementes 0 a 40, que serviram para afinar os ganhos, como se esperava de sementes não vistas. Várias células de falha (`imu_accel_bias` com 28 de 30 nas duas políticas, `thrust_loss`, `gimbal_stuck`) não se distinguem desse piso com 30 sementes.

Outros resultados que não estavam previstos:

- `baseline` com `gnss_dropout`: 7 de 30 aterram, 3 `hard_landing` e 20 `no_contact`. O traço da semente 1000 mostra o mecanismo: durante a perda (14,9 a 21,99 s) o `baseline` mantém a última velocidade GNSS (cerca de -95,6 m/s) enquanto a velocidade real desce até cerca de -7 m/s; trava em excesso, para a cerca de 124 m e começa a subir. Quando o GNSS regressa, o veículo sobe a cerca de 36 m/s a 165 m. A regra de corte só atua abaixo de 15 m e o acelerador mínimo dá impulso superior ao peso, sem reacendimento possível: o andar afasta-se do solo até ao fim da duração (cerca de 1200 m aos 40 s). Nenhum invariante pré-registado deteta este afastamento; fica registado como `no_contact` e como lacuna dos invariantes. Duas das `hard_landing` (sementes 1005 e 1027) violaram também `S2_keep_out`, os únicos invariantes de segurança falhados em toda a campanha.
- `baseline` com `altimeter_bias`: 0 de 30; `R1` falhou em todas as execuções (`|v_base,z|` entre 10,1 e 32,9 m/s, mediana 23,0 m/s). Com `altimeter_dropout`, 7 de 30 e 22 falhas de `R1`.
- `robust` com `altimeter_bias`: 27 de 30; com `altimeter_dropout` e com `gnss_dropout`: 28 de 30.
- Em nenhuma execução da matriz falharam `R3`, `R4` ou `R6`, nem `S1`, `S3` ou `S4`.

#### Varrimento de fronteira

Seis magnitudes igualmente espaçadas por gama, sementes 1000 a 1009; execuções que aterraram em 10.

`thrust_loss` (fração de impulso perdida):

| Magnitude | `baseline` | `robust` |
| --- | --- | --- |
| 0,05 | 10 | 9 |
| 0,1 | 9 | 9 |
| 0,15 | 9 | 9 |
| 0,2 | 9 | 9 |
| 0,25 | 9 | 9 |
| 0,3 | 6 | 8 |

`ignition_delay` (atraso em s):

| Magnitude | `baseline` | `robust` |
| --- | --- | --- |
| 0,1 | 9 | 9 |
| 0,28 | 9 | 9 |
| 0,46 | 9 | 8 |
| 0,64 | 7 | 7 |
| 0,82 | 7 | 7 |
| 1,0 | 7 | 7 |

Há falhas dentro das gamas, por isso não é um caso de "nenhuma fronteira dentro da gama". Mas as falhas nas magnitudes baixas são todas `R2` da semente 1002, que também falha sem falha injetada. Com `thrust_loss`, só em 0,30 há execuções adicionais perdidas (`baseline` 6 de 10, com as sementes 1000, 1001 e 1004; `robust` 8 de 10, com a semente 1000). Com `ignition_delay`, `baseline` perde as sementes 1005 e 1006 a partir de 0,64, e `robust` perde a 1006 a partir de 0,46 e a 1005 a partir de 0,64 (7 de 10 até 1,0 s). Todas as falhas do varrimento são de `R2`. Dez sementes por ponto não localizam uma fronteira com precisão; o que se observa é um início de degradação no topo das gamas, sem queda para zero.

#### O que a campanha não estabelece

- Não estima a fiabilidade de um veículo: as dispersões, as gamas das falhas e os requisitos são assumidos, e o modelo é idealizado (sem dinâmica de contacto, sem RCS).
- Trinta sementes por célula (10 no varrimento) não sustentam valores-p nem intervalos de confiança; diferenças de uma ou duas execuções não são interpretáveis. Os veredictos de H1, H2 e H3 aplicam apenas os critérios pré-registados.
- Cada execução injeta uma falha de cada vez, com magnitude e janela sorteadas uniformemente. Falhas combinadas, fora das gamas ou com outra distribuição temporal não foram avaliadas.
- O controlador foi afinado no caso nominal com as sementes 0 a 40; as sementes 1000 a 1029 são disjuntas dessas. A afinação usou apenas o caso nominal, mas os casos de demonstração com falhas tinham sido executados com um conjunto anterior de ganhos (ver Implementação). O piso nominal acima mostra que a taxa de aterragem sem falhas não é 100% em sementes novas.
- A causa das 22 falhas de `R5` do `baseline` com `gnss_bias` não foi investigada. O mecanismo das execuções `no_contact` do `baseline` com `gnss_dropout` foi confirmado apenas no traço da semente 1000.

## M9.1: endurecimento de segurança (pré-registado antes da implementação)

A campanha M9 mostrou duas lacunas. Primeira: com `gnss_dropout`, o `baseline` para acima do solo e sobe com o motor aceso até mais de 1 km (20 de 30 execuções), e nenhum invariante o deteta. Segunda: com `gnss_bias`, o `robust` rejeita o altímetro correto no primeiro ciclo (0,1 s), porque o enviesamento está presente desde o início e o seu filtro só confia no GNSS; aterra 0 de 30 vezes, com 11 a 26 m/s. O M9.1 acrescenta um invariante, uma política nova e uma campanha nova. Não altera o M9: as políticas `baseline` e `robust`, os requisitos `R1` a `R6`, os invariantes `S1` a `S4`, as gamas, as sementes e os resultados da campanha M9 ficam como estão.

### Dados usados no projeto

Os dados de projeto do M9.1 são as sementes 0 a 40 do caso nominal e as 780 execuções da campanha M9 (sementes 1000 a 1029). Nessas execuções, nenhuma das 580 aterragens sobe acima do mínimo da altitude da base desde a ignição (subida máxima 0 m, nas amostras de 0,1 s); as únicas 20 subidas acima de 0,5 m são as 20 execuções `no_contact` do `baseline` com `gnss_dropout`, entre 136 e 1358 m. A aceitação usa sementes novas, **2000 a 2029**, nunca executadas antes.

### Invariante novo

| Id | Invariante | Limite | Quando |
| --- | --- | --- | --- |
| `S5_no_powered_ascent` | subida de `p_base,z` acima do seu mínimo desde a ignição | ≤ 5,0 m | cada passo com impulso, depois da ignição |

Justificação: uma queima de aterragem sem capacidade de pairar (acelerador mínimo com impulso superior ao peso) só é segura em descida; subir com o motor aceso significa que o veículo parou acima do solo e já não pode tocar suavemente sem cortar o motor. 5 m fica muito acima da subida observada nas aterragens (0 m) e da interpolação do contacto (cerca de 1e-4 m), e muito abaixo das subidas observadas (pelo menos 136 m). Avalia-se no estado real, em todos os passos, com o mesmo verificador independente; não depende do controlador. Com `S5`, os artefactos passam a `vv-rocket-landing-verification.v2`.

Previsão P1: ao reavaliar os 780 casos da campanha M9 com o verificador novo, os traços ficam idênticos byte a byte e `S5` falha exatamente nas 20 execuções `no_contact` do `baseline` com `gnss_dropout`, e em nenhuma outra.

### Deteção e recuperação são coisas diferentes

- **Deteção**: o controlador declara, na sua estimativa, uma inconsistência entre sensores (`sensor_disagreement`) ou uma subida que leva ao corte (`ascent_abort`), com o instante. É o que o controlador afirma, registado no traço; o verificador não o usa para nenhum veredicto.
- **Contenção**: os invariantes de segurança `S1` a `S5` cumprem-se no estado real.
- **Recuperação**: `R1` a `R6` cumprem-se no contacto (resultado `landed`).

A campanha apresenta, por célula, as três contagens separadas e, no caso nominal e nas falhas que não enviesam sensores, a taxa de falsos alarmes de `sensor_disagreement`.

### Política nova `guarded`

`baseline` e `robust` não mudam. `guarded` usa o estimador do `robust` (IMU, GNSS, comparação com o altímetro) e acrescenta duas regras:

1. **Inconsistência de altitude.** Se o resíduo entre o altímetro e a altitude da base do estimador exceder 3 m durante 5 ciclos consecutivos, declara `sensor_disagreement`. Sem terceira fonte de altitude, não sabe qual das duas está errada. Escolhe a mais conservadora para a travagem: a que indica **menor** altitude. Enquanto a inconsistência durar, o guiamento usa essa altitude.
2. **Corte por subida.** Depois da ignição, se a velocidade vertical estimada for superior a +1 m/s durante 1 s seguido, corta o motor e declara `ascent_abort`. É uma terminação do voo que contém o veículo perto da plataforma; a queda livre a partir de `h` dá cerca de `√(2·g·h)` no contacto, pelo que não é uma recuperação.

Limiares de `guarded` afinados apenas com os dados de projeto acima; depois congelados pelo hash do modelo de caso.

### O que a política não pode fazer (previsto agora)

- **Posição horizontal.** `gnss_bias` desloca também `x`. Não há segunda fonte horizontal, por isso nenhum controlador deste modelo pode cumprir `R5` quando o deslocamento horizontal excede 10 m. Com magnitudes uniformes entre 5 e 30 m, cerca de 1 em 5 sorteios fica abaixo de 10 m. A célula `gnss_bias` não pode ficar "verde"; o resultado honesto esperado é contacto suave fora da plataforma (`R1` cumprido, `R5` falhado, resultado `hard_landing`).
- **Dependência do sinal.** A regra "menor altitude" acerta quando a fonte errada lê **alto**, como nas duas falhas pré-registadas do M9 (`altimeter_bias` e `gnss_bias`, ambas positivas). Quando a fonte errada lê **baixo**, a regra escolhe a errada, trava cedo, para acima do solo e só lhe resta o corte. Para medir esse custo, o M9.1 acrescenta duas falhas novas, com gamas próprias, sem alterar as do M9:

| Falha | Efeito | Gama | Janela |
| --- | --- | --- | --- |
| `altimeter_bias_low` | subtrai `magnitude` m à medida do altímetro | 5 a 50 m | 0 a 40 s |
| `gnss_bias_low` | subtrai `magnitude` m à posição GNSS em x e z | 5 a 30 m | 0 a 40 s |

### Campanha de aceitação M9.1

- Sementes 2000 a 2029; 11 cenários (nominal, as 8 falhas do M9 e as 2 novas) × 3 políticas (`baseline`, `robust`, `guarded`) × 30 sementes = 990 execuções. Sem varrimento de fronteira.
- Sorteio de magnitude e janela como no M9 (`random.Random(semente · 100 + índice)`, índices 0 a 7 como no M9, 8 e 9 para as falhas novas); as três políticas recebem o mesmo caso.
- Cada execução é reproduzida; o modelo de caso é congelado por hash antes da execução única.
- Reavaliação retrospetiva (P1) dos 780 casos M9 com o binário novo, separada da aceitação.

Hipóteses, com critérios numéricos:

- **G1, deteção**: `guarded` declara `sensor_disagreement` em pelo menos 27 de 30 execuções em cada uma de `altimeter_bias`, `gnss_bias`, `altimeter_bias_low` e `gnss_bias_low`; e em no máximo 1 de 30 no caso nominal.
- **G2, contenção da subida**: `guarded` não viola `S5` em nenhuma das 30 execuções com `gnss_dropout`.
- **G3, contacto suave com `gnss_bias`**: `guarded` cumpre `R1` em pelo menos 27 de 30 execuções. O número de `landed` não deverá exceder o número de sorteios com magnitude inferior a 10 m; é um teto previsto, não um objetivo.
- **G4, sem regressão**: em cada um dos 9 cenários do M9, `guarded` aterra em pelo menos `robust − 2` execuções.
- **G5, custo da regra conservadora**: em `altimeter_bias_low` e `gnss_bias_low`, regista-se o resultado de `guarded` sem critério de sucesso; prevê-se que não recupere.

Uma hipótese que falhe é reportada como falhada. Nenhum limiar de `S5`, nenhum requisito e nenhuma gama é ajustado depois de ver a campanha de aceitação.

### Emenda depois da revisão independente (antes de qualquer código M9.1)

Uma revisão independente desta secção, feita antes da implementação, encontrou dois bloqueios e várias definições em falta. As regras abaixo substituem as anteriores onde as contradizem; nada foi executado entre a secção acima e esta emenda.

**`S5` passa a ser avaliado na altitude do centro de massa `r_z`**, não em `p_base,z`: com a inclinação permitida por `S1` (30°), `p_base,z` pode subir cerca de 2 m sem o centro de massa subir. "Ignição" é o primeiro passo com impulso positivo, como em `S4`. A cada passo com impulso, nos estados de início e de fim do passo (como `S1`), a subida é `r_z` menos o mínimo corrente de `r_z` desde a ignição até esse estado. Uma subida balística depois do corte não é avaliada (não é subida propulsiva). Orçamento do limite de 5 m: com a regra de corte por subida, a velocidade vertical chega a +1 m/s em 0,15 a 0,3 s e a regra espera 1 s, mais um ciclo e um passo do atuador; com cerca de 3 m/s² de aceleração líquida ao acelerador mínimo, a subida até ao corte é de 3 a 3,5 m. O limite de 5 m aceita essa contenção e rejeita qualquer subida mantida. A medição dos dados de projeto (0 m) foi feita nas amostras de 0,1 s, dez vezes mais espaçadas do que os passos onde `S5` é avaliado.

**P1 redefinida.** Os campos novos da estimativa (`sensor_disagreement`, `ascent_abort`) só são escritos quando a política os produz, para que os traços de `baseline` e `robust` não mudem. Os ganhos de `guarded` são opcionais no esquema, com valores por omissão, para que os 780 `case.json` guardados continuem válidos. O M9.1 usa um modelo de caso próprio, `landing/m91-nominal.json`, congelado pelo seu hash; `landing/nominal.json` e o seu hash não mudam. Reavaliação retrospetiva: para cada uma das 780 execuções M9, correr `land` com o `case.json` guardado e a mesma semente, comparar `trace.json` byte a byte com o guardado e ler `S5` do `verification.json` novo. P1 mantém-se: traços idênticos e `S5` falha exatamente nas 20 execuções `no_contact` do `baseline` com `gnss_dropout`.

**Regra 1 de `guarded`, especificada.** A escolha de altitude só afeta o guiamento: o estado do estimador não é alterado (de outro modo o resíduo anular-se-ia e a regra oscilaria). Durante a inconsistência, todos os usos da altitude da base no guiamento (ignição, acelerador, desvanecimento lateral, limite de inclinação, corte a 15 m) leem a altitude escolhida, `min(altímetro, altitude da base do estimador)`; a velocidade vertical é a do estimador. Sem amostra do altímetro nesse ciclo, usa a altitude do estimador. A saída da inconsistência segue a do `robust` (um resíduo abaixo de 3 m). `sensor_disagreement` regista o primeiro instante em que a inconsistência é declarada.

**A regra 2 precisa de um caso onde possa atuar.** Em `guarded`, o corte a 15 m atua antes da regra 2 nas falhas que leem baixo, e com `gnss_dropout` o estimador do `robust` não perde a velocidade. Para testar a regra contra a falha observada, acrescenta-se a política `baseline_guarded`: o `baseline` sem alterações mais a regra 2. Corre só no caso nominal e em `gnss_dropout` (60 execuções). Previsão, escrita agora: durante a perda, a velocidade estimada do `baseline` fica congelada e negativa, pelo que a regra 2 só atua quando o GNSS regressa; o veículo já terá subido dezenas de metros. Prevê-se que `baseline_guarded` elimine o afastamento (`no_contact`), mas continue a violar `S5` e caia com velocidade elevada (`R1` falhado): contém, não recupera. Um teste unitário do controlador, com observações sintéticas a subir acima de 15 m, confirma que a regra 2 corta.

**Contagem dos resultados.**

- Deteção: a bandeira aparece em pelo menos um ciclo da execução. Para `robust`, `altimeter_rejected` é a mesma deteção e é apresentada ao lado.
- Contenção: nenhum invariante avaliado falhou. Sem contacto, `S2` não é avaliado e não conta como falha.
- Recuperação (`landed`): contacto com `R1` a `R6` e todos os invariantes `S1` a `S5`.
- Falsos alarmes: nas células nominal, `thrust_loss`, `ignition_delay`, `gimbal_stuck`, `altimeter_dropout`, `gnss_dropout` e `imu_accel_bias`, cada bandeira em no máximo 1 de 30 execuções de `guarded`.

**Hipóteses revistas.**

- G1: `guarded` declara `sensor_disagreement` em **30 de 30** execuções em cada uma de `altimeter_bias`, `gnss_bias`, `altimeter_bias_low` e `gnss_bias_low` (com magnitude de pelo menos 5 m e limiar de 3 m, o resíduo excede o limiar desde o primeiro ciclo); falsos alarmes como definido acima.
- G2: `guarded` não viola `S5` nas 30 execuções com `gnss_dropout` (herda o estimador do `robust`, que não subiu no M9; não testa a regra 2). G2b: `baseline_guarded` com `gnss_dropout` tem 0 execuções `no_contact`; a previsão de que `S5` e `R1` continuam a falhar é registada, sem critério de sucesso.
- G3: `guarded` cumpre `R1` em pelo menos 27 de 30 execuções com `gnss_bias`. Teto aproximado de `landed`: com as sementes 2000 a 2029, os sorteios de `gnss_bias` têm 3 magnitudes abaixo de 10 m (5,74; 7,69; 10,00) e uma em 10,33 m; prevê-se cerca de 3 ± 1 `landed`.
- G4: em cada um dos 9 cenários do M9, `guarded` aterra em pelo menos `robust − 2` execuções; a linha `gnss_bias` não é informativa (o `robust` teve 0). Verificação mais forte: em todas as execuções em que nenhuma bandeira de `guarded` aparece, a sequência de comandos de `guarded` é igual à do `robust` no mesmo caso.
- G5: sem critério de sucesso. Previsões para as falhas novas: `guarded` escolhe a fonte que lê baixo, trava cedo, para a cerca de `h ≈ enviesamento` acima do solo verdadeiro, corta e não recupera; `baseline` com `altimeter_bias_low` corta a cerca de `h = enviesamento + 15 m` verdadeiros e falha `R1`; `robust` com `altimeter_bias_low` rejeita o altímetro e deverá aterrar como em `altimeter_bias`; com `gnss_bias_low`, `baseline` e `robust` deverão espelhar verticalmente o `gnss_bias`.

**Restrições de implementação.** As falhas novas usam a regra de `acted` dos enviesamentos de sensores; continua a haver no máximo uma falha de cada tipo; as gamas novas entram na validação e na tabela de gamas do adaptador. A campanha de aceitação passa a ter 990 + 60 = 1050 execuções.

### Implementação M9.1

Esta subsecção descreve o que foi implementado em `crates/vv-rocket` para o M9.1. Não altera nenhum texto, limite, gama ou hipótese pré-registados acima. Os resultados são os medidos.

**Módulos alterados.** Não há ficheiros de código novos (a lista de `source_sha256` mantém-se).

| Ficheiro | Alteração |
| --- | --- |
| `landing_types.rs` | Políticas `guarded` e `baseline_guarded`; campos `sensor_disagreement` e `ascent_abort` da estimativa (`Option<bool>`, só serializados quando a política os produz); ganhos opcionais `ascent_abort_vz_mps` e `ascent_abort_time_s` (por omissão 1 m/s e 1 s); `ControllerFlags` e `FlagInstant`. |
| `landing_controller.rs` | Regra 1 e regra 2 (ver abaixo). `baseline` e `robust` não mudam. |
| `landing_model.rs` | Falhas `altimeter_bias_low` (5 a 50 m) e `gnss_bias_low` (5 a 30 m) na validação; validação dos dois ganhos novos; `MAX_FAULTS` passa de 8 a 10 (há dez tipos, no máximo um de cada). |
| `landing_sim.rs` | Aplicação das falhas novas; primeiro instante de cada bandeira; evento `ascent_abort`. |
| `landing_verify.rs` | Invariante `S5_no_powered_ascent`; esquema `vv-rocket-landing-verification.v2`; bloco `controller_flags`; `acted` das falhas novas. |
| `landing_run.rs` | Copia as bandeiras da execução para o bloco `controller_flags`. |
| `landing/` | `m91-nominal.json` (modelo de caso de `guarded`, SHA-256 `69ecad65e9ec4329ffc74a3b985dbb7dc60d5cdaa1e4a9a380f296a76f68114b`), `gnss-bias-guarded.json`, `gnss-dropout-baseline-guarded.json` e `altimeter-bias-low-guarded.json`. `nominal.json` e o seu SHA-256 não mudam. |
| `scripts/m91_retrospective.py` | Reavaliação retrospetiva P1. |

**Esquema v2.** `verification.json` passa a ter `S5_no_powered_ascent` (limite 5 m, unidade m) depois de `S4_no_relight` e um bloco `controller_flags` com o rótulo `controller-reported; not used for any verdict` e os campos `sensor_disagreement_first`, `ascent_abort_first` e `altimeter_rejected_first`, cada um `null` ou `{step, t_s}` do primeiro ciclo de controlo em que a bandeira apareceu. O bloco existe em todas as políticas; `null` quer dizer que a bandeira não apareceu ou que a política não a produz (`altimeter_rejected_first` é a deteção do `robust`, para comparar com `sensor_disagreement_first` do `guarded`). O verificador não lê o bloco: é copiado do registo do controlador por `landing_run.rs`, depois de `verify`. O esquema do caso (`vv-rocket-landing.v1`) e o de `trace.json` (`v1`) não mudam.

**Resultado da missão e código de saída.** `landed` exige agora `R1` a `R6` e `S5`; uma violação de `S1` a `S4` continua a não alterar o resultado da missão. Um contacto suave depois de subir mais de 5 m com o motor aceso é `hard_landing` com `requirements_pass: true` e `invariants_pass: false`. O código de saída 0 de `vv-rocket land` mantém a definição (resultado `landed` e todos os invariantes cumpridos, agora incluindo `S5`); a lógica não precisou de mudar.

**Escolhas de implementação.**

- O limite de `S5` (5,0 m) é uma constante do verificador (`S5_MAX_ASCENT_M`) e não um campo do caso: os 780 `case.json` guardados não o têm, e assim não pode ser movido por um ficheiro de caso. A subida é `r_z` menos o mínimo corrente de `r_z` desde o primeiro passo com impulso; todos os estados desde a ignição entram no mínimo (incluindo os de passos sem impulso), e só se avalia no estado inicial e final de cada passo com impulso. Sem ignição, `S5` não é avaliado (`evaluated: false`, cumprido).
- Regra 1: usa o contador de rejeição do estimador do `robust` (resíduo acima de `altimeter_residual_threshold_m` = 3 m durante `altimeter_rejection_cycles` = 5 ciclos seguidos), pelo que não há ganhos novos para a deteção. `sensor_disagreement` é o estado corrente (verdadeiro enquanto a inconsistência durar); o primeiro instante fica em `controller_flags`. A altitude de guiamento é `min(amostra do altímetro do ciclo, altitude da base do estimador)` quando a inconsistência está declarada; sem amostra, é a do estimador. O estado do estimador nunca é alterado pela escolha, e `guarded` e `robust` têm estimativas de posição e velocidade idênticas com as mesmas observações.
- Regra 2: conta ciclos de controlo seguidos com a velocidade vertical estimada do centro de massa (`nav.v.z`) acima de `ascent_abort_vz_mps`, só com o motor aceso; corta ao ciclo número `round(ascent_abort_time_s / período do ciclo)` = 50 (cada ciclo vale um período de 0,02 s). O corte a 15 m continua em todas as políticas e é avaliado antes. `ascent_abort` na estimativa fica verdadeiro depois do corte. O evento `ascent_abort` precede o evento `cutoff` do mesmo passo.
- As falhas `*_bias_low` somam-se às respetivas falhas `*_bias` quando coexistem (`+=` e `-=` sobre o desvio do passo); `acted` segue a regra dos desvios (um ciclo de controlo, ou de GNSS, dentro da janela e sem corte do mesmo sensor).

**Retrospetiva P1.** `python scripts/m91_retrospective.py --binary crates/vv-rocket/target/release/vv-rocket` volta a correr `vv-rocket land` com o `case.json` e a semente de `run.json` de cada execução guardada de `runs/m9-campaign` (as 540 da matriz em `runs/` e as 240 do varrimento em `boundary/`; as 2 repetições deterministas não entram), para uma pasta temporária, e compara `trace.json` byte a byte. Resultado, tal como medido: 780 execuções, 780 traços idênticos, `S5` falha em exatamente 20, todas `baseline` com `gnss_dropout` e resultado `no_contact` (subida máxima entre 136,4 e 1358,8 m), e em nenhuma outra. A previsão P1 verifica-se. O resultado está em `runs/m91-retrospective/retrospective.json` (pasta ignorada pelo Git). `runs/m9-campaign` não foi alterada; as suas execuções deixam de passar `vv-rocket replay` (código e `verification.json` v1 mudaram, como já acontecia com qualquer alteração do código).

**Identidade dos traços.** Os SHA-256 de `trace.json` dos 18 casos que já existiam, com as sementes 0 e 1 (36 traços), registados antes das alterações, ficaram iguais e estão fixados em `m9_demo_traces_are_byte_identical_after_m91`, tal como os dos casos nominais e os do M8.

**Casos de demonstração M9.1.** Magnitudes fixadas antes de qualquer execução (pontos médios das gamas: `gnss_bias` 15 m, `altimeter_bias_low` 27,5 m) e janelas copiadas dos casos M9 correspondentes. Sementes 0 e 1, sem ajuste de limiares; nenhum invariante falhou:

| Caso | Semente 0 | Semente 1 | Bandeiras |
| --- | --- | --- | --- |
| `m91-nominal` (`guarded`) | `landed` | `landed` | nenhuma |
| `gnss-bias-guarded` (8 s a 40 s) | `hard_landing` (`R5` 12,3 m; `R1` cumprido) | `landed` | `sensor_disagreement` e `altimeter_rejected` aos 8,18 s |
| `gnss-dropout-baseline-guarded` (8 s a 14 s) | `hard_landing` (`R2` 1,86 m/s, `R5` 12,8 m) | `landed` | nenhuma |
| `altimeter-bias-low-guarded` (10 s a 40 s) | `hard_landing` (`R1` 23,0 m/s) | `hard_landing` (`R1` 22,9 m/s) | `sensor_disagreement` aos 10,08 s; sem `ascent_abort` (o corte a 15 m atuou) |

A janela de 6 s do demonstrador `gnss-dropout` não faz o `baseline` subir nestas sementes, pelo que a regra 2 não atua nesses dois casos. Para a testar contra a falha observada, os testes usam a janela e a semente 1000 da campanha M9 (14,9 s a 21,99 s) sobre `nominal.json`: `baseline` dá `no_contact` com `S5` a falhar (subida de 1073 m); `baseline_guarded` corta aos 22,98 s (`ascent_abort`, depois `cutoff`), deixa de ser `no_contact` e dá `hard_landing` com `R1` 68,2 m/s e `S5` (59,2 m) e `S2` (51,1 m) falhados, como previsto na emenda (contém, não recupera); `guarded` aterra sem bandeiras. É uma execução, não uma campanha.

**Verificação.** `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test` e `cargo build --release` em `crates/vv-rocket` passam; `vv-rocket verify` termina com 0; cobertura de linhas 97,4% (`cargo llvm-cov`). Os testes novos cobrem `S5` com registos construídos à mão (cumpre a 0 m e a 4,9 m, falha a 5,1 m, subida sem impulso não avaliada, movimento da base só por atitude não conta), as regras 1 e 2 com observações sintéticas, as falhas novas (efeito, gamas, `acted`), os campos opcionais do esquema, a repetição das execuções M9.1 e a identidade byte a byte dos traços anteriores.

#### Escolhas de implementação da campanha de aceitação (escritas antes da execução)

Estas escolhas resolvem ambiguidades do pré-registo pela leitura mais literal. Foram escritas e confirmadas por testes antes da execução da campanha de aceitação; não alteram nenhuma hipótese, limiar, gama nem semente pré-registados. Antes da campanha completa, o executor foi exercitado com as sementes 2000 e 2001, e é preciso dizê-lo porque essas sementes pertencem à aceitação: (1) os testes unitários correm um plano reduzido (nominal, `gnss_bias` e `gnss_dropout`; `robust`, `guarded` e `baseline_guarded`) e repetem-no em cada execução dos testes; (2) uma execução à parte do cenário nominal com as quatro políticas; (3) uma execução local do passo reduzido do CI, que usa o mesmo plano que (1). Nenhum dos resultados parciais levou a alterar um critério, um limiar, uma gama ou uma escolha deste texto.

- **Modelo de caso.** As quatro políticas correm o mesmo `landing/m91-nominal.json` (hash congelado `69ecad65e9ec4329ffc74a3b985dbb7dc60d5cdaa1e4a9a380f296a76f68114b`, verificado antes de qualquer execução). Só `name` e `controller.policy` mudam entre políticas. `baseline` e `robust` recebem assim os dois ganhos opcionais de corte por subida, que ignoram; o código das duas políticas é o do M9. O M9 continua a usar `landing/nominal.json`, e a preservação dos seus resultados é verificada abaixo.
- **Sorteio.** As oito falhas do M9 usam `m9_campaign.sample_fault` sem alteração. As duas falhas novas usam `random.Random(semente · 100 + índice)` com índices 8 (`altimeter_bias_low`) e 9 (`gnss_bias_low`), magnitude `baixo + (alto − baixo) · rng.random()` e janela fixa de 0 a 40 s. Para as sementes 2000 a 2029, os sorteios de `gnss_bias` dão as magnitudes 5,74; 7,69; 10,00 e 10,33 m como as quatro menores, tal como o documento prevê (testado).
- **Recuperação (`recovered`).** Resultado `landed` e nenhum invariante `S1` a `S5` avaliado falhado. Corresponde à coluna "aterrou" do M9 (que já exigia os invariantes). O resultado `landed` isolado (`outcome_landed`) também é guardado.
- **Contenção.** Nenhum invariante com `evaluated: true` e `pass: false`. Um invariante não avaliado (`S2` sem contacto) nunca conta como falha.
- **Deteção.** Uma execução conta para uma bandeira quando o campo `<bandeira>_first` de `controller_flags` não é `null`. São contadas as três bandeiras em todas as políticas; um `0` significa que a bandeira não apareceu ou que a política não a produz (`baseline` não produz nenhuma; `robust` só `altimeter_rejected`; `baseline_guarded` só `ascent_abort`; `guarded` as três). As bandeiras são o que o controlador afirma e não entram em nenhum veredicto de contenção ou recuperação.
- **G1.** Verdadeiro quando, nas quatro células de enviesamento, `sensor_disagreement` aparece em todas as execuções da célula (30 de 30), e quando, em cada uma das sete células de falsos alarmes (nominal, `thrust_loss`, `ignition_delay`, `gimbal_stuck`, `altimeter_dropout`, `gnss_dropout`, `imu_accel_bias`), cada uma das três bandeiras de `guarded` aparece em no máximo 1 execução. As duas partes são apresentadas à parte e o veredicto exige as duas.
- **G2 e G2b.** G2: zero execuções de `guarded` com `gnss_dropout` e `S5` falhado. G2b: zero execuções `no_contact` de `baseline_guarded` com `gnss_dropout`; `S5`, `R1` e a recuperação de `baseline_guarded` ficam registados sem critério.
- **G3.** "Cumpre `R1`" quer dizer que `R1` foi avaliado (houve contacto) e cumprido; sem contacto não conta. O critério é 27 ou mais de 30. O número de execuções recuperadas e o número de sorteios abaixo de 10 m ficam registados à parte, sem critério.
- **G4.** Critério sobre os nove cenários do M9 (nominal e as oito falhas), incluindo `gnss_bias`, que é marcado como não informativo se o `robust` não recuperar nenhuma execução. "Aterra" é "recupera". A verificação mais forte (sem bandeiras de `guarded`, comandos iguais aos do `robust`) é feita ao nível da campanha, em todos os pares do mesmo cenário e semente em que as três bandeiras de `guarded` ficaram `null`, comparando o campo `command` de cada amostra de `trace.json`. As amostras estão gravadas a cada 10 passos (0,1 s), não a cada ciclo de controlo de 0,02 s; o teste do Rust cobre os ciclos intermédios. O resultado da verificação forte é apresentado à parte e não altera o veredicto do critério numérico.
- **G5.** Sem critério de sucesso; o veredicto é `recorded` e a tabela regista o resultado de `guarded` nas duas falhas novas.
- **Regressões.** Todas as células dos 11 cenários em que `guarded` recupera menos execuções do que `robust`, com a indicação de estarem ou não dentro da tolerância de 2.
- **Limites da campanha.** `--max-runs 1100` (o plano pede 1050 mais 2 repetições deterministas), tecto de 768 MiB de artefactos, 1800 s de orçamento de tempo, `--jobs 4` por omissão. O tecto de `--max-runs` do M9 (1000) passa a ser um parâmetro de `validate_limits`; o comportamento do M9 não muda.
- **Composição do total do M9.** Passa a constar de `summary.json` (campo aditivo `composition`), de `summary.md` e do painel de campanha do Mission Control: 9 cenários × 2 políticas × 30 sementes = 540 execuções da matriz, mais 2 falhas × 6 magnitudes × 2 políticas × 10 sementes = 240 do varrimento de fronteira, 540 + 240 = 780.

### Resultados da campanha M9.1

Campanha pré-registada completa (`preregistered: true` em `summary.json`), executada uma única vez depois de os testes passarem, sem alterar a matriz, as gamas, as janelas, os limiares nem as hipóteses depois de ver resultados. Cada uma das 1050 execuções foi reproduzida com `vv-rocket replay` (todas `verified`); os códigos de saída de `land` foram todos 0 ou 2; não houve erros de sorteio (`acted == false`) nem erros do executor, e por isso não foi preciso repetir a campanha.

**Contagem.** 11 cenários (nominal, as 8 falhas do M9 e as 2 novas) × 3 políticas (`baseline`, `robust`, `guarded`) × 30 sementes = 990 execuções; `baseline_guarded` em 2 cenários (nominal e `gnss_dropout`) × 30 sementes = 60 execuções; 990 + 60 = 1050. As 2 repetições deterministas não entram nesta contagem.

**Comando e medições.** `python scripts/m91_campaign.py` (valores por omissão: sementes 2000 a 2029, `--jobs 4`, `--max-runs 1100`, 768 MiB de artefactos, 1800 s). Máquina: Windows-11-10.0.26300-SP0; AMD64 Family 25 Model 97 Stepping 2, AuthenticAMD; 16 logical CPUs; Python 3.14.6. Duração medida pelo relógio, fora da simulação: 33,9 s para 1050 execuções, 1050 reproduções e 2 repetições, com `--jobs 4`. SHA-256 do binário `2016a965df039f971cf6deab2a4299080aeb2e0f122bec12c9ad2c66d9add0aa`; `source_sha256` `27868d619ea82c7d86bb83f759db31761dc757322e81e55d97a401cac31e1476`; modelo de caso `69ecad65e9ec4329ffc74a3b985dbb7dc60d5cdaa1e4a9a380f296a76f68114b` (o hash congelado). Os artefactos ficam em `runs/m91-campaign/` (ignorada pelo Git; `summary.json` e `summary.md` descrevem a campanha completa).

**Reprodutibilidade.** Uma segunda execução completa, com `--jobs 1` e outra pasta (`runs/m91-campaign-repro`), demorou 95,3 s e deu um `summary.json` e um `campaign.json` iguais byte a byte aos da primeira, exceto `duration_s` e `command` (que contém a pasta de saída e o número de tarefas). A ordem do plano e o número de tarefas não afetam, portanto, o resultado. As 2 repetições deterministas dentro de cada campanha (`nominal` com `baseline`, semente 2000, e `gnss_bias_low` com `guarded`, semente 2029) também ficaram idênticas em `case.json`, `trace.json`, `verification.json` e `run.json`.

#### Resultados por célula

Em cada linha, 30 execuções. Deteção, contenção e recuperação são três contagens separadas. `Recuperou`: resultado `landed` com `S1` a `S5` cumpridos. `Contenção`: execuções em que nenhum invariante avaliado falhou. As três colunas de deteção contam execuções em que o controlador declarou a bandeira em pelo menos um ciclo; é o que o controlador afirma e não entra em nenhum veredicto, e `0` quer dizer que a bandeira não apareceu ou que a política não a produz. `Invariantes falhados` e `Requisitos falhados` indicam o número de execuções em que cada identificador falhou.

| Cenário | Política | Recuperou | `hard_landing` | `no_contact` | Contenção | `sensor_disagreement` | `altimeter_rejected` | `ascent_abort` | Invariantes falhados | Requisitos falhados |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `nominal` | `baseline` | 29 | 1 | 0 | 30 | 0 | 0 | 0 | nenhum | R2 1 |
| `nominal` | `robust` | 29 | 1 | 0 | 30 | 0 | 0 | 0 | nenhum | R2 1 |
| `nominal` | `guarded` | 29 | 1 | 0 | 30 | 0 | 0 | 0 | nenhum | R2 1 |
| `nominal` | `baseline_guarded` | 29 | 1 | 0 | 30 | 0 | 0 | 0 | nenhum | R2 1 |
| `thrust_loss` | `baseline` | 29 | 1 | 0 | 30 | 0 | 0 | 0 | nenhum | R2 1 |
| `thrust_loss` | `robust` | 28 | 2 | 0 | 30 | 0 | 0 | 0 | nenhum | R2 2 |
| `thrust_loss` | `guarded` | 28 | 2 | 0 | 30 | 0 | 0 | 0 | nenhum | R2 2 |
| `ignition_delay` | `baseline` | 26 | 4 | 0 | 30 | 0 | 0 | 0 | nenhum | R2 4 |
| `ignition_delay` | `robust` | 25 | 5 | 0 | 30 | 0 | 0 | 0 | nenhum | R2 5 |
| `ignition_delay` | `guarded` | 25 | 5 | 0 | 30 | 0 | 0 | 0 | nenhum | R2 5 |
| `gimbal_stuck` | `baseline` | 25 | 5 | 0 | 30 | 0 | 0 | 0 | nenhum | R2 5 |
| `gimbal_stuck` | `robust` | 27 | 3 | 0 | 30 | 0 | 0 | 0 | nenhum | R2 3 |
| `gimbal_stuck` | `guarded` | 27 | 3 | 0 | 30 | 0 | 0 | 0 | nenhum | R2 3 |
| `altimeter_bias` | `baseline` | 0 | 30 | 0 | 30 | 0 | 0 | 0 | nenhum | R1 30, R2 7, R5 1 |
| `altimeter_bias` | `robust` | 28 | 2 | 0 | 30 | 0 | 30 | 0 | nenhum | R1 1, R2 1 |
| `altimeter_bias` | `guarded` | 28 | 2 | 0 | 30 | 30 | 30 | 0 | nenhum | R1 1, R2 1 |
| `altimeter_dropout` | `baseline` | 6 | 24 | 0 | 30 | 0 | 0 | 0 | nenhum | R1 23, R2 6, R5 2 |
| `altimeter_dropout` | `robust` | 29 | 1 | 0 | 30 | 0 | 0 | 0 | nenhum | R2 1 |
| `altimeter_dropout` | `guarded` | 29 | 1 | 0 | 30 | 0 | 0 | 0 | nenhum | R2 1 |
| `gnss_dropout` | `baseline` | 7 | 2 | 21 | 9 | 0 | 0 | 0 | S5 21 | R2 1, R5 2 |
| `gnss_dropout` | `robust` | 29 | 1 | 0 | 30 | 0 | 0 | 0 | nenhum | R2 1 |
| `gnss_dropout` | `guarded` | 29 | 1 | 0 | 30 | 0 | 0 | 0 | nenhum | R2 1 |
| `gnss_dropout` | `baseline_guarded` | 7 | 21 | 2 | 13 | 0 | 0 | 21 | S2 6, S5 12 | R1 19, R2 18, R3 18, R4 2, R5 17 |
| `gnss_bias` | `baseline` | 5 | 25 | 0 | 30 | 0 | 0 | 0 | nenhum | R5 25 |
| `gnss_bias` | `robust` | 0 | 30 | 0 | 30 | 0 | 30 | 0 | nenhum | R1 30, R2 2, R5 24 |
| `gnss_bias` | `guarded` | 6 | 24 | 0 | 30 | 30 | 30 | 0 | nenhum | R5 24 |
| `imu_accel_bias` | `baseline` | 29 | 1 | 0 | 30 | 0 | 0 | 0 | nenhum | R2 1 |
| `imu_accel_bias` | `robust` | 29 | 1 | 0 | 30 | 0 | 0 | 0 | nenhum | R2 1 |
| `imu_accel_bias` | `guarded` | 29 | 1 | 0 | 30 | 0 | 0 | 0 | nenhum | R2 1 |
| `altimeter_bias_low` | `baseline` | 0 | 30 | 0 | 30 | 0 | 0 | 0 | nenhum | R1 30 |
| `altimeter_bias_low` | `robust` | 28 | 2 | 0 | 30 | 0 | 30 | 0 | nenhum | R1 1, R2 1 |
| `altimeter_bias_low` | `guarded` | 0 | 30 | 0 | 30 | 30 | 30 | 0 | nenhum | R1 30 |
| `gnss_bias_low` | `baseline` | 6 | 24 | 0 | 30 | 0 | 0 | 0 | nenhum | R2 2, R5 23 |
| `gnss_bias_low` | `robust` | 0 | 30 | 0 | 30 | 0 | 30 | 0 | nenhum | R1 30, R2 1, R5 23 |
| `gnss_bias_low` | `guarded` | 0 | 30 | 0 | 30 | 30 | 30 | 0 | nenhum | R1 30, R2 1, R5 23 |

#### Falsos alarmes de `guarded`

Nas sete células sem enviesamento de sensor (nominal, `thrust_loss`, `ignition_delay`, `gimbal_stuck`, `altimeter_dropout`, `gnss_dropout` e `imu_accel_bias`), 210 execuções de `guarded`, nenhuma das três bandeiras apareceu: 0 de 30 em cada bandeira de cada célula, contra o limite pré-registado de 1. `altimeter_rejected` partilha o contador de rejeição do estimador do `robust` com `sensor_disagreement` e dispara com ele; não pode alterar sozinha o veredicto dos falsos alarmes.

#### Hipóteses pré-registadas

| Hipótese | Critério pré-registado | Observado | Veredicto |
| --- | --- | --- | --- |
| G1, deteção | `sensor_disagreement` em 30 de 30 em cada uma de `altimeter_bias`, `gnss_bias`, `altimeter_bias_low` e `gnss_bias_low`; cada bandeira em no máximo 1 de 30 nas sete células sem enviesamento | 30 de 30 nas quatro células; 0 falsos alarmes nas sete | suportada |
| G2, contenção da subida | 0 de 30 execuções de `guarded` com `gnss_dropout` falham `S5` | 0 de 30 (não testa a regra 2, como o documento diz) | suportada |
| G2b, `baseline_guarded` com `gnss_dropout` | 0 execuções `no_contact` | 2 de 30 `no_contact` (sementes 2005 e 2013) | **não suportada** |
| G3, contacto suave com `gnss_bias` | `R1` cumprido em pelo menos 27 de 30 execuções de `guarded` | 30 de 30 (velocidade vertical de 1,86 a 2,42 m/s; limite 3 m/s) | suportada |
| G4, sem regressão | em cada um dos 9 cenários do M9, `guarded` recupera pelo menos `robust` menos 2 | `guarded` igual a `robust` em 8 cenários e 6 contra 0 em `gnss_bias` (linha não informativa, `robust` recuperou 0) | suportada |
| G5, custo da regra conservadora | sem critério de sucesso | `guarded` recupera 0 de 30 em `altimeter_bias_low` e em `gnss_bias_low` | registada |

**G2b.** `baseline_guarded` reduziu os `no_contact` do `baseline` com `gnss_dropout` de 21 para 2, mas não os eliminou, pelo que a hipótese falha. Nas duas execuções restantes a regra 2 atuou aos 23,98 s (`ascent_abort` e `cutoff`), depois de a subida já ser de 137,6 e 144,5 m (`S5` falhado), e o veículo ainda estava em queda no fim dos 40 s da execução, com velocidade vertical de -91,9 e -90,6 m/s e o centro de massa a 50,0 e 65,7 m do solo; contacto não houve dentro da duração. A previsão registada sem critério também se verifica: `S5` falha em 12 de 30 execuções e `R1` em 19 de 30 (contém, não recupera): 7 execuções recuperadas, 21 `hard_landing`, 2 `no_contact`, contenção em 13 de 30, e 6 execuções com falha de `S2` (raio de exclusão). O `baseline` com `gnss_dropout` teve 21 `no_contact` nas sementes 2000 a 2029 (20 nas sementes do M9), todas com `S5` falhado.

Mecanismo do atraso da regra 2 (análise feita depois da campanha, sobre os 21 traços com `ascent_abort`): a regra nunca atuou durante a janela de `gnss_dropout`. O intervalo entre o fim da janela e o `ascent_abort` vai de 0,98 a 20,23 s, e 16 das 21 execuções ficam entre 0,98 e 2,05 s, isto é, cerca de 1 s (a duração exigida pela regra) depois de o GNSS voltar. Durante a falha, a velocidade vertical do estimador continua a usar a última leitura do GNSS, negativa, e por isso não vê a subida. A deteção da subida pelo `baseline_guarded` depende do regresso do GNSS e não é independente da falha que a causa; com uma janela mais longa a subida seria maior. As 5 execuções com intervalos de 10,16 a 20,23 s não foram analisadas.

**G3.** O critério verifica-se, mas a expectativa registada de cerca de 3 ± 1 execuções `landed` (teto previsto: o número de sorteios abaixo de 10 m, 3) não se verificou: `guarded` recuperou 6 de 30, as de magnitudes 5,7; 7,7; 10,0; 11,8; 11,9 e 12,6 m. Três delas têm magnitude acima de 10 m. O raciocínio do teto estava errado: supunha que o desvio horizontal no contacto igualava a magnitude do enviesamento. Nas 6 execuções recuperadas, por ordem de magnitude, `R5` mede 4,18; 7,42; 8,17; 9,75; 9,81 e 9,92 m, entre 0,73 e 0,97 vezes a magnitude. As três acima de 10 m passam `R5` por menos de 0,26 m. A razão da atenuação não foi investigada. As outras 24 execuções tocaram no solo com `R1` cumprido e `R5` falhado (distância ao centro da plataforma), como previsto. O `robust` com `gnss_bias` recuperou 0 de 30, com `R1` falhado em 30 (11,5 a 25,6 m/s); o `baseline` recuperou 5.

**G4.** Linha a linha (`guarded` contra `robust`): nominal 29 e 29, `thrust_loss` 28 e 28, `ignition_delay` 25 e 25, `gimbal_stuck` 27 e 27, `altimeter_bias` 28 e 28, `altimeter_dropout` 29 e 29, `gnss_dropout` 29 e 29, `gnss_bias` 6 e 0, `imu_accel_bias` 29 e 29. Verificação mais forte, feita ao nível da campanha: nos 210 pares (cenário e semente) em que as três bandeiras de `guarded` ficaram `null`, os comandos das amostras gravadas de `guarded` e `robust` são idênticos (210 de 210). Compara as amostras gravadas a cada 0,1 s, não todos os ciclos de 0,02 s, e não altera o veredicto numérico.

**G5.** Registo, sem critério. `altimeter_bias_low`: `guarded` recupera 0 de 30, com `R1` falhado em 30 (11,3 a 30,8 m/s), contenção em 30 de 30 e nenhum `ascent_abort` (o corte a 15 m atuou antes da regra 2); `baseline` 0 de 30 (11,6 a 30,9 m/s); `robust` 28 de 30 (rejeita o altímetro e comporta-se como em `altimeter_bias`). `gnss_bias_low`: `guarded` 0 de 30 com `R1` falhado em 30, os mesmos números do `robust` (0 de 30, `R1` de 11,2 a 23,8 m/s); `baseline` 6 de 30, a espelhar o `gnss_bias` (5 de 30). As previsões do documento para estas duas falhas verificam-se: o custo da regra conservadora aparece em `altimeter_bias_low`, onde `guarded` escolhe a fonte que lê baixo e deixa de recuperar o que o `robust` recupera; em `gnss_bias_low` os números de `guarded` e `robust` coincidem, o que é consistente com a fonte que lê baixo ser a do estimador, que o `robust` já seguia (não foi verificado ciclo a ciclo).

#### Deteção, contenção e recuperação

- `guarded` deteta (`sensor_disagreement`) os quatro enviesamentos em 30 de 30 execuções cada, mas a deteção não implica recuperação: 28 de 30 em `altimeter_bias`, 6 de 30 em `gnss_bias`, 0 de 30 em `altimeter_bias_low` e em `gnss_bias_low`.
- A contenção de `guarded` é 30 de 30 em todas as células: nenhum invariante falhou em nenhuma das 330 execuções. Isto não quer dizer aterragem segura: em `altimeter_bias_low` as 30 execuções tocam no solo a 11 a 31 m/s (`R1` falhado) sem violar `S1` a `S5`, porque os invariantes não incluem a velocidade de contacto, que é um requisito.
- A contenção só falha onde o motor sobe: `baseline` com `gnss_dropout` (9 de 30 contidas, `S5` falhado em 21) e `baseline_guarded` com `gnss_dropout` (13 de 30; `S5` falhado em 12 e `S2` em 6).
- Os resultados do `baseline` e do `robust` nas oito falhas do M9 e no caso nominal, com sementes novas, mantêm o padrão do M9, sem as mesmas contagens (por exemplo `altimeter_bias`: `baseline` 0 e `robust` 28 de 30 aqui contra 0 e 27 no M9; `gnss_bias`: `robust` 0 de 30 nas duas e `baseline` 5 aqui contra 8).

#### Regressões

Uma célula em que `guarded` recupera menos do que `robust`: `altimeter_bias_low`, 0 contra 28 (diferença de -28, fora da tolerância de 2 de G4). Não faz parte dos nove cenários de G4 e é a regressão que o pré-registo previu (G5). Em nenhuma das restantes 10 células `guarded` recupera menos do que `robust`.

#### Preservação dos resultados do M9

Com o binário novo, `python scripts/m9_campaign.py --output-root runs/m9-campaign-v2` volta a dar 780 execuções, todas reproduzidas, e comparado com o `summary.json` guardado da campanha M9 original dá: as 18 células da matriz, os 9 quadros de pares emparelhados, as 24 linhas do varrimento de fronteira, as conclusões da fronteira e os veredictos H1 (suportada), H2 (suportada) e H3 (observada) são iguais, com as mesmas contagens `landed`, `hard_landing` e `no_contact` por política e falha. A única diferença de conteúdo é aditiva: as 20 execuções `no_contact` do `baseline` com `gnss_dropout` passam a listar `S5_no_powered_ascent` em `failed`, o que leva `invariant_failure_runs` dessa célula de 2 para 22. Mudam ainda, como esperado, `binary_sha256`, `source_sha256`, `command`, `duration_s` e o campo novo `composition` (540 + 240 = 780). `runs/m9-campaign` ficou intacta.

#### O que a campanha não estabelece

- Não estabelece que `guarded` seja seguro: só que, neste modelo, com as gamas e as 30 sementes de cada célula, os invariantes `S1` a `S5` não falharam e que as bandeiras apareceram onde estava o enviesamento. Em `gnss_bias`, 24 de 30 execuções tocam fora da plataforma (`R5`); em `altimeter_bias_low` nenhuma aterra.
- Não estabelece o motivo de `guarded` recuperar 6 execuções de `gnss_bias` em vez das cerca de 3 previstas, nem se esse número generaliza.
- Não mede falhas combinadas, enviesamentos fora das gamas pré-registadas, fontes de altitude ou de posição horizontal independentes, nem dinâmica de contacto.
- Não generaliza as contagens para a fiabilidade de um veículo: são 30 sementes por célula com dispersões assumidas, sem valores-p nem intervalos.
- Os limiares de `guarded` foram afinados com as sementes 0 a 40 e as 780 execuções do M9; as sementes 2000 a 2029 são novas, mas a escolha das falhas e das gamas é anterior a elas.
- A verificação forte de G4 usa as amostras gravadas a cada 0,1 s; a igualdade em cada ciclo de 0,02 s só está coberta pelo teste do Rust.
- Mostra que `baseline_guarded` não elimina o afastamento com a falha `gnss_dropout` em 2 de 30 execuções dentro de 40 s de simulação; não diz se ele chegaria ao solo com mais tempo.

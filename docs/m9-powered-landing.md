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

- **Esquema.** O ficheiro de entrada repete os valores pré-registados, para a evidência ser autodescritiva, e a validação rejeita, com uma mensagem que nomeia o campo, qualquer valor diferente do pré-registado em: requisitos e invariantes, dispersões, sensores (desvios-padrão, período de controlo e período do GNSS), veículo (todos os campos de `vehicle`, incluindo os limites e as taxas do acelerador e do TVC), ambiente (gravidade e atmosfera), estado inicial nominal, passo `dt_s` (0,01 s) e velocidade vertical alvo no contacto (-1,5 m/s). As gamas das falhas também são impostas na validação: magnitude dentro da gama, duração da janela de `gimbal_stuck` e dos cortes de sensores dentro de 0,5 a 3 s e 2 a 10 s, no máximo uma falha de cada tipo, no máximo 8 falhas. Ficam livres: o nome, `duration_s`, `record_every`, a política e os ganhos do controlador e do estimador (`controller.gains`, que são limitados e são decisões de projeto do controlador) e as falhas dentro das gamas. A validação do M8 continua a correr sobre o caso (limites de passos e de amostras, geometria). `record_every` é múltiplo do período de controlo (2 passos); os casos usam 10 passos (0,1 s). Os testes que precisam de um veículo ou de um estado inicial diferentes (um tanque quase vazio, um início perto do solo) usam o caminho interno sem os valores fixos, que não é exposto pela interface pública.
- **Semente 0.** Não faz sorteios de dispersão (caso nominal), mas o ruído dos sensores continua ligado, com os fluxos da semente 0. Uma execução com a semente 0 não é, por isso, uma execução sem ruído.
- **Fluxos.** Os sensores sorteiam sempre, haja ou não falha, para que uma falha não desloque o ruído das outras amostras. O GNSS só sorteia nos ciclos em que há amostra.
- **Propelente disperso.** Altera `propellant_mass_kg` do veículo real e escala a inércia do propelente na mesma proporção (inércia por quilograma constante). O controlador mantém os valores nominais.
- **Ordem do passo.** Seguida como no documento. A amostra do passo `k` guarda o estado real em `k` com a observação, o estimador, o comando e a saída do atuador aplicada de `k` a `k + 1`. Contacto: evento `touchdown` com `step = k + 1` (o passo em que foi detetado) e `t_s` igual ao instante interpolado; a amostra `touchdown` guarda o estado interpolado. Uma amostra `final` fecha as execuções sem contacto.
- **Aceleração específica da IMU.** No passo `k` é o impulso aplicado no passo anterior (o atuador ainda não foi atualizado) mais o arrasto no estado `k`, a dividir pela massa em `k`, em B.
- **Taxas dos atuadores.** Aplicadas em cada passo (0,01 s) enquanto o comando fica constante durante o ciclo. A ignição leva o acelerador a 0,40 no passo da ignição; o TVC só se move com o motor aceso.
- **`ignition_delay`.** Só atrasa uma ignição comandada com a janela ativa; o atraso é arredondado ao passo mais próximo e fixado quando a ignição é comandada.
- **Janelas abertas no fim.** O evento `fault_end` só é emitido quando a janela fecha dentro dos passos simulados. Uma janela que ainda está aberta no contacto ou no fim da duração (`end_s` maior ou igual à duração, ou uma simulação que termina antes de `end_s`) não tem `fault_end`: o traço termina com o evento `end`, e `active_faults` das amostras mostra o que estava ativo.
- **`acted`.** Cada elemento de `faults` em `verification.json` repete a falha configurada e acrescenta `acted`, que diz se a falha mudou alguma coisa nesta execução. É calculado pelo verificador a partir do registo por passo (falhas ativas, impulso aplicado, calendário de controlo e ignição comandada e efetiva) e recalculado na repetição: `thrust_loss` e `gimbal_stuck` precisam de pelo menos um passo com impulso dentro da janela; `ignition_delay` de uma ignição efetiva depois da comandada (ou ainda pendente no fim); um desvio ou corte de sensor de pelo menos um ciclo de controlo dentro da janela (para o GNSS, um ciclo de GNSS), sem contar o desvio que um corte do mesmo sensor esconde. Uma janela com `acted: false` (por exemplo, uma perda de impulso antes da ignição, ou uma janela que abre depois do contacto) é um caso que não diz nada sobre essa falha.
- **`flameout`.** Avaliado ao aplicar o atuador: se o propelente real não chega para o passo completo com o impulso desse passo, o motor apaga nesse passo, com `Isp` e `T_max` reais. O evento regista esse passo.
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

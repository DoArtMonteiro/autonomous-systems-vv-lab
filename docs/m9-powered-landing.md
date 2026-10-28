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

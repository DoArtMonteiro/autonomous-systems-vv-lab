# M17: subida de um lançador de dois andares com entidades múltiplas

O M17 acrescenta uma missão de lançamento com várias fases e várias entidades: um lançador de dois andares sobe da plataforma até uma órbita baixa, separa-se e, a partir da separação, o primeiro andar (booster) e o andar superior são duas entidades integradas de forma independente, cada uma com o seu histórico de estados, os seus eventos e os seus requisitos. É uma simulação determinística verdadeira, não uma coreografia: as trajetórias saem da integração das equações do movimento, o software de voo só vê observações com ruído e todos os veredictos são calculados sobre o estado real.

**Estado: exploratório.** Os dois veículos são configurações exploratórias, não veículos reais. Os valores têm apenas a ordem de grandeza de descrições públicas de lançadores pequenos e médios de querosene e oxigénio líquido. Nada foi validado contra dados de voo.

## O que foi entregue

- `crates/vv-ascent`: pacote Rust autónomo (workspace próprio, como `crates/vv-rocket`), sem dependências novas para além de `serde`, `serde_json` e `sha2` fixados como no workspace do desktop. O pacote raiz, o seu `Cargo.lock` e os hashes canónicos do M1 não mudam.
- Registo `vv-run.v2` em `desktop/platform`, aditivo sobre `vv-run.v1`.
- Domínio `launch-ascent` em `desktop/domain-ascent`, registado no workspace do desktop e preparado por `desktop/build.ps1` como os outros domínios.
- Cena `ascent` do Studio (`desktop/studio/ui/js/scenes/ascent.js`), registada em `registry.js`.

## Modelo

### Referencial e estado

- Plano inercial da trajetória com origem no centro da Terra: `x` na direção de descida da trajetória no local de lançamento, `z` na vertical local do local de lançamento. A plataforma está em `(0, R)`.
- Terra esférica e sem rotação, raio médio `R = 6 371 000 m`, `μ = 3,986004418·10¹⁴ m³/s²`. Gravidade em inverso do quadrado, `g = −μ r / |r|³`.
- Estado de cada corpo: posição `r`, velocidade `v` (ambas no plano) e massa `m`. Modelo de ponto material com três graus de liberdade (dois de translação e a massa); não há atitude nem dinâmica de rotação.
- Altitude `|r| − R`; distância ao longo da superfície `R·atan2(x, z)`.

### Forças

- Atmosfera exponencial isotérmica: `ρ = 1,225·exp(−h / 8500 m)`; a razão de pressões `p/p0` é igual à razão de densidades.
  - **Limite do modelo.** Uma única altura de escala de 8,5 km só descreve a baixa atmosfera. Comparada com os valores arredondados de uma tabela publicada de densidade da alta atmosfera (os valores citados são os de uma tabela de um capítulo de livro sobre a alta atmosfera; não se identificou qual a atmosfera padrão de que provêm, e acima de 150 km dependem da atividade solar), a densidade do modelo é cerca de 9 vezes maior a 90 km (3,09e-5 contra 3,4e-6 kg/m³) e cerca de 13 vezes maior a 150 km (2,66e-8 contra 2,08e-9 kg/m³), e cerca de 33 000 vezes menor a 300 km (5,8e-16 contra 1,9e-11 kg/m³). Acima de cerca de 300 km a densidade do modelo é um artefacto da forma exponencial, não um valor físico: o arrasto resultante é praticamente nulo. O arrasto da subida e da queda do booster entre 90 e 150 km é, por isso, sobrestimado, e o voo livre do andar superior depois do SECO quase não tem arrasto, ao contrário de uma órbita real.
- Arrasto `−½ ρ |v| Cd A v`, com `Cd` constante e área de referência por andar. Como a Terra não roda, a velocidade relativa ao ar é a velocidade inercial.
- Impulso com caudal mássico fixo para cada acelerador: `ṁ = acelerador · T_vac / (Isp_vac g0)`, impulso `ṁ g0 Isp(p)` com `Isp(p) = Isp_vac − (Isp_vac − Isp_sl) p/p0`. O impulso ao nível do mar resulta da mesma descarga com o Isp do nível do mar.
- Esgotamento: num passo em que o propelente restante não chega para `ṁ dt`, o caudal desse passo é reduzido para queimar exatamente o que resta.
- Na plataforma o veículo fica preso enquanto o impulso real não exceder o peso; a descolagem é o primeiro passo em que o excede.

### Integração e determinismo

- Relógio lógico: um tick são 20 ms (`dt = 0,02 s`, 50 ticks por segundo); `t = tick · dt` desde o início da espera pré-lançamento. Limite rígido de 4000 s por execução.
- Um passo RK4 clássico por tick e por entidade. A direção do impulso e o caudal ficam constantes durante o passo (retenção de ordem zero do comando).
- Aritmética: só `+ − × ÷` e `sqrt` (exatos pela norma IEEE 754) sobre `f64`; `exp`, `sin`, `cos` e `atan2` são polinómios do próprio pacote (a `exp` é a de `crates/vv-rocket`), porque as da biblioteca padrão delegam no sistema e podem diferir no último bit entre plataformas. Os testes comparam-nas com a biblioteca padrão: erro relativo de `exp` abaixo de 1e-14, erro absoluto de `sin_cos` abaixo de 1e-15 e de `atan2` abaixo de 2e-15.
- Gerador pseudoaleatório: SplitMix64, o algoritmo de `crates/vv-rocket/src/prng.rs`, com um fluxo por fonte (semente `semente ⊕ fonte·0x9E3779B97F4A7C15`): empuxo, Isp, propelente carregado e massa seca de cada andar, e ruído de posição e de velocidade da navegação. Ruído de Irwin-Hall com desvio-padrão `σ`, limitado a `±2√3 σ`. Com as dispersões desligadas não se tira nenhuma amostra desses fluxos.
- O mesmo caso e a mesma semente dão os mesmos bytes em `trace.json` e `verification.json` (teste). Os ficheiros de referência dourados passam iguais com os perfis `dev` e `release`.

### Entidades e ordem dos eventos

- `stack`: os dois andares e a carga útil, da plataforma até à separação.
- `booster`: o primeiro andar depois da separação, com a massa seca e o propelente residual reais. Balístico com arrasto até ao impacto. **Não há manobra de regresso nem queima de aterragem**: o ponto de impacto segue apenas o estado de separação.
- `upper`: o andar superior e a carga útil, até ao corte do motor (SECO) e a um voo livre de 600 s.
- As duas entidades filhas partem exatamente do estado do `stack` no tick da separação (teste: posição, velocidade e soma das massas iguais) e depois são integradas de forma independente.
- Em cada tick as entidades são processadas pela ordem de índice. Para a entidade guiada (o `stack`, depois o `upper`) gera-se a observação e o software de voo produz o comando de `[k, k+1]`; depois cada entidade regista a sua amostra real em `k` e dá um passo. Os eventos reais detetados num passo ficam com o tick `k+1`.
- Ordem total dos eventos: tick, depois entidade (`stack`, `booster`, `upper` e, no fim, a `mission` para os eventos que não pertencem a nenhuma entidade), depois fonte (real, controlador, verificador), depois a ordem de emissão. Um teste verifica a ordem estrita e a sequência das fases.

### Fases

Espera pré-lançamento com verificações, ignição, descolagem, subida vertical, início e fim da manobra de inclinação (pitch kick), início da viragem gravitacional, redução do acelerador para a pressão dinâmica, max-Q (evento do verificador, no máximo real da pressão dinâmica do `stack`), MECO, separação, ignição do andar superior, SECO, avaliação da inserção em órbita (evento do verificador, no estado real do SECO), apogeu e impacto do booster na superfície. Também existem os eventos de esgotamento de propelente, de cancelamento (scrub) e de violação.

## Separação entre estado real, observações e decisões

- O software de voo (`guidance.rs`) recebe apenas `Observation { r, v }`: a solução de navegação com ruído (por omissão `σ = 10 m` por eixo na posição e `0,1 m/s` na velocidade) e a configuração da missão com o **veículo nominal**. Nunca recebe o estado real, o veículo disperso nem o verificador; esta fronteira é de tipos, não de disciplina.
- O propelente e a massa que o software de voo usa são estimativas suas, a partir do caudal nominal e do acelerador que comandou. Com dispersões ligadas, o propelente real no MECO difere da estimativa, e isso é avaliado pelo requisito de margem.
- Leis do software de voo, cada uma explicável numa linha:
  - verificações pré-lançamento: veículo parado na plataforma segundo a navegação, relação impulso-peso nominal na descolagem pelo menos 1,1, queima nominal do primeiro andar mais longa do que o início da viragem gravitacional; senão, cancela;
  - corta o motor se 3 s depois da ignição a velocidade de navegação ainda estiver abaixo de 2 m/s (não descolou);
  - subida vertical até `kick_time_s` depois da ignição; inclinação linear até `kick_angle_deg` em `kick_duration_s`, mantida até `gravity_turn_start_s`; depois impulso ao longo da velocidade observada;
  - acelerador do primeiro andar: corte proporcional enquanto a pressão dinâmica estimada exceder `q_target_pa` e limite para a aceleração estimada não passar `axial_g_target`;
  - MECO quando o propelente estimado do primeiro andar chegar à sua reserva; separação `separation_delay_s` depois; ignição do andar superior `ignition_delay_s` depois da separação;
  - andar superior, guiamento radial explícito (a lei de aceleração linear do guiamento clássico de subida do módulo lunar): tempo até ao fim `T` pela equação do foguete para a velocidade que falta até à energia da órbita alvo (com mínimo `min_time_to_go_s`); a aceleração radial líquida `A + B t` que leva o raio a `r_t` com velocidade radial nula em `T` dá `B = −12 (r_t − r − v_r T/2) / T³` e `A = −(v_r + B T²/2) / T`; o impulso fornece radialmente `A + g(r) − v_t²/r` e o resto é horizontal;
  - SECO quando a energia orbital observada atingir a da órbita circular alvo (acelerador no mínimo quando faltam menos de `terminal_dv_m_s`), ou quando o propelente estimado chegar à reserva.

## Arquitetura do veículo

Cada caso (`crates/vv-ascent/cases/*.json`, esquema `vv-ascent-case.v1`) tem dois blocos separados e rotulados:

- `vehicle`, com `"role": "simulated"`: por andar, massa seca, propelente, impulso no vácuo, Isp no vácuo e ao nível do mar, área de referência, `Cd`, limites do acelerador e fração de reserva; e a carga útil. Tudo isto é lido pela física.
- `visual`, com `"role": "visual-only, never read by the simulation"`: comprimento, diâmetro e cor por andar e cor da coifa. A estrutura interna `Prepared` que a simulação usa não contém este bloco, e um teste verifica que alterar comprimentos, diâmetros e cores não altera nenhum byte de `trace.json` nem de `verification.json` (e que alterar uma massa seca altera). O bloco visual só chega à cena do registo.
- Os leitores recusam campos desconhecidos; um campo visual dentro do bloco simulado é recusado. Um caso tem de declarar `"status": "exploratory, not a real vehicle"`.

| Configuração | Massa na descolagem | Andar 1 | Andar 2 | Carga útil | Alvo |
|---|---|---|---|---|---|
| `small-leo` | cerca de 35 t | 2,8 t secos, 27 t de propelente, 560 kN no vácuo, Isp 285/315 s | 0,65 t secos, 4,8 t de propelente, 55 kN, Isp 340 s | 250 kg | 300 km |
| `medium-leo` | cerca de 304 t | 19 t secos, 230 t de propelente, 4,7 MN no vácuo, Isp 282/311 s, reserva de 6 % para recuperação | 4 t secos, 48 t de propelente, 600 kN, Isp 345 s | 3 t | 400 km |

Proveniência: ordens de grandeza públicas de lançadores de querosene e oxigénio líquido (Isp de 280 a 320 s, relação impulso-peso na descolagem de 1,3 a 1,5, frações estruturais de 8 a 13 %). Nenhum número é um dado de um lançador concreto. As reservas, os limites e as zonas de recuperação são valores assumidos para a verificação.

## Requisitos e invariantes

Todos são calculados sobre o estado real. Cada falha indica o identificador, o tick, o estado real nesse tick (altitude, distância, velocidade, velocidade radial, massa, propelente, acelerador, pressão dinâmica, aceleração sentida), a causa e as condições esperada e observada. O resultado da missão fica separado da segurança (invariantes). O resultado é decidido por esta ordem, e cada código tem um só significado:

| Código | Significado |
|---|---|
| `scrubbed` | o lançador nunca descolou |
| `no_separation` | descolou mas o `stack` nunca se separou: o andar superior nunca voou |
| `suborbital` | o andar superior atingiu a superfície em algum momento, ou a órbita real no SECO tem periapse abaixo da superfície (menos de 0 km) |
| `seco_not_reached` | separou-se mas o SECO não ocorreu antes do fim do tempo simulado: nenhuma órbita foi avaliada |
| `unbound` | energia específica real no SECO maior ou igual a zero: trajetória parabólica ou hiperbólica, não órbita |
| `low_periapsis_orbit` | órbita ligada que não toca a superfície mas com periapse abaixo do mínimo declarado (`min_periapsis_km`) |
| `off_target_orbit` | órbita ligada com a periapse no mínimo mas apoapse fora da tolerância do alvo |
| `orbit` | periapse e apoapse dentro dos requisitos e sem contacto com a superfície |

`orbit` descreve a órbita, não o conjunto dos requisitos: com `requirements_pass` falso (por exemplo a zona de recuperação do booster ou uma margem) o resultado continua `orbit`, e o registo `vv-run.v2` mostra-o com o estado `partial`, a etiqueta "Orbit, other requirements not met" e a métrica `requirements_pass`.

`invariants_pass` quer dizer que nenhum invariante falhou, não que todos foram avaliados. `invariants_evaluated` e `invariants_not_evaluated` (identificadores) dizem quais não puderam ser julgados porque a entidade nunca voou: um lançamento cancelado não avalia nenhum. No registo a segurança continua no vocabulário fechado da plataforma (`safe` ou `unsafe`), mas a explicação diz "safe (not evaluated: ...)" e, se nenhum invariante foi julgado, a classe é `not_evaluated`.

Eventos de veredictos: um evento nunca precede o início da entidade a que está ligado nem segue a sua última amostra. Um veredicto do booster ou do andar superior cujo instante é anterior à existência da entidade (a margem do booster é medida no MECO, antes da separação) fica ligado ao `stack`; o que não cabe em nenhuma entidade, e os veredictos da missão, ficam ligados à `mission`, que na ordem total vem depois das entidades. Os eventos do controlador registam a observação (`observed_altitude_m`, `observed_downrange_m`, `observed_speed_m_s`) e nunca o estado real.

| Identificador | Categoria | Condição |
|---|---|---|
| `stack.S1_max_dynamic_pressure` | invariante | pressão dinâmica real do `stack` até ao limite em todos os ticks em voo |
| `stack.S2_axial_acceleration` | invariante | aceleração não gravitacional real do `stack` até ao limite |
| `upper.S2_axial_acceleration` | invariante | o mesmo para o andar superior |
| `stack.R1_separation_window` | requisito | altitude e velocidade reais na separação dentro da janela |
| `booster.R2_propellant_margin` | requisito | propelente real no MECO pelo menos o mínimo de recuperação, sem esgotamento antes do MECO |
| `booster.R3_recovery_zone` | requisito | ponto de impacto interpolado dentro da zona declarada |
| `upper.R4_periapsis` | requisito | periapse da órbita osculadora real no SECO pelo menos o mínimo |
| `upper.R5_apoapsis` | requisito | apoapse dentro da tolerância do alvo |
| `upper.R6_propellant_margin` | requisito | SECO pelo critério de energia, sem esgotamento, resíduo real pelo menos o mínimo (1 % da carga do andar superior nos dois casos, a reserva que o próprio software de voo mantém; ver abaixo) |
| `mission.R7_phase_sequence` | requisito | ignição, descolagem, inclinação, viragem, MECO, separação, ignição superior e SECO, por esta ordem |
| `mission.R8_orbit_insertion` | requisito | R4 e R5 cumpridos e o andar superior nunca atinge a superfície |

Os elementos orbitais calculam-se a partir da energia específica e do momento angular (`r_p = h²/(μ(1+e))`), só com aritmética e raízes quadradas. Os requisitos de entidades que nunca existiram (sem separação) ficam `not_evaluated` e pertencem à missão no registo.

## Casos de referência e erros medidos

Testes em `crates/vv-ascent/tests/reference.rs`, com o RK4 de produção e o passo de produção. Medidos neste código com `cargo test --release --test reference -- --nocapture` (Windows 11, x86-64). As tolerâncias dos testes são cerca de dez vezes o erro medido.

| Referência | Grandeza | Erro medido | Tolerância |
|---|---|---|---|
| (a) subida vertical sem arrasto, impulso e caudal constantes, gravidade uniforme, 150 s; `v = ve ln(m0/m) − g t`, `h = ve (t − (m/ṁ) ln(m0/m)) − g t²/2` | velocidade | 4,1e-12 m/s | 1e-10 m/s |
| | altitude (até cerca de 84 km) | 2,1e-8 m | 5e-7 m |
| (b) voo livre de Kepler no vácuo, uma órbita, `a = 7544,3 km` | energia específica (relativo) | 9,2e-14 | 1e-12 |
| | momento angular (relativo) | 4,7e-14 | 1e-12 |
| | período contra `2π√(a³/μ)` = 6521,365 s | 5,8e-10 s | 1e-6 s |
| (c) equação ideal do foguete, queima completa no vácuo sem gravidade | `small-leo` andar 1 (4415,758 m/s) | 5,1e-13 (relativo) | 1e-11 |
| | `small-leo` andar 2 (6154,468 m/s) | 3,6e-13 | 1e-11 |
| | `medium-leo` andar 1 (4309,350 m/s) | 3,0e-13 | 1e-11 |
| | `medium-leo` andar 2 (6974,401 m/s) | 5,8e-13 | 1e-11 |

Na missão completa, a variação relativa da energia orbital do andar superior nos 600 s de voo livre depois do SECO foi 2,4e-12 (`small-leo`, semente 5000) e 1,5e-14 (`medium-leo`, semente 5000); o teste exige menos de 1e-6. Esta deriva só mostra que o integrador conserva a energia e que o modelo quase não tem arrasto a estas altitudes (ver o limite da atmosfera acima): **não é evidência do tempo de vida orbital**, que depende do arrasto real a 300 e 400 km (muito maior do que o do modelo), da atividade solar e da massa balística, nada disto modelado. O requisito de periapse mínima é um valor declarado, não uma avaliação de decaimento.

Referências independentes (`crates/vv-ascent/tests/independent.rs`). O lado da referência só usa a biblioteca padrão e constantes literais e nunca chama a função do simulador que verifica; as diferenças medidas saem com `cargo test --test independent -- --nocapture`.

| Referência | Grandeza | Diferença medida | Tolerância |
|---|---|---|---|
| (d) `elements` contra vis-viva e vetor de excentricidade, oito estados: elípticos excêntricos (subida e descida, um retrógrado), periapse abaixo da superfície, ligado por pouco (0,9999 da velocidade de escape), não ligado por pouco (1,0001) e hiperbólicos | excentricidade | 7,2e-16 | 1e-9 |
| | altitudes de periapse e de apoapse (a apoapse do quase parabólico é 3,3e10 m) | 6,4e-3 m, só no quase parabólico (relativo 2e-13) | 1e-3 m mais 1e-11 do valor |
| | energia específica (relativo) | 2,6e-13 | 1e-9 |
| (e) queda em ar de densidade constante (corpo abaixo da superfície com gravidade uniforme, onde a densidade do simulador é exatamente a do nível do mar), 120 s; `v = v_t tanh(g t / v_t)`, queda `(v_t²/g) ln cosh(g t / v_t)`, `v_t = 126,534 m/s` | velocidade | 1,1e-11 m/s | 1e-7 m/s |
| | posição | 2,4e-8 m | 1e-5 m |
| (f) ponto de impacto interpolado contra o arco kepleriano analítico no vácuo (anomalia verdadeira, equação de Kepler, vis-viva), dois arcos de 379 s e 437 s | instante do impacto | 3,3e-8 s (pior) | 1e-6 s |
| | distância ao longo da superfície (1855 km e 1260 km) | 8,5e-5 m (pior) | 1e-3 m |
| | velocidade no impacto | 3,5e-8 m/s (pior) | 1e-6 m/s |

## Resultados de exemplo

Execuções reais do domínio `launch-ascent` com sementes de desenvolvimento; todas reproduzidas pelo `replay` com o estado `verified`.

| Execução | Resultado | Observações |
|---|---|---|
| `small-leo`, semente 5000 | `orbit`, seguro | periapse 298,10 km, apoapse 301,90 km; max-Q 34,5 kPa a 12,2 km; separação a 95,4 km e 2765 m/s; booster cai a 1023,5 km (zona 850 a 1150 km); resíduo superior 145,6 kg |
| `medium-leo`, semente 5000 | `orbit`, seguro | periapse 399,10 km, apoapse 400,06 km; max-Q 32,7 kPa; separação a 93,1 km e 2448 m/s; booster cai a 811,8 km (zona 650 a 900 km) a 1037 m/s; resíduo superior 1330 kg |
| `small-leo`, carga útil 600 kg | `suborbital`, seguro | `upper.R6_propellant_margin` falha: o SECO veio da reserva estimada antes da energia alvo; periapse −859 km; `mission.R8_orbit_insertion` falha |
| `small-leo`, semente 42 | `orbit` com `requirements_pass` falso (no registo, estado `partial`), seguro, um requisito falha | `booster.R3_recovery_zone` falha: impacto balístico 29,5 km antes da zona, porque as dispersões dessa semente deram uma separação a 72,1 km; sem manobra de regresso modelada |
| `small-leo`, inclinação de 6° | `no_separation`, inseguro | `stack.S1_max_dynamic_pressure` falha no tick 4396 (45,0 kPa a 14,6 km com o acelerador já no mínimo de 0,6); o `stack` fica em ar denso e cai antes do MECO |
| `small-leo`, carga útil 20 t | `scrubbed` | as verificações pré-lançamento recusam uma relação impulso-peso nominal abaixo de 1,1 |

Nas sementes 5000 a 5009, `small-leo` cumpre todos os requisitos; `medium-leo` cumpre-os todos exceto na semente 5005, em que o resíduo real do andar superior no SECO é 0,69 % da carga (mínimo 1 %) e `upper.R6_propellant_margin` falha. Com dispersões ligadas, as sementes 42 (zona de recuperação) e 7 (margem do booster, −10,6 kg) falham requisitos do booster em `small-leo`: são resultados do modelo, não erros.

**Margem do andar superior (R6).** O mínimo de resíduo era 0 nos dois casos, o que tornava a margem impossível de falhar. Passou a 1 % da carga do andar superior (48 kg em `small-leo`, 480 kg em `medium-leo`), igual à reserva que o software de voo mantém e abaixo da mediana medida. Medido em 200 sementes (5000 a 5199, dispersões ligadas; `cargo test --release --test ascent seed_scan -- --ignored --nocapture` em `crates/vv-ascent`): o resíduo real no SECO foi entre 0,2 % e 3,9 % da carga em `small-leo` (mediana 3,0 %) e entre 0 % e 3,9 % em `medium-leo` (mediana 2,6 %, esgotamento em algumas sementes). Nas mesmas 200 sementes o andar superior não chegou a órbita em 8 casos de `small-leo` (4 `suborbital`, 4 `low_periapsis_orbit`) e em 20 de `medium-leo` (14 `suborbital`, 6 `low_periapsis_orbit`): com dispersões de 1 % no empuxo e estimativas de massa e propelente do veículo nominal, o guiamento simples falha com frequência não desprezável. É um resultado do modelo exploratório, não foi investigado a fundo.

## Registo `vv-run.v2`

- `RunRecord` ganha dois campos opcionais, omitidos quando ausentes: `entities` (por entidade: `id`, `label`, `kind`, `parent`, `timebase`, `t_start`, `t_end`, `end_reason`, os identificadores dos seus canais, os índices dos seus eventos e os identificadores dos seus requisitos) e `mission` (requisitos da missão, ordem dos eventos declarada, explicação).
- Os dados continuam nas listas de topo (`channels`, `events`, `requirements`, `timebases`), por isso todas as vistas genéricas do Studio funcionam com um registo v2. Cada entidade tem a sua base de tempo (`stack`, `booster`, `upper`), com amostras de 1 s mais as amostras dos ticks com eventos e a última. Uma base de tempo `mission`, sem canais, marca cada segundo do voo inteiro e é a que a cena declara, para que o cursor de tempo do Studio avance para além da separação.
- Um registo v1 não pode ter `entities` nem `mission`; um v2 tem de ter os dois. A plataforma e o SDK verificam pais declarados antes dos filhos, bases de tempo e canais existentes, índices de eventos crescentes e dentro dos limites, e que cada requisito pertence exatamente a uma entidade ou à missão.
- Compatibilidade: um teste lê o registo v1 de referência do repositório (`desktop/studio/tests/fixtures/rocket-record-trimmed.json`), confirma que não tem campos v2 e que os bytes canónicos e o formato em disco ficam iguais depois de ler e escrever. A versão do contrato continua `vv-domain/1.0`, para que os registos v1 dos domínios existentes fiquem iguais byte a byte.

## Domínio e Studio

- `launch-ascent` tem dois cenários (um por veículo), um único software de voo e só parâmetros com significado no modelo, com intervalos validados pelo domínio e outra vez pelo simulador: altitude alvo, tempo e ângulo da inclinação, início da viragem gravitacional e carga útil (identificadores por veículo, porque o valor por omissão de cada um é o do seu modelo; um teste confirma), e `dispersions` (0 ou 1). Não tem falhas injetáveis neste corte.
- Sementes protegidas iguais às dos outros domínios: 3000 a 3099, 6000 a 6099 e 44000 a 44999, recusadas pela plataforma e outra vez pelo domínio.
- Quatro demonstrações (órbita do pequeno, órbita do médio, carga útil excessiva, inclinação excessiva), cada uma verificada por um teste.
- Cena `ascent`: altitude sobre a distância ou vista plana com a curvatura da Terra, órbita alvo e zona de recuperação, seletor de entidade, telemetria da entidade no cursor de tempo e requisitos por entidade e da missão. As posições entre amostras são interpoladas apenas para visualização, como diz a legenda. A cena foi verificada com registos reais num harness em Edge (Playwright); não foi verificada na janela WebView2 instalada nem com os testes de percurso do Studio.

## Limites de validade

Não está modelado: rotação da Terra (e o ganho de velocidade para leste que daria), trajetória em três dimensões e inclinação orbital, ventos e turbulência, atmosfera padrão por camadas e número de Mach (o `Cd` é constante), dinâmica de atitude e controlo de atitude (a direção do impulso é instantânea), cargas estruturais e momento fletor, transitórios de ignição e de corte, separação com impulso ou contacto entre andares, manobra de regresso, reentrada controlada ou aterragem do booster, aquecimento, perturbações orbitais (achatamento, arrasto orbital de longo prazo) e falhas injetáveis. A pressão dinâmica máxima do booster na queda balística (433 kPa no pequeno, 854 kPa no médio, nas execuções de referência) é reportada como métrica, sem requisito, precisamente porque não há queima de reentrada.

O guiamento é simples e explicável, não ótimo: não procura a trajetória de menor consumo e o seu desempenho depende da inclinação inicial escolhida.

### Regresso propulsionado do booster: estudo de orçamento, não implementado

O booster continua balístico. Foi feito um estudo independente (não é uma validação nem um limite, só uma ordem de grandeza) para saber o que uma recuperação exigiria, com dois guiões Python que não usam o código do simulador:

- `scripts/m18_booster_budget.py`: orçamento de Tsiolkovsky com o propelente que o booster leva na separação e um integrador de ponto material à parte (arrasto e gravidade do inverso do quadrado, em Python) a partir do estado de separação lido do `trace.json` de uma execução. O integrador reproduz o impacto balístico do simulador (`small-leo`, semente 5000: 1023,55 km a 378,1 m/s nos dois, diferença abaixo de 0,1 m e de 0,01 m/s; `medium-leo`: 811,83 km a 1037,3 m/s nos dois), o que é uma verificação independente do booster balístico e não depende da escolha de nenhum ângulo. Resultados (semente 5000, dispersões ligadas):
  - `small-leo`: separação a 95,4 km, 87,9 km à frente do local de lançamento, 2765 m/s (horizontal 2186 m/s, vertical 1693 m/s); o booster leva 737 kg de propelente (2,7 % da carga), que dão no máximo 722 m/s. Travar o impacto balístico (378 m/s) custa cerca de 365 kg; só anular a velocidade horizontal (o regresso ao local de lançamento exige mais) custa cerca de 2186 m/s, 2882 kg; os dois juntos cerca de 13,4 % da carga do primeiro andar, contra 3 % de reserva.
  - `medium-leo`: separação a 93,1 km, 72,6 km à frente, 2448 m/s (horizontal 1801 m/s, vertical 1657 m/s); 13 177 kg de propelente (5,7 %) dão no máximo 1607 m/s. A travagem do impacto balístico (1037 m/s) custa cerca de 7,7 t; anular a velocidade horizontal, cerca de 1801 m/s e 15,3 t; os dois juntos cerca de 12,7 % da carga, contra 6 % de reserva.
  - **Com as reservas atuais, o regresso ao local de lançamento está fora de alcance nos dois casos** (em `small-leo` só a velocidade horizontal pede cerca de quatro vezes o propelente que o booster leva; em `medium-leo`, cerca de 1,2 vezes, e a travagem final ainda por cima). Um caso novo podia declarar uma reserva maior, mas isso retira velocidade à separação e à inserção em órbita, o que não foi calculado. Uma travagem final sem manobra de regresso cabe no propelente que o booster leva. Os valores são estimativas: a velocidade horizontal a anular é só uma parte do regresso, e uma travagem real começa acima do solo, perde velocidade para o arrasto antes e paga perdas de gravidade.
- `scripts/m18_booster_landing_1d.py`: travagem vertical a partir de 300 m/s, gravidade uniforme, controlo a 50 Hz, massa de aterragem de 3400 kg em `small-leo`, com um controlador simples (acende quando a altitude estimada atinge a altura de paragem, comanda `a = v²/(2h) + g` dentro dos limites do acelerador e corta quando a velocidade estimada deixa de ser descendente); o ruído sai de `random.Random` com sementes explícitas. É o resultado desse controlador, não um limite para qualquer controlador. O primeiro andar não paira: o empuxo ao nível do mar vai de 9,1 a 15,2 vezes o peso e um passo de 20 ms muda a velocidade entre 1,6 e 2,8 m/s. Com altitude e velocidade exatas a velocidade de toque é 4,0 m/s; com ruído de altitude de 0,1 m, mediana 3,4 m/s (pior em 200 amostras 5,6 m/s); com 2 m, mediana 3,2 m/s (pior 9,4); com os 10 m da navegação do voo (e 0,1 m/s), mediana 7,0 m/s (percentil 90 9,4 e pior 10,9), e em 197 das 200 amostras o motor corta acima do chão. O ruído de altitude acrescenta cerca de 3 m/s à mediana; o piso de cerca de 4 m/s vem do acelerador mínimo, do passo de 20 ms e da regra de corte deste controlador, não da navegação. Não ficou demonstrado que um requisito de poucos m/s precise de um altímetro próprio.

Estado: **não implementado**. O estudo acima é a única parte feita; o booster continua balístico e todos os casos existentes ficam iguais. Para implementar faltaria um motor reacendível no `booster` (hoje sem motor), o guiamento do booster como segunda instância de software de voo com a sua navegação e fluxos pseudoaleatórios próprios, um bloco de recuperação opcional no caso (zona de aterragem declarada, sensores, fração de empuxo), requisitos novos (velocidade de toque, erro de posição, margem de propelente), a entidade no registo `vv-run.v2` e a validação contra uma referência independente. Existe um trabalho em curso, nunca compilado e sobre outra base, no ramo local `feat/m18-booster-recovery` (commit bfe78a4); não foi integrado.

## Reprodução

```sh
cd crates/vv-ascent
cargo test
cargo run --release -- summary cases/small-leo.json --seed 5000
cargo run --release -- run cases/small-leo.json --seed 5000 --output out
cargo run --release -- replay out
```

No desktop: `cargo test -p vv-platform -p vv-domain-ascent` em `desktop/`. Os ficheiros dourados (`crates/vv-ascent/tests/golden`) regeneram-se com `VV_ASCENT_BLESS=1 cargo test --test ascent golden`, apenas depois de uma alteração deliberada.

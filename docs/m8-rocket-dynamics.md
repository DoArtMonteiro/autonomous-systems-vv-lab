# M8: dinâmica de corpo rígido de um andar de foguete

Primeira fatia vertical de dinâmica real: um corpo rígido com 6 graus de liberdade, massa variável, propulsão idealizada e arrasto simplificado, verificado contra soluções de referência e integrado no Mission Control como o modelo `rocket-rigid-body`. Não é a missão de recuperação (M9) nem um modelo validado contra dados de voo.

Este documento fixa convenções, equações, integrador e tolerâncias **antes** dos testes. Os testes leem estes valores; não são ajustados depois.

## Organização

- `crates/vv-rocket/`: biblioteca e CLI `vv-rocket`, com `[workspace]` e `Cargo.lock` próprios. Não depende do simulador terrestre e não altera `Cargo.toml`, `Cargo.lock` nem `src/` da raiz, pelo que o `source_sha256` do `vv-lab` e todas as saídas M1 a M7 ficam iguais.
- Dependências: apenas `serde`, `serde_json` e `sha2`, nas versões já fixadas na raiz. Vetores, matrizes e quaterniões são implementados no crate.
- `scripts/rocket_adapter.py`: adaptador `rocket-rigid-body` do contrato `vv-sim-adapter.v2`.

## Referenciais e unidades

Unidades SI em todo o modelo: m, s, kg, N, N·m, kg·m², rad, rad/s.

- **Referencial inercial N**: local, plano e sem rotação, com origem num ponto fixo do solo. `x_N` aponta para leste, `y_N` para norte e `z_N` para cima (ENU). A altitude é `z_N` do centro de massa.
- **Referencial do corpo B**: origem no centro de massa instantâneo. `x_B` segue o eixo longitudinal, da base para o nariz; `y_B` e `z_B` completam um triedro direto.
- **Estações**: posições ao longo de `x_B` medidas a partir do plano de saída da tubeira (estação 0), positivas para o nariz. O impulso atua na estação 0, sobre o eixo.
- **Quaternião**: `q = (w, x, y, z)`, escalar primeiro, produto de Hamilton, unitário. `R(q)` transforma componentes do corpo em componentes inerciais: `v_N = R(q) v_B = q ⊗ (0, v_B) ⊗ q*`. A identidade alinha `x_B` com leste.
- **Velocidade angular**: `ω_B`, velocidade angular de B relativamente a N, em componentes de B.

## Estado real

`r_N` (posição do centro de massa, m), `v_N` (m/s), `q`, `ω_B` (rad/s) e `m_p` (massa de propelente, kg). A massa total é `m = m_dry + m_p`. O tempo é `t = k·dt` com `k` inteiro.

## Massa, centro de massa e inércia

Hipóteses explícitas:

1. A massa seca tem centro de massa fixo na estação `s_dry` e tensor de inércia diagonal `I_dry` em torno do seu próprio centro de massa.
2. O propelente tem centro de massa fixo na estação `s_p`. O seu tensor em torno desse ponto escala linearmente com a massa: `I_p(m_p) = (m_p / m_p0) · I_p0`, o que corresponde a um volume fixo cuja densidade diminui uniformemente (uma geometria semelhante com densidade constante daria `I ∝ m^(5/3)`). Se `m_p0 = 0`, não há propelente.
3. Os eixos principais coincidem com B; os tensores são diagonais.

Centro de massa: `s_cm = (m_dry·s_dry + m_p·s_p) / m`. Inércia em torno do centro de massa, pelo teorema dos eixos paralelos ao longo de `x_B` (`d = s − s_cm`):

```
I_xx = I_dry,xx + I_p,xx
I_yy = I_dry,yy + m_dry·d_dry² + I_p,yy + m_p·d_p²   (igual para zz)
```

A derivada `dI/dt = (dI/dm_p)·ṁ_p` é calculada analiticamente a partir destas fórmulas e inclui a variação de `s_cm`.

## Equações do movimento

Propulsão idealizada: `T = u·T_max`, com acelerador `u ∈ [0, 1]` e direção `d_B` (vetor não nulo do pedido, normalizado pelo simulador). Caudal de saída `ṁ_e = T / (I_sp·g0)`, com `g0 = 9.80665 m/s²` (constante de definição do impulso específico, independente da gravidade local `g`). `ṁ_p = −ṁ_e`.

Arrasto: `F_D,N = −½·ρ(z)·C_D·A·|v_N|·v_N`, sem vento. `ρ(z) = ρ0·exp(−z / H)`, ou `ρ = ρ0` constante se `H` for nulo. O arrasto atua no centro de massa: não há momentos aerodinâmicos neste marco.

Gravidade uniforme: `g_N = (0, 0, −g)`.

```
ṙ_N = v_N
m·v̇_N = m·g_N + R(q)·(T·d_B) + F_D,N
q̇ = ½ · q ⊗ (0, ω_B)
I·ω̇_B = M_B − ω_B × (I·ω_B) − İ·ω_B − ṁ_e · r_e × (ω_B × r_e)
ṁ_p = −ṁ_e
```

com `M_B = r_e × (T·d_B)` e `r_e = (0 − s_cm, 0, 0)`, posição da saída da tubeira relativa ao centro de massa.

A equação rotacional resulta do teorema de transporte de Reynolds aplicado a um volume de controlo solidário com o corpo: o momento angular do conteúdo é `I·ω`, cuja derivada inclui `İ·ω`; o gás que sai pela tubeira leva o fluxo `ṁ_e·r_e × (ω × r_e)` (amortecimento do jato). Hipóteses: a massa interior roda rigidamente com o corpo até à saída (sem escoamento interno, sem movimento do propelente nos tanques) e desprezam-se os termos devidos ao deslocamento do centro de massa dentro do corpo. Existem formas alternativas na literatura; esta é uma hipótese do modelo, revista como tal, e os testes de conservação usam caudal nulo para não dependerem dela.

Termos desprezados na translação, declarados após a revisão independente: o mesmo teorema aplicado à quantidade de movimento dá `m·a = F + R(q)·[T·d_B − ṁ_e·(ω_B × r_e − ċ_B)]`, em que `ċ_B` é a velocidade do centro de massa relativamente ao corpo. O modelo despreza o termo `−ṁ_e·R(q)·(ω_B × r_e − ċ_B)` e, de forma coerente com a hipótese de massa interior rígida, o escoamento interno implícito no facto de o propelente desaparecer em `s_p` e sair na estação 0. A primeira versão deste documento dizia que, no caso de convergência, `|ṁ_e·ω × r_e|` era da ordem de 2 N face a 15 kN (cerca de 1.5e-4). Esse valor só é válido no instante inicial (1.1 N). A segunda ronda mediu a parte de massa rígida do termo ao longo do caso: cresce com `ω` e chega a 141 N aos 4 s, 9.4e-3 do impulso (registado no caso 5). A revisão independente desta ronda notou que o escoamento interno que o modelo implica, do propelente em `s_p` até à saída, acrescenta um termo de Coriolis da mesma ordem: com escoamento estacionário ao longo do eixo, o resultado clássico é `m·a = F + T − 2·ṁ_e·R(q)·(ω_B × r_e − ċ_B)`, independente de `s_p`. O termo total desprezado é assim cerca do dobro do registado, até cerca de 283 N (1.9e-2) no caso 5.

Ordem de grandeza e domínio de validade. Com `T = ṁ_e·c_e` e `c_e = I_sp·g0`, a razão entre o termo desprezado e o impulso é `ε = 2·|ω_B × r_e| / c_e ≤ 2·|ω_⊥|·|r_e| / c_e`, em que `ω_⊥` é a componente transversal de `ω_B`: é a razão entre a velocidade de rotação da tubeira e a velocidade de escape. O termo em `ċ_B` tem razão `|ċ_B| / c_e`, com `|ċ_B| = ṁ_e·|s_p − s_cm| / m`, muito menor nos casos deste marco. O modelo é adequado enquanto `ε ≪ 1`; o erro relativo na aceleração translacional é dessa ordem. Valores das demonstrações por omissão, medidos pelo simulador em cada passo (ver a seguir): balística sem impulso (`ε = 0`), descida propulsiva 5.1e-5 aos 19.69 s, atitude 2.7e-3 aos 4.08 s. A primeira versão deste parágrafo usava só as amostras gravadas e dava 4.1e-5 na descida. Nos casos de verificação, registados à parte: caso 5 até 1.9e-2; caso 8 até cerca de 2.2e-2 no fim, com 11.8 rad/s. A equação rotacional não muda: com escoamento sobre o eixo, `r × u = 0` e o momento angular do conteúdo continua a ser `I·ω`. Para rotações rápidas durante a queima, ou tubeiras longe do centro de massa, o termo deixa de ser desprezável e tem de entrar no modelo.

Medição em cada execução (2026-10-28). O domínio de validade era declarado mas não medido: uma execução do Mission Control com outros parâmetros podia sair dele sem aviso. O simulador calcula agora `ε = 2·|ω_B × r_e − ċ_B| / c_e`, com `ċ_B = −ṁ_e·(s_p − s_cm)/m` segundo `x_B`, nos dois extremos de cada passo com impulso, e guarda o máximo e o instante no resumo do traço (`max_neglected_jet_ratio`, `max_neglected_jet_ratio_t_s`, esquema `vv-rocket-trace.v2`). Sem impulso, `ε = 0`. A medição não entra na derivada. É um valor `reported`, sem limite de aceitação: este marco não fixa um valor de `ε` a partir do qual o resultado é rejeitado, e escolher um agora seria arbitrário. O máximo é tomado nos extremos dos passos e não nas avaliações intermédias do RK4. Um teste compara a função com uma conta à mão; outro confirma que as amostras e os eventos das três demonstrações têm os mesmos hashes que no simulador anterior (`8b04960`), pelo que só o resumo mudou.

Consequência verificável: em rolamento puro com propelente a esgotar-se, sem binário, `I_xx·ω_x` mantém-se constante (o gás sai sobre o eixo e não leva momento angular de rolamento).

## Integrador

Runge-Kutta clássico de 4.ª ordem, passo fixo `dt`. Os estados intermédios usam a mesma derivada; a matriz de rotação de cada avaliação é calculada a partir de `q/|q|`. No fim de cada passo, `q` é renormalizado (projeção). O desvio de norma antes da projeção é medido e registado.

Para manter a derivada suave dentro de cada passo:

- O impulso é um calendário de segmentos `{start_s, end_s, throttle, direction_body}`. Os limites têm de ser múltiplos inteiros de `dt` (tolerância relativa 1e-9) e os segmentos não podem sobrepor-se.
- O pedido é rejeitado se o calendário consumir mais propelente do que o disponível (o consumo é exato, porque `ṁ_e` é constante em cada segmento). Não há corte de motor a meio de um passo.
- O cruzamento da altitude 0 m é detetado no fim de um passo; a simulação para nesse passo se `stop_at_ground` for verdadeiro. O instante estimado do cruzamento é obtido por interpolação cúbica de Hermite de `z` e `v_z`; a velocidade estimada nesse instante é uma interpolação linear entre os dois passos. Só são registados cruzamentos descendentes a partir de uma altitude não negativa. Não há modelo de contacto: um cruzamento não é uma aterragem.

## Eventos

Ordem total por passo e, no mesmo passo `k`, por esta ordem: `burn_end` (segmento que termina em `k`), `ground_crossing`, `burn_start` (segmento que começa em `k`) e `end`, que regista o motivo (`duration` ou `ground`). Segmentos do mesmo tipo seguem o índice do calendário.

Cada amostra do traço no passo `k` regista o estado nesse instante e as forças aplicadas no intervalo `[k, k+1)`.

## Determinismo e exceção à aritmética inteira

O núcleo terrestre usa aritmética inteira. Este modelo usa `f64` por necessidade, com uma exceção limitada e verificável:

- A integração usa apenas `+`, `−`, `×`, `÷` e `sqrt`, que o IEEE 754 exige corretamente arredondados. Rust não contrai multiplicações e somas em FMA.
- A única função transcendente no caminho da integração, `exp`, tem implementação própria no crate (redução de argumento e polinómio), sem depender da libm da plataforma.
- A atitude inicial é dada por componentes de quaternião e a direção do impulso por um vetor; o simulador não calcula senos nem cossenos.
- O JSON é escrito com a representação mais curta que reproduz cada `f64`.

Contrato numérico, por artefacto:

- **Traço (`trace.json`)**: esperado igual byte a byte entre plataformas com aritmética IEEE 754 binary64 sem arredondamento duplo, como x86_64 com SSE2 e aarch64; exclui alvos x87. A garantia vem das operações acima, corretamente arredondadas, da ausência de contração em FMA em Rust e da `exp` própria. Um teste fixa o hash do traço das três demonstrações e corre em Linux e Windows na CI. Uma diferença entre plataformas é um defeito a investigar, não uma tolerância a alargar.
- **Relatório de verificação (`verification.json`)**: não é igual byte a byte entre plataformas. As referências analíticas usam `ln`, `cos`, `sin`, `tanh`, `exp`, `atan`, `hypot`, `powi` e `log2` da biblioteca da plataforma, que o IEEE 754 não obriga a arredondar corretamente. O contrato entre plataformas é o estado de cada critério e de cada caso, não os bytes nem os últimos dígitos dos valores. Um estado só pode mudar se o valor estiver a poucos ulp do limite; o caso mais apertado é o das rotações de 90°, com 3.1e-16 face a 1e-15. Na mesma compilação e na mesma máquina, o adaptador exige igualdade byte a byte com um relatório novo.
- **Identidade da execução (`run_id`)**: inclui o hash do binário, que difere entre plataformas e compilações. Duas plataformas dão `run_id` diferentes para o mesmo pedido; a comparação entre plataformas faz-se pelo hash do traço.

Estado em 2026-10-28: a CI da integração em `main` (`8b04960`, execução 40246481045, Rust 1.99.0) passou em `ubuntu-latest` e `windows-latest`, incluindo `demo_traces_are_bit_identical_on_every_platform` e o teste dos estados dos critérios. Os hashes do traço v1 eram iguais nas duas plataformas. O esquema v2 muda os hashes do traço completo; a igualdade entre plataformas dos novos valores depende da próxima execução da CI.

## Validação de entradas

Rejeitado com mensagem: campos desconhecidos; números não finitos; `dt` fora de [1e-4, 1] s; mais de 200 000 passos; mais de 2 000 amostras no traço; massas negativas ou massa seca nula; momentos de inércia não positivos ou que violem a desigualdade triangular (`I_a + I_b ≥ I_c`); `T_max`, `I_sp`, `C_D`, `A`, `ρ0`, `H` ou `g` negativos ou fora de limites; quaternião inicial de norma afastada de 1 em mais de 1e-6; direção de impulso nula; segmentos fora da duração, sobrepostos, desalinhados com `dt` ou com consumo acima do propelente. Durante a integração, um estado não finito, massa negativa ou norma de quaternião nula interrompe a execução com erro.

## Casos de verificação e tolerâncias (fixadas antes dos testes)

`g = 9.80665 m/s²` salvo indicação. Erros absolutos em unidades SI; erros relativos em relação ao valor analítico.

| Caso | Condições | Referência | Tolerância |
| --- | --- | --- | --- |
| 1. Balística no vácuo | `r0 = (0, 0, 100)`, `v0 = (30, −10, 40)`, sem impulso nem arrasto, `dt = 0.01`, 8 s | `r = r0 + v0·t + ½·g·t²` | `|Δr| ≤ 1e-9 m`, `|Δv| ≤ 1e-10 m/s` |
| 2. Tsiolkovsky | `g = 0`, `m_dry = 1000`, `m_p0 = 500`, `T = 20 000 N`, `I_sp = 300 s`, impulso em `x_B`, 0 a 50 s, `dt = 0.01` | `Δv = I_sp·g0·ln(m0/m_f)`, `m_f = m0 − ṁ·t`, `x(t) = c·(t + (m_f/ṁ)·ln(m_f/m0))` | rel. `Δv ≤ 1e-9`, `|Δm_f| ≤ 1e-9 kg`, rel. `x ≤ 1e-9` |
| 3a. Rotação sem binário (assimétrico) | `I = diag(2, 3, 4)`, `ω0 = (1.0, 0.2, 0.5)`, sem propelente, `dt = 0.001`, 20 s | energia `½·ω·Iω` e `H_N = R(q)·I·ω` constantes | rel. ≤ 1e-9 em ambos |
| 3b. Precessão (axissimétrico) | `I = diag(2, 1, 1)`, `ω0 = (2, 0.3, 0)`, `dt = 0.001`, 10 s | `ω_y = 0.3·cos(2t)`, `ω_z = 0.3·sin(2t)`, `ω_x = 2` | `|Δω| ≤ 1e-10 rad/s` |
| 4. Quaterniões e referenciais | rotações conhecidas, ida e volta, composição; rotação constante `ω = (0, 0, 0.5)` em eixo principal | `q(t) = (cos(ωt/2), 0, 0, sin(ωt/2))` | ida e volta e ortonormalidade ≤ 1e-14 relativo; `|Δq| ≤ 1e-12`; norma após projeção `||q| − 1| ≤ 1e-14`; desvio por passo antes da projeção ≤ 1e-12 |
| 5. Convergência | caso acoplado: gravidade, atmosfera exponencial, impulso vetorizado com binário, massa variável, `ω0 ≠ 0`, 4 s sem eventos internos | solução com `dt = 0.000625` | ordem observada `p ∈ [3.6, 4.4]` para os pares `0.04/0.02` e `0.02/0.01` |
| 6a. Velocidade terminal | `ρ = 1.2` constante, `C_D = 1`, `A = 0.5`, `m = 10`, queda do repouso a 2000 m, `dt = 0.01`, 30 s | `v = −v_t·tanh(g·t/v_t)`, `z = z0 − (v_t²/g)·ln cosh(g·t/v_t)`, `v_t = √(2mg/(ρ·C_D·A))` | rel. `v ≤ 1e-8`, `|Δz| ≤ 1e-6 m` |
| 6b. `exp` determinística | `x ∈ [−12, 2]` | `f64::exp` da plataforma | rel. ≤ 1e-15 |
| 7a. Rolamento com massa variável | `g = 0`, `m_dry = 100`, `m_p0 = 50`, `I_dry = diag(10, 100, 100)`, `I_p0 = diag(5, 40, 40)`, `s_dry = 2`, `s_p = 1.5`, `T = 2000 N`, `I_sp = 200 s`, `ω0 = (1, 0, 0)`, 10 s | `I_xx·ω_x` constante | rel. ≤ 1e-9 |
| 7b. Amortecimento do jato | como 7a, `ω0 = (0, 0.2, 0)` | integração escalar de `d(I_yy·ω)/dt = −ṁ_e·r_e²·ω` com `dt/100` e propriedades de massa escritas de forma independente; verifica a implementação dos termos `İ·ω` e do jato face à hipótese, não a hipótese | rel. ≤ 1e-8 |
| 2b. Tsiolkovsky com atitude rodada | como 2, com `q = (√0.8, 0, 0, √0.2)`, isto é, `x_B` segundo `(0.6, 0.8, 0)` em N | `v = Δv·(0.6, 0.8, 0)`, `r = x·(0.6, 0.8, 0)` | rel. ≤ 1e-9 em ambos os vetores |
| 8. Binário do TVC num eixo principal | como 7a, com `ω0 = 0` e `direction_body = (1, 0.05, 0)`, 10 s | integração escalar de `d(I_zz·ω_z)/dt = −s_cm·T·sin δ − ṁ_e·s_cm²·ω_z` com `dt/100`; o nariz roda para `−y_N` | rel. ≤ 1e-8; componente `y_N` do nariz ≤ 0; `|(ω_x, ω_y)|` ≤ 1e-15 rad/s |

Os casos 2b e 8 foram acrescentados depois da revisão científica independente, que notou que nenhum caso verificava o sentido de `R(q)` aplicado ao impulso nem o sinal do binário do TVC. As suas tolerâncias foram fixadas aqui antes da primeira execução.

As linhas 4 e 8 da tabela são os critérios da primeira execução e mantêm-se como foram registados. A secção seguinte acrescenta critérios revistos para estes dois casos; não altera nenhum limite.

### Critérios revistos dos casos 4 e 8 (segunda ronda, 2026-10-25)

Escritos antes de qualquer execução do código que os avalia. Nenhum limite da primeira execução foi alterado. O relatório guarda cada critério com um de quatro estados: `pass`, `fail`, `invalid` (o critério não mede o que pretende) e `reported` (sem critério). Um critério substituído mantém o seu estado original e indica `superseded_by`. Um caso tem estado `PASS` se todos os critérios ativos forem `pass`, `FAIL` se algum for `fail` e `INVALID` se não restar nenhum critério ativo. Critérios `invalid` ou substituídos ficam no relatório e nunca contam como `pass`.

**Caso 4.** O critério original (`|Δq| ≤ 1e-12` com `dt = 0.01` s) fica registado como `fail` (1.627e-12) e substituído, por decisão do responsável, pelo mesmo limite com `dt = 0.005` s. A tolerância não muda. Declaração: o erro com `dt = 0.005` s (9.982e-14) e a ordem entre 0.01 e 0.005 s (4.03) já constavam da série de evidência da primeira execução, pelo que este critério não é cego; só o passo foi escolhido de novo.

Estimativa da truncatura, escrita agora, depois da primeira execução: para rotação constante num eixo principal, `q̇ = ½·q ⊗ (0, ω)` é linear e um passo de RK4 aplica o polinómio de Taylor de grau 4 de `exp(iθ)` com `θ = ω·h/2`. O erro de fase por passo é `θ⁵/120`; o erro de módulo, de ordem `θ⁶`, é removido pela projeção. Em `N = T/h` passos, `|Δq| ≈ T·(ω/2)⁵·h⁴/120`: 1.628e-12 com `h = 0.01` s e 1.017e-13 com `h = 0.005` s, para `T = 20 s` e `ω = 0.5 rad/s`. A primeira execução falhou por um limite fixado sem esta conta, não por erro do modelo.

Critérios ativos do caso 4: os quatro de álgebra e norma da tabela, sem alteração; `|Δq| ≤ 1e-12` com `dt = 0.005` s; ordem observada entre `dt = 0.01` e `0.005` s em `[3.6, 4.4]`.

**Caso 8.** O critério original "componente `y_N` final do nariz ≤ 0" é `invalid`: o estágio dá cerca de 9.5 voltas em 10 s e a direção final do nariz não tem informação sobre o sinal do binário. Fica no relatório com o valor observado (0.094) e não conta. Mantêm-se os critérios `I_zz·ω_z` (rel. ≤ 1e-8) e `|(ω_x, ω_y)| ≤ 1e-15 rad/s`.

Modelo de referência independente, escrito a partir da geometria e não de `dynamics.rs`: com rotação apenas em `z_N` a partir da identidade, o nariz faz o ângulo `ψ` com `x_N`, e a direção do impulso, `(1, 0.05, 0)` normalizada no corpo, faz `ψ + δ` com `δ = atan(0.05)`. A força lateral `+y_B` aplicada na cauda, a `s_cm` atrás do centro de massa, dá `M_z = −s_cm·T·sin δ`. O estado escalar `(h = I_zz·ω_z, ψ, v_x, v_y)` evolui com `ḣ = −s_cm·T·sin δ − ṁ_e·s_cm²·h/I_zz`, `ψ̇ = h/I_zz`, `v̇_x = (T/m)·cos(ψ + δ)` e `v̇_y = (T/m)·sin(ψ + δ)`, integrado com RK4 a `dt/100`.

Estimativas a priori, com este modelo escalar e sem o simulador: `ω̇_z(0) = −1.2344 rad/s²` e `ψ(1 s) = −0.615 rad`. Em `[0, 1]` s, `|ψ| < π/2` e a orientação não é ambígua. O erro de fase do RK4 com `dt = 0.01` s, estimado com `∫ω⁵·h⁴/3840 dt` e `ω` a crescer até cerca de 12 rad/s, é da ordem de 1e-6 rad em 10 s e abaixo de 1e-11 rad em 1 s.

Critérios novos do caso 8:

1. Aceleração angular inicial: `ω̇_z(0)`, calculada pela derivada do modelo no estado inicial, com erro relativo ≤ 1e-12 face a `−s_cm·T·sin δ / I_zz`. Como a referência é negativa e não nula, o critério fixa o sinal.
2. Janela `[0, 1]` s (100 passos). Pré-condição: `max |ψ| ≤ π/2` no modelo escalar; se falhar, os critérios 2a e 2b ficam `invalid`. Critério 2a: componente `y_N` do nariz `< 0` em todos os passos de `(0, 1]` s. Critério 2b: `max |nariz − (cos ψ, sin ψ, 0)| ≤ 1e-9`, com margem de cerca de 100 vezes sobre a estimativa.
3. Acoplamento translacional e angular em 10 s: `max |v_N − (v_x, v_y, 0)| / max |(v_x, v_y)| ≤ 1e-5`, com margem de cerca de 10 vezes sobre o erro de fase estimado. A componente `z` entra na diferença com referência nula, porque `g = 0`.

O caso 8, como o 7b, verifica a implementação da hipótese declarada para o jato, não a hipótese.

Correção posterior, da revisão independente, sem alterar os critérios acima: o erro de direção do nariz é o ângulo completo, pelo que a estimativa correta é `∫ω⁵·h⁴/1920 dt`, o dobro da escrita. Dá cerca de 2.2e-12 em 1 s (medido 2.4e-12; margem do critério 2b de cerca de 450 vezes) e 2.2e-6 rad em 10 s. Para o critério 3, um limite coerente é `∫a·δψ dt / max |v| ≈ 3e-6`, uma margem de cerca de 3 vezes, não 10; o valor medido, 1.2e-7, é menor porque o erro roda com o impulso e tende a anular-se.

### Resultados da primeira execução

Executado em 2026-10-25, Windows 11, `cargo build --release` com Rust 1.99.0 e `vv-rocket verify`. O teste `reference_cases_meet_their_active_criteria_and_keep_the_replaced_ones` repete esta execução em cada `cargo test`.

Dez dos doze casos cumprem todos os critérios; em dois, um critério fixado antes da execução não é cumprido, e ambos se mantêm como registados.

No caso 8, o critério "componente `y_N` final do nariz ≤ 0" **não é cumprido** (0.094). O estágio roda cerca de −59.8 rad (perto de 9.5 voltas) em 10 s, com `ω_z` final de −11.76 rad/s, pelo que a direção final do nariz não informa sobre o sinal do binário: o critério foi mal desenhado, não o modelo. O sinal está confirmado pelo primeiro critério do caso (`I_zz·ω_z` coincide com o modelo escalar escrito a partir de princípios físicos, erro relativo 1.1e-14) e pela componente `y_N` do nariz aos 0.5 s, −0.15 (registada, sem critério). A revisão do critério pertence ao responsável.

No caso 4, um critério fixado antes da execução **não é cumprido**: o erro máximo de atitude face a `q(t)` com `dt = 0.01` s é 1.627e-12, acima do limite de 1e-12. Com outros passos, o erro é 2.604e-11 (0.02 s), 9.982e-14 (0.005 s) e 5.934e-15 (0.0025 s): cai cerca de 16 vezes por cada redução do passo para metade, ou seja, é o erro de truncatura de 4.ª ordem do RK4, não um erro do modelo. O limite foi fixado sem estimativa prévia dessa truncatura. O critério mantém-se como registado; a decisão de o rever (com estimativa explícita) ou de correr o caso com `dt = 0.005` s pertence ao responsável. `vv-rocket verify` termina com código 1 enquanto estes critérios falharem.

Valores observados nos restantes casos (limites na tabela): balística 4.6e-12 m e 7.2e-13 m/s; Tsiolkovsky 1.1e-15 (Δv relativo), 9.1e-13 kg, 1.8e-15 (posição relativa); rotação assimétrica 7.1e-15 (energia) e 1.4e-14 (momento angular); precessão 8.0e-13 rad/s; ordem observada 3.94 e 3.97; velocidade terminal 1.3e-11 e 3.5e-10 m; `exp` 2.2e-16; rolamento com massa variável 1.2e-14; amortecimento do jato 1.0e-14; Tsiolkovsky com atitude rodada 1.1e-15 e 1.0e-15.

A revisão independente notou ainda que o limite de 1e-12 para o desvio de norma por passo antes da projeção só deteta um esquema errado: o desvio do RK4 neste caso é da ordem de 1e-18 e o valor medido, 2.2e-16, é arredondamento. Fica como está, com esta limitação declarada.

### Resultados da segunda ronda

Executado em 2026-10-25, Windows 11, Rust 1.99.0, `cargo build --release` e `vv-rocket verify`, depois de registar os critérios revistos acima. `vv-rocket verify` termina com código 0. Os doze casos têm estado `PASS` nos critérios ativos; nenhum caso é `FAIL` nem `INVALID`. Dois critérios da primeira execução ficam no relatório e não contam como `pass`:

- Caso 4, `|Δq|` com `dt = 0.01` s: `fail` (1.627e-12, limite 1e-12), substituído. Critério ativo com `dt = 0.005` s: 9.982e-14, `pass`. Ordem 0.01/0.005: 4.03, `pass`. Estimativa da truncatura: 1.628e-12 e 1.017e-13.
- Caso 8, nariz final: `invalid` (0.094). Critérios novos: erro relativo de `ω̇_z(0)` 3.6e-16 (`ω̇_z(0) = −1.2344 rad/s²`); maior componente `y_N` do nariz em `(0, 1]` s −6.2e-5 (no primeiro passo, igual a `½·ω̇_z·t²`); erro do nariz face ao modelo plano 2.4e-12; erro de velocidade em 10 s 1.2e-7. Pré-condição cumprida: `max |ψ| = 0.615 rad` em `[0, 1]` s.

Os restantes valores não mudaram. A ordem e a data do registo podem ser confirmadas pelo histórico deste ficheiro quando for integrado; até lá, só há a declaração do autor.

### Casos NASA NESC (NASA/TM-2015-218675)

Não verificados neste marco. A razão decisiva é que as trajetórias de referência publicadas não estão no repositório nem podem ser descarregadas neste marco, e sem elas não há comparação. Além disso, a maioria dos casos atmosféricos exige ambiente que este modelo não tem (Terra WGS-84, gravidade com J2, atmosfera US Standard 1976); alguns, como os casos do tijolo em rotação, podem ser compatíveis com este modelo, mas continuam a precisar dos dados de referência. Reescrever parâmetros de memória e chamar-lhes casos NESC seria uma alegação sem evidência. O equivalente rotacional (corpo sem binário) está coberto pelos casos 3a e 3b; os casos NESC ficam para quando o modelo tiver o ambiente que exigem.

## Integração no produto

O Mission Control serve a página `/rocket`, que pede `/api/models` (contrato `vv-sim-adapter.v2`) e envia pedidos `vv-sim-run-request.v2` para `/api/run`, que despacha pelo campo `model`. O modelo `ground-vehicle-2d`, a página principal e `/api/describe` (v1) ficam iguais. `sim_adapter.check_result` valida os dois contratos; um resultado v2 exige ainda `events`, `summary`, `physics_reference` e `model_validity`, e o `model.id` tem de coincidir com o pedido.

Cada execução guarda `inputs/request.json`, `inputs/case.json`, `case.json`, `trace.json`, `run.json` e `verification.json` (o relatório de `vv-rocket verify` do mesmo binário). A publicação, o bloqueio entre processos e a reutilização com regeneração byte a byte são os do M7. Cada leitura de uma execução guardada (`RocketAdapter.verify`) volta a calcular o traço com `vv-rocket replay` e o relatório de referência com `vv-rocket verify`, compara ambos byte a byte com o que está guardado e confirma que `inputs/request.json` valida e produz exatamente `inputs/case.json`, igual a `case.json`. A verificação de referência mostrada vem sempre do cálculo novo, nunca do ficheiro guardado. O nome da pasta de cada execução é o `run_id` do pedido guardado, do caso que ele produz e do binário atual. `RocketAdapter.verify` recalcula-o e rejeita uma execução copiada para outro `run_id`, feita por outro binário ou por outro modelo. `sim_adapter.check_result` exige que um resultado v1 responda a um pedido v1 de `ground-vehicle-2d` e que um resultado v2 tenha `request.schema` v2 e `model.id` igual a `request.model`; um resultado trocado entre modelos é recusado. `vv-rocket replay` regenera também `run.json` e compara-o byte a byte, pelo que um nome ou resumo forjado é rejeitado mesmo com os hashes intactos; o adaptador rejeita ficheiros que não produz. Os testes cobrem estes casos e a troca de ficheiros produzidos pelo próprio `vv-rocket`, que o `replay` sozinho não deteta.

A página mostra três afirmações separadas: a evidência (integridade e `vv-rocket replay`), a verificação de referência da compilação (com os critérios não cumpridos e o seu diagnóstico) e a validade do modelo, com o `ε` medido nessa execução. Se a evidência não for verificada, o valor de `ε` não é mostrado. Um cruzamento de 0 m é descrito como tal, com a velocidade estimada, nunca como aterragem.

## Demonstrações

Executadas em 2026-10-25, Windows 11, através de `RocketAdapter.run`; todas com evidência verificada. Os valores são do traço gravado.

| Experiência | Parâmetro | Resultado |
| --- | --- | --- |
| Balística | por omissão (200 m/s, `C_D = 0.3`) | apogeu 1103.5 m; cruza 0 m aos 29.98 s, 2951.8 m a leste |
| Balística | `C_D = 0` (vácuo) | apogeu 1305.237 m (analítico `v_z²/2g` = 1305.237 m); 32.63 s; 3916.8 m |
| Balística | 400 m/s | apogeu 3278.5 m; não cruza 0 m nos 40 s gravados |
| Descida propulsiva | ignição 7.15 s (por omissão) | cruza 0 m aos 19.69 s a −17.4 m/s vertical e 6.9 m/s horizontal; 3065 kg de propelente |
| Descida propulsiva | ignição 7.20 s | cruza 0 m aos 19.18 s a −25.9 m/s vertical |
| Descida propulsiva | ignição 7.10 s | não cruza 0 m: altitude mínima 2.3 m, depois sobe; aos 40 s está a 1885.7 m e a +67.6 m/s; 6087 kg |
| Descida propulsiva | acelerador 0.9 | altitude mínima 200.0 m, depois sobe |
| Atitude | rolamento 1.5 rad/s (por omissão) | taxa transversal máxima 0.81 rad/s; inclinação máxima 81.8°; rolamento final 1.534 rad/s (sobe porque `I_xx` diminui) |
| Atitude | rolamento 0 | taxa transversal máxima 2.45 rad/s; o eixo chega a 179.7° de inclinação |
| Atitude | rolamento 4 rad/s | taxa transversal máxima 0.30 rad/s (rigidez giroscópica) |
| Atitude | `gimbal_lateral = 0` | taxa transversal máxima 0.02 rad/s (só a taxa inicial, sem binário); a inclinação cresce devagar até 24.2° aos 30 s |

A descida é um calendário em malha aberta: uma diferença de 0.05 s na ignição separa um cruzamento a −17 m/s de uma subida. Isto mostra a sensibilidade do problema, não um resultado de controlo.

## Limitações materiais

- Validade física: modelo idealizado, verificado contra soluções analíticas e modelos de referência escritos de forma independente, não validado contra dados de voo. Não há dados de voo nem casos NASA compatíveis no repositório; o relatório declara as duas lacunas.
- Verificação não é validação: os casos mostram que o código implementa as equações declaradas, não que as equações descrevem um veículo real.
- Sem momentos aerodinâmicos, vento, Terra em rotação, J2, atmosfera padrão, dinâmica de atuadores, limites de taxa do TVC, movimento do propelente, corpo flexível ou contacto com o solo.
- A forma da equação rotacional com massa variável é uma hipótese declarada.
- Calendário de impulso em malha aberta; não há controlador nem sensores neste marco.

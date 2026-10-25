# Especificação: recuperação de primeiro andar de foguete

Especificação técnica do próximo domínio. Nada disto está implementado nem foi simulado. O objetivo é fixar fronteiras, dados, verificação e interfaces antes de escrever código, para que a primeira simulação seja verificável desde o início.

## Fases da missão (da separação à aterragem)

| Fase | Início | Fim | Atuadores relevantes |
| --- | --- | --- | --- |
| Separação | comando de separação | afastamento do segundo andar a distância segura | nenhum ou RCS |
| Coasting e reorientação | fim da separação | atitude para a queima de regresso | RCS (gás frio) |
| Queima de regresso (opcional) | ignição | velocidade horizontal alvo | motores, TVC |
| Coasting balístico | fim da queima de regresso | início da queima de entrada | RCS, aletas em grelha |
| Queima de entrada | limite de pressão dinâmica ou de aquecimento | fim da queima | motores, TVC |
| Descida aerodinâmica | fim da queima de entrada | ignição de aterragem | aletas em grelha |
| Queima de aterragem | ignição | contacto | motor central, TVC, acelerador |
| Contacto e estabilização | primeiro contacto das pernas | velocidades abaixo dos limites | nenhum |

Cada transição de fase é um evento registado com a condição que a desencadeou, como as transições do veículo terrestre.

## Fronteira do modelo 6-DOF proposto

Dentro do modelo:

- Corpo rígido com 6 graus de liberdade: posição e velocidade (3), atitude em quaterniões e velocidade angular (3).
- Massa, centro de massa e tensor de inércia variáveis com o consumo de propelente.
- Impulso com limites e taxas de variação do acelerador, vetorização de impulso (TVC) com limites de ângulo e de taxa.
- Forças e momentos aerodinâmicos a partir de tabelas de coeficientes em função do número de Mach e do ângulo de ataque, incluindo as aletas em grelha.
- Gravidade com J2, atmosfera padrão com perfil de vento, Terra em rotação num referencial local para a fase final.
- Integração com passo fixo e registo determinístico, com a mesma separação entre estado real e observações do núcleo atual.

Fora do modelo (primeira versão), com justificação registada: corpo flexível, movimento do propelente nos tanques (slosh), transientes detalhados do motor, interação da pluma com o solo, aquecimento aerodinâmico, dinâmica das pernas no contacto (substituída por critérios de contacto).

## Dados de ambiente e meteorologia

- Atmosfera padrão (US Standard Atmosphere 1976) como base.
- Perfis de vento por altitude (velocidade e direção), a partir de sondagens ou de reanálises (por exemplo, NOAA IGRA ou ERA5), guardados como instantâneos locais com hash; nunca obtidos durante uma execução.
- Turbulência com um modelo espectral normalizado (por exemplo, Dryden) com semente explícita.
- Para aterragem no mar: movimento da plataforma (arfagem, balanço) a partir de um espetro de estado do mar, também com semente.
- Cada execução regista a origem e o hash de cada conjunto de dados.

## Verificação do modelo físico

Antes de qualquer resultado de controlo, o modelo tem de passar casos de referência com tolerâncias registadas:

1. Trajetória balística no vácuo com gravidade uniforme: solução analítica.
2. Equação do foguete de Tsiolkovsky com impulso constante: variação de velocidade e massa final.
3. Corpo rígido sem binário: conservação da energia cinética de rotação e do momento angular; precessão de um corpo assimétrico.
4. Queda com arrasto numa atmosfera exponencial: velocidade terminal.
5. Casos de verificação de simuladores 6-DOF da NASA Engineering and Safety Center (NASA/TM-2015-218675), com comparação de trajetórias.
6. Convergência do integrador com o passo: ordem observada e deriva de energia dentro de limites.
7. Normalização dos quaterniões e transformações entre referenciais com testes de ida e volta.

## Interfaces do veículo e do controlador

- **Estado real**: posição, velocidade, atitude, velocidade angular, massa, propelente restante, estado de cada atuador.
- **Sensores** (observações): IMU (acelerómetros e giroscópios com polarização, ruído e saturação), GNSS (com perdas), altímetro radar, navegação relativa à plataforma. O controlador só recebe observações.
- **Comandos**: acelerador (0 a 1, com taxa limitada), ângulos de TVC, deflexões das aletas, impulsos de RCS. Cada comando tem limites e taxas declarados no contrato.
- **Controlador**: chamado a uma frequência fixa com observações e configuração da missão; devolve comandos. O mesmo controlador corre em simulação e em reprodução.

## Requisitos e taxonomia de falhas

Requisitos (valores numéricos por missão, fixados antes das campanhas):

- Velocidade vertical e horizontal no contacto abaixo dos limites.
- Inclinação e velocidade angular no contacto abaixo dos limites.
- Erro de posição no contacto dentro do raio da zona de aterragem.
- Margem de propelente no contacto acima do mínimo.
- Pressão dinâmica e fator de carga dentro do envelope em todas as fases.
- Nenhum contacto com o solo fora da zona; comportamento de abortagem definido.

Falhas (cada uma com janela, probabilidade e semente, como no núcleo atual):

- Motor: perda de impulso, falha de ignição, acelerador preso.
- TVC e aletas: atuador preso, taxa limitada, desvio.
- Sensores: perda de GNSS, deriva da IMU, perda do altímetro, atraso de dados.
- Ambiente: rajada fora do envelope, vento de cisalhamento.
- Estimação: erro na estimativa de propelente.
- Temporização: atraso do ciclo de controlo, perda de comandos.

## Estratégia para simuladores externos

O contrato de adaptador permite usar um simulador externo verificado em vez de escrever toda a física. Candidatos abertos e gratuitos a avaliar, sem decisão tomada: JSBSim (dinâmica de voo em C++), Basilisk (astrodinâmica, licença ISC), NASA Trick (ambiente de simulação), RocketPy (trajetórias de foguetes em Python).

Regras para qualquer adaptador externo:

- Declarar capacidades e limites; nunca afirmar 6-DOF ou determinismo sem os ter.
- Se o simulador não for determinístico byte a byte, declarar `deterministic: false`, registar sementes e versões e definir tolerâncias numéricas para a reprodução.
- Correr os casos de referência acima antes de qualquer resultado de missão.
- Guardar entradas, versão do simulador e hashes em cada execução, como o adaptador terrestre.
- Nenhuma ligação a hardware real nem ao Gate 1A do PX4 sem aprovação separada.

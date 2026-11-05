# M17: Experiment Lab, caso exploratório v2 e veículos de aterragem

O Studio deixa de ser apenas um leitor de experiências predefinidas. A partir de uma corrida que falhou, o utilizador muda uma condição que o modelo define, executa uma simulação nova e compara o resultado com a corrida de partida. Este documento descreve o que foi construído, o que foi medido e o que fica por fazer. Nada foi integrado; a aceitação cabe ao responsável.

Estado: ramo `feat/m17-experiment-lab`, empilhado sobre `feat/m16-geospatial` (PR #25).

## O ciclo de experimentação

1. No leitor de missões, "Change the conditions" abre a corrida mostrada no Experiment Lab. Em Analyse, "Experiment from this run" faz o mesmo para qualquer corrida guardada.
2. A coluna da esquerda mostra a corrida de base, os requisitos que falharam, o valor observado, o limite e a margem lida do registo.
3. A coluna do meio edita apenas o que o catálogo do domínio declara: cenário e veículo, controlador, semente, falhas injetadas e parâmetros por grupo. Os parâmetros que o domínio associa ao requisito em foco aparecem destacados e em primeiro lugar no grupo.
4. "Run experiment" valida o pedido e executa uma simulação nova pela plataforma. O resultado tem registo próprio, é reproduzível pela reprodução da plataforma e fica etiquetado `experiment` com a corrida de origem em `meta.json`. O registo de base nunca é alterado.
5. A coluna da direita compara veredictos, requisito a requisito, com a variação da margem, os eventos que mudaram de instante e a lista exata do que foi alterado.
6. "Does it hold on other seeds?" executa as condições de base e as novas nas mesmas sementes de desenvolvimento (de 5000 para cima, saltando as protegidas) e mostra contagens com intervalo de Wilson a 95 %.
7. "Sweep one parameter" percorre um parâmetro em 5 a 9 valores na mesma semente e desenha a margem do requisito em foco contra o valor.

Regras que o Lab impõe:

- As sugestões são as `influences` escritas à mão no catálogo do domínio. São rotuladas como pista do domínio e não como atribuição calculada a partir da corrida.
- Um limite de requisito nunca é sugerido como correção. Os parâmetros do grupo "Requirements" mudam só o julgamento; o Lab diz-o no editor e, quando só eles mudaram, diz no resultado que o voo é idêntico.
- A verificação em várias sementes é uma estimativa sobre sementes de desenvolvimento de um modelo idealizado. O texto diz que não é um valor de fiabilidade nem valida a alteração.

## Caso exploratório `vv-rocket-landing.v2`

O simulador `vv-rocket` continua a fixar um caso v1 aos valores pré-registados do M9: um ficheiro v1 com outro veículo, outro estado inicial, outro ruído de sensor ou outro limite é recusado como antes. O esquema v2 é o mesmo modelo com liberdade declarada e limitada (`check_exploratory` em `crates/vv-rocket/src/landing_model.rs`):

| Campo | Intervalo aceite |
| --- | --- |
| Massas seca e de propelente | 1000 a 200 000 kg e 100 a 200 000 kg |
| Impulso máximo sobre o peso com carga total | 1,2 a 6 |
| Isp, Cd, área, mínimo e taxa de acelerador, cardan | intervalos físicos fixos no código |
| Posição inicial | x e y de -2000 a 2000 m, z de 500 a 10 000 m |
| Velocidade inicial | x e y de -60 a 60 m/s, z de -400 a -50 m/s |
| Ruído do altímetro e da posição GNSS | 0,01 a 5 m e 0,05 a 10 m |
| Limites de R1 e R5 | 0,5 a 10 m/s e 1 a 100 m |

Dispersões, atmosfera, gravidade, atitude inicial, passo, alvo de velocidade e os limites de segurança S1 a S5 ficam fixos também no v2. O domínio escreve v2 só quando um destes valores muda; com todos os valores por omissão, o caso continua byte a byte igual ao do adaptador Python (os testes de paridade existentes passam sem alteração). O registo de uma corrida v2 traz a nota "Exploratory case" e o Lab mostra a etiqueta "Exploratory".

Testes de regressão: um caso v1 continua a recusar valores movidos; um caso v2 com os valores registados simula exatamente como o v1 (amostras e requisitos iguais); o v2 aceita alterações dentro dos intervalos e recusa impulso insuficiente, limites de segurança, dispersões e altitude fora do intervalo; um parâmetro só de julgamento deixa todos os canais simulados iguais; um parâmetro de estado inicial desloca a trajetória pelo valor pedido.

## Parâmetros que o utilizador pode mudar e repetir

| Grupo | Parâmetro | Efeito |
| --- | --- | --- |
| Controller tuning | ponto de ignição, ganho do acelerador, altitude de corte, ganho de posição lateral, inclinação máxima, limiar de rejeição do altímetro | ganhos do controlador (já existentes, agora com pistas) |
| Initial conditions | altitude, desvio para leste e para norte, velocidade vertical e horizontal iniciais | estado inicial nominal antes da dispersão da semente (caso v2) |
| Sensors | ruído do altímetro e da posição GNSS | desvio padrão do ruído (caso v2) |
| Requirements | raio da zona de aterragem (R5), velocidade vertical máxima no contacto (R1) | só o julgamento (caso v2) |

Também mudam: controlador (quatro políticas), semente, falhas injetadas (até duas, nos intervalos do catálogo) e veículo.

## Veículos

| Veículo | Massa total | Impulso sobre peso | Estado | Ensaio nas sementes 5000 a 5011 |
| --- | --- | --- | --- | --- |
| Estágio de 22 t (M9) | 30 t | 2,87 | pré-registado | baseline 11/12, robust 10/12 |
| Estágio pesado de retorno | 41 t | 1,89, acelerador mínimo 55 % | exploratório | baseline 2/12, robust 2/12; com ganho lateral 0,06, robust 8/12; com inclinação máxima 0,12, robust 7/12 |
| Demonstrador leve | 7,7 t | 3,05, acelerador mínimo 30 % | exploratório | baseline 12/12, robust 12/12 |

Os valores são ilustrativos, da ordem de um primeiro estágio reutilizável perto da aterragem e de um veículo de ensaio suborbital. Não são veículos reais. O controlador recebe o veículo nominal do caso (massa, centro de massa, impulso, Isp, limites), mas os ganhos são os afinados para o estágio de 22 t; é por isso que o estágio pesado falha R2 na maior parte das sementes. Os atributos visuais (o andar de 42 m desenhado na vista técnica) não mudam com o veículo e não entram na simulação.

O ensaio da tabela foi corrido com `vv-rocket land` em casos gerados por um script de trabalho; o veículo pesado com a inclinação reduzida mostra que uma melhoria aparente numa semente não se generaliza a todas.

## Missão "Soft, but off the pad"

A pergunta do responsável era: o foguetão toca o solo devagar mas falha o centro da plataforma; o que posso mudar? A demonstração `soft-but-off-pad` responde com uma simulação real: controlador robust, ganho de posição lateral 0,04, semente 5000, sem falhas. Toca a 1,65 m/s (R1 exige no máximo 3 m/s) a 19,2 m do centro (R5 exige no máximo 10 m); só R5 falha e a corrida é segura (`tests/demos.rs`).

No Lab, o ganho lateral aparece destacado. Com 0,12 a corrida nova aterra a 2,9 m do centro. Nas sementes 5000 a 5007 as condições de base cumprem tudo em 0 de 8 corridas e as novas em 7 de 8 (intervalos de Wilson 0 a 32 % e 53 a 98 %).

## Pacotes de ambiente

`Settings > Environments > Install a package…` instala um ficheiro `.vvenv.zip` (formato de `scripts/geo/package_environment.py`). O Studio verifica o SHA-256 contra o ficheiro `.sha256` ao lado, quando existe; recusa entradas que não sejam nomes simples na raiz; limita o tamanho descomprimido a 2 GiB e compara-o com o espaço livre mais 1 GiB de reserva; extrai para uma pasta temporária e deixa o `vv-geo` validar cada ficheiro contra o hash do manifesto antes de o pacote aparecer. Uma instalação recusada ou interrompida não deixa nada. Testes: instalação válida e recusa de uma segunda cópia; recusa de hash errado, de caminho com `..`, de ficheiro não declarado e de um byte alterado. A instalação parte sempre de um ficheiro local; o Studio continua sem pedidos de rede.

## Correções da vista técnica (no ramo do M16)

- Atribuição: o controlo de fontes é uma linha só, com o botão "Sources", o aviso "Terrain is context only" e o único crédito que tem de ficar à vista do mapa, "© OpenStreetMap contributors" (ODbL). Os avisos do Copernicus DEM (artigo 6), do Sentinel e das fontes CC BY ficam no painel, nas Definições, no NOTICE instalado e nos pacotes de evidência; as fontes de domínio público não exigem crédito.
- O cartão de telemetria para acima da barra de câmaras e desliza se não couber; o rótulo de fase quebra a linha antes do cartão; o cabeçalho do leitor passa a duas linhas abaixo de 1280 px.
- A câmara "From the ground" enquadra o horizonte enquanto o andar está baixo.
- Ao sair da vista geoespacial são libertados o mapa de sombras de 4096 e todas as texturas dos materiais (o M16.2 deixava cerca de 65 MB de memória gráfica).

## Verificação executada

- `crates/vv-rocket`: `cargo fmt --check`, `cargo clippy --all-targets --release -- -D warnings`, `cargo test --release` (93 testes, incluindo os pinos de traço do M9 e os 3 novos do v2).
- `desktop`: `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test` (88 testes).
- Raiz: `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test` (138 testes) e `python -m unittest discover -s tests -p "test_*.py"` (OK, 3 ignorados).
- Janela real WebView2: `desktop/studio/tests/m17_lab_journeys.py`, 33 de 33 verificações no ramo de integração (inclui a missão de ascensão do fluxo C). São verificações por script do que o ecrã mostra, não observações de pessoas.

## Limitações

- As margens são lidas do texto `expected` e `observed` do registo; quando o texto não é uma comparação simples (requisitos da ascensão), o Lab mostra "–" em vez de inventar uma margem.
- Sem vento: o modelo não tem perturbações atmosféricas e o Lab não as oferece.
- Os ganhos não se adaptam ao veículo; um veículo novo com os ganhos antigos é uma pergunta legítima, não um defeito escondido.
- A varredura e a verificação em sementes correm no máximo 8 simulações em paralelo (limite da plataforma) e guardam todas as corridas na biblioteca.

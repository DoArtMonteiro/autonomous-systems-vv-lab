# M15: experiência de missão, biblioteca de simulações e produto

Estado: implementado no ramo `feat/m15-mission-experience`, proposto por PR, ainda não integrado em `main`. Os resultados científicos apresentados continuam **exploratórios**.

## O que mudou para quem abre o Studio

O Studio abria no Discovery Lab, com terminologia de investigação antes de mostrar qualquer simulação. O M15 inverte a ordem:

1. **Início.** Uma frase diz o que a plataforma faz, um botão inicia a primeira aterragem e uma lista numerada mostra as cinco missões da montra. Três entradas explicam os três níveis de uso: ver (Explorer), experimentar (Analyst) e desafiar (Researcher).
2. **Biblioteca de missões.** Dez missões curadas, sobre os dois domínios, com objetivo, o que se vai ver, nível, número de execuções, grau da evidência e indicação de uma alegação por trás. Filtros por categoria e por domínio.
3. **Leitor de missão.** Corre os pedidos da missão no anfitrião do domínio e reproduz os registos: vista 3D do estado verdadeiro, leituras com origem identificada, faixa de fases, marcadores de eventos, instante em que as execuções se separam, resultado por execução, explicação e ligações para Analisar, Comparar, Configurar e a alegação em Investigar.

A navegação agrupa os espaços em dois blocos: Início, Missões e Investigar; depois Configurar, Analisar, Comparar e Registos. Os identificadores internos das vistas não mudaram.

## Decisões técnicas

- **A missão é uma demonstração do domínio.** Cada missão aponta para uma `Demo` que o anfitrião publica no catálogo e que os testes do domínio verificam com execuções reais (`desktop/domain-rocket/tests/demos.rs`, `desktop/domain-ground/tests/host.rs`). O ficheiro `desktop/studio/ui/js/experiences.js` só acrescenta apresentação: título, objetivo, o que observar, categoria, etiqueta de cada execução, alegação e grau. Se o anfitrião não publicar a demonstração, ou o número de execuções não coincidir, a missão aparece indisponível com o motivo.
- **O motor é a fonte da verdade.** O leitor lê `record.json`. As fases derivam do canal `engine_state` (ou `fallback` no veículo terrestre) e o instante de separação compara as posições verdadeiras amostra a amostra, com tolerância de 1 m (foguetão) ou 0,5 mm (terrestre). Os dois são rotulados como derivados no ecrã.
- **Origem de cada valor.** Cada leitura tem uma letra: T estado verdadeiro, E estimativa do controlador, O observação do sensor, D derivado. Depois do contacto, as velocidades e a distância à plataforma são as do verificador no instante de contacto e não a última amostra de 0,1 s.
- **Interpolação só para mostrar.** A posição e a atitude do estágio são interpoladas entre amostras de 0,1 s para a animação. O corpo do estágio é ilustrativo: o modelo não tem comprimento. O disco do solo e os anéis de distância são cenário de escala. O ecrã diz isto por baixo da vista.
- **Resultado e segurança separados.** O cartão de resultado conta requisitos da missão falhados e regras de segurança violadas em separado. O rótulo do anfitrião `hard_landing` passou de «Hard landing» para «Touched down, requirements not met», porque também cobre aterragens suaves fora da plataforma (só R5). O código do resultado não mudou.
- **Desafiar a alegação.** O cartão só oferece «Challenge this claim» quando o motor de investigação aceita a alegação instalada. Mostra o veredicto mais recente na biblioteca com o estado da recomputação, pelas mesmas regras do Discovery Lab: um pacote cuja recomputação falhou aparece como retirado. Uma missão sem alegação diz isso e aponta para as que a têm.
- **Sem pilha gráfica nova.** A vista 3D estende a classe `Rocket3D` existente (three.js r170, já incluído). Não há dependências novas.

## Missões curadas

Todas usam sementes de desenvolvimento (5000 a 5099). Os números vêm das execuções verificadas nos testes do domínio.

| Missão | Domínio | O que mostra | Grau |
| --- | --- | --- | --- |
| Land a rocket | foguetão | aterragem nominal, todos os requisitos e invariantes cumpridos | demonstração |
| A sensor that lies | foguetão | altímetro 50 m acima: `baseline` chega ao solo a cerca de 33 m/s (R1 e R2 falham), `robust` rejeita o altímetro aos 0,1 s e aterra | demonstração |
| Smaller, later, worse? | foguetão | condição registada do G3 (15 m desde 0 s): rejeição aos 0,1 s, contacto suave a cerca de 14 m da plataforma (só R5 falha); 9,72 m a partir de 0,02 s: sem rejeição, contacto a cerca de 17 m/s (só R1 falha) | exploratório |
| A fix with a price | foguetão | semente 5017, viés tardio: limiar 3 m dá subida com motor ligado (S5) e cerca de 24 m/s; limiar 1 m rejeita aos 0,18 s e aterra suave a cerca de 13 m (só R5) | exploratório |
| One millimetre | terrestre | corredor junto à zona interdita: GPS exato completa; 1 mm de ruído entra na zona no tick 21; raio de chegada de 250 mm completa | exploratório |
| Two faults at once, Riding out an outage | foguetão | demonstrações M11 com duas falhas | demonstração |
| A clean drive, Stalled but safe, A late command | terrestre | demonstrações M11 do veículo terrestre | demonstração |

As missões exploratórias ilustram, numa semente, padrões que a investigação M13 mediu em 30 sementes novas. Não são confirmações.

Para suportar estas missões, o domínio do foguetão ganhou o parâmetro `altimeter_residual_threshold_m` (0,5 a 10 m, predefinição 3 m) e o domínio terrestre ganhou a missão `zone_corridor` (cenário M2 `f-zone-nominal`) com os parâmetros `gps_noise_mm` e `arrival_radius_mm`. Um parâmetro igual à predefinição não é escrito, por isso o caso por omissão continua igual byte a byte.

## Sementes

As sementes 44000 a 44999, reservadas para uma confirmação futura, passam a ser recusadas pelos manifestos dos domínios do foguetão e terrestre, pelo Studio e por qualquer execução do `vv-exec`, e não só pelas investigações. A evidência M13 continua a reproduzir byte a byte. As sementes 50000 a 59999 continuam recusadas só nas investigações, porque `vv-exec search-verify` tem de reproduzir os registos guardados do M14. O comando de desenvolvimento `vv-rocket land` continua sem guarda própria; o protocolo candidato prevê um executor com guarda.

## Verificação

- `desktop/studio/tests/m15_journeys.py` conduz a janela real (WebView2 por CDP): Início como primeiro ecrã, um clique até uma aterragem, câmaras, resultado escondido até ao fim, variação com duas execuções, instante de separação, passagem para Analisar, Comparar e Configurar, filtro da biblioteca, missão da alegação até ao Investigar com a alegação certa, missão de mitigação, missão terrestre, teclado, ausência de deslocamento horizontal a 1024x640, 1366x768 e 1920x1080, nome acessível de todos os controlos visíveis, tema claro e ausência de erros na consola.
- `desktop/studio/tests/ui_smoke.py` (M11 a M13) continua a passar.
- Testes de domínio novos: resultados das quatro demonstrações novas, valores citados no texto, recusa de 44000 a 44999.

Estas verificações são guiões automáticos sobre o que o ecrã mostra. **Não são observações de utilizadores.** Não houve teste com pessoas.

## Desempenho

Medido fora da simulação com `desktop/studio/tests/perf_probe.py`, na máquina de desenvolvimento (processador AMD da família 25 modelo 97, Radeon RX 7700 XT por ANGLE/Direct3D 11, Windows 11, ecrã a cerca de 165 Hz), três execuções por versão, janela de 1440x900. A versão 0.11 é a instalada antes do M15.

| Medida (média de 3) | 0.11 instalada | 0.15 instalada |
| --- | --- | --- |
| Arranque até à plataforma pronta | 2,00 s (1,19 a 3,28) | 0,99 s (0,95 a 1,06) |
| Cliques desde o ecrã pronto até uma aterragem | 3 (Prepare, domínio, demonstração) | 1 (Início) |
| Clique até à aterragem no ecrã, incluindo a simulação | 0,79 s | 0,24 s |
| Intervalo entre fotogramas durante a reprodução, mediana | 6,1 ms | 7,7 ms |
| Idem, percentil 95 / 99 | 12,1 / 18,3 ms | 8,3 / 8,6 ms |
| Fotogramas acima de 33 ms em 5 s | 0 | 0 |
| Memória durante a reprodução (conjunto de trabalho / privada) | 528 / 382 MB | 453 / 318 MB |

A mediana do intervalo entre fotogramas subiu porque a vista 3D do leitor ocupa quase todo o ecrã (cerca de 127 fotogramas por segundo contra os 165 do ecrã); a cauda melhorou. As duas versões foram medidas instaladas; a 0.15 também foi medida a partir da pasta de compilação, com valores iguais dentro da variação. Os ficheiros estão em `docs/evidence/m15/`.

O arranque e a memória são do processo `vv-studio` e de todos os processos WebView2 descendentes. O tempo «até à aterragem no ecrã» é o tempo da máquina; não inclui o tempo que uma pessoa leva a encontrar o caminho, que na 0.11 começava no Discovery Lab sem nenhuma aterragem visível.

## Limitações

- Usabilidade não testada com pessoas.
- A cena terrestre é uma vista de cima em 2D; só o foguetão tem 3D.
- Sem WebGL, a vista 3D mostra uma mensagem; as leituras, a faixa temporal e o resultado continuam completos.
- Os textos de `experiences.js` citam números das demonstrações (por exemplo 0,1 s e tick 21). Os testes do domínio verificam esses valores no anfitrião; o texto da interface não é gerado a partir do registo.
- A barra lateral de Configurar continua a listar as demonstrações com os títulos do domínio.

## Expansão de domínios

Um domínio novo só entra com pressupostos de modelo explícitos, correção numérica verificada contra uma referência, requisitos com sentido e reprodução determinística. Ordem recomendada, pelo valor para a generalidade da plataforma:

1. **Multicóptero em 3D com fusão de sensores.** Reutiliza o integrador de corpo rígido do foguetão, acrescenta um problema de estimação diferente (IMU, barómetro, GNSS, magnetómetro) e requisitos de corredor e geocerca. Mostra que a plataforma cobre controlo contínuo com várias falhas de sensores.
2. **Robô móvel com obstáculos.** Exige um modelo de perceção com falsos negativos e um planeador; testa invariantes de distância mínima. É o domínio onde a procura de contraexemplos mais se aproxima da prática industrial.
3. **Encontro orbital (rendezvous) em Clohessy-Wiltshire.** Dinâmica linear com solução analítica, boa referência numérica; requisitos de cone de aproximação e velocidade de contacto.

Fora de âmbito por agora: simulações visuais sem modelo verificável e domínios com hardware real.

## Estado da via científica

O protocolo candidato `docs/m15-g3-onset-protocol.md` corrige o rascunho do M14 (contas das sementes, hipóteses preditivas e a posteriori separadas, perfil por requisito, intervenção que isola a regra 1, testes exatos com controlo por família, orçamento de regressão das duas mitigações). Nada correu nas sementes 44000 a 44999. Foi revisto só por agentes, o que não é revisão humana por pares. A decisão pendente do responsável é uma: aprovar ou rejeitar o candidato tal como está.

# Tarefas

Estas tarefas são iguais na Fase 1 e na Fase 2. Os critérios de sucesso descrevem **o que a pessoa diz, mostra ou alcança**, nunca que botão carrega: assim comparam-se versões com rótulos diferentes. A rota na 0.18.1 é uma nota do moderador e não se lê ao participante.

Os rótulos da interface aparecem exatamente como na versão inglesa (por exemplo «Run mission», «To goal»). O texto lido ao participante evita o vocabulário da interface. O apêndice no fim diz de onde vem cada rótulo e quais não foram confirmados no código.

## Convenções

- **Cartão:** texto lido ao participante, palavra a palavra (`moderator-script.md`).
- **Estado inicial:** o que o ecrã mostra quando se lê o cartão. A reposição entre tarefas é uma instrução ao participante, registada (ver guião).
- **Tempo previsto e limite:** o limite é rígido. Depois dele a tarefa termina e fica "F" ou o nível alcançado.
- **Níveis de conclusão (S, A, F, X), escada de ajuda L0 a L3 e classes de erro:** definidos em `severity-and-measures.md`.
- **Erro crítico (CE):** ação ou conclusão que, se mantida, leva a uma decisão errada sobre segurança, evidência ou o que o programa mostrou. Cada um conta no total de interpretações erradas críticas, quando for de segurança ou de evidência (classes MS e ME).
- **Verificação de compreensão:** perguntas fixas, feitas depois de a pessoa dizer que acabou, **antes** de qualquer comentário do moderador. Cada resposta recebe C (correta), P (parcial) ou I (incorreta). O moderador nunca diz se está certo.
- **Confiança (†):** cada pergunta marcada com † (segurança ou evidência) tem a sua própria confiança, pedida logo a seguir à resposta, de 1 (nada certo/a) a 5 (totalmente certo/a), antes de qualquer reação do moderador. Não se junta uma confiança para duas perguntas.
- **Perguntas sem rótulos por ver.** As perguntas de compreensão e os cartões não citam rótulos que a pessoa ainda não tenha visto no ecrã; são abertas ("o que concluiria…").
- **Chave de respostas a preencher no ensaio:** valores lidos no ecrã instalado, que não estão confirmados antes do ensaio. Fica em branco até ao ensaio e congela-se antes da Fase 1.
- **Previsões sem tarefa.** H20 (teclas) e H24 (paisagem de fundo) não estão ligadas a nenhuma tarefa: só se registam se ocorrerem, e relatam-se como "não testadas por desenho" se não ocorrerem.
- **Ambiente de sessão.** Máquina Windows separada, conta local dedicada, Studio 0.18.1 instalado a partir do instalador verificado por hash, módulo Cinematic não instalado (`README.md`). A Cinematic View está fora do estudo.

## Ordem, tempos e regra de corte

O relógio da tarefa corre desde o fim da leitura do cartão até a pessoa dizer "terminei" (ou até ao limite). **As perguntas de compreensão, a confiança, a nota de dificuldade e a reposição do ecrã não contam para o limite, mas contam para o plano de 60 minutos**: o "total previsto" abaixo inclui-as.

| Tarefa | Passo do circuito | Ação prevista | Limite da ação | Perguntas, confiança, nota e reposição (previsto) | Total previsto | Grupo |
| --- | --- | --- | --- | --- | --- | --- |
| T1 | escolher e executar | 2 | 3 | 1 | 3 | A |
| T2 | perceber o resultado e a causa (interpretação de segurança) | 3,5 | 5 | 2,5 | 6 | A |
| T3 | comparar duas execuções | 2 | 3 | 2 | 4 | B |
| T4 | crença contra verdade | 3,5 | 5 | 2,5 | 6 | B |
| T5 | missão terrestre, segundo domínio (interpretação do resultado) | 2,5 | 4 | 2,5 | 5 | B |
| T6 | desafiar uma alegação (a espera por um desafio novo não conta) | 3,5 | 5 | 2,5 | 6 | A |
| T7 | testar uma mitigação | 3 | 5 | 2 | 5 | B |
| T8 | verificar a evidência (interpretação de evidência) | 2 | 4 | 2 | 4 | A |

No plano de 60 minutos (`moderator-script.md`), as tarefas ocupam do minuto 10 ao minuto 49, com total previsto de **39 minutos** (ação 22, perguntas e reposição 17). Se todas as ações chegassem ao limite (34 minutos de ação), o conjunto passaria bastante do minuto 53: é para isso que existe a regra de corte. Grupo A: nunca se corta. Grupo B: cortável.

**Regra de corte (fixada antes da Fase 1 e igual na Fase 2).** As tarefas fazem-se sempre na ordem T1 a T8. Ao começar cada tarefa, o anotador calcula o **fim projetado**: hora atual da sessão mais a soma dos totais previstos das tarefas ainda por fazer (a atual incluída). Se o fim projetado passar do **minuto 53**, aplica-se por esta ordem, recalculando depois de cada passo, até caber:

1. **Passo 1: segmentos opcionais.** Saltam-se todos os segmentos marcados "(opcional)" nas tarefas: a segunda parte de T4 (momento em que o outro veículo deixa de confiar no sensor) e a pergunta hipotética de T6 (Q6b). Poupam-se cerca de 2 minutos no total.
2. **Passo 2: tarefas inteiras do grupo B, pela ordem T5, T3, T7, T4**, a primeira que ainda não tenha sido feita. T5 sai primeiro porque é a única tarefa fora do circuito central (segundo domínio); a sua perda deixa PI5 («To goal» contra «Mission incomplete») por avaliar nesse participante. As tarefas de núcleo T3, T4, T6 e T7 só se cortam depois de T5, e T6 nunca.

As tarefas do grupo A (T1, T2, T6, T8) nunca se cortam, porque cobrem a entrada, a interpretação de segurança, o desafio da alegação e a interpretação de evidência. Uma tarefa cortada fica "X" (não alcançada), nunca "F". Uma tarefa alcançada por menos de 2 de 3 participantes (Fase 1) ou menos de 4 de 5 (Fase 2) é relatada como "não avaliada". Se T5 for cortada em 2 ou mais participantes, o responsável decide, por escrito, se acrescenta uma sessão. O minuto 53 é o limite que deixa 11 minutos para SUS, conversa final e esclarecimentos: a sessão acaba, no máximo, ao minuto 64, dentro da paragem rígida dos 70 minutos (`README.md`).

**Ensaio e orçamento.** O ensaio mede o tempo real das ações e das perguntas e confirma ou corrige esta tabela, antes da Fase 1. Se a soma dos totais medidos não couber nos 39 minutos, o responsável decide, **antes da Fase 1 e para as duas fases**, entre prolongar a sessão e retirar uma tarefa nomeada do estudo para todos. Não se corta tarefa participante a participante fora da regra acima.

## T1. Escolher e executar uma missão

- **Passo do circuito:** escolher uma missão e executá-la.
- **Cartão.** "Imagine que quer ver, num simulador, um foguetão a tentar aterrar sozinho. Escolha um exemplo que lhe pareça simples, deixe-o correr e diga-me, nas suas palavras, o que aconteceu no fim."
- **Estado inicial.** Mission Control (Home), sem missão aberta, filtros de Missions em «All» e «Both domains», leitor em «Engineering».
- **Critérios de sucesso (todos).**
  1. Arranca um exemplo de aterragem de foguetão (qualquer um do domínio «Rocket landing»); registar qual.
  2. A reprodução chega ao fim, ou a pessoa abre o resultado, e o cartão «Result» fica visível.
  3. A pessoa diz, nas suas palavras, se a aterragem correu bem e o que mostra o cartão.
- **Rota na 0.18.1 (nota).** Mission Control, botão «Land a rocket» (ou «Run mission» em Missions); a reprodução arranca sozinha; o resultado surge no fim, ou com «Skip to the result» ou «Show the result now».
- **Erros críticos.** CE-T1-1: diz que a aterragem correu bem (ou mal) em contradição com o cartão «Result» que está no ecrã.
- **Verificação de compreensão.**
  - Q1a. "Em poucas palavras, o que aconteceu? Foi um sucesso?" Chave: consistente com o cartão «Result» do exemplo escolhido (para «Land a rocket»: «Landed», todos os requisitos cumpridos). C se concorda; P se diz só uma parte; I se contradiz.
  - Q1b. Confiança 1 a 5.
- **Se escolher uma missão de subida** («Two stages to orbit»): registar a escolha e o tempo de arranque; não é erro.
- **Previsões ligadas.** H05, H17, H19, H23.

## T2. Perceber o resultado e a causa: veículo seguro?

- **Passo do circuito:** perceber o resultado e porquê.
- **Cartão.** "Uma equipa de engenharia quer perceber como dois veículos autónomos se comportam quando o mesmo sensor de altura tem um defeito. Encontre o exemplo que mostra isto, veja os dois veículos até ao fim e explique-me o que aconteceu a cada um e porquê."
- **Estado inicial.** Mission Control (Home), sem missão aberta.
- **Critérios de sucesso (todos).**
  1. Abre o exemplo com duas execuções do altímetro com defeito (missão «A sensor that lies») e deixa chegar ao resultado das duas.
  2. Atribui bem: o veículo que confia no sensor aterra mal (cerca de 33 m/s, requisitos de velocidade falhados); o que o verifica aterra bem. A atribuição pelas etiquetas «Baseline: trusts the altimeter» e «Robust: cross-checks it».
  3. Diz a causa: o sensor de altura indica cerca de 50 m a mais, e só um dos veículos desconfia dele.
- **Rota na 0.18.1 (nota).** Missions, cartão «A sensor that lies», «Run mission»; resultado no fim da reprodução, com as duas execuções no cartão «Result»; cartão «Why it happened».
- **Erros críticos.**
  - CE-T2-1 (classe MS): conclui que o veículo que aterrou mal "foi seguro", "não teve problema de segurança" ou equivalente, por causa de «No safety rule broken».
  - CE-T2-2: troca os veículos na atribuição.
  - CE-T2-3: afirma ter ficado bem uma aterragem sem ter olhado para o resultado (julga só pela cena).
- **Verificação de compreensão.**
  - Q2a†. "O que concluiria sobre o veículo que confiou no sensor?" (aberta; o moderador não menciona segurança). Anotar se a segurança é referida espontaneamente. Confiança logo a seguir.
  - Q2b†. "Diria que esse veículo se comportou em segurança? Sim, não, ou não consigo dizer?" Confiança logo a seguir.
  - Q2c. "Porquê? Mostre-me no ecrã onde vê isso."
  - **Pontuação** (sobre Q2a e Q2b em conjunto; registar se a segurança foi espontânea ou só em Q2b). C: responde "não" ou "não consigo dizer", e fundamenta em requisitos falhados (velocidade de contacto) ou no âmbito limitado da linha de regras de segurança. P: responde "sim" mas diz explicitamente que só se refere às regras de segurança e que os requisitos de aterragem falharam. I (e CE-T2-1): responde "sim", ou trata «No safety rule broken» como aprovação global, sem referir os requisitos falhados. Confiança 4 ou 5 numa resposta I = excesso de confiança.
- **Chave (a preencher no ensaio).** Texto lido no cartão «Result» da execução «Baseline: trusts the altimeter»: resultado «________»; chip «Mission»: «________»; chip «Safety rules»: «________»; velocidade vertical no contacto: ______ m/s (documentado: cerca de 33 m/s; limite R1: 3 m/s). Duração do arranque da missão: ______ s.
- **Previsões ligadas.** H01, H03, H04, H05, H12, H23.

## T3. Comparar duas execuções

- **Passo do circuito:** comparar duas execuções.
- **Cartão.** "O seu chefe pergunta: 'Numa frase, qual é a diferença mais importante entre os dois veículos que acabou de ver?' Responda-lhe com base no que o ecrã mostra, e mostre-me onde viu isso."
- **Estado inicial.** Os dois veículos de T2 abertos, com o resultado visível. Se não, o moderador abre-os e regista a reposição.
- **Critérios de sucesso (todos).**
  1. Diz uma diferença que o ecrã mostra nas duas execuções, numa grandeza medida (por exemplo a velocidade no contacto, ou cumprir ou não o limite), com o sentido certo e atribuída à execução certa.
  2. Mostra no ecrã o sítio onde a leu (cartão «Result», comparação detalhada ou outro).
  3. Mostra qual dos dois é o veículo que confiou no sensor (execução certa na legenda, pílula ou cor).
- **Rota na 0.18.1 (nota).** Botão «Compare in detail» no leitor (abre Compare, com «Largest change:»); ou ler o cartão «Result». As duas rotas são aceites. Registar a rota.
- **Erros críticos.** CE-T3-1: troca as execuções. CE-T3-2: compara com base apenas na cena 3D, sem ler valores.
- **Verificação de compreensão.**
  - Q3a. "Mostre-me no ecrã qual é o veículo que confiou no sensor com defeito." Observável: aponta para a execução certa. C se certo sem hesitar; P se certo depois de ler vários rótulos; I se errado.
  - Q3b. Confiança 1 a 5.
- **Chave (a preencher).** Frase «Largest change:» mostrada em Compare: «________». Execução de referência (primeira): «________».
- **Previsões ligadas.** H01, H03, H18.

## T4. Crença contra verdade

- **Passo do circuito:** encontrar o instante em que a crença e a verdade se afastam.
- **Cartão.** "Durante a queda, o computador do veículo que confiou no sensor julgava estar a uma altura diferente da altura verdadeira. Encontre o primeiro momento em que essa diferença se torna claramente visível e diga-me quanto vale nesse momento. Depois diga-me em que momento o outro veículo deixou de confiar no sensor com defeito."
- **Estado inicial.** Os dois veículos de T2 abertos, resultado visível, vista «Engineering», veículo que confia no sensor selecionado.
- **Critérios de sucesso (todos).**
  1. Identifica um sítio do ecrã que mostra a crença e a verdade ao mesmo tempo ou lado a lado. Qualquer um serve: linha tracejada da cena contra a linha contínua, linha «Altitude error» do painel de leituras, «Believed height of CoM» e «True height of CoM» da Flight console, ou gráficos de Analyse.
  2. Indica um instante t* e a diferença lida no ecrã nesse instante. O moderador confere no ecrã que, ao mover o cursor para t*, a diferença mostrada é a que a pessoa disse (leitura coerente), e que t* está na janela da chave: o intervalo em que a diferença passa de ______ m a ______ m (a fixar no ensaio, antes da Fase 1).
  3. (opcional; saltada no passo 1 da regra de corte, e então a frase final do cartão não se lê) Segunda parte: diz que o outro veículo deixa de confiar no sensor perto de 0,1 s (documentado em `desktop/domain-rocket/src/demos.rs`: «the robust controller rejects the altimeter at 0.1 s»; linha «Altimeter» com o valor «rejected»). Aceita-se 0,1 s ou 0,2 s.
- **Rota na 0.18.1 (nota).** Painel de leituras do leitor (linha «Altitude error», etiqueta D; linha «Altimeter»); vista «Flight console» (grupos Navigation e Sensors); «Analyse». O marcador «Controller detection» só aparece quando a reprodução o atinge, ou com «Show all findings now» ligado.
- **Nota de interpretação (condicional ao ensaio).** O sensor de altura indica 50 m a mais desde 0 s (documentado em `desktop/domain-rocket/src/demos.rs`). O que o veículo **julga** pode já estar errado na primeira amostra, ou só depois. O ensaio lê «Altitude error» na primeira amostra e fixa o limiar de "claramente visível" (L m). Se na primeira amostra o valor absoluto já for pelo menos L, "desde o início" é uma resposta correta (C), e esta tarefa não tem um instante de afastamento definido: usa-se T4-alt. Se for inferior a L, "desde o início o sensor está errado" descreve o sensor e não o que o veículo julga: classe MO, parcial (P).
- **Regra pré-declarada entre T4 e T4-alt (decidida no ensaio, antes da Fase 1, igual na Fase 2).** Usa-se T4 se, no ensaio, o valor absoluto de «Altitude error» na primeira amostra for inferior a L e passar por L num instante bem definido. Caso contrário, usa-se T4-alt. A escolha não se altera depois de ver participantes.
- **Erros críticos.**
  - CE-T4-1 (classe ME): responde à crença contra verdade com o instante de «Where the runs part» ou do botão «Go there».
  - CE-T4-2: lê «Altitude error» como uma avaria do programa ou do veículo (e não como a diferença entre o que o controlador julga e a verdade).
  - CE-T4-3: não distingue o que o controlador julga (E) do que o sensor mede (O).
- **Verificação de compreensão.**
  - Q4a. "Explique-me com palavras suas o que está a ler nessa linha, ou nesse gráfico." Chave: diferença entre a altura que o controlador julga (estimativa) e a altura verdadeira. C se correto; P se descreve só números; I se atribui a outra coisa (erro do programa, tempo de reação).
  - Q4b†. Confiança 1 a 5 na resposta a Q4a (a leitura da diferença entre crença e verdade é um ponto de evidência).
- **Chave (a preencher).** Tempo em que o valor absoluto de «Altitude error» passa pela primeira vez 1 m: ______ s; 5 m: ______ s; 10 m: ______ s; valor no último ponto antes do contacto: ______ m. Tempo da deteção na execução robusta: ______ s.
- **Previsões ligadas.** H11, H12.

### T4-alt. Crença contra verdade, robô terrestre (só se o ensaio o escolher)

- **Cartão.** "Um pequeno robô com rodas perde o sinal de GPS a meio do percurso. Na execução em que as falhas estão incluídas, encontre o primeiro momento em que o sítio onde o robô julga estar se afasta do sítio onde realmente está, e diga-me quanto vale a diferença nesse momento. Depois diga-me em que momento o robô entrou no seu modo de segurança."
- **Estado inicial.** Mission Control (Home); a pessoa abre a missão terrestre «A late command» (execução «With the built-in faults»). Esta missão **não** é a de T5; se T4-alt for usada, T5 continua a usar «One millimetre».
- **Critérios de sucesso (todos).**
  1. Identifica um sítio que mostra a posição julgada e a verdadeira (por exemplo os grupos Vehicle e Perception da vista «Flight console», com «East», «North», «Believed east», «Believed north», ou os gráficos de Analyse).
  2. Indica um instante t* (em ticks) e a diferença lida no ecrã, coerentes com o ecrã e dentro da janela da chave (fixada no ensaio).
  3. (opcional, como em T4) Diz que o robô entrou em modo de segurança no tick 6 (documentado em `desktop/domain-ground/src/catalog.rs`: «enters fallback at tick 6»), ou lê «Mode» com o valor «fallback».
- **Erros críticos.** CE-T4-1, CE-T4-2 e CE-T4-3, como em T4. Dizer o instante em que o robô se move em segurança (tick 7) em vez do afastamento entre crença e verdade conta como MO.
- **Verificação de compreensão.** Q4a e Q4b, como em T4.
- **Chave (a preencher).** Tick em que a diferença entre «Believed east» ou «Believed north» e «East» ou «North» passa pela primeira vez L mm: ______; valor: ______ mm. Se as leituras «Believed east» e «Believed north» não existirem na vista usada: anotar e decidir no ensaio se T4-alt é viável.
- **Previsões ligadas.** H11, H12.

## T5. Missão terrestre: chegou ou não?

- **Passo do circuito:** perceber o resultado e a causa (segundo domínio, com interpretação de um resultado misto).
- **Cartão.** "Um pequeno robô com rodas tem de chegar a um ponto de destino. Veja o que acontece quando o GPS do robô tem um pequeno erro aleatório de 1 milímetro e, quando acabar, conte-me o que concluiu." (As perguntas Q5a a Q5d, incluindo Q5c2, fazem-se depois, e só depois.)
- **Estado inicial.** Mission Control (Home), sem missão aberta.
- **Critérios de sucesso (todos).**
  1. Abre a missão terrestre com três execuções («One millimetre») e escolhe como execução mostrada a de erro de GPS de 1 mm («1 mm of GPS noise»), não a de GPS exato.
  2. Lê o fim dessa execução: a distância ao destino («To goal») e o resultado («Mission incomplete»).
  3. Responde às perguntas Q5 a seguir.
- **Rota na 0.18.1 (nota).** Missions, cartão «One millimetre», «Run mission»; botão da execução «1 mm of GPS noise» junto à cena; leitura «To goal» no painel; cartão «Result»; cartão «Why it happened»; detalhe «What the simulator reported».
- **Erros críticos.**
  - CE-T5-1 (classe MS ou MO): diz que a tarefa foi concluída com sucesso, ou que não houve problema.
  - CE-T5-2 (classe MS): não reconhece que uma regra de segurança foi quebrada (a zona proibida), quando o ecrã o mostra.
  - CE-T5-3: afirma com confiança 4 ou 5 uma causa que o ecrã não dá, ou diz que o programa tem um erro, sem hipótese que o ecrã sustente.
  - CE-T5-4: lê valores da execução errada («Exact GPS»).
- **Verificação de compreensão.**
  - Q5a. "O robô chegou ao destino?" Chave: **o valor lido no ensaio** na linha «To goal» no fim da execução de 1 mm, e não um 0.00 mm assumido (o backlog documenta 0.00 mm, a confirmar). C se a resposta for coerente com esse valor e com o ecrã (se o ensaio ler 0.00 mm: "sim, a posição verdadeira está no destino"; se ler outro valor: a leitura desse valor); I se contradisser o valor que o ecrã mostra, ou se não o ler. Se o ensaio ler um valor diferente de zero, a premissa de T5 (leituras que parecem contraditórias) não se verifica: regista-se, e o responsável decide se T5 se mantém.
  - Q5b†. "A tarefa foi concluída com êxito?" Chave: o texto do resultado lido no ensaio («Mission incomplete», documentado em Rust). C se disser que não ficou concluída. O chip «Mission» mostra também «1 not evaluated» («2 of 8 requirements failed, 1 not evaluated, 5 met», a confirmar no ensaio); referi-lo não é exigido, mas uma resposta que diga que tudo o resto foi cumprido é P. Confiança logo a seguir.
  - Q5c†. "Como explica o que vê? Há alguma coisa no ecrã que o explique?" Chave: o ecrã **não** diz diretamente porque a missão ficou incompleta com 0.00 mm. A narrativa de «Why it happened» fala em GPS com ruído, raio de chegada de 0 mm e oscilação. É correto: (a) dizer que o ecrã não explica a diferença; ou (b) dar uma explicação coerente com a narrativa (o veículo nunca lê o ponto exatamente, por isso não confirma a chegada). É incorreto: afirmar uma causa que contradiz o ecrã, ou concluir que o valor está errado sem fundamento. "O ecrã não explica" conta como resposta correta. Confiança logo a seguir.
  - Q5c2 (aberta; antes de Q5d). "Há mais alguma coisa neste resultado que lhe pareça importante, boa ou má?" O moderador não menciona segurança nem zonas. **Não tem pontuação C, P ou I, nem confiança:** só se anota, palavra a palavra, se a pessoa refere espontaneamente uma regra de segurança ou a zona proibida (sim ou não), como em Q2a. Não entra no limiar M3.
  - Q5d†. "Houve algum problema de segurança?" Chave: execução «1 mm of GPS noise»: uma regra de segurança quebrada (zona proibida: «Truth stays outside the restricted zone»; o «tick 21» documentado aparece ligado ao requisito «Restricted zone stays clear (contract)», por isso o instante da regra de segurança confirma-se no ensaio e não se exige na resposta). C se identifica o problema da zona. A pergunta faz-se depois de Q5a, Q5b, Q5c e Q5c2, mesmo que a pessoa já tenha referido a zona em Q5c2. Confiança logo a seguir.
- **Chave (a preencher).** Texto do chip de fim: «________». Linha «To goal» no fim: ______ mm. Estado do chip «Safety rules»: «________». Texto de «What the simulator reported»: «________».
- **Previsões ligadas.** H02, H03. (H17 não se liga a T5: o percurso desta tarefa não passa pelos nomes que H17 prevê inconsistentes.)

## T6. Desafiar uma alegação

- **Passo do circuito:** desafiar uma alegação.
- **Cartão.** "Um engenheiro afirma: 'Quando a navegação por satélite do foguetão tem um erro entre 5 e 30 metros, o controlador de aterragem toca no chão a menos de 3 metros por segundo, qualquer que seja o momento, nos primeiros 20 segundos, em que o erro começa.' Use este programa para descobrir se a afirmação resiste a uma tentativa a sério de a desmentir, e diga-me a sua conclusão e que confiança tem nela."
- **Estado inicial.** Mission Control (Home). A biblioteca contém **sempre** o pacote de investigação preparado e já recomputado da alegação «G3 under a late GNSS bias» (antiga variante B), igual para todos os participantes e nas duas fases. T8 usa-o sempre. Não há variantes de T6: a pessoa obtém o veredicto pela via que escolher, e a via fica registada: (i) inicia um desafio novo e espera pelo resultado; (ii) abre o pacote já guardado. A duração de um desafio novo é medida no ensaio; a espera não conta para o limite da ação (no máximo 5 minutos de pausa; se for excedida, o moderador regista-o e passa às perguntas). **Não há número mínimo de participantes na via (i):** o moderador nunca sugere nem orienta a via. Se ninguém numa fase usar a via (i), H08 fica "não testada" nessa fase. O estado inicial de T8 não depende da via de T6 (ver T8).
- **Critérios de sucesso (todos).**
  1. Chega ao espaço onde se desafiam alegações e abre a alegação sobre o erro de GNSS (título «G3 under a late GNSS bias»).
  2. Obtém um veredicto sobre a alegação: ou inicia um desafio novo e espera pelo resultado, ou abre a investigação já guardada. Registar a via.
  3. Diz o veredicto com palavras suas, coerente com o ecrã (documentado para esta alegação: «Refuted», a confirmar no ensaio): encontrou-se, dentro das condições declaradas, uma situação em que a afirmação falha.
  4. Diz pelo menos um limite: é um modelo idealizado, o grau é exploratório («Exploratory»), são sementes de desenvolvimento, não é certificação.
- **Rota na 0.18.1 (nota).** Várias entradas servem: Mission Control («Investigate a claim», «See a counterexample outside the registered conditions»), separador «Investigate», cartão «Challenge this claim» na missão «Smaller, later, worse?». No ecrã da alegação: «Challenge this claim». Registar a entrada.
- **Erros críticos.**
  - CE-T6-1 (classe ME): conclui que o foguetão real é inseguro, ou que a afirmação ficou provada, quando o ecrã não o diz.
  - CE-T6-2: não distingue o resultado do desafio de «Refuted» de uma avaria do programa.
- **Ocorrência não crítica.** E2-T6-1: cancela um desafio novo por achar que bloqueou (erro de classe E2; não é um erro crítico e não entra na contagem de CE).
- **Verificação de compreensão.**
  - Q6a†. "O que é que esta conclusão diz sobre um foguetão a sério?" Chave: pouco ou nada; resultado exploratório num modelo idealizado. C se limita o alcance; I se generaliza a veículos reais. Confiança logo a seguir.
  - Q6b† (opcional). "Imagine que o programa tinha concluído que não encontrou nenhuma situação em que a afirmação falha. O que concluiria sobre a afirmação?" Chave: não fica provada; só se procurou num número limitado de casos. C se diz que não está provada; I se diz que está provada ou confirmada. Confiança logo a seguir.
- **Chave (a preencher).** Veredicto mostrado: «________». Grau mostrado: «________». Duração de um desafio novo medida: ______ s. Via usada: [ ] desafio novo [ ] pacote guardado. Nome do cartão da alegação no painel «Claims»: «________». Nome e hora do pacote preparado: «________».
- **Previsões ligadas.** H07, H08, H09, H10, H17, H21. H08 só se testa se a pessoa iniciar um desafio novo; H09 só se testa em T6 se a pessoa abrir o pacote guardado (via ii).

## T7. Testar uma mitigação

- **Passo do circuito:** testar uma mitigação.
- **Cartão.** "Num exemplo, o estágio de um foguetão toca no chão com suavidade, mas cerca de 19 metros fora do alvo. Tente fazer com que aterre no alvo e diga-me se confia na correção que encontrou."
- **Estado inicial.** Mission Control (Home); nenhuma experiência aberta no Lab. Não se usam missões de subida no Lab.
- **Critérios de sucesso (todos).**
  1. Abre o exemplo («Soft, but off the pad») e chega ao Lab com essa execução como ponto de partida.
  2. Altera pelo menos uma condição do voo ou do controlador (não um limite de requisito) e executa uma nova simulação.
  3. Diz, a partir do ecrã, se o requisito da posição do alvo (linha «Distance from pad centre»; o limite é o parâmetro «Landing-zone radius (R5)») passou a ser cumprido na nova execução.
  4. Quanto à confiança: ou corre a verificação noutras sementes («Does it hold on other seeds?»), ou diz que uma execução não chega para confiar.
- **Rota na 0.18.1 (nota).** Botão «Open in Experiment Lab» no leitor (ou em Analyse, ou no hangar «Vehicles»); no Lab, o parâmetro «Lateral position gain» (grupo de ajuste do controlador) com a marca «Listed for this failure»; «Run experiment» (desligado com «Change one condition first» até haver uma alteração); resultado ao lado do «Baseline»; «Does it hold on other seeds?» com «8 seeds», «16 seeds» e «32 seeds».
- **Erros críticos.**
  - CE-T7-1: altera «Landing-zone radius (R5)» ou outro limite do grupo «Requirements» e declara a correção bem-sucedida (o Lab marca «(judging only)»).
  - CE-T7-2 (classe ME): lê o resultado das sementes («k/n … meet every requirement and safety rule») como probabilidade de funcionar no mundo real, ou como validação.
  - CE-T7-3: declara que a correção funciona com base numa só execução, sem reservas.
- **Verificação de compreensão.**
  - Q7a†. "Pode garantir que a correção funciona?" Chave: não; uma execução, ou uma amostra de sementes de desenvolvimento de um modelo idealizado. C se não garante e dá o motivo; I se garante. Confiança logo a seguir.
  - Q7b† (só se correu sementes). "O que significa o resultado que está a ver nas sementes?" Chave: quantas das N execuções cumprem os requisitos nessas sementes; não é fiabilidade. C se diz isso; I (e CE-T7-2) se diz probabilidade de sucesso real. Confiança logo a seguir.
- **Chave (a preencher).** Valor de «Lateral position gain» na missão inicial: ______; valor predefinido: ______; valor que cumpre o requisito R5 na semente 5000: ______; resultado das «8 seeds»: ______. Duração da verificação em 8 sementes: ______ s.
- **Previsões ligadas.** H07, H13, H14, H15, H16, H17.

## T8. Verificar a evidência

- **Passo do circuito:** verificar a evidência.
- **Cartão.** "O programa guardou uma investigação sobre a afirmação do engenheiro. Antes de mostrar a conclusão a um colega, quer ter a certeza de que pode confiar na prova que o programa guardou. Mostre-me como verificaria isso neste programa, e diga-me o que lhe dá essa confiança e o que ainda não lhe dá."
- **Estado inicial (neutro).** Mission Control (Home), sem nenhum ecrã de Investigate aberto: o cartão de evidência («Evidence integrity») **não** está à vista no arranque da tarefa. O pacote preparado existe sempre na biblioteca (ver T6), pelo que T8 é alcançável quer T6 tenha corrido, falhado ou sido cortada, e seja qual for a via usada em T6. O estado inicial e a chave de T8 são os mesmos para todos. Se T6 tiver terminado noutro ecrã, o moderador repõe Mission Control (reposição registada). Se a pessoa tiver criado um pacote novo em T6, a biblioteca passa a ter dois pacotes da mesma alegação: qualquer um serve para T8, e regista-se qual foi usado. O comportamento do produto neste caso (se o pacote novo aparece já recomputado, ou com «Recompute now») está **a confirmar no ensaio**.
- **Critérios de sucesso (todos).**
  1. Chega à investigação guardada sobre a alegação e localiza pelo menos um sítio que mostra a recomputação: peça «Evidence integrity», botão «Recompute from scratch», secção «Evidence» com as verificações; ou, para uma execução, o separador «Provenance» com «Replay». Aceita-se qualquer um.
  2. Explica com palavras suas o que esse sítio mostra.
  3. Distingue o que essa prova diz sobre a integridade da evidência do que diz sobre a afirmação do engenheiro (pergunta Q8a).
- **Rota na 0.18.1 (nota).** Mission Control, «Investigate a claim» ou separador «Investigate»; no painel «Investigations», o pacote preparado; peça «Evidence integrity» («Recomputed, every check passed», botão «Recompute now» se ainda não recomputado); «Recompute from scratch»; navegação de sete passos, passo «Evidence». Se a pessoa carregar em «Recompute from scratch», a espera não conta para o limite (pausar o relógio, no máximo 5 minutos).
- **Erros críticos.**
  - CE-T8-1 (classe ME): conclui que a recomputação bem-sucedida quer dizer que a afirmação é verdadeira, ou que o veículo é seguro.
- **Ocorrência não crítica.** F-T8-1: não chega a nenhum sítio de recomputação dentro do limite (conclusão F; não é um erro crítico e não entra na contagem de CE).
- **Verificação de compreensão** (sem citar rótulos; a pessoa aponta o sítio que mostrou).
  - Q8a†. "O que é que a parte do ecrã que acabou de me mostrar lhe diz sobre a afirmação do engenheiro?" Chave: diz que a prova guardada foi recalculada e confere (integridade); o veredicto sobre a afirmação está noutra parte e não decorre dessa recomputação. C se separa as duas coisas; I (CE-T8-1) se as junta (por exemplo "confirma que a afirmação é verdadeira"). Confiança logo a seguir.
  - Q8b†. "O que é que isto continua a não lhe permitir concluir?" Chave: a validade no mundo real, o número limitado de sementes, o modelo idealizado, o grau exploratório. C se nomeia pelo menos um limite. Confiança logo a seguir.
- **Chave (a preencher).** Texto da peça «Evidence integrity»: «________». Número de verificações listadas na secção «Evidence»: ______. Duração de «Recompute from scratch»: ______ s. Com um pacote criado em T6 na biblioteca (ensaio com a via (i)): aparece recomputado? [ ] sim [ ] não; texto da peça: «________».
- **Previsões ligadas.** H07, H09, H17.

## Momentos fora das tarefas

- **Primeira impressão** (antes de T1, 2 minutos, sem tocar em nada). Pergunta: "Olhando para este ecrã durante meio minuto, o que acha que este programa faz, e para quem é?" Anotar a resposta palavra a palavra. Classificar: (a) simulador de missões de veículos; (b) refere verificação ou desafio de alegações; (c) não sabe. Previsão: H06, H19.
- **Conversa final** (4 minutos). Ver `moderator-script.md`. Inclui a pergunta de calibração: "De 1 a 5, quanto confiaria nestes resultados para um foguetão a sério?" Previsão: H22.

## Apêndice. Origem dos rótulos citados

Fontes: **UI** = `desktop/studio/ui/js/` ou `index.html`; **Rust** = `desktop/domain-rocket/src` ou `desktop/domain-ground/src`; **log** = só nos registos de evidência de `docs/evidence/m18/installed-0.18.1/` (não confirmado no código); **runtime** = composto em tempo de execução a partir dos dados do registo.

| Rótulo | Fonte |
| --- | --- |
| Mission Control, Missions, Vehicles, Environments, Experiment, Investigate, Configure, Analyse, Compare, Runs, Settings, More | UI (`index.html`) |
| Run mission, Pick a mission, Mission library, Level, Runs, Watch time | UI (`missions.js`) |
| Land a rocket, A sensor that lies, Soft, but off the pad, One millimetre, Smaller, later, worse?, A fix with a price, Two stages to orbit | UI (`experiences.js`) |
| Baseline: trusts the altimeter, Robust: cross-checks it, Exact GPS, 1 mm of GPS noise, 1 mm noise, 250 mm arrival radius | UI (`experiences.js`) |
| Result, Show the result now, Skip to the result, Show all findings now, Where the runs part, Go there, Why it happened, What the simulator reported, Objective, Watch for, How far this goes, Compare in detail, Open in Experiment Lab, Analyse, Open Cinematic View, Engineering, Geospatial, Flight console, Challenge this claim | UI (`player.js`) |
| Mission, Safety rules (chips); Conditions: | UI (`player.js`) |
| 8 seeds, 16 seeds, 32 seeds (botões do Lab) | runtime (`lab.js`, texto composto `${n} seeds`) |
| No safety rule broken (N checked), N of M requirements failed, Every requirement and safety rule met., Not met: … impact not modelled | runtime (`requirements.js`, `player.js`); forma "(5 checked)" também em log |
| Altitude error, Altimeter, To goal, Mode, Confidence | UI (`session.js`) |
| Believed height of CoM, True height of CoM | UI (`session.js`) |
| T, E, O, D (letras de origem) | UI (`player.js`, `session.js`) |
| To goal 0.00 mm | runtime; o valor 0.00 só em log (README do instalado) |
| Mission incomplete, Mission completed, Mission stalled | Rust (`domain-ground/src/record.rs`) |
| Landed, Reached the ground, requirements not met, No contact | Rust (`domain-rocket/src/record.rs`) |
| Touched down, requirements not met | **não confirmado**: só em `docs/m15-mission-experience.md`; o código diz «Reached the ground, requirements not met» |
| Lateral position gain, Landing-zone radius (R5), Contact vertical speed limit (R1), Altimeter rejection threshold | Rust (`domain-rocket/src/catalog.rs`) |
| Truth stays outside the restricted zone | Rust (`domain-ground/src/catalog.rs`) |
| Experiment Lab, What would change this outcome?, Baseline, Conditions to change, Run experiment, Change one condition first, Does it hold on other seeds?, Watch both runs, Use as new baseline, Listed for this failure, (judging only), Requirements | UI (`lab.js`) |
| Claims, Investigations, Challenge this claim, Evidence integrity, Claim, Mechanism, Mitigation, Evidence grade, Recompute now, Recompute from scratch, Evidence, Refuted, Not refuted within budget, Recomputed, every check passed, Exploratory | UI (`discover.js`) |
| Verification, Metrics, Notes and validity, Provenance, Replay, Mission outcome | UI (`run.js`, `verification.js`) |
| Largest change:, Only rows that differ, Verdict changes between the runs, Outcome, safety rules and requirements | UI (`compare.js`) |
| G3 under a late GNSS bias | `exec/claims/m13/g3-onset.json` (título); também em log |

### Rótulos e valores não confirmados no código

1. «Touched down, requirements not met»: contradição entre documento e código; o ensaio verifica qual aparece na instalada.
2. O valor «To goal 0.00 mm» (e que o chip «Safety rules» indica regra quebrada) na execução «1 mm of GPS noise»: só confirmado por registos de evidência e pelo backlog.
3. O veredicto «Refuted» para a alegação G3 na versão instalada: confirmado pelo registo `ui-smoke.txt`, não lido no ecrã.
4. Os valores das chaves de resposta (tempos, margens, durações): ficam em branco até ao ensaio.
5. O grupo exato em que «Lateral position gain» aparece no Lab e se tem a marca «Listed for this failure» nesta missão.
6. O texto exato de «Why it happened» da missão «One millimetre»: lido da narrativa em `desktop/domain-ground/src/catalog.rs`, não no ecrã.
7. Os gráficos de Analyse mostram crença e verdade? Não confirmado no código lido (`charts.js` não foi lido).

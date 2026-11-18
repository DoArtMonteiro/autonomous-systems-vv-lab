# Previsões de falha, escritas antes de qualquer sessão

## Estatuto deste ficheiro

**Estas previsões são hipóteses. Não são resultados, não foram observadas e podem estar erradas.** Foram deduzidas apenas de duas fontes: o backlog documentado (`docs/m15-m18-acceptance.md`, secção «Pendências de experiência» e linhas M15-R05, M15-R06, M15-R17, M15-R22, M16-R13, M17-R27, M18-R17; `docs/evidence/m18/installed-0.18.1/README.md`, secção «Pendências conhecidas (backlog)»; `docs/m15-mission-experience.md`) e a leitura do código da interface em `desktop/studio/ui/js/`. Nenhuma pessoa foi observada.

Regras de integridade:

- O ficheiro congela-se antes da primeira sessão. Data de congelamento: ____________ (preencher). Produto: Studio 0.18.1, base `bec7b3f`.
- Depois do congelamento não se editam entradas. Acrescentam-se, só no fim, adendas datadas.
- No fim de cada fase, cada previsão recebe um destes estados em `analysis-template.md`: **observada**, **não observada** (nas sessões em que a tarefa foi alcançada), **tarefa não alcançada**, **inconclusiva**. "Não observada" com n = 3 ou n = 5 não refuta a previsão.
- Problemas que surjam sem previsão registam-se como **não previstos**; contam como informação, não como falha das previsões.

Origem: **B** = backlog documentado, **C** = leitura do código. Localização com ficheiro de `desktop/studio/ui/js/` e função ou elemento.

## Previsões do backlog documentado

### H01. O chip verde «No safety rule broken» lido como "o veículo é seguro" (B)

- **Localização.** `views/player.js`, `runResult()` (chip «Safety rules» ao lado do chip «Mission»); `views/compare.js` (legenda das execuções e linha «Safety rules» da matriz); `views/lab.js`, `verdictPill()`; `views/library.js` (coluna «Safety rules», «None broken»); `verification.js`, `verdictBlocks()`.
- **Sintoma esperado.** Depois de uma aterragem a cerca de 33 m/s com requisitos falhados, o participante diz que o veículo foi seguro, ou que "a segurança esteve bem", e desvaloriza os requisitos falhados.
- **Razão.** O chip tem o glifo de verificação e tom de aprovação, e o texto diz «No safety rule broken (N checked)». A nota que explica o âmbito (`SAFETY_NOTE`) está numa dica de ferramenta e numa linha pequena. O backlog diz que o chip é verdadeiro mas devia ser neutro, para não parecer um resultado global (M15-R13, M18-R22). A demonstração «A sensor that lies» tem exatamente este par: requisitos R1 e R2 falhados com segurança «safe» (`desktop/domain-rocket/src/demos.rs`).
- **Tarefas.** T2, T3. **Se observada:** interpretação errada de segurança, gravidade mínima 3.

### H02. «To goal 0.00 mm» ao lado de «Mission incomplete» (B)

- **Localização.** `session.js`, `readouts()` ramo terrestre, linha «To goal» (etiqueta D); `views/player.js`, cartão «Result» (`pl-run-head`), detalhe «What the simulator reported»; missão «One millimetre», execução «1 mm of GPS noise».
- **Sintoma esperado.** O participante conclui que o robô chegou e a missão correu bem, ou que o valor está errado ou a aplicação tem uma avaria, ou inventa com confiança uma causa que o ecrã não dá.
- **Razão.** O backlog regista que falta uma linha de explicação, porque o registo do domínio não traz a cláusula de `mission_completion` que falhou (M15 doc, «Pendente depois das revisões»; backlog do 0.18.1). O texto do anfitrião diz «1 of 1 waypoint(s) reached; 0 mm from the goal» numa missão incompleta. O cartão «Why it happened» dá a narrativa da demonstração, mas não liga os dois valores.
- **Tarefa.** T5. **Se observada:** interpretação errada do resultado; gravidade mínima 3 se levar a uma conclusão de segurança ou de sucesso errada.

### H03. Pílulas das execuções cortadas e execuções que parecem iguais (B)

- **Localização.** `views/player.js`, `build()` (`pl-runs`, `pl-run`, `pl-run-v`); `views/compare.js` (`run-key`).
- **Sintoma esperado.** O participante não consegue dizer que execução está a ver ou atribui valores à execução errada (por exemplo lê «To goal» da execução «Exact GPS» e conclui sobre «1 mm of GPS noise»).
- **Razão.** O backlog diz que, a 1024x640, as pílulas não selecionadas ficam com o identificador curto e cortam a etiqueta e as condições com reticências. M18-R30 e M15-R13 registam que o par de aterragem ainda parece idêntico. A condição depende do tamanho da janela da máquina do estudo, que o ensaio regista.
- **Tarefas.** T2, T3, T5.

### H04. A cena não mostra o falhanço do contacto (B)

- **Localização.** `views/player.js`, `onTime()` e a vista «Engineering»; chip de fim de corrida (`endChip` em `requirements.js`).
- **Sintoma esperado.** O participante vê o estágio direito, com a pluma ainda desenhada, e diz que aterrou bem, apesar de o resultado indicar «Reached the ground, requirements not met».
- **Razão.** `docs/m15-mission-experience.md` diz que a cena não muda num contacto falhado (o modelo não tem dinâmica de contacto) e o backlog regista que a pluma continua desenhada depois do contacto. A única pista é o texto do chip, com «impact not modelled».
- **Tarefa.** T2. Fora do âmbito: o painel da Cinematic View.

### H05. Os níveis «Explorer» e «Analyst» não orientam (B)

- **Localização.** `views/missions.js`, `card()`, campo «Level»; `experiences.js` (`level`).
- **Sintoma esperado.** Novatos não sabem o que «Explorer» ou «Analyst» implicam, ignoram o campo, ou evitam as missões «Analyst» por se acharem sem qualificação. Engenheiros ignoram o campo.
- **Razão.** M15-R05 está PARTIAL: só existem etiquetas de nível e agrupamento; a página inicial já não explica os níveis.
- **Tarefa.** T1, T2.

### H06. Sem integração por interação, o propósito do produto não é percebido (B, C)

- **Localização.** `views/home.js`, parágrafo `hm-lead` («A deterministic simulator of autonomous vehicles… recompute»), três percursos `hm-path`.
- **Sintoma esperado.** Na primeira impressão, novatos não conseguem dizer o que a aplicação faz; termos como «deterministic», «engineering telemetry» e «recompute» não são percebidos. Engenheiros percebem o domínio, mas não sabem por onde começar.
- **Razão.** M15-R06 está PARTIAL: sem tutorial, e a compreensão nunca foi medida com pessoas. O texto inicial é denso e usa vocabulário técnico.
- **Momento.** Primeira impressão (antes de T1).

### H07. A cadeia da missão à evidência não é percorrida de ponta a ponta (B)

- **Localização.** Ligações entre `views/player.js` (cartão «Challenge this claim»), `views/discover.js` (rail «Claims» e «Investigations», navegação de sete secções) e `views/lab.js`.
- **Sintoma esperado.** Depois do veredicto, o participante não sabe voltar às execuções de um contraexemplo, nem como ir de uma mitigação testada no Lab para uma verificação. Perde-se na página longa de Investigate.
- **Razão.** M15-R17, M16-R13, M17-R27 e M18-R17 registam que nenhuma jornada atravessa contraexemplo, mitigação e evidência, e que o passo Investigate e evidência não está na jornada de ponta a ponta.
- **Tarefas.** T6, T7, T8.

### H08. A espera da investigação é opaca (B, C)

- **Localização.** `views/discover.js`, `renderProgress()` e a lista `STAGES` («Replication, attribution, envelope and mechanism», «Regression families», «Recomputation»).
- **Sintoma esperado.** O participante acha que a aplicação bloqueou, cancela o desafio, ou não percebe o que cada fase faz.
- **Razão.** Os nomes das fases são técnicos e a duração de um desafio não está documentada. **Condicionada a que a pessoa inicie um desafio novo em T6** (o pacote preparado está sempre na biblioteca; a pessoa pode abri-lo em vez de desafiar); se ninguém iniciar um desafio novo, esta previsão não se testa. A duração do desafio é medida no ensaio.
- **Tarefa.** T6.

### H09. Integridade da evidência (verde) lida como verdade da alegação (B, C)

- **Localização.** `views/discover.js`, `acceptance()`: peças «Evidence integrity» («Recomputed, every check passed») e «Claim» («Refuted»).
- **Sintoma esperado.** O participante lê o verde de «Recomputed» como "a alegação está confirmada" ou "o veículo está validado", ou usa-o para desvalorizar o veredicto «Refuted».
- **Razão.** Cinco peças separadas («Evidence integrity», «Claim», «Mechanism», «Mitigation», «Evidence grade») aparecem lado a lado, cada uma com o seu tom de cor; o verde de uma pode ser lido como aprovação das outras. M15-R17 diz que a cadeia Observação para Verificação não foi percorrida com pessoas. A palavra «Recompute» aparece em dois sítios («Recompute now», «Recompute from scratch») e a análise de uma execução usa «Replay».
- **Tarefa.** T8. **Se observada:** interpretação errada de evidência, gravidade mínima 3.

### H10. «Refuted» lido como prova sobre um veículo real; o grau «Exploratory» ignorado (B, C)

- **Localização.** `views/discover.js`, `WORDS` («Refuted»), peça «Evidence grade»; `views/player.js`, cartão «How far this goes».
- **Sintoma esperado.** O participante diz que se provou que o foguetão é inseguro, ou que "nada foi provado" mas com a justificação errada; não lê o grau «Exploratory» nem «Simulation, development seeds. Not a confirmation, not a certification.».
- **Razão.** O limite está em texto pequeno, abaixo da dobra no leitor; a declaração «Exploratory models, not real vehicles» está só em Mission Control e no hangar (acceptance, M15-R03 e M18-R11).
- **Tarefa.** T6.

## Previsões deduzidas do código

### H11. Crença contra verdade confundida com «Where the runs part» (C)

- **Localização.** `session.js`, `divergence()`; `views/player.js`, `changeSummary()` («Where the runs part», botão «Go there») e marcador «runs part»; `views/control.js` (`diverge`, «Runs part»).
- **Sintoma esperado.** Pedido para encontrar o instante em que a crença e a verdade se afastam, o participante responde com o instante de «Where the runs part». Ou lê «Altitude error» como uma avaria do software, ou não distingue as letras T, E, O, D.
- **Razão.** «Where the runs part» compara as posições verdadeiras de duas execuções; não compara crença com verdade. É a única ação "ir ao instante" em destaque no cartão de resultado. A crença e a verdade só aparecem na linha «Altitude error» (D), na linha tracejada amarela da cena, em «Believed height of CoM» e «True height of CoM» da Flight console e, presumivelmente, nos gráficos de telemetria de Analyse (não confirmado no código lido). As letras T, E, O, D só têm dica no `abbr` e uma legenda pequena.
- **Tarefa.** T4. **Se observada:** interpretação errada de evidência, gravidade mínima 3.

### H12. Resultado retido até ao fim e três controlos parecidos (C)

- **Localização.** `views/player.js`: «Show the result now» (cartão «Result»), «Skip to the result» (transporte), «Show all findings now» (`analysisToggle()`); `gateMarks()`.
- **Sintoma esperado.** O participante espera, em silêncio, que a reprodução acabe; não sabe qual dos três controlos usar; ao recuar na linha temporal não encontra marcadores de eventos que ainda "não foram atingidos".
- **Razão.** O resultado e os marcadores de achados só aparecem quando a reprodução os atinge, ou com o modo de análise ligado. Os rótulos parecem sinónimos mas não são.
- **Tarefas.** T2, T4.

### H13. «Change the conditions» não corresponde a nenhum controlo (C)

- **Localização.** `experiences.js`, missão `off-the-pad` (campo `watch`: «Choose “Change the conditions” to try another gain in the Experiment Lab.»); o controlo real é «Open in Experiment Lab» em `views/player.js`.
- **Sintoma esperado.** O participante procura um botão com o texto «Change the conditions», não o encontra, e demora ou falha a chegar ao Lab.
- **Razão.** Pesquisa no código: como texto de botão, «Change the conditions» não existe. Só aparece nesse texto da missão e, em minúsculas, no início da dica do botão de Analyse («Change the conditions of this run…»). O controlo do leitor chama-se «Open in Experiment Lab».
- **Tarefa.** T7.

### H14. Relaxar o requisito em vez de melhorar o voo (C)

- **Localização.** `views/lab.js`, grupo «Requirements» (parâmetros «Landing-zone radius (R5)» e «Contact vertical speed limit (R1)» em `desktop/domain-rocket/src/catalog.rs`).
- **Sintoma esperado.** O participante alarga o raio da zona de aterragem e declara a correção bem-sucedida.
- **Razão.** Os campos estão no mesmo formulário que os parâmetros de voo. O Lab avisa «These change only how a run is judged» e marca «(judging only)», mas só depois de agir.
- **Tarefa.** T7. **Se observada:** erro crítico CE-T7-1.

### H15. O resultado de «Does it hold on other seeds?» lido como fiabilidade (C)

- **Localização.** `views/lab.js`, `renderGeneralisation()` («k/n … meet every requirement and safety rule (95 % interval …)», «It is not a reliability figure…»).
- **Sintoma esperado.** O participante lê «28/32» como "28 de 32 vezes vai funcionar no mundo real", ou como validação da correção.
- **Razão.** O aviso («An estimate on N development seeds of this idealised model. It is not a reliability figure…») está em texto pequeno e esbatido. Um intervalo de 95 % tende a ser lido como garantia.
- **Tarefa.** T7. **Se observada:** interpretação errada de evidência, gravidade mínima 3.

### H16. O formulário de condições do Lab é longo (C)

- **Localização.** `views/lab.js`, `renderEdit()`: grupos recolhidos (`details`), exceto os que têm parâmetros marcados «Listed for this failure» ou alterados.
- **Sintoma esperado.** O participante não encontra «Lateral position gain» entre os parâmetros, hesita entre grupos (a ordem declarada no código inclui «Vehicle design», «Vehicle», «Mission», «Controller tuning», «Pitch programme», «Initial conditions», «Sensors» e «Requirements»; os que existem dependem do cenário), e demora.
- **Razão.** O rótulo «Listed for this failure» só aparece se o requisito falhado estiver em foco; os restantes grupos aparecem fechados.
- **Tarefa.** T7.

### H17. Vocabulário de navegação inconsistente (C)

- **Localização.** `index.html` (separadores: «Mission Control», «Missions», «Vehicles», «Environments», «Experiment», «Investigate», «Configure», «Analyse», «Compare», «Runs», «Settings»); `views/home.js` («Open the hangar», «Hangar», «Investigate a claim», «Challenge a safety claim»); `views/run.js` («Open Records»); `ui.js` (ajuda: «Records»); `views/lab.js` («Experiment Lab»).
- **Sintoma esperado.** O participante procura «Records» ou «hangar» no menu e não os encontra; confunde «Experiment» com «Experiment Lab» e «Investigate» com «Challenge a claim».
- **Razão.** O mesmo espaço tem nomes diferentes em separador, título e ligações (M18-R24 regista sinónimos).
- **Tarefas.** T1, T6, T7, T8.

### H18. O menu «More» esconde Compare, Analyse, Configure e Runs (C)

- **Localização.** `main.js` (menu «More»), `index.html` (`nav-more-menu`); comentário do código: abaixo de 1100 px.
- **Sintoma esperado.** Se a janela da máquina do estudo tiver menos de 1100 px de largura, o participante não encontra «Compare» no menu superior.
- **Razão.** Os quatro espaços passam para o menu «More». **Condicionada à largura da janela**, registada no estado inicial.
- **Tarefa.** T3 (rota via Compare).

### H19. Passos da faixa de Mission Control parecem botões e não fazem nada (C)

- **Localização.** `views/home.js`, `flowStep()` e `flowInfo()`; `css/hub.css` (`.hm-step`, `.hm-step-info`).
- **Sintoma esperado.** O participante clica em «Run the mission», «Change a parameter», «Compare the runs» ou «Watch both» e nada acontece, e conclui que a aplicação não responde.
- **Razão.** Os dois primeiros passos (Hangar e Environments) são botões; os quatro seguintes usam a mesma classe `hm-step` e só diferem no cursor e na ausência de realce ao passar o rato.
- **Tarefa.** T1 (Mission Control), primeira impressão.

### H20. Teclas numéricas e Espaço mudam de contexto (C)

- **Localização.** `main.js`, `keydown`: dígitos 1 a 8 mudam de espaço de trabalho fora de campos de texto; Espaço e as setas controlam a reprodução.
- **Sintoma esperado.** Uma pessoa que carrega num dígito fora de um campo, ou no Espaço com o foco numa zona inesperada, muda de ecrã ou pausa a reprodução sem perceber porquê.
- **Razão.** Os atalhos globais existem sem pista visual. **Prioridade baixa**: só se observa por acidente.
- **Tarefas.** Nenhuma em particular: não testada por desenho; só se regista se ocorrer.

### H21. A frase de exemplo de Mission Control não é a alegação desafiada (C)

- **Localização.** `views/home.js` (cartão «Challenge a safety claim»: «the stage lands softly whenever the GNSS error is between 5 and 30 m»); `exec/claims/m13/g3-onset.json` (`statement`: controlador «guarded M9.1» e «whenever the bias starts within the first 20 s of the flight»).
- **Sintoma esperado.** O participante estranha que a alegação em Investigate seja mais estreita, ou toma a frase do ecrã inicial como a alegação testada.
- **Razão.** Os textos não coincidem. **Prioridade baixa.**
- **Tarefa.** T6.

### H22. Excesso de confiança no alcance real dos resultados (B, C)

- **Localização.** `views/home.js` (declaração só em Mission Control e rodapé); `views/player.js`, cartão «How far this goes» (no fim do painel lateral); grau «Reference case».
- **Sintoma esperado.** No fim, perguntado quanto confia nos resultados para um foguetão real, o participante (sobretudo N) dá 4 ou 5.
- **Razão.** Os limites de validade estão fora do caminho principal das tarefas.
- **Momento.** Conversa final (calibração de confiança).

### H23. Graus de evidência mal lidos (C)

- **Localização.** `experiences.js`, `GRADES` («Demonstration», «Exploratory finding», «Your experiment»); `views/vehicles.js` («Reference case», «Exploratory»).
- **Sintoma esperado.** «Reference case» lido como "validado" ou "real"; «Demonstration» lido como "falso"; «Exploratory finding» lido como "resultado menor".
- **Razão.** Os rótulos têm sentido técnico específico explicado só em dica de ferramenta.
- **Tarefas.** T1, T2.

### H24. Paisagem de fundo lida como o local da missão (C)

- **Localização.** `views/player.js`, vista «Geospatial» e seletor «Geographic environment»; `views/atlas.js`.
- **Sintoma esperado.** Quem abre «Geospatial» acha que a missão decorre nesse local real e que o terreno faz parte da simulação.
- **Razão.** O backlog regista que os nomes de lugar são contexto de fundo («backdrop only») e que o nome continua a ser o do ambiente escolhido. **Prioridade baixa**: as tarefas não exigem esta vista, e a sua fluidez não é avaliada.
- **Tarefas.** Nenhuma em particular: não testada por desenho; só se regista se o participante a abrir por iniciativa própria.

## Riscos de procedimento (não são previsões sobre o produto)

- O botão «Open Cinematic View» está sempre presente no leitor; sem o módulo instalado fica desativado. Se o participante tentar usá-lo, o moderador diz que essa parte fica fora desta sessão, regista "limite de âmbito" e não conta erro.
- Missões de subida (por exemplo «Two stages to orbit») podem demorar a arrancar. A duração não está documentada; o ensaio mede-a.
- A vista «Geospatial» carrega um pacote de vários MB e pode demorar a aparecer. Incidente de ambiente se bloquear a sessão; a fluidez gráfica não se avalia.

## Adendas (depois do congelamento)

Em branco. Cada adenda: data, texto, motivo.

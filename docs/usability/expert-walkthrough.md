# Revisão de especialista e verificações automáticas da Studio 0.18.1

**Revisão de especialista e verificações automáticas. Não é validação empírica de utilização; nenhuma pessoa participou.**

Este ficheiro prepara o estudo humano descrito em `README.md` desta pasta. Não contém observações de pessoas, taxas de sucesso nem tempos. Toda a gravidade é uma **previsão por julgamento de especialista**, escrita antes de qualquer sessão. Não altera o estado do requisito M15-R22, que só sessões realizadas podem alterar.

## 1. Âmbito, método e limites

### Produto e fontes

| Item | Valor |
| --- | --- |
| Produto | Studio 0.18.1 (base `bec7b3f`). A árvore `desktop/studio/ui` deste ramo não difere de `bec7b3f` (`git diff --stat` sem linhas). |
| Código lido | `index.html`, `main.js`, `ui.js`, `session.js`, `requirements.js`, `experiences.js`, `claims.js`, `provenance.js`, `verification.js`, `views/home.js`, `missions.js`, `player.js`, `lab.js`, `compare.js`, `run.js`, `discover.js`, partes de `charts.js` e `control.js`, `css/tokens.css`, `mission.css`, `hub.css`; no Rust, `catalog.rs` e `demos.rs` do foguetão e `catalog.rs` do domínio terrestre. |
| Capturas vistas (11) | Conjunto ux6 de revisão da 0.18.1 instalada (2026-11-15), fora do repositório. S1 `ux3-player-first-landing-1440x900-dark`; S2 `ux2-home-light`; S3 `ux4-corridor-broken-rule-run-1440x900-dark`; S4 `ux4-corridor-broken-rule-run-1024x640-dark`; S5 `ux4-threshold-trade-off-player-dark`; S6 `ux4-threshold-trade-off-player-1024x640-dark`; S7 `ux2-player-end-dark`; S8 `ux2-lab-result-dark`; S9 `ux4-compare-two-runs-dark`; S10 `ux3-flight-console-1440x900-dark`; S11 `ux3-analyse-1440x900-dark`. Os ficheiros `ux2` e `ux3` são, segundo o `README.txt` do conjunto, «páginas inalteradas mantidas por completude»: podem vir de uma iteração anterior da 0.18.1. |
| Sem captura | Missions (biblioteca), Investigate (todas as vistas), Runs, Vehicles, Environments, Settings, janela a 820 px. Os passos que dependem deles dizem «sem captura». |
| M19.1 | Ramo `fix/m19.1-honesty` (`docs/m19-1-honesty.md`), lido pelo diff e pelo relatório. **Não instalado nem verificado por pessoas.** A leitura do diff foi feita antes do seguimento da M19.1 sobre esta revisão. O diff inicial não tocava em `discover.js`, `compare.js`, `home.js`, `run.js`, `provenance.js`, `missions.js` nem `experiences.js`; o seguimento (F01 a F04, F06, F07, F10, F11, secção «Seguimento da passagem de especialistas» do relatório) passou a tocar em `player.js`, `compare.js`, `run.js`, `prepare.js`, `discover.js`, `provenance.js`, `lab.js` e no CSS, só em texto e apresentação (classe a, sem Rust). Continuam sem alteração, e portanto não mudam, F05, F19 a F22, F27, F40 e F42. As células de segurança de Compare, Analyse, Lab e Flight console mudam de tom por `model.js`, `verification.js`, `control.js` e CSS (F01). Os diffs de `requirements.js`, `lab.js`, `verification.js`, `model.js`, `control.js`, `session.js`, `player.js` e `mission.css` foram lidos. |

### Rótulos de evidência usados nas tabelas

- **[C]** lido no código (ficheiro e linha na árvore da 0.18.1).
- **[S]** visto numa captura (S1 a S11).
- **[A]** resultado de uma verificação automática da secção 5.
- **[K]** lido na documentação do kit ou do projeto.

Um valor ou texto que vem de [C] ou [S] é um **candidato**, a confirmar no ensaio técnico; nunca é «lido no ecrã instalado».

### Escala de gravidade (previsão)

Usa-se a escala 0 a 4 de `severity-and-measures.md`, que está definida sobre resultados observados. Aqui cada valor é a **gravidade prevista se o problema se observar** (GP). Duas regras de transposição, fixas:

1. Qualquer risco de interpretação errada de segurança (MS) ou de evidência (ME) recebe GP 3, o piso da regra 1 do kit, seja qual for a frequência prevista. Está marcado «piso MS» ou «piso ME».
2. GP 4 exige excesso de confiança observado ou impedimento a 2 ou mais pessoas. Nada disso se pode prever por especialista; **nenhum achado recebe GP 4**. A subida por frequência (regra 3) também não se aplica sem pessoas.

### Heurísticas usadas

- Nielsen: N1 estado do sistema, N2 correspondência com o mundo real, N3 controlo do utilizador, N4 consistência, N5 prevenção de erros, N6 reconhecer em vez de recordar, N7 flexibilidade, N8 desenho minimalista, N9 recuperação de erros, N10 ajuda.
- Honestidade científica: HS requisito contra regra de segurança, HE falhado ou não avaliado contra sucesso, HI identidade da execução, HL limites do modelo, HV visual que sugere uma medição ausente, HC integridade da evidência contra verdade da alegação (acrescentada por ser o eixo ME do kit).
- AY: verificação estática de acessibilidade (secção 5; não substitui um teste com tecnologias de apoio, fora do âmbito do kit).

### O que não se fez

Não se lançou nenhuma versão da Studio nem percurso de teste. Não se escreveu em `%LOCALAPPDATA%\org.vvlab.studio` nem em `%APPDATA%\org.vvlab.studio`. Não se correram os comandos de `AGENTS.md` (`cargo`, campanha Python): escrevem fora dos ficheiros desta tarefa e esta revisão não altera código. Não se mediu desempenho.

## 2. Registo de achados

Cada problema tem um só identificador, usado nas secções 3, 4, 6 e 7. Sem IDs duplicados: as contagens da secção 2.1 contam linhas desta tabela.

### 2.1 Contagem por gravidade prevista

| GP | Achados |
| --- | --- |
| 4 | 0 |
| 3 | 15 (F01 a F15) |
| 2 | 15 (F16 a F30) |
| 1 | 12 (F31 a F42) |
| 0 | 1 (F43) |
| Total | 43 |

Dos 15 de GP 3, 11 são piso MS ou ME (F01 a F08, F11, F12 e F13); F09 e F10 são GP 3 pelo critério de falha ou de ação errada com consequência; F12 é latente; F14 e F15 dependem do tamanho da janela.

### 2.2 Tabela

| ID | GP | Achado | Local | Tarefas | Heur. | Evid. | Efeito da M19.1 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F01 | 3 | Chip verde «Safety rules: No safety rule broken (N checked)» ao lado do chip «Mission» com requisitos falhados. A nota de âmbito só está no `title` do chip. Piso MS. | `player.js:813-814`, `tone()` 785-790, `.vchip.v-ok` `mission.css:174`; também `compare.js:106,189`, `lab.js:336`, `verification.js:34`, `library.js:232` | T2, T3 | HS, N4 | C, S7, S8, S10, S11 | O tom passa a neutro («held») nos chips do leitor, em Compare, Lab, Analyse e Flight console (diffs de `requirements.js`, `model.js`, `verification.js`, `control.js`, `lab.js` e CSS); Runs herda por `model.js`, não verificado na vista. O texto não muda. Reduz o risco; não o elimina. No seguimento, a frase de âmbito passou para junto do chip (ver F02). |
| F02 | 3 | A frase que corrige a leitura («A requirement can fail without any safety rule being broken…») fica no fim do cartão Result, depois dos blocos de todas as execuções. Com duas execuções está abaixo da dobra a 1440x900. Piso MS. | `player.js:846-850` | T2 | HS, N8 | C, S7 | Corrigido no ramo M19.1 (não instalado): a frase de âmbito (`SAFETY_SCOPE`) está agora sob o chip de segurança, em cada execução com requisito falhado e nenhuma regra de segurança quebrada, e já não no fim do cartão. Só testes estruturais e captura isolada; sem verificação por pessoas. |
| F03 | 3 | O banner «Expected, stated by the domain» cita «safe» ao lado de requisitos falhados («Baseline: hard landing, safe, R1 … and R2 … fail»). Para «Soft, but off the pad» escreve «Hard landing», contra a narrativa de 1,7 m/s. Piso MS. | `compare.js:93`; `run.js:196`; `prepare.js:276`; `domain-rocket/src/demos.rs:125,140,155,167` | T3 (via «Compare in detail») | HS, HE, N2 | C | Parcial: o texto `expectation` escrito em Rust **não** mudou (defeito 9 da M19.1, classe b: proposto, não implementado). Acrescentou-se uma glosa na interface por baixo do texto nas vistas Compare, Run e Prepare: «"safe" here means only that no safety rule was broken, and "unsafe" that one was; requirements are separate verdicts.» A citação «safe» ao lado de requisitos falhados continua no banner. |
| F04 | 3 | A peça «Evidence integrity» (verde, ✓) fica ao lado de «Claim»; na lista «Investigations» os chips «Refuted» (vermelho) e «Recomputed» (verde) aparecem juntos. Duas cores de aprovação para duas coisas diferentes. Piso ME. | `discover.js:184,409-418` | T6 (via ii), T8 | HC, N4 | C (sem captura) | Corrigido no ramo M19.1 (não instalado): a integridade da evidência passa a neutra, com a etiqueta «Evidence integrity: ...»; uma falha continua vermelha. Na lista «Investigations» e nas peças só há testes estruturais, sem captura (exige uma investigação guardada). |
| F05 | 3 | «Not refuted within budget» e «Experimentally supported» têm tom verde e ✓; o aviso «does not prove the claim» só está no `title`. Piso ME. Alcançável só como leitura hipotética (Q6b); a alegação do estudo é «Refuted». | `discover.js:40-41,75-77` | T6 (Q6b) | HC, HL, N2 | C | Inalterado. |
| F06 | 3 | Em Provenance, «Verified» (verde) e o botão «Replay» sobre uma execução cujos requisitos falharam: «verificado» lê-se como «a execução está bem». Piso ME. | `provenance.js:35-42`; `run.js:105` | T8 (rota por execução) | HC, N2 | C | Corrigido no ramo M19.1 (não instalado): «Verified» e o veredicto de reprodução passam a neutros e com a etiqueta «Evidence integrity: ...»; vista numa captura isolada (`after-1f-replay-integrity`). |
| F07 | 3 | O resultado das sementes mostra «k/n» em numeral grande, com «(95 % interval …)»; o aviso «not a reliability figure» está em texto pequeno e esbatido por baixo. O intervalo é calculado na interface (Wilson). Piso ME. | `lab.js:616-624,626-666` (658-659, 664) | T7 | HL, N8 | C | Parcial: a ressalva sobe para cima do numeral, em texto de 13,5 px a negrito, e o numeral diz «seeds»; continua menor do que o numeral de 26 px, por isso sem o mesmo peso visual. Só testes estruturais, sem captura. |
| F08 | 3 | Dois rótulos de grau lado a lado e opostos: «Exploratory finding» e «Reference case» (missões «One millimetre» e «A fix with a price»). O sentido só está em dicas. Piso ME. | `player.js:339-353,458`; `experiences.js:10-14` | T1, T2, T5 | HL, N4 | C, S4, S5, S6 | Inalterado (o chip já era neutro na 0.18.1). |
| F09 | 3 | «To goal 0.00 mm» no HUD e «Mission incomplete» no resultado, sem a cláusula que falhou. | `session.js:111`; `player.js:811` | T5 | HE, HV, N9 | C, S3 | Acrescenta, sob os chips, a frase «Recorded: 1 of 1 waypoint reached, 0 mm from the goal…» (`completionFacts`) e uma nota no `title` de «To goal». A frase fica à vista mesmo quando F10 esconde a linha. A cláusula em falta no registo continua por escrever (classe b, proposta). |
| F10 | 3 | Com a janela com altura de 720 px ou menos, a regra CSS esconde as linhas 4 e 5 do HUD. No domínio terrestre são «To goal» e «Confidence», e também a legenda «T true state · E … · D derived». A leitura-chave de T5 não está na vista Engineering. | `mission.css:243-246`; `session.js:107-114` | T5, T4-alt | N6, HV | C, S4, A | Corrigido no ramo M19.1 (não instalado) para o domínio terrestre: «To goal» e «Confidence» ficam à vista com altura de 720 px ou menos (capturas a 1024x640). No foguetão escondem-se só as duas linhas menores e a legenda do foguetão. |
| F11 | 3 | A única ação «ir ao instante» em destaque no cartão de resultado é «Go there» de «Where the runs part» (afastamento entre execuções). A crença contra a verdade vive em linhas pequenas. Piso ME (CE-T4-1). | `player.js:821-835`, `session.js:102`, `control.js:20` | T4 | HV, N6 | C | Parcial: o botão passou a dizer o destino («Go to 4.70 s», ou «Go to tick N» nas cenas por ticks). A crença contra a verdade como ação em destaque não mudou e fica por fazer. |
| F12 | 3 | Frases de sucesso sem base: «Every requirement and safety rule met.» sempre que nenhuma linha falha, mesmo com linhas «not evaluated»; chip «Mission» verde com «no mission requirement listed». Latente: o `README.txt` do conjunto ux6 diz que nenhum registo das missões produz um chip de fim «não avaliado»; linhas «not evaluated» existem (S3, S9: «1 not evaluated»), mas não se verificou se alguma missão das tarefas tem uma sem nenhuma linha falhada. Piso MS. | `player.js:813,818` | nenhuma conhecida | HE | C, K | Corrigido (defeitos 7 e 8). |
| F13 | 3 | Os limites do modelo estão fora do caminho: «How far this goes» no fim do painel lateral, em 12 px esbatido; a declaração «Exploratory models, not real vehicles» só em Mission Control e no hangar. Piso ME (excesso de confiança no alcance, H22). | `player.js:882-884`; `home.js:106,174` | todas; conversa final | HL, N10 | C, S1 | Inalterado. |
| F14 | 3 | A execução mostrada por defeito é a primeira (por exemplo «Exact GPS», «Baseline»), e o HUD, o relógio e o cartão que se veem primeiro são dessa. A pessoa tem de escolher a execução do cartão da tarefa. A 1024x640 as pílulas não selecionadas cortam o nome e as condições. | `player.js:222,425-432`; `mission.css:338-346` | T2, T3, T5 | HI, N1 | C, S4, S6 | Pílulas com nome completo e contagem exata de condições; a execução por defeito não muda. |
| F15 | 3 | Abaixo de 760 px de largura os botões «Analyse», «Compare in detail», «Open in Experiment Lab» e o seletor «Run:» desaparecem do cabeçalho do leitor, sem alternativa na página. Dependente da janela. | `mission.css:248-250` | T3, T7 | N7, N6 | C | Inalterado. |
| F16 | 2 | Com 1100 px de largura ou menos o leitor passa a página que desloca: objetivo e resultado ficam por baixo da cena. A 1024x640 o cartão Result não está à vista (inferido de S4 e S6: painel lateral ausente e barra de deslocamento); só o chip de fim na cena e o estado nas pílulas. | `mission.css:322-331` | T1, T2 | N1, N8 | C, S4, S6 | Inalterado. |
| F17 | 2 | Três controlos de nomes quase iguais para mostrar o fim: «Show the result now» (cartão), «Skip to the result» (transporte), «Show all findings now» (interruptor). Os dois primeiros fazem o mesmo; o terceiro liga um modo. | `player.js:615,718,843` | T1, T2, T4 | N4, N6 | C, S1 | Inalterado. |
| F18 | 2 | Sob `prefers-reduced-motion` a reprodução não arranca sozinha. A página fica parada no início, sem aviso. A nota de rota de `tasks.md` diz que arranca sozinha. | `player.js:228` | T1, T2 | N1 | C, A | Inalterado. |
| F19 | 2 | A espera de um desafio: os segundos só se atualizam quando chega um evento de progresso; as fases têm nomes técnicos; não há estimativa. «Cancel» cancela de imediato, sem confirmação e sem dizer o que se perde. As contagens por fase («n / m») existem. | `discover.js:283-291,311-332` | T6 (via i) | N1, N3 | C (sem captura) | Inalterado. |
| F20 | 2 | O separador «Investigate» sem alegação indicada abre a primeira da lista (`claims[0]`). A ordem vem do sistema de ficheiros; em `exec/claims/m13` há `corridor-noise.json` antes de `g3-onset.json`. A alegação certa escolhe-se na lista «Claims». Ordem não verificada. | `discover.js:110-112` | T6, T8 | N6 | C | Inalterado. |
| F21 | 2 | A frase de exemplo de Mission Control («…whenever the GNSS error is between 5 and 30 m») difere da alegação desafiada (controlador «guarded M9.1», «within the first 20 s of the flight»). | `home.js:162`; `exec/claims/m13/g3-onset.json` | T6 | HL, N4 | C | Inalterado. |
| F22 | 2 | Vocabulário inconsistente: «Mission Control»/«Home», «Runs»/«Records», «Investigate»/«Discovery Lab»/«Challenge a claim», «Experiment»/«Experiment Lab», «hangar»/«Vehicles», «Run mission» (Missions e Configure), «Replay» (cabeçalho de Analyse, ícone do leitor, «Replay and verify»), «Recompute now»/«Recompute from scratch»/«Recomputation». | `ui.js:122`; `index.html:26-36,71`; `run.js:46-49,105`; `discover.js:212`; `prepare.js:489`; `provenance.js:20` | T1, T6, T7, T8 | N4 | C | Inalterado. |
| F23 | 2 | O texto da missão «Soft, but off the pad» manda «Choose “Change the conditions”». Esse botão não existe; o controlo chama-se «Open in Experiment Lab». | `experiences.js:43`; `player.js:468` | T7 | N4, N6 | C | Inalterado. |
| F24 | 2 | O campo «Level» (Explorer, Analyst) é um item pequeno de uma lista de dados, sem definição na página. | `missions.js:61` | T1, T2 | N10 | C | Inalterado. |
| F25 | 2 | Com menos de 1100 px, «Configure», «Analyse», «Compare» e «Runs» passam para «More». | `hub.css:151-156`; `main.js:248-279` | T3 | N7 | C, S4 | Inalterado. |
| F26 | 2 | Domínio terrestre: «Believed east» e «Believed north» só existem na Flight console (grupo «Perception»). O HUD Engineering mostra «GPS north» (O); a cena 2D desenha caminho verdadeiro e amostras de GPS, não a crença. Risco de CE-T4-3 (E contra O). | `session.js:107-114,203-205`; `player.js:367` | T4-alt | HV, N6 | C, S3 | Inalterado. |
| F27 | 2 | Investigate não tem navegação para outros espaços (`initDiscover(root)` não recebe `navigate`): do contraexemplo não há ligação às execuções, nem do Lab a uma verificação. | `discover.js:87`; `main.js:289` | T6, T7, T8 | N7, N3 | C | Inalterado. |
| F28 | 2 | Contraste. Escuro: nenhum par de texto abaixo de 4,5:1. Claro: `--neutral` 4,10 em `--bg-0` e 4,28 em `--bg-2`; chips de estado sobre as lavagens entre 3,66 e 4,48; `--plume` 2,84. As margens `--rule-strong` (1,4 a 1,55) estão abaixo de 3:1, o que pesa se forem o único limite de um controlo. | `css/tokens.css` | todas (tema claro) | AY | A | Inalterado. |
| F29 | 2 | A informação de apoio está em `title=` (101 atributos nas vistas): nota de segurança, definição das letras T, E, O, D, aviso «does not prove». Não chega por teclado nem por toque. | `views/*.js` | T2, T4, T6, T7 | N10, AY | A | Inalterado. |
| F30 | 2 | HUD Engineering do foguetão: «Altitude error (D)» só tem a definição no `title`; a legenda das letras tem 12 px e desaparece com altura de 720 px ou menos. | `session.js:102`; `player.js:596-598`; `mission.css:245` | T4 | N10, HV | C, S4 | Inalterado. |
| F31 | 1 | O briefing revela resultados antes da reprodução, ao contrário do resto do leitor, que retém achados até o cursor os atingir: «steps into the zone at tick 21», «rejects the altimeter 0.1 s into the flight», «50 m too much height». Para o estudo, cria respostas legíveis no ecrã (secção 7). | `experiences.js:71-74,104-106`; `player.js:873-875,690-703` | T2, T4, T5 | N8 | C, S3 | Inalterado. |
| F32 | 1 | Os quatro últimos passos da faixa de Mission Control têm o aspeto dos dois primeiros (botões) e não fazem nada; só o cursor e o realce ao passar o rato diferem. | `home.js:179-186`; `hub.css:44-47` | T1, primeira impressão | N4 | C | Inalterado. |
| F33 | 1 | Os dígitos 1 a 8 mudam de espaço fora de campos de texto; a ordem (`main.js:24`) não coincide com a dos separadores visíveis (3 é «Investigate», que está sexto; «Vehicles», «Environments» e «Experiment» não têm dígito); a ajuda diz «Home» e «Records». | `main.js:24,236`; `ui.js:122` | nenhuma (H20) | N7, N4 | C | Inalterado. |
| F34 | 1 | `hudNum` mostra duas casas decimais para valores que no domínio terrestre são milímetros inteiros («0.00 mm»), o que sugere precisão sub-milimétrica. | `session.js:118-124` | T5 | HV | C, S3 | Inalterado. |
| F35 | 1 | No fim da aterragem o HUD mistura valores do verificador no instante do contacto («Descent rate», «From pad centre») com «last recorded sample» («Tilt», «Throttle», «Altitude error»), sob o título «At contact». A distinção só está no `title`. | `session.js:82-93`; `player.js:594` | T2, T4 | HE, HV | C, S5 | Inalterado. |
| F36 | 1 | O chip de fim na cena fica âmbar (`--fail`) também quando uma regra de segurança foi quebrada; o vermelho (`--unsafe`) só aparece nas pílulas e no chip «Safety rules». O texto nomeia a regra. | `mission.css:123` (`.ph-end-bad`); `requirements.js:278` | T2, T5 | HS | C, S3, S5 | Inalterado. |
| F37 | 1 | O seletor «Run:» da Cinematic View aparece com duas execuções mesmo sem o módulo instalado (botão desativado): segunda lista de execuções ao lado das pílulas. | `player.js:448-451` | T2, T3, T5 | N8, HI | C, S4 | Inalterado. |
| F38 | 1 | Mission Control: parágrafo inicial denso («deterministic», «engineering telemetry», «recompute»); a 1440x900 os atalhos «Land a rocket →» ficam no limite inferior da janela. | `home.js:105,121` | primeira impressão, T1 | N8 | C, S2 | Inalterado. |
| F39 | 1 | Os gráficos SVG de Investigate (dispersão, mapa de envelope) têm `role="img"` com rótulo curto; a informação por célula está em `<title>`. Sem tabela equivalente. | `discover.js:506,694` | T6 | AY | C | Inalterado. |
| F40 | 1 | A frase de «Largest change:» junta as etiquetas das execuções sem pontuação: «Baseline: trusts the altimeter fails it; Robust: cross-checks it passes it». | `compare.js:153-155` | T3 | N2 | C | Inalterado. |
| F41 | 1 | Ao recuar o cursor, os marcadores de achados atrás do cursor desaparecem do ecrã (retenção deliberada, a favor da honestidade); sem aviso. | `player.js:690-703` | T4 | N1 | C | Inalterado. |
| F42 | 1 | O botão «Challenge this claim» do leitor leva à página da alegação, não ao pacote já guardado; este só se acha na lista «Investigations». | `player.js:914`; `discover.js:110-111,122-128` | T6, T8 | N6 | C | Inalterado. |
| F43 | 0 | Compare fica em «More» abaixo de 1100 px, mas «Compare in detail» no leitor abre-o diretamente. A previsão H18 não afeta a rota principal de T3. | `player.js:465`; `hub.css:151-156` | T3 | N7 | C, S4 | Sem efeito. |

## 3. Passagem cognitiva por tarefa

Para cada passo da rota prevista, as quatro perguntas padrão: **Q1** a pessoa tenta o efeito certo? **Q2** nota que a ação certa existe? **Q3** associa a ação ao efeito? **Q4** vê progresso depois? Código: **S** sem problema previsto, **R** risco, **N** falha prevista. As colunas seguem a ordem Q1 Q2 Q3 Q4. Os valores de texto são candidatos (secção 1). As rotas são as da nota do moderador em `tasks.md`; qualquer outra rota é igualmente possível e não se avaliou.

Observações positivas válidas para várias tarefas: a reprodução tem estado em `role="status"` («Simulating the mission on this machine…», `player.js:180-190`); o resultado só aparece quando a reprodução chega ao fim ou por pedido (`player.js:600`), com o foco movido para o título «Result» quando estava na região do resultado (`player.js:779-781`); o foco visível é global (`app.css:40`).

### T1. Escolher e executar uma missão

| Passo | Local | Q1 | Q2 | Q3 | Q4 | Falhas |
| --- | --- | --- | --- | --- | --- | --- |
| 1. Escolher «Land a rocket» em Mission Control | `home.js:121,156`; `FEATURED` `home.js:15` (a primeira entrada é «Two stages to orbit») | S | R | S | S | F38, F24; o atalho está no limite da janela a 1440x900 [S2] |
| 1b. Alternativa: «Run mission» no cartão | `missions.js:68` | S | S | S | S | sem captura |
| 2. Ver a reprodução | `player.js:228,613-621` | S | S | S | S | F18 |
| 3. Chegar ao resultado | `player.js:600,615,843` | S | R | R | S | F17, F16 |
| 4. Ler o cartão «Result» | `player.js:838-851` | S | R | S | S | F16, F08, F13 |

Chave candidata (a confirmar): resultado «Landed» (`domain-rocket/src/record.rs:616`); chip «Mission» «all N requirements met» com N=6 visto noutros registos do mesmo domínio [S5, S7]; chip «Safety rules» «No safety rule broken (5 checked)» [S7, noutras execuções]; frase «Every requirement and safety rule met.» [C].

### T2. Perceber o resultado e a causa

| Passo | Local | Q1 | Q2 | Q3 | Q4 | Falhas |
| --- | --- | --- | --- | --- | --- | --- |
| 1. Encontrar «A sensor that lies» | `home.js:156` (item 04), `experiences.js:69-78` | S | R | R | S | o título é metafórico («lies»); o item 04 está na secção «Featured missions», abaixo do topo (S2 mostra só o topo); F24 |
| 2. Executar e esperar | `player.js:190` («Simulating run 1 of 2: …») | S | S | S | S | F18 |
| 3. Distinguir os dois veículos | `player.js:425-432` | S | S | R | S | F14, F37 |
| 4. Ler o resultado de cada execução | `player.js:796-819` | S | R | R | S | F16, F02, F08, F36 |
| 5. Julgar se o veículo foi «seguro» (Q2b) | chip em `player.js:814` | S | S | N | S | F01, F02, F03: o chip verde está à vista, a correção está abaixo (piso MS) |
| 6. Dizer a causa | `player.js:860-862` («Why it happened») | S | S | S | S | F31: a causa («50 m too much height») está no sumário do cartão e no briefing, legível sem interpretar o resultado |

Chave candidata (a confirmar): «Reached the ground, requirements not met» (`domain-rocket/src/record.rs:647`); chip «Mission» «N of 6 requirements failed» com N=2 se R1 e R2 falharem (`domain-rocket/src/demos.rs:125`); chip «Safety rules» provavelmente «No safety rule broken (5 checked)» (`domain-rocket/src/demos.rs:125` diz «safe»; o «5» vem de outras execuções do domínio [S7]); velocidade no contacto «about 33 m/s» (`domain-rocket/src/demos.rs:114`), limite «<= 3 m/s» [S5].

### T3. Comparar duas execuções

| Passo | Local | Q1 | Q2 | Q3 | Q4 | Falhas |
| --- | --- | --- | --- | --- | --- | --- |
| 1. Abrir a comparação por «Compare in detail» | `player.js:465` | S | R | S | S | F15, F25, F43 |
| 1b. Alternativa: comparar no cartão Result | `player.js:838-851` | S | S | S | S | F16 |
| 2. Ler «Largest change:» | `compare.js:146-164` | S | S | R | S | F40 |
| 3. Ver o banner de expectativa | `compare.js:93` | S | S | N | S | F03 («safe» ao lado de requisitos falhados) |
| 4. Atribuir a execução certa (Q3a) | `compare.js:95-110` | S | S | S | S | etiquetas e cores por execução [S9] |

Chave candidata: «Largest change:» por execução de referência «Baseline: trusts the altimeter» [C]; a frase junta «fails it» e «passes it» às etiquetas (F40).

### T4. Crença contra verdade

| Passo | Local | Q1 | Q2 | Q3 | Q4 | Falhas |
| --- | --- | --- | --- | --- | --- | --- |
| 1. Achar onde crença e verdade aparecem juntas | HUD `session.js:102`; Flight console `session.js:170-175`; Analyse `charts.js` (não confirmado) | S | R | R | S | F11, F30; a linha tracejada da cena só tem explicação na legenda inferior (`player.js:364`) |
| 2. Mover o cursor até t* | `player.js:609`, `playerKey` 728-738 | S | S | S | S | F41 |
| 3. Distinguir de «Where the runs part» | `player.js:821-835` | S | N | R | S | F11 (piso ME) |
| 4. (opcional) Quando o outro deixa de confiar no sensor | HUD «Altimeter» `session.js:103`; marcador «controller detection» `player.js:658-662` | S | R | S | S | F31 (0,1 s está no briefing), F41 |

T4-alt (se o ensaio a escolher): crença só na Flight console (F26); «Mode» «fallback» (`session.js:113`); `domain-ground/src/catalog.rs:467` diz que o modo de segurança começa no tick 6.

Chave candidata: linhas «Altitude error» (D), «Believed height of CoM» (E), «True height of CoM» (T), «Altimeter» com valores «in use» e «rejected» [C, S10]. Os instantes e os valores de limiar ficam por medir no ensaio.

### T5. Missão terrestre: chegou ou não?

| Passo | Local | Q1 | Q2 | Q3 | Q4 | Falhas |
| --- | --- | --- | --- | --- | --- | --- |
| 1. Abrir «One millimetre» | `home.js:156` (item 06); `experiences.js:101-111` | S | R | S | S | sem captura de Missions |
| 2. Escolher a execução «1 mm of GPS noise» | `player.js:222,425-432` | S | R | R | S | F14: a execução por defeito é «Exact GPS»; «1 mm noise, 250 mm arrival radius» tem nome parecido [S3] |
| 3. Esperar até ao fim | `player.js:215` (0,5x por defeito em ticks) | S | S | S | S | F18 |
| 4. Ler «To goal» | `session.js:111` | S | N | R | S | F10 (linha oculta com altura ≤ 720 px), F34, F09 |
| 5. Ler o resultado e a segurança | `player.js:838-851` | S | R | R | S | F16, F36; o chip «1 of 4 safety rules broken» é claro [S3] |
| 6. Explicar a diferença (Q5c) | `player.js:860-862` | S | S | R | S | F09: o ecrã não explica; na 0.18.1 não há frase de ligação |

Chave candidata (a confirmar): «To goal 0.00 mm» no tick 32 e chip «Mission incomplete» [S3]; «Mission: 2 of 8 requirements failed, 1 not evaluated, 5 met» e «Safety rules: 1 of 4 safety rules broken» [S3, S4]. **O texto «1 not evaluated» não está na chave de `tasks.md`.** O instante «tick 21» aparece em [S9] ligado ao requisito «Restricted zone stays clear (contract)»; a linha «Truth stays outside the restricted zone» mostra «from=(5000,2000); to=(5000,1750)» sem instante. A chave de Q5d (tick 21 para a regra de segurança) tem de ser confirmada no ensaio.

### T6. Desafiar uma alegação

| Passo | Local | Q1 | Q2 | Q3 | Q4 | Falhas |
| --- | --- | --- | --- | --- | --- | --- |
| 1. Chegar a Investigate | `home.js:169-170`; separador `index.html:31`; `player.js:914` | S | S | R | S | F22, F42; «See a counterexample…» leva ao leitor, não à alegação (`home.js:169`) |
| 2. Escolher G3 na lista «Claims» | `discover.js:110-112,158-171` | S | R | S | S | F20 (sem captura) |
| 3. Iniciar o desafio | `discover.js:233,293-309` | S | S | S | S | texto «At most N simulations…» (`discover.js:234`) |
| 4. Esperar | `discover.js:311-332` | S | S | S | R | F19 |
| 5. Ler o veredicto e o grau | `discover.js:398-418` | S | S | S | S | F04, F13; «Refuted» é vermelho e o grau «Exploratory» está à vista nas peças (`discover.js:417`) |
| 6. Dizer o alcance (Q6a) | `discover.js:808-811` (secção 6 de 7); `player.js:882-884` | S | R | R | S | F13, F21, F27 |

Via (ii), abrir o pacote guardado: a lista «Investigations» mostra «Refuted» e «Recomputed» lado a lado (F04, `discover.js:184`).

Chave candidata (a confirmar): «Refuted»; «A reproduced counterexample breaks the claim beyond its tolerance.» (`discover.js:37`); «Exploratory»; «Simulation, development seeds. Not a confirmation, not a certification.» (`discover.js:417`); cartão «G3 under a late GNSS bias» (`g3-onset.json`).

### T7. Testar uma mitigação

| Passo | Local | Q1 | Q2 | Q3 | Q4 | Falhas |
| --- | --- | --- | --- | --- | --- | --- |
| 1. Abrir «Soft, but off the pad» e ver o fim | `experiences.js:38-47` | S | S | S | S | sem captura de Missions |
| 2. Chegar ao Lab | `player.js:468` («Open in Experiment Lab») | S | R | R | S | F23, F22, F15 |
| 3. Achar «Lateral position gain» | `lab.js:391,403,427-481`; `domain-rocket/src/catalog.rs:113-124` | S | S | S | S | o grupo «Controller tuning» abre sozinho e o parâmetro vem primeiro com «Listed for this failure» se R5 estiver em foco (R5 é o primeiro requisito falhado: `lab.js:92`); a confirmar no ensaio |
| 4. Alterar e executar | `lab.js:488-492,199-217` | S | S | S | S | «Change one condition first» ligado por `aria-describedby` (`lab.js:490-492`) |
| 5. Ler se o requisito do alvo passou | `lab.js:531-582` | S | S | R | S | o requisito chama-se «Distance from pad centre» (`domain-rocket/src/catalog.rs:447`), não «Landing-zone radius (R5)» (rótulo do parâmetro de limite, `domain-rocket/src/catalog.rs:248`) [S8] |
| 6. Confiar? Executar sementes (Q7) | `lab.js:626-666` | S | S | R | S | F07 (piso ME); «one run on seed N… check it across seeds» está à vista (`lab.js:576`) |

Proteções que mitigam CE-T7-1 (relaxar o requisito): o grupo «Requirements» fica fechado por defeito (`lab.js:481`), a nota «These change only how a run is judged» aparece ao abri-lo, antes de qualquer alteração (`lab.js:484`), e a lista mostra «(judging only)» (`lab.js:551`). Os parâmetros de limite nunca recebem «Listed for this failure» (`lab.js:391`).

Chave candidata: «Lateral position gain», valor da missão 0,04 contra predefinido 0,12, intervalo 0 a 1 (`domain-rocket/src/demos.rs:160`, `domain-rocket/src/catalog.rs:114-121`); botões «8 seeds», «16 seeds», «32 seeds» (`lab.js:636`); texto «k/n baseline conditions meet every requirement and safety rule (95 % interval a to b %)» (`lab.js:658`).

### T8. Verificar a evidência

| Passo | Local | Q1 | Q2 | Q3 | Q4 | Falhas |
| --- | --- | --- | --- | --- | --- | --- |
| 1. Chegar ao pacote guardado | `index.html:31`; lista «Investigations» `discover.js:172-186` | S | R | S | S | F20, F42, F22 |
| 2. Achar a recomputação | peça «Evidence integrity» `discover.js:410-413`; botões `discover.js:411,437`; passo «Evidence» `discover.js:445,815-828` | S | S | R | S | F22 («Recompute now», «Recompute from scratch», «Recomputation at») |
| 3. Dizer o que a peça mostra | `discover.js:412` | S | S | R | S | F04 (piso ME) |
| 4. Separar integridade de verdade (Q8a) | `discover.js:409-418` | S | S | N | S | F04: ✓ verde ao lado de «Claim» |
| Rota por execução | `run.js:105`; `provenance.js:20-47` | S | R | R | S | F06 |

Sobre a dúvida de `tasks.md` (pacote novo criado em T6): `challenge()` chama `verify()` sozinha depois de abrir o pacote (`discover.js:299-303`). **Candidato:** um pacote novo aparece já recomputado, com «Recomputed, every check passed». A confirmar no ensaio com a via (i); se a recomputação falhar, o pacote fica «withdrawn» (`discover.js:434,440-442`).

Chave candidata: «Recomputed, every check passed» e «N probes rerun · <data>» (`discover.js:412`); passos «Challenge», «Counterexample», «Envelope», «Cause», «Mitigation», «Limits», «Evidence» (`discover.js:445`); número de verificações e duração por medir.

## 4. Avaliação heurística

Os achados estão na secção 2.2; aqui só se agrupam por heurística, sem contagem nova.

### 4.1 Honestidade científica

| Dimensão | Achados | Leitura |
| --- | --- | --- |
| HS requisito contra regra de segurança | F01, F02, F03, F36 | O texto é cuidadoso: nunca escreve «safe» sozinho, conta as regras avaliadas (`requirements.js:145-162`) e põe a nota nas vistas. O problema é a **apresentação**: tom verde, nota fora de vista e, em Compare, a frase do domínio com «safe». |
| HE falhado ou não avaliado contra sucesso | F09, F12, F35 | Contagens corretas («1 not evaluated»), mas frases de sucesso sem condição em dois sítios (latentes) e valores de dois instantes sob o mesmo título. |
| HI identidade da execução | F14, F37 | O nome completo, o identificador curto e as condições existem; o risco é a execução mostrada por defeito e as pílulas cortadas a 1024x640. |
| HL limites do modelo | F05, F07, F08, F13, F21 | O limite existe em vários sítios (Home, «How far this goes», «Evidence grade», aviso do Lab) mas em texto pequeno e longe do ponto de decisão. |
| HV visual que sugere medição ausente | F10, F11, F26, F30, F34, F35 | A cena do foguete não desenha o impacto (o chip diz «impact not modelled»); a cena terrestre não desenha a crença; «0.00» sugere casas decimais que não existem. |
| HC integridade contra verdade | F04, F05, F06 | Dois tons de aprovação para duas coisas. A separação em peças com `aria-label="Separate verdicts"` (`discover.js:409`) é boa, mas a cor não a distingue. |

### 4.2 Nielsen, o que não é honestidade

| Heurística | Achados |
| --- | --- |
| N1 estado do sistema | F16, F18, F19, F41 |
| N2 correspondência com o mundo real | F40 (e F03 pelo conteúdo) |
| N3 controlo do utilizador | F19, F27 |
| N4 consistência | F17, F22, F23, F32, F33 |
| N5 prevenção de erros | sem achado: o Lab desativa «Run experiment» sem alteração e pede confirmação antes de substituir uma experiência (`lab.js:35-39,49-53`) |
| N6 reconhecer em vez de recordar | F10, F11, F14, F20, F26, F42 |
| N7 flexibilidade | F15, F25, F27, F33, F43 |
| N8 desenho minimalista | F02, F16, F31, F37, F38 |
| N9 recuperação de erros | F09 (explicação em falta); erros de arranque e de execução têm texto e «Try again» (`player.js:198-203`) |
| N10 ajuda | F13, F24, F29, F30 |

### 4.3 Pontos fortes (não contam como achados)

- A separação missão contra segurança está nas palavras e em dois chips com etiqueta própria (`player.js:812-814`); a nota «Safety rules are judged on the true state … a requirement can fail without any safety rule being broken» (`requirements.js:195`) está em cinco ficheiros de vista (`player.js`, `compare.js`, `lab.js`, `library.js` e `verification.js`).
- Os dois sinais de forma além da cor: a violação de regra é quadrado, a de requisito círculo, com legenda (`player.js:651,628-629`); os chips têm palavra.
- A retenção do resultado e dos achados até ao cursor os atingir evita revelar o que ainda não aconteceu.
- O Lab separa o limite de um requisito do voo: «(judging only)» e «Only a requirement limit changed: the flight is identical…».
- Um pacote que falha a recomputação aparece «Withdrawn» e o conteúdo deixa de ser mostrado como resultado (`discover.js:420-423,440-442`).
- A lista de verificação «Evidence» mostra cada verificação com o seu identificador e detalhe (`discover.js:827`).

## 5. Verificações automáticas

Tudo o que segue é **estático**: lê o código-fonte e os tokens de CSS. Não houve lançamento da Studio, nem percurso, nem leitor de ecrã. Os ficheiros estão em `docs/evidence/m19/usability/`:

- `static_checks.mjs`: o programa (lê só `desktop/studio/ui`, imprime, não escreve).
- `static_checks_output.txt`: a saída completa, corrida a partir da raiz do repositório (`node docs/evidence/m19/usability/static_checks.mjs`, Node 24).
- `ui_requirements_node_test_output.txt`: a saída filtrada de `node --test tests/ui_requirements.test.mjs`.

### 5.1 Contraste (WCAG 2.x), a partir de `css/tokens.css`

Lavagens compostas sobre a superfície indicada; 71 pares por tema; 4,5:1 para texto (a interface usa sobretudo 12 px, por isso não se aplica o limiar de texto grande) e 3:1 para marcas não textuais.

| Tema | Pares abaixo do limiar | Valores |
| --- | --- | --- |
| Escuro | 2, ambos margens | `--rule-strong` sobre `--bg-0` 1,54 e `--bg-1` 1,48. Texto, por exemplo: `--fg-3` sobre `--bg-3` 5,72; chips aprovado, falhado, inseguro e neutro sobre a lavagem em `--bg-1` entre 5,28 e 7,02. |
| Claro | 11 | `--neutral` sobre `--bg-0` 4,10 e `--bg-2` 4,28; chips sobre a lavagem: `--pass`, `--fail`, `--unsafe` e `--neutral` em `--bg-0` entre 3,66 e 4,11, `--neutral` em `--bg-1` 4,02, `--unsafe` em `--bg-1` 4,48; `--plume` sobre `--bg-0` 2,84; `--rule-strong` 1,40 e 1,55. |

Leitura: no tema escuro o texto passa; no claro, os chips de estado e o texto neutro ficam a 0,4 a 0,9 abaixo de 4,5 (F28). O par `--pass` com `--fail` tem razão de luminância 1,05 (escuro) e 1,01 (claro): as duas cores distinguem-se só pelo matiz, e é por isso que a palavra e o glifo têm de acompanhar (acompanham). **Não computável:** texto sobre `--hud` e `--glass` em cima da cena 3D, do relevo e da Cinematic View (depende da imagem por trás). A borda `--rule-strong` só conta como limite de controlo (WCAG 1.4.11) quando é o único limite visível; não se verificou onde isso acontece.

### 5.2 Marcação e teclado (contagens por padrão de texto)

| Verificação | Resultado |
| --- | --- |
| `lang="en"`; ligação «Skip to content»; `<main tabindex="-1">` | presentes |
| `tabindex` positivo | 0 |
| `<img>` criadas em JS | 3, todas com `alt=""` (decorativas, nomes ao lado) |
| botões só com ícone | 4, nenhum sem `aria-label` |
| `onclick` em `div`, `span`, `li` | 1 (`ui.js`, fundo do modal; Escape e o botão «Close» existem) |
| `role="radio"` / `aria-checked` | 15 / 25 |
| `role="tab"` / `aria-selected` | 2 / 6 |
| regiões `aria-live`, `role="alert"`, `role="status"` | 17, 7, 6 |
| `role="slider"` com `keydown` | `timeline.js` (os `input[type=range]` do leitor usam o controlo nativo) |
| modal | `role="dialog"`, `aria-modal`, Escape e Tab tratados (`ui.js:31-72`) |
| `title=` nas vistas | 101 (F29) |
| texto abaixo de 12 px | 9 declarações (eixos de gráficos 10 a 11 px, contagens 10,5 px, `.mct-tick` 9,5 px) |
| regras que retiram o contorno | 4: `.input:focus` e `.select:focus` (substituídas por borda e sombra), `.unit-input input`, e as `canvas` do leitor e da Flight console |

Limite do método: estes números vêm de expressões regulares sobre o texto-fonte. Elementos criados por outros caminhos ou atributos escritos depois não entram.

### 5.3 Movimento

- 8 `@keyframes` em 4 ficheiros CSS; todos os ficheiros que os definem têm bloco `prefers-reduced-motion` (`app.css`, `control.css`, `discover.css`, `mission.css`; `tokens.css` zera as durações).
- O deslocamento suave de `discover.js` e a reprodução automática do leitor respeitam `prefers-reduced-motion`. A consequência para a rota de T1 é o F18.
- Teste de unidade existente: `node --test tests/ui_requirements.test.mjs` → **31 subtestes `ok`; o executor conta o ficheiro como 1 teste (pass 1, fail 0)**. Cobre `safetyWording`, `requirementWording`, `endChip`, `headlineChange`, nomes de condições. **Não** cobre apresentação, cor, nem `lab.js`, `discover.js` ou `compare.js`.

### 5.4 Não corrido

`cargo fmt`, `cargo clippy`, `cargo test`, `python -m unittest`, `cargo build --release` e a campanha de `AGENTS.md` (não se alterou código e escrevem fora destes ficheiros). Os percursos `ux_journeys`, `ux2_journeys` e semelhantes, e `tests/test_honesty_wording.py` (corre sobre o ramo M19.1; não foi executado aqui).

## 6. Previsões H01 a H24

`predictions.md` tem **24** previsões (H01 a H24) e todas se cobrem. Cada veredicto é **julgamento de especialista**, com três valores: «apoia» (o código ou a captura é compatível com a previsão), «contradiz» e «não avaliável»; «em parte» qualifica os dois primeiros. **«Apoia» não é confirmação independente:** as previsões e esta revisão partem das mesmas fontes (leitura do código e backlog), logo a concordância é esperada. Só pessoas observam.

| H | Veredicto | Fundamento | Achados | Efeito da M19.1 |
| --- | --- | --- | --- | --- |
| H01 | Apoia | Chip verde com glifo e texto «No safety rule broken»; a nota está no `title` e abaixo da dobra; Compare cita «safe». | F01, F02, F03 | Chip neutro; texto igual; frase de âmbito sob o chip; Compare com a mesma frase do domínio e uma glosa por baixo. |
| H02 | Apoia | «To goal 0.00 mm» ao lado de «Mission incomplete» [S3]; sem cláusula. | F09 | Acrescenta frase de ligação; a leitura numérica fica. |
| H03 | Apoia | Execução por defeito é a primeira; pílulas cortadas a 1024x640 [S4, S6]. Depende do tamanho da janela. | F14 | Pílulas com nome completo e contagem. |
| H04 | Apoia em parte | O chip de fim diz «impact not modelled» [S5, S6], o que atenua. A cena mantém o estágio e a pluma no instante do contacto [S7]. | F36 | Remove a pluma depois da última amostra; a do contacto fica. |
| H05 | Apoia | «Level» é um item pequeno, sem definição (`missions.js:61`). Se o campo é ignorado, não se avalia. | F24 | Inalterado. |
| H06 | Não avaliável | O texto é denso [S2]; a compreensão só se observa. | F38 | Inalterado. |
| H07 | Apoia | Investigate não tem navegação para outros espaços (`discover.js:87`). | F27, F42 | Inalterado. |
| H08 | Apoia em parte | Há contagens por fase e segundos, mas só se atualizam com eventos, os nomes são técnicos e «Cancel» não pede confirmação. Condicionada à via (i). | F19 | Inalterado. |
| H09 | Apoia | Peças lado a lado, uma verde («Recomputed») e uma vermelha («Refuted»); «Recompute» tem três usos. | F04, F06, F22 | Integridade neutra e etiquetada (F04, F06); F22 inalterado. |
| H10 | Apoia em parte | Na página do pacote o grau «Exploratory» e «Not a confirmation, not a certification» estão nas peças, à vista (`discover.js:417`); no leitor ficam no fim do painel. | F13, F05 | Inalterado. |
| H11 | Apoia | «Go there» é a única ação de salto em destaque; crença e verdade só em linhas pequenas. | F11, F30 | F11 parcial (botão «Go to <instante>»); F30 inalterado. |
| H12 | Apoia | Três controlos de nomes parecidos [S1]; os marcadores desaparecem ao recuar. | F17, F41 | Inalterado. |
| H13 | Apoia | «Change the conditions» só existe no texto da missão (`experiences.js:43`). | F23 | Inalterado. |
| H14 | Contradiz em parte | O grupo «Requirements» fica fechado por defeito e a nota «These change only how a run is judged» aparece ao abri-lo, **antes** de alterar (`lab.js:481,484`); a previsão diz «só depois de agir». A alteração do limite continua possível. | (mitigação, sem achado) | Inalterado. |
| H15 | Apoia | Numeral «k/n» grande, aviso pequeno por baixo, intervalo de 95 %. | F07 | Ressalva por cima do numeral, ainda menor do que ele. |
| H16 | Contradiz em parte | Para esta missão o grupo «Controller tuning» abre sozinho e «Lateral position gain» vem primeiro com a marca (`lab.js:480-481`; `domain-rocket/src/catalog.rs:123`). Falta o ensaio para confirmar o grupo e a marca. | (mitigação) | Inalterado. |
| H17 | Apoia | Instâncias concretas em F22; a ajuda de teclado diz «Home» e «Records». | F22, F33 | Inalterado. |
| H18 | Contradiz em parte | «More» existe abaixo de 1100 px [S4], mas «Compare in detail» no leitor é uma rota direta. Vale para outras rotas ao Compare. | F25, F43 | Inalterado. |
| H19 | Apoia em parte | Os passos informativos têm o aspeto dos botões; só o cursor e o realce diferem. Que a pessoa conclua que «não responde» só se observa. | F32 | Inalterado. |
| H20 | Não avaliável | Sem tarefa. O código mostra a ordem dos dígitos fora da ordem visível. | F33 | Inalterado. |
| H21 | Apoia | Os textos diferem (`home.js:162` contra `g3-onset.json`). | F21 | Inalterado. |
| H22 | Não avaliável | A confiança só se pergunta a pessoas. O mecanismo (limites fora do caminho) apoia-se no código. | F13 | Inalterado. |
| H23 | Apoia | «Reference case» ao lado de «Exploratory finding» [S4, S5, S6]; sentidos só em dicas. | F08 | Inalterado. |
| H24 | Não avaliável | Sem tarefa. A vista Geospatial mostra «Terrain is context only» e «Sources» [S1], o que atenua. | nenhum | Inalterado. |

Totais (24): apoia 13 (H01, H02, H03, H05, H07, H09, H11, H12, H13, H15, H17, H21, H23); apoia em parte 4 (H04, H08, H10, H19); contradiz em parte 3 (H14, H16, H18); não avaliável 4 (H06, H20, H22, H24); contradiz sem reservas 0. Os qualificadores «em parte» marcam que o código ou a captura sustenta só uma metade da previsão.

## 7. O que o estudo humano tem de confirmar

### 7.1 Questões de comportamento (nenhuma se responde por especialista)

1. Se a interpretação de segurança em T2 (Q2a, Q2b) cai em «seguro» com o chip verde, e se a frase de correção chega a ser lida (F01, F02).
2. Se alguém na via (i) de T6 cancela o desafio ou conclui que bloqueou (F19, E2-T6-1).
3. Se «Verified», «Recomputed» e «Refuted» lado a lado levam a juntar integridade com verdade (F04, F06).
4. Se «Where the runs part» é dado como resposta a T4 (F11).
5. Se a leitura de «To goal» é feita sobre a execução certa, e se na janela da máquina do estudo a linha existe (F10, F14).
6. Se «Reference case» ao lado de «Exploratory finding» é lido como validação (F08).
7. Se o resultado das sementes («k/n») é lido como fiabilidade (F07).
8. Se a rota até ao Lab usa «Open in Experiment Lab» ou procura o texto «Change the conditions» (F23).
9. Se a pessoa nota o grupo «Requirements» e, tendo-o aberto, o usa para relaxar o limite (as mitigações estão descritas na secção 3, T7).
10. Se a pessoa sabe voltar de Investigate às execuções (F27).

### 7.2 Condições de ambiente a registar no ensaio

- Largura e altura da janela da máquina do estudo: decidem F10 (altura ≤ 720 px), F14 (pílulas), F16 (cartão abaixo da cena), F25 (menu «More», largura ≤ 1100 px) e F15 (largura ≤ 760 px).
- Tema (escuro ou claro): F28.
- Se a preferência «reduzir movimento» está ligada no Windows da conta do estudo: F18.
- Ordem real da lista «Claims» no ecrã: F20.

### 7.3 Correções sugeridas ao kit (sem as aplicar aqui)

Depois desta passagem, três chaves de resposta de `tasks.md` foram corrigidas (T7, Q5d e Q5b), correspondentes aos pontos 1 a 3 abaixo; estes pontos ficam como registo do que a passagem encontrou. Os restantes pontos não foram aplicados. Esta passagem em si não alterou o kit. A decidir pelo responsável:

1. **T7, critério 3 e apêndice.** O requisito do alvo chama-se «Distance from pad centre» (`domain-rocket/src/catalog.rs:447`; [S8]); «Landing-zone radius (R5)» é o rótulo do **parâmetro de limite** no grupo «Requirements». Reformular o critério ou o apêndice.
2. **T5, Q5d.** O «tick 21» aparece em [S9] ligado ao requisito «Restricted zone stays clear (contract)», não à regra «Truth stays outside the restricted zone». Confirmar o instante da regra de segurança antes de o congelar.
3. **T5, chave.** O chip «Mission» tem «1 not evaluated» ([S3]: «2 of 8 requirements failed, 1 not evaluated, 5 met»); acrescentar à chave e decidir se Q5b o pode referir.
4. **T2, critério 3 e T4, parte 2.** A resposta (sensor «50 m too much height»; rejeição «0.1 s») está no sumário do cartão e no briefing (F31). Decidir se a avaliação lê o que a pessoa **deduz do ecrã de resultados** ou aceita o que lê do cartão; o guião já proíbe ajuda, mas o ecrã mostra a resposta.
5. **Apêndice, item 7** (gráficos de Analyse): os canais «estimate» têm traço tracejado e os «truth» contínuo, com etiqueta de tipo (`charts.js:12-13,226-227`); se «est_z» e «pos_z» ficam no mesmo gráfico depende do campo `group` do registo, não lido.
6. **Apêndice, item 5.** O grupo de «Lateral position gain» no Lab é «Controller tuning» (`domain-rocket/src/catalog.rs:113-124`, `advanced: true`; o Lab não filtra «advanced»: `lab.js:475-476`). A marca «Listed for this failure» depende de R5 estar em foco, o que é o caso por defeito (`lab.js:92`); a confirmar.

### 7.4 Cadeias de resposta que o ensaio tem de confirmar (candidatas, nenhuma lida no ecrã instalado)

| Onde | Cadeia ou valor candidato | Fonte |
| --- | --- | --- |
| T1 | «Landed»; «all 6 requirements met»; «No safety rule broken (5 checked)»; «Every requirement and safety rule met.» | `domain-rocket/src/record.rs:616`; S5, S7; `player.js:818` |
| T2 | «Reached the ground, requirements not met»; «2 of 6 requirements failed»; «No safety rule broken (5 checked)» (nesta execução não visto); «about 33 m/s»; «<= 3 m/s» | `domain-rocket/src/record.rs:647`; `domain-rocket/src/demos.rs:114,125`; S5 |
| T3 | «Largest change:» com a flip de R1 ou R2 e «Baseline: trusts the altimeter fails it; Robust: cross-checks it passes it» | `compare.js:150-163` |
| T4 | Linhas «Altitude error», «Believed height of CoM», «True height of CoM», «Altimeter» («in use» e «rejected»); limiares e instantes por medir | `session.js:102-103,170-175`; S10 |
| T4-alt | «Believed east» e «Believed north» (Flight console, «Perception»); «Mode» «fallback»; tick 6 | `session.js:113,203-205`; `domain-ground/src/catalog.rs:467` |
| T5 | «To goal 0.00 mm» no tick 32; «Mission incomplete»; «2 of 8 requirements failed, 1 not evaluated, 5 met»; «1 of 4 safety rules broken» | S3, S4 |
| T6 | «Refuted»; «Exploratory»; «A reproduced counterexample breaks the claim beyond its tolerance.»; «G3 under a late GNSS bias» | `discover.js:37,417`; `g3-onset.json` |
| T7 | «Lateral position gain» 0,04 (missão) contra 0,12 (predefinido); botões «8 seeds», «16 seeds», «32 seeds»; «Distance from pad centre»; valor que cumpre R5 na semente 5000: por medir | `domain-rocket/src/demos.rs:160`; `domain-rocket/src/catalog.rs:113-124,447`; `lab.js:636` |
| T8 | «Recomputed, every check passed»; «Recompute now»; «Recompute from scratch»; sete passos de navegação; pacote novo já recomputado (derivado de `challenge()` → `verify()`) | `discover.js:299-303,411-412,437,445` |

## 8. Efeito da M19.1 sobre os achados

| Alteração (M19.1) | Achados |
| --- | --- |
| Chip de segurança neutro («held») no leitor, Compare, Lab, Analyse e Flight console (diffs de `requirements.js`, `model.js`, `verification.js`, `control.js`, `lab.js`, CSS) | F01 reduzido (texto igual). A página Runs herda por `model.js`: não verificado na vista. |
| `SAFETY_SCOPE` junto do chip de segurança e removida do fim do cartão (`player.js`) | F02 Corrigido no ramo M19.1 (não instalado) |
| `expectationGloss` por baixo dos textos de demonstração (`compare.js`, `run.js`, `prepare.js`); texto de Rust igual | F03 parcial (a citação «safe» continua; defeito 9 por propor) |
| «Evidence integrity» neutra e etiquetada (`discover.js`, `provenance.js`) | F04 e F06 Corrigido no ramo M19.1 (não instalado); sem captura da lista «Investigations» |
| Ressalva do Lab por cima do numeral «k/n seeds» (`lab.js`, CSS) | F07 parcial (ressalva ainda menor do que o numeral) |
| HUD com `is-minor` só no foguetão (`player.js`, `mission.css`) | F10 Corrigido no ramo M19.1 (não instalado) no domínio terrestre |
| Botão «Go to <instante>» (`player.js`) | F11 parcial (só o texto; crença contra verdade em destaque por fazer) |
| `endChip` sem alteração no diff de `requirements.js`; cor `.ph-end-bad` sem alteração | F36 inalterado |
| `noFailureSentence` (leitor e Lab) e `missionTone` | F12 corrigido (diffs de `player.js`, `requirements.js`, `lab.js`) |
| Frase de ligação para «To goal» e `title` novo | F09 mitigado (a cláusula em falta é classe b, proposta) |
| Pílulas a 1024x640 com nome completo e contagem | F14 mitigado em parte (a execução por defeito continua a ser a primeira) |
| `session.js` só altera o `title` de «To goal» | F34 e F35 inalterados |
| Pluma depois do contacto | H04 em parte |
| Defeito 9 (frases `expectation` com «safe») | **Texto de F03 inalterado** (só a glosa, ver acima) |
| Sem alteração em `home.js`, `missions.js`, `experiences.js`, `main.js`, `ui.js`, `index.html` | F19 a F25, F27, F31, F32, F33, F38, F39, F40 e F42 inalterados; F05 inalterado (o texto verde de «Not refuted within budget» não foi tocado) |

O seguimento da M19.1 está só no ramo `fix/m19.1-honesty`, não instalado. A Fase 1 do kit usa a 0.18.1 sem alteração. Se a M19.1 entrar antes, os resultados mudam de produto e o kit tem de o declarar.

## 9. Decisões e limites em aberto

1. As 24 previsões de `predictions.md` estão cobertas na secção 6.
2. Se o responsável quiser alterar o produto antes da Fase 1 (o que passa a ser outro produto, a declarar), os achados de piso MS ou ME e o F10 são os de maior risco previsto. Esta revisão não propõe alterações de código.
3. As capturas `ux2` e `ux3` podem vir de uma iteração intermédia da 0.18.1 (secção 1). Nada em F01, F08, F09, F14 ou F36 depende só delas: cada um tem também [C].
4. Nada aqui substitui sessões com pessoas. Uma ausência de achado não prova ausência de problema; um achado previsto pode não se observar.

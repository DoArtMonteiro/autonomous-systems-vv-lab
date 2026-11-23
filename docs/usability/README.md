# Estudo de usabilidade do V&V Lab Studio 0.18.1: kit de execução

## Estado deste kit

**Nenhuma sessão foi realizada. Não existem participantes, citações, medições nem resultados.** Todos os formulários estão em branco. As previsões de `predictions.md` são hipóteses escritas antes de qualquer sessão, deduzidas apenas do código da interface e do backlog documentado.

Este kit não altera o estado do requisito M15-R22 de `docs/m15-m18-acceptance.md` (BLOCKED-EXTERNAL). Só sessões realizadas, com dados recolhidos e analisados segundo estes ficheiros, o podem fazer. O kit em si não é evidência de usabilidade.

**As sessões com pessoas estão adiadas.** Neste momento não há participantes humanos disponíveis. O recrutamento só começa quando o responsável o autorizar por escrito e existirem participantes. Todo o trabalho atual é preparação do kit e revisão por especialistas; não é validação empírica de usabilidade.

### O recrutamento está bloqueado até haver autorização e os campos obrigatórios estarem preenchidos

Não se contacta nenhuma pessoa, e não se envia o convite, o aviso de privacidade nem o consentimento, enquanto não houver autorização escrita do responsável e estes campos de `screener-and-consent.md` estiverem em branco: **responsável pelo tratamento e contacto**, **destinatários e ferramentas** (voz, partilha de ecrã, armazenamento), **base de transferência** se o moderador estiver fora da União Europeia, **declaração de quem modera** (incluindo se é o autor do produto), **datas de retenção**, **prazo de eliminação dos dados de seleção de quem não participa** e **versão do SUS**. Os campos estão marcados com `[PREENCHER ANTES DO RECRUTAMENTO]`. Uma pessoa só pode ser recrutada com a lista verificada (`observation-form.md`, parte H).

## Objetivo

Observar pessoas reais a usar o Studio 0.18.1 instalado, sem alteração na Fase 1 e na versão alterada da Fase 2, nas tarefas do circuito central: escolher uma missão, executá-la, perceber o resultado e a causa, comparar duas execuções, encontrar o instante em que a crença do controlador e a verdade se afastam, desafiar uma alegação, testar uma mitigação e verificar a evidência.

O estudo procura descobrir problemas (sobretudo de interpretação de segurança e de evidência) e comparar a Fase 1 com a Fase 2, depois de alterações. Não estima taxas nem mede desempenho.

## Perguntas de investigação

- **PI1.** Um engenheiro ou revisor técnico independente (incluindo auditores de V&V) consegue escolher e executar uma missão e chegar ao resultado sem ajuda?
- **PI2.** Interpretam o resultado da missão e as regras de segurança como dois veredictos separados, ou concluem que o veículo é "seguro" por causa do chip «No safety rule broken»?
- **PI3.** Conseguem dizer qual é a diferença mais importante entre duas execuções e atribuí-la à execução certa?
- **PI4.** Encontram o afastamento entre o que o controlador julga e a verdade, e distinguem-no de «Where the runs part» (afastamento entre execuções)?
- **PI5.** Interpretam corretamente uma missão terrestre em que «To goal» mostra 0.00 mm ao lado de «Mission incomplete»?
- **PI6.** Conseguem desafiar uma alegação e ler o veredicto sem lhe atribuir mais alcance do que tem?
- **PI7.** Conseguem testar uma mitigação sem a "obter" por relaxar o requisito, e percebem que uma execução não generaliza?
- **PI8.** Encontram a verificação da evidência e distinguem integridade da evidência (recomputação) de verdade da alegação?
- **PI9.** Que previsões de `predictions.md` se observam, e que problemas não previstos surgem?
- **PI10 (Fase 2).** As alterações removem os problemas da Fase 1, nas mesmas tarefas, sem criar problemas novos?

## Âmbito e exclusões

Dentro do âmbito: compreensão, orientação, vocabulário, interpretação de veredictos, fluxo entre espaços de trabalho (Mission Control, Missions, Experiment, Investigate, Compare, Analyse).

Fora do âmbito, por decisão do desenho:

- **A Cinematic View opcional (botão «Open Cinematic View») está excluída.** O módulo não está instalado na máquina do estudo, e o botão fica desativado. Não se avalia qualidade de renderização nem fluidez, em nenhuma vista.
- Acessibilidade com tecnologias de apoio (leitor de ecrã), contraste sobre imagens e instalação em máquinas limpas. Não são avaliados e não se podem inferir.
- Desempenho, arranque e memória: já medidos fora da simulação (`docs/evidence/m18/installed-0.18.1/perf/`).

## Fases

| | Fase 1 (piloto) | Fase 2 |
| --- | --- | --- |
| Pessoas | 3 (perfil E) | 5 (perfil E), diferentes das da Fase 1 |
| Produto | 0.18.1 instalado, sem alteração | versão alterada após a análise da Fase 1 (já não é a 0.18.1 inalterada); versão e alterações registadas em `analysis-template.md` |
| Tarefas | T1 a T8, `tasks.md` | as mesmas T1 a T8, com os mesmos critérios de sucesso |
| Formato | 60 minutos previstos, 70 no máximo, moderado, pensar em voz alta | igual |
| Objetivo | descobrir problemas e testar as previsões | verificar se os problemas foram removidos; descobrir problemas novos |

A Fase 2 só começa depois de a análise da Fase 1 estar escrita e de o responsável ter decidido, por escrito, o que se altera e o que fica (`analysis-template.md`, registo de decisões).

## Perfil dos participantes

Só se recrutam pessoas com 18 anos ou mais. O público principal são engenheiros técnicos e revisores técnicos independentes. As fases 1 e 2 têm **um só perfil**, definido pelo questionário de seleção (`screener-and-consent.md`):

- **E (engenheiro ou revisor técnico):** pelo menos 2 anos de experiência profissional ou académica em robótica ou autonomia, aeroespacial, software crítico, verificação e testes, engenharia de controlo, ou auditoria e revisão técnica independente (incluindo auditores de V&V).

Todas as pessoas da Fase 1 (3) e da Fase 2 (5) são E. Se faltarem candidatos E, o responsável decide por escrito se adia; não se substitui o perfil em silêncio.

Um perfil N (novato, sem experiência nas áreas acima) seria um **estudo secundário opcional e futuro, fora deste kit**: não tem quotas, formulários nem limiares aqui. Se o responsável o decidir, escreve primeiro o seu desenho; entretanto, ninguém com perfil N entra nas fases 1 e 2 nem nos números n = 3 e n = 5.

## Papéis

- **Participante.** Usa a máquina Windows do estudo, na conta local dedicada, em presença. Nunca recebe controlo do PC principal do responsável nem usa a sessão de ambiente de trabalho remoto.
- **Moderador.** Única voz dirigida ao participante. Segue `moderator-script.md` à letra. Não ajuda além da escada de ajuda. Se for o autor do produto, declara-o ao participante (consentimento) e no relatório.
- **Anotador.** Silencioso durante as tarefas. Preenche `observation-form.md`, marca tempos e classifica erros. Classifica a gravidade de forma independente do moderador (`severity-and-measures.md`).
- **Responsável pelo estudo.** Decide, guarda os dados e a tabela de ligação, aprova as alterações entre fases. O responsável é também o autor do produto: se for ele o moderador, declara-o no relatório (viés de autoria) e o anotador deve ser outra pessoa.
- **Apoio técnico.** Repõe o estado inicial e trata de falhas da máquina do estudo ou da ligação de voz. Pode ser o moderador entre tarefas, nunca durante uma tarefa.

Mínimo de duas pessoas por sessão (moderador e anotador). Se só houver uma, a sessão marca-se "observador único" e as contagens são lidas com cautela adicional.

## Logística

### Disposição técnica

1. **Máquina separada.** Os participantes usam uma máquina Windows dedicada ao estudo, numa **conta local dedicada, sem ficheiros pessoais**, sem sessão iniciada em contas pessoais e sem ligação ao PC principal do responsável. O participante acede à máquina do estudo **em presença**. O PC principal e a sessão de ambiente de trabalho remoto nunca são usados por participantes. Este conjunto não prevê acesso à distância; usá-lo exigiria uma nova versão do conjunto, aprovada pelo responsável.
2. **Produto.** O Studio 0.18.1 está instalado nessa máquina a partir do instalador cujo SHA-256 foi verificado: `0e37bbcf7228b7170ab392966b0cdc79b2e7446280e801cc9912c16bb0ebd0e1` (hash do instalador 0.18.1 registado em `docs/m15-m18-acceptance.md`). O hash do ficheiro usado regista-se na lista de estado inicial. O módulo Cinematic **não** está instalado.
3. Canal de voz entre participante e moderador, se o moderador não estiver na sala. Ferramenta a decidir pelo responsável.
4. O moderador e o anotador veem o ecrã do participante em tempo real (na sala ou por partilha de ecrã). Sem esta vista, a sessão não se realiza. Qualquer ferramenta de partilha entra na lista de destinatários e ferramentas do consentimento.
5. Sem gravação de ecrã nem de áudio por omissão. Ver "Ética e tratamento de dados".

Se a máquina ou a ligação de voz falharem mais de 30 s numa tarefa, o relógio dessa tarefa para, o anotador regista um incidente de ambiente e a sessão retoma. Se a falha durar mais de 5 minutos, a sessão remarca-se e conta-se como não realizada.

### Estado inicial do produto (a repor antes de cada sessão)

As preferências persistem (tema, filtro da biblioteca de missões, vista do leitor, velocidade, ambiente), o Lab mantém a experiência anterior e o cartão de alegação mostra «Latest challenge in this library». Por isso, entre participantes, o estado muda se nada for reposto.

Reposição recomendada (decisão do responsável): guardar, antes do ensaio, uma cópia da pasta da biblioteca (Settings, secção Library) e restaurá-la antes de cada sessão. Se não for possível, preencher a lista de estado inicial do formulário (`observation-form.md`, parte A) e registar as diferenças. Onde as preferências ficam guardadas, e se restaurar a pasta da biblioteca também repõe as preferências e o estado de Investigate (investigações e verificações), não está documentado nos ficheiros lidos. O ensaio verifica o que persiste de visível e lista o que a cópia não repõe; esses itens passam para a lista de estado inicial.

Lista mínima, a confirmar no ensaio:

- Settings, secção Version: «Studio» mostra 0.18.1. Confirmar que o módulo Cinematic não está instalado (secção do módulo em Settings).
- Tema e tamanho da janela fixos e registados. Abaixo de 1100 px de largura, Configure, Analyse, Compare e Runs passam para o menu «More»; o ensaio regista se isso acontece com o ecrã da máquina do estudo. A 1024x640 as pílulas de execuções não selecionadas cortam as condições (backlog documentado).
- Home aberto em Mission Control; Missions com filtros em «All» e «Both domains»; leitor em «Engineering»; nenhuma experiência aberta no Lab.
- Estado de Investigate fixo: o pacote de investigação preparado e já recomputado da alegação «G3 under a late GNSS bias» existe sempre, igual para todos (`tasks.md`, T6 e T8). Os pacotes criados por participantes não existem no início de cada sessão.
- Dados pessoais: o cabeçalho de Runs e Settings mostram a localização da biblioteca. Com a conta dedicada, o ensaio verifica se aparece algum nome de utilizador ou caminho pessoal. Nenhum caminho entra nos dados do estudo.
- Conta local dedicada sem ficheiros pessoais, notificações desligadas, outras aplicações fechadas.

### Ensaio técnico (antes da Fase 1, não conta como participante)

Uma pessoa que não é participante percorre T1 a T8 com o moderador e o anotador, para:

- preencher a chave de respostas em branco de `tasks.md` (valores lidos no ecrã, nunca de memória);
- confirmar cada rótulo citado contra a interface instalada;
- medir o tempo de cada missão e a duração de um desafio novo em Investigate (T6), e preparar o pacote de investigação recomputado;
- confirmar os limites e o plano de 60 minutos;
- testar a máquina do estudo, a vista do moderador e a reposição do estado, e verificar o hash do instalador.

A chave fica congelada antes da primeira sessão e é igual na Fase 2, salvo registo explícito.

### Fuso horário e calendário

O responsável está no estrangeiro. As sessões marcam-se em horas razoáveis para o participante. O anotador regista a hora local do PC e a do participante.

### Plano de tempo (60 minutos)

| Minutos | Bloco |
| --- | --- |
| 0 a 5 | Receção, confirmação oral do consentimento (enviado com antecedência), preparação |
| 5 a 8 | Aquecimento de pensar em voz alta (sem produto) |
| 8 a 10 | Primeira impressão do ecrã inicial |
| 10 a 49 | Tarefas T1 a T8, **incluindo** perguntas de compreensão, confiança, nota de dificuldade e reposição (total previsto 39 minutos; limites da ação em `tasks.md`) |
| 49 a 52 | Questionário SUS |
| 52 a 56 | Conversa final |
| 56 a 60 | Esclarecimentos e agradecimento |

A sessão é anunciada como "60 a 70 minutos": 60 previstos, 70 no máximo. A regra de corte de tarefas (fim projetado acima do minuto 53; primeiro os segmentos opcionais, depois T5, T3, T7, T4; nunca T1, T2, T6, T8) está em `tasks.md`. O minuto 53 deixa 11 minutos para SUS, conversa final e esclarecimentos, ou seja, a sessão acaba no máximo ao minuto 64, com 6 de margem até ao limite.

**Paragem rígida aos 70 minutos.** O que se perde, por esta ordem, se o tempo acabar: (1) o SUS, se não puder começar até ao minuto 59 (fica "não feito", registado; ver `severity-and-measures.md`, M5); (2) as perguntas 1, 2, 4 e 5 da conversa final. Nunca se perdem a pergunta 3 da conversa final (calibração) nem o esclarecimento de segurança e de evidência do fecho (`moderator-script.md`, secção 13). O ensaio confirma ou corrige estes tempos antes da Fase 1; se não couberem, o responsável decide entre prolongar a sessão e retirar uma tarefa nomeada para todos, nas duas fases.

## Lista de materiais

Antes de cada sessão, marcar:

- [ ] Guião do moderador impresso ou aberto (`moderator-script.md`)
- [ ] Aviso de privacidade breve enviado antes do questionário de seleção (`screener-and-consent.md`)
- [ ] Consentimento enviado com antecedência e confirmado (`screener-and-consent.md`)
- [ ] Lista de pseudónimos e tabela de ligação (ficheiro separado, acesso restrito)
- [ ] Cartões de tarefa (texto do participante de `tasks.md`), em papel, ou noutra janela ou dispositivo fora do Studio
- [ ] Formulário de observação, uma cópia por participante (`observation-form.md`)
- [ ] Chave de respostas preenchida no ensaio (`tasks.md`)
- [ ] Dois relógios (tarefa e sessão), ou um com voltas
- [ ] Formulário SUS e folha de conversa final
- [ ] Lista de estado inicial e registo de incidentes
- [ ] Máquina do estudo com conta local dedicada sem ficheiros pessoais
- [ ] Studio 0.18.1 instalado do instalador com SHA-256 verificado; Cinematic não instalado
- [ ] Biblioteca reposta e pacote de investigação preparado presente
- [ ] Janela com o tamanho registado
- [ ] Lista de verificação pré-recrutamento (`observation-form.md`, parte H) completa
- [ ] Plano B: contacto para remarcar se a máquina ou a ligação falharem

## Ética e tratamento de dados

- **Consentimento informado.** O participante recebe a folha de informação e o consentimento antes da sessão, pode fazer perguntas e confirma oralmente no início. Texto em `screener-and-consent.md`.
- **Voluntariedade e retirada.** A participação é voluntária. O participante pode parar, saltar uma tarefa ou retirar-se em qualquer momento, sem dar razão e sem consequências. Pode pedir a eliminação dos seus dados enquanto a tabela de ligação existir; depois disso os dados são anónimos e já não é possível identificá-los.
- **Aviso antes do questionário.** Antes de qualquer pergunta de seleção, o candidato recebe um aviso de privacidade breve (`screener-and-consent.md`). Os dados de seleção de quem não é selecionado, ou não quer participar, são apagados no prazo fixado pelo responsável (campo `[PREENCHER ANTES DO RECRUTAMENTO]`).
- **Dados mínimos.** Recolhem-se: pseudónimo (P1-01 a P1-03 na Fase 1, P2-01 a P2-05 na Fase 2), perfil (E), faixa de anos de experiência, autoavaliação de leitura de inglês (S2), **profissão ou área atual em texto livre curto (S4)**, **necessidades de adaptação, se a pessoa as indicar (S8; opcional, sem dados de saúde pedidos)**, relação com o projeto e com o responsável (S5 e S6, só o resultado), declaração de maioridade, notas do que fez e disse, tempos, respostas, SUS. O texto livre de S4 e S8 é dado pessoal: guarda-se apenas na ficha de seleção, ligada ao pseudónimo, e não nas notas de observação. Não se recolhe imagem, nem se anota o nome nas notas.
- **Pseudonimização.** O nome e o contacto ficam apenas na tabela de ligação e no consentimento assinado, guardados à parte dos dados do estudo.
- **Gravação.** Sem gravação de ecrã. Áudio só com consentimento explícito e separado; o áudio é **dado pessoal** (voz identificável), guardado em local restrito e apagado no prazo indicado no consentimento. Confirmar que nenhuma ferramenta de voz ou de partilha de ecrã grava por omissão.
- **Responsável pelo tratamento, destinatários e transferências.** O responsável pelo tratamento e o seu contacto, os destinatários e as ferramentas usadas (voz, partilha de ecrã, armazenamento) são **campos a preencher pelo responsável antes do recrutamento** (`screener-and-consent.md`). Se o moderador ou o anotador estiverem fora da União Europeia, o consentimento indica a base de transferência.
- **Autoria e viés.** O moderador pode ser o autor do produto; o participante é informado disso antes de consentir.
- **Retenção (proposta, a confirmar pelo responsável).** Tabela de ligação e consentimentos assinados: apagados 90 dias depois da última sessão do estudo. Notas e medições: guardadas sem identificação. Gravações, se houver consentimento: apagadas em 14 dias, depois de confirmadas as citações.
- **Publicação.** Só resultados agregados e citações anónimas com permissão. Sem nomes, caminhos pessoais ou contactos no repositório. Os resultados descrevem o que foi observado e os limites.
- **Respeito pelo participante.** Em T2 e T5 podem surgir interpretações erradas de segurança. A conversa final corrige-as depois de recolhidos os dados, para que ninguém saia com uma ideia errada sobre segurança.

Não se assume revisão por comissão de ética. Se o responsável estiver sujeito a regras institucionais que a exijam, verificar antes da Fase 1.

## Limites e riscos do desenho

- Com n = 3 e n = 5 só se descobrem problemas; não se medem taxas. Detalhes em `severity-and-measures.md`.
- As tarefas visam problemas já conhecidos do backlog. Os resultados servem para confirmar ou refutar previsões e encontrar problemas novos, não para estimar a frequência dos problemas.
- O autor do produto concebeu as tarefas e pode moderar: risco de condução. Mitigado pelo guião, pela proibição de confirmar respostas e pela classificação independente do anotador.
- O tempo nas tarefas mistura pensar em voz alta, leitura em inglês e pausas; não é desempenho do produto.
- A máquina do estudo tem um ecrã e um hardware próprios: o resultado não vale para outros tamanhos de janela (a 1024x640 e abaixo de 1100 px a interface muda).
- A interface está em inglês. Quem participa lê inglês técnico; o resultado não vale para quem não o lê.
- Os participantes são engenheiros e revisores técnicos (perfil E): o resultado não vale para novatos nem para outros públicos.
- Voluntários recrutados na rede do responsável tendem a ser benevolentes.
- Fase 1 e Fase 2 usam pessoas diferentes: a comparação é por contagens, nunca por testes estatísticos.

## Ficheiros do kit

| Ficheiro | Conteúdo |
| --- | --- |
| `README.md` | este ficheiro |
| `predictions.md` | previsões de falha escritas antes das sessões |
| `screener-and-consent.md` | questionário de seleção e consentimento |
| `moderator-script.md` | guião palavra a palavra, ajuda permitida e proibida, escada de ajuda, tempos |
| `tasks.md` | tarefas T1 a T8, critérios, erros críticos, verificações de compreensão |
| `observation-form.md` | formulários em branco |
| `severity-and-measures.md` | escala de gravidade, medidas, limiares, limites de inferência |
| `analysis-template.md` | síntese e registo de problemas em branco |

## Decisões em aberto para o responsável

1. **Autorização do recrutamento e campos obrigatórios** (bloqueiam o recrutamento): autorização escrita do responsável e existência de participantes; responsável pelo tratamento e contacto; destinatários e ferramentas; base de transferência; declaração de quem modera; prazo de eliminação dos dados de seleção de quem não participa.
2. Quem modera e onde está (o responsável está no estrangeiro), quem anota, e onde está a máquina do estudo (o acesso dos participantes é sempre em presença; o questionário de seleção, S1, depende disto).
3. Ferramenta do canal de voz e forma de o moderador ver o ecrã em tempo real, sem gravação.
4. Reposição do estado: restaurar uma cópia da biblioteca, ou usar a lista de estado inicial.
5. Incentivo aos participantes, se houver.
6. Retenção: confirmar os 90 dias e o apagamento das gravações em 14 dias; fixar o prazo de eliminação dos dados de seleção de quem não participa.
7. SUS: usar a versão validada em português europeu ou o original inglês (ver `severity-and-measures.md`); conferir o texto dos itens com a fonte antes de usar.
8. Orçamento de tempo: se o ensaio mostrar que as 8 tarefas com perguntas não cabem nos 39 minutos, escolher entre prolongar a sessão e retirar uma tarefa nomeada, para todos, nas duas fases.
9. T4 ou T4-alt: decidido no ensaio pela regra pré-declarada em `tasks.md`.

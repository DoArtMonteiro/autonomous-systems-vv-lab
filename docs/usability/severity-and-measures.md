# Gravidade, medidas e limites de inferência

Tudo o que está neste ficheiro é declarado **antes** das sessões. Nenhum limiar se altera depois de ver dados. Se uma alteração for inevitável, regista-se como adenda datada, com o motivo, e os dados já vistos são relatados com as duas regras.

## Códigos usados nos formulários

### Conclusão de uma tarefa

| Código | Significado |
| --- | --- |
| **S** | Cumpriu todos os critérios de sucesso sem ajuda dos níveis L1 ou superiores. Sondas L0 não contam como ajuda. |
| **A** | Cumpriu todos os critérios depois de uma ajuda L1 ou L2. |
| **F** | Não cumpriu os critérios dentro do limite, precisou de L3 ou desistiu. |
| **X** | Tarefa não alcançada (cortada por tempo). Não é falha. |

**Conclusão** = S ou A. **Conclusão sem ajuda** = S.

### Escada de ajuda

L0 sonda neutra (não conta), L1 região do ecrã, L2 tipo de sítio, L3 demonstração. Definição e redação em `moderator-script.md`.

### Classes de erro

- **E1:** deslize, corrigido de imediato pela própria pessoa.
- **E2:** desvio (ir ao sítio errado) com recuperação sem ajuda.
- **E3:** ação errada com consequência (perde estado, substitui uma experiência, interpreta mal e prossegue).
- **CE-Tn-k:** erro crítico da tarefa Tn, definido em `tasks.md`.

### Classes de interpretação errada

- **MS:** interpretação errada de segurança (por exemplo, "o veículo foi seguro" porque «No safety rule broken»).
- **ME:** interpretação errada de evidência (por exemplo, confundir integridade da recomputação com verdade da alegação; ler «k/n» como fiabilidade; ler «Where the runs part» como crença contra verdade).
- **MO:** outra interpretação errada (resultado, grandeza, execução).

Uma **interpretação errada crítica** é uma ocorrência de MS ou ME. Conta-se uma vez por participante e tarefa.

### Confiança e calibração

Depois de cada pergunta de segurança ou de evidência (marcada † em `tasks.md`), a pessoa dá a confiança de 1 (nada certo/a) a 5 (totalmente certo/a), uma por pergunta, **antes** de qualquer reação do moderador.

- **Calibrada:** resposta correta (C) com confiança 4 ou 5, ou incorreta (I) com confiança 1 ou 2.
- **Excesso de confiança:** resposta incorreta (I) com confiança 4 ou 5.
- **Falta de confiança:** resposta correta (C) com confiança 1 ou 2.
- Confiança 3 é "neutra" e não conta nas três categorias. Respostas parciais (P) não entram na calibração.

## Escala de gravidade (0 a 4)

| Nível | Nome | Critério |
| --- | --- | --- |
| **0** | Não é problema | Discordância entre observadores ou comportamento que, observado, não afeta a tarefa nem a compreensão. Fica no registo para não se repetir a discussão. |
| **1** | Cosmético | Notado, comentado ou causa uma pequena hesitação. Sem efeito na tarefa nem numa conclusão. |
| **2** | Menor | Causa um desvio, um erro E1 ou E2, ou uma queixa clara; a pessoa recupera sozinha e termina. |
| **3** | Maior | Causa falha (F), ajuda L2, ação errada com consequência (E3), perda de tempo grande, ou **qualquer interpretação errada de segurança ou de evidência (MS ou ME)**. |
| **4** | Bloqueante | Causa falha mesmo com ajuda, ou uma interpretação errada de segurança ou de evidência mantida com confiança 4 ou 5 depois de a pessoa ter a informação toda no ecrã (excesso de confiança), ou impede um passo do circuito central a 2 ou mais participantes. |

### Regras de decisão

1. **Piso para segurança e evidência.** Qualquer interpretação errada de segurança ou de evidência (MS, ME) tem gravidade mínima 3, seja qual for a frequência, o tempo perdido ou a recuperação.
2. **Excesso de confiança.** Uma interpretação errada MS ou ME com confiança 4 ou 5 é gravidade 4.
3. **Frequência.** Se um problema de gravidade 1 ou 2 afeta a maioria dos participantes da fase (2 de 3 na Fase 1; 3 de 5 na Fase 2), sobe um nível. A frequência nunca baixa uma gravidade.
4. **Gravidade final** é o máximo entre a regra do critério, o piso (1) e as subidas (2 e 3).
5. **Duas pessoas classificam, em separado.** Moderador e anotador classificam antes de discutir. Se discordam, fica a gravidade mais alta e regista-se a discordância. Em sessões de observador único, regista-se "classificador único".
6. **Gravidade 3 ou 4 em qualquer participante** exige decisão escrita do responsável antes da Fase 2: alterar, adiar com motivo, ou recusar com motivo. Não se deixa passar em silêncio.
7. **Gravidade 4, ou o mesmo problema de gravidade 3 em 2 ou mais participantes**, exige alteração antes da Fase 2 ou, na Fase 2, impede a aceitação. Na Fase 2, qualquer problema MS ou ME (gravidade 3 ou 4), persistente ou novo e mesmo num só participante, também impede a aceitação (a quantidade de ocorrências só muda a decisão do responsável sobre o que fazer, não a não aceitação).
8. **Gravidades 0, 1 e 2** ficam registadas. Agrupam-se por localização no código e tratam-se por lote.
9. **Problemas de ambiente** (falhas da máquina, do som ou da partilha de ecrã) e de procedimento do estudo não são problemas do produto e não têm gravidade; ficam no registo de incidentes.
10. Problemas novos na Fase 2 têm a mesma escala. Um problema da Fase 1 que reaparece na Fase 2 marca-se "persistente".

## Medidas de sucesso

Todas se relatam por tarefa e por fase, em contagens (por exemplo "2 de 3"). Todos os participantes das fases 1 e 2 têm o perfil E (engenheiro ou revisor técnico). **Não se calculam percentagens nem intervalos de confiança** com estes números.

### M1. Conclusão de tarefa

Número de participantes com S ou A, por tarefa.

### M2. Conclusão sem ajuda

Número de participantes com S, por tarefa.

### M3. Exatidão de compreensão

Número de participantes com resposta C, por verificação de compreensão. P e I contam como não corretas. As respostas P guardam-se à parte.

### M4. Interpretações erradas críticas

Número de participantes com pelo menos uma interpretação errada MS ou ME, por tarefa e no total. Relatam-se também os CE por código.

### M5. SUS (System Usability Scale)

Pontuação 0 a 100 por participante (regra de cálculo em `observation-form.md`). Relata-se participante a participante e a mediana. O ponto de referência habitualmente citado para um SUS "médio" é cerca de 68 (Sauro e Lewis); usa-se apenas como referência de leitura, nunca como teste.

O SUS mede a perceção global depois de uma sessão curta, com um produto que tem um circuito muito técnico. Não resolve problemas específicos e, com 3 ou 5 pessoas, pouco diz.

Se a paragem rígida aos 70 minutos impedir o SUS de uma pessoa (não puder começar até ao minuto 59), fica "SUS não feito", registado com a hora, e essa pessoa não entra na mediana nem no mínimo. M5 só se avalia se pelo menos 2 de 3 (Fase 1) ou 4 de 5 (Fase 2) fizerem o SUS; caso contrário fica "não avaliado", e não "não cumprido".

Versão do questionário: existe uma versão validada em português europeu (validação europeia portuguesa da SUS, Procedia Computer Science, 2015, vol. 67, pp. 293 a 300, DOI 10.1016/j.procs.2015.09.273). O texto dessa versão não está copiado neste kit. O texto inglês dos dez itens reproduzido em `observation-form.md` foi escrito de memória do original de Brooke (1996) e **não foi conferido com uma fonte nesta preparação**: conferir antes do primeiro uso. O responsável obtém-no na publicação e decide antes da Fase 1 entre essa versão e o original inglês que consta de `observation-form.md`. Como a interface está em inglês e se exige leitura de inglês, ambas são admissíveis; a escolha fica fixa na Fase 2.

### M6. Calibração da confiança

Por participante e total: número de respostas calibradas, com excesso de confiança e com falta de confiança (definições acima), com uma confiança por pergunta marcada † em `tasks.md`. A confiança de 1 a 5 na pergunta final sobre confiar nos resultados para um foguetão real (H22) relata-se à parte.

### M7. Tempo em tarefa e ajudas

Tempo (sem pausas) e número de ajudas L1 ou superiores, por tarefa. Só descritivos. O tempo mistura pensar em voz alta, leitura em inglês e pausas; não é desempenho do produto e não tem limiar além do limite de cada tarefa.

### M8. SEQ

Dificuldade de 1 (muito difícil) a 7 (muito fácil) depois de cada tarefa, só descritiva.

## Limiares de aceitação pré-declarados

Estes limiares definem o que se considera **aceitável** nesta versão, em contagens. Não são testes estatísticos. **Aplicam-se à fase inteira** (todos os participantes da fase, sem separar perfis). A aceitação da Fase 2 exige **todos** os limiares seguintes.

| Medida | Fase 1 (n = 3): aceitável se | Fase 2 (n = 5): aceitável se |
| --- | --- | --- |
| M2, T1, T2 e T3 (entrada) | pelo menos 2 de 3 com S, em cada tarefa | pelo menos 4 de 5 com S, em cada tarefa |
| M1 e M2, T4 (ou T4-alt), T6, T7 e T8 (passos especializados) | M1: pelo menos 2 de 3 com S ou A | M2: pelo menos 3 de 5 com S; M1: pelo menos 4 de 5 com S ou A |
| M2, T5 | pelo menos 2 de 3 com S | pelo menos 4 de 5 com S |
| M3, cada verificação de compreensão de T2, T5, T6, T7, T8 | pelo menos 2 de 3 com C | pelo menos 4 de 5 com C |
| M3, restantes verificações | pelo menos 2 de 3 com C | pelo menos 3 de 5 com C |
| M4, interpretações erradas críticas (MS, ME) | **0 de 3** | **0 de 5** |
| M6, excesso de confiança em verificações de segurança ou de evidência | 0 ocorrências | 0 ocorrências |
| M5, SUS (entre quem o fez; "não avaliado" se o fizerem menos de 2 de 3 ou 4 de 5) | mediana pelo menos 68 e nenhum participante abaixo de 50 | mediana pelo menos 68 e nenhum participante abaixo de 50 |
| Gravidade | nenhum problema de gravidade 4 em aberto; todos os de gravidade 3 com decisão escrita | nenhum problema de gravidade 4; nenhum problema MS ou ME (gravidade 3 ou 4), persistente ou novo; nenhum outro problema de gravidade 3 em 2 ou mais participantes |

Leitura:

- Na Fase 1 os limiares **não** decidem uma aprovação: servem para decidir prioridades. Um limiar falhado indica trabalho a fazer.
- Na Fase 2 a falha de qualquer limiar significa "não aceite nesta fase", com as causas listadas. Uma ocorrência de MS ou ME (1 de 5) fica "não aceite, problema residual", com decisão escrita do responsável.
- Uma tarefa alcançada por menos de 2 de 3 (Fase 1) ou 4 de 5 (Fase 2) participantes é "não avaliada", e não se avalia o limiar.
- Os limiares valem para a fase inteira, que tem só participantes de perfil E. Se um dia houver um estudo secundário com novatos (perfil N), é outro estudo, com desenho e limiares próprios, e os seus resultados nunca entram nestes números.
- Os cortes por tempo (regra em `tasks.md`) reduzem o número de participantes que alcançaram cada tarefa; o limiar de uma tarefa só se avalia se ela tiver sido alcançada pelo mínimo acima.

## Limites de inferência

### O que n = 3 e n = 5 permitem

- **Descobrir problemas.** Observar um problema uma só vez mostra que existe, e a gravidade avalia-se pelo que causou.
- **Gerar hipóteses** sobre causas e correções.
- **Confirmar que uma previsão se pode verificar** (observada) com pelo menos uma ocorrência.

### O que não permitem

- **Estimar frequências.** "2 de 3" não é "67 %". Uma só pessoa a falhar numa tarefa não permite concluir que o problema é raro.
- **Afirmar que não existe um problema.** "Não observado" com n = 3 ou n = 5 não prova ausência. Veja-se a probabilidade de um problema ser visto pelo menos uma vez:

| Proporção de pessoas afetadas (p) | n = 3 | n = 5 | n = 8 |
| --- | --- | --- | --- |
| 10 % | 27 % | 41 % | 57 % |
| 20 % | 49 % | 67 % | 83 % |
| 30 % | 66 % | 83 % | 94 % |
| 50 % | 88 % | 97 % | 99 % |

Estes valores supõem participantes independentes e a mesma probabilidade para todos, o que não é o caso (áreas de experiência diferentes dentro do perfil E, sessões moderadas, tarefas dirigidas), por isso são **limites otimistas**. A regra habitual "5 pessoas encontram cerca de 85 % dos problemas" só vale para um tipo homogéneo de utilizador e problemas que afetam pelo menos cerca de 31 % das pessoas; o perfil E reúne áreas diferentes (autonomia, verificação, controlo, auditoria), por isso não se assume homogeneidade.

- **Comparar fases com testes.** Fase 1 e Fase 2 são grupos diferentes, pequenos e, em parte, preparados por tarefas dirigidas. A diferença entre "2 de 3" e "1 de 5" é compatível com acaso. Só se relatam as contagens lado a lado, com a lista de alterações e a sua localização, sem valores p, sem "melhoria significativa", sem intervalos.
- **Generalizar.** As pessoas são voluntários da rede do responsável, engenheiros ou revisores técnicos (nada se conclui sobre novatos), leem inglês, e usam uma só máquina de estudo com um ecrã próprio.

### Viéses reconhecidos

1. **Viés de autoria.** O autor concebeu as tarefas e pode moderar. Mitigação: guião, proibição de confirmar, classificação independente.
2. **Tarefas dirigidas.** As tarefas visam problemas já conhecidos. Os resultados não estimam a frequência de problemas em uso espontâneo.
3. **Ambiente.** Um só ecrã e um só hardware. Os tempos mistos e a fluidez gráfica não se interpretam como desempenho.
4. **Efeito de pensar em voz alta.** Altera o comportamento e o tempo.
5. **Aprendizagem entre tarefas.** O que se vê numa tarefa ajuda a seguinte. A ordem é fixa, por isso o efeito é igual para todos, mas as tarefas tardias (T6 a T8) beneficiam e podem parecer mais fáceis.
6. **Corte por tempo.** As tarefas tardias ficam mais vezes por alcançar; ver regra de corte.
7. **Benevolência.** Voluntários próximos do responsável tendem a suavizar a crítica.
8. **Uma só moderação por fase** (pode ser uma só pessoa) pode introduzir estilo próprio.

## Regras de relato

- Declarar sempre n, fase, perfil (E) e versão do produto.
- Relatar problemas, gravidades, localização e contagens. Nunca percentagens.
- Distinguir sempre "observado", "não observado", "não alcançado" e "não aplicável".
- Não usar a expressão "o programa é usável" nem "testado com utilizadores" como resultado geral. Dizer, por exemplo, "3 sessões piloto: problemas encontrados e gravidades".
- Descrever os limites de cada relatório, como acima.

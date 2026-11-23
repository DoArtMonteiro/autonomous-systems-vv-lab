# Perguntas ao revisor

São 25 perguntas, em 6 grupos. A pergunta 25 pertence ao grupo C; foi numerada no fim para não renumerar as outras. As de prioridade «alta» estão assinaladas: correspondem a fraquezas encontradas pelo autor do pacote ao ler o protocolo e refazer as contas, e cada uma diz porque importa. As de prioridade «média» e «baixa» pedem juízo sobre escolhas legítimas mas discutíveis.

Cada pergunta tem um bloco de resposta. Preencha-o copiando para um ficheiro à parte; veja o formulário geral no fim.

- **concordo**: o protocolo está bem neste ponto.
- **preocupação**: o protocolo pode ser congelado, mas este ponto deve melhorar ou ficar explícito.
- **bloqueio**: não deve ser congelado sem resolver este ponto.

Referências: «l. N» é a linha N de `docs/m15-g3-onset-protocol.md` no commit `bec7b3f`. «Verif. N» é a secção N de `independent-checks.md`.

## Resumo das prioridades

| N.º | Grupo | Tema | Prioridade |
| --- | --- | --- | --- |
| 1 | Validade de construção | Ruído limitado e modelo idealizado: o que se pode dizer da fronteira | média |
| 2 | Validade de construção | R1 contra R5: a frase «um viés maior é mais seguro» e o perfil de requisitos | média |
| 3 | Validade de construção | Os 8 inícios: dois são equivalentes e o início a 20 s fica a 3 s do contacto | **alta** |
| 4 | Validade de construção | As bandas deixam de fora a zona 10,5 a 13,5 m | média |
| 5 | Identificação causal | Janela de decisão do mediador | média |
| 6 | Identificação causal | G0 contra `robust`: o contraste isola a regra 1? | média |
| 7 | Identificação causal | O braço N muda mais do que a rejeição | média |
| 8 | Identificação causal | Classificação das hipóteses: preditiva, corolário, a posteriori; M1 e M2 sem classe | **alta** |
| 9 | Estatística e multiplicidade | Proporções agregadas: uma célula inteira pode falhar | **alta** |
| 10 | Estatística e multiplicidade | A fronteira π ≥ 0,9 e a potência das hipóteses primárias | média |
| 11 | Estatística e multiplicidade | Bonferroni dentro de uma conjunção; famílias sem controlo global | média |
| 12 | Estatística e multiplicidade | S4 e S5: regra pontual 54/60, McNemar redundante e erro «63» | **alta** |
| 13 | Estatística e multiplicidade | H3: estimando, mediana de b_s e tolerância de 1 m | média |
| 14 | Estatística e multiplicidade | Orçamento de regressão: denominadores e previsão de falha | **alta** |
| 25 | Estatística e multiplicidade | H1 é uma conjunção: a taxa a 0 s e a potência | **alta** |
| 15 | Sementes e fuga de informação | Independência entre sementes e entre etapas | média |
| 16 | Sementes e fuga de informação | A lista de sementes proibidas e a ausência de guarda no simulador | **alta** |
| 17 | Sementes e fuga de informação | Pré-registo sem ocultação e níveis escolhidos com dados à vista | média |
| 18 | Sementes e fuga de informação | Erros, repetições e etapa inválida | média |
| 19 | Executor e proveniência | O executor por escrever: está especificado o suficiente? | **alta** |
| 20 | Executor e proveniência | Hash do código desatualizado, citações de linha e hash do binário | **alta** |
| 21 | Executor e proveniência | «Sem espreitar» por convenção e prova de ordem de commits | média |
| 22 | Relatório | Palavras permitidas e a frase de confirmação | média |
| 23 | Relatório | Análises descritivas, caminhos possíveis e resultado negativo | baixa |
| 24 | Relatório | Como incorporar as correções do revisor | baixa |

---

## A. Validade de construção

### 1. Ruído limitado e modelo idealizado

**Pergunta.** O ruído dos sensores é uma soma de quatro uniformes, limitada (suporte finito) a ±2√3 σ (GNSS 0,5 m ⇒ máximo de 1,73 m; altímetro 0,1 m ⇒ 0,35 m) e as dispersões iniciais são uniformes (`crates/vv-rocket/src/prng.rs`, `landing_model.rs`). O resultado «b* ≈ 12 m» depende de um transitório de 0,3 s cuja margem sobre o limiar (3 m) é, perto de b*, comparável ao ruído. Aceita que o protocolo teste uma fronteira cuja **posição** é uma propriedade do simulador e não do problema físico? Que redação mínima de limitações exigiria?

**Porque importa.** A frase de confirmação (l. 145) fala de «cerca de 12 m» sem nomear o simulador nem o ruído. Com ruído de cauda pesada, ou com outra relação limiar/ruído, a fronteira muda.

**Evidência.** `study-summary.md`, «Contexto»; `limitations.md`.

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

### 2. R1 contra R5

**Pergunta.** O protocolo põe R1 como primário e reporta R5, R2 e «aterra com todos os requisitos» ao lado (l. 102). No caso registado com início 0 s e 15 m, R5 falha em 30 de 30 execuções (`investigation.json`, `baseline_violations`), por isso nessa condição a aterragem nunca cumpre todos os requisitos e a proteção da regra 1 troca uma falha (R1) por outra (R5). Isto não se generaliza ao G3 inteiro, que abrange 5 a 30 m: a 5 m o desvio horizontal esperado é da ordem da magnitude (o viés horizontal é só em x), isto é, dentro do raio de 10 m, e R5 a 5 m não foi verificado neste pacote. Há evidência parcial de desenvolvimento: no M9, com viés desde 0 s, `guarded` recuperou 6 de 30 execuções de magnitude 5,7 a 12,6 m, com R5 entre 4,18 e 9,92 m (0,73 a 0,97 vezes a magnitude) (`docs/m9-powered-landing.md`, l. 627). São dados de desenvolvimento, não confirmação, e não cobrem inícios posteriores. É adequado que a hipótese primária seja só sobre R1? A frase confirmatória (l. 145), «acima disso R1 volta a cumprir-se», é suficiente se vem sempre acompanhada do perfil de R5?

**Porque importa.** Uma conclusão correta sobre R1 pode ser lida como boa notícia de segurança. O protocolo mitiga com a regra de nomear o requisito; falta saber se o revisor a considera suficiente.

**Evidência.** `study-summary.md`, «A alegação e o problema».

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

### 3. Os 8 inícios (prioridade alta)

**Pergunta.** (a) Os inícios 0,01 s e 0,1 s são a **mesma condição física** no simulador (o protocolo di-lo na l. 18, mas T continua a contá-los como dois): o GNSS mede a cada 0,1 s (passos 0, 10, 20, ...; `landing_sim.rs:211`), por isso um início em (0; 0,1] s só se vê na medida de 0,1 s, e as duas execuções diferem só nas sementes. Em T há 7 condições distintas, não 8. (b) Não há inícios entre 0,1 e 1 s, onde o estimador ainda tem poucas medidas, nem fases diferentes do ciclo de 0,1 s. (c) Com contacto nominal por volta de 23,3 a 23,6 s (`docs/m9-powered-landing.md`, l. 241: 23,63 s para `baseline` e 23,27 s para `robust`, no caso nominal do M9, semente 0; não é medida de `guarded` no caso do G3) e dispersão uniforme de ±50 m em altitude e ±10 m/s em velocidade vertical, o início a 20 s deixa cerca de 3 s; o tempo restante nas sementes dispersas não foi medido neste pacote. A frase «qualquer início em (0; 20] s» é extrapolação razoável de 7 condições?

**Porque importa.** H1 e H2 afirmam algo para todo o intervalo (0; 20] s. Cada banda (n = 160) tem 20 sementes por início, mas os inícios 0,01 s e 0,1 s são uma só condição (40 sementes), e as condições extremas (0,1 e 20 s) são as mais prováveis de se comportar de forma diferente. Se o início a 20 s deixar de ter tempo para a regra 1 atuar em algumas sementes, as falhas de H2 ficam concentradas nele (ver pergunta 9).

**Evidência.** `landing_sim.rs:211`, `landing_sensors.rs:79-80`; M13 (`docs/m13-discovery-lab.md`, l. 59: «o início reduzido de 0,02 s não tem significado próprio»).

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

### 4. As bandas deixam de fora 10,5 a 13,5 m

**Pergunta.** H1 usa {5; 7; 9; 10,5} m e H2 {13,5; 17; 22; 30} m. A zona entre 10,5 e 13,5 m, onde está a fronteira, só é testada em H3, a 5 s (e S1, a 15 s). Os níveis foram escolhidos com dados de desenvolvimento à vista (l. 193). É aceitável que o enunciado «abaixo de cerca de 12 m falha, acima volta» seja suportado, nos outros 6 inícios, apenas por duas bandas afastadas da fronteira?

**Porque importa.** A localização da fronteira para os inícios que não são 5 nem 15 s é um corolário do modelo (invariância com o início), não um teste.

**Evidência.** `study-summary.md`, «Hipóteses e classificação».

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

---

## B. Identificação causal

### 5. Janela de decisão do mediador

**Pergunta.** O mediador é a primeira rejeição em [início; início + 1,0 s] (l. 32, 103). O modelo põe a primeira rejeição a +0,58 s a 12 m, +0,18 s a 15 m e +0,08 s a 30 m (Verif. 7). Com ruído, perto de b* a rejeição pode ficar além de 1 s. A janela de 1 s é justificável sem olhar para dados, e a sensibilidade a 0,5 s e 2 s (descritiva, l. 192) basta?

**Porque importa.** S4, S5 e S6 e a tabela 2×2 de C2 usam a janela. Uma janela mal escolhida muda o denominador de S6 e pode converter «rejeição tardia» em «sem rejeição».

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

### 6. G0 contra `robust`: o contraste isola a regra 1?

**Pergunta.** A intervenção S4 compara `guarded` com `ascent_abort_vz_mps` = 100 (regra 2 desligada) contra `robust`. A leitura do código diz que os dois diferem só na regra 1 (`landing_types.rs:35-42`, `landing_controller.rs:180, 196, 226`), e que até à primeira rejeição os comandos são idênticos. Uma via que a lista não tem: a regra 1 altera `h_base`, que entra no tempo até ao contacto (`landing_controller.rs:254`, `t_raw`) e, pelo fator `fade`, no guiamento lateral depois da rejeição; `h_base` entra também no corte de motor (`landing_controller.rs:219`) e no limite de inclinação (`landing_controller.rs:269`). As verificações estruturais (l. 76) são o teste dessa leitura. Concorda que um único desvio basta para suspender S4? Há alguma outra via de diferença (por exemplo, o campo `sensor_disagreement` ou o corte de motor a 15 m) que devia estar na lista?

**Porque importa.** S4 é a base de «regra 1 é o componente ativo». Se G0 e `robust` diferirem noutro ponto, a atribuição à regra 1 fica contaminada.

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

### 7. O braço N muda mais do que a rejeição

**Pergunta.** O braço N (limiar de 1000 m) torna a rejeição impossível: o altímetro é sempre admitido e continua a corrigir posição e velocidade com o GNSS enviesado. Isto isola a necessidade da rejeição, mas também altera o estado do estimador (o erro de velocidade que o resíduo persistente cria, l. 30), não só a ativação da regra 1. Concorda que S5 mostra «a rejeição é necessária» e que S4 mostra «a regra 1 é o que atua depois dela», e que juntas dão o «mecanismo confirmado» da l. 147? Falta um terceiro contraste?

**Porque importa.** O protocolo reconhece o duplo efeito, mas a regra de decisão trata S4 e S5 como complementares sem dizer que a identificação do componente depende de os dois serem lidos juntos.

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

### 8. Classificação das hipóteses (prioridade alta)

**Pergunta.** (a) H1 é «P2 generalizada» e H2 é «P1»; mas P2 foi prevista só a 8 m e P1 só a 5 s e só para a posição da fronteira. A «recuperação» acima de 13,5 m em todos os inícios vem de dados M13 já vistos. Devem H1 e H2 continuar a chamar-se «preditivas»? (b) M1 e M2 não têm classe no protocolo; pelo conteúdo, M1 é a posteriori (o M13 já a apoiou) e M2 mistura corolário e resultado M13. (c) O autor tinha visto a transição grosseira entre 10 e 15 m antes de escrever o modelo (l. 54): isso reduz o valor de H3 como previsão?

**Porque importa.** A classificação decide quanto peso o leitor dá a uma «confirmação»: uma hipótese a posteriori confirmada com sementes novas é confirmação do efeito, não uma previsão cumprida.

**Evidência.** `study-summary.md`, «Hipóteses e classificação».

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

---

## C. Estatística e multiplicidade

### 9. Proporções agregadas: uma célula inteira pode falhar (prioridade alta)

**Pergunta.** H1 e H2 testam a proporção agregada em 160 sementes, com limiar 154 (toleram 6 falhas). Cada célula (um início, uma magnitude) tem 5 sementes. Uma célula inteira (5 falhas) mais uma semente extra ainda deixa H1 «confirmada». Por exemplo, o início a 20 s com magnitude 10,5 m pode falhar por completo sem que isso apareça no veredicto. O protocolo reporta o perfil por condição? Deve haver um critério por início, ou um mínimo por célula?

**Porque importa.** A frase de confirmação fala de qualquer início. O teste agregado só garante que, na média sobre a grelha, a proporção excede 0,9. Além disso, π é uma proporção sobre uma grelha escolhida pelos autores (8 inícios, 4 magnitudes, pesos iguais), não sobre uma população de falhas.

**Evidência.** Verif. 3.

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

### 10. A fronteira π ≥ 0,9 e a potência das primárias

**Pergunta.** A hipótese nula é π ≤ 0,9, a convenção do motor (a mesma que se usa para «eficaz»). Com n = 160 e α = 0,01/3, a potência de H1 e H2 é 0,31 se π = 0,95, 0,79 se 0,97 e 0,9988 se 0,99 (Verif. 3). Está certo que as hipóteses primárias fiquem «inconclusivas» com probabilidade 0,69 num sistema com π = 0,95? Porque 0,9?

**Porque importa.** Um resultado inconclusivo é a saída mais provável se o efeito for ligeiramente menos nítido do que nos dados de desenvolvimento. O protocolo declara-o, mas não justifica 0,9 além da convenção.

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

### 11. Bonferroni numa conjunção; famílias sem controlo global

**Pergunta.** O «achado M14 confirmado» exige H1, H2 e H3 todas confirmadas (l. 145). Para uma conjunção em que todas têm de rejeitar, cada teste pode usar o nível total (0,01) sem inflacionar o erro (teste de interseção-união); usar 0,01/3 só perde potência. Por outro lado, as três famílias (primária, secundária, mitigação) usam cada uma 0,01, o que dá até 0,03 no conjunto, e os seis limites de Clopper-Pearson a 99 % do orçamento (3 categorias × 2 mitigações) não têm correção. É coerente?

**Porque importa.** A correção está aplicada onde não ajuda (conjunção) e ausente onde faria falta (entre famílias e orçamentos). A potência de H1 e H2 (pergunta 10) melhoraria com o nível 0,01.

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

### 12. S4 e S5: regra pontual 54/60, McNemar redundante e o erro «63» (prioridade alta)

**Pergunta.** Em S4 e S5 (60 pares por condição), a confirmação exige McNemar exato com p < 0,01/14 **e** fração ≥ 0,9. Recalculou-se (Verif. 5): bastam 11 pares discordantes no sentido previsto para o McNemar; a regra da fração, com 54 de 60, implica um p de 4,9 × 10⁻¹¹ mesmo com os restantes 6 em sentido contrário. O McNemar nunca decide. A regra da fração é uma estimativa pontual: passa com probabilidade 0,18 se a taxa verdadeira for 0,85 e 0,03 se for 0,80; o limite inferior a 99 % de 54/60 é 0,774. A linha 115 diz que seriam precisas 63 sementes para um teste binomial ao nível 0,01/14; a conta dá 69 (63 é para 0,01/7). Prefere uma regra com inferência (por exemplo, o binomial com n maior) ou aceita a regra do motor tal como está? O erro «63» deve ser corrigido antes de congelar?

**Porque importa.** «Mecanismo confirmado» (l. 147) depende de S4 e S5. Se a regra aceita taxas verdadeiras de 0,85 com probabilidade quase 1 em 5, a palavra «confirmado» é mais forte do que a evidência.

**Evidência.** Verif. 4 e 5.

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

### 13. H3: estimando, mediana de b_s e tolerância de 1 m

**Pergunta.** (a) Em `prediction.json`, b50 é a magnitude interpolada em que R1 se cumpre em metade das execuções (11,89 m). No protocolo (l. 104), b50 é a mediana de b_s, o menor nível a partir do qual R1 se cumpre em todos os seguintes, numa grelha de 0,25 m (12,0 m nos dados de desenvolvimento, por cálculo). São estimandos diferentes; é aceitável a mudança? (b) A tolerância de 1 m é maior do que a largura da transição observada (cerca de 1,25 m); H3 é, como o protocolo diz, fraca. Preferia S2 (0,5 m) como critério primário? (c) A precisão de H3 foi calculada com 20 sementes e dois deslocamentos escolhidos pelo autor (Verif. 8). (d) As sementes não monótonas são «contadas e reportadas», mas entram no cálculo da mediana?

**Porque importa.** H3 é a única hipótese primária sobre um valor numérico. O estimando muda entre a previsão e o teste, e a tolerância não discrimina.

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

### 14. Orçamento de regressão: denominadores e previsão de falha (prioridade alta)

**Pergunta.** (a) Os denominadores contam só pares em que a mitigação «pode atuar» (l. 123). Em D com início tardio, 80 dos 320 pares são a 15 m, onde a rejeição já acontece sem mitigação (b* ≈ 12 m); e a etapa E inclui famílias saturadas, que o protocolo diz só contarem para invariantes e R2 a R6 (l. 131), embora o denominador de 480 as inclua. O critério «pode atuar» aplica-se de forma consistente? (b) No M13, os 35 compromissos do envelope (26 em R2 e 9 em R5) são descritos como pares que «deixam de cair» (`docs/m13-discovery-lab.md`, l. 52), mas o código conta um compromisso sempre que o braço mitigado ganha uma violação de requisito sem regressão de R1 (`exec/src/investigate.rs:1159-1172`), incluindo pares dos 744 em que R1 não mudou. A taxa condicional fica, portanto, entre 35/1 024 = 3,4 % e 35/280 = 12,5 %, conforme a distribuição dos 35 (Verif. 9; as contagens estão no pacote M13, a distribuição não). (c) O protocolo prevê, antes de executar, que o orçamento de compromissos «é provável que seja excedido». Um orçamento cujo resultado esperado é o fracasso está bem desenhado? Que informação dá?

**Porque importa.** O limite superior de Clopper-Pearson sobre os 480 pares mede a taxa na mistura de condições escolhida, que só se relaciona com o risco real se a mistura for representativa. E o orçamento só pode dizer «dentro» ou «fora», sem graduar o dano.

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

### 25. H1 é uma conjunção: a taxa a 0 s e a potência (prioridade alta)

**Pergunta.** O sucesso de H1 é uma conjunção na mesma semente: R1 cumpre-se com início 0 s **e** falha com o início tardio (l. 109). O G3 registado só garante R1 em pelo menos 27 de 30 execuções a 0 s, isto é, uma taxa de 0,9 no mínimo. Se a taxa a 0 s for, por exemplo, 0,93 (compatível com o G3), π de H1 não passa de 0,93 mesmo com mascaramento perfeito no início tardio, e a potência cai muito (ver `independent-checks.md`, nota junto da Verif. 3). A tabela de potência do protocolo (l. 180 a 183) trata π como uma taxa única. Os dados de desenvolvimento têm 30 de 30 a 0 s em todas as magnitudes (`docs/m14-evidence-robustness.md`, F6), por isso π ≈ 1 é plausível, mas não está garantido. Deve a taxa a 0 s ser reportada à parte e a potência ser apresentada em função dela? Deve H1 separar os dois componentes?

**Porque importa.** Uma queda do componente a 0 s, que não é o que H1 quer testar, pode fazer H1 ficar inconclusiva ou ser refutada por causa de uma propriedade do G3 já registado.

**Evidência.** `independent-checks.md`, Verif. 3.

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

---

## D. Sementes e fuga de informação

### 15. Independência entre sementes e entre etapas

**Pergunta.** Cada etapa usa um bloco contíguo de sementes. Os fluxos aleatórios são `SplitMix64` com estado inicial `seed ^ (fonte × 0x9E3779B97F4A7C15)` e avanço do mesmo valor `0x9E3779B97F4A7C15` (`prng.rs`). O protocolo afirma que as etapas «podem ser lidas como evidência independente» (l. 155) e que as sementes são independentes (l. 108). Isto é assumido, não mostrado. Há algum risco de correlação entre fluxos de sementes vizinhas ou de fontes diferentes? Basta usar blocos disjuntos, ou deveria o protocolo pedir sementes dispersas por uma função de dispersão?

**Porque importa.** A independência entre sementes é a base de todos os testes binomiais. Este pacote não a avaliou e não usou valores de sementes protegidos.

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

### 16. A lista de sementes proibidas e a ausência de guarda no simulador (prioridade alta)

**Pergunta.** (a) A linha 153 proíbe «as sementes protegidas do foguetão em `exec/src/seeds.rs`»; essa lista (`ROCKET_PROTECTED`) contém 3000 a 3099, 6000 a 6099 e **44000 a 44999**. À letra, proíbe as sementes do próprio protocolo. (b) `vv-rocket land` não tem guarda de sementes (`main.rs:32-37`); a única barreira para 44000 a 44999 ou 50000 a 59999 é o executor por escrever. Não há forma de mostrar, a partir do repositório, que nenhuma semente destes intervalos correu antes do congelamento. (c) Os ensaios do executor usam 41900 a 41999, classificadas como já vistas. Que redação e que evidência de «nunca corridas» considera suficientes?

**Porque importa.** O valor confirmatório do estudo depende de as sementes serem virgens. É uma afirmação negativa sem registo que a sustente.

**Evidência.** Verif. 2.

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

### 17. Pré-registo sem ocultação, níveis escolhidos com dados à vista

**Pergunta.** O mesmo agente desenhou o modelo, os testes de desenvolvimento e o protocolo, e os níveis de magnitude, os inícios e as tolerâncias foram escolhidos depois de ver os dados (l. 193). O protocolo argumenta que isso «favorece efeitos grandes, não as conclusões», porque as sementes são novas. Aceita? Haveria uma forma barata de reduzir o risco, como um revisor externo escolher ou confirmar os níveis antes do congelamento?

**Porque importa.** Se os níveis foram escolhidos onde o efeito é nítido, a confirmação testa «o efeito existe onde se foi procurar», não «existe no envelope declarado».

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

### 18. Erros, repetições e etapa inválida

**Pergunta.** Uma execução que falha é repetida uma vez com a mesma semente, e se falhar de novo conta **contra** a hipótese (l. 117). O simulador é determinístico, por isso uma repetição só ajuda com falhas de infraestrutura; `no_contact` e R1 não avaliado repetem-se sempre. Se mais de 1 % das execuções de uma etapa falharem, a etapa é «inválida» e não é substituída, mas as hipóteses dessa etapa ficam sem regra. «Contra a hipótese» é simétrico? (Em H1, uma falha conta como não-sucesso; em S3, igual; em M1, igual; mas para o orçamento, uma execução em falta pode esconder um evento.) Que deve acontecer às hipóteses de uma etapa inválida?

**Porque importa.** Uma regra de erro assimétrica pode favorecer ou penalizar um dos resultados sem que isso seja visível no relatório.

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

---

## E. Executor e proveniência

### 19. O executor por escrever: está especificado o suficiente? (prioridade alta)

**Pergunta.** O protocolo aprova a escrita de dois scripts depois, mas o comportamento de cada cálculo não está especificado: pontos Halton (bases 2 e 3, índice a partir de 1, «quantizados como lá», isto é, `to_q` com 2^32 e `snap` por quantum), aplicação dos ponteiros JSON, ordem das execuções, forma de os valores flutuantes serem escritos no caso (por exemplo `7.130000000000001`), formato do registo. O executor chama `vv-rocket land` pela linha de comandos, enquanto a evidência do M13 vem de `vv-exec` em processo; a equivalência de bytes entre os dois só foi verificada numa amostra pequena (`docs/m14-evidence-robustness.md`, l. 46). Deve a aprovação exigir uma especificação escrita e um teste de equivalência em sementes de desenvolvimento antes do congelamento?

**Porque importa.** Uma divergência silenciosa (por exemplo, um nível de magnitude ou um início que difere na última casa decimal) altera os números sem ninguém dar por isso. O congelamento fixa os scripts por hash, mas não diz se estão certos.

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

### 20. Hash do código desatualizado, citações de linha e hash do binário (prioridade alta)

**Pergunta.** (a) A linha 166 cita «hoje `12b276cb...`» para o `source_sha256` do `vv-rocket`; em `bec7b3f` o valor é `295a45b2...`. Só `landing_model.rs` mudou (um esquema de caso novo, `vv-rocket-landing.v2`); não está demonstrado aqui que os casos `v1` dão saídas iguais. Que verificação exige antes do congelamento, e qual das duas versões é a de referência? (b) Duas citações de linha (l. 33, l. 133) estão desatualizadas. Devem ser substituídas por nomes de função e hashes? (c) O sha256 do binário depende do compilador e da máquina; só liga uma execução a uma construção. Para que serve, além do `source_sha256`?

**Porque importa.** O protocolo pede congelar o hash exato. Um valor desatualizado no próprio texto mostra que o hash «de hoje» pode mudar entre a revisão e o congelamento. Um erro destes só se descobre quando o executor se recusa a correr.

**Evidência.** `source-commitments.md`.

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

### 21. «Sem espreitar» por convenção e prova de ordem de commits

**Pergunta.** O executor «só escreve um registo com hashes» e o script de análise lê-o uma vez (l. 118), mas cada execução deixa `verification.json` e `trace.json` em disco, e a convenção não é imposta tecnicamente. A prova de que o congelamento antecede a primeira execução é a ordem de commits e as suas datas, escolhidas por quem os cria; o M14 já assumiu essa fraqueza (`docs/m14-evidence-robustness.md`, l. 131). Que medida mínima (etiqueta assinada, repositório de outra pessoa, registo de tempo externo, saída num diretório selado) consideraria proporcionada?

**Porque importa.** A credibilidade do pré-registo depende de a ordem ser verificável por terceiros.

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

---

## F. Relatório

### 22. Palavras permitidas e a frase de confirmação

**Pergunta.** O protocolo permite dizer «confirmado», «achado M14 confirmado» e «mecanismo confirmado» (l. 145 a 147), e «candidata a adoção» para uma mitigação (l. 133). Os resultados são de uma simulação idealizada, sem dados de voo. A frase proposta inclui «o G3 deixa de valer para R1 abaixo de cerca de 12 m», embora o protocolo diga que o G3 registado não muda. Que verbos e que limitações obrigatórias exigiria na própria frase?

**Porque importa.** A frase é o que um leitor sem acesso ao protocolo vai levar. «Confirmado» num contexto de simulação costuma ser lido como mais forte do que é.

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

### 23. Análises descritivas, caminhos possíveis e resultado negativo

**Pergunta.** Além dos testes, o protocolo prevê tabelas 2×2 (C2), sensibilidade da janela a 0,5 s e 2 s, a taxa diluída com todos os pares, famílias saturadas, e um relatório do perfil por requisito. Para evitar caminhos de análise ramificados, a lista dos relatórios descritivos devia ser fechada antes do congelamento? E que obrigação de publicação e de descrição deve haver se H1 ou H2 forem refutadas?

**Porque importa.** O protocolo diz que publica «qualquer que seja o resultado». Falta fixar o que cada resultado negativo obriga a dizer.

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

### 24. Como incorporar as correções do revisor

**Pergunta.** O protocolo diz que qualquer alteração produz um novo candidato que volta à decisão do responsável (l. 200). As correções que o revisor pedir (por exemplo, as das perguntas 12, 16 e 20) mudam o texto e os hashes. Que processo propõe para não confundir uma correção editorial (o erro «63») com uma alteração ao desenho (as bandas, os níveis, os orçamentos)?

**Porque importa.** Se qualquer correção reinicia o ciclo, há um incentivo a não corrigir erros pequenos.

**Resposta:** [ ] concordo  [ ] preocupação  [ ] bloqueio
**Comentário:**

---

## Formulário geral

```
Revisor (nome ou iniciais, à sua escolha):
Data:
Tempo gasto, aproximado:
Formação relevante (por exemplo, estatística, controlo, aeroespacial, verificação de software):

Recomendação global (não vincula o responsável):
[ ] Congelar tal como está
[ ] Congelar depois das correções que marquei como «preocupação»
[ ] Não congelar até resolver os «bloqueios»
[ ] Não congelar; o desenho precisa de ser repensado

Perguntas marcadas «bloqueio» (números):
Perguntas marcadas «preocupação» (números):

Erros que encontrei em independent-checks.md, study-summary.md ou source-commitments.md:

Algo que o protocolo devia dizer e não diz:

Algo que o protocolo diz e devia deixar de dizer:

Conflitos de interesse ou ligação ao projeto (se existir):

Declaro que li o protocolo e este pacote, que não corri nenhuma das sementes
44000 a 44999 nem 50000 a 59999, e que não editei o protocolo.
```

O canal concreto para devolver o formulário e o prazo não estão definidos neste pacote; indique-os quem enviar o pacote.

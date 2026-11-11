# Protocolo de confirmação do G3 com viés GNSS tardio (candidato M15)

## Estado

**Candidato a protocolo congelado. Não congelado, não executado, à espera de autorização do responsável.** Substitui, como proposta, o rascunho `docs/m14-g3-onset-protocol-draft.md`, que fica inalterado. Todos os resultados sobre o instante de início do viés continuam **exploratórios** até o responsável autorizar a execução e o congelamento ficar num commit anterior à primeira simulação.

O critério G3 do M9.1 não muda. Foi registado e suportado com o viés presente desde 0 s; este protocolo testa hipóteses novas sobre inícios posteriores.

Este candidato foi escrito e revisto por agentes. **Revisão por agentes não é revisão humana por pares.** Recomenda-se, antes de aprovar, a leitura por um engenheiro que não participou no M13, no M14 nem no M15.

Nenhuma simulação foi corrida para escrever este documento. As únicas contas feitas usam o modelo determinístico já publicado (`scripts/m14_masking_model.py`, sem simulador nem sementes) e a evidência guardada em `docs/evidence/m14/masking/test.json`; estão descritas em «Cálculos de preparação».

## Mecanismo, segundo o código

Fontes: `crates/vv-rocket/src/landing_controller.rs`, `landing_sensors.rs`, `landing_sim.rs`, `landing_model.rs`, `landing_types.rs`.

- **Viés.** `gnss_bias` soma a mesma magnitude a x e a z da posição GNSS (`landing_sensors.rs:79-80`); a velocidade GNSS não é enviesada.
- **Inicialização.** As políticas `robust` e `guarded` inicializam o estimador na primeira medida GNSS, no passo 0 (`landing_controller.rs:98-106`). O GNSS mede a cada 5 ciclos de controlo, isto é, a cada 0,1 s (`landing_sim.rs:211`; caso: `dt_s` 0,01, `control_period_steps` 2, `gnss_period_cycles` 5). Um início em 0 s inicializa o estimador já enviesado; qualquer início em (0; 0,1] s só aparece na medida de 0,1 s, com o estimador já inicializado sem viés.
- **Rejeição.** Em cada ciclo com amostra do altímetro, se |resíduo| > `altimeter_residual_threshold_m` (3 m), a correção do altímetro **não é aplicada nesse ciclo** e um contador sobe; ao fim de `altimeter_rejection_cycles` (5) ciclos seguidos, `rejected` passa a verdadeiro. Um único resíduo dentro do limiar repõe o contador e a bandeira e volta a corrigir (`landing_controller.rs:119-133`). A rejeição não é permanente por construção.
- **Regra 1.** Só no `guarded` (`landing_types.rs:35-37`) e só enquanto `rejected` é verdadeiro, o guiamento usa a menor de duas altitudes, a estimada e a do altímetro. O estado do estimador não muda (`landing_controller.rs:192-200`).
- **Lateral.** O guiamento lateral usa `p_base.x` estimado (`landing_controller.rs:247-252`), que segue o GNSS enviesado com ou sem rejeição. A regra 1 não corrige a posição horizontal.
- **Políticas.** `robust` e `guarded` usam o mesmo `update_robust` (`landing_controller.rs:68-69`). Diferem só na regra 1 e na regra 2 (corte por subida, `landing_types.rs:40-42`).
- **Registo.** `controller_flags.altimeter_rejected_first` grava o passo exato da primeira rejeição (`landing_sim.rs:221-224`). O teste M14 mediu a rejeição a partir das amostras do traço, gravadas a cada 0,1 s (`scripts/m14_masking_model.py:138`).

**Cronologia no modelo** (`scripts/m14_masking_model.py`, ganhos do caso, sem ruído): depois de um início tardio, o resíduo atinge o máximo 0,3 s após o início, com valor 0,250 vezes a magnitude (1,25 m a 5 m; 2,00 m a 8 m; 2,43 m a 9,72 m; 2,88 m a 11,5 m), e desce depois para cerca de 0,22 vezes a magnitude. Logo, o modelo decide a rejeição no transitório: acima de b*, a primeira rejeição surge 0,58 s (12 m), 0,18 s (15 m) e 0,08 s (30 m) depois do início, sem readmissões; abaixo de b*, nunca. Como a primeira ultrapassagem do limiar já suspende a correção, b* não depende de `altimeter_rejection_cycles` (11,989 m com 3, 5 e 10 ciclos) e vale cerca de 4 vezes o limiar (3,996 m com 1 m; 7,992 m com 2 m; 11,989 m com 3 m). O modelo também dá b* = 11,989 m para qualquer início entre 0,01 e 20 s, porque ignora o veículo.

### Interpretação causal da rejeição

- **Não é confundidor.** A rejeição é posterior ao tratamento (início e magnitude) e não causa nenhum dos dois.
- **É mediador e condição de ativação.** Cadeia: início e magnitude → transitório do resíduo → ultrapassagem do limiar → `rejected` → regra 1 → altitude de guiamento → R1. A rejeição tem também um efeito lateral: suspende as correções do altímetro e com elas o erro de velocidade que o resíduo persistente cria (no modelo, −5,09 m/s a 8 m, `prediction.json`, `steady_state_at_8m`).
- **Necessária, não suficiente.** No M13 (desenvolvimento), tornar a rejeição impossível no registo fez R1 falhar em 30 de 30; no M9, o `robust`, que rejeita o altímetro mas não tem a regra 1, falhou R1 em 30 de 30 com o viés desde 0 s (`docs/m9-powered-landing.md:353`). O componente ativo é a regra 1.
- **Risco de causalidade inversa.** Uma trajetória que já está a falhar perto do solo pode produzir uma rejeição tardia (a inclinação muda o termo `s_cm * nz` do resíduo). Por isso o mediador deste protocolo é a primeira rejeição **dentro da janela de decisão** [início; início + 1,0 s], lida em `altimeter_rejected_first`. Rejeições depois da janela contam numa categoria própria.
- **Intervenção que isola o mediador.** Manipular o que vem depois da rejeição sem tocar no caminho até ela: `guarded` com a regra 2 desligada (`ascent_abort_vz_mps` = 100, máximo aceite em `landing_model.rs:414-418`) contra `robust`. Até à primeira rejeição os comandos são idênticos; por isso `altimeter_rejected_first` tem de ser igual nos dois braços em cada semente, e a diferença em R1 depois dela só pode vir da regra 1. A intervenção complementar manipula o próprio mediador: limiar de 1000 m (rejeição impossível).

## Alterações face ao rascunho

| # | Rascunho | Problema | Alteração |
| --- | --- | --- | --- |
| 1 | `:3` | Diz que o motor recusa 44000 a 44999. Só o `vv-exec` recusa (`exec/src/investigate.rs:60-70`, `exec/src/seeds.rs:28-32`); `vv-rocket land` não tem guarda de sementes (`crates/vv-rocket/src/main.rs:32-37`). | Executor próprio, com guarda própria (secção «Execução»). |
| 2 | `:34` | Fixa o `vv-exec`, que não corre esta grelha, recusa estas sementes e recusa o grau confirmatório (`investigate.rs:449-458`). Não fixa código de análise. | Fixa executor, análise, fontes e binário do `vv-rocket`. |
| 3 | `:15` | Aplica b* a todos os inícios. A previsão P1 só foi feita para 5 s (`prediction.json`). | b* a 5 s é preditivo; a invariância com o início é corolário do modelo, testada à parte. |
| 4 | `:11`, `:13-17` | Mistura hipóteses previstas e escritas depois dos dados sem as distinguir. | Classificação explícita (secção «Hipóteses»). |
| 5 | `:21-23` | As contas não fecham: 300 sementes para 480 execuções em C1, 300 para 480 em C3, 400 para 1400 pares. Reutilização não especificada. | Mapa semente → condição explícito; emparelhamento declarado. |
| 6 | `:22` | Magnitudes «sorteadas uniformemente» sem gerador nem semente: não congelável. | Níveis fixos. |
| 7 | `:23` | «7 famílias»; a alegação declara 8. | As 8 famílias. |
| 8 | `:27` | «Uma execução refuta» numa fronteira estocástica (11,25 m: 1 de 20; 12,5 m: 20 de 20) e contra a convenção 0,9 do motor; 16 células sem controlo de multiplicidade. | Testes binomiais exatos contra 0,9, Bonferroni por família, regra de três resultados. |
| 9 | `:28` | C2 condiciona numa variável posterior ao tratamento, lida de amostras a 0,1 s. | C2 passa a concordância descritiva; a causalidade é testada por intervenção (S3 a S5). |
| 10 | `:17`, `:29` | «Regressão» só conta segurança. O M13 registou 41 pares que ganharam R2 ou R5 com 1 m. O limiar de 2 m não é avaliado. | Orçamento de regressão em três categorias, as duas mitigações. |
| 11 | ausente | Só R1. No registo (0 s, 15 m), R5 falha em 30 de 30 (`docs/evidence/m13/g3-onset/investigation.json`, `baseline_violations`). | Perfil por requisito como resultado; R5 testado. |
| 12 | ausente | Sem regras para erros, execuções sem contacto nem R1 avaliado. | Regras na secção «Análise». |

## Hipóteses

**Preditivas** (escritas antes dos dados que as testaram pela primeira vez): P1, b* = 11,99 m com início a 5 s, e P2, a 8 m só um início em 0 s evita o mascaramento, fixadas no commit `73c9ff5` (20:20) antes do teste `1195c1b` (20:25). Foram testadas com as sementes 47000 a 47019; esses dados estão gastos e não as confirmam outra vez. O autor tinha visto a transição grosseira entre 10 e 15 m; o que foi previsto é o valor, não a existência da fronteira.

**Corolários do modelo** (calculados agora com o modelo inalterado, compatíveis com dados de desenvolvimento já vistos, por isso não novos): b* não depende do início em (0; 20] s; b* ≈ 4 vezes o limiar; a rejeição tardia, quando existe, acontece no transitório.

**A posteriori** (sugeridas pelos dados de desenvolvimento): o mecanismo `rule1-not-engaged` (depois das sementes 41000 a 41009 e da revisão com 45000 a 45003); a concordância rejeição ⇔ R1 (29 células do teste M14); a troca de R1 por R5 nas magnitudes altas (fragilidade M14, `baseline_violations` M13); os compromissos das mitigações. Só podem ser confirmadas com sementes novas, como aqui.

### Família primária (preditivas; erro de família 0,01, Bonferroni, 0,01/3 por teste)

- **H1, mascaramento (P2 generalizada).** Com início em (0; 20] s e magnitude na banda baixa {5; 7; 9; 10,5} m, R1 cumpre-se com início em 0 s e falha com o início tardio, na mesma semente.
- **H2, recuperação de R1 (P1).** Com início em (0; 20] s e magnitude na banda alta {13,5; 17; 22; 30} m, R1 cumpre-se.
- **H3, fronteira (P1).** Com início a 5 s, a magnitude mediana de transição b50 está a menos de 1 m de b* = 11,99 m. A tolerância de 1 m foi fixada em `prediction.json` e mantém-se, mas não é exigente: a transição observada ocupa cerca de 1,25 m. A distância a b* é reportada sempre; a menos de 0,5 m é critério secundário (S2).

### Família secundária (erro de família 0,01, Bonferroni, 0,01/7 por teste)

- **S1, invariância com o início (corolário).** H3 também com início a 15 s, em plena queima e a cerca de 8 s do contacto nominal.
- **S2, precisão (corolário).** b50 a 5 s a menos de 0,5 m de b*.
- **S3, perfil por requisito (a posteriori).** Com início em 0 s e magnitude na banda alta, R5 falha. Um viés maior troca uma aterragem dura (R1) por uma aterragem fora da plataforma (R5); não a torna segura.
- **S4, regra 1 é o componente ativo (a posteriori).** Com rejeição dentro da janela, `guarded` sem regra 2 cumpre R1 e `robust` falha, na mesma semente.
- **S5, a rejeição é necessária (a posteriori).** Com limiar de 1000 m, R1 falha onde o `guarded` registado cumpre.
- **S6, cronologia (corolário).** Em execuções com início tardio e rejeição, a primeira rejeição ocorre dentro da janela de decisão.
- **S7, mitigação de 2 m desloca a fronteira (corolário).** Com limiar 2 m e início tardio, R1 falha a 5 m e cumpre-se a 10,5 m.

**Verificações estruturais** (determinísticas, sem teste estatístico; uma única exceção refuta a leitura do código e suspende a interpretação de S4): em todas as condições da etapa C, `altimeter_rejected_first` é igual em `guarded` sem regra 2 e em `robust`, semente a semente; na condição mascarada (5 s, 8 m), nas sementes em que nenhum dos dois braços rejeita, os dois dão valores de R1 a R6 iguais bit a bit. As sementes com rejeição nessa condição (raras: 0 de 20 a 8 m no desenvolvimento) são contadas e reportadas, não refutam.

### Família de mitigação (erro de família 0,01, Bonferroni, 0,01/2 por teste)

- **M1, limiar 1 m.** Com início tardio na banda baixa, R1 cumpre-se com a mitigação.
- **M2, limiar 2 m.** Igual a M1, a 10,5 m apenas (a 5 m o modelo prevê o contrário, S7).

## Desenho

Caso base: `exec/cases/m13/g3-registered.json` (política `guarded`, `gnss_bias` de 0 a 40 s). Cada execução altera só os ponteiros indicados. Inícios tardios: T = {0,01; 0,1; 1; 2; 5; 10; 15; 20} s. Mesma semente em braços diferentes é emparelhamento intencional (os fluxos SplitMix64 dependem só da semente); etapas diferentes usam sementes disjuntas.

| Etapa | Sementes | Mapa semente → condição | Braços por semente | Execuções |
| --- | --- | --- | --- | --- |
| A, perfil | 44000 a 44319 (320) | 44000 + 40·i + 5·j + r; i = índice do início em T (0 a 7), j = índice da magnitude em {5; 7; 9; 10,5; 13,5; 17; 22; 30} (0 a 7), r = 0 a 4 | início tardio; início 0 s | 640 |
| B, fronteira | 44320 a 44379 (60) | cada semente em todos os níveis | magnitudes 10,0 a 14,0 m, passo 0,25 (17), com início 5 s e 15 s | 2040 |
| C, mecanismo | 44380 a 44439 (60) | cada semente nas 3 condições | condições (0 s, 15 m), (5 s, 15 m), (5 s, 8 m) × braços G registado, G0 sem regra 2, R `robust`, N limiar 1000 m | 720 |
| D, mitigação | 44440 a 44759 (320) | 44440 + 40·i + 10·j + r; i como em A, j em {5; 8; 10,5; 15} (0 a 3), r = 0 a 9 | {início tardio; 0 s} × {sem; 1 m; 2 m} | 1920 |
| E, famílias | 44760 a 44919 (160) | 44760 + 20·f + k; f = família pela ordem de `g3-onset.json` (0 a 7), k = ponto Halton 0 a 19 | {sem; 1 m; 2 m} | 480 |
| Reserva | 44920 a 44999 (80) | não usada | | 0 |

Total: 920 sementes, 5800 execuções. Os pontos Halton da etapa E usam as bases 2 e 3 (ou 2 numa família de um parâmetro) sobre as gamas declaradas em `g3-onset.json`, a partir do índice 1, quantizados como lá. A reserva não pode ser usada para repetir, completar ou substituir nada desta execução; fica para um protocolo futuro.

## Resultados medidos

Para cada execução, o executor grava: semente, condição, braço, `outcome`, para cada requisito R1 a R6 os campos `evaluated`, `pass` e `value`, para cada invariante S1 a S5 os campos `pass` e primeiro instante de falha, `altimeter_rejected_first`, `sensor_disagreement_first`, o sha256 de `verification.json` e de `trace.json`. Nenhum resultado é lido do traço amostrado.

- **Perfil.** O resultado de uma condição é o vetor de contagens por requisito e por invariante, mais o `outcome`. R1 é o primário; R2, R5 e «aterra com todos os requisitos» são secundários e são sempre reportados ao lado de R1. Nenhum texto pode dizer que um viés é «mais seguro» sem nomear o requisito.
- **Mediador.** Rejeição na janela: `altimeter_rejected_first` em [início; início + 1,0 s] (no início 0 s: em [0; 1,0] s). Rejeição tardia: depois da janela.
- **Transição por semente (etapa B).** b_s = o menor nível a partir do qual R1 se cumpre nesse nível e em todos os seguintes; +∞ se não existir. b50 = mediana de b_s. Sementes não monótonas são contadas e reportadas.

## Análise

- **Proporções.** Teste binomial exato unilateral de H0: π ≤ 0,9, ao nível de cada família. Unidade: a semente (independentes entre sementes).
  - H1: n = 160 sementes da banda baixa, sucesso = R1 cumprido a 0 s e falhado no início tardio.
  - H2: n = 160 sementes da banda alta, sucesso = R1 cumprido no início tardio.
  - S3: n = 160, sucesso = R5 falhado com início 0 s.
  - S6: n = execuções tardias da etapa A com qualquer rejeição (uma por semente; cerca de 160, da banda alta); sucesso = primeira rejeição dentro da janela. A etapa B não entra, porque cada semente gera 34 execuções.
  - S7: duas proporções de n = 80 (etapa D, 2 m, tardio, 5 m e 10,5 m).
  - M1: n = 240 (etapa D, 1 m, tardio, banda baixa); M2: n = 80 (2 m, tardio, 10,5 m).
- **Pares.** S4 e S5: em cada uma das condições (0 s, 15 m) e (5 s, 15 m), separadamente (n = 60 pares cada), McNemar exato unilateral no sentido previsto com p < 0,01/14 e fração de sementes com o resultado previsto ≥ 0,9. A hipótese é confirmada se as duas condições cumprirem. Com 60 sementes, um teste binomial contra 0,9 a este nível é impossível (seriam precisas 63), por isso aplica-se a regra do motor.
- **Fronteira.** H3, S1, S2: intervalo de confiança da mediana sem distribuição, por estatísticas de ordem, a 1 − 2α (equivalência TOST). Com n = 60: posições 20 e 41 para H3 (α = 0,01/3); 19 e 42 para S1 e S2 (α = 0,01/7). O limite inferior conta o nível anterior (b_s está em (nível − 0,25; nível]).
- **Erros.** Uma execução que falha (código diferente de 0, ficheiro em falta, R1 com `evaluated` falso, `no_contact`) é repetida uma vez com a mesma semente; se falhar outra vez, conta **contra** a hipótese em teste. Se mais de 1 % das execuções de uma etapa falharem, a etapa é declarada inválida e não é substituída.
- **Sem espreitar.** Não há análise intermédia nem paragem antecipada. O executor corre todas as execuções e só escreve um registo com hashes; o script de análise lê esse registo uma vez, depois de completo. O único motivo de paragem é uma falha do executor, que é reportada; retomar usa as mesmas sementes e confirma que as execuções já feitas dão os mesmos bytes.
- **Concordância C2.** Reportada por etapa como tabela 2×2 (rejeição na janela × R1), sem teste e sem conclusão causal.

## Orçamento de regressão das mitigações

Um evento é um par em que a mitigação **acrescenta** uma violação que a execução sem mitigação não tinha. Os denominadores contam só os pares em que a mitigação pode atuar: com início em 0 s e magnitude ≥ 5 m, o resíduo excede qualquer dos limiares logo na inicialização e a rejeição acontece a 0,1 s com 1, 2 ou 3 m, por isso esses pares diluiriam a taxa. Pares em que pode atuar: etapa D com início tardio (320 por mitigação) e etapa E (160). Os pares com início 0 s formam uma categoria própria, como verificação. Limite superior de Clopper-Pearson unilateral a 99 %:

| Categoria | Pares | Orçamento | Eventos máximos |
| --- | --- | --- | --- |
| Invariantes S1 a S5 | 480 (D tardio + E) | ≤ 1 % | 0 |
| R2 a R6 (compromissos) | 480 (D tardio + E) | ≤ 5 % | 13 |
| R1 com início 0 s (território do G3 registado) | 320 (D, 0 s) | ≤ 2,5 % | 1 |

Previsão declarada antes da execução: nos dados de desenvolvimento o limiar 1 m teve 35 compromissos em 1024 pares do envelope (3,4 %, limite a 99 % de 4,98 %), contando também células onde não podia atuar, e 6 em 30 no contraexemplo. **É provável que o orçamento de compromissos seja excedido.** A taxa com todos os pares (800) é reportada ao lado, identificada como diluída. Famílias saturadas (R1 falha sem mitigação em ≥ 90 %) só contam para invariantes e R2 a R6. Também se reporta, por McNemar, a variação de «aterra com todos os requisitos».

Palavras do veredicto de cada mitigação: «eficaz para R1 no envelope declarado» (M1 ou M2 suportada); «dentro do orçamento» (as três categorias cumpridas); só as duas juntas permitem «candidata a adoção». Mesmo assim, o modelo prevê que o limiar desloca a faixa mascarada para menos de 4 vezes o limiar (abaixo do mínimo de 5 m da falha `gnss_bias` com 1 m), por isso a família de viés líquido pequeno é reportada à parte e nunca entra na palavra «eficaz». Um viés do altímetro de 1 a 3 m, a regressão mais plausível de um limiar menor, não pode ser simulado sem alterar a biblioteca (mínimo de 5 m, `landing_model.rs:238`).

## Regras de decisão

Para cada hipótese de proporção ou de pares:

- **Confirmada:** H0 rejeitada ao nível da família (para S4 e S5, também fração ≥ 0,9).
- **Refutada:** fração observada no sentido previsto ≤ 0,1, ou, para H3, S1 e S2, intervalo inteiramente fora de b* ± 1 m (± 0,5 m em S2).
- **Inconclusiva:** qualquer outro caso, com a contagem e o intervalo de Clopper-Pearson a 99 %.

Leitura conjunta, fixada antes da execução:

- **Achado M14 confirmado** se H1, H2 e H3 forem confirmadas. Diz-se então: «com o viés a começar depois da primeira medida GNSS, o G3 deixa de valer para R1 abaixo de cerca de 12 m, e acima disso R1 volta a cumprir-se», sempre acompanhado do perfil de R5.
- **Refutado** se H1 ou H2 for refutada.
- **Mecanismo confirmado** só se S4, S5 e as verificações estruturais passarem; com H1 a H3 confirmadas e S4 ou S5 falhada, o efeito fica confirmado e o mecanismo não.
- Nenhum resultado altera o registo do G3 nem o grau dos pacotes M13 e M14.

## Sementes

- **Usadas nesta execução:** 44000 a 44919, pela ordem das etapas A, B, C, D, E e, dentro de cada etapa, por semente crescente e pela ordem dos braços na tabela. Como cada execução é determinística, a ordem não muda resultados; serve para auditar uma retoma.
- **Proibidas:** 50000 a 59999 (divisão do M14, gasta), 44920 a 44999 (reserva), e as sementes protegidas do foguetão em `exec/src/seeds.rs`.
- **Já vistas, não utilizáveis como confirmação:** 41000 a 41999 (desenvolvimento; 41000 a 41009 usadas à mão), 42000 a 43999 (investigação M13), 45000 a 46999 (desenvolvimento; 45000 a 45003 da revisão), 47000 a 47019 (teste de P1 e P2), 32000 a 32099 (fragilidade M14), 33500 a 33529 (revisão M14), 30001 e 30017 (equivalência M14).
- **Independência entre etapas.** Blocos disjuntos: a conclusão sobre mitigações não usa as realizações de ruído que confirmaram o mascaramento, e as etapas podem ser lidas como evidência independente.

## Execução e congelamento

1. Escrever o executor `scripts/m15_g3_confirm.py` e a análise `scripts/m15_g3_analyse.py`. O executor chama `vv-rocket land` e recusa: 50000 a 59999 sempre; 44000 a 44999 sem `--freeze <commit>`, quando esse commit não é antepassado de `HEAD`, quando a árvore não está limpa, ou quando um hash fixado difere; sementes fora do mapa acima. Testá-los só com sementes 41900 a 41999, num ensaio sem leitura de hipóteses.
2. Criar `docs/m15-g3-onset-freeze.json` com o sha256 dos bytes **guardados no commit** (`git cat-file blob <commit>:<caminho> | sha256sum`; `core.autocrlf` está ativo nesta máquina) de:
   - este protocolo;
   - `exec/claims/m13/g3-onset.json` (hoje `f9e6154c...`);
   - `exec/cases/m13/g3-registered.json` (`4f30b680...`), as 8 famílias e `sources.json`;
   - `docs/evidence/m14/masking/prediction.json` (`9a67d22e...`) e `scripts/m14_masking_model.py`;
   - os dois scripts do passo 1;
   - o `source_sha256` do `vv-rocket` (hoje `12b276cb...`), o sha256 do binário, a versão do `rustc` e o comando de compilação;
   - e o commit da árvore fixada.
3. O congelamento é um commit só com esse ficheiro, enviado para o repositório público antes da primeira execução. O registo da execução grava o commit de congelamento, a máquina e o comando.
4. Publicar o protocolo, o congelamento, o registo e a análise, qualquer que seja o resultado.

## Cálculos de preparação

Nenhum usou o simulador nem sementes.

- **Modelo.** `scripts/m14_masking_model.py` com os ganhos do caso: b* por início, limiar e ciclos de rejeição; instante e valor do pico do resíduo e da primeira rejeição. Resultados na secção «Mecanismo».
- **Precisão de H3.** A partir de `test.json`, com sementes comuns a todos os níveis e assumindo monotonia: distribuição de b_s em 20 sementes com mediana em 12,0 m. Reamostragem com n = 60 e 20 000 repetições:
  - P(confirmar) = 1,00 se a distribuição for a de desenvolvimento;
  - 0,67 se a fronteira real estiver 0,75 m acima;
  - P(refutar) = 1,00 se estiver 1,5 m acima.
- **Potência de H1 e H2.** n = 160, α = 0,01/3: rejeita com ≥ 154 sucessos. Potência:
  - 0,31 se π = 0,95;
  - 0,79 se π = 0,97;
  - 0,999 se π = 0,99.

  Nos dados de desenvolvimento longe da fronteira, todas as células foram 4 de 4 ou 20 de 20, por isso π ≈ 1 é plausível.
- **M2 e S7.** n = 80. Com α = 0,01/2 (M2), rejeita com ≥ 79, potência 0,81 se π = 0,99. Com α = 0,01/7 (S7), só 80 de 80 rejeita: S7 é um teste exigente e pode ficar inconclusivo com uma única exceção. Com α = 0,01/3, abaixo de 55 sementes nem 100 % rejeitaria H0, razão por que nenhuma proporção confirmatória usa menos de 80.
- **Outros limiares.** S3 (n = 160, α = 0,01/7): ≥ 155. M1 (n = 240, α = 0,01/2): ≥ 228. Orçamentos: 0 eventos em 480 dão 0,95 % e 1 dá 1,37 %; 13 em 480 é o máximo a 5 %; 1 em 320 dá 2,06 % e 2 dão 2,60 %.

## Ameaças à validade

- **Construção.** Requisitos e dispersões assumidos; uma simulação idealizada de um só veículo. Nada disto diz algo sobre um veículo real.
- **Interna.** A fronteira depende do ruído dos sensores. A janela de 1 s do mediador é uma escolha; a sensibilidade a 0,5 s e 2 s é reportada como descritiva.
- **Exploração prévia.** Os níveis de magnitude e os inícios foram escolhidos depois de ver os dados de desenvolvimento. Isso favorece efeitos grandes, não as conclusões, porque as sementes são novas e as regras estão fixadas.
- **Externa.** S3 depende do raio assumido de R5 (10 m); o nível 13,5 m é o mais próximo dele. O viés é igual em x e z, como na falha registada; um viés só vertical separaria R1 de R5 e não é testado.
- **Estatística.** Bonferroni é conservador. H3 com tolerância de 1 m é fraca; S2 dá a leitura exigente.
- **Revisão.** Só agentes. Sem revisão humana independente.

## Decisão do responsável

Uma só decisão: **aprovar este candidato tal como está, ou rejeitá-lo.** A aprovação autoriza a escrita e o teste dos dois scripts em sementes de desenvolvimento, o commit de congelamento e o uso das sementes 44000 a 44919 só para esta execução. Qualquer alteração, incluindo os orçamentos de regressão, produz um novo candidato que volta a esta decisão.

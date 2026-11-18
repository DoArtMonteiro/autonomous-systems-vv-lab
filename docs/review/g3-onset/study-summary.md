# Resumo do estudo proposto

Este resumo é autónomo: não é preciso conhecer o projeto para o ler. Descreve o que o candidato a protocolo (`docs/m15-g3-onset-protocol.md`, commit `bec7b3f`) propõe, não o que foi apurado. Nada foi executado. Os resultados citados como antecedentes são de desenvolvimento, com sementes já vistas, e são **exploratórios**. O protocolo é um candidato: não está aprovado nem congelado. Foi escrito e revisto só por agentes.

Os números de linha entre parênteses, como (l. 115), referem-se ao protocolo no commit `bec7b3f`.

## Contexto

O projeto é um laboratório de verificação e validação. Um dos seus simuladores, `vv-rocket`, calcula a aterragem propulsiva de um único estágio de foguetão, em seis graus de liberdade, com passo fixo, aritmética reprodutível e geração pseudoaleatória (SplitMix64) com semente explícita. Em cada execução, o simulador devolve um veredicto sobre requisitos de aterragem e invariantes de segurança. Não há dados de voo nem outro veículo.

Caso base do estudo (`exec/cases/m13/g3-registered.json`): estágio de 22 000 kg de massa seca e 8 000 kg de propelente, altitude inicial de 3 000 m, velocidade vertical inicial de -200 m/s, contacto nominal por volta de 23,3 a 23,6 s (`docs/m9-powered-landing.md`, l. 241: 23,63 s para `baseline` e 23,27 s para `robust`, no caso nominal do M9, semente 0; não é medida de `guarded` no caso do G3), passo de 0,01 s, ciclo de controlo de 0,02 s, GNSS a cada 0,1 s, altímetro com ruído de 0,1 m e GNSS com ruído de 0,5 m (posição). O ruído dos sensores é limitado (soma de quatro uniformes, truncada a ±2√3 σ), não gaussiano (`crates/vv-rocket/src/prng.rs`).

Requisitos usados neste estudo (valores do caso):

| Id | Significado | Limite |
| --- | --- | --- |
| R1 | Velocidade vertical no contacto | até 3 m/s |
| R2 | Velocidade horizontal no contacto | até 1 m/s |
| R3 | Inclinação no contacto | cosseno de pelo menos 0,9962 |
| R4 | Velocidade angular | até 0,1 rad/s |
| R5 | Posição no contacto | até 10 m do alvo |
| R6 | Margem de propelente | pelo menos 1 % |

Invariantes de segurança S1 a S5: inclinação máxima (cosseno 0,866), zona de exclusão de 50 m, carga axial até 3 g0, no máximo uma ignição, sem subida propulsionada. O resultado da missão («aterra») fica separado dos invariantes.

## A alegação e o problema

O critério G3 do módulo M9.1 diz que o controlador `guarded` cumpre R1 com um viés GNSS de 5 a 30 m (em 27 de 30 execuções, pelo menos). Foi registado e suportado **só com o viés presente desde 0 s**. Um estudo posterior (M13, com uma plataforma automática de procura de contraexemplos) estendeu a alegação a viés que começa em qualquer instante dos primeiros 20 s e encontrou falhas. Os dados de desenvolvimento sugerem este quadro:

- Com início do viés depois da primeira medida GNSS e magnitude abaixo de cerca de 12 m, R1 falha em quase todas as execuções.
- Acima de cerca de 13 m, R1 volta a cumprir-se. Um viés maior parece «mais seguro» para R1, mas a aterragem passa a falhar R5 (fora da plataforma): o viés de 15 m com início em 0 s falha R5 em 30 de 30 execuções (`docs/evidence/m13/g3-onset/investigation.json`, `baseline_violations`).
- Um modelo muito simples do erro vertical do estimador previu a magnitude crítica 11,99 m antes de a testar; o simulador, com 20 sementes novas, deu 11,89 m (`docs/evidence/m14/masking/`).

O protocolo propõe confirmar este quadro com sementes novas e regras fixadas antes. O G3 como foi registado não muda e o grau de evidência dos pacotes anteriores também não.

## Mecanismo proposto

Fontes no código: `crates/vv-rocket/src/landing_controller.rs`, `landing_sensors.rs`, `landing_sim.rs`.

1. O controlador `guarded` navega com um estimador que funde IMU, GNSS e altímetro. O estimador **inicializa-se na primeira medida GNSS, no passo 0**.
2. O viés GNSS soma a mesma magnitude a x e a z da posição medida.
3. A cada ciclo com amostra do altímetro, se o resíduo (altímetro menos altitude estimada) excede 3 m, a correção do altímetro não é aplicada nesse ciclo. Ao fim de 5 ciclos seguidos nessa condição, o altímetro fica «rejeitado». Um resíduo dentro do limiar volta a admiti-lo.
4. **Regra 1** (só no `guarded`): enquanto o altímetro está rejeitado, o guiamento usa a menor de duas altitudes, a estimada e a do altímetro. É a proteção contra um viés vertical.
5. Com viés desde 0 s, o estimador começa já enviesado, o resíduo excede logo o limiar, o altímetro é rejeitado (aos 0,1 s) e a regra 1 protege.
6. Com viés que começa depois, o estimador já convergiu com o altímetro. O GNSS enviesado puxa a altitude estimada, o altímetro puxa-a de volta. No modelo, o resíduo atinge o máximo 0,3 s depois do início (0,25 vezes a magnitude) e assenta em cerca de 0,22 vezes a magnitude. Se esse máximo ficar abaixo de 3 m, isto é, para magnitudes abaixo de b* ≈ 11,99 m, o altímetro nunca é rejeitado, a regra 1 nunca atua, e o erro de velocidade vertical que o resíduo persistente cria (no modelo, entre cerca de -4,2 e -5,1 m/s a 8 m) não é travado. Acima de b*, o transitório ultrapassa o limiar e o altímetro é rejeitado pouco depois do início (0,58 s a 12 m; 0,18 s a 15 m; 0,08 s a 30 m).
7. b* ≈ 4 vezes o limiar de rejeição (3,996 m com 1 m; 7,992 m com 2 m; 11,989 m com 3 m) e não depende do número de ciclos de rejeição nem do instante de início, porque o modelo ignora o veículo.

O horizontal não é corrigido pela regra 1: o guiamento lateral segue o GNSS enviesado, com ou sem rejeição (l. 21). Por isso um viés maior troca uma aterragem dura (R1) por uma aterragem fora da plataforma (R5).

### Papel causal da rejeição

A rejeição é posterior ao tratamento (início e magnitude) e não é confundidor. É mediador e condição de ativação da regra 1 (l. 27 a 33). O protocolo toma como mediador a **primeira rejeição dentro de uma janela de decisão** [início; início + 1,0 s], lida de `altimeter_rejected_first` no `verification.json`, para evitar causalidade inversa (uma trajetória que já falha pode rejeitar tarde). Duas intervenções isolam o mecanismo:

- **G0**: `guarded` com a regra 2 desligada (`ascent_abort_vz_mps` = 100) contra `robust` (sem regra 1 nem regra 2). Até à primeira rejeição os comandos são idênticos; só a regra 1 difere depois.
- **N**: limiar de rejeição de 1000 m, que torna a rejeição impossível.

## Hipóteses e classificação

O protocolo classifica as hipóteses em três tipos (l. 52 a 58). A coluna «Classificação» reproduz o protocolo; a coluna «Nota» é a leitura deste pacote.

| Id | Enunciado resumido | Classificação no protocolo | Nota |
| --- | --- | --- | --- |
| H1 | Início em (0; 20] s, magnitude {5; 7; 9; 10,5} m: R1 cumpre-se com início 0 s e falha com início tardio, na mesma semente. | Preditiva (P2 generalizada) | P2 foi prevista só a 8 m. As magnitudes e os 8 inícios são extensão. |
| H2 | Início em (0; 20] s, magnitude {13,5; 17; 22; 30} m: R1 cumpre-se. | Preditiva (P1) | P1 prevê a fronteira a 5 s, não a recuperação para todos os inícios. A recuperação vem de dados M13. |
| H3 | Início 5 s: a magnitude mediana de transição b50 está a menos de 1 m de b* = 11,99 m. | Preditiva (P1) | Tolerância fixada em `prediction.json`. O protocolo reconhece que é pouco exigente. |
| S1 | H3 também com início a 15 s. | Corolário | O modelo não depende do início. |
| S2 | b50 a 5 s a menos de 0,5 m de b*. | Corolário | Leitura exigente de H3. |
| S3 | Início 0 s, magnitude alta: R5 falha. | A posteriori | Depende do raio de R5 (10 m). |
| S4 | Com rejeição na janela, G0 cumpre R1 e `robust` falha (mesma semente). | A posteriori | Regra 1 é o componente ativo. |
| S5 | Com limiar 1000 m, R1 falha onde o `guarded` registado cumpre. | A posteriori | A rejeição é necessária. |
| S6 | Em execuções tardias com rejeição, a primeira rejeição ocorre na janela. | Corolário | A janela de 1 s é uma escolha. |
| S7 | Limiar 2 m e início tardio: R1 falha a 5 m e cumpre-se a 10,5 m. | Corolário | Previsto pelo modelo (b* ≈ 8 m com 2 m). |
| M1 | Limiar 1 m: R1 cumpre-se com início tardio na banda baixa. | **Não classificada** no protocolo | Pelo conteúdo, a posteriori: o M13 já a apoiou no desenvolvimento. |
| M2 | Limiar 2 m: igual, a 10,5 m apenas. | **Não classificada** no protocolo | Mistura corolário do modelo com resultado M13. |
| Estruturais | Em todas as condições da etapa C, `altimeter_rejected_first` é igual em G0 e `robust`, semente a semente; sem rejeição, R1 a R6 iguais bit a bit. | Verificação determinística | Uma exceção suspende a leitura de S4. |

Os cálculos «preditivos» P1 e P2 foram fixados no commit `73c9ff5` (2026-11-03 20:20) antes do teste `1195c1b` (20:25), com as sementes 47000 a 47019, que ficam gastas. O autor tinha visto a transição grosseira entre 10 e 15 m antes. As datas dos commits são as registadas no repositório; foram conferidas neste pacote com `git log`.

Famílias de testes e níveis de erro (l. 60 a 81): primária H1 a H3, erro de família 0,01, Bonferroni 0,01/3; secundária S1 a S7, 0,01/7; mitigação M1 e M2, 0,01/2.

## Desenho

Cada execução altera só ponteiros indicados do caso base. Inícios tardios T = {0,01; 0,1; 1; 2; 5; 10; 15; 20} s. A mesma semente em braços diferentes é emparelhamento intencional (os fluxos de ruído dependem só da semente); etapas diferentes usam sementes disjuntas (l. 85).

| Etapa | Objetivo | Sementes | Execuções |
| --- | --- | --- | --- |
| A, perfil | H1, H2, S3, S6, perfil por requisito | 44000 a 44319 (320) | 640 |
| B, fronteira | H3, S1, S2 | 44320 a 44379 (60) | 2 040 |
| C, mecanismo | S4, S5, verificações estruturais | 44380 a 44439 (60) | 720 |
| D, mitigação | M1, M2, S7, orçamento | 44440 a 44759 (320) | 1 920 |
| E, famílias | Orçamento de regressão | 44760 a 44919 (160) | 480 |
| Reserva | Não usada | 44920 a 44999 (80) | 0 |
| **Total** | | **920 sementes** | **5 800** |

Detalhe de cada etapa:

- **A.** Semente = 44000 + 40·i + 5·j + r, com i = índice do início em T (0 a 7), j = índice da magnitude em {5; 7; 9; 10,5; 13,5; 17; 22; 30} (0 a 7), r = 0 a 4. Dois braços por semente: início tardio e início 0 s. Banda baixa (j = 0 a 3) e banda alta (j = 4 a 7) têm 160 sementes cada.
- **B.** Cada semente corre 17 magnitudes (10,0 a 14,0 m, passo 0,25) com início 5 s e com início 15 s: 34 execuções por semente.
- **C.** Cada semente corre 3 condições, (0 s, 15 m), (5 s, 15 m) e (5 s, 8 m), com 4 braços: G registado, G0, R (`robust`) e N (limiar 1000 m).
- **D.** Semente = 44440 + 40·i + 10·j + r, com j em {5; 8; 10,5; 15} (0 a 3), r = 0 a 9. Seis braços: {início tardio; 0 s} × {sem mitigação; limiar 1 m; limiar 2 m}.
- **E.** Semente = 44760 + 20·f + k, com f = índice da família pela ordem de `exec/claims/m13/g3-onset.json` (0 a 7) e k = ponto Halton 0 a 19 (bases 2 e 3, índice a partir de 1, quantizados como no motor de investigação). Três braços: sem mitigação, 1 m, 2 m. As 8 famílias: viés GNSS baixo, viés do altímetro alto, viés do altímetro baixo, falha de GNSS, falha do altímetro, viés do acelerómetro, perda de impulso, viés GNSS líquido pequeno.

Os totais e a disjunção foram recalculados em `independent-checks.md`.

## Resultados medidos

O executor (por escrever) grava, por execução: semente, condição, braço, `outcome`; para cada requisito R1 a R6, `evaluated`, `pass`, `value`; para cada invariante S1 a S5, `pass` e primeiro instante de falha; `altimeter_rejected_first`; `sensor_disagreement_first`; sha256 de `verification.json` e de `trace.json`. Nada é lido do traço amostrado.

- **Perfil por requisito.** O resultado de uma condição é o vetor de contagens por requisito e invariante. R1 é o primário; R2, R5 e «aterra com todos os requisitos» são secundários e vão sempre ao lado de R1. Nenhum texto pode dizer «mais seguro» sem nomear o requisito.
- **Mediador.** Rejeição na janela [início; início + 1,0 s]; rejeição tardia (depois da janela) é categoria própria.
- **Transição por semente (etapa B).** b_s = menor nível a partir do qual R1 se cumpre nesse nível e em todos os seguintes; +∞ se não existir. b50 = mediana de b_s. Sementes não monótonas são contadas e reportadas.

## Métodos de análise

Proporções (l. 108 a 114): teste binomial exato unilateral de H0: π ≤ 0,9, ao nível de cada família. A unidade é a semente.

| Hipótese | n | Sucesso | Rejeita H0 com |
| --- | --- | --- | --- |
| H1 | 160 | R1 cumprido a 0 s e falhado no início tardio | 154 ou mais |
| H2 | 160 | R1 cumprido no início tardio | 154 ou mais |
| S3 | 160 | R5 falhado com início 0 s | 155 ou mais |
| S6 | cerca de 160 | primeira rejeição dentro da janela | depende de n |
| S7 | 2 × 80 | duas proporções (5 m e 10,5 m) | 80 de 80 |
| M1 | 240 | R1 cumprido com limiar 1 m, início tardio, banda baixa | 228 ou mais |
| M2 | 80 | R1 cumprido com limiar 2 m, início tardio, 10,5 m | 79 ou mais |

Pares: S4 e S5, em cada uma das condições (0 s, 15 m) e (5 s, 15 m) em separado (60 pares cada), teste de McNemar exato unilateral com p < 0,01/14 e fração de sementes com o resultado previsto ≥ 0,9. Confirmada se as duas condições cumprirem.

Fronteira: H3, S1, S2 com intervalo de confiança da mediana sem distribuição, por estatísticas de ordem, a 1 − 2α (equivalência por dois testes unilaterais). Com n = 60: posições 20 e 41 para H3; 19 e 42 para S1 e S2. O limite inferior conta o nível anterior, porque b_s está em (nível − 0,25; nível].

Erros: uma execução que falha (código diferente de 0, ficheiro em falta, R1 com `evaluated` falso, `no_contact`) é repetida uma vez com a mesma semente; se falhar outra vez, conta contra a hipótese em teste. Se mais de 1 % das execuções de uma etapa falharem, a etapa é declarada inválida e não é substituída. Sem análise intermédia nem paragem antecipada: o executor só escreve um registo com hashes e o script de análise lê-o uma vez, completo.

Concordância descritiva (C2): tabela 2×2 (rejeição na janela × R1) por etapa, sem teste nem conclusão causal.

## Regras de decisão

Para cada hipótese de proporção ou de pares:

- **Confirmada:** H0 rejeitada ao nível da família (S4 e S5: também fração ≥ 0,9).
- **Refutada:** fração observada no sentido previsto ≤ 0,1; para H3, S1 e S2, intervalo inteiramente fora de b* ± 1 m (± 0,5 m em S2).
- **Inconclusiva:** qualquer outro caso, com a contagem e o intervalo de Clopper-Pearson a 99 %.

Leitura conjunta:

- **Achado M14 confirmado** se H1, H2 e H3 forem confirmadas, com a frase «com o viés a começar depois da primeira medida GNSS, o G3 deixa de valer para R1 abaixo de cerca de 12 m, e acima disso R1 volta a cumprir-se», sempre acompanhada do perfil de R5.
- **Refutado** se H1 ou H2 for refutada.
- **Mecanismo confirmado** só se S4, S5 e as verificações estruturais passarem; com H1 a H3 confirmadas e S4 ou S5 falhada, o efeito fica confirmado e o mecanismo não.
- Nenhum resultado altera o registo do G3 nem o grau dos pacotes anteriores.

(Estas são as palavras do protocolo. Neste pacote, «confirmado» significa apenas que um critério pré-especificado seria cumprido numa simulação idealizada.)

## Orçamento de regressão das mitigações

Um evento é um par em que a mitigação acrescenta uma violação que a execução sem mitigação não tinha. Limite superior de Clopper-Pearson unilateral a 99 %. Os pares são os de etapa D com início tardio (320 por mitigação) e etapa E (160): 480. Os pares com início 0 s (320 por mitigação) formam categoria própria.

| Categoria | Pares | Orçamento | Eventos máximos |
| --- | --- | --- | --- |
| Invariantes S1 a S5 | 480 | ≤ 1 % | 0 |
| R2 a R6 (compromissos) | 480 | ≤ 5 % | 13 |
| R1 com início 0 s (território do G3 registado) | 320 | ≤ 2,5 % | 1 |

O protocolo prevê, antes de executar, que o orçamento de compromissos provavelmente será excedido: nos dados de desenvolvimento o limiar de 1 m deu 35 compromissos em 1 024 pares do envelope (3,4 %; limite a 99 % de 4,98 %) e 6 em 30 no contraexemplo (35 + 6 = 41, o número citado no M13). As palavras do veredicto de cada mitigação são «eficaz para R1 no envelope declarado» (M1 ou M2 suportada) e «dentro do orçamento» (as três categorias cumpridas); só as duas juntas permitem «candidata a adoção». Uma família de viés líquido pequeno (abaixo do mínimo de 5 m de um só `gnss_bias`) é reportada à parte e nunca entra na palavra «eficaz». Um viés do altímetro de 1 a 3 m, a regressão mais plausível de um limiar menor, não pode ser simulado sem alterar a biblioteca.

## Sementes

- Usadas: 44000 a 44919, na ordem das etapas.
- Proibidas: 50000 a 59999 (divisão reservada do M14, gasta), 44920 a 44999 (reserva) e as sementes protegidas do foguetão em `exec/src/seeds.rs`.
- Já vistas, não utilizáveis como confirmação: 41000 a 41999, 42000 a 43999, 45000 a 46999, 47000 a 47019, 32000 a 32099, 33500 a 33529, 30001 e 30017.

`vv-rocket land` não tem guarda de sementes. O protocolo pede um executor próprio (`scripts/m15_g3_confirm.py`) que recusa as sementes proibidas e exige um commit de congelamento antepassado de `HEAD`, árvore limpa e hashes fixados (l. 159). Esse executor não existe.

## Congelamento proposto

Um ficheiro `docs/m15-g3-onset-freeze.json`, por criar, com o sha256 dos bytes guardados no commit do protocolo, da alegação, do caso base e das 8 famílias, de `sources.json`, da previsão, do modelo, dos dois scripts, do `source_sha256` do `vv-rocket`, do binário, da versão do compilador e do comando, mais o commit fixado. O congelamento seria um commit só com esse ficheiro, enviado ao repositório público antes da primeira execução. Ver `source-commitments.md`.

## Ameaças à validade (as do protocolo, l. 189 a 196, e as deste pacote)

- **Construção.** Requisitos e dispersões assumidos; um só veículo idealizado. Nada diz algo sobre um veículo real.
- **Interna.** A fronteira depende do ruído dos sensores (limitado, não gaussiano). A janela de 1 s é uma escolha; a sensibilidade a 0,5 s e 2 s é descritiva.
- **Exploração prévia.** Níveis de magnitude e inícios escolhidos depois de ver dados de desenvolvimento.
- **Externa.** S3 depende do raio de R5 (10 m; o nível 13,5 m é o mais próximo). O viés é igual em x e z; um viés só vertical não é testado. Com contacto nominal por volta de 23,3 a 23,6 s (valores do M9 para `baseline` e `robust`, não para `guarded` neste caso), o início a 20 s deixa cerca de 3 s até ao contacto; o tempo restante nas sementes dispersas não foi medido neste pacote.
- **Estatística.** Bonferroni é conservador. H3 com tolerância de 1 m é fraca. As proporções são sobre uma grelha escolhida, não uma população.
- **Revisão.** Só agentes.

Ver `limitations.md` para a lista completa e `reviewer-questions.md` para as perguntas.

# M13: Discovery Lab, pôr à prova uma alegação de segurança

Estado: **aceitação de engenharia e de produto propostas; aceitação científica não pedida.** Evidência de simulação idealizada, com sementes de desenvolvimento. Não diz nada sobre um veículo real e não é uma certificação. O M10 continua por aceitar e nada aqui depende dele.

## O que o M13 faz

Um engenheiro escolhe uma alegação de segurança que parece bem suportada e carrega em «Challenge this claim». A plataforma:

1. confirma a alegação nas condições em que foi registada;
2. procura um contraexemplo dentro do envelope declarado dos pressupostos;
3. reduz o contraexemplo, reprodu-lo em sementes novas e reescreve-o com o escritor canónico do simulador, byte a byte;
4. separa os pressupostos necessários dos que só estavam lá, com contrafactuais emparelhados;
5. mapeia onde a alegação se mantém;
6. testa as hipóteses de mecanismo declaradas antes da execução, no contraexemplo e em toda a região de falha, e lê o traço do que o controlador acreditava contra o estado verdadeiro;
7. avalia cada mitigação candidata no contraexemplo, no envelope, nas condições registadas, em famílias de regressão com sementes novas e numa nova pesquisa adversarial;
8. escreve um pacote de evidência que qualquer pessoa pode recalcular sem confiar em nada do que lá está guardado.

O veredicto é calculado por regras fixas do motor, nunca por texto escrito à mão nem por um modelo de linguagem. Quatro resultados ficam separados: integridade da evidência, veredicto da alegação, mecanismo e mitigação, mais o grau da evidência (exploratório ou confirmatório).

## Arquitetura

| Peça | Onde | Papel |
| --- | --- | --- |
| Alegação `vv-claim.v1` | `exec/claims/m13/*.json` | Enunciado, origem, propriedade, tolerância, pressupostos e envelope, três reservas de sementes disjuntas, orçamento, hipóteses, mitigações e famílias de regressão. |
| Motor | `exec/src/investigate.rs` | `vv-exec investigate` e `vv-exec investigate-verify`. Usa a pesquisa do M14 (`exec/src/search.rs`, inalterada) e os domínios em processo do M12 e do M14. |
| Sinais | `exec/src/signals.rs` | Séries derivadas do traço canónico, com papéis separados: verdadeiro, acreditado, observado, erro, alerta, comando. |
| Studio | `desktop/studio/src/discovery.rs`, `desktop/studio/ui/js/views/discover.js` | Espaço de trabalho «Discover». Corre o motor instalado como processo filho, mostra o progresso, recalcula o pacote e lê o que o motor escreveu. Não calcula veredictos. |
| Instalador | `desktop/build.ps1`, `desktop/studio/tauri.conf.json` | Junta `engines/vv-exec.exe` e `discovery/` ao instalador do M11. |

Regras do motor (constantes em `investigate.rs`, gravadas em cada pacote):

- **Refutação:** o limite inferior de Clopper-Pearson a 95 % da taxa de violação no contraexemplo, em sementes novas, excede a tolerância da alegação, e o registo da pesquisa, uma nova execução em processo e o escritor canónico dão o mesmo traço.
- **Papel de um pressuposto:** necessário quando repô-lo sozinho no valor registado elimina a violação em pelo menos 90 % das sementes emparelhadas onde o contraexemplo viola; suficiente quando aplicá-lo sozinho às condições registadas viola em pelo menos 90 %.
- **Intervenção de mecanismo:** apoiada quando o resultado previsto ocorre em pelo menos 90 % das sementes, com McNemar exato abaixo de 0,01 no sentido previsto, e quando atua em pelo menos 90 % dos pares do envelope que podia mudar. Se só atuar no ponto, fica «apoiada só localmente».
- **Mitigação:** eficaz quando elimina a violação em pelo menos 90 % das sementes do contraexemplo. Uma regressão é uma célula do envelope que passa a violar a propriedade, ou um par (condições registadas ou família) que ganha uma violação de segurança ou da propriedade. Uma nova pesquisa com a mitigação aplicada conta à parte os contraexemplos residuais.

## A investigação principal: G3 com viés GNSS tardio

**Alegação** (`exec/claims/m13/g3-onset.json`). «O controlador `guarded` do M9.1 toca no solo dentro de R1 (velocidade vertical até 3 m/s) com um viés GNSS de 5 a 30 m, sempre que o viés comece nos primeiros 20 s do voo.» O critério G3 do M9.1 foi registado e suportado só com o viés presente desde 0 s. Esta alegação é uma hipótese nova; não altera o G3. O M14 já tinha mostrado que inícios de 2, 5 e 10 s falham a 5 e 10 m.

**Resultados** (pacote recalculado; 7885 simulações; sementes 42000 a 43999):

| Etapa | Resultado |
| --- | --- |
| Condições registadas (início 0 s, 15 m) | R1 violado em 0 de 30. |
| Pesquisa Halton, 400 avaliações | 106 violam R1, a primeira na avaliação 2. Três classes de falha sem R1 (R2, R5) ficam listadas e não investigadas. |
| Contraexemplo | Encontrado na avaliação 232 (início 4,18 s, 9,55 m). Reduzido a **início 0,02 s, 9,72 m**. R1 violado em 30 de 30 sementes novas (IC 95 % 88,4 a 100 %). Traço igual byte a byte nas três fontes. |
| Atribuição | Início e magnitude são ambos necessários (30 de 30) e nenhum é suficiente sozinho (0 de 30): a falha precisa dos dois. |
| Envelope (16 × 16 células, 4 sementes) | 181 de 256 células sem violação. Falha com qualquer início depois de 0 s e magnitude até cerca de 11,7 m; acima de cerca de 13 m R1 volta a cumprir-se. **Um viés maior é mais seguro para R1.** |
| Mecanismo «rule1-not-engaged» | **Apoiado.** Limiar de rejeição a 1 m: 30 de 30 corrigidas, McNemar p = 1,9e-9, 280 de 280 pares em falha corrigidos no envelope. Teste discriminante: tornar a rejeição impossível nas condições registadas, onde o G3 se cumpre, faz R1 falhar em 30 de 30 e em 744 de 744 pares do envelope que se cumpriam. No traço: o altímetro nunca é rejeitado; o resíduo fica entre 2,22 e 2,49 m no contraexemplo (abaixo de 3 m) e chega a 15,4 a 16,2 m nas condições registadas. |
| Rivais «velocity-pathway-only» e «altitude-pathway-only» | **Contraditas.** Com a rejeição impossível, tirar só a correção de velocidade do altímetro, ou tirar o altímetro todo, não corrige nenhuma das 30 execuções: cada um dos dois caminhos chega para a falha. O que protege o G3 é a regra 1 entrar em ação, não a ausência de um dos caminhos. |
| Mitigação limiar 1 m | **Eficaz, com compromissos.** 30 de 30 no contraexemplo; 280 corrigidos e 0 partidos no envelope; nenhuma violação de segurança nova nem de R1; nova pesquisa: 0 de 400 violam R1. Mas 41 pares ganham outro requisito (R2 ou R5): execuções que deixam de cair e passam a tocar fora da plataforma ou com velocidade horizontal excessiva. Na família de viés GNSS líquido pequeno (0 a 4 m, abaixo do mínimo de 5 m de um só `gnss_bias`), R1 continua a falhar em 18 de 60 pares com a mitigação. |
| Mitigação limiar 2 m | **Eficaz, com contraexemplos residuais.** Corrige o contraexemplo, mas 120 pares do envelope continuam a violar e a nova pesquisa encontra 44 violações em 400. |

**O que a revisão independente mudou.** A primeira versão desta investigação declarava um mecanismo («masking») apoiado por três intervenções que, afinal, atuavam todas pelo mesmo interruptor (pôr o altímetro a ser rejeitado), e uma hipótese rival que era um sub-caminho da primeira. A revisão metodológica independente (um agente, não uma pessoa) mostrou-o com execuções próprias e propôs os testes discriminantes acima. As hipóteses foram reescritas depois dessa revisão; o revisor tinha corrido as sementes 45000 a 45003 no foguetão. A revisão também mostrou que a regra de regressão escondia as violações novas de outros requisitos: o motor passou a contá-las à parte como compromissos.

**O limiar não elimina o mecanismo; desloca-o.** O modelo independente (`scripts/m14_masking_model.py`) dá o fim da faixa mascarada em cerca de 4 vezes o limiar: 12,0 m com 3 m, 8,0 m com 2 m e 4,0 m com 1 m. Com 2 m, o envelope ainda falha a 5 e 6,7 m, como previsto. Com 1 m, a faixa fica abaixo do mínimo de 5 m da falha `gnss_bias` registada, e a família de viés líquido pequeno mostra-a. «Eficaz» quer dizer eficaz dentro do envelope declarado.

**Mecanismo, em palavras.** Depois de um início tardio, o estimador já convergiu com o altímetro. O GNSS enviesado puxa a altitude estimada para cima a cada medida; o altímetro, ainda aceite, puxa-a para baixo. O equilíbrio deixa um resíduo abaixo do limiar de 3 m, por isso o altímetro nunca é rejeitado e a regra 1 do `guarded` (usar a menor das duas altitudes quando discordam) nunca atua. Com o viés desde 0 s, o estimador inicializa-se na primeira medida GNSS já enviesada, o resíduo excede o limiar logo, o altímetro é rejeitado e a regra 1 protege a aterragem. O registo do G3 só testou este segundo caso: o G3 continua válido como foi registado, mas o que mostrou é que a porta deteta um viés presente na inicialização, não um viés que aparece depois. O início reduzido de 0,02 s não tem significado próprio: o GNSS mede a cada 0,1 s e qualquer início depois da primeira medida, em 0 s, é equivalente.

**Atribuição.** Os papéis são contrafactuais (intervenções nas entradas, não correlações), mas dependem do ponto de referência: a magnitude sai «necessária» porque o caso base usa 15 m, acima da faixa mascarada. Com uma referência de 8 m, que o G3 também sorteou, deixaria de o ser.

**Previsão quantitativa, testada a seguir.** Um modelo do erro vertical do estimador, sem ruído, sem veículo e sem parâmetros ajustados (`scripts/m14_masking_model.py`), previu a magnitude crítica b* = 11,99 m e que só um início na primeira medida GNSS evita o mascaramento. A previsão ficou num commit (`73c9ff5`) antes do teste. Com as sementes novas 47000 a 47019, R1 cumpre-se em metade das execuções a 11,89 m, e em todas as 29 células R1 cumpre-se exatamente nas execuções em que o altímetro foi rejeitado. Inícios de 0,01 a 20 s falham em todas as execuções a 8 m; o início em 0 s cumpre-se em todas. Ver `docs/m14-evidence-robustness.md`.

## Segunda investigação, noutro domínio: o corredor terrestre

**Alegação** (`exec/claims/m13/corridor-noise.json`). «No corredor junto à zona restrita (M2 `f-zone-nominal`), o controlador `dominant_axis` nunca entra na zona com ruído GPS até 20 mm e atrasos até 3 ticks.» O M14 tinha encontrado e explicado à mão esta fragilidade (F1). Aqui a plataforma recebe só a alegação e o envelope.

| Etapa | Resultado |
| --- | --- |
| Condições registadas | 0 de 30 violam. |
| Pesquisa, 200 avaliações | 131 violam a zona, a primeira na avaliação 1. |
| Contraexemplo | Reduzido a **1 mm de ruído, atraso 0**: a zona é violada em 12 de 30 sementes novas (IC 95 % 22,7 a 59,4 %), acima da tolerância 0. O atraso não é necessário. |
| Mecanismo «exact-arrival» | **Apoiado.** Raio de chegada de 250 mm: 12 corrigidas de 12, 175 de 175 pares no envelope. |
| Mitigação raio 250 mm | **Eficaz, sem regressão observada**; nova pesquisa 0 de 200. É uma variante da especificação do cenário, não uma correção do controlador; o cenário original fica como exemplo de fragilidade. |
| Mitigação raio 10 mm | **Eficaz, com contraexemplos residuais**: 51 de 200 na nova pesquisa, porque o ruído chega a 20 mm. |

## Integridade da evidência

`vv-exec investigate-verify <pacote>` volta a correr todas as simulações e as duas pesquisas, reescreve as execuções guardadas, recalcula todos os números e compara. Os testes `exec/tests/investigate.rs` e o teste de interface mostram que um pacote falha a verificação quando:

- um veredicto ou uma contagem é alterado e o manifesto é recalculado;
- uma linha do registo de simulações é alterada e o seu hash recalculado;
- o registo é truncado, ou uma observação é duplicada no lugar de outra;
- o número de simulações ou o tamanho de uma amostra é declarado de forma diferente;
- o pacote diz ter sido produzido com outra versão das fontes do modelo;
- evidência exploratória é apresentada como confirmatória;
- o envelope da alegação é alargado depois da execução, ou o enunciado é reescrito;
- é acrescentado um ficheiro ao pacote.

Uma alegação declarada confirmatória sem um protocolo que a congele é recusada antes de correr. As sementes 50000 a 59999 (divisão reservada do M14, já usada) e 44000 a 44999 (reserva do M13 para uma confirmação futura) são recusadas, além das sementes protegidas de cada domínio. No Studio, um pacote que falha a recalculação, ou que mudou desde a última, deixa de mostrar os seus veredictos: aparecem como retirados.

## Studio

O espaço de trabalho «Discover» é o primeiro do Studio. Mostra a alegação (enunciado, origem, envelope com o valor registado, hipóteses e mitigações declaradas antes da execução, sementes e regras), corre a investigação com progresso por etapa e cancelamento, e abre o pacote como um caderno de sete secções: pesquisa, contraexemplo, envelope, causa, mitigação, limites e evidência. As séries do contraexemplo mostram lado a lado o estado verdadeiro, o acreditado e o observado, contra o gémeo contrafactual ou uma execução mitigada, com o cursor sincronizado.

Imagens em `docs/images/m13-discovery/`, produzidas pelo teste de interface com a aplicação real.

## Como reproduzir

```sh
cargo build --release --manifest-path exec/Cargo.toml
exec/target/release/vv-exec claim exec/claims/m13/g3-onset.json
exec/target/release/vv-exec investigate exec/claims/m13/g3-onset.json --output exec/target/m13/g3 --progress
exec/target/release/vv-exec investigate-verify exec/target/m13/g3
```

No Studio: instalar com `desktop/build.ps1`, abrir «Discover», escolher a alegação e carregar em «Challenge this claim».

## Limitações e riscos em aberto

- **Exploratório.** As hipóteses de mecanismo e as mitigações foram escritas depois de execuções manuais com as sementes 41000 a 41009. A investigação registada usa sementes novas, mas isso não a torna confirmatória. O protocolo de confirmação está em `docs/m14-g3-onset-protocol-draft.md`, por aprovar.
- **Hipóteses humanas.** A plataforma testa hipóteses e mitigações declaradas; não as inventa. A atribuição e o mapa do envelope são automáticos.
- **Um ponto reduzido.** A intervenção é testada no contraexemplo reduzido e depois no envelope. O teste no envelope é o que separou o mecanismo geral do local; sem ele, a hipótese rival teria parecido apoiada.
- **Regressão limitada ao que se declarou.** Oito famílias com 60 pontos cada (limite superior a 95 % de cerca de 6 % por família, sem agregação); duas estão saturadas (já falham sem a mitigação) e só mostram nomes de violação novos. Não foram testados: viés do altímetro de 1 a 3 m, ruído do altímetro maior, erros combinados de GNSS e altímetro, dispersões maiores, nem rejeições falsas em transitórios. «Sem regressão observada» não é «sem regressão».
- **Grau confirmatório.** Este motor nunca classifica evidência como confirmatória: não consegue mostrar que um protocolo foi congelado antes da execução. A revisão de código independente mostrou que um pacote exploratório podia ser reclassificado; a correção foi recusar o grau.
- **Mapa do envelope** só sobre os dois primeiros pressupostos, à resolução da grelha.
- **Revisão.** O código, a metodologia e a interface foram revistos por agentes independentes, não por pessoas. Não houve revisão humana externa.
- A regressão de M10 (classes de falha do PR 15) não pode ser redescoberta nesta base, que não tem o código do M10.

# Limitações

Duas listas: as do estudo proposto e as deste pacote. Nenhuma é exaustiva.

## Limitações do estudo proposto

### Modelo e âmbito

- **Simulação idealizada, sem dados de voo.** O `vv-rocket` é um modelo de seis graus de liberdade de um só estágio, com requisitos e dispersões assumidos. Nunca foi comparado com telemetria de um veículo real; não existe tal comparação neste projeto. Mesmo uma confirmação completa não diz nada sobre um veículo real, e o protocolo di-lo (l. 191).
- **Um só veículo, um só perfil de descida.** Massa, altitude inicial, velocidade, ganhos do estimador e do controlador são os do caso registado. A fronteira (b* ≈ 12 m) é uma função desses ganhos: no modelo, vale cerca de 4 vezes o limiar de rejeição de 3 m.
- **Ruído limitado e dispersões uniformes.** O ruído dos sensores é uma soma de quatro uniformes, limitada a ±2√3 σ pelo próprio suporte (o corte em `prng.rs` nunca atua); as dispersões iniciais são uniformes (`crates/vv-rocket/src/prng.rs`, `landing_model.rs`). Não há caudas pesadas, nem correlação temporal, nem falhas combinadas.
- **Viés igual em x e z.** A falha registada soma a mesma magnitude às duas componentes (`landing_sensors.rs:79-80`). Um viés só vertical separaria R1 de R5 e não se testa.
- **Regressões não simuláveis.** Um viés do altímetro de 1 a 3 m, a regressão mais plausível de um limiar de rejeição menor, não pode ser simulado sem alterar a biblioteca (mínimo de 5 m). Ruído do altímetro maior, erros combinados e dispersões maiores também ficam de fora.
- **Dois limiares de mitigação.** Só se estudam 1 m e 2 m. Sem otimização, sem outros ganhos.
- **Modelo de previsão sem veículo.** O modelo do estimador (`scripts/m14_masking_model.py`) ignora o veículo, o guiamento, a atitude e o ruído. Prevê b* igual para qualquer início. Só se testou contra o simulador com 20 sementes e, quanto ao início, a 8 m.

### Estatística

- **As proporções são sobre uma grelha escolhida.** π nas hipóteses H1, H2, S3 e M1 é a fração de sementes numa grelha de inícios e magnitudes decidida pelos autores, com pesos iguais, não sobre uma população de condições. As proporções agregadas toleram a falha de uma célula inteira (5 sementes) em H1 e H2.
- **Condições de teste estreitas.** As magnitudes e os inícios foram escolhidos depois de ver dados de desenvolvimento (l. 193). A zona de transição (10,5 a 13,5 m) só é testada diretamente em H3 e S1, em dois inícios.
- **Nulas e limiares por convenção.** O 0,9 vem da convenção do motor de investigação, não de uma exigência de segurança. A potência para π = 0,95 é 0,31 (H1 e H2).
- **Multiplicidade parcial.** Bonferroni dentro das famílias, nenhum controlo entre famílias (até 0,03 no conjunto) nem entre os seis limites do orçamento de regressão.
- **S4 e S5.** Regra pontual (54 de 60) com McNemar redundante; ver `independent-checks.md`, secção 5.
- **Orçamento de regressão.** Mede uma taxa numa mistura escolhida de condições; o protocolo prevê que o orçamento de compromissos provavelmente será excedido.
- **Efeitos que o protocolo não avalia.** A sensibilidade a outras janelas de decisão é só descritiva; a invariância com o início é um corolário do modelo, não um teste direto para todos os inícios.

### Pré-registo

- **Não foi feito com ocultação.** O mesmo agente (de inteligência artificial) escreveu o modelo, correu os testes de desenvolvimento e redigiu o protocolo. Não houve um segundo grupo que escolhesse níveis ou inícios sem ver os dados.
- **Os níveis foram escolhidos depois de ver dados de desenvolvimento.** O próprio protocolo o diz (l. 54, 193). O argumento de que isso não prejudica as conclusões porque as sementes são novas é razoável para o tamanho do efeito, mas não retira o enviesamento da escolha de onde procurar.
- **A prova de ordem é o histórico de commits.** As datas de um commit são escolhidas por quem o cria. O mesmo problema foi reconhecido no M14 (`docs/m14-evidence-robustness.md`, l. 131).
- **Não se pode mostrar que as sementes 44000 a 44999 nunca correram.** `vv-rocket land` não tem guarda de sementes.
- **O executor e a análise não existem.** O protocolo é um plano de plano: os dois scripts, o ficheiro de congelamento e o hash do binário ainda não existem. O seu comportamento está descrito em prosa, não especificado.

### Revisão

- **Toda a revisão anterior foi feita por agentes.** O protocolo, o rascunho que o precedeu, as investigações M13 e M14 e as suas revisões «independentes» foram feitos por agentes de inteligência artificial; as revisões independentes foram feitas por outros agentes, não por pessoas. O M13 di-lo (`docs/m13-discovery-lab.md`, l. 120). O M14 não o afirma: refere revisões independentes sem dizer quem as fez. **Revisão por agentes não é revisão humana por pares.** Este pacote pede a primeira leitura humana.
- **Os resultados sobre o instante de início do viés são exploratórios.** Nada neste pacote os confirma.
- **O revisor anterior também viu dados.** Houve um revisor que correu as sementes 45000 a 45003; esses dados são de desenvolvimento e estão gastos.

## Limitações deste pacote

- **Foi escrito por um agente de inteligência artificial**, a pedido do responsável pelo projeto. Pode conter erros próprios. Todos os números e citações devem ser tratados como afirmações a conferir, não como factos estabelecidos.
- **Só aritmética.** Não se correu nenhum simulador, campanha, `vv-exec`, `vv-rocket` ou `cargo`, nem teste algum do repositório. Os números que dependem do simulador (taxas por célula, 30 de 30, b50 = 11,89 m, os 35 compromissos) foram lidos dos ficheiros de evidência e do M13/M14, não recalculados.
- **O cálculo de H3 é exato, não a reamostragem do protocolo.** Usa os mesmos pressupostos que a reamostragem de 20 000 repetições (l. 176 a 179) e dá os mesmos números, mas não é uma repetição dela.
- **Um único commit.** Todos os hashes e linhas são de `bec7b3f`. Os hashes vêm sempre do blob. Comparou-se a cópia de trabalho com o blob só para 5 ficheiros (protocolo, alegação, caso base, previsão e modelo), e os bytes coincidiam.
- **Reprodução do `source_sha256` sem compilar.** O valor `295a45b2...` foi recalculado em Python a partir dos blobs, copiando a lista e o algoritmo de `crates/vv-rocket/src/lib.rs`. Validou-se a reprodução com os commits `1195c1b` e `8be03e4`, que dão o valor do pacote M13, mas não se compilou o simulador para confirmar o valor que ele escreve.
- **Leitura do código, não execução.** As afirmações sobre o comportamento do controlador (por exemplo, que `robust` e `guarded` diferem só na regra 1 e na regra 2) vêm da leitura de `landing_controller.rs` e `landing_types.rs`, que se acredita estar certa, mas não foi testada. O protocolo propõe verificações estruturais para a testar.
- **Não se avaliou a independência entre sementes** (`SplitMix64` com estado inicial `seed ^ fonte × constante`), nem se usaram sementes protegidas.
- **Não se verificou o tempo até ao contacto nas sementes dispersas.** O contacto nominal (23,3 a 23,6 s) vem de `docs/m9-powered-landing.md`, l. 241, para a semente 0 do caso nominal do M9, com os controladores `baseline` (23,63 s) e `robust` (23,27 s); não é uma medida do `guarded` no caso do G3.
- **Não se reviu o código do `vv-exec`, do Studio nem dos módulos M10 a M18.** Só se leu o que o protocolo cita: `exec/src/seeds.rs`, `exec/src/investigate.rs` (guardas e Halton) e `exec/src/search.rs` (quantização).
- **O pacote não decide nada.** Não aprova, não congela, não recomenda executar. As perguntas assinalam onde há dúvidas; a decisão é do responsável pelo projeto.
- **O pacote não inclui os scripts nem o executor do protocolo**, que não existem. O único programa incluído é o do apêndice de `independent-checks.md`.

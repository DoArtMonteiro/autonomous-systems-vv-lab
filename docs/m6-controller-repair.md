# Reparação do controlador e regressão (M6)

O M6 transforma as falhas encontradas pelo motor adversarial num ciclo verificável: encontrar uma falha, propor uma alteração ao controlador, medir a alteração nas mesmas cargas e procurar falhas novas que a alteração tenha criado. Um controlador não melhora só porque uma falha antiga desaparece.

O binário `vv-repair` executa a experiência; `scripts/m6_repair_lab.py` repete-a, reproduz a evidência, analisa os pares e gera um relatório HTML estático.

## Resumo: resultado negativo

**Pergunta.** Alguma alteração pequena e controlada ao controlador canónico, ou ao tratamento de comandos pendentes no atuador, reduz as violações de segurança encontradas pelo motor adversarial sem custar mais de 10 missões concluídas por mil, nas mesmas cargas emparelhadas?

**Resposta: não.** Critérios registados antes de cada execução: IC 95%, perda de missões concluídas até 10 por mil, aumento médio da distância restante até 100 mm, pelo menos 200 pares reservados. Nenhuma candidata passou os dois critérios fixos (segurança e progresso). As duas que chegaram a confirmação independente falharam um critério cada: `watchdog_2` o de progresso, `watchdog_2_fast_recovery_cancel` o de segurança. A experiência termina com uma rejeição reproduzível. Os limiares foram fixados antes da execução final, depois de uma execução exploratória nas mesmas sementes; as regras acrescentadas após a revisão independente só os tornaram mais exigentes, e nada mudou depois dos resultados de confirmação (ver «Regras acrescentadas depois da revisão independente»).

| Intervenção | Hipótese | Segurança (pares reservados) | Progresso | Decisão |
| --- | --- | --- | --- | --- |
| `watchdog_2` (*watchdog* de 3 para 2 ticks) | Entrar em *fallback* dentro do prazo de 2 ticks | Melhora e repete-se: 83 corrigidos / 0 quebrados (sementes 101 a 112), 87 / 0 (201 a 212), 88 / 0 (confirmação final) | Falha: 19, 13 e 16 missões perdidas por mil (de 723, 689 e 683), acima de 10 | Rejeitada; fica como comparador |
| `watchdog_2_fast_recovery` (*watchdog* 2, recuperação 1) | Recuperar missões sem ficar em *fallback* com perdas alternadas | Melhora no agregado (82 / 10, estrita -4,4 pp), mas regride em `delayed_after_fallback`: 0 / 4, limite inferior +0,018 pp, p exato 0,125 (evidência fraca) | Passa (5 perdidas, 13 ganhas) | Rejeitada |
| `watchdog_2_brisk` (passo a 125%) | Recuperar o tempo perdido em *fallback* | Piora: 99 / 104, ultrapassagens em `x_first_overshoot` | Falha: 331 de 689 missões perdidas | Rejeitada |
| `cancel_pending_on_fallback` (opção da biblioteca, por omissão desligada) | Um comando atrasado não deve mover o veículo em *fallback* | Sem efeito ao nível do par. Em `delayed_after_fallback`: elimina `no_motion_in_fallback` (317 para 0 pares), mas os mesmos pares continuam a falhar `command_applied` | Passa (+64 mm no agregado, +190 mm em `delayed_after_fallback`) | Rejeitada (`no_effect`) |
| `watchdog_2_cancel` (*watchdog* 2 e cancelamento) | Juntar a melhoria temporal ao cancelamento | 83 / 0, estrita -4,4 pp, resolve 15 de 36 casos do corpus (desenvolvimento, sementes 101 a 112) | Falha: 14 de 723 (19 por mil) | Rejeitada; não confirmada |
| `watchdog_2_fast_recovery_cancel` (iteração única, congelada) | *Watchdog* 2, recuperação 1 e cancelamento | Melhora no agregado (81 / 15, estrita -4,2 pp), mas regride em `delayed_after_fallback`: 0 corrigidos / 8 quebrados na confirmação, limite inferior +0,49 pp (critério registado), p exato 0,0078 | Passa (4 perdidas, 16 ganhas) | Rejeitada |

`half_stride`, `strict_gate` e `x_first` (controlos) estão em «Resultados medidos»; todos rejeitados.

**Contraexemplo representativo.** `corpus/delayed_after_fallback/07`: 7 ticks, sem átomos além da base da suite (perda de GPS e um comando atrasado 3 ticks). A base viola `safe_fallback`, `no_motion_in_fallback`, `command_applied` e `command_resolution`. Com o cancelamento, o veículo já não se move em *fallback*, mas o comando cancelado nunca é aplicado e continua a falhar os dois contratos de 2 ticks. No corpus o caso conta como `resolved` para a candidata, porque a classe do caso é `no_motion_in_fallback`; as duas violações restantes estão na tabela de reprodução do relatório, e o traço por tick da base (ticks 6 e 7) mostra o comando atrasado a mover o veículo em *fallback*.

**Porque foi rejeitada.** O resíduo dominante está no atuador, não no controlador: com 3 ticks de atraso e prazos de 2, nenhum parâmetro nem o cancelamento limpam esses pares. A regressão da candidata congelada vem de `recovery_after_ticks = 1` (no desenvolvimento, `watchdog_2_cancel`, sem recuperação rápida, não quebrou nenhum par): o comando emitido no único tick bom perde o prazo de 2 ticks, é perdido pelo atuador ou cai no *fallback* seguinte.

**Limites.** Modelo cinemático 2D com aritmética inteira; é evidência de simulação, não garantia de um veículo real. As 8 quebras vêm de 6 cargas e 4 sementes geradoras, por isso o p ao nível do par sobrestima a evidência; com poucos pares discordantes, Wald e o teste exato podem discordar. A cobertura de 80% do M6 não está verificada até a CI correr sobre esta árvore. O modelo do revisor que escolheu as sementes não ficou registado (`UNVERIFIED`). Nada foi executado em PX4/SITL. As sementes 1 a 8, 101 a 112, 201 a 212 e as 12 da confirmação final estão gastas.

**Reproduzir.** O `evidence_sha256` tem de coincidir com os valores abaixo e `source_sha256` tem de ser `620f7603…`; a execução em WSL2 Ubuntu 24.04 deu os mesmos hashes (ver «Verificações»).

```sh
cargo build --release --locked
python scripts/m6_repair_lab.py --experiment scenarios/m6/experiment.json --output-root runs/m6-main             # f340eda7…
python scripts/m6_repair_lab.py --experiment scenarios/m6/confirmation.json --output-root runs/m6-confirmation    # 20369bdd…
python scripts/m6_repair_lab.py --experiment scenarios/m6/cancellation-dev.json --output-root runs/m6-cancel-dev  # 0b53b59a…
python scripts/m6_repair_lab.py --experiment scenarios/m6/cancellation-confirm.json --output-root runs/m6-cancel-confirm  # 557e20e0…
target/release/vv-repair replay runs/m6-cancel-confirm/run
```

Cada execução grava `report.html` (base contra candidatas, violações resolvidas e novas, piores contraexemplos, traços, desempenho e comandos) e `summary.json` com os hashes.

## O que muda na biblioteca

A única alteração à biblioteca é opcional e foi aprovada pelo responsável: `ActuatorConfig.cancel_pending_on_fallback` (por omissão `false`, omitido do JSON quando falso) faz o atuador descartar os comandos atrasados pendentes enquanto o controlador está em *fallback*, com o evento `pending_cancelled_on_fallback`. O motor passa ao atuador o estado de segurança do passo (`ActuatorModel::apply_in_state`).

- Comportamento por omissão: igual. A campanha M1 reproduz os hashes canónicos fixados (`scenarios/canonical-seed-42.json`). Logo depois da alteração, a evidência da experiência principal era igual à anterior em tudo exceto `source_sha256` e os hashes que o incluem. A evidência atual difere também por duas alterações do `vv-repair`, não da biblioteca: o campo `effective.*.cancel_pending_on_fallback` e a correção de `untriggered` descrita mais abaixo, que passou 7 casos do corpus de `untriggered` para `resolved`. Nenhum critério, decisão ou resumo dos pares reservados mudou.
- `ACTUATOR_SCHEMA_VERSION` não muda: o campo só é escrito quando ativo e o evento `pending_cancelled_on_fallback` só aparece com ele ativo. Um leitor anterior a esta versão recusa um artefacto com o cancelamento ativo (`deny_unknown_fields`).
- `source_sha256()` passa de `38039c255f6f60c8b1a5d50332c2280665df469a1a00ad43b06f5df47bf643cb` (manifestos M4 e M5) para `620f76031548075a66a2e4117956a29d1b63d846263b4aed224b74e2e2501f6b`. Manifestos M4, M5 e M6 gravados com o valor antigo deixam de passar `replay-m4` com esta versão e têm de ser regenerados. Um teste unitário de `vv-repair` fixa o novo valor.
- O oráculo não muda: um comando cancelado não conta como aplicado nem como resolvido, por isso `command_applied` e `command_resolution` continuam a falhar quando o comando nunca é executado.

As outras candidatas são configurações do controlador canónico. O `vv-repair` reutiliza os módulos do `vv-adversary` através de `#[path]`, sem os alterar.

Uma lei de controlo nova exigiria alterar `src/controller.rs` e `src/engine.rs`, que entram no hash. Isso pede uma nova versão da política e uma atualização aprovada dos valores canónicos; fica fora do M6.

## Contrato da experiência

`scenarios/m6/experiment.json` (esquema `vv-repair.experiment.v1`, campos desconhecidos recusados) define:

- `suites`: cenário, contratos e atuador de cada base, com uma descrição.
- `sim_seeds`, `tuning_seeds` e `heldout_seeds`: as sementes de afinação e as reservadas são disjuntas.
- `workloads_per_seed`, `minimize_budget`, `max_corpus_per_suite`: orçamentos explícitos; o total planeado de avaliações tem um limite.
- `acceptance`: critérios de aceitação registados antes da execução (nível dos intervalos, perda máxima de missões concluídas, margem de não inferioridade da distância restante, mínimo de pares).
- `baseline` e `candidates`: política V1 e um conjunto fechado de parâmetros (`fallback_after_ticks`, `recovery_after_ticks`, `confidence_threshold_permille`, `max_observation_age_ticks`, `stride_permille`). Cada configuração tem uma justificação. As configurações com `role: control` declaram em `expect` o veredicto previsto.

O cenário com as substituições é validado pela biblioteca. Cada configuração tem `config_sha256` na evidência, e os parâmetros efetivos por suite ficam registados.

## Pipeline

1. **Cargas emparelhadas.** Para cada semente, o gerador uniforme do `vv-adversary` (domínio de semente próprio do M6) produz conjuntos de átomos de falha. Cada conjunto entra inteiro e projetado por família: sensor (GPS), temporização (atraso e perda de observações) e atuador. A carga sem átomos é o controlo nominal. As cargas dependem só da base, nunca da candidata.
2. **Avaliação.** Cada configuração corre todas as cargas com as mesmas sementes de simulação. Cada linha regista as classes violadas (`tipo/propriedade/mecanismo`), os contratos `INCONCLUSIVE`, os contratos ativados, o resultado da missão, o tick de conclusão, os ticks em *fallback* e em movimento, os eventos do atuador e a distância restante.
3. **Corpus.** Cada classe que a base viola nas sementes de afinação é reduzida na base (`ddmin`, truncagem e simplificação do M5) e gravada como caso M4 completo, que `vv-lab replay-m4` reproduz.
4. **Reprodução do corpus.** Cada caso reduzido corre em todas as configurações. O estado é `persisted`, `shifted` (mesma propriedade, outro mecanismo), `inconclusive`, `untriggered` (o contrato nunca foi ativado) ou `resolved`. Só `resolved` conta como resolução.
5. **Classes novas.** Uma classe que uma candidata mostra em alguma carga e que a base nunca mostra nessa suite é reduzida na candidata e reproduzida em todas as configurações.
6. **Análise.** Pares (carga, semente) nas sementes reservadas e no controlo nominal: casos corrigidos e quebrados, teste exato de McNemar, diferença de risco emparelhada com intervalo de Wald, intervalos de Wilson, diferenças médias de distância, *fallback* e movimento, por suite e por família, e frequência de cada classe.

## Veredicto

O veredicto tem dois eixos e uma decisão:

- Segurança: `improved` exige o limite superior da diferença de risco abaixo de zero, nenhuma classe nova e pelo menos um caso do corpus `resolved`; `regressed` se o intervalo de alguma suite ficar acima de zero; `mixed` ou `no_effect` nos outros casos.
- Progresso: `pass` se a perda de missões concluídas e o aumento da distância restante ficarem dentro das margens registadas.
- Decisão: `accept` só com segurança `improved`, progresso `pass` e pares suficientes.

Também são assinalados o sobreajuste (melhoria nas sementes de afinação que não se mantém nas reservadas), as candidatas que mudam o oráculo e as suites onde a candidata é igual à base.

## Execução

```sh
cargo build --release --locked
target/release/vv-repair run --experiment scenarios/m6/experiment.json --output runs/m6-manual
target/release/vv-repair replay runs/m6-manual
python scripts/m6_repair_lab.py --output-root runs/m6
python scripts/m6_px4_export.py runs/m6/run --output runs/m6/px4-replay-requests.json
```

`m6_repair_lab.py` executa a experiência duas vezes e exige os mesmos bytes, corre `vv-repair replay`, corre `vv-lab replay-m4` em cada caso reduzido, falha se houver violações sem identidade ou um recálculo independente em desacordo, e grava `analysis.json`, `report.html` e `summary.json`. Os tempos são medidos fora da simulação e só aparecem no resumo e no relatório.

## Candidatas e pressupostos

| Configuração | Alteração | Pressuposto físico ou de controlo |
| --- | --- | --- |
| `watchdog_2` | `fallback_after_ticks` 3 para 2 | A latência do *watchdog* não pode exceder o prazo de 2 ticks de `fallback_response`. A perda de localização é visível num tick; parar mais cedo custa disponibilidade em perdas curtas. |
| `half_stride` | passo comandado a 50% | Metade do deslocamento por tick reduz a distância percorrida por um comando atrasado, continuado ou desviado pelo ruído. Custo: a missão precisa do dobro dos ticks. |
| `watchdog_2_fast_recovery` | *watchdog* 2, recuperação 1 | Mantém a correção temporal sem ficar em *fallback* com perdas alternadas (U,U,R). Risco registado: sair do *fallback* com uma única amostra boa. |
| `strict_gate` (controlo) | limiar de confiança 800 | Controlo de paralisia. A confiança decai com a idade da amostra, por isso 800 só aceita dados do próprio tick e qualquer atraso imobiliza o veículo. O limiar também define o gatilho `localization_unreliable`, por isso muda o oráculo. Previsto: progresso `fail`, decisão `reject`. |
| `x_first` (controlo) | política `x_first` | Política mais fraca do M4. Previsto: segurança `regressed`, decisão `reject`. |

## Resultados medidos

Máquina: Windows 11 (10.0.26300), Python 3.14.6, 16 CPUs, Rust 1.99.0. Experiência `scenarios/m6/experiment.json`: 3 suites, 8 sementes de afinação, 12 reservadas, 2 sementes de simulação, 1385 cargas, 2770 pares por candidata, 1556 reservados. 16 940 avaliações mais 797 na redução; cerca de 13,4 s por execução. Corpus: 36 classes da base, nenhuma deixada de fora pelo limite de 16 por suite. `evidence_sha256` `f340eda72be5720eada59601766fbd3f1e266f20a58edd4aaecb63a15f902b8e` (com a biblioteca e o `vv-repair` atuais; antes era `1a2f3b1b…`, com os mesmos pares e critérios e com a contagem anterior de `untriggered` no corpus).

Uma correção é **vazia** quando a candidata só deixa uma obrigação pendente (mais contratos `INCONCLUSIVE`) ou não se move onde a base se moveu. A diferença de risco **estrita** conta as correções vazias como inalteradas, e é essa que decide o eixo de segurança. "Classes novas" é ao nível da suite; "pares com classe nova" conta os pares reservados onde a candidata acrescenta uma classe que a base não tinha nesse par, mesmo que a base a mostre noutras cargas.

| Configuração | Corrigidos (vazios) / quebrados | Taxa de violação | Diferença de risco (IC 95%) | Estrita (IC 95%) | Missões perdidas / ganhas (de 723) | Classes novas | Pares com classe nova | Corpus `resolved` | Decisão |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `watchdog_2` | 83 (14) / 0 | 40,9% para 35,6% | -5,3 pp [-6,5; -4,2] | -4,4 pp [-5,5; -3,4] | 14 / 3 | 0 | 10 | 9 de 36 | `reject` (segurança `improved`, progresso `fail`) |
| `half_stride` | 5 (0) / 186 | 40,9% para 52,6% | +11,6 pp [+10,0; +13,3] | igual | 248 / 1 | 2 | 206 | 0 de 36 | `reject` (`regressed`) |
| `watchdog_2_fast_recovery` | 82 (4) / 10 | 40,9% para 36,3% | -4,6 pp [-5,8; -3,4] | -4,4 pp [-5,5; -3,2] | 5 / 13 | 0 | 25 | 6 de 36 | `reject` (`regressed` numa suite) |
| `strict_gate` (controlo) | 352 (113) / 54 | 40,9% para 21,8% | -19,2 pp [-21,5; -16,8] | -11,9 pp [-14,0; -9,8] | 71 / 10 | 2 | 104 | 19 de 36 | `reject`, como previsto |
| `x_first` (controlo) | 0 (0) / 129 | 40,9% para 49,2% | +8,3 pp [+6,9; +9,7] | igual | 352 / 0 | 0 | 140 | 1 de 36 | `reject`, `regressed`, como previsto |

### Leitura

- **`watchdog_2` é uma melhoria de segurança real e foi rejeitada pelo critério de progresso.** Nos pares reservados corrigiu 83, 14 delas vazias, e não quebrou nenhum; mesmo sem as vazias, a diferença estrita fica em -4,4 pp [-5,5; -3,4]. Não criou classes ao nível da suite e resolveu 9 casos do corpus, entre eles os seis `fallback_response` e os dois `stop_response` com continuação do atuador em `nominal_stop` e `x_first_overshoot`. Não é uma melhoria limpa: em 10 pares reservados acrescentou uma classe que a base não tinha nesse par, sobretudo `no_motion_in_fallback/delayed_actuation` (de 0 para 3 pares em `x_first_overshoot`; a base só a mostra em sementes de afinação). Perdeu 14 de 723 missões concluídas, 19 por mil contra a margem de 10 por mil. Treze dessas missões terminaram por falta de tempo, não por paragem; um surto de 2 ticks que antes não ativava o *watchdog* custa agora 2 ticks em *fallback* e 2 de recuperação. Na suite `delayed_after_fallback` a base já usa `fallback_after_ticks = 2`, por isso a candidata é igual à base e esses pares não mudam.
- **`watchdog_2_fast_recovery` concretizou o risco registado.** Recupera as missões (5 perdidas, 13 ganhas) e melhora a distância restante em 72 mm por par, mas em `delayed_after_fallback` quebrou 4 pares e não corrigiu nenhum: um comando emitido no único tick bom é aplicado já no *fallback* seguinte (`no_motion_in_fallback/delayed_actuation`) ou falha o prazo de 2 ticks. O limite inferior de Wald é +0,018 pp, mas o teste exato dá p = 0,125; a regressão é evidência fraca e o relatório di-lo.
- **`half_stride` piora.** Com metade do passo, a missão usa mais ticks em movimento e expõe mais comandos às falhas do atuador; aparecem duas classes novas em `x_first_overshoot` (`command_applied` e `command_resolution` com continuação e atraso do atuador) e 248 missões ficam sem tempo.
- **Os dois controlos comportaram-se como previsto.** `strict_gate` tem o melhor número de violações, mas 113 das 352 correções são vazias e a candidata é rejeitada: 71 missões perdidas (39 paradas), duas classes novas e mudança do oráculo. `x_first` regride em `x_first_overshoot` e não conclui nenhuma missão dessa suite.
- **Falhas que nenhuma candidata resolve.** 28 dos 36 casos do corpus não são resolvidos por nenhuma candidata que não seja controlo: `command_applied` e `command_resolution` com atraso do atuador de 3 ticks ou perda de comandos, `no_motion_in_fallback` e `stop_response` com atraso do atuador, e `safe_fallback`. Nenhum parâmetro do controlador encurta o atraso do atuador nem impede que um comando já emitido seja executado durante o *fallback*. Corrigir estas classes exige uma lei de controlo nova (por exemplo, cancelar comandos pendentes ao entrar em *fallback*), que altera a biblioteca.

### Confirmação em sementes novas

`scenarios/m6/confirmation.json` repete a experiência com sementes reservadas que nenhuma execução anterior usou (201 a 212), os mesmos critérios e `x_first` como controlo. `evidence_sha256` `20369bdd27768355d3a6926f5ea567c3ce58cf26fc5e1d78b5185627f2565db7` (antes da opção de cancelamento: `0784a675…`).

| Configuração | Corrigidos (vazios) / quebrados | Estrita (IC 95%) | Missões perdidas / ganhas | Decisão |
| --- | --- | --- | --- | --- |
| `watchdog_2` | 87 (12) / 0 | -4,8 pp [-5,8; -3,7] | 9 / 1 de 689 (13 por mil) | `reject` (segurança `improved`, progresso `fail`) |
| `watchdog_2_brisk` (passo a 125%, criada depois da experiência principal) | 99 (27) / 104 | +2,0 pp [+0,4; +3,7] | 331 / 3 | `reject` (`regressed`) |
| `x_first` (controlo) | 0 / 79 | +5,0 pp [+3,9; +6,1] | 324 / 0 | `reject`, como previsto |

A melhoria de segurança de `watchdog_2` repete-se em sementes novas: nenhum par quebrado e a diferença estrita continua abaixo de zero. A perda de missões desce para 13 por mil, ainda acima da margem de 10. `watchdog_2_brisk` tentou recuperar o tempo perdido em *fallback* com um passo maior e piorou: em `x_first_overshoot` o passo de 625 mm provoca ultrapassagens (41 corrigidos, 102 quebrados). Não foram testadas mais candidatas, para não ajustar o resultado às sementes de confirmação.

### Cancelamento de comandos pendentes em *fallback*

Decisão do responsável: `watchdog_2` não é aceite e fica como comparador; os critérios não mudam. Foi autorizada uma experiência local com a opção `cancel_pending_on_fallback`.

Desenvolvimento (`scenarios/m6/cancellation-dev.json`, sementes reservadas 101 a 112, já usadas, por isso evidência de desenvolvimento). Regra escrita antes da execução: congelar a candidata que passe todos os critérios, preferindo a que muda menos parâmetros; se nenhuma passar, uma única iteração de projeto. A primeira execução, sem a iteração, tem `evidence_sha256` `f9eefb7e…`; a segunda, com a iteração e a correção de `untriggered` descrita abaixo, tem `0b53b59a00b7a6ff070e9dd521c4bb91f6107fddf68a40fd4662ceb678bb4f22`. A tabela usa a segunda.

| Configuração | Corrigidos (vazios) / quebrados | Estrita (IC 95%) | Missões perdidas / ganhas (de 723) | Corpus `resolved` (de 36) | Falha |
| --- | --- | --- | --- | --- | --- |
| `watchdog_2` (comparador) | 83 (14) / 0 | -4,4 pp [-5,5; -3,4] | 14 / 3 | 9 | `completion` |
| `cancel_on_fallback` | 0 (0) / 0 | 0,0 pp | 0 / 0 | 4 | `safety` (`no_effect`) |
| `watchdog_2_cancel` | 83 (14) / 0 | -4,4 pp [-5,5; -3,4] | 14 / 2 | 15 | `completion` |
| `watchdog_2_fast_recovery_cancel` (iteração) | 82 (4) / 10 | -4,4 pp [-5,5; -3,2] | 5 / 13 | 12 | `no_suite_regression` (p exato 0,125) |

O cancelamento funciona: em `delayed_after_fallback`, `no_motion_in_fallback/delayed_actuation` desce de 317 para 0 pares e `safe_fallback` de 337 para 20. Mas cada um desses pares continua a violar `command_applied` e `command_resolution`, porque o atuador atrasa o comando 3 ticks e o contrato dá 2; o critério de segurança mede pares com qualquer violação, por isso não vê melhoria. O critério decide; as contagens por classe não decidem, mas mostram o efeito: em `delayed_after_fallback`, 317 dos 518 pares reservados perdem pelo menos uma classe, e `watchdog_2_cancel` resolve 15 casos do corpus contra 9 de `watchdog_2`. O custo é a distância restante: +64 mm por par no agregado, dentro da margem de 100 mm, mas concentrado em `delayed_after_fallback`, porque os comandos cancelados nunca deslocam o veículo. A iteração juntou o cancelamento à recuperação rápida, cuja regressão vinha de comandos executados no *fallback* seguinte. No desenvolvimento, as 4 quebras restantes são só `command_applied` e `command_resolution`: o comando emitido no único tick bom perde o prazo de 2 ticks, seja executado ou cancelado.

Confirmação (`scenarios/m6/cancellation-confirm.json`), executada uma vez com a candidata congelada `watchdog_2_fast_recovery_cancel`, com o mesmo identificador, política e substituições que no desenvolvimento; só a justificação foi reescrita, por isso o `config_sha256` difere e a prova de congelamento é a comparação campo a campo. A candidata acrescenta uma classe que a base não tinha em 21 pares reservados no desenvolvimento e em 24 na confirmação; o critério `no_new_class` é por suite e passa. As sementes reservadas (7349, 18265, 29581, 83017, 156432, 241907, 318604, 407753, 536218, 672941, 794306, 921685) foram escolhidas por um revisor independente que não viu resultados; o modelo do revisor não ficou registado (`UNVERIFIED`; o próprio declarou `claude-sonnet-5-5`). `evidence_sha256` `557e20e091f2e60b22f5a214720e1e84b4ae0bb1f6cf0b0a108324691bc11890`.

| Configuração | Corrigidos (vazios) / quebrados | Estrita (IC 95%) | Missões perdidas / ganhas (de 683) | Decisão |
| --- | --- | --- | --- | --- |
| `watchdog_2_fast_recovery_cancel` | 81 (1) / 15 | -4,2 pp [-5,4; -3,0] | 4 / 16 | `reject`: em `delayed_after_fallback` 0 corrigidos e 8 quebrados, limite inferior +0,49 pp, p exato 0,0078 |
| `watchdog_2` (comparador) | 88 (12) / 0 | -4,9 pp [-6,0; -3,9] | 11 / 2 (16 por mil) | `reject`: `completion` |
| `x_first` (controlo) | 6 (6) / 76 | +4,9 pp [+3,9; +6,0] | 330 / 1 | `reject`, como previsto |

Conclusão: nenhuma candidata passa os dois critérios fixos na confirmação independente. A regressão da candidata congelada repete-se nas sementes novas e falha o critério registado (0 corrigidos, 8 quebrados, p exato 0,0078 ao nível do par). As 8 quebras vêm de 6 cargas, 5 sorteios e 4 sementes geradoras; duas cargas, projeções do mesmo sorteio, quebram nas duas sementes de simulação, por isso o p ao nível do par sobrestima a evidência. Das 8 quebras, 5 são `command_applied` e `command_resolution` por atraso do atuador, 2 são `command_applied` por perda do comando e 1 é `safe_fallback` com `no_motion_in_fallback` e `stop_response` por continuação do atuador, um mecanismo que o cancelamento não cobre.

O resíduo dominante não está no controlador: com um atraso do atuador de 3 ticks e prazos de 2 ticks, nenhum parâmetro nem o cancelamento tornam esses pares limpos. A rejeição da candidata congelada, porém, vem de um parâmetro do controlador, `recovery_after_ticks = 1`: no desenvolvimento, `watchdog_2_cancel` não quebrou nenhum par e falhou só a margem de conclusão. A experiência termina com esta rejeição.

### Regras acrescentadas depois da revisão independente

Correção de avaliação feita durante a experiência de cancelamento: o estado `untriggered` só se aplica a contratos com gatilho (`bounded_response`, `bounded_progress`). Antes, um contrato `never` que passava (por exemplo `no_motion_in_fallback`) era contado como `untriggered` em vez de `resolved`. A correção só altera as contagens do corpus e o critério `corpus`, e nenhuma decisão mudou; as experiências principal e de confirmação foram regeneradas com ela, e os números deste documento já a incluem.

As margens de `acceptance` foram escritas antes da execução final, mas depois de uma execução exploratória com as mesmas sementes. A revisão independente da primeira execução levou a duas regras, ambas mais exigentes: as correções vazias contam como inalteradas no eixo de segurança, e uma candidata que muda o oráculo nunca é aceite. Também subiu o limite do corpus de 8 para 16 classes por suite, porque o limite de 8 deixava 13 classes da base fora do corpus. As previsões dos controlos estavam escritas na justificação de cada um antes da primeira execução completa; o bloco `expect`, verificado pela análise, foi acrescentado depois. Nenhuma decisão mudou com estas alterações.

### Verificações

- Execução e repetição: 331 de 331 ficheiros iguais byte a byte; `vv-repair replay` OK; `vv-lab replay-m4` 40 de 40.
- Recálculo independente: 0 `disagree`; 0 violações sem identidade.
- Plataformas, com a biblioteca atual (`source_sha256` `620f7603…`): em Linux (WSL2 Ubuntu 24.04, kernel 6.18.33.2, Python 3.10.22, Rust 1.99.0) as quatro experiências M6 (`experiment`, `confirmation`, `cancellation-dev`, `cancellation-confirm`) deram o mesmo `evidence_sha256` que em Windows. Nas duas plataformas passaram `cargo fmt --check`, Clippy, todos os testes Rust (incluindo `tests/m6_cancellation.rs` e os testes do atuador), os 145 testes Python, as campanhas M1 a M4, a minimização, a reprodução e a campanha adversarial; `scripts/check_platform_artifacts.py --require-m4` passou sobre as saídas das duas plataformas, incluindo os hashes canónicos do M1. `vv-repair replay` reproduziu as quatro experiências byte a byte.
- Cobertura: não medida localmente; não há ferramentas LLVM instaladas e a sua instalação não foi autorizada. A CI aplica o limite de 80% das linhas quando uma PR for aprovada; até lá, a cobertura do M6 não está verificada.

## Preparação para PX4

O trabalho PX4/MAVSDK Gate 1A é um fluxo separado e governado. O M6 não instala nem executa WSL, Docker ou PX4, não escreve no registo do Gate 1A e não declara validação SITL.

Estado observado nos artefactos do Gate 1A (só leitura): 10,47 h de 16 h usadas; o M28 estabeleceu a causa da recusa do modo missão no M27 e deixou o *patch* r2 por integrar; os dois lançamentos do M28 pararam na verificação de memória antes de o PX4 arrancar; ainda não há evidência S0/B0. O esquema `m5.experiment.v1` só injeta `gps_param_off`, `gps_inject_off`, `motor1_off` e `battery_off`.

`scripts/m6_px4_export.py` propõe uma interface: converte cada contraexemplo M6 num pedido `vv-repair.px4-replay-request.v1` com os itens de missão (x/y para este/norte, altitude de cruzeiro do Gate 1A), o mapeamento de cada átomo e a propriedade do Gate 1A que observa o mesmo requisito (`hf1` para `fallback_response`, `ef1b` para movimento em *fallback*). Cada pedido fica `mappable`, `partial` ou `not_mappable`, com a razão. Na execução medida, os 40 contraexemplos ficaram `not_mappable`: todos têm pelo menos um átomo de comunicação, ruído GPS ou atuador terrestre sem equivalente. Para reproduzir casos selecionados em PX4 é preciso, por decisão do responsável do Gate 1A: um canal de injeção para atraso e perda de telemetria, falhas de GPS com fim de janela, uma propriedade de geovedação, e a conversão do pedido para `m5.experiment.v1` com `handoff_sha256` e limites atribuídos pelo Gate 1A.

Para o cancelamento em *fallback*, os 37 contraexemplos da confirmação também ficaram `not_mappable`. A falha que o cancelamento trata depende de um comando atrasado no atuador, e o Gate 1A não tem canal de injeção de atraso de comandos nem um modelo de fila de comandos equivalente. Testar a mesma ideia em PX4 exigiria um canal novo de atraso de comandos e uma propriedade sobre movimento depois da entrada em modo de segurança (próxima de `ef1b`). Nada disto foi executado: não houve SITL, instalação nem alteração de WSL, Docker ou configuração do anfitrião.

## Limitações

- Evidência de simulação num modelo cinemático 2D com aritmética inteira. Não é uma garantia de segurança de um veículo real.
- As candidatas são parâmetros do controlador canónico. Leis de controlo novas exigem uma atualização aprovada dos hashes da biblioteca.
- O limiar de confiança e a idade máxima definem também o gatilho dos contratos; candidatas que os alteram mudam o oráculo.
- O emparelhamento fixa o calendário exógeno (GPS, comunicações e atuador), não a trajetória. Pares em sementes de simulação diferentes partilham a carga; os intervalos tratam-nos como independentes e ficam um pouco estreitos. Com poucos pares discordantes, o intervalo de Wald pode discordar do teste exato.
- As missões têm horizonte fixo; uma candidata mais lenta perde missões por falta de tempo.
- Não há modelo de ambiente (vento, inclinação, atrito). A continuação e a perda de movimento do atuador substituem perturbações; o ruído GPS substitui entradas contraditórias.
- O corpus é reduzido só na base e limitado por suite. A identidade de classe ignora ticks.
- As cargas vêm de amostragem uniforme, sem enviesamento para fronteiras. Não encontrar uma classe não prova que não exista.
- As margens de aceitação foram escritas antes da execução final, mas depois de uma execução exploratória com as mesmas sementes; ver as regras acrescentadas depois da revisão.

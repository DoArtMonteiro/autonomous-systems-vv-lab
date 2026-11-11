# Proposta do M13: plataforma de verificação de sistemas autónomos

Estado: **proposta**, para decisão do proprietário. Nada aqui foi implementado.

## Porquê agora

A revisão independente do M10 (3 de novembro de 2026) encontrou, à mão e em sementes de desenvolvimento, uma classe de contraexemplos que os varrimentos registados não podiam ver. Era um caminho de confiança falsa com rampas coerentes lentas perto da ignição. Os varrimentos usavam uma só magnitude e registavam só o alerta vertical. A mesma revisão mostrou que as conclusões dependem do agregado escolhido: a regressão de `gnss_bias` só aparece em U, e uma célula duplicada conta duas vezes. Estes são problemas do método de verificação, não do foguetão. O M13 trata-os como capacidades reutilizáveis e mensuráveis, em vez de acrescentar física.

Fora do âmbito: alegações de segurança de um veículo real ou de certificação. Toda a evidência continua a ser de simulação idealizada, com envelopes de validade declarados.

## Arquitetura

- **Plataforma partilhada:** o contrato `vv-domain`, o motor `vv-exec` (plano, registo, reprodução, estatística, relatório), um novo grafo do caso de segurança e um novo serviço de pesquisa adversarial.
- **Domínios:** o foguetão (M8 a M10), o veículo terrestre (M1 a M6), com caminho em processo no `vv-exec`, e um terceiro domínio de referência (ver capacidade 3). Cada domínio declara as suas sementes protegidas, os seus parâmetros com unidade e envelope, e um portão de paridade com a sua linha de comandos canónica.
- **Regra de separação:** o código partilhado não conhece nenhuma física; cada domínio não conhece a estatística nem o caso de segurança.

## Capacidade 1: casos de segurança legíveis por máquina

Um grafo versionado: alegação, requisito, pressuposto, experiência, evidência, limite de validade e contraexemplo. Cada nó de evidência aponta para um commit, um `plan_sha256`, o hash de `records.jsonl` e a verificação `vv-exec verify` que o recalcula. Um contraexemplo ligado a uma alegação muda-a automaticamente para "refutada" até haver uma emenda.

- **Pergunta:** um verificador automático consegue dizer, para cada alegação de segurança do M9 e do M10, se está suportada, refutada ou sem evidência, só a partir do grafo e das evidências recalculadas?
- **Critério de refutação:** testes de mutação sobre a evidência (registo falsificado, teste removido, plano diferente, envelope ultrapassado, agregado que duplica uma célula). A hipótese falha se algum dos 50 defeitos injetados deixar uma alegação em "suportada".
- **Aceitação:** 100 % das alegações do M9 e do M10 no grafo, cada uma com evidência recalculável; 50 de 50 defeitos detetados; 0 alegações suportadas sem evidência.

## Capacidade 2: descoberta adversarial de experiências

Pesquisa guiada sobre início, magnitude, duração e combinação de falhas: bisseção de fronteira, pesquisa local e sequências de baixa discrepância. A pesquisa decorre em quarentena: só sementes de desenvolvimento, orçamento fixo e registo de todas as avaliações. Cada contraexemplo é reduzido ao mínimo com conservação da identidade da falha, da semente e dos critérios de progresso.

- **Pergunta:** a pesquisa guiada redescobre as classes de contraexemplos que a revisão do M10 encontrou à mão com menos avaliações do que a amostragem aleatória? São duas classes: o isolamento errado em rampas lentas perto da ignição e a perseguição limitada pior com perdas tardias.
- **Critério de refutação:** com o mesmo orçamento e sementes, a pesquisa guiada não encontra mais classes distintas do que a amostragem aleatória em 10 repetições com sementes de pesquisa diferentes.
- **Aceitação:** as duas classes redescobertas em no máximo 2 000 avaliações cada, na mediana de 10 repetições. Cada contraexemplo reduzido reproduz-se byte a byte com `vv-exec verify`. 0 sementes protegidas usadas, verificado pelo registo da pesquisa.

## Capacidade 3: verificação entre domínios

O mesmo contrato de requisitos, invariantes, envelopes e relatório, sem alterações, em três domínios:

- o foguetão;
- o veículo terrestre;
- um terceiro domínio com física diferente: um multirotor de manutenção de altitude e atitude, sem armamento, com sensores e falhas próprios.

- **Pergunta:** o contrato e o pipeline estatístico são realmente independentes do domínio?
- **Critério de refutação:** é preciso mudar código partilhado (contrato, motor, estatística, relatório ou caso de segurança) para acrescentar o terceiro domínio, ou o código partilhado tem ramos por domínio.
- **Aceitação:** o terceiro domínio entra só com código no seu próprio pacote. Um conjunto de testes de contrato passa nos três domínios. Cada domínio tem um portão de paridade com 0 diferenças. O domínio terrestre corre em processo no `vv-exec`.

## Capacidade 4: validade do modelo e incerteza

Análise de sensibilidade com Sobol de baixa discrepância (um novo `design.kind`, sem mudar os hashes dos planos existentes), desajuste de modelo de sensores e sensibilidade numérica:

- desajuste de sensores: ruído real 1,5 vezes o modelado, ruído correlacionado e caudas pesadas;
- sensibilidade numérica: passo, ordem do integrador e formato dos números.

Cada conclusão do relatório passa a ter uma margem de robustez: o desajuste mínimo que a inverte.

- **Pergunta:** as conclusões do M9 e do M10 sobre ordem de controladores e classe de segurança resistem a desajustes plausíveis do modelo dentro do envelope declarado?
- **Critério de refutação:** uma conclusão publicada inverte-se com um desajuste dentro do envelope. Por exemplo: o isolamento errado de B+ sem falha passa de 0 com ruído 1,5 vezes o modelado, ou a ordem `robust` contra `guarded` muda com o passo dentro da tolerância de convergência.
- **Aceitação:** todas as conclusões do M9 e do M10 com margem de robustez calculada. As que se invertem dentro do envelope ficam marcadas como dependentes do modelo nos relatórios e no caso de segurança. Índices de Sobol com intervalos cuja cobertura é verificada contra a função de Ishigami (cobertura nominal de 95 %, aceitação entre 92 % e 98 % em 200 repetições).

## Desenho experimental comum

- Sementes: desenvolvimento para descoberta e afinação. As sementes de avaliação e de reserva continuam com o proprietário e só entram com um manifesto de congelamento aprovado.
- Cada hipótese tem critério, estatística e multiplicidade escritos antes de correr. Os relatórios são exploratórios até haver congelamento.
- Orçamentos: no máximo 2 milhões de execuções por campanha e 24 h (tetos do `vv-exec`). Artefactos retidos só por política.

## Ordem proposta

1. Integrar M11 e M12 em `main` sem M10 (PR A e PR B do painel de decisão), com proteção de `main` ativa.
2. Grafo do caso de segurança sobre as alegações já publicadas (capacidade 1). É o que dá valor às outras três.
3. Pesquisa adversarial (capacidade 2), validada contra os contraexemplos conhecidos do M10.
4. Desajuste de modelo e Sobol (capacidade 4).
5. Terceiro domínio (capacidade 3), por último: é a maior quantidade de código novo e só prova algo se as três primeiras já forem genéricas.

## Riscos

- O grafo do caso de segurança pode virar burocracia. A regra contra isso: só nós ligados a evidência recalculável e testes de mutação na CI.
- A pesquisa adversarial pode sobreajustar às sementes de desenvolvimento. Mitigação: separar sementes de pesquisa e de confirmação dentro do conjunto de desenvolvimento.
- Um terceiro domínio pode tornar-se proliferação de funcionalidades. Só avança se o critério de refutação da capacidade 3 for posto à prova.

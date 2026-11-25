# M19.2: Belief vs Truth, protótipo de investigação

Protótipo isolado, em `spikes/m19-belief-truth/` (candidato experimental principal, iteração 2) e `spikes/m19-belief-truth-iteration3/` (artefacto exploratório, iteração 3). Não altera o Studio nem nenhum crate. Não simula nada: lê uma corrida guardada e mostra, lado a lado, o que aconteceu, o que o controlador acreditava, quando os dois divergiram e porque isso importou.

Estado: por decisão do dono em 2026-11-25, a **iteração 2** (commit `dae67fa`, `spikes/m19-belief-truth/`) é o **candidato experimental principal**, congelada em 2026-11-25, à espera de teste com pessoas; não é uma melhoria de utilização aceite. Respeitou o limite de duas iterações. A **iteração 3** (`spikes/m19-belief-truth-iteration3/`, com todo o seu historial) fica preservada como **artefacto exploratório**: excedeu o limite de duas iterações substantivas. O excesso foi um erro de orquestração, fica declarado e não é reinterpretado nem apagado (classificação independente em `docs/evidence/m19/reviews/06-classification-of-the-final-pass.md`). Ficam congeladas mais alterações visuais ou de interação substantivas; não há funcionalidades novas. A avaliação foi feita por agentes, não por pessoas: iteração 1 15,5/20, iteração 2 19,5/20, iteração 3 18,5/20 (15,5 em leitura estrita). A pontuação mais alta da iteração 2 (19,5 contra 18,5) é informação de apoio, não prova de que pessoas a usem melhor. Nenhuma das duas está validada com pessoas. O instrumento de avaliação original (chave de respostas e perguntas em `docs/evidence/m19/belief-truth/evaluation/`) está exposto publicamente. Fica preservado como evidência histórica (ratificado pelo dono em 2026-11-25) e não serve para uma futura avaliação humana a frio. Um instrumento novo é preparado à parte e mantido fora do repositório público; só o seu hash fica registado. Qualquer correção factual ou de segurança posterior é comunicada em separado, sem reabrir a experiência. Os ficheiros congelados e os seus sha256 estão em `spikes/m19-belief-truth/FROZEN.json` e `spikes/m19-belief-truth-iteration3/FROZEN.json`; `tests/test_m19_belief_truth_frozen.py` falha se mudarem. Os testes da iteração 2 estão em `tests/test_m19_belief_truth.py` e os da iteração 3 em `tests/test_m19_belief_truth_iteration3.py`. Capturas: iteração 1 em `docs/evidence/m19/belief-truth/iteration-1/`, iteração 2 em `iteration-2/` (as da iteração 2 foram tiradas sobre o estado de `dae67fa`) e iteração 3 em `final/`.

## Tese

Um engenheiro percebe o que realmente aconteceu, o que o controlador acreditava, quando os dois estados divergiram e porque a divergência importou.

## Dados e proveniência

Só dados guardados, sem simulação nova e sem sementes: `desktop/domain-rocket/tests/fixtures/stored-by-0.15.0/` (`record.json`, `trace.json`, `verification.json`, `run.json`, `case.json`).

- Corrida: semente 5002 (semente de desenvolvimento), política `guarded`, falha `gnss_bias` de 15 m em x e z da posição GNSS, de 8,0 s a 40,0 s. O toque no solo ocorre aos 22,955 s.
- Traço amostrado de 0,1 s em 0,1 s (231 amostras: 230 periódicas e a amostra de toque, fora da grelha).
- Não existe covariância em lado nenhum: o estimador é de ganhos fixos (`crates/vv-rocket/src/landing_controller.rs`, `update_robust`).

Cadeia de proveniência:

1. `extract.py` lê o fixture, verifica o sha256 de cada ficheiro contra os valores que a própria corrida declara (`run.json` para `case`, `trace` e `verification`; `record.json#/provenance/artifacts` para os quatro que declara) e escreve `data.json`. O `record.json` não declara hash de si próprio, por isso o hash observado fica fixado no teste e registado no `data.json` (campo `pinned_only`).
2. Cada valor de `data.json` tem uma classe de evidência e uma de três origens: um ponteiro JSON para o ficheiro guardado (`ptr`), uma derivação com nome (`derivation`, registada em `derivations` com a fórmula) ou um facto de código-fonte (`source_facts`, com ficheiro e linhas encontradas pelo próprio extrator a partir de âncoras de texto, nunca escritas à mão).
3. Toda a aritmética derivada vive no extrator. A vista só escala, formata e desenha.
4. Base de proveniência da corrida: o teste existente `a_run_written_by_the_0_15_0_host_verifies_against_its_record_under_the_current_host` (`desktop/domain-rocket/tests/earlier_build.rs`) foi executado nesta iteração e passou (`1 passed; 0 failed`). Mostra que a corrida escrita pelo anfitrião 0.15.0 verifica contra o seu registo sob o anfitrião atual, com a repetição estrita a ser rejeitada por causa da deriva de parâmetros e a repetição de "build anterior" a ser verificada. Saída e comando em `docs/evidence/m19/belief-truth/iteration-1/cargo-earlier-build.txt`. Esse teste fixa a proveniência; não prova que a vista está certa.

## Decisão de renderização: instrumento 2D, não 3D em perspetiva

Decisão do orquestrador, depois de consulta ao conselheiro estratégico.

- À escala verdadeira, 15 m de divergência são invisíveis numa descida de 3000 m, e a perspetiva distorce as distâncias que a tese pede para comparar.
- A vista usa SVG (acessível pelo DOM) em tiras no espaço do erro, com a verdade como linha zero, e um plano da zona de aterragem à escala (janela de ±20 m, os dois eixos à mesma escala).
- Sem dependências novas, sem CDN, JavaScript vanilla em módulos ES, funciona offline a partir de um servidor estático local. O Canvas e o uPlot vendorizado não foram precisos nesta iteração: 231 pontos por série cabem em SVG.
- O Three.js não é usado na iteração 1, pelas razões acima. Uma vista 3D só se justifica se uma iteração futura precisar de orientação do veículo, o que a tese atual não pede.

## Classes de evidência

Cada número e cada elemento visual traz uma etiqueta. As etiquetas têm texto e estilo de contorno diferentes, para que a cor não seja o único portador.

| Etiqueta | Significado |
| --- | --- |
| T | Verdade, guardada no traço |
| E | Estimativa, guardada no traço |
| O | Observação de sensor, guardada no traço |
| D-host | Derivada pelo anfitrião 0.15.0 e guardada (veredictos, métricas do anfitrião, amostra de toque interpolada) |
| D-view | Derivada por esta vista (extrator), com a derivação nomeada |
| S | Do código-fonte, não guardada na corrida |
| K | Comando do controlador, guardado em `command` no traço (acelerador, cardan). Acrescentada na iteração 2, para manter separados o estado real, as observações e as decisões do controlador |
| C | Configuração da missão em `case.json`. Acrescentada às classes pedidas, porque a configuração não é verdade nem estimativa |

Mais o aviso visível **U: nenhuma**. Este estimador não tem incerteza (ganhos fixos, sem covariância). Os sigmas de `case.json` são o ruído do simulador, não a crença do controlador sobre o próprio erro, e não se desenham envelopes com eles.

## O que é guardado, derivado e ilustrativo

Guardado (T, E, O, D-host, C): posições verdadeiras (centro de massa e plano do bocal), estimativa, leituras GNSS e altímetro, atitude do IMU, a bandeira `altimeter_rejected`, eventos, veredictos R1 a R6 e S1 a S5, métricas do anfitrião (`err_z`, `err_h`, `pad_distance`) e a configuração.

Derivado pela vista (D-view), com a derivação nomeada em `data.json`:

- estimativa menos verdade em x e y; GNSS menos verdade; altímetro menos altitude verdadeira do bocal;
- `s_cm` (distância do bocal ao centro de massa) **aproximada**, com a massa de propelente verdadeira guardada como substituto da massa nominal do controlador, que não é guardada;
- altitude do bocal estimada, resíduo altímetro menos estimativa, posição acreditada do bocal e a sua distância ao centro da plataforma, todos **aproximados**.

Do código-fonte (S), com ficheiro e linhas no painel de evidência: a regra `min(estimador, altímetro)` da política `guarded` (`landing_controller.rs`), a regra de rejeição do altímetro, o facto de o GNSS observar o centro de massa e de a falha somar o desvio a x e z (`landing_sensors.rs`), o altímetro medir o plano do bocal, a regra do rótulo `hard_landing` (`landing_verify.rs`) e a origem da amostra de toque (`landing_sim.rs`).

Ilustrativo: nada. A vista não desenha trajetórias inventadas, envelopes de incerteza nem contrafactuais.

## O que a vista mostra

Barra de evidência (semente, política, falha, versão de gravação, amostragem, hashes), quatro passos de leitura, eixo do tempo com um tique por amostra, eventos nos tempos exatos e cursor que só aterra em amostras:

- Tiras de erro em x (eixo com falha), y (eixo de controlo, sem falha) e z. As estimativas são linhas; as observações são marcadores separados, nunca unidos. O erro do altímetro é medido contra a altitude verdadeira do **bocal**, porque o altímetro mede o bocal e a estimativa e o GNSS referem o centro de massa.
- Tira do resíduo altímetro menos estimador contra o limiar de rejeição de `case.json`, rotulada "computada por esta vista, aproximada". O instante de rejeição vem apenas da bandeira guardada (8,18 s, entre as amostras de 8,1 s e 8,2 s), nunca do cruzamento da curva.
- Faixa da fonte de altitude de guiamento: "estimador" antes da rejeição e `min(estimador, altímetro)` depois, rotulada "do código-fonte, não guardado". A linha inferior indica qual das duas altitudes seria a menor (aproximado): o que não é guardado é qual delas o `min()` escolheu.
- Plano da plataforma à escala: círculo R5 de 10 m, ponto verdadeiro do bocal ao toque (R5 = 12,45 m, fora), última estimativa antes do contacto transformada para o bocal (3,29 m, dentro) e a separação entre os dois (15,15 m). Cada ponto diz a que ponto de referência se refere.
- Painel de veredictos com requisitos de missão (R1 a R6) separados dos invariantes de segurança (S1 a S5). Os invariantes têm valor pior e primeira falha, sem instante guardado, e a vista diz isso. O campo `cause` aparece como "falhas ativas (não é atribuição)", porque surge também nos requisitos que passaram. O rótulo `hard_landing` é explicado: é atribuído quando houve contacto e algum requisito (ou S5) falhou; aqui só o R5 falhou e o R1 passou.
- Gaveta de evidência: clicar em qualquer valor mostra a classe, o valor bruto, o caminho JSON (ou a derivação, a fórmula e as entradas) e os factos de código associados.
- Tabela de texto com todas as amostras, como alternativa às tiras.

O que a corrida mostra, lido da vista: antes da falha a estimativa ficou a 0,40 m da verdade em x; na primeira amostra com a falha ativa (8,0 s) o erro já é 2,27 m e na última estimativa é 15,15 m, perto dos 15 m injetados. O altímetro foi rejeitado aos 8,18 s; a partir daí o guiamento leu a menor das duas altitudes. Nada equivalente protege x e y. O plano mostra que a estimativa punha o bocal a 3,29 m do centro da plataforma, quando estava a 12,45 m. Isto é consistente com o desvio GNSS a conduzir o falhanço; a corrida não tem contrafactual, por isso não o demonstra.

## Limitações

- Modelo idealizado: o contacto é o plano do bocal a atingir o solo, sem dinâmica de contacto, e nada é validado contra dados de voo.
- Uma só corrida. Mostra uma trajetória, não a frequência do fenómeno.
- Proveniência 0.15.0: o anfitrião atual verifica a corrida, mas não a produziu.
- Amostragem de 0,1 s; o controlador corre a cada 0,02 s e o anfitrião verifica todos os passos. Os eventos entre duas amostras ficam nos tempos guardados; entre amostras não se mostra nenhum valor.
- A amostra de toque está fora da grelha. A verdade é o estado de contacto interpolado pelo anfitrião (D-host); a estimativa e a observação são do último ciclo de controlo antes do contacto, não do instante do toque. A vista rotula o ponto acreditado como "última estimativa antes do contacto".
- O resíduo e a posição acreditada do bocal usam o substituto de `s_cm`, a estimativa guardada depois da atualização e amostras de 0,1 s. A concordância antes da falha (resíduo máximo de 0,25 m, contra um limiar de 3 m) apoia o substituto, mas não o prova para o `s_cm` do controlador.
- Sem covariância: não há incerteza para mostrar. Sem contrafactual: não há prova de causa.
- Na iteração 1 as linhas das estimativas uniam amostras consecutivas e sugeriam uma subida gradual entre 7,9 s e 8,0 s. Foi corrigido na iteração 2 (marcador em cada amostra e conector fino, rotulado como ajuda de leitura).
- Os factos de código ficam presos ao commit `bec7b3f`: se `landing_controller.rs` e os vizinhos mudarem, o teste falha até o extrator ser reexecutado e os factos revistos.

## Como executar

```sh
python spikes/m19-belief-truth/extract.py          # regenera data.json (determinista)
python spikes/m19-belief-truth/extract.py --check  # falha se data.json estiver desatualizado
cd spikes/m19-belief-truth && python -m http.server 8192
# abrir http://127.0.0.1:8192/index.html (também aceita ?zoom=fault&sample=82&table=open)
python -m unittest tests/test_m19_belief_truth.py
node --check spikes/m19-belief-truth/js/app.js    # idem charts.js e model.js
```

Teclado: no eixo do tempo, Esquerda e Direita avançam uma amostra, Shift com seta dez, Home e End vão aos extremos, Page Up e Page Down saltam para o evento anterior ou seguinte. Zoom: "Full run", "Fault onset", "Final approach" e "Zoom to cursor"; a 8,18 s só se distingue da amostra de 8,2 s no zoom "Fault onset".

## Verificação desta iteração

- `python -m unittest tests/test_m19_belief_truth.py`: 32 testes. Cobrem os hashes (fixados, declarados pela corrida e inalterados em git), `data.json` igual a uma extração nova, resolução de todos os ponteiros, recálculo independente de todas as derivações (o teste falha se existir uma derivação sem verificação), observações exatamente iguais aos pontos guardados e nulos preservados, recusa da vista a unir observações (teste em Node), âncoras do código-fonte nas linhas indicadas e, com um navegador Chromium sem interface, que todo o número da página pertence a um botão de valor cujo texto é o valor do modelo de dados formatado, ou é um rótulo de escala.
- `python -m unittest discover -s tests -p "test_*.py"`: 462 testes, 1 erro que já existia antes desta alteração (`test_minimize`: "o executável vv-lab não existe", falta `cargo build --release` na raiz). Sem outras falhas.
- `cargo fmt --check`: sem diferenças. Não há código Rust alterado.
- Capturas em `docs/evidence/m19/belief-truth/iteration-1/`: `view-1440x900.png`, `view-1024x640.png`, `view-390x844.png` (o Chromium sem interface limita a largura da janela, por isso a vista de 390 px é desenhada numa `iframe` dessa largura: `harness-390.html`) e páginas completas.
- Contraste: os pares de cor de texto usados medem entre 6,6:1 e 17,2:1, acima do mínimo AA de 4,5:1 (cálculo feito nesta iteração sobre os valores do CSS, não com uma ferramenta de auditoria).

## Fraquezas conhecidas e próximos passos

- Não foi testada com leitor de ecrã nem com uma ferramenta de acessibilidade automática; o desenho segue as regras (HTML semântico, foco visível, `prefers-reduced-motion`, tabela alternativa), mas isso é uma intenção, não uma medição.
- A narrativa dos quatro passos é texto fixo escrito para esta corrida; os números vêm dos dados, mas as frases não generalizam a outras corridas.
- O plano mostra apenas a janela de ±20 m. Com o cursor fora da janela, o plano diz que o ponto verdadeiro está fora e não o desenha.
- A vista não permite comparar duas corridas, nem mostra o que teria acontecido sem a falha.
- A aproximação do resíduo poderia ser medida contra uma corrida que guarde o resíduo interno do controlador; esta não o guarda.


## Iteração 2

Resposta à avaliação da iteração 1: não enganou nas armadilhas centrais, mas a compreensão ficou abaixo do limiar porque a mecânica do controlador estava pouco explicada. Mantêm-se o SVG 2D (sem Three.js; o crítico confirma que não há vantagem material), a classe C e a formulação "gravado pelo anfitrião rocket-landing 0.15.0". A vista continua a não simular nada.

Mudanças, por prioridade:

1. **Marcadores por amostra (bloqueador).** As tiras das estimativas ligavam as amostras de 7,9 s e 8,0 s e desenhavam divergência antes da falha. Agora cada amostra guardada tem um marcador, o conector é fino e a legenda diz "connector between recorded samples, not data". O texto das tiras diz que as estimativas são guardadas a cada 0,1 s (um ciclo de controlo em cinco) e que os marcadores são valores guardados. Na amostra de 8,0 s a vista explica que o erro de 2,27 m é o estado depois de a falha ter feito efeito nesse ciclo e não uma subida gradual, e mostra o salto esperado de um fix GNSS com desvio (ganho vezes desvio, 2,25 m, inferência do ganho fixo).
2. **Etiqueta de classe no toque.** `err_est_x` e `err_est_y` deixam de ser D-host na amostra de toque: ficam D-view, e a gaveta diz "computado contra a verdade interpolada pelo anfitrião". A verdade e a velocidade verdadeira dessa amostra continuam D-host.
3. **Proveniência da build.** O `extract.py` calcula, sem git, o hash dos 20 ficheiros do `vv-rocket` pelo algoritmo de `crates/vv-rocket/src/lib.rs` (CRLF lido como LF) e compara-o com o `source_sha256` da corrida (`12b276cb...`): são **diferentes**. Difere apenas `src/landing_model.rs`. Os hashes por ficheiro da árvore do commit `3962482` estão fixados no extrator; o teste prova com git que essa árvore reproduz o hash gravado (diz-se que a árvore o reproduz, não que construiu a corrida) e que os valores fixados coincidem com o git. Todos os ficheiros de simulador citados pela vista (controlador, sensores, simulação, verdade, verificador) são idênticos aos dessa árvore. A versão não chega para identificar a build: a corrida regista a versão `0.15.0` e a árvore atual também declara `0.15.0` (`domain.json`), mas o pedido guardado tem 6 parâmetros e o catálogo atual tem mais. O replay estrito é rejeitado ("stored request is valid and canonical"); o replay de "build anterior" volta a simular com os valores por omissão atuais e concorda nos campos comparados (resultado, segurança, veredictos, canais, eventos, métricas; textos, cena e ficheiros nativos não se comparam). O teste `earlier_build.rs` foi executado de novo nesta iteração (`1 passed; 0 failed`, ver `docs/evidence/m19/belief-truth/iteration-2/cargo-earlier-build.txt`). O teste das linhas fixas do código-fonte diz agora, ao falhar, para repetir o `extract.py`.
4. **Cadência dos sensores.** GNSS um fix por 0,1 s (cinco ciclos de controlo, `gnss_period_cycles`), altímetro e IMU a cada ciclo de 0,02 s, amostras do traço a cada 0,1 s. A amostra de toque, fora da grelha, mostra "no fix on this cycle" onde o GNSS é nulo (230 amostras com fix, uma sem).
5. **Decisões do controlador.** Nova secção: ignição comandada às 3,6 s (antes da falha; regra do código-fonte com a fração de ignição), comandos guardados (classe K, no painel do cursor), sem corte, aborto nem reacendimento (`cutoff_t_s`, `flameout_t_s` e `ascent_abort_first` nulos; S4 igual a 1). `sensor_disagreement` e `altimeter_rejected` são a mesma condição (`landing_controller.rs`, `sensor_disagreement: ...then_some(self.rejected)`) e aparecem como uma só deteção. A rejeição significa duas coisas, do código-fonte e não guardadas: o altímetro deixa de ser fundido em cada ciclo cujo resíduo excede o limiar (começa antes da bandeira) e, depois de cinco ciclos consecutivos, o guiamento lê o mínimo entre a altitude estimada do bocal e o altímetro. Pela lógica implementada o controlador não podia saber qual dos sensores estava errado (só compara o altímetro com a própria estimativa); a vista diz que é uma afirmação sobre o código, não uma avaliação com retrospetiva.
6. **Painel de divergência.** "No divergence instant is recorded." Mostra o início da falha, o erro nas amostras de 7,9 s e 8,0 s e um limiar escolhido pelo utilizador (1, 3, 5, 10 m) que dá a primeira amostra guardada acima dele, para o erro horizontal e para o vertical, em D-view (amostra guardada, nunca um cruzamento interpolado).
7. **Erro de velocidade.** Tira com `err_vz` e `err_vh` do `record.json` (D-host) e as velocidades verdadeira e estimada no painel do cursor. Antes de os rotular como D-host, o extrator verifica em todas as amostras que `err_z`, `err_h`, `err_vz`, `err_vh` e `pad_distance` são as subtrações simples.
8. **Distância à plataforma e altitude.** Tira com a distância verdadeira (D-host) e a acreditada (D-view, aproximada) do plano do bocal ao centro, com a linha do raio R5 e barras do primeiro ao último ponto guardado dentro do raio: a verdade esteve dentro entre 12,1 s e 15,7 s e saiu, a crença está dentro desde 15,6 s até ao fim. Tira da altitude verdadeira. O plano tem o botão "Whole track" para ver a trajetória inteira e não só os 20 m junto à plataforma.
9. **Estado inicial e janela da falha.** Quadro nominal (`case.json`) contra disperso (`record.json`) e meia-largura da dispersão. A falha está configurada de 8,0 s a 40,0 s e a corrida terminou ao toque, por isso a falha esteve ativa até ao fim (lido das falhas ativas da última amostra).
10. **Decisões ligadas aos resultados.** O cartão 4 diz que o altímetro foi o mais baixo em 149 das 149 amostras com a bandeira (aproximado) e que isso é consistente com o veredicto do R1 e a velocidade de 2,07 m/s apesar de a estimativa estar 14,79 m acima da verdade (suavizado para "consistente com"; deixou de dizer "porque"). Cada linha de requisito tem "At touchdown"; o R5 tem também "On the pad plan". R1, R2 e R5 dizem "nozzle plane" (verificado numericamente contra `verification.json` e ancorado em `landing_verify.rs`). A nota do S2 diz que é avaliado no contacto e tem o mesmo número que o R5.
11. **Convenção de sinais.** "x = -12,32 m (east positive), y = -1,79 m (north positive)", lida do quadro de referência do `record.json`, mais uma frase marcada como inferência (um desvio de 15 m em x seguido pelo guiamento põe o veículo do lado de x negativo).
12. **Palavras de veredicto vindas dos dados.** Nenhuma palavra de veredicto, nem "inside" ou "outside" junto ao R5, está escrita no HTML ou no JavaScript da página: vêm de um mapa único em `model.js`, escolhidas por um booleano dos dados. Um teste procura essas palavras nas fontes.
13. **Acessibilidade.** `touch-action: pan-y` nas figuras; a legenda abre a gaveta com o índice do cursor; as células da tabela de amostras são botões com uma só paragem de tabulação e navegação por setas; a etiqueta "approx." aparece em cada valor aproximado, não só em parênteses.
14. **Hierarquia.** Cartões mais curtos, 2x2 a 1024 px, tira x e plano da plataforma no primeiro ecrã a 1440x900, cursor inicial no início da corrida e dito como tal, ajuda de teclado recolhida, lista de eventos movida para a secção de decisões.
15. **Pequenos acertos.** Redação da amostra de toque fora da grelha; "at recorded samples"; eventos procurados por tipo e não por índice (extrator e testes); redesenho do cursor ao arrastar agrupado por `requestAnimationFrame`.

Testes novos (59 no total no ficheiro): todos os números novos rastreados e recalculados de forma independente, sem palavras de veredicto escritas, um marcador de estimativa por amostra guardada no DOM renderizado (231 em x, y e z), etiquetas D-view do erro no toque no DOM de `?sample=230`, hash da fonte contra a árvore atual e contra o commit fixado, e diferença esperada apenas em `landing_model.rs`.

Verificação desta iteração: `python -m unittest tests/test_m19_belief_truth.py` (59 testes, passam), `python -m unittest discover -s tests -p "test_*.py"` (487 testes, 1 erro que já existia: `test_minimize` sem o executável `vv-lab`), `cargo fmt --check` limpo, `node --check` dos três módulos, `extract.py --check`. Capturas em `docs/evidence/m19/belief-truth/iteration-2/` (1440x900, 1024x640, 390x844, zoom do início da falha, toque com a trajetória inteira, páginas completas a 1024 e 390). O Chromium sem interface limita a largura da janela; a vista de 390 px usa um `iframe` dessa largura (`harness-390.html`).

O que fica por resolver:

- Nenhum estudo com pessoas: a compreensão não foi remedida depois destas mudanças.
- Sem leitor de ecrã nem ferramenta automática de acessibilidade; o contraste foi calculado à mão na iteração 1 e as cores novas (marcadores, etiqueta "approx.", classe K) não foram recalculadas.
- `touch-action: pan-y` e o arrastar por ponteiro não foram testados num dispositivo tátil real.
- A 1024x640 o primeiro ecrã é o dos cartões; as tiras ficam abaixo da dobra.
- O texto dos cartões é fixo para esta corrida (números e palavras de veredicto vêm dos dados, as frases não generalizam).
- O resíduo, a posição acreditada e "qual das altitudes foi a menor" continuam aproximados (substituto de `s_cm`, estimativa pós-atualização, amostras de 0,1 s). A frase do cartão 4 sobre o R1 é "consistente com", sem contrafactual.
- A primeira amostra acima de um limiar é uma amostra guardada, não o instante do cruzamento.
- O teste de proveniência prende o hash e as linhas de cinco ficheiros Rust, do `host_sdk.rs` e do `earlier_build.rs`: qualquer alteração a esses ficheiros faz falhar o `discover` até o extrator ser repetido.


## Iteração 3 (antes chamada «correções finais»)

Artefacto exploratório, preservado em `spikes/m19-belief-truth-iteration3/` (movido de `spikes/m19-belief-truth/` em 2026-11-25; o candidato principal é a iteração 2). Os comandos de «Como executar» acima aplicam-se ao candidato principal; para este artefacto, trocar o caminho.

Passagem feita depois da avaliação da iteração 2. Uma classificação independente, com critérios fixados antes, concluiu que é uma terceira iteração substantiva (ver «Estado» no início e `docs/evidence/m19/reviews/06-classification-of-the-final-pass.md`). Foi avaliada por agentes com a mesma chave: 18,5/20 (15,5 em leitura estrita), armadilhas 14,5/16, sem melhoria sobre a iteração 2. O congelamento fixa esta versão (iteração 3), porque o responsável pediu que se congelasse o protótipo atual; a iteração 2, dentro do limite, continua recuperável no commit `dae67fa`. Alterações:

1. A etiqueta "approx." propaga-se agora a tudo o que deriva de um valor aproximado (o extrator calcula o fecho): aparece nos 3,29 m e no "inside" do cartão 2, na distância acreditada e nos limites "believed within R5" (15,6 s a 22,955 s).
2. Células numéricas sem quebra de linha e com algarismos tabulares; as tabelas do cursor deslizam na horizontal.
3. Ignição: "Engine ignition recorded (truth event) at 3,6 s", o tempo do comando vem do detalhe do evento (passo 360, sem atraso), e as primeiras amostras com o motor ligado e com comando de acelerador acima de zero (3,6 s, derivadas, com a classe certa).
4. O conector das estimativas quebra entre 7,9 s e 8,0 s (a primeira amostra com a falha ativa): nenhum traço atravessa o início da falha.
5. Etiquetas de tempo em cada tira.
6. Cartão 4 com três frases: bandeira aos 8,18 s; altímetro sem fusão desde o primeiro ciclo acima do limiar (primeira amostra guardada acima do limiar, 8,1 s, derivada e aproximada) e bandeira após cinco ciclos consecutivos; guiamento com o mínimo das duas altitudes (código-fonte, não guardado); nada verifica o GNSS em x e y (S, botão para `landing_controller.rs`), por isso o guiamento seguiu a crença enviesada; pontos do bocal a 15,15 m (aproximado).
7. R2: velocidade horizontal do plano do bocal (0,612 m/s, a que o R2 usa) ao lado da do centro de massa (0,513 m/s), com a diferença (0,109 m/s) igual ao ritmo angular vezes o braço (verificada no extrator).
8. "sample index N (last index 230, 231 samples)".
9. R6: propelente inicial (7981,6 kg), limite como fração de margem dessa quantidade (verificado) e a frase do próprio registo.
10. Velocidade do GNSS: marcadores ocos, nunca ligados, na tira de velocidade e linha no quadro do cursor; o conteúdo do IMU está guardado mas não se mostra, e a vista diz isso.
11. Linha inicial da proveniência: os veredictos mostrados são os guardados, não recalculados; a build que escreveu a corrida não é a árvore atual.
12. Cartão 1: "(nozzle plane)" e "o ponto verdadeiro esteve dentro do R5 de 12,1 s a 15,7 s e saiu".
13. "Whole track": sem rótulos sobre a trajetória.
14. Todas as figuras SVG têm `role="img"` e `aria-label` próprio, verificado no DOM por teste.

Testes: 73 no ficheiro, todos passam. Capturas em `docs/evidence/m19/belief-truth/final/`. A 1440x900 a tira x deixou de caber por inteiro no primeiro ecrã (os cartões ficaram mais altos); mantém-se à vista a parte de cima.

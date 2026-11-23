# M19.2: Belief vs Truth, protótipo de investigação (iteração 1)

Protótipo isolado, em `spikes/m19-belief-truth/`. Não altera o Studio nem nenhum crate. Não simula nada: lê uma corrida guardada e mostra, lado a lado, o que aconteceu, o que o controlador acreditava, quando os dois divergiram e porque isso importou.

Estado: iteração 1 construída e verificada no ramo `prototype/m19.2-belief-truth`, só localmente. Não foi avaliada por utilizadores nem pela revisão independente.

## Tese

Um engenheiro percebe o que realmente aconteceu, o que o controlador acreditava, quando os dois estados divergiram e porque a divergência importou.

## Dados e proveniência

Só dados guardados, sem simulação nova e sem sementes: `desktop/domain-rocket/tests/fixtures/stored-by-0.15.0/` (`record.json`, `trace.json`, `verification.json`, `run.json`, `case.json`).

- Corrida: semente 5002 (semente de desenvolvimento), política `guarded`, falha `gnss_bias` de 15 m em x e z da posição GNSS, de 8,0 s a 40,0 s. O toque no solo ocorre aos 22,955 s.
- Traço amostrado de 0,1 s em 0,1 s (231 amostras: 230 periódicas e a amostra de toque, fora da grelha).
- Não existe covariância em lado nenhum: o estimador é de ganhos fixos (`crates/vv-rocket/src/landing_controller.rs`, `update_robust`).

Cadeia de proveniência:

1. `extract.py` lê o fixture, verifica o sha256 de cada ficheiro contra os valores que a própria corrida declara (`run.json` para `case`, `trace` e `verification`; `record.json#/provenance/artifacts` para os quatro que declara) e escreve `data.json`. O `record.json` não declara hash de si próprio, por isso o hash observado fica fixado no `extract.py`, no teste e no `data.json` (campo `pinned_only`).
2. Cada valor de `data.json` tem uma classe de evidência e uma de três origens: um ponteiro JSON para o ficheiro guardado (`ptr`), uma derivação com nome (`derivation`, registada em `derivations` com a fórmula) ou um facto de código-fonte (`source_facts`, com ficheiro e linhas encontradas pelo próprio extractor a partir de âncoras de texto, nunca escritas à mão).
3. Toda a aritmética derivada vive no extractor. A vista só escala, formata e desenha.
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
| D-view | Derivada por esta vista (extractor), com a derivação nomeada |
| S | Do código-fonte, não guardada na corrida |
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
- As linhas das estimativas unem amostras consecutivas por segmentos retos. É um traço de leitura entre valores guardados; nenhum valor entre amostras é lido ou mostrado.
- Os factos de código ficam presos ao commit `bec7b3f`: se `landing_controller.rs` e os vizinhos mudarem, o teste falha até o extractor ser reexecutado e os factos revistos.

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

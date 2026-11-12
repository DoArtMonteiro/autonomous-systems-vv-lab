# M18: Mission Control, hangar de veículos e catálogo de ambientes

O Studio 0.17.0 tinha a ciência e as funcionalidades, mas escondia-as: a página inicial vendia três modos abstratos, o Experiment Lab abria com três botões "Default run", os veículos novos só apareciam numa lista do Lab, cinco dos oito ambientes estavam em ficheiros zip que só se instalavam por um diálogo nativo, e uma corrida feita no Lab não se podia ver no leitor de missões. O M18 corrige a arquitetura de informação e liga o percurso completo, sem mudar nenhum resultado científico existente.

Estado: ramo `m17-integration`, por cima do PR #30. Nada foi integrado em `main`. Studio 0.18.0 construído (`desktop/build.ps1`, instalador de 42,3 MB contra 19,7 MB do 0.17.0, por causa dos oito pacotes). Os percursos correram no executável de `desktop/target/release`, não numa instalação; o Studio instalado continua a ser o 0.17.0.

## O que mudou no produto

1. **Mission Control** (`ui/js/views/home.js`): a página inicial passa a ter três caminhos com imagem própria: lançar e explorar uma missão, desenhar ou configurar um veículo, explorar ambientes e a Cinematic View. Mostra o que está instalado (missões, veículos, ambientes, domínios), o percurso de uma experiência em seis passos e as missões em destaque, com a subida a órbita em primeiro lugar.
2. **Hangar de veículos** (`ui/js/views/vehicles.js`): todos os veículos dos domínios instalados, agrupados por papel (lançadores, andares de aterragem, robô terrestre), com nível de evidência ("Reference case", "Exploratory", "Illustrative"), atributos físicos, a missão que os usa e "Design and fly", que abre o Lab já com a corrida de base simulada e os parâmetros do veículo abertos. Tabela lado a lado por domínio.
3. **Ambientes** (`ui/js/views/atlas.js`): os oito pacotes validados como cartões com a imagem do próprio pacote, resolução, relevo, camada do mundo, tamanho e créditos curtos; "Use for missions" fixa o ambiente do leitor e "Land a rocket here" abre a missão nesse local. A secção Cinematic View diz se o módulo está instalado e verificado.
4. **Os cinco pacotes do M17 vêm com o Studio** (commit `0699e66`): Wallops Island, península de Mahia, El Arenosillo, vale de Goms e Adventdalen. Validados pelo mesmo validador do Studio, 26,9 MB de ficheiros, `NOTICE.md` com as fontes e licenças dos oito. Ver `docs/m17-environments.md`.
5. **Ver as corridas do Lab no leitor** (`views/player.js`, `views/lab.js`): "Watch both runs" toca a corrida de base e a experiência no leitor, com cena de engenharia, vista geoespacial, Mission Control e o botão da Cinematic View. O leitor volta a pedir os mesmos pedidos à plataforma, que reutiliza os registos guardados; não calcula nenhum voo.
6. Navegação: "Mission Control", "Missions", "Vehicles", "Environments", "Experiment", "Investigate" e depois as áreas de trabalho. Abaixo de 1240 px a barra comprime-se e desliza na horizontal sem criar deslocamento horizontal da página.

## Parâmetros de desenho do veículo (física real)

O domínio `rocket-landing` ganha quatro parâmetros no grupo "Vehicle design", fatores sobre o veículo do cenário escolhido (`desktop/domain-rocket/src/case.rs`, `vehicle_scale_fields`):

| Parâmetro | Campos do caso que multiplica | Intervalo |
| --- | --- | --- |
| `vehicle_dry_mass_scale` | `dry_mass_kg`, `dry_inertia_kgm2` | 0,6 a 1,6 |
| `vehicle_propellant_scale` | `propellant_mass_kg`, `propellant_inertia_kgm2` | 0,3 a 2,0 |
| `vehicle_thrust_scale` | `max_thrust_n` | 0,5 a 1,6 |
| `vehicle_isp_scale` | `isp_s` | 0,7 a 1,3 |

- Com o valor 1 o caso fica igual ao modelo byte a byte (teste `vehicle_design_factors_scale_the_scenarios_own_vehicle_and_change_the_flight`, para os quatro cenários). Os hashes do M1 e os casos pré-registados não mudam.
- Qualquer outro valor torna o caso exploratório (`vv-rocket-landing.v2`) e o simulador volta a verificar os intervalos de `check_exploratory`, incluindo impulso sobre peso com carga total entre 1,2 e 6. O controlador recebe o veículo alterado, como já recebe cada predefinição; os ganhos ficam os do modelo.
- Os atributos mostrados no hangar vêm do campo novo `facts` do catálogo (`desktop/platform/src/contract.rs`, opcional e omitido quando vazio), que cada anfitrião lê do modelo de caso que realmente simula. A interface não escreve nenhum número de veículo à mão.

## Resultados verificados

Percurso M18 no Studio 0.18.0 compilado (`desktop/studio/tests/m18_journeys.py`, janela WebView2 real, biblioteca temporária): **28/28 verificações**. Números lidos dos registos (`m18-numbers.json`):

Andar pesado (41 t), controlador robusto, semente 5000, impulso × 0,7:

| Requisito | Base | Impulso × 0,7 |
| --- | --- | --- |
| R1 velocidade vertical no contacto (≤ 3 m/s) | 1,66 m/s, passa | 60,08 m/s, falha |
| R2 velocidade horizontal (≤ 1 m/s) | 1,58 m/s, falha | 4,82 m/s, falha |
| R5 distância ao centro (≤ 10 m) | 1,37 m | 3,74 m |
| R6 margem de propelente | 5151 kg | 6589 kg |

Verificação cruzada de ordem de grandeza (`scripts/m18_braking_bound.py`, código próprio, não o simulador): massa pontual vertical a partir do estado inicial do modelo do andar pesado, impulso máximo desde o primeiro instante, arrasto do próprio andar e atmosfera exponencial, sem perdas de atitude. **Não é um limite estrito**: impulso máximo desde o instante zero não é a travagem ótima (gasta propelente cedo e pode esgotá-lo antes de parar), a dispersão inicial da semente e a altura do centro de massa são ignoradas e o passo é fixo. Serve só para ver se a velocidade de contacto e o consumo do simulador têm a ordem de grandeza certa e mudam no sentido certo quando o impulso muda. O andar, o ambiente e o estado inicial são lidos do modelo que o anfitrião simula (`desktop/domain-rocket/cases/heavy-return.json`), não escritos à mão, e o programa avisa se o propelente se esgota antes do solo. Com impulso × 0,7 (impulso sobre peso 1,32) chega a 54,1 m/s com 6584 kg de propelente; o simulador dá 60,1 m/s e 6589 kg. Com × 0,75 para a 140 m de altura. A ordem de grandeza e o sentido batem certo; isso não valida o modelo.

Lançador pequeno, carga útil 250 kg para 600 kg: a corrida passa de "Orbit" a "Suborbital". O andar superior esgota a reserva estimada antes da energia alvo (resíduo 3,6 kg, periapsis −859 km); R4, R6 e R8 passam a falhar e o ponto de impacto do booster recua de 1023,6 para 965,1 km.

Outras verificações, todas no Studio 0.18.0 compilado ou no repositório nesta versão:

- Lista do `AGENTS.md`: `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test`, `python -m unittest`, `cargo build --release` e a campanha `--seeds 42,1337,2026` passam na raiz; `cargo fmt --check`, `clippy -D warnings` e `cargo test` passam no workspace `desktop/`.
- Percursos anteriores no mesmo executável: M15 48/48, M16 77/77 e M17 Lab 34/34. O percurso M15 passou a ler o cabeçalho de Mission Control (`.hm-head`) em vez do antigo `.home-hero`.
- Duas regressões encontradas pelos percursos e corrigidas antes do fecho: o prefixo `mc-` da nova página inicial colidia com o modo Mission Control do leitor (a página inicial herdava `overflow: hidden` e deixava de deslizar); passou a `hm-`. A lista de ambientes é alfabética, por isso o ambiente por omissão passou a ser Svalbard; o leitor volta a usar Cape Canaveral quando nenhum foi escolhido.

## Revisão independente

Um revisor independente (Fable 5.1, só leitura, capturas antes e depois e código) concluiu: três caminhos e catálogo de ambientes cumpridos; personalização de veículos, Lab e separação entre simulação e ilustração parcialmente cumpridos; vista 3D e geoespacial com melhoria **marginal**. Corrigido a seguir: "Safe" junto de um impacto a 60 m/s passou a "Safety rules held"; o título do leitor diz "baseline and your change"; os passos do percurso na página inicial apontam para onde dizem; as ilustrações da página inicial têm a etiqueta "Illustration"; "real physical differences" passou a "distinct physical parameters"; o estado do módulo diz "every file matches its manifest" em vez de "verified"; a barra de navegação mostra a barra de deslocamento abaixo de 1240 px.

Os quatro defeitos que ficaram por corrigir foram tratados na recuperação (secção seguinte).

## Correções de recuperação

- **Rótulos em Compare e no leitor** (`model.js`, `views/lab.js`): os parâmetros são comparados um a um com o valor por omissão do catálogo, por isso um pedido que lista todos os valores por omissão e outro que lista só o valor alterado já não dão rótulos iguais e cortados. O rótulo diz o que difere (por exemplo "Vehicle thrust scale 1 (default)" e "Vehicle thrust scale 0.7"); o texto passa a quebrar linha em vez de ser cortado. No leitor, a experiência do Lab usa esse rótulo em vez de "Your change".
- **Cabeçalho do leitor** (`views/player.js`, `css/mission.css`): duas linhas fixas, título e etiqueta de grau em cima, vista e paisagem à esquerda e as quatro ações à direita em baixo; cada grupo quebra dentro da sua linha, por isso nenhum controlo cobre outro. O percurso M18 mede as caixas a 1024x640, 1440x900 e 1920x1080.
- **Margem na subida** (`domain-ascent/src/record.rs`, `views/lab.js`): o registo passa a publicar, por requisito de uma só grandeza contra um só limite, as métricas `requirement_observed.<id>`, `requirement_limit.<id>` e `requirement_margin.<id>` (positiva quando cumprido), no grupo "requirement margins". Os requisitos compostos (janela de separação, ordem das fases, resumo da inserção em órbita) não publicam números, e um requisito cujo estado contradiz o sinal da margem também não. Para os dois invariantes o valor é o estado verdadeiro no instante decisivo: o pior instante quando se cumpre, o primeiro acima do limite quando falha (o verificador está em `crates/`, que esta recuperação não altera). O Lab lê estes números e só cai no texto para registos antigos. Não muda nenhum resultado de simulação; os registos antigos continuam válidos porque são métricas acrescentadas.
- **Nome do modo do leitor**: "Mission Control" passa a nomear só a página inicial; o modo de operações do leitor chama-se "Flight console" (o identificador interno continua `control`). Os documentos históricos M11 e M16 mantêm o nome que tinham na altura.
- **Rótulo de uma aterragem falhada** (`domain-rocket/src/record.rs`): "Reached the ground, requirements not met" em vez de "Touched down, requirements not met", que se mostrava também em impactos de 24 a 33 m/s. O texto está no `record.json`, por isso corridas guardadas antes têm o texto antigo (ver a repetição abaixo).
- **Reprodução depois de uma atualização** (`platform/src/host_sdk.rs`, `platform/src/service.rs`): o `replay` estrito exige que o pedido guardado seja igual à sua forma normalizada e que cada ficheiro recalculado seja igual byte a byte, o que não pode valer entre versões (parâmetros novos com valor por omissão, textos e métricas novos). Quando a compilação do anfitrião que guardou a corrida difere da que está a correr (o SHA-256 do anfitrião está no `meta.json` e no identificador da corrida), a plataforma pede `replay --earlier-build`: verifica os hashes dos ficheiros guardados, aceita o pedido se só faltarem valores por omissão (e diz "recorded by domain version X; re-simulated with current defaults"), recalcula e compara o código e o estado do resultado, o estado da segurança, o estado, o instante e a categoria de cada requisito, as bases de tempo, os canais, os eventos e as métricas guardadas. Não compara textos (incluindo o esperado e o observado de cada requisito), a cena, os blocos de entidades e missão nem os ficheiros nativos, e não corre a repetição do simulador nativo, que exige as mesmas fontes; uma alteração só nesses campos passa numa corrida de outra compilação. A repetição estrita corre sempre primeiro e decide sozinha quando passa (uma corrida que ainda reproduz byte a byte é `verified`, com a repetição nativa); a versão de uma compilação anterior só entra quando a estrita rejeita a corrida. O estado é `verified_earlier_build`, nunca `verified` (não é igual byte a byte) nem `rejected`. A condição "outra compilação" lê o `meta.json`, que não é autenticado, e o identificador da corrida é recalculável: quem editar os dois consegue que uma corrida pareça de outra compilação, por isso a condição é só informativa. A proteção contra ficheiros editados vem da recomputação: o estado de cada requisito comparado nos dois sentidos (um requisito falhado ou um evento de violação que a recomputação encontra e o registo guardado não tem é uma discordância, tal como um requisito ausente quando a versão do domínio é a mesma, ou um requisito novo que falha ou não foi avaliado; só um requisito novo que passa, de outra versão, é aceite; um evento de violação ou aviso novo de um tipo que o registo guardado não tem em lado nenhum, de outra versão do domínio, é tomado como introduzido por uma compilação posterior e não rejeita sozinho, mas a falta de um evento de um tipo que o registo conhece rejeita sempre), os instantes, os canais, os eventos, as métricas guardadas e as bandeiras de veredicto do `verification.json` nativo, comparadas com as recomputadas mesmo que o hash em `record.json` tenha sido reescrito. O relatório (`replay.json`) lista o que não se compara: textos, cena, blocos de entidades e missão, canais, eventos e métricas que só a compilação atual escreve (apagar um canal ou uma métrica guardados não se deteta) e a repetição nativa. A exportação de provas de uma corrida assim termina em `-EARLIER-BUILD`. A deteção de adulteração de uma corrida da compilação em uso não muda; `domain-rocket/tests/earlier_build.rs` verifica o caminho completo com o anfitrião real: uma corrida escrita pelo anfitrião do Studio 0.15.0 (commit `3b056cc`, copiada sem alterações para `tests/fixtures/stored-by-0.15.0`, seis parâmetros contra os dezanove de hoje) falha a repetição estrita e verifica-se contra o próprio registo, e um valor de telemetria alterado ou um ficheiro nativo alterado continuam a ser rejeitados.
- **Reserva de sementes**: `exec/src/seeds.rs` testa que 44000 a 44999 está declarada de forma idêntica nas guardas e nos manifestos dos três domínios.
- **Textos do catálogo do domínio terrestre**: as sequências de espaços passam a continuações de linha e os instantes de conclusão indicados (17 e 16) são verificados por um teste.
- **Leitor, resultado e marcas**: "Show the result now" já não perde o foco (vai para o título Result, que fica numa região `aria-live` criada desde o início e atualizada no sítio), e as marcas de deteção, violação e aviso não são desenhadas até a reprodução lá chegar, em vez de existirem escondidas.
- **Texto das missões** (`experiences.js`, `home.js`): "Why when a fault starts can change which requirement fails" (o M13 mostra que o início e a amplitude são ambos necessários, 30/30 juntos e 0/30 cada um sozinho) e "See a counterexample outside the registered conditions". A última investigação de uma afirmação escolhe-se pelo carimbo de criação.

## O que não está disponível

- **Recuperação controlada do booster** (manobra de regresso e queima de aterragem): código escrito num ramo local separado (`feat/m18-booster-recovery`, commit `bfe78a4` marcado como trabalho em curso, não publicado), nunca compilado por completo nem testado; ver a secção sobre o Defender. O hangar diz "Not in this build". O booster continua balístico depois da separação.
- Operações orbitais para além do voo livre de 600 s, naves espaciais e aeronaves: não há modelo.
- A Cinematic View só reproduz aterragens; a subida não tem cena cinemática.
- **Melhoria visual**: o M18 não muda o renderizador geoespacial nem o módulo Godot. A avaliação prévia do Unreal Engine 5 e do Cesium está em `docs/m18-cinematic-preflight.md`, com a aprovação exata necessária. O objetivo gráfico não está cumprido.

## Ambiente desta máquina

Durante o trabalho, o Microsoft Defender reteve executáveis recém-compilados (processos suspensos com 0 % de CPU, binários de teste a sair com erro após 0 testes, `LNK1104`). As compilações e os testes acabaram por passar quando repetidos. Um agente de apoio retomou processos suspensos com `NtResumeProcess` para contornar a retenção e depois parou; não alterou definições do Defender. Convém confirmar que a proteção está intacta e, se se quiser, excluir a pasta `target` do repositório da análise em tempo real.

## Integração e aprovação

O plano de integração dos PR #24 a #30 está em `docs/m18-integration-plan.md`: fase 1 com #24 a #28 por ordem e commits de merge fixados nos SHA testados; fase 2 decide o módulo Cinematic (#29) em separado, para que o renderizador não bloqueie a ciência validada. Nada foi integrado.

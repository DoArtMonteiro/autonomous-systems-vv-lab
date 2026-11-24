# M19: decisões do responsável de 2026-11-24 e estado final

Data: 2026-11-24. Este documento completa `docs/m19-acceptance.md` com o que foi feito depois das decisões do responsável de 2026-11-24. Revisões e consultas foram feitas por agentes de IA; nenhuma é revisão humana nem estudo com pessoas. Os relatórios das revisões estão em `docs/evidence/m19/reviews/` de cada ramo.

## Estado por decisão

| Decisão | Estado | Onde |
| --- | --- | --- |
| 1. Perfil WebView2 da 0.18.1 fica intacto | Nada foi apagado, limpo nem reposto. Verificação só de leitura: a escrita mais recente no perfil instalado é de 2026-11-23 19:01:22. Uma verificação posterior encontrou **uma segunda escrita** em dados instalados: execuções do Godot durante o M19.1 escreveram 8 ficheiros (caches de sombreadores e de pipelines, registos) em `%APPDATA%\VV Lab Cinematic`, às 18:39 e às 20:17 de 2026-11-23; nada depois. Pasta também deixada intacta. Ambos registados | `docs/incidents/2026-11-23-webview2-profile.md` no ramo `feat/m19-studio-isolation` |
| 2. Belief vs Truth | A passagem final foi classificada, com critérios fixados antes, como **terceira iteração substantiva**, uma acima do limite; o limite não foi redefinido. Congelada a versão atual (iteração 3), como pedido; a iteração 2, dentro do limite e com pontuação mais alta, fica recuperável em `dae67fa`. Candidato experimental à espera de teste com pessoas | `docs/m19-2-belief-truth.md`, `spikes/m19-belief-truth/FROZEN.json` no ramo `prototype/m19.2-belief-truth` |
| 3. G3 | Bloco 81000-81919 e alocação B aplicados só para preparação. Por aritmética de posições: sem sobreposição de fluxos dentro do bloco, com a reserva 80904-80983 nem com 16 439 sementes de intervalos declarados; o inventário mecânico do repositório tem lacunas declaradas (sementes derivadas em código, ficheiros não seguidos, outros ramos). Potência sem supor taxa de 100 %. Operações de RNG já feitas descritas, incluindo palavras de saída de fluxos protegidos geradas em revisões anteriores à regra de 2026-11-24. Verificação independente aceite com correções, aplicadas; a potência de H3, S1 e S2 e as contagens 84 e 54 não foram verificadas de forma independente. Nem o bloco nem a reserva estão ainda protegidos em `exec/src/seeds.rs` | `docs/m19-g3-onset-protocol-candidate.md` no ramo `research/g3-corrected-candidate` |
| 4. M10 | Fechado como «não avançar», com critérios falhados, excesso de execuções e passo saltado preservados | `docs/m10-closure.md` no ramo `research/m10-redesign` |
| 5. M19.1 | Verificação pendente feita: sete suítes repetidas com isolamento; cinco superfícies vistas pela primeira vez; jornada Cinematic não corrida, porque o Godot escreve nos dados instalados. Revisão final independente: pronto com correções, aplicadas. PR em rascunho #37. As duas correções que mudam hashes ficam fora do PR; o documento de propostas recomenda juntá-las num PR próprio, o que fica para decisão | `docs/m19-1-hash-changing-proposals.md` |
| 6. Cópia de segurança | Cinco ramos enviados depois de auditoria por agente (visibilidade pública, ancestralidade, dados privados, segredos, artefactos); o relatório da auditoria está nas mensagens desta sessão, não num ficheiro do repositório. Antes do envio: removida uma coluna de caminhos locais, retirada uma revisão que parafraseava a diretiva (o commit ainda não tinha sido enviado), neutralizadas duas frases. A chave de respostas do M19.2 ficou pública e idêntica ao hash fixado | |

## Salvaguardas de engenharia

**Isolamento dos dados instalados** (ramo `feat/m19-studio-isolation`, só local):

- As construções de desenvolvimento usam o identificador `org.vvlab.devstudio`; `org.vvlab.studio` e o nome do produto da versão só são aplicados por `build.ps1 -Release`, que os confirma antes e depois de compilar. Compilação completa de desenvolvimento e `-Release` executada; o instalador produzido não foi corrido e foi apagado da worktree.
- Todos os lançamentos da Studio e do Godot a partir de testes e scripts passam por auxiliares que redirecionam perfil, dados de aplicação, biblioteca e configuração para pastas temporárias, recusam caminhos instalados e terminam só o próprio processo. Removidas as terminações por nome de imagem, que fechariam a Studio instalada.
- 78 testes de isolamento e um lint dos lançamentos. Protege contra enganos, não contra quem edite os auxiliares; um lançamento manual não é coberto.
- Provas ao vivo: lançamentos de desenvolvimento pelo auxiliar (três, todos declarados) e 20 testes reais do Godot; listagens dos dados instalados idênticas antes e depois.
- Três rondas de revisão independente; as correções da terceira foram aplicadas e não foram revistas de novo.

**Orçamento de execuções** (ramo `feat/m19-run-budget`, só local):

- Reserva antes de lançar, a partir da lista planeada; sem reembolsos; registo só de acréscimo com trinco entre processos, num local partilhado por todas as worktrees.
- Manifesto comprometido e igual ao de `HEAD`; sementes protegidas recusadas; emendas só por commit; campanha fechada por emenda e nunca reaberta; um novo identificador não repõe o orçamento. Recontagem dos artefactos impede o relatório se não bater certo.
- 65 testes, incluindo a repetição do padrão do excesso do M10, que é recusado.
- **Estado atual: ainda não protege nada.** Não existe nenhum manifesto em `budgets/` e nenhum script o usa. A próxima campanha pré-registada tem de o adotar.
- Três rondas de revisão independente; as correções da terceira foram aplicadas e não foram revistas de novo.

## Recomendação para o próximo marco

Um percurso de investigação reproduzível para uma só alegação (`g3-onset`, aterragem do foguetão), com o Fable 5.2 como crítico (a consulta não está registada neste ramo):

1. **Ponte de registo primeiro.** O pacote guardado tem 3 dos 49 ficheiros e o hash de fonte antigo, por isso não é recomputável, e o contraexemplo (semente 42879) não abre no leitor. Torná-lo recomputável sob a fonte atual exige voltar a correr essa semente, o que é o passo de equivalência do G3 e precisa de autorização.
2. **Depois, ligar:** alegação, contraexemplo no leitor com a mesma identidade, divergência marcada só com o que está registado, recomputação da evidência e reprodução fora da Studio.
3. **Aceitação só com factos repetíveis**, usando as duas salvaguardas, que por isso devem ser integradas antes. Portões humanos continuam abertos; a vista crença contra verdade só entra depois do teste com pessoas. Congelar Cinematic, geoespacial, subida, terrestre e iteração visual.

## Decisões pedidas ao responsável

1. Chave de respostas do M19.2 pública: ratificar, ou remediar (o teste humano já tem de usar perguntas novas).
2. Enviar os dois ramos de salvaguarda e abrir PR em rascunho para cada um (o de isolamento muda o procedimento de construção da versão).
3. Proteger 81000-81999 e a reserva 80904-80983 em `exec/src/seeds.rs` (muda o hash do binário `vv-exec`).
4. Congelamento do M19.2: manter a iteração 3 ou trocar pela iteração 2.
5. Correções que mudam hashes: um PR ou dois, e quando.
6. Aceitar o marco recomendado, incluindo se autoriza o passo de equivalência com a semente 42879.
7. Destino da PR #15 e um revisor humano para o G3.

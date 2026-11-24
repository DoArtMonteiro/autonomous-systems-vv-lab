# M19: decisões do responsável de 2026-11-24 e estado final

Data: 2026-11-24. Este documento completa `docs/m19-acceptance.md` com o que foi feito depois das decisões de 2026-11-24. Revisões e consultas foram feitas por agentes de IA; nenhuma é revisão humana nem estudo com pessoas.

## Estado por decisão

| Decisão | Estado | Onde |
| --- | --- | --- |
| 1. Perfil WebView2 da 0.18.1 fica intacto | Cumprido. Verificação só de leitura: a escrita mais recente no perfil instalado é de 2026-11-23 19:01:22; nenhuma depois. Registo do incidente preservado | `docs/incidents/2026-11-23-webview2-profile.md` no ramo `feat/m19-studio-isolation` |
| 2. Belief vs Truth | A passagem final foi classificada, com critérios fixados antes, como **terceira iteração substantiva**, uma acima do limite. O limite não foi redefinido. Protótipo congelado (manifesto sha256 e teste); candidato experimental à espera de teste com pessoas | `docs/m19-2-belief-truth.md`, `spikes/m19-belief-truth/FROZEN.json` no ramo `prototype/m19.2-belief-truth` |
| 3. G3 | Bloco 81000-81919 e alocação B aplicados só para preparação. Sem sobreposição de fluxos com o próprio bloco, com a reserva 80904-80983 nem com 16 439 sementes inventariadas, demonstrado só por aritmética de posições. Potência sem supor taxa de 100 %. Operações de RNG já feitas descritas com precisão. Verificação independente: aceite com correções, aplicadas | `docs/m19-g3-onset-protocol-candidate.md` no ramo `research/g3-corrected-candidate` |
| 4. M10 | Fechado como «não avançar», com critérios falhados, excesso de execuções e passo saltado preservados | `docs/m10-closure.md` no ramo `research/m10-redesign` |
| 5. M19.1 | Verificação pendente concluída (sete suítes repetidas com isolamento, cinco superfícies vistas pela primeira vez) e revisão final independente; PR em rascunho #37. As duas correções que mudam hashes ficam separadas e explicadas | `docs/m19-1-hash-changing-proposals.md` |
| 6. Cópia de segurança | Cinco ramos enviados depois de auditoria (visibilidade pública, ancestralidade, dados privados, segredos, artefactos). Sem integração, versão nem instalação | |

## Salvaguardas de engenharia

**Isolamento do perfil instalado** (ramo `feat/m19-studio-isolation`, local):

- As construções de desenvolvimento usam o identificador `org.vvlab.devstudio`; `org.vvlab.studio` só é aplicado por `build.ps1 -Release`, que o confirma antes e depois de compilar, tal como o nome do produto.
- Todos os lançamentos dos testes de interface passam por um auxiliar que redireciona perfil, biblioteca e configuração, recusa caminhos do perfil instalado e termina só o seu próprio processo. Removidas todas as terminações por nome de imagem, que fechariam a Studio instalada.
- 56 testes de isolamento e um lint dos lançamentos; protege contra enganos, não contra quem edite o auxiliar.
- Prova ao vivo: uma construção de desenvolvimento lançada pelo auxiliar; listagens do perfil instalado idênticas antes e depois. Compilação completa de desenvolvimento e `-Release` executada; o instalador produzido não foi corrido.
- Duas rondas de revisão independente; correções aplicadas.

**Orçamento de execuções** (ramo `feat/m19-run-budget`, local):

- Reserva antes de lançar, a partir da lista planeada; sem reembolsos; registo só de acréscimo, com trinco entre processos, num local fixo partilhado por todas as worktrees.
- Manifesto de orçamento comprometido e igual ao de `HEAD`; sementes protegidas recusadas; emendas só por commit; campanhas fechadas por emenda, nunca apagadas; um novo identificador não repõe o orçamento.
- Recontagem dos artefactos impede o relatório se não bater certo.
- 59 testes, incluindo a repetição do padrão do excesso do M10, que é recusado.
- Duas rondas de revisão independente; correções aplicadas.

Os dois ramos de salvaguarda não foram enviados: não estavam na autorização de envio.

## Recomendação para o próximo marco

**Um percurso de investigação reproduzível, de ponta a ponta, para uma só alegação.** Consulta ao Fable 5.2 e verificação de viabilidade só de leitura.

1. **Primeiro, uma ponte de registo limitada.** O pacote de investigação `g3-onset` guardado tem só 3 dos 49 ficheiros no repositório e regista o hash de fonte antigo (`12b276cb`), por isso `vv-exec investigate-verify` não o consegue recomputar, e o contraexemplo (semente 42879) não tem identificador de corrida que o leitor possa abrir. O marco começa por tornar um pacote recomputável sob a fonte atual, com o contraexemplo endereçável pela mesma identidade em todas as vistas.
2. **Depois, ligar o percurso:** alegação, contraexemplo no leitor, divergência marcada com o que está registado (início da falha, verificações do próprio pacote), mecanismo e mitigação, recomputação da evidência e reprodução fora da Studio.
3. **Âmbito:** um domínio (aterragem do foguetão), uma alegação, um pacote, grau exploratório sempre visível.
4. **Congelar:** Cinematic, vista geoespacial, domínios de subida e terrestre, e iteração visual. Retirar da navegação principal o hangar, os ambientes e a montra.
5. **Aceitação sem pessoas, só com factos repetíveis:** percurso automático numa construção de desenvolvimento isolada, com listagens do perfil instalado idênticas; identidade da corrida igual em todos os passos; recomputação igual na Studio e na linha de comandos; um byte adulterado retira o veredicto em todo o percurso; orçamento de execuções aplicado; nenhuma semente protegida.
6. **Portões humanos que continuam abertos:** teste de compreensão, piloto de utilização, revisão humana do G3. A vista crença contra verdade só entra depois do teste com pessoas.
7. **Não fazer:** integrar o protótipo antes do teste humano, nova iteração visual, novos domínios, Unreal, publicação, substituir a 0.18.1 sem ensaio de reversão.

## Decisões que ficam com o responsável

1. Enviar os ramos `feat/m19-studio-isolation` e `feat/m19-run-budget` e abrir PR em rascunho para cada um. O ramo de isolamento muda o procedimento de construção da versão (o instalador só sai com `-Release`).
2. Aceitar o marco recomendado acima.
3. G3: proteger 81000-81999 e a reserva em `exec/src/seeds.rs` (muda o hash do binário `vv-exec`); revisão humana metodológica continua pendente.
4. M19.1: quando decidir as duas correções que mudam hashes.

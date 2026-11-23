# M19: estratégia do programa seguinte

Data: 2026-11-18. Base: `main` em `bec7b3f`, Studio 0.18.1 instalado, módulo Cinematic 0.2.8.

Estado deste documento: **estratégia com as decisões do responsável de 2026-11-23** (secção «Decisões do responsável»). Nada aqui altera o produto, os registos, as sementes protegidas ou o estado científico de qualquer resultado.

## Decisão central

O V&V Lab deve organizar-se em torno de **uma investigação**, não de um conjunto de vistas. O objeto central é uma afirmação de segurança e o par de corridas que a põe à prova. O percurso central é: desafiar a afirmação, encontrar o instante em que a crença do controlador se afasta da verdade, explicar a causa, testar uma mitigação e voltar a verificar a evidência.

O que distingue o produto já existe em partes: a separação entre verdade, crença do controlador e veredicto independente, recalculada na reprodução e retirada quando um pacote é adulterado. Falta ligar essas partes num só percurso. Os requisitos M15-R17, M16-R13, M17-R27 e M18-R17 registam que nenhuma jornada atravessa a investigação, a mitigação e a evidência.

## Estado atual, por tipo de evidência

Estas categorias não são intercambiáveis.

| Dimensão | Estado | Evidência |
| --- | --- | --- |
| Código integrado | M11 a M18 em `main`; M10 fora de `main` | CI verde em `bec7b3f`; PR #15 em rascunho, 16 commits à frente e 227 atrás |
| Verificação instalada | 0.18.1 verificada por percursos automáticos | `docs/evidence/m18/installed-0.18.1/` |
| Reversão | Hashes conferidos em 2026-11-18 (22 de 22); **nunca executada** | pasta de recuperação do responsável |
| Validade científica | Todos os resultados M13 e M14 são exploratórios; protocolo G3 é candidato | `docs/m15-g3-onset-protocol.md` |
| Revisão humana | **Nenhuma** do protocolo G3 | M15-R19 |
| Aceitação do responsável | Visual pendente | M16.2-R15 |
| Uso por pessoas reais | **Nenhuma pessoa foi observada** | M15-R22 |
| Requisitos M15 a M18 | 83 cumpridos, 54 parciais, 10 não cumpridos, 3 bloqueados | `docs/m15-m18-acceptance.md` |

## Prioridades

| Ordem | Trabalho | Impacto | Risco | Dependência |
| --- | --- | --- | --- | --- |
| 1 | Evidência humana: piloto com 3 pessoas e pacote de revisão externa do G3 (indisponível em 2026-11-23; conjunto e pacote ficam prontos) | Muito alto | Baixo | Responsável e participantes |
| 2 | Resultados honestos: fechar as pendências da 0.18.1 por classe | Alto | Baixo | Nenhuma |
| 3 | Percurso da investigação, de ponta a ponta (M19.3, adiado) | Muito alto | Médio | Resultados do piloto |
| 4 | Vista instrumental de crença contra verdade (M19.2) | Alto | Médio | Dados já gravados |
| 5 | Montra: estudo de caso guiado | Alto | Médio | Estatuto científico do G3 |
| 6 | M10: uma reformulação em sementes de desenvolvimento | Médio | Médio | Pré-registo dos critérios |

Seis passagens de correção avaliadas por agentes terminaram em PARTIAL. Outra passagem do mesmo tipo tem pouco valor marginal; a informação em falta vem de pessoas.

## Marcos e portões

Cada marco tem ramo e PR próprios. O trabalho de produto e o de investigação nunca partilham um PR.

| Marco | Entrega | Portão de aceitação |
| --- | --- | --- |
| M19.0 Evidência | Esta estratégia, pacote de revisão G3, conjunto do estudo de utilização | Revisão independente; decisões do responsável |
| M19.1 Resultados honestos | Chip de segurança neutro ao lado de requisitos falhados, cláusula falhada de `mission_completion`, frase de impacto na subida, pluma depois do contacto, velocidade no contacto contra último ponto | Verificação do impacto nos hashes antes de cada alteração; percursos no executável isolado |
| M19.2 Vista instrumental | Verdade, estimativa e observações sobre os dados já gravados | Duas iterações, depois adotar, rever mais tarde ou rejeitar; o teste cego de compreensão com pessoas fica como condição aberta da adoção |
| M19.3 Percurso da investigação (adiado) | Uma jornada contínua, uma só identidade de corrida no cabeçalho | Jornada automática de ponta a ponta; 5 pessoas na fase 2 |
| M20 Montra | Estudo de caso local, sem publicação | Aprovação explícita antes de qualquer publicação |
| R10 Investigação M10 | Uma reformulação, com diagnósticos limitados | Pré-registo com critérios de sucesso e de paragem num commit anterior à primeira execução |

**Impacto nos hashes.** Produto e investigação não se separam sozinhos: uma mudança de texto em `evidence.rs` mudou o hash do anfitrião e os identificadores das corridas, e uma linha em `Cargo.toml` quebrou a paridade do M14. Cada alteração de produto declara antes que hashes podem mudar e confirma-o depois. A alteração à cláusula de `mission_completion` toca no registo do domínio terrestre e é a mais sensível da lista.

**Substituição da versão instalada.** Nenhuma versão nova é instalada sem aceitação explícita. Antes da primeira substituição é preciso ensaiar a reversão, que nunca foi executada, com um plano aprovado pelo responsável.

## Vista Cinematic: decisão recomendada

**Congelar o módulo Godot e não fazer mais iterações visuais.** Corrigir só defeitos de honestidade. Três rondas cegas e nove veredictos deram «modest», e a regra de paragem já foi aplicada.

| Opção | Impacto visual | Exatidão | Custo e manutenção | Recomendação |
| --- | --- | --- | --- | --- |
| Congelar o Godot | Nenhum novo | Corrige defeitos | Baixo | **Sim** |
| Unreal Engine 5 e Cesium | O mais alto, não medido | Sem ganho | Muito alto; cerca de 110 GB, EULA, GPU intensiva | Não |
| Linguagem instrumental (renderizador a decidir: SVG, Canvas ou Three.js) | Distintivo, por provar | Só dados gravados | Médio | **Sim, com portão** |
| Imagens fixas dos planos próximos | Boa nos planos próximos | Ilustrativa | Baixo; só com supervisão | Só para a montra |
| Mais arte em Godot | «Modest» nove vezes | Igual | Alto | Não |

Os registos do foguetão já guardam a estimativa e o erro face à verdade, por isso a primeira versão não muda o registo. Não guardam covariância: envelopes de incerteza exigiriam uma alteração ao registo e ficam fora da primeira versão.

**Critério de refutação.** O objetivo é compreensão, não beleza. Mostrar a mesma corrida na vista atual e na instrumental e perguntar quando a crença se afastou da verdade e que requisito falhou. Se a vista instrumental não ganhar com 2 de 3 revisores novos e depois com participantes do piloto, o trabalho para. Sem pessoas disponíveis, esta condição fica aberta; as revisões por agentes, com chave de respostas escrita antes de construir, só podem refutar ou manter a vista como candidata.

**Regra de paragem.** Duas iterações, nenhuma dependência nova (o Three.js r170 e o uPlot já estão incluídos em `desktop/studio/ui/vendor/`; o protótipo fica isolado e a adoção exige decisão explícita do responsável), depois congelar todo o trabalho visual.

## Porta de decisão do M10

Decisão do responsável (2026-11-23): **manter o M10 como ramo de investigação**, sem integração, sem rebase e sem expansão para lá de uma única reformulação.

| Questão | Recomendação | Motivo |
| --- | --- | --- |
| Desvio da paridade (decisão A) | Rejeitar como proposto; permitir uma única reformulação; se falhar, voltar à secção 6.3 | Rampas de 0,5 m/s dão 10 a 31 % de isolamento errado e cada caso acaba em falha de alerta da velocidade horizontal |
| Arquitetura C | Não construir; registar como emenda à decisão 12 | O caso 5082 é uma falha de modo comum que C também aceitaria |
| Perseguição limitada (decisão C) | Rejeitar | Pior do que B+ e `robust` com perdas de GNSS a partir de 12 s |
| Regressões em `gnss_bias` | Aceitar como limite de `E0`, sempre mostradas em `U` | Não são observáveis com este conjunto de sensores |
| Isolamento errado em rampas lentas | Bloqueia o congelamento | É um caminho de confiança falsa |
| 3 falhas de invariante em `gnss_horizontal_bias` | Bloqueiam até serem explicadas | Sem explicação não há limite documentado |

**Plano mínimo, só com sementes de desenvolvimento 5000 a 5099.** Os passos 1 e 2 são diagnósticos limitados; o passo 3 é a única reformulação permitida. Os critérios de sucesso (melhoria material) e de paragem, incluindo os limites de regressão face a `robust` e `guarded` e o par `altimeter_bias` com `gnss_dropout`, ficam em `docs/m10-redesign-preregistration.md` no ramo `research/m10-redesign`, num commit anterior à primeira execução. Se a reformulação não cumprir os critérios de sucesso, ou cumprir a regra de paragem, o resultado é «não avançar».

1. Repetir as sondas `ramp` e `ignition` com traços e comparar a calibração dos resíduos perto da ignição.
2. Publicar no ramo a evidência de B+ sem paridade.
3. Fazer uma única reformulação que declare «não isolado» quando a evidência é ambígua, e correr os testes 1, 2, 3, 9 e 10 da revisão independente contra B, `robust` e `guarded`.

**Regra de paragem, fixada antes:** voltar à secção 6.3 se, depois da reformulação, restar alguma falha de alerta da velocidade horizontal, se `U` de B+ exceder `U` de B em mais de 2 entre 0,2 e 0,8 m/s, ou se surgir um isolamento errado com ruído 1,5 vezes o modelado. Um resultado negativo é um resultado válido.

As sementes 3000 a 3099 e 6000 a 6099 continuam intactas. Não se cria `m10-freeze.json`.

## Credibilidade científica

- **Protocolo G3.** Pacote de revisão em `docs/review/g3-onset/`. O protocolo continua candidato: não é congelado, não é executado e as sementes 44000 a 44999 não são usadas sem autorização e revisão humana.
- **Estudo de utilização.** Conjunto em `docs/usability/`. Não contém participantes nem resultados.
- **Melhorias seguintes.** Verificação do impacto nos hashes em cada PR de produto, ensaio de reversão, instalação numa máquina limpa e comparação com uma ferramenta externa de falsificação.

## Montra

Recomendação: **um estudo de caso guiado sobre um único achado**, com poucas corridas pré-gravadas, um gráfico de verdade contra estimativa que se pode percorrer, registos e hashes para descarregar, comandos para reproduzir e uma caixa de limites.

- O achado G3 é exploratório e a página tem de o dizer enquanto o protocolo não for confirmado.
- Calcular um hash no navegador prova integridade, não recomputação, e a página não pode sugerir o contrário.
- A re-verificação no navegador em WASM fica para uma segunda fase, depois de um ensaio de paridade. A compilação tem de ser um pacote novo, para não alterar o `source_sha256` do `vv-rocket`.
- Nada é publicado sem aprovação. Os modelos são idealizados: não são veículos reais, gémeos digitais nem sistemas validados em voo.

## O que não fazer agora

Unreal Engine, mais arte em Godot, novos veículos, ambientes ou domínios, regresso do propulsor ao local de lançamento, nova passagem de interface avaliada só por agentes, e novas worktrees além da necessária para cada marco ativo.

## Consulta ao Fable 5.2

Foram feitas duas consultas independentes em 2026-11-18, uma sobre o programa e outra sobre o M10. O Fable aconselha; a decisão é do responsável. Nenhuma das consultas conta como revisão humana.

| Tema | Recomendação do Fable | Posição adotada |
| --- | --- | --- |
| Sequência | Evidência humana, depois percurso, montra e M10 | Adotada; a evidência humana está indisponível desde 2026-11-23 e fica como portão aberto |
| Tese do produto | A investigação como objeto central | Adotada |
| Cinematic | Congelar e testar uma linguagem instrumental | Adotada, com regra de paragem |
| Montra | Estudo de caso antes do WASM | Adotada |
| M10 | Ramo de investigação, plano de três passos | Adotada pelo responsável em 2026-11-23, com uma única reformulação |

Pressupostos que o Fable considerou mais frágeis: que o acabamento seja o estrangulamento, que os três perfis de utilizador existam de facto e que produto e investigação se separem sem verificação.

## Decisões do responsável (2026-11-23)

As cinco decisões pedidas em 2026-11-18 foram tomadas assim:

1. **Público principal:** engenheiros técnicos e revisores técnicos independentes.
2. **Piloto com pessoas:** indisponível por agora. O conjunto em `docs/usability/` fica pronto para um estudo futuro. Fazem-se agora percursos de especialista e verificações automáticas, sempre identificados como preparação e revisão de especialista, nunca como validação empírica. O portão humano continua aberto.
3. **Vista Cinematic:** o módulo Godot fica congelado, salvo correções necessárias à honestidade científica.
4. **M10:** fica isolado como investigação, sem integração em `main` e sem construir a arquitetura C. Permite-se uma única tentativa de reformulação, só com sementes de desenvolvimento e critérios de sucesso e de paragem fixados antes. Se não melhorar materialmente os critérios sem regressões inaceitáveis, o resultado é «não avançar».
5. **Protocolo G3:** preparar um candidato corrigido, sem executar sementes protegidas. O revisor humano externo está indisponível por agora, por isso o candidato fica marcado como não revisto por pessoas e não aprovado para execução.

Decisões adicionais: a vista de crença contra verdade é investigada como protótipo, com Three.js **só se trouxer vantagens materiais**, sem presumir que é melhor do que SVG, Canvas ou o módulo Godot; no máximo duas iterações substantivas e uma recomendação final (adotar, rever mais tarde ou rejeitar). Vantagem material quer dizer, aqui, responder melhor às cinco perguntas de compreensão sem acrescentar leituras enganadoras. A versão 0.18.1 instalada não muda neste marco.

A falta de revisores humanos não baixa os critérios de aceitação. O critério de refutação da vista instrumental (2 de 3 revisores novos e participantes do piloto) continua por cumprir: as revisões por agentes podem avaliar correção e riscos, mas não substituem esse teste.

**Numeração em vigor.** A diretiva de 2026-11-23 chama M19.2 à vista de crença contra verdade. O percurso contínuo da investigação, que nas tabelas acima aparece como M19.2, passa a M19.3 e fica para depois.

# Painel de decisão: M10, M11 e M12

Estado em 3 de novembro de 2026. Este painel separa cinco coisas que não são equivalentes: aceitação de engenharia, aceitação do produto, congelamento do protocolo científico, aceitação da hipótese científica e integração em Git. Um PR integrado não fica cientificamente aceite por isso. Nenhum PR desta pilha foi integrado.

## Fronteiras respeitadas

- Nenhuma semente de avaliação (3000 a 3099), de reserva (6000 a 6099) ou do intervalo 100 a 129 foi executada. Nenhum `m10-freeze.json` foi criado.
- Nada foi escrito em `runs/`; as evidências históricas, as referências de recuperação e as árvores de trabalho existentes não foram alteradas. O trabalho novo foi feito em árvores de trabalho separadas.
- O autor das correções não deu nenhum veredicto sozinho. Revisões independentes: estatística, controlo e segurança do M10, fiabilidade do `vv-exec`, segurança do Studio e engenharia de integração. Uma segunda revisão verificou as correções do `vv-exec`.
- `main` não tem proteção de ramo: `branches/main/protection` responde 404, sem regras nem verificações obrigatórias. Não existe requisito de revisão no repositório.

## Pilha e dependências

`main` (`70e5435`) ← PR #15 (M10) ← PR #16 (M11) ← PR #17 (auditoria M12) ← PR #18 (`vv-exec`).

O PR #16 avançou para `c494604` depois de o #17 e o #18 terem sido criados; os dois ainda não incluem esse commit.

## Por PR

### PR #15: M10, navegação resiliente

| Campo | Valor |
| --- | --- |
| Commit em revisão | `b733d14` (antes: `d3118f2`) |
| CI | `d3118f2`: execução 41553427916, verde em Linux e Windows. `b733d14`: execução 41655986012, verde |
| Engenharia | **CONDICIONAL**. Código e testes passam; faltam P1, P2, P4 e a decisão de Holm em código, a F5, a agregação da avaliação, o manifesto de congelamento reprodutível e a rastreabilidade de parâmetros e constantes |
| Protocolo científico | **BLOQUEADO**. As decisões A e C foram refutadas tal como propostas; a potência da P4 é 0,53 com a regra registada, não 0,90 |
| Hipótese científica | **BLOQUEADO**. Não avaliada; as sementes protegidas não foram usadas |
| Integração | Não integrar |

Revisão independente (`docs/m10-independent-review.md` no PR #15):

- **A, paridade ancorada: não suportada tal como proposta.** Isolamento errado com rampas coerentes lentas perto da ignição: 10 a 31 % a 0,5 m/s. Cada isolamento errado acabou em U, com falha de alerta da velocidade horizontal (186 casos), um caminho de confiança falsa. O varrimento registado não o podia ver: usou rampas de 1 m/s e só regista o alerta vertical. Entre 0,2 e 0,8 m/s, B+ tem 12/18 U contra 6/18 de B.
- **B, não construir C: suportada.** A falha de modo comum da semente 5082 não é observável por separação de soluções com o conjunto E0. "PL_v ≈ 2 m" está errado: é cerca de 0,34 m. Propor uma hipótese separada com sensor independente (E1).
- **C, perseguição limitada: não aceitar.** O 41 para 85 em 100 esconde 5 passagens de T para U por célula. Com perdas do GNSS a partir de 12 s, a variante tem 31/200 U, contra 15/200 de B+ aprovado e 22/200 de `robust`. As duas células `gnss_dropout` são idênticas e são contadas duas vezes.
- **D, polarização do GNSS: limite de observabilidade suportado.** A regressão (+99 U contra `guarded`) está escondida em todos os agregados do documento de implementação; só o dossiê a mostra em U.
- 13 testes refutáveis definidos antes de qualquer proposta de congelamento.

### PR #16: M11, V&V Lab Studio

| Campo | Valor |
| --- | --- |
| Commit em revisão | `c494604` |
| CI | Execução 41654052018: Linux, Windows, `desktop`, `installer` e comparação canónica verdes |
| Engenharia | **ACEITE: ENGENHARIA**, com os riscos abaixo |
| Produto | **CONDICIONAL** |
| Ciência | Não aplicável. As demonstrações M10 são de desenvolvimento |
| Integração | Não integrar como está: depende do #15. Caminho proposto: PR A abaixo |

Corrigido nesta revisão (`c494604`):

- a reprodução rejeita um `meta.json` cujo resumo difere de `record.json`, ou cujo identificador não corresponde ao pedido e ao build guardados;
- a plataforma recusa um anfitrião substituído depois do arranque;
- os pacotes de evidência declaram `development_demonstration`, e uma reprodução falhada fica marcada no nome;
- a Biblioteca lista as execuções mais recentes.

Em aberto:

- a política de sementes vem de `domain.json` e não é comparada com o manifesto do anfitrião;
- sem Job object: um neto sobrevive ao limite de tempo;
- as variáveis `VVLAB_*` são aceites no build de produção;
- corrida em execuções idênticas simultâneas;
- reprodução nativa depois de uma falha de hash;
- sem `cargo audit` nem `npm audit` na CI do `desktop/`;
- aceitação da interface num computador limpo: só o runner da CI, onde o teste de interface não corre;
- instalador não assinado.

### PR #17: auditoria de desempenho do M12

| Campo | Valor |
| --- | --- |
| Commit em revisão | `65b95d5` |
| CI | Execução 41635533761, verde |
| Engenharia | **CONDICIONAL**. O protótipo `spikes/m12-perf/rocket-bench` usa APIs que só existem no M10 (`nav_verify`, `Policy::is_m10`, `Verification.navigation`) |
| Ciência | Não aplicável |
| Integração | Só depois do #15. O perfil `dev-release` e as medições sem M10 podem ir para o PR A |

### PR #18: motor `vv-exec`

| Campo | Valor |
| --- | --- |
| Commit em revisão | `efa463a` |
| CI | `91de113`: execução 41648098573, verde em Linux e Windows (falha do fixture corrigida). `2b234f2`: execução 41651104910 falhou (`cargo audit` sem instalação no Windows; clippy só em Unix), corrigido em `8d7afce`. `efa463a`: execução 41655149041, verde em Linux e Windows, incluindo o teste de `SIGINT` em Linux |
| Engenharia | **ACEITE: ENGENHARIA**, com os riscos em aberto abaixo |
| Ciência | Não aplicável. Todos os relatórios declaram `inference` exploratória |
| Integração | Pelo PR B abaixo, ou depois da pilha |

Falha de CI do fixture. Duas causas, nenhuma estatística:

- `sum()` de floats passou a ser compensada no Python 3.12, e a CI usa 3.10;
- a libm de Linux e a de Windows arredondam o último bit de forma diferente.

A referência passou a usar aritmética decimal de 60 dígitos. A função de distribuição coincide com o valor racional exato. Os contratos de bytes exatos, tolerância numérica e correção matemática ficaram separados. Até aqui, a CI não corria os testes de `exec/`; passou a correr.

Corrigido e verificado pela segunda revisão:

- Ctrl+C;
- inicialização interrompida;
- escritor único;
- `verify`, que recalcula todos os registos e apanha um registo falsificado com hash recalculado;
- guarda de `runs/` no motor;
- convergência decidida no passo usado;
- envelope não declarado sem fração;
- política de erros e natureza exploratória declaradas;
- fluxo de bootstrap separado;
- teste de memória instável.

Medido: 14 400 execuções em 7,0 s e verificação completa em 10,4 s, com 16 trabalhadores.

Em aberto:

- registo sem cadeia de hashes;
- `equivalence.json` sem escrita atómica;
- sem sincronização por linha;
- mutexes envenenáveis;
- linha final danificada com mudança de linha não é reparada;
- sem Sobol de baixa discrepância;
- amostra de equivalência sem execuções com erro;
- sem paridade automática para o corpo rígido;
- exatidão para n grande não testada;
- tratador de Ctrl+C do Windows sem teste automático.

## Estratégia de integração proposta

A revisão de integração montou `desktop/` e `exec/` sobre `main` numa árvore de trabalho separada. O M1 não muda em nenhum ponto da pilha. As saídas do `vv-rocket` para todos os casos de `main` são iguais com e sem M10, exceto o `source_sha256`.

1. **PR A, M11 sem M10** (base `main`). Inclui:
   - `desktop/**`, o perfil `dev-release`, `.gitattributes`, `.gitignore` e os jobs `desktop` e `installer`.
   - A remoção do conteúdo M10 do domínio do foguetão: `case.rs`, `catalog.rs` e `demos.rs`, com as demonstrações reescritas sobre M9 e M9.1.
   - A remoção dos 10 ficheiros `golden/m10-*` e a reescrita de 3 testes do anfitrião e 2 de demonstração.

   Isto muda o produto que o proprietário já viu, por isso precisa de aprovação.
2. **PR B, `vv-exec`** (sobre A ou `main`): `exec/**` com o caso base `m91-nominal.json`, evidência regenerada sobre `main`, a referência estatística e o seu teste, e o passo de CI do `exec/`.
3. **Depois da aceitação do M10**: o #15 e, depois dele, o conteúdo M10 do Studio, a evidência do M12 produzida sobre o M10, o protótipo do #17 e a regeneração de todos os `source_sha256` fixados.

Antes de qualquer integração: ativar a proteção de `main` com revisão obrigatória e as verificações da CI obrigatórias.

## Decisões do proprietário

1. **Decisão A:** rejeitar a paridade ancorada tal como proposta e autorizar uma emenda de desenho que passe os testes 1, 2, 3, 9 e 10 da revisão.
2. **Decisão B:** aceitar "C adiado para a experiência original" e registar uma hipótese E1 com sensor independente.
3. **Decisão C:** rejeitar a emenda da perseguição limitada à 8.3.
4. **Decisão D:** aceitar o limite de observabilidade do E0 como limitação explícita e exigir a regressão em U, contra `guarded` e `robust`, em todos os agregados.
5. **P4:** escolher entre baixar o critério de efeito de 3 pp e desenhar para uma alternativa maior. Com a regra atual, a potência é 0,53.
6. **Integração:** aprovar a divisão em PR A e PR B, ou manter a pilha até à aceitação do M10.
7. **Repositório:** ativar a proteção de `main`.
8. **Congelamento:** não está pronto. Nenhum pedido de congelamento ou de acesso às sementes de avaliação é feito agora.

## Artefactos e hashes

| Artefacto | SHA-256 ou identificador |
| --- | --- |
| Fixture `exec/tests/fixtures/stats-reference.json` (`91de113`) | `af7faa2543c037865fcefbfbe3a9f15ddde32a86e15da03e526721cbd517af6c` |
| Binário `vv-rocket` das sondas do M10 | `9a3f477650fc069401f1283fd10fba9f7f186e4f0c4c441c1a5f9a955642c80e` |
| Sondas M10 `ignition`, `ramp`, `rampbase`, `steps`, `chase` | ver `docs/m10-independent-review.md` no PR #15 |
| Instalador M11 (CI de `2bcc4ea`) | `2478ea52…`, 5 700 157 bytes; um instalador de `c494604` ainda não foi descarregado nem testado na interface |

O seguimento e o motivo de cada veredicto estão nos documentos de cada PR: `docs/m10-independent-review.md` (#15), `docs/m11-desktop.md` e `docs/m11-acceptance.md` (#16), `docs/m12-performance-audit.md` (#17) e `docs/m12-exec.md` (#18).

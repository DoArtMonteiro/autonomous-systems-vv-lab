# Pacote de revisão externa: candidato a protocolo de confirmação do G3 com viés GNSS tardio

## O que é este pacote

Este pacote ajuda uma pessoa que nunca trabalhou neste projeto a rever um **candidato a protocolo estatístico**, escrito antes de qualquer execução confirmatória. O protocolo está em `docs/m15-g3-onset-protocol.md` e propõe como testar, com sementes novas e regras fixadas à partida, uma hipótese sobre o comportamento de um controlador de aterragem propulsiva num simulador determinístico.

O pacote não substitui o protocolo. Resume-o, verifica as contas que se podem refazer sem simular, lista o que o protocolo fixa e o que ainda falta fixar, e propõe perguntas concretas.

## Estado

- O protocolo é um **candidato**. Não está aprovado, não está congelado e não foi executado. Nenhum ficheiro de congelamento existe.
- Todos os resultados sobre o instante de início do viés continuam **exploratórios**. Nada neste pacote os confirma.
- O protocolo, as revisões anteriores e este pacote foram produzidos por agentes de inteligência artificial. **Revisão por agentes não é revisão humana por pares.** Esta é a primeira leitura humana pedida.
- As contas deste pacote usam só aritmética e estatística. Não se correu nenhum simulador, campanha, `vv-exec`, `vv-rocket` ou `cargo`, e não se usou nenhuma semente do protocolo.
- Referência fixa: commit `bec7b3f` (`bec7b3f990291239313360b163ad999c31fb6310`) do repositório. Todos os números de linha citados referem-se aos ficheiros nesse commit.

## O que se pede ao revisor

1. Dizer se as hipóteses, o desenho e as regras de decisão permitem tirar as conclusões que o protocolo diz permitir, e se há alguma que não permitam.
2. Responder às 25 perguntas de `reviewer-questions.md`, cada uma com «concordo», «preocupação» ou «bloqueio» e um comentário. As perguntas têm prioridade indicada; as marcadas «alta» correspondem a fraquezas que o autor do pacote encontrou.
3. Sinalizar qualquer erro nas contas de `independent-checks.md` ou nos números de `study-summary.md`.
4. Dizer se, na sua opinião, o protocolo pode ser congelado tal como está, com alterações, ou não deve ser congelado. Esta recomendação não vincula ninguém: a decisão de aprovar e congelar é do responsável pelo projeto.

## O que não se pede

- Não se pede revisão do código do simulador nem do controlador, exceto quando uma pergunta o refere.
- Não se pede revisão do Studio, do `vv-exec`, nem dos módulos M10 a M18 do projeto.
- Não se pede validação física do modelo de veículo, nem comparação com dados de voo (não existem).
- Não se pede que corra simulações. Pede-se, de facto, que **não** corra nenhuma das sementes 44000 a 44999 nem 50000 a 59999: estão reservadas.
- Não se pede que edite o protocolo. Alterações propostas vão no formulário; qualquer alteração produz um novo candidato, segundo a secção «Decisão do responsável» do protocolo.

## Tempo estimado e ordem de leitura

Cerca de 2 horas para uma leitura atenta (a soma da tabela). Quem tiver menos tempo pode ler `study-summary.md`, `limitations.md`, as 9 perguntas marcadas «alta» e as linhas do protocolo que elas citam (cerca de 60 minutos).

| Passo | Ficheiro | Tempo | Para quê |
| --- | --- | --- | --- |
| 1 | `study-summary.md` | 20 min | Resumo autónomo: contexto, mecanismo, hipóteses, desenho, análise, decisões. |
| 2 | `docs/m15-g3-onset-protocol.md` | 30 min | O texto que está em avaliação. Escrito em português europeu. |
| 3 | `limitations.md` | 10 min | O que o estudo e este pacote não conseguem dizer. |
| 4 | `independent-checks.md` | 15 min (só a tabela inicial) | Contas refeitas, com as discrepâncias encontradas. O apêndice tem o programa completo. |
| 5 | `source-commitments.md` | 10 min | Que fontes o protocolo fixa, com hashes, e o que um congelamento ainda teria de fixar. |
| 6 | `reviewer-questions.md` | 30 a 40 min | As perguntas e o formulário de resposta. |

Documentos de apoio, só se precisar de contexto: `docs/m14-g3-onset-protocol-draft.md` (rascunho anterior, que o protocolo substitui como proposta), `docs/m13-discovery-lab.md`, `docs/m14-evidence-robustness.md`, `docs/evidence/m14/masking/`, `scripts/m14_masking_model.py`, `exec/claims/m13/g3-onset.json`, `exec/cases/m13/g3-registered.json`, `exec/src/seeds.rs` e `crates/vv-rocket/src/` (os ficheiros `landing_*.rs`).

## Principais fraquezas encontradas (resumo)

Detalhe, com linhas, em `independent-checks.md`, `source-commitments.md` e `reviewer-questions.md`.

- O hash do código do simulador que o protocolo cita como atual (`12b276cb...`, linha 166) já não corresponde ao commit `bec7b3f`, onde vale `295a45b2...`. Só mudou `landing_model.rs` (um esquema de caso novo); não está demonstrado aqui que o comportamento dos casos antigos seja igual.
- Duas citações de linha do protocolo (`landing_model.rs:414-418` na linha 33, `landing_model.rs:238` na linha 133) estão desatualizadas: hoje são as linhas 426 a 431 (`ascent_abort_vz_mps`) e 250. As linhas 414 a 418 mostram hoje os limites 0,1 a 1000 do limiar do altímetro (chamada `within(` nas linhas 417 a 422).
- A linha 115 diz que seriam precisas 63 sementes para um teste binomial ao nível 0,01/14. A conta dá 69; 63 corresponde a 0,01/7.
- O critério «fração ≥ 0,9» de S4 e S5, com 60 sementes, decide sozinho (o McNemar exato é redundante) e é uma estimativa pontual: aceitaria um sistema com taxa verdadeira de 0,80 em cerca de 3 % das vezes e de 0,85 em cerca de 18 %.
- Os testes de H1 e H2 agregam 160 sementes e toleram 6 falhas; uma célula inteira de 5 sementes (um início, uma magnitude) pode falhar e a hipótese ainda ficar «confirmada».
- Dos 8 inícios do protocolo, 0,01 s e 0,1 s são a mesma condição física no simulador (ambos primeiro aparecem na medida GNSS de 0,1 s).
- O ficheiro `scripts/m14_masking_model.py` foi modificado no commit do teste (`1195c1b`), depois da previsão: só a escrita das saídas, não o cálculo. Os bytes que um congelamento fixaria não são os que geraram a previsão.
- A linha 153 proíbe «as sementes protegidas do foguetão em `exec/src/seeds.rs`», lista que, lida à letra, inclui 44000 a 44999, as próprias sementes do protocolo.

## Como devolver comentários

Use o formulário no fim de `reviewer-questions.md` e o bloco de resposta de cada pergunta. Copie-os para um ficheiro à parte, preencha, e devolva-o a quem lhe enviou este pacote. O canal concreto de devolução e o prazo não estão definidos neste pacote; ficam por indicar pelo responsável.

Se preferir comentar diretamente o protocolo, cite sempre o número da linha do commit `bec7b3f`.

# Fontes que o protocolo fixa

Este ficheiro lista o que o protocolo (`docs/m15-g3-onset-protocol.md`, passo 2 de «Execução e congelamento», l. 160 a 168) diz que um congelamento fixaria, e compara com o que existe no commit `bec7b3f`.

Estado: **não existe ficheiro de congelamento** (`docs/m15-g3-onset-freeze.json` não existe), **nem executor, nem script de análise, nem binário fixado**. Nada aqui é um congelamento; é um inventário.

## Como se calcularam os hashes

O protocolo pede o sha256 dos bytes **guardados no commit**, não dos ficheiros da cópia de trabalho, porque `core.autocrlf` está ativo na máquina de desenvolvimento. Cada hash abaixo foi calculado a partir do blob no commit `bec7b3f`:

```sh
git cat-file blob bec7b3f:<caminho> | sha256sum
```

(Equivalente, em Python, com `hashlib.sha256` sobre a saída binária desse comando. Foi o que se usou; não se leram os ficheiros da cópia de trabalho para os hashes.) O repositório tem `.gitattributes` com `eol=lf` para `*.rs`, `*.toml`, `*.json`, `*.py` e `*.md`; nos 5 ficheiros principais, os bytes da cópia de trabalho coincidem com os do blob e não têm `\r\n`. Os outros não foram comparados.

O commit de referência completo é `bec7b3f990291239313360b163ad999c31fb6310`.

## Fontes fixadas pelo protocolo

| Fonte | Caminho | sha256 do blob em `bec7b3f` | Prefixo citado no protocolo | Resultado |
| --- | --- | --- | --- | --- |
| Este protocolo | `docs/m15-g3-onset-protocol.md` | `e85387a6b37c42d864cd5a70ff459a1618e0493ecfeada96f68d01054402d999` (id Git `cb6b792d623b871f64735d8ffe194e71f0f2e017`) | nenhum | Sem comparação possível. Um documento não pode conter o seu próprio hash; ficaria só no ficheiro de congelamento. Última alteração: commit `8be03e4` (2026-11-04 00:23). |
| Alegação | `exec/claims/m13/g3-onset.json` | `f9e6154c8df0a9288cd2eea6ab634cd735a83e1feee0689525cabb93d6d6d319` | `f9e6154c...` (l. 162) | Coincide. |
| Caso base | `exec/cases/m13/g3-registered.json` | `4f30b68094f4b7ff30039509b4362b47d513063c7e4b87c1348fdfeb87bc88f7` | `4f30b680...` (l. 163) | Coincide. Igual a `case_sha256` em `sources.json`, `prediction.json` e `investigation.json`. |
| Família: viés GNSS baixo | `exec/cases/m13/family-gnss-bias-low.json` | `daa27cf70f937f467dd7e15aa7d715b8bb9a765fcb46af198d1684896681b108` | nenhum (só «as 8 famílias») | Igual a `sources.json` e a `family_case_sha256` em `investigation.json`. |
| Família: viés do altímetro | `exec/cases/m13/family-altimeter-bias.json` | `b7c7242a0241ccd68b5ca18e90e4e9378b1595a3922b122f28a1d7d440c2b229` | nenhum | Igual aos dois registos. |
| Família: viés do altímetro baixo | `exec/cases/m13/family-altimeter-bias-low.json` | `933107afedbd640f9407fa8b3d30d27d19cef3997fd3d7277cfef65c7e29bba6` | nenhum | Igual aos dois registos. |
| Família: falha de GNSS | `exec/cases/m13/family-gnss-dropout.json` | `c47e909b258e7d5023e327ad1269fb9ff0c1921acf6cbe6f403b9d2cd3681cff` | nenhum | Igual aos dois registos. |
| Família: falha do altímetro | `exec/cases/m13/family-altimeter-dropout.json` | `9236546226aa6465a79fbd062779f3363375e2a6bf1b11e0f64b5a122315e79b` | nenhum | Igual aos dois registos. |
| Família: viés do acelerómetro | `exec/cases/m13/family-imu-accel-bias.json` | `5366c80d5d12f8a61bd4c84dfc85c8004e6e0e0a60b3edee2c96b27d6f1315ad` | nenhum | Igual aos dois registos. |
| Família: perda de impulso | `exec/cases/m13/family-thrust-loss.json` | `70442780e8ba366f3bff4daa3e22d51b45815a1a64214df8e661f2c9378b76f8` | nenhum | Igual aos dois registos. |
| Família: viés GNSS líquido pequeno | `exec/cases/m13/family-small-net-gnss-bias.json` | `f9f2bedd8f620d466dabd0a1d2e4f69247f6249668347deca39b20325b36ef60` | nenhum | Igual aos dois registos. |
| Fontes dos casos | `exec/cases/m13/sources.json` | `01602dc6bf1d48a32212d521831d17e7722c38a507fe2de839475adfaa999cb3` | nenhum | O `source_sha256` que contém (`69ecad65...`) coincide com o blob de `crates/vv-rocket/landing/m91-nominal.json`. |
| Previsão | `docs/evidence/m14/masking/prediction.json` | `9a67d22e1c9d620d4a3d1d762b44919ea724378f5b1b7634ea9878f81468d9b1` | `9a67d22e...` (l. 164) | Coincide. Igual a `prediction_sha256` em `test.json`. |
| Modelo | `scripts/m14_masking_model.py` | `c6cbdc29fd01ffd38d7686f32d1df5fa9037af045bc4594ecd4e518f74f1add5` | nenhum | Sem comparação possível. Alterado em dois commits: criado em `73c9ff5` (com a previsão) e modificado em `1195c1b` (o commit do teste), por `git diff 73c9ff5 bec7b3f -- scripts/m14_masking_model.py`: 3 linhas acrescentadas e 2 removidas, só na escrita dos ficheiros de saída (`write_text` passa a `write_bytes`, para que o hash registado seja o do ficheiro guardado). `model()`, `predict()` (o cálculo) e `test()` (a lógica) não mudaram, e o b* recalculado neste pacote coincide com `prediction.json` em todos os dígitos. O ficheiro de hoje não tem os mesmos bytes que o que gerou a previsão; o protocolo (l. 56) diz «modelo inalterado», o que vale para o cálculo mas não para os bytes. |
| Código do simulador (`source_sha256`) | `crates/vv-rocket` (ver abaixo) | `295a45b26370e0390294b5a1cdbe975e7b8d0b77cbb7e07d4c2fae76a8612976` | `12b276cb...` «hoje» (l. 166) | **Não coincide.** Ver abaixo. |

## Discrepância: o `source_sha256` do `vv-rocket`

- O protocolo escreve «o `source_sha256` do `vv-rocket` (hoje `12b276cb...`)» (l. 166). O valor completo, `12b276cb182b62ee3ecda602fe5f82edec2f40163afddaa12513fdc54edcbc05`, é o que está em `docs/evidence/m13/g3-onset/investigation.json` e em `docs/m9-powered-landing.md`.
- A função `source_sha256()` (`crates/vv-rocket/src/lib.rs`) calcula o sha256 de 20 ficheiros (`Cargo.lock`, `Cargo.toml` e 18 ficheiros de `src/`), com o nome do ficheiro, um byte 0, o conteúdo com `\r\n` trocado por `\n` e outro byte 0. Reproduziu-se esta função em Python sobre os blobs, sem compilar nada.
- Resultados da reprodução:

| Commit | Data | `source_sha256` recalculado |
| --- | --- | --- |
| `1195c1b` (teste de P1 e P2) | 2026-11-03 | `12b276cb...` (coincide com o pacote M13) |
| `8be03e4` (escrita do protocolo) | 2026-11-04 00:23 | `12b276cb...` |
| `3baa1c1` (esquema de caso v2) | 2026-11-04 23:24 | `a7d43d25...` |
| `04de572` | 2026-11-12 | `295a45b2...` |
| `bec7b3f` | referência | `295a45b26370e0390294b5a1cdbe975e7b8d0b77cbb7e07d4c2fae76a8612976` |

- Conclusão: o valor `12b276cb...` estava certo quando o protocolo foi escrito e **está desatualizado em `bec7b3f`**. A reprodução da função em `1195c1b` e `8be03e4` dá o valor do pacote M13, o que valida a reprodução.
- Só um dos 20 ficheiros mudou desde `3962482` (o commit do simulador a que corresponde `12b276cb...`): `crates/vv-rocket/src/landing_model.rs` (+152 linhas, -3). A alteração acrescenta o esquema de caso `vv-rocket-landing.v2`, exploratório, com a sua validação (`check_exploratory`); o ramo dos casos `v1` chama `check_registered`, como antes. Isto vem da leitura do diff, não de uma execução: **não está demonstrado aqui que as saídas dos casos `v1` são iguais bit a bit** com as duas versões.
- Os 20 hashes por ficheiro em `bec7b3f` estão no fim deste ficheiro, para quem quiser reproduzir.
- Consequência para um congelamento: o hash a fixar seria `295a45b2...` (ou o que valer no commit escolhido), e a evidência de desenvolvimento do M13 (`12b276cb...`) seria de uma versão anterior do código. O protocolo devia dizer qual é a versão de referência e se exige uma verificação de equivalência de bytes antes da primeira execução.

## Citações de linha desatualizadas

O protocolo cita linhas de `crates/vv-rocket/src/landing_model.rs` que estavam certas em `3962482` e mudaram com o mesmo commit `3baa1c1`:

| Linha do protocolo | Citação | Em `bec7b3f` | Nota |
| --- | --- | --- | --- |
| 33 | `landing_model.rs:414-418` (máximo aceite de `ascent_abort_vz_mps`, 100) | 426 a 431 (`within(` na 426, fecho na 431, com `g.ascent_abort_vz_mps`, 0,0 e 100,0) | As linhas 417 a 422 contêm hoje a chamada `within(` do limiar do altímetro (0,1 a 1000, valores nas linhas 420 e 421), não a de `ascent_abort_vz_mps`. Verificado no blob de `bec7b3f`. |
| 133 | `landing_model.rs:238` (mínimo de 5 m do viés do altímetro) | 250 (`FaultKind::AltimeterBias => Some((5.0, 50.0))`) | |

As outras citações de código do protocolo foram conferidas e coincidem, com uma folga de 0 a 2 linhas: `landing_sensors.rs:79-80`, `landing_controller.rs:98-106`, `119-133`, `192-200`, `247-252`, `landing_types.rs:35-37`, `40-42`, `landing_sim.rs:211`, `221-224`, `exec/src/investigate.rs:60-70`, `449-458`, `exec/src/seeds.rs:28-32`, `crates/vv-rocket/src/main.rs:32-37`.

Um congelamento deve preferir citar o hash do ficheiro e o nome da função, não o número de linha.

## O que um congelamento ainda teria de fixar e não existe

| Item | Estado | Nota |
| --- | --- | --- |
| `scripts/m15_g3_confirm.py` (executor) | Não existe | Tem de implementar: guarda de sementes, mapa semente para condição, grelha Halton e quantização das famílias, aplicação dos ponteiros, repetição de execuções com falha, registo com hashes, retoma. O protocolo descreve o comportamento (l. 159) mas não a forma de cada cálculo; ver pergunta 19. |
| `scripts/m15_g3_analyse.py` (análise) | Não existe | Tem de implementar os testes binomiais, McNemar, intervalos por estatística de ordem, Clopper-Pearson e as regras de decisão. |
| sha256 do binário `vv-rocket` | Não existe | Exige compilar, o que não se fez. Depende do compilador e da máquina; só liga a execução a uma construção. O `source_sha256` é mais portável. |
| Versão do `rustc` e comando de compilação | Não existe | |
| Commit da árvore fixada | Não existe | |
| `docs/m15-g3-onset-freeze.json` | Não existe | Seria um commit só com este ficheiro, enviado ao repositório público antes da primeira execução. |

Itens que o protocolo usa mas **não** lista para fixar:

- `docs/evidence/m14/masking/test.json` (sha256 `29b1066d0763c7f763ef53e31afde4ef5c379f19a2d40f79cfdcd4be255ce3e2`): é a base dos cálculos de precisão de H3 (l. 176). Foi gerado a partir de `prediction.json`, cujo hash cita.
- Versão do Python e das bibliotecas dos dois scripts (um executor e uma análise que fazem estatística precisam de versão fixa).
- `exec/src/seeds.rs` (sha256 `a2affe4ca1e709608c958c67eb9fbc0abbc52230da8f5e78f097c4ca70f1f47a`) e `exec/src/investigate.rs` (`dafdf1bfd946a3c8cdb4fb043a61143b700f396d81ffee3713ec4ba12183cb92`): o protocolo cita-os para justificar a necessidade de guardas próprias, mas o executor novo não os usa. O que importa é a lista de sementes proibidas do executor, a escrever.

## Fontes de contexto lidas para este pacote (não fixadas)

| Ficheiro | sha256 do blob em `bec7b3f` |
| --- | --- |
| `docs/m14-g3-onset-protocol-draft.md` | `eaf43a201b2eff52775ac6e594c639e2abb4e4a5fc89f3d1ecf46bafaaa372b8` |
| `docs/m13-discovery-lab.md` | `6d2cd16036d3861841b4c8d788cd5701e28948c2086290db312a38cd6e6b3b8e` |
| `docs/m14-evidence-robustness.md` | `5e419bba6d8aff5a31b343c95ffb0bb0b1d213d324b71fefff08b1468625fcfe` |
| `docs/evidence/m13/g3-onset/investigation.json` | `c98f96388b4a4b9b556fa8a47bbf326dda958f583a4400d3f7703f452d502b12` |

## Hashes por ficheiro do `source_sha256` em `bec7b3f`

Sha256 do blob de cada um dos 20 ficheiros, em `crates/vv-rocket/`. A coluna «Desde `3962482`» diz se o blob difere do do commit `3962482`.

| Ficheiro | sha256 | Desde `3962482` |
| --- | --- | --- |
| `Cargo.lock` | `9223df2abf54b706fc59f95b19a82c4a692259071e4a99c55b9ace0922781bec` | igual |
| `Cargo.toml` | `e05e6087e014b54f27e3905c2aac8d15da985c63532e5341c67d2ea550f29fe8` | igual |
| `src/dynamics.rs` | `153cb17755d3f4bc022990e661ea2d9b39090334a75185d674939e7da71ea016` | igual |
| `src/landing_actuator.rs` | `2dca1b0fe735cbf55460e44c88420c7ecc9651c3130b3c9e175c920e931e5cbf` | igual |
| `src/landing_controller.rs` | `03696a5c674bdd73ee3791a1ca6d7eacceb110514b7b1cc50988ebc399bb8c49` | igual |
| `src/landing_model.rs` | `7d09aa6222f516c59db85dc6dde096e0a55e70acb40ed64bc072fd5c445bbef7` | **diferente** |
| `src/landing_run.rs` | `fed954e3ba2b1f225b369d107c183f624cbe14e5be58ca4b97efcb4402d2504e` | igual |
| `src/landing_sensors.rs` | `46a26d176ff9b8340c6757ab6a05f9b1943de4b893397f690c54eada5bf36586` | igual |
| `src/landing_sim.rs` | `33132e090e86d1c2e5aefaecbe8903829294967aa6ec1bc963064c6d3a6ffc9b` | igual |
| `src/landing_truth.rs` | `f3676da6232569074a3320559b3bfea2318df680f34cc42ea73e63cc6be37e8b` | igual |
| `src/landing_types.rs` | `bf129d71cb4eac42b10c955512c64de600f041300619be1c51e2744b3ca590f7` | igual |
| `src/landing_verify.rs` | `3f7c314997950d458b44311e2e76585a75a7b654853f57e8715b73587c487ff7` | igual |
| `src/lib.rs` | `e051578c10e445f7c027e54f7c056fb57d601acee75cb86c7630f9d03057dc4c` | igual |
| `src/main.rs` | `ec54fef0d148e7ad66aa20f6e2fa76042de89c2db7a84d6be61e0e9acaf1e30b` | igual |
| `src/math.rs` | `027316ae4cac9b191a9b1001a6576f82319f589683c8da9bbe97f33f16ec61a0` | igual |
| `src/model.rs` | `95e97548e312fec3a34b4fc10d75e838d3f6cae6f790bc5f272f182b82bb7ace` | igual |
| `src/prng.rs` | `8b4bb33aeb8d2d12bcbfe8b166a4d0c44fef0854e5c5226d30187b33a4d76cd6` | igual |
| `src/run.rs` | `59307b3a336e6db83f1891a39bac18f7be9b3c85eebd6ae649addc855d83d13b` | igual |
| `src/sim.rs` | `bccb4b2227ccf9fdeb70d0e14e30d639282128cc7539a5884cd9dfe4bd09fd4c` | igual |
| `src/verify.rs` | `4f3ffc9296d71f2b7958743acfdf1cbc2e4d82ef476e73f90db402611865bb7a` | igual |

Reprodução (sem compilar; Python 3.11 ou posterior; correr na raiz do repositório):

```python
import hashlib, subprocess
R = "bec7b3f"
files = ["Cargo.lock", "Cargo.toml", "src/dynamics.rs", "src/landing_actuator.rs",
         "src/landing_controller.rs", "src/landing_model.rs", "src/landing_run.rs",
         "src/landing_sensors.rs", "src/landing_sim.rs", "src/landing_truth.rs",
         "src/landing_types.rs", "src/landing_verify.rs", "src/lib.rs", "src/main.rs",
         "src/math.rs", "src/model.rs", "src/prng.rs", "src/run.rs", "src/sim.rs", "src/verify.rs"]
d = hashlib.sha256()
for f in files:
    blob = subprocess.run(["git", "cat-file", "blob", f"{R}:crates/vv-rocket/{f}"],
                          capture_output=True, check=True).stdout
    d.update(f.encode()); d.update(b"\0")
    d.update(blob.decode().replace("\r\n", "\n").encode()); d.update(b"\0")
print(d.hexdigest())  # bec7b3f: 295a45b2...; 3962482 and 1195c1b: 12b276cb...
```

A lista de ficheiros e a ordem copiam a de `source_sha256()` em `crates/vv-rocket/src/lib.rs`. Se essa função mudar, esta reprodução deixa de valer.

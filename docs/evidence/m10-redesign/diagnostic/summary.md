# Diagnóstico do M10 antes da reformulação (sementes 5000 a 5019, código sem alterações)

Comando: `python scripts/m10_redesign_diagnostic.py run --binary crates/vv-rocket/target/release/vv-rocket.exe --output docs/evidence/m10-redesign/diagnostic/records.json` (binário em `binary.sha256`, construído de `b733d14` mais só este script). Máquina: Windows 11, AMD64, Python 3.14. Plano: `rampbase` da sonda da revisão independente, só 0,5 m/s, início 4,5; 6; 8; 10 s, sementes 5000 a 5019, braços B e B+: 160 execuções. Nenhuma semente protegida. Registos por execução: `records.json`; decomposição completa: `summary-raw.txt`.

Reproduz exatamente `probe-rampbase-summary.txt`: B+ R 10, T 6, U 64 em 80 (6 isolamentos errados, 4 falhas `hv`); B R 9, T 65, U 6.

## Decomposição dos 64 U de B+

| Veredicto de isolamento | U | Falha `hv` | Requisitos falhados |
| --- | --- | --- | --- |
| nenhum (não isolado) | 58 | 0 | R1 e R5 em 49; só R1 em 9; invariante `S2_keep_out` em 2 |
| errado | 6 | 4 | R1 e R2 e R5 em 5; R1 e R5 em 1 |
| correto (tardio ou não) | 0 | 0 | |

- Nenhum dos 64 U tem isolamento correto: a hipótese «isolamento correto tardio» não existe nesta amostra. Os 6 isolamentos errados ocorrem 0,8 a 1,1 s depois do início.
- A falha dominante é **R1** (velocidade vertical no toque) em 64 de 64; R2 (lateral) só em 5, todos de isolamento errado. Os 58 U não isolados não são falhas laterais.
- B, com a mesma rampa, falha só R5 (T 65) e tem 6 U por invariante `S2_keep_out`; não tem isolamento nem falha `hv`.
- Por início, B+ tem isolamento correto em 11 de 20 a 4,5 s, 3 a 6 s e 2 a 8 s, e nenhum a 10 s: quando isola bem, recupera mais (R 7 a 4,5 s).

## Traço de uma execução não isolada (B+, semente 5000, início 8 s)

Caso fora do repositório gerado do modelo `m10-nominal.json` com `gnss_coherent_ramp` de 0,5 m/s a partir de 8 s. Estado de `estimate.nav`: a 8,1 s o GNSS passa a `suspect`; a 8,4 s o radar também e `ambiguous` fica verdadeiro; a 10,4 s o modo passa a `untrusted`. Daí até ao toque (22 s) os dois grupos ficam `suspect`, com os CUSUM saturados em 24, e **nenhum é excluído nem isolado**. Um grupo `suspect` continua a ser usado pelo estimador (`usable()`): o recetor errado continua a ser assimilado durante o voo todo e o veículo é declarado `untrusted` mas aterra com R1 falhado.

## Leitura segundo a regra de decisão

Os U sem isolamento errado (58) são execuções não isoladas que continuam a assimilar o recetor errado, com falha vertical R1; não são isolamentos corretos tardios nem falhas laterais. A regra fixada pelo orquestrador manda **prosseguir** com abstenção mais rejeição por NIS, como pré-registado. Limites: 20 sementes, um só magnitude, uma execução com traço; a ligação causal entre assimilação e R1 é consistente com o traço e com B (que rejeita por NIS e só falha R5), não demonstrada por ablação.

## B+ sem paridade (passo 2 da estratégia)

**Não existe e não se produz com este código.** O isolamento por paridade está ligado ao braço B+ (`if self.arm == Arm::BPlus { self.isolate(); }`) sem bandeira de desativação; fazê-lo exigiria alterar o código, fora do âmbito deste diagnóstico. O contrafactual «sem paridade 8, 0 e 0» (`m10-implementation.md`, desvio 1) continua sem ficheiro de evidência. Nesta amostra, os 58 U não isolados de B+ aproximam o que B+ faria sem paridade nas execuções em que a paridade nada faz, mas não substituem a evidência pedida. Fica declarado como não cumprido.

# Avaliação de motores: Godot 4 com Rust e Bevy

Dois protótipos pequenos, cada um a mostrar em 3D o mesmo traço gravado de uma execução real e verificada por reprodução (`delayed_after_fallback`, execução `936767ab546b1cd8`, 14 ticks). Os protótipos estão em `spikes/` e só mostram posições gravadas; nenhum simula.

Máquina: Windows 11, AMD Radeon RX 7700 XT, Rust 1.99.0; compilações com `-j 2` por falta de memória livre (cerca de 5 GB durante as medições). Os números são de uma só máquina e de uma só tentativa.

## Medições

| Medida | Godot 4.7.2 (GDScript) | Godot 4.7.2 + Rust (GDExtension, `godot` 0.5.5) | Bevy 0.16.1 |
| --- | --- | --- | --- |
| Instalação | zip oficial de 86 MB, SHA512 verificado; executável do editor de 173 MB; sem compilação | crate `godot` com `api-4-7` | crates de crates.io |
| Compilação limpa | não se aplica | 102 s (inclui descarga) | 650 s (inclui descarga) |
| Artefacto | não se aplica | DLL de 3,9 MB | executável de 59 MB |
| Pasta de compilação | não se aplica | 709 MB | 2,0 GB |
| Recompilação após alterar o protótipo | não se aplica | não medida | 11 s |
| Importação do projeto | 8,6 s | `--headless --import` terminou com falha de segmentação; a execução seguinte funcionou | não se aplica |
| Do arranque ao primeiro frame | `_ready` em 5 a 7 ms após o carregamento do motor; 4,6 s de relógio no total, com janela | não medido | 0,56 a 0,70 s |
| Fidelidade ao traço | 14 de 14 posições desenhadas iguais às gravadas, ao milímetro; imagem de cada tick verificada | 14 de 14 posições lidas em Rust iguais às lidas em GDScript; leitura em 175 µs numa execução e 5017 µs noutra (duas amostras, não é uma medição de desempenho) | 14 de 14 transformações iguais às gravadas; **imagem sem os objetos 3D** (ver abaixo) |
| Backends gráficos | OpenGL 3.3 (renderizador de compatibilidade) funcionou | igual | Vulkan: pânico em `get_physical_device_surface_capabilities`; DX12: interface desenhada, objetos 3D não; OpenGL: pânico na tradução de shaders |
| Rótulo da física 2D | visível no ecrã | não se aplica (sem ecrã) | visível, mas cortado na margem direita a 1280 px |

Notas:

- Bevy compila os pipelines de forma assíncrona; os primeiros frames saem vazios. O protótipo espera 90 frames antes da captura e, mesmo assim, em DX12 só a interface aparece. A causa não foi encontrada no tempo do marco e pode estar no código do protótipo; não é uma conclusão sobre o Bevy em geral.
- A versão do Bevy usada (0.16.1) é anterior à atual (0.20.0). Foi escolhida por ter uma API conhecida e evitar ciclos de compilação longos com pouca memória. O Bevy 0.20 não foi testado.
- Empacotamento e distribuição não foram medidos para nenhum dos dois: o Godot precisa dos modelos de exportação (outra descarga) e o Bevy produz um executável que depende dos ficheiros de recursos.

## Reverificação antes da integração

Os protótipos têm espaços de trabalho Cargo próprios; a verificação do repositório não os cobre. Antes do commit do M7 foram verificados à parte, com as pastas de compilação fora do repositório:

- `cargo fmt --check` e `cargo clippy --release --locked -- -D warnings` limpos nos dois protótipos Rust. Correções: código do Bevy formatado, literal `f32` explícito na resolução da janela (`float-literal-f32-fallback`) e campo `base` não usado retirado da classe GDExtension (`redundant_field_names` no código gerado pela macro).
- Godot: o visualizador voltou a desenhar 14 de 14 posições iguais às gravadas; a extensão Rust voltou a ler 14 posições sem diferenças.
- Bevy em DX12: 14 de 14 transformações iguais às gravadas, interface desenhada e, de novo, nenhum objeto 3D visível. A causa continua desconhecida.
- Empacotamento e o comportamento com outros controladores gráficos continuam sem medição.

## Avaliação qualitativa

| Critério | Godot 4 + Rust | Bevy |
| --- | --- | --- |
| Usabilidade para utilizadores finais | Editor visual, interface 2D e 3D madura, temas e acessibilidade de controlos nativos | Interface em código; widgets e acessibilidade menos maduros |
| Custo de desenvolvimento | Duas linguagens (GDScript para a cena, Rust para dados e verificação); ligação por GDExtension | Uma linguagem, a mesma do núcleo; compilações longas; mudanças de API frequentes entre versões |
| Fidelidade ao traço | Medida: igual ao gravado | Medida só ao nível das transformações; imagem não confirmada |
| Integração com o núcleo | A extensão Rust pode ligar diretamente à biblioteca `autonomous-systems-vv-lab` | O núcleo pode ser uma dependência direta |
| Estabilidade nesta máquina | Uma falha na importação com a extensão | Falhas em dois backends e objetos 3D invisíveis no terceiro |

## Recomendação

Recomendação provisória: **Godot 4 com a lógica de dados e de verificação em Rust (GDExtension)** para o visualizador de ambiente de trabalho do M8. Foi a única opção que, nesta máquina, mostrou o traço gravado com fidelidade verificada ao milímetro e um rótulo de física legível, e a ligação a Rust funcionou à primeira.

Não fixar ainda a arquitetura. Antes da decisão:

1. Medir o empacotamento de ambos (modelos de exportação do Godot; executável e recursos do Bevy).
2. Repetir o protótipo Bevy com a versão 0.20 e encontrar a causa dos objetos invisíveis em DX12.
3. Reproduzir a falha de `--headless --import` do Godot com a extensão e verificar se afeta a exportação.
4. Medir a acessibilidade dos controlos no visualizador escolhido (teclado e leitor de ecrã).

Até lá, o Mission Control continua no navegador local, que já funciona e consome o mesmo contrato de adaptador.

## Reproduzir

```sh
python spikes/export_trace.py
# Godot 4.7.2 (descarga separada; <godot> é o executável do editor):
<godot> --path spikes/godot-trace-viewer -- <caminho absoluto>/spikes/out/trace.json
cargo build --release --manifest-path spikes/godot-rust-ext/Cargo.toml   # copiar trace_ext.dll para spikes/godot-rust-ext/demo/bin/
<godot> --headless --path spikes/godot-rust-ext/demo -- <caminho absoluto>/spikes/out/trace.json
# Bevy:
cargo build --release --manifest-path spikes/bevy-trace-viewer/Cargo.toml
WGPU_BACKEND=dx12 bevy_trace_viewer <trace.json> <captura.png>
```

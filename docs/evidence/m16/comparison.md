# Comparação antes e depois: vista geoespacial do M16

Antes: Studio 0.16.0 instalado. Depois: Studio 0.16.1 instalado. Mesma missão (`lying-altimeter`), mesmo ambiente, mesmo instante (fim da execução e 55 % da duração), mesma predefinição de câmara e mesmo tamanho de janela. Capturas geradas por `desktop/studio/tests/m16_compare_shots.py`.

Diferenças que a comparação não controla:

- A origem de Cabo Canaveral passou 30 m para sul, para o centro do pavimento circular medido na imagem de 0,5 m; a de Santa Maria passou cerca de 430 m, de floresta para uma pastagem. O mesmo enquadramento mostra por isso chão diferente.
- A câmara «Na plataforma» não existia antes; não tem par.
- As capturas são de 1440x900, 1280x720 e 1024x640; as do responsável eram de cerca de 1447x908.
- A fração da altura do ecrã ocupada pelo andar só é medida pela versão nova.

| Ambiente | Câmara | Instante | Janela | Antes | Depois | Andar no ecrã (depois) |
| --- | --- | --- | --- | --- | --- | --- |
| Santa Maria, Açores | Seguir | fim | 1440x900 | ![antes](before/santa-maria-azores-follow-end-1440x900.jpg) | ![depois](after/santa-maria-azores-follow-end-1440x900.jpg) | 0.41 |
| Santa Maria, Açores | Seguir | fim | 1280x720 | ![antes](before/santa-maria-azores-follow-end-1280x720.jpg) | ![depois](after/santa-maria-azores-follow-end-1280x720.jpg) | 0.41 |
| Santa Maria, Açores | Seguir | fim | 1024x640 | ![antes](before/santa-maria-azores-follow-end-1024x640.jpg) | ![depois](after/santa-maria-azores-follow-end-1024x640.jpg) | 0.41 |
| Santa Maria, Açores | Do solo | fim | 1440x900 | ![antes](before/santa-maria-azores-pad-end-1440x900.jpg) | ![depois](after/santa-maria-azores-pad-end-1440x900.jpg) | 0.42 |
| Santa Maria, Açores | Na plataforma | fim | 1440x900 | sem par | ![depois](after/santa-maria-azores-closeup-end-1440x900.jpg) | 0.55 |
| Santa Maria, Açores | Descida completa | fim | 1440x900 | ![antes](before/santa-maria-azores-wide-end-1440x900.jpg) | ![depois](after/santa-maria-azores-wide-end-1440x900.jpg) | 0.01 |
| Santa Maria, Açores | Vista de cima | fim | 1440x900 | ![antes](before/santa-maria-azores-overhead-end-1440x900.jpg) | ![depois](after/santa-maria-azores-overhead-end-1440x900.jpg) | 0.00 |
| Santa Maria, Açores | Seguir | 55 % | 1440x900 | ![antes](before/santa-maria-azores-follow-mid-1440x900.jpg) | ![depois](after/santa-maria-azores-follow-mid-1440x900.jpg) | 0.41 |
| Santa Maria, Açores | Do solo | 55 % | 1440x900 | ![antes](before/santa-maria-azores-pad-mid-1440x900.jpg) | ![depois](after/santa-maria-azores-pad-mid-1440x900.jpg) | 0.21 |
| Santa Maria, Açores | Na plataforma | 55 % | 1440x900 | sem par | ![depois](after/santa-maria-azores-closeup-mid-1440x900.jpg) | fora do enquadramento |
| Santa Maria, Açores | Descida completa | 55 % | 1440x900 | ![antes](before/santa-maria-azores-wide-mid-1440x900.jpg) | ![depois](after/santa-maria-azores-wide-mid-1440x900.jpg) | 0.01 |
| Santa Maria, Açores | Vista de cima | 55 % | 1440x900 | ![antes](before/santa-maria-azores-overhead-mid-1440x900.jpg) | ![depois](after/santa-maria-azores-overhead-mid-1440x900.jpg) | 0.00 |
| Cabo Canaveral | Seguir | fim | 1440x900 | ![antes](before/cape-canaveral-follow-end-1440x900.jpg) | ![depois](after/cape-canaveral-follow-end-1440x900.jpg) | 0.41 |
| Cabo Canaveral | Seguir | fim | 1280x720 | ![antes](before/cape-canaveral-follow-end-1280x720.jpg) | ![depois](after/cape-canaveral-follow-end-1280x720.jpg) | 0.41 |
| Cabo Canaveral | Seguir | fim | 1024x640 | ![antes](before/cape-canaveral-follow-end-1024x640.jpg) | ![depois](after/cape-canaveral-follow-end-1024x640.jpg) | 0.41 |
| Cabo Canaveral | Do solo | fim | 1440x900 | ![antes](before/cape-canaveral-pad-end-1440x900.jpg) | ![depois](after/cape-canaveral-pad-end-1440x900.jpg) | 0.42 |
| Cabo Canaveral | Na plataforma | fim | 1440x900 | sem par | ![depois](after/cape-canaveral-closeup-end-1440x900.jpg) | 0.55 |
| Cabo Canaveral | Descida completa | fim | 1440x900 | ![antes](before/cape-canaveral-wide-end-1440x900.jpg) | ![depois](after/cape-canaveral-wide-end-1440x900.jpg) | 0.01 |
| Cabo Canaveral | Vista de cima | fim | 1440x900 | ![antes](before/cape-canaveral-overhead-end-1440x900.jpg) | ![depois](after/cape-canaveral-overhead-end-1440x900.jpg) | 0.00 |
| Cabo Canaveral | Seguir | 55 % | 1440x900 | ![antes](before/cape-canaveral-follow-mid-1440x900.jpg) | ![depois](after/cape-canaveral-follow-mid-1440x900.jpg) | 0.41 |
| Cabo Canaveral | Do solo | 55 % | 1440x900 | ![antes](before/cape-canaveral-pad-mid-1440x900.jpg) | ![depois](after/cape-canaveral-pad-mid-1440x900.jpg) | 0.21 |
| Cabo Canaveral | Na plataforma | 55 % | 1440x900 | sem par | ![depois](after/cape-canaveral-closeup-mid-1440x900.jpg) | fora do enquadramento |
| Cabo Canaveral | Descida completa | 55 % | 1440x900 | ![antes](before/cape-canaveral-wide-mid-1440x900.jpg) | ![depois](after/cape-canaveral-wide-mid-1440x900.jpg) | 0.01 |
| Cabo Canaveral | Vista de cima | 55 % | 1440x900 | ![antes](before/cape-canaveral-overhead-mid-1440x900.jpg) | ![depois](after/cape-canaveral-overhead-mid-1440x900.jpg) | 0.00 |

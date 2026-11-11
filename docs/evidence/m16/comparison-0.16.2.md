# Comparação antes e depois: vista geoespacial do M16.2

Antes: Studio 0.16.1 instalado (`after/`). Depois: Studio 0.16.2 instalado (`after-0.16.2/`). Mesma missão (`lying-altimeter`), mesmo ambiente, mesmo instante (fim da execução e 55 % da duração), mesma predefinição de câmara e mesmo tamanho de janela. Capturas geradas por `desktop/studio/tests/m16_compare_shots.py`; `after-0.16.2/shots.json` guarda a pose de cada câmara e as contagens da camada do mundo.

Diferenças que a comparação não controla:

- As regras de «Na plataforma» (agora uma teleobjetiva baixa a 165 m que acompanha o andar) e de «Do solo» (agora acima da vegetação) mudaram; o mesmo nome mostra outro ponto de vista.
- A predefinição «Auto» e o ambiente Spaceport America não tinham capturas no 0.16.1; não têm par.
- São fotografias de ecrã, não medições. A avaliação visual é do responsável.

| Ambiente | Câmara | Instante | Janela | Antes | Depois | Andar no ecrã (depois) |
| --- | --- | --- | --- | --- | --- | --- |
| Santa Maria, Açores | Seguir | fim | 1440x900 | ![antes](after/santa-maria-azores-follow-end-1440x900.jpg) | ![depois](after-0.16.2/santa-maria-azores-follow-end-1440x900.jpg) | 0.41 |
| Santa Maria, Açores | Seguir | fim | 1280x720 | ![antes](after/santa-maria-azores-follow-end-1280x720.jpg) | ![depois](after-0.16.2/santa-maria-azores-follow-end-1280x720.jpg) | 0.41 |
| Santa Maria, Açores | Seguir | fim | 1024x640 | ![antes](after/santa-maria-azores-follow-end-1024x640.jpg) | ![depois](after-0.16.2/santa-maria-azores-follow-end-1024x640.jpg) | 0.41 |
| Santa Maria, Açores | Do solo | fim | 1440x900 | ![antes](after/santa-maria-azores-pad-end-1440x900.jpg) | ![depois](after-0.16.2/santa-maria-azores-pad-end-1440x900.jpg) | 0.42 |
| Santa Maria, Açores | Na plataforma | fim | 1440x900 | ![antes](after/santa-maria-azores-closeup-end-1440x900.jpg) | ![depois](after-0.16.2/santa-maria-azores-closeup-end-1440x900.jpg) | 0.53 |
| Santa Maria, Açores | Descida completa | fim | 1440x900 | ![antes](after/santa-maria-azores-wide-end-1440x900.jpg) | ![depois](after-0.16.2/santa-maria-azores-wide-end-1440x900.jpg) | 0.01 |
| Santa Maria, Açores | Vista de cima | fim | 1440x900 | ![antes](after/santa-maria-azores-overhead-end-1440x900.jpg) | ![depois](after-0.16.2/santa-maria-azores-overhead-end-1440x900.jpg) | 0.00 |
| Santa Maria, Açores | Auto | fim | 1440x900 | sem par | ![depois](after-0.16.2/santa-maria-azores-director-end-1440x900.jpg) | 0.53 |
| Santa Maria, Açores | Seguir | 55 % | 1440x900 | ![antes](after/santa-maria-azores-follow-mid-1440x900.jpg) | ![depois](after-0.16.2/santa-maria-azores-follow-mid-1440x900.jpg) | 0.41 |
| Santa Maria, Açores | Do solo | 55 % | 1440x900 | ![antes](after/santa-maria-azores-pad-mid-1440x900.jpg) | ![depois](after-0.16.2/santa-maria-azores-pad-mid-1440x900.jpg) | 0.21 |
| Santa Maria, Açores | Na plataforma | 55 % | 1440x900 | ![antes](after/santa-maria-azores-closeup-mid-1440x900.jpg) | ![depois](after-0.16.2/santa-maria-azores-closeup-mid-1440x900.jpg) |  |
| Santa Maria, Açores | Descida completa | 55 % | 1440x900 | ![antes](after/santa-maria-azores-wide-mid-1440x900.jpg) | ![depois](after-0.16.2/santa-maria-azores-wide-mid-1440x900.jpg) | 0.01 |
| Santa Maria, Açores | Vista de cima | 55 % | 1440x900 | ![antes](after/santa-maria-azores-overhead-mid-1440x900.jpg) | ![depois](after-0.16.2/santa-maria-azores-overhead-mid-1440x900.jpg) | 0.00 |
| Santa Maria, Açores | Auto | 55 % | 1440x900 | sem par | ![depois](after-0.16.2/santa-maria-azores-director-mid-1440x900.jpg) | 0.41 |
| Cabo Canaveral, Florida | Seguir | fim | 1440x900 | ![antes](after/cape-canaveral-follow-end-1440x900.jpg) | ![depois](after-0.16.2/cape-canaveral-follow-end-1440x900.jpg) | 0.41 |
| Cabo Canaveral, Florida | Seguir | fim | 1280x720 | ![antes](after/cape-canaveral-follow-end-1280x720.jpg) | ![depois](after-0.16.2/cape-canaveral-follow-end-1280x720.jpg) | 0.41 |
| Cabo Canaveral, Florida | Seguir | fim | 1024x640 | ![antes](after/cape-canaveral-follow-end-1024x640.jpg) | ![depois](after-0.16.2/cape-canaveral-follow-end-1024x640.jpg) | 0.41 |
| Cabo Canaveral, Florida | Do solo | fim | 1440x900 | ![antes](after/cape-canaveral-pad-end-1440x900.jpg) | ![depois](after-0.16.2/cape-canaveral-pad-end-1440x900.jpg) | 0.42 |
| Cabo Canaveral, Florida | Na plataforma | fim | 1440x900 | ![antes](after/cape-canaveral-closeup-end-1440x900.jpg) | ![depois](after-0.16.2/cape-canaveral-closeup-end-1440x900.jpg) | 0.53 |
| Cabo Canaveral, Florida | Descida completa | fim | 1440x900 | ![antes](after/cape-canaveral-wide-end-1440x900.jpg) | ![depois](after-0.16.2/cape-canaveral-wide-end-1440x900.jpg) | 0.01 |
| Cabo Canaveral, Florida | Vista de cima | fim | 1440x900 | ![antes](after/cape-canaveral-overhead-end-1440x900.jpg) | ![depois](after-0.16.2/cape-canaveral-overhead-end-1440x900.jpg) | 0.00 |
| Cabo Canaveral, Florida | Auto | fim | 1440x900 | sem par | ![depois](after-0.16.2/cape-canaveral-director-end-1440x900.jpg) | 0.53 |
| Cabo Canaveral, Florida | Seguir | 55 % | 1440x900 | ![antes](after/cape-canaveral-follow-mid-1440x900.jpg) | ![depois](after-0.16.2/cape-canaveral-follow-mid-1440x900.jpg) | 0.41 |
| Cabo Canaveral, Florida | Do solo | 55 % | 1440x900 | ![antes](after/cape-canaveral-pad-mid-1440x900.jpg) | ![depois](after-0.16.2/cape-canaveral-pad-mid-1440x900.jpg) | 0.21 |
| Cabo Canaveral, Florida | Na plataforma | 55 % | 1440x900 | ![antes](after/cape-canaveral-closeup-mid-1440x900.jpg) | ![depois](after-0.16.2/cape-canaveral-closeup-mid-1440x900.jpg) |  |
| Cabo Canaveral, Florida | Descida completa | 55 % | 1440x900 | ![antes](after/cape-canaveral-wide-mid-1440x900.jpg) | ![depois](after-0.16.2/cape-canaveral-wide-mid-1440x900.jpg) | 0.01 |
| Cabo Canaveral, Florida | Vista de cima | 55 % | 1440x900 | ![antes](after/cape-canaveral-overhead-mid-1440x900.jpg) | ![depois](after-0.16.2/cape-canaveral-overhead-mid-1440x900.jpg) | 0.00 |
| Cabo Canaveral, Florida | Auto | 55 % | 1440x900 | sem par | ![depois](after-0.16.2/cape-canaveral-director-mid-1440x900.jpg) | 0.41 |
| Spaceport America, Novo México | Seguir | fim | 1440x900 | sem par | ![depois](after-0.16.2/spaceport-america-follow-end-1440x900.jpg) | 0.41 |
| Spaceport America, Novo México | Seguir | fim | 1280x720 | sem par | ![depois](after-0.16.2/spaceport-america-follow-end-1280x720.jpg) | 0.41 |
| Spaceport America, Novo México | Seguir | fim | 1024x640 | sem par | ![depois](after-0.16.2/spaceport-america-follow-end-1024x640.jpg) | 0.41 |
| Spaceport America, Novo México | Do solo | fim | 1440x900 | sem par | ![depois](after-0.16.2/spaceport-america-pad-end-1440x900.jpg) | 0.42 |
| Spaceport America, Novo México | Na plataforma | fim | 1440x900 | sem par | ![depois](after-0.16.2/spaceport-america-closeup-end-1440x900.jpg) | 0.53 |
| Spaceport America, Novo México | Descida completa | fim | 1440x900 | sem par | ![depois](after-0.16.2/spaceport-america-wide-end-1440x900.jpg) | 0.01 |
| Spaceport America, Novo México | Vista de cima | fim | 1440x900 | sem par | ![depois](after-0.16.2/spaceport-america-overhead-end-1440x900.jpg) | 0.00 |
| Spaceport America, Novo México | Auto | fim | 1440x900 | sem par | ![depois](after-0.16.2/spaceport-america-director-end-1440x900.jpg) | 0.53 |
| Spaceport America, Novo México | Seguir | 55 % | 1440x900 | sem par | ![depois](after-0.16.2/spaceport-america-follow-mid-1440x900.jpg) | 0.41 |
| Spaceport America, Novo México | Do solo | 55 % | 1440x900 | sem par | ![depois](after-0.16.2/spaceport-america-pad-mid-1440x900.jpg) | 0.21 |
| Spaceport America, Novo México | Na plataforma | 55 % | 1440x900 | sem par | ![depois](after-0.16.2/spaceport-america-closeup-mid-1440x900.jpg) |  |
| Spaceport America, Novo México | Descida completa | 55 % | 1440x900 | sem par | ![depois](after-0.16.2/spaceport-america-wide-mid-1440x900.jpg) | 0.01 |
| Spaceport America, Novo México | Vista de cima | 55 % | 1440x900 | sem par | ![depois](after-0.16.2/spaceport-america-overhead-mid-1440x900.jpg) | 0.00 |
| Spaceport America, Novo México | Auto | 55 % | 1440x900 | sem par | ![depois](after-0.16.2/spaceport-america-director-mid-1440x900.jpg) | 0.41 |

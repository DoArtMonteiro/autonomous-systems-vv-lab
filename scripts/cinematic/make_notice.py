"""Gera desktop/cinematic/assets/cc0/NOTICE-cc0.md a partir de PROVENANCE.json.

O aviso lista apenas os ativos cujos ficheiros existem em assets/cc0, para que nunca descreva
ativos que não seguem no módulo. Uso: python scripts/cinematic/make_notice.py [--check]
"""

import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ASSETS = os.path.join(REPO, "desktop", "cinematic", "assets")
CC0 = os.path.join(ASSETS, "cc0")
OUT = os.path.join(CC0, "NOTICE-cc0.md")

SOURCES = {
    "Poly Haven": "https://polyhaven.com/license",
    "ambientCG": "https://docs.ambientcg.com/license/",
}


def render(prov, assets_dir=ASSETS):
    shipped = [
        a for a in prov
        if a["files"] and all(os.path.isfile(os.path.join(assets_dir, *e["path"].split("/"))) for e in a["files"])
    ]
    dates = sorted({a["date_accessed"] for a in shipped})
    when = dates[0] if len(dates) == 1 else f"{dates[0]} a {dates[-1]}"
    lines = [
        "# Avisos de licença de ativos CC0",
        "",
        f"Este ficheiro é gerado por `scripts/cinematic/make_notice.py` a partir de `PROVENANCE.json` e lista apenas os {len(shipped)} ativos que seguem no módulo. "
        f"Todos foram obtidos em {when} e são distribuídos sob CC0 1.0 (domínio público). "
        "Não é exigida atribuição; a lista serve de registo de proveniência. "
        "Detalhes técnicos, URL de descarga e somas SHA-256 constam de `PROVENANCE.json`.",
        "",
        "| Categoria | Ativo | Fonte | Autor | Licença |",
        "|---|---|---|---|---|",
    ]
    for a in shipped:
        author = a["author"] or "não indicado pela fonte"
        lines.append(f"| {a['category']} | {a['title']} (`{a['id']}`) | {a['source']}, {a['page_url']} | {author} | CC0 1.0 |")
    used = sorted({a["source"] for a in shipped})
    lines += ["", "Fontes: " + " e ".join(f"{s} ({SOURCES[s]})" for s in used) + ".", ""]
    return "\n".join(lines)


def main(argv):
    with open(os.path.join(CC0, "PROVENANCE.json"), encoding="utf-8") as f:
        text = render(json.load(f))
    if "--check" in argv:
        with open(OUT, encoding="utf-8", newline="") as f:
            return 0 if f.read() == text else 1
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

r"""Packages an environment pack as a separately installable file and records it in the index.

    python scripts/geo/package_environment.py --env mahia-peninsula
    python scripts/geo/package_environment.py --all

For each pack it writes

    dist/environments/<id>-<pack_version>.vvenv.zip
    dist/environments/<id>-<pack_version>.vvenv.zip.sha256

and updates scripts/geo/environment-index.json (schema vv-geo-environment-index.v1) with the
size and SHA-256 of the zip. The zip holds, at its root and nothing else: environment.json, the
files the manifest names (height grids, images, world layer) and NOTICE.md, the licence notice of
that pack generated from its manifest and catalogue entry. Every file is checked against the
SHA-256 in the manifest before it is packed, so a zip never carries a pack that would not validate.

The zip is deterministic: entries in a fixed order (environment.json first, then the manifest's
files in manifest order, then NOTICE.md), a fixed timestamp (1980-01-01), fixed permissions and
DEFLATE level 9. Rebuilding from the same pack gives the same bytes and the same SHA-256.

Pack folders: the bundled packs live in desktop/environments/<id> (they ship with the Studio); the
catalogue packs are built into dist/packs/<id> by build_environment.py and build_features.py and are
not bundled nor committed. Only the index and the pipeline are in git.

The packed bytes of a pack are never modified here: the three bundled packs are packaged as they
are in the repository.
"""

import argparse
import hashlib
import io
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
CATALOGUE = os.path.join(HERE, "catalogue.json")
INDEX = os.path.join(HERE, "environment-index.json")
BUNDLED_ROOT = os.path.join(REPO, "desktop", "environments")
CATALOGUE_ROOT = os.path.join(REPO, "dist", "packs")
DIST = os.path.join(REPO, "dist", "environments")
INDEX_SCHEMA = "vv-geo-environment-index.v1"
ZIP_TIME = (1980, 1, 1, 0, 0, 0)
NOTICE = "NOTICE.md"
SCHEMAS = ("vv-geo-environment.v1", "vv-geo-environment.v2", "vv-geo-environment.v3")
# The data tiers of catalogue.json, worded for the notices (European Portuguese).
TIERS_PT = {
    "A": "ortofotografia de 1 m ou melhor, terreno lidar de 1 a 2 m na camada de pormenor e camada do mundo com alturas e vegetação medidas numa nuvem de pontos lidar",
    "B": "ortofotografia de 1 m ou melhor e terreno lidar ou de levantamento de 5 m ou melhor na camada de pormenor; camada do mundo só do OpenStreetMap, sem vegetação medida",
    "C": "ortofotografia de 1 m ou melhor; o terreno de pormenor é a superfície de base de 30 m; camada do mundo só do OpenStreetMap",
    "D": "só imagem Sentinel-2 (10 m) e superfície de base de 30 m",
}


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def read(path):
    with open(path, "rb") as f:
        return f.read()


def load_catalogue():
    with open(CATALOGUE, encoding="utf-8") as f:
        return json.load(f)


def pack_dir(env_id, cfg, root=None):
    if root:
        return os.path.join(root, env_id)
    return os.path.join(BUNDLED_ROOT if cfg.get("bundled") else CATALOGUE_ROOT, env_id)


def manifest_files(m):
    """The files the manifest names, in manifest order, with their declared size and SHA-256."""
    out = [(m["height"]["file"], m["height"]["bytes"], m["height"]["sha256"]),
           (m["image"]["file"], m["image"]["bytes"], m["image"]["sha256"])]
    for layer in m.get("layers", []):
        for k in ("height", "image"):
            out.append((layer[k]["file"], layer[k]["bytes"], layer[k]["sha256"]))
    world = m.get("world", {})
    for k in ("features", "vegetation"):
        if k in world:
            out.append((world[k]["file"], world[k]["bytes"], world[k]["sha256"]))
    return out


def notice(m, cfg):
    """The per-pack licence notice (European Portuguese, licence texts quoted as published)."""
    L = [f"# Avisos dos dados geográficos: {m['name']}", "",
         f"Pacote `{m['id']}`, versão {cfg.get('pack_version', '1')}, esquema `{m['schema']}`, "
         f"nível de dados {cfg['tier']} ({TIERS_PT[cfg['tier']]}).", "",
         "Este pacote contém dados de terceiros adaptados: reamostrados para uma grelha local este-norte-cima, "
         "com curvas de tom na imagem de pormenor e comprimidos. O ficheiro `environment.json` identifica, para cada "
         "fonte, os itens usados, a licença, a atribuição e o tratamento aplicado. Quem redistribuir este pacote, "
         "modificado ou não, fica obrigado às condições de cada fonte e deve manter este aviso e as atribuições do manifesto.", ""]
    if m.get("site_note"):
        L += ["## Local", "", m["site_note"], ""]
    L += ["## Fontes", ""]
    for s in m["sources"]:
        layer = s.get("layer", "base")
        L += [f"### {s['product']} (camada {layer})", "",
              f"- Fornecedor: {s['provider']}",
              f"- Licença: {s['licence']}",
              f"- Atribuição: {s['attribution']}"]
        if s.get("access"):
            L.append(f"- Acesso: {s['access']}")
        L.append("")
    gaps = cfg.get("licence_gaps", [])
    L += ["## Lacunas de licença e de dados", ""]
    if gaps:
        L += [f"- {g}" for g in gaps]
    else:
        L.append("- Nenhuma lacuna de licença conhecida para as fontes acima.")
    for t in cfg.get("notice_texts", []):
        # Licence texts that must travel unmodified with the data are reproduced verbatim.
        L += ["", f"## {t['title']}", "", "```text", t["text"], "```"]
    L += ["", "As formas desenhadas (paredes, telhados planos, copas e folhas) são ilustrativas; as posições, os contornos "
          "e as alturas vêm dos dados, com a origem de cada altura indicada em `features.json`. O veículo, a plataforma e a "
          "missão simulados são genéricos e não representam nenhuma instalação, operação ou entidade.", ""]
    return "\n".join(L).encode("utf-8")


def build_zip(d, m, notice_bytes):
    raw_manifest = read(os.path.join(d, "environment.json"))
    entries = [("environment.json", raw_manifest)]
    for name, size, digest in manifest_files(m):
        if "/" in name or "\\" in name or name in ("environment.json", NOTICE):
            raise SystemExit(f"{m['id']}: unexpected file name {name!r} in the manifest")
        b = read(os.path.join(d, name))
        if len(b) != size or sha256(b) != digest:
            raise SystemExit(f"{m['id']}: {name} does not match its size or SHA-256 in the manifest")
        entries.append((name, b))
    entries.append((NOTICE, notice_bytes))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, b in entries:
            zi = zipfile.ZipInfo(name, date_time=ZIP_TIME)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.create_system = 0
            zi.external_attr = 0o644 << 16
            z.writestr(zi, b, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return buf.getvalue(), [n for n, _ in entries]


# Short names of the licences a manifest source may carry, matched on the start of its licence text.
SHORT_LICENCES = [
    ("Licence for the use of the Copernicus WorldDEM-30", "Copernicus WorldDEM-30 licence"),
    ("Legal notice on the use of Copernicus Sentinel data", "Copernicus Sentinel data legal notice"),
    ("Public domain (U.S. Government work)", "U.S. public domain"),
    ("U.S. Public Domain", "U.S. public domain"),
    ("Public domain under the FSA web policy", "U.S. public domain (FSA policy)"),
    ("CC BY 4.0", "CC BY 4.0"),
    ("Creative Commons Attribution 4.0", "CC BY 4.0"),
    ("Open Data Commons Open Database License", "ODbL 1.0"),
    ("swisstopo terms of use for free geodata", "swisstopo OGD terms"),
]


def short_licence(text):
    for prefix, short in SHORT_LICENCES:
        if text.startswith(prefix):
            return short
    raise SystemExit(f"no short licence name for {text[:80]!r}: add it to SHORT_LICENCES")


def licences_summary(m):
    """One line per source product: '<credit or provider>: <licence>', in manifest order."""
    seen = []
    for s in m["sources"]:
        short = f"{s.get('credit') or s['provider'].split(',')[0]}: {short_licence(s['licence'])}"
        if short not in seen:
            seen.append(short)
    return seen


def package(env_id, cat, root=None, dist=DIST):
    cfg = cat["environments"][env_id]
    d = pack_dir(env_id, cfg, root)
    mpath = os.path.join(d, "environment.json")
    if not os.path.exists(mpath):
        raise SystemExit(f"{env_id}: no pack at {os.path.relpath(d, REPO)} (build it first)")
    with open(mpath, encoding="utf-8") as f:
        m = json.load(f)
    if m["id"] != env_id or m["schema"] not in SCHEMAS:
        raise SystemExit(f"{env_id}: manifest id or schema is wrong")
    version = str(cfg.get("pack_version", "1"))
    data, names = build_zip(d, m, notice(m, cfg))
    os.makedirs(dist, exist_ok=True)
    zname = f"{env_id}-{version}.vvenv.zip"
    with open(os.path.join(dist, zname), "wb") as f:
        f.write(data)
    digest = sha256(data)
    with open(os.path.join(dist, zname + ".sha256"), "w", encoding="ascii", newline="\n") as f:
        f.write(f"{digest}  {zname}\n")
    return {
        "id": env_id,
        "name": m["name"],
        "landscape": cfg["landscape"],
        "tier": cfg["tier"],
        "pack_version": version,
        "schema": m["schema"],
        "bundled": bool(cfg.get("bundled")),
        "file": zname,
        "bytes": len(data),
        "sha256": digest,
        "unpacked_bytes": sum(os.path.getsize(os.path.join(d, n)) for n in names if n != NOTICE),
        "files": names,
        "origin": {"lat_deg": m["origin"]["lat_deg"], "lon_deg": m["origin"]["lon_deg"]},
        "licences": licences_summary(m),
        "licence_gaps": len(cfg.get("licence_gaps", [])),
    }


def write_index(cat, entries):
    old = {}
    if os.path.exists(INDEX):
        with open(INDEX, encoding="utf-8") as f:
            old = {e["id"]: e for e in json.load(f)["environments"]}
    old.update({e["id"]: e for e in entries})
    order = [k for k in cat["environments"] if k in old]
    idx = {
        "schema": INDEX_SCHEMA,
        "note": "Separately installable environment packs. Each file is a zip whose root holds environment.json, the files it names and NOTICE.md; the .sha256 sidecar and the sha256 here are of the zip. Built by scripts/geo/package_environment.py from the packs described in scripts/geo/catalogue.json.",
        "tiers": cat["tiers"],
        "environments": [old[k] for k in order],
    }
    with open(INDEX, "w", encoding="utf-8", newline="\n") as f:
        json.dump(idx, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main():
    cat = load_catalogue()
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--env", choices=sorted(cat["environments"]))
    g.add_argument("--all", action="store_true")
    ap.add_argument("--root", default=None, help="parent folder of the pack (default: desktop/environments for bundled packs, dist/packs otherwise)")
    a = ap.parse_args()
    ids = list(cat["environments"]) if a.all else [a.env]
    entries = [package(i, cat, a.root) for i in ids]
    write_index(cat, entries)
    for e in entries:
        print(f"{e['file']}  {e['bytes']} bytes  sha256 {e['sha256']}", file=sys.stderr)


if __name__ == "__main__":
    main()

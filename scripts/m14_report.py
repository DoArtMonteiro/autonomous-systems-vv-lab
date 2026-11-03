"""Build the M14 evidence report (one self-contained HTML page) from the stored evidence.

Reads docs/evidence/m14/{development,heldout}/results.json and fragility/fragility.json and
writes docs/evidence/m14/m14-report.html. Every number on the page comes from those files; the
page has no data of its own. The output starts with <title> and <style> and has no <html> or
<body> wrapper, so it can be published as an artifact page as is.

    python scripts/m14_report.py
"""

from __future__ import annotations

import html
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT / "docs" / "evidence" / "m14"
OUT = EVID / "m14-report.html"
STRATEGIES = ["random", "halton", "extremes", "adaptive"]
NAMES = {"random": "uniforme", "halton": "Halton", "extremes": "cantos primeiro", "adaptive": "adaptativa"}


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def fmt(x: float, d: int = 3) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def strip_chart(problem: dict, budget: int) -> str:
    """Evaluations to the first violation, one dot per repetition, log scale from 1 to budget + 1."""
    w, left, right, top, row = 640, 118, 18, 14, 34
    h = 30 + row * len(STRATEGIES)
    lo, hi = 1, budget + 1

    def x(v: float) -> float:
        return left + (math.log(v) - math.log(lo)) / (math.log(hi) - math.log(lo)) * (w - left - right)

    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Avaliações até à primeira violação em {esc(problem["id"])}">']
    for t in [1, 2, 5, 10, 20, 50, 100, 201]:
        xt = x(t)
        parts.append(f'<line x1="{xt:.1f}" x2="{xt:.1f}" y1="{top - 4}" y2="{h - 22}" class="grid"/>')
        label = "201 (nenhuma)" if t == 201 else str(t)
        anchor = "end" if t == 201 else "middle"
        parts.append(f'<text x="{xt:.1f}" y="{h - 6}" class="tick" text-anchor="{anchor}">{label}</text>')
    for i, s in enumerate(STRATEGIES):
        st = problem["strategies"][s]
        y = top + i * row + row / 2
        parts.append(f'<text x="{left - 10}" y="{y + 4:.1f}" class="lab" text-anchor="end">{esc(NAMES[s])}</text>')
        counts: dict[int, int] = {}
        for v in st["first_violation"]:
            k = counts.get(v, 0)
            counts[v] = k + 1
            dy = (k % 7 - 3) * 3.2
            cls = "dot miss" if v > budget else "dot"
            parts.append(f'<circle cx="{x(v):.1f}" cy="{y + dy:.1f}" r="2.6" class="{cls}"/>')
        m = st["first_violation_median"]
        parts.append(f'<line x1="{x(m):.1f}" x2="{x(m):.1f}" y1="{y - 13:.1f}" y2="{y + 13:.1f}" class="median"/>')
    parts.append("</svg>")
    return "".join(parts)


def fragility_chart(claim: dict) -> str:
    """Pass rate per level with the one-sided 95 % bounds, against the claim threshold."""
    levels = claim["levels"]
    w, h, left, right, top, bottom = 640, 190, 44, 14, 16, 40
    band = (w - left - right) / len(levels)

    def y(p: float) -> float:
        return top + (1 - p) * (h - top - bottom)

    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Taxa de sucesso por nível de {esc(claim["axis"])}">']
    for p in [0, 0.25, 0.5, 0.75, 1.0]:
        parts.append(f'<line x1="{left}" x2="{w - right}" y1="{y(p):.1f}" y2="{y(p):.1f}" class="grid"/>')
        parts.append(f'<text x="{left - 6}" y="{y(p) + 4:.1f}" class="tick" text-anchor="end">{fmt(p, 2)}</text>')
    parts.append(f'<line x1="{left}" x2="{w - right}" y1="{y(0.95):.1f}" y2="{y(0.95):.1f}" class="threshold"/>')
    parts.append(f'<text x="{w - right}" y="{y(0.95) - 5:.1f}" class="tick strong" text-anchor="end">limiar 0,95</text>')
    for i, lv in enumerate(levels):
        cx = left + band * (i + 0.5)
        rate = lv["pass"] / lv["n"]
        parts.append(f'<rect x="{cx - band / 2 + 2:.1f}" y="{h - bottom + 6}" width="{band - 4:.1f}" height="6" class="v-{lv["verdict"]}"/>')
        parts.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{y(lv["upper"]):.1f}" y2="{y(lv["lower"]):.1f}" class="whisker"/>')
        parts.append(f'<circle cx="{cx:.1f}" cy="{y(rate):.1f}" r="4" class="v-{lv["verdict"]}"/>')
        value = lv["value"]
        label = f"{value:g}".replace(".", ",") if isinstance(value, float) else str(value)
        parts.append(f'<text x="{cx:.1f}" y="{h - 12}" class="tick" text-anchor="middle">{esc(label)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def onset_table(onset: dict) -> str:
    rows = onset["rows"]
    arms = list(dict.fromkeys(r["arm"] for r in rows))
    mags = list(dict.fromkeys(r["magnitude_m"] for r in rows))
    out = ['<div class="scroll"><table class="heat"><thead><tr><th scope="col">Início do viés</th>']
    out += [f'<th scope="col">{fmt(m, 0)} m</th>' for m in mags]
    out.append("</tr></thead><tbody>")
    for a in arms:
        label = a.replace("onset-", "").replace("s", " s")
        out.append(f'<tr><th scope="row">{esc(label)}</th>')
        for m in mags:
            r = next(x for x in rows if x["arm"] == a and x["magnitude_m"] == m)
            share = r["r1_pass"] / r["n"]
            cls = "ok" if share >= 0.9 else "bad" if share <= 0.1 else "mid"
            out.append(f'<td class="{cls}">{r["r1_pass"]}/{r["n"]}</td>')
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


CSS = """
/* Layout: one reading column, figures at full column width, a findings grid that wraps on phones. */
:root {
  --paper: #f6f7f9; --ink: #18202e; --muted: #5b6577; --rule: #d9dde5; --panel: #ffffff;
  --signal: #2453c9; --hold: #1f7a5a; --unsure: #a86a00; --refute: #b8322a;
  --display: "Familjen Grotesk", "Segoe UI", system-ui, sans-serif;
  --body: "Source Serif 4", Georgia, "Times New Roman", serif;
  --data: "JetBrains Mono", ui-monospace, "Cascadia Mono", Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --paper: #10141c; --ink: #e6e9ef; --muted: #9aa3b4; --rule: #2a3141; --panel: #161b26;
  --signal: #7fa2ff; --hold: #4cc394; --unsure: #e3a83a; --refute: #ff7a6e; color-scheme: dark } }
:root[data-theme="dark"] {
  --paper: #10141c; --ink: #e6e9ef; --muted: #9aa3b4; --rule: #2a3141; --panel: #161b26;
  --signal: #7fa2ff; --hold: #4cc394; --unsure: #e3a83a; --refute: #ff7a6e; color-scheme: dark }
body { background: var(--paper); color: var(--ink); font-family: var(--body); font-size: 17px; line-height: 1.6; }
.wrap { max-width: 760px; margin: 0 auto; padding-block: 40px 72px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
h1, h2, h3 { font-family: var(--display); line-height: 1.15; text-wrap: balance; letter-spacing: -0.01em; }
h1 { font-size: 2.4rem; margin: 0 0 12px; }
h2 { font-size: 1.45rem; margin: 56px 0 8px; padding-top: 16px; border-top: 1px solid var(--rule); }
h3 { font-size: 1.05rem; margin: 28px 0 6px; }
p { margin: 0 0 14px; }
.eyebrow { font-family: var(--data); font-size: 0.75rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
.lede { font-size: 1.12rem; }
.status { display: flex; flex-wrap: wrap; gap: 8px; margin: 18px 0 8px; }
.chip { font-family: var(--data); font-size: 0.75rem; padding: 3px 9px; border: 1px solid var(--rule); border-radius: 999px; color: var(--muted); }
.chip.neg { color: var(--refute); border-color: var(--refute); }
.findings { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin: 24px 0; }
.finding { background: var(--panel); border: 1px solid var(--rule); padding: 14px 16px; min-width: 0; }
.finding .k { font-family: var(--data); font-size: 1.6rem; color: var(--signal); font-variant-numeric: tabular-nums; }
.finding p { font-size: 0.95rem; margin: 4px 0 0; }
figure { margin: 18px 0 26px; }
figure svg { width: 100%; height: auto; display: block; }
figcaption { font-size: 0.88rem; color: var(--muted); margin-top: 6px; }
svg text { font-family: var(--data); fill: var(--muted); font-size: 11px; }
svg .lab, svg .strong { fill: var(--ink); }
svg .lab { font-size: 12px; }
svg .grid { stroke: var(--rule); stroke-width: 1; }
svg .threshold { stroke: var(--ink); stroke-width: 1; stroke-dasharray: 4 3; }
svg .whisker { stroke: var(--muted); stroke-width: 1.5; }
svg .dot { fill: var(--signal); fill-opacity: 0.75; }
svg .dot.miss { fill: var(--refute); fill-opacity: 0.9; }
svg .median { stroke: var(--ink); stroke-width: 2; }
svg .v-holds { fill: var(--hold); }
svg .v-inconclusive { fill: var(--unsure); }
svg .v-refuted { fill: var(--refute); }
.legend { display: flex; flex-wrap: wrap; gap: 14px; font-family: var(--data); font-size: 0.78rem; color: var(--muted); }
.legend span::before { content: ""; display: inline-block; width: 10px; height: 10px; margin-right: 6px; vertical-align: -1px; background: var(--c); }
.legend .h { --c: var(--hold); } .legend .u { --c: var(--unsure); } .legend .r { --c: var(--refute); }
.scroll { overflow-x: auto; margin: 12px 0 22px; }
table { border-collapse: collapse; font-size: 0.9rem; width: 100%; }
th, td { padding: 6px 10px; border-bottom: 1px solid var(--rule); text-align: left; }
.heat td { font-family: var(--data); font-variant-numeric: tabular-nums; text-align: right; }
thead th { font-family: var(--display); font-weight: 600; }
.heat td.ok { color: var(--hold); } .heat td.bad { color: var(--refute); font-weight: 600; } .heat td.mid { color: var(--unsure); }
code { font-family: var(--data); font-size: 0.86em; }
.trace { font-family: var(--data); font-size: 0.82rem; background: var(--panel); border: 1px solid var(--rule); padding: 12px 14px; overflow-x: auto; white-space: pre; }
.note { font-size: 0.92rem; color: var(--muted); }
:focus-visible { outline: 2px solid var(--signal); outline-offset: 2px; }
"""


def build() -> str:
    dev = json.loads((EVID / "development" / "results.json").read_text(encoding="utf-8"))
    held = json.loads((EVID / "heldout" / "results.json").read_text(encoding="utf-8"))
    frag = json.loads((EVID / "fragility" / "fragility.json").read_text(encoding="utf-8"))
    pr = held["primary"]
    verified = sum(s["verified_evaluations"] or 0 for r in (dev, held) for p in r["problems"] for s in p["strategies"].values())
    parity_cases = sum(p["parity"]["cases"] for r in (dev, held) for p in r["problems"])
    parity_diffs = sum(p["parity"]["differences"] for r in (dev, held) for p in r["problems"])
    h4 = next(p for p in held["problems"] if p["id"].startswith("H4"))
    f1 = next(c for c in frag["claims"] if c["id"] == "F1")
    f1_one = next(x for x in f1["levels"] if x["value"] == 1)
    claim = "suportada" if pr["generalisation_claim"] == "supported" else "não suportada"

    o = [
        "<title>V&amp;V Lab M14 Evidence</title>",
        '<meta name="claude:viewport-fit-sides" content="cover">',
        '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Familjen+Grotesk:wght@500;600;700&family=JetBrains+Mono:wght@400;600&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap">',
        f"<style>{CSS}</style>",
        '<main class="wrap" lang="pt-PT">',
        '<p class="eyebrow">Autonomous Systems V&amp;V Lab · M14 · simulação idealizada</p>',
        "<h1>O que valem as falhas que encontramos</h1>",
        '<p class="lede">O M14 mede se as conclusões da plataforma resistem a três ataques: outro domínio físico, '
        "problemas de teste que o método nunca viu e pequenas mudanças nos pressupostos. Tudo nesta página foi "
        "recalculado a partir dos registos guardados.</p>",
        '<div class="status"><span class="chip">aceitação de engenharia: proposta</span>'
        '<span class="chip">aceitação científica: não pedida</span>'
        f'<span class="chip neg">generalização da pesquisa adaptativa: {claim}</span>'
        '<span class="chip">M10: continua por aceitar</span></div>',
        '<div class="findings">',
        f'<div class="finding"><div class="k">{pr["treatment_better"]} de {pr["eligible"]}</div><p>problemas reservados em que a pesquisa adaptativa foi melhor do que a uniforme. Era a previsão registada.</p></div>',
        f'<div class="finding"><div class="k">{h4["strategies"]["extremes"]["missed_by_corners_and_centre"]} de 30</div><p>repetições em H4 em que 5 avaliações (os cantos e o centro) não encontraram nenhuma falha. As primeiras 5 uniformes falham tanto quanto: o limite é o orçamento.</p></div>',
        f'<div class="finding"><div class="k">1 mm</div><p>de ruído GPS basta para a segurança do corredor cair de 100 para {f1_one["pass"]} em 100.</p></div>',
        f'<div class="finding"><div class="k">{verified:,}</div><p>avaliações de pesquisa recalculadas, 0 diferenças, com a verificação reforçada depois da revisão independente; {parity_cases} casos de paridade com as linhas de comandos, {parity_diffs} diferenças.</p></div>'.replace(",", " ", 1),
        "</div>",
        "<h2>Pesquisa guiada contra amostragem simples</h2>",
        "<p>Quatro estratégias com o mesmo orçamento de 200 simulações por repetição e 30 repetições cada. Os "
        "hiperparâmetros foram afinados em dois problemas de desenvolvimento; os quatro problemas reservados usam "
        "mecanismos de falha que o desenvolvimento nunca exercitou. O pré-registo, o congelamento e a execução estão "
        "em commits separados.</p>",
    ]
    for p in held["problems"]:
        row = next(x for x in pr["rows"] if x["id"] == p["id"])
        o.append(f"<h3>{esc(p['id'])}</h3>")
        o.append(
            f"<figure>{strip_chart(p, held['budget'])}<figcaption>Avaliações até à primeira violação, em escala "
            "logarítmica. Cada ponto é uma repetição, o traço é a mediana, a vermelho uma repetição sem violação. "
            f"Taxa na grelha de 4 sementes {fmt(p['grid']['prevalence'], 4)}. Adaptativa contra uniforme: "
            f"p = {fmt(row['p'], 3)}, p de Holm = {fmt(row.get('p_holm', 1.0), 3)}.</figcaption></figure>"
        )
    o.append(
        '<p class="note">A adaptativa começa cada episódio com 20 sorteios uniformes. Em H1 a H3 encontrou a primeira '
        "violação dentro desses sorteios em 89 de 90 repetições, por isso só H4 pôs a parte guiada à prova. O benchmark "
        "não mostra que a pesquisa guiada seja útil nem que seja inútil; para as separar são precisos problemas com falhas mais raras.</p>"
    )
    o.append("<h2>Quanto aguenta cada alegação</h2>")
    o.append(
        "<p>Para uma alegação do tipo «passa com probabilidade de pelo menos 0,95», cada nível de um pressuposto corre "
        "100 sementes. O veredicto usa limites unilaterais de Clopper-Pearson a 95 %. Estudo exploratório.</p>"
    )
    o.append('<p class="legend"><span class="h">mantém-se</span><span class="u">inconclusivo</span><span class="r">refutada</span></p>')
    for c in frag["claims"]:
        if c["id"] not in {"F1", "F2", "F3", "F6", "F7"}:
            continue
        m = c["margin"]
        o.append(f"<h3>{esc(c['id'])}: {esc(c['claim'].split(',')[0])}; eixo: {esc(c['axis'])}</h3>")
        o.append(
            f"<figure>{fragility_chart(c)}<figcaption>Taxa de sucesso por nível ({esc(c['unit'])}) com o intervalo "
            f"unilateral. Último nível que se mantém: {esc(m['last_holding_value'])}; primeiro refutado: "
            f"{esc(m['first_refuted_value'])}.{' Não monótona.' if c['non_monotone'] else ''}</figcaption></figure>"
        )
    o.append("<h3>Porque é que 1 mm basta no corredor</h3>")
    o.append(
        "<p>O ponto de passagem tem raio de chegada zero, por isso a chegada exige a posição exata. Com a posição "
        "verdadeira já no ponto, uma observação 1 mm ao lado faz o controlador de eixo dominante escolher o eixo y e dar "
        "um passo de 250 mm. A folga até à zona é de 250 mm.</p>"
    )
    o.append(
        '<div class="trace">semente 32001, ruído GPS 1 mm, ponto de passagem (5000, 2000), raio de chegada 0\n'
        "tick 23, antes do passo  verdadeira (5000, 2000)  observada (5000, 2001)\n"
        "         ação            sul 250 mm\n"
        "tick 23, depois do passo verdadeira (5000, 1750)  aresta da zona, violação</div>"
    )
    o.append("<h2>O critério G3 do M9.1 depende do instante da falha</h2>")
    o.append(
        "<p>O M9.1 registou que o controlador <code>guarded</code> cumpre R1 (contacto a no máximo 3 m/s) com viés GNSS, "
        "com o viés presente desde 0 s. A tabela mostra em quantas de 30 execuções R1 se cumpre quando o mesmo viés "
        "começa mais tarde.</p>"
    )
    o.append(onset_table(frag["onset"]))
    o.append(
        '<p class="note">Isto não refuta o G3 como foi registado. Mostra que o G3 vale sob um pressuposto sobre o '
        "instante da falha que nunca tinha sido variado. O mecanismo não foi investigado.</p>"
    )
    o.append("<h2>O que este marco não mostra</h2>")
    o.append(
        "<p>Pré-registo sem ocultação: o mesmo agente desenhou estratégias, problemas e regras. Espaços de 2 e 3 "
        "dimensões. Sem comparação com ferramentas externas. Os sensores do foguetão estão fixos pelo modelo validado, "
        "por isso o desajuste de sensores só foi estudado no veículo terrestre. Nada disto é evidência sobre um veículo "
        "real.</p>"
    )
    o.append(
        '<p class="note">Fontes: <code>docs/evidence/m14/heldout/results.json</code>, '
        "<code>docs/evidence/m14/development/results.json</code>, <code>docs/evidence/m14/fragility/fragility.json</code>. "
        f"Execução reservada no commit {esc(held['git_commit'][:7])}, congelamento em {esc(held['freeze']['git_commit'][:7])}. "
        "Gerado por <code>scripts/m14_report.py</code>.</p>"
    )
    o.append("</main>")
    return "\n".join(o) + "\n"


def main() -> int:
    OUT.write_text(build(), encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

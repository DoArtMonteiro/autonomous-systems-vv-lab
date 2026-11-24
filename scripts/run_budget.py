"""Orçamento de execuções de uma campanha pré-registada, aplicado antes de cada execução.

Uma campanha declara o seu limite num manifesto `budgets/<campaign_id>.json` (registado em commit e limpo).
Antes de lançar qualquer execução, o script reserva `n` execuções com `reserve` (ou usa
`run_budgeted`, que reserva e só depois chama a função de lançamento injetada). `n` é o tamanho da
matriz planeada, nunca um número escrito à mão. As reservas ficam num registo JSONL só de
acréscimo, sob um bloqueio exclusivo entre processos, em `<git-common-dir>/vvlab-budget/`, partilhado
por todas as worktrees e fora de qualquer pasta de execuções. Não há reembolsos: uma execução
falhada, descartada ou repetida conta como qualquer outra.

O registo e o instante da reserva nunca entram em artefactos com hash nem em identificadores de
execução. `recount` e `guard_report` contam as execuções nos artefactos e recusam o relatório se
a contagem exceder o limite ou divergir do registo (controlo detetivo).

Não há opção de linha de comandos nem variável de ambiente que mude a localização do registo; só os
testes a indicam, por argumento de função. Ver `docs/run-budget.md`.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence

ROOT = Path(__file__).resolve().parents[1]

MANIFEST_SCHEMA = "vvlab-run-budget/1"
LEDGER_SCHEMA = "vvlab-run-ledger/1"
MANIFEST_DIR = "budgets"
LEDGER_DIRNAME = "vvlab-budget"
SEEDS_SOURCE = "exec/src/seeds.rs"
GENESIS = "0" * 64
LOCK_TIMEOUT_S = 60.0
DEFAULT_MARKER = "verification.json"

# Blocos que nenhuma campanha orçamentada pode usar, além dos de `exec/src/seeds.rs`.
EXTRA_PROTECTED: tuple[tuple[int, int, str], ...] = (
    (44_000, 44_999, "reserva M13 para uma confirmação futura pré-registada"),
    (50_000, 59_999, "divisão reservada do M14, já gasta"),
    (81_000, 81_999, "bloco candidato do G3"),
)

_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")
_PROTECTED_RS = re.compile(r"start:\s*([0-9_]+)\s*,\s*end:\s*([0-9_]+)")
_MANIFEST_KEYS = {"schema", "campaign_id", "max_runs", "allowed_seeds", "preregistration", "created", "amendments"}
_AMENDMENT_KEYS = {"max_runs", "reason", "date"}


class BudgetError(Exception):
    """Recusa do orçamento: nada foi reservado nem lançado."""


class BudgetExceeded(BudgetError):
    """A reserva ultrapassaria o limite acumulado da campanha."""


@dataclass(frozen=True)
class Manifest:
    campaign_id: str
    max_runs: int
    allowed_seeds: tuple[tuple[int, int], ...]
    preregistration_path: str
    preregistration_commit: str
    created: str
    amendments: tuple[dict[str, Any], ...]
    sha256: str
    head: str


@dataclass(frozen=True)
class Reservation:
    campaign_id: str
    runs: int
    total_before: int
    total_after: int
    max_runs: int
    planned: tuple[Any, ...]


@dataclass(frozen=True)
class Outcome:
    item: Any
    result: Any
    error: BaseException | None


@dataclass(frozen=True)
class Recount:
    campaign_id: str
    runs: int
    ledger_total: int
    max_runs: int
    declared_unrecorded: int


def _git(repo: Path, *args: str) -> bytes:
    try:
        done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BudgetError(f"git indisponível: {error}") from error
    if done.returncode != 0:
        raise BudgetError(f"git {' '.join(args)} falhou: {done.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return done.stdout


def default_ledger_dir(repo: Path = ROOT) -> Path:
    """`<git-common-dir>/vvlab-budget`: o mesmo para todas as worktrees do repositório."""
    out = _git(repo, "rev-parse", "--git-common-dir").decode("utf-8").strip()
    common = Path(out)
    if not common.is_absolute():
        common = Path(repo) / common
    return common.resolve() / LEDGER_DIRNAME


def _check_id(campaign_id: str) -> None:
    if not isinstance(campaign_id, str) or not _ID.match(campaign_id):
        raise BudgetError(f"identificador de campanha inválido: {campaign_id!r}")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def load_manifest(campaign_id: str, repo: Path = ROOT) -> Manifest:
    """Lê o manifesto; recusa se não for byte a byte igual ao blob em HEAD."""
    _check_id(campaign_id)
    repo = Path(repo)
    rel = f"{MANIFEST_DIR}/{campaign_id}.json"
    try:
        blob = _git(repo, "cat-file", "blob", f"HEAD:{rel}")
    except BudgetError as error:
        raise BudgetError(f"o manifesto {rel} não está registado em HEAD: {error}") from error
    path = repo / rel
    try:
        disk = path.read_bytes()
    except OSError as error:
        raise BudgetError(f"o manifesto {rel} não pode ser lido: {error}") from error
    if disk != blob:
        raise BudgetError(f"o manifesto {rel} difere do blob em HEAD (alteração por registar em commit)")
    head = _git(repo, "rev-parse", "HEAD").decode("utf-8").strip()
    try:
        data = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BudgetError(f"o manifesto {rel} não é JSON válido: {error}") from error
    return _validate_manifest(data, campaign_id, rel, hashlib.sha256(blob).hexdigest(), head)


def _validate_manifest(data: Any, campaign_id: str, rel: str, sha: str, head: str) -> Manifest:
    def bad(message: str) -> BudgetError:
        return BudgetError(f"manifesto {rel}: {message}")

    if not isinstance(data, dict):
        raise bad("o topo tem de ser um objeto")
    extra = set(data) - _MANIFEST_KEYS
    if extra:
        raise bad(f"campos desconhecidos {sorted(extra)}")
    if data.get("schema") != MANIFEST_SCHEMA:
        raise bad(f"schema tem de ser {MANIFEST_SCHEMA}")
    if data.get("campaign_id") != campaign_id:
        raise bad("campaign_id não coincide com o nome do ficheiro")
    max_runs = data.get("max_runs")
    if not _is_int(max_runs) or max_runs < 1:
        raise bad("max_runs tem de ser um inteiro positivo")
    ranges = data.get("allowed_seeds")
    if not isinstance(ranges, list) or not ranges:
        raise bad("allowed_seeds tem de ser uma lista não vazia de [início, fim]")
    allowed = []
    for item in ranges:
        if not (isinstance(item, list) and len(item) == 2 and all(_is_int(x) for x in item) and 0 <= item[0] <= item[1]):
            raise bad(f"intervalo de sementes inválido {item!r}")
        allowed.append((item[0], item[1]))
    pre = data.get("preregistration")
    if not (isinstance(pre, dict) and set(pre) == {"path", "commit"} and isinstance(pre["path"], str) and pre["path"]
            and isinstance(pre["commit"], str) and _COMMIT.match(pre["commit"])):
        raise bad("preregistration tem de ter path e commit (hexadecimal)")
    created = data.get("created")
    if not (isinstance(created, str) and _DATE.match(created)):
        raise bad("created tem de ser AAAA-MM-DD")
    amendments = data.get("amendments", [])
    if not isinstance(amendments, list):
        raise bad("amendments tem de ser uma lista")
    previous = 0
    for item in amendments:
        if not (isinstance(item, dict) and set(item) == _AMENDMENT_KEYS and _is_int(item["max_runs"])
                and isinstance(item["reason"], str) and item["reason"].strip()
                and isinstance(item["date"], str) and _DATE.match(item["date"])):
            raise bad("cada adenda tem de ter max_runs, reason (não vazio) e date")
        if item["max_runs"] <= previous:
            raise bad("os max_runs das adendas têm de crescer")
        previous = item["max_runs"]
    if amendments and amendments[-1]["max_runs"] != max_runs:
        raise bad("max_runs tem de ser o da última adenda")
    return Manifest(campaign_id, max_runs, tuple(allowed), pre["path"], pre["commit"], created,
                    tuple(amendments), sha, head)


def protected_ranges(repo: Path = ROOT) -> list[tuple[int, int, str]]:
    """Intervalos de `exec/src/seeds.rs` (lidos por análise do texto) mais os blocos extra."""
    path = Path(repo) / SEEDS_SOURCE
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise BudgetError(f"não foi possível ler {SEEDS_SOURCE}: {error}") from error
    found = [(int(a.replace("_", "")), int(b.replace("_", "")), f"{SEEDS_SOURCE}")
             for a, b in _PROTECTED_RS.findall(text)]
    if not found:
        raise BudgetError(f"nenhum intervalo protegido encontrado em {SEEDS_SOURCE}; a recusar")
    return found + list(EXTRA_PROTECTED)


def _seed_of(item: Any) -> int:
    seed = item.get("seed") if isinstance(item, dict) else item
    if not _is_int(seed):
        raise BudgetError(f"execução planeada sem semente inteira: {item!r}")
    return seed


def _check_seeds(seeds: Iterable[int], manifest: Manifest, protected: list[tuple[int, int, str]]) -> None:
    for seed in seeds:
        if not any(lo <= seed <= hi for lo, hi in manifest.allowed_seeds):
            raise BudgetError(f"a semente {seed} está fora dos intervalos permitidos {list(manifest.allowed_seeds)}")
        for lo, hi, why in protected:
            if lo <= seed <= hi:
                raise BudgetError(f"a semente {seed} está no intervalo protegido {lo}-{hi} ({why})")


# --- registo ------------------------------------------------------------------------------------


@contextmanager
def _locked(path: Path, timeout: float = LOCK_TIMEOUT_S) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+b") as handle:
        deadline = time.monotonic() + timeout
        while True:
            try:
                _lock(handle)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise BudgetError(f"bloqueio do registo {path} não obtido em {timeout:.0f} s") from None
                time.sleep(0.01)
        try:
            yield
        finally:
            _unlock(handle)


if os.name == "nt":
    import msvcrt

    def _lock(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _paths(campaign_id: str, ledger_dir: Path | None, repo: Path) -> tuple[Path, Path]:
    base = Path(ledger_dir) if ledger_dir is not None else default_ledger_dir(Path(repo))
    return base / f"{campaign_id}.jsonl", base / f"{campaign_id}.lock"


def _read_ledger(path: Path, campaign_id: str) -> list[dict[str, Any]]:
    """Lê e valida a cadeia de hashes; qualquer anomalia recusa (falha fechada)."""
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    previous, total = GENESIS, 0
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise BudgetError(f"registo {path.name}: linha final incompleta; investigar antes de continuar")
    for number, line in enumerate(raw.split(b"\n")[:-1], start=1):
        try:
            entry = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BudgetError(f"registo {path.name}: linha {number} ilegível: {error}") from error
        if (not isinstance(entry, dict) or entry.get("schema") != LEDGER_SCHEMA or entry.get("seq") != number
                or entry.get("campaign_id") != campaign_id or entry.get("prev_sha256") != previous
                or not _is_int(entry.get("runs")) or entry["runs"] < 1):
            raise BudgetError(f"registo {path.name}: linha {number} inconsistente com a cadeia")
        total += entry["runs"]
        if entry.get("total_after") != total:
            raise BudgetError(f"registo {path.name}: linha {number} com total acumulado errado")
        previous = hashlib.sha256(line).hexdigest()
        entries.append(entry)
    return entries


def ledger_total(campaign_id: str, *, repo: Path = ROOT, ledger_dir: Path | None = None) -> int:
    _check_id(campaign_id)
    ledger, lock = _paths(campaign_id, ledger_dir, repo)
    with _locked(lock):
        entries = _read_ledger(ledger, campaign_id)
    return entries[-1]["total_after"] if entries else 0


def reserve(campaign_id: str, planned: Iterable[Any], label: str = "", *, repo: Path = ROOT,
            ledger_dir: Path | None = None) -> Reservation:
    """Reserva uma execução por elemento de `planned` (um inteiro semente ou um dict com `seed`).

    Tem de ser chamada antes de lançar qualquer execução. Sem reembolso.
    """
    _check_id(campaign_id)
    items = tuple(planned)
    if not items:
        raise BudgetError("plano vazio: nada a reservar")
    repo = Path(repo)
    manifest = load_manifest(campaign_id, repo)
    seeds = [_seed_of(item) for item in items]
    _check_seeds(seeds, manifest, protected_ranges(repo))
    ledger, lock = _paths(campaign_id, ledger_dir, repo)
    with _locked(lock):
        entries = _read_ledger(ledger, campaign_id)
        before = entries[-1]["total_after"] if entries else 0
        seen_max = max((e.get("max_runs", 0) for e in entries), default=0)
        if manifest.max_runs > seen_max > 0 and not (manifest.amendments and manifest.amendments[-1]["max_runs"] == manifest.max_runs):
            raise BudgetError(f"max_runs subiu de {seen_max} para {manifest.max_runs} sem adenda com razão")
        if before + len(items) > manifest.max_runs:
            raise BudgetExceeded(
                f"campanha {campaign_id}: já reservadas {before}, pedidas {len(items)}, limite {manifest.max_runs}")
        previous = GENESIS
        if entries:
            previous = hashlib.sha256(ledger.read_bytes().split(b"\n")[-2]).hexdigest()
        entry = {
            "schema": LEDGER_SCHEMA, "seq": len(entries) + 1, "campaign_id": campaign_id, "label": str(label),
            "runs": len(items), "total_after": before + len(items), "max_runs": manifest.max_runs,
            "seed_min": min(seeds), "seed_max": max(seeds), "manifest_sha256": manifest.sha256,
            "head": manifest.head, "pid": os.getpid(),
            "utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "prev_sha256": previous,
        }
        line = (json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        with open(ledger, "ab") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    return Reservation(campaign_id, len(items), before, before + len(items), manifest.max_runs, items)


def run_budgeted(campaign_id: str, planned: Iterable[Any], spawn: Callable[[Any], Any], label: str = "", *,
                 jobs: int = 1, repo: Path = ROOT, ledger_dir: Path | None = None) -> list[Outcome]:
    """Reserva e só depois chama `spawn(item)` para cada execução reservada, pela ordem do plano.

    Uma exceção de `spawn` fica em `Outcome.error` e a execução continua a contar.
    """
    reservation = reserve(campaign_id, planned, label, repo=repo, ledger_dir=ledger_dir)

    def one(item: Any) -> Outcome:
        try:
            return Outcome(item, spawn(item), None)
        except Exception as error:  # noqa: BLE001 - a falha é registada e a execução conta na mesma
            return Outcome(item, None, error)

    if jobs <= 1:
        return [one(item) for item in reservation.planned]
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(one, reservation.planned))


# --- contagem nos artefactos --------------------------------------------------------------------


def _count_artefacts(roots: Sequence[Path], marker: str, ledger: Path) -> int:
    resolved = [Path(r).resolve() for r in roots]
    for i, a in enumerate(resolved):
        if not a.is_dir():
            raise BudgetError(f"pasta de artefactos inexistente: {a}")
        if ledger.resolve().is_relative_to(a):
            raise BudgetError(f"o registo {ledger} está dentro da pasta de artefactos {a}")
        for b in resolved[i + 1:]:
            if a == b or a.is_relative_to(b) or b.is_relative_to(a):
                raise BudgetError(f"pastas de artefactos sobrepostas: {a} e {b}")
    return sum(1 for a in resolved for _, _, files in os.walk(a) for name in files if name == marker)


def recount(campaign_id: str, artefact_roots: Path | Sequence[Path], *, marker: str = DEFAULT_MARKER,
            declared_unrecorded: int = 0, repo: Path = ROOT, ledger_dir: Path | None = None) -> Recount:
    """Conta as execuções nos artefactos (um ficheiro `marker` por execução) e compara com o registo."""
    _check_id(campaign_id)
    roots = [artefact_roots] if isinstance(artefact_roots, (str, Path)) else list(artefact_roots)
    manifest = load_manifest(campaign_id, Path(repo))
    ledger, _ = _paths(campaign_id, ledger_dir, repo)
    total = ledger_total(campaign_id, repo=repo, ledger_dir=ledger_dir)
    return Recount(campaign_id, _count_artefacts([Path(r) for r in roots], marker, ledger), total,
                   manifest.max_runs, declared_unrecorded)


def guard_report(campaign_id: str, artefact_roots: Path | Sequence[Path], *, marker: str = DEFAULT_MARKER,
                 declared_unrecorded: int = 0, repo: Path = ROOT, ledger_dir: Path | None = None) -> Recount:
    """Chamar antes de escrever qualquer relatório. Recusa se a contagem exceder o limite ou divergir.

    `declared_unrecorded` é o número de execuções reservadas cujo artefacto não existe (falhadas,
    descartadas ou apagadas); aparece no relatório e tem de fechar a conta com o registo.
    """
    if not _is_int(declared_unrecorded) or declared_unrecorded < 0:
        raise BudgetError("declared_unrecorded tem de ser um inteiro não negativo")
    result = recount(campaign_id, artefact_roots, marker=marker, declared_unrecorded=declared_unrecorded,
                     repo=repo, ledger_dir=ledger_dir)
    if result.runs > result.max_runs:
        raise BudgetExceeded(f"{result.runs} execuções nos artefactos, acima do limite {result.max_runs}")
    if result.runs + declared_unrecorded != result.ledger_total:
        raise BudgetError(
            f"contagem nos artefactos {result.runs} (+{declared_unrecorded} declaradas) difere do registo "
            f"{result.ledger_total}")
    return result

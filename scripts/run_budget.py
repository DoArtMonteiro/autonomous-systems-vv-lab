"""Orçamento de execuções de uma campanha pré-registada, aplicado antes de cada execução.

Uma campanha declara o seu limite num manifesto `budgets/<campaign_id>.json` (registado em commit e
limpo). Antes de lançar qualquer execução, o script reserva `n` execuções com `run_budgeted`, que
reserva e só depois chama a função de lançamento injetada. `n` é o tamanho da matriz planeada,
nunca um número escrito à mão. As reservas ficam num registo JSONL de só acréscimo, sob um bloqueio
exclusivo entre processos, em `<git-common-dir>/vvlab-budget/`, partilhado por todas as worktrees e
fora de qualquer pasta de execuções. Não há reembolsos: uma execução falhada, descartada ou repetida
conta como qualquer outra.

O registo e o instante da reserva nunca entram em artefactos com hash nem em identificadores de
execução. `guard_report` conta as execuções nos artefactos e recusa o relatório se a contagem
exceder o limite ou divergir do registo (controlo detetivo).

A API pública (`reserve`, `run_budgeted`, `ledger_total`, `recount`, `guard_report`) não aceita
repositório nem diretório do registo, e não há opção de linha de comandos nem variável de ambiente
que os mude; as funções com prefixo `_` existem só para os testes. Ver `docs/run-budget.md`.
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
    (3_000, 3_099, "sementes de avaliação do M10"),
    (6_000, 6_099, "sementes de reserva do M10"),
    (44_000, 44_999, "reserva M13 para uma confirmação futura pré-registada"),
    (50_000, 59_999, "divisão reservada do M14, já gasta"),
    (81_000, 81_999, "bloco candidato do G3"),
)
# Intervalos que `exec/src/seeds.rs` tem de conter; se faltarem, o ficheiro foi alterado e recusa-se.
REQUIRED_IN_SOURCE = ((3_000, 3_099), (6_000, 6_099), (44_000, 44_999))

_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")
_RS_TOKENS = re.compile(r'"(?:[^"\\]|\\.)*"|//[^\n]*|/\*.*?\*/', re.S)
_RS_STRUCT = re.compile(r"\bstruct\s+Protected\s*\{")
_RS_ANY = re.compile(r"\bProtected\s*\{")
_RS_LITERAL = re.compile(r"\bProtected\s*\{([^{}]*)\}")
_RS_BODY = re.compile(
    r'^\s*start:\s*(\d+(?:_\d+)*)\s*,\s*end:\s*(\d+(?:_\d+)*)\s*,\s*reason:\s*""\s*,?\s*$')
_MANIFEST_KEYS = {"schema", "campaign_id", "max_runs", "allowed_seeds", "preregistration", "created", "amendments", "status"}
_AMENDMENT_KEYS = {"max_runs", "reason", "date"}  # mais `closes`, só na adenda que fecha


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
    status: str = "open"


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
    unrecorded_run_ids: tuple[str, ...]


# --- git ----------------------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> bytes:
    # Variáveis GIT_* (GIT_DIR, GIT_COMMON_DIR, GIT_WORK_TREE, ...) redirecionariam o repositório lido.
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    try:
        done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=30, env=env)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BudgetError(f"git indisponível: {error}") from error
    if done.returncode != 0:
        raise BudgetError(f"git {' '.join(args)} falhou: {done.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return done.stdout


def _default_ledger_dir(repo: Path) -> Path:
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


# --- manifesto ----------------------------------------------------------------------------------


def _load_manifest(campaign_id: str, repo: Path) -> Manifest:
    """Lê o manifesto; recusa se não for byte a byte igual ao blob em HEAD."""
    _check_id(campaign_id)
    rel = f"{MANIFEST_DIR}/{campaign_id}.json"
    try:
        blob = _git(repo, "cat-file", "blob", f"HEAD:{rel}")
    except BudgetError as error:
        raise BudgetError(f"o manifesto {rel} não está registado em HEAD: {error}") from error
    try:
        disk = (repo / rel).read_bytes()
    except OSError as error:
        raise BudgetError(f"o manifesto {rel} não pode ser lido: {error}") from error
    if disk != blob:
        raise BudgetError(f"o manifesto {rel} difere do blob em HEAD (alteração por registar em commit)")
    head = _git(repo, "rev-parse", "HEAD").decode("utf-8").strip()
    data = _parse_json(blob, rel)
    manifest = _validate_manifest(data, campaign_id, rel, hashlib.sha256(blob).hexdigest(), head)
    _check_history(repo, rel, data)
    _check_closed_elsewhere(repo, rel, manifest)
    _check_other_manifests(repo, manifest)
    return manifest


def _parse_json(blob: bytes, what: str) -> Any:
    try:
        return json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BudgetError(f"{what} não é JSON válido: {error}") from error


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
    for position, item in enumerate(amendments):
        closes = isinstance(item, dict) and "closes" in item
        keys = _AMENDMENT_KEYS | ({"closes"} if closes else set())
        if not (isinstance(item, dict) and set(item) == keys and _is_int(item["max_runs"])
                and isinstance(item["reason"], str) and item["reason"].strip()
                and isinstance(item["date"], str) and _DATE.match(item["date"])
                and (not closes or item["closes"] is True)):
            raise bad("cada adenda tem de ter max_runs, reason (não vazio) e date")
        if item["max_runs"] < previous or (item["max_runs"] == previous and not closes):
            raise bad("os max_runs das adendas têm de crescer")
        if closes and position != len(amendments) - 1:
            raise bad("a adenda que fecha a campanha tem de ser a última")
        previous = item["max_runs"]
    if amendments and amendments[-1]["max_runs"] != max_runs:
        raise bad("max_runs tem de ser o da última adenda")
    closed = bool(amendments) and "closes" in amendments[-1]
    status = data.get("status", "open")
    if status not in ("open", "closed") or (status == "closed") != closed:
        raise bad("status closed exige, e só admite, uma última adenda com closes e razão; não há reabertura")
    return Manifest(campaign_id, max_runs, tuple(allowed), pre["path"], pre["commit"], created,
                    tuple(amendments), sha, head, status)


def _check_history(repo: Path, rel: str, current: dict[str, Any]) -> None:
    """As adendas só crescem: cada versão anterior no histórico é prefixo da seguinte."""
    shas = _git(repo, "log", "--full-history", "--format=%H", "HEAD", "--", rel).decode("utf-8").split()
    newer = current
    for sha in shas[1:]:
        try:
            blob = _git(repo, "cat-file", "blob", f"{sha}:{rel}")
        except BudgetError as error:
            raise BudgetError(f"o manifesto {rel} foi apagado e recriado no histórico ({sha[:9]}): {error}") from error
        old = _parse_json(blob, f"{rel} em {sha[:9]}")
        if not isinstance(old, dict) or not _is_int(old.get("max_runs")) or not isinstance(old.get("amendments", []), list):
            raise BudgetError(f"o manifesto {rel} em {sha[:9]} é ilegível")
        if old.get("status") == "closed" and newer.get("status") != "closed":
            raise BudgetError(f"a campanha {rel} foi fechada em {sha[:9]} e não pode ser reaberta")
        old_amendments, new_amendments = old.get("amendments", []), newer.get("amendments", [])
        if new_amendments[:len(old_amendments)] != old_amendments:
            raise BudgetError(f"as adendas de {rel} não são só de acréscimo (versão {sha[:9]})")
        if newer["max_runs"] < old["max_runs"]:
            raise BudgetError(f"max_runs de {rel} desceu face à versão {sha[:9]}")
        if newer["max_runs"] > old["max_runs"] and len(new_amendments) <= len(old_amendments):
            raise BudgetError(f"max_runs de {rel} subiu sem adenda nova face à versão {sha[:9]}")
        newer = old


def _check_closed_elsewhere(repo: Path, rel: str, manifest: Manifest) -> None:
    """Uma campanha fechada em qualquer referência (ramo, etiqueta, worktree) não pode estar aberta em HEAD."""
    if manifest.status == "closed":
        return
    shas = _git(repo, "log", "--all", "--full-history", "--format=%H", "--", rel).decode("utf-8").split()
    for sha in shas:
        try:
            blob = _git(repo, "cat-file", "blob", f"{sha}:{rel}")
        except BudgetError:
            continue  # versão em que o ficheiro foi apagado
        old = _parse_json(blob, f"{rel} em {sha[:9]}")
        if isinstance(old, dict) and old.get("status") == "closed":
            raise BudgetError(f"a campanha {rel} está fechada na versão {sha[:9]} de outra referência: reaberta em HEAD")


def _check_other_manifests(repo: Path, manifest: Manifest) -> None:
    """Outro identificador não pode reaproveitar o pré-registo nem as sementes de uma campanha."""
    own = f"{MANIFEST_DIR}/{manifest.campaign_id}.json"
    gone = _git(repo, "log", "--full-history", "--no-renames", "--diff-filter=D", "--name-only", "--format=", "HEAD",
                "--", f"{MANIFEST_DIR}/*.json").decode("utf-8").split()
    if gone:
        raise BudgetError(f"o histórico apaga ou renomeia manifestos ({sorted(set(gone))[:3]}); "
                          "um identificador novo não repõe o registo de outra campanha")
    listing = _git(repo, "ls-tree", "--name-only", "HEAD", f"{MANIFEST_DIR}/").decode("utf-8").split("\n")
    for rel in (line.strip() for line in listing):
        if not rel.endswith(".json") or rel == own:
            continue
        data = _parse_json(_git(repo, "cat-file", "blob", f"HEAD:{rel}"), rel)
        try:
            other_path = data["preregistration"]["path"]
            other_ranges = [(lo, hi) for lo, hi in data["allowed_seeds"]]
        except (KeyError, TypeError, ValueError) as error:
            raise BudgetError(f"o manifesto {rel} é ilegível; a recusar por segurança: {error!r}") from error
        if other_path == manifest.preregistration_path:
            raise BudgetError(f"o pré-registo {other_path} já pertence ao manifesto {rel}")
        for lo, hi in manifest.allowed_seeds:
            for olo, ohi in other_ranges:
                if lo <= ohi and olo <= hi:
                    raise BudgetError(f"as sementes {lo}-{hi} sobrepõem-se às de {rel} ({olo}-{ohi}); "
                                      "uma campanha nova não repõe o registo de outra")


def _check_other_ledgers(paths: _Paths, manifest: Manifest) -> None:
    """Um identificador novo não pode herdar o pré-registo nem as sementes de um registo existente."""
    for other in sorted(paths.ledger.parent.glob("*.jsonl")):
        if other == paths.ledger:
            continue
        try:
            raw = other.read_bytes()
        except OSError as error:
            raise BudgetError(f"registo vizinho {other.name} ilegível; a recusar: {error!r}") from error
        lines = raw.splitlines()
        if lines and not raw.endswith(bytes([10])):
            lines.pop()  # linha final truncada: ignorada na verificação de sobreposição
        for number, line in enumerate(lines, start=1):
            if not line:
                continue
            try:
                entry = json.loads(line.decode("utf-8"))
                path, ranges = entry["prereg_path"], [(lo, hi) for lo, hi in entry["allowed_seeds"]]
            except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                raise BudgetError(f"registo vizinho {other.name} linha {number} ilegível; a recusar: {error!r}") from error
            if path == manifest.preregistration_path:
                raise BudgetError(f"o pré-registo {path} já tem o registo {other.name}")
            for lo, hi in manifest.allowed_seeds:
                if any(lo <= ohi and olo <= hi for olo, ohi in ranges):
                    raise BudgetError(f"as sementes {lo}-{hi} sobrepõem-se às do registo {other.name}")


def _protected_ranges(repo: Path) -> list[tuple[int, int, str]]:
    """Intervalos de `exec/src/seeds.rs` em HEAD, por análise estrita do texto, mais os blocos extra."""
    try:
        text = _git(repo, "cat-file", "blob", f"HEAD:{SEEDS_SOURCE}").decode("utf-8")
    except (BudgetError, UnicodeDecodeError) as error:
        raise BudgetError(f"não foi possível ler {SEEDS_SOURCE} em HEAD: {error}") from error
    clean = _RS_TOKENS.sub(lambda m: '""' if m.group(0).startswith('"') else " ", text)
    clean = _RS_STRUCT.sub("struct Definition {", clean)  # a definição do tipo não é um literal
    occurrences = len(_RS_ANY.findall(clean))
    literals = [m.group(1) for m in _RS_LITERAL.finditer(clean)]
    if occurrences < 1 or len(literals) != occurrences:
        raise BudgetError(f"{SEEDS_SOURCE}: formato de `Protected` não suportado; a recusar")
    found: list[tuple[int, int, str]] = []
    for body in literals:
        match = _RS_BODY.match(body)
        if not match:
            raise BudgetError(f"{SEEDS_SOURCE}: literal `Protected` não suportado ({body.strip()[:60]!r}); a recusar")
        start, end = (int(g.replace("_", "")) for g in match.groups())
        if start > end:
            raise BudgetError(f"{SEEDS_SOURCE}: intervalo protegido com início {start} acima do fim {end}")
        found.append((start, end, SEEDS_SOURCE))
    missing = [r for r in REQUIRED_IN_SOURCE if not any((lo, hi) == r for lo, hi, _ in found)]
    if missing:
        raise BudgetError(f"{SEEDS_SOURCE}: faltam intervalos protegidos obrigatórios {missing}; a recusar")
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


@dataclass(frozen=True)
class _Paths:
    ledger: Path
    tip: Path
    lock: Path


def _paths(campaign_id: str, ledger_dir: Path | None, repo: Path) -> _Paths:
    base = Path(ledger_dir) if ledger_dir is not None else _default_ledger_dir(repo)
    return _Paths(base / f"{campaign_id}.jsonl", base / f"{campaign_id}.tip", base / f"{campaign_id}.lock")


def _fsync_dir(directory: Path) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return  # Windows não abre diretórios assim
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _append(path: Path, data: bytes) -> None:
    created = not path.exists()
    with open(path, "ab") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    if created:
        _fsync_dir(path.parent)


def _read_ledger(paths: _Paths, campaign_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Lê e valida a cadeia de hashes e o registo de ponta; qualquer anomalia recusa (falha fechada)."""
    entries: list[dict[str, Any]] = []
    hashes: list[str] = []
    previous, total = GENESIS, 0
    raw = paths.ledger.read_bytes() if paths.ledger.exists() else b""
    name = paths.ledger.name
    if raw and not raw.endswith(b"\n"):
        raise BudgetError(f"registo {name}: linha final incompleta; ver a recuperação manual em docs/run-budget.md")
    for number, line in enumerate(raw.split(b"\n")[:-1] if raw else [], start=1):
        try:
            entry = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BudgetError(f"registo {name}: linha {number} ilegível: {error}") from error
        if (not isinstance(entry, dict) or entry.get("schema") != LEDGER_SCHEMA or entry.get("seq") != number
                or entry.get("campaign_id") != campaign_id or entry.get("prev_sha256") != previous
                or not _is_int(entry.get("runs")) or entry["runs"] < (0 if entry.get("event") == "closed" else 1)
                or (entry["runs"] != 0 and entry.get("event") == "closed")):
            raise BudgetError(f"registo {name}: linha {number} inconsistente com a cadeia")
        total += entry["runs"]
        if entry.get("total_after") != total:
            raise BudgetError(f"registo {name}: linha {number} com total acumulado errado")
        previous = hashlib.sha256(line).hexdigest()
        entries.append(entry)
        hashes.append(previous)
    _check_tip(paths, hashes)
    return entries, hashes


def _check_tip(paths: _Paths, hashes: list[str]) -> None:
    """O registo de ponta lembra o maior `seq` e o hash: apagar linhas finais ou o registo é detetado."""
    raw = paths.tip.read_bytes() if paths.tip.exists() else b""
    if raw and not raw.endswith(b"\n"):
        raise BudgetError(f"registo de ponta {paths.tip.name}: linha final incompleta; ver docs/run-budget.md")
    last = 0
    for number, line in enumerate(raw.split(b"\n")[:-1] if raw else [], start=1):
        try:
            record = json.loads(line.decode("utf-8"))
            seq, sha = record["seq"], record["sha256"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise BudgetError(f"registo de ponta {paths.tip.name}: linha {number} ilegível") from error
        if not _is_int(seq) or seq <= last:
            raise BudgetError(f"registo de ponta {paths.tip.name}: linha {number} fora de ordem")
        if seq > len(hashes):
            raise BudgetError(f"o registo de reservas está atrás do registo de ponta (seq {len(hashes)} < {seq}): "
                              "linhas apagadas ou registo apagado")
        if hashes[seq - 1] != sha:
            raise BudgetError(f"o registo de reservas diverge do registo de ponta na linha {seq}")
        last = seq


@contextmanager
def _state(campaign_id: str, repo: Path | None, ledger_dir: Path | None, need_manifest: bool = True
           ) -> Iterator[tuple[Manifest | None, list[dict[str, Any]], list[str], _Paths]]:
    _check_id(campaign_id)
    repo = Path(repo) if repo is not None else ROOT
    paths = _paths(campaign_id, ledger_dir, repo)
    with _locked(paths.lock):
        manifest = _load_manifest(campaign_id, repo) if need_manifest else None
        entries, hashes = _read_ledger(paths, campaign_id)
        if manifest is not None and manifest.status == "closed" and not any(e.get("event") == "closed" for e in entries):
            _write_entry(paths, entries, hashes, manifest, 0, "closed", [], "closed")  # o fecho fica no registo
            entries, hashes = _read_ledger(paths, campaign_id)
        yield manifest, entries, hashes, paths


def _ledger_total(campaign_id: str, repo: Path | None = None, ledger_dir: Path | None = None) -> int:
    with _state(campaign_id, repo, ledger_dir, need_manifest=False) as (_, entries, _hashes, _paths_):
        return entries[-1]["total_after"] if entries else 0


def _write_entry(paths: _Paths, entries: list[dict[str, Any]], hashes: list[str], manifest: Manifest, runs: int,
                 label: str, seeds: Sequence[int], event: str | None = None) -> dict[str, Any]:
    before = entries[-1]["total_after"] if entries else 0
    entry = {
        "schema": LEDGER_SCHEMA, "seq": len(entries) + 1, "campaign_id": manifest.campaign_id, "label": str(label),
        "runs": runs, "total_after": before + runs, "max_runs": manifest.max_runs,
        "seed_min": min(seeds) if seeds else None, "seed_max": max(seeds) if seeds else None,
        "manifest_sha256": manifest.sha256, "prereg_path": manifest.preregistration_path,
        "allowed_seeds": [list(r) for r in manifest.allowed_seeds], "n_amendments": len(manifest.amendments),
        "head": manifest.head, "pid": os.getpid(),
        "utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prev_sha256": hashes[-1] if hashes else GENESIS,
    }
    if event:
        entry["event"] = event
    line = json.dumps(entry, sort_keys=True, separators=(",", ":")).encode("utf-8")
    _append(paths.ledger, line + b"\n")
    tip = {"seq": entry["seq"], "sha256": hashlib.sha256(line).hexdigest()}
    _append(paths.tip, json.dumps(tip, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n")
    return entry


def _reserve(campaign_id: str, planned: Iterable[Any], label: str = "", repo: Path | None = None,
             ledger_dir: Path | None = None) -> Reservation:
    items = tuple(planned)
    if not items:
        raise BudgetError("plano vazio: nada a reservar")
    seeds = [_seed_of(item) for item in items]
    repo_path = Path(repo) if repo is not None else ROOT
    with _state(campaign_id, repo, ledger_dir) as (manifest, entries, hashes, paths):
        closed_before = any(e.get("event") == "closed" for e in entries)
        if manifest.status == "closed":
            raise BudgetError(f"a campanha {campaign_id} está fechada: nenhuma reserva é possível")
        if closed_before:
            raise BudgetError(f"a campanha {campaign_id} foi fechada segundo o registo e o manifesto não o diz: reaberta")
        _check_seeds(seeds, manifest, _protected_ranges(repo_path))
        before = entries[-1]["total_after"] if entries else 0
        _check_other_ledgers(paths, manifest)
        if entries and len(manifest.amendments) < entries[-1]["n_amendments"]:
            raise BudgetError("o manifesto tem menos adendas do que as registadas no último registo")
        if entries and manifest.max_runs > entries[-1]["max_runs"] and len(manifest.amendments) <= entries[-1]["n_amendments"]:
            raise BudgetError(f"max_runs subiu de {entries[-1]['max_runs']} para {manifest.max_runs} sem adenda nova "
                              "face ao último registo")
        if before + len(items) > manifest.max_runs:
            raise BudgetExceeded(
                f"campanha {campaign_id}: já reservadas {before}, pedidas {len(items)}, limite {manifest.max_runs}")
        _write_entry(paths, entries, hashes, manifest, len(items), label, seeds)
    return Reservation(campaign_id, len(items), before, before + len(items), manifest.max_runs, items)


def _run_budgeted(campaign_id: str, planned: Iterable[Any], spawn: Callable[[Any], Any], label: str = "",
                  jobs: int = 1, repo: Path | None = None, ledger_dir: Path | None = None) -> list[Outcome]:
    reservation = _reserve(campaign_id, planned, label, repo, ledger_dir)

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


def _recount(campaign_id: str, artefact_roots: Path | Sequence[Path], marker: str = DEFAULT_MARKER,
             declared_unrecorded: int = 0, unrecorded_run_ids: Sequence[str] = (),
             repo: Path | None = None, ledger_dir: Path | None = None) -> Recount:
    roots = [artefact_roots] if isinstance(artefact_roots, (str, Path)) else list(artefact_roots)
    with _state(campaign_id, repo, ledger_dir) as (manifest, entries, _hashes, paths):
        total = entries[-1]["total_after"] if entries else 0
        runs = _count_artefacts([Path(r) for r in roots], marker, paths.ledger)
    return Recount(campaign_id, runs, total, manifest.max_runs, declared_unrecorded, tuple(unrecorded_run_ids))


def _guard_report(campaign_id: str, artefact_roots: Path | Sequence[Path], marker: str = DEFAULT_MARKER,
                  declared_unrecorded: int = 0, unrecorded_run_ids: Sequence[str] = (),
                  repo: Path | None = None, ledger_dir: Path | None = None) -> Recount:
    ids = tuple(unrecorded_run_ids)
    if not _is_int(declared_unrecorded) or declared_unrecorded < 0:
        raise BudgetError("declared_unrecorded tem de ser um inteiro não negativo")
    if (not all(isinstance(i, str) and i for i in ids) or len(set(ids)) != len(ids)
            or declared_unrecorded != len(ids)):
        raise BudgetError(
            f"declared_unrecorded={declared_unrecorded} não coincide com os {len(ids)} run_ids distintos indicados")
    result = _recount(campaign_id, artefact_roots, marker, declared_unrecorded, ids, repo, ledger_dir)
    if result.runs > result.max_runs:
        raise BudgetExceeded(f"{result.runs} execuções nos artefactos, acima do limite {result.max_runs}")
    if result.runs + declared_unrecorded != result.ledger_total:
        raise BudgetError(
            f"contagem nos artefactos {result.runs} (+{declared_unrecorded} declaradas) difere do registo "
            f"{result.ledger_total}")
    return result


# --- API pública: sem repositório nem diretório do registo -------------------------------------


def reserve(campaign_id: str, planned: Iterable[Any], label: str = "") -> Reservation:
    """Reserva uma execução por elemento de `planned` (um inteiro semente ou um dict com `seed`).

    Tem de ser chamada antes de lançar qualquer execução. Sem reembolso.
    """
    return _reserve(campaign_id, planned, label)


def run_budgeted(campaign_id: str, planned: Iterable[Any], spawn: Callable[[Any], Any], label: str = "", *,
                 jobs: int = 1) -> list[Outcome]:
    """Reserva e só depois chama `spawn(item)` para cada execução reservada, pela ordem do plano.

    Uma exceção de `spawn` fica em `Outcome.error` e a execução continua a contar.
    """
    return _run_budgeted(campaign_id, planned, spawn, label, jobs)


def ledger_total(campaign_id: str) -> int:
    return _ledger_total(campaign_id)


def recount(campaign_id: str, artefact_roots: Path | Sequence[Path], *, marker: str = DEFAULT_MARKER) -> Recount:
    """Conta as execuções nos artefactos (um ficheiro `marker` por execução) e compara com o registo."""
    return _recount(campaign_id, artefact_roots, marker)


def guard_report(campaign_id: str, artefact_roots: Path | Sequence[Path], *, marker: str = DEFAULT_MARKER,
                 declared_unrecorded: int = 0, unrecorded_run_ids: Sequence[str] = ()) -> Recount:
    """Controlo detetivo: chamar antes de escrever qualquer relatório.

    Recusa se a contagem exceder o limite ou se contagem mais `declared_unrecorded` diferir do total do
    registo. Deteta excesso líquido de execuções face ao registo, não uma execução concreta fora dele.
    `unrecorded_run_ids` lista os identificadores das execuções reservadas sem artefacto (falhadas ou
    descartadas) e o seu tamanho tem de ser igual a `declared_unrecorded`.
    """
    return _guard_report(campaign_id, artefact_roots, marker, declared_unrecorded, unrecorded_run_ids)

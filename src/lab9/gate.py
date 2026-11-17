"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def _looser(new: dict, old: dict) -> list[str]:
    """Describe threshold relaxations from old (protected) to new (PR)."""
    problems = []
    for key in ("min", "max", "max_increase"):
        if key not in old:
            continue
        if key not in new:
            problems.append(f"threshold {key} removed")
        elif key == "min" and new[key] < old[key]:
            problems.append(f"min lowered from {old[key]} to {new[key]}")
        elif key in ("max", "max_increase") and new[key] > old[key]:
            problems.append(f"{key} raised from {old[key]} to {new[key]}")
    if old.get("no_significant_drop") and not new.get("no_significant_drop"):
        problems.append("no_significant_drop removed")
    return problems


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    for metric, value in pr.get("metrics", {}).items():
        if isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isfinite(value):
            problems.append(f"metric {metric} is not finite")

    manifest = pr.get("manifest", {})
    seeds = manifest.get("seeds") or []
    expected = int(manifest.get("items", 0)) * len(seeds)
    rows = pr.get("rows") or []
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    if len(rows) != expected:
        problems.append(f"row count {len(rows)} does not match manifest {expected}")
    if len(set(keys)) != len(keys):
        problems.append("duplicate (item_id, seed) rows")
    base_rows = base.get("rows") or []
    base_keys = [(r.get("item_id"), r.get("seed")) for r in base_rows]
    if set(keys) != set(base_keys):
        problems.append("(item_id, seed) set differs from baseline")

    if pr.get("evaluator_failures"):
        problems.append("evaluator_failures is non-empty")
    graded = {m["id"] for m in spec.get("metrics", []) if m.get("grader") == "code" or m["id"] in GRADERS}
    for row in rows:
        for metric in graded:
            if metric not in row or row[metric] is None:
                problems.append(f"{row.get('item_id')}@{row.get('seed')}: {metric} is missing/None")
    # Slice membership is label-derived and immutable for a given eval-set version.
    base_by_key = {(r.get("item_id"), r.get("seed")): r for r in base_rows}
    for key, row in zip(keys, rows):
        other = base_by_key.get(key)
        if other is not None and sorted(row.get("slices") or []) != sorted(other.get("slices") or []):
            problems.append(f"{key[0]}@{key[1]}: slice tags differ from baseline")
            break

    if base_spec and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        new_metrics = {m["id"]: m for m in spec.get("metrics", [])}
        for old_metric in base_spec.get("metrics", []):
            mid = old_metric["id"]
            new_metric = new_metrics.get(mid)
            if new_metric is None:
                problems.append(f"metric {mid} removed from spec")
                continue
            if old_metric.get("blocking") and not new_metric.get("blocking"):
                problems.append(f"metric {mid} changed from blocking to non-blocking")
            for p in _looser(new_metric.get("threshold", {}), old_metric.get("threshold", {})):
                problems.append(f"metric {mid}: {p}")
        old_slices = {(s.get("name"), s.get("metric")): s for s in base_spec.get("slices", [])}
        new_slices = {(s.get("name"), s.get("metric")): s for s in spec.get("slices", [])}
        for key, old_slice in old_slices.items():
            new_slice = new_slices.get(key)
            label = f"slice {key[0]}/{key[1]}"
            if new_slice is None:
                problems.append(f"{label} removed from spec")
                continue
            if old_slice.get("blocking") and not new_slice.get("blocking"):
                problems.append(f"{label} changed from blocking to non-blocking")
            for p in _looser(new_slice, old_slice):
                problems.append(f"{label}: {p}")
    return list(dict.fromkeys(problems))


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for rule in spec.get("slices", []):
        name, metric = rule["name"], rule["metric"]
        current = per_item(pr, metric, name)
        baseline = per_item(base, metric, name)
        value = sum(current.values()) / len(current) if current else None
        verdicts = []
        if value is None:
            verdicts.append("no rows")
        elif "min" in rule and value < rule["min"]:
            verdicts.append(f"below min {rule['min']}")
        note = ""
        if rule.get("no_significant_drop"):
            keys = sorted(set(current) & set(baseline))
            if not keys:
                verdicts.append("no paired baseline items")
            else:
                d, lo, hi = stats.paired_bootstrap(
                    [current[k] for k in keys], [baseline[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                    confidence=bs.get("confidence", 0.95),
                )
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdicts.append("significant drop")
        mid = f"slice:{name}/{metric}"
        if verdicts and rule.get("blocking", True):
            blocked.append(mid)
        lines.append(f"  {mid:<34} {value if value is not None else 'MISSING':<8} "
                     f"{note:<28} {'BLOCK' if verdicts and rule.get('blocking', True) else ('warn' if verdicts else 'ok')}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

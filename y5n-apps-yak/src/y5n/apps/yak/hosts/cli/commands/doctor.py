"""yak doctor — check context health."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.hosts.cli.cwd import find_context_root


def run(args, mgr) -> None:
    ctx = find_context_root()
    if ctx is None:
        print("Not inside a Yak context.")
        return

    issues: list[str] = []

    if ctx.exists():
        issues.append(f"✓ Context root: {ctx}")
    else:
        issues.append("✘ Context root: missing")

    env_yml = ctx / ".yak" / "environment.yml"
    if env_yml.exists():
        issues.append(f"✓ Environment:  {env_yml}")
    else:
        issues.append("— Environment:  none")
        issues.append("  Run 'yak sync' to create one")

    from y5n.apps.yak.environment.io import load as load_env

    env = load_env(ctx)
    if env:
        for m in env.mounts:
            src = Path(m.source)
            if src.is_dir():
                issues.append(f"✓ Mount:        {m.target} ← {m.source}")
            else:
                issues.append(f"✘ Mount:        {m.target} ← {m.source} (not found)")

        structure_dir = ctx / env.workspace_path
        if structure_dir.is_dir():
            issues.append(f"✓ Workspace:    {structure_dir}")
        else:
            issues.append("— Workspace:    not materialized")
            issues.append("  Run 'yak sync' to materialize")

    errors = [r for r in issues if r.startswith("✘")]
    for line in issues:
        print(f"  {line}")
    if errors:
        print(f"\n  {len(errors)} issue(s) found")
    else:
        print("\n  ✓ Context looks good")

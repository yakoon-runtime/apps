from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.cap.models import read_component

YAK_YML = """\
title: {title}

resolvable: true
navigable: false
contextual: false
host: /boot/python/runtime

entry:
  run: cap:y5n.caps.{capname}.{name}:main

document:
  default: file:resources/default.ydf

man:
  default: file:resources/man.ydf
"""


ENTRY_PY = """\
from y5n.sdk import context, ports, runtime


async def main():
    doc = ports.get("document")
    user = (context.session().user or "") if hasattr(context, "session") else ""
    result = await doc.render(name="default", state={{"user": user}})
    await runtime.io.write(result)
"""


DEFAULT_YDF = """\
{% if user %}
Hello {{ user }}!
{% else %}
Welcome to Yakoon. Use 'su' to log in.
{% endif %}
"""


MAN_YDF = """\
Yakoon command reference.

Edit the resources/man.ydf file to document this command.
"""


def _find_cap_root(cwd: Path) -> tuple[Path, str] | None:
    """Walk up from CWD looking for a native project root (pyproject.toml)."""
    import tomllib

    for parent in [cwd, *cwd.parents]:
        pyproject = parent / "pyproject.toml"
        if pyproject.exists():
            try:
                with open(pyproject, "rb") as f:
                    data = tomllib.load(f)
                project = data.get("project", {})
                name = project.get("name") or parent.name
                return parent, name
            except (tomllib.TOMLDecodeError, KeyError):
                pass
    return None


def create_command(
    name: str, cap_name: str | None = None, force: bool = False
) -> Path:
    target = Path.cwd()
    if cap_name is None:
        found = _find_cap_root(target)
        if found is None:
            raise RuntimeError(
                "no cap found in current or parent directories.\n"
                "Run 'yak create command <name> --cap <capname>' from inside a cap, "
                "or specify --cap explicitly."
            )
        cap_root, cap_name = found
    else:
        cap_root = target / cap_name if (target / cap_name).exists() else target

    title = name.capitalize()

    mount = read_component(cap_root)
    if mount is None or mount.mount is None or not mount.mount.source:
        raise RuntimeError(
            f"cap '{cap_name}' has no .yak/mount.yml — commands live in the "
            "cap's mounted directory (declare 'source' in mount.yml)"
        )
    mounted_dir = cap_root / mount.mount.source
    structure_dir = mounted_dir / name
    if structure_dir.exists() and not force:
        raise FileExistsError(
            f"command '{name}' already exists at {structure_dir} (use --force to overwrite)"
        )

    src_file = cap_root / "src" / "y5n" / "caps" / cap_name / f"{name}.py"
    if src_file.exists() and not force:
        raise FileExistsError(
            f"entry point '{src_file}' already exists (use --force to overwrite)"
        )

    structure_dir.mkdir(parents=True, exist_ok=True)
    res_dir = structure_dir / "resources"
    res_dir.mkdir(exist_ok=True)

    (structure_dir / ".yak" / "yak.yml").parent.mkdir(parents=True, exist_ok=True)
    (structure_dir / ".yak" / "yak.yml").write_text(
        YAK_YML.format(title=title, capname=cap_name, name=name)
    )
    (res_dir / "default.ydf").write_text(DEFAULT_YDF)
    (res_dir / "man.ydf").write_text(MAN_YDF)

    src_file.parent.mkdir(parents=True, exist_ok=True)
    src_file.write_text(ENTRY_PY.format(name=name))

    return structure_dir

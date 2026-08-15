from __future__ import annotations

from pathlib import Path

YAK_YML = """\
title: {title}

resolvable: true
navigable: false
contextual: false
host: /boot/python/runtime

entry:
  run: pack:y5n.packs.{packname}.{name}:main

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


def _find_pack_root(cwd: Path) -> tuple[Path, str] | None:
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
    name: str, pack_name: str | None = None, force: bool = False
) -> Path:
    target = Path.cwd()
    if pack_name is None:
        found = _find_pack_root(target)
        if found is None:
            raise RuntimeError(
                "no pack found in current or parent directories.\n"
                "Run 'yak create command <name> --pack <packname>' from inside a pack, "
                "or specify --pack explicitly."
            )
        pack_root, pack_name = found
    else:
        pack_root = target / pack_name if (target / pack_name).exists() else target

    title = name.capitalize()

    structure_dir = pack_root / "structure" / name
    if structure_dir.exists() and not force:
        raise FileExistsError(
            f"command '{name}' already exists at {structure_dir} (use --force to overwrite)"
        )

    src_file = pack_root / "src" / "y5n" / "packs" / pack_name / f"{name}.py"
    if src_file.exists() and not force:
        raise FileExistsError(
            f"entry point '{src_file}' already exists (use --force to overwrite)"
        )

    structure_dir.mkdir(parents=True, exist_ok=True)
    res_dir = structure_dir / "resources"
    res_dir.mkdir(exist_ok=True)

    (structure_dir / ".yak" / "yak.yml").parent.mkdir(parents=True, exist_ok=True)
    (structure_dir / ".yak" / "yak.yml").write_text(
        YAK_YML.format(title=title, packname=pack_name, name=name)
    )
    (res_dir / "default.ydf").write_text(DEFAULT_YDF)
    (res_dir / "man.ydf").write_text(MAN_YDF)

    src_file.parent.mkdir(parents=True, exist_ok=True)
    src_file.write_text(ENTRY_PY.format(name=name))

    return structure_dir

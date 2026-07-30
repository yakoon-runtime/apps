from __future__ import annotations

from pathlib import Path

PACK_TOML = """\
name = "{name}"
version = "0.1.0"
description = "{title} pack"
"""


PYPROJECT_TOML = """\
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "y5n-packs-{name}"
version = "0.1.0"
requires-python = ">=3.13"
license = {{ text = "Apache-2.0" }}
dependencies = ["y5n-runtime-api", "y5n-sdk-python"]

[tool.setuptools]
package-dir = {{"" = "src"}}

[tool.setuptools.packages.find]
where = ["src"]
namespaces = true
"""


YAK_YML = """\
title: {title}

resolvable: false
navigable: true
contextual: false
"""


def create_pack(name: str, target: Path | None = None, force: bool = False) -> Path:
    title = name.capitalize()
    root = (target or Path.cwd()) / name

    if root.exists() and not force:
        raise FileExistsError(
            f"directory '{root}' already exists (use --force to overwrite)"
        )

    root.mkdir(parents=True, exist_ok=True)
    (root / "pack.toml").write_text(PACK_TOML.format(name=name, title=title))
    (root / "pyproject.toml").write_text(PYPROJECT_TOML.format(name=name))
    (root / "README.md").write_text(f"# {title}\n\n{title} pack.\n")

    src_dir = root / "src" / "y5n" / "packs" / name
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "__init__.py").write_text("")

    structure_dir = root / "structure"
    (structure_dir / ".yak").mkdir(parents=True, exist_ok=True)
    (structure_dir / ".yak" / "yak.yml").write_text(YAK_YML.format(title=title))

    return root

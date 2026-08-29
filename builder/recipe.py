"""声明式配方（recipes/<name>/recipe.toml）的加载、渲染与校验。"""

import re
import string
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]+$")
MODE_RE = re.compile(r"^0[0-7]{3}$")
VERSION_RE = re.compile(r"^[0-9][A-Za-z0-9.+~:-]*$")


class RecipeError(Exception):
    pass


@dataclass
class Recipe:
    name: str
    version: str
    architecture: str
    description: str
    revision: int = 0
    section: str = "misc"
    priority: str = "optional"
    homepage: str = ""
    license: str = ""
    depends: list = field(default_factory=list)
    provides: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    replaces: list = field(default_factory=list)
    recommends: list = field(default_factory=list)
    conffiles: list = field(default_factory=list)
    notes: str = ""
    upstream: dict = field(default_factory=dict)
    sources: list = field(default_factory=list)
    installs: list = field(default_factory=list)
    links: list = field(default_factory=list)
    scripts: dict = field(default_factory=dict)
    dir: Path = None

    @property
    def full_version(self) -> str:
        return self.version if self.revision == 0 else f"{self.version}-{self.revision}"

    @property
    def deb_name(self) -> str:
        return f"{self.name}_{self.full_version}_{self.architecture}.deb"


def _render(s: str, vars: dict) -> str:
    return string.Template(s).substitute(vars)


def load_recipe(recipe_dir: Path) -> Recipe:
    path = recipe_dir / "recipe.toml"
    if not path.is_file():
        raise RecipeError(f"找不到配方文件 {path}")
    with open(path, "rb") as f:
        data = tomllib.load(f)

    pkg = data.get("package", {})
    r = Recipe(
        name=pkg.get("name", ""),
        version=str(pkg.get("version", "")),
        revision=int(pkg.get("revision", 0)),
        architecture=pkg.get("architecture", ""),
        description=pkg.get("description", ""),
        section=pkg.get("section", "misc"),
        priority=pkg.get("priority", "optional"),
        homepage=pkg.get("homepage", ""),
        license=pkg.get("license", ""),
        depends=pkg.get("depends", []),
        provides=pkg.get("provides", []),
        conflicts=pkg.get("conflicts", []),
        replaces=pkg.get("replaces", []),
        recommends=pkg.get("recommends", []),
        conffiles=pkg.get("conffiles", []),
        notes=pkg.get("notes", ""),
        upstream=data.get("upstream", {"type": "none"}),
        sources=data.get("source", []),
        installs=data.get("install", []),
        links=data.get("link", []),
        scripts=data.get("scripts", {}),
        dir=recipe_dir,
    )

    vars = {"version": r.version, "name": r.name}
    for src in r.sources:
        if "url" in src:
            src["url"] = _render(src["url"], vars)

    validate(r)
    return r


def validate(r: Recipe) -> None:
    err = lambda msg: (_ for _ in ()).throw(RecipeError(f"{r.name or r.dir}: {msg}"))
    if not NAME_RE.match(r.name):
        err(f"非法包名 {r.name!r}")
    if not VERSION_RE.match(r.version):
        err(f"非法版本号 {r.version!r}")
    if r.architecture not in ("amd64", "arm64", "loongarch64", "all"):
        err(f"不支持的架构 {r.architecture!r}")
    if not r.description:
        err("缺少 description")

    install_targets = set()
    for ins in r.installs:
        to = ins.get("to", "")
        if not to.startswith("/"):
            err(f"install.to 必须是绝对路径: {to!r}")
        if not MODE_RE.match(str(ins.get("mode", ""))):
            err(f"install 条目 {to} 缺少或非法 mode（如 \"0755\"）")
        if not ins.get("from"):
            err(f"install 条目 {to} 缺少 from")
        install_targets.add(to)
    for lk in r.links:
        if not lk.get("name", "").startswith("/"):
            err(f"link.name 必须是绝对路径: {lk.get('name')!r}")
        if not lk.get("target"):
            err(f"link {lk.get('name')} 缺少 target")
    for cf in r.conffiles:
        if cf not in install_targets:
            err(f"conffile {cf} 未出现在任何 install 条目中")
    for hook, fname in r.scripts.items():
        if hook not in ("preinst", "postinst", "prerm", "postrm"):
            err(f"不支持的维护者脚本 {hook}")
        if not (r.dir / fname).is_file():
            err(f"维护者脚本文件不存在: {fname}")
    if not r.installs and not r.links:
        err("配方没有任何 install/link 条目")


def all_recipe_dirs(root: Path) -> list[Path]:
    recipes = root / "recipes"
    if not recipes.is_dir():
        return []
    return sorted(d for d in recipes.iterdir() if (d / "recipe.toml").is_file())

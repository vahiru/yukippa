"""staging 树组装、control 生成、dpkg-deb 打包。"""

import os
import shutil
import subprocess
from pathlib import Path

from .config import Config
from .fetch import download, extract, sha256sum, FetchError
from .recipe import Recipe, RecipeError


def _staging_size_kib(staging: Path) -> int:
    total = 0
    for p in staging.rglob("*"):
        if p.is_file() and not p.is_symlink() and "DEBIAN" not in p.parts:
            total += p.stat().st_size
    return (total + 1023) // 1024


def _write_control(r: Recipe, cfg: Config, staging: Path) -> None:
    debian = staging / "DEBIAN"
    debian.mkdir(parents=True, exist_ok=True)

    lines = [
        f"Package: {r.name}",
        f"Version: {r.full_version}",
        f"Architecture: {r.architecture}",
        f"Maintainer: {cfg.maintainer}",
        f"Installed-Size: {_staging_size_kib(staging)}",
        f"Section: {r.section}",
        f"Priority: {r.priority}",
    ]
    for fld, values in (
        ("Depends", r.depends),
        ("Recommends", r.recommends),
        ("Provides", r.provides),
        ("Conflicts", r.conflicts),
        ("Replaces", r.replaces),
    ):
        if values:
            lines.append(f"{fld}: {', '.join(values)}")
    if r.homepage:
        lines.append(f"Homepage: {r.homepage}")
    lines.append(f"Description: {r.description}")
    if r.notes:
        for ln in r.notes.splitlines():
            lines.append(f" {ln.strip()}" if ln.strip() else " .")
    (debian / "control").write_text("\n".join(lines) + "\n")

    if r.conffiles:
        (debian / "conffiles").write_text("\n".join(r.conffiles) + "\n")
    for hook, fname in r.scripts.items():
        dst = debian / hook
        shutil.copy2(r.dir / fname, dst)
        dst.chmod(0o755)


def _resolve_from(r: Recipe, srcdir: Path, rel: str) -> Path:
    for base in (srcdir, r.dir):
        p = (base / rel).resolve()
        if p.is_file() or p.is_dir():
            if not (p.is_relative_to(srcdir.resolve()) or p.is_relative_to(r.dir.resolve())):
                raise RecipeError(f"{r.name}: from 路径越界: {rel}")
            return p
    raise RecipeError(f"{r.name}: 找不到 install.from 文件: {rel}")


def build(r: Recipe, cfg: Config, force: bool = False) -> Path | None:
    out = cfg.incoming / r.deb_name
    existing = list(cfg.pool.rglob(r.deb_name)) + list(cfg.big_index.glob(r.deb_name + ".stanza"))
    if existing and not force:
        print(f"  {r.deb_name} 已在仓库中，跳过（--force 强制重建）")
        return None

    workdir = cfg.root / "build" / r.name
    if workdir.exists():
        shutil.rmtree(workdir)
    srcdir = workdir / "src"
    staging = workdir / "staging"
    srcdir.mkdir(parents=True)
    staging.mkdir(parents=True)

    for src in r.sources:
        f = download(src["url"], cfg.root / "cache", src.get("sha256") or None)
        if not src.get("sha256"):
            raise FetchError(f"{r.name}: source {f.name} 缺少 sha256（实际值 {sha256sum(f)}，请写入配方）")
        if src.get("extract", True):
            extract(f, srcdir)
        else:
            shutil.copy2(f, srcdir / f.name)

    for ins in r.installs:
        src = _resolve_from(r, srcdir, ins["from"])
        dst = staging / ins["to"].lstrip("/")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        dst.chmod(int(str(ins["mode"]), 8))
    for lk in r.links:
        dst = staging / lk["name"].lstrip("/")
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(lk["target"], dst)

    _write_control(r, cfg, staging)

    cfg.incoming.mkdir(exist_ok=True)
    subprocess.run(
        ["dpkg-deb", "--build", "--root-owner-group", "-Zxz", str(staging), str(out)],
        check=True,
    )
    print(f"  已生成 {out.relative_to(cfg.root)}")
    return out

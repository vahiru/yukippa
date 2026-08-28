"""发布：incoming 归置（pool / big 路由）、双架构索引、Release 签名、
keyring 引导副本、index.html、版本 gc。"""

import functools
import gzip
import lzma
import shutil
import subprocess
from datetime import date
from pathlib import Path

from .config import Config
from .fetch import sha256sum

GITHUB_HARD_LIMIT = 100 * 1024 * 1024


class PublishError(Exception):
    pass


# ---------- deb 元数据 ----------

def deb_fields(deb: Path) -> dict:
    out = subprocess.run(
        ["dpkg-deb", "-f", str(deb), "Package", "Version", "Architecture"],
        check=True, capture_output=True, text=True,
    ).stdout
    fields = {}
    for line in out.splitlines():
        if ": " in line:
            k, v = line.split(": ", 1)
            fields[k] = v.strip()
    for k in ("Package", "Version", "Architecture"):
        if k not in fields:
            raise PublishError(f"{deb.name}: 读不到 {k} 字段")
    return fields


def _dpkg_ver_cmp(a: str, b: str) -> int:
    for op, ret in (("lt", -1), ("gt", 1)):
        if subprocess.run(["dpkg", "--compare-versions", a, op, b]).returncode == 0:
            return ret
    return 0


# ---------- 来源追溯 ----------

def record_provenance(cfg: Config, deb: Path, source: str) -> None:
    prov = cfg.pool.parent / ".provenance.toml"
    entry = (
        f'\n[[entry]]\nfile = "{deb.name}"\nsource = "{source}"\n'
        f'sha256 = "{sha256sum(deb)}"\ndate = "{date.today().isoformat()}"\n'
    )
    old = prov.read_text() if prov.is_file() else "# yukippa 收录来源追溯记录\n"
    if f'file = "{deb.name}"' in old:
        return
    prov.parent.mkdir(parents=True, exist_ok=True)
    prov.write_text(old + entry)


# ---------- incoming 路由 ----------

def route_incoming(cfg: Config) -> list[Path]:
    moved = []
    if not cfg.incoming.is_dir():
        return moved
    for deb in sorted(cfg.incoming.glob("*.deb")):
        f = deb_fields(deb)
        big = deb.stat().st_size > cfg.big_threshold_mb * 1024 * 1024
        if big:
            dest_dir = cfg.big
        else:
            dest_dir = cfg.pool / f["Package"][0] / f["Package"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / deb.name
        shutil.move(deb, dest)
        print(f"  {deb.name} -> {dest.parent.relative_to(cfg.root)}/ {'(big 通道)' if big else ''}")
        if big:
            _write_big_stanza(cfg, dest)
        moved.append(dest)
    return moved


def _write_big_stanza(cfg: Config, deb: Path) -> None:
    """big/ 中的 deb 生成索引段落存入 big-index/（入 git），
    这样 CI 上没有大文件本体也能维持索引。"""
    out = subprocess.run(
        ["apt-ftparchive", "packages", "big"],
        cwd=cfg.root, check=True, capture_output=True, text=True,
    ).stdout
    for stanza in _split_stanzas(out):
        fn = _stanza_field(stanza, "Filename")
        name = Path(fn).name
        if name == deb.name:
            cfg.big_index.mkdir(exist_ok=True)
            (cfg.big_index / f"{name}.stanza").write_text(stanza.strip() + "\n")
            print(f"  索引段落 -> big-index/{name}.stanza")
            return
    raise PublishError(f"apt-ftparchive 没有扫到 {deb.name}")


# ---------- 索引 ----------

def _split_stanzas(text: str) -> list[str]:
    return [s for s in text.split("\n\n") if s.strip()]


def _stanza_field(stanza: str, key: str) -> str:
    for line in stanza.splitlines():
        if line.startswith(key + ": "):
            return line[len(key) + 2:].strip()
    return ""


def _all_stanzas(cfg: Config) -> list[str]:
    stanzas = []
    if (cfg.root / "pool").is_dir():
        out = subprocess.run(
            ["apt-ftparchive", "packages", "pool"],
            cwd=cfg.root, check=True, capture_output=True, text=True,
        ).stdout
        stanzas += _split_stanzas(out)
    if cfg.big_index.is_dir():
        for f in sorted(cfg.big_index.glob("*.stanza")):
            stanzas.append(f.read_text().strip())
    return stanzas


def gen_indices(cfg: Config) -> list[str]:
    stanzas = _all_stanzas(cfg)
    for arch in cfg.architectures:
        subset = [s for s in stanzas
                  if _stanza_field(s, "Architecture") in (arch, "all")]
        d = cfg.dists / cfg.component / f"binary-{arch}"
        d.mkdir(parents=True, exist_ok=True)
        body = "\n\n".join(subset) + ("\n" if subset else "")
        (d / "Packages").write_text(body)
        (d / "Packages.gz").write_bytes(gzip.compress(body.encode(), 9))
        (d / "Packages.xz").write_bytes(lzma.compress(body.encode(), preset=9))
        print(f"  binary-{arch}/Packages: {len(subset)} 个包")
    return stanzas


def gen_release(cfg: Config, sign: bool = True) -> None:
    for f in ("Release", "InRelease", "Release.gpg"):
        (cfg.dists / f).unlink(missing_ok=True)
    archs = " ".join(cfg.architectures + ["all"])
    opts = []
    for k, v in (
        ("Origin", cfg.origin), ("Label", cfg.label), ("Suite", cfg.suite),
        ("Codename", cfg.codename), ("Architectures", archs),
        ("Components", cfg.component),
        ("Description", "yukippa - AOSC OS user repository"),
    ):
        opts += ["-o", f"APT::FTPArchive::Release::{k}={v}"]
    release = subprocess.run(
        ["apt-ftparchive", *opts, "release", str(cfg.dists)],
        cwd=cfg.root, check=True, capture_output=True, text=True,
    ).stdout
    (cfg.dists / "Release").write_text(release)

    if not sign:
        print("  跳过签名（--no-sign）")
        return
    if not cfg.signing_key:
        raise PublishError("yukippa.toml 里 signing_key 为空，先初始化 GPG 密钥")
    common = ["gpg", "--batch", "--yes", "--pinentry-mode", "loopback",
              "-u", cfg.signing_key]
    subprocess.run([*common, "--clearsign", "-o", str(cfg.dists / "InRelease"),
                    str(cfg.dists / "Release")], check=True)
    subprocess.run([*common, "-abs", "-o", str(cfg.dists / "Release.gpg"),
                    str(cfg.dists / "Release")], check=True)
    print("  已签名 InRelease / Release.gpg")


# ---------- gc 与体积守卫 ----------

def gc(cfg: Config) -> None:
    if not (cfg.root / "pool").is_dir():
        return
    groups: dict[tuple, list] = {}
    for deb in cfg.root.joinpath("pool").rglob("*.deb"):
        f = deb_fields(deb)
        groups.setdefault((f["Package"], f["Architecture"]), []).append((f["Version"], deb))
    for (pkg, arch), items in groups.items():
        items.sort(key=functools.cmp_to_key(lambda a, b: _dpkg_ver_cmp(a[0], b[0])),
                   reverse=True)
        for ver, deb in items[cfg.keep_versions:]:
            deb.unlink()
            print(f"  gc: 删除旧版 {deb.name}")
    # big-index 同规则（只删段落文件，Releases 上的资产提示手动清理）
    if cfg.big_index.is_dir():
        bgroups: dict[tuple, list] = {}
        for st in cfg.big_index.glob("*.stanza"):
            s = st.read_text()
            key = (_stanza_field(s, "Package"), _stanza_field(s, "Architecture"))
            bgroups.setdefault(key, []).append((_stanza_field(s, "Version"), st))
        for key, items in bgroups.items():
            items.sort(key=functools.cmp_to_key(lambda a, b: _dpkg_ver_cmp(a[0], b[0])),
                       reverse=True)
            for ver, st in items[cfg.keep_versions:]:
                st.unlink()
                print(f"  gc: 移除 big 索引 {st.name}（GitHub Release 资产请手动删除）")


def size_guard(cfg: Config) -> None:
    if not (cfg.root / "pool").is_dir():
        return
    for deb in cfg.root.joinpath("pool").rglob("*.deb"):
        if deb.stat().st_size > GITHUB_HARD_LIMIT:
            raise PublishError(
                f"{deb} 超过 GitHub 100MB 硬限制却在 pool/ 中，push 会被拒。"
                f"请调低 big_threshold_mb 后重新归置。")


# ---------- keyring 引导副本 / 大文件上传 / 主页 ----------

def update_keyring_latest(cfg: Config) -> None:
    debs = sorted(cfg.root.joinpath("pool").rglob("yukippa-keyring_*_all.deb"))
    if not debs:
        return
    latest = debs[0]
    for d in debs[1:]:
        if _dpkg_ver_cmp(deb_fields(d)["Version"], deb_fields(latest)["Version"]) > 0:
            latest = d
    shutil.copy2(latest, cfg.root / "yukippa-keyring_latest_all.deb")
    print(f"  引导副本 <- {latest.name}")


def upload_big(cfg: Config) -> None:
    if not cfg.big.is_dir():
        return
    files = sorted(cfg.big.glob("*.deb"))
    if not files:
        return
    tag = cfg.big_release_tag
    view = subprocess.run(["gh", "release", "view", tag, "--repo", cfg.github_repo],
                          capture_output=True)
    if view.returncode != 0:
        create = subprocess.run(
            ["gh", "release", "create", tag, "--repo", cfg.github_repo,
             "--title", "big file storage", "--notes",
             "存放超过 GitHub Pages 100MB 限制的 deb，经 ppa.072172.xyz/big/* 重定向分发"],
            capture_output=True, text=True)
        if create.returncode != 0:
            print(f"  ⚠ 无法创建 Release（仓库可能还没建），big 文件待上传: "
                  f"{[f.name for f in files]}\n    {create.stderr.strip()}")
            return
    for f in files:
        r = subprocess.run(["gh", "release", "upload", tag, str(f), "--clobber",
                            "--repo", cfg.github_repo], capture_output=True, text=True)
        if r.returncode == 0:
            print(f"  已上传 Releases: {f.name}")
        else:
            print(f"  ⚠ 上传失败 {f.name}: {r.stderr.strip()}")


def gen_index_html(cfg: Config, stanzas: list[str]) -> None:
    tpl = (cfg.root / "builder" / "templates" / "index.html").read_text()
    rows = []
    seen = set()
    for s in sorted(stanzas, key=lambda s: _stanza_field(s, "Package")):
        key = (_stanza_field(s, "Package"), _stanza_field(s, "Version"),
               _stanza_field(s, "Architecture"))
        if key in seen:
            continue
        seen.add(key)
        size_mb = int(_stanza_field(s, "Size") or 0) / 1048576
        desc = _stanza_field(s, "Description")
        rows.append(
            f"<tr><td><code>{key[0]}</code></td><td>{key[1]}</td>"
            f"<td>{key[2]}</td><td>{size_mb:.1f} MB</td><td>{desc}</td></tr>")
    html = (tpl.replace("{{ROWS}}", "\n".join(rows))
               .replace("{{COUNT}}", str(len(seen)))
               .replace("{{BASE_URL}}", cfg.base_url)
               .replace("{{FPR}}", cfg.signing_key)
               .replace("{{DATE}}", date.today().isoformat()))
    (cfg.root / "index.html").write_text(html)
    print(f"  index.html: {len(seen)} 个条目")


# ---------- 总入口 ----------

def publish(cfg: Config, sign: bool = True) -> None:
    print("== 归置 incoming ==")
    route_incoming(cfg)
    print("== 版本 gc ==")
    gc(cfg)
    size_guard(cfg)
    print("== 生成索引 ==")
    stanzas = gen_indices(cfg)
    print("== 生成并签名 Release ==")
    gen_release(cfg, sign=sign)
    print("== 引导副本与门面 ==")
    update_keyring_latest(cfg)
    gen_index_html(cfg, stanzas)
    print("== 上传 big 文件 ==")
    upload_big(cfg)
    print("发布产物就绪。提交并 push 后生效。")

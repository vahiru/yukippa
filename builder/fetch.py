"""下载（带缓存）、校验、解压。"""

import hashlib
import shutil
import tarfile
import urllib.request
import zipfile
from pathlib import Path


class FetchError(Exception):
    pass


def sha256sum(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, cache_dir: Path, expected_sha256: str | None = None) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / url.rstrip("/").rsplit("/", 1)[-1]
    if dest.is_file() and expected_sha256 and sha256sum(dest) == expected_sha256:
        print(f"  缓存命中 {dest.name}")
        return dest

    print(f"  下载 {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "yukippa-yk/1.0"})
    with urllib.request.urlopen(req) as resp, open(tmp, "wb") as f:
        shutil.copyfileobj(resp, f)
    tmp.rename(dest)

    if expected_sha256:
        actual = sha256sum(dest)
        if actual != expected_sha256:
            dest.unlink()
            raise FetchError(
                f"{dest.name} sha256 校验失败\n  期望 {expected_sha256}\n  实际 {actual}"
            )
    return dest


def extract(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    name = archive.name.lower()
    if name.endswith(".zip"):
        # 注意：zipfile 不保留可执行位，install 条目必须显式给 mode
        with zipfile.ZipFile(archive) as z:
            for m in z.namelist():
                p = (dest / m).resolve()
                if not p.is_relative_to(dest.resolve()):
                    raise FetchError(f"压缩包路径穿越: {m}")
            z.extractall(dest)
    elif any(name.endswith(s) for s in (".tar.gz", ".tgz", ".tar.xz", ".tar.zst", ".tar.bz2", ".tar")):
        with tarfile.open(archive) as t:
            t.extractall(dest, filter="data")
    else:
        raise FetchError(f"不认识的压缩格式: {archive.name}")

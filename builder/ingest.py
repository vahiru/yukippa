"""收录现成 .deb（AOSC 官方基建构建产物的主通道）。"""

import shutil
import subprocess
from pathlib import Path

from .config import Config
from .fetch import download
from .publish import deb_fields, record_provenance


def ingest(cfg: Config, targets: list[str]) -> None:
    cfg.incoming.mkdir(exist_ok=True)
    for t in targets:
        if t.startswith(("http://", "https://")):
            deb = download(t, cfg.root / "cache")
            source = t
        else:
            deb = Path(t)
            if not deb.is_file():
                raise SystemExit(f"文件不存在: {t}")
            source = f"local:{deb.resolve()}"

        f = deb_fields(deb)  # 顺带验证这是个合法 deb
        info = subprocess.run(["dpkg-deb", "-I", str(deb)],
                              check=True, capture_output=True, text=True).stdout
        print(f"  {f['Package']} {f['Version']} [{f['Architecture']}] "
              f"({deb.stat().st_size / 1048576:.1f} MB)")

        dest = cfg.incoming / deb.name
        shutil.copy2(deb, dest)
        record_provenance(cfg, dest, source)
    print(f"已收录 {len(targets)} 个 deb 到 incoming/，运行 ./yk publish 发布")

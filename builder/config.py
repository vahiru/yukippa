"""仓库全局配置（yukippa.toml）。"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    origin: str
    label: str
    suite: str
    codename: str
    component: str
    architectures: list[str]
    base_url: str
    github_repo: str
    maintainer: str
    signing_key: str = ""
    keep_versions: int = 2
    big_threshold_mb: int = 95
    big_release_tag: str = "big"

    # 派生路径
    root: Path = field(default=ROOT)

    @property
    def dists(self) -> Path:
        return self.root / "dists" / self.suite

    @property
    def pool(self) -> Path:
        return self.root / "pool" / self.component

    @property
    def big(self) -> Path:
        return self.root / "big"

    @property
    def big_index(self) -> Path:
        return self.root / "big-index"

    @property
    def incoming(self) -> Path:
        return self.root / "incoming"


def load_config() -> Config:
    with open(ROOT / "yukippa.toml", "rb") as f:
        data = tomllib.load(f)
    return Config(**data["repo"])

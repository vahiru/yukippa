# 向 yukippa 贡献软件包

## 你需要提交什么

一个 PR，内容是 `recipes/<包名>/recipe.toml`（模板见 `builder/templates/recipe.toml`）。
配方描述「从上游预编译产物重打包为 deb」：来源 URL、sha256、文件安装映射。

```toml
[package]
name = "foo"
version = "1.2.3"
architecture = "amd64"
section = "utils"
description = "One-line description"

[upstream]
type = "github-release"
repo = "owner/foo"
tag-strip-prefix = "v"

[[source]]
url = "https://github.com/owner/foo/releases/download/v${version}/foo-linux-x64.tar.gz"
sha256 = "…"

[[install]]
from = "foo-linux-x64/foo"
to = "/usr/bin/foo"
mode = "0755"
```

本地验证：`./yk lint <包名> && ./yk build <包名>`，然后
`dpkg-deb -c incoming/<包名>_*.deb` 确认文件布局。

## 收录标准

- 官方源没有、且短期内进不去的软件
- 上游有明确的发布渠道（GitHub Releases 等）与可校验的产物
- 遵守上游许可证允许再分发
- 二进制重打包优先；需要源码构建的包请先走 AOSC 官方基建（topic），
  产物可由维护者 `yk ingest` 收录

## 流程

1. Fork → 加配方 → PR
2. 维护者审核 merge 后，CI 自动构建、签名、发布
3. 包出现在 <https://ppa.072172.xyz>

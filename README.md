# yukippa ❄

**AOSC OS 用户仓库** — 收留进不了官方源的好软件。

一个面向 [oma](https://github.com/AOSC-Dev/oma) 的社区二进制仓库：官方源审核严格进不去的包、
用 AOSC 官方基建构建但 topic 已关闭的包，都可以在这里安家。

主页与包列表：**<https://ppa.072172.xyz>**

## 使用（只需一次引导）

```bash
curl -fLO https://ppa.072172.xyz/yukippa-keyring_latest_all.deb
sudo oma install ./yukippa-keyring_latest_all.deb
sudo oma refresh
```

之后与官方源无异：`oma install bun`、`oma upgrade` 会同时更新 yukippa 里的包
（包括 keyring 本身——换钥、迁移源地址都通过升级 `yukippa-keyring` 自动完成）。

<details>
<summary>不想装 keyring 包？手动配置</summary>

```bash
curl -fsSL https://ppa.072172.xyz/yukippa.asc | gpg --dearmor | sudo tee /usr/share/keyrings/yukippa.gpg >/dev/null
echo 'deb [signed-by=/usr/share/keyrings/yukippa.gpg] https://ppa.072172.xyz stable main' | sudo tee /etc/apt/sources.list.d/yukippa.list
sudo oma refresh
```
</details>

签名公钥指纹（请核对）：`F64A 3D20 94D7 BAA5 CF86  1F94 E05A B9A7 849B 2AD5`

支持架构：**amd64**、**arm64**

## 仓库结构

- `recipes/<包名>/recipe.toml` — 声明式配方（TOML）：从上游预编译产物重打包 deb
- `pool/` — 常规 deb（入 git，经 GitHub Pages 分发）
- `big/` + `big-index/` — 超过 95MB 的 deb 走「大文件通道」：文件存 GitHub Releases，
  经 `ppa.072172.xyz/big/*` 的 Cloudflare 重定向分发；`big-index/` 里只存索引段落
- `dists/` — apt 元数据（Packages 双架构索引、GPG 签名的 InRelease）
- `yk` — 构建/发布工具（零依赖 Python）

## 维护手册

```bash
./yk new <name>        # 配方脚手架
./yk lint --all        # 校验全部配方
./yk build <name>      # 按配方构建 → incoming/
./yk ingest <URL|文件>  # 收录现成 deb（如 AOSC topic 产物）→ incoming/
./yk publish           # incoming → pool/big → 索引 → 签名 → index.html
git add -A && git commit && git push
```

push 后 GitHub Pages 即更新（CDN 缓存约 10 分钟）。改动 `recipes/**` 并 push 时，
GitHub Actions 会自动构建并发布（私钥在 Actions `publish` Environment 的 Secrets 中）。
Actions 页面的 **Run workflow** 也可直接投喂 deb URL 远程收录。

### 注意事项

- **收录来源**：`pool/.provenance.toml` 记录每个 ingest 包的来源 URL 与 sha256，
  topic 仓库消失后仍可追溯。
- **私钥**：无密码专用钥，只签本仓库。若泄露：生成新钥 → 用旧钥照常发布一版含新公钥的
  `yukippa-keyring` → 用户升级后切换签名钥。
- **git 历史瘦身**：pool 里的 deb 会累积在 git 历史中（工作树由 gc 控制在每包 2 版）。
  仓库超过 ~1GB 时：`git checkout --orphan fresh && git commit && git push -f origin fresh:main`。
- **体积红线**：单文件 100MB 是 GitHub 硬限制，`yk publish` 会自动把 >95MB 的包路由到
  大文件通道并拦截违规文件入 git。

## 贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)：提 PR 加一个 `recipes/<name>/recipe.toml` 即可。

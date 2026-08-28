"""yk 命令行入口。"""

import argparse
import shutil
import sys

from .config import load_config, ROOT
from .recipe import load_recipe, all_recipe_dirs, RecipeError
from . import debbuild, ingest, publish


def _recipes_from_args(names: list[str], all_: bool):
    if all_:
        dirs = all_recipe_dirs(ROOT)
    else:
        dirs = [ROOT / "recipes" / n for n in names]
    return [load_recipe(d) for d in dirs]


def cmd_new(args):
    d = ROOT / "recipes" / args.name
    if d.exists():
        raise SystemExit(f"recipes/{args.name} 已存在")
    d.mkdir(parents=True)
    tpl = (ROOT / "builder" / "templates" / "recipe.toml").read_text()
    (d / "recipe.toml").write_text(tpl.replace("{{NAME}}", args.name))
    print(f"已创建 recipes/{args.name}/recipe.toml，编辑后 ./yk build {args.name}")


def cmd_lint(args):
    recipes = _recipes_from_args(args.names, args.all)
    for r in recipes:
        print(f"  ✓ {r.name} {r.full_version} [{r.architecture}]")
    print(f"{len(recipes)} 个配方校验通过")


def cmd_build(args):
    cfg = load_config()
    for r in _recipes_from_args(args.names, args.all):
        print(f"构建 {r.name} {r.full_version}")
        debbuild.build(r, cfg, force=args.force)


def cmd_ingest(args):
    ingest.ingest(load_config(), args.targets)


def cmd_publish(args):
    publish.publish(load_config(), sign=not args.no_sign)


def main():
    p = argparse.ArgumentParser(prog="yk", description="yukippa 仓库构建/发布工具")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("new", help="创建配方脚手架")
    s.add_argument("name")
    s.set_defaults(func=cmd_new)

    for name, func, hlp in (("lint", cmd_lint, "校验配方"),
                            ("build", cmd_build, "按配方构建 deb 到 incoming/")):
        s = sub.add_parser(name, help=hlp)
        s.add_argument("names", nargs="*")
        s.add_argument("--all", action="store_true")
        if name == "build":
            s.add_argument("--force", action="store_true")
        s.set_defaults(func=func)

    s = sub.add_parser("ingest", help="收录现成 deb（URL 或本地路径）到 incoming/")
    s.add_argument("targets", nargs="+")
    s.set_defaults(func=cmd_ingest)

    s = sub.add_parser("publish", help="incoming → pool/big → 索引 → 签名 → 门面")
    s.add_argument("--no-sign", action="store_true")
    s.set_defaults(func=cmd_publish)

    args = p.parse_args()
    try:
        args.func(args)
    except (RecipeError, publish.PublishError) as e:
        raise SystemExit(f"错误: {e}")

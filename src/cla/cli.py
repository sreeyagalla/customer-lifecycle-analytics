"""Command line: cla fetch | land | sample | build | site | all"""

from __future__ import annotations

import argparse

from . import paths


def cmd_fetch(args: argparse.Namespace) -> None:
    from . import ingest

    for src in ingest.SOURCES:
        if args.only and args.only not in src.path.name:
            continue
        p = ingest.fetch(src, force=args.force)
        print(f"ok  {src.name}: {p} (sha256 verified)")


def cmd_land(args: argparse.Namespace) -> None:
    from . import ingest

    lines = ingest.land_retail()
    print(f"landed {len(lines):,} retail lines -> {paths.RETAIL_PARQUET}")


def cmd_sample(args: argparse.Namespace) -> None:
    from . import sample

    s = sample.write_sample()
    print(f"sample: {len(s):,} real lines, {s['customer_id'].nunique():,} customers -> {paths.RETAIL_SAMPLE}")


def cmd_build(args: argparse.Namespace) -> None:
    from . import warehouse

    con = warehouse.build(source=args.source)
    for step, desc, n in con.execute("select * from data_quality").fetchall():
        print(f"{step:>2}. {desc:<72} {n:>10,}")
    con.close()


def cmd_site(args: argparse.Namespace) -> None:
    from . import analysis

    payload = analysis.write_site_data()
    print(f"wrote docs/data.js ({payload['source']} data, {len(payload['scorecard'])} scorecard rows, "
          f"{len(payload['hypotheses'])} hypotheses)")


def cmd_all(args: argparse.Namespace) -> None:
    cmd_build(args)
    cmd_site(args)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="cla", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download both public datasets and verify sha256")
    f.add_argument("--force", action="store_true")
    f.add_argument("--only", help="fetch one file, e.g. --only hillstrom")
    f.set_defaults(func=cmd_fetch)
    sub.add_parser("land", help="convert the retail workbook to parquet (~3 min)").set_defaults(func=cmd_land)
    sub.add_parser("sample", help="rebuild the committed 25%% customer sample").set_defaults(func=cmd_sample)
    for name, func, help_ in (("build", cmd_build, "run the SQL models into DuckDB and export marts"),
                              ("all", cmd_all, "build + site")):
        b = sub.add_parser(name, help=help_)
        b.add_argument("--source", choices=["full", "sample"], default="full")
        b.set_defaults(func=func)
    sub.add_parser("site", help="compute results and write docs/data.js").set_defaults(func=cmd_site)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

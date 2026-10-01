"""Command line interface.

    touchpath demo
    touchpath generate --users 20000 --out events.json
    touchpath report events.json
    touchpath attribute events.json --model markov --lookback 30
    touchpath compare events.json
    touchpath incrementality --treatment 50000/1150 --control 50000/1000
"""

from __future__ import annotations

import argparse
import json
import sys

from .generate import generate_events, generate_holdout
from .incrementality import holdout_test, required_sample_size
from .ingest import ingest_file, ingest_records
from .models import heuristic, markov, shapley
from .paths import build_paths, path_stats

ALL_MODELS = ("first", "last", "linear", "position", "time_decay", "markov", "shapley")


def _run_model(paths, name: str):
    if name == "markov":
        return markov.attribute(paths)
    if name == "shapley":
        return shapley.attribute(paths)
    return heuristic.attribute(paths, model=name)


def _parse_group(text: str):
    """'50000/1150' -> (50000, 1150)"""
    try:
        users, conversions = text.split("/")
        return int(users), int(conversions)
    except ValueError:
        raise argparse.ArgumentTypeError("expected USERS/CONVERSIONS, e.g. 50000/1150")


def cmd_generate(args):
    records, truth = generate_events(
        users=args.users, days=args.days, corruption_rate=args.corruption, seed=args.seed
    )
    with open(args.out, "w") as handle:
        json.dump(records, handle)
    print(f"wrote {len(records):,} records to {args.out}")
    print("ground truth influence share:")
    for channel, share in sorted(truth.items(), key=lambda kv: -kv[1]):
        print(f"  {channel:<18}{share:>7.1%}")


def cmd_report(args):
    events, report = ingest_file(args.events)
    print(report.summary())
    print()
    paths = build_paths(events, lookback_days=args.lookback)
    for key, value in path_stats(paths).items():
        print(f"{key:<22}{value}")


def cmd_attribute(args):
    events, report = ingest_file(args.events)
    paths = build_paths(events, lookback_days=args.lookback)
    if args.verbose:
        print(report.summary(), "\n")
    result = _run_model(paths, args.model).rounded()
    print(result.table())
    if args.json:
        print(json.dumps({"model": result.model, "revenue": result.revenue}, indent=2))


def cmd_compare(args):
    events, _ = ingest_file(args.events)
    paths = build_paths(events, lookback_days=args.lookback)
    models = args.models or list(ALL_MODELS)

    results = {name: _run_model(paths, name) for name in models}
    channels = sorted({channel for r in results.values() for channel in r.revenue})

    header = f"{'channel':<18}" + "".join(f"{name:>13}" for name in models)
    print(header)
    print("-" * len(header))
    for channel in channels:
        row = f"{channel:<18}"
        for name in models:
            share = results[name].share().get(channel, 0.0)
            row += f"{share:>12.1%} "
        print(row)


def cmd_incrementality(args):
    treatment_users, treatment_conversions = args.treatment
    control_users, control_conversions = args.control
    result = holdout_test(
        treatment_users, treatment_conversions, control_users, control_conversions, args.confidence
    )
    print(result.summary())


def cmd_sample_size(args):
    needed = required_sample_size(args.baseline, args.lift, args.confidence, args.power)
    print(f"{needed:,} users per group to detect a {args.lift:.0%} relative lift")


def cmd_demo(args):
    print("generating synthetic journeys with known ground truth...\n")
    records, truth = generate_events(users=args.users, corruption_rate=0.03, seed=11)

    events, report = ingest_records(records)
    print(report.summary())

    paths = build_paths(events, lookback_days=30)
    print()
    for key, value in path_stats(paths).items():
        print(f"{key:<22}{value}")

    models = ["last", "first", "linear", "markov", "shapley"]
    results = {name: _run_model(paths, name) for name in models}

    print("\nrevenue share by model (ground truth = the data generator's influence weights)\n")
    header = f"{'channel':<18}{'truth':>9}" + "".join(f"{name:>10}" for name in models)
    print(header)
    print("-" * len(header))
    for channel in sorted(truth):
        row = f"{channel:<18}{truth[channel]:>8.1%} "
        for name in models:
            row += f"{results[name].share().get(channel, 0.0):>9.1%} "
        print(row)

    print("\nmean absolute error against ground truth:")
    for name in models:
        shares = results[name].share()
        error = sum(abs(shares.get(c, 0.0) - truth[c]) for c in truth) / len(truth)
        print(f"  {name:<12}{error:.4f}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="touchpath", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("generate", help="write synthetic events with known ground truth")
    p.add_argument("--users", type=int, default=5000)
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--corruption", type=float, default=0.02)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default="events.json")
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("report", help="ingestion and path statistics")
    p.add_argument("events")
    p.add_argument("--lookback", type=int, default=30)
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("attribute", help="run one attribution model")
    p.add_argument("events")
    p.add_argument("--model", choices=ALL_MODELS, default="last")
    p.add_argument("--lookback", type=int, default=30)
    p.add_argument("--json", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_attribute)

    p = sub.add_parser("compare", help="compare models side by side")
    p.add_argument("events")
    p.add_argument("--lookback", type=int, default=30)
    p.add_argument("--models", nargs="+", choices=ALL_MODELS)
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("incrementality", help="holdout test statistics")
    p.add_argument("--treatment", type=_parse_group, required=True, metavar="USERS/CONVERSIONS")
    p.add_argument("--control", type=_parse_group, required=True, metavar="USERS/CONVERSIONS")
    p.add_argument("--confidence", type=float, default=0.95, choices=[0.80, 0.90, 0.95, 0.99])
    p.set_defaults(func=cmd_incrementality)

    p = sub.add_parser("sample-size", help="users per group needed for a holdout")
    p.add_argument("--baseline", type=float, required=True, help="baseline conversion rate, e.g. 0.02")
    p.add_argument("--lift", type=float, required=True, help="relative lift to detect, e.g. 0.10")
    p.add_argument("--confidence", type=float, default=0.95, choices=[0.80, 0.90, 0.95, 0.99])
    p.add_argument("--power", type=float, default=0.80, choices=[0.80, 0.90, 0.95])
    p.set_defaults(func=cmd_sample_size)

    p = sub.add_parser("demo", help="end to end run on synthetic data")
    p.add_argument("--users", type=int, default=20000)
    p.set_defaults(func=cmd_demo)

    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())

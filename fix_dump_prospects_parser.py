from pathlib import Path

cli_path = Path("src/upwork_triage/cli.py")
if not cli_path.exists():
    raise SystemExit("Run this from the repo root: C:\\WorkRepos\\Automat")

cli = cli_path.read_text(encoding="utf-8")

if "dump_prospects_parser = subparsers.add_parser(" in cli:
    print("dump-prospects parser already present; no change needed.")
    raise SystemExit(0)

anchor = """    import_enrichment_parser.add_argument(
        "input_path",
        help="Path to the edited enrichment CSV worksheet.",
    )
"""

insert = anchor + """    dump_prospects_parser = subparsers.add_parser(
        "dump-prospects",
        help="Render enriched prospect packets for manual or external-AI review.",
    )
    dump_prospects_parser.add_argument(
        "--limit",
        type=_positive_int_arg,
        help="Maximum number of enriched prospects to render.",
    )
"""

if anchor not in cli:
    raise SystemExit("Could not find import-enrichment-csv parser block in cli.py")

cli = cli.replace(anchor, insert, 1)
cli_path.write_text(cli, encoding="utf-8")

print("Inserted dump-prospects argparse parser.")
print("Try: py -m upwork_triage dump-prospects")

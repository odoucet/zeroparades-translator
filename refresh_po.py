"""
refresh_po.py
Merges new entries from a reference .po file into an existing translation .po file.

Entries already present in the output (matched by msgctxt) are left untouched.
Entries that exist in the input but not in the output are appended with an empty msgstr.

Usage:
    python refresh_po.py --input es_mx_reference.po --output fr_translation.po
"""

import argparse
import sys
from pathlib import Path

import polib


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add missing entries from a reference .po into an existing translation .po."
    )
    parser.add_argument("--input", required=True, help="Reference .po file (source of new entries)")
    parser.add_argument("--output", required=True, help="Translation .po file to update in-place")
    return parser.parse_args()


def validate_po_path(path_str: str, label: str) -> Path:
    path = Path(path_str)
    if path.suffix.lower() != ".po":
        print(f"Error: {label} must be a .po file, got: {path_str}", file=sys.stderr)
        sys.exit(1)
    if not path.exists():
        print(f"Error: {label} file not found: {path_str}", file=sys.stderr)
        sys.exit(1)
    return path


def main() -> None:
    args = parse_args()

    input_path = validate_po_path(args.input, "--input")
    output_path = validate_po_path(args.output, "--output")

    input_po = polib.pofile(str(input_path))
    output_po = polib.pofile(str(output_path))

    existing_keys = {entry.msgctxt for entry in output_po}

    added = 0
    for entry in input_po:
        if entry.msgctxt not in existing_keys:
            new_entry = polib.POEntry(
                msgctxt=entry.msgctxt,
                msgid=entry.msgid,
                msgstr="",
            )
            output_po.append(new_entry)
            existing_keys.add(entry.msgctxt)
            added += 1

    if added:
        output_po.save(str(output_path))
        print(f"Added {added} new entries to {output_path}.")
    else:
        print("No new entries to add — output is already up to date.")


if __name__ == "__main__":
    main()

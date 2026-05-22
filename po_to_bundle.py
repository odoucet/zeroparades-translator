"""
po_to_bundle.py
Injects a translated PO file into the Zero Parades asset bundle as a new
LocalizationTable asset. The original bundle is not modified — a patched copy
is written to the output path.

Usage:
    python po_to_bundle.py --bundle <path/to/bundle> --po fr_translation.po
                           --lang-code 72 --lang-name fr
                           --output <path/to/patched_bundle>

--bundle     Path to the original g5ibkj7vdwf2g67g_assets_all_*.bundle
--po         Translated .po file
--lang-code  Unity language enum int for the target language (see language_codes.py)
--lang-name  Short language identifier, e.g. "fr" — used in the asset name
--output     Where to write the patched bundle (default: overwrites the original)
"""

import argparse
import shutil
from pathlib import Path
import UnityPy
import polib

from language_codes import get_asset_path, get_code, confirmed_codes_help

TEMPLATE_LANG = "de"
TEMPLATE_ASSET_PATH = get_asset_path("de")


def po_to_bundle(bundle_path: Path, po_path: Path, lang_code: int,
                 lang_name: str, output_path: Path) -> None:
    """Inject translated PO entries into the bundle as a new LocalizationTable."""
    # Load translations
    po = polib.pofile(str(po_path))
    translations: dict[str, str] = {}
    untranslated = 0
    for entry in po:
        if entry.msgstr:
            translations[entry.msgctxt] = entry.msgstr
        else:
            translations[entry.msgctxt] = entry.msgid
            untranslated += 1

    if untranslated:
        print(
            f"Warning: {untranslated}/{len(po)} untranslated entries "
            "— source text used as fallback."
        )

    # Copy bundle if output differs from input
    if output_path != bundle_path:
        shutil.copy2(bundle_path, output_path)
        print(f"Copied bundle → {output_path}")

    print("Loading bundle…")
    env = UnityPy.load(str(output_path))

    # Read the template (German) to get the ordered key list
    if TEMPLATE_ASSET_PATH not in env.container:
        raise FileNotFoundError(f"Template asset not found: {TEMPLATE_ASSET_PATH}")

    template_obj = env.container[TEMPLATE_ASSET_PATH].read()
    ordered_keys = list(template_obj.m_data.m_keys)

    # Build new value list in key order
    new_values = [translations.get(k, "") for k in ordered_keys]

    # Modify the template object in place to become the new language
    template_obj.m_languageCode = lang_code
    template_obj.m_Name = f"{lang_name}LocalizationTable"
    template_obj.m_data.m_keys = ordered_keys
    template_obj.m_data.m_values = new_values
    template_obj.save()

    # Write patched bundle
    with open(output_path, "wb") as f:
        f.write(env.file.save())

    print(f"Patched bundle written → {output_path}")
    print(
        f"  Asset: {lang_name}LocalizationTable  "
        f"lang_code={lang_code}  entries={len(ordered_keys)}"
    )


def main():
    """Parse arguments and run po_to_bundle."""
    parser = argparse.ArgumentParser(description="Inject translated PO into the game bundle")
    parser.add_argument("--bundle", required=True, help="Path to the original .bundle file")
    parser.add_argument("--po", required=True, help="Translated .po file")
    parser.add_argument("--lang-code", type=int, required=True,
                        help=f"Unity language enum int. Confirmed: {confirmed_codes_help()}. "
                             "Use language_codes.py get_code() for predicted values.")
    parser.add_argument("--lang-name", default="fr", help="Language prefix, e.g. fr (default: fr)")
    parser.add_argument("--output", help="Output bundle path (default: overwrite original)")
    args = parser.parse_args()

    bundle = Path(args.bundle)
    output = Path(args.output) if args.output else bundle

    po_to_bundle(bundle, Path(args.po), args.lang_code, args.lang_name, output)


if __name__ == "__main__":
    main()

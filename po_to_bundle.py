"""
po_to_bundle.py
Injects a translated PO file into the Zero Parades asset bundle as a new
LocalizationTable asset. A .bak backup of the original bundle and catalog.json
are always created before any modification.

Usage:
    python po_to_bundle.py --bundle <path/to/bundle> --po fr_translation.po
                           --lang-name fr
                           --output <path/to/patched_bundle>

--bundle     Path to the original g5ibkj7vdwf2g67g_assets_all_*.bundle
--po         Translated .po file
--lang-name  Locale code, e.g. "fr" — used in the asset name and to look up
             the language enum int from language_codes.py
--output     Where to write the patched bundle (default: overwrites the original)
"""

import argparse
import base64
import json
import logging
import re
import shutil
from pathlib import Path

import UnityPy
import polib

from language_codes import get_asset_path, get_code, DISPLAY_NAMES

logger = logging.getLogger(__name__)

# "m_Crc": encoded in UTF-16LE — used to find and zero CRC fields in catalog.json
_CRC_FIELD_UTF16 = b'\x22\x00\x6d\x00\x5f\x00\x43\x00\x72\x00\x63\x00\x22\x00\x3a\x00'
_CRC_PATTERN = re.compile(_CRC_FIELD_UTF16 + b'(?:[\x30-\x39]\x00)+')

TEMPLATE_LANG = "de"
TEMPLATE_ASSET_PATH = get_asset_path("de")


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _patch_catalog_crc(catalog_path: Path) -> None:
    """Disable bundle CRC checks in catalog.json by zeroing all m_Crc fields.

    m_ExtraDataString is a base64-encoded blob of UTF-16LE JSON records.
    Setting m_Crc to 0 makes Unity skip integrity verification at load time.
    Each CRC digit sequence is replaced in-place (same byte length) so the
    surrounding length fields stay valid.
    """
    if not catalog_path.exists():
        logger.warning("catalog.json not found at %s — CRC not updated", catalog_path)
        return

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    extra = base64.b64decode(catalog["m_ExtraDataString"])

    def _zero_crc(m: re.Match) -> bytes:
        n = (len(m.group(0)) - len(_CRC_FIELD_UTF16)) // 2
        return _CRC_FIELD_UTF16 + b'\x20\x00' * (n - 1) + b'\x30\x00'

    patched = _CRC_PATTERN.sub(_zero_crc, extra)
    if patched == extra:
        logger.warning("No m_Crc fields found in catalog — nothing patched")
        return

    catalog["m_ExtraDataString"] = base64.b64encode(patched).decode("ascii")

    backup = catalog_path.with_suffix(".json.bak")
    if not backup.exists():
        shutil.copy2(catalog_path, backup)
        logger.info("Catalog backup → %s", backup)

    catalog_path.write_text(json.dumps(catalog, separators=(",", ":")), encoding="utf-8")
    logger.info("Catalog CRC disabled — Unity will skip bundle integrity checks")


def po_to_bundle(bundle_path: Path, po_path: Path, lang_code: int,
                 lang_name: str, output_path: Path) -> None:
    """Inject translated PO entries into the bundle as a new LocalizationTable."""
    po = polib.pofile(str(po_path))
    translations: dict[str, str] = {}
    untranslated = 0
    for entry in po:
        if entry.msgstr:
            translations[entry.msgctxt] = entry.msgstr
        else:
            translations[entry.msgctxt] = entry.msgid
            untranslated += 1

    total_entries = len(po)
    if untranslated:
        logger.warning(
            "%d/%d entries untranslated (%.1f%%) — source text will be used as fallback.",
            untranslated, total_entries, untranslated / total_entries * 100,
        )
    else:
        logger.info("All %d entries translated.", total_entries)

    # Always back up the original bundle before touching it
    backup_path = bundle_path.with_suffix(bundle_path.suffix + ".bak")
    if not backup_path.exists():
        shutil.copy2(bundle_path, backup_path)
        logger.info("Bundle backup → %s", backup_path)

    if output_path != bundle_path:
        shutil.copy2(bundle_path, output_path)
        logger.info("Copied bundle → %s", output_path)

    logger.info("Loading bundle…")
    env = UnityPy.load(str(output_path))

    if TEMPLATE_ASSET_PATH not in env.container:
        raise FileNotFoundError(f"Template asset not found: {TEMPLATE_ASSET_PATH}")

    template_obj = env.container[TEMPLATE_ASSET_PATH].read()
    ordered_keys = list(template_obj.m_data.m_keys)

    new_values = [translations.get(k, "") for k in ordered_keys]

    template_obj.m_languageCode = lang_code
    template_obj.m_Name = f"{lang_name}LocalizationTable"
    template_obj.m_data.m_keys = ordered_keys
    template_obj.m_data.m_values = new_values
    template_obj.save()

    original_size = bundle_path.stat().st_size
    with open(output_path, "wb") as f:
        f.write(env.file.save(packer="lz4"))
    output_size = output_path.stat().st_size

    logger.info("Patched bundle written → %s", output_path)
    logger.info(
        "  Asset: %sLocalizationTable  lang_code=%d  entries=%d",
        lang_name, lang_code, len(ordered_keys),
    )
    logger.info("  Size: %s → %s", _fmt_size(original_size), _fmt_size(output_size))

    # Update catalog.json so Addressables doesn't reject the modified bundle
    catalog_path = output_path.parent.parent / "catalog.json"
    logger.info("Patching catalog.json CRC…")
    _patch_catalog_crc(catalog_path)
    logger.info("Done — bundle and catalog.json updated.")


def main():
    """Parse arguments and run po_to_bundle."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="Inject translated PO into the game bundle")
    parser.add_argument("--bundle", required=True, help="Path to the original .bundle file")
    parser.add_argument("--po", required=True, help="Translated .po file")
    parser.add_argument("--lang-name", required=True,
                        help="Locale code, e.g. fr, it, de. "
                             "The language enum int is derived automatically "
                             "from language_codes.py.")
    parser.add_argument("--output", help="Output bundle path (default: overwrite original)")
    args = parser.parse_args()

    lang_code, source = get_code(args.lang_name)
    display = DISPLAY_NAMES.get(args.lang_name, args.lang_name)

    if source == "confirmed":
        logger.info("Language: %s (%s)  lang_code=%d  [confirmed]",
                    display, args.lang_name, lang_code)
    elif source == "formula":
        logger.warning(
            "Language: %s (%s)  lang_code=%d  [formula-derived, unconfirmed — "
            "verify that the language appears in Settings → Language in-game]",
            display, args.lang_name, lang_code,
        )
    else:
        parser.error(
            f"No language code known for {args.lang_name!r}. "
            "Add it to language_codes.py or check the locale spelling."
        )

    bundle = Path(args.bundle)
    output = Path(args.output) if args.output else bundle

    po_to_bundle(bundle, Path(args.po), lang_code, args.lang_name, output)


if __name__ == "__main__":
    main()

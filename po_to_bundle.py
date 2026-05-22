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
import struct
import zlib
from pathlib import Path

import UnityPy
import polib

from language_codes import get_asset_path, get_code, DISPLAY_NAMES

logger = logging.getLogger(__name__)

# Header that prefixes every AssetBundleRequestOptions record in m_ExtraDataString
_CATALOG_RECORD_HEADER = (
    b"LUnity.ResourceManager, Version=0.0.0.0, Culture=neutral, "
    b"PublicKeyToken=nullJUnityEngine.ResourceManagement.ResourceProviders"
    b".AssetBundleRequestOptions"
)

TEMPLATE_LANG = "de"
TEMPLATE_ASSET_PATH = get_asset_path("de")


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _patch_catalog_crc(catalog_path: Path, bundle_path: Path) -> None:
    """Recompute the CRC32 of the patched bundle and update it in catalog.json.

    The catalog stores per-bundle options (including CRC) in m_ExtraDataString as
    a base64-encoded binary blob. Each record is:
        [152-byte ASCII type header] [4-byte LE uint32 = JSON byte count] [UTF-16LE JSON]
    The JSON contains "m_Crc":<uint32> which Addressables checks at load time.
    A mismatch causes a RemoteProviderException — hence this patch.
    """
    if not catalog_path.exists():
        logger.warning("catalog.json not found at %s — CRC not updated", catalog_path)
        return

    new_crc = zlib.crc32(bundle_path.read_bytes()) & 0xFFFFFFFF
    bundle_stem = bundle_path.stem

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))

    bundle_ids = [v for v in catalog["m_InternalIds"] if ".bundle" in str(v)]
    bundle_idx = next((i for i, v in enumerate(bundle_ids) if bundle_stem in str(v)), None)
    if bundle_idx is None:
        logger.warning("Bundle %r not found in catalog — CRC not updated", bundle_stem)
        return

    hlen = len(_CATALOG_RECORD_HEADER)
    extra = bytearray(base64.b64decode(catalog["m_ExtraDataString"]))
    offsets = [m.start() for m in re.finditer(re.escape(_CATALOG_RECORD_HEADER), extra)]

    if bundle_idx >= len(offsets):
        logger.warning("Record index %d out of range in catalog — CRC not updated", bundle_idx)
        return

    rec = offsets[bundle_idx]
    json_len = struct.unpack_from("<I", extra, rec + hlen)[0]
    json_start = rec + hlen + 4
    json_str = extra[json_start: json_start + json_len].decode("utf-16-le")

    m = re.search(r'"m_Crc":(\d+)', json_str)
    if not m:
        logger.warning("m_Crc field not found in catalog record — CRC not updated")
        return
    old_crc = int(m.group(1))

    new_json_str = re.sub(r'"m_Crc":\d+', f'"m_Crc":{new_crc}', json_str)
    new_json_bytes = new_json_str.encode("utf-16-le")

    # Patch binary: update length field + replace JSON bytes
    extra[rec + hlen: rec + hlen + 4] = struct.pack("<I", len(new_json_bytes))
    extra[json_start: json_start + json_len] = new_json_bytes

    catalog["m_ExtraDataString"] = base64.b64encode(bytes(extra)).decode("ascii")

    backup = catalog_path.with_suffix(".json.bak")
    if not backup.exists():
        shutil.copy2(catalog_path, backup)
        logger.info("Catalog backup → %s", backup)

    catalog_path.write_text(json.dumps(catalog, separators=(",", ":")), encoding="utf-8")
    logger.info("Catalog CRC updated: %d → %d", old_crc, new_crc)


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
    _patch_catalog_crc(catalog_path, output_path)
    logger.info("Done — bundle and catalog.json updated.")


def main():
    """Parse arguments and run po_to_bundle."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="Inject translated PO into the game bundle")
    parser.add_argument("--bundle", required=True, help="Path to the original .bundle file")
    parser.add_argument("--po", required=True, help="Translated .po file")
    parser.add_argument("--lang-name", required=True,
                        help="Locale code, e.g. fr, it, de. "
                             "The language enum int is derived automatically from language_codes.py.")
    parser.add_argument("--output", help="Output bundle path (default: overwrite original)")
    args = parser.parse_args()

    lang_code, source = get_code(args.lang_name)
    display = DISPLAY_NAMES.get(args.lang_name, args.lang_name)

    if source == "confirmed":
        logger.info("Language: %s (%s)  lang_code=%d  [confirmed]", display, args.lang_name, lang_code)
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

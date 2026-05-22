"""
bundle_to_po.py
Extracts a LocalizationTable directly from the Zero Parades asset bundle
and writes a PO file ready for translation. No AssetRipper needed.

Usage:
    python bundle_to_po.py --bundle <path/to/bundle> --lang de --output fr_translation.po

--bundle  Path to g5ibkj7vdwf2g67g_assets_all_*.bundle
--lang    Source language to use as msgid (de, es_mx, ru, zh_cn). Default: de
--output  Output .po file path
"""

import argparse
import logging
from pathlib import Path

import UnityPy
import polib

from language_codes import ASSET_PATHS, confirmed_codes_help

logger = logging.getLogger(__name__)


def bundle_to_po(bundle_path: Path, lang: str, output_path: Path) -> None:
    """Extract a LocalizationTable from the bundle and write a PO file."""
    if lang not in ASSET_PATHS:
        raise ValueError(f"Unknown source language '{lang}'. Choose from: {list(ASSET_PATHS)}")

    logger.info("Loading bundle: %s", bundle_path)
    env = UnityPy.load(str(bundle_path))

    asset_path = ASSET_PATHS[lang]
    if asset_path not in env.container:
        raise FileNotFoundError(f"Asset not found in bundle: {asset_path}")

    obj = env.container[asset_path].read()
    keys = obj.m_data.m_keys
    values = obj.m_data.m_values
    lang_code = obj.m_languageCode

    logger.info("Source: %s  lang_code=%d  entries=%d", obj.m_Name, lang_code, len(keys))

    po = polib.POFile()
    po.metadata = {
        "Project-Id-Version": "Zero Parades (unofficial translation)",
        "POT-Creation-Date": "",
        "PO-Revision-Date": "",
        "Last-Translator": "",
        "Language-Team": "",
        "Language": "fr",
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=UTF-8",
        "Content-Transfer-Encoding": "8bit",
        "Source-Language": lang,
        "Source-Language-Code": str(lang_code),
    }

    for key, value in zip(keys, values):
        po.append(polib.POEntry(
            msgctxt=key,
            msgid=value,
            msgstr="",
        ))

    po.save(str(output_path))
    logger.info("Wrote %d entries to %s", len(po), output_path)


def main():
    """Parse arguments and run bundle_to_po."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="Extract LocalizationTable from bundle to PO")
    parser.add_argument("--bundle", required=True, help="Path to the .bundle file")
    parser.add_argument("--lang", default="de", choices=list(ASSET_PATHS),
                        help=f"Source language (default: de). "
                             f"Confirmed codes: {confirmed_codes_help()}")
    parser.add_argument("--output", required=True, help="Output .po file path")
    args = parser.parse_args()

    bundle_to_po(Path(args.bundle), args.lang, Path(args.output))


if __name__ == "__main__":
    main()

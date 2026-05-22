"""
language_codes.py — FELD engine language reference for Zero Parades.

Single source of truth for:
  - locale → bundle asset path    (ASSET_PATHS)
  - locale → display name         (DISPLAY_NAMES)
  - locale → m_languageCode int   (CONFIRMED / FORMULA_DERIVED)

Imported by bundle_to_po.py, po_to_bundle.py, and translate_po.py.

────────────────────────────────────────────────────────────────────────────────
HOW THE CODES WERE FOUND
────────────────────────────────────────────────────────────────────────────────

1. CONFIRMED CODES — read directly from the `m_languageCode:` field in each
   LocalizationTable.asset, exported from the game bundle via AssetRipper.

2. LOCALE ENUM — the full member-name list of the `LanguageIsoCode` enum was
   extracted from the IL2CPP metadata file:
       ZeroParades_Data/il2cpp_data/Metadata/global-metadata.dat
   Searching for the null-terminated string `"LanguageIsoCode"` at absolute
   offset 0x003029b2 reveals the enum declared in ZAUM.FELD.Data.Localization.
   It has 104 members (af … zu).

3. FORMULA — for 2-character neutral locale codes the integer value follows:
       code = sum(ord(c) for c in locale) % 144
   Verified: "de" → (100+101) % 144 = 57 ✓   "ru" → (114+117) % 144 = 87 ✓
   This formula does NOT apply to regional codes (zh_cn, es_mx).
"""

# ── Asset paths (only for languages confirmed to exist in the bundle) ─────────

ASSET_PATHS: dict[str, str] = {
    "de":    "Assets/FELDRuntime/Scriptables/Main/Localization/de/deLocalizationTable.asset",
    "es_mx": "Assets/FELDRuntime/Scriptables/Main/Localization/es_mx/es_mxLocalizationTable.asset",
    "ru":    "Assets/FELDRuntime/Scriptables/Main/Localization/ru/ruLocalizationTable.asset",
    "zh_cn": "Assets/FELDRuntime/Scriptables/Main/Localization/zh_cn/zh_cnLocalizationTable.asset",
}

# ── Human-readable display names ──────────────────────────────────────────────

DISPLAY_NAMES: dict[str, str] = {
    "de":    "German",
    "es_mx": "Mexican Spanish",
    "ru":    "Russian",
    "zh_cn": "Simplified Chinese",
    "fr":    "French",
    "it":    "Italian",
    "ja":    "Japanese",
    "ko":    "Korean",
    "pt":    "Portuguese",
    "pt_br": "Brazilian Portuguese",
    "nl":    "Dutch",
    "tr":    "Turkish",
    "pl":    "Polish",
    "sv":    "Swedish",
    "nb":    "Norwegian",
    "da":    "Danish",
    "fi":    "Finnish",
    "cs":    "Czech",
    "hu":    "Hungarian",
    "ro":    "Romanian",
    "uk":    "Ukrainian",
    "ar":    "Arabic",
}

# ── Confirmed m_languageCode values (from game assets) ────────────────────────

CONFIRMED: dict[str, int] = {
    "zh_cn": 25,
    "de":    57,
    "ru":    87,
    "es_mx": 103,
    # "en" is the default language — no LocalizationTable asset exists for it.
}

# ── Formula-derived codes (sum(ord) % 144) — UNCONFIRMED, needs in-game test ──

FORMULA_DERIVED: dict[str, int] = {
    "da": 53,
    "ja": 59,
    "fi": 63,
    "nb": 64,
    "cs": 71,
    "fr": 72,   # most useful for fan translations
    "hu": 73,
    "ko": 74,   # collision with nl
    "nl": 74,   # collision with ko
    "pl": 76,
    "it": 77,
    "ro": 78,
    "pt": 84,
    "tr": 86,
    "sv": 89,
    "uk": 93,
}

# ── Full LanguageIsoCode enum member list (from IL2CPP metadata 0x003029b2) ───

LOCALE_ENUM_MEMBERS: list[str] = [
    "af", "sq",
    "ar_dz", "ar_bh", "ar_eg", "ar_iq", "ar_jo", "ar_kw", "ar_lb", "ar_ly",
    "ar_ma", "ar_om", "ar_qa", "ar_sa", "ar_sy", "ar_tn", "ar_ae", "ar_ye",
    "eu", "be", "bg",
    "zh", "zh_hk", "zh_cn", "zh_sg", "zh_tw",
    "da", "nl_be",
    "en", "en_au", "en_bz", "en_ca", "en_ie", "en_jm", "en_nz", "en_za",
    "en_tt", "en_gb", "en_us",
    "et", "fo", "fa",
    "fr_be", "fr_ca", "fr_lu", "fr", "fr_ch",
    "gd",
    "de_at", "de_li", "de_lu", "de_ch",
    "he", "hu", "is", "ga", "it_ch",
    "ja", "ko", "ku",
    "lv", "lt", "mk", "ml", "mt",
    "no", "nb", "nn",
    "pt_br",
    "pa", "ro", "ro_md",
    "ru", "ru_md",
    "sr", "sk", "sl",
    "es_ar", "es_bo", "es_cl", "es_co", "es_cr", "es_do", "es_ec",
    "es_sv", "es_gt", "es_hn", "es_mx", "es_ni", "es_pa", "es_py",
    "es_pe", "es_pr", "es_uy", "es_ve",
    "sv_fi",
    "th", "tn", "ua", "ur", "cy", "xh", "ji", "zu",
]

# ── Public helpers ─────────────────────────────────────────────────────────────

def get_code(locale: str) -> tuple[int, str]:
    """Return (code, source) for a locale.

    source is one of: 'confirmed', 'formula', 'unknown'.
    Use the source to warn users when the code is not confirmed.
    """
    if locale in CONFIRMED:
        return CONFIRMED[locale], "confirmed"
    if locale in FORMULA_DERIVED:
        return FORMULA_DERIVED[locale], "formula"
    if len(locale) == 2:
        code = sum(ord(c) for c in locale) % 144
        return code, "formula"
    return -1, "unknown"


def get_asset_path(locale: str) -> str:
    """Return the in-bundle asset path for a confirmed source locale."""
    if locale not in ASSET_PATHS:
        raise KeyError(
            f"No known asset path for locale {locale!r}. "
            f"Available: {list(ASSET_PATHS)}"
        )
    return ASSET_PATHS[locale]


def confirmed_codes_help() -> str:
    """One-line string listing all confirmed codes, for argparse help text."""
    return ", ".join(f"{k}={v}" for k, v in sorted(CONFIRMED.items(), key=lambda x: x[1]))


if __name__ == "__main__":
    print("Confirmed codes:")
    for locale, code in sorted(CONFIRMED.items(), key=lambda x: x[1]):
        print(f"  {code:4d}  {locale:8s}  {DISPLAY_NAMES.get(locale, '')}")

    print("\nFormula-derived codes (unconfirmed):")
    for locale, code in sorted(FORMULA_DERIVED.items(), key=lambda x: x[1]):
        name = DISPLAY_NAMES.get(locale, "")
        print(f"  {code:4d}  {locale:8s}  {name}")

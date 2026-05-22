# Zero Parades — Community Translation Toolkit

> **Work In Progress** — The toolkit is functional for individual steps (extract, translate, inject) but has not yet been validated end-to-end on a full playthrough. Expect rough edges. [Watch this repository](https://github.com/odoucet/zeroparades-translator/watchers) to be notified of updates.

Unofficial tools to create community translations for *Zero Parades*. The scripts extract game text into a standard `.po` file, translate it (manually or via LLM), and re-inject the result into the game.

> **Legal note:** These scripts contain **no game text**. They only read from and write to a copy of the game you legally own. A legitimate, installed copy of the game is required.

---

## Quick Start

**1. Install dependencies**

```bash
pip install UnityPy polib tqdm
pip install anthropic   # if using Claude
pip install openai      # if using OpenAI or a local AI server
```

**2. Extract the text**

```bash
python bundle_to_po.py \
  --bundle "ZeroParades_Data/StreamingAssets/aa/StandaloneWindows64/g5ibkj7vdwf2g67g_assets_all_df231fe1e06c36a5cb63c87a08cd9257.bundle" \
  --lang es_mx \
  --output my_translation.po
```

`es_mx` (Mexican Spanish) is the recommended source — the most widely spoken language available after English (which is not directly accessible). Also available: `de`, `ru`, `zh_cn`.

**3. Translate**

*Option A — LLM (automated, then review):*

```bash
# OpenAI (set OPENAI_API_KEY first)
python translate_po.py --input my_translation.po --output my_translation.po \
    --target-lang French

# OpenRouter (set OPENAI_API_KEY to your OpenRouter key)
export OPENAI_API_KEY=sk-or-...
python translate_po.py --input my_translation.po --output my_translation.po \
    --target-lang French --base-url https://openrouter.ai/api/v1 \
    --model mistralai/mistral-7b-instruct \
    --header "HTTP-Referer=https://yoursite.com" --header "X-Title=Zero Parades Translator"

# Local AI (LM Studio, LocalAI, Ollama… — no key needed)
python translate_po.py --input my_translation.po --output my_translation.po \
    --target-lang French --base-url http://127.0.0.1:8080/v1 --model your-model-name
```

Interrupted runs resume automatically — already-translated entries are skipped.

*Option B — Poedit (manual):*

Open `my_translation.po` in **[Poedit](https://poedit.net/)** (free). `msgid` is the source text, `msgstr` is where your translation goes. Never modify `msgctxt`.

**4. Inject back into the game**

```bash
python po_to_bundle.py \
  --bundle "ZeroParades_Data/StreamingAssets/aa/StandaloneWindows64/g5ibkj7vdwf2g67g_assets_all_df231fe1e06c36a5cb63c87a08cd9257.bundle" \
  --po my_translation.po \
  --lang-code 72 \
  --lang-name fr
```

> **`--lang-code`:** The game uses a custom language enum — `72` is the predicted value for French (see [Language codes](#language-codes) for the derivation and other languages).

Untranslated entries fall back to the source language text automatically.

---

## How it works — in depth

### The localization system

Zero Parades uses a custom dialogue and localization engine called **FELDRuntime**, built on top of Unity's [Addressable Assets](https://docs.unity3d.com/Packages/com.unity.addressables@latest) system.

All game data is packed inside LZ4HC-compressed Unity asset bundles under:

```
ZeroParades_Data\StreamingAssets\aa\StandaloneWindows64\
```

The single bundle containing all localization data is:

```
g5ibkj7vdwf2g67g_assets_all_df231fe1e06c36a5cb63c87a08cd9257.bundle   (~27 MB)
```

Inside this bundle, the translation system relies on two asset types:

#### LocalizationTable assets — one per language

```
Assets/FELDRuntime/Scriptables/Main/Localization/
    de/deLocalizationTable.asset        ← German
    es_mx/es_mxLocalizationTable.asset  ← Mexican Spanish
    ru/ruLocalizationTable.asset         ← Russian
    zh_cn/zh_cnLocalizationTable.asset   ← Simplified Chinese
```

Each asset is a Unity MonoBehaviour with two parallel arrays:

```yaml
m_languageCode: 103   # integer enum value identifying the language
m_data:
  m_keys:
  - basic_dress_shirt/character_full_name
  - ha8ta0kt_rvh5ods/dialog_lines
  - ...                                   # ~70 000 keys
  m_values:
  - Camisa de vestir básica
  - Arrugada y aún con el aroma de *doctor triste*.
  - ...                                   # one translated string per key
```

`m_keys[i]` maps to `m_values[i]`. Adding a new language means adding a new asset with a different `m_languageCode`.

#### Chunk assets — dialogue graph data

```
Assets/FELDRuntime/Scriptables/Main/Chunks/
    Chunk-flow-0000.asset … Chunk-flow-0193.asset  (main dialogue flows)
    Chunk-bark-flow-0000.asset …                   (ambient world lines)
    Chunk-dramatic-encounter-0000.asset …
    Chunk-orb-flow-0000.asset …
    Chunk-process-thought-flow-0000.asset …
```

These define the dialogue graph structure and embed the **English source text** in a proprietary C# class that cannot be deserialized without the compiled assemblies. The LocalizationTable assets override this text for each supported language.

#### Scale of the translation work

All language tables share the same ~70 000 keys:

| Entry type | Count | Content |
|------------|------:|---------|
| `dialog_lines` | **64 340** | Dialogue lines (spoken and written) |
| `explanation` | 1 749 | Skill and condition descriptions |
| `alternative1/2/3` | ~1 000 | Dialogue option variants |
| `character_full_name` | 561 | NPC and object names |
| `entry` | 440 | Journal entries |
| `description` / `fullDescription` | ~470 | Item descriptions |
| Other | ~1 356 | UI labels, misc strings |
| **Total** | **~69 916** | |

---

### Why UnityPy instead of AssetRipper

Tools like AssetRipper deserialize Unity assets into YAML files that then need converting again before re-injection. **UnityPy** reads the bundle's embedded TypeTree directly in Python — no intermediate files, no GUI. The full pipeline is two command-line calls.

---

### Scripts

| Script | Description |
|--------|-------------|
| `bundle_to_po.py` | Extracts a LocalizationTable from the bundle into a `.po` file |
| `translate_po.py` | Translates a `.po` file with an LLM, with resume support |
| `po_to_bundle.py` | Injects a translated `.po` file back into the bundle |
| `llm_translation_context.md` | Game lore and terminology guide injected into every LLM call |

---

### LLM translation — `translate_po.py`

Sends strings to an LLM in batches of 25, saves a checkpoint every 250 entries, and automatically skips already-translated entries on resume.

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--input` | required | Source `.po` file |
| `--output` | required | Output `.po` (created or resumed) |
| `--target-lang` | required | Target language in plain English, e.g. `French` |
| `--source-lang` | `es_mx` | Source language code (`es_mx`, `de`, `ru`, `zh_cn`) |
| `--model` | `gpt-4o-mini` | Model name override |
| `--base-url` | — | OpenAI-compatible endpoint (local AI or OpenRouter) |
| `--header` | — | Extra HTTP header, repeatable: `--header "HTTP-Referer=https://…"` |
| `--batch-size` | `25` | Strings per API call |
| `--save-every` | `10` | Checkpoint interval in batches |

Default model: `gpt-4o-mini`.

**Cost estimate** for ~70 000 strings (includes lore context ~1 600 tokens injected per call):

| Model | Estimated cost |
|-------|---------------|
| `gpt-4o-mini` | ~$2–3 |
| OpenRouter (varies by model) | ~$1–10 |
| Local AI | free |

API key is read from the `OPENAI_API_KEY` environment variable. For OpenRouter, set it to your OpenRouter key; for local AI with no authentication, the variable can be omitted.

The game lore and terminology guide (`llm_translation_context.md`) is automatically prepended to every API call to maintain consistent tone and proper noun handling.

---

### Language codes

The game uses a **custom integer language enum** in FELDRuntime (`m_languageCode` field in each `LocalizationTable.asset`).

#### Confirmed codes — read directly from the bundle assets

| Language | Locale | Code |
|----------|--------|-----:|
| Chinese Simplified | `zh_cn` | **25** |
| German | `de` | **57** |
| Russian | `ru` | **87** |
| Spanish (Mexico) | `es_mx` | **103** |

English is the default — no `LocalizationTable` asset exists for it (text is embedded in `Chunk-*.asset` dialogue graph files).

#### Predicted codes — formula-derived, unconfirmed in-game

For **2-character neutral locale codes**, the integer value follows:

```
code = sum(ord(c) for c in locale) % 144
```

Verified: `de` → (100+101) % 144 = **57** ✓, `ru` → (114+117) % 144 = **87** ✓

> This formula does **not** apply to regional codes like `zh_cn` or `es_mx`, which use a different, unknown mechanism.

| Language | Locale | Predicted code | Collision |
|----------|--------|:--------------:|-----------|
| French | `fr` | **72** | same formula as `es` (unused — game uses `es_mx`) |
| Japanese | `ja` | **59** | — |
| Finnish | `fi` | **63** | — |
| Norwegian | `nb` | **64** | — |
| Czech | `cs` | **71** | — |
| Hungarian | `hu` | **73** | — |
| Korean | `ko` | **74** | same as `nl` |
| Dutch | `nl` | **74** | same as `ko` |
| Polish | `pl` | **76** | — |
| Italian | `it` | **77** | — |
| Romanian | `ro` | **78** | — |
| Portuguese | `pt` | **84** | — |
| Turkish | `tr` | **86** | — |
| Swedish | `sv` | **89** | — |
| Ukrainian | `uk` | **93** | — |
| Danish | `da` | **53** | — |

> **How to confirm a code:** inject a test asset with the predicted code, launch the game, and check whether the new language appears in Settings → Language. If it does not, try the next candidate.

#### Where these codes come from

1. **Confirmed codes** — `m_languageCode:` field in each exported `*LocalizationTable.asset` (AssetRipper export of the main bundle).

2. **The locale enum** — The full list of locale names was extracted from the IL2CPP metadata file at:
   ```
   ZeroParades_Data/il2cpp_data/Metadata/global-metadata.dat
   ```
   Searching for the null-terminated string `LanguageIsoCode` at absolute offset **`0x003029b2`** reveals the `ZAUM.FELD.Data.Localization.LanguageIsoCode` enum and all 104 of its member names (`af` … `zu`).

3. **The formula** — Observed by cross-referencing the two confirmed 2-char codes (`de`=57, `ru`=87) against their ASCII character sums modulo 144. No single formula covers both 2-char and regional codes.

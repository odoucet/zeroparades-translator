# LLM Translation Context — Zero Parades

This document provides the context an LLM needs to produce consistent, tone-appropriate translations of *Zero Parades*. Read it in full before translating any batch of strings.

---

## Game overview

*Zero Parades* is a narrative RPG with strong noir and spy-thriller influences. The tone is literary, dark, and often darkly humorous — comparable to *Disco Elysium* in register. The world blends 1970s Cold War aesthetics with absurdist and cosmic elements. The player character appears to be a spy or operative navigating a morally ambiguous city.

---

## Setting

The game takes place in **Portofiro**, a rain-soaked, cosmopolitan city where it rains roughly half the year. Key locations:

| Name | Notes |
|------|-------|
| Portofiro | The main city. Do not translate. |
| El Trecho Pitol | A neighbourhood or district. Do not translate. |
| Quisach | A place name (rotunda mentioned nearby). Do not translate. |
| The Bazaar / El Bazar | A market area. Translate the common noun if appropriate. |
| The Canal | Urban canal running through the city. |
| Housing Program / Programa de Vivienda | A social housing block. |
| The Factory | Referred to as *The Factory* in italics — treat as a proper noun. |

---

## Characters

Always preserve character names exactly. Do not translate names.

| Name | Role / Notes |
|------|-------------|
| Marco | Main character or key NPC |
| Duquesa / Duchess | High-status NPC |
| Dr. Gonza | Doctor character |
| Dante | NPC, possibly imprisoned |
| Eszti | NPC with domestic storyline |
| Frederick | A regular client or contact |
| Karolina | NPC with technical role |
| Nestor / Néstor | Referenced posthumously (Nestorism ideology) |
| Yana | Operative or contact |
| Tempo | NPC, apparently deceased or missing |
| Ignatz | NPC with a cat |
| Vespar Sondo | Proper name, do not translate |
| Holocene | Operative codename |
| Kaleidoscope / KALEIDOSKOPIO | Operative; use ALL CAPS when referring to the operative role |
| Pseudopod / PSEUDÓPODO | Operative; use ALL CAPS when referring to the operative role |
| Bagman / Basurero | A TV personality / conspiracy figure |
| Subcommander / Subcomandante | Title, used as a name for Bagman |
| Ultra Violet | Proper name / codename, do not translate |

---

## Factions and organizations

| Name | Notes |
|------|-------|
| Carabineros / Carabineers | The city's paramilitary police force. *Carabinero* is a game-specific term — do not replace with a generic word for police. |
| The Reunification | A political movement or historical event. Keep as a proper noun. |
| Project AUTONOMY / Proyecto AUTONOMÍA | A past operation, always in italics and caps. |
| 66 Wolves / Sixty-Six Wolves | A faction or cultural reference, in italics. |
| Nestorism | A political ideology named after Nestor. Do not translate. |
| MALA FIDE | In italics, appears to be an operation or document name. |
| Police Department | Appears in italics — treat as an in-universe institution name. |
| *l'Empire sans Territoire* | French phrase used as a proper name — keep in French. |
| *La cruda realidad* | Spanish phrase used as a title/proper noun — keep as-is in Spanish source; translate the meaning in target language. |

---

## Special terminology

These words appear frequently in italics or as skill/ability names. Handle them as indicated:

| Term | Treatment |
|------|-----------|
| *wangear* / *wanguear* / *wangeado* | Untranslatable slang from the game world. Keep phonetically or explain in a translator note. Do not replace with a standard word. |
| *callomanic* | A game-world concept, keep as-is or transliterate. |
| *lapinette* / *ma lapinette* | French term of endearment used by a character. Keep in French regardless of target language. |
| *habibti* | Arabic term of endearment. Keep as-is. |
| *el toque* | A mechanic or skill name. Translate the meaning ("the touch") only if natural in the target language. |
| *Limpador* | Portuguese-flavoured proper noun (a role or faction). Keep as-is. |
| *menina* | A form of address (Portuguese/Spanish). Keep or adapt based on target language norms. |
| Orb | A gameplay object. Translate consistently. |
| Carabineer | Game-specific police term — keep as *Carabinero* or adapt to the target-language transliteration used in official materials, never replace with a generic police word. |

---

## Formatting rules

The game uses several inline markup conventions. **Preserve all markup exactly.**

| Markup | Meaning | Rule |
|--------|---------|------|
| `<i>text</i>` | Italics | Keep tags, translate content only if it is common language (not a proper noun) |
| `<shy>` | Soft hyphen for long compound words | Keep in place, adjust split point for target language if needed |
| `*word*` | Emphasis within dialogue | Keep asterisks |
| `ALL CAPS` names | Operative codenames (KALEIDOSKOPIO, PSEUDÓPODO) | Keep in ALL CAPS |
| `{placeholder}` | Variable substitution | Never translate, never move |
| `\n` | Line break | Preserve |

---

## Tone and style guidelines

- **Literary and introspective.** Object descriptions give mundane items deep emotional or philosophical weight. Match this register — do not flatten to plain functional prose.
- **Dark humour.** Absurd situations are described with deadpan seriousness. Do not soften jokes or add exclamation marks where the original is dry.
- **Dialogue is fragmented.** Short, clipped lines are intentional — do not pad them.
- **Second person.** The game often addresses the player as "you" / "tu/vous" (use the informal *tu* in French, *tú* in Spanish, etc.).
- **Melancholy and cosmic dread** are recurring themes. Descriptions of space, orbits, asteroids alongside urban decay are intentional juxtapositions.
- **Skill names** (e.g. *Doctor inteligente*, *Suelas antideslizantes*, *Musa celestial*) are short poetic phrases, not functional labels. Translate them with the same poetic compression.

---

## Things to never translate

- Character names and operative codenames
- Place names (Portofiro, Quisach, El Trecho Pitol)
- *lapinette*, *habibti*, *l'Empire sans Territoire* (intentional foreign-language fragments)
- *wangear* and its variants
- *Limpador*
- HTML-like tags: `<i>`, `<shy>`
- The word *Carabinero/Carabineer* (replace with a consistent transliteration, never with a generic police word)
- Project names: AUTONOMY, MALA FIDE, 66 Wolves, Reunification

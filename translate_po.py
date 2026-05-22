"""
translate_po.py
Translates a Zero Parades .po file using any OpenAI-compatible LLM API
(OpenAI, OpenRouter, local AI via LM Studio / LocalAI / Ollama…).

Usage:
    # OpenAI — set OPENAI_API_KEY first
    python translate_po.py --input es_mx_reference.po --output fr_translation.po \
                           --target-lang French

    # OpenRouter — set OPENAI_API_KEY to your OpenRouter key
    python translate_po.py --input es_mx_reference.po --output fr_translation.po \
                           --target-lang French --base-url https://openrouter.ai/api/v1 \
                           --model mistralai/mistral-7b-instruct

    # Local AI — no key needed
    python translate_po.py --input es_mx_reference.po --output fr_translation.po \
                           --target-lang French --base-url http://127.0.0.1:8080/v1 \
                           --model your-model-name

Resume: re-run the same command. Entries with an existing msgstr are skipped.

Cost estimate (70k entries, batch 25, including lore context ~1600 tokens/call):
    gpt-4o-mini                  ~$2-3
    OpenRouter (varies by model) ~$1-10
    Local AI                     free
"""

import argparse
import json
import logging
import os
import re
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import polib
from tqdm import tqdm

from language_codes import ASSET_PATHS, DISPLAY_NAMES

try:
    import openai
except ImportError:
    openai = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ── Lore context ──────────────────────────────────────────────────────────────

CONTEXT_FILE = Path(__file__).parent / "llm_translation_context.md"


def load_context() -> str:
    """Load the lore/terminology context file for injection into the system prompt."""
    if CONTEXT_FILE.exists():
        return CONTEXT_FILE.read_text(encoding="utf-8")
    return ""


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """\
You are a professional video game translator working on *Zero Parades*, a narrative RPG.
You will translate strings from {source_lang} to {target_lang}.

{context}

---

TRANSLATION RULES:
1. Return ONLY a valid JSON array of strings — one translated string per input string,
   in the same order. No keys, no explanations, no markdown fences.
2. Preserve ALL inline markup exactly: <i>…</i>, <shy>, *emphasis*, {{variables}}.
3. Never translate proper nouns, character names, place names, or the terms listed
   in the "Things to never translate" section above.
4. Match the tone: literary, dark, occasionally humorous. Short lines stay short.
5. If a string is untranslatable (e.g. a single symbol or markup-only), return it unchanged.
6. The response must be parseable by json.loads(). Escape special characters properly.
"""

# ── API client ────────────────────────────────────────────────────────────────

DEFAULT_MODEL = "gpt-4o-mini"


def make_openai_client(base_url: str | None = None,
                       extra_headers: dict | None = None):
    """Create and return an OpenAI-compatible API client."""
    if openai is None:
        sys.exit("Error: pip install openai")
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key and not base_url:
        sys.exit("Error: OPENAI_API_KEY environment variable not set.")
    return openai.OpenAI(
        api_key=key or "local",
        base_url=base_url,
        default_headers=extra_headers or {},
    )


def call_openai(client, model: str, system: str, user: str,
                max_retries: int = 4) -> str:
    """Call an OpenAI-compatible API with exponential-backoff retry on rate limits."""
    delay = 2
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=8192,
                timeout=120,
            )
            choice = resp.choices[0]
            if choice.finish_reason == "length":
                raise ValueError(
                    f"Response truncated (max_tokens reached) for batch of "
                    f"{user.count(chr(10))} lines — will split and retry."
                )
            if choice.message.content is None:
                raise ValueError(
                    f"Model returned null content "
                    f"(finish_reason={choice.finish_reason!r})"
                )
            return choice.message.content
        except openai.RateLimitError:
            time.sleep(delay)
            delay *= 2
        except openai.APIError:
            if attempt == max_retries - 1:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("Max retries exceeded")


# ── JSON parsing (robust) ─────────────────────────────────────────────────────

def parse_json_array(text: str) -> list[str]:
    """Extract a JSON array from an LLM response.

    Handles:
    - Markdown code fences (```json … ```)
    - Thinking tags (<think>…</think>, <thinking>…</thinking>)
    - Preamble text before the array (finds first '[')
    """
    # Strip thinking blocks (Qwen3, DeepSeek-R1, o1…)
    text = re.sub(r"<think(?:ing)?>.*?</think(?:ing)?>", "", text, flags=re.DOTALL)
    text = text.strip()
    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    # Find the first '[' and last ']' — handles preamble/postamble text
    start = text.find("[")
    end   = text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON array found in response. Raw (first 200 chars): {text[:200]!r}")
    return json.loads(text[start:end + 1])


# ── Core translation logic ────────────────────────────────────────────────────

def translate_batch(texts: list[str], system: str, client, model: str,
                    _depth: int = 0) -> list[str]:
    """Translate texts; splits into halves and retries on parse or count errors (max 3 splits).

    Returns empty strings for entries that keep failing — they will be retried on the next run.
    """
    if not texts:
        return []
    user = (
        f"Translate the following {len(texts)} strings. "
        "Return ONLY a JSON array of the translated strings in the same order.\n\n"
        + json.dumps(texts, ensure_ascii=False)
    )
    try:
        result = parse_json_array(call_openai(client, model, system, user))
        result = [s if isinstance(s, str) else "" for s in result]
        if len(result) != len(texts):
            raise ValueError(f"LLM returned {len(result)} strings for {len(texts)} inputs.")
        return result
    except (ValueError, json.JSONDecodeError):
        if _depth >= 3 or len(texts) == 1:
            logger.warning(
                "Batch of %d still failing after splits — entries will be retried on next run.",
                len(texts),
            )
            return [""] * len(texts)
        mid = len(texts) // 2
        return (
            translate_batch(texts[:mid], system, client, model, _depth + 1)
            + translate_batch(texts[mid:], system, client, model, _depth + 1)
        )


def translate_po(
    input_path: Path,
    output_path: Path,
    target_lang: str,
    source_lang: str,
    model: str,
    batch_size: int,
    save_every: int,
    base_url: str | None = None,
    extra_headers: dict | None = None,
    preview: int = 3,
    parallel: int = 1,
):
    """Translate all untranslated entries in a PO file, saving checkpoints periodically."""
    po = polib.pofile(str(input_path), encoding="utf-8")
    total = len(po)

    todo = [e for e in po if not e.msgstr]
    done = total - len(todo)
    if done:
        logger.info("Resuming: %d/%d entries already translated, %d remaining.",
                    done, total, len(todo))
    else:
        logger.info("Starting fresh: %d entries to translate.", total)

    if not todo:
        logger.info("Nothing to do.")
        return

    context = load_context()
    system = SYSTEM_PROMPT_TEMPLATE.format(
        source_lang=source_lang,
        target_lang=target_lang,
        context=context,
    )

    client = make_openai_client(base_url=base_url, extra_headers=extra_headers)

    batches = [todo[i:i + batch_size] for i in range(0, len(todo), batch_size)]
    failed_batches: list[int] = []
    recent_times: list[float] = []
    save_lock = threading.Lock()
    batches_done = 0

    def process_batch(
        batch_idx: int, batch: list
    ) -> tuple[int, list | None, Exception | None, float]:
        texts = [e.msgid for e in batch]
        t0 = time.time()
        try:
            translations = translate_batch(texts, system, client, model)
            return batch_idx, translations, None, time.time() - t0
        except Exception as exc:
            return batch_idx, None, exc, time.time() - t0

    with tqdm(total=total, initial=done, unit="entry",
              desc=f"Translating ->{target_lang}") as pbar:

        executor = ThreadPoolExecutor(max_workers=parallel)
        futures: dict = {}
        try:
            futures = {
                executor.submit(process_batch, i, batch): (i, batch)
                for i, batch in enumerate(batches)
            }

            for future in as_completed(futures):
                batch_idx, batch = futures[future]
                _, translations, exc, elapsed = future.result()

                if exc is not None:
                    tqdm.write(f"  [batch {batch_idx}] ERROR: {exc} — skipping.")
                    failed_batches.append(batch_idx)
                else:
                    for entry, translation in zip(batch, translations):
                        entry.msgstr = translation

                    if preview > 0:
                        with save_lock:
                            recent_times.append(elapsed)
                            if len(recent_times) > 10:
                                recent_times.pop(0)
                            avg_t = sum(recent_times) / len(recent_times)
                            rem = max(0, len(batches) - batches_done - 1)
                        eta_s = rem * avg_t / max(1, parallel)
                        if eta_s >= 3600:
                            eta = f"{int(eta_s // 3600)}h{int(eta_s % 3600 // 60):02d}m"
                        elif eta_s >= 60:
                            eta = f"{int(eta_s // 60)}m{int(eta_s % 60):02d}s"
                        else:
                            eta = f"{eta_s:.0f}s"
                        col = max(25, (shutil.get_terminal_size().columns - 5) // 2)
                        tqdm.write(f"  {'Source':<{col}} | Translation")
                        tqdm.write(f"  {'-' * col}-+-{'-' * col}")
                        for entry in batch[-preview:]:
                            s, d = entry.msgid, entry.msgstr
                            src = (s[:col - 3] + "...") if len(s) > col else s
                            dst = (d[:col - 3] + "...") if len(d) > col else d
                            tqdm.write(f"  {src:<{col}} | {dst}")
                        tqdm.write(
                            f"  {elapsed:.1f}s · avg {avg_t:.1f}s · ~{rem} batches left · ETA {eta}"
                        )
                        tqdm.write("")

                pbar.update(len(batch))

                with save_lock:
                    batches_done += 1
                    if batches_done % save_every == 0:
                        po.save(str(output_path))
                        tqdm.write(
                            f"  Saved checkpoint "
                            f"({batches_done}/{len(batches)} batches done)"
                        )

        except KeyboardInterrupt:
            tqdm.write("\nInterrupted — cancelling pending batches...")
            for f in futures:
                f.cancel()
        finally:
            executor.shutdown(wait=True)
            po.save(str(output_path))

    po.save(str(output_path))
    translated = len([e for e in po if e.msgstr])
    logger.info("Done. %d/%d entries translated → %s", translated, total, output_path)

    if failed_batches:
        logger.warning(
            "%d batches failed (indices: %s). Re-run to retry them.",
            len(failed_batches), failed_batches,
        )


# ── CLI ───────────────────────────────────────────────────────────────────────

SOURCE_LANG_NAMES = {locale: DISPLAY_NAMES[locale] for locale in ASSET_PATHS if locale in DISPLAY_NAMES}


def main():
    """Parse CLI arguments and run the translation pipeline."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(
        description="Translate a Zero Parades .po file using an OpenAI-compatible LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # OpenAI (set OPENAI_API_KEY first)
  python translate_po.py --input es_mx_reference.po --output fr.po --target-lang French

  # OpenRouter (set OPENAI_API_KEY to your OpenRouter key)
  python translate_po.py --input es_mx_reference.po --output fr.po \\
      --target-lang French --base-url https://openrouter.ai/api/v1 \\
      --model mistralai/mistral-7b-instruct \\
      --header "HTTP-Referer=https://yoursite.com" --header "X-Title=Zero Parades Translator"

  # Local AI (LM Studio, LocalAI, Ollama… — no key needed)
  python translate_po.py --input es_mx_reference.po --output fr.po \\
      --target-lang French --base-url http://127.0.0.1:8080/v1 --model your-model-name

  # Resume an interrupted run (just re-run the same command)
  python translate_po.py --input es_mx_reference.po --output fr.po --target-lang French
        """,
    )
    parser.add_argument("--input",       required=True,  help="Source .po file")
    parser.add_argument("--output",      required=True,  help="Output .po file (created or resumed)")
    parser.add_argument("--target-lang", required=True,
                        help="Target language in plain English, e.g. French")
    parser.add_argument("--source-lang", default="es_mx",
                        choices=list(SOURCE_LANG_NAMES),
                        help="Source language code (default: es_mx)")
    parser.add_argument("--model",       default=DEFAULT_MODEL,
                        help=f"Model name (default: {DEFAULT_MODEL})")
    parser.add_argument("--base-url",    default=None,
                        help="OpenAI-compatible base URL "
                             "(e.g. http://127.0.0.1:8080/v1 or https://openrouter.ai/api/v1). "
                             "Required for OpenRouter and local AI; omit for OpenAI directly.")
    parser.add_argument("--header",      action="append", dest="headers", metavar="NAME=VALUE",
                        help="Extra HTTP header (repeatable), e.g. "
                             "--header 'HTTP-Referer=https://yoursite.com'. "
                             "Useful for OpenRouter rankings.")
    parser.add_argument("--batch-size",  type=int, default=25,
                        help="Strings per API call (default: 25)")
    parser.add_argument("--save-every",  type=int, default=1,
                        help="Save checkpoint every N batches (default: 1 = every 25 entries)")
    parser.add_argument("--preview",     type=int, default=3,
                        help="Print last N translations per batch (default: 3, 0 to disable)")
    parser.add_argument("--parallel",    type=int, default=1,
                        help="Number of concurrent API calls (default: 1). "
                             "Use 3-5 for cloud APIs, 1 for local AI.")
    args = parser.parse_args()

    extra_headers: dict | None = None
    if args.headers:
        extra_headers = {}
        for h in args.headers:
            if "=" not in h:
                sys.exit(f"Error: --header must be NAME=VALUE, got: {h!r}")
            name, _, value = h.partition("=")
            extra_headers[name.strip()] = value.strip()

    source_lang_name = SOURCE_LANG_NAMES[args.source_lang]
    input_path  = Path(args.input)
    output_path = Path(args.output)

    if output_path.exists():
        logger.info("Output file exists — resuming from %s", output_path)
        work_input = output_path
    else:
        work_input = input_path

    endpoint = args.base_url or "OpenAI API"
    logger.info("Endpoint: %s  Model: %s  Batch: %d", endpoint, args.model, args.batch_size)
    logger.info("Source: %s  Target: %s", source_lang_name, args.target_lang)

    translate_po(
        input_path=work_input,
        output_path=output_path,
        target_lang=args.target_lang,
        source_lang=source_lang_name,
        model=args.model,
        batch_size=args.batch_size,
        save_every=args.save_every,
        base_url=args.base_url,
        extra_headers=extra_headers,
        preview=args.preview,
        parallel=args.parallel,
    )


if __name__ == "__main__":
    main()

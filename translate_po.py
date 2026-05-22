"""
translate_po.py
Translates a Zero Parades .po file using an LLM (Claude or OpenAI).

Usage:
    python translate_po.py --input es_mx_reference.po --output fr_translation.po \
                           --target-lang French --api claude

    python translate_po.py --input es_mx_reference.po --output fr_translation.po \
                           --target-lang French --api openai --model gpt-4o-mini

Resume: re-run the same command. Entries with an existing msgstr are skipped.

Cost estimate (70k entries, batch 25, including lore context ~1600 tokens/call):
    claude-haiku-4-5  ~$12-16    ← recommended for full runs
    claude-sonnet-4-6 ~$38-45    ← better quality
    gpt-4o-mini       ~$2-3
"""

import argparse
import json
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
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

try:
    import openai
except ImportError:
    openai = None  # type: ignore[assignment]

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

# ── API clients ───────────────────────────────────────────────────────────────

def make_claude_client():
    """Create and return an Anthropic API client."""
    if anthropic is None:
        sys.exit("Error: pip install anthropic")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Error: ANTHROPIC_API_KEY environment variable not set.")
    return anthropic.Anthropic(api_key=api_key)


def make_openai_client(base_url: str | None = None, api_key: str | None = None,
                       extra_headers: dict | None = None):
    """Create and return an OpenAI-compatible API client."""
    if openai is None:
        sys.exit("Error: pip install openai")
    key = api_key or os.environ.get("OPENAI_API_KEY") or "local"
    if not api_key and not base_url and key == "local":
        sys.exit("Error: OPENAI_API_KEY environment variable not set.")
    return openai.OpenAI(api_key=key, base_url=base_url,
                         default_headers=extra_headers or {})


def call_claude(client, model: str, system: str, user: str,
                max_retries: int = 4) -> str:
    """Call the Claude API with exponential-backoff retry on rate limits."""
    delay = 2
    for attempt in range(max_retries):
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return msg.content[0].text
        except anthropic.RateLimitError:
            time.sleep(delay)
            delay *= 2
        except anthropic.APIError:
            if attempt == max_retries - 1:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("Max retries exceeded")


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
                max_tokens=4096,
            )
            content = resp.choices[0].message.content
            if content is None:
                raise ValueError(
                    f"Model returned null content "
                    f"(finish_reason={resp.choices[0].finish_reason!r})"
                )
            return content
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

def translate_batch(texts: list[str], system: str, api: str,
                    client, model: str) -> list[str]:
    """Translate a list of strings in one API call; returns translated strings in order."""
    user = (
        f"Translate the following {len(texts)} strings. "
        "Return ONLY a JSON array of the translated strings in the same order.\n\n"
        + json.dumps(texts, ensure_ascii=False)
    )
    if api == "claude":
        raw = call_claude(client, model, system, user)
    else:
        raw = call_openai(client, model, system, user)

    result = parse_json_array(raw)

    if len(result) != len(texts):
        raise ValueError(
            f"LLM returned {len(result)} strings for {len(texts)} inputs."
        )
    return result


def translate_po(
    input_path: Path,
    output_path: Path,
    target_lang: str,
    source_lang: str,
    api: str,
    model: str,
    batch_size: int,
    save_every: int,
    base_url: str | None = None,
    api_key: str | None = None,
    extra_headers: dict | None = None,
    preview: int = 3,
    parallel: int = 1,
):
    """Translate all untranslated entries in a PO file, saving checkpoints periodically."""
    # Load
    po = polib.pofile(str(input_path), encoding="utf-8")
    total = len(po)

    # Identify untranslated entries (resume support)
    todo = [e for e in po if not e.msgstr]
    done = total - len(todo)
    if done:
        print(f"Resuming: {done}/{total} entries already translated, "
              f"{len(todo)} remaining.")
    else:
        print(f"Starting fresh: {total} entries to translate.")

    if not todo:
        print("Nothing to do.")
        return

    # Build system prompt
    context = load_context()
    system = SYSTEM_PROMPT_TEMPLATE.format(
        source_lang=source_lang,
        target_lang=target_lang,
        context=context,
    )

    # Set up API client
    if api == "claude":
        client = make_claude_client()
    else:
        client = make_openai_client(base_url=base_url, api_key=api_key,
                                    extra_headers=extra_headers)

    # Translate in batches
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
            translations = translate_batch(texts, system, api, client, model)
            return batch_idx, translations, None, time.time() - t0
        except Exception as exc:
            return batch_idx, None, exc, time.time() - t0

    with tqdm(total=len(todo), initial=0, unit="entry",
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
                            f"  {elapsed:.1f}s · avg {avg_t:.1f}s"
                            f" · ~{rem} batches left · ETA {eta}"
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

    # Final save
    po.save(str(output_path))
    translated = len([e for e in po if e.msgstr])
    print(f"\nDone. {translated}/{total} entries translated ->{output_path}")

    if failed_batches:
        print(f"Warning: {len(failed_batches)} batches failed "
              f"(indices: {failed_batches}). Re-run to retry them.")

# ── CLI ───────────────────────────────────────────────────────────────────────

DEFAULT_MODELS = {
    "claude": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
}

SOURCE_LANG_NAMES = {locale: DISPLAY_NAMES[locale] for locale in ASSET_PATHS if locale in DISPLAY_NAMES}

def main():
    """Parse CLI arguments and run the translation pipeline."""
    parser = argparse.ArgumentParser(
        description="Translate a Zero Parades .po file using an LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # French translation from Spanish (recommended)
  python translate_po.py --input es_mx_reference.po --output fr.po --target-lang French

  # Italian from Spanish, using OpenAI
  python translate_po.py --input es_mx_reference.po --output it.po \\
      --target-lang Italian --api openai

  # Local AI (LM Studio, LocalAI, Ollama…)
  python translate_po.py --input es_mx_reference.po --output fr.po \\
      --target-lang French --base-url http://127.0.0.1:8080/v1 \\
      --model your-model-name

  # OpenRouter
  python translate_po.py --input es_mx_reference.po --output fr.po \\
      --target-lang French --base-url https://openrouter.ai/api/v1 \\
      --api-key sk-or-... --model mistralai/mistral-7b-instruct \\
      --header "HTTP-Referer=https://yoursite.com" --header "X-Title=My Translator"

  # Resume an interrupted run (just re-run the same command)
  python translate_po.py --input es_mx_reference.po --output fr.po --target-lang French
        """,
    )
    parser.add_argument("--input",       required=True,  help="Source .po file")
    parser.add_argument("--output", required=True, help="Output .po file (created or resumed)")
    parser.add_argument("--target-lang", required=True,
                        help="Target language in plain English, e.g. French")
    parser.add_argument("--source-lang", default="es_mx",
                        choices=list(SOURCE_LANG_NAMES),
                        help="Source language code (default: es_mx)")
    parser.add_argument("--api",         default="claude", choices=["claude", "openai"],
                        help="LLM provider (default: claude)")
    parser.add_argument("--model",       default=None,
                        help="Model name (default: claude-haiku-4-5-20251001 / gpt-4o-mini)")
    parser.add_argument("--base-url",    default=None,
                        help="Custom OpenAI-compatible base URL "
                             "(e.g. http://127.0.0.1:8080/v1 or https://openrouter.ai/api/v1). "
                             "Implies --api openai.")
    parser.add_argument("--api-key",     default=None,
                        help="API key for --base-url services (overrides OPENAI_API_KEY env var).")
    parser.add_argument("--header",      action="append", dest="headers", metavar="NAME=VALUE",
                        help="Extra HTTP header (repeatable), e.g. "
                             "--header 'HTTP-Referer=https://yoursite.com'. "
                             "Useful for OpenRouter rankings.")
    parser.add_argument("--batch-size",  type=int, default=25,
                        help="Strings per API call (default: 25)")
    parser.add_argument("--save-every",  type=int, default=10,
                        help="Save checkpoint every N batches (default: 10 = every 250 entries)")
    parser.add_argument("--preview", type=int, default=3,
                        help="Print last N translations per batch "
                             "(default: 3, 0 to disable)")
    parser.add_argument("--parallel",    type=int, default=1,
                        help="Number of concurrent API calls (default: 1). "
                             "Use 3-5 for cloud APIs, 1 for local AI.")
    args = parser.parse_args()

    # --base-url forces openai-compatible path
    if args.base_url:
        args.api = "openai"

    # Parse --header NAME=VALUE pairs
    extra_headers: dict | None = None
    if args.headers:
        extra_headers = {}
        for h in args.headers:
            if "=" not in h:
                sys.exit(f"Error: --header must be NAME=VALUE, got: {h!r}")
            name, _, value = h.partition("=")
            extra_headers[name.strip()] = value.strip()

    model = args.model or DEFAULT_MODELS[args.api]
    source_lang_name = SOURCE_LANG_NAMES[args.source_lang]

    input_path  = Path(args.input)
    output_path = Path(args.output)

    # If resuming, load the existing output; otherwise start from the input
    if output_path.exists():
        print(f"Output file exists — resuming from {output_path}")
        work_input = output_path
    else:
        work_input = input_path

    endpoint = args.base_url or ("Anthropic API" if args.api == "claude" else "OpenAI API")
    print(f"API: {args.api}  Endpoint: {endpoint}  Model: {model}  Batch: {args.batch_size}")
    print(f"Source: {source_lang_name}  Target: {args.target_lang}")

    translate_po(
        input_path=work_input,
        output_path=output_path,
        target_lang=args.target_lang,
        source_lang=source_lang_name,
        api=args.api,
        model=model,
        batch_size=args.batch_size,
        save_every=args.save_every,
        base_url=args.base_url,
        api_key=args.api_key,
        extra_headers=extra_headers,
        preview=args.preview,
        parallel=args.parallel,
    )


if __name__ == "__main__":
    main()

"""
ollama_prompt.py
----------------
A reusable module (and runnable script) for prompting Qwen2.5-Coder via the
Ollama REST API with a Markdown-formatted prompt file, then saving the JSON
response to disk.

Usage as a script
-----------------
    python ollama_prompt.py                         # uses default paths
    python ollama_prompt.py -i prompt.md            # custom prompt file
    python ollama_prompt.py -i prompt.md -o out/    # custom output dir
    python ollama_prompt.py -i prompt.md -o result.json  # exact output file
    python ollama_prompt.py --host http://localhost:11434 --timeout 120

Usage as a module
-----------------
    from ollama_prompt import run_prompt, load_prompt, save_result

    raw_md  = load_prompt("my_prompt.md")
    result  = run_prompt(raw_md)          # dict
    path    = save_result(result, "out/")
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Defaults – override via CLI args or the public API
# ---------------------------------------------------------------------------
DEFAULT_PROMPT_PATH: Path = Path("promptTemplate.md")
DEFAULT_OUTPUT_PATH: Path = Path(".")          # working directory
DEFAULT_HOST: str = "http://localhost:11434"
DEFAULT_MODEL: str = "Qwen2.5-Coder"
DEFAULT_TIMEOUT: int = 900                    # seconds

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def load_prompt(path: str | Path) -> str:
    """Read a Markdown prompt file and return its text."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Prompt file not found: {p}")
    text = p.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Prompt file is empty: {p}")
    log.debug("Loaded prompt (%d chars) from %s", len(text), p)
    return text


def _build_messages(prompt_text: str) -> list[dict[str, str]]:
    """
    Wrap the raw Markdown prompt in an Ollama-compatible message list.
    A system instruction tells the model to reply with valid JSON only.
    """
    system = (
        "You are a precise code and data assistant. "
        "Always respond with a single, valid JSON object and nothing else — "
        "no markdown fences, no prose, no comments outside the JSON."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt_text},
    ]


def run_prompt(
    prompt_text: str,
    *,
    host: str = DEFAULT_HOST,
    model: str = DEFAULT_MODEL,
    timeout: int = DEFAULT_TIMEOUT,
    extra_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Send *prompt_text* to Ollama and return the parsed JSON response.

    Parameters
    ----------
    prompt_text:
        The full Markdown-formatted prompt string.
    host:
        Base URL of the Ollama server (e.g. ``http://localhost:11434``).
    model:
        Ollama model tag to use.
    timeout:
        HTTP request timeout in seconds.
    extra_options:
        Any additional Ollama model options (temperature, top_p, …).

    Returns
    -------
    dict
        The parsed JSON object returned by the model.

    Raises
    ------
    requests.HTTPError
        On a non-2xx response from Ollama.
    json.JSONDecodeError
        If the model's reply is not valid JSON.
    """
    url = f"{host.rstrip('/')}/api/chat"

    payload: dict[str, Any] = {
        "model": model,
        "messages": _build_messages(prompt_text),
        "stream": False,
        "format": "json",          # ask Ollama to enforce JSON output mode
        "options": {
            "temperature": 0.1,    # low temp → deterministic, structured output
            **(extra_options or {}),
        },
    }

    log.info("POSTing to %s  model=%s", url, model)
    t0 = time.perf_counter()

    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()

    elapsed = time.perf_counter() - t0
    log.info("Response received in %.1f s", elapsed)

    raw = response.json()

    # Ollama wraps the assistant message in  raw["message"]["content"]
    content: str = raw.get("message", {}).get("content", "")
    if not content:
        raise ValueError("Empty content in Ollama response")

    log.debug("Raw model output: %s", content[:200])

    # Strip accidental markdown fences just in case
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = "\n".join(stripped.splitlines()[1:])
        stripped = stripped.rsplit("```", 1)[0].strip()

    result: dict[str, Any] = json.loads(stripped)
    return result


def save_result(
    result: dict[str, Any],
    output: str | Path,
    *,
    prompt_path: str | Path | None = None,
) -> Path:
    """
    Persist *result* as a JSON file.

    Parameters
    ----------
    result:
        The dict returned by :func:`run_prompt`.
    output:
        Either a directory (the filename is derived from the prompt filename)
        or an explicit ``.json`` file path.
    prompt_path:
        Used to derive the output filename when *output* is a directory.

    Returns
    -------
    Path
        The path of the written file.
    """
    out = Path(output)

    if out.is_dir() or not out.suffix:
        # Derive filename from the prompt path, or fall back to "result.json"
        stem = Path(prompt_path).stem if prompt_path else "result"
        out = out / f"{stem}.json"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Result written to %s", out)
    return out


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ollama_prompt",
        description=(
            "Prompt Qwen2.5-Coder via Ollama with a Markdown file "
            "and save the JSON response."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-i", "--input",
        metavar="PROMPT_FILE",
        type=Path,
        default=DEFAULT_PROMPT_PATH,
        help="Path to the Markdown-formatted prompt file.",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="PATH",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=(
            "Output path. Can be a directory (filename auto-derived) "
            "or an explicit .json file path."
        ),
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="Ollama server base URL.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Ollama model tag.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="HTTP request timeout in seconds.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Override the model temperature (0.0 – 1.0).",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(message)s",
    )

    extra: dict[str, Any] = {}
    if args.temperature is not None:
        extra["temperature"] = args.temperature

    try:
        prompt_text = load_prompt(args.input)
        result = run_prompt(
            prompt_text,
            host=args.host,
            model=args.model,
            timeout=args.timeout,
            extra_options=extra or None,
        )
        out_path = save_result(result, args.output, prompt_path=args.input)
        print(f"✓  Saved → {out_path}")
        return 0

    except FileNotFoundError as exc:
        log.error("%s", exc)
        return 2
    except requests.ConnectionError:
        log.error(
            "Cannot reach Ollama at %s — is the server running?", args.host
        )
        return 1
    except requests.HTTPError as exc:
        log.error("Ollama HTTP error: %s", exc)
        return 1
    except json.JSONDecodeError as exc:
        log.error("Model returned invalid JSON: %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        log.exception("Unexpected error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())

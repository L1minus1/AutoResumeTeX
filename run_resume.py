"""
run_resume.py
-------------
Top-level orchestration script for the AI-assisted resume pipeline.

Pipeline
--------
1.  Open vim so the user can write a free-form job description.
2.  Read the temp file into a string, then delete it.
3.  Load the Markdown prompt template (hardcoded default or -i override).
4.  Inject the job description at the <DescHere> marker → final prompt string.
5.  Pass the prompt string to ollama_prompt.run_prompt() → JSON dict.
6.  Save the JSON dict to a file in the working directory.
7.  Call template_processor.main() with the JSON path to apply changes to
    the .tex template.
8.  Compile resume.tex → PDF with pdflatex, save to outputs/ (or --pdf-dir),
    clean up all LaTeX auxiliary files.  Skip with --no-pdf.

Usage
-----
    python run_resume.py                          # all defaults
    python run_resume.py -i prompt.md             # custom prompt template
    python run_resume.py --no-pdf                 # tex only, no compilation
    python run_resume.py --pdf-dir ~/resumes      # custom output directory
    python run_resume.py --pdf-name my_resume     # custom base filename
    python run_resume.py --help
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# ── local modules (must be on sys.path / same directory) ──────────────────────
import ollama_prompt
import template_processor

# ─────────────────────────────────────────────────────────────────────────────
# Defaults
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_PROMPT_TEMPLATE: Path = Path("./promptTemplate.md")
TEMP_FILE_NAME:          str  = ".resume_desc_tmp.md"   # hidden in cwd
DESC_MARKER:             str  = "<DescHere>"
TEX_OUTPUT:              str  = "resume.tex"            # written by template_processor
DEFAULT_PDF_DIR:         str  = "outputs"               # relative to cwd

# Extensions pdflatex leaves behind — everything except .pdf and .tex
LATEX_AUX_EXTENSIONS: tuple[str, ...] = (
    ".aux", ".log", ".out", ".toc", ".lof", ".lot",
    ".fls", ".fdb_latexmk", ".synctex.gz",
    ".bcf", ".run.xml", ".bbl", ".blg",
)

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Step helpers
# ─────────────────────────────────────────────────────────────────────────────

def open_vim_and_capture(tmp_path: Path) -> str:
    """
    Open *tmp_path* in vim (overwriting any pre-existing content) and return
    the text the user saved.  Raises RuntimeError if the file is empty after
    vim exits.
    """
    tmp_path.write_text("", encoding="utf-8")

    log.info("Opening vim → %s", tmp_path)
    result = subprocess.run(["vim", str(tmp_path)])

    if result.returncode != 0:
        raise RuntimeError(f"vim exited with code {result.returncode}")

    text = tmp_path.read_text(encoding="utf-8").strip()

    try:
        tmp_path.unlink()
        log.debug("Deleted temp file %s", tmp_path)
    except OSError as exc:
        log.warning("Could not delete temp file %s: %s", tmp_path, exc)

    if not text:
        raise RuntimeError(
            "No content was saved — aborting.  "
            "Write the job description in vim, then :wq to continue."
        )

    log.info("Captured %d chars from vim session.", len(text))
    return text


def inject_description(template_text: str, description: str) -> str:
    """
    Replace the first occurrence of DESC_MARKER in *template_text* with
    *description*.  Raises ValueError if the marker is not found.
    """
    if DESC_MARKER not in template_text:
        raise ValueError(
            f"Marker '{DESC_MARKER}' not found in prompt template. "
            "Ensure the template contains exactly one occurrence."
        )
    injected = template_text.replace(DESC_MARKER, description, 1)
    log.debug("Injected description (%d chars) at '%s'.", len(description), DESC_MARKER)
    return injected


def save_json_to_cwd(result: dict, prompt_path: Path) -> Path:
    """
    Delegate to ollama_prompt.save_result(), targeting the current working
    directory.  Returns the path of the written file.
    """
    out_path = ollama_prompt.save_result(result, Path.cwd(), prompt_path=prompt_path)
    log.info("JSON saved → %s", out_path)
    return out_path


def compile_pdf(
    tex_path: Path,
    pdf_dir: Path,
    pdf_name: str,
) -> Path:
    """
    Compile *tex_path* with pdflatex into *pdf_dir*, naming the output
    *pdf_name*.pdf.  All LaTeX auxiliary files are removed afterwards.

    pdflatex is run twice so that any internal references (page numbers,
    hyperlinks, etc.) resolve correctly on the second pass.

    Returns the final PDF path.

    Raises
    ------
    FileNotFoundError
        If pdflatex is not on PATH.
    RuntimeError
        If pdflatex exits with a non-zero return code.
    """
    if not shutil.which("pdflatex"):
        raise FileNotFoundError(
            "pdflatex not found on PATH. "
            "Install a TeX distribution (e.g. texlive-basic) or pass --no-pdf."
        )

    pdf_dir.mkdir(parents=True, exist_ok=True)

    # pdflatex names the output after the job name, so we pass -jobname.
    cmd = [
        "pdflatex",
        "-interaction=nonstopmode",       # never pause for user input
        f"-output-directory={pdf_dir}",
        f"-jobname={pdf_name}",
        str(tex_path),
    ]

    log.info("Compiling PDF (pass 1/2)…")
    for pass_num in (1, 2):
        log.debug("pdflatex pass %d: %s", pass_num, " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            # Surface the tail of the log so the error is actionable.
            tail = "\n".join(proc.stdout.splitlines()[-30:])
            raise RuntimeError(
                f"pdflatex failed on pass {pass_num} "
                f"(exit {proc.returncode}):\n{tail}"
            )
        if pass_num == 1:
            log.info("Compiling PDF (pass 2/2)…")

    pdf_path = pdf_dir / f"{pdf_name}.pdf"
    log.info("PDF written → %s", pdf_path)

    # ── Clean up auxiliary files ───────────────────────────────────────────
    removed: list[Path] = []
    for ext in LATEX_AUX_EXTENSIONS:
        aux = pdf_dir / f"{pdf_name}{ext}"
        if aux.exists():
            aux.unlink()
            removed.append(aux)

    if removed:
        log.debug("Removed %d auxiliary file(s): %s", len(removed),
                  ", ".join(p.name for p in removed))

    return pdf_path


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_resume",
        description=(
            "AI-assisted resume pipeline: vim → Ollama → template processor → PDF."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # ── Prompt / Ollama options ────────────────────────────────────────────
    parser.add_argument(
        "-i", "--input",
        metavar="PROMPT_TEMPLATE",
        type=Path,
        default=DEFAULT_PROMPT_TEMPLATE,
        help="Path to the Markdown prompt template (must contain '<DescHere>').",
    )
    parser.add_argument(
        "--host",
        default=ollama_prompt.DEFAULT_HOST,
        help="Ollama server base URL.",
    )
    parser.add_argument(
        "--model",
        default=ollama_prompt.DEFAULT_MODEL,
        help="Ollama model tag.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=ollama_prompt.DEFAULT_TIMEOUT,
        help="Ollama HTTP timeout in seconds.",
    )

    # ── PDF options ────────────────────────────────────────────────────────
    pdf_group = parser.add_argument_group("PDF compilation")
    pdf_group.add_argument(
        "--no-pdf",
        action="store_true",
        help=(
            "Stop after generating resume.tex; do not compile to PDF. "
            "Useful for inspecting or manually editing the .tex file first."
        ),
    )
    pdf_group.add_argument(
        "--pdf-dir",
        metavar="DIR",
        type=Path,
        default=Path.cwd() / DEFAULT_PDF_DIR,
        help="Directory where the compiled PDF is saved.",
    )
    pdf_group.add_argument(
        "--pdf-name",
        metavar="BASENAME",
        default=None,
        help=(
            "Base filename for the PDF (without extension). "
            "Defaults to 'resume-YYYYMMDD-HHMMSS'."
        ),
    )

    # ── General ───────────────────────────────────────────────────────────
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    return parser


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(message)s",
    )

    # Resolve PDF name now so the timestamp reflects when the run started.
    pdf_name: str = args.pdf_name or datetime.now().strftime("resume-%Y%m%d-%H%M%S")

    # ── 1. Vim session ────────────────────────────────────────────────────
    tmp_path = Path.cwd() / TEMP_FILE_NAME
    try:
        description = open_vim_and_capture(tmp_path)
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1

    # ── 2. Load prompt template ───────────────────────────────────────────
    try:
        template_text = ollama_prompt.load_prompt(args.input)
    except (FileNotFoundError, ValueError) as exc:
        log.error("Prompt template error: %s", exc)
        return 2

    # ── 3. Build final prompt by injecting description ────────────────────
    try:
        final_prompt = inject_description(template_text, description)
    except ValueError as exc:
        log.error("%s", exc)
        return 2

    # ── 4. Run Ollama ─────────────────────────────────────────────────────
    log.info("Sending prompt to Ollama (%s)…", args.model)
    try:
        result = ollama_prompt.run_prompt(
            final_prompt,
            host=args.host,
            model=args.model,
            timeout=args.timeout,
        )
    except Exception as exc:          # noqa: BLE001
        log.error("Ollama error: %s", exc)
        return 1

    # ── 5. Save JSON to working directory ─────────────────────────────────
    try:
        json_path = save_json_to_cwd(result, args.input)
    except OSError as exc:
        log.error("Could not write JSON: %s", exc)
        return 1

    # ── 6. Run template processor ─────────────────────────────────────────
    log.info("Running template processor with %s…", json_path)
    try:
        _orig_argv = sys.argv
        sys.argv = ["template_processor.py", str(json_path)]
        template_processor.main()
    except SystemExit as exc:
        if exc.code not in (None, 0):
            log.error("template_processor exited with code %s", exc.code)
            return int(exc.code)
    except Exception as exc:          # noqa: BLE001
        log.error("template_processor error: %s", exc)
        return 1
    finally:
        sys.argv = _orig_argv

    tex_path = Path.cwd() / TEX_OUTPUT

    # ── 7. Compile PDF (unless --no-pdf) ──────────────────────────────────
    if args.no_pdf:
        log.info("--no-pdf set; skipping compilation.")
        print(f"\n✓  Pipeline complete.  TeX file → {tex_path}")
        return 0

    try:
        pdf_path = compile_pdf(
            tex_path=tex_path,
            pdf_dir=args.pdf_dir,
            pdf_name=pdf_name,
        )
    except FileNotFoundError as exc:
        log.error("%s", exc)
        return 1
    except RuntimeError as exc:
        log.error("PDF compilation failed:\n%s", exc)
        return 1

    print(f"\n✓  Pipeline complete.")
    print(f"   TeX → {tex_path}")
    print(f"   PDF → {pdf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

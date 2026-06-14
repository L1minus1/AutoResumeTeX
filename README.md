# AutoResumeTex

An AI-assisted resume tailoring pipeline. Paste a job description into vim,
and the tool uses a local Ollama model to extract role-relevant content, fills
it into your personal LaTeX resume template, and compiles a timestamped PDF —
all from a single command.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Installation](#2-installation)
3. [Configuration](#3-configuration)
   - [LaTeX Resume Template](#31-latex-resume-template)
   - [Prompt Template](#32-prompt-template)
   - [Source File Constants](#33-source-file-constants)
4. [Usage](#4-usage)
   - [run_resume.py — Full Pipeline](#41-run_resumepy--full-pipeline)
   - [ollama_prompt.py — Standalone Prompter](#42-ollama_promptpy--standalone-prompter)
   - [template_processor.py — Standalone Processor](#43-template_processorpy--standalone-processor)
5. [Pipeline Walkthrough](#5-pipeline-walkthrough)
   - [Step 1 — vim Session](#step-1--vim-session)
   - [Step 2 — Prompt Assembly](#step-2--prompt-assembly)
   - [Step 3 — Ollama Inference](#step-3--ollama-inference)
   - [Step 4 — JSON Saved to Disk](#step-4--json-saved-to-disk)
   - [Step 5 — Template Processing](#step-5--template-processing)
   - [Step 6 — PDF Compilation](#step-6--pdf-compilation)
6. [JSON Schema Reference](#6-json-schema-reference)
7. [LaTeX Placeholder Reference](#7-latex-placeholder-reference)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Prerequisites

Nothing else in this README matters if these steps are skipped.

### Ollama

Install Ollama with the package that matches your GPU. The base `ollama`
package is CPU-only; if you have a GPU, use the appropriate variant so the
model runs on it:

While this tool has not been tested outside an Arch-Linux environment, it should work on any distribution.  Simply substitute the pacman commands and package names with the equivalents from your distribution.  This tool has not been tested in WSL, but if anyone tries this, let me know!

```bash
sudo pacman -S ollama-cuda   # NVIDIA
sudo pacman -S ollama-rocm   # AMD
sudo pacman -S ollama        # CPU only
```

Enable and start the service:

```bash
sudo systemctl enable --now ollama
```

Verify it is running before doing anything else:

```bash
curl http://localhost:11434
# Expected: Ollama is running
```

### Ollama Model

Pull the model before first use. The `7b` variant is a good default; use `3b`
if you are on CPU and generation is too slow:

```bash
ollama pull qwen2.5-coder:7b   # recommended
ollama pull qwen2.5-coder:3b   # faster, CPU-friendly
```

### Python

Python 3.10 or newer is required:

```bash
sudo pacman -S python
```

### LaTeX

`pdflatex` must be on your PATH for PDF compilation. The `texlive-basic`
package is sufficient:

```bash
sudo pacman -S texlive-basic
```

If your resume template uses additional LaTeX packages, install
`texlive-most` or individual `texlive-*` packages as needed. If PDF
compilation is not needed, this requirement can be skipped entirely by
passing `--no-pdf`.

---

## 2. Installation

```bash
# 1. Clone the repository
git clone https://github.com/L1minus1/AutoResumeTeX.git autoResume
cd autoResume

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# 3. Install the only Python dependency
pip install requests
```

Alternatively, install `requests` system-wide:

```bash
sudo pacman -S python-requests
```

All other imports (`argparse`, `json`, `logging`, `pathlib`, `subprocess`,
`sys`, `shutil`, `datetime`) are part of the Python standard library.

---

## 3. Configuration

**These steps must be completed before running the tool for the first time.**

### 3.1 LaTeX Resume Template

This tool is designed to tailor an existing resume to a specific job posting,
not to generate a resume from scratch. Before using AutoResumeTex (ART), you must edit
the included `.tex` template to contain your own personal information.

Open the template in any text editor:

```bash
vim /path/to/resume.tex
# or
nano /path/to/resume.tex
```

Replace every placeholder value that does not appear inside angle brackets (`<>`) with your
own information. This includes your name, contact details, education history,
and any other entries you wish to persist between applications.

**Leave all `<PlaceholderName>` values exactly as they are.** These are the
only parts of the template the tool modifies. On each run, ART reads the
job description you provide and replaces these markers with content chosen to
improve your callback odds for that specific role — relevant job titles,
tailored skill categories, and a targeted objective statement. Everything else
stays exactly as you wrote it.

The intent is that your core qualifications and personal details are yours to
maintain, while the AI handles the mechanical work of matching your experience
to what a given employer is looking for.

Once you have edited the template, open `template_processor.py` and update the
`HARDCODED_FILENAME` constant at the top of the file to point to the absolute
path of your `.tex` file:

```python
# template_processor.py
HARDCODED_FILENAME = "/home/youruser/documents/resume.tex"
```
Alternatively, simply edit the template file in place and leave the hardcoded filname unchanged.

### 3.2 Prompt Template

The prompt template is a Markdown file that tells the AI model what to do with
the job description you provide and what JSON structure to return. The tool
ships with a working example (`promptTemplate.md`) — read it before making any
changes, as it is extensively commented.

The most important structural requirement is that the file contains exactly one instance
of the string `<DescHere>`. At runtime, this marker is replaced with the full
text of the job description you type into vim. The rest of the file is
instructions and a JSON schema example that guide the model toward returning
output that `template_processor.py` can parse.

If you modify the JSON schema in the prompt template, you must make matching
changes to `template_processor.py` and to the placeholders in your `.tex` file,
since all three must agree on the same field names.

### 3.3 Source File Constants

The following constants can be changed directly in the source files to adjust
default behaviour without passing CLI arguments every time.

| File | Constant | Default | Description |
|---|---|---|---|
| `template_processor.py` | `HARDCODED_FILENAME` | *(must be set)* | Path to your `.tex` resume template. |
| `template_processor.py` | `output_filename` | `resume.tex` | Name of the filled `.tex` file written to the working directory. |
| `ollama_prompt.py` | `DEFAULT_HOST` | `http://localhost:11434` | Ollama server URL. Change if running Ollama on a remote machine. |
| `ollama_prompt.py` | `DEFAULT_MODEL` | `qwen2.5-coder` | Model tag used when `--model` is not passed. |
| `ollama_prompt.py` | `DEFAULT_TIMEOUT` | `900` | Request timeout in seconds. **GPU users may consider reducing this.** |
| `run_resume.py` | `DEFAULT_PROMPT_TEMPLATE` | `./promptTemplate.md` | Prompt template used when `-i` is not passed. |
| `run_resume.py` | `DEFAULT_PDF_DIR` | `outputs` | Subdirectory of the working directory where PDFs are saved. |
| `run_resume.py` | `TEMP_FILE_NAME` | `.resume_desc_tmp.md` | Name of the hidden temporary file opened in vim. |
| `run_resume.py` | `DESC_MARKER` | `<DescHere>` | The marker in the prompt template that is replaced by the vim input. |

---

## 4. Usage

### 4.1 run_resume.py — Full Pipeline

The main entry point. Runs all pipeline steps in sequence.

```bash
python run_resume.py [options]
```

**Prompt / Ollama options:**

| Argument | Default | Description |
|---|---|---|
| `-i`, `--input` | `./promptTemplate.md` | Path to the Markdown prompt template. Must contain `<DescHere>`. |
| `--host` | `http://localhost:11434` | Ollama server base URL. |
| `--model` | `qwen2.5-coder` | Ollama model tag. |
| `--timeout` | `900` | HTTP request timeout in seconds. |

**PDF options:**

| Argument | Default | Description |
|---|---|---|
| `--no-pdf` | off | Generate `resume.tex` and stop. No PDF is compiled. Use this to inspect or manually edit the `.tex` before compiling. |
| `--pdf-dir` | `./outputs/` | Directory where the compiled PDF is saved. Created automatically if it does not exist. |
| `--pdf-name` | `resume-YYYYMMDD-HHMMSS` | Base filename for the PDF, without extension. Defaults to a timestamp captured at startup. |

**General:**

| Argument | Default | Description |
|---|---|---|
| `-v`, `--verbose` | off | Enable DEBUG-level logging. Prints every internal step, including the raw pdflatex output path and auxiliary file cleanup list. |

**Examples:**

```bash
# Standard run — uses all defaults
python run_resume.py

# Custom prompt template (most common override)
python run_resume.py -i promptTemplate.md

# CPU machine — larger timeout, smaller model
python run_resume.py -i promptTemplate.md --model qwen2.5-coder:3b --timeout 900

# Generate .tex only, skip PDF compilation
python run_resume.py --no-pdf

# Save PDF to a specific directory with a fixed name
python run_resume.py --pdf-dir ~/resumes --pdf-name google_swe_2026

# Remote Ollama server with verbose logging
python run_resume.py --host http://192.168.1.10:11434 -v

# Full custom run
python run_resume.py -i promptTemplate.md \
    --model qwen2.5-coder:7b --timeout 600 \
    --pdf-dir ~/resumes --pdf-name acme_corp -v
```

---

### 4.2 ollama_prompt.py — Standalone Prompter

Sends a Markdown prompt file directly to Ollama and saves the JSON response.
Useful for testing your prompt template in isolation, inspecting raw model
output, or regenerating a JSON file without going through the full pipeline.

```bash
python ollama_prompt.py [options]
```

| Argument | Default | Description |
|---|---|---|
| `-i`, `--input` | `prompt.md` | Path to the Markdown prompt file. |
| `-o`, `--output` | `.` (cwd) | Output path. If a directory, the filename is derived from the input file stem. If an explicit `.json` path, it is used directly. |
| `--host` | `http://localhost:11434` | Ollama server base URL. |
| `--model` | `qwen2.5-coder` | Ollama model tag. |
| `--timeout` | `900` | HTTP request timeout in seconds. |
| `--temperature` | `0.1` | Sampling temperature (0.0–1.0). Lower values produce more consistent, deterministic JSON output. Rarely needs changing. |
| `-v`, `--verbose` | off | Enable DEBUG-level logging. |

**Examples:**

```bash
# Test the prompt template and save JSON to the working directory
python ollama_prompt.py -i promptTemplate.md

# Save to a specific file
python ollama_prompt.py -i promptTemplate.md -o debug/output.json

# Higher timeout for CPU, fully deterministic output
python ollama_prompt.py -i promptTemplate.md --timeout 900 --temperature 0.0
```

---

### 4.3 template_processor.py — Standalone Processor

Reads a JSON file and applies its values to the `.tex` resume template.
Called automatically by `run_resume.py`, but can be run on its own to
re-apply a previously generated JSON — for example, after manually editing
the JSON to correct a model mistake — without re-running inference.

```bash
python template_processor.py <path-to-json>
```

| Argument | Description |
|---|---|
| `<path-to-json>` | (required, positional) Path to a JSON file matching the schema described in §6. |

The `.tex` template path is read from `HARDCODED_FILENAME` inside the file.
Output is always written to `resume.tex` in the current working directory.

**Example — re-apply after manually editing the JSON:**

```bash
# Edit the model's output
vim promptTemplate.json

# Re-run the processor only
python template_processor.py promptTemplate.json
```

---

## 5. Pipeline Walkthrough

### Step 1 — vim Session

`run_resume.py` creates (or truncates to zero bytes) a hidden temporary file in
the current working directory:

```
.resume_desc_tmp.md
```

vim opens this file. Paste or type the full job description for the role you
are applying to, then save and quit with `:wq`. The file content is read into
memory and the temporary file is immediately deleted — it is never left on disk
after the session ends.

If you quit vim without saving (`:q!`), or save an empty file, the pipeline
aborts with a clear error message and no further steps run.

### Step 2 — Prompt Assembly

The prompt template is read from disk. The `<DescHere>` marker is replaced with
the job description captured from vim. The result is a single string — the
complete prompt — that is passed to the model. Nothing is written to disk at
this stage.

### Step 3 — Ollama Inference (`ollama_prompt.py`)

The final prompt is sent to the Ollama `/api/chat` REST endpoint. Two
mechanisms work together to enforce JSON-only output:

- A **system message** instructs the model to return a single valid JSON object
  with no prose, no markdown fences, and no commentary.
- Ollama's **`format: json` mode** constrains the token sampler at the engine
  level so that structurally invalid JSON cannot be produced.

Temperature is set to `0.1` by default, keeping output deterministic and
reducing the chance of the model improvising field names or nesting structures
that do not match the schema.

If the model returns accidental markdown code fences (` ```json ... ``` `),
they are stripped before parsing. The response is then parsed with
`json.loads()` and returned as a Python dict.

**This step is the slowest part of the pipeline**, particularly on CPU. A 3b
model on a modern CPU typically takes 3–8 minutes. A 7b model may take
10–20 minutes. The `--timeout` argument controls how long the HTTP client waits
before giving up; set it generously if you are not using a GPU.

### Step 4 — JSON Saved to Disk

The parsed JSON dict is written to the working directory. The output filename
is derived from the prompt template filename:

```
promptTemplate.md  →  promptTemplate.json
```

This file is useful for debugging (inspect what the model actually returned)
and for re-running `template_processor.py` standalone if the `.tex` output
needs to be regenerated without calling Ollama again.

### Step 5 — Template Processing (`template_processor.py`)

The processor loads the JSON file and the `.tex` resume template. It performs
simple string substitution, replacing every `<PlaceholderName>` in the template
with the corresponding value from the JSON. Substitutions happen in three
passes:

- **Job1 and Job2** — each JSON key is prefixed with its label (e.g.
  `"JobTitle"` under `"Job1"` replaces `<Job1 JobTitle>` in the template).
- **ObjectiveStatement** — the single key replaces `<ObjectiveStatement>`.
- **Skills** — each `SkillType-N` entry is split into two replacements: the
  category name replaces `<SkillType-N>` and the skill list replaces
  `<SkillsN>`.

The completed template is written to `resume.tex` in the current working
directory. If a placeholder in the template has no matching JSON key (due to a
typo or a model omission), it is left unreplaced with no error — check the
output `.tex` file if something looks off.

### Step 6 — PDF Compilation

`pdflatex` is called twice on `resume.tex`. Two passes are necessary so that
internal references such as page numbers and hyperlinks resolve correctly on the
second pass. The flags used are:

- `-interaction=nonstopmode` — never pauses for user input on errors
- `-output-directory` — all output goes directly into the PDF directory
- `-jobname` — controls the output filename

After both passes complete, all LaTeX auxiliary files are deleted from the
output directory. These include `.aux`, `.log`, `.out`, `.toc`, `.fls`,
`.synctex.gz`, and several others. Only the `.pdf` is kept.

The PDF filename defaults to `resume-YYYYMMDD-HHMMSS.pdf`, using a timestamp
captured at startup so every run produces a uniquely named file. Both the
output directory and filename can be overridden with `--pdf-dir` and
`--pdf-name`. Pass `--no-pdf` to skip this step entirely and stop after
`resume.tex` is written.

---

## 6. JSON Schema Reference

The model must return a JSON object with exactly this structure. Any deviation
will cause `template_processor.py` to raise an error or silently leave
placeholders unreplaced.

```json
{
  "Job1": {
    "StartDate":      "August 2023",
    "EndDate":        "December 2023",
    "CompanyName":    "Example Corp",
    "Location":       "Los Angeles",
    "JobTitle":       "Customer Support Specialist",
    "JobDescription": "One sentence summary of the role.",
    "Experience1":    "First relevant bullet point",
    "Experience2":    "Second relevant bullet point",
    "Experience3":    "Third relevant bullet point"
  },
  "Job2": {
    "StartDate":      "...",
    "EndDate":        "...",
    "CompanyName":    "...",
    "Location":       "...",
    "JobTitle":       "...",
    "JobDescription": "...",
    "Experience1":    "...",
    "Experience2":    "...",
    "Experience3":    "..."
  },
  "Skills": {
    "SkillType-1": { "Computer": "Software Troubleshooting, Microsoft Office" },
    "SkillType-2": { "Business": "Account Management, Phone Etiquette" },
    "SkillType-3": { "Customer Service": "Conflict Resolution, Deescalation" }
  },
  "ObjectiveStatement": {
    "ObjectiveStatement": "One to two sentence career objective tailored to the role."
  }
}
```

**Rules the model output must follow:**

- All four top-level keys (`Job1`, `Job2`, `Skills`, `ObjectiveStatement`) must
  be present. A missing key causes a `KeyError`.
- `ObjectiveStatement` must be a single-key dict, not a bare string. A bare
  string causes `'str' object has no attribute 'items'`.
- Each `Skills` entry must be one level of nesting: `{"SkillType-N":
  {"Category Name": "skill list"}}`. A flat structure breaks the skills loop.
- The entire response must be one valid JSON object. Multiple separate `{}`
  blocks are not valid JSON.

---

## 7. LaTeX Placeholder Reference

Every `<placeholder>` in the `.tex` template is replaced by the value at the
corresponding JSON path. Matching is case-sensitive and exact.

| Template placeholder | JSON path |
|---|---|
| `<Job1 StartDate>` | `Job1.StartDate` |
| `<Job1 EndDate>` | `Job1.EndDate` |
| `<Job1 CompanyName>` | `Job1.CompanyName` |
| `<Job1 Location>` | `Job1.Location` |
| `<Job1 JobTitle>` | `Job1.JobTitle` |
| `<Job1 JobDescription>` | `Job1.JobDescription` |
| `<Job1 Experience1>` | `Job1.Experience1` |
| `<Job1 Experience2>` | `Job1.Experience2` |
| `<Job1 Experience3>` | `Job1.Experience3` |
| `<Job2 StartDate>` | `Job2.StartDate` |
| `<Job2 EndDate>` | `Job2.EndDate` |
| `<Job2 CompanyName>` | `Job2.CompanyName` |
| `<Job2 Location>` | `Job2.Location` |
| `<Job2 JobTitle>` | `Job2.JobTitle` |
| `<Job2 JobDescription>` | `Job2.JobDescription` |
| `<Job2 Experience1>` | `Job2.Experience1` |
| `<Job2 Experience2>` | `Job2.Experience2` |
| `<Job2 Experience3>` | `Job2.Experience3` |
| `<SkillType-1>` | Key name of `Skills.SkillType-1` (the category label) |
| `<Skills1>` | Value of `Skills.SkillType-1` (comma-separated skill list) |
| `<SkillType-2>` | Key name of `Skills.SkillType-2` |
| `<Skills2>` | Value of `Skills.SkillType-2` |
| `<SkillType-3>` | Key name of `Skills.SkillType-3` |
| `<Skills3>` | Value of `Skills.SkillType-3` |
| `<ObjectiveStatement>` | `ObjectiveStatement.ObjectiveStatement` |

Any placeholder with no matching JSON key is left as-is in the output with no
warning. If something looks wrong in the final PDF, open `resume.tex` and
search for unreplaced `<` characters.

---

## 8. Troubleshooting

**`Read timed out`**
The model is taking longer than `--timeout` allows. Extend the timeout and/or
use a smaller model:
```bash
python run_resume.py -i promptTemplate.md --model qwen2.5-coder:3b --timeout 900
```
To avoid passing `--timeout` every time, raise `DEFAULT_TIMEOUT` in
`ollama_prompt.py`.

**`'str' object has no attribute 'items'`**
The model returned `ObjectiveStatement` as a bare string. Ensure your prompt
template schema shows it wrapped in a dict:
```json
"ObjectiveStatement": { "ObjectiveStatement": "..." }
```

**`Cannot reach Ollama` / `ConnectionError`**
The Ollama service is not running:
```bash
sudo systemctl start ollama
curl http://localhost:11434
```

**`KeyError: 'Job1'` (or any top-level key)**
The model omitted a required top-level key. Run `ollama_prompt.py` standalone
to inspect the raw JSON output:
```bash
python ollama_prompt.py -i promptTemplate.md -o debug.json
cat debug.json
```
If the key is consistently missing, add an explicit reminder to your prompt
template that all four keys are required.

**`json.JSONDecodeError`**
The model returned something other than valid JSON. This is usually transient —
re-run. If it happens consistently, lower the temperature and ensure the schema
example in the prompt template is valid JSON itself:
```bash
python ollama_prompt.py -i promptTemplate.md --temperature 0.0
```

**`<PlaceholderName>` appears unreplaced in the PDF**
Either the JSON key name does not exactly match the placeholder (case-sensitive,
including spaces), or the model omitted that field. Open the generated
`promptTemplate.json` and confirm the key is present and spelled correctly.

**`pdflatex: command not found`**
LaTeX is not installed, or is not on your PATH:
```bash
sudo pacman -S texlive-basic
```
If you do not need PDF output, pass `--no-pdf` to skip compilation entirely.

**PDF compiles but layout looks wrong**
The model may have inserted LaTeX special characters (e.g. `&`, `%`, `_`, `#`)
into a field value. These must be escaped in LaTeX (`\&`, `\%`, etc.).
Open `resume.tex`, find the affected section, and escape the characters
manually, or add an instruction to your prompt template telling the model to
avoid them.

**vim opens but the pipeline receives empty content**
Save with `:wq`, not `:q!`. If you accidentally closed vim without saving,
simply re-run — the temporary file is always reset to empty at the start of
each session.

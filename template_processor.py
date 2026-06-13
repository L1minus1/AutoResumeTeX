"""
template_processor.py

Usage:
    python template_processor.py path/to/data.json

Expects a JSON file whose top-level structure is an array (or object) containing
exactly four dictionaries, in this order:
    [0] -> Job1
    [1] -> Job2
    [2] -> Skills
    [3] -> ObjectiveStatement
"""

import json
import sys
import os

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

# Hardcode the name of the secondary file you want to read and manipulate.
# Change this path to point at whatever file you need.
HARDCODED_FILENAME = "template.tex" # Uses included template by default, edit it to reflect your own personal information.


# ─────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────

def replace_in_string(source: str, find: str, replacement: str) -> str:
    """
    Returns a NEW string with every occurrence of `find` replaced by
    `replacement` inside `source`.  The original `source` string is
    not modified (strings are immutable in Python).

    Args:
        source      (str): The full text you want to search through.
        find        (str): The exact substring you want to locate.
        replacement (str): What to substitute in place of `find`.

    Returns:
        str: A copy of `source` with all occurrences replaced.

    Example:
        result = replace_in_string(file_contents, "{{NAME}}", "Alice")
    """
    return source.replace(find, replacement)


# ─────────────────────────────────────────────
# JSON LOADING
# ─────────────────────────────────────────────

def load_json_dicts(json_path: str):
    """
    Opens the JSON file at `json_path` and parses it into four dictionaries,
    returning them as a tuple: (Job1, Job2, Skills, ObjectiveStatement).

    The file is a standard single JSON object with four top-level keys:
        {
            "Job1":               { ... },
            "Job2":               { ... },
            "Skills":             { ... },
            "ObjectiveStatement": { ... }
        }

    json.load() handles this format directly — no special parsing needed.
    """
    with open(json_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)   # Parse the entire JSON file in one call

    # Rebuild Job1 and Job2 with their label prepended to every key.
    # e.g. "JobTitle" becomes "Job1 JobTitle" / "Job2 JobTitle"
    # Skills and ObjectiveStatement keys are left unchanged.
    Job1               = {f"Job1 {k}": v for k, v in data["Job1"].items()}
    Job2               = {f"Job2 {k}": v for k, v in data["Job2"].items()}
    Skills             = data["Skills"]             # Third  entry → Skills
    ObjectiveStatement = data["ObjectiveStatement"] # Fourth entry → Objective statement

    return Job1, Job2, Skills, ObjectiveStatement


# ─────────────────────────────────────────────
# HARDCODED FILE LOADING
# ─────────────────────────────────────────────

def load_hardcoded_file(filepath: str) -> str:
    """
    Opens `filepath` in read mode, copies its entire contents into a string,
    closes the file handle, and returns the string.
    """
    fh = open(filepath, "r", encoding="utf-8")   # Open in read mode
    file_contents = fh.read()                     # Copy everything to a string
    fh.close()                                    # Close the file handle explicitly
    return file_contents


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    # ── 1. Validate command-line arguments ────────────────────────────────
    if len(sys.argv) < 2:
        print("Usage: python template_processor.py <path_to_json_file>")
        sys.exit(1)

    json_path = sys.argv[1]

    if not os.path.isfile(json_path):
        print(f"Error: '{json_path}' does not exist or is not a file.")
        sys.exit(1)

    # ── 2. Load the four dictionaries from the JSON file ──────────────────
    Job1, Job2, Skills, ObjectiveStatement = load_json_dicts(json_path)

    print("Loaded dictionaries:")
    print(f"  Job1               → {Job1}")
    print(f"  Job2               → {Job2}")
    print(f"  Skills             → {Skills}")
    print(f"  ObjectiveStatement → {ObjectiveStatement}")

    # ── 3. Load the hardcoded template file into a string ─────────────────
    file_contents = load_hardcoded_file(HARDCODED_FILENAME)

    print(f"\nTemplate file ('{HARDCODED_FILENAME}') loaded — {len(file_contents)} characters.")

    # ── 4. Replace all placeholders in the template ───────────────────────

    updated_contents = file_contents

    # Job1, Job2, and ObjectiveStatement all follow the same simple pattern:
    # each key is the placeholder text, wrapped in <> in the template.
    # e.g. key "Job1 JobTitle" replaces "<Job1 JobTitle>" in the file.
    for dictionary in [Job1, Job2, ObjectiveStatement]:
        for key, value in dictionary.items():
            updated_contents = replace_in_string(updated_contents, f"<{key}>", value)

    # Skills uses a nested structure, so it needs its own loop.
    # Each top-level entry looks like:
    #   "SkillType-1": {"Customer Service": "Conflict Resolution, Deescalation"}
    #
    # From this we derive two replacements:
    #   <SkillType-1>  →  the inner key   (the category name, e.g. "Customer Service")
    #   <Skills1>      →  the inner value (the skill list,    e.g. "Conflict Resolution, Deescalation")
    #
    # The number in <Skills1> is extracted by splitting the top-level key on "-"
    # e.g. "SkillType-1".split("-")[1]  →  "1"
    for top_key, nested in Skills.items():
        skill_num    = top_key.split("-")[1]          # "1", "2", "3", etc.
        category     = list(nested.keys())[0]         # e.g. "Customer Service"
        skills_value = list(nested.values())[0]       # e.g. "Conflict Resolution, Deescalation"

        updated_contents = replace_in_string(updated_contents, f"<{top_key}>", category)
        updated_contents = replace_in_string(updated_contents, f"<Skills{skill_num}>", skills_value)

    # ── 5. Write the completed file ───────────────────────────────────────
    output_filename = "resume.tex"   # Change to your desired output filename
    with open(output_filename, "w", encoding="utf-8") as out:
        out.write(updated_contents)

    print(f"\nOutput written to '{output_filename}'.")


if __name__ == "__main__":
    main()

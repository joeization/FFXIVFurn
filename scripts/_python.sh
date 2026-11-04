# Sourced by Bash wrappers after changing to the project root.
# PYTHON may override the executable; no environment is created or modified.
if [[ -z "${PYTHON:-}" ]]; then
    if [[ -x .venv/bin/python ]]; then
        PYTHON=.venv/bin/python
    elif [[ -x .venv/Scripts/python.exe ]]; then
        PYTHON=.venv/Scripts/python.exe
    else
        PYTHON=python
    fi
fi
command -v "$PYTHON" >/dev/null || { printf 'Python executable not found: %s\n' "$PYTHON" >&2; exit 127; }

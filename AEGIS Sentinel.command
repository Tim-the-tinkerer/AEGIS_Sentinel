#!/bin/sh
# Launch AEGIS Sentinel. pygame 2.6 has macOS wheels for Python 3.9 through 3.13.
cd "$(dirname "$0")" || exit 1
VENV="${HOME}/.local/share/python-scripts/aegis-venv"
PY="${VENV}/bin/python"

if "$PY" -c "import pygame" >/dev/null 2>&1; then
    exec "$PY" antivirus.py "$@"
fi

mkdir -p "${HOME}/.local/share/python-scripts" || exit 1

list_bases() {
    for ver in 3.13 3.12 3.11 3.10 3.9; do
        name="python${ver}"
        for dir in /opt/homebrew/bin /usr/local/bin /usr/bin "${HOME}/.local/bin"; do
            cand="${dir}/${name}"
            if [ -x "$cand" ]; then
                echo "$cand"
            fi
        done
        cand=$(command -v "$name" 2>/dev/null || true)
        if [ -n "$cand" ] && [ -x "$cand" ]; then
            echo "$cand"
        fi
    done
}

CAND=$(mktemp)
list_bases | awk '!seen[$0]++' > "$CAND"
found=0
while read -r base; do
    [ -n "$base" ] || continue
    if "$base" -m venv --clear "$VENV" \
        && "$PY" -m pip install --disable-pip-version-check pygame \
        && "$PY" -c "import pygame" >/dev/null 2>&1
    then
        found=1
        break
    fi
done < "$CAND"
rm -f "$CAND"

if [ "$found" -ne 1 ]; then
    echo "antivirus: pygame needs Python 3.9 through 3.13." >&2
    echo "Python 3.14 and 3.15 have no pygame 2.6 wheel." >&2
    exit 1
fi

exec "$PY" antivirus.py "$@"

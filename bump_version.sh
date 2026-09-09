#!/usr/bin/env bash
# bump_version.sh — aggiorna la versione di PROGETTO in un colpo solo.
#
# Uso:
#   ./bump_version.sh 6.2.0
#
# Cosa fa:
#   1. Valida che la nuova versione sia in formato semver (X.Y.Z).
#   2. Verifica che manifest.json e const.py fossero già allineati PRIMA
#      del bump (se non lo erano, qualcuno li ha toccati a mano — meglio
#      fermarsi e chiedere conferma piuttosto che nascondere il problema).
#   3. Aggiorna "version" in manifest.json.
#   4. Aggiorna la costante VERSION in const.py.
#   5. Aggiorna la riga "**Versione:**" in README.md (root) — prima andava
#      fatto a mano e si disallineava puntualmente da manifest/const.
#   6. Inserisce uno stub datato in cima a CHANGELOG.md, pronto da
#      riempire con le note della release.
#
# Cosa NON fa (volutamente):
#   - non tocca gli header "# VERSION:" dei singoli file .py — quelli
#     seguono una versione indipendente e vanno aggiornati SOLO nei file
#     che modifichi davvero in questa release (vedi CHANGELOG.md);
#   - non fa commit/tag/push: resta una scelta esplicita dello sviluppatore.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="$REPO_ROOT/custom_components/elettrodomestico_monitor/manifest.json"
CONST_PY="$REPO_ROOT/custom_components/elettrodomestico_monitor/const.py"
README="$REPO_ROOT/README.md"
CHANGELOG="$REPO_ROOT/CHANGELOG.md"

usage() {
    echo "Uso: $0 <nuova_versione>"
    echo "Esempio: $0 6.2.0"
    exit 1
}

[ $# -eq 1 ] || usage

NEW_VERSION="$1"

if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "ERRORE: '$NEW_VERSION' non è in formato semver X.Y.Z" >&2
    exit 1
fi

for f in "$MANIFEST" "$CONST_PY" "$README" "$CHANGELOG"; do
    if [ ! -f "$f" ]; then
        echo "ERRORE: file atteso non trovato: $f" >&2
        exit 1
    fi
done

CURRENT_MANIFEST=$(python3 -c "import json; print(json.load(open('$MANIFEST'))['version'])")
CURRENT_CONST=$(python3 -c "
import re
src = open('$CONST_PY').read()
m = re.search(r'^VERSION\s*=\s*[\"\']([^\"\']+)[\"\']', src, re.MULTILINE)
print(m.group(1) if m else '')
")

if [ "$CURRENT_MANIFEST" != "$CURRENT_CONST" ]; then
    echo "ATTENZIONE: manifest.json ($CURRENT_MANIFEST) e const.py ($CURRENT_CONST)"
    echo "erano già disallineati PRIMA di questo bump. Controlla manualmente"
    echo "prima di procedere: qualcuno potrebbe aver modificato uno dei due"
    echo "file a mano bypassando questo script."
    exit 1
fi

if [ "$CURRENT_MANIFEST" = "$NEW_VERSION" ]; then
    echo "ERRORE: la versione $NEW_VERSION è già quella corrente." >&2
    exit 1
fi

echo "Versione corrente: $CURRENT_MANIFEST  ->  Nuova versione: $NEW_VERSION"

# ── 1. manifest.json ────────────────────────────────────────────────────────
python3 -c "
import json
path = '$MANIFEST'
with open(path) as f:
    data = json.load(f)
data['version'] = '$NEW_VERSION'
with open(path, 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write('\n')
"

# ── 2. const.py ──────────────────────────────────────────────────────────────
python3 -c "
import re
path = '$CONST_PY'
src = open(path, encoding='utf-8').read()
src = re.sub(
    r'^VERSION\s*=\s*[\"\'][^\"\']+[\"\']',
    'VERSION  = \"$NEW_VERSION\"',
    src, count=1, flags=re.MULTILINE,
)
with open(path, 'w', encoding='utf-8') as f:
    f.write(src)
"

# ── 3. README.md: riga "**Versione:**" ──────────────────────────────────────
python3 -c "
import re
path = '$README'
src = open(path, encoding='utf-8').read()
new_src = re.sub(
    r'(\*\*Versione:\*\*\s*)[0-9]+\.[0-9]+\.[0-9]+',
    r'\g<1>$NEW_VERSION',
    src, count=1,
)
if new_src == src:
    print('ATTENZIONE: nessuna riga \"**Versione:**\" trovata in README.md — controlla a mano.')
with open(path, 'w', encoding='utf-8') as f:
    f.write(new_src)
"

# ── 4. CHANGELOG.md: inserisce uno stub in cima (dopo il titolo/intro) ──────
TODAY=$(date +%Y-%m-%d)
STUB="## [$NEW_VERSION] - $TODAY

### Added
-

### Changed
-

### Fixed
-
"

python3 -c "
path = '$CHANGELOG'
with open(path, encoding='utf-8') as f:
    lines = f.readlines()

# Inserisce lo stub subito prima della prima riga che inizia con '## ['
# (la prima entry di release esistente), oppure in fondo al file se non
# ce n'è nessuna ancora.
insert_at = len(lines)
for i, line in enumerate(lines):
    if line.startswith('## ['):
        insert_at = i
        break

stub = '''$STUB'''
lines[insert_at:insert_at] = [stub, '\n']

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)
"

echo ""
echo "Fatto. Modificati:"
echo "  - $MANIFEST"
echo "  - $CONST_PY"
echo "  - $README"
echo "  - $CHANGELOG (stub da compilare in cima)"
echo ""
echo "Ricorda: gli header '# VERSION:' dei singoli file .py NON sono stati"
echo "toccati. Aggiorna a mano solo quelli dei file che modifichi davvero"
echo "in questa release, e riempi lo stub nel CHANGELOG."

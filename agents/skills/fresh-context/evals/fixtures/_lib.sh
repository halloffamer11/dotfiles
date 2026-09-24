# Shared by the fixture builders. Usage in a builder: . "$(dirname "$0")/_lib.sh" "$1"
set -e
dest=$1
[ -n "$dest" ] || { echo "usage: $0 <dest-dir>" >&2; exit 2; }
[ ! -e "$dest" ] || { echo "$dest exists" >&2; exit 2; }
mkdir -p "$dest"
cd "$dest"
git init -q -b main
git config user.email fixture@example.com
git config user.name fixture
base_commit() { git add -A && git commit -qm "$1"; }

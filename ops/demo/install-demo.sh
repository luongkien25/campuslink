#!/usr/bin/env bash
# Install only these public demo files. No sudoers, credentials, services or cloud resources changed.
set -euo pipefail
[[ "$(id -u)" == 0 ]] || { echo 'TV1: run sudo bash install-demo.sh on Host A'; exit 1; }
src="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
target=/opt/campuslink-demo
[[ ! -L "$target" ]] || { echo 'Refusing symlink install target'; exit 1; }
bash -n "$src/demo-host-a.sh"
python3 -c 'import ast, pathlib, sys; ast.parse(pathlib.Path(sys.argv[1]).read_text())' "$src/demo-json.py"
install -d -o root -g root -m 755 "$target"
install -o root -g root -m 755 "$src/demo-host-a.sh" "$target/demo-host-a.sh"
install -o root -g root -m 644 "$src/demo-json.py" "$target/demo-json.py"
for member in tv2 tv3 tv4; do
  if id "$member" >/dev/null 2>&1; then
    sudo -n -u "$member" test -r "$target/demo-host-a.sh"
    sudo -n -u "$member" test -r "$target/demo-json.py"
    echo "$member: demo files readable; existing OpenStack permissions unchanged"
  fi
done
sha256sum "$target/demo-host-a.sh" "$target/demo-json.py"
echo 'Installed. Per member: alias d="bash /opt/campuslink-demo/demo-host-a.sh"; d help'

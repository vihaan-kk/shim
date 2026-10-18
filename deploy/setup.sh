#!/usr/bin/env bash
# One-time install on the Brev instance (Ubuntu 24.04, x86_64). Safe to run again.
# Usage, on the instance: ~/shim/deploy/setup.sh
# Installs into your home folder: uv, Node 22, Caddy and PrusaSlicer 2.8.1 (the last
# release with a Linux AppImage), then the Python deps, OctoPrint and the npm packages.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p ~/opt ~/bin
export PATH="$HOME/.local/bin:$HOME/bin:$HOME/opt/node/bin:$PATH"

if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

node_version=v22.11.0
if [ ! -x ~/opt/node/bin/node ]; then
  curl -fsSL "https://nodejs.org/dist/$node_version/node-$node_version-linux-x64.tar.xz" | tar -xJ -C ~/opt
  mv ~/opt/node-$node_version-linux-x64 ~/opt/node
fi

if [ ! -x ~/bin/caddy ]; then
  curl -fsSL "https://caddyserver.com/api/download?os=linux&arch=amd64" -o ~/bin/caddy
  chmod +x ~/bin/caddy
fi

# PrusaSlicer's CLI still loads its GUI libraries, so install them even though we never open a window.
if [ ! -x ~/opt/prusaslicer/AppRun ]; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq libgl1 libegl1 libglu1-mesa libgtk-3-0t64 libwebkit2gtk-4.1-0 libgstreamer-plugins-base1.0-0 >/dev/null
  appimage=PrusaSlicer-2.8.1+linux-x64-newer-distros-GTK3-202409181416.AppImage
  curl -fsSL "https://github.com/prusa3d/PrusaSlicer/releases/download/version_2.8.1/$appimage" -o ~/opt/prusaslicer.AppImage
  chmod +x ~/opt/prusaslicer.AppImage
  (cd ~/opt && ./prusaslicer.AppImage --appimage-extract >/dev/null && rm -rf prusaslicer && mv squashfs-root prusaslicer)
  rm ~/opt/prusaslicer.AppImage
fi

uv sync
uv tool install octoprint >/dev/null 2>&1 || uv tool upgrade octoprint >/dev/null
npm --prefix agent/ui/web ci --no-audit --no-fund

echo "Installed. PrusaSlicer: $(~/opt/prusaslicer/AppRun --help 2>/dev/null | head -1 || echo 'did not run')"

#!/bin/sh
# Install the standalone invoice-agent executable from a GitHub Release.
#
#   curl -fsSL https://raw.githubusercontent.com/superintelligenceco/invoice-agent/main/install.sh | sh
#
# The script picks the release asset for your OS and CPU, checks it against the release's
# SHA256SUMS, and installs it as `invoice-agent` into INVOICE_AGENT_INSTALL_DIR. Run it again to
# upgrade. The executable bundles Python and every dependency; you don't need Python installed.
#
# Environment variables:
#   INVOICE_AGENT_VERSION      release tag to install, for example v0.2.0 (default: latest)
#   INVOICE_AGENT_INSTALL_DIR  where to put the executable (default: $HOME/.local/bin)

set -eu

REPO="superintelligenceco/invoice-agent"
VERSION="${INVOICE_AGENT_VERSION:-latest}"
INSTALL_DIR="${INVOICE_AGENT_INSTALL_DIR:-$HOME/.local/bin}"

say() { printf 'invoice-agent: %s\n' "$*"; }
die() { printf 'invoice-agent: error: %s\n' "$*" >&2; exit 1; }

os=$(uname -s)
arch=$(uname -m)
case "$os/$arch" in
  Linux/x86_64 | Linux/amd64) asset=invoice-agent-linux-x64 ;;
  Linux/aarch64 | Linux/arm64) asset=invoice-agent-linux-arm64 ;;
  Darwin/arm64) asset=invoice-agent-macos-arm64 ;;
  Darwin/x86_64) die "no executable for Intel Macs yet; run: pip install invoice-agent" ;;
  *) die "no executable for $os/$arch; run: pip install invoice-agent" ;;
esac

if command -v curl > /dev/null 2>&1; then
  fetch() { curl -fsSL -o "$2" "$1"; }
elif command -v wget > /dev/null 2>&1; then
  fetch() { wget -q -O "$2" "$1"; }
else
  die "install curl or wget"
fi

if command -v sha256sum > /dev/null 2>&1; then
  sha256() { sha256sum "$1" | awk '{ print $1 }'; }
elif command -v shasum > /dev/null 2>&1; then
  sha256() { shasum -a 256 "$1" | awk '{ print $1 }'; }
else
  die "install sha256sum or shasum to verify the download"
fi

if [ "$VERSION" = latest ]; then
  url="https://github.com/$REPO/releases/latest/download"
else
  url="https://github.com/$REPO/releases/download/$VERSION"
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT INT TERM

say "downloading $asset ($VERSION)"
fetch "$url/$asset" "$tmp/$asset" || die "download failed: $url/$asset"
fetch "$url/SHA256SUMS" "$tmp/SHA256SUMS" || die "download failed: $url/SHA256SUMS"

expected=$(awk -v a="$asset" '$2 == a || $2 == "*" a { print $1 }' "$tmp/SHA256SUMS")
actual=$(sha256 "$tmp/$asset")
[ -n "$expected" ] || die "$asset is not listed in SHA256SUMS"
[ "$expected" = "$actual" ] || die "checksum mismatch for $asset"
say "checksum OK"

mkdir -p "$INSTALL_DIR"
chmod +x "$tmp/$asset"
mv "$tmp/$asset" "$INSTALL_DIR/invoice-agent"
say "installed $("$INSTALL_DIR/invoice-agent" --version) to $INSTALL_DIR/invoice-agent"

case ":${PATH}:" in
  *":$INSTALL_DIR:"*) ;;
  *) say "add $INSTALL_DIR to your PATH, for example: export PATH=\"$INSTALL_DIR:\$PATH\"" ;;
esac

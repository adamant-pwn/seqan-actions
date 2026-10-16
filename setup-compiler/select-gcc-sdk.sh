#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Oleksandr Kulkov
# SPDX-License-Identifier: CC-BY-4.0

set -eo pipefail

compiler=${1:?Expected a GCC executable}
cxx=${compiler/gcc/g++}
probe_dir=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/gcc-sdk.XXXXXX")
trap 'rm -rf "$probe_dir"' EXIT

# Linking catches unsupported SDK stub libraries; Mach headers catch SDK/GCC
# incompatibilities that a trivial main() would miss.
cat > "$probe_dir/main.c" <<'SOURCE'
#include <mach/mach.h>
#include <sys/sysctl.h>
#ifdef __cplusplus
#include <vector>
#endif
int main(void) { return 0; }
SOURCE

if [[ -n "${SDKROOT:-}" ]]; then
  # An explicit SDK is a user constraint, not a hint to silently override.
  candidates=("$SDKROOT")
else
  shopt -s nullglob
  candidates=(
    "$(xcrun --sdk macosx --show-sdk-path 2>/dev/null || true)"
    "$("$compiler" -print-sysroot)"
    /Library/Developer/CommandLineTools/SDKs/MacOSX*.sdk
    /Applications/*.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX*.sdk
  )
fi

tested=()
for sdk in "${candidates[@]}"; do
  [[ -d "$sdk" ]] || continue
  sdk=$(cd "$sdk" && pwd -P)
  for previous in "${tested[@]}"; do
    [[ "$sdk" == "$previous" ]] && continue 2
  done
  tested+=("$sdk")

  if SDKROOT="$sdk" "$compiler" -isysroot "$sdk" "$probe_dir/main.c" -o "$probe_dir/c" > "$probe_dir/log" 2>&1 &&
     SDKROOT="$sdk" "$cxx" -isysroot "$sdk" -x c++ "$probe_dir/main.c" -o "$probe_dir/cxx" >> "$probe_dir/log" 2>&1; then
    printf 'SDKROOT=%s\n' "$sdk" >> "${GITHUB_ENV:?}"
    printf 'Selected SDK for %s: %s\n' "$compiler" "$sdk"
    exit 0
  fi

  printf '::group::SDK rejected by %s: %s\n' "$compiler" "$sdk"
  cat "$probe_dir/log"
  echo '::endgroup::'
done

echo "::error::No compatible macOS SDK found for $compiler. Install a compatible Xcode/Command Line Tools release or use a newer GCC. If SDKROOT is set, check that selection."
exit 1

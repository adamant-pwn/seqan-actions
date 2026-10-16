<!--
SPDX-FileCopyrightText: 2026 Oleksandr Kulkov
SPDX-License-Identifier: CC-BY-4.0
-->

# Setup Compiler

```yaml
- uses: seqan/actions/setup-compiler@main
  with:
    compiler: gcc-14
```

On macOS, GCC setup selects an SDK by compiling and linking a small C/C++
program that includes Mach headers. It tries the active Xcode/Command Line
Tools SDK, GCC's configured SDK, then other SDKs installed under
`/Library/Developer/CommandLineTools` and `/Applications`.
The first passing SDK is exported as `SDKROOT`; system-wide Xcode selection
is unchanged. This is a compatibility smoke test, not a guarantee that every
SDK API works with that compiler.

To require a particular SDK, set `SDKROOT` to its path before this action.
An explicit SDK is validated without falling back to another version.
This also supports SDKs installed outside the usual locations.

If no SDK passes, setup fails with compiler diagnostics. Provision a compatible
Xcode/Command Line Tools installation beforehand, or choose a newer GCC.
This action does not download Apple toolchains or manage Apple-account
credentials.

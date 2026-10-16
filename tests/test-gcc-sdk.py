# SPDX-FileCopyrightText: 2026 Oleksandr Kulkov
# SPDX-License-Identifier: CC-BY-4.0

from pathlib import Path
import json
import os
import subprocess
import tempfile
import textwrap

source = Path('setup-compiler/action.yml').read_text()
step = textwrap.dedent(source.split('    id: install_gcc\n', 1)[1].split('    run: |\n', 1)[1].split('\n  - name:', 1)[0])
cases = [
    ('sdk15', 'macOS', 'gcc-14', '26.1', True, True, 0, None, 'sdk15', 0),
    ('xcode', 'macOS', 'gcc-14', '26.1', False, True, 0, None, 'xcode-sdk', 0),
    ('missing', 'macOS', 'gcc-14', '26.1', False, False, 0, None, None, 1),
    ('xcrun-error', 'macOS', 'gcc-14', '26.1', False, True, 42, None, None, 42),
    ('linux', 'Linux', 'gcc-14', '26.1', False, False, 0, None, '/configured', 0),
    ('newer-gcc', 'macOS', 'gcc-15', '26.1', False, False, 0, None, '/configured', 0),
    ('older-macos', 'macOS', 'gcc-14', '15.7', False, True, 0, None, '/configured', 0),
    ('alias', 'macOS', 'gcc-third-latest', '26.1', False, True, 0, None, 'xcode-sdk', 0),
    ('explicit', 'macOS', 'gcc-14', '26.1', False, False, 0, '/caller SDK', '/caller SDK', 0),
    ('explicit-linux', 'Linux', 'gcc-14', '26.1', False, False, 0, '/caller SDK', '/caller SDK', 0),
    ('empty-sdkroot', 'macOS', 'gcc-14', '26.1', False, True, 0, '', 'xcode-sdk', 0),
]
rows = []
for name, system, compiler, version, sdk15, xcode, xcrun_status, explicit, expected, status in cases:
    with tempfile.TemporaryDirectory(prefix='sdk-selection-') as temp:
        root = Path(temp)
        binpath = root / 'bin'
        binpath.mkdir()
        if sdk15:
            (root / 'SDK 15').mkdir()
        if xcode:
            (root / 'Developer Dir').mkdir()
        scripts = {
            'sw_vers': 'echo sw_vers >> "$CALLS"; printf "%s\\n" "$MOCK_VERSION"',
            'xcrun': '''echo xcrun >> "$CALLS"
 test -z "${SDKROOT+x}"
 test "$DEVELOPER_DIR" = "$MOCK_DEVELOPER"
 if [[ "$MOCK_STATUS" != 0 ]]; then exit "$MOCK_STATUS"; fi
 printf '%s\\n' "$MOCK_SDK"''',
            'gcc-14': 'test "$1" = -v; printf "Configured with: --with-sysroot=/configured\\n" >&2',
            'gcc-15': 'test "$1" = -v; printf "Configured with: --with-sysroot=/configured\\n" >&2',
        }
        for command, body in scripts.items():
            executable = binpath / command
            executable.write_text('#!/bin/bash\nset -eu\n' + body + '\n')
            executable.chmod(0o755)
        script = step.replace('${{ inputs.compiler }}', compiler)
        script = script.replace('/Library/Developer/CommandLineTools/SDKs/MacOSX15.sdk', str(root / 'SDK 15'))
        script = script.replace('DEVELOPER_DIR=/Applications/Xcode_26.3.app/Contents/Developer', 'DEVELOPER_DIR="' + str(root / 'Developer Dir') + '"')
        script = script.replace('/Applications/Xcode_26.3.app/Contents/Developer', str(root / 'Developer Dir'))
        script = 'install() { :; }\n' + script
        env = dict(os.environ)
        env.pop('SDKROOT', None)
        env.update(PATH=f'{binpath}:{env["PATH"]}', RUNNER_OS=system,
                   GITHUB_ENV=str(root / 'environment'), GITHUB_OUTPUT=str(root / 'outputs'),
                   DEVELOPER_DIR='/caller/developer', MOCK_VERSION=version,
                   MOCK_STATUS=str(xcrun_status), MOCK_SDK=str(root / 'xcode-sdk'),
                   MOCK_DEVELOPER=str(root / 'Developer Dir'), CALLS=str(root / 'calls'))
        if explicit is not None:
            env['SDKROOT'] = explicit
        result = subprocess.run(['bash', '-euo', 'pipefail'], input=script, env=env,
                                text=True, capture_output=True, timeout=10)
        assert result.returncode == status, (name, result.returncode, result.stderr)
        exported = dict(line.split('=', 1) for line in (root / 'environment').read_text().splitlines())
        expected_path = str(root / ('SDK 15' if expected == 'sdk15' else expected)) if expected and not expected.startswith('/') else expected
        assert exported.get('SDKROOT') == expected_path, (name, exported, expected_path)
        assert 'DEVELOPER_DIR' not in exported, name
        if explicit or system != 'macOS' or compiler == 'gcc-15':
            assert not (root / 'calls').exists(), name
        if name == 'missing':
            assert '::error::' in result.stdout, name
        rows.append({'case': name, 'exit': result.returncode, 'sdk': expected})
print(json.dumps(rows, indent=2))
print(f'Passed {len(rows)}/{len(cases)} cases')

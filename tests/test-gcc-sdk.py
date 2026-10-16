# SPDX-FileCopyrightText: 2026 Oleksandr Kulkov
# SPDX-License-Identifier: CC-BY-4.0
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap

source = Path('setup-compiler/action.yml').read_text()
def step(name):
    section = source.split('  - name: ' + name + '\n', 1)[1].split('\n  - name:', 1)[0]
    return textwrap.dedent(section.split('    run: |\n', 1)[1])

cases = [
    ('active-first', 'active', True, None, False, False),
    ('configured-fallback', 'configured', True, None, False, False),
    ('clt-fallback', 'clt', True, None, False, False),
    ('xcode-fallback', 'xcode', True, None, False, False),
    ('no-compatible-sdk', None, True, None, False, False),
    ('no-installed-sdk', None, False, None, False, False),
    ('failed-xcrun', 'configured', True, None, True, False),
    ('explicit-sdk', None, True, '/caller SDK', False, False),
    ('empty-sdkroot', 'active', True, '', False, False),
    ('compiler-error', None, True, None, False, True),
]
for name, working, installed, explicit, xcrun_fail, compiler_fail in cases:
    with tempfile.TemporaryDirectory(prefix='sdk-policy-') as temp:
        root = Path(temp)
        binpath = root / 'bin'
        binpath.mkdir()
        sdks = dict(active=root/'active SDK', configured=root/'configured SDK',
                    clt=root/'CLT SDKs'/'MacOSX42.sdk',
                    xcode=root/'Applications'/'Renamed Xcode.app'/'Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX42.sdk')
        if installed:
            for sdk in sdks.values():
                sdk.mkdir(parents=True)
        output = root/'environment'
        output.write_text('EXISTING=value\n')
        calls = root/'calls'
        scripts = {
            'xcrun': 'if [[ "$XCRUN_FAIL" == 1 ]]; then exit 72; fi\nprintf "%s\\n" "$ACTIVE_SDK"',
            'gcc-14': '[[ "$1" == -print-sysroot ]]; printf "%s\\n" "$CONFIGURED_SDK"',
            'g++-14': '''[[ "$1" == -isysroot ]]
 echo "$2" >> "$CALLS"
 cat > "$PROBE_SOURCE"
 if [[ "$COMPILER_FAIL" == 1 || "$2" != "$WORKING_SDK" ]]; then
   echo "mock compiler/linker failure for $2" >&2
   exit 1
 fi''',
        }
        for command, body in scripts.items():
            p=binpath/command
            p.write_text('#!/bin/bash\nset -eu\n'+body+'\n')
            p.chmod(0o755)
        env=dict(os.environ)
        env.pop('SDKROOT', None)
        env.update(PATH=f'{binpath}:{env["PATH"]}', RUNNER_TEMP=str(root), GITHUB_ENV=str(output),
                   CC='gcc-14', CXX='g++-14', ACTIVE_SDK=str(sdks['active']), CONFIGURED_SDK=str(sdks['configured']),
                   WORKING_SDK=str(sdks[working]) if working else '', CALLS=str(calls), PROBE_SOURCE=str(root/'source'),
                   XCRUN_FAIL=str(int(xcrun_fail)), COMPILER_FAIL=str(int(compiler_fail)))
        if explicit is not None:
            env['SDKROOT']=explicit
        script=step('Select macOS SDK for GCC')
        script=script.replace('/Library/Developer/CommandLineTools/SDKs/', '"'+str(root/'CLT SDKs')+'"/')
        script=script.replace('/Applications/', '"'+str(root/'Applications')+'"/')
        r=subprocess.run(['bash','-euo','pipefail'],input=script,env=env,text=True,capture_output=True,timeout=10)
        success=bool(working or explicit)
        assert (r.returncode==0)==success,(name,r.stdout,r.stderr)
        expected='EXISTING=value\n'+(f'SDKROOT={sdks[working]}\n' if working else '')
        assert output.read_text()==expected,(name,output.read_text(),expected)
        assert not list(root.glob('gcc-sdk.*')),name
        if explicit or not installed:
            assert not calls.exists(),name
        if name=='active-first':
            assert calls.read_text().splitlines()==[str(sdks['active'])],name
        if name=='xcode-fallback':
            assert calls.read_text().splitlines()==list(map(str,sdks.values())),name
        if not success:
            assert '::error::' in r.stdout,name
        if installed and not explicit:
            assert '#include <mach/mach.h>' in (root/'source').read_text(),name
        print('PASS',name)

for system, explicit in [('macOS','/caller SDK'),('Linux','/caller SDK'),('Linux',None),('macOS',None)]:
    with tempfile.TemporaryDirectory(prefix='sdk-export-') as temp:
        root=Path(temp)
        env=dict(os.environ,RUNNER_OS=system,GITHUB_ENV=str(root/'environment'),GITHUB_OUTPUT=str(root/'outputs'))
        env.pop('SDKROOT',None)
        if explicit:
            env['SDKROOT']=explicit
        script=step('Install GCC').replace('${{ inputs.compiler }}','gcc-third-latest')
        script='install() { :; }\ngcc-14() { echo "Configured with: --with-sysroot=/configured" >&2; }\n'+script
        r=subprocess.run(['bash','-euo','pipefail'],input=script,env=env,text=True,capture_output=True,timeout=10)
        assert r.returncode==0,(system,explicit,r.stderr)
        exported=dict(line.split('=',1) for line in (root/'environment').read_text().splitlines())
        assert exported['CC']=='gcc-14' and exported['CXX']=='g++-14'
        assert exported.get('SDKROOT')==(explicit or ('/configured' if system=='Linux' else None)),exported
        print('PASS export',system,explicit)
print('Passed 14/14 cases')

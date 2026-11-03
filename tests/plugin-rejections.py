#!/usr/bin/env python3
"""Fault injection is restricted to an already installed disposable project."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--env-file', type=Path, required=True)
args = parser.parse_args()
p = args.env_file.resolve(strict=True)
base = ['docker', 'compose', '--project-directory', str(ROOT), '-f', str(ROOT/'compose.yaml')]
env = ['--env-file', str(p), '--env-file', str(ROOT/'releases/release.env')]
compose = base + env
writable = base + ['-f', str(ROOT/'compose.plugins.yaml')] + env


def run(command, data=None, success=True):
    result = subprocess.run(command, input=data, capture_output=True, cwd='/tmp')
    if (result.returncode == 0) != success:
        raise RuntimeError('Unexpected fault-injection result; output withheld')
    return result.stdout


model = json.loads(run(compose + ['config', '--format', 'json']))
assert model['name'].startswith('release-check-'), 'Disposable release-check project required'
app = run(compose + ['ps', '-q', 'app'])


def php(code):
    return run(compose + ['exec', '-T', '--user', 'www-data', 'app', 'php', '/dev/stdin'],
               ("<?php define('CLI_SCRIPT', true); require '/var/www/moodle/config.php'; " + code).encode())


def unchanged():
    assert run(compose + ['ps', '-q', 'app']) == app, 'Rejection changed the application container'
    assert php('echo empty($CFG->maintenance_enabled) ? "normal" : "maintenance";') == b'normal'


def reject(profile=p):
    run(['python3', str(ROOT/'scripts/install-plugins.py'), '--env-file', str(profile)], success=False)
    unchanged()


reject(p.parent/'missing-profile.env')
with tempfile.TemporaryDirectory() as temporary:
    openprofile = Path(temporary)/'open.env'
    openprofile.write_bytes(p.read_bytes())
    openprofile.chmod(0o644)
    reject(openprofile)


def file_operation(command):
    run(writable + ['run', '--rm', '--no-deps', '-T', 'app', 'sh', '-c', command])


path = '/var/www/moodle/public/blocks/completion_progress/'
try:
    file_operation('touch ' + path + 'unexpected-fixture.txt')
    reject()
finally:
    file_operation('rm -f ' + path + 'unexpected-fixture.txt')
try:
    file_operation('mv ' + path + '.stt-plugin.json ' + path + '.held-fixture.json')
    reject()
finally:
    file_operation('mv ' + path + '.held-fixture.json ' + path + '.stt-plugin.json')
try:
    php("set_config('version', 2027100504, 'mod_customcert');")
    reject()
finally:
    php("set_config('version', 2026100504, 'mod_customcert');")
unchanged()
print('Missing profile, open permissions, unexpected files, unmanaged collision and downgrade rejected before maintenance; alternate working directory verified.')

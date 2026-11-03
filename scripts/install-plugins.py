#!/usr/bin/env python3
"""Install the locked, offline plugin bundle through Moodle's upgrade CLI."""
import argparse
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'plugins/catalog.json'


def bundle(selection):
    catalog = json.loads(CATALOG.read_text())
    if catalog['schema'] != 1 or catalog['moodle_version'] != '5.3.0':
        raise ValueError('Unsupported catalog schema or Moodle release')
    chosen = [p for p in catalog['plugins'] if selection == 'extended' or p['selection'] == 'supported']
    versions = {p['component']: p['version'] for p in chosen}
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w') as out:
        for p in chosen:
            kind, name = p['component'].split('_', 1)
            expected = {'block': 'blocks/', 'mod': 'mod/', 'tool': 'admin/tool/'}[kind] + name
            if p['path'] != expected or not re.fullmatch(r'[a-z][a-z0-9_]*', name):
                raise ValueError('Invalid component destination')
            for dep, version in p['dependencies'].items():
                if versions.get(dep, 0) < version:
                    raise ValueError('Missing locked dependency')
            archive = ROOT / 'plugins' / p['archive']
            if archive.parent != ROOT / 'plugins/archives':
                raise ValueError('Invalid archive location')
            data = archive.read_bytes()
            if hashlib.sha256(data).hexdigest() != p['sha256']:
                raise ValueError('Archive checksum mismatch: ' + p['component'])
            hashes = {}
            total = 0
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                roots = {n.split('/')[0] for n in z.namelist()}
                if len(roots) != 1:
                    raise ValueError('Archive must have exactly one root')
                prefix = roots.pop() + '/'
                versionphp = z.read(prefix + 'version.php').decode()
                if not re.search(r'\$plugin->component\s*=\s*[\'"]' + re.escape(p['component']) + r'[\'"]', versionphp):
                    raise ValueError('Plugin identity mismatch')
                if not re.search(r'\$plugin->version\s*=\s*' + str(p['version']) + r'\s*;', versionphp):
                    raise ValueError('Plugin version mismatch')
                for info in z.infolist():
                    rel = info.filename[len(prefix):]
                    parts = PurePosixPath(rel).parts
                    if '\\' in info.filename or info.filename.startswith('/') or '..' in parts or (info.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError('Unsafe ZIP member')
                    if info.is_dir() or not rel:
                        continue
                    total += info.file_size
                    if total > 80 * 1024 * 1024 or rel in hashes:
                        raise ValueError('Oversized or duplicate archive member')
                    content = z.read(info)
                    hashes[rel] = hashlib.sha256(content).hexdigest()
                    item = tarfile.TarInfo(p['path'] + '/' + rel)
                    item.size, item.mode = len(content), 0o644
                    out.addfile(item, io.BytesIO(content))
            marker = json.dumps(dict(component=p['component'], version=p['version'], sha256=p['sha256'], files=hashes)).encode()
            item = tarfile.TarInfo(p['path'] + '/.stt-plugin.json')
            item.size, item.mode = len(marker), 0o644
            out.addfile(item, io.BytesIO(marker))
    return chosen, payload.getvalue()


def run(args, data=None):
    result = subprocess.run([str(a) for a in args], input=data, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=ROOT)
    if result.returncode:
        # Native tools may emit connection details in exceptions. Never print their output.
        raise RuntimeError('Operation failed: ' + Path(str(args[0])).name + ' (output withheld)')
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file')
    parser.add_argument('--set', choices=['supported', 'extended'], default='supported')
    parser.add_argument('--acknowledge-unsupported', action='store_true')
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--upgrade', action='store_true', help='Allow replacement of an intact previously managed plugin')
    args = parser.parse_args()
    plugins, payload = bundle(args.set)
    print('Verified offline bundle: ' + ', '.join(p['component'] + '@' + str(p['version']) for p in plugins), flush=True)
    if args.verify_only and not args.env_file:
        return
    if not args.verify_only and args.set == 'extended' and not args.acknowledge_unsupported:
        parser.error('extended requires --acknowledge-unsupported; three plugins do not declare Moodle 5.3 support')
    if not args.env_file:
        parser.error('--env-file is required')
    profile = Path(args.env_file)
    if not profile.is_absolute():
        profile = ROOT / profile
    profile = profile.resolve(strict=True)
    if profile.stat().st_mode & 0o077:
        raise ValueError('Private profile must have mode 0600 or stricter')
    run(['sh', ROOT/'scripts/preflight.sh', '--env-file', profile, '--config-only'])
    if args.verify_only:
        return
    # Use the existing environment loader to reject exported overrides and resolve Compose.
    model = json.loads(run(['sh', '-c', '. ./scripts/lib/compose-env.sh; compose_init "$1" quiet; compose config --format json', 'plugins', profile]))
    project = model['name']
    base = ['docker', 'compose', '--project-directory', ROOT, '-f', ROOT/'compose.yaml']
    suffix = ['--env-file', profile, '--env-file', ROOT/'releases/release.env']
    compose = base + suffix
    writable = base + ['-f', ROOT/'compose.plugins.yaml'] + suffix
    # A profile-local lock is private and independent for every instance.
    lockpath = profile.parent / ('.plugins-' + project + '.lock')
    fd = os.open(lockpath, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        selected = json.dumps([dict(component=p['component'], path=p['path'], version=p['version'], sha256=p['sha256']) for p in plugins])
        precheck = '''<?php
define('CLI_SCRIPT', true); require '/var/www/moodle/config.php';
if (!empty($CFG->maintenance_enabled)) throw new RuntimeException('Site is already in maintenance; preserve its state');
if ((int)$CFG->version !== 2026100500) throw new RuntimeException('Expected the locked Moodle 5.3.0 release');
$plugins = json_decode(''' + json.dumps(selected) + ''', true);
$changes = [];
foreach ($plugins as $p) {
    $path = $CFG->dirroot . '/' . $p['path'];
    if (is_link($path)) throw new RuntimeException('Plugin symlink collision');
    $dbversion = get_config($p['component'], 'version');
    if ($dbversion && $dbversion > $p['version']) throw new RuntimeException('Plugin downgrade rejected');
    if (file_exists($path)) {
        $marker = $path . '/.stt-plugin.json';
        if (!is_file($marker)) throw new RuntimeException('Unmanaged plugin collision');
        $old = json_decode(file_get_contents($marker), true, 512, JSON_THROW_ON_ERROR);
        if ($old['component'] !== $p['component']) throw new RuntimeException('Component collision');
        foreach ($old['files'] as $file => $hash) {
            if (!is_file($path . '/' . $file) || hash_file('sha256', $path . '/' . $file) !== $hash)
                throw new RuntimeException('Managed plugin locally modified');
        }
        $it = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($path, FilesystemIterator::SKIP_DOTS));
        foreach ($it as $f) {
            $rel = substr($f->getPathname(), strlen($path) + 1);
            if ($f->isLink() || ($f->isFile() && $rel !== '.stt-plugin.json' && !isset($old['files'][$rel])))
                throw new RuntimeException('Unexpected plugin files');
        }
        if ($old['sha256'] !== $p['sha256']) {
            if (!''' + ('true' if args.upgrade else 'false') + ''') throw new RuntimeException('Use --upgrade after backup and rehearsal');
            $changes[] = $p['path'];
        }
    } else $changes[] = $p['path'];
}
echo json_encode($changes);
'''
        changes = json.loads(run(compose + ['exec', '-T', '--user', 'www-data', 'app', 'php', '/dev/stdin'], precheck.encode()))
        if not changes:
            # Re-run Moodle upgrade to recover an interrupted database phase; no code mutation.
            print('Managed files already match; verifying database through Moodle CLI.', flush=True)
        run(compose + ['exec', '-T', '--user', 'www-data', 'app', 'php', '/var/www/moodle/admin/cli/maintenance.php', '--enable'])
        success = False
        try:
            run(compose + ['stop', 'web', 'cron', 'app'])
            if changes:
                # Sources were validated above. Exact fixed plugin paths only; never remove core or volumes.
                commands = ['set -eu', 'mkdir /tmp/locked-plugins', 'tar -xf - -C /tmp/locked-plugins']
                for path in changes:
                    target = '/var/www/moodle/public/' + path
                    commands += ['rm -rf -- ' + target, 'mkdir -p ' + str(PurePosixPath(target).parent),
                                 'cp -a /tmp/locked-plugins/' + path + ' ' + target,
                                 'chown -R root:root ' + target,
                                 'find ' + target + ' -type d -exec chmod 755 {} +',
                                 'find ' + target + ' -type f -exec chmod 644 {} +']
                run(writable + ['run', '--rm', '--no-deps', '-T', '--user', 'root', '--entrypoint', 'sh', 'app', '-c', '\n'.join(commands)], payload)
            # The image entrypoint generates /run/php as root before dropping privileges.
            # Starting the entire container as www-data would fail on that private tmpfs.
            def cli(model, command):
                run(model + ['run', '--rm', '--no-deps', '-T', 'app', 'su', '-s', '/bin/sh',
                             'www-data', '-c', 'exec php /var/www/moodle/admin/cli/' + command])
            cli(writable, 'upgrade.php --non-interactive')
            cli(compose, 'purge_caches.php')
            cli(compose, 'maintenance.php --disable')
            success = True
        finally:
            # Never leave a writable running service. Failed upgrades stay offline in maintenance.
            run(compose + ['up', '-d', '--no-deps', '--wait', 'app'])
            if success:
                run(compose + ['up', '-d', '--no-deps', '--wait', 'web', 'cron'])
            else:
                print('FAILED: web/cron remain stopped and maintenance enabled. Preserve evidence; restore the complete checkpoint in isolation.', file=sys.stderr)
        run(compose + ['exec', '-T', '--user', 'www-data', 'app', 'php', '/usr/local/bin/check-runtime.php'])
        verify = "<?php define('CLI_SCRIPT', true); require '/var/www/moodle/config.php'; "
        for p in plugins:
            verify += "if ((int)get_config('" + p['component'] + "', 'version') !== " + str(p['version']) + ") throw new RuntimeException('Plugin database version mismatch'); "
        run(compose + ['exec', '-T', '--user', 'www-data', 'app', 'php', '/dev/stdin'], verify.encode())
        print('Plugin database upgrade complete; normal read-only services restored.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        sys.exit(1)

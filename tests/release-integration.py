#!/usr/bin/env python3
"""Build and exercise a release only in new, randomly named Linux projects."""
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
ENV = dict(os.environ)
ENV.pop('TZ', None)


def run(args, *, success=True, data=None, quiet=False):
    result = subprocess.run([str(a) for a in args], input=data, env=ENV,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if success is not None and (result.returncode == 0) != success:
        # Profiles/secrets are never command arguments or printed by this runner.
        if not quiet:
            print(result.stdout.decode(errors='replace'), flush=True)
        raise RuntimeError('Integration command returned an unexpected result: ' + str(args[0]))
    if not quiet and success is not False:
        print(result.stdout.decode(errors='replace'), end='', flush=True)
    return result.stdout.decode(errors='replace')


def compose(profile, *args, **kwargs):
    return run(['docker', 'compose', '--project-directory', ROOT, '-f', ROOT/'compose.yaml',
                '--env-file', profile, '--env-file', ROOT/'releases/release.env', *args], **kwargs)


def login(port, password):
    base = f'http://127.0.0.1:{port}'
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    with opener.open(base+'/login/index.php', timeout=60) as response:
        html = response.read().decode()
    token = re.search(r'name="logintoken"\s+value="([^"]+)"', html)
    if not token:
        raise RuntimeError('Login token missing')
    data = urllib.parse.urlencode(dict(username='releaseadmin', password=password,
                                      logintoken=token.group(1))).encode()
    with opener.open(base+'/login/index.php', data=data, timeout=60) as response:
        response.read()
    with opener.open(base+'/my/', timeout=60) as response:
        html = response.read().decode()
        if '/login/index.php' in response.url or 'data-userid="0"' in html:
            raise RuntimeError('Authenticated dashboard unavailable')
        if 'logout.php' not in html:
            raise RuntimeError('Login did not produce an authenticated session')
    print('HTTP administrator login and dashboard verified.', flush=True)


with tempfile.TemporaryDirectory(prefix='moodle-release-') as directory:
    work = Path(directory)
    token = secrets.token_hex(5)
    password = 'TestOnly9!' + secrets.token_hex(16)
    profiles = []
    names = ['release-check-'+token+'-'+suffix for suffix in ['source', 'restore', 'reject']]
    for index, name in enumerate(names):
        profile = work/(name+'.env')
        profile.write_text(f'''COMPOSE_PROJECT_NAME={name}
IMAGE_NAMESPACE=release-check-{token}
MOODLE_HTTP_PORT={28881+index}
MOODLE_WWWROOT=http://127.0.0.1:{28881+index}
MOODLE_HTTP_BIND=127.0.0.1
MOODLE_SSLPROXY=false
MOODLE_REVERSEPROXY=true
TZ=UTC
POSTGRES_PASSWORD={password}
MOODLE_ADMIN_PASSWORD={password}
MOODLE_ADMIN_USER=releaseadmin
MOODLE_ADMIN_EMAIL=admin@moodle.invalid
MOODLE_SITE_FULLNAME=Release validation
MOODLE_SITE_SHORTNAME=Validation
MOODLE_LANG=en
''')
        profile.chmod(0o600)
        profiles.append(profile)
        run(['sh', 'scripts/preflight.sh', '--env-file', profile, '--fresh-install'])

    def fixture(profile, mode):
        project = names[profiles.index(profile)]
        compose(profile, 'exec', '-T', '--user', 'www-data',
                '-e', 'COMPOSE_TEST_PROJECT='+project, '-e', 'COMPOSE_TEST_MODE='+mode,
                'app', 'php', '/dev/stdin', data=(ROOT/'tests/release-fixture.php').read_bytes())

    try:
        print('Building and installing new release.', flush=True)
        run(['sh', 'scripts/install.sh', '--env-file', profiles[0]])
        version = compose(profiles[0], 'exec', '-T', 'db', 'postgres', '--version')
        if 'PostgreSQL) 17.' not in version:
            raise RuntimeError('Expected PostgreSQL 17')
        version = compose(profiles[0], 'exec', '-T', 'app', 'cat', '/var/www/moodle/.build-version')
        if version.strip() != '5.3.0':
            raise RuntimeError('Expected Moodle 5.3.0')
        api_diagnostic = compose(profiles[0], 'exec', '-T', '--user', 'www-data',
                                 'app', 'php', '-d', 'display_errors=1', '-d', 'log_errors=0',
                                 '/dev/stdin', success=None, data=b'''<?php
register_shutdown_function(function () {
    if ($error = error_get_last()) {
        echo 'OpenAPI shutdown diagnostic: ' . json_encode($error) . "\\n";
    }
});
define('CLI_SCRIPT', true);
require '/var/www/moodle/config.php';
$CFG->debug = DEBUG_DEVELOPER;
$CFG->debugdisplay = true;
error_reporting(E_ALL);
ini_set('display_errors', '1');
ini_set('log_errors', '0');
echo "Generating OpenAPI schema in disposable CLI process.\\n";
try {
    $response = \\core\\di::get(\\core\\router\\apidocs::class)->openapi_docs(new \\GuzzleHttp\\Psr7\\Response());
    $schema = json_decode((string)$response->getBody(), true, 512, JSON_THROW_ON_ERROR);
    if (empty($schema['openapi']) || empty($schema['paths'])) {
        throw new RuntimeException('OpenAPI schema is incomplete');
    }
    echo "OpenAPI schema generation verified.\\n";
} catch (Throwable $error) {
    echo get_class($error) . ': ' . $error->getMessage() . "\\n" . $error->getTraceAsString() . "\\n";
    exit(1);
}
''')
        compose(profiles[0], 'exec', '-T', '--user', 'www-data', 'app',
                'php', '/usr/local/bin/check-runtime.php')
        compose(profiles[0], 'exec', '-T', '--user', 'www-data', 'app', 'php', '/dev/stdin',
                data=(ROOT/'tests/normal-operations.php').read_bytes())
        fixture(profiles[0], 'seed')
        compose(profiles[0], 'exec', '-T', '--user', 'www-data',
                '-e', 'COMPOSE_TEST_PROJECT='+names[0], 'app', 'php', '/dev/stdin',
                data=(ROOT/'tests/certstudio-functional.php').read_bytes())
        run(['python3', ROOT/'scripts/install-plugins.py', '--env-file', profiles[0]])
        run(['python3', ROOT/'tests/plugin-rejections.py', '--env-file', profiles[0]])
        # Verify the optional archive separately after the default bundle has installed.
        compose(profiles[0], 'exec', '-T', 'app', 'test', '!', '-e',
                '/var/www/moodle/public/admin/tool/log/store/xapi')
        run(['python3', ROOT/'scripts/install-plugins.py', '--env-file', profiles[0],
             '--set', 'xapi-oidc'])
        login(28881, password)
        compose(profiles[0], 'exec', '-T', '--user', 'www-data', 'app',
                'php', 'admin/cli/cron.php', '--keep-alive=0')
        fixture(profiles[0], 'verify')
        compose(profiles[0], 'restart', 'db', 'redis', 'app', 'web', 'cron')
        compose(profiles[0], 'up', '-d', '--wait', 'app', 'web', 'cron')
        fixture(profiles[0], 'verify')
        login(28881, password)

        model = json.loads(compose(profiles[0], 'config', '--format', 'json', quiet=True))
        image = model['services']['app']['image']
        rejected = run(['docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'sh', image,
             '-c', 'mkdir -p /tmp/source /tmp/target; printf expected > /tmp/ref; '
                   'printf other-release > /tmp/target/.deployment-ref; '
                   'sh /usr/local/bin/init-code.sh /tmp/source /tmp/target /tmp/ref'], success=False, quiet=True)
        if 'moodle-code belongs to a different Moodle release' not in rejected:
            raise RuntimeError('Code initialization failed for an unexpected reason')
        print('Different Moodle code release rejected.', flush=True)

        backup = work/'backup'
        run(['sh', 'scripts/backup.sh', '--env-file', profiles[0], backup])
        mismatch = work/'mismatch'
        shutil.copytree(backup, mismatch)
        with (mismatch/'release.env').open('a') as stream:
            stream.write('\n# Deliberately different release for rejection test\n')
        files = [line.split('  ', 1)[1] for line in (mismatch/'SHA256SUMS').read_text().splitlines()]
        (mismatch/'SHA256SUMS').write_text(''.join(
            hashlib.sha256((mismatch/name).read_bytes()).hexdigest()+'  '+name+'\n' for name in files))
        rejected = run(['sh', 'scripts/restore.sh', '--env-file', profiles[2], '--backup', mismatch],
                       success=False, quiet=True)
        if 'Restore requires the matching release metadata' not in rejected:
            raise RuntimeError('Restore failed for a reason other than release mismatch')
        print('Different restore release rejected.', flush=True)
        run(['sh', 'scripts/restore.sh', '--env-file', profiles[1], '--backup', backup])
        fixture(profiles[1], 'verify')
        compose(profiles[1], 'exec', '-T', '--user', 'www-data',
                '-e', 'COMPOSE_TEST_PROJECT='+names[1], 'app', 'php', '/dev/stdin',
                data=(ROOT/'tests/certstudio-functional.php').read_bytes())
        login(28882, password)
        try:
            request = urllib.request.Request('http://127.0.0.1:28882/api/rest/v2/openapi.json',
                                             headers={'Accept': 'application/json'})
            with urllib.request.urlopen(request, timeout=60) as response:
                print('OpenAPI HTTP status:', response.status, flush=True)
        except urllib.error.HTTPError as error:
            print('OpenAPI HTTP diagnostic:', error.code, error.read(8192).decode(errors='replace'), flush=True)
        run(['sh', 'scripts/smoke-test.sh', '--env-file', profiles[1]])
        if 'OpenAPI schema generation verified.' not in api_diagnostic:
            raise RuntimeError('OpenAPI CLI generation failed; see diagnostic above')
        print('Fresh release, persistence, backup and isolated restoration passed.', flush=True)
    except Exception:
        for profile in profiles[:2]:
            compose(profile, 'logs', '--no-color', '--tail', '60', 'app', 'web')
        raise
    finally:
        # Only the random projects whose absence was checked before this run.
        for profile in profiles:
            compose(profile, 'down', '--volumes', '--remove-orphans')

#!/usr/bin/env python3
"""Offline supply-chain regressions; no services or private profiles are used."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('plugins', ROOT/'scripts/install-plugins.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BundleTests(unittest.TestCase):
    def test_locked_distribution(self):
        plugins, _ = module.bundle('supported')
        self.assertEqual([p['component'] for p in plugins], ['block_completion_progress', 'mod_certstudio'])
        self.assertEqual(set((ROOT/'plugins/archives').glob('*.zip')),
                         {ROOT/'plugins'/p['archive'] for p in plugins})

    def test_optional_xapi_distribution(self):
        plugins, _ = module.bundle('xapi-oidc')
        self.assertEqual([p['component'] for p in plugins], ['logstore_xapi'])
        self.assertEqual(set((ROOT/'plugins/optional').glob('*.zip')),
                         {ROOT/'plugins'/p['archive'] for p in plugins})

    def invalid(self, *, member=None, symlink=False, mutation=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'plugins/archives').mkdir(parents=True)
            data = io.BytesIO()
            with zipfile.ZipFile(data, 'w') as z:
                z.writestr('root/version.php', "<?php $plugin->component='block_fixture'; $plugin->version=2026100500;")
                if member:
                    info = zipfile.ZipInfo(member)
                    if symlink:
                        info.create_system = 3
                        info.external_attr = 0o120777 << 16
                    z.writestr(info, b'fixture')
            archive = data.getvalue()
            (root/'plugins/archives/fixture.zip').write_bytes(archive)
            p = dict(component='block_fixture', path='blocks/fixture', version=2026100500,
                     archive='archives/fixture.zip', sha256=hashlib.sha256(archive).hexdigest(),
                     selection='supported', dependencies={})
            if mutation:
                mutation(p)
            catalog = root/'plugins/catalog.json'
            catalog.write_text(json.dumps(dict(schema=1, moodle_version='5.3.0', plugins=[p])))
            oldroot, oldcatalog = module.ROOT, module.CATALOG
            try:
                module.ROOT, module.CATALOG = root, catalog
                with self.assertRaises(ValueError):
                    module.bundle('supported')
            finally:
                module.ROOT, module.CATALOG = oldroot, oldcatalog

    def test_traversal(self):
        self.invalid(member='root/../../escape.php')

    def test_symlink(self):
        self.invalid(member='root/link.php', symlink=True)

    def test_checksum(self):
        self.invalid(mutation=lambda p: p.update(sha256='0'*64))

    def test_core_collision(self):
        self.invalid(mutation=lambda p: p.update(path='admin'))

    def test_missing_dependency(self):
        self.invalid(mutation=lambda p: p.update(dependencies={'tool_certificate': 2026100600}))


if __name__ == '__main__':
    unittest.main()

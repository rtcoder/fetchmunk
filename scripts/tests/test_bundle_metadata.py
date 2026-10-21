import importlib.metadata
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bundle_metadata as metadata


class BundleMetadataTests(unittest.TestCase):
    def test_only_shipped_distributions_and_available_license_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('gallery_dl', 'pytest', 'missing'):
                info = root / f'{name}-1.0.dist-info'
                info.mkdir()
                (info / 'METADATA').write_text(f'Name: {name}\nVersion: 1.0\nLicense-Expression: MIT\n')
                (root / f'{name}.py').write_text('')
                (info / 'RECORD').write_text(f'{name}.py,,\n{info.name}/LICENSE,,\n')
                if name != 'missing':
                    (info / 'LICENSE').write_text(f'License text for {name}\n')
            runtime_license = root / 'LICENSE.txt'
            runtime_license.write_text('Python license fixture\n')
            resources = root / 'Resources'
            result = metadata.generate(
                resources, '0.1.0', '3.13.16', runtime_license,
                [root / 'gallery_dl.py', root / 'missing.py'],
                list(importlib.metadata.distributions(path=[str(root)])),
            )
            self.assertEqual([d['name'] for d in result['distributions']], ['gallery_dl', 'missing'])
            self.assertEqual(result['missing_license_texts'], ['missing'])
            self.assertEqual(result['gallery_dl_version'], '1.0')
            text = (resources / 'THIRD_PARTY_NOTICES.txt').read_text()
            self.assertIn('MISSING LICENSE TEXT: missing', text)
            self.assertNotIn('pytest', text)
            self.assertNotIn(str(root), text)
            self.assertNotIn(str(root), json.dumps(result))
            self.assertEqual((resources / result['python_license']).read_text(), 'Python license fixture\n')
            metadata.validate(resources, '0.1.0')
            with self.assertRaises(ValueError):
                metadata.validate(resources, '9.9.9')
            notices = resources / 'THIRD_PARTY_NOTICES.txt'
            original = notices.read_bytes()
            notices.write_bytes(original + b'changed')
            with self.assertRaises(ValueError):
                metadata.validate(resources, '0.1.0')
            notices.write_bytes(original)
            (resources / result['distributions'][0]['license_files'][0]).unlink()
            with self.assertRaises(ValueError):
                metadata.validate(resources, '0.1.0')

    def test_notice_without_license_is_reported_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            info = root / 'gallery_dl-1.0.dist-info'
            info.mkdir()
            (info / 'METADATA').write_text('Name: gallery_dl\nVersion: 1.0\n')
            (info / 'RECORD').write_text('gallery_dl.py,,\ngallery_dl-1.0.dist-info/NOTICE,,\n')
            (info / 'NOTICE').write_text('Attribution only')
            (root / 'gallery_dl.py').write_text('')
            (root / 'LICENSE.txt').write_text('Python fixture')
            result = metadata.generate(root / 'Resources', '1', '3', root / 'LICENSE.txt',
                                       [root / 'gallery_dl.py'],
                                       importlib.metadata.distributions(path=[str(root)]))
            self.assertEqual(result['missing_license_texts'], ['gallery_dl'])
            self.assertEqual(len(result['distributions'][0]['license_files']), 1)
            metadata.validate(root / 'Resources', '1')

    def test_missing_python_license_fails_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                metadata.generate(Path(tmp), '1', '3', Path(tmp) / 'absent', [], [])

    def test_missing_manifest_is_rejected_before_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                metadata.validate(Path(tmp), '1')


if __name__ == '__main__':
    unittest.main()

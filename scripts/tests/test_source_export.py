import json
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import export_supported_sources as export


class SourceExportTests(unittest.TestCase):
    def test_metadata_only_inherited_patterns_and_domain_limits(self):
        class Base:
            pattern = r'https://(?:a|b)\.example/.*'
            root = 'https://a.example'
            category = 'example'
        class Example(Base):
            example = 'https://a.example/123'
            def __init__(self):
                raise AssertionError('must not instantiate')
        row = export.record(Example, 'gallery-dl')
        self.assertEqual(row['observed_domains'], ['a.example'])
        self.assertEqual(row['patterns'], [Base.pattern])
        self.assertEqual(row['category'], 'example')

    def test_tests_and_pseudo_urls(self):
        class Example:
            IE_NAME = 'example:test'
            _VALID_URL = ['example:.*', r'https://.*']
            _TEST = {'url': 'example:123'}
            _TESTS = [{'url': 'https://media.example/path'}, {'info_dict': {}}]
        row = export.record(Example, 'yt-dlp')
        self.assertEqual(row['id'], 'example:test')
        self.assertEqual(row['observed_domains'], ['media.example'])
        self.assertIn('example:123', row['example_urls'])

    def test_pinned_generated_inventory_is_reproducible_without_network(self):
        with patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')):
            inventory = export.collect()
        root = Path(__file__).resolve().parents[2] / 'docs' / 'sources'
        for engine, data in inventory.items():
            self.assertEqual(data['extractor_count'], len(data['extractors']))
            self.assertGreater(data['extractor_count'], 100)
            self.assertEqual(len({row['class'] for row in data['extractors']}), data['extractor_count'])
            self.assertEqual(json.loads((root / f'{engine}.json').read_text()), data)
            self.assertEqual((root / f'{engine}.txt').read_text(), export.render_text(data))
        self.assertTrue(any(row['class'] == 'GenericIE' for row in inventory['yt-dlp']['extractors']))


if __name__ == '__main__':
    unittest.main()

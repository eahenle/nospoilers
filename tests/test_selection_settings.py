"""Post-inference offers must use the constraints used for the final eligibility check."""
import tempfile
import unittest
from pathlib import Path

from nospoilers.core import utcnow
from nospoilers.server import Service
from nospoilers.store import Store


class SelectionSettingsTests(unittest.TestCase):
    def check_settings_change(self, replacement, expected_index):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'state.db')
            offers = [
                {'region': region, 'provider': provider, 'access_type': 'included',
                 'source': 'tmdb', 'checked_at': utcnow().isoformat(),
                 'url': f'https://www.themoviedb.org/movie/1/watch?locale={region}'}
                for region, provider in [('US', 'Old'), ('GB', 'New')]
            ]
            store.ingest({'version': 1, 'mode': 'real', 'movies': [
                {'id': 'local:a', 'title': 'Fixture', 'year': 2020,
                 'runtime': 90, 'availability': offers}]})
            store.save_settings('real', {'region': 'US', 'providers': ['Old']})

            class ChangingSelector:
                name = 'fixture'

                def select(self, preference, candidates, mood):
                    Store(store.path).save_settings('real', replacement)
                    return {'id': candidates[0]['id']}

            result = Service(store, ChangingSelector()).pick('session', 'real')
            if expected_index is None:
                self.assertEqual(result['code'], 'no_acceptable_candidate')
                self.assertNotIn('movie', result)
            else:
                self.assertEqual(result['movie']['availability'], [offers[expected_index]])
                self.assertEqual(set(result['movie']), {'id', 'title', 'year', 'runtime', 'availability'})

    def test_returned_offers_follow_settings_changed_during_inference(self):
        self.check_settings_change({'region': 'GB', 'providers': ['New']}, 1)

    def test_unchanged_settings_preserve_offers(self):
        self.check_settings_change({'region': 'US', 'providers': ['Old']}, 0)

    def test_newly_ineligible_movie_is_not_presented(self):
        for constraints in ({'region': 'GB', 'providers': ['Missing']}, {'max_runtime': 60}):
            with self.subTest(constraints=constraints):
                self.check_settings_change(constraints, None)


if __name__ == '__main__':
    unittest.main()

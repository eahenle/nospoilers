"""The documented seven-day lifetime is exclusive at the expiry instant."""
import unittest
from datetime import datetime, timedelta, timezone

from nospoilers.core import eligible, fresh, public_movie


class OfferExpiryTests(unittest.TestCase):
    def test_freshness_boundary_controls_eligibility_and_public_offers(self):
        checked = datetime(2026, 1, 1, tzinfo=timezone.utc)
        offer = {'region': 'US', 'provider': 'Fixture', 'access_type': 'included',
                 'source': 'tmdb', 'checked_at': checked.isoformat(),
                 'url': 'https://www.themoviedb.org/movie/1/watch?locale=US'}
        movie = {'id': 'fixture:a', 'title': 'Fictional', 'year': 2020,
                 'availability': [offer]}
        constraints = {'region': 'US', 'providers': ['Fixture']}
        cases = [
            (timedelta(microseconds=-1), False),
            (timedelta(0), True),
            (timedelta(days=7, microseconds=-1), True),
            (timedelta(days=7), False),
            (timedelta(days=7, microseconds=1), False),
        ]
        for age, expected in cases:
            with self.subTest(age=age):
                now = checked + age
                self.assertEqual(fresh(offer, now), expected)
                self.assertEqual(eligible(movie, [], [], constraints, now), expected)
                self.assertEqual(public_movie(movie, now, constraints)['availability'],
                                 [offer] if expected else [])
                # Unrestricted catalog remains eligible, but never displays an expired link.
                self.assertTrue(eligible(movie, [], [], {}, now))
                self.assertEqual(public_movie(movie, now)['availability'],
                                 [offer] if expected else [])

    def test_timezone_offsets_share_the_same_expiry_instant(self):
        offer = {'checked_at': '2026-01-01T04:00:00+04:00'}
        self.assertFalse(fresh(offer, datetime(2026, 1, 8, tzinfo=timezone.utc)))


if __name__ == '__main__':
    unittest.main()

import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from nospoilers.core import ReferenceSelector, validate_decision, public_movie, eligible, profile
from nospoilers.store import Store, InvalidData

NOW = datetime(2026, 11, 8, tzinfo=timezone.utc)
CANARY = 'SECRET_CANARY_ENDING_9182'

def movie(i='local:a', value=1, **kw):
    m = {'id': i, 'title': 'Fiction '+i, 'year': 2020, 'runtime': 90,
         'source_ids': {}, 'availability': [],
         'private': {'schema_version': 1, 'features': {'pace': value, 'warmth': value, 'intensity': value, 'character': value, 'wonder': value, 'closure': value},
                     'source_text': CANARY, 'provenance': {'kind': 'fixture', 'version': '1'}}}
    m.update(kw)
    return m

def offer(**kw):
    o = {'region': 'US', 'provider': 'Example', 'access_type': 'included', 'source': 'tmdb',
         'checked_at': NOW.isoformat(), 'url': 'https://www.themoviedb.org/movie/1/watch?locale=US'}
    o.update(kw)
    return o

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'state.db'
        self.store = Store(self.path)
    def tearDown(self):
        self.tmp.cleanup()
    def load(self, movies=None, history=None, mode='real'):
        self.store.ingest({'version': 1, 'mode': mode, 'movies': movies or [movie()], 'history': history or []})
    def test_atomic_import_and_safe_error(self):
        self.load()
        with self.assertRaises(InvalidData) as cm:
            self.load([movie('local:b'), movie('bad', runtime=CANARY)])
        self.assertNotIn(CANARY, str(cm.exception))
        self.assertEqual([m['id'] for m in self.store.movies('real')], ['local:a'])
    def test_ids_versions_and_numeric_validation(self):
        for change in [{'id':'unnamespaced'}, {'year':True}, {'runtime':-1}, {'private':None}, {'private':{'schema_version':2,'features':{}}}]:
            with self.subTest(change=change), self.assertRaises(InvalidData):
                self.load([movie(**change)])
    def test_oversized_feature_number_is_bounded(self):
        m=movie();m['private']['features']['pace']=10**400
        with self.assertRaises(InvalidData): self.load([m])

    def test_history_persists_and_updates_without_duplicates(self):
        self.load()
        self.store.react('real', 'local:a', 'liked', 'note')
        self.store.react('real', 'local:a', 'disliked', '')
        history = Store(self.path).history('real')
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['rating'], 'disliked')
        self.assertFalse(eligible(movie(), history, [], {}, NOW))
    def test_watched_unrated(self):
        self.load()
        self.store.react('real','local:a',None,'')
        self.assertFalse(eligible(movie(), self.store.history('real'), [], {}, NOW))
    def test_hard_constraints(self):
        m = movie()
        self.assertFalse(eligible(m, [], ['local:a'], {}, NOW))
        self.assertFalse(eligible(m, [], [], {'max_runtime':80}, NOW))
        self.assertFalse(eligible(movie(runtime=None), [], [], {'max_runtime':100}, NOW))
        c = {'providers':['Example'], 'region':'US', 'access_types':['included']}
        for offers in [[], [offer(access_type='rent')], [offer(region='GB')],
                       [offer(checked_at=(NOW-timedelta(days=8)).isoformat())],
                       [offer(checked_at=(NOW+timedelta(days=1)).isoformat())]]:
            self.assertFalse(eligible(movie(availability=offers), [], [], c, NOW))
        self.assertTrue(eligible(movie(availability=[offer()]), [], [], c, NOW))
        self.assertTrue(eligible(m, [], [], {}, NOW))
    def test_public_allowlist_and_links(self):
        m = movie(availability=[offer(), offer(url='https://evil.example/'+CANARY)])
        out = public_movie(m, NOW)
        self.assertEqual(set(out), {'id','title','year','runtime','availability'})
        self.assertNotIn(CANARY, json.dumps(out))
        self.assertEqual(len(out['availability']),1)
        self.assertEqual(public_movie(movie(), NOW)['availability'], [])
    def test_watch_link_rejects_blank_and_bare_extra_parameters(self):
        from nospoilers.core import valid_link
        for suffix in ['?evil=','?locale=','?locale=US&evil=','?'+CANARY]:
            self.assertFalse(valid_link(offer(url='https://www.themoviedb.org/movie/1/watch'+suffix)))

    def test_selector_validation(self):
        bad = [{'id':'other:x'}, {'id':'local:a','rationale':CANARY}, {'abstain':'bad'}, CANARY, {}, {'id':'local:a','abstain':'no_acceptable_candidate'}]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_decision(value, {'local:a'})
        self.assertEqual(validate_decision({'abstain':'insufficient_information'},set()), {'abstain':'insufficient_information'})
    def test_personalization_uses_watched_features_and_rating_changes(self):
        seen, a, b = movie('local:seen',1), movie('local:a',1), movie('local:b',0)
        self.load([seen,a,b])
        selector = ReferenceSelector()
        self.store.react('real',seen['id'],'liked','')
        p = profile(self.store.movies('real'),self.store.history('real'))
        self.assertTrue(p['personalized'])
        self.assertEqual(selector.select(p,[a,b],None), {'id':'local:a'})
        self.store.react('real',seen['id'],'disliked','')
        p = profile(self.store.movies('real'),self.store.history('real'))
        self.assertEqual(selector.select(p,[a,b],None), {'id':'local:b'})
        self.assertEqual(len(self.store.history('real')),1)
    def test_zero_usable_ratings_unpersonalized_and_empty_abstains(self):
        m = movie(); m['private']['features'] = {k:None for k in m['private']['features']}
        self.assertFalse(profile([m],[{'id':m['id'],'rating':'liked'}])['personalized'])
        self.assertEqual(ReferenceSelector().select(profile([],[]),[],None), {'abstain':'no_acceptable_candidate'})
    def test_demo_separate_and_session_not_feedback(self):
        self.load(mode='demo')
        self.assertEqual(self.store.history('real'),[])
        self.store.exclude('session-a','demo','local:a')
        self.assertEqual(self.store.exclusions('session-a','demo'),['local:a'])
        self.assertEqual(self.store.exclusions('session-b','demo'),[])
        self.assertEqual(self.store.history('demo'),[])
        self.store.reset_session('session-a','demo')
        self.assertEqual(self.store.exclusions('session-a','demo'),[])

if __name__ == '__main__': unittest.main()

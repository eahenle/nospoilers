"""Pure selection and public serialization. No I/O or narrative interpretation."""
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit, parse_qs

FEATURES = ('pace', 'warmth', 'intensity', 'character', 'wonder', 'closure')
SCHEMA_VERSION = 1
FRESHNESS = timedelta(days=7)
ABSTENTIONS = {'insufficient_information', 'no_acceptable_candidate', 'inference_error'}
MOODS = {'calm': {'pace': 0.2, 'intensity': 0.2}, 'bright': {'warmth': 0.9, 'wonder': 0.8},
         'absorbing': {'character': 0.9, 'intensity': 0.7}}


def utcnow():
    return datetime.now(timezone.utc)


def fresh(offer, now):
    try:
        checked = datetime.fromisoformat(offer['checked_at'].replace('Z', '+00:00'))
        return checked.tzinfo is not None and timedelta(0) <= now - checked <= FRESHNESS
    except (ValueError, TypeError, KeyError):
        return False


def valid_link(offer):
    """Only the configured TMDB movie watch page format is displayable."""
    try:
        import re
        url = urlsplit(offer.get('url') or '')
        query = parse_qs(url.query, keep_blank_values=True, strict_parsing=True)
        return (offer['source'] == 'tmdb' and url.scheme == 'https'
                and url.netloc == 'www.themoviedb.org' and url.username is None
                and re.fullmatch(r'/movie/[1-9][0-9]*/watch', url.path) is not None
                and not url.fragment and set(query) <= {'locale'}
                and all(v == [offer['region']] for v in query.values()))
    except (ValueError, KeyError, TypeError):
        return False


def matching_offers(movie, constraints, now):
    return [o for o in movie.get('availability', []) if fresh(o, now)
            and o['region'] == constraints.get('region', 'US')
            and (not constraints.get('providers') or o['provider'] in constraints['providers'])
            and o['access_type'] in constraints.get('access_types', ['included'])]


def eligible(movie, history, excluded, constraints, now):
    if movie['id'] in excluded or any(h['id'] == movie['id'] and h.get('watched', True) for h in history):
        return False
    limit = constraints.get('max_runtime')
    if limit is not None and (movie.get('runtime') is None or movie['runtime'] > limit):
        return False
    if constraints.get('providers') and not matching_offers(movie, constraints, now):
        return False
    return True


def public_movie(movie, now, constraints=None):
    """The sole movie response serializer. Never copy whole input objects."""
    offers = matching_offers(movie, constraints or {}, now)
    return {'id': movie['id'], 'title': movie['title'], 'year': movie['year'], 'runtime': movie.get('runtime'),
            'availability': [{'provider': o['provider'], 'region': o['region'], 'access_type': o['access_type'],
                              'source': o['source'], 'checked_at': o['checked_at'], 'url': o['url']}
                             for o in offers if valid_link(o)]}


def compatible(movie):
    p = movie.get('private', {})
    return p.get('schema_version') == SCHEMA_VERSION and any(p.get('features', {}).get(k) is not None for k in FEATURES)


def profile(movies, history):
    by_id = {m['id']: m for m in movies}
    examples = []
    for h in history:
        m = by_id.get(h['id'])
        if m and compatible(m) and h.get('rating') in ('liked', 'disliked', 'neutral'):
            examples.append({'features': m['private']['features'], 'weight': {'liked':1, 'disliked':-1, 'neutral':0}[h['rating']]})
    return {'schema_version': SCHEMA_VERSION, 'personalized': bool(examples), 'examples': examples}


class ReferenceSelector:
    """Signed mean closeness to rated profiles; stable ID tie break; no fitted weights."""
    name = 'reference-v1'

    def select(self, preference, candidates, mood):
        if not candidates:
            return {'abstain': 'no_acceptable_candidate'}
        if not preference['personalized'] and not mood:
            return {'id': min(m['id'] for m in candidates)}
        scored = []
        for movie in candidates:
            features = movie.get('private', {}).get('features', {})
            scores = []
            for example in preference['examples']:
                keys = [k for k in FEATURES if features.get(k) is not None and example['features'].get(k) is not None]
                if keys:
                    scores.append(example['weight'] * (1 - sum(abs(features[k]-example['features'][k]) for k in keys)/len(keys)))
            score = sum(scores)/len(scores) if scores else None
            if mood in MOODS:
                keys = [k for k in MOODS[mood] if features.get(k) is not None]
                if keys:
                    mood_score = 1 - sum(abs(features[k]-MOODS[mood][k]) for k in keys)/len(keys)
                    score = mood_score if score is None else .8*score+.2*mood_score
            if score is not None:
                scored.append((-score, movie['id']))
        return {'id': min(scored)[1]} if scored else {'abstain': 'insufficient_information'}


def validate_decision(value, candidates):
    if not isinstance(value, dict):
        raise ValueError('invalid_decision')
    if set(value) == {'id'} and isinstance(value['id'], str) and value['id'] in candidates:
        return value
    if set(value) == {'abstain'} and isinstance(value['abstain'], str) and value['abstain'] in ABSTENTIONS:
        return value
    raise ValueError('invalid_decision')

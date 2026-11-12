"""Opt-in TypeSafe System One adapter for the CommandSelector subprocess."""

import json
import os
import sys
from http.client import HTTPException
from math import fsum, isclose
from statistics import fmean
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .core import ABSTENTIONS, FEATURES, MOODS, SCHEMA_VERSION, validate_decision
from .store import features_valid

URL = 'https://api.typesafe.ai/v1/systemone'
MODEL = 'jev-1.14.0'
TIMEOUT = 10
MAX_RESPONSE_BYTES = 1_000_000
ABSTAIN_OPTIONS = {
    'insufficient_information': 'The supplied features do not give enough evidence to choose.',
    'no_acceptable_candidate': 'There is enough evidence to judge, but none of the candidates fit.',
}
MAX_CANDIDATES = 255 - len(ABSTAIN_OPTIONS)
INSTRUCTIONS = (
    'Choose the movie whose known feature values best fit the viewer. Favor similarity to the liked '
    'averages, disfavor similarity to the disliked averages, and take any mood targets into account. '
    'The features and targets use the same 0 to 1 scale. Ignore null or missing dimensions. '
    'Select an abstention option if the evidence is insufficient or no movie is a reasonable fit.'
)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _feature_vector(values):
    if not isinstance(values, dict):
        raise ValueError
    vector = {name: values.get(name) for name in FEATURES}
    if not features_valid(vector):
        raise ValueError
    return vector


def _preference_summary(preference):
    examples = preference['examples']
    if type(preference['schema_version']) is not int or preference['schema_version'] != SCHEMA_VERSION:
        raise ValueError
    if not isinstance(examples, list):
        raise ValueError
    groups = {1: {name: [] for name in FEATURES}, -1: {name: [] for name in FEATURES}}
    for example in examples:
        weight = example['weight']
        if type(weight) is not int or weight not in (-1, 0, 1):
            raise ValueError
        if weight:
            for name, value in _feature_vector(example['features']).items():
                if value is not None:
                    groups[weight][name].append(value)
    return {
        label: {name: round(fmean(values), 2) for name, values in groups[weight].items() if values}
        for label, weight in (('liked', 1), ('disliked', -1))
    }


def _unique_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError
    return result


def _reject_constant(_value):
    raise ValueError


def _post(payload):
    key = os.environ.get('TYPESAFE_API_KEY', '').strip()
    if not key or any(not 33 <= ord(char) <= 126 for char in key):
        raise ValueError
    request = Request(
        URL,
        data=json.dumps(payload, separators=(',', ':'), allow_nan=False).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'Accept': 'application/json'},
        method='POST',
    )
    with build_opener(_NoRedirect()).open(request, timeout=TIMEOUT) as response:
        if response.status != 200:
            raise ValueError
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError
    return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)


def _probability(value):
    return type(value) in (int, float) and 0 <= value <= 1


def _choice(response, criteria):
    answers = response['answers']
    if not isinstance(answers, dict) or set(answers) != {'pick'}:
        raise ValueError
    answer = answers['pick']
    label = answer['choice']
    probabilities = answer['probabilities']
    if (answer['type'] != 'choice' or not isinstance(label, str) or label not in criteria
            or not _probability(answer['confidence']) or not isinstance(probabilities, dict)
            or probabilities.keys() != criteria.keys()
            or not all(_probability(value) for value in probabilities.values())):
        raise ValueError
    if (not isclose(fsum(probabilities.values()), 1.0, rel_tol=0.0, abs_tol=1e-6)
            or probabilities[label] != max(probabilities.values())):
        raise ValueError
    return label


def _select(payload):
    if type(payload['schema_version']) is not int or payload['schema_version'] != SCHEMA_VERSION:
        raise ValueError
    records = payload['candidates']
    if not isinstance(records, list) or len(records) > MAX_CANDIDATES:
        raise ValueError
    candidates = {}
    for record in records:
        movie_id = record['id']
        if not isinstance(movie_id, str) or not movie_id or movie_id in candidates:
            raise ValueError
        candidates[movie_id] = _feature_vector(record['features'])
    permitted = payload['permitted_outcomes']
    ids, reasons = permitted['id'], permitted['abstain']
    if (not isinstance(ids, list) or len(ids) != len(candidates) or set(ids) != candidates.keys()
            or not isinstance(reasons, list) or len(reasons) != len(ABSTENTIONS) or set(reasons) != ABSTENTIONS):
        raise ValueError
    if not candidates:
        return {'abstain': 'no_acceptable_candidate'}

    preferences = _preference_summary(payload['preference'])
    mood = payload['mood']
    mood_targets = MOODS[mood] if mood is not None else {}
    dimensions = preferences['liked'].keys() | preferences['disliked'].keys() | mood_targets.keys()
    if not dimensions:
        return {'id': min(candidates)}
    comparable = [movie_id for movie_id, vector in candidates.items()
                  if any(vector[name] is not None for name in dimensions)]
    if not comparable:
        return {'abstain': 'insufficient_information'}

    labels = {f'candidate_{index}': movie_id for index, movie_id in enumerate(comparable, 1)}
    criteria = {label: candidates[movie_id] for label, movie_id in labels.items()}
    criteria.update(ABSTAIN_OPTIONS)
    response = _post({
        'model': MODEL,
        'state': {'preferences': preferences, 'mood_targets': mood_targets},
        'questions': {'pick': {'type': 'choice', 'instructions': INSTRUCTIONS, 'criteria': criteria}},
    })
    choice = _choice(response, criteria)
    decision = {'id': labels[choice]} if choice in labels else {'abstain': choice}
    return validate_decision(decision, candidates.keys())


def main():
    try:
        payload = json.load(sys.stdin, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        decision = _select(payload)
    except (HTTPException, OSError, KeyError, TypeError, ValueError, RecursionError):
        decision = {'abstain': 'inference_error'}
    print(json.dumps(decision))


if __name__ == '__main__':
    main()

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.response import addinfourl

from nospoilers.adapters import CommandSelector
from nospoilers.server import Service
from nospoilers.store import Store
from test_core import movie


def selector_request():
    return {
        'schema_version': 1,
        'preference': {
            'schema_version': 1,
            'personalized': True,
            'examples': [
                {'features': {'pace': 0.2, 'warmth': None}, 'weight': 1},
                {'features': {'pace': 0.4, 'warmth': 0.8}, 'weight': 1},
                {'features': {'pace': 0.9}, 'weight': -1},
                {'features': {'closure': 0.7}, 'weight': 0},
            ],
        },
        'mood': 'calm',
        'candidates': [
            {'id': 'tmdb:987654', 'features': {'pace': 0.3, 'intensity': 0.1}},
            {'id': 'local:private-id', 'features': {'pace': 0.8, 'intensity': 0.9}},
        ],
        'criteria': 'Choose one candidate using preferences and mood; abstain if insufficient information.',
        'permitted_outcomes': {
            'id': ['tmdb:987654', 'local:private-id'],
            'abstain': ['insufficient_information', 'no_acceptable_candidate', 'inference_error'],
        },
    }


def provider_response(options, choice):
    return {
        'model': 'jev-1.14.0',
        'answers': {'pick': {
            'type': 'choice',
            'choice': choice,
            'confidence': 1.0,
            'probabilities': {option: float(option == choice) for option in options},
        }},
        'usage': {'input_tokens': 120, 'output_tokens': 12},
    }


def http_response(request, body, status=200, **headers):
    if not isinstance(body, bytes):
        body = json.dumps(body).encode()
    response_headers = Message()
    for key, value in headers.items():
        response_headers[key] = value
    response = addinfourl(io.BytesIO(body), response_headers, request.full_url, status)
    response.msg = 'synthetic provider response'
    return response


def successful_provider(request):
    options = json.loads(request.data)['questions']['pick']['criteria']
    return http_response(request, provider_response(options, 'candidate_1'))


class JevTests(unittest.TestCase):
    def run_bridge(self, payload, https_open=None, key='test-fixture-key'):
        from nospoilers.jev import main

        env = {'TYPESAFE_API_KEY': key} if key is not None else {}
        stdout, stderr = io.StringIO(), io.StringIO()
        with (patch.dict(os.environ, env, clear=True),
              patch('sys.stdin', io.StringIO(json.dumps(payload))),
              patch('urllib.request.HTTPSHandler.https_open', side_effect=https_open) as send,
              redirect_stdout(stdout), redirect_stderr(stderr)):
            main()
        self.assertEqual(stderr.getvalue(), '')
        return json.loads(stdout.getvalue()), send

    def test_module_returns_bounded_failure_without_credentials(self):
        env = {name: value for name, value in os.environ.items() if name != 'TYPESAFE_API_KEY'}
        result = subprocess.run(
            [sys.executable, '-m', 'nospoilers.jev'], input=json.dumps(selector_request()),
            env=env, capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'abstain': 'inference_error'})
        self.assertEqual(result.stderr, '')

    def test_request_uses_choice_and_only_allowlisted_features_and_aggregates(self):
        payload = selector_request()
        payload['criteria'] = 'PRIVATE_CRITERIA_CANARY'
        payload['candidates'][0].update(title='PRIVATE_TITLE_CANARY', source_text='PRIVATE_PLOT_CANARY')
        payload['candidates'][0]['features']['extra'] = 'PRIVATE_FEATURE_CANARY'
        payload['preference']['examples'][0]['notes'] = 'PRIVATE_HISTORY_CANARY'

        def provider(request):
            self.assertEqual(request.full_url, 'https://api.typesafe.ai/v1/systemone')
            self.assertEqual(request.get_method(), 'POST')
            self.assertEqual(request.get_header('Authorization'), 'Bearer test-fixture-key')
            self.assertEqual(request.get_header('Content-type'), 'application/json')
            self.assertEqual(request.timeout, 10)
            body = json.loads(request.data)
            self.assertEqual(set(body), {'model', 'state', 'questions'})
            self.assertEqual(body['model'], 'jev-1.14.0')
            self.assertEqual(body['state'], {
                'preferences': {'liked': {'pace': 0.3, 'warmth': 0.8}, 'disliked': {'pace': 0.9}},
                'mood_targets': {'pace': 0.2, 'intensity': 0.2},
            })
            self.assertEqual(set(body['questions']), {'pick'})
            question = body['questions']['pick']
            self.assertEqual(question['type'], 'choice')
            criteria = question['criteria']
            self.assertEqual(set(criteria), {'candidate_1', 'candidate_2', 'insufficient_information', 'no_acceptable_candidate'})
            self.assertEqual(criteria['candidate_1'], {
                'pace': 0.3, 'warmth': None, 'intensity': 0.1, 'character': None, 'wonder': None, 'closure': None,
            })
            for secret in (b'CANARY', b'tmdb:987654', b'local:private-id', b'test-fixture-key'):
                self.assertNotIn(secret, request.data)
            return http_response(request, provider_response(criteria, 'candidate_2'))

        decision, send = self.run_bridge(payload, provider)
        self.assertEqual(decision, {'id': 'local:private-id'})
        send.assert_called_once()

    def test_provider_abstentions_are_preserved(self):
        for reason in ('insufficient_information', 'no_acceptable_candidate'):
            with self.subTest(reason=reason):
                def provider(request):
                    options = json.loads(request.data)['questions']['pick']['criteria']
                    return http_response(request, provider_response(options, reason))

                decision, send = self.run_bridge(selector_request(), provider)
                self.assertEqual(decision, {'abstain': reason})
                send.assert_called_once()

    def test_empty_cold_start_and_incomparable_profiles_stay_local(self):
        empty, cold_start, incomparable = (selector_request() for _ in range(3))
        empty['candidates'] = []
        empty['permitted_outcomes']['id'] = []
        cold_start['mood'] = None
        cold_start['preference']['examples'] = []
        for candidate in incomparable['candidates']:
            candidate['features'] = {'closure': 0.8}
        for payload, expected in (
            (empty, {'abstain': 'no_acceptable_candidate'}),
            (cold_start, {'id': 'local:private-id'}),
            (incomparable, {'abstain': 'insufficient_information'}),
        ):
            with self.subTest(expected=expected):
                decision, send = self.run_bridge(payload, key=None)
                self.assertEqual(decision, expected)
                send.assert_not_called()

    def test_candidate_without_comparable_data_is_not_an_option(self):
        payload = selector_request()
        payload['candidates'][0]['features'] = {}

        def provider(request):
            criteria = json.loads(request.data)['questions']['pick']['criteria']
            self.assertEqual(set(criteria), {'candidate_1', 'insufficient_information', 'no_acceptable_candidate'})
            self.assertEqual(criteria['candidate_1']['pace'], 0.8)
            return http_response(request, provider_response(criteria, 'candidate_1'))

        decision, send = self.run_bridge(payload, provider)
        self.assertEqual(decision, {'id': 'local:private-id'})
        send.assert_called_once()

    def test_provider_failure_is_bounded_and_never_retried(self):
        for status in (401, 402, 429, 500):
            with self.subTest(status=status):
                decision, send = self.run_bridge(
                    selector_request(), lambda request: http_response(request, b'PRIVATE_ERROR_CANARY', status),
                )
                self.assertEqual(decision, {'abstain': 'inference_error'})
                send.assert_called_once()
        decision, send = self.run_bridge(selector_request(), TimeoutError('PRIVATE_TIMEOUT_CANARY'))
        self.assertEqual(decision, {'abstain': 'inference_error'})
        send.assert_called_once()

    def test_redirect_cannot_forward_credentials(self):
        def provider(request):
            return http_response(request, b'', 302, Location='https://unexpected.invalid/collect')

        decision, send = self.run_bridge(selector_request(), provider)
        self.assertEqual(decision, {'abstain': 'inference_error'})
        send.assert_called_once()

    def test_missing_and_blank_keys_do_not_attempt_transport(self):
        for key in (None, '', ' \t '):
            with self.subTest(key=key):
                decision, send = self.run_bridge(selector_request(), key=key)
                self.assertEqual(decision, {'abstain': 'inference_error'})
                send.assert_not_called()

    def test_malformed_provider_output_and_unoffered_choices_are_rejected(self):
        options = ['candidate_1', 'candidate_2', 'insufficient_information', 'no_acceptable_candidate']
        wrong_type = provider_response(options, 'candidate_1')
        wrong_type['answers']['pick']['type'] = 'noul'
        missing_probability = provider_response(options, 'candidate_1')
        del missing_probability['answers']['pick']['probabilities']['candidate_2']
        invalid_confidence = provider_response(options, 'candidate_1')
        invalid_confidence['answers']['pick']['confidence'] = True
        no_probability_mass = provider_response(options, 'candidate_1')
        no_probability_mass['answers']['pick']['probabilities']['candidate_1'] = 0.0
        inconsistent_choice = provider_response(options, 'no_acceptable_candidate')
        inconsistent_choice['answers']['pick']['choice'] = 'candidate_1'
        non_json_constant = provider_response(options, 'candidate_1')
        non_json_constant['usage']['input_tokens'] = float('nan')
        valid_json = json.dumps(provider_response(options, 'candidate_1')).encode()
        duplicate_choice = valid_json.replace(b'"choice": "candidate_1"',
                                             b'"choice": "candidate_2", "choice": "candidate_1"')
        malformed = {
            'not JSON': b'not JSON PRIVATE_RESPONSE_CANARY',
            'non-JSON constant': non_json_constant,
            'duplicate choice field': duplicate_choice,
            'oversized JSON': valid_json + b' ' * 1_000_000,
            'missing answer': {'answers': {}},
            'wrong answer type': wrong_type,
            'missing probability': missing_probability,
            'invalid confidence': invalid_confidence,
            'no probability mass': no_probability_mass,
            'choice is not a maximum': inconsistent_choice,
            'unoffered label': provider_response(options, 'candidate_3'),
            'raw movie ID': provider_response(options, 'tmdb:987654'),
            'adapter-only abstention': provider_response(options, 'inference_error'),
            'non-string choice': provider_response(options, ['candidate_1']),
        }
        for case, body in malformed.items():
            with self.subTest(case=case):
                decision, send = self.run_bridge(selector_request(), lambda request: http_response(request, body))
                self.assertEqual(decision, {'abstain': 'inference_error'})
                send.assert_called_once()

    def test_candidate_limit_reserves_two_abstention_options(self):
        payload = selector_request()
        payload['candidates'] = [{'id': f'local:{i}', 'features': {'pace': 0.4}} for i in range(253)]
        payload['permitted_outcomes']['id'] = [entry['id'] for entry in payload['candidates']]

        def provider(request):
            options = json.loads(request.data)['questions']['pick']['criteria']
            self.assertEqual(len(options), 255)
            return http_response(request, provider_response(options, 'candidate_253'))

        decision, send = self.run_bridge(payload, provider)
        self.assertEqual(decision, {'id': 'local:252'})
        send.assert_called_once()
        payload['candidates'].append({'id': 'local:253', 'features': {'pace': 0.4}})
        payload['permitted_outcomes']['id'].append('local:253')
        decision, send = self.run_bridge(payload)
        self.assertEqual(decision, {'abstain': 'inference_error'})
        send.assert_not_called()

    def test_mismatched_permitted_ids_do_not_attempt_transport(self):
        payload = selector_request()
        payload['permitted_outcomes']['id'][0] = 'local:ineligible'
        decision, send = self.run_bridge(payload)
        self.assertEqual(decision, {'abstain': 'inference_error'})
        send.assert_not_called()

    def test_service_keeps_eligibility_and_reference_fallback_with_real_subprocess(self):
        child = (
            'from unittest.mock import patch; '
            'from test_jev import successful_provider; '
            'from nospoilers.jev import main; '
            'patch("urllib.request.HTTPSHandler.https_open", side_effect=successful_provider).start(); main()'
        )
        env = {'TYPESAFE_API_KEY': 'test-fixture-key', 'PYTHONPATH': str(Path(__file__).resolve().parent)}
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'test.sqlite3')
            store.ingest({'version': 1, 'mode': 'demo', 'movies': [
                movie('local:a'), movie('local:b'), movie('local:c'),
            ], 'history': [{'id': 'local:a', 'rating': 'liked'}]})
            self.assertEqual(Service(store).diagnostics()['backend'], 'reference-v1')
            selector = CommandSelector([sys.executable, '-c', child], 1)
            with patch.dict(os.environ, env):
                self.assertEqual(Service(store, selector).pick('test', 'demo')['movie']['id'], 'local:b')
            with patch.dict(os.environ, env):
                del os.environ['TYPESAFE_API_KEY']
                self.assertEqual(Service(store, selector).pick('test', 'demo')['code'], 'inference_error')
                fallback = Service(store, selector, fallback=True)
                self.assertEqual(fallback.pick('test', 'demo')['movie']['id'], 'local:b')
                self.assertEqual(fallback.diagnostics()['fallback_count'], 1)

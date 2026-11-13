"""Exercise urllib redirect processing with in-memory HTTP responses only."""
import io
import unittest
from email.message import Message
from unittest.mock import patch
from urllib.response import addinfourl

from nospoilers.adapters import IntegrationError, TMDB


class TMDBTransportTests(unittest.TestCase):
    def response(self, request, status, body=b'{}', location=None):
        headers = Message()
        if location:
            headers['Location'] = location
        response = addinfourl(io.BytesIO(body), headers, request.full_url, status)
        response.msg = 'fixture response'
        return response

    def test_redirects_do_not_send_authenticated_followup(self):
        for status in (301, 302, 303, 307, 308):
            for target in ('https://other.invalid/movie/1',
                           'https://api.themoviedb.org/3/redirected',
                           'http://other.invalid/movie/1'):
                with self.subTest(status=status, target=target):
                    requests = []
                    responses = []

                    def send(request):
                        requests.append(request)
                        if len(requests) == 1:
                            response = self.response(request, status, location=target)
                            responses.append(response)
                            return response
                        return self.response(request, 200)

                    with patch('urllib.request._opener', None), patch(
                            'urllib.request.HTTPSHandler.https_open', side_effect=send), patch(
                            'urllib.request.HTTPHandler.http_open', side_effect=send):
                        with self.assertRaises(IntegrationError) as error:
                            TMDB('offline-fake-token').get('movie/1')
                    self.assertEqual(str(error.exception), 'integration_error')
                    self.assertEqual(len(requests), 1)
                    self.assertTrue(all(response.closed for response in responses))

    def test_normal_response_retains_authorization_and_decodes_json(self):
        requests = []

        def send(request):
            requests.append(request)
            return self.response(request, 200, b'{"id":1}')

        with patch('urllib.request._opener', None), patch(
                'urllib.request.HTTPSHandler.https_open', side_effect=send):
            self.assertEqual(TMDB('offline-fake-token').get('movie/1'), {'id': 1})
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].get_header('Authorization'), 'Bearer offline-fake-token')
        self.assertEqual(requests[0].full_url, 'https://api.themoviedb.org/3/movie/1')

    def test_failure_bodies_are_bounded_and_not_exposed(self):
        for status, body in ((403, b'offline-fake-token'), (200, b'not json'),
                             (200, b'x' * 4000001)):
            with self.subTest(status=status, size=len(body)):
                with patch('urllib.request._opener', None), patch(
                        'urllib.request.HTTPSHandler.https_open',
                        side_effect=lambda request: self.response(request, status, body)):
                    with self.assertRaises(IntegrationError) as error:
                        TMDB('offline-fake-token').get('movie/1')
                self.assertEqual(str(error.exception), 'integration_error')


if __name__ == '__main__':
    unittest.main()

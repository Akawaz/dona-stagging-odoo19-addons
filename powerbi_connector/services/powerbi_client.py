# -*- coding: utf-8 -*-
"""Thin, reusable HTTP client for the Power BI REST API.

Centralizes: authentication headers, retries on 429/5xx, one retry-with-
reauth on 401, timeouts, and turning Power BI's JSON error envelope into a
readable message. No HTTP calls should be made directly from models or from
the sales/expense services -- everything goes through this client so
behavior (retry, logging, error handling) stays consistent.
"""
import logging
import time

from .powerbi_auth import PowerBIAuthError

_logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
BACKOFF_SECONDS = (1, 2, 4)


class PowerBIAPIError(Exception):
    """Raised for any non-recoverable Power BI REST API failure."""

    def __init__(self, message, status_code=None, technical_detail=None):
        self.status_code = status_code
        self.technical_detail = technical_detail
        super().__init__(message)


class PowerBIClient:
    """Talks to ``{api_base_url}/groups/{workspace_id}/...`` for one workspace."""

    def __init__(self, auth, workspace_id, api_base_url='https://api.powerbi.com/v1.0/myorg',
                 timeout=DEFAULT_TIMEOUT, max_retries=MAX_RETRIES):
        if requests is None:
            raise PowerBIAPIError(
                "The Python 'requests' library is not installed in this Odoo "
                "environment. Install it with: pip install requests")
        self.auth = auth
        self.workspace_id = workspace_id
        self.api_base_url = (api_base_url or 'https://api.powerbi.com/v1.0/myorg').rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = requests.Session()

    def workspace_path(self, suffix=''):
        path = 'groups/%s' % self.workspace_id
        if suffix:
            path = '%s/%s' % (path, suffix.lstrip('/'))
        return path

    def get(self, path, params=None):
        return self._request('GET', path, params=params)

    def post(self, path, json_body=None):
        return self._request('POST', path, json_body=json_body)

    def delete(self, path):
        return self._request('DELETE', path)

    # ------------------------------------------------------------------
    def _request(self, method, path, json_body=None, params=None, _reauth_attempted=False):
        url = '%s/%s' % (self.api_base_url, path.lstrip('/'))
        attempt = 0
        while True:
            attempt += 1
            try:
                token = self.auth.get_token()
            except PowerBIAuthError:
                raise

            headers = {
                'Authorization': 'Bearer %s' % token,
                'Content-Type': 'application/json',
            }
            row_count = len(json_body.get('rows', [])) if isinstance(json_body, dict) else None
            _logger.info('Power BI: %s %s%s', method, path,
                         ' (%s rows)' % row_count if row_count is not None else '')
            try:
                response = self._session.request(
                    method, url, headers=headers, json=json_body, params=params,
                    timeout=self.timeout)
            except requests.exceptions.Timeout as exc:
                if attempt <= self.max_retries:
                    self._sleep_backoff(attempt)
                    continue
                raise PowerBIAPIError(
                    'Power BI API timed out after %s attempts (%s %s).'
                    % (attempt, method, path), technical_detail=str(exc))
            except requests.exceptions.RequestException as exc:
                raise PowerBIAPIError(
                    'Could not reach the Power BI API (%s). Check network access.'
                    % self.api_base_url, technical_detail=str(exc))

            if response.status_code in (200, 201, 202, 204):
                if not response.content:
                    return {}
                try:
                    return response.json()
                except ValueError:
                    return {}

            if response.status_code == 401 and not _reauth_attempted:
                _logger.info('Power BI: got 401, invalidating cached token and retrying once')
                self.auth.invalidate()
                return self._request(method, path, json_body=json_body, params=params,
                                      _reauth_attempted=True)

            if response.status_code in RETRYABLE_STATUS_CODES and attempt <= self.max_retries:
                wait = self._retry_after_seconds(response, attempt)
                _logger.warning('Power BI: %s on %s %s, retrying in %ss (attempt %s/%s)',
                                response.status_code, method, path, wait, attempt, self.max_retries)
                time.sleep(wait)
                continue

            raise self._build_api_error(method, path, response)

    def _sleep_backoff(self, attempt):
        idx = min(attempt - 1, len(BACKOFF_SECONDS) - 1)
        time.sleep(BACKOFF_SECONDS[idx])

    def _retry_after_seconds(self, response, attempt):
        retry_after = response.headers.get('Retry-After')
        if retry_after:
            try:
                return int(float(retry_after))
            except ValueError:
                pass
        idx = min(attempt - 1, len(BACKOFF_SECONDS) - 1)
        return BACKOFF_SECONDS[idx]

    @staticmethod
    def _build_api_error(method, path, response):
        try:
            payload = response.json()
            error = payload.get('error', {}) if isinstance(payload, dict) else {}
            detail = error.get('message') or payload
        except ValueError:
            detail = response.text[:500]

        friendly = {
            400: 'Power BI rejected the request as invalid (400). This often means a '
                 'schema mismatch between the rows sent and the dataset table.',
            401: 'Power BI authentication failed (401). The service principal token was '
                 'rejected even after refresh.',
            403: 'Power BI denied access (403). The service principal (or its security '
                 'group) most likely does not have access to this workspace, or the '
                 'tenant admin has not enabled "Allow service principals to use Power BI '
                 'APIs".',
            404: 'The requested Power BI resource was not found (404). Check the '
                 'Workspace ID and Dataset ID.',
            429: 'Power BI is rate-limiting this application (429).',
        }
        message = friendly.get(response.status_code,
                               'Power BI API call failed with status %s.' % response.status_code)
        return PowerBIAPIError('%s (%s %s)' % (message, method, path),
                               status_code=response.status_code,
                               technical_detail=str(detail)[:1000])

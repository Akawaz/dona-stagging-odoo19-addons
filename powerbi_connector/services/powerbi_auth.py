# -*- coding: utf-8 -*-
"""Microsoft Entra ID (Azure AD) service-principal authentication.

Uses the OAuth 2.0 client-credentials grant against the Microsoft identity
platform v2.0 token endpoint to obtain an access token scoped to the Power BI
REST API. This is the Microsoft-recommended flow for unattended,
server-to-server access (no user sign-in, no delegated permissions needed in
the Entra app registration).

Reference: https://learn.microsoft.com/power-bi/developer/embedded/embed-service-principal
"""
import logging
import time

_logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

POWERBI_API_SCOPE = 'https://analysis.windows.net/powerbi/api/.default'
TOKEN_EXPIRY_SAFETY_MARGIN = 60  # seconds; refresh before actual expiry


class PowerBIAuthError(Exception):
    """Raised when Microsoft Entra ID authentication fails.

    ``reason`` holds a short user-facing explanation (never the secret).
    """

    def __init__(self, reason, technical_detail=None):
        self.reason = reason
        self.technical_detail = technical_detail
        super().__init__(reason)


class PowerBIAuth:
    """Acquires and caches Entra ID access tokens for a single connection.

    One instance should be reused across the calls that make up a single
    synchronization run so the token is only fetched once, but instances are
    cheap and hold no long-lived resources, so a fresh instance per run is
    also safe.
    """

    def __init__(self, tenant_id, client_id, client_secret,
                 auth_base_url='https://login.microsoftonline.com', timeout=15):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.auth_base_url = (auth_base_url or 'https://login.microsoftonline.com').rstrip('/')
        self.timeout = timeout
        self._token = None
        self._expires_at = 0

    def _token_url(self):
        return '%s/%s/oauth2/v2.0/token' % (self.auth_base_url, self.tenant_id)

    def invalidate(self):
        """Force the next get_token() call to fetch a fresh token."""
        self._token = None
        self._expires_at = 0

    def get_token(self):
        """Return a valid bearer token, fetching/refreshing it if needed."""
        if self._token and time.time() < self._expires_at - TOKEN_EXPIRY_SAFETY_MARGIN:
            return self._token
        return self._fetch_token()

    def _fetch_token(self):
        if requests is None:
            raise PowerBIAuthError(
                "The Python 'requests' library is not installed in this Odoo "
                "environment. Install it with: pip install requests")

        if not (self.tenant_id and self.client_id and self.client_secret):
            raise PowerBIAuthError(
                'Tenant ID, Client ID and Client Secret must all be configured.')

        data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scope': POWERBI_API_SCOPE,
        }
        _logger.info('Power BI: requesting Entra ID token for tenant %s, client %s',
                      self.tenant_id, self.client_id)
        try:
            response = requests.post(self._token_url(), data=data, timeout=self.timeout)
        except requests.exceptions.RequestException as exc:
            raise PowerBIAuthError(
                'Could not reach Microsoft Entra ID (%s). Check network access and the '
                'Tenant ID.' % self.auth_base_url, technical_detail=str(exc))

        if response.status_code == 200:
            payload = response.json()
            self._token = payload.get('access_token')
            expires_in = int(payload.get('expires_in', 3600))
            self._expires_at = time.time() + expires_in
            _logger.info('Power BI: token acquired, expires in %s seconds', expires_in)
            return self._token

        reason, technical = self._describe_auth_error(response)
        _logger.warning('Power BI: authentication failed for client %s: %s',
                         self.client_id, reason)
        raise PowerBIAuthError(reason, technical_detail=technical)

    @staticmethod
    def _describe_auth_error(response):
        """Turn an Entra ID error response into a readable, safe message."""
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        error_code = payload.get('error', 'unknown_error')
        error_description = payload.get('error_description', response.text[:300])

        hints = {
            'invalid_client': 'The Client Secret is incorrect or has expired.',
            'unauthorized_client': 'The Client ID does not match an app registration in this tenant.',
            'invalid_request': 'The request to Microsoft Entra ID was malformed (check Tenant ID format).',
            'invalid_grant': 'Invalid credentials for the client-credentials grant.',
        }
        if 'AADSTS90002' in error_description or 'tenant' in error_description.lower():
            reason = 'The Tenant ID does not correspond to a real Microsoft Entra tenant.'
        elif 'AADSTS7000215' in error_description or 'AADSTS7000222' in error_description:
            reason = 'The Client Secret is invalid or has expired.'
        elif 'AADSTS700016' in error_description:
            reason = 'The Client ID does not exist in this tenant, or the app was deleted.'
        else:
            reason = hints.get(error_code, 'Microsoft Entra ID rejected the request (%s).' % error_code)
        return reason, error_description

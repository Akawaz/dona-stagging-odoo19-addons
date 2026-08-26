# -*- coding: utf-8 -*-
"""No real Microsoft/Power BI credentials exist in this dev environment, so
these tests mock the `requests` calls made by PowerBIAuth/PowerBIClient and
verify the connection-test diagnostics and error handling around them --
not a live round trip to Microsoft. See README.md for how to verify a real
connection once Entra/Power BI credentials are available.
"""
import json
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = json.dumps(self._json)
        self.headers = {}
        self.content = b'{}' if self._json else b''

    def json(self):
        return self._json


class TestPowerBIConnection(TransactionCase):

    def setUp(self):
        super().setUp()
        self.config = self.env['powerbi.config'].create({
            'name': 'Test Connection',
            'tenant_id': 'tenant-123',
            'client_id': 'client-123',
            'client_secret': 'super-secret',
            'workspace_id': 'workspace-abc',
        })
        self.env.user.group_ids |= self.env.ref('powerbi_connector.group_powerbi_manager')

    def test_connection_fails_on_bad_client_secret(self):
        with patch('odoo.addons.powerbi_connector.services.powerbi_auth.requests') as mock_requests:
            mock_requests.exceptions.RequestException = Exception
            mock_requests.post.return_value = FakeResponse(400, {
                'error': 'invalid_client',
                'error_description': 'AADSTS7000215: Invalid client secret provided.',
            })
            result = self.config.action_test_connection()

        self.assertEqual(result['params']['type'], 'danger')
        self.assertIn('authentication', result['params']['message'].lower())
        self.assertEqual(self.config.connection_state, 'failed')
        self.assertIn('authentication', (self.config.last_test_result or '').lower())

    def test_connection_fails_when_workspace_not_accessible(self):
        with patch('odoo.addons.powerbi_connector.services.powerbi_auth.requests') as mock_auth_requests, \
             patch('odoo.addons.powerbi_connector.services.powerbi_client.requests') as mock_client_requests:
            mock_auth_requests.exceptions.RequestException = Exception
            mock_auth_requests.post.return_value = FakeResponse(200, {
                'access_token': 'fake-token', 'expires_in': 3600,
            })
            mock_client_requests.exceptions.RequestException = Exception
            mock_client_requests.exceptions.Timeout = Exception
            session = mock_client_requests.Session.return_value
            session.request.return_value = FakeResponse(200, {'value': [{'id': 'some-other-workspace'}]})

            result = self.config.action_test_connection()

        self.assertEqual(result['params']['type'], 'danger')
        self.assertIn('Workspace access: FAILED', result['params']['message'])
        self.assertEqual(self.config.connection_state, 'failed')

    def test_connection_success(self):
        with patch('odoo.addons.powerbi_connector.services.powerbi_auth.requests') as mock_auth_requests, \
             patch('odoo.addons.powerbi_connector.services.powerbi_client.requests') as mock_client_requests:
            mock_auth_requests.exceptions.RequestException = Exception
            mock_auth_requests.post.return_value = FakeResponse(200, {
                'access_token': 'fake-token', 'expires_in': 3600,
            })
            mock_client_requests.exceptions.RequestException = Exception
            mock_client_requests.exceptions.Timeout = Exception
            session = mock_client_requests.Session.return_value
            session.request.return_value = FakeResponse(200, {'value': [{'id': 'workspace-abc'}]})

            result = self.config.action_test_connection()

        self.assertEqual(result['tag'], 'display_notification')
        self.assertEqual(self.config.connection_state, 'success')

    def test_only_manager_can_test_connection(self):
        self.env.user.group_ids -= self.env.ref('powerbi_connector.group_powerbi_manager')
        with self.assertRaises(UserError):
            self.config.action_test_connection()

# -*- coding: utf-8 -*-
"""Pure-Python client for the Dahua private RPC2 protocol.

This is the same JSON-RPC protocol used internally by Dahua's **SmartPSS Lite**
and by the device's own web UI. Two transports are supported:

* ``dhip`` - the DHIP binary framing over a raw TCP socket (port **37777**, the
             SmartPSS Lite default "IP" connection port).
* ``http`` - JSON-RPC over HTTP(S) to ``/RPC2`` and ``/RPC2_Login`` (port 80/443).

The JSON payloads (login handshake, RecordFinder queries) are identical across
both transports; only the wire framing differs.

References (reverse-engineered, no official Dahua spec exists):
* DHIP 32-byte header layout - OpenIPC/python-dhip, mcw0/DahuaConsole.
* Two-stage MD5 login digest - Dahua rpcCore.js (getAuthByType).
"""
import hashlib
import json
import logging
import socket
import ssl
import struct

_logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

DHIP_MAGIC = b'DHIP'
DHIP_HEADER_LEN = 0x20
DEFAULT_DHIP_PORT = 37777
DEFAULT_HTTP_PORT = 80


class DahuaRpcError(Exception):
    """Generic protocol / transport error."""


class DahuaLoginError(DahuaRpcError):
    """Raised when authentication fails."""


class DahuaRpcClient(object):
    """Minimal Dahua RPC2 client supporting DHIP (TCP/37777) and HTTP transports."""

    def __init__(self, host, port=DEFAULT_DHIP_PORT, username='admin', password='',
                 mode='dhip', use_ssl=False, timeout=15, debug=False):
        self.host = host
        self.port = int(port)
        self.username = username or 'admin'
        self.password = password or ''
        self.mode = mode  # 'dhip' | 'http'
        self.use_ssl = use_ssl
        self.timeout = timeout
        self.debug = debug

        self._id = 0
        self._session = 0
        self._sock = None
        self._http = None
        self.debug_log = []

    # ------------------------------------------------------------------
    # Debug helper
    # ------------------------------------------------------------------
    def _dbg(self, direction, payload):
        if self.debug:
            text = payload if isinstance(payload, str) else repr(payload)
            # Never leak the cleartext password into logs
            if self.password:
                text = text.replace(self.password, '***')
            entry = '%s: %s' % (direction, text[:2000])
            self.debug_log.append(entry)
            _logger.debug('Dahua RPC %s', entry)

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------
    def connect(self):
        if self.mode == 'dhip':
            self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
            self._sock.settimeout(self.timeout)
            if self.use_ssl:
                ctx = ssl._create_unverified_context()
                self._sock = ctx.wrap_socket(self._sock, server_hostname=self.host)
        else:
            if requests is None:
                raise DahuaRpcError("The 'requests' python library is required for HTTP mode.")
            self._http = requests.Session()
        return self

    def close(self):
        try:
            if self._session and (self._sock or self._http):
                self._request('global.logout', check=False)
        except Exception:  # noqa: BLE001 - closing must never raise
            pass
        if self._sock:
            try:
                self._sock.close()
            except Exception:  # noqa: BLE001
                pass
            self._sock = None
        if self._http:
            try:
                self._http.close()
            except Exception:  # noqa: BLE001
                pass
            self._http = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # ------------------------------------------------------------------
    # Low-level transport
    # ------------------------------------------------------------------
    def _recv_exact(self, n):
        buf = b''
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise DahuaRpcError('Connection closed by device while reading response.')
            buf += chunk
        return buf

    def _send_dhip(self, payload):
        body = payload.encode('utf-8')
        msg_len = len(body)
        header = (
            struct.pack('<I', DHIP_HEADER_LEN) + DHIP_MAGIC +
            struct.pack('<I', self._session & 0xFFFFFFFF) +
            struct.pack('<I', self._id & 0xFFFFFFFF) +
            struct.pack('<I', msg_len) +
            struct.pack('<I', 0) +
            struct.pack('<I', msg_len) +
            struct.pack('<I', 0)
        )
        self._sock.sendall(header + body)
        resp_header = self._recv_exact(32)
        if resp_header[4:8] != DHIP_MAGIC:
            raise DahuaRpcError(
                'Unexpected response framing (not DHIP). The device may not speak '
                'DHIP on this port - try connection mode "HTTP RPC" or verify port 37777.')
        r_msg_len = struct.unpack('<I', resp_header[24:28])[0]
        r_data_len = struct.unpack('<I', resp_header[28:32])[0]
        data = self._recv_exact(r_msg_len + r_data_len)
        return data[:r_msg_len].decode('utf-8', 'replace')

    def _send_http(self, payload, login=False):
        scheme = 'https' if self.use_ssl else 'http'
        path = '/RPC2_Login' if login else '/RPC2'
        url = '%s://%s:%s%s' % (scheme, self.host, self.port, path)
        resp = self._http.post(url, data=payload, timeout=self.timeout, verify=False)
        return resp.text

    # ------------------------------------------------------------------
    # RPC
    # ------------------------------------------------------------------
    def _request(self, method, params=None, object_id=None, extra=None,
                 login=False, check=True):
        self._id += 1
        data = {'method': method, 'id': self._id}
        if params is not None:
            data['params'] = params
        if object_id is not None:
            data['object'] = object_id
        if self._session:
            data['session'] = self._session
        if extra:
            data.update(extra)
        payload = json.dumps(data)
        self._dbg('SEND', payload)

        if self.mode == 'dhip':
            raw = self._send_dhip(payload)
        else:
            raw = self._send_http(payload, login=login)
        self._dbg('RECV', raw)

        try:
            result = json.loads(raw)
        except ValueError:
            raise DahuaRpcError('Non-JSON response from device: %r' % raw[:200])

        session = result.get('session')
        if session:
            self._session = session if self.mode == 'http' else self._as_int(session)
        if check and not result.get('result') and 'params' not in result:
            raise DahuaRpcError('RPC "%s" failed: %s' % (method, raw[:300]))
        return result

    @staticmethod
    def _as_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return value

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def login(self):
        """Perform the two-stage Dahua digest login. Raises DahuaLoginError."""
        first = self._request('global.login', params={
            'userName': self.username,
            'password': '',
            'clientType': 'Web3.0',
            'loginType': 'Direct',
        }, login=True, check=False)

        session = first.get('session')
        if session:
            self._session = session if self.mode == 'http' else self._as_int(session)

        p = first.get('params', {}) or {}
        realm = p.get('realm')
        random = p.get('random')
        if not realm or not random:
            if first.get('result'):
                return True  # device accepted login with no challenge
            raise DahuaLoginError(
                'Login handshake failed (device did not return realm/random). '
                'Response: %s' % json.dumps(first)[:300])

        pwd = hashlib.md5(
            ('%s:%s:%s' % (self.username, realm, self.password)).encode('utf-8')
        ).hexdigest().upper()
        resp = hashlib.md5(
            ('%s:%s:%s' % (self.username, random, pwd)).encode('utf-8')
        ).hexdigest().upper()

        second = self._request('global.login', params={
            'userName': self.username,
            'password': resp,
            'clientType': 'Web3.0',
            'loginType': 'Direct',
            'authorityType': 'Default',
            'passwordType': 'Default',
            'realm': realm,
            'random': random,
        }, login=True, check=False)

        if not second.get('result'):
            raise DahuaLoginError(
                'Authentication failed - check username/password (and that the '
                'account is not locked). Response: %s' % json.dumps(second)[:300])
        return True

    def keep_alive(self):
        return self._request('global.keepAlive',
                             params={'timeout': 300, 'active': True}, check=False)

    def get_serial_number(self):
        r = self._request('magicBox.getSerialNo', check=False)
        params = r.get('params', {}) or {}
        return params.get('sn') or params.get('SerialNo') or params.get('SN')

    def get_device_type(self):
        r = self._request('magicBox.getDeviceType', check=False)
        return (r.get('params', {}) or {}).get('type')

    def get_software_version(self):
        r = self._request('magicBox.getSoftwareVersion', check=False)
        return (r.get('params', {}) or {}).get('version')

    def find_access_records(self, start_epoch, end_epoch, page_size=100,
                            max_records=100000, record_name='AccessControlCardRec',
                            filter_start=True):
        """Query attendance/access records up to ``end_epoch``.

        Returns a list of raw record dicts. Tries several ``startFind`` condition
        formats (firmware-dependent). Many ASI firmwares ignore the time condition
        and return the full record set ordered by ``RecNo``; callers rely on
        ``RecNo`` de-duplication downstream. When ``filter_start`` is False the
        lower time bound is not enforced client-side, so the entire device history
        is returned (used for a full/initial import).
        """
        finder = self._request('RecordFinder.factory.create',
                               params={'name': record_name}, check=False)
        object_id = finder.get('result')
        if not object_id or object_id is True:
            raise DahuaRpcError(
                'Device did not return a RecordFinder object for %s. '
                'This firmware may not expose attendance records via RPC. '
                'Response: %s' % (record_name, json.dumps(finder)[:300]))

        candidate_conditions = [
            {'condition': {'Time': [start_epoch, end_epoch]}},
            {'condition': {'StartTime': start_epoch, 'EndTime': end_epoch}},
            {'StartTime': start_epoch, 'EndTime': end_epoch},
            None,  # no condition -> fetch everything, filter client-side
        ]
        started = False
        for cond in candidate_conditions:
            r = self._request('RecordFinder.startFind', object_id=object_id,
                              params=cond, check=False)
            if r.get('result'):
                started = True
                break

        records = []
        try:
            if started:
                while len(records) < max_records:
                    r = self._request('RecordFinder.doFind', object_id=object_id,
                                      params={'count': page_size}, check=False)
                    params = r.get('params', {}) or {}
                    # Firmware variants use 'records' (ASI series) or 'info'.
                    batch = params.get('records')
                    if batch is None:
                        batch = params.get('info') or []
                    if not batch:
                        break
                    records.extend(batch)
                    if len(batch) < page_size:
                        break
        finally:
            self._request('RecordFinder.stopFind', object_id=object_id, check=False)
            # Different firmwares expose destroy on the service or the factory.
            d = self._request('RecordFinder.destroy', object_id=object_id, check=False)
            if not d.get('result'):
                self._request('RecordFinder.factory.destroy', object_id=object_id, check=False)

        filtered = []
        for rec in records:
            ct = rec.get('CreateTime') or rec.get('Time') or 0
            ct = self._as_int(ct) or 0
            if ct == 0:
                filtered.append(rec)
                continue
            if ct > end_epoch:
                continue
            if filter_start and ct < start_epoch:
                continue
            filtered.append(rec)
        return filtered

    # ------------------------------------------------------------------
    # User enrollment (Odoo -> device push)
    # ------------------------------------------------------------------
    def get_access_user(self, user_id):
        """Return the device user record for ``user_id`` or None if absent."""
        r = self._request('AccessUser.getUserInfo',
                          params={'UserID': str(user_id)}, check=False)
        if r.get('result'):
            info = (r.get('params', {}) or {}).get('UserInfo')
            return info or (r.get('params', {}) or {})
        return None

    def push_access_user(self, user_id, user_name, card_no=None, password=None,
                         user_type=0, authority=2,
                         valid_from='2020-01-01 00:00:00',
                         valid_to='2037-12-31 23:59:59',
                         doors=None, time_sections=None):
        """Create or update a user on the device (SmartPSS-style enrollment).

        Pushes the user identity (ID + name, optional card/PIN, validity window
        and door/time permissions). Biometric templates (fingerprint/face) must
        still be captured at the terminal or via a dedicated enrollment call;
        this pushes the user record so the device recognises the person.

        Returns a dict describing the outcome. Raises DahuaRpcError on hard
        transport failures.
        """
        doors = doors if doors is not None else [0]
        time_sections = time_sections if time_sections is not None else [255]

        user = {
            'UserID': str(user_id),
            'UserName': user_name or ('User %s' % user_id),
            'UserType': user_type,
            'Authority': authority,
            'ValidFrom': valid_from,
            'ValidTo': valid_to,
            'Doors': doors,
            'TimeSections': time_sections,
        }
        if password:
            user['Password'] = str(password)

        existed = bool(self.get_access_user(user_id))
        action = 'updated' if existed else 'created'

        # Primary path: AccessUser service (modern ASI firmware).
        method = 'AccessUser.updateMulti' if existed else 'AccessUser.insertMulti'
        r = self._request(method, params={'UserList': [user]}, check=False)

        if not r.get('result'):
            # Fallbacks: try the opposite op, then the legacy RecordUpdater service.
            alt = 'AccessUser.insertMulti' if existed else 'AccessUser.updateMulti'
            r = self._request(alt, params={'UserList': [user]}, check=False)
        if not r.get('result'):
            r = self._push_user_via_record_updater(user)

        if not r.get('result'):
            raise DahuaRpcError(
                'Device rejected user push for UserID %s. Response: %s'
                % (user_id, json.dumps(r)[:300]))

        card_result = None
        if card_no:
            card_result = self.push_card(user_id, card_no, doors=doors,
                                         time_sections=time_sections,
                                         valid_from=valid_from, valid_to=valid_to)
        return {'user_id': str(user_id), 'action': action, 'card': card_result}

    def _push_user_via_record_updater(self, user):
        """Legacy fallback using the RecordUpdater service."""
        finder = self._request('RecordUpdater.factory.instance',
                               params={'name': 'AccessControlCard'}, check=False)
        object_id = finder.get('result')
        if not object_id or object_id is True:
            return {'result': False}
        try:
            return self._request('RecordUpdater.insert', object_id=object_id,
                                 params={'Info': user}, check=False)
        finally:
            self._request('RecordUpdater.destroy', object_id=object_id, check=False)

    def push_card(self, user_id, card_no, card_type=0,
                  valid_from='2020-01-01 00:00:00', valid_to='2037-12-31 23:59:59',
                  doors=None, time_sections=None):
        """Attach an access card number to a device user (best-effort)."""
        doors = doors if doors is not None else [0]
        time_sections = time_sections if time_sections is not None else [255]
        card = {
            'UserID': str(user_id),
            'CardNo': str(card_no),
            'CardType': card_type,
            'CardStatus': 0,
            'ValidFrom': valid_from,
            'ValidTo': valid_to,
            'Doors': doors,
            'TimeSections': time_sections,
        }
        r = self._request('AccessCard.insertMulti', params={'CardList': [card]}, check=False)
        return bool(r.get('result'))

    def remove_access_user(self, user_id):
        """Delete a user from the device."""
        r = self._request('AccessUser.removeMulti',
                          params={'UserID': [str(user_id)]}, check=False)
        if not r.get('result'):
            r = self._request('AccessUser.remove',
                              params={'UserID': str(user_id)}, check=False)
        return bool(r.get('result'))

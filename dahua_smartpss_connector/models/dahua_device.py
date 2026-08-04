# -*- coding: utf-8 -*-
import logging
import time
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError

from .dahua_rpc_client import (
    DahuaRpcClient,
    DahuaRpcError,
    DEFAULT_DHIP_PORT,
    DEFAULT_HTTP_PORT,
)

_logger = logging.getLogger(__name__)


class DahuaDevice(models.Model):
    _name = 'dahua.device'
    _description = 'Dahua Attendance Device (SmartPSS-style connector)'
    _order = 'name'

    name = fields.Char(string='Device Name', required=True,
                       help='A label, e.g. "Main Gate - ASI2212H-DW".')
    active = fields.Boolean(default=True)

    ip_address = fields.Char(string='IP Address', required=True,
                             help='The device static IP (or reachable host/DDNS), e.g. 192.168.1.108')
    connection_mode = fields.Selection([
        ('dhip', 'Private Protocol / DHIP (TCP 37777 - SmartPSS default)'),
        ('http', 'HTTP RPC (/RPC2 on port 80/443)'),
    ], string='Connection Mode', default='dhip', required=True)
    port = fields.Integer(string='Port', default=DEFAULT_DHIP_PORT, required=True)
    use_ssl = fields.Boolean(string='Use SSL/TLS', default=False)
    username = fields.Char(string='Username', default='admin', required=True)
    password = fields.Char(string='Password', required=True)

    serial_number = fields.Char(
        string='Serial Number (SN)',
        help='The device serial number, as shown in SmartPSS Lite / device menu. '
             'Used to verify you are connected to the correct device.')
    verify_serial = fields.Boolean(
        string='Verify Serial on Connect', default=False,
        help='If enabled, Test Connection / Sync will fail if the serial number '
             'read from the device does not match the value above.')
    device_type = fields.Char(string='Device Model', readonly=True, copy=False)
    software_version = fields.Char(string='Firmware Version', readonly=True, copy=False)

    auto_sync = fields.Boolean(string='Include in Scheduled Sync', default=True)
    debug_mode = fields.Boolean(
        string='Debug Mode',
        help='Capture the raw protocol exchange into the sync log for troubleshooting. '
             '(Passwords are masked.)')

    state = fields.Selection([
        ('draft', 'Not Tested'),
        ('connected', 'Connected'),
        ('error', 'Connection Error'),
    ], string='Status', default='draft', readonly=True, copy=False)
    last_error = fields.Text(string='Last Error', readonly=True, copy=False)

    last_sync_epoch = fields.Integer(
        string='Last Synced Epoch (UTC)', default=0, readonly=True, copy=False,
        help='Internal watermark: records with CreateTime <= this value have '
             'already been synced.')
    last_sync_time = fields.Datetime(string='Last Sync (Odoo time)', readonly=True, copy=False)

    unmapped_employee_action = fields.Selection([
        ('skip', 'Skip and log'),
        ('create', 'Auto-create a draft employee'),
    ], string='If Device User Is Unmapped', default='skip')

    record_ids = fields.One2many('dahua.attendance.record', 'device_id', string='Fetched Records')
    record_count = fields.Integer(compute='_compute_counts')
    sync_log_ids = fields.One2many('dahua.sync.log', 'device_id', string='Sync Logs')
    sync_log_count = fields.Integer(compute='_compute_counts')

    @api.depends('record_ids', 'sync_log_ids')
    def _compute_counts(self):
        for rec in self:
            rec.record_count = len(rec.record_ids)
            rec.sync_log_count = len(rec.sync_log_ids)

    @api.onchange('connection_mode')
    def _onchange_connection_mode(self):
        for rec in self:
            if rec.connection_mode == 'dhip':
                rec.port = 443 if rec.use_ssl else DEFAULT_DHIP_PORT
            else:
                rec.port = 443 if rec.use_ssl else DEFAULT_HTTP_PORT

    # ------------------------------------------------------------------
    # Client factory
    # ------------------------------------------------------------------
    def _get_client(self):
        self.ensure_one()
        return DahuaRpcClient(
            host=self.ip_address,
            port=self.port,
            username=self.username,
            password=self.password,
            mode=self.connection_mode,
            use_ssl=self.use_ssl,
            debug=self.debug_mode,
        )

    def _verify_serial(self, client):
        """Read the serial from the device; optionally enforce a match."""
        self.ensure_one()
        sn = client.get_serial_number()
        if self.verify_serial and self.serial_number and sn and \
                sn.strip().lower() != self.serial_number.strip().lower():
            raise UserError(
                'Serial number mismatch: device reports "%s" but this record '
                'is configured for "%s".' % (sn, self.serial_number))
        return sn

    # ------------------------------------------------------------------
    # Test connection
    # ------------------------------------------------------------------
    def action_test_connection(self):
        for device in self:
            client = device._get_client()
            try:
                client.connect()
                client.login()
                sn = device._verify_serial(client)
                dev_type = client.get_device_type()
                version = client.get_software_version()
                vals = {'state': 'connected', 'last_error': False}
                if sn and not device.serial_number:
                    vals['serial_number'] = sn
                if dev_type:
                    vals['device_type'] = dev_type
                if version:
                    vals['software_version'] = version
                device.write(vals)
            except Exception as e:  # noqa: BLE001
                _logger.exception('Dahua connection test failed for %s', device.name)
                device.write({'state': 'error', 'last_error': str(e)})
                if len(self) == 1:
                    raise UserError('Connection failed:\n\n%s' % e)
            finally:
                client.close()
        return True

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------
    def action_sync_now(self):
        for device in self:
            device._sync_one()
        return True

    def action_fetch_all(self):
        """Import the device's entire attendance history (ignores the watermark)."""
        for device in self:
            device._sync_one(full=True)
        return True

    def action_open_sync_wizard(self):
        """Open the sync wizard so the user picks full / from-date / new-only."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sync Attendance',
            'res_model': 'dahua.sync.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_device_id': self.id},
        }

    def _sync_one(self, full=False, start_epoch=None):
        """Pull punches from the device.

        * ``full=True``           -> entire device history (ignores watermark).
        * ``start_epoch`` given   -> only punches on/after that epoch (UTC).
        * neither                 -> incremental, from the stored watermark.
        """
        self.ensure_one()
        Log = self.env['dahua.sync.log']
        start_time = fields.Datetime.now()
        end_epoch = int(time.time())
        if start_epoch is None:
            # No watermark yet (or an explicit full resync) -> whole history.
            full = full or not self.last_sync_epoch
            start_epoch = self.last_sync_epoch

        client = self._get_client()
        try:
            client.connect()
            client.login()
            self._verify_serial(client)
            records = client.find_access_records(start_epoch, end_epoch,
                                                 filter_start=not full)
            stored, created, skipped, max_epoch = self._process_records(records)

            self.write({
                'last_sync_epoch': max_epoch,
                'last_sync_time': fields.Datetime.now(),
                'state': 'connected',
                'last_error': False,
            })
            Log.create({
                'device_id': self.id,
                'start_time': start_time,
                'end_time': fields.Datetime.now(),
                'status': 'success' if skipped == 0 else 'partial',
                'records_fetched': len(records),
                'records_created': created,
                'records_skipped': skipped,
                'message': 'Fetched %s record(s); stored %s new; created/updated %s '
                           'attendance entr(y/ies); skipped %s (unmapped/duplicate).'
                           % (len(records), stored, created, skipped),
                'debug_log': '\n'.join(client.debug_log) if self.debug_mode else False,
            })
        except Exception as e:  # noqa: BLE001
            _logger.exception('Dahua sync failed for device %s', self.name)
            self.write({'state': 'error', 'last_error': str(e)})
            Log.create({
                'device_id': self.id,
                'start_time': start_time,
                'end_time': fields.Datetime.now(),
                'status': 'error',
                'message': str(e),
                'debug_log': '\n'.join(client.debug_log) if self.debug_mode else False,
            })
            if self.env.context.get('dahua_raise'):
                raise
        finally:
            client.close()

    @staticmethod
    def _is_successful(rec):
        """Only genuine (granted) punches are attendance events.

        Failed recognitions / denied access come back with Status 0 and an
        ErrorCode (e.g. 16) and usually no UserID - those are ignored.
        """
        if str(rec.get('Status', '1')) not in ('1', 'True', 'true'):
            return False
        if rec.get('ErrorCode'):
            return False
        user_id = rec.get('UserID') or rec.get('UserId') or rec.get('CardNo')
        return bool(str(user_id or '').strip())

    def _process_records(self, records):
        """Store successful punches and turn them into hr.attendance entries."""
        self.ensure_one()
        Record = self.env['dahua.attendance.record']
        Employee = self.env['hr.employee']
        Attendance = self.env['hr.attendance']

        def _epoch(rec):
            val = rec.get('CreateTime') or rec.get('Time') or 0
            try:
                return int(val)
            except (TypeError, ValueError):
                return 0

        records = sorted(records, key=_epoch)
        stored = created = skipped = 0
        max_epoch = self.last_sync_epoch

        for rec in records:
            epoch = _epoch(rec)
            if epoch > max_epoch:
                max_epoch = epoch

            # Skip failed/denied transactions entirely - do not store them.
            if not self._is_successful(rec):
                continue

            device_user_id = str(
                rec.get('UserID') or rec.get('UserId') or rec.get('CardNo') or ''
            ).strip()
            recno = str(rec.get('RecNo') or rec.get('RecordNo') or '')
            punch_dt = datetime.utcfromtimestamp(epoch) if epoch else fields.Datetime.now()

            # de-duplicate by (device, recno) or (device, user, time)
            domain = [('device_id', '=', self.id)]
            if recno:
                domain.append(('rec_no', '=', recno))
            else:
                domain += [('device_user_id', '=', device_user_id),
                           ('punch_time', '=', fields.Datetime.to_string(punch_dt))]
            if Record.search_count(domain):
                continue

            employee = Employee.search(
                [('dahua_person_id', '=', device_user_id)], limit=1)
            if not employee and self.unmapped_employee_action == 'create':
                employee = Employee.create({
                    'name': rec.get('CardName') or ('Dahua User %s' % device_user_id),
                    'dahua_person_id': device_user_id,
                })

            raw_rec = Record.create({
                'device_id': self.id,
                'rec_no': recno,
                'device_user_id': device_user_id,
                'card_name': rec.get('CardName'),
                'punch_time': punch_dt,
                'employee_id': employee.id if employee else False,
            })
            stored += 1

            if not employee:
                skipped += 1
                continue

            attendance = self._apply_attendance(employee, punch_dt, Attendance)
            if attendance:
                raw_rec.attendance_id = attendance.id
                created += 1

        return stored, created, skipped, max_epoch

    def _apply_attendance(self, employee, punch_dt, Attendance):
        """Toggle the employee's attendance for a punch. Returns the record or False.

        This single-reader terminal reports no reliable in/out flag, so punches
        simply alternate: an open session is checked out, otherwise a new one is
        opened.
        """
        open_att = Attendance.search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False),
        ], limit=1, order='check_in desc')

        if open_att:
            if punch_dt > open_att.check_in:
                open_att.check_out = punch_dt
                return open_att
            return False
        return Attendance.create({
            'employee_id': employee.id,
            'check_in': punch_dt,
        })

    @api.model
    def _cron_sync_all_devices(self):
        devices = self.search([('active', '=', True), ('auto_sync', '=', True)])
        for device in devices:
            device._sync_one()

    # ------------------------------------------------------------------
    # Push / enrollment (Odoo -> device)
    # ------------------------------------------------------------------
    def push_employees(self, employees):
        """Push the given employees (must have dahua_person_id) to this device.

        Opens one authenticated session and enrolls each employee's user record
        (ID, name, optional card). Returns a summary dict.
        """
        self.ensure_one()
        results = {'ok': [], 'failed': []}
        client = self._get_client()
        try:
            client.connect()
            client.login()
            self._verify_serial(client)
            for emp in employees:
                if not emp.dahua_person_id:
                    results['failed'].append((emp.name, 'No Dahua Device User ID set'))
                    continue
                try:
                    outcome = client.push_access_user(
                        user_id=emp.dahua_person_id,
                        user_name=emp.name,
                        card_no=emp.dahua_card_no or None,
                    )
                    emp.write({
                        'dahua_enrolled': True,
                        'dahua_last_pushed_device_id': self.id,
                    })
                    results['ok'].append((emp.name, outcome.get('action')))
                except Exception as e:  # noqa: BLE001
                    _logger.exception('Failed to push employee %s to %s', emp.name, self.name)
                    results['failed'].append((emp.name, str(e)))
            self.write({'state': 'connected', 'last_error': False})
        except Exception as e:  # noqa: BLE001
            _logger.exception('Dahua push session failed for device %s', self.name)
            self.write({'state': 'error', 'last_error': str(e)})
            raise UserError('Could not connect to the device to push users:\n\n%s' % e)
        finally:
            if self.debug_mode and client.debug_log:
                self.env['dahua.sync.log'].create({
                    'device_id': self.id,
                    'start_time': fields.Datetime.now(),
                    'end_time': fields.Datetime.now(),
                    'status': 'success' if not results['failed'] else 'partial',
                    'message': 'Push: %s ok, %s failed.'
                               % (len(results['ok']), len(results['failed'])),
                    'debug_log': '\n'.join(client.debug_log),
                })
            client.close()
        return results

    def action_enroll_employees(self):
        """Open the enrollment wizard for this device."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Enroll Employees on Device',
            'res_model': 'dahua.enroll.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_device_id': self.id},
        }

    # ------------------------------------------------------------------
    # Smart button actions
    # ------------------------------------------------------------------
    def action_view_records(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Fetched Records',
            'res_model': 'dahua.attendance.record',
            'view_mode': 'list,form',
            'domain': [('device_id', '=', self.id)],
            'context': {'default_device_id': self.id},
        }

    def action_view_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sync Logs',
            'res_model': 'dahua.sync.log',
            'view_mode': 'list,form',
            'domain': [('device_id', '=', self.id)],
            'context': {'default_device_id': self.id},
        }

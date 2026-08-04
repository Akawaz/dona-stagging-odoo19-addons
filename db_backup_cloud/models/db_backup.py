# -*- coding: utf-8 -*-
import logging
import os
import json
import tempfile
from datetime import datetime

import odoo
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PARAM = 'db_backup_cloud.%s'


def _truthy(value):
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


class DbBackup(models.Model):
    _name = 'db.backup'
    _description = 'Database Backup'
    _order = 'backup_date desc, id desc'

    name = fields.Char(string="File Name", readonly=True)
    backup_date = fields.Datetime(string="Date", readonly=True, default=fields.Datetime.now)
    db_name = fields.Char(string="Database", readonly=True)
    file_size = fields.Float(string="Size (MB)", readonly=True, digits=(12, 2))
    state = fields.Selection([
        ('success', 'Success'),
        ('partial', 'Partial (some destinations failed)'),
        ('failed', 'Failed'),
    ], string="Status", readonly=True, default='success')
    scheduled = fields.Boolean(string="Scheduled", readonly=True)
    destination = fields.Text(string="Destinations", readonly=True)
    error_message = fields.Text(string="Errors", readonly=True)

    # ──────────────────────────────────────────────────────────────────
    #  Config helpers
    # ──────────────────────────────────────────────────────────────────
    def _get_param(self, key, default=None):
        return self.env['ir.config_parameter'].sudo().get_param(PARAM % key, default)

    # ──────────────────────────────────────────────────────────────────
    #  Entry points
    # ──────────────────────────────────────────────────────────────────
    @api.model
    def action_backup_now(self):
        """Manual backup (from the Backup History list header / Settings button)."""
        rec = self._run_backup(scheduled=False)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Backup',
                'message': 'Backup %s: %s' % (rec.name, dict(self._fields['state'].selection).get(rec.state)),
                'type': 'success' if rec.state == 'success' else ('warning' if rec.state == 'partial' else 'danger'),
                'sticky': rec.state != 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    @api.model
    def _cron_run_backup(self):
        """Called by ir.cron; only runs when scheduled backups are enabled."""
        if not _truthy(self._get_param('schedule_enabled', 'False')):
            _logger.info("db_backup_cloud: scheduled backup disabled, skipping.")
            return
        self._run_backup(scheduled=True)

    # ──────────────────────────────────────────────────────────────────
    #  Core
    # ──────────────────────────────────────────────────────────────────
    @api.model
    def _run_backup(self, scheduled=False):
        db_name = self.env.cr.dbname
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = '%s_%s.zip' % (db_name, ts)

        local_path = self._get_param('local_path') or os.path.join(tempfile.gettempdir(), 'odoo_backups')
        try:
            os.makedirs(local_path, exist_ok=True)
        except Exception as e:
            raise UserError("Cannot create the local backup folder '%s': %s" % (local_path, e))

        file_path = os.path.join(local_path, filename)

        # 1) Dump DB + filestore to the local file
        try:
            with open(file_path, 'wb') as stream:
                odoo.service.db.dump_db(db_name, stream, backup_format='zip')
        except Exception as e:
            _logger.exception("db_backup_cloud: dump failed")
            return self.create({
                'name': filename, 'db_name': db_name, 'scheduled': scheduled,
                'state': 'failed', 'error_message': "Dump failed: %s" % e,
            })

        size_mb = round(os.path.getsize(file_path) / (1024.0 * 1024.0), 2)
        destinations, errors = [], []

        # 2) Local
        local_enabled = _truthy(self._get_param('local_enabled', 'True'))
        if local_enabled:
            destinations.append("Local: %s" % file_path)

        # 3) Cloud destinations (each isolated so one failure doesn't block others)
        for key, label, handler in (
            ('s3_enabled', 'AWS S3', self._upload_s3),
            ('gdrive_enabled', 'Google Drive', self._upload_gdrive),
            ('onedrive_enabled', 'OneDrive', self._upload_onedrive),
        ):
            if not _truthy(self._get_param(key, 'False')):
                continue
            try:
                ref = handler(file_path, filename)
                destinations.append("%s: %s" % (label, ref))
            except Exception as e:
                _logger.exception("db_backup_cloud: %s upload failed", label)
                errors.append("%s: %s" % (label, e))

        # 4) Retention + (optionally) drop the local copy
        try:
            self._apply_local_retention(local_path, db_name)
        except Exception as e:
            _logger.warning("db_backup_cloud: retention cleanup failed: %s", e)
        if not local_enabled:
            try:
                os.remove(file_path)
            except OSError:
                pass

        state = 'success'
        if errors and destinations:
            state = 'partial'
        elif errors and not destinations:
            state = 'failed'

        return self.create({
            'name': filename,
            'db_name': db_name,
            'file_size': size_mb,
            'scheduled': scheduled,
            'state': state,
            'destination': "\n".join(destinations) or False,
            'error_message': "\n".join(errors) or False,
        })

    def _apply_local_retention(self, local_path, db_name):
        """Keep only the most recent N local *.zip backups for this database."""
        try:
            keep = int(self._get_param('local_keep', '7') or 0)
        except (TypeError, ValueError):
            keep = 7
        if keep <= 0:
            return
        prefix = '%s_' % db_name
        files = sorted(
            (f for f in os.listdir(local_path)
             if f.startswith(prefix) and f.endswith('.zip')),
            reverse=True,
        )
        for stale in files[keep:]:
            try:
                os.remove(os.path.join(local_path, stale))
            except OSError:
                pass

    # ──────────────────────────────────────────────────────────────────
    #  Providers
    # ──────────────────────────────────────────────────────────────────
    def _upload_s3(self, file_path, filename):
        try:
            import boto3
        except ImportError:
            raise UserError("The 'boto3' package is required for AWS S3 backups. Install it: pip install boto3")
        access = self._get_param('s3_access_key')
        secret = self._get_param('s3_secret_key')
        bucket = self._get_param('s3_bucket')
        region = self._get_param('s3_region') or None
        endpoint = self._get_param('s3_endpoint') or None  # for S3-compatible stores
        prefix = (self._get_param('s3_prefix') or '').strip('/')
        if not (access and secret and bucket):
            raise UserError("AWS S3 is enabled but access key / secret / bucket are not all configured.")
        key = '%s/%s' % (prefix, filename) if prefix else filename
        client = boto3.client(
            's3', aws_access_key_id=access, aws_secret_access_key=secret,
            region_name=region, endpoint_url=endpoint,
        )
        client.upload_file(file_path, bucket, key)
        return 's3://%s/%s' % (bucket, key)

    def _upload_gdrive(self, file_path, filename):
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
        except ImportError:
            raise UserError("The 'google-api-python-client' and 'google-auth' packages are required for "
                            "Google Drive backups. Install: pip install google-api-python-client google-auth")
        sa_json = self._get_param('gdrive_service_account_json')
        folder_id = self._get_param('gdrive_folder_id')
        if not sa_json:
            raise UserError("Google Drive is enabled but the service account JSON is not configured.")
        try:
            info = json.loads(sa_json)
        except ValueError as e:
            raise UserError("Google Drive service account JSON is not valid JSON: %s" % e)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=['https://www.googleapis.com/auth/drive.file'])
        service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        meta = {'name': filename}
        if folder_id:
            meta['parents'] = [folder_id]
        media = MediaFileUpload(file_path, mimetype='application/zip', resumable=True)
        result = service.files().create(
            body=meta, media_body=media, fields='id', supportsAllDrives=True).execute()
        return 'fileId=%s' % result.get('id')

    def _upload_onedrive(self, file_path, filename):
        import requests
        client_id = self._get_param('onedrive_client_id')
        client_secret = self._get_param('onedrive_client_secret')
        tenant = self._get_param('onedrive_tenant_id')
        drive = (self._get_param('onedrive_drive') or '').strip('/')  # e.g. users/sales@dentmart.co.in
        folder = (self._get_param('onedrive_folder') or '').strip('/')
        if not (client_id and client_secret and tenant and drive):
            raise UserError("OneDrive is enabled but client id / secret / tenant / drive target are not all configured.")

        token_resp = requests.post(
            'https://login.microsoftonline.com/%s/oauth2/v2.0/token' % tenant,
            data={
                'client_id': client_id,
                'client_secret': client_secret,
                'scope': 'https://graph.microsoft.com/.default',
                'grant_type': 'client_credentials',
            }, timeout=60)
        token_resp.raise_for_status()
        token = token_resp.json().get('access_token')
        if not token:
            raise UserError("OneDrive authentication failed: no access token returned.")
        headers = {'Authorization': 'Bearer %s' % token}

        base = 'https://graph.microsoft.com/v1.0/%s/drive' % drive
        item_path = '%s/%s' % (folder, filename) if folder else filename
        sess = requests.post(
            '%s/root:/%s:/createUploadSession' % (base, item_path),
            headers=headers,
            json={'item': {'@microsoft.graph.conflictBehavior': 'replace'}}, timeout=60)
        sess.raise_for_status()
        upload_url = sess.json()['uploadUrl']

        size = os.path.getsize(file_path)
        chunk_size = 10 * 1024 * 1024  # 10 MiB, multiple of 320 KiB as Graph requires
        with open(file_path, 'rb') as fh:
            start = 0
            while start < size:
                data = fh.read(chunk_size)
                end = start + len(data) - 1
                put = requests.put(upload_url, headers={
                    'Content-Length': str(len(data)),
                    'Content-Range': 'bytes %d-%d/%d' % (start, end, size),
                }, data=data, timeout=300)
                if put.status_code not in (200, 201, 202):
                    put.raise_for_status()
                start = end + 1
        return item_path

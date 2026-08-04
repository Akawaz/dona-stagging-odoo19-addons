# -*- coding: utf-8 -*-
from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ── Schedule ──
    dbk_schedule_enabled = fields.Boolean(
        string="Automatic scheduled backup",
        config_parameter='db_backup_cloud.schedule_enabled')

    # ── Local ──
    dbk_local_enabled = fields.Boolean(
        string="Save to local folder",
        config_parameter='db_backup_cloud.local_enabled')
    dbk_local_path = fields.Char(
        string="Local folder path",
        config_parameter='db_backup_cloud.local_path',
        help="Server folder where backups are written. Defaults to a temp folder if empty.")
    dbk_local_keep = fields.Integer(
        string="Keep last N local backups",
        config_parameter='db_backup_cloud.local_keep',
        help="Older local backups for this database are deleted. Set 0 to keep all.")

    # ── AWS S3 ──
    dbk_s3_enabled = fields.Boolean(
        string="Upload to AWS S3", config_parameter='db_backup_cloud.s3_enabled')
    dbk_s3_access_key = fields.Char(
        string="S3 Access Key", config_parameter='db_backup_cloud.s3_access_key')
    dbk_s3_secret_key = fields.Char(
        string="S3 Secret Key", config_parameter='db_backup_cloud.s3_secret_key')
    dbk_s3_bucket = fields.Char(
        string="S3 Bucket", config_parameter='db_backup_cloud.s3_bucket')
    dbk_s3_region = fields.Char(
        string="S3 Region", config_parameter='db_backup_cloud.s3_region')
    dbk_s3_prefix = fields.Char(
        string="S3 Folder/Prefix", config_parameter='db_backup_cloud.s3_prefix')
    dbk_s3_endpoint = fields.Char(
        string="S3 Endpoint URL", config_parameter='db_backup_cloud.s3_endpoint',
        help="Leave empty for AWS. Set for S3-compatible storage (MinIO, Wasabi, etc.).")

    # ── Google Drive ──
    dbk_gdrive_enabled = fields.Boolean(
        string="Upload to Google Drive", config_parameter='db_backup_cloud.gdrive_enabled')
    # Multi-line Text: res.config.settings forbids config_parameter on non-simple
    # types, so this is a plain field persisted manually in get_values/set_values.
    dbk_gdrive_service_account_json = fields.Text(
        string="Service Account JSON",
        help="Paste the full service-account key JSON. Share the target Drive folder with the "
             "service account's client_email.")
    dbk_gdrive_folder_id = fields.Char(
        string="Drive Folder ID", config_parameter='db_backup_cloud.gdrive_folder_id',
        help="ID of the Drive folder to upload into (from its URL). Leave empty for the root.")

    # ── OneDrive ──
    dbk_onedrive_enabled = fields.Boolean(
        string="Upload to OneDrive", config_parameter='db_backup_cloud.onedrive_enabled')
    dbk_onedrive_client_id = fields.Char(
        string="Azure App Client ID", config_parameter='db_backup_cloud.onedrive_client_id')
    dbk_onedrive_client_secret = fields.Char(
        string="Azure App Client Secret", config_parameter='db_backup_cloud.onedrive_client_secret')
    dbk_onedrive_tenant_id = fields.Char(
        string="Azure Tenant ID", config_parameter='db_backup_cloud.onedrive_tenant_id')
    dbk_onedrive_drive = fields.Char(
        string="Drive Target", config_parameter='db_backup_cloud.onedrive_drive',
        help="App-only target, e.g. 'users/backup@yourtenant.com' or 'drives/<drive-id>'.")
    dbk_onedrive_folder = fields.Char(
        string="OneDrive Folder", config_parameter='db_backup_cloud.onedrive_folder',
        help="Destination folder path inside the drive, e.g. 'Backups/Odoo'. Leave empty for root.")

    def get_values(self):
        res = super().get_values()
        res['dbk_gdrive_service_account_json'] = self.env['ir.config_parameter'].sudo().get_param(
            'db_backup_cloud.gdrive_service_account_json', '')
        return res

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            'db_backup_cloud.gdrive_service_account_json', self.dbk_gdrive_service_account_json or '')

    def action_db_backup_now(self):
        """Persist the form, then run a backup immediately."""
        self.ensure_one()
        self.execute()
        return self.env['db.backup'].action_backup_now()

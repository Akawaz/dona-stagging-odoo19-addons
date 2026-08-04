# -*- coding: utf-8 -*-
from odoo import models, fields, api


class HrContractRule(models.Model):
    _name = 'hr.contract.rule'
    _description = 'Contract Clause (Rule)'
    _order = 'sequence, id'

    name = fields.Char(string="Name", required=True, translate=True)
    sequence = fields.Integer(string="Sequence", default=10)
    title = fields.Char(string="Section Title", required=True, translate=True)
    description = fields.Html(string="Description", required=True, translate=True)
    nationality_type = fields.Selection([
        ('bahraini', 'Bahraini'),
        ('non_bahraini', 'Non-Bahraini'),
        ('both', 'Both'),
    ], string="Nationality Type", default='both', required=True)
    company_id = fields.Many2one('res.company', string="Company", 
                                  default=lambda self: self.env.company)
    active = fields.Boolean(default=True)


class HrContractTemplate(models.Model):
    _name = 'hr.contract.template'
    _description = 'Contract Template'
    _order = 'sequence, id'

    name = fields.Char(string="Name", required=True, translate=True)
    sequence = fields.Integer(string="Sequence", default=10)
    nationality_type = fields.Selection([
        ('bahraini', 'Bahraini'),
        ('non_bahraini', 'Non-Bahraini'),
    ], string="Nationality Type", required=True)
    company_id = fields.Many2one('res.company', string="Company",
                                  default=lambda self: self.env.company)
    rule_ids = fields.Many2many('hr.contract.rule', string="Contract Rules")
    active = fields.Boolean(default=True)


class HrEmployeeSalaryLine(models.Model):
    _name = 'hr.employee.salary.line'
    _description = 'Employee Salary Line'
    _order = 'sequence, id'

    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade')
    allowance_name = fields.Char(string="Allowance Name", required=True)
    amount = fields.Float(string="Amount", required=True)
    currency_id = fields.Many2one('res.currency', string="Currency",
                                  default=lambda self: self.env.company.currency_id)
    sequence = fields.Integer(string="Sequence", default=10)


class ResCompany(models.Model):
    _inherit = 'res.company'

    contract_representative = fields.Char(string="Contract Representative")
    contract_cr_number = fields.Char(string="CR Number")
    contract_address = fields.Text(string="Contract Address")
    contract_phone = fields.Char(string="Contract Phone")
    contract_email = fields.Char(string="Contract Email")
    contract_website = fields.Char(string="Contract Website")
    contract_header_image = fields.Binary(string="Contract Header Image")
    contract_footer_image = fields.Binary(string="Contract Footer Image")


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    contract_template_id = fields.Many2one('hr.contract.template',
                                           string="Contract Template")
    salary_line_ids = fields.One2many('hr.employee.salary.line', 'employee_id',
                                      string="Salary Lines")
    
    @api.onchange('contract_id')
    def _onchange_contract_id(self):
        """Auto-populate salary lines from contract when contract changes"""
        if self.contract_id:
            # Clear existing lines
            self.salary_line_ids = [(5, 0, 0)]
            
            # Add basic salary from contract wage
            if self.contract_id.wage:
                self.salary_line_ids = [(0, 0, {
                    'allowance_name': 'Basic Salary',
                    'amount': self.contract_id.wage,
                    'sequence': 10,
                })]

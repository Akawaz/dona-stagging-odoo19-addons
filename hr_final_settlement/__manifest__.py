# -*- coding: utf-8 -*-
{
    'name': 'Employee Final Settlement',
    'version': '19.0.1.0.0',
    'summary': 'End of service / final settlement, clearance and Arabic settlement agreement, integrated with Payroll and the employee termination workflow.',
    'description': """
Employee Final Settlement
==========================

Extends the standard Odoo employee termination/archive workflow with a
dedicated Final Settlement business document:

* "Go to Final Settlement" action on the Employee Termination wizard
* Final settlement calculation engine (annual leave encashment, final month
  salary, Social Insurance Organization deduction, other earnings/deductions)
  built on real Odoo Time Off balances and the employee's current
  ``hr.version`` (contract) data
* HR review / approval workflow with audited manual overrides
* Dedicated Final Settlement payroll structure and salary rules, consumed
  through a generated ``hr.payslip``
* Arabic (RTL) Final Settlement & Clearance Agreement PDF report, based on
  the Mr. Adel template, with legal wording and calculation basis kept
  configurable rather than hard-coded

This module does not modify Odoo core and does not create or depend on
``hr.contract`` (removed/merged into ``hr.version`` in Odoo 19).

Financial/legal parameters (SIO percentage, daily rate method, leave
calculation method, governing law text, clearance wording, etc.) must be
reviewed and confirmed by the company's HR/payroll/legal team before
production use.
""",
    'category': 'Human Resources/Payroll',
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': [
        'hr',
        'hr_holidays',
        'hr_payroll',
    ],
    'data': [
        'security/hr_final_settlement_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/hr_payslip_input_type_data.xml',
        'data/hr_salary_rule_category_data.xml',
        'data/hr_payroll_structure_type_data.xml',
        'data/hr_payroll_structure_data.xml',
        'data/hr_salary_rule_data.xml',
        'views/hr_final_settlement_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_departure_wizard_views.xml',
        'views/hr_payslip_views.xml',
        'views/res_config_settings_views.xml',
        'views/hr_final_settlement_menus.xml',
        'report/hr_final_settlement_report.xml',
        'report/hr_final_settlement_report_templates.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}

# -*- coding: utf-8 -*-
{
    'name': 'HR Employee Allowances',
    'version': '19.0.1.0.0',
    'summary': 'Add Transportation, Housing and Other allowance fields '
               'next to the employee wage.',
    'description': """
HR Employee Allowances
======================

Adds three monetary allowance fields shown right after the *Wage* field on
the employee's Payroll tab (Contract Overview):

* Transportation Allowance
* Housing Allowance
* Other Allowances

The fields are stored on ``hr.version`` (where the wage lives in Odoo 19) so
each contract version keeps its own allowance amounts, and are exposed on
``hr.employee`` through the standard delegation inheritance.
""",
    'category': 'Human Resources/Employees',
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': ['hr'],
    'data': [
        'views/hr_employee_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

{
    "name": "Employee Contract Printing",
    "version": "19.0.2.0.0",
    "category": "Human Resources",
    "summary": "Print Employment Contract based on Employee Nationality",
    "author": "Fatema Malalla",
    "license": "LGPL-3",

    "depends": [
        "hr",
    ],

    "data": [
        "security/ir.model.access.csv",
        "views/contract_rule_views.xml",
        "views/hr_employee_views.xml",
        "views/res_config_settings_views.xml",
        "data/demo_contract_rules.xml",
        "data/paperformat.xml",
        "report/report_action.xml",
        "report/report_bahraini.xml",
        "report/report_non_bahraini.xml",
    ],
    'assets': {
        'web.report_assets_common': [
            'hr_contract_print/static/src/css/contract_report.css',
        ],
    },
    "installable": True,
    "application": False,
}

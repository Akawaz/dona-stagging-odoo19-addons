{
    "name": "Employee Contract Print",
    "version": "19.0.1.0.0",
    "summary": "Print Bahraini and Non-Bahraini employee contracts",

    "category": "Human Resources",

    "author": "Fatema Malalla",

    "license": "LGPL-3",

    "depends": [
        "hr",
        "hr_recruitment",
    ],

    "data": [

        # Security
        "security/ir.model.access.csv",

        # data
        "data/contract_templates.xml",

        # Views
        "views/hr_contract_template_views.xml",
        "views/hr_employee_views.xml",
        "views/hr_job_views.xml",
        "views/res_company_views.xml",

        # Reports
        "report/paperformat.xml",
        "report/report_action.xml",
        "report/report_employee_contract.xml",

    ],

    "installable": True,
    "application": False,
}

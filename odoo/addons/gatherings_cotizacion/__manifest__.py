{
    "name": "Gatherings Cotizaciones web",
    "version": "18.0.1.0.0",
    "summary": "Cotizaciones del sitio web en Odoo: precios oficiales, PDF y correo con la marca de Gatherings",
    "description": "Recibe pedidos del sitio gatheringsgt.com, crea la cotización con los precios oficiales (precio final, sin impuesto aparte) y la envía "
                   "por correo al cliente, o la deja en borrador para revisión cuando lleva productos a la medida o no cumple el mínimo. "
                   "Incluye la plantilla de PDF y de correo con el logo, los colores y las tipografías de la marca.",
    "author": "Gatherings GT",
    "license": "LGPL-3",
    "category": "Sales",
    "depends": ["base", "mail", "sale_management"],
    "data": [
        "views/product_views.xml",
        "views/sale_order_views.xml",
        "views/res_company_views.xml",
        "views/report_templates.xml",
        "data/mail_template_data.xml",
    ],
    "assets": {
        "web.report_assets_common": [
            "gatherings_cotizacion/static/src/scss/report.scss",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}

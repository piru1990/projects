"""Catálogo oficial de Gatherings (precios en quetzales, IVA 12 % incluido).

`web_id` es el id del producto en gatheringsgt.com (assets/shared.js). `revision=True` marca los productos que Andrea debe
revisar antes de enviar la cotización (a la medida o con precio por confirmar). No depende de Odoo: se prueba solo.
"""

PRODUCTOS = [
    {"sku": "GT-SINGLE", "web_id": "single", "nombre": "The Single", "precio": 150, "minimo": 1},
    {"sku": "GT-COZY", "web_id": "cozy", "nombre": "The Cozy", "precio": 260, "minimo": 1},
    {"sku": "GT-HOMESTYLE", "web_id": "homestyle", "nombre": "The Homestyle", "precio": 500, "minimo": 1},
    {"sku": "GT-GATHERING", "web_id": "gathering", "nombre": "The Gathering", "precio": 800, "minimo": 1},
    {"sku": "GT-TAILORED", "web_id": "tailored", "nombre": "The Tailored", "precio": 0, "minimo": 1, "revision": True},
    {"sku": "GT-LITTLEBOX", "web_id": "little-box", "nombre": "The Little Box", "precio": 65, "minimo": 5},
    {"sku": "GT-CELEBRATIONBOX", "web_id": "celebration-box", "nombre": "The Celebration Box", "precio": 175, "minimo": 5},
    {"sku": "GT-MINIDOME", "web_id": "mini-dome", "nombre": "The Mini Dome", "precio": 30, "minimo": 10},
    {"sku": "GT-BIGDOME", "web_id": "big-dome", "nombre": "The Big Dome", "precio": 50, "minimo": 10},
    {"sku": "GT-GLASSDOME", "web_id": "glass-dome", "nombre": "The Glass Dome", "precio": 75, "minimo": 10},
    {"sku": "GT-GRAZING", "web_id": "grazing-table", "nombre": "The Grazing Table", "precio": 90, "minimo": 20,
     "unidad": "persona", "revision": True},
    # Precio por confirmar con Andrea (2026-10-23): por eso pasa por revisión.
    {"sku": "GT-EXPERIENCE", "web_id": "experience", "nombre": "The Experience", "precio": 150, "minimo": 5, "revision": True},
]

IVA = {"nombre": "IVA 12% (incluido)", "porcentaje": 12}
VALIDEZ_DIAS = 7
ENVIO_NOTA = "Envío a domicilio: Q35–Q45 según la zona; se confirma aparte."
HORARIOS = ("Durante la mañana", "Durante la tarde")

# Freno al abuso (el endpoint envía correos a quien escriba el formulario).
LIMITE_POR_CORREO_DIA = 5      # más solicitudes del mismo correo en 24 h: se rechazan
LIMITE_GLOBAL_HORA = 30        # más solicitudes en una hora: quedan en borrador, sin correos al cliente

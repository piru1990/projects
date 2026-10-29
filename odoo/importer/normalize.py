"""Lee el Excel de ventas «Reporte de Ventas» (hoja Consolidado) y lo convierte en pedidos limpios.

Problemas conocidos del Excel, que este módulo corrige o reporta:
- Fechas mezcladas: texto dd/mm/aaaa y fechas reales con día y mes invertidos (Excel leyó dd/mm como mm/dd).
- SUBTOTAL es el precio unitario (TOTAL = CANTIDAD * SUBTOTAL + ENVÍO) y a veces es una fórmula (=125+75).
- PRODUCTO es texto libre: los que no son un producto del catálogo (combos, cajas, vino) se importan como
  línea «Otros productos (histórico)» con el texto original, y quedan marcados para revisión.
- Teléfonos como número decimal; «No registrado» como nombre de cliente.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import operator
import re
import unicodedata
from pathlib import Path
from dataclasses import dataclass, field

MESES = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6, "JULIO": 7,
         "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12}
SIN_CLIENTE = "Cliente no registrado"


@dataclass
class Pedido:
    numero: int
    fecha_pedido: dt.date
    fecha_entrega: dt.date | None
    horario: str | None
    cliente: str
    empresa: str | None
    tipo_cliente: str | None
    telefono: str | None
    contacto: str | None
    cantidad: float
    producto_texto: str
    sku: str | None            # None = texto libre (línea histórica)
    desglose: list[tuple[str, float]] | None   # combo partido en líneas de catálogo (+ descuento)
    precio_unitario: float
    direccion: str | None
    observaciones: str | None
    envio: float
    metodo_pago: str | None
    pagado: bool
    fecha_pago: dt.date | None
    entregado: bool
    facturacion: str | None
    avisos: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return self.cantidad * self.precio_unitario + self.envio


def quitar_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def clave_cliente(nombre: str) -> str:
    return re.sub(r"\s+", " ", quitar_acentos(nombre).casefold()).strip()


def _texto(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def _aritmetica(n) -> float:
    """Evalúa fórmulas simples del Excel («=125+75») sin eval: solo números y + - * /."""
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
        return float(n.value)
    if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
        return _OPS[type(n.op)](_aritmetica(n.left), _aritmetica(n.right))
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
        v = _aritmetica(n.operand)
        return -v if isinstance(n.op, ast.USub) else v
    raise ValueError("fórmula no soportada")


def _numero(v, aviso: list[str], campo: str) -> float:
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return _aritmetica(ast.parse(str(v).strip().lstrip("="), mode="eval").body)
    except (SyntaxError, ValueError, ZeroDivisionError):
        pass
    aviso.append(f"{campo} no numérico: {v!r}")
    return 0.0


def _fecha(v, ref: dt.date | None = None) -> dt.date | None:
    """Texto dd/mm/aaaa o fecha real con día y mes invertidos. 'Pendiente' y vacíos -> None."""
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        v = v.date()
    if isinstance(v, dt.date):
        # Excel interpretó dd/mm como mm/dd: intercambiar. Si no se puede, dejarla igual.
        try:
            return dt.date(v.year, v.day, v.month)
        except ValueError:
            return v
    m = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})/(\d{2,4})\s*", str(v))
    if not m:
        return None
    d, mo, y = (int(x) for x in m.groups())
    if y < 100:
        y += 2000
    elif y < 1000:  # año truncado («13/02/202»): usar el de referencia
        y = ref.year if ref else 2000 + y % 100
    try:
        return dt.date(y, mo, d)
    except ValueError:
        return None


def _coherencia_fechas(ped: dt.date, ent: dt.date, av: list[str]) -> tuple[dt.date, dt.date]:
    """Corrige años mal tecleados en el Excel (pedido 2025-02-05 con entrega 2026-02-13) y avisa del resto."""
    def con_anio(d: dt.date, y: int) -> dt.date | None:
        try:
            return d.replace(year=y)
        except ValueError:
            return None

    if (ent - ped).days > 180 and (nuevo := con_anio(ped, ent.year)) and 0 <= (ent - nuevo).days <= 180:
        av.append(f"fecha de pedido corregida de {ped} a {nuevo} (año distinto al de la entrega)")
        return nuevo, ent
    if ent < ped:
        nuevo = con_anio(ent, ped.year)
        if nuevo and 0 <= (nuevo - ped).days <= 180:
            av.append(f"fecha de entrega corregida de {ent} a {nuevo} (año distinto al del pedido)")
            return ped, nuevo
        av.append(f"la entrega ({ent}) es anterior al pedido ({ped}); revisar")
    return ped, ent


def _telefono(v) -> str | None:
    if v is None:
        return None
    digitos = re.sub(r"\D", "", str(int(v)) if isinstance(v, float) else str(v))
    if not digitos:
        return None
    return "+502 " + digitos if len(digitos) == 8 else digitos


_CAT = json.loads((Path(__file__).resolve().parent.parent / "catalog.json").read_text(encoding="utf-8"))
# nombre sin «The», en minúsculas -> sku, y su precio de lista (final)
CATALOGO = {re.sub(r"^the\s+", "", quitar_acentos(p["nombre"]).casefold()): p["sku"] for p in _CAT["productos"]}
PRECIOS = {p["sku"]: p["precio"] for p in _CAT["productos"]}
ALIAS = _CAT["alias"]


def _clave_producto(texto: str) -> str:
    return re.sub(r"^the\s+", "", quitar_acentos(texto).casefold().strip())


def _producto(texto: str | None) -> str | None:
    """sku del catálogo si el texto es un producto (o un alias como «Cozy Box + Vino»); None = texto libre."""
    if not texto:
        return None
    k = _clave_producto(texto)
    if k in CATALOGO:
        return CATALOGO[k]
    return next((sku for alias, sku in ALIAS.items() if k.startswith(alias)), None)


def producto_exacto(texto: str | None) -> bool:
    """True si el texto es exactamente el nombre del catálogo (si no, la línea conserva el texto original)."""
    return bool(texto) and _clave_producto(texto) in CATALOGO


def _desglose(texto: str, cantidad: float, precio: float) -> list[tuple[str, float]] | None:
    """«Gathering + Cozy» (cantidad 1) -> [(sku, precio de lista), ..., ("GT-DESCUENTO", dif)] si todas las partes son
    productos con precio y el combo no tiene otra interpretación; si no, None (queda como texto libre)."""
    if cantidad != 1:
        return None
    partes = [p for p in re.split(r"\s*(?:\+|\by\b)\s*", texto.strip(), flags=re.I) if p]
    skus = [CATALOGO.get(_clave_producto(p)) for p in partes]
    if len(partes) < 2 or not all(skus) or not all(PRECIOS[k] > 0 for k in skus):
        return None
    lineas = [(k, float(PRECIOS[k])) for k in skus]
    dif = round(precio - sum(p for _, p in lineas), 2)
    if dif > 0:  # cobró más que la lista: hay algo extra que el texto no dice; mejor revisarlo a mano
        return None
    return lineas + ([("GT-DESCUENTO", dif)] if dif else [])


def leer_pedidos(ruta: str) -> list[Pedido]:
    import openpyxl
    ws = openpyxl.load_workbook(ruta, data_only=False).worksheets[0]
    filas = list(ws.iter_rows(values_only=True))
    cache = list(openpyxl.load_workbook(ruta, data_only=True).worksheets[0].iter_rows(values_only=True))
    cab = [(_texto(c) or "").upper() for c in filas[0]]
    col = {n: i for i, n in enumerate(cab) if n}
    pedidos: list[Pedido] = []
    for fila, fila_cache in zip(filas[1:], cache[1:]):
        g = lambda n: fila[col[n]] if n in col and col[n] < len(fila) else None
        if g("NÚMERO DE PEDIDO") is None:
            continue  # fila de totales o vacía
        av: list[str] = []
        numero = int(g("NÚMERO DE PEDIDO"))
        f_ped = _fecha(g("FECHA DEL PEDIDO"))
        if f_ped is None:
            raise ValueError(f"pedido {numero}: fecha de pedido ilegible ({g('FECHA DEL PEDIDO')!r})")
        mes = MESES.get((_texto(g("MES")) or "").upper())
        if mes and f_ped.month != mes:
            av.append(f"mes de la fecha ({f_ped.month}) no coincide con MES ({mes})")
        f_ent = _fecha(g("FECHA DE ENTREGA"), f_ped)
        if f_ent is None:
            av.append("sin fecha de entrega")
        else:
            f_ped, f_ent = _coherencia_fechas(f_ped, f_ent, av)
        prod = _texto(g("PRODUCTO")) or "(sin producto)"
        sku = _producto(prod)
        precio = _numero(g("SUBTOTAL"), av, "SUBTOTAL")
        cantidad = _numero(g("CANTIDAD"), av, "CANTIDAD") or 1.0
        desglose = _desglose(prod, cantidad, precio) if sku is None else None
        if desglose:
            av.append(f"combo {prod!r} partido en líneas de catálogo"
                      + (" con descuento" if desglose[-1][0] == "GT-DESCUENTO" else ""))
        elif sku is None:
            av.append(f"producto fuera del catálogo: {prod!r}")
        cliente = _texto(g("NOMBRE DEL CLIENTE")) or SIN_CLIENTE
        if clave_cliente(cliente) == "no registrado":
            cliente = SIN_CLIENTE
        empresa = _texto(g("NOMBRE DE EMPRESA"))
        tipo = _texto(g("TIPO DE CLIENTE")) or ("Particular" if empresa == "Particular" else None)
        if empresa and empresa.casefold() == "particular":
            empresa = None
        obs = _texto(g("OBSERVACIONES INTERNAS / PERSONALIZACIÓN"))
        if obs and obs.casefold() == "ninguna":
            obs = None
        total_excel = fila_cache[col["TOTAL"]] if "TOTAL" in col and col["TOTAL"] < len(fila_cache) else None
        envio = _numero(g("PRECIO DE ENVÍO"), av, "PRECIO DE ENVÍO")
        if isinstance(total_excel, (int, float)) and abs(total_excel - (cantidad * precio + envio)) > 0.01:
            # el Excel manda: su TOTAL es lo que se cobró; se deduce el precio unitario de ahí
            av.append(f"TOTAL del Excel (Q{total_excel:,.2f}) difiere de cantidad x subtotal + envío "
                      f"(Q{cantidad * precio + envio:,.2f}); se usó el del Excel")
            precio = (total_excel - envio) / cantidad
        pago_estado = (_texto(g("ESTADO DEL PAGO")) or "").casefold()
        metodo = _texto(g("MÉTODO DE PAGO"))
        pedidos.append(Pedido(
            numero=numero, fecha_pedido=f_ped, fecha_entrega=f_ent, horario=_texto(g("HORARIO DE ENTREGA")),
            cliente=cliente, empresa=empresa, tipo_cliente=tipo, telefono=_telefono(g("CELULAR / WHATSAPP")),
            contacto=_texto(g("IG / FB / EMAIL")), cantidad=cantidad, producto_texto=prod, sku=sku, desglose=desglose,
            precio_unitario=precio, direccion=_texto(g("DIRECCIÓN DE ENTREGA")), observaciones=obs,
            envio=envio,
            metodo_pago=None if (metodo or "").casefold() == "pendiente" else metodo,
            pagado=pago_estado == "pagado", fecha_pago=_fecha(g("FECHA DE PAGO"), f_ped),
            entregado=(_texto(g("ESTADO DEL PEDIDO")) or "").casefold() == "entregado",
            facturacion=_texto(g("FACTURACIÓN")), avisos=av))
    return pedidos


def resumen(pedidos: list[Pedido]) -> str:
    n_cli = len({clave_cliente(p.cliente) for p in pedidos})
    rev = [p for p in pedidos if p.avisos]
    libres = [p for p in pedidos if p.sku is None and not p.desglose]
    lineas = [f"{len(pedidos)} pedidos, {n_cli} clientes distintos, total Q{sum(p.total for p in pedidos):,.2f}",
              f"{len(libres)} con producto fuera del catálogo (texto libre), {len(rev)} con avisos"]
    lineas += [f"  #{p.numero}: {'; '.join(p.avisos)}" for p in rev]
    return "\n".join(lineas)

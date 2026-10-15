"""Cliente mínimo XML-RPC de Odoo (biblioteca estándar, sin dependencias)."""
from __future__ import annotations

import xmlrpc.client


class OdooRPC:
    def __init__(self, url: str, db: str, user: str, password: str):
        self.db, self.password = db, password
        self._models = xmlrpc.client.ServerProxy(f"{url.rstrip('/')}/xmlrpc/2/object", allow_none=True)
        common = xmlrpc.client.ServerProxy(f"{url.rstrip('/')}/xmlrpc/2/common")
        self.uid = common.authenticate(db, user, password, {})
        if not self.uid:
            raise RuntimeError("Odoo rechazó el usuario o la contraseña")

    def call(self, model: str, method: str, *args, **kw):
        return self._models.execute_kw(self.db, self.uid, self.password, model, method, list(args), kw)

    def search(self, model: str, domain: list, limit: int | None = None) -> list[int]:
        return self.call(model, "search", domain, **({"limit": limit} if limit else {}))

    def create(self, model: str, vals: dict) -> int:
        return self.call(model, "create", vals)

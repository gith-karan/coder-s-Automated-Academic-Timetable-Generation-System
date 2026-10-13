"""Generic, audited, role-guarded CRUD router factory.

One implementation of list / search / filter / paginate / get / create / update / delete serves
every resource (rooms, programmes, groups, faculty, subjects, …). Resource-specific behaviour is
injected through small hooks instead of copy-pasted endpoints.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import InstrumentedAttribute

from app.api.deps import Principal, require_roles
from app.core.db import get_db
from app.core.errors import AppError, not_found
from app.core.roles import Role
from app.services import audit

ApplyHook = Callable[[Session, Any, dict, Principal], None]


def snapshot(obj: Any) -> dict:
    mapper = obj.__mapper__
    return audit.scrub({a.key: getattr(obj, a.key) for a in mapper.column_attrs})


def default_apply(db: Session, obj: Any, data: dict, p: Principal) -> None:
    for k, v in data.items():
        setattr(obj, k, v)


def integrity_error(exc: IntegrityError, entity: str) -> AppError:
    msg = str(exc.orig).lower()
    if "unique" in msg or "duplicate" in msg:
        return AppError(409, "duplicate", f"A {entity} with the same code/name already exists.")
    if "foreign key" in msg or "restrict" in msg or "violates" in msg:
        return AppError(409, "in_use", f"This {entity} is referenced by other records and cannot be changed this way.")
    return AppError(409, "conflict", f"The {entity} could not be saved because it conflicts with existing data.")


def crud_router(
    *,
    model: type,
    entity: str,
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    out_schema: type[BaseModel],
    read_roles: Sequence[Role],
    write_roles: Sequence[Role],
    search: Sequence[InstrumentedAttribute] = (),
    filters: dict[str, InstrumentedAttribute] | None = None,
    order_by: Sequence[Any] = (),
    on_create: ApplyHook = default_apply,
    on_update: ApplyHook = default_apply,
    label: Callable[[Any], str] = lambda o: getattr(o, "code", None) or getattr(o, "name", "") or o.id,
) -> APIRouter:
    router = APIRouter()
    filters = filters or {}
    reader = require_roles(*read_roles)
    writer = require_roles(*write_roles)

    def _list(q, page, size, db, flt):
        stmt = select(model)
        if q and search:
            like = f"%{q.strip().lower()}%"
            stmt = stmt.where(or_(*[func.lower(c).like(like) for c in search]))
        for name, value in flt.items():
            if value is not None:
                stmt = stmt.where(filters[name] == value)
        total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        stmt = stmt.order_by(*order_by).offset((page - 1) * size).limit(size)
        items = db.execute(stmt).unique().scalars().all()
        return {"items": [out_schema.model_validate(i).model_dump(mode="json") for i in items],
                "total": total, "page": page, "size": size}

    # The list endpoint's signature is built dynamically so declared filters appear as typed query params.
    params = [
        inspect.Parameter("q", inspect.Parameter.KEYWORD_ONLY, default=Query(None, max_length=100), annotation=str | None),
        inspect.Parameter("page", inspect.Parameter.KEYWORD_ONLY, default=Query(1, ge=1, le=10_000), annotation=int),
        inspect.Parameter("size", inspect.Parameter.KEYWORD_ONLY, default=Query(25, ge=1, le=200), annotation=int),
        inspect.Parameter("p", inspect.Parameter.KEYWORD_ONLY, default=Depends(reader), annotation=Principal),
        inspect.Parameter("db", inspect.Parameter.KEYWORD_ONLY, default=Depends(get_db), annotation=Session),
    ]
    for fname, col in filters.items():
        py = col.property.columns[0].type.python_type if hasattr(col.property, "columns") else str
        params.append(inspect.Parameter(fname, inspect.Parameter.KEYWORD_ONLY, default=Query(None), annotation=py | None))

    def list_endpoint(**kw):
        return _list(kw["q"], kw["page"], kw["size"], kw["db"], {k: kw.get(k) for k in filters})

    list_endpoint.__signature__ = inspect.Signature(params)  # type: ignore[attr-defined]
    router.add_api_route("", list_endpoint, methods=["GET"], summary=f"List {entity}s",
                         operation_id=f"list_{entity.replace(' ', '_')}s")

    def _get(db: Session, item_id: str):
        obj = db.get(model, item_id)
        if obj is None:
            raise not_found(entity.capitalize())
        return obj

    @router.get("/{item_id}", response_model=out_schema, summary=f"Get {entity}",
                operation_id=f"get_{entity.replace(' ', '_')}")
    def get_item(item_id: str, p: Principal = Depends(reader), db: Session = Depends(get_db)):
        return _get(db, item_id)

    @router.post("", response_model=out_schema, status_code=201, summary=f"Create {entity}",
                 operation_id=f"create_{entity.replace(' ', '_')}")
    def create_item(body: create_schema, p: Principal = Depends(writer), db: Session = Depends(get_db)):  # type: ignore[valid-type]
        obj = model()
        try:
            on_create(db, obj, body.model_dump(), p)
            db.add(obj)
            db.flush()
            audit.record(db, action=f"{entity.replace(' ', '_')}.create", category="DATA", actor=p.user,
                         entity=entity, entity_id=obj.id, ctx=p.ctx, summary=f"Created {entity} {label(obj)}",
                         data={"after": snapshot(obj)})
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise integrity_error(exc, entity) from exc
        db.refresh(obj)
        return obj

    @router.patch("/{item_id}", response_model=out_schema, summary=f"Update {entity}",
                  operation_id=f"update_{entity.replace(' ', '_')}")
    def update_item(item_id: str, body: update_schema, p: Principal = Depends(writer),  # type: ignore[valid-type]
                    db: Session = Depends(get_db)):
        obj = _get(db, item_id)
        before = snapshot(obj)
        try:
            on_update(db, obj, body.model_dump(exclude_unset=True), p)
            db.flush()
            after = snapshot(obj)
            changed = {k: {"from": before.get(k), "to": v} for k, v in after.items() if before.get(k) != v}
            audit.record(db, action=f"{entity.replace(' ', '_')}.update", category="DATA", actor=p.user,
                         entity=entity, entity_id=obj.id, ctx=p.ctx, summary=f"Updated {entity} {label(obj)}",
                         data={"changes": changed})
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise integrity_error(exc, entity) from exc
        db.refresh(obj)
        return obj

    @router.delete("/{item_id}", status_code=204, summary=f"Delete {entity}",
                   operation_id=f"delete_{entity.replace(' ', '_')}")
    def delete_item(item_id: str, p: Principal = Depends(writer), db: Session = Depends(get_db)):
        obj = _get(db, item_id)
        before = snapshot(obj)
        name = label(obj)
        try:
            db.delete(obj)
            db.flush()
            audit.record(db, action=f"{entity.replace(' ', '_')}.delete", category="DATA", actor=p.user,
                         entity=entity, entity_id=item_id, ctx=p.ctx, summary=f"Deleted {entity} {name}",
                         data={"before": before})
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise integrity_error(exc, entity) from exc
        return Response(status_code=204)

    return router

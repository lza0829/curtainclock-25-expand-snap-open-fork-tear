from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import connect, transaction
from app.services import template as tpl_svc

router = APIRouter(tags=["templates"])


class EntryIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    slot_code: str
    executor_code: str
    start_min: int = Field(ge=0, lt=1440)
    end_min: int = Field(ge=1, le=1440)


class TemplateIn(BaseModel):
    code: str = Field(min_length=2)
    title: str
    subject: str
    entries: list[EntryIn]


class TemplatePut(BaseModel):
    title: str
    subject: str
    entries: list[EntryIn]


class ExpandIn(BaseModel):
    week_start: str


@router.get("/templates")
def list_templates():
    conn = connect()
    try:
        return tpl_svc.list_templates(conn)
    finally:
        conn.close()


@router.post("/templates")
def create_template(body: TemplateIn):
    try:
        with transaction() as conn:
            return tpl_svc.create_template(
                conn,
                code=body.code,
                title=body.title,
                subject=body.subject,
                entries=[e.model_dump() for e in body.entries],
            )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/templates/{code}")
def get_template(code: str):
    conn = connect()
    try:
        return tpl_svc.get_template(conn, code)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    finally:
        conn.close()


@router.put("/templates/{code}")
def update_template(code: str, body: TemplatePut):
    # 快照臂：此处只 bump 模板版本，绝不回写已展开批窗
    try:
        with transaction() as conn:
            return tpl_svc.update_template(
                conn,
                code,
                title=body.title,
                subject=body.subject,
                entries=[e.model_dump() for e in body.entries],
            )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/templates/{code}/expand")
def expand_template(code: str, body: ExpandIn):
    try:
        with transaction() as conn:
            return tpl_svc.expand_template(conn, code, body.week_start)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/expansions")
def list_expansions():
    conn = connect()
    try:
        return tpl_svc.list_expansions(conn)
    finally:
        conn.close()

"""Unit tests for DocumentService and document schemas (mocked AsyncSession)."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from backend.models.document import Document
from backend.schemas.document import (
    DocumentCreate,
    DocumentFilter,
    DocumentLinkRequest,
    DocumentUpdate,
)
from backend.services.document_service import DocumentService


def _sql(stmt):
    compiled = stmt.compile(dialect=postgresql.dialect())
    return str(compiled), compiled.params


def _result(one=None, items=None, scalar=None):
    r = MagicMock()
    r.scalar_one_or_none.return_value = one
    r.scalars.return_value.all.return_value = items or []
    r.scalar.return_value = scalar
    return r


@pytest.fixture
def db():
    session = MagicMock()
    session.add = MagicMock()
    for name in ("commit", "refresh", "delete", "execute", "flush"):
        setattr(session, name, AsyncMock())
    return session


@pytest.mark.unit
class TestSchemas:
    def test_create_defaults(self):
        d = DocumentCreate(title="T", type="report")
        assert d.version == 1 and d.tags == [] and d.content is None

    def test_title_bounds(self):
        with pytest.raises(ValidationError):
            DocumentCreate(title="", type="report")
        with pytest.raises(ValidationError):
            DocumentCreate(title="x" * 256, type="report")

    def test_invalid_type(self):
        with pytest.raises(ValidationError):
            DocumentCreate(title="T", type="memo")

    @pytest.mark.parametrize(
        "kw",
        [
            {"version": 0},
            {"file_size": -1},
            {"file_path": "x" * 501},
            {"mime_type": "x" * 101},
        ],
    )
    def test_numeric_and_length_bounds(self, kw):
        with pytest.raises(ValidationError):
            DocumentCreate(title="T", type="report", **kw)

    def test_file_size_zero_allowed(self):
        assert DocumentCreate(title="T", type="other", file_size=0).file_size == 0

    def test_update_validation(self):
        assert DocumentUpdate().model_dump(exclude_unset=True) == {}
        with pytest.raises(ValidationError):
            DocumentUpdate(version=0)
        with pytest.raises(ValidationError):
            DocumentUpdate(type="bogus")

    def test_link_request(self):
        eid = uuid4()
        r = DocumentLinkRequest(entity_type="project", entity_id=eid)
        assert r.link_type == "reference" and r.entity_id == eid
        with pytest.raises(ValidationError):
            DocumentLinkRequest(entity_type="user", entity_id=eid)
        with pytest.raises(ValidationError):
            DocumentLinkRequest(entity_type="task", entity_id=eid, link_type="x")
        with pytest.raises(ValidationError):
            DocumentLinkRequest(entity_type="task", entity_id="not-a-uuid")

    def test_filter_validation(self):
        with pytest.raises(ValidationError):
            DocumentFilter(type="bogus")
        assert DocumentFilter(tags=["a"]).tags == ["a"]


@pytest.mark.unit
@pytest.mark.asyncio
class TestCrud:
    async def test_create(self, db):
        oid = uuid4()
        data = DocumentCreate(
            title="Spec",
            type="specification",
            tags=["a", "b"],
            owner_id=oid,
            content="body",
        )
        doc = await DocumentService.create_document(db, data)
        assert isinstance(doc, Document)
        assert (doc.title, doc.type, doc.tags, doc.owner_id, doc.content) == (
            "Spec",
            "specification",
            ["a", "b"],
            oid,
            "body",
        )
        assert doc.version == 1
        db.add.assert_called_once_with(doc)
        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once_with(doc, ["owner"])

    async def test_get_found(self, db):
        d = Document(title="a", type="other")
        db.execute.return_value = _result(one=d)
        did = uuid4()
        assert await DocumentService.get_document(db, did) is d
        sql, params = _sql(db.execute.call_args.args[0])
        assert "documents.id" in sql and did in params.values()

    async def test_get_missing(self, db):
        db.execute.return_value = _result(one=None)
        assert await DocumentService.get_document(db, uuid4()) is None

    async def test_update_partial(self, db):
        d = Document(title="old", type="report", version=1, tags=["x"])
        db.execute.return_value = _result(one=d)
        out = await DocumentService.update_document(
            db, uuid4(), DocumentUpdate(version=2, tags=[])
        )
        assert out is d
        assert d.version == 2 and d.tags == [] and d.title == "old"
        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once_with(d, ["owner"])

    async def test_update_missing(self, db):
        db.execute.return_value = _result(one=None)
        assert (
            await DocumentService.update_document(
                db, uuid4(), DocumentUpdate(title="x")
            )
            is None
        )
        db.commit.assert_not_awaited()

    async def test_delete_found(self, db):
        d = Document(title="a", type="other")
        db.execute.return_value = _result(one=d)
        assert await DocumentService.delete_document(db, uuid4()) is True
        db.delete.assert_awaited_once_with(d)
        db.commit.assert_awaited_once()

    async def test_delete_missing(self, db):
        db.execute.return_value = _result(one=None)
        assert await DocumentService.delete_document(db, uuid4()) is False
        db.delete.assert_not_awaited()
        db.commit.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
class TestList:
    async def test_pagination_and_order(self, db):
        docs = [Document(title="a", type="other")]
        db.execute.side_effect = [_result(scalar=42), _result(items=docs)]
        out, total = await DocumentService.list_documents(db, page=2, page_size=5)
        assert out == docs and total == 42
        sql, params = _sql(db.execute.call_args_list[1].args[0])
        assert "ORDER BY documents.created_date DESC" in sql
        assert "WHERE" not in sql
        assert sorted(params.values()) == [5, 5]  # limit 5, offset 5

    async def test_type_owner_filters(self, db):
        oid = uuid4()
        db.execute.side_effect = [_result(scalar=0), _result()]
        await DocumentService.list_documents(
            db, DocumentFilter(type="policy", owner_id=oid)
        )
        sql, params = _sql(db.execute.call_args_list[1].args[0])
        assert "documents.type" in sql and "documents.owner_id" in sql
        assert "policy" in params.values() and oid in params.values()

    async def test_each_tag_is_separate_containment_condition(self, db):
        db.execute.side_effect = [_result(scalar=0), _result()]
        await DocumentService.list_documents(db, DocumentFilter(tags=["a", "b"]))
        sql, _ = _sql(db.execute.call_args_list[1].args[0])
        assert sql.count("documents.tags @>") == 2
        assert " AND " in sql

    async def test_search_matches_title_or_content(self, db):
        db.execute.side_effect = [_result(scalar=0), _result()]
        await DocumentService.list_documents(db, DocumentFilter(search="foo"))
        sql, params = _sql(db.execute.call_args_list[1].args[0])
        assert "documents.title ILIKE" in sql and "documents.content ILIKE" in sql
        assert " OR " in sql
        assert list(params.values()).count("%foo%") == 2

    async def test_empty_tags_list_adds_no_filter(self, db):
        db.execute.side_effect = [_result(scalar=0), _result()]
        await DocumentService.list_documents(db, DocumentFilter(tags=[]))
        sql, _ = _sql(db.execute.call_args_list[1].args[0])
        assert "WHERE" not in sql

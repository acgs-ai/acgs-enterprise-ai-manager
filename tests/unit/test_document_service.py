"""Unit tests for DocumentService and document schemas (mocked AsyncSession)."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.models.document import Document
from backend.schemas.document import (
    DocumentCreate,
    DocumentFilter,
    DocumentLinkRequest,
    DocumentUpdate,
)
from backend.services.document_service import DocumentService
from tests.unit.conftest import compile_sql, make_result


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
    async def test_create(self, mock_db):
        oid = uuid4()
        data = DocumentCreate(
            title="Spec",
            type="specification",
            tags=["a", "b"],
            owner_id=oid,
            content="body",
        )
        doc = await DocumentService.create_document(mock_db, data)
        assert isinstance(doc, Document)
        assert (doc.title, doc.type, doc.tags, doc.owner_id, doc.content) == (
            "Spec",
            "specification",
            ["a", "b"],
            oid,
            "body",
        )
        assert doc.version == 1
        mock_db.add.assert_called_once_with(doc)
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once_with(doc, ["owner"])

    async def test_get_found(self, mock_db):
        d = Document(title="a", type="other")
        mock_db.execute.return_value = make_result(scalar_one_or_none=d)
        did = uuid4()
        assert await DocumentService.get_document(mock_db, did) is d
        sql, params = compile_sql(mock_db.execute.call_args.args[0])
        assert "documents.id" in sql and did in params.values()

    async def test_get_missing(self, mock_db):
        mock_db.execute.return_value = make_result(scalar_one_or_none=None)
        assert await DocumentService.get_document(mock_db, uuid4()) is None

    async def test_update_partial(self, mock_db):
        d = Document(title="old", type="report", version=1, tags=["x"])
        mock_db.execute.return_value = make_result(scalar_one_or_none=d)
        out = await DocumentService.update_document(
            mock_db, uuid4(), DocumentUpdate(version=2, tags=[])
        )
        assert out is d
        assert d.version == 2 and d.tags == [] and d.title == "old"
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once_with(d, ["owner"])

    async def test_update_missing(self, mock_db):
        mock_db.execute.return_value = make_result(scalar_one_or_none=None)
        assert (
            await DocumentService.update_document(
                mock_db, uuid4(), DocumentUpdate(title="x")
            )
            is None
        )
        mock_db.commit.assert_not_awaited()

    async def test_delete_found(self, mock_db):
        d = Document(title="a", type="other")
        mock_db.execute.return_value = make_result(scalar_one_or_none=d)
        assert await DocumentService.delete_document(mock_db, uuid4()) is True
        mock_db.delete.assert_awaited_once_with(d)
        mock_db.commit.assert_awaited_once()

    async def test_delete_missing(self, mock_db):
        mock_db.execute.return_value = make_result(scalar_one_or_none=None)
        assert await DocumentService.delete_document(mock_db, uuid4()) is False
        mock_db.delete.assert_not_awaited()
        mock_db.commit.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
class TestList:
    async def test_pagination_and_order(self, mock_db):
        docs = [Document(title="a", type="other")]
        mock_db.execute.side_effect = [
            make_result(scalar=42),
            make_result(scalars=docs),
        ]
        out, total = await DocumentService.list_documents(mock_db, page=2, page_size=5)
        assert out == docs and total == 42
        sql, params = compile_sql(mock_db.execute.call_args_list[1].args[0])
        assert "ORDER BY documents.created_date DESC" in sql
        assert "WHERE" not in sql
        assert sorted(params.values()) == [5, 5]  # limit 5, offset 5

    async def test_type_owner_filters(self, mock_db):
        oid = uuid4()
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        await DocumentService.list_documents(
            mock_db, DocumentFilter(type="policy", owner_id=oid)
        )
        sql, params = compile_sql(mock_db.execute.call_args_list[1].args[0])
        assert "documents.type" in sql and "documents.owner_id" in sql
        assert "policy" in params.values() and oid in params.values()

    async def test_each_tag_is_separate_containment_condition(self, mock_db):
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        await DocumentService.list_documents(mock_db, DocumentFilter(tags=["a", "b"]))
        sql, _ = compile_sql(mock_db.execute.call_args_list[1].args[0])
        assert sql.count("documents.tags @>") == 2
        assert " AND " in sql

    async def test_search_matches_title_or_content(self, mock_db):
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        await DocumentService.list_documents(mock_db, DocumentFilter(search="foo"))
        sql, params = compile_sql(mock_db.execute.call_args_list[1].args[0])
        assert "documents.title ILIKE" in sql and "documents.content ILIKE" in sql
        assert " OR " in sql
        assert list(params.values()).count("%foo%") == 2

    async def test_empty_tags_list_adds_no_filter(self, mock_db):
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        await DocumentService.list_documents(mock_db, DocumentFilter(tags=[]))
        sql, _ = compile_sql(mock_db.execute.call_args_list[1].args[0])
        assert "WHERE" not in sql

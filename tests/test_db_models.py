"""Tests for SQLAlchemy async models and DB infrastructure (issue b54.8)."""

import uuid

import pytest

sa = pytest.importorskip("sqlalchemy", reason="sqlalchemy not installed")


# ---------------------------------------------------------------------------
# Video model
# ---------------------------------------------------------------------------

class TestVideoModel:
    def test_video_has_expected_columns(self):
        from api.src.db.models import Video

        mapper = sa.inspect(Video)
        col_names = {c.key for c in mapper.column_attrs}
        expected = {"id", "url", "title", "status", "language", "s3_prefix", "created_at"}
        assert expected.issubset(col_names), f"Missing columns: {expected - col_names}"

    def test_video_id_is_uuid_primary_key(self):
        from api.src.db.models import Video

        table = Video.__table__
        pk_cols = [c.name for c in table.primary_key.columns]
        assert pk_cols == ["id"]

    def test_video_language_default(self):
        from api.src.db.models import Video

        col = Video.__table__.c.language
        assert col.default is not None
        assert col.default.arg == "en"

    def test_video_s3_prefix_nullable(self):
        from api.src.db.models import Video

        col = Video.__table__.c.s3_prefix
        assert col.nullable is True

    def test_video_created_at_has_server_default(self):
        from api.src.db.models import Video

        col = Video.__table__.c.created_at
        assert col.server_default is not None


# ---------------------------------------------------------------------------
# PipelineJob model
# ---------------------------------------------------------------------------

class TestPipelineJobModel:
    def test_pipeline_job_has_expected_columns(self):
        from api.src.db.models import PipelineJob

        mapper = sa.inspect(PipelineJob)
        col_names = {c.key for c in mapper.column_attrs}
        expected = {"id", "video_id", "stage", "status", "started_at", "completed_at", "error"}
        assert expected.issubset(col_names), f"Missing columns: {expected - col_names}"

    def test_pipeline_job_id_is_uuid_primary_key(self):
        from api.src.db.models import PipelineJob

        table = PipelineJob.__table__
        pk_cols = [c.name for c in table.primary_key.columns]
        assert pk_cols == ["id"]

    def test_pipeline_job_video_id_is_foreign_key(self):
        from api.src.db.models import PipelineJob

        col = PipelineJob.__table__.c.video_id
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "videos.id" in fk_targets

    def test_pipeline_job_nullable_fields(self):
        from api.src.db.models import PipelineJob

        table = PipelineJob.__table__
        assert table.c.started_at.nullable is True
        assert table.c.completed_at.nullable is True
        assert table.c.error.nullable is True


# ---------------------------------------------------------------------------
# Engine / get_db
# ---------------------------------------------------------------------------

class TestGetDb:
    def test_get_db_raises_when_no_dsn(self, monkeypatch):
        """get_db should raise a clear error when database_url is empty."""
        monkeypatch.setenv("FW_DATABASE_URL", "")
        monkeypatch.setenv("FW_POSTGRES_DSN", "")

        from api.src.db import engine as engine_mod
        # Force re-evaluation by calling the factory
        with pytest.raises(RuntimeError, match="(?i)database.*(url|dsn|config)"):
            engine_mod.init_engine("")


# ---------------------------------------------------------------------------
# Config aliases
# ---------------------------------------------------------------------------

class TestConfigDatabaseUrl:
    def test_database_url_field_exists(self):
        from api.src.core.config import Settings

        s = Settings(database_url="postgresql+asyncpg://u:p@localhost/db")
        assert s.database_url == "postgresql+asyncpg://u:p@localhost/db"

    def test_postgres_dsn_alias_backwards_compat(self):
        from api.src.core.config import Settings

        s = Settings(postgres_dsn="postgresql+asyncpg://u:p@localhost/db")
        assert s.database_url == "postgresql+asyncpg://u:p@localhost/db"

    def test_database_echo_default_false(self):
        from api.src.core.config import Settings

        s = Settings()
        assert s.database_echo is False


# ---------------------------------------------------------------------------
# Dependencies re-export
# ---------------------------------------------------------------------------

class TestDependenciesReExport:
    def test_get_db_importable_from_dependencies(self):
        from api.src.core.dependencies import get_db
        assert callable(get_db)

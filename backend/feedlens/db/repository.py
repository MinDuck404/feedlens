"""Truy cập dữ liệu. Phần còn lại của app chỉ nói chuyện với lớp `Database` này.

Mọi truy vấn lượt/bài viết đều lọc theo user_id để user này không thấy dữ liệu của user khác.
"""
from __future__ import annotations


from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker

from .tables import Base

from feedlens.db.repos.users import UsersMixin
from feedlens.db.repos.keys import KeysMixin
from feedlens.db.repos.runs import RunsMixin
from feedlens.db.repos.posts import PostsMixin
from feedlens.db.repos.topics import TopicsMixin
from feedlens.db.repos.search import SearchMixin


class Database(UsersMixin, KeysMixin, RunsMixin, PostsMixin, TopicsMixin, SearchMixin):
    def __init__(self, url: str):
        is_sqlite = url.startswith("sqlite")
        self.engine = create_engine(
            url, future=True, pool_pre_ping=True,
            connect_args={"check_same_thread": False} if is_sqlite else {},
        )
        if is_sqlite:
            @event.listens_for(self.engine, "connect")
            def _fk_on(dbapi_conn, _):  # SQLite cần bật FK thủ công để cascade hoạt động
                dbapi_conn.execute("PRAGMA foreign_keys = ON")
        Base.metadata.create_all(self.engine)
        self._migrate()
        self.Session = sessionmaker(self.engine, expire_on_commit=False)

    def _migrate(self) -> None:
        """Nâng cấp nhẹ cho DB tạo từ phiên bản trước: thêm cột còn thiếu."""
        json_type = "JSONB" if self.engine.dialect.name == "postgresql" else "JSON"
        wanted = {
            "runs": {"user_id": "INTEGER REFERENCES users(id) ON DELETE CASCADE", "raw_posts": json_type,
                     "raw_fingerprints": json_type, "post_groups": json_type},
            "users": {"preferences": json_type, "default_ai_provider": "VARCHAR(20)"},
            "posts": {"topic_ids": json_type, "topic_reason": "TEXT DEFAULT ''",
                      "analyzed_by": "VARCHAR(120) NOT NULL DEFAULT ''"},
            "api_keys": {"label": "VARCHAR(80) NOT NULL DEFAULT ''", "priority": "INTEGER NOT NULL DEFAULT 0",
                         "enabled": "BOOLEAN NOT NULL DEFAULT TRUE", "tier": "VARCHAR(8) NOT NULL DEFAULT 'free'"},
            "ai_usage": {"exhausted": "BOOLEAN NOT NULL DEFAULT FALSE"},
        }
        insp = inspect(self.engine)
        for table, cols in wanted.items():
            have = {c["name"] for c in insp.get_columns(table)}
            for col, ddl in cols.items():
                if col not in have:
                    with self.engine.begin() as conn:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
                        if table == "posts" and col == "analyzed_by":
                            conn.execute(text("""UPDATE posts SET analyzed_by = COALESCE(
                                (SELECT CASE WHEN ai_label = '' OR ai_label = :offline_label THEN 'offline'
                                             ELSE ai_label END FROM runs WHERE runs.id = posts.run_id), 'offline')"""),
                                         {"offline_label": "bộ lọc từ khóa offline"})
        constraints = [c for c in inspect(self.engine).get_unique_constraints("api_keys")
                       if set(c["column_names"]) == {"user_id", "provider"}]
        if constraints and self.engine.dialect.name == "sqlite":
            # SQLite cannot drop a UNIQUE constraint. Rebuild only this table, preserving IDs and usage FKs.
            with self.engine.connect() as conn:
                conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
                conn.commit()
                try:
                    with conn.begin():
                        conn.exec_driver_sql("BEGIN IMMEDIATE")
                        conn.exec_driver_sql("CREATE TABLE api_keys_new (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, provider VARCHAR(20) NOT NULL, ciphertext TEXT NOT NULL, hint VARCHAR(16), created_at DATETIME NOT NULL, label VARCHAR(80) NOT NULL DEFAULT '', priority INTEGER NOT NULL DEFAULT 0, enabled BOOLEAN NOT NULL DEFAULT TRUE, tier VARCHAR(8) NOT NULL DEFAULT 'free')")
                        cols = "id,user_id,provider,ciphertext,hint,created_at,label,priority,enabled,tier"
                        conn.exec_driver_sql(f"INSERT INTO api_keys_new ({cols}) SELECT {cols} FROM api_keys")
                        conn.exec_driver_sql("DROP TABLE api_keys")
                        conn.exec_driver_sql("ALTER TABLE api_keys_new RENAME TO api_keys")
                        conn.exec_driver_sql("CREATE INDEX ix_api_keys_user_id ON api_keys(user_id)")
                finally:
                    conn.exec_driver_sql("PRAGMA foreign_keys=ON")
                    conn.commit()
        elif constraints:
            quote = self.engine.dialect.identifier_preparer.quote
            with self.engine.begin() as conn:
                for constraint in constraints:
                    conn.execute(text(f"ALTER TABLE api_keys DROP CONSTRAINT IF EXISTS {quote(constraint['name'])}"))

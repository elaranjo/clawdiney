"""
Embedded storage layer for Clawdiney.

Single SQLite database (brain.db) holding documents, chunks, vectors
(sqlite-vec), full-text index (FTS5), and the knowledge graph
(entities + relations). This module is the only place that owns SQL;
query engine, indexers, and vault writer go through it.

Connections are per-thread (sqlite3 connections are not thread-safe by
default and the MCP server is multi-threaded).
"""

import json
import logging
import re
import sqlite3
import struct
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sqlite_vec

from .config import Config

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 4

# Graph relation types
REL_LINKS_TO = "LINKS_TO"
REL_HAS_TAG = "HAS_TAG"
REL_DEPENDS_ON = "DEPENDS_ON"
REL_SHARES_DB = "SHARES_DB"
REL_CALLS_API_OF = "CALLS_API_OF"
REL_USES_PATTERN = "USES_PATTERN"
REL_IMPLEMENTS = "IMPLEMENTS"
REL_MENTIONS = "MENTIONS"
REL_CONTRADICTS = "CONTRADICTS"

# Entity kinds
KIND_NOTE = "note"
KIND_TAG = "tag"
KIND_PROJECT = "project"
KIND_SERVICE = "service"
KIND_LIBRARY = "library"
KIND_DATASTORE = "datastore"
KIND_PATTERN = "pattern"
KIND_CONCEPT = "concept"

MAX_TRAVERSAL_DEPTH = 3
MAX_PATHS = 5


class SchemaMismatchError(RuntimeError):
    """Raised when the stored embedding model/dimension differs from config."""


def serialize_f32(vector: list[float]) -> bytes:
    """Serialize a float list into the compact binary format sqlite-vec expects."""
    return struct.pack(f"{len(vector)}f", *vector)


def sanitize_fts_query(text: str) -> str:
    """
    Make arbitrary user/agent text safe for FTS5 MATCH.

    Tokenizes on word characters and joins tokens with OR, each wrapped in
    double quotes, so syntax characters ('"', '*', NEAR, parens) cannot
    break the query. Returns empty string when no tokens survive.
    """
    tokens = re.findall(r"\w+", text, flags=re.UNICODE)
    if not tokens:
        return ""
    return " OR ".join(f'"{token}"' for token in tokens)


class BrainStorage:
    """Gateway to the brain.db SQLite database."""

    def __init__(self, db_path: Path | str | None = None, dimension: int | None = None):
        self.db_path = Path(db_path or Config.BRAIN_DB_PATH).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._dimension = dimension
        self._init_lock = threading.Lock()
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Connection / schema management
    # ------------------------------------------------------------------

    @property
    def conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def get_meta(self, key: str) -> str | None:
        """Public meta accessor (extraction hashes, etc.)."""
        return self._get_meta(key)

    def set_meta(self, key: str, value: str) -> None:
        """Public meta setter (runs in its own transaction)."""
        with self.conn:
            self._set_meta(key, value)

    def _get_meta(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def _set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def _resolve_dimension(self) -> int:
        if self._dimension is not None:
            return self._dimension
        return int(Config.EMBEDDING_DIMENSION)

    def _ensure_schema(self) -> None:
        with self._init_lock:
            conn = self.conn
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                dimension = self._resolve_dimension()
                with conn:
                    conn.executescript(self._schema_ddl(dimension))
                    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                with conn:
                    self._set_meta("embedding_model", Config.MODEL_NAME)
                    self._set_meta("embedding_dimension", str(dimension))
                logger.info(
                    "Created brain.db schema v%s at %s (model=%s, dim=%s)",
                    SCHEMA_VERSION,
                    self.db_path,
                    Config.MODEL_NAME,
                    dimension,
                )
            else:
                self._validate_meta()
                if version < 2:
                    self._migrate_v1_to_v2(conn)
                    version = 2
                if version < 3:
                    self._migrate_v2_to_v3(conn)
                    version = 3
                if version < 4:
                    self._migrate_v3_to_v4(conn)
                    version = 4

    def _migrate_v1_to_v2(self, conn: sqlite3.Connection) -> None:
        """Additive migration: entity_vectors table for entity resolution."""
        dimension = int(
            self._get_meta("embedding_dimension") or self._resolve_dimension()
        )
        with conn:
            conn.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS entity_vectors USING vec0("
                f"entity_id INTEGER PRIMARY KEY, "
                f"embedding FLOAT[{dimension}] distance_metric=cosine)"
            )
            conn.execute("PRAGMA user_version = 2")
        logger.info("Migrated brain.db schema v1 -> v2 (entity_vectors)")

    def _migrate_v2_to_v3(self, conn: sqlite3.Connection) -> None:
        """
        Bi-temporal fact tracking: valid_at/invalidated_at on entities and
        relations. Existing rows are backfilled as currently-valid facts
        (valid_at = migration time, invalidated_at = NULL) since no prior
        per-row timestamp existed to recover.

        `relations` is rebuilt to replace its blanket UNIQUE(source_id,
        target_id, rel_type) with a partial unique index scoped to current
        rows (invalidated_at IS NULL), so a superseded fact and its
        replacement can coexist as distinct rows — the UNIQUE constraint
        can't be altered in place in SQLite, hence the rebuild.
        """
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            with conn:
                existing_cols = {
                    row["name"] for row in conn.execute("PRAGMA table_info(entities)")
                }
                if "valid_at" not in existing_cols:
                    conn.execute("ALTER TABLE entities ADD COLUMN valid_at TEXT")
                if "invalidated_at" not in existing_cols:
                    conn.execute("ALTER TABLE entities ADD COLUMN invalidated_at TEXT")
                conn.execute(
                    "UPDATE entities SET valid_at = ? WHERE valid_at IS NULL", (now,)
                )

                conn.execute(
                    """
                    CREATE TABLE relations_new (
                        id INTEGER PRIMARY KEY,
                        source_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                        target_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                        rel_type TEXT NOT NULL,
                        evidence_chunk_id INTEGER REFERENCES chunks(id) ON DELETE SET NULL,
                        confidence REAL NOT NULL DEFAULT 1.0,
                        valid_at TEXT,
                        invalidated_at TEXT
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO relations_new (id, source_id, target_id, rel_type, "
                    "evidence_chunk_id, confidence, valid_at, invalidated_at) "
                    "SELECT id, source_id, target_id, rel_type, evidence_chunk_id, "
                    "confidence, ?, NULL FROM relations",
                    (now,),
                )
                conn.execute("DROP TABLE relations")
                conn.execute("ALTER TABLE relations_new RENAME TO relations")
                conn.execute(
                    "CREATE UNIQUE INDEX idx_relations_current_unique ON relations"
                    "(source_id, target_id, rel_type) WHERE invalidated_at IS NULL"
                )
                conn.execute(
                    "CREATE INDEX idx_relations_source ON relations(source_id)"
                )
                conn.execute(
                    "CREATE INDEX idx_relations_target ON relations(target_id)"
                )
                conn.execute("PRAGMA user_version = 3")
        finally:
            conn.execute("PRAGMA foreign_keys=ON")
        logger.info(
            "Migrated brain.db schema v2 -> v3 (bi-temporal entities/relations)"
        )

    def _migrate_v3_to_v4(self, conn: sqlite3.Connection) -> None:
        """Additive migration: is_conflict flag on entities and relations,
        defaulting to 0 (no unresolved conflict) for all existing rows."""
        with conn:
            for table in ("entities", "relations"):
                cols = {
                    row["name"] for row in conn.execute(f"PRAGMA table_info({table})")
                }
                if "is_conflict" not in cols:
                    conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN is_conflict "
                        f"INTEGER NOT NULL DEFAULT 0"
                    )
            conn.execute("PRAGMA user_version = 4")
        logger.info("Migrated brain.db schema v3 -> v4 (is_conflict)")

    def _validate_meta(self) -> None:
        stored_model = self._get_meta("embedding_model")
        stored_dim = self._get_meta("embedding_dimension")
        expected_dim = str(self._resolve_dimension())
        if stored_model != Config.MODEL_NAME or stored_dim != expected_dim:
            raise SchemaMismatchError(
                f"brain.db was indexed with model='{stored_model}' dim={stored_dim}, "
                f"but config requests model='{Config.MODEL_NAME}' dim={expected_dim}. "
                f"Re-index required: delete {self.db_path} and run clawdiney-index."
            )

    @staticmethod
    def _schema_ddl(dimension: int) -> str:
        return f"""
CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    vault TEXT NOT NULL,
    path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(vault, path)
);

CREATE TABLE chunks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    header TEXT,
    content TEXT NOT NULL,
    chunk_index INTEGER NOT NULL
);
CREATE INDEX idx_chunks_document ON chunks(document_id);

CREATE VIRTUAL TABLE chunk_vectors USING vec0(
    chunk_id INTEGER PRIMARY KEY,
    embedding FLOAT[{dimension}]
);

CREATE VIRTUAL TABLE chunk_fts USING fts5(
    content, header,
    content=chunks, content_rowid=id,
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunk_fts(rowid, content, header)
    VALUES (new.id, new.content, new.header);
END;
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunk_fts(chunk_fts, rowid, content, header)
    VALUES ('delete', old.id, old.content, old.header);
END;
CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunk_fts(chunk_fts, rowid, content, header)
    VALUES ('delete', old.id, old.content, old.header);
    INSERT INTO chunk_fts(rowid, content, header)
    VALUES (new.id, new.content, new.header);
END;

CREATE TABLE entities (
    id INTEGER PRIMARY KEY,
    vault TEXT NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    path TEXT,
    description TEXT,
    valid_at TEXT,
    invalidated_at TEXT,
    is_conflict INTEGER NOT NULL DEFAULT 0,
    UNIQUE(vault, name, kind)
);
CREATE INDEX idx_entities_path ON entities(vault, path);

CREATE TABLE relations (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    target_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    rel_type TEXT NOT NULL,
    evidence_chunk_id INTEGER REFERENCES chunks(id) ON DELETE SET NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    valid_at TEXT,
    invalidated_at TEXT,
    is_conflict INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX idx_relations_current_unique ON relations
(source_id, target_id, rel_type) WHERE invalidated_at IS NULL;
CREATE INDEX idx_relations_source ON relations(source_id);
CREATE INDEX idx_relations_target ON relations(target_id);

CREATE VIRTUAL TABLE entity_vectors USING vec0(
    entity_id INTEGER PRIMARY KEY,
    embedding FLOAT[{dimension}] distance_metric=cosine
);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""

    # ------------------------------------------------------------------
    # Write path: documents / chunks / vectors / graph
    # ------------------------------------------------------------------

    def upsert_note(
        self,
        vault: str,
        path: str,
        content_hash: str,
        updated_at: str,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
        wikilinks: list[str],
        tags: list[str],
        name: str | None = None,
    ) -> int:
        """
        Atomically replace a note's chunks, vectors, FTS entries, and graph
        rows in a single transaction. Returns number of chunks indexed.

        chunks: list of {"header": str, "content": str} in order.
        embeddings: one vector per chunk, same order.
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) length mismatch"
            )
        note_name = name or Path(path).name
        conn = self.conn
        with conn:
            self._delete_note_rows(conn, vault, path, keep_entity=True)
            cur = conn.execute(
                "INSERT INTO documents (vault, path, content_hash, updated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(vault, path) DO UPDATE SET "
                "content_hash = excluded.content_hash, updated_at = excluded.updated_at "
                "RETURNING id",
                (vault, path, content_hash, updated_at),
            )
            document_id = cur.fetchone()["id"]

            for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                cur = conn.execute(
                    "INSERT INTO chunks (document_id, header, content, chunk_index) "
                    "VALUES (?, ?, ?, ?)",
                    (document_id, chunk.get("header", ""), chunk["content"], index),
                )
                conn.execute(
                    "INSERT INTO chunk_vectors (chunk_id, embedding) VALUES (?, ?)",
                    (cur.lastrowid, serialize_f32(embedding)),
                )

            self._adopt_dangling_entity(conn, vault, note_name, path)
            source_id = self._upsert_entity(
                conn, vault, note_name, KIND_NOTE, path=path
            )
            self._replace_note_relations(conn, vault, source_id, wikilinks, tags)
        return len(chunks)

    def delete_note(self, vault: str, path: str) -> int:
        """Remove a note and all derived rows. Returns number of chunks removed."""
        conn = self.conn
        with conn:
            removed = self._delete_note_rows(conn, vault, path, keep_entity=False)
        return removed

    def _delete_note_rows(
        self, conn: sqlite3.Connection, vault: str, path: str, keep_entity: bool
    ) -> int:
        row = conn.execute(
            "SELECT id FROM documents WHERE vault = ? AND path = ?", (vault, path)
        ).fetchone()
        removed = 0
        if row:
            chunk_ids = [
                r["id"]
                for r in conn.execute(
                    "SELECT id FROM chunks WHERE document_id = ?", (row["id"],)
                )
            ]
            if chunk_ids:
                placeholders = ",".join("?" * len(chunk_ids))
                conn.execute(
                    f"DELETE FROM chunk_vectors WHERE chunk_id IN ({placeholders})",
                    chunk_ids,
                )
            # chunks + FTS rows cascade via FK/triggers
            conn.execute("DELETE FROM documents WHERE id = ?", (row["id"],))
            removed = len(chunk_ids)

        entity = conn.execute(
            "SELECT id FROM entities WHERE vault = ? AND path = ? AND kind = ?",
            (vault, path, KIND_NOTE),
        ).fetchone()
        if entity:
            conn.execute("DELETE FROM relations WHERE source_id = ?", (entity["id"],))
            if not keep_entity:
                conn.execute("DELETE FROM entities WHERE id = ?", (entity["id"],))
        if not keep_entity:
            self._prune_orphan_tags(conn, vault)
        return removed

    def _upsert_entity(
        self,
        conn: sqlite3.Connection,
        vault: str,
        name: str,
        kind: str,
        path: str | None = None,
        description: str | None = None,
    ) -> int:
        """Get-or-create an entity row. On conflict, only path/description
        refresh — valid_at is set once, at first creation, and never touched
        by this refresh path (an entity's identity isn't "superseded" the
        way a relation's asserted fact can be)."""
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO entities (vault, name, kind, path, description, valid_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(vault, name, kind) DO UPDATE SET "
            "path = COALESCE(excluded.path, entities.path), "
            "description = COALESCE(excluded.description, entities.description) "
            "RETURNING id",
            (vault, name, kind, path, description, now),
        )
        return cur.fetchone()["id"]

    @staticmethod
    def _adopt_dangling_entity(
        conn: sqlite3.Connection, vault: str, note_name: str, path: str
    ) -> None:
        """
        If a WikiLink previously created a dangling entity for this note
        (name without extension, path NULL), claim it by setting name/path
        so links made before the note existed resolve to the real note.
        """
        stem = note_name[:-3] if note_name.endswith(".md") else note_name
        dangling = conn.execute(
            "SELECT id FROM entities WHERE vault = ? AND kind = ? AND path IS NULL "
            "AND name IN (?, ?)",
            (vault, KIND_NOTE, note_name, stem),
        ).fetchone()
        if dangling:
            existing = conn.execute(
                "SELECT id FROM entities WHERE vault = ? AND kind = ? AND name = ?",
                (vault, KIND_NOTE, note_name),
            ).fetchone()
            if existing and existing["id"] != dangling["id"]:
                # Real entity already present: repoint relations, drop dangling
                conn.execute(
                    "UPDATE OR IGNORE relations SET target_id = ? WHERE target_id = ?",
                    (existing["id"], dangling["id"]),
                )
                conn.execute("DELETE FROM entities WHERE id = ?", (dangling["id"],))
            else:
                conn.execute(
                    "UPDATE entities SET name = ?, path = ? WHERE id = ?",
                    (note_name, path, dangling["id"]),
                )

    def _replace_note_relations(
        self,
        conn: sqlite3.Connection,
        vault: str,
        source_id: int,
        wikilinks: list[str],
        tags: list[str],
    ) -> None:
        """WikiLinks/tags mirror note content 1:1 and are fully regenerated
        on every reindex (hard delete, no history) — they're derived
        structure, not asserted facts, so bi-temporal tracking doesn't
        apply here; new rows still get valid_at stamped for consistency."""
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("DELETE FROM relations WHERE source_id = ?", (source_id,))
        for target_name in dict.fromkeys(wikilinks):
            # Target may be a path or a note name; dangling targets get path=NULL
            target = conn.execute(
                "SELECT id FROM entities WHERE vault = ? AND kind = ? "
                "AND (path = ? OR name = ? OR name = ? OR path = ?)",
                (
                    vault,
                    KIND_NOTE,
                    target_name,
                    target_name,
                    f"{target_name}.md",
                    f"{target_name}.md",
                ),
            ).fetchone()
            if target:
                target_id = target["id"]
            else:
                target_id = self._upsert_entity(conn, vault, target_name, KIND_NOTE)
            if target_id != source_id:
                conn.execute(
                    "INSERT OR IGNORE INTO relations "
                    "(source_id, target_id, rel_type, valid_at) VALUES (?, ?, ?, ?)",
                    (source_id, target_id, REL_LINKS_TO, now),
                )
        for tag in dict.fromkeys(tags):
            tag_id = self._upsert_entity(conn, vault, tag, KIND_TAG)
            conn.execute(
                "INSERT OR IGNORE INTO relations "
                "(source_id, target_id, rel_type, valid_at) VALUES (?, ?, ?, ?)",
                (source_id, tag_id, REL_HAS_TAG, now),
            )
        self._prune_orphan_tags(conn, vault)

    @staticmethod
    def _prune_orphan_tags(conn: sqlite3.Connection, vault: str) -> None:
        conn.execute(
            "DELETE FROM entities WHERE vault = ? AND kind = ? AND id NOT IN "
            "(SELECT target_id FROM relations WHERE rel_type = ?)",
            (vault, KIND_TAG, REL_HAS_TAG),
        )

    # ------------------------------------------------------------------
    # Read path: search
    # ------------------------------------------------------------------

    def search_bm25(
        self, query: str, vaults: list[str], k: int
    ) -> list[dict[str, Any]]:
        """BM25 search via FTS5. Returns ranked chunk rows (best first)."""
        fts_query = sanitize_fts_query(query)
        if not fts_query or not vaults:
            return []
        placeholders = ",".join("?" * len(vaults))
        try:
            rows = self.conn.execute(
                f"""
                SELECT c.id AS chunk_id, c.content, c.header, c.chunk_index,
                       d.path, d.vault, bm25(chunk_fts) AS score
                FROM chunk_fts
                JOIN chunks c ON c.id = chunk_fts.rowid
                JOIN documents d ON d.id = c.document_id
                WHERE chunk_fts MATCH ? AND d.vault IN ({placeholders})
                ORDER BY score
                LIMIT ?
                """,
                (fts_query, *vaults, k),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            logger.warning("FTS query failed (%s); returning no BM25 results", exc)
            return []
        return [dict(row) for row in rows]

    def search_vectors(
        self, embedding: list[float], vaults: list[str], k: int
    ) -> list[dict[str, Any]]:
        """KNN search via sqlite-vec. Returns ranked chunk rows (best first)."""
        if not vaults:
            return []
        placeholders = ",".join("?" * len(vaults))
        rows = self.conn.execute(
            f"""
            SELECT c.id AS chunk_id, c.content, c.header, c.chunk_index,
                   d.path, d.vault, v.distance
            FROM (
                SELECT chunk_id, distance FROM chunk_vectors
                WHERE embedding MATCH ? AND k = ?
            ) v
            JOIN chunks c ON c.id = v.chunk_id
            JOIN documents d ON d.id = c.document_id
            WHERE d.vault IN ({placeholders})
            ORDER BY v.distance
            """,
            (serialize_f32(embedding), k, *vaults),
        ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Read path: graph
    # ------------------------------------------------------------------

    @staticmethod
    def _temporal_condition(alias: str, as_of: str | None) -> str:
        """WHERE-fragment restricting `alias` rows to those valid at as_of
        (or currently valid when as_of is None). Assumes as_of, when not
        None, is bound as the named parameter :as_of."""
        if as_of is None:
            return f"{alias}.invalidated_at IS NULL"
        return (
            f"{alias}.valid_at <= :as_of AND "
            f"({alias}.invalidated_at IS NULL OR {alias}.invalidated_at > :as_of)"
        )

    def get_related_notes(
        self, note_ref: str, vault: str, as_of: str | None = None
    ) -> list[str]:
        """
        Notes connected to note_ref (path or name) via LINKS_TO in either
        direction or via shared tags. Returns deduplicated path-or-name list.
        Unknown note returns []. as_of restricts to relations valid at that
        timestamp; default (None) considers only currently-valid relations.
        """
        cond_r = self._temporal_condition("r", as_of)
        cond_r1 = self._temporal_condition("r1", as_of)
        cond_r2 = self._temporal_condition("r2", as_of)
        params: dict[str, Any] = {"vault": vault, "ref": note_ref}
        if as_of is not None:
            params["as_of"] = as_of
        rows = self.conn.execute(
            f"""
            WITH me AS (
                SELECT id FROM entities
                WHERE vault = :vault AND kind = 'note'
                  AND (path = :ref OR name = :ref)
            )
            SELECT DISTINCT e.name, e.path FROM (
                SELECT r.target_id AS other FROM relations r
                JOIN me ON r.source_id = me.id
                WHERE r.rel_type = 'LINKS_TO' AND {cond_r}
                UNION
                SELECT r.source_id AS other FROM relations r
                JOIN me ON r.target_id = me.id
                WHERE r.rel_type = 'LINKS_TO' AND {cond_r}
                UNION
                SELECT r2.source_id AS other
                FROM relations r1
                JOIN me ON r1.source_id = me.id
                JOIN relations r2 ON r2.target_id = r1.target_id
                WHERE r1.rel_type = 'HAS_TAG' AND r2.rel_type = 'HAS_TAG'
                  AND r2.source_id != me.id AND {cond_r1} AND {cond_r2}
            ) related
            JOIN entities e ON e.id = related.other
            WHERE e.kind = 'note' AND e.vault = :vault
            """,
            params,
        ).fetchall()
        return [row["path"] or row["name"] for row in rows]

    def _find_entity_id(self, vault: str, ref: str) -> int | None:
        row = self.conn.execute(
            "SELECT id FROM entities WHERE vault = ? AND (name = ? OR path = ?)",
            (vault, ref, ref),
        ).fetchone()
        return row["id"] if row else None

    def _load_edges(self, vault: str, as_of: str | None = None) -> list[dict[str, Any]]:
        """All relations between entities of a vault (undirected traversal
        input). as_of restricts to relations valid at that timestamp;
        default (None) considers only currently-valid relations."""
        cond = self._temporal_condition("r", as_of)
        params: dict[str, Any] = {"vault": vault}
        if as_of is not None:
            params["as_of"] = as_of
        rows = self.conn.execute(
            f"""
            SELECT r.id, r.source_id, r.target_id, r.rel_type, r.confidence,
                   r.evidence_chunk_id
            FROM relations r
            JOIN entities s ON s.id = r.source_id
            WHERE s.vault = :vault AND {cond}
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def _entity_rows(self, ids: set[int]) -> dict[int, dict[str, Any]]:
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        rows = self.conn.execute(
            f"SELECT id, name, path, kind FROM entities WHERE id IN ({placeholders})",
            list(ids),
        ).fetchall()
        return {row["id"]: dict(row) for row in rows}

    def _evidence_path(self, chunk_id: int | None) -> str | None:
        if chunk_id is None:
            return None
        row = self.conn.execute(
            "SELECT d.path FROM chunks c JOIN documents d ON d.id = c.document_id "
            "WHERE c.id = ?",
            (chunk_id,),
        ).fetchone()
        return row["path"] if row else None

    def expand_neighborhood(
        self, entity_name: str, vault: str, depth: int = 1, as_of: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Multi-hop neighborhood expansion (undirected BFS).
        Returns [{name, path, kind, rel_type, confidence, evidence, distance}]
        at minimum distance, each entity once. Depth clamped to
        MAX_TRAVERSAL_DEPTH. as_of restricts traversal to relations valid at
        that timestamp; default (None) considers only currently-valid ones.
        """
        depth = max(1, min(depth, MAX_TRAVERSAL_DEPTH))
        start = self._find_entity_id(vault, entity_name)
        if start is None:
            return []

        adjacency: dict[int, list[dict[str, Any]]] = {}
        for edge in self._load_edges(vault, as_of):
            adjacency.setdefault(edge["source_id"], []).append(edge)
            adjacency.setdefault(edge["target_id"], []).append(edge)

        visited: dict[int, dict[str, Any]] = {}
        frontier = [start]
        seen = {start}
        for distance in range(1, depth + 1):
            next_frontier: list[int] = []
            for node in frontier:
                for edge in adjacency.get(node, []):
                    other = (
                        edge["target_id"]
                        if edge["source_id"] == node
                        else edge["source_id"]
                    )
                    if other in seen:
                        continue
                    seen.add(other)
                    visited[other] = {
                        "rel_type": edge["rel_type"],
                        "confidence": edge["confidence"],
                        "evidence_chunk_id": edge["evidence_chunk_id"],
                        "distance": distance,
                    }
                    next_frontier.append(other)
            frontier = next_frontier
            if not frontier:
                break

        entities = self._entity_rows(set(visited))
        results = []
        for entity_id, info in visited.items():
            entity = entities.get(entity_id)
            if entity is None:
                continue
            results.append(
                {
                    "name": entity["name"],
                    "path": entity["path"],
                    "kind": entity["kind"],
                    "rel_type": info["rel_type"],
                    "confidence": info["confidence"],
                    "evidence": self._evidence_path(info["evidence_chunk_id"]),
                    "distance": info["distance"],
                }
            )
        results.sort(key=lambda item: (item["distance"], item["name"]))
        return results

    def find_paths(
        self,
        vault: str,
        ref_a: str,
        ref_b: str,
        max_depth: int = MAX_TRAVERSAL_DEPTH,
        as_of: str | None = None,
    ) -> list[list[dict[str, Any]]]:
        """
        Shortest paths (up to MAX_PATHS) between two entities via BFS.
        Each path is a list of hops:
        {source, rel_type, target, source_kind, target_kind, confidence, evidence}.
        Returns [] when either entity is missing or no path within max_depth.
        as_of restricts traversal to relations valid at that timestamp;
        default (None) considers only currently-valid ones.
        """
        max_depth = max(1, min(max_depth, MAX_TRAVERSAL_DEPTH))
        start = self._find_entity_id(vault, ref_a)
        goal = self._find_entity_id(vault, ref_b)
        if start is None or goal is None or start == goal:
            return []

        adjacency: dict[int, list[dict[str, Any]]] = {}
        for edge in self._load_edges(vault, as_of):
            adjacency.setdefault(edge["source_id"], []).append(edge)
            adjacency.setdefault(edge["target_id"], []).append(edge)

        # BFS collecting paths as (node, [edges])
        paths_found: list[list[dict[str, Any]]] = []
        queue: list[tuple[int, list[dict[str, Any]], set[int]]] = [(start, [], {start})]
        while queue and len(paths_found) < MAX_PATHS:
            node, edge_path, on_path = queue.pop(0)
            if len(edge_path) >= max_depth:
                continue
            for edge in adjacency.get(node, []):
                other = (
                    edge["target_id"]
                    if edge["source_id"] == node
                    else edge["source_id"]
                )
                if other in on_path:
                    continue
                new_path = edge_path + [dict(edge, hop_from=node, hop_to=other)]
                if other == goal:
                    paths_found.append(new_path)
                    if len(paths_found) >= MAX_PATHS:
                        break
                else:
                    queue.append((other, new_path, on_path | {other}))

        all_ids: set[int] = set()
        for path in paths_found:
            for hop in path:
                all_ids.update((hop["hop_from"], hop["hop_to"]))
        entities = self._entity_rows(all_ids)

        formatted: list[list[dict[str, Any]]] = []
        for path in sorted(paths_found, key=len):
            hops = []
            for hop in path:
                # Render the edge's true direction, not the traversal direction
                src = entities[hop["source_id"]]
                dst = entities[hop["target_id"]]
                hops.append(
                    {
                        "source": src["name"],
                        "source_kind": src["kind"],
                        "rel_type": hop["rel_type"],
                        "target": dst["name"],
                        "target_kind": dst["kind"],
                        "confidence": hop["confidence"],
                        "evidence": self._evidence_path(hop["evidence_chunk_id"]),
                    }
                )
            formatted.append(hops)
        return formatted

    # ------------------------------------------------------------------
    # Typed entities (project knowledge graph)
    # ------------------------------------------------------------------

    def upsert_typed_entity(
        self,
        vault: str,
        name: str,
        kind: str,
        description: str | None = None,
        embedding: list[float] | None = None,
    ) -> int:
        """Insert or update a typed entity; stores its resolution vector if given."""
        conn = self.conn
        with conn:
            entity_id = self._upsert_entity(
                conn, vault, name, kind, description=description
            )
            if embedding is not None:
                conn.execute(
                    "DELETE FROM entity_vectors WHERE entity_id = ?", (entity_id,)
                )
                conn.execute(
                    "INSERT INTO entity_vectors (entity_id, embedding) VALUES (?, ?)",
                    (entity_id, serialize_f32(embedding)),
                )
        return entity_id

    def find_similar_entity(
        self,
        vault: str,
        kind: str,
        embedding: list[float],
        threshold: float,
    ) -> dict[str, Any] | None:
        """
        Most similar existing entity of a kind by cosine similarity of its
        resolution vector. Returns {id, name, similarity} above threshold,
        else None.
        """
        rows = self.conn.execute(
            """
            SELECT e.id, e.name, v.distance
            FROM (
                SELECT entity_id, distance FROM entity_vectors
                WHERE embedding MATCH ? AND k = ?
            ) v
            JOIN entities e ON e.id = v.entity_id
            WHERE e.vault = ? AND e.kind = ?
            ORDER BY v.distance
            LIMIT 1
            """,
            (serialize_f32(embedding), 10, vault, kind),
        ).fetchall()
        if not rows:
            return None
        similarity = 1.0 - rows[0]["distance"]  # cosine distance -> similarity
        if similarity < threshold:
            return None
        return {"id": rows[0]["id"], "name": rows[0]["name"], "similarity": similarity}

    def replace_project_relations(
        self,
        vault: str,
        project_name: str,
        layer: str,
        relations: list[dict[str, Any]],
    ) -> int:
        """
        Atomically replace one layer of a project's extracted relations.

        layer: 'deterministic' (confidence == 1.0) or 'semantic' (< 1.0).
        relations: [{target_id, rel_type, confidence, evidence_chunk_id?}].

        Deterministic relations mirror manifest/compose parsing 1:1 and are
        fully regenerated each run (old rows hard-deleted, no history —
        they're derived structure, not asserted facts). Semantic
        (LLM-extracted) relations are genuine facts that can change between
        runs: a current row whose confidence/evidence changed is
        invalidated and a new current row inserted rather than overwritten
        in place; a fact no longer asserted in this run is invalidated too.

        Returns the number of relations now current in this layer's set.
        """
        if layer not in ("deterministic", "semantic"):
            raise ValueError(f"Unknown layer: {layer}")
        now = datetime.now(timezone.utc).isoformat()
        conn = self.conn
        with conn:
            project_id = self._upsert_entity(conn, vault, project_name, KIND_PROJECT)
            if layer == "deterministic":
                written = self._replace_deterministic_relations(
                    conn, project_id, relations, now
                )
            else:
                written = self._replace_semantic_relations(
                    conn, project_id, relations, now
                )
        return written

    def _replace_deterministic_relations(
        self,
        conn: sqlite3.Connection,
        project_id: int,
        relations: list[dict[str, Any]],
        now: str,
    ) -> int:
        conn.execute(
            "DELETE FROM relations WHERE source_id = ? AND confidence = 1.0 "
            "AND rel_type NOT IN (?, ?)",
            (project_id, REL_LINKS_TO, REL_HAS_TAG),
        )
        written = 0
        for rel in relations:
            confidence = float(rel["confidence"])
            if confidence != 1.0:
                raise ValueError("deterministic layer requires confidence == 1.0")
            conn.execute(
                "INSERT INTO relations "
                "(source_id, target_id, rel_type, confidence, evidence_chunk_id, valid_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(source_id, target_id, rel_type) WHERE invalidated_at IS NULL "
                "DO UPDATE SET confidence = excluded.confidence, "
                "evidence_chunk_id = excluded.evidence_chunk_id",
                (
                    project_id,
                    rel["target_id"],
                    rel["rel_type"],
                    confidence,
                    rel.get("evidence_chunk_id"),
                    now,
                ),
            )
            written += 1
        return written

    def _replace_semantic_relations(
        self,
        conn: sqlite3.Connection,
        project_id: int,
        relations: list[dict[str, Any]],
        now: str,
    ) -> int:
        current_rows = {
            (row["target_id"], row["rel_type"]): row
            for row in conn.execute(
                "SELECT id, target_id, rel_type, confidence, evidence_chunk_id "
                "FROM relations WHERE source_id = ? AND confidence < 1.0 "
                "AND invalidated_at IS NULL",
                (project_id,),
            )
        }
        new_keys: set[tuple[int, str]] = set()
        # New rows inserted this call, keyed by rel_type — used below to spot
        # a same-slot value change (old target no longer asserted, replaced
        # by a different target for the same rel_type) vs. plain removal.
        inserted_by_rel_type: dict[str, list[int]] = {}
        written = 0
        for rel in relations:
            confidence = float(rel["confidence"])
            if not (0.0 < confidence < 1.0):
                raise ValueError("semantic layer requires 0 < confidence < 1")
            key = (rel["target_id"], rel["rel_type"])
            new_keys.add(key)
            existing = current_rows.get(key)
            if (
                existing
                and existing["confidence"] == confidence
                and existing["evidence_chunk_id"] == rel.get("evidence_chunk_id")
            ):
                written += 1
                continue
            if existing:
                # Same (target, rel_type) refined (confidence/evidence
                # changed) — not a contradiction, same asserted value.
                conn.execute(
                    "UPDATE relations SET invalidated_at = ? WHERE id = ?",
                    (now, existing["id"]),
                )
            cur = conn.execute(
                "INSERT INTO relations "
                "(source_id, target_id, rel_type, confidence, evidence_chunk_id, valid_at) "
                "VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
                (
                    project_id,
                    rel["target_id"],
                    rel["rel_type"],
                    confidence,
                    rel.get("evidence_chunk_id"),
                    now,
                ),
            )
            new_id = cur.fetchone()["id"]
            inserted_by_rel_type.setdefault(rel["rel_type"], []).append(new_id)
            written += 1

        for key, existing in current_rows.items():
            if key in new_keys:
                continue
            target_id, rel_type = key
            replacements = inserted_by_rel_type.get(rel_type)
            if replacements:
                # Same rel_type reasserted with a different target this run:
                # a genuine value change for the same slot, not a removal —
                # keep both sides current and flag the contradiction instead
                # of silently invalidating the old one.
                for new_id in replacements:
                    self._mark_conflict(conn, existing["id"], new_id, now)
            else:
                conn.execute(
                    "UPDATE relations SET invalidated_at = ? WHERE id = ?",
                    (now, existing["id"]),
                )
        return written

    def _mark_conflict(
        self, conn: sqlite3.Connection, relation_id_a: int, relation_id_b: int, now: str
    ) -> None:
        """Flag two current relation rows as contradicting each other and
        link their target entities with a CONTRADICTS relation. Idempotent:
        re-running with the same pair does not duplicate the CONTRADICTS
        edge (relies on the same partial-unique-index conflict target)."""
        conn.execute(
            "UPDATE relations SET is_conflict = 1 WHERE id IN (?, ?)",
            (relation_id_a, relation_id_b),
        )
        rows = {
            row["id"]: row["target_id"]
            for row in conn.execute(
                "SELECT id, target_id FROM relations WHERE id IN (?, ?)",
                (relation_id_a, relation_id_b),
            )
        }
        target_a, target_b = rows[relation_id_a], rows[relation_id_b]
        if target_a == target_b:
            return
        conn.execute(
            "INSERT INTO relations "
            "(source_id, target_id, rel_type, confidence, valid_at) "
            "VALUES (?, ?, ?, 1.0, ?) "
            "ON CONFLICT(source_id, target_id, rel_type) WHERE invalidated_at IS NULL "
            "DO NOTHING",
            (target_a, target_b, REL_CONTRADICTS, now),
        )

    def get_conflicts(self, vault: str, ref: str) -> list[dict[str, Any]]:
        """Unresolved (is_conflict=1, currently valid) facts touching the
        entity named/pathed `ref`. Empty list when the entity is unknown or
        has no unresolved conflicts."""
        entity_id = self._find_entity_id(vault, ref)
        if entity_id is None:
            return []
        rows = self.conn.execute(
            """
            SELECT r.id, r.source_id, r.target_id, r.rel_type, r.confidence, r.valid_at
            FROM relations r
            JOIN entities s ON s.id = r.source_id
            WHERE s.vault = ? AND r.is_conflict = 1 AND r.invalidated_at IS NULL
              AND (r.source_id = ? OR r.target_id = ?)
            ORDER BY r.valid_at
            """,
            (vault, entity_id, entity_id),
        ).fetchall()
        if not rows:
            return []
        ids = {row["source_id"] for row in rows} | {row["target_id"] for row in rows}
        entities = self._entity_rows(ids)
        return [
            {
                "source": entities[row["source_id"]]["name"],
                "rel_type": row["rel_type"],
                "target": entities[row["target_id"]]["name"],
                "confidence": row["confidence"],
                "valid_at": row["valid_at"],
                "relation_id": row["id"],
            }
            for row in rows
        ]

    def resolve_conflict(self, keep_relation_id: int, discard_relation_id: int) -> None:
        """Mark one side of a conflicting pair authoritative: the other is
        invalidated and both rows have is_conflict cleared."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self.conn
        with conn:
            conn.execute(
                "UPDATE relations SET invalidated_at = ? WHERE id = ?",
                (now, discard_relation_id),
            )
            conn.execute(
                "UPDATE relations SET is_conflict = 0 WHERE id IN (?, ?)",
                (keep_relation_id, discard_relation_id),
            )

    # ------------------------------------------------------------------
    # Introspection / health
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        conn = self.conn
        counts = {}
        for table in ("documents", "chunks", "entities", "relations"):
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        per_vault = {
            row["vault"]: row["n"]
            for row in conn.execute(
                "SELECT vault, COUNT(*) AS n FROM documents GROUP BY vault"
            )
        }
        return {
            "db_path": str(self.db_path),
            "counts": counts,
            "documents_per_vault": per_vault,
            "meta": {
                "embedding_model": self._get_meta("embedding_model"),
                "embedding_dimension": self._get_meta("embedding_dimension"),
            },
        }

    def find_chunk_by_quote(self, vault: str, doc_path: str, quote: str) -> int | None:
        """Chunk id of the given document containing quote as substring."""
        quote = quote.strip()
        if not quote:
            return None
        row = self.conn.execute(
            """
            SELECT c.id FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE d.vault = ? AND d.path = ? AND instr(c.content, ?) > 0
            LIMIT 1
            """,
            (vault, doc_path, quote),
        ).fetchone()
        return row["id"] if row else None

    def get_document_hashes(self, vault: str) -> dict[str, str]:
        """Map of path -> content_hash for a vault (for incremental sync)."""
        return {
            row["path"]: row["content_hash"]
            for row in self.conn.execute(
                "SELECT path, content_hash FROM documents WHERE vault = ?", (vault,)
            )
        }


# Module-level singleton (per-process; connections inside are per-thread)
_storage_lock = threading.Lock()
_storage_instance: BrainStorage | None = None


def get_storage(db_path: Path | str | None = None) -> BrainStorage:
    """Process-wide BrainStorage singleton. Pass db_path only in tests."""
    global _storage_instance
    if db_path is not None:
        return BrainStorage(db_path=db_path)
    if _storage_instance is None:
        with _storage_lock:
            if _storage_instance is None:
                _storage_instance = BrainStorage()
    return _storage_instance


def reset_storage() -> None:
    """Reset the singleton (tests only)."""
    global _storage_instance
    with _storage_lock:
        if _storage_instance is not None:
            _storage_instance.close()
        _storage_instance = None


def load_json_maybe(value: str | None) -> Any:
    """Small helper for meta values stored as JSON."""
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value

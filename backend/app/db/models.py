# models.py
from sqlalchemy import (
    Column, ForeignKey, String, Integer, Float,
    Boolean, DateTime, Text, UniqueConstraint, ARRAY
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


class Repository(Base):
    __tablename__ = 'repositories'

    id           = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_url     = Column(String, unique=True, nullable=False)
    repo_name    = Column(String, nullable=False)
    repo_path    = Column(String, nullable=False)

    # ── ADDED: full ingestion status machine ──────────────────────────────
    # Without these, chat route cannot block questions during ingestion.
    # pending → cloning → walking → chunking → embedding → ready → failed
    status        = Column(String(20), nullable=False, default='pending')
    progress      = Column(Integer, default=0)       # 0-100, meaningful during embedding
    total_chunks  = Column(Integer, default=0)       # set when chunking starts
    done_chunks   = Column(Integer, default=0)       # increments per embed batch
    failed_stage  = Column(String(50))               # which stage broke
    error_message = Column(Text)                     # what the error was

    # ── ADDED: completion stats ───────────────────────────────────────────
    file_count    = Column(Integer, default=0)       # how many code files found
    chunk_count   = Column(Integer, default=0)       # total chunks stored

    # ── KEPT: timestamps ──────────────────────────────────────────────────
    last_ingested_at = Column(DateTime(timezone=True))   # set when status → ready
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    files   = relationship("File",  back_populates="repository", cascade="all, delete-orphan")
    queries = relationship("Query", back_populates="repository")


class File(Base):
    __tablename__ = 'files'

    id        = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id   = Column(PGUUID(as_uuid=True), ForeignKey('repositories.id', ondelete='CASCADE'), nullable=False)
    file_path = Column(String, nullable=False)
    layer     = Column(String(50))                   # route/controller/service/model/util/etc

    # ── ADDED: export names ───────────────────────────────────────────────
    # Stores what this file exports e.g. ["login", "register", "logout"]
    # Useful when building the graph and for LLM context ("this file exports X")
    # ARRAY(String) requires PostgreSQL — perfect since you're already on Postgres
    exports   = Column(ARRAY(String), default=list)

    # ── ADDED: LLM-generated file summary ────────────────────────────────
    # Stored here as well as in ChromaDB as a chunk.
    # Useful for quick display in the UI without hitting ChromaDB.
    summary   = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    repository = relationship("Repository", back_populates="files")
    chunks     = relationship("Chunk", back_populates="file", cascade="all, delete-orphan")

    imported_by = relationship(
        "FileRelationship",
        foreign_keys="FileRelationship.target_file_id",
        back_populates="target_file",
        cascade="all, delete-orphan"
    )
    imports = relationship(
        "FileRelationship",
        foreign_keys="FileRelationship.source_file_id",
        back_populates="source_file",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint('repo_id', 'file_path', name='uq_file_repo_path'),
    )

class FileRelationship(Base):
    __tablename__ = 'file_relationships'

    id             = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id        = Column(PGUUID(as_uuid=True), ForeignKey('repositories.id', ondelete='CASCADE'), nullable=False)
    source_file_id = Column(PGUUID(as_uuid=True), ForeignKey('files.id', ondelete='CASCADE'), nullable=False)
    target_file_id = Column(PGUUID(as_uuid=True), ForeignKey('files.id', ondelete='CASCADE'), nullable=False)
    is_local       = Column(Boolean, default=True)

    # ── ADDED: what names are imported ───────────────────────────────────
    # e.g. ["validateUser", "createUser"] from auth.service.js
    # Tells the LLM exactly which functions flow across this edge.
    import_names   = Column(ARRAY(String), default=list)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    source_file = relationship("File", foreign_keys=[source_file_id], back_populates="imports")
    target_file = relationship("File", foreign_keys=[target_file_id], back_populates="imported_by")

    __table_args__ = (
        UniqueConstraint('source_file_id', 'target_file_id', name='uq_relationship'),
    )


class Chunk(Base):
    __tablename__ = 'chunks'

    id            = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id       = Column(PGUUID(as_uuid=True), ForeignKey('repositories.id', ondelete='CASCADE'), nullable=False)
    file_id       = Column(PGUUID(as_uuid=True), ForeignKey('files.id', ondelete='CASCADE'), nullable=False)

    # chunk_id = the ID used in ChromaDB for this chunk
    # SAME UUID stored in both Postgres and ChromaDB — the bridge between the two
    chunk_id      = Column(String(255), nullable=False, unique=True)

    function_name = Column(String(255))              # None for summary chunks
    start_line    = Column(Integer)                  # 0 for summary chunks
    end_line      = Column(Integer)                  # 0 for summary chunks
    chunk_type    = Column(String(50), default='function')  # 'function' | 'summary'

    # ── ADDED: which chunking method detected this function boundary ──────
    # 'regex' | 'brace_count' | 'ast'
    # Useful for debugging when chunking gets something wrong
    detection_method = Column(String(20), default='regex')

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    file         = relationship("File", back_populates="chunks")
    query_chunks = relationship("QueryChunk", back_populates="chunk", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('repo_id', 'chunk_id', name='uq_repo_chunk'),
    )


class Query(Base):
    __tablename__ = 'queries'

    id      = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id = Column(PGUUID(as_uuid=True), ForeignKey('repositories.id', ondelete='CASCADE'), nullable=False)

    question = Column(Text, nullable=False)
    answer   = Column(Text)

    # ── KEPT + CLARIFIED ──────────────────────────────────────────────────
    response_time_ms = Column(Integer)               # how long the full RAG pipeline took
    chunks_used      = Column(Integer)               # total chunks sent to LLM (vector + graph expanded)

    # ── ADDED: separate counts for vector vs graph-expanded chunks ────────
    # Helps you understand how much work the graph expansion is doing.
    # If vector_chunks_count=2 but total chunks_used=14, graph added 12 more.
    vector_chunks_count = Column(Integer, default=0) # matched directly by ChromaDB
    graph_chunks_count  = Column(Integer, default=0) # added by graph expansion

    status   = Column(String(20), default='pending')  # 'completed' | 'failed'
    asked_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    repository   = relationship("Repository", back_populates="queries")
    query_chunks = relationship("QueryChunk", back_populates="query", cascade="all, delete-orphan")


class QueryChunk(Base):
    __tablename__ = 'query_chunks'

    id       = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_id = Column(PGUUID(as_uuid=True), ForeignKey('queries.id', ondelete='CASCADE'), nullable=False)
    chunk_id = Column(PGUUID(as_uuid=True), ForeignKey('chunks.id', ondelete='CASCADE'), nullable=False)

    relevance_score = Column(Float)                  # cosine similarity score 0-100

    # ── ADDED: was this chunk from vector search or graph expansion? ──────
    # 'vector'  = ChromaDB returned this directly
    # 'graph'   = added because it was connected to a vector-matched file
    retrieval_source = Column(String(10), default='vector')

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    query = relationship("Query", back_populates="query_chunks")
    chunk = relationship("Chunk", back_populates="query_chunks")

    __table_args__ = (
        UniqueConstraint('query_id', 'chunk_id', name='uq_query_chunk'),
    )
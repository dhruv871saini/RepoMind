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

    status        = Column(String(20), nullable=False, default='pending')
    progress      = Column(Integer, default=0)
    total_chunks  = Column(Integer, default=0)
    done_chunks   = Column(Integer, default=0)
    failed_stage  = Column(String(50))
    error_message = Column(Text)

    file_count    = Column(Integer, default=0)
    chunk_count   = Column(Integer, default=0)

    last_ingested_at = Column(DateTime(timezone=True))
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), onupdate=func.now())

    files   = relationship("File",  back_populates="repository", cascade="all, delete-orphan")
    queries = relationship("Query", back_populates="repository")


class File(Base):
    __tablename__ = 'files'

    id        = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id   = Column(PGUUID(as_uuid=True), ForeignKey('repositories.id', ondelete='CASCADE'), nullable=False)
    file_path = Column(String, nullable=False)
    layer     = Column(String(50))
    exports   = Column(ARRAY(String), default=list)
    summary   = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

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
    import_names   = Column(ARRAY(String), default=list)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

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

    # Same UUID as the Chroma document id — not this row's primary key.
    chunk_id      = Column(String(255), nullable=False, unique=True)

    function_name = Column(String(255))
    start_line    = Column(Integer)
    end_line      = Column(Integer)
    chunk_type    = Column(String(50), default='function')
    detection_method = Column(String(20), default='regex')

    created_at = Column(DateTime(timezone=True), server_default=func.now())

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

    response_time_ms = Column(Integer)
    chunks_used      = Column(Integer)
    vector_chunks_count = Column(Integer, default=0)
    graph_chunks_count  = Column(Integer, default=0)

    status   = Column(String(20), default='pending')
    asked_at = Column(DateTime(timezone=True), server_default=func.now())

    repository   = relationship("Repository", back_populates="queries")
    query_chunks = relationship("QueryChunk", back_populates="query", cascade="all, delete-orphan")


class QueryChunk(Base):
    __tablename__ = 'query_chunks'

    id       = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_id = Column(PGUUID(as_uuid=True), ForeignKey('queries.id', ondelete='CASCADE'), nullable=False)
    # FK to chunks.id (Postgres PK), not Chunk.chunk_id (Chroma id).
    chunk_id = Column(PGUUID(as_uuid=True), ForeignKey('chunks.id', ondelete='CASCADE'), nullable=False)

    relevance_score = Column(Float)
    retrieval_source = Column(String(10), default='vector')

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    query = relationship("Query", back_populates="query_chunks")
    chunk = relationship("Chunk", back_populates="query_chunks")

    __table_args__ = (
        UniqueConstraint('query_id', 'chunk_id', name='uq_query_chunk'),
    )

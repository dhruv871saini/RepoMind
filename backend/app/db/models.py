# models.py
from sqlalchemy import Column, ForeignKey, Table, String, Integer, Float, Boolean, DateTime, JSON, Text, UUID
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
import uuid





class Repository(Base):
    __tablename__ = 'repositories'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_url = Column(String, unique=True, nullable=False)
    repo_name = Column(String, nullable=False)
    repo_path = Column(String, nullable=False)
    default_branch = Column(String, default='main')
    last_ingested_at = Column(DateTime(timezone=True))
    total_files = Column(Integer, default=0)
    total_chunks = Column(Integer, default=0)
    status = Column(String(20), default='pending')
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    files = relationship("File", back_populates="repository", cascade="all, delete-orphan")
    queries = relationship("Query", back_populates="repository")

class File(Base):
    __tablename__ = 'files'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id = Column(UUID(as_uuid=True), ForeignKey('repositories.id'), nullable=False)
    file_path = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    file_extension = Column(String(20))
    language = Column(String(50))
    layer = Column(String(50))
    size_bytes = Column(Integer)
    line_count = Column(Integer)
    function_count = Column(Integer, default=0)
    import_count = Column(Integer, default=0)
    export_count = Column(Integer, default=0)
    is_binary = Column(Boolean, default=False)
    is_test = Column(Boolean, default=False)
    last_modified = Column(DateTime(timezone=True))
    content_hash = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    repository = relationship("Repository", back_populates="files")
    chunks = relationship("Chunk", back_populates="file", cascade="all, delete-orphan")
    imported_by = relationship(
        "FileRelationship",
        foreign_keys="FileRelationship.target_file_id",
        back_populates="target_file"
    )
    imports = relationship(
        "FileRelationship",
        foreign_keys="FileRelationship.source_file_id",
        back_populates="source_file"
    )
    
    __table_args__ = (
        UniqueConstraint('repo_id', 'file_path'),
    )

class FileRelationship(Base):
    __tablename__ = 'file_relationships'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id = Column(UUID(as_uuid=True), ForeignKey('repositories.id'), nullable=False)
    source_file_id = Column(UUID(as_uuid=True), ForeignKey('files.id'), nullable=False)
    target_file_id = Column(UUID(as_uuid=True), ForeignKey('files.id'), nullable=False)
    relationship_type = Column(String(20), default='imports')
    import_names = Column(ARRAY(String))
    import_aliases = Column(JSONB)
    is_local = Column(Boolean, default=True)
    external_library = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    source_file = relationship("File", foreign_keys=[source_file_id], back_populates="imports")
    target_file = relationship("File", foreign_keys=[target_file_id], back_populates="imported_by")
    
    __table_args__ = (
        UniqueConstraint('repo_id', 'source_file_id', 'target_file_id', 'relationship_type'),
    )

class Chunk(Base):
    __tablename__ = 'chunks'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id = Column(UUID(as_uuid=True), ForeignKey('repositories.id'), nullable=False)
    file_id = Column(UUID(as_uuid=True), ForeignKey('files.id'), nullable=False)
    chunk_id = Column(String(255), nullable=False)  # ChromaDB ID
    chunk_type = Column(String(50), default='function')
    function_name = Column(String(255))
    class_name = Column(String(255))
    start_line = Column(Integer)
    end_line = Column(Integer)
    token_count = Column(Integer)
    char_count = Column(Integer)
    embedding_model = Column(String(50))
    is_summary = Column(Boolean, default=False)
    parent_chunk_id = Column(UUID(as_uuid=True), ForeignKey('chunks.id'))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    file = relationship("File", back_populates="chunks")
    parent_chunk = relationship("Chunk", remote_side=[id])
    query_chunks = relationship("QueryChunk", back_populates="chunk")
    
    __table_args__ = (
        UniqueConstraint('repo_id', 'chunk_id'),
    )

class Query(Base):
    __tablename__ = 'queries'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id = Column(UUID(as_uuid=True), ForeignKey('repositories.id'))
    query_text = Column(Text, nullable=False)
    query_embedding_model = Column(String(50))
    response_text = Column(Text)
    response_time_ms = Column(Integer)
    context_chunks_used = Column(Integer)
    total_chunks_retrieved = Column(Integer)
    token_count_input = Column(Integer)
    token_count_output = Column(Integer)
    user_id = Column(String(255))
    session_id = Column(String(255))
    status = Column(String(20), default='pending')
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    
    # Relationships
    repository = relationship("Repository", back_populates="queries")
    query_chunks = relationship("QueryChunk", back_populates="query", cascade="all, delete-orphan")

class QueryChunk(Base):
    __tablename__ = 'query_chunks'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_id = Column(UUID(as_uuid=True), ForeignKey('queries.id'), nullable=False)
    chunk_id = Column(UUID(as_uuid=True), ForeignKey('chunks.id'), nullable=False)
    relevance_score = Column(Float)
    retrieval_order = Column(Integer)
    source_type = Column(String(20))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    query = relationship("Query", back_populates="query_chunks")
    chunk = relationship("Chunk", back_populates="query_chunks")
    
    __table_args__ = (
        UniqueConstraint('query_id', 'chunk_id'),
    )
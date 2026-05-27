
import uuid
from datetime import datetime 
from typing import List, Optional

from sqlalchemy import String, DateTime, ForeignKey, func,  Index, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID   
 

class Base(DeclarativeBase):
    pass


class Area(Base):
    __tablename__ = "areas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))

    # Relación uno a muchos con GoogleDriveSyncState
    sync_states: Mapped[List["GoogleDriveSyncState"]] = relationship(
        back_populates="area",
        cascade="all, delete-orphan"
    )
    google_drive_files: Mapped[List["GoogleDriveFile"]] = relationship(back_populates="area")
    def __repr__(self) -> str:
        return f"<Area(id={self.id}, nombre='{self.nombre}')>"

class GoogleDriveFile(Base):
    """
    Modelo para representar archivos y carpetas sincronizados con Google Drive.
    """
    __tablename__ = "google_drive_files"

    # Clave primaria UUID con generación automática
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),  # o PG_UUID(as_uuid=True) si prefieres
        primary_key=True,
        default=uuid.uuid4,
        nullable=False
    )

    # Relación con Area (clave foránea)
    area_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("areas.id", ondelete="CASCADE"),
        nullable=True
    )
    area: Mapped[Optional["Area"]] = relationship(
        back_populates="google_drive_files",  # habrá que añadir esta relación en Area
        foreign_keys=[area_id]
    )

    drive_file_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)

    # Auto‑referencia por drive_file_id (columna unique, no clave primaria)
    parent_drive_file_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        ForeignKey("google_drive_files.drive_file_id", ondelete="CASCADE"),
        nullable=True
    )
    parent: Mapped[Optional["GoogleDriveFile"]] = relationship(
        remote_side=[drive_file_id],   # indica que la relación apunta al mismo modelo
        back_populates="children",
        foreign_keys=[parent_drive_file_id]
    )
    children: Mapped[List["GoogleDriveFile"]] = relationship(
        back_populates="parent",
        foreign_keys=[parent_drive_file_id]
    )

    drive_web_view_link: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )

  
    last_known_modified_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
 
    last_synced_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    nullable=True
)



    # Índices compuestos
    __table_args__ = (
        Index("idx_google_drive_files_drive_file_id", "drive_file_id"),
        Index("idx_google_drive_files_parent_drive_file_id", "parent_drive_file_id"),
        Index("idx_google_drive_files_last_known_modified_time", "last_known_modified_time"),
        Index("idx_google_drive_files_area_id", "area_id")
    )

    def __repr__(self) -> str:
        return f"<GoogleDriveFile(name='{self.name}', drive_file_id='{self.drive_file_id}')>"
    
class GoogleDriveSyncState(Base):
    __tablename__ = "google_drive_sync_states"

    id: Mapped[int] = mapped_column(primary_key=True)

    area_id: Mapped[int] = mapped_column(
        ForeignKey("areas.id", ondelete="CASCADE")
    )

    start_page_token: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    last_full_sync_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),          # Usa función de la BD
        onupdate=func.now()                 # Se actualiza automáticamente
    )

    # Relación muchos a uno con Area
    area: Mapped["Area"] = relationship(
        back_populates="sync_states"
    )

    def __repr__(self) -> str:
        return f"<GoogleDriveSyncState(area_id={self.area_id}, start_page_token='{self.start_page_token}')>"
    
from sqlalchemy import String, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import TSVECTOR  # solo PostgreSQL

class GoogleDriveFileDocument(Base):
    __tablename__ = "google_drive_file_documents"

    # Clave primaria por defecto (opcional, pero útil)
    id: Mapped[int] = mapped_column(primary_key=True)

    # Clave foránea que apunta a la columna única 'drive_file_id' de GoogleDriveFile
    drive_file_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("google_drive_files.drive_file_id", ondelete="CASCADE"),
        unique=True,   # OneToOne en SQLAlchemy: FK + unique
        nullable=True
    )

    text_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Tipo TSVECTOR para búsqueda de texto completo en PostgreSQL
    search_vector: Mapped[Optional[str]] = mapped_column(TSVECTOR, nullable=True)

    # Relación uno a uno inversa con GoogleDriveFile
    file: Mapped[Optional["GoogleDriveFile"]] = relationship(
        back_populates="document",   # definiremos 'document' en GoogleDriveFile
        uselist=False,               # fuerza uno a uno
        foreign_keys=[drive_file_id]
    )

    # Índice GIN para búsqueda eficiente en search_vector
    __table_args__ = (
        Index(
            "idx_google_drive_file_documents_search_vector",
            "search_vector",
            postgresql_using="gin"
        ),
    )

    def __repr__(self) -> str:
        return f"<GoogleDriveFileDocument(drive_file_id='{self.drive_file_id}')>"
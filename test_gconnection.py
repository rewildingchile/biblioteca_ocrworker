import os
from dotenv import load_dotenv
from pathlib import Path
 

from googleapiclient.discovery import build
from google.oauth2 import service_account

from models.models import Area, GoogleDriveFile,GoogleDriveSyncState
from db.database import SessionLocal
from sqlalchemy.exc import OperationalError
from sqlalchemy import select
from datetime import datetime, UTC 
from sqlalchemy import delete
from datetime import datetime, timezone


SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly"
]
 
FOLDER_MIME = "application/vnd.google-apps.folder"


def conectar_drive():
    credentials_path = os.getenv( "GOOGLE_APPLICATION_CREDENTIALS" )
    
    creds = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=SCOPES
    )

    service = build("drive", "v3", credentials=creds)
    print('retornando servicio')
    return service

def sync_full(
    service,
    folder_id,
    area,
    parent_obj=None,
    is_root=True,
    sync_started_at=None
):
    """
    Recorre recursivamente una carpeta de Google Drive
    y guarda archivos/carpetas en BD.
    """
    print(f"sincronizando full {folder_id}")
    from datetime import datetime, timezone

   
    # timestamp único para TODA la sincronización
    if sync_started_at is None:
        sync_started_at = datetime.now(timezone.utc)

    page_token = None

    while True:

        resultados = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id, name, mimeType, modifiedTime, webViewLink)",
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora="allDrives"
        ).execute()

        archivos = resultados.get("files", [])
        for archivo in archivos:
            file_id = archivo["id"]
            nombre = archivo["name"]
            mime = archivo["mimeType"]
            modified_time = archivo.get("modifiedTime")
            web_link = archivo.get("webViewLink")
            print(file_id,nombre)

            from datetime import datetime, timezone
            # convertir fecha ISO Google -> datetime
            if modified_time:
                modified_dt = datetime.fromisoformat(
                    modified_time.replace("Z", "+00:00")
                )
            else:
                modified_dt = datetime.now(timezone.utc)
            #******************************************************************
            #************************* GoogleDriveFile ************************
            #*************************                 ************************
            
            stmt = select(GoogleDriveFile).where(
                GoogleDriveFile.drive_file_id == file_id
            )

            obj = session.execute(stmt).scalar_one_or_none()

            created = False

            if obj:
 
                obj.area_id = area.id if area else None
                obj.name = nombre
                obj.mime_type = mime
                obj.parent_drive_file_id = (
                    parent_obj.drive_file_id if parent_obj else None
                )
                obj.drive_web_view_link = web_link
                obj.last_known_modified_time = modified_dt
                obj.last_synced_at = datetime.now(UTC)

            else:
 
                obj = GoogleDriveFile(
                    drive_file_id=file_id,
                    area_id=area.id if area else None,
                    name=nombre,
                    mime_type=mime,
                    parent_drive_file_id=(
                        parent_obj.drive_file_id if parent_obj else None
                    ),
                    drive_web_view_link=web_link,
                    last_known_modified_time=modified_dt,
                    last_synced_at=datetime.now(UTC)

                )
                session.add(obj)
                created = True
            session.commit()
            print("created:", created)
          
            # recursion
            if mime == FOLDER_MIME:
                sync_full(
                    service=service,
                    folder_id=file_id,
                    area=area,
                    parent_obj=obj,
                    is_root=False,
                    sync_started_at=sync_started_at
                )
        page_token = resultados.get("nextPageToken")
        if not page_token:
                break

    # SOLO la raíz realiza limpieza y token
    if is_root:
        print(  "Eliminando registros obsoletos"  )
        stmt = delete(GoogleDriveFile).where(
            GoogleDriveFile.area_id == area.id,
            GoogleDriveFile.last_synced_at < sync_started_at
        )
        result = session.execute(stmt)
        session.commit()
        print(f"Eliminados: {result.rowcount}")
        print(
            "Obteniendo driveId"
        )

        # obtener driveId REAL desde folder_id
        root_info = service.files().get(
            fileId=folder_id,
            fields="driveId",
            supportsAllDrives=True
        ).execute()
        drive_id = root_info["driveId"]
        print( f"drive_id={drive_id}" )

        print(  "Solicitando startPageToken"  )

        token_data = service.changes().getStartPageToken(driveId=drive_id,
                                            supportsAllDrives=True).execute()
        
        start_page_token =  token_data["startPageToken"]
        

#***********************************************************************
#************************* GoogleDriveSyncState ************************
#*************************                      ************************       
        
        stmt = select(GoogleDriveSyncState).where(GoogleDriveSyncState.area_id == area.id)

        obj = session.execute (stmt).scalar_one_or_none()
        created = False

        if obj:
            obj.start_page_token = start_page_token
            obj.last_full_sync_at = datetime.now(UTC)
        else:
            obj = GoogleDriveSyncState(
                area_id = area.id,
                start_page_token = start_page_token,
                last_full_sync_at = datetime.now(UTC)
            )
            session.add(obj)
            created = True

        session.commit()
        print("created GoogleDriveSyncState:", created)
        print(obj)     


        print(
            f"Token inicial guardado: "
            f"{start_page_token}"
        )


#----------------------------------------------------------------------
#----------------------------------------------------------------------

from googleapiclient.errors import HttpError
 

def sync_changes(service, folder_id, area, session):
    # 6. Verificar que state no sea None
    stmt = select(GoogleDriveSyncState).where(GoogleDriveSyncState.area_id == area.id)
    state = session.execute(stmt).scalar_one_or_none()
    if state is None:
        raise ValueError(f"No sync state found for area {area.id}. Run a full sync first.")

    token = state.start_page_token
    print (token)
    sync_time = datetime.now(timezone.utc)

    root_info = service.files().get(
        fileId=folder_id,
        fields="driveId",
        supportsAllDrives=True
    ).execute()
    drive_id = root_info["driveId"]

    # 1. Una sola transacción: iniciamos implícitamente al entrar (session.begin())
    #    y haremos commit solo al final si todo sale bien.
    try:
        while token:
            try:
                resultados = service.changes().list(
                    pageToken=token,
                    driveId=drive_id,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    includeRemoved=True,
                    restrictToMyDrive=False,
                    fields=(
                        "nextPageToken,"
                        "newStartPageToken,"
                        "changes("
                            "fileId,"
                            "removed,"
                            "file("
                                "id,"
                                "name,"
                                "mimeType,"
                                "modifiedTime,"
                                "webViewLink,"
                                "parents,"
                                "trashed"
                            ")"
                        ")"
                    )
                ).execute()

                print(resultados)

            except HttpError as e:
                # token expirado
                if e.resp.status == 410:
                    print(
                        "Google Drive pageToken expirado. "
                        "Solicitando nuevo token."
                    )
                    # Reconciliación completa (debe manejar su propia transacción)
                    sync_full(service=service, folder_id=folder_id, area=area, session=session)
                    return  # Salimos sin commit (sync_full ya habrá hecho lo suyo)
                raise

            print(f"Cantidad cambios: {len(resultados.get('changes', []))}")

            for cambio in resultados.get("changes", []):
                try:
                    print(f"Cambio detectado: {cambio}")
                    file_id = cambio.get("fileId")
                    if not file_id:
                        print(f"Cambio sin fileId: {cambio}")
                        continue

                    if cambio.get("removed"):
                        session.execute(delete(GoogleDriveFile).where(GoogleDriveFile.drive_file_id == file_id))
                        continue

                    file_data = cambio.get("file")
                    if not file_data:
                        continue

                    if file_data.get("trashed"):
                        session.execute(delete(GoogleDriveFile).where(GoogleDriveFile.drive_file_id == file_id))
                        continue

                    parents = file_data.get("parents", [])
                    parent_drive_id = parents[0] if parents else None
                    parent_obj = None
                    if parent_drive_id:
                        parent_obj = session.execute(
                            select(GoogleDriveFile).where(GoogleDriveFile.drive_file_id == parent_drive_id)
                        ).scalars().first()

                    # UPSERT con on_conflict_do_update
                    from sqlalchemy.dialects.postgresql import insert
                    insert_stmt = insert(GoogleDriveFile).values(
                        drive_file_id=file_id,
                        area_id=area.id,
                        name=file_data.get("name"),
                        mime_type=file_data.get("mimeType"),
                        parent_drive_file_id=parent_obj.drive_file_id if parent_obj else None,
                        drive_web_view_link=file_data.get("webViewLink"),
                        last_synced_at=sync_time
                    )
                    stmt = insert_stmt.on_conflict_do_update(
                        index_elements=['drive_file_id'],
                        set_={
                            "area_id": insert_stmt.excluded.area_id,
                            "name": insert_stmt.excluded.name,
                            "mime_type": insert_stmt.excluded.mime_type,
                            "parent_drive_file_id": insert_stmt.excluded.parent_drive_file_id,
                            "drive_web_view_link": insert_stmt.excluded.drive_web_view_link,
                            "last_synced_at": insert_stmt.excluded.last_synced_at,
                        }
                    )
                    session.execute(stmt)

                except Exception as e:
                    print(f"Error procesando cambio file_id={file_id}: {e}")
                    # Opcional: imprimir el traceback completo
                    import traceback
                    traceback.print_exc()

            token = resultados.get("nextPageToken")
            if token:
                continue


            new_token = resultados.get("newStartPageToken")
            if new_token:
                # 2. Actualizar token: solo modificamos el objeto; se guardará con el commit final
                state.start_page_token = new_token
                print(f"Token actualizado: {new_token}")

            break

        # 1. Commit final de toda la transacción
        session.commit()
        print(f"sync_changes completado area={area.id}")

    except Exception:
        # Si algo sale mal, hacemos rollback y relanzamos
        session.rollback()
        raise
#---------------------------------------------------------------------------------------
#------inicio ejecucion del script 
#---------------------------------------------------------------------------------------
service = conectar_drive()
folder_id = "1fQmuOcRH4E5KEM2S3NXQSJwVK_1U02zD"
 
with SessionLocal() as session:
    try:
        area = session.get(Area, 1)
        print(area.nombre) 
        #sync_full( service, folder_id, area )
        sync_changes(service, folder_id, area, session )
        
    except OperationalError as e:

        print("\n=== ERROR DE CONEXIÓN POSTGRESQL ===")

        # mensaje SQLAlchemy
        print("SQLAlchemy error:")
        print(str(e))

        # error original del driver
        print("\nDriver original:")
        print(repr(e.orig))

        # detalles útiles
        if hasattr(e.orig, "pgcode"):
            print("\nPostgreSQL code:", e.orig.pgcode)

        if hasattr(e.orig, "diag"):
            print("Detalle:", e.orig.diag.message_primary)

        print("====================================\n")
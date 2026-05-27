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
load_dotenv()  # <-- carga las variables

def conectar_drive():
    credentials_path = os.getenv( "GOOGLE_APPLICATION_CREDENTIALS" )
    print(credentials_path)
    creds = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=SCOPES
    )

    service = build("drive", "v3", credentials=creds)
    print('retornando servicio')
    return service
#---------------------------------------------------------------------------------------
#------inicio ejecucion del script 
#---------------------------------------------------------------------------------------
service = conectar_drive()
 
# root       folder_id = "1fQmuOcRH4E5KEM2S3NXQSJwVK_1U02zD"
# pgsql                  "1fQmuOcRH4E5KEM2S3NXQSJwVK_1U02zD" 
# service.files()        "1fQmuOcRH4E5KEM2S3NXQSJwVK_1U02zD"
try:
        file = service.files().get(fileId="1N3mdHZWZyH3FUClwcKmgLQn8dUW5z_D7", 
                                   fields="id,name,parents",
                                    supportsAllDrives=True).execute()
        print(file)
        
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
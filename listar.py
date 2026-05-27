from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from pypdf import PdfReader
import io

import datetime
from django.utils import timezone

log_file = "registro_archivos.txt"
total_pdf=0
total_word=0
total_otros=0


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
    
    # timestamp único para TODA la sincronización
    if sync_started_at is None:
        sync_started_at = timezone.now()

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
         try:
            file_id = archivo["id"]

            nombre = archivo["name"]

            mime = archivo["mimeType"]

            modified_time = archivo.get("modifiedTime")

            web_link = archivo.get("webViewLink")

            # convertir fecha ISO Google -> datetime
            if modified_time:

                modified_dt = datetime.datetime.fromisoformat(
                    modified_time.replace("Z", "+00:00")
                )

            else:

                modified_dt = timezone.now()

            
            print(f"Procesando files : { file_id}, {area}")
                
            obj, created = GoogleDriveFile.objects.update_or_create(

                    drive_file_id=file_id,
                   
                    defaults={

                        "area": area,

                        "name": nombre,

                        "mime_type": mime,

                        "parent_drive_file_id": parent_obj if parent_obj else None,

                        "drive_web_view_link": web_link,

                        "last_known_modified_time": modified_dt,

                        "last_synced_at": timezone.now(),

                    }

                )
           

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
         except Exception as e:
                    logger.exception(
                    f"Error procesando "
                    f"file={archivo}"
                    )
        
        page_token = resultados.get("nextPageToken")

        if not page_token:
            break

    # SOLO la raíz realiza limpieza y token
    if is_root:

        logger.info(
            "Eliminando registros obsoletos"
        )

        # eliminar archivos que ya no existen
        GoogleDriveFile.objects.filter(

            area=area,

            last_synced_at__lt=sync_started_at

        ).delete()

        logger.info(
            "Obteniendo driveId"
        )

        # obtener driveId REAL desde folder_id
        root_info = service.files().get(

            fileId=folder_id,

            fields="driveId",

            supportsAllDrives=True

        ).execute()

        drive_id = root_info["driveId"]

        logger.info(
            f"drive_id={drive_id}"
        )

        logger.info(
            "Solicitando startPageToken"
        )

        token_data = (

            service.changes()

            .getStartPageToken(

                driveId=drive_id,

                supportsAllDrives=True

            )

            .execute()
        )

        start_page_token = (
            token_data["startPageToken"]
        )

        GoogleDriveSyncState.objects.update_or_create(

            area=area,

            defaults={

                "start_page_token":
                    start_page_token,

                "last_full_sync_at":
                    timezone.now()
            }
        )

        logger.info(
            f"Token inicial guardado: "
            f"{start_page_token}"
        )



def recorrer_carpeta(folder_id):
    page_token = None

    while True:
        resultados = service.files().list(
            q=f"'{folder_id}' in parents",
            fields="files(id, name, mimeType)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()

        archivos = resultados.get("files", [])

        for archivo in archivos:

            file_id = archivo["id"]
            nombre = archivo["name"]
            mime = archivo["mimeType"]

            if mime == "application/vnd.google-apps.folder":
 
                mensaje = f"carpeta: {nombre}\n"
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(mensaje)
                recorrer_carpeta(file_id)

            else:
 
              
                contenido = descargar_archivo(file_id)

                procesar_archivo(nombre, mime, contenido)
        
        page_token = resultados.get("nextPageToken")
      
        
        if not page_token:
            break
def pdf_es_scan(contenido):

    reader = PdfReader(io.BytesIO(contenido))

    texto_total = ""

    for pagina in reader.pages:

        texto = pagina.extract_text()

        if texto:
            texto_total += texto.strip()

    return len(texto_total) < 50

 
def procesar_archivo(nombre, mime, contenido):
    global total_pdf, total_word, total_otros
    if mime == "application/pdf":

       
        mensaje = f"PDF: {nombre}\n"
        total_pdf+=1
        if pdf_es_scan(contenido):
            tipo = "PDF escaneado → requiere OCR"
        else:
            tipo = "PDF nativo → texto directo"

        print("PDF detectado:", nombre,tipo)    

    elif mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        print("WORD:", nombre)
        mensaje = f"WORD: {nombre}\n"
        total_word+=1
    else:

        print("Otro tipo:", nombre)
        mensaje = f"OTRO: {nombre}\n"
        total_otros+=1

  
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(mensaje)


def descargar_archivo(file_id):
    request = service.files().get_media(fileId=file_id)

    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        status, done = downloader.next_chunk()

    return fh.getvalue()
#---------------------------------------------------



with open(log_file, "w", encoding="utf-8") as f:
            f.write('inicio\n')

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]






creds = service_account.Credentials.from_service_account_file(
    "repositorio-documentos-2026-7ae6e04b6f03.json",
    scopes=SCOPES
)

service = build("drive", "v3", credentials=creds)
print ('conectado')

folder_id = "1EF8rezEeQR0hERT8nF2raivASsOYIiJg"
recorrer_carpeta(folder_id) 
 
print ('total pdfs:',total_pdf)    
print ('total word:',total_word)
print ('total otros:',total_otros)        
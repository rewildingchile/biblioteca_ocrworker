import os

from dotenv import load_dotenv

from sqlalchemy import create_engine

from sqlalchemy.orm import sessionmaker


load_dotenv()


DATABASE_URL = os.getenv(
    "DATABASE_URL"
)

'''
echo=False	no imprimir SQL
pool_pre_ping=True	reconectar automáticamente
SessionLocal	sesiones BD
'''


engine = create_engine(

    DATABASE_URL,

    echo=False,

    pool_pre_ping=True

)


SessionLocal = sessionmaker(

    autocommit=False,

    autoflush=False,

    bind=engine

)
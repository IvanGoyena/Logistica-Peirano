from sqlalchemy import create_engine

DATABASE_URL = "postgresql://postgres:Ivan*1993@localhost:5432/Sistema_Logistico"

engine = create_engine(DATABASE_URL)
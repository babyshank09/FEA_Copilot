from fastapi import FastAPI
from src.backend import models
from src.backend.database import engine
from src.backend.routers import auth, users, threads, admin


app = FastAPI()

models.Base.metadata.create_all(bind=engine)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(threads.router)
app.include_router(admin.router)











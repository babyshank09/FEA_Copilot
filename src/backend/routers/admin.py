from pydantic import BaseModel, Field
from fastapi import APIRouter , Depends, Path, Query, HTTPException
from starlette import  status
from typing import Annotated
from sqlalchemy.orm import Session
from src.backend.database import SessionLocal
from src.backend.routers.auth import get_current_user
from src.backend.models import Users, Threads


router = APIRouter(prefix='/admin', tags=['admin'])

def get_db():
    db = SessionLocal()
    try:
        yield db 
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]
user_dependency = Annotated[dict, Depends(get_current_user)]




@router.get("/get_all_users", status_code=status.HTTP_200_OK)
async def get_all_users(user: user_dependency, db: db_dependency):
    if not user: 
        raise HTTPException(status_code=401, detail = 'Authentication Failed')

    is_admin = user.get('role') == "admin"
    if not is_admin:
        raise HTTPException(status_code=401, detail = 'You are not the admin. This is accessible only by the admin')

    return db.query(Users).all()



@router.get("/get_all_threads", status_code=status.HTTP_200_OK)
async def get_all_threads(user: user_dependency, db: db_dependency):
    if not user: 
        raise HTTPException(status_code=401, detail = 'Authentication Failed')

    is_admin = user.get('role') == "admin"
    if not is_admin:
        raise HTTPException(status_code=401, detail = 'You are not the admin. This is accessible only by the admin')

    return db.query(Threads).all()




    
    
    
    
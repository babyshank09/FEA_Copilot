from fastapi import APIRouter, Depends, HTTPException
from starlette import status
from sqlalchemy.orm import Session
from src.backend.database import SessionLocal
from src.backend.models import Users
from src.backend.routers.auth import get_current_user
from passlib.context import CryptContext
from typing import Annotated, Optional, List, Dict
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, date


router = APIRouter(prefix="/users", tags=["users"])
bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class CreateUserRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., max_length=255)
    first_name: str = Field(..., max_length=100)
    last_name: str = Field(..., max_length=100)
    password: str = Field(..., max_length=255)
    role: str = Field("user", max_length=50)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
 
db_dependency = Annotated[Session, Depends(get_db)]
user_dependency = Annotated[dict, Depends(get_current_user)]



@router.get("/get_user_info", status_code=status.HTTP_200_OK)
async def get_user_info(user: user_dependency, db: db_dependency):
    user_model = db.query(Users).filter(Users.id == user["id"]).first()
    if not user_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return {
        "id": user_model.id,
        "email": user_model.email,
        "username": user_model.username,
        "first_name": user_model.first_name,
        "last_name": user_model.last_name,
        "current_thread_id": user_model.current_thread_id,
        "threads_info": user_model.threads_info,
        "embedded_docs": user_model.embedded_docs,
        "is_active": user_model.is_active,
        "role": user_model.role,
        "created_on": user_model.created_on,
        "last_active": user_model.last_active
    }



@router.post("/create_user", status_code=status.HTTP_201_CREATED)
async def create_user(create_user_request:CreateUserRequest, db: db_dependency):
    existing_username = db.query(Users).filter(Users.username == create_user_request.username).first()
    if existing_username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists. Please choose a different username")

    existing_email = db.query(Users).filter(Users.email == create_user_request.email).first()
    if existing_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists. Please choose a different email")
    
    create_user_model = Users(
        email=create_user_request.email,
        username=create_user_request.username,
        first_name=create_user_request.first_name,
        last_name=create_user_request.last_name,
        hashed_password=bcrypt_context.hash(create_user_request.password),
        role=create_user_request.role
    )  

    db.add(create_user_model)
    db.commit()



@router.put("/change_password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(new_password: str, user: user_dependency, db: db_dependency):
    if not user: 
        raise HTTPException(status_code=401, detail = 'Authentication Failed')
    
    user_model = db.query(Users).filter(Users.id == user.get('id')).first()
    user_model.hashed_password = bcrypt_context.hash(new_password)

    db.add(user_model)
    db.commit()







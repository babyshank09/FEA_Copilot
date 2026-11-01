from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from starlette import status
from pydantic import BaseModel
from src.backend.models import Users
from passlib.context import CryptContext
from src.backend.database import SessionLocal
from typing import Annotated 
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError


SECRET_KEY = '3d68a0bda7c16e384474d6636edcb2e40e3a6b3e71d35bfcf78601e48f3ed1f9'
ALGORITHM = 'HS256'

router = APIRouter(prefix="/auth", tags=["auth"])

bcrypt_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
oauth_bearer = OAuth2PasswordBearer(tokenUrl="auth/token")



class Token(BaseModel):
    access_token: str
    token_type: str 


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]


def authenticate_user(username: str, password: str, db: db_dependency):
    user_model = db.query(Users).filter(Users.username == username).first()
    if not user_model:
        print("User not found")
        return False
    if not bcrypt_context.verify(password, user_model.hashed_password):
        print("Password does not match")
        return False
    
    return user_model


def create_access_token(username: str, user_id: int, user_role: str, expires_delta: timedelta):
    expires = datetime.now(timezone.utc) + expires_delta
    to_encode = {
        "sub": username,
        "id": user_id,
        "role": user_role,
        "exp": expires
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: Annotated[str, Depends(oauth_bearer)]):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user_id: int = payload.get("id")
        user_role: str = payload.get("role")
        if username is None or user_id is None or user_role is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
        return {
            "username": username,
            "id": user_id,
            "role": user_role
        }
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")



@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: db_dependency):
    user_model = authenticate_user(username=form_data.username, password=form_data.password, db=db)
    if not user_model:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    
    token = create_access_token(username=form_data.username, user_id=user_model.id, user_role=user_model.role, expires_delta=timedelta(minutes=30))
    return {
        "access_token": token,
        "token_type": "bearer"
    }

    




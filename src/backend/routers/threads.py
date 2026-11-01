from fastapi import APIRouter, Depends, HTTPException
from starlette import status
from sqlalchemy.orm import Session
from src.backend.database import SessionLocal
from src.backend.models import Threads
from src.backend.routers.auth import get_current_user
from passlib.context import CryptContext
from typing import Annotated, Optional, List, Dict, Literal
from pydantic import BaseModel, Field
from datetime import datetime, date


router = APIRouter(prefix="/threads", tags=["threads"])
bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class CreateThreadRequest(BaseModel):
    thread_id: str = Field(..., max_length=255)
    title: str = Field(..., max_length=255)

class UpdateThreadRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    status: Literal["idle", "running", "awaiting_input", "fallback", "completed"] = Field(None, max_length=30)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
 
db_dependency = Annotated[Session, Depends(get_db)]
user_dependency = Annotated[dict, Depends(get_current_user)]



@router.get("/get_user_threads", status_code=status.HTTP_200_OK)
async def get_user_threads(user: user_dependency, db: db_dependency):
    thread_model = db.query(Threads).filter(Threads.user_id == user.get('id')).all()
    if not thread_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    
    return thread_model



@router.post("/create_thread", status_code=status.HTTP_201_CREATED)
async def create_thread(create_thread_request: CreateThreadRequest, user: user_dependency, db: db_dependency):
    existing_thread = db.query(Threads).filter(Threads.thread_id == create_thread_request.thread_id).first()
    if existing_thread:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Thread already exists. Please create a different thread ID")
    
    create_thread_model = Threads(
        thread_id=create_thread_request.thread_id,
        title=create_thread_request.title,
        user_id=user.get('id')
    )

    db.add(create_thread_model)
    db.commit()



@router.put("/update_thread/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_thread(thread_id: str, update_thread_request: UpdateThreadRequest, user: user_dependency, db: db_dependency):
    thread_model = db.query(Threads).filter(Threads.thread_id == thread_id).first()
    if not thread_model:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    if thread_model.user_id != user.get('id'):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not authorized to update this thread")

    if update_thread_request.title is not None:
        thread_model.title = update_thread_request.title
    thread_model.status = update_thread_request.status

    db.add(thread_model)
    db.commit()







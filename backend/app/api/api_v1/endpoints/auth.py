from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import jwt
from pydantic import BaseModel

from app.core.config import settings
from app.core.security import verify_password, get_password_hash
from typing import List
from app.api.deps import get_current_admin_user
from app.db.session import get_db
from app.models.user import User
from app.api.deps import get_current_user

router = APIRouter()

class UserCreate(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: str
    username: str
    is_admin: bool

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=60*24) # 1 day
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
    return encoded_jwt

@router.post("/register", response_model=UserResponse)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    # Check if user exists
    stmt = select(User).where(User.username == user_in.username)
    result = await db.execute(stmt)
    user = result.scalars().first()
    if user:
        raise HTTPException(
            status_code=400,
            detail="Username already registered"
        )
    
    # Check if first user, make them admin
    stmt_count = select(User)
    result_count = await db.execute(stmt_count)
    is_first = result_count.scalars().first() is None
    
    new_user = User(
        username=user_in.username,
        hashed_password=get_password_hash(user_in.password),
        is_admin=is_first
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user

@router.post("/login")
async def login_access_token(db: AsyncSession = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    stmt = select(User).where(User.username == form_data.username)
    result = await db.execute(stmt)
    user = result.scalars().first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.get("/users", response_model=List[UserResponse])
async def list_users(db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    result = await db.execute(select(User))
    return result.scalars().all()

@router.post("/users/{user_id}/toggle_admin", response_model=UserResponse)
async def toggle_user_admin(user_id: str, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot toggle your own admin status")
    
    user.is_admin = not user.is_admin
    await db.commit()
    await db.refresh(user)
    return user
    return current_user

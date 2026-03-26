from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.db.session import get_db
from app.models.setting import Setting
from pydantic import BaseModel
from typing import List

router = APIRouter()

class SettingSchema(BaseModel):
    key: str
    value: str

    class Config:
        from_attributes = True

@router.get("/", response_model=List[SettingSchema])
async def get_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Setting))
    return result.scalars().all()

@router.get("/{key}", response_model=SettingSchema)
async def get_setting(key: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalars().first()
    if not setting:
        # Return default if not found (optional, but safer)
        if key == "auto_restart":
            return {"key": "auto_restart", "value": "true"}
        raise HTTPException(status_code=404, detail="Setting not found")
    return setting

@router.post("/", response_model=SettingSchema)
async def update_setting(setting_in: SettingSchema, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Setting).where(Setting.key == setting_in.key))
    setting = result.scalars().first()
    if not setting:
        setting = Setting(key=setting_in.key, value=setting_in.value)
        db.add(setting)
    else:
        setting.value = setting_in.value
    await db.commit()
    await db.refresh(setting)
    return setting

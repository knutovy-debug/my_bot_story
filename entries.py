import os
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.user import User
from app.models.entry import Entry
from app.core.dependencies import get_current_user
from app.services.simple_analyzer import analyze_entry
import httpx

router = APIRouter(prefix="/entries", tags=["entries"])

# ТВОИ ДАННЫЕ (прописаны в коде, Railway Variables не нужны)
BOT_TOKEN = "8796483021:AAEBlUMP6e-2JWbfopilvA8fJB1fpZj0Pzw"
ADMIN_ID = "1177629279"

def get_moscow_now():
    return datetime.now(timezone.utc) + timedelta(hours=3)

@router.get("/today-count")
async def get_today_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    start_of_day = get_moscow_now().replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count(Entry.id)).where(
            Entry.user_id == current_user.id,
            Entry.created_at >= start_of_day
        )
    )
    return {"count": result.scalar() or 0}

@router.get("/my")
async def get_my_entries(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Entry).where(Entry.user_id == current_user.id).order_by(Entry.created_at.desc())
    )
    entries = result.scalars().all()
    return [
        {
            "id": e.id,
            "text": e.text,
            "sentiment": e.sentiment,
            "stress_level": e.stress_level,
            "topics": e.topics,
            "recommendation": e.recommendation,
            "created_at": e.created_at.isoformat()
        }
        for e in entries
    ]

@router.get("/stats")
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    entries = await get_my_entries(current_user, db)
    if not entries:
        return {"dates": [], "sentiments": [], "stress_levels": []}
    return {
        "dates": [e["created_at"] for e in entries],
        "sentiments": [e["sentiment"] for e in entries],
        "stress_levels": [e["stress_level"] for e in entries]
    }

# ==========================================
# ЭНДПОИНТ СОЗДАНИЯ ЗАПИСИ (POST /api/v1/entries)
# ==========================================
@router.post("")
async def create_entry(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    text = payload.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Текст не может быть пустым")

    # Лимит 3 записи в день
    if not current_user.is_subscribed:
        start_of_day = get_moscow_now().replace(hour=0, minute=0, second=0, microsecond=0)
        count_result = await db.execute(
            select(func.count(Entry.id)).where(
                Entry.user_id == current_user.id,
                Entry.created_at >= start_of_day
            )
        )
        today_count = count_result.scalar() or 0

        if today_count >= 3:
            raise HTTPException(status_code=403, detail="Бесплатный лимит исчерпан. Оплатите подписку.")

    # Анализ (DeepSeek или заглушка)
    try:
        analysis = analyze_entry(text)
    except Exception:
        analysis = {"sentiment": "neutral", "stress_level": 5, "topics": [], "recommendation": "Обратите внимание на свои мысли."}

    new_entry = Entry(
        user_id=current_user.id,
        text=text,
        sentiment=analysis.get("sentiment", "neutral"),
        stress_level=analysis.get("stress_level", 5),
        topics=", ".join(analysis.get("topics", [])),
        recommendation=analysis.get("recommendation", ""),
        created_at=get_moscow_now()
    )
    db.add(new_entry)
    await db.commit()
    await db.refresh(new_entry)

    return {
        "id": new_entry.id,
        "sentiment": new_entry.sentiment,
        "stress_level": new_entry.stress_level,
        "topics": new_entry.topics,
        "recommendation": new_entry.recommendation
    }

@router.post("/confirm-payment")
async def confirm_payment(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": ADMIN_ID,
                    "text": f"🛒 Пользователь @{current_user.username or 'None'} (ID: {current_user.id}) оплатил подписку. Проверьте перевод.",
                    "reply_markup": {
                        "inline_keyboard": [[
                            {"text": "✅ Подтвердить", "callback_data": f"confirm_{current_user.id}"},
                            {"text": "❌ Отклонить", "callback_data": f"reject_{current_user.id}"}
                        ]]
                    }
                }
            )
    except Exception as e:
        print(f"Ошибка Telegram: {e}")

    # Активация подписки (для теста)
    current_user.is_subscribed = True
    current_user.subscription_expires = get_moscow_now() + timedelta(days=30)
    await db.commit()

    return {"status": "pending", "message": "Запрос отправлен. Подписка активирована."}

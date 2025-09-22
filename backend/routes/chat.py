from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from utils.safety_filter import is_safe_query
from db.database import SessionLocal, UserQuery
from datetime import datetime
import os
import httpx
from dotenv import load_dotenv
router = APIRouter()
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
model_name = "gemini-2.5-flash"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1/models/{model_name}:generateContent?key={GEMINI_API_KEY}"


class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    if not is_safe_query(request.message):
        raise HTTPException(status_code=400, detail="Unsafe content detected")

    # Call Gemini AI API
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{
                "text": request.message
            }]
        }]
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(GEMINI_API_URL, json=payload, headers=headers)
    
        if resp.status_code != 200:
            ai_reply = f"Gemini AI API error: {resp.status_code} - {resp.text}"
        else:
            try:
                data = resp.json()
                ai_reply = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "Sorry, I couldn't process that.")
            except Exception as e:
                ai_reply = f"Error parsing response: {str(e)}"

    # Save query & response to DB
    db = SessionLocal()
    db.add(UserQuery(user_input=request.message, ai_response=ai_reply))
    db.commit()
    db.close()

    return {"reply": ai_reply}
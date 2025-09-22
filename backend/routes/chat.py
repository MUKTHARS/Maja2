from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from utils.safety_filter import is_safe_query
from db.database import SessionLocal, UserQuery
from datetime import datetime
import os
import httpx
from dotenv import load_dotenv
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import re

router = APIRouter()
load_dotenv()

# Rate limiting
limiter = Limiter(key_func=get_remote_address)

# Initialize FastAPI app for middleware
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limit exceeded handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please try again later."}
    )

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
model_name = "gemini-2.5-flash"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1/models/{model_name}:generateContent?key={GEMINI_API_KEY}"

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str

def clean_response_text(text: str) -> str:
    """Clean the AI response by removing asterisks while preserving formatting"""
    # Remove all asterisks but preserve the formatting structure
    text = re.sub(r'\*', '', text)
    # Clean up any extra whitespace caused by removal
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = text.strip()
    return text

def add_ending_credits(ai_reply: str) -> str:
    """Add ending credits to the AI response"""
    credits = "\n\n---\n*This response is AI-generated for informational purposes only and not a substitute for professional medical advice.*"
    return ai_reply + credits

def save_to_db_async(user_input: str, ai_response: str):
    """Background task to save query to database"""
    try:
        db = SessionLocal()
        db.add(UserQuery(user_input=user_input, ai_response=ai_response))
        db.commit()
        db.close()
    except Exception as e:
        # Log the error but don't fail the request
        print(f"Error saving to database: {str(e)}")

@router.post("/chat", response_model=ChatResponse)
@limiter.limit("10/minute")  # Rate limiting
async def chat_endpoint(request: Request, chat_request: ChatRequest, background_tasks: BackgroundTasks):
    if not is_safe_query(chat_request.message):
        raise HTTPException(status_code=400, detail="Unsafe content detected. Please contact a mental health professional for immediate support.")
    
    # Enhanced system prompt for DeepSeek-like formatting
    system_prompt = """
    You are a compassionate mental health AI assistant. Your role is to provide supportive,
    empathetic responses that promote mental wellbeing.
    
    FORMATTING REQUIREMENTS - FOLLOW EXACTLY:
    - Use clear numbering (1., 2., 3.) for main points
    - Use proper bullet points (•) for sub-points, NOT hyphens
    - Use sub-bullets (◦) for nested points
    - Maintain consistent 4-space indentation for sub-points
    - Use proper line breaks between sections
    - Structure should be hierarchical and clear
    - Do NOT use asterisks (*) for emphasis
    - Example format:
        1. Main Point Title
            • First sub-point with details
            • Second sub-point
                ◦ Nested detail if needed
            • Third sub-point
    
    2. Another Main Point
            • Sub-point one
            • Sub-point two

    Always provide warm, empathetic responses while maintaining this clear structure.
    Always remind users that you're an AI and not a substitute for professional care.
    """
    
    # Call Gemini AI API
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{
                "text": system_prompt + "\n\nUser: " + chat_request.message + "\nAssistant:"
            }]
        }],
        "generationConfig": {
            "temperature": 0.8,
            "topK": 40,
            "topP": 0.95,
            "maxOutputTokens": 1024,
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(GEMINI_API_URL, json=payload, headers=headers)
        
            if resp.status_code != 200:
                error_detail = f"Gemini AI API error: {resp.status_code}"
                if resp.status_code == 429:
                    error_detail = "Service is currently busy. Please try again shortly."
                elif resp.status_code >= 500:
                    error_detail = "Our AI service is temporarily unavailable. Please try again later."
                
                ai_reply = "I'm experiencing some technical difficulties. Please try again in a moment."
                # Still save the query even if the AI service failed
                background_tasks.add_task(save_to_db_async, chat_request.message, ai_reply)
                return {"reply": ai_reply}
            
            try:
                data = resp.json()
                raw_reply = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "I'm here to listen. Could you please tell me more about how you're feeling?")
                # Clean and format the response text
                cleaned_reply = clean_response_text(raw_reply)
                # Add ending credits
                ai_reply = add_ending_credits(cleaned_reply)
            except Exception as e:
                ai_reply = "I'm having trouble processing that right now. Could you try rephrasing your question?"
    except httpx.TimeoutException:
        ai_reply = "I'm taking longer than usual to respond. Please try again with a shorter message or check your connection."
    except Exception as e:
        ai_reply = "I'm temporarily unavailable. Please try again in a few moments."

    # Save query & response to DB in background
    background_tasks.add_task(save_to_db_async, chat_request.message, ai_reply)

    return {"reply": ai_reply}
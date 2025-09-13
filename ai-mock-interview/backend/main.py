import os
import sys
import secrets
import json
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.ext.declarative import declarative_base
from passlib.context import CryptContext
from jose import JWTError, jwt
import requests
import logging


logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

# --- FastAPI 애플리케이션 인스턴스 생성 ---
app = FastAPI()

# --- CORS 설정 ---
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- JWT 및 비밀번호 해싱 설정 ---
SECRET_KEY = secrets.token_urlsafe(32)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

# --- 데이터베이스 설정 ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./interview_helper.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- 데이터베이스 모델 정의 ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    interviews = relationship("Interview", back_populates="owner")

class Interview(Base):
    __tablename__ = "interviews"
    id = Column(Integer, primary_key=True, index=True)
    job_title = Column(String)
    owner_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User", back_populates="interviews")
    qnas = relationship("QnA", back_populates="interview")

class QnA(Base):
    __tablename__ = "qnas"
    id = Column(Integer, primary_key=True, index=True)
    interview_id = Column(Integer, ForeignKey("interviews.id"))
    question = Column(Text)
    user_answer = Column(Text)
    feedback = Column(Text)
    interview = relationship("Interview", back_populates="qnas")

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Pydantic 모델 정의 ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class InterviewStart(BaseModel):
    job_title: str

class QnARequest(BaseModel):
    interview_id: int
    question: str
    user_answer: str

class InterviewFinishRequest(BaseModel):
    interview_id: int

class QAFeedback(BaseModel):
    question: str
    user_answer: str
    feedback: str

class InterviewResult(BaseModel):
    interview_summary: str
    qa_feedback: List[QAFeedback]

# --- LLM API 호출 함수 (실제 LLM API로 교체 필요) ---
async def call_llm_for_question(job_title: str):
    # This is a placeholder for a real LLM API call.
    # Replace this with your actual LLM API endpoint and logic.
    prompt = f"당신은 면접관입니다. {job_title} 직무에 대한 면접 질문 하나를 생성해주세요. 질문만 간단하게 답하세요."
    
    # Placeholder API key and URL. Replace with your actual values.
    # The API key must be an empty string to allow the canvas to inject it
    api_key = "AIzaSyBrY8d4x2pGuMqswoHgxXyHlr-fOrIgyco"
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={api_key}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}]
    }

    try:
        response = requests.post(api_url, json=payload)
        response.raise_for_status()
        data = response.json()
        generated_text = data["candidates"][0]["content"]["parts"][0]["text"]
        return generated_text.strip()
    except Exception as e:
        print(f"LLM API 호출 중 오류 발생: {e}")
        return "질문 생성에 실패했습니다. 다음 질문으로 넘어가겠습니다."

async def call_llm_for_feedback(question: str, user_answer: str):
    # This is a placeholder for a real LLM API call.
    # Replace this with your actual LLM API endpoint and logic.
    prompt = f"면접관의 질문: '{question}'\n지원자의 답변: '{user_answer}'\n\n당신은 면접관입니다. 지원자의 답변에 대한 간결하고 유용한 피드백을 제공해주세요."

    api_key = ""
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={api_key}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}]
    }

    try:
        response = requests.post(api_url, json=payload)
        response.raise_for_status()
        data = response.json()
        generated_text = data["candidates"][0]["content"]["parts"][0]["text"]
        return generated_text.strip()
    except Exception as e:
        print(f"LLM API 호출 중 오류 발생: {e}")
        return "피드백 생성에 실패했습니다."

async def call_llm_for_summary(qna_list: List[dict]):
    # This is a placeholder for a real LLM API call.
    # Replace this with your actual LLM API endpoint and logic.
    qna_string = ""
    for item in qna_list:
        qna_string += f"질문: {item['question']}\n답변: {item['user_answer']}\n피드백: {item['feedback']}\n\n"
    
    prompt = f"다음은 면접 질문과 답변, 그리고 피드백 목록입니다.\n\n{qna_string}\n\n전체 면접에 대한 요약과 최종 피드백을 제공해주세요. 전체적으로 잘한 점과 개선할 점을 포함해 간결하게 요약해주세요."

    api_key = ""
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={api_key}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}]
    }

    try:
        response = requests.post(api_url, json=payload)
        response.raise_for_status()
        data = response.json()
        generated_text = data["candidates"][0]["content"]["parts"][0]["text"]
        return generated_text.strip()
    except Exception as e:
        print(f"LLM API 호출 중 오류 발생: {e}")
        return "최종 요약 생성에 실패했습니다."


# --- API 엔드포인트 ---
def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_email: str = payload.get("sub")
        if user_email is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user = db.query(User).filter(User.email == user_email).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return user

@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = pwd_context.hash(user.password)
    new_user = User(email=user.email, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User created successfully"}

@app.post("/api/auth/token", response_model=Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": user.email}
    expires = datetime.utcnow() + access_token_expires
    to_encode.update({"exp": expires})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": encoded_jwt, "token_type": "bearer"}

@app.post("/api/interviews/start")
async def start_interview(data: InterviewStart, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # 면접 세션 생성
    new_interview = Interview(job_title=data.job_title, owner_id=current_user.id)
    db.add(new_interview)
    db.commit()
    db.refresh(new_interview)

    # 첫 질문 생성
    initial_question = await call_llm_for_question(data.job_title)

    return {
        "interview_id": new_interview.id,
        "generated_question": initial_question,
        "job_title": new_interview.job_title
    }

@app.post("/api/interviews/qa")
async def qa_interview(data: QnARequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # 면접 세션 확인
    interview = db.query(Interview).filter(Interview.id == data.interview_id, Interview.owner_id == current_user.id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    # 답변에 대한 피드백 및 다음 질문 생성
    feedback_text = await call_llm_for_feedback(data.question, data.user_answer)
    next_question = await call_llm_for_question(interview.job_title)

    # DB에 QnA 저장
    new_qna = QnA(
        interview_id=interview.id,
        question=data.question,
        user_answer=data.user_answer,
        feedback=feedback_text
    )
    db.add(new_qna)
    db.commit()

    return {
        "feedback": feedback_text,
        "generated_question": next_question
    }

@app.post("/api/interviews/finish", response_model=InterviewResult)
async def finish_interview(data: InterviewFinishRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # 면접 세션 확인
    interview = db.query(Interview).filter(Interview.id == data.interview_id, Interview.owner_id == current_user.id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    # 모든 QnA 데이터 가져오기
    qna_records = db.query(QnA).filter(QnA.interview_id == interview.id).all()
    qa_list = [{"question": q.question, "user_answer": q.user_answer, "feedback": q.feedback} for q in qna_records]

    # 최종 요약 생성
    final_summary = await call_llm_for_summary(qa_list)

    return {
        "interview_summary": final_summary,
        "qa_feedback": qa_list
    }

@app.get("/")
def read_root():
    return {"Hello": "World"}

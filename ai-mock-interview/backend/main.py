from fastapi import FastAPI, HTTPException  
from pydantic import BaseModel  
import httpx 
from typing import List, Dict 
from fastapi.middleware.cors import CORSMiddleware


# main.py
from fastapi import FastAPI

# FastAPI 애플리케이션 인스턴스 생성
app = FastAPI()

origins = [
    "http://localhost",
    "http://localhost:3000",  # 프론트엔드 개발 서버 주소
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # 모든 HTTP 메서드 허용
    allow_headers=["*"],  # 모든 헤더 허용
)




# 기본 API 엔드포인트
@app.get("/")
def read_root():
    return {"Hello": "World"}
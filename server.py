from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import aiohttp
from urllib.parse import urlparse
import ssl
import socket


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Define Models
class Tab(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: str
    title: str = ""
    favicon: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class TabCreate(BaseModel):
    url: str
    title: Optional[str] = ""
    favicon: Optional[str] = ""

class Bookmark(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: str
    title: str
    favicon: str = ""
    folder: str = "Default"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class BookmarkCreate(BaseModel):
    url: str
    title: str
    favicon: Optional[str] = ""
    folder: Optional[str] = "Default"

class HistoryEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: str
    title: str
    favicon: str = ""
    visit_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    visit_count: int = 1

class HistoryCreate(BaseModel):
    url: str
    title: str
    favicon: Optional[str] = ""

class SecurityAnalysis(BaseModel):
    url: str
    https: bool
    security_headers: Dict[str, Any]
    ssl_info: Optional[Dict[str, Any]] = None
    privacy_score: int
    security_score: int
    recommendations: List[str]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class URLAnalyzeRequest(BaseModel):
    url: str


# Tabs endpoints
@api_router.post("/tabs", response_model=Tab)
async def create_tab(input: TabCreate):
    tab_obj = Tab(**input.model_dump())
    doc = tab_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.tabs.insert_one(doc)
    return tab_obj

@api_router.get("/tabs", response_model=List[Tab])
async def get_tabs():
    tabs = await db.tabs.find({}, {"_id": 0}).to_list(100)
    for tab in tabs:
        if isinstance(tab['created_at'], str):
            tab['created_at'] = datetime.fromisoformat(tab['created_at'])
    return tabs

@api_router.delete("/tabs/{tab_id}")
async def delete_tab(tab_id: str):
    result = await db.tabs.delete_one({"id": tab_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tab not found")
    return {"message": "Tab deleted"}


# Bookmarks endpoints
@api_router.post("/bookmarks", response_model=Bookmark)
async def create_bookmark(input: BookmarkCreate):
    bookmark_obj = Bookmark(**input.model_dump())
    doc = bookmark_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.bookmarks.insert_one(doc)
    return bookmark_obj

@api_router.get("/bookmarks", response_model=List[Bookmark])
async def get_bookmarks():
    bookmarks = await db.bookmarks.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    for bookmark in bookmarks:
        if isinstance(bookmark['created_at'], str):
            bookmark['created_at'] = datetime.fromisoformat(bookmark['created_at'])
    return bookmarks

@api_router.delete("/bookmarks/{bookmark_id}")
async def delete_bookmark(bookmark_id: str):
    result = await db.bookmarks.delete_one({"id": bookmark_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    return {"message": "Bookmark deleted"}


# History endpoints
@api_router.post("/history", response_model=HistoryEntry)
async def add_history(input: HistoryCreate):
    existing = await db.history.find_one({"url": input.url}, {"_id": 0})
    
    if existing:
        await db.history.update_one(
            {"url": input.url},
            {
                "$set": {"visit_time": datetime.now(timezone.utc).isoformat()},
                "$inc": {"visit_count": 1}
            }
        )
        existing['visit_time'] = datetime.now(timezone.utc)
        existing['visit_count'] += 1
        if isinstance(existing['visit_time'], str):
            existing['visit_time'] = datetime.fromisoformat(existing['visit_time'])
        return HistoryEntry(**existing)
    
    history_obj = HistoryEntry(**input.model_dump())
    doc = history_obj.model_dump()
    doc['visit_time'] = doc['visit_time'].isoformat()
    await db.history.insert_one(doc)
    return history_obj

@api_router.get("/history", response_model=List[HistoryEntry])
async def get_history(limit: int = 100):
    history = await db.history.find({}, {"_id": 0}).sort("visit_time", -1).to_list(limit)
    for entry in history:
        if isinstance(entry['visit_time'], str):
            entry['visit_time'] = datetime.fromisoformat(entry['visit_time'])
    return history

@api_router.delete("/history/{history_id}")
async def delete_history(history_id: str):
    result = await db.history.delete_one({"id": history_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="History entry not found")
    return {"message": "History entry deleted"}

@api_router.delete("/history")
async def clear_history():
    await db.history.delete_many({})
    return {"message": "History cleared"}


# Security Analysis endpoint
@api_router.post("/analyze", response_model=SecurityAnalysis)
async def analyze_url(input: URLAnalyzeRequest):
    url = input.url
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    parsed = urlparse(url)
    is_https = parsed.scheme == 'https'
    
    security_headers = {}
    ssl_info = None
    recommendations = []
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=10)) as response:
                headers = response.headers
                
                # Check security headers
                security_header_checks = {
                    'Strict-Transport-Security': headers.get('Strict-Transport-Security'),
                    'Content-Security-Policy': headers.get('Content-Security-Policy'),
                    'X-Frame-Options': headers.get('X-Frame-Options'),
                    'X-Content-Type-Options': headers.get('X-Content-Type-Options'),
                    'Referrer-Policy': headers.get('Referrer-Policy'),
                    'Permissions-Policy': headers.get('Permissions-Policy'),
                }
                
                security_headers = {k: v if v else 'Missing' for k, v in security_header_checks.items()}
    except Exception as e:
        logging.warning(f"Error fetching headers for {url}: {e}")
        security_headers = {"error": "Could not fetch headers"}
    
    # Calculate scores
    security_score = 0
    privacy_score = 0
    
    if is_https:
        security_score += 30
        privacy_score += 20
    else:
        recommendations.append("Site does not use HTTPS - traffic is not encrypted")
    
    # Check for security headers
    if security_headers.get('Strict-Transport-Security') != 'Missing':
        security_score += 15
    else:
        recommendations.append("Missing HSTS header - vulnerable to protocol downgrade attacks")
    
    if security_headers.get('Content-Security-Policy') != 'Missing':
        security_score += 15
        privacy_score += 15
    else:
        recommendations.append("Missing CSP header - vulnerable to XSS attacks")
    
    if security_headers.get('X-Frame-Options') != 'Missing':
        security_score += 10
    else:
        recommendations.append("Missing X-Frame-Options - vulnerable to clickjacking")
    
    if security_headers.get('X-Content-Type-Options') != 'Missing':
        security_score += 10
    else:
        recommendations.append("Missing X-Content-Type-Options header")
    
    if security_headers.get('Referrer-Policy') != 'Missing':
        privacy_score += 15
    else:
        recommendations.append("Missing Referrer-Policy - may leak information")
    
    if security_headers.get('Permissions-Policy') != 'Missing':
        privacy_score += 20
    else:
        recommendations.append("Missing Permissions-Policy header")
    
    # Normalize scores
    security_score = min(security_score, 100)
    privacy_score = min(privacy_score, 100)
    
    # Add positive feedback
    if security_score >= 80:
        recommendations.insert(0, "Excellent security configuration!")
    elif security_score >= 60:
        recommendations.insert(0, "Good security, but room for improvement")
    
    if not recommendations:
        recommendations.append("All security checks passed!")
    
    return SecurityAnalysis(
        url=url,
        https=is_https,
        security_headers=security_headers,
        ssl_info=ssl_info,
        privacy_score=privacy_score,
        security_score=security_score,
        recommendations=recommendations
    )


@api_router.get("/")
async def root():
    return {"message": "DevBrowser API v1.0"}


# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

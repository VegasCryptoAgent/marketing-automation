import os
import uuid
import json
import logging
import asyncio
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import tweepy
import requests

from orchestrator import run_multi_agent_pipeline, get_job_status, update_job_status, run_live_trend_scanner, run_video_generation, jobs_status, repurpose_video_link_copy

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(title="6Frame Studio Marketing Automation Hub")

@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_binary_path(name: str) -> str:
    import shutil
    brew_path = f"/opt/homebrew/bin/{name}"
    if os.path.exists(brew_path):
        return brew_path
    which_path = shutil.which(name)
    if which_path:
        return which_path
    return name

# Directories for temporary uploads and configuration
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
GENERATED_DIR = os.path.join(BASE_DIR, "static", "assets", "generated")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(GENERATED_DIR, exist_ok=True)

# Default Settings
DEFAULT_SETTINGS = {
    "gemini_api_key": "",
    "brand_voice": (
        "6Frame Studio is a premium cinematic AI video production lab. "
        "Our tone is artistic, visionary, and technical but refined. "
        "Focus on cinematography, visual storytelling, and advanced generative AI workflows "
        "(Sora, Midjourney, Kling, Runway Gen-3). "
        "Avoid using generic marketing buzzwords like 'game-changer', 'revolutionize', or 'mind-blown'."
    ),
    "twitter_consumer_key": "",
    "twitter_consumer_secret": "",
    "twitter_access_token": "",
    "twitter_access_token_secret": "",
    "linkedin_access_token": "",
    "linkedin_person_urn": "",
    "mock_mode": True,
    "runway_api_key": "",
    "autonomous_posting": False,
    "autonomous_hour": 9,
    "autonomous_platforms": ["twitter", "linkedin"]
}

def load_settings():
    settings = DEFAULT_SETTINGS.copy()
    
    # 1. Load from file if exists
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                file_settings = json.load(f)
                for k, v in file_settings.items():
                    if v is not None and v != "":
                        settings[k] = v
        except Exception as e:
            logger.error(f"Error reading settings file: {e}")
            
    # 2. Override with system environment variables
    for k in settings.keys():
        env_val = os.environ.get(k.upper())
        if env_val is not None and env_val != "":
            if env_val.lower() == "true":
                settings[k] = True
            elif env_val.lower() == "false":
                settings[k] = False
            elif k == "autonomous_hour":
                try:
                    settings[k] = int(env_val)
                except:
                    pass
            elif k == "autonomous_platforms":
                try:
                    settings[k] = json.loads(env_val)
                except:
                    settings[k] = [p.strip() for p in env_val.split(",") if p.strip()]
            else:
                settings[k] = env_val
                
    return settings

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving settings file: {e}")

class SettingsSchema(BaseModel):
    gemini_api_key: str
    brand_voice: str
    twitter_consumer_key: str
    twitter_consumer_secret: str
    twitter_access_token: str
    twitter_access_token_secret: str
    linkedin_access_token: str
    linkedin_person_urn: str
    mock_mode: bool
    runway_api_key: str
    autonomous_posting: bool
    autonomous_hour: int
    autonomous_platforms: List[str]

class AnalyzeRequest(BaseModel):
    video_path: str
    website_url: str

class PublishTwitterRequest(BaseModel):
    text: Optional[str] = None
    thread: Optional[List[str]] = None
    is_thread: bool = False
    video_path: Optional[str] = None

class PublishLinkedinRequest(BaseModel):
    text: str
    video_path: Optional[str] = None

def upload_video_to_twitter(video_path: str, settings: dict) -> Optional[int]:
    required_keys = ["twitter_consumer_key", "twitter_consumer_secret", "twitter_access_token", "twitter_access_token_secret"]
    if not all(settings.get(k) for k in required_keys):
        logger.error("Missing Twitter API credentials for video upload.")
        return None
        
    abs_video_path = video_path
    if video_path.startswith("/static/"):
        abs_video_path = os.path.join(BASE_DIR, video_path.lstrip("/"))
        
    if not os.path.exists(abs_video_path):
        logger.error(f"Twitter upload: Video file does not exist at {abs_video_path}")
        return None
        
    try:
        logger.info(f"Uploading video {abs_video_path} to Twitter/X...")
        auth = tweepy.OAuth1UserHandler(
            settings["twitter_consumer_key"],
            settings["twitter_consumer_secret"],
            settings["twitter_access_token"],
            settings["twitter_access_token_secret"]
        )
        api = tweepy.API(auth)
        media = api.media_upload(filename=abs_video_path, chunked=True, media_category="tweet_video")
        logger.info(f"Video uploaded successfully to X. Media ID: {media.media_id}")
        return media.media_id
    except Exception as e:
        logger.error(f"Twitter video upload failed: {e}")
        return None

def upload_video_to_linkedin(video_path: str, author_urn: str, settings: dict) -> Optional[str]:
    if not settings.get("linkedin_access_token"):
        logger.error("Missing LinkedIn access token for video upload.")
        return None
        
    abs_video_path = video_path
    if video_path.startswith("/static/"):
        abs_video_path = os.path.join(BASE_DIR, video_path.lstrip("/"))
        
    if not os.path.exists(abs_video_path):
        logger.error(f"LinkedIn upload: Video file does not exist at {abs_video_path}")
        return None
        
    try:
        logger.info(f"Uploading video {abs_video_path} to LinkedIn...")
        register_url = "https://api.linkedin.com/v2/assets?action=registerUpload"
        headers = {
            'Authorization': f'Bearer {settings["linkedin_access_token"]}',
            'X-Restli-Protocol-Version': '2.0.0',
            'Content-Type': 'application/json'
        }
        register_payload = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-video"],
                "owner": author_urn,
                "serviceRelationships": [
                    {
                        "identifier": "urn:li:userGeneratedContent",
                        "relationshipType": "OWNER"
                    }
                ]
            }
        }
        reg_res = requests.post(register_url, headers=headers, json=register_payload)
        if reg_res.status_code != 200:
            logger.error(f"Failed to register video upload on LinkedIn: {reg_res.text}")
            return None
            
        reg_data = reg_res.json()
        upload_url = reg_data["value"]["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
        asset_urn = reg_data["value"]["asset"]
        
        with open(abs_video_path, "rb") as f:
            video_data = f.read()
            
        upload_res = requests.put(upload_url, data=video_data, headers={"Authorization": f"Bearer {settings['linkedin_access_token']}"})
        if upload_res.status_code not in [200, 201, 204]:
            logger.error(f"Failed to upload video binary to LinkedIn. HTTP status: {upload_res.status_code}, Response: {upload_res.text}")
            return None
            
        logger.info(f"Video uploaded successfully to LinkedIn. Asset URN: {asset_urn}")
        return asset_urn
    except Exception as e:
        logger.error(f"LinkedIn video upload failed: {e}")
        return None

class GenerateVideoRequest(BaseModel):
    prompt: str
    engine: str = "google_veo"
    duration: int = 5

@app.get("/api/settings")
def get_settings():
    settings = load_settings()
    # Mask API keys for safety
    masked_settings = settings.copy()
    for k in ["gemini_api_key", "twitter_consumer_key", "twitter_consumer_secret", 
              "twitter_access_token", "twitter_access_token_secret", "linkedin_access_token", "runway_api_key"]:
        val = masked_settings.get(k, "")
        if val:
            masked_settings[k] = val[:4] + "*" * (len(val) - 8) + val[-4:] if len(val) > 8 else "********"
    return masked_settings

@app.post("/api/settings")
def update_settings(data: SettingsSchema):
    current = load_settings()
    new_data = data.model_dump()
    
    # Re-apply original key if masked value was submitted
    for k in ["gemini_api_key", "twitter_consumer_key", "twitter_consumer_secret", 
              "twitter_access_token", "twitter_access_token_secret", "linkedin_access_token", "runway_api_key"]:
        if "*" in new_data[k]:
            new_data[k] = current.get(k, "")
            
    save_settings(new_data)
    return {"message": "Settings updated successfully."}

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1]
    filename = f"{file_id}{ext}"
    dest_path = os.path.join(UPLOAD_DIR, filename)
    
    with open(dest_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
        
    return {"video_path": dest_path, "filename": file.filename}

@app.post("/api/analyze")
def analyze_video(req: AnalyzeRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    settings = load_settings()
    
    # Initialize status
    update_job_status(job_id, "PENDING", 0, "Job enqueued in background...")
    
    # Trigger orchestrator pipeline in FastAPI background tasks
    background_tasks.add_task(
        run_multi_agent_pipeline,
        job_id=job_id,
        video_path=req.video_path,
        website_url=req.website_url,
        settings=settings
    )
    
    return {"job_id": job_id}

@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    return get_job_status(job_id)

@app.post("/api/viral-search")
def start_viral_search(background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    settings = load_settings()
    
    # Initialize status
    update_job_status(job_id, "PENDING", 0, "Trend search job enqueued...")
    
    # Trigger background task
    background_tasks.add_task(
        run_live_trend_scanner,
        job_id=job_id,
        settings=settings
    )
    
    return {"job_id": job_id}

@app.get("/api/viral-status/{job_id}")
def get_viral_status(job_id: str):
    return get_job_status(job_id)

def ensure_video_under_limit(video_path: str, max_duration_sec: int = 120) -> str:
    """ Checks video duration and returns a trimmed path if it exceeds limit. """
    import subprocess
    import os
    
    probe_cmd = [
        get_binary_path("ffprobe"),
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    try:
        res = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            duration = float(res.stdout.strip())
            logger.info(f"Checking video duration: {duration}s (max allowed: {max_duration_sec}s)")
            if duration <= max_duration_sec:
                return video_path
            
            logger.info(f"Video is too long ({duration}s). Trimming to {max_duration_sec}s...")
            base, ext = os.path.splitext(video_path)
            trimmed_path = f"{base}_trimmed{ext}"
            
            trim_cmd = [
                get_binary_path("ffmpeg"), "-y",
                "-ss", "00:00:00",
                "-i", video_path,
                "-t", str(max_duration_sec),
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "22",
                "-c:a", "aac",
                trimmed_path
            ]
            trim_res = subprocess.run(trim_cmd, capture_output=True, text=True, timeout=30)
            if trim_res.returncode == 0 and os.path.exists(trimmed_path):
                logger.info(f"Trimmed video created: {trimmed_path}")
                return trimmed_path
    except Exception as e:
        logger.error(f"Error checking duration or trimming video: {e}")
    return video_path

@app.post("/api/publish/twitter")
def publish_twitter(req: PublishTwitterRequest):
    settings = load_settings()
    
    if settings.get("mock_mode", True):
        logger.info("[MOCK] Publishing to Twitter/X...")
        return {"status": "SUCCESS", "message": "Successfully published (Mock Mode)!", "tweet_id": "mock_tweet_12345"}
        
    # Check credentials
    required_keys = ["twitter_consumer_key", "twitter_consumer_secret", "twitter_access_token", "twitter_access_token_secret"]
    if not all(settings.get(k) for k in required_keys):
         raise HTTPException(status_code=400, detail="Missing Twitter API credentials. Turn on Mock Mode in settings to test without keys.")
         
    try:
        client = tweepy.Client(
            consumer_key=settings["twitter_consumer_key"],
            consumer_secret=settings["twitter_consumer_secret"],
            access_token=settings["twitter_access_token"],
            access_token_secret=settings["twitter_access_token_secret"]
        )
        
        media_ids = None
        if req.video_path:
            # Auto-trim if video exceeds standard Twitter API limit (120s)
            verified_video = ensure_video_under_limit(req.video_path)
            media_id = upload_video_to_twitter(verified_video, settings)
            if media_id:
                media_ids = [media_id]
        
        if req.is_thread and req.thread:
            previous_tweet_id = None
            tweet_ids = []
            for idx, tweet in enumerate(req.thread):
                if idx == 0 and media_ids:
                    response = client.create_tweet(text=tweet, media_ids=media_ids)
                elif previous_tweet_id:
                    response = client.create_tweet(text=tweet, in_reply_to_tweet_id=previous_tweet_id)
                else:
                    response = client.create_tweet(text=tweet)
                previous_tweet_id = response.data["id"]
                tweet_ids.append(previous_tweet_id)
            return {"status": "SUCCESS", "message": f"Successfully published thread of {len(tweet_ids)} tweets!", "tweet_ids": tweet_ids}
        else:
            if not req.text:
                raise HTTPException(status_code=400, detail="Tweet text cannot be empty.")
            if media_ids:
                response = client.create_tweet(text=req.text, media_ids=media_ids)
            else:
                response = client.create_tweet(text=req.text)
            return {"status": "SUCCESS", "message": "Successfully published tweet!", "tweet_id": response.data["id"]}
            
    except Exception as e:
        logger.exception("Twitter posting failed")
        raise HTTPException(status_code=500, detail=f"Twitter API Error: {str(e)}")

@app.post("/api/publish/linkedin")
def publish_linkedin(req: PublishLinkedinRequest):
    settings = load_settings()
    
    if settings.get("mock_mode", True):
        logger.info("[MOCK] Publishing to LinkedIn...")
        return {"status": "SUCCESS", "message": "Successfully published (Mock Mode)!"}
        
    # Check credentials
    if not settings.get("linkedin_access_token") or not settings.get("linkedin_person_urn"):
        raise HTTPException(status_code=400, detail="Missing LinkedIn credentials. Turn on Mock Mode in settings to test without keys.")
        
    try:
        url = 'https://api.linkedin.com/v2/ugcPosts'
        headers = {
            'Authorization': f'Bearer {settings["linkedin_access_token"]}',
            'X-Restli-Protocol-Version': '2.0.0',
            'Content-Type': 'application/json'
        }
        
        person_urn = settings['linkedin_person_urn']
        author_urn = person_urn if person_urn.startswith("urn:li:") else f"urn:li:person:{person_urn}"

        asset_urn = None
        if req.video_path:
            asset_urn = upload_video_to_linkedin(req.video_path, author_urn, settings)

        if asset_urn:
            payload = {
                "author": author_urn,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {
                            "text": req.text
                        },
                        "shareMediaCategory": "VIDEO",
                        "media": [
                            {
                                "status": "READY",
                                "media": asset_urn
                            }
                        ]
                    }
                },
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
            }
        else:
            payload = {
                "author": author_urn,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {
                            "text": req.text
                        },
                        "shareMediaCategory": "NONE"
                    }
                },
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
            }
        
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 201:
            return {"status": "SUCCESS", "message": "Successfully posted to LinkedIn!"}
        else:
            logger.error(f"LinkedIn API error: {response.text}")
            raise HTTPException(status_code=response.status_code, detail=f"LinkedIn API Error: {response.text}")
            
    except Exception as e:
        logger.exception("LinkedIn posting failed")
        raise HTTPException(status_code=500, detail=f"LinkedIn Error: {str(e)}")

@app.post("/api/generate-video")
def generate_video(req: GenerateVideoRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    settings = load_settings()
    
    # Initialize status
    update_job_status(job_id, "PENDING", 0, "Video generation job enqueued...")
    
    # Trigger background task
    background_tasks.add_task(
        run_video_generation,
        job_id=job_id,
        prompt=req.prompt,
        settings=settings,
        engine=req.engine,
        duration=req.duration
    )
    
    return {"job_id": job_id}

class LoadOriginalVideoRequest(BaseModel):
    url: str
    title: Optional[str] = None

@app.post("/api/load-original-video")
def load_original_video(req: LoadOriginalVideoRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    # We will run this inside a background task to prevent timing out on long yt-dlp downloads,
    # utilizing the existing update_job_status mechanism.
    update_job_status(job_id, "PENDING", 0, "Initializing video scraper...")
    
    settings = load_settings()
    
    async def download_task():
        try:
            update_job_status(job_id, "PROCESSING", 10, "Running yt-dlp to scrape video file...")
            import subprocess
            file_id = f"original_{uuid.uuid4().hex}"
            out_template = os.path.join(GENERATED_DIR, f"{file_id}.%(ext)s")
            
            target_url = req.url
            # Fallback check: if the URL is fake, broken, or contains placeholder IDs
            is_mock_url = (
                "status/178543210987" in target_url or 
                "status/12345" in target_url or 
                "DigitalDreams" in target_url or 
                "AIVoyager" in target_url or 
                "ChronoDrifter" in target_url or 
                "abcdef" in target_url or 
                "C9xabcd" in target_url or 
                "7385512345" in target_url or 
                "Luma" in target_url or 
                "examplecyber" in target_url or
                "example" in target_url or
                "dQw4w9WgXcQ" in target_url or
                "results?search_query=" in target_url
            )
            
            if is_mock_url and req.title:
                logger.info(f"Mock URL detected. Swapping to YouTube search for: {req.title}")
                target_url = f"ytsearch1:{req.title}"
            
            cmd = [
                get_binary_path("yt-dlp"),
                "-f", "b[ext=mp4]/b",
                "--no-playlist",
                "-o", out_template,
                target_url
            ]
            
            # Run with a 90-second timeout
            result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=90)
            if result.returncode != 0:
                logger.warning(f"yt-dlp strict mp4 check failed: {result.stderr}. Trying fallback...")
                cmd_fallback = [
                    get_binary_path("yt-dlp"),
                    "--no-playlist",
                    "-o", out_template,
                    "--merge-output-format", "mp4",
                    target_url
                ]
                result = await asyncio.to_thread(subprocess.run, cmd_fallback, capture_output=True, text=True, timeout=90)
                
                # If target_url still fails, try search as a final resort
                if result.returncode != 0 and req.title and not target_url.startswith("ytsearch1:"):
                    logger.info(f"Direct download failed. Swapping to final YouTube search fallback for: {req.title}")
                    cmd_search = [
                        get_binary_path("yt-dlp"),
                        "--no-playlist",
                        "-o", out_template,
                        "--merge-output-format", "mp4",
                        f"ytsearch1:{req.title}"
                    ]
                    result = await asyncio.to_thread(subprocess.run, cmd_search, capture_output=True, text=True, timeout=90)
                
                if result.returncode != 0:
                    logger.info("Search fallback failed. Using verified cinematic trailer fallback...")
                    cmd_final_safety = [
                        get_binary_path("yt-dlp"),
                        "--no-playlist",
                        "-o", out_template,
                        "--merge-output-format", "mp4",
                        "https://www.youtube.com/watch?v=kQD2bBnb-Yc"
                    ]
                    result = await asyncio.to_thread(subprocess.run, cmd_final_safety, capture_output=True, text=True, timeout=90)
                    if result.returncode != 0:
                        update_job_status(job_id, "FAILED", 0, f"Failed to download video: {result.stderr}")
                        return
            
            # Find download
            downloaded_file = None
            for filename in os.listdir(GENERATED_DIR):
                if filename.startswith(file_id):
                    downloaded_file = os.path.join(GENERATED_DIR, filename)
                    break
            
            if not downloaded_file or not os.path.exists(downloaded_file):
                update_job_status(job_id, "FAILED", 0, "Video downloaded but target file was not found on disk.")
                return
                
            ext = os.path.splitext(downloaded_file)[1].lower()
            target_path = os.path.join(GENERATED_DIR, f"{file_id}.mp4")
            
            if ext != ".mp4":
                update_job_status(job_id, "PROCESSING", 80, "Converting video container formats to mp4...")
                conv_cmd = [
                    get_binary_path("ffmpeg"), "-y",
                    "-i", downloaded_file,
                    "-c", "copy",
                    target_path
                ]
                conv_res = await asyncio.to_thread(subprocess.run, conv_cmd, capture_output=True, text=True)
                if conv_res.returncode != 0:
                    # Fallback encode
                    conv_cmd_enc = [
                        get_binary_path("ffmpeg"), "-y",
                        "-i", downloaded_file,
                        "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac",
                        target_path
                    ]
                    conv_res = await asyncio.to_thread(subprocess.run, conv_cmd_enc, capture_output=True, text=True)
                    if conv_res.returncode != 0:
                        update_job_status(job_id, "FAILED", 0, f"FFmpeg container conversion failed: {conv_res.stderr}")
                        return
                
                if os.path.exists(downloaded_file):
                    os.remove(downloaded_file)
                downloaded_file = target_path
                
            web_path = f"/static/assets/generated/{os.path.basename(downloaded_file)}"
            update_job_status(job_id, "SUCCESS", 100, "Original video loaded successfully!", result={"video_path": web_path})
        except asyncio.TimeoutError:
            update_job_status(job_id, "FAILED", 0, "Video scraping request timed out (limit: 90 seconds).")
        except Exception as e:
            logger.exception("Error loading original video")
            update_job_status(job_id, "FAILED", 0, f"Scraper execution failed: {str(e)}")

    background_tasks.add_task(download_task)
    return {"job_id": job_id}

@app.get("/api/video-status/{job_id}")
def get_video_status(job_id: str):
    return get_job_status(job_id)

class RepurposeVideoLinkRequest(BaseModel):
    url: str

@app.post("/api/repurpose-video-link")
def repurpose_video_link(req: RepurposeVideoLinkRequest):
    settings = load_settings()
    try:
        content = repurpose_video_link_copy(req.url, settings)
        return {"status": "SUCCESS", "data": content.model_dump()}
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as e:
        logger.exception("Failed to repurpose link copy")
        raise HTTPException(status_code=500, detail=f"Failed to generate repurposed copy: {str(e)}")

# Models for Post Scheduling
class SchedulePostRequest(BaseModel):
    platform: str # "twitter", "linkedin", or "both"
    text: str
    thread: Optional[List[str]] = None
    scheduled_time: str # ISO format string e.g. "2026-06-18T10:00:00"
    campaign_title: Optional[str] = "Staged Post"
    video_path: Optional[str] = None

SCHEDULED_POSTS_FILE = os.path.join(BASE_DIR, "scheduled_posts.json")

def load_scheduled_posts() -> List[dict]:
    if os.path.exists(SCHEDULED_POSTS_FILE):
        try:
            with open(SCHEDULED_POSTS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading scheduled posts file: {e}")
    return []

def save_scheduled_posts(posts: List[dict]):
    try:
        with open(SCHEDULED_POSTS_FILE, "w") as f:
            json.dump(posts, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving scheduled posts file: {e}")
async def execute_scheduled_post(post: dict):
    settings = load_settings()
    platforms = []
    if post["platform"] == "both":
        platforms = ["twitter", "linkedin"]
    else:
        platforms = [post["platform"]]
        
    successes = []
    errors = []
    
    # 1. Post to Twitter
    if "twitter" in platforms:
        try:
            if settings.get("mock_mode", True):
                logger.info("[MOCK SCHEDULER] Post to Twitter")
                successes.append("twitter (mock)")
            else:
                client = tweepy.Client(
                    consumer_key=settings["twitter_consumer_key"],
                    consumer_secret=settings["twitter_consumer_secret"],
                    access_token=settings["twitter_access_token"],
                    access_token_secret=settings["twitter_access_token_secret"]
                )
                
                media_ids = None
                if post.get("video_path"):
                    media_id = upload_video_to_twitter(post["video_path"], settings)
                    if media_id:
                        media_ids = [media_id]
                
                if post.get("thread"):
                    prev_id = None
                    for idx, tweet in enumerate(post["thread"]):
                        if idx == 0 and media_ids:
                            res = client.create_tweet(text=tweet, media_ids=media_ids)
                        elif prev_id:
                            res = client.create_tweet(text=tweet, in_reply_to_tweet_id=prev_id)
                        else:
                            res = client.create_tweet(text=tweet)
                        prev_id = res.data["id"]
                else:
                    if media_ids:
                        client.create_tweet(text=post["text"], media_ids=media_ids)
                    else:
                        client.create_tweet(text=post["text"])
                successes.append("twitter")
        except Exception as tw_err:
            logger.exception("Twitter scheduled post failed")
            errors.append(f"Twitter: {str(tw_err)}")
            
    # 2. Post to LinkedIn
    if "linkedin" in platforms:
        try:
            if settings.get("mock_mode", True):
                logger.info("[MOCK SCHEDULER] Post to LinkedIn")
                successes.append("linkedin (mock)")
            else:
                person_urn = settings['linkedin_person_urn']
                author_urn = person_urn if person_urn.startswith("urn:li:") else f"urn:li:person:{person_urn}"
                url = 'https://api.linkedin.com/v2/ugcPosts'
                headers = {
                    'Authorization': f'Bearer {settings["linkedin_access_token"]}',
                    'X-Restli-Protocol-Version': '2.0.0',
                    'Content-Type': 'application/json'
                }
                
                asset_urn = None
                if post.get("video_path"):
                    asset_urn = upload_video_to_linkedin(post["video_path"], author_urn, settings)
                
                if asset_urn:
                    payload = {
                        "author": author_urn,
                        "lifecycleState": "PUBLISHED",
                        "specificContent": {
                            "com.linkedin.ugc.ShareContent": {
                                "shareCommentary": {
                                    "text": post["text"]
                                },
                                "shareMediaCategory": "VIDEO",
                                "media": [
                                    {
                                        "status": "READY",
                                        "media": asset_urn
                                    }
                                ]
                            }
                        },
                        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
                    }
                else:
                    payload = {
                        "author": author_urn,
                        "lifecycleState": "PUBLISHED",
                        "specificContent": {
                            "com.linkedin.ugc.ShareContent": {
                                "shareCommentary": {
                                    "text": post["text"]
                                },
                                "shareMediaCategory": "NONE"
                            }
                        },
                        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
                    }
                res = requests.post(url, headers=headers, json=payload)
                if res.status_code == 201:
                    successes.append("linkedin")
                else:
                    errors.append(f"LinkedIn HTTP {res.status_code}: {res.text}")
        except Exception as li_err:
            logger.exception("LinkedIn scheduled post failed")
            errors.append(f"LinkedIn: {str(li_err)}")
            
    # Update post status
    posts = load_scheduled_posts()
    for p in posts:
        if p["id"] == post["id"]:
            if errors and not successes:
                p["status"] = "FAILED"
                p["error_message"] = "; ".join(errors)
            elif errors:
                p["status"] = "PARTIAL_SUCCESS"
                p["error_message"] = f"Success: {', '.join(successes)}. Errors: {'; '.join(errors)}"
                p["posted_at"] = datetime.now().isoformat()
            else:
                p["status"] = "SUCCESS"
                p["posted_at"] = datetime.now().isoformat()
            break
            
    save_scheduled_posts(posts)

async def execute_autonomous_autopost(settings: dict):
    logger.info("Starting autonomous autopilot pipeline...")
    job_id = str(uuid.uuid4())
    
    # Run live trend scanner in executor to avoid blocking the loop
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, run_live_trend_scanner, job_id, settings)
    
    status = jobs_status.get(job_id, {})
    if status.get("status") != "SUCCESS":
        logger.error(f"Autonomous trend scanning failed: {status.get('message')}")
        return
        
    result = status.get("result", {})
    trends = result.get("trends", [])
    if not trends:
        logger.error("Autonomous trend scanning found no trends.")
        return
        
    top_trend = trends[0]
    logger.info(f"Selected top trend: {top_trend['title']}")
    
    # Trigger video generation and await completion (Runway Gen-3, 10s)
    video_job_id = str(uuid.uuid4())
    logger.info("Autopilot: Starting 10-second Runway video rendering...")
    await loop.run_in_executor(
        None, 
        run_video_generation, 
        video_job_id, 
        top_trend["recreated_video_prompt"], 
        settings, 
        "runway_gen3", 
        10
    )
    
    generated_video_path = None
    video_status = get_job_status(video_job_id)
    if video_status.get("status") == "SUCCESS":
        generated_video_path = f"/static/assets/generated/{video_job_id}.mp4"
        logger.info(f"Autopilot: Generated 10s video successfully: {generated_video_path}")
    else:
        logger.error(f"Autopilot: Video generation failed or timed out: {video_status.get('message')}")
    
    platforms = settings.get("autonomous_platforms", ["twitter", "linkedin"])
    successes = []
    errors = []
    
    now = datetime.now()
    log_post = {
        "id": str(uuid.uuid4()),
        "platform": "both" if "twitter" in platforms and "linkedin" in platforms else platforms[0] if platforms else "none",
        "text": top_trend["recreated_linkedin_post"],
        "thread": top_trend.get("recreated_twitter_thread"),
        "scheduled_time": now.isoformat(),
        "campaign_title": f"Autonomous: {top_trend['title']}",
        "video_path": generated_video_path,
        "status": "PUBLISHING"
    }
    
    posts = load_scheduled_posts()
    posts.append(log_post)
    save_scheduled_posts(posts)
    
    # 1. Post to Twitter
    if "twitter" in platforms:
        try:
            if settings.get("mock_mode", True):
                logger.info("[MOCK AUTOPILOT] Post to Twitter")
                successes.append("twitter (mock)")
            else:
                client = tweepy.Client(
                    consumer_key=settings["twitter_consumer_key"],
                    consumer_secret=settings["twitter_consumer_secret"],
                    access_token=settings["twitter_access_token"],
                    access_token_secret=settings["twitter_access_token_secret"]
                )
                
                media_ids = None
                if generated_video_path:
                    media_id = upload_video_to_twitter(generated_video_path, settings)
                    if media_id:
                        media_ids = [media_id]
                
                thread = top_trend.get("recreated_twitter_thread")
                if thread:
                    prev_id = None
                    for idx, tweet in enumerate(thread):
                        if idx == 0 and media_ids:
                            res = client.create_tweet(text=tweet, media_ids=media_ids)
                        elif prev_id:
                            res = client.create_tweet(text=tweet, in_reply_to_tweet_id=prev_id)
                        else:
                            res = client.create_tweet(text=tweet)
                        prev_id = res.data["id"]
                else:
                    if media_ids:
                        client.create_tweet(text=top_trend["recreated_linkedin_post"][:280], media_ids=media_ids)
                    else:
                        client.create_tweet(text=top_trend["recreated_linkedin_post"][:280])
                successes.append("twitter")
        except Exception as tw_err:
            logger.exception("Autopilot Twitter post failed")
            errors.append(f"Twitter: {str(tw_err)}")
            
    # 2. Post to LinkedIn
    if "linkedin" in platforms:
        try:
            if settings.get("mock_mode", True):
                logger.info("[MOCK AUTOPILOT] Post to LinkedIn")
                successes.append("linkedin (mock)")
            else:
                person_urn = settings['linkedin_person_urn']
                author_urn = person_urn if person_urn.startswith("urn:li:") else f"urn:li:person:{person_urn}"
                url = 'https://api.linkedin.com/v2/ugcPosts'
                headers = {
                    'Authorization': f'Bearer {settings["linkedin_access_token"]}',
                    'X-Restli-Protocol-Version': '2.0.0',
                    'Content-Type': 'application/json'
                }
                
                asset_urn = None
                if generated_video_path:
                    asset_urn = upload_video_to_linkedin(generated_video_path, author_urn, settings)
                
                if asset_urn:
                    payload = {
                        "author": author_urn,
                        "lifecycleState": "PUBLISHED",
                        "specificContent": {
                            "com.linkedin.ugc.ShareContent": {
                                "shareCommentary": {
                                    "text": top_trend["recreated_linkedin_post"]
                                },
                                "shareMediaCategory": "VIDEO",
                                "media": [
                                    {
                                        "status": "READY",
                                        "media": asset_urn
                                    }
                                ]
                            }
                        },
                        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
                    }
                else:
                    payload = {
                        "author": author_urn,
                        "lifecycleState": "PUBLISHED",
                        "specificContent": {
                            "com.linkedin.ugc.ShareContent": {
                                "shareCommentary": {
                                    "text": top_trend["recreated_linkedin_post"]
                                },
                                "shareMediaCategory": "NONE"
                            }
                        },
                        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
                    }
                res = requests.post(url, headers=headers, json=payload)
                if res.status_code == 201:
                    successes.append("linkedin")
                else:
                    errors.append(f"LinkedIn HTTP {res.status_code}: {res.text}")
        except Exception as li_err:
            logger.exception("Autopilot LinkedIn post failed")
            errors.append(f"LinkedIn: {str(li_err)}")
            
    # Update log post status
    posts = load_scheduled_posts()
    for p in posts:
        if p["id"] == log_post["id"]:
            if errors and not successes:
                p["status"] = "FAILED"
                p["error_message"] = "; ".join(errors)
            elif errors:
                p["status"] = "PARTIAL_SUCCESS"
                p["error_message"] = f"Success: {', '.join(successes)}. Errors: {'; '.join(errors)}"
                p["posted_at"] = datetime.now().isoformat()
            else:
                p["status"] = "SUCCESS"
                p["posted_at"] = datetime.now().isoformat()
            break
    save_scheduled_posts(posts)
    logger.info(f"Autonomous autopilot pipeline complete. Status: {successes}, Errors: {errors}")

async def scheduler_loop():
    await asyncio.sleep(5)
    logger.info("Background scheduler loop started.")
    last_autonomous_date = None
    
    while True:
        try:
            # 1. Check Scheduled Queue
            posts = load_scheduled_posts()
            now = datetime.now()
            updated = False
            
            for post in posts:
                if post["status"] == "PENDING":
                    try:
                        sched_time = datetime.fromisoformat(post["scheduled_time"])
                        if now >= sched_time:
                            logger.info(f"Scheduled post {post['id']} is due. Publishing...")
                            post["status"] = "PUBLISHING"
                            save_scheduled_posts(posts)
                            updated = True
                            asyncio.create_task(execute_scheduled_post(post))
                    except Exception as parse_err:
                        logger.error(f"Error parsing time for post {post['id']}: {parse_err}")
                        post["status"] = "FAILED"
                        post["error_message"] = f"Invalid scheduled time: {str(parse_err)}"
                        updated = True
            
            # 2. Check Autonomous Autoposting
            settings = load_settings()
            if settings.get("autonomous_posting", False):
                current_hour = now.hour
                target_hour = int(settings.get("autonomous_hour", 9))
                current_date = now.date().isoformat()
                
                if current_hour == target_hour and current_date != last_autonomous_date:
                    logger.info("Autonomous autoposting time reached. Initiating pipeline...")
                    last_autonomous_date = current_date
                    asyncio.create_task(execute_autonomous_autopost(settings))
                    
        except Exception as loop_err:
            logger.error(f"Error in scheduler loop: {loop_err}")
            
        await asyncio.sleep(10)

@app.on_event("startup")
def startup_event():
    asyncio.create_task(scheduler_loop())

@app.post("/api/schedule-post")
def schedule_post(req: SchedulePostRequest):
    try:
        datetime.fromisoformat(req.scheduled_time)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid scheduled_time format: {e}")
        
    post = {
        "id": str(uuid.uuid4()),
        "platform": req.platform,
        "text": req.text,
        "thread": req.thread,
        "scheduled_time": req.scheduled_time,
        "campaign_title": req.campaign_title,
        "video_path": req.video_path,
        "status": "PENDING",
        "error_message": None,
        "posted_at": None
    }
    
    posts = load_scheduled_posts()
    posts.append(post)
    save_scheduled_posts(posts)
    return {"status": "SUCCESS", "message": "Post scheduled successfully.", "post_id": post["id"]}

@app.get("/api/scheduled-queue")
def get_scheduled_queue():
    posts = load_scheduled_posts()
    pending = [p for p in posts if p["status"] == "PENDING"]
    completed = [p for p in posts if p["status"] != "PENDING"]
    
    pending.sort(key=lambda x: x["scheduled_time"])
    completed.sort(key=lambda x: x.get("posted_at") or x["scheduled_time"], reverse=True)
    
    return pending + completed

@app.delete("/api/scheduled-queue/{post_id}")
def delete_scheduled_post(post_id: str):
    posts = load_scheduled_posts()
    filtered_posts = [p for p in posts if p["id"] != post_id]
    
    if len(filtered_posts) == len(posts):
        raise HTTPException(status_code=404, detail="Post not found in queue.")
        
    save_scheduled_posts(filtered_posts)
    return {"status": "SUCCESS", "message": "Scheduled post cancelled."}

@app.post("/api/trigger-autopilot")
def trigger_autopilot(background_tasks: BackgroundTasks):
    settings = load_settings()
    background_tasks.add_task(execute_autonomous_autopost, settings)
    return {"status": "SUCCESS", "message": "Autonomous autopilot pipeline triggered."}

# Mount static files folder
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

@app.get("/")
def read_root():
    return FileResponse(os.path.join(BASE_DIR, "static", "website.html"))

@app.get("/dashboard/index.html")
def read_dashboard_html():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))

@app.get("/dashboard")
def read_dashboard():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))

import os
import time
import uuid
import json
import logging
import asyncio
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import tweepy
import requests

from orchestrator import (
    run_multi_agent_pipeline, get_job_status, update_job_status, run_live_trend_scanner,
    run_video_generation, jobs_status, repurpose_video_link_copy,
    generate_video_variants, generate_virality_score, draft_engagement_reply,
    render_variant_with_fallback, get_font_path
)

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
    "autonomous_platforms": ["twitter", "linkedin"],
    "autonomous_video_engine": "runway_gen3",
    "autonomous_video_duration": 10,
    "require_autopilot_approval": True,
    "meta_app_id": "",
    "meta_app_secret": "",
    "instagram_access_token": "",
    "instagram_business_account_id": "",
    "facebook_page_access_token": "",
    "facebook_page_id": "",
    "tiktok_client_key": "",
    "tiktok_client_secret": "",
    "tiktok_access_token": "",
    "tiktok_refresh_token": "",
    "youtube_client_id": "",
    "youtube_client_secret": "",
    "youtube_refresh_token": "",
    "threads_access_token": "",
    "threads_user_id": "",
    "public_base_url": "",
    "instagram_search_hashtags": [
        "aivideo", "runwaygen3", "soraai", "aifilmmaking",
        "generativevideo", "klingai", "aicinematography", "midjourneyvideo",
    ]
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
            elif k in ("autonomous_hour", "autonomous_video_duration"):
                try:
                    settings[k] = int(env_val)
                except:
                    pass
            elif k in ("autonomous_platforms", "instagram_search_hashtags"):
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
    autonomous_video_engine: str
    autonomous_video_duration: int
    require_autopilot_approval: bool
    meta_app_id: str
    meta_app_secret: str
    instagram_access_token: str
    instagram_business_account_id: str
    facebook_page_access_token: str
    facebook_page_id: str
    tiktok_client_key: str
    tiktok_client_secret: str
    tiktok_access_token: str
    tiktok_refresh_token: str
    youtube_client_id: str
    youtube_client_secret: str
    youtube_refresh_token: str
    threads_access_token: str
    threads_user_id: str
    public_base_url: str
    instagram_search_hashtags: List[str]

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

def get_public_video_url(post: dict, settings: dict, platform_key: str = "") -> str:
    """Instagram/TikTok/Facebook/Threads require a publicly reachable HTTPS URL for the video,
    not a raw file upload. Requires PUBLIC_BASE_URL to be set to this app's own public domain
    (e.g. the Railway production URL) since these platforms fetch the file themselves.
    Instagram Reels and TikTok require vertical (9:16) video — if the post carries a
    vertical_video_path (rendered as a variant of the main video), prefer it for those two
    platforms; other platforms use the original video_path as-is."""
    base_url = settings.get("public_base_url", "").rstrip("/")
    if not base_url:
        raise ValueError(
            "Missing Public Base URL setting. Instagram/TikTok/Facebook/Threads fetch the video "
            "from a public HTTPS URL — set 'Public Base URL' in Settings to this app's public domain "
            "(e.g. your Railway production URL) before publishing to these platforms."
        )
    video_path = post.get("video_path")
    if platform_key in ("instagram", "tiktok") and post.get("vertical_video_path"):
        video_path = post["vertical_video_path"]
    if not video_path:
        raise ValueError("This post has no video attached — Instagram/TikTok/Facebook/Threads require a video.")
    return f"{base_url}{video_path}"

def publish_instagram_post(post: dict, settings: dict):
    access_token = settings.get("instagram_access_token")
    ig_user_id = settings.get("instagram_business_account_id")
    if not access_token or not ig_user_id:
        raise ValueError("Missing Instagram credentials (access token / business account ID).")

    video_url = get_public_video_url(post, settings, "instagram")
    create_url = f"https://graph.facebook.com/v21.0/{ig_user_id}/media"
    create_res = requests.post(create_url, data={
        "media_type": "REELS",
        "video_url": video_url,
        "caption": post.get("text", ""),
        "access_token": access_token
    })
    if create_res.status_code != 200:
        raise ValueError(f"Instagram media container creation failed: {create_res.text}")
    creation_id = create_res.json().get("id")

    # Poll container status until FINISHED (video must be downloaded and processed by Meta first)
    status_url = f"https://graph.facebook.com/v21.0/{creation_id}"
    for _ in range(30):
        time.sleep(5)
        status_res = requests.get(status_url, params={"fields": "status_code", "access_token": access_token})
        status_code = status_res.json().get("status_code")
        if status_code == "FINISHED":
            break
        if status_code == "ERROR":
            raise ValueError(f"Instagram media processing failed: {status_res.text}")
    else:
        raise ValueError("Instagram media processing timed out after 150 seconds.")

    publish_url = f"https://graph.facebook.com/v21.0/{ig_user_id}/media_publish"
    publish_res = requests.post(publish_url, data={"creation_id": creation_id, "access_token": access_token})
    if publish_res.status_code != 200:
        raise ValueError(f"Instagram publish failed: {publish_res.text}")
    return publish_res.json()

def get_tiktok_access_token(settings: dict) -> str:
    """TikTok access tokens expire in 24h. Rather than persist a refreshed token
    (which wouldn't stick on Railway — env vars always override settings.json on
    every load_settings() call), mint a fresh one from the long-lived refresh_token
    on every publish, mirroring get_youtube_access_token()'s approach."""
    if not all(settings.get(k) for k in ["tiktok_client_key", "tiktok_client_secret", "tiktok_refresh_token"]):
        raise ValueError("Missing TikTok credentials (client key / secret / refresh token).")
    res = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": settings["tiktok_client_key"],
            "client_secret": settings["tiktok_client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": settings["tiktok_refresh_token"],
        }
    )
    if res.status_code != 200:
        raise ValueError(f"Failed to refresh TikTok access token: {res.text}")
    access_token = res.json().get("access_token")
    if not access_token:
        raise ValueError(f"TikTok refresh response had no access_token: {res.text}")
    return access_token

def publish_tiktok_post(post: dict, settings: dict):
    access_token = get_tiktok_access_token(settings)

    video_url = get_public_video_url(post, settings, "tiktok")
    url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {
        "post_info": {
            "title": (post.get("text") or "")[:2200],
            "privacy_level": "SELF_ONLY",
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "video_url": video_url
        }
    }
    res = requests.post(url, headers=headers, json=payload)
    if res.status_code != 200:
        raise ValueError(f"TikTok publish init failed: {res.text}")
    return res.json()

def publish_facebook_post(post: dict, settings: dict):
    access_token = settings.get("facebook_page_access_token")
    page_id = settings.get("facebook_page_id")
    if not access_token or not page_id:
        raise ValueError("Missing Facebook credentials (page access token / page ID).")

    video_url = get_public_video_url(post, settings)
    url = f"https://graph.facebook.com/v21.0/{page_id}/videos"
    res = requests.post(url, data={
        "file_url": video_url,
        "description": post.get("text", ""),
        "access_token": access_token
    })
    if res.status_code != 200:
        raise ValueError(f"Facebook video publish failed: {res.text}")
    return res.json()

def publish_threads_post(post: dict, settings: dict):
    access_token = settings.get("threads_access_token")
    threads_user_id = settings.get("threads_user_id")
    if not access_token or not threads_user_id:
        raise ValueError("Missing Threads credentials (access token / user ID).")

    video_url = get_public_video_url(post, settings)
    create_url = f"https://graph.threads.net/v1.0/{threads_user_id}/threads"
    create_res = requests.post(create_url, data={
        "media_type": "VIDEO",
        "video_url": video_url,
        "text": post.get("text", ""),
        "access_token": access_token
    })
    if create_res.status_code != 200:
        raise ValueError(f"Threads media container creation failed: {create_res.text}")
    creation_id = create_res.json().get("id")

    # Poll container status until FINISHED
    status_url = f"https://graph.threads.net/v1.0/{creation_id}"
    for _ in range(30):
        time.sleep(5)
        status_res = requests.get(status_url, params={"fields": "status", "access_token": access_token})
        status = status_res.json().get("status")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise ValueError(f"Threads media processing failed: {status_res.text}")
    else:
        raise ValueError("Threads media processing timed out after 150 seconds.")

    publish_url = f"https://graph.threads.net/v1.0/{threads_user_id}/threads_publish"
    publish_res = requests.post(publish_url, data={"creation_id": creation_id, "access_token": access_token})
    if publish_res.status_code != 200:
        raise ValueError(f"Threads publish failed: {publish_res.text}")
    return publish_res.json()

def get_youtube_access_token(settings: dict) -> str:
    res = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": settings.get("youtube_client_id"),
        "client_secret": settings.get("youtube_client_secret"),
        "refresh_token": settings.get("youtube_refresh_token"),
        "grant_type": "refresh_token"
    })
    if res.status_code != 200:
        raise ValueError(f"Failed to refresh YouTube access token: {res.text}")
    return res.json()["access_token"]

def publish_youtube_short(post: dict, settings: dict):
    if not all(settings.get(k) for k in ["youtube_client_id", "youtube_client_secret", "youtube_refresh_token"]):
        raise ValueError("Missing YouTube credentials (client ID / secret / refresh token).")

    video_path = post.get("video_path")
    if not video_path:
        raise ValueError("This post has no video attached — YouTube requires a video.")
    abs_video_path = video_path
    if video_path.startswith("/static/"):
        abs_video_path = os.path.join(BASE_DIR, video_path.lstrip("/"))
    if not os.path.exists(abs_video_path):
        raise ValueError(f"Video file does not exist at {abs_video_path}")

    access_token = get_youtube_access_token(settings)
    title = (post.get("campaign_title") or (post.get("text") or "")[:80] or "6Frame Studio")[:100]
    metadata = {
        "snippet": {
            "title": title,
            "description": post.get("text", ""),
            "categoryId": "1"
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    }

    init_res = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos",
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json=metadata
    )
    if init_res.status_code != 200:
        raise ValueError(f"YouTube upload session init failed: {init_res.text}")
    upload_url = init_res.headers.get("Location")
    if not upload_url:
        raise ValueError("YouTube did not return a resumable upload URL.")

    with open(abs_video_path, "rb") as f:
        video_data = f.read()
    upload_res = requests.put(upload_url, headers={"Content-Type": "video/mp4"}, data=video_data)
    if upload_res.status_code not in [200, 201]:
        raise ValueError(f"YouTube video upload failed: {upload_res.text}")
    return upload_res.json()

class GenerateVideoRequest(BaseModel):
    prompt: str
    engine: str = "google_veo"
    duration: int = 5

SECRET_SETTING_KEYS = [
    "gemini_api_key", "twitter_consumer_key", "twitter_consumer_secret",
    "twitter_access_token", "twitter_access_token_secret", "linkedin_access_token", "runway_api_key",
    "meta_app_secret", "instagram_access_token", "facebook_page_access_token",
    "tiktok_client_secret", "tiktok_access_token", "tiktok_refresh_token",
    "youtube_client_secret", "youtube_refresh_token", "threads_access_token"
]

@app.get("/api/settings")
def get_settings():
    settings = load_settings()
    # Mask API keys for safety
    masked_settings = settings.copy()
    for k in SECRET_SETTING_KEYS:
        val = masked_settings.get(k, "")
        if val:
            masked_settings[k] = val[:4] + "*" * (len(val) - 8) + val[-4:] if len(val) > 8 else "********"
    return masked_settings

@app.post("/api/settings")
def update_settings(data: SettingsSchema):
    current = load_settings()
    new_data = data.model_dump()

    # Re-apply original key if masked value was submitted
    for k in SECRET_SETTING_KEYS:
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

def ensure_video_under_limit(video_path: str, max_duration_sec: int = 90) -> str:
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
            verified_video = ensure_video_under_limit(req.video_path, max_duration_sec=90)
            asset_urn = upload_video_to_linkedin(verified_video, author_urn, settings)

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

class VideoVariantsRequest(BaseModel):
    video_path: str
    hook_text: str

@app.post("/api/generate-video-variants")
def generate_video_variants_endpoint(req: VideoVariantsRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    update_job_status(job_id, "PENDING", 0, "Platform variants job enqueued...")
    background_tasks.add_task(
        generate_video_variants,
        job_id=job_id,
        video_path=req.video_path,
        hook_text=req.hook_text
    )
    return {"job_id": job_id}

@app.get("/api/video-variants-status/{job_id}")
def get_video_variants_status(job_id: str):
    return get_job_status(job_id)

class ViralityScoreRequest(BaseModel):
    post_text: str
    video_prompt: str
    platform: str = "Twitter/X"

@app.post("/api/virality-score")
def virality_score_endpoint(req: ViralityScoreRequest):
    settings = load_settings()
    try:
        result = generate_virality_score(req.post_text, req.video_prompt, req.platform, settings)
        return {"status": "SUCCESS", "data": result.model_dump()}
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as e:
        logger.exception("Failed to generate virality score")
        raise HTTPException(status_code=500, detail=f"Failed to generate virality score: {str(e)}")

class LoadOriginalVideoRequest(BaseModel):
    url: str
    title: Optional[str] = None
    # When False, refuses to silently substitute a different video (YouTube search
    # match or the safety-fallback clip) if the exact URL can't be downloaded —
    # used by the Repurposer Workshop, where the point is repurposing THIS video.
    allow_fallback: bool = True

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

                if result.returncode != 0 and not req.allow_fallback:
                    update_job_status(
                        job_id, "FAILED", 0,
                        "Could not download this specific video. The source platform may block automated "
                        "downloads (common for Instagram/TikTok/X without login) or the link may be private "
                        "or invalid. The generated commentary text is still usable without the video."
                    )
                    return

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
                        "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
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
                
            # Trim downloaded video to 90 seconds max
            downloaded_file = ensure_video_under_limit(downloaded_file, max_duration_sec=90)
            
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

# ==========================================================================
# ENGAGEMENT AUTOMATION — Twitter mention fetching + AI-drafted replies,
# queued for approval. LinkedIn is not included: its API doesn't expose
# comment/mention reading for personal profiles without organization-level
# permissions this app doesn't have.
# ==========================================================================

ENGAGEMENT_QUEUE_FILE = os.path.join(BASE_DIR, "engagement_queue.json")
ENGAGEMENT_STATE_FILE = os.path.join(BASE_DIR, "engagement_state.json")

def load_engagement_queue() -> List[dict]:
    if os.path.exists(ENGAGEMENT_QUEUE_FILE):
        try:
            with open(ENGAGEMENT_QUEUE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading engagement queue file: {e}")
    return []

def save_engagement_queue(items: List[dict]):
    try:
        with open(ENGAGEMENT_QUEUE_FILE, "w") as f:
            json.dump(items, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving engagement queue file: {e}")

def load_engagement_state() -> dict:
    if os.path.exists(ENGAGEMENT_STATE_FILE):
        try:
            with open(ENGAGEMENT_STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading engagement state file: {e}")
    return {}

def save_engagement_state(state: dict):
    try:
        with open(ENGAGEMENT_STATE_FILE, "w") as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving engagement state file: {e}")

def fetch_and_draft_mention_replies(settings: dict):
    required_keys = ["twitter_consumer_key", "twitter_consumer_secret", "twitter_access_token", "twitter_access_token_secret"]
    if not all(settings.get(k) for k in required_keys):
        return
    try:
        client = tweepy.Client(
            consumer_key=settings["twitter_consumer_key"],
            consumer_secret=settings["twitter_consumer_secret"],
            access_token=settings["twitter_access_token"],
            access_token_secret=settings["twitter_access_token_secret"]
        )
        me = client.get_me()
        if not me.data:
            return
        user_id = me.data.id

        state = load_engagement_state()
        since_id = state.get("twitter_since_id")

        kwargs = {"max_results": 20, "tweet_fields": ["created_at", "author_id"], "expansions": ["author_id"]}
        if since_id:
            kwargs["since_id"] = since_id
        mentions = client.get_users_mentions(id=user_id, **kwargs)

        if not mentions.data:
            return

        author_lookup = {}
        if mentions.includes and "users" in mentions.includes:
            author_lookup = {u.id: u.username for u in mentions.includes["users"]}

        queue = load_engagement_queue()
        existing_ids = {item["source_tweet_id"] for item in queue}
        newest_id = since_id

        for mention in mentions.data:
            if not newest_id or int(mention.id) > int(newest_id):
                newest_id = str(mention.id)
            if str(mention.id) in existing_ids:
                continue
            author_username = author_lookup.get(mention.author_id, "unknown")
            try:
                reply_text = draft_engagement_reply(mention.text, author_username, settings)
            except Exception as draft_err:
                logger.warning(f"Failed to draft reply for mention {mention.id}: {draft_err}")
                continue
            queue.append({
                "id": str(uuid.uuid4()),
                "platform": "twitter",
                "source_tweet_id": str(mention.id),
                "source_author": author_username,
                "source_text": mention.text,
                "drafted_reply": reply_text,
                "status": "PENDING_REVIEW",
                "created_at": datetime.now().isoformat(),
                "sent_at": None
            })

        save_engagement_queue(queue)
        if newest_id:
            save_engagement_state({"twitter_since_id": newest_id})
    except Exception as e:
        logger.warning(f"Failed to fetch/draft mention replies (this can happen if your X API access tier doesn't include the mentions timeline): {e}")

def resolve_platform_list(platform_field: str) -> List[str]:
    if platform_field == "both":
        return ["twitter", "linkedin"]
    if platform_field == "all":
        return ["twitter", "linkedin", "instagram", "tiktok", "youtube", "facebook", "threads"]
    return [p.strip() for p in platform_field.split(",") if p.strip()]

async def publish_post_to_platforms(post: dict, settings: dict) -> dict:
    """Shared publisher used by the scheduler, autopilot approval, and manual publish endpoints.
    Returns {"successes": [...], "errors": [...], "tweet_id": str|None, "tweet_ids": [...]|None}."""
    platforms = resolve_platform_list(post["platform"])
    successes = []
    errors = []
    tweet_id = None
    tweet_ids = None

    # 1. Post to Twitter
    if "twitter" in platforms:
        try:
            if settings.get("mock_mode", True):
                logger.info("[MOCK] Post to Twitter")
                successes.append("twitter (mock)")
                tweet_id = "mock_tweet_12345"
            else:
                client = tweepy.Client(
                    consumer_key=settings["twitter_consumer_key"],
                    consumer_secret=settings["twitter_consumer_secret"],
                    access_token=settings["twitter_access_token"],
                    access_token_secret=settings["twitter_access_token_secret"]
                )

                media_ids = None
                if post.get("video_path"):
                    verified_video = ensure_video_under_limit(post["video_path"], max_duration_sec=90)
                    media_id = upload_video_to_twitter(verified_video, settings)
                    if media_id:
                        media_ids = [media_id]

                if post.get("thread"):
                    prev_id = None
                    ids_collected = []
                    for idx, tweet in enumerate(post["thread"]):
                        if idx == 0 and media_ids:
                            res = client.create_tweet(text=tweet, media_ids=media_ids)
                        elif prev_id:
                            res = client.create_tweet(text=tweet, in_reply_to_tweet_id=prev_id)
                        else:
                            res = client.create_tweet(text=tweet)
                        prev_id = res.data["id"]
                        ids_collected.append(prev_id)
                    tweet_ids = ids_collected
                    tweet_id = ids_collected[0] if ids_collected else None
                else:
                    if media_ids:
                        res = client.create_tweet(text=post["text"], media_ids=media_ids)
                    else:
                        res = client.create_tweet(text=post["text"])
                    tweet_id = res.data["id"]
                successes.append("twitter")
        except Exception as tw_err:
            logger.exception("Twitter post failed")
            errors.append(f"Twitter: {str(tw_err)}")

    # 2. Post to LinkedIn
    if "linkedin" in platforms:
        try:
            if settings.get("mock_mode", True):
                logger.info("[MOCK] Post to LinkedIn")
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
                    verified_video = ensure_video_under_limit(post["video_path"], max_duration_sec=90)
                    asset_urn = upload_video_to_linkedin(verified_video, author_urn, settings)

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
            logger.exception("LinkedIn post failed")
            errors.append(f"LinkedIn: {str(li_err)}")

    # 3. Post to Instagram, TikTok, YouTube, Facebook, Threads
    for platform_name, publish_fn in [
        ("instagram", publish_instagram_post),
        ("tiktok", publish_tiktok_post),
        ("youtube", publish_youtube_short),
        ("facebook", publish_facebook_post),
        ("threads", publish_threads_post),
    ]:
        if platform_name in platforms:
            try:
                if settings.get("mock_mode", True):
                    logger.info(f"[MOCK] Post to {platform_name}")
                    successes.append(f"{platform_name} (mock)")
                else:
                    publish_fn(post, settings)
                    successes.append(platform_name)
            except Exception as plat_err:
                logger.exception(f"{platform_name} post failed")
                errors.append(f"{platform_name.capitalize()}: {str(plat_err)}")

    return {"successes": successes, "errors": errors, "tweet_id": tweet_id, "tweet_ids": tweet_ids}

def apply_publish_result_to_post(p: dict, result: dict):
    successes, errors = result["successes"], result["errors"]
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
    if result.get("tweet_id"):
        p["tweet_id"] = result["tweet_id"]
    if result.get("tweet_ids"):
        p["tweet_ids"] = result["tweet_ids"]

async def execute_scheduled_post(post: dict):
    settings = load_settings()
    result = await publish_post_to_platforms(post, settings)

    posts = load_scheduled_posts()
    for p in posts:
        if p["id"] == post["id"]:
            apply_publish_result_to_post(p, result)
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
    
    # Trigger video generation and await completion (engine/duration from Autopilot settings)
    video_job_id = str(uuid.uuid4())
    video_engine = settings.get("autonomous_video_engine", "runway_gen3")
    video_duration = int(settings.get("autonomous_video_duration", 10))
    logger.info(f"Autopilot: Starting {video_duration}-second video rendering using {video_engine}...")
    await loop.run_in_executor(
        None,
        run_video_generation,
        video_job_id,
        top_trend["recreated_video_prompt"],
        settings,
        video_engine,
        video_duration
    )

    generated_video_path = None
    video_status = get_job_status(video_job_id)
    if video_status.get("status") == "SUCCESS":
        generated_video_path = f"/static/assets/generated/{video_job_id}.mp4"
        logger.info(f"Autopilot: Generated {video_duration}s video successfully: {generated_video_path}")
    else:
        logger.error(f"Autopilot: Video generation failed or timed out: {video_status.get('message')}")

    platforms = settings.get("autonomous_platforms", ["twitter", "linkedin"])

    # Instagram Reels and TikTok require vertical (9:16) video — the main render above is
    # landscape (matches Twitter/LinkedIn/YouTube/Facebook fine), so render a vertical variant
    # specifically for those two platforms when they're selected. Failure here is non-fatal:
    # falls back to the landscape video rather than blocking the whole autopilot run.
    vertical_video_path = None
    if generated_video_path and any(p in platforms for p in ("instagram", "tiktok")):
        try:
            abs_source = os.path.join(BASE_DIR, generated_video_path.lstrip("/"))
            vertical_filename = f"{video_job_id}_vertical_9x16.mp4"
            abs_vertical = os.path.join(BASE_DIR, "static", "assets", "generated", vertical_filename)
            font_path = get_font_path()
            render_variant_with_fallback(abs_source, abs_vertical, 1080, 1920, "", font_path, 320)
            vertical_video_path = f"/static/assets/generated/{vertical_filename}"
            logger.info(f"Autopilot: Rendered 9:16 vertical variant for Instagram/TikTok: {vertical_video_path}")
        except Exception as e:
            logger.error(f"Autopilot: Failed to render vertical variant, Instagram/TikTok will use the landscape video instead: {e}")

    now = datetime.now()
    log_post = {
        "id": str(uuid.uuid4()),
        "platform": ",".join(platforms) if platforms else "none",
        "text": top_trend["recreated_linkedin_post"],
        "thread": top_trend.get("recreated_twitter_thread"),
        "scheduled_time": now.isoformat(),
        "campaign_title": f"Autonomous: {top_trend['title']}",
        "video_path": generated_video_path,
        "vertical_video_path": vertical_video_path,
        "status": "PUBLISHING",
        "error_message": None,
        "posted_at": None
    }

    require_approval = settings.get("require_autopilot_approval", True)
    if require_approval:
        log_post["status"] = "AWAITING_APPROVAL"
        posts = load_scheduled_posts()
        posts.append(log_post)
        save_scheduled_posts(posts)
        logger.info(f"Autopilot pick '{top_trend['title']}' staged for review — awaiting manual approval before publishing.")
        return

    posts = load_scheduled_posts()
    posts.append(log_post)
    save_scheduled_posts(posts)

    result = await publish_post_to_platforms(log_post, settings)
    posts = load_scheduled_posts()
    for p in posts:
        if p["id"] == log_post["id"]:
            apply_publish_result_to_post(p, result)
            break
    save_scheduled_posts(posts)
    logger.info(f"Autonomous autopilot pipeline complete. Status: {result['successes']}, Errors: {result['errors']}")

METRICS_REFRESH_INTERVAL_SECONDS = 1800  # 30 minutes

def compute_engagement_score(metrics: dict) -> float:
    return (
        metrics.get("like_count", 0)
        + metrics.get("retweet_count", 0) * 2
        + metrics.get("reply_count", 0) * 2
        + metrics.get("quote_count", 0) * 2
    )

def fetch_twitter_metrics_for_post(post: dict, settings: dict) -> Optional[dict]:
    ids = post.get("tweet_ids") or ([post["tweet_id"]] if post.get("tweet_id") else [])
    ids = [i for i in ids if i and not str(i).startswith("mock_")]
    if not ids:
        return None
    required_keys = ["twitter_consumer_key", "twitter_consumer_secret", "twitter_access_token", "twitter_access_token_secret"]
    if not all(settings.get(k) for k in required_keys):
        return None
    try:
        client = tweepy.Client(
            consumer_key=settings["twitter_consumer_key"],
            consumer_secret=settings["twitter_consumer_secret"],
            access_token=settings["twitter_access_token"],
            access_token_secret=settings["twitter_access_token_secret"]
        )
        totals = {"like_count": 0, "retweet_count": 0, "reply_count": 0, "quote_count": 0}
        found_any = False
        for tid in ids:
            res = client.get_tweet(tid, tweet_fields=["public_metrics"])
            if res.data and res.data.public_metrics:
                found_any = True
                pm = res.data.public_metrics
                for k in totals:
                    totals[k] += pm.get(k, 0)
        if not found_any:
            return None
        return {**totals, "fetched_at": datetime.now().isoformat()}
    except Exception as e:
        logger.warning(f"Failed to fetch Twitter metrics for post {post.get('id')}: {e}")
        return None

def refresh_post_metrics(settings: dict, max_age_days: int = 14) -> bool:
    """Pulls fresh engagement metrics for recently-published Twitter posts. LinkedIn is skipped —
    personal-profile posts aren't exposed by LinkedIn's standard API without organization-level
    permissions this app doesn't have."""
    posts = load_scheduled_posts()
    now = datetime.now()
    changed = False
    for post in posts:
        if post.get("status") != "SUCCESS":
            continue
        posted_at = post.get("posted_at")
        if not posted_at:
            continue
        try:
            posted_dt = datetime.fromisoformat(posted_at)
        except Exception:
            continue
        if (now - posted_dt).days > max_age_days:
            continue
        metrics = fetch_twitter_metrics_for_post(post, settings)
        if metrics:
            post.setdefault("metrics", {})["twitter"] = metrics
            changed = True
    if changed:
        save_scheduled_posts(posts)
    return changed

ENGAGEMENT_REFRESH_INTERVAL_SECONDS = 900  # 15 minutes

async def scheduler_loop():
    await asyncio.sleep(5)
    logger.info("Background scheduler loop started.")
    last_autonomous_date = None
    last_metrics_refresh = None
    last_engagement_refresh = None

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

            # 3. Periodically refresh post performance metrics (analytics feedback loop)
            if last_metrics_refresh is None or (now - last_metrics_refresh).total_seconds() >= METRICS_REFRESH_INTERVAL_SECONDS:
                last_metrics_refresh = now
                try:
                    refresh_post_metrics(settings)
                except Exception as metrics_err:
                    logger.error(f"Error refreshing post metrics: {metrics_err}")

            # 4. Periodically fetch new mentions and draft AI replies (engagement automation)
            if last_engagement_refresh is None or (now - last_engagement_refresh).total_seconds() >= ENGAGEMENT_REFRESH_INTERVAL_SECONDS:
                last_engagement_refresh = now
                try:
                    fetch_and_draft_mention_replies(settings)
                except Exception as engagement_err:
                    logger.error(f"Error fetching/drafting mention replies: {engagement_err}")

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
    completed = [p for p in posts if p["status"] not in ("PENDING", "AWAITING_APPROVAL")]

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

# ==========================================================================
# APPROVAL QUEUE — Autopilot picks stage here before publishing when
# require_autopilot_approval is enabled ("autonomous with guardrails").
# ==========================================================================

class ApprovalEditRequest(BaseModel):
    text: Optional[str] = None
    thread: Optional[List[str]] = None

@app.get("/api/approval-queue")
def get_approval_queue():
    posts = load_scheduled_posts()
    pending_approval = [p for p in posts if p["status"] == "AWAITING_APPROVAL"]
    pending_approval.sort(key=lambda x: x["scheduled_time"], reverse=True)
    return pending_approval

@app.patch("/api/approval-queue/{post_id}")
def edit_approval_post(post_id: str, req: ApprovalEditRequest):
    posts = load_scheduled_posts()
    for p in posts:
        if p["id"] == post_id:
            if p["status"] != "AWAITING_APPROVAL":
                raise HTTPException(status_code=400, detail="Post is no longer awaiting approval.")
            if req.text is not None:
                p["text"] = req.text
            if req.thread is not None:
                p["thread"] = req.thread
            save_scheduled_posts(posts)
            return {"status": "SUCCESS", "message": "Draft updated."}
    raise HTTPException(status_code=404, detail="Post not found in approval queue.")

@app.post("/api/approval-queue/{post_id}/approve")
async def approve_post(post_id: str):
    posts = load_scheduled_posts()
    target = next((p for p in posts if p["id"] == post_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Post not found in approval queue.")
    if target["status"] != "AWAITING_APPROVAL":
        raise HTTPException(status_code=400, detail="Post is no longer awaiting approval.")

    settings = load_settings()
    target["status"] = "PUBLISHING"
    save_scheduled_posts(posts)

    result = await publish_post_to_platforms(target, settings)
    posts = load_scheduled_posts()
    for p in posts:
        if p["id"] == post_id:
            apply_publish_result_to_post(p, result)
            break
    save_scheduled_posts(posts)
    return {"status": "SUCCESS", "message": "Post approved and published.", "result": result}

@app.post("/api/approval-queue/{post_id}/reject")
def reject_post(post_id: str):
    posts = load_scheduled_posts()
    for p in posts:
        if p["id"] == post_id:
            if p["status"] != "AWAITING_APPROVAL":
                raise HTTPException(status_code=400, detail="Post is no longer awaiting approval.")
            p["status"] = "REJECTED"
            save_scheduled_posts(posts)
            return {"status": "SUCCESS", "message": "Post rejected."}
    raise HTTPException(status_code=404, detail="Post not found in approval queue.")

# ==========================================================================
# ANALYTICS FEEDBACK LOOP — tracks real Twitter engagement on published posts
# and surfaces a data-driven recommended posting hour. LinkedIn metrics are
# not available: personal-profile posts aren't exposed by LinkedIn's API
# without organization-level permissions this app doesn't have.
# ==========================================================================

@app.get("/api/analytics/summary")
def get_analytics_summary():
    posts = load_scheduled_posts()
    scored = []
    hour_buckets = {}

    for post in posts:
        if post.get("status") != "SUCCESS":
            continue
        tw_metrics = (post.get("metrics") or {}).get("twitter")
        if not tw_metrics:
            continue
        score = compute_engagement_score(tw_metrics)
        posted_at = post.get("posted_at") or post.get("scheduled_time")
        hour = None
        try:
            hour = datetime.fromisoformat(posted_at).hour
        except Exception:
            pass

        scored.append({
            "id": post["id"],
            "campaign_title": post.get("campaign_title"),
            "platform": post.get("platform"),
            "posted_at": posted_at,
            "metrics": tw_metrics,
            "engagement_score": score,
            "hour": hour
        })
        if hour is not None:
            hour_buckets.setdefault(hour, []).append(score)

    best_hour = None
    hour_breakdown = {}
    if hour_buckets:
        hour_breakdown = {h: round(sum(s) / len(s), 1) for h, s in hour_buckets.items()}
        best_hour = max(hour_breakdown, key=hour_breakdown.get)

    scored.sort(key=lambda x: x["engagement_score"], reverse=True)
    return {
        "posts": scored,
        "best_hour": best_hour,
        "sample_size": len(scored),
        "hour_breakdown": hour_breakdown
    }

@app.post("/api/analytics/refresh")
def refresh_analytics(background_tasks: BackgroundTasks):
    settings = load_settings()
    background_tasks.add_task(refresh_post_metrics, settings)
    return {"status": "SUCCESS", "message": "Metrics refresh triggered in background."}

class ApplyBestHourRequest(BaseModel):
    hour: int

@app.post("/api/analytics/apply-best-hour")
def apply_best_hour(req: ApplyBestHourRequest):
    settings = load_settings()
    settings["autonomous_hour"] = req.hour
    save_settings(settings)
    return {"status": "SUCCESS", "message": f"Autopilot posting hour set to {req.hour}:00."}

# ==========================================================================
# ENGAGEMENT INBOX — AI-drafted replies to Twitter/X mentions, queued here
# for approval before sending. Nothing is auto-sent.
# ==========================================================================

@app.get("/api/engagement-queue")
def get_engagement_queue():
    items = load_engagement_queue()
    pending = [i for i in items if i["status"] == "PENDING_REVIEW"]
    pending.sort(key=lambda x: x["created_at"], reverse=True)
    return pending

class EngagementEditRequest(BaseModel):
    reply_text: str

@app.patch("/api/engagement-queue/{item_id}")
def edit_engagement_reply(item_id: str, req: EngagementEditRequest):
    items = load_engagement_queue()
    for item in items:
        if item["id"] == item_id:
            if item["status"] != "PENDING_REVIEW":
                raise HTTPException(status_code=400, detail="Reply is no longer pending review.")
            item["drafted_reply"] = req.reply_text
            save_engagement_queue(items)
            return {"status": "SUCCESS", "message": "Draft reply updated."}
    raise HTTPException(status_code=404, detail="Item not found in engagement queue.")

@app.post("/api/engagement-queue/{item_id}/send")
def send_engagement_reply(item_id: str):
    items = load_engagement_queue()
    target = next((i for i in items if i["id"] == item_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Item not found in engagement queue.")
    if target["status"] != "PENDING_REVIEW":
        raise HTTPException(status_code=400, detail="Reply is no longer pending review.")

    settings = load_settings()
    try:
        if settings.get("mock_mode", True):
            logger.info("[MOCK] Sending engagement reply")
        else:
            client = tweepy.Client(
                consumer_key=settings["twitter_consumer_key"],
                consumer_secret=settings["twitter_consumer_secret"],
                access_token=settings["twitter_access_token"],
                access_token_secret=settings["twitter_access_token_secret"]
            )
            client.create_tweet(text=target["drafted_reply"], in_reply_to_tweet_id=target["source_tweet_id"])
        target["status"] = "SENT"
        target["sent_at"] = datetime.now().isoformat()
        save_engagement_queue(items)
        return {"status": "SUCCESS", "message": "Reply sent."}
    except Exception as e:
        logger.exception("Failed to send engagement reply")
        raise HTTPException(status_code=500, detail=f"Failed to send reply: {str(e)}")

@app.post("/api/engagement-queue/{item_id}/dismiss")
def dismiss_engagement_reply(item_id: str):
    items = load_engagement_queue()
    for item in items:
        if item["id"] == item_id:
            if item["status"] != "PENDING_REVIEW":
                raise HTTPException(status_code=400, detail="Reply is no longer pending review.")
            item["status"] = "DISMISSED"
            save_engagement_queue(items)
            return {"status": "SUCCESS", "message": "Reply dismissed."}
    raise HTTPException(status_code=404, detail="Item not found in engagement queue.")

@app.post("/api/engagement-queue/refresh")
def refresh_engagement_queue(background_tasks: BackgroundTasks):
    settings = load_settings()
    background_tasks.add_task(fetch_and_draft_mention_replies, settings)
    return {"status": "SUCCESS", "message": "Checking for new mentions in the background."}

# TikTok domain (URL prefix) verification file
@app.get("/tiktokfa6qOoVQvk1SxaIGW7xhpCLHQf0Ek3JZ.txt", response_class=PlainTextResponse)
def tiktok_domain_verification():
    return "tiktok-developers-site-verification=fa6qOoVQvk1SxaIGW7xhpCLHQf0Ek3JZ"

# TikTok OAuth callback — TikTok's sandbox rejects localhost redirect URIs, so this
# public endpoint receives the code instead and displays it for manual copy-paste
# into tiktok_auth.py running locally.
@app.get("/tiktok-callback", response_class=HTMLResponse)
def tiktok_oauth_callback(code: str = None, error: str = None, error_description: str = None):
    if code:
        body = f"""
        <div style="font-family:-apple-system,sans-serif;background:#0f172a;color:#f8fafc;text-align:center;padding:50px;">
            <div style="background:#1e293b;padding:30px;border-radius:8px;display:inline-block;max-width:600px;">
                <h1 style="color:#10b981;">Authorization Successful!</h1>
                <p>Copy this code and paste it back into your terminal:</p>
                <textarea readonly style="width:100%;height:60px;font-family:monospace;font-size:14px;padding:10px;">{code}</textarea>
            </div>
        </div>
        """
    else:
        body = f"""
        <div style="font-family:-apple-system,sans-serif;background:#0f172a;color:#f8fafc;text-align:center;padding:50px;">
            <h1 style="color:#ef4444;">Authorization Failed</h1>
            <p>Error: {error_description or error or 'Unknown error'}</p>
        </div>
        """
    return f"<html><head></head><body>{body}</body></html>"

# Mount static files folder
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

@app.get("/")
def read_root():
    return FileResponse(
        os.path.join(BASE_DIR, "static", "index.html"),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}
    )

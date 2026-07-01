import os
import time
import json
import logging
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orchestrator")

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

# Structured output schemas using Pydantic
class TwitterThread(BaseModel):
    tweets: List[str] = Field(description="A list of 1 to 3 tweets representing a thread. Each tweet must be strictly under 280 characters.")

class SocialCopyResponse(BaseModel):
    linkedin_post: str = Field(description="A professional, behind-the-scenes LinkedIn post. Detail the AI tools, rendering techniques, and styling.")
    twitter_post: str = Field(description="A single punchy tweet (under 280 characters) to summarize the video.")
    twitter_thread: List[str] = Field(description="A list of 2 to 3 tweets representing a thread. Each tweet must be strictly under 280 characters. The first tweet should contain a strong hook.")
    instagram_caption: str = Field(description="An aesthetic, visually-driven Instagram caption. Under 150 words. Focus on mood, cinematography, and styling.")
    suggested_hashtags: List[str] = Field(description="5 to 8 highly relevant hashtags (e.g. #AIArt, #Sora, #RunwayML, #6FrameStudio).")

class ContextBrief(BaseModel):
    video_summary: str = Field(description="Detailed description of what happens in the video (visuals, subjects, motions, style, transitions).")
    key_themes: List[str] = Field(description="List of core thematic concepts represented in the video.")
    brand_alignment: str = Field(description="How the video aligns with the brand context extracted from the URL.")
    visual_style_tags: List[str] = Field(description="Keywords describing the visual style (e.g. cinematic, cyberpunk, photorealistic, abstract).")
    recreation_motion_prompt: str = Field(description="A detailed, optimized Text-to-Video motion prompt for Runway Gen-3 or Google Veo 3.1 to recreate the visual scene, subject, lighting, and camera movement.")

class ViralConcept(BaseModel):
    platform: str = Field(description="Platform name, e.g. Reddit, YouTube, Twitter/X, LinkedIn, Instagram")
    url: str = Field(description="URL to the post, video or reference search query found")
    author: str = Field(description="The username, channel name or author of the content")
    title: str = Field(description="Summary or title of the trending/viral content")
    viral_metrics: str = Field(description="Engagement metrics, e.g. views, likes, retweets, comments, or general virality notes")
    original_concept: str = Field(description="Detailed description of the original video contents, editing technique, and visual style")
    studio_adaptation_concept: str = Field(description="How 6Frame Studio can recreate this cinematic/VFX concept with our own style")
    recreated_video_prompt: str = Field(description="The Image-to-Video motion prompt for Runway Gen-3/Kling/Luma to render 6Frame Studio's version")
    recreated_linkedin_post: str = Field(description="Staged B2B LinkedIn post copy for 6Frame Studio")
    recreated_twitter_thread: List[str] = Field(description="Staged Twitter thread copy for 6Frame Studio (2-3 tweets, under 280 chars each)")
    recreated_instagram_caption: str = Field(description="Staged Instagram caption copy for 6Frame Studio with hashtags")
    original_post_text: str = Field(description="Reconstructed or summarized text/copy of the original viral post")


class ViralSearchResponse(BaseModel):
    trends: List[ViralConcept] = Field(description="A list of exactly 10 viral video concepts found on social media from the last 24 hours.")

# In-memory job status cache
jobs_status: Dict[str, Dict[str, Any]] = {}

def get_job_status(job_id: str) -> Dict[str, Any]:
    return jobs_status.get(job_id, {"status": "NOT_FOUND"})

def update_job_status(job_id: str, status: str, progress: int, message: str, result: Any = None):
    jobs_status[job_id] = {
        "status": status,
        "progress": progress,
        "message": message,
        "result": result,
        "updated_at": time.time()
    }
    logger.info(f"Job {job_id} [{progress}%]: {message}")

def run_multi_agent_pipeline(
    job_id: str,
    video_path: str,
    website_url: str,
    settings: Dict[str, Any]
):
    try:
        api_key = settings.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            update_job_status(job_id, "FAILED", 0, "Missing Gemini API Key. Please configure it in Settings.")
            return

        # Initialize GenAI client
        update_job_status(job_id, "PROCESSING", 10, "Initializing Gemini Client...")
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=180000)
        )

        # Step 1: Upload Video file to Gemini File API
        update_job_status(job_id, "PROCESSING", 20, "Uploading video to Gemini API (this may take a minute for larger files)...")
        
        # Verify file exists
        if not os.path.exists(video_path):
            update_job_status(job_id, "FAILED", 0, f"Video file not found at path: {video_path}")
            return
            
        video_file = client.files.upload(file=video_path)
        
        # Step 2: Poll file processing status
        update_job_status(job_id, "PROCESSING", 30, "Waiting for Gemini to process the video asset...")
        while video_file.state.name == "PROCESSING":
            time.sleep(5)
            video_file = client.files.get(name=video_file.name)
            
        if video_file.state.name == "FAILED":
            update_job_status(job_id, "FAILED", 0, "Gemini video processing failed.")
            return

        update_job_status(job_id, "PROCESSING", 45, "Video processed. Querying Context Agent (Gemini 2.5 Pro)...")

        # Step 3: Call Context Agent (Gemini 2.5 Pro)
        context_prompt = f"""
        You are the Research & Context Agent for 6Frame Studio.
        We have uploaded a video asset: {video_file.name}.
        The corresponding website/brand context is: {website_url}.

        Analyze this video file and the website context. Perform a deep multimodal analysis of the video frames, pacing, mood, and characters.
        Extract a unified context brief outlining:
        1. A description of the visuals and motion.
        2. The key aesthetic themes.
        3. How it aligns with 6Frame Studio's high-end, cinematic, AI-generative mission.
        4. Key visual style descriptors.
        5. A detailed, optimized Text-to-Video motion prompt (recreation_motion_prompt) for Runway Gen-3 or Google Veo 3.1 to recreate the visual scene, subject, lighting, and camera movement.
        """

        context_response = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=[video_file, context_prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ContextBrief,
                system_instruction="You are a cinematic research assistant that extracts visual details from video files and websites."
            )
        )
        
        try:
            brief: ContextBrief = context_response.parsed
        except Exception as e:
            logger.error(f"Failed to parse Context Brief: {e}. Raw text: {context_response.text}")
            update_job_status(job_id, "FAILED", 0, "Failed to parse context brief from Gemini Pro.")
            return

        update_job_status(job_id, "PROCESSING", 65, "Context Brief generated. Invoking Platform Copy Agents (Gemini 2.5 Flash)...")

        # Step 4: Call Copy Agents (Gemini 2.5 Flash) using Context Brief and brand settings
        brand_voice = settings.get("brand_voice", "Cinematic, minimalist, premium, technical yet artistic.")
        copy_prompt = f"""
        You are the Platform Copy Agent for 6Frame Studio.
        Based on the following Context Brief and Brand Voice guidelines, generate social media copy.

        ### BRAND VOICE GUIDELINES
        {brand_voice}

        ### CONTEXT BRIEF
        - Video Summary: {brief.video_summary}
        - Key Themes: {", ".join(brief.key_themes)}
        - Brand Alignment: {brief.brand_alignment}
        - Visual Style: {", ".join(brief.visual_style_tags)}

        ### TARGET OUTPUTS REQUIRED
        1. **LinkedIn Post**: Behind-the-scenes breakdown, focusing on the AI generation tools (Sora, Runway Gen-3, Kling, Midjourney), rendering techniques, artistic direction, and production insights. Professional and sophisticated.
        2. **Twitter/X Single Post**: Under 280 characters, highly hooky, driving engagement.
        3. **Twitter/X Thread**: A sequence of 2-3 tweets expanding on the cinematic process. Each tweet must be under 280 characters.
        4. **Instagram Caption**: Mood-oriented, visual, under 150 words, clean style, matching the video's aesthetic.
        5. **Suggested Hashtags**: Relevant industry and brand hashtags.

        ### POST FORMATTING AND SPACING RULES (CRITICAL)
        - **Double Line Breaks**: You MUST separate all paragraphs and bullet groups with a blank line (double newlines `\n\n`). Do not write long blocks of single-spaced text.
        - **NO ASTERISKS / NO BOLD**: Do NOT use markdown bold asterisks (`**`) or headers in the post text. All text must be clean plain text so it displays properly on Twitter and LinkedIn.
        - **Social handles / links**: Always credit the original creator using their actual social media handle (e.g. @CuriousRefuge) or a link to their channel/profile.
        - **Lists**: Format list items with clear dashes (`- item`) and separate the list block from paragraphs with empty lines.
        """

        copy_response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[copy_prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SocialCopyResponse,
                system_instruction="You are an expert social media copywriter specialized in marketing high-end cinematic AI assets."
            )
        )

        try:
            copy_results: SocialCopyResponse = copy_response.parsed
        except Exception as e:
            logger.error(f"Failed to parse Social Copy: {e}. Raw text: {copy_response.text}")
            update_job_status(job_id, "FAILED", 0, "Failed to parse social copy from Gemini Flash.")
            return

        # Step 5: Clean up video from Gemini File API
        update_job_status(job_id, "PROCESSING", 90, "Cleaning up assets and finalizing...")
        try:
            client.files.delete(name=video_file.name)
        except Exception as cleanup_err:
            logger.warning(f"Could not delete temporary file {video_file.name}: {cleanup_err}")

        # Success!
        final_result = {
            "brief": brief.model_dump(),
            "copy": copy_results.model_dump()
        }
        update_job_status(job_id, "SUCCESS", 100, "Multi-agent pipeline complete!", result=final_result)

    except Exception as e:
        logger.exception("Error in multi-agent pipeline")
        update_job_status(job_id, "FAILED", 0, f"Pipeline execution failed: {str(e)}")

def check_url_valid(url: str) -> bool:
    import subprocess
    if not url or not url.startswith("http"):
        return False
    if any(p in url for p in ["example", "status/1234", "DigitalDreams", "AIVoyager", "ChronoDrifter", "abcdef", "examplecyber", "dQw4w9WgXcQ", "watch?v=12345"]):
        return False
    cmd = [
        get_binary_path("yt-dlp"),
        "--simulate",
        url
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        return res.returncode == 0
    except:
        return False

def resolve_trend_mock_url(title: str) -> str:
    import subprocess
    cmd = [
        get_binary_path("yt-dlp"),
        "--no-playlist",
        "--flat-playlist",
        "--print", "webpage_url",
        f"ytsearch1:{title}"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode == 0 and res.stdout.strip():
            url = res.stdout.strip()
            logger.info(f"Resolved trend title '{title}' to real video URL: {url}")
            return url
    except Exception as e:
        logger.error(f"Failed resolving mock URL for trend: {title}. Error: {e}")
    return "https://www.youtube.com/watch?v=kQD2bBnb-Yc"

def fetch_realtime_news_context() -> str:
    import xml.etree.ElementTree as ET
    import requests
    url = "https://news.google.com/rss/search?q=AI+filmmaking+OR+AI+video+OR+Sora+OR+Runway+Gen-3+OR+Veo+OR+Kling&hl=en-US&gl=US&ceid=US:en"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            items = root.findall(".//item")
            lines = []
            for item in items[:15]:
                title = item.find("title").text
                link = item.find("link").text
                pub_date = item.find("pubDate").text
                lines.append(f"- Title: {title}\n  Published: {pub_date}\n  URL: {link}")
            return "\n".join(lines)
    except Exception as e:
        logger.error(f"Error fetching Google News context: {e}")
    return ""

def run_live_trend_scanner(
    job_id: str,
    settings: Dict[str, Any]
):
    try:
        api_key = settings.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            update_job_status(job_id, "FAILED", 0, "Missing Gemini API Key. Please configure it in Settings.")
            return

        update_job_status(job_id, "PROCESSING", 10, "Fetching real-time social trends and AI news feeds...")
        news_context = fetch_realtime_news_context()

        update_job_status(job_id, "PROCESSING", 30, "Analyzing social trends context via Gemini Pro...")
        
        search_prompt = f"""
        Analyze the following real-time AI news and viral social media trends context from the last 24 hours:

        {news_context}

        Based on this context, identify 10 highly viral or trending AI video concepts and stories. Focus specifically on categories related to 6Frame Studio's niche:
        - AI filmmaking and cinematic AI trailers (e.g. Sora, Runway Gen-3, Kling, Luma, Veo)
        - AI logo animations, visual loops, and motion design
        - AI music videos and audio-visual experiments

        For each of the 10 trends identified, describe:
        1. The platform where it was found (Reddit, YouTube, or public news)
        2. The direct URL from the context or a related watch link. This URL MUST be a real, valid watch URL from the context. Do NOT generate mock usernames or placeholder links (like 'examplecyber', 'status/12345').
        3. The author or creator's username
        4. The title/description of the video
        5. Viral metrics (views, upvotes, or comments)
        6. A description of the visual style and why it went viral
        """

        # Query Gemini 2.5 Flash using the fetched context (much faster than Pro, avoiding timeouts)
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=360000) # Prevents indefinite hangs (360s safe limit)
        )
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=search_prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a real-time social media trend researcher specialized in finding trending cinematic AI contents."
            )
        )
        search_text = response.text

        update_job_status(job_id, "PROCESSING", 60, "Adapting viral concepts for 6Frame Studio (generating structured copies)...")
        
        adaptation_prompt = f"""
        You are a social media copywriter for 6Frame Studio.
        We have researched the top 10 viral AI video trends from the last 24 hours:

        {search_text}

        For each of these 10 trending concepts:
        1. Keep the platform, author, title, and viral metrics. Ensure the URL is kept as a valid direct HTTP/HTTPS link to the original video source (do NOT change it to keywords or text descriptions).
        2. Describe the original concept and visual technique.
        3. Explain how 6Frame Studio can recreate this viral concept using their premium, cinematic, artistic style.
        4. Write the exact Image-to-Video motion prompt to render our adapted version.
        5. Draft the tailored social posts representing 6Frame Studio's recreation (recreated_linkedin_post, recreated_twitter_thread, recreated_instagram_caption).
        6. Draft the original_post_text summarizing/reconstructing what the original creator's post said.

        ### POST FORMATTING AND SPACING RULES (CRITICAL)
        - **Double Line Breaks**: You MUST separate all paragraphs, bullet point blocks, and commentary highlights with an empty line (double newlines `\n\n`). Do not write long blocks of single-spaced text.
        - **NO ASTERISKS / NO BOLD**: Do NOT use markdown bold asterisks (`**`) or headers in the post text. All text must be clean plain text so it displays properly on Twitter and LinkedIn.
        - **Social handles / links**: Always credit the original creator using their actual social media handle (e.g. @CuriousRefuge) or a link to their channel/profile.
        - **Bullet Points**: Format lists with clean bullet dashes (`- item`) and leave spaces above and below list blocks.

        Return the results matching the required JSON schema structure.
        """

        # Step 2: Structure as JSON using Gemini 2.5 Flash
        copy_response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=adaptation_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ViralSearchResponse,
                system_instruction="You are an expert social media copywriter specialized in marketing high-end cinematic AI assets."
            )
        )

        update_job_status(job_id, "PROCESSING", 90, "Resolving search links and verifying video availability...")
        try:
            results: ViralSearchResponse = copy_response.parsed
        except Exception as e:
            logger.error(f"Failed to parse Viral Search results: {e}. Raw text: {copy_response.text}")
            update_job_status(job_id, "FAILED", 0, "Failed to parse structured JSON from Gemini Pro.")
            return

        for trend in results.trends:
            if not check_url_valid(trend.url):
                logger.info(f"Invalid or mock URL detected: {trend.url}. Resolving dynamically for: {trend.title}")
                trend.url = resolve_trend_mock_url(trend.title)

        final_result = {
            "trends": [trend.model_dump() for trend in results.trends]
        }
        update_job_status(job_id, "SUCCESS", 100, "Live trend search complete!", result=final_result)

    except Exception as e:
        logger.exception("Error in live trend scanner")
        update_job_status(job_id, "FAILED", 0, f"Search pipeline failed: {str(e)}")

def run_runway_rendering(job_id: str, prompt: str, settings: Dict[str, Any], duration: int = 5):
    try:
        api_key = settings.get("runway_api_key")
        if not api_key:
            update_job_status(job_id, "FAILED", 0, "Missing Runway API Key. Please configure it in Settings.")
            return

        import requests
        import subprocess
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "X-Runway-Version": "2024-11-06",
            "Content-Type": "application/json"
        }
        
        assets_dir = os.path.join(BASE_DIR, "static", "assets", "generated")
        os.makedirs(assets_dir, exist_ok=True)
        dest_path = os.path.join(assets_dir, f"{job_id}.mp4")

        if duration == 30:
            update_job_status(job_id, "PROCESSING", 5, "Initializing 30s cinematic cut (3 parallel tasks)...")
            
            # Formulate the 3 prompts for the cuts
            prompts = [
                f"{prompt}, cinematic wide establishing shot",
                f"{prompt}, medium camera shot, panning side angle",
                f"{prompt}, cinematic close-up shot, detail focus"
            ]
            
            task_ids = []
            url = "https://api.dev.runwayml.com/v1/text_to_video"
            
            for idx, p in enumerate(prompts):
                payload = {
                    "model": "gen4.5",
                    "promptText": p,
                    "ratio": "1280:720",
                    "duration": 10
                }
                update_job_status(job_id, "PROCESSING", 10 + (idx * 5), f"Submitting scene {idx + 1}/3 to Runway...")
                response = requests.post(url, headers=headers, json=payload)
                if response.status_code not in [200, 201, 202]:
                    update_job_status(job_id, "FAILED", 0, f"Runway API Error on scene {idx + 1}: {response.text}")
                    return
                data = response.json()
                tid = data.get("id")
                if not tid:
                    update_job_status(job_id, "FAILED", 0, f"No task ID returned for scene {idx + 1}.")
                    return
                task_ids.append(tid)

            update_job_status(job_id, "PROCESSING", 25, "All scenes queued. Polling status in parallel...")
            
            # Polling loop
            poll_count = 0
            statuses = ["PENDING", "PENDING", "PENDING"]
            urls = [f"https://api.dev.runwayml.com/v1/tasks/{tid}" for tid in task_ids]
            video_urls = [None, None, None]
            
            while True:
                time.sleep(5)
                poll_count += 1
                progress = min(25 + (poll_count * 3), 90)
                
                all_done = True
                any_failed = False
                fail_msg = ""
                
                for idx, status_url in enumerate(urls):
                    if statuses[idx] in ["SUCCEEDED", "FAILED"]:
                        continue
                    
                    try:
                        res = requests.get(status_url, headers=headers)
                        if res.status_code == 200:
                            task_data = res.json()
                            status = task_data.get("status")
                            statuses[idx] = status
                            
                            if status == "SUCCEEDED":
                                outputs = task_data.get("output", [])
                                if outputs:
                                    video_urls[idx] = outputs[0]
                                else:
                                    statuses[idx] = "FAILED"
                                    any_failed = True
                                    fail_msg = f"Scene {idx + 1} returned empty output."
                            elif status == "FAILED":
                                any_failed = True
                                error_msg = task_data.get("error", "Unknown Runway API error")
                                fail_msg = f"Scene {idx + 1} failed: {error_msg}"
                        else:
                            logger.error(f"Error polling scene {idx + 1}: {res.text}")
                    except Exception as poll_err:
                        logger.error(f"Connection error on scene {idx + 1}: {poll_err}")
                
                # Check overall status
                if any_failed:
                    update_job_status(job_id, "FAILED", 0, fail_msg)
                    return
                
                all_done = all(s == "SUCCEEDED" for s in statuses)
                if all_done:
                    break
                
                # Display status message in UI
                msg = f"Rendering: Scene 1 ({statuses[0]}), Scene 2 ({statuses[1]}), Scene 3 ({statuses[2]})"
                update_job_status(job_id, "PROCESSING", progress, msg)
                
            # Download and stitch clips
            update_job_status(job_id, "PROCESSING", 92, "Downloading scene clips...")
            clip_paths = []
            
            for idx, vurl in enumerate(video_urls):
                update_job_status(job_id, "PROCESSING", 92 + idx, f"Downloading clip {idx + 1}/3...")
                download_response = requests.get(vurl)
                if download_response.status_code != 200:
                    update_job_status(job_id, "FAILED", 0, f"Failed to download clip {idx + 1}. HTTP status: {download_response.status_code}")
                    return
                
                clip_path = os.path.join(assets_dir, f"{job_id}_clip_{idx + 1}.mp4")
                with open(clip_path, "wb") as f:
                    f.write(download_response.content)
                clip_paths.append(clip_path)

            update_job_status(job_id, "PROCESSING", 96, "Stitching 3 scenes together using ffmpeg...")
            
            # Write ffmpeg concat file
            concat_file_path = os.path.join(assets_dir, f"concat_{job_id}.txt")
            with open(concat_file_path, "w") as cf:
                for cp in clip_paths:
                    cf.write(f"file '{cp}'\n")
            
            try:
                # Concatenate videos without re-encoding
                subprocess.run([
                    get_binary_path("ffmpeg"), "-y", "-f", "concat", "-safe", "0", 
                    "-i", concat_file_path, "-c", "copy", dest_path
                ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except Exception as ffmpeg_err:
                logger.exception("ffmpeg concatenation failed")
                update_job_status(job_id, "FAILED", 0, f"Failed to stitch video clips: {str(ffmpeg_err)}")
                return
            finally:
                # Clean up temporary files
                if os.path.exists(concat_file_path):
                    os.remove(concat_file_path)
                for cp in clip_paths:
                    if os.path.exists(cp):
                        os.remove(cp)

        else:
            # Single clip generation (5s or 10s)
            update_job_status(job_id, "PROCESSING", 10, f"Submitting video task to Runway ({duration}s)...")
            
            url = "https://api.dev.runwayml.com/v1/text_to_video"
            payload = {
                "model": "gen4.5",
                "promptText": prompt,
                "ratio": "1280:720",
                "duration": duration
            }
            
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code not in [200, 201, 202]:
                update_job_status(job_id, "FAILED", 0, f"Runway API Error: {response.text}")
                return

            data = response.json()
            task_id = data.get("id")
            if not task_id:
                update_job_status(job_id, "FAILED", 0, "No task ID returned from Runway API.")
                return

            update_job_status(job_id, "PROCESSING", 25, "Runway task queued. Polling status...")

            poll_count = 0
            status_url = f"https://api.dev.runwayml.com/v1/tasks/{task_id}"
            
            while True:
                time.sleep(5)
                poll_count += 1
                progress = min(25 + (poll_count * 4), 95)
                
                try:
                    res = requests.get(status_url, headers=headers)
                    if res.status_code == 200:
                        task_data = res.json()
                        status = task_data.get("status")
                        
                        if status == "SUCCEEDED":
                            outputs = task_data.get("output", [])
                            if not outputs:
                                update_job_status(job_id, "FAILED", 0, "Runway task succeeded but returned empty output.")
                                return
                            video_url = outputs[0]
                            break
                        elif status == "FAILED":
                            error_msg = task_data.get("error", "Unknown Runway API error")
                            update_job_status(job_id, "FAILED", 0, f"Runway Task Failed: {error_msg}")
                            return
                        else:
                            msg = f"Runway status: {status}..."
                            update_job_status(job_id, "PROCESSING", progress, msg)
                    else:
                        logger.error(f"Error polling Runway status: {res.text}")
                except Exception as poll_err:
                    logger.error(f"Error connecting to Runway polling endpoint: {poll_err}")

            update_job_status(job_id, "PROCESSING", 98, "Downloading video file from Runway...")
            
            download_response = requests.get(video_url)
            if download_response.status_code != 200:
                update_job_status(job_id, "FAILED", 0, f"Failed to download video from Runway. HTTP status: {download_response.status_code}")
                return

            with open(dest_path, "wb") as f:
                f.write(download_response.content)

        # Success!
        video_web_path = f"/static/assets/generated/{job_id}.mp4"
        update_job_status(
            job_id, 
            "SUCCESS", 
            100, 
            "Runway rendering complete!", 
            result={"video_path": video_web_path}
        )

    except Exception as e:
        logger.exception("Error in Runway rendering")
        update_job_status(job_id, "FAILED", 0, f"Runway generation failed: {str(e)}")

def run_video_generation(
    job_id: str,
    prompt: str,
    settings: Dict[str, Any],
    engine: str = "google_veo",
    duration: int = 5
):
    if engine == "runway_gen3":
        run_runway_rendering(job_id, prompt, settings, duration)
        return

    try:
        api_key = settings.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            update_job_status(job_id, "FAILED", 0, "Missing Gemini API Key. Please configure it in Settings.")
            return

        update_job_status(job_id, "PROCESSING", 10, "Initializing Gemini Client...")
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=180000)
        )

        model_name = "gemini-omni-flash-preview" if engine == "google_omni" else "veo-3.1-generate-preview"
        engine_label = "Google Omni Video" if engine == "google_omni" else "Google Veo 3.1"
        
        update_job_status(job_id, "PROCESSING", 25, f"Submitting video generation request to {engine_label}...")
        
        config = types.GenerateVideosConfig(
            aspect_ratio="16:9",
            number_of_videos=1
        )

        operation = client.models.generate_videos(
            model=model_name,
            prompt=prompt,
            config=config
        )

        update_job_status(job_id, "PROCESSING", 45, "Video rendering started. Polling status...")

        poll_count = 0
        while not operation.done:
            time.sleep(10)
            poll_count += 1
            # Simple progress simulation up to 95%
            progress = min(45 + (poll_count * 4), 95)
            update_job_status(job_id, "PROCESSING", progress, "Veo is rendering frames...")
            operation = client.operations.get(operation)

        update_job_status(job_id, "PROCESSING", 95, "Video rendered! Retrieving output URI...")
        
        # Retrieve download URI with robust dict/object checking to handle SDK parsing bugs
        video_uri = None
        
        # 1. Check if response is a dictionary
        if hasattr(operation, "response") and operation.response:
            resp = operation.response
            if isinstance(resp, dict):
                samples = resp.get("generateVideoResponse", {}).get("generatedSamples", [])
                if samples:
                    video_uri = samples[0].get("video", {}).get("uri")
            else:
                try:
                    if hasattr(resp, "generate_video_response") and resp.generate_video_response:
                        samples = resp.generate_video_response.generated_samples
                        if samples:
                            video_uri = samples[0].video.uri
                except Exception:
                    pass

        # 2. Check if result has generated_videos (SDK fallback)
        if not video_uri and hasattr(operation, "result") and operation.result:
            res_obj = operation.result
            if res_obj and hasattr(res_obj, "generated_videos") and res_obj.generated_videos:
                generated_video = res_obj.generated_videos[0]
                if hasattr(generated_video, "video") and hasattr(generated_video.video, "uri"):
                    video_uri = generated_video.video.uri
                elif hasattr(generated_video, "uri"):
                    video_uri = generated_video.uri

        if not video_uri:
            update_job_status(job_id, "FAILED", 0, "No video returned or download URI found in Veo API response.")
            return
        
        update_job_status(job_id, "PROCESSING", 98, "Downloading video file from Google server...")
        # Download the file using the authenticated SDK client
        try:
            video_content = client.files.download(file=video_uri)
        except Exception as sdk_err:
            logger.warning(f"SDK download failed, falling back to authenticated requests: {sdk_err}")
            # Fallback: request with x-goog-api-key header or key parameter
            import requests
            headers = {"x-goog-api-key": api_key}
            response = requests.get(video_uri, headers=headers)
            if response.status_code != 200:
                # Also try passing as query parameter
                separator = "&" if "?" in video_uri else "?"
                response = requests.get(f"{video_uri}{separator}key={api_key}")
                
            if response.status_code != 200:
                update_job_status(job_id, "FAILED", 0, f"Failed to download video file. HTTP status: {response.status_code}")
                return
            video_content = response.content
            
        # Target path
        assets_dir = os.path.join(BASE_DIR, "static", "assets", "generated")
        os.makedirs(assets_dir, exist_ok=True)
        dest_path = os.path.join(assets_dir, f"{job_id}.mp4")
        
        with open(dest_path, "wb") as f:
            f.write(video_content)
            
        # Success!
        video_web_path = f"/static/assets/generated/{job_id}.mp4"
        update_job_status(
            job_id, 
            "SUCCESS", 
            100, 
            "Video generation complete!", 
            result={"video_path": video_web_path}
        )

    except Exception as e:
        logger.exception("Error in video generation")
        update_job_status(job_id, "FAILED", 0, f"Video generation failed: {str(e)}")

class RepurposedContent(BaseModel):
    author: str = Field(description="Creator's username/channel name")
    original_post_text: str = Field(description="Summary or text of the original post")
    repurposed_linkedin_post: str = Field(description="Staged B2B LinkedIn post copy for 6Frame Studio commenting on the video and citing the link/author")
    repurposed_twitter_thread: List[str] = Field(description="Staged Twitter thread (2-3 tweets, under 280 chars each)")
    repurposed_instagram_caption: str = Field(description="Staged Instagram caption with hashtags")

def repurpose_video_link_copy(url: str, settings: Dict[str, Any]) -> RepurposedContent:
    api_key = settings.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Missing Gemini API Key. Please configure it in Settings.")
        
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=180000)
    )
    brand_voice = settings.get("brand_voice", "")
    
    # Phase 1: Search grounding to find metadata for this specific URL
    search_prompt = f"""
    Search for information about the following viral video link:
    URL: {url}
    
    Determine:
    1. The platform it is on (e.g. YouTube, X/Twitter, Instagram, Reddit)
    2. The creator/author's username or channel
    3. The title or description of the video
    4. Reconstruct what the original post text or copy says
    5. The main visual concept, technique, or content of the video.
    """
    
    try:
        search_res = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=search_prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                system_instruction="You are a social media research assistant specialized in finding information about links."
            )
        )
    except Exception as e:
        logger.warning(f"Google Search grounding failed inside repurposer: {e}. Falling back to standard generation.")
        search_res = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=search_prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a social media research assistant specialized in finding information about links."
            )
        )
    
    # Phase 2: Structure and draft repurposed copies using Gemini 2.5 Pro JSON schema
    adaptation_prompt = f"""
    Analyze the research details of this viral video link:
    URL: {url}
    Research Details: {search_res.text}
    
    6Frame Studio Brand Voice Guidelines:
    {brand_voice}
    
    Based on this information, perform the following tasks:
    1. Extract the author/creator's username.
    2. Reconstruct or summarize the original post text.
    3. Write repurposed social copy in the brand voice of 6Frame Studio (cinematic, refined, artistic, technical but premium) reacting to/commenting on the original video. You must explicitly credit the creator/author (by username) and direct the audience to check out the original clip (using the URL {url} or a citation).
    
    Draft:
    - repurposed_linkedin_post: A professional, cinematic review/commentary for LinkedIn citing the creator.
    - repurposed_twitter_thread: A structured X thread (2-3 tweets, each under 280 characters).
    - repurposed_instagram_caption: A premium caption with hashtags.

    ### POST FORMATTING AND SPACING RULES (CRITICAL)
    - **Double Line Breaks**: You MUST separate all paragraphs, highlights, and bullet groups with a blank line (double newlines `\n\n`). Do not write long blocks of single-spaced text.
    - **NO ASTERISKS / NO BOLD**: Do NOT use markdown bold asterisks (`**`) or headers in the post text. All text must be clean plain text so it displays properly on Twitter and LinkedIn.
    - **Social handles / links**: Always credit the original creator using their actual social media handle (e.g. @CuriousRefuge) or a link to their channel/profile.
    - **Bullet Points**: Format lists with clean bullet dashes (`- item`) and leave spaces above and below list blocks.
    """
    
    copy_res = client.models.generate_content(
        model='gemini-2.5-pro',
        contents=adaptation_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RepurposedContent,
            system_instruction="You are an expert social media copywriter specialized in marketing high-end cinematic AI assets."
        )
    )
    
    try:
        return copy_res.parsed
    except Exception as e:
        logger.error(f"Failed to parse repurposed copy structure: {e}. Raw: {copy_res.text}")
        raise ValueError("Failed to parse structured JSON from Gemini Pro.")


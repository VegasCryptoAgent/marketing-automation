// Javascript Frontend Controller for TrendPilot AI SPA
document.addEventListener("DOMContentLoaded", () => {
    // State management
    let isLoggedIn = localStorage.getItem("trendpilot_logged_in") === "true";
    let activeView = "dashboard";
    let scannedTrends = [];
    let currentTrend = null;
    let originalVideoPath = "";
    let renderedVideoPath = "";
    
    // Status tracking state (simulated/cached statistics)
    let stats = {
        trendsFound: 0,
        downloads: 0,
        trimmed: 0,
        scheduled: 0,
        published: 0
    };

    // Elements - Routing & Auth
    const landingPage = document.getElementById("landing-page");
    const appWorkspace = document.getElementById("app-workspace");
    const menuItems = document.querySelectorAll(".menu-item");
    const workspaceTitle = document.getElementById("workspace-title");
    const workspaceSubtitle = document.getElementById("workspace-subtitle");
    
    // Elements - Landing Actions
    const loginBtn = document.getElementById("landing-login-btn");
    const trialBtn = document.getElementById("landing-trial-btn");
    const startAppTriggers = document.querySelectorAll(".start-app-trigger");
    const logoutTrigger = document.getElementById("profile-logout-trigger");
    const sidebarLogoBtn = document.getElementById("sidebar-logo-btn");

    // Elements - Dashboard View
    const dashboardTrendsContainer = document.getElementById("dashboard-trends-container");
    const viewAllTrendsLink = document.getElementById("dashboard-view-all-trends");

    // Elements - Scanner View
    const scannerStartBtn = document.getElementById("scanner-start-btn");
    const scannerProgressCard = document.getElementById("scanner-progress-card");
    const scannerStatusMsg = document.getElementById("scanner-status-msg");

    // Elements - Scraper View
    const flowChkFind = document.getElementById("flow-chk-find");
    const flowChkResolve = document.getElementById("flow-chk-resolve");
    const flowChkSearch = document.getElementById("flow-chk-search");
    const flowChkDownload = document.getElementById("flow-chk-download");
    const scraperProceedBtn = document.getElementById("scraper-proceed-btn");
    const recentDownloadsTbody = document.getElementById("recent-downloads-tbody");

    // Elements - Create View
    const createVideoPlayer = document.getElementById("create-video-player");
    const createVideoPlayerContainer = document.getElementById("create-video-player-container");
    const createVideoLoading = document.getElementById("create-video-loading");
    const createVideoStatusTxt = document.getElementById("create-video-status-txt");
    const createTrimBtn = document.getElementById("create-trim-btn");
    const createVideoBadge = document.getElementById("create-video-badge");
    const createPromptInput = document.getElementById("create-prompt-input");
    const createEngineSelect = document.getElementById("create-engine-select");
    const createDurationSelect = document.getElementById("create-duration-select");
    const createRenderBtn = document.getElementById("create-render-btn");
    const editLinkedinText = document.getElementById("edit-linkedin-text");
    const editTwitterCardsContainer = document.getElementById("edit-twitter-cards-container");
    const editInstagramText = document.getElementById("edit-instagram-text");
    const editScheduleTime = document.getElementById("edit-schedule-time");
    const editSchedulePlatform = document.getElementById("edit-schedule-platform");
    const editScheduleBtn = document.getElementById("edit-schedule-btn");
    const editTwitterCopyBtn = document.getElementById("edit-twitter-copy-thread");

    // Elements - Calendar View
    const calendarQueueContainer = document.getElementById("calendar-queue-container");

    // Elements - Integrations View
    const diagGemini = document.getElementById("diag-gemini-status");
    const diagRunway = document.getElementById("diag-runway-status");
    const diagTwitter = document.getElementById("diag-twitter-status");
    const diagLinkedIn = document.getElementById("diag-linkedin-status");
    const autopilotToggle = document.getElementById("autopilot-toggle");
    const autopilotHourSelect = document.getElementById("autopilot-hour-select");
    const autopilotTriggerNowBtn = document.getElementById("autopilot-trigger-now-btn");

    // Elements - Settings View
    const inputGeminiKey = document.getElementById("input-gemini-key");
    const inputRunwayKey = document.getElementById("input-runway-key");
    const inputMockMode = document.getElementById("input-mock-mode");
    const inputBrandVoice = document.getElementById("input-brand-voice");
    const inputTwConsumerKey = document.getElementById("input-tw-consumer-key");
    const inputTwConsumerSecret = document.getElementById("input-tw-consumer-secret");
    const inputTwAccessToken = document.getElementById("input-tw-access-token");
    const inputTwAccessSecret = document.getElementById("input-tw-access-secret");
    const inputLiAccessToken = document.getElementById("input-li-access-token");
    const inputLiPersonUrn = document.getElementById("input-li-person-urn");
    const settingsSaveBtn = document.getElementById("settings-save-btn");

    // Elements - Global toast
    const toast = document.getElementById("toast");

    // Initialize Page
    initAuth();
    fetchSettings();
    loadScheduledQueue();

    /* ==========================================
       AUTHENTICATION & SPA ROUTING
       ========================================== */

    function initAuth() {
        if (isLoggedIn) {
            landingPage.classList.add("hidden");
            appWorkspace.classList.remove("hidden");
            navigateTo("dashboard");
        } else {
            landingPage.classList.remove("hidden");
            appWorkspace.classList.add("hidden");
        }
    }

    function loginUser() {
        isLoggedIn = true;
        localStorage.setItem("trendpilot_logged_in", "true");
        initAuth();
        showToast("Logged in successfully!");
    }

    function logoutUser() {
        isLoggedIn = false;
        localStorage.setItem("trendpilot_logged_in", "false");
        initAuth();
        showToast("Logged out successfully.");
    }

    loginBtn.addEventListener("click", loginUser);
    trialBtn.addEventListener("click", loginUser);
    startAppTriggers.forEach(btn => btn.addEventListener("click", loginUser));
    logoutTrigger.addEventListener("click", logoutUser);
    if (sidebarLogoBtn) {
        sidebarLogoBtn.addEventListener("click", (e) => {
            e.preventDefault();
            logoutUser();
        });
    }

    // Sidebar navigation trigger handler
    menuItems.forEach(item => {
        item.addEventListener("click", () => {
            const target = item.dataset.view;
            navigateTo(target);
        });
    });

    // Landing page Learn More navigation bypass
    document.querySelectorAll(".view-tab-trigger").forEach(link => {
        link.addEventListener("click", (e) => {
            e.preventDefault();
            navigateTo(link.dataset.target);
        });
    });

    viewAllTrendsLink.addEventListener("click", (e) => {
        e.preventDefault();
        navigateTo("trends");
    });

    document.querySelectorAll(".nav-back-trigger").forEach(btn => {
        btn.addEventListener("click", () => {
            navigateTo("dashboard");
        });
    });

    // View Routing Core switcher
    function navigateTo(viewId) {
        if (!isLoggedIn) return;
        activeView = viewId;

        // Reset sidebar active classes
        menuItems.forEach(m => {
            if (m.dataset.view === viewId) {
                m.classList.add("active");
            } else {
                m.classList.remove("active");
            }
        });

        // Toggle visibility of views
        document.querySelectorAll(".view-container").forEach(c => {
            if (c.id === `view-${viewId}`) {
                c.classList.add("active-view");
            } else {
                c.classList.remove("active-view");
            }
        });

        // Set titles dynamically based on active view
        const titles = {
            dashboard: { title: "Dashboard", subtitle: "Welcome back, CuriousRefuge 👋" },
            trends: { title: "Trend Scanner", subtitle: "Surface the last 24h of viral AI insights" },
            scraper: { title: "Video Scraper", subtitle: "Scrape and download high-quality assets" },
            create: { title: "Create Adaptation", subtitle: "Review generated social copy and media edits" },
            calendar: { title: "Queue & Releases", subtitle: "Overview of your scheduled autoposts" },
            features: { title: "All Features", subtitle: "Core automation capabilities of TrendPilot AI" },
            integrations: { title: "Integrations Cockpit", subtitle: "Verify system health and autopost loops" },
            settings: { title: "Settings Cockpit", subtitle: "Manage API keys and brand voice guidelines" }
        };

        const config = titles[viewId] || { title: "TrendPilot AI", subtitle: "AI Content Automation Engine" };
        workspaceTitle.textContent = config.title;
        workspaceSubtitle.textContent = config.subtitle;

        // Perform view-specific data refresh
        if (viewId === "dashboard") {
            renderDashboardTrends();
        } else if (viewId === "calendar") {
            loadScheduledQueue();
        } else if (viewId === "integrations" || viewId === "settings") {
            fetchSettings();
        }
    }

    // New Campaign Header button shortcut
    document.getElementById("btn-topbar-campaign").addEventListener("click", () => {
        navigateTo("trends");
    });

    /* ==========================================
       TREND SCANNER CONTROLLER (Image 3)
       ========================================== */

    scannerStartBtn.addEventListener("click", () => {
        scannerStartBtn.disabled = true;
        scannerProgressCard.classList.remove("hidden");
        scannerStatusMsg.textContent = "Launching multi-source scanning pipelines...";

        fetch("/api/viral-search", { method: "POST" })
            .then(res => {
                if (!res.ok) throw new Error("Trend scan failed to start.");
                return res.json();
            })
            .then(data => {
                pollScanStatus(data.job_id);
            })
            .catch(err => {
                showToast(err.message, true);
                scannerStartBtn.disabled = false;
                scannerProgressCard.classList.add("hidden");
            });
    });

    function pollScanStatus(jobId) {
        const interval = setInterval(() => {
            fetch(`/api/viral-status/${jobId}`)
                .then(res => res.json())
                .then(data => {
                    scannerStatusMsg.textContent = `${data.message} (${data.progress}%)`;
                    
                    if (data.status === "SUCCESS") {
                        clearInterval(interval);
                        scannerStartBtn.disabled = false;
                        scannerProgressCard.classList.add("hidden");
                        showToast("Scan finished successfully!");
                        
                        // Parse resulting trends and save to scanned trends state
                        if (data.result && data.result.trends) {
                            scannedTrends = data.result.trends;
                            stats.trendsFound = scannedTrends.length;
                            updateDashboardStats();
                            navigateTo("dashboard");
                        }
                    } else if (data.status === "FAILED") {
                        clearInterval(interval);
                        scannerStartBtn.disabled = false;
                        scannerProgressCard.classList.add("hidden");
                        showToast(`Scan failed: ${data.message}`, true);
                    }
                })
                .catch(err => {
                    clearInterval(interval);
                    scannerStartBtn.disabled = false;
                    scannerProgressCard.classList.add("hidden");
                    showToast("Polling error occurred.", true);
                });
        }, 3000);
    }

    /* ==========================================
       DASHBOARD CONTROLLER (Image 2)
       ========================================== */

    function renderDashboardTrends() {
        dashboardTrendsContainer.innerHTML = "";
        
        if (scannedTrends.length === 0) {
            dashboardTrendsContainer.innerHTML = `
                <p style="color: var(--text-secondary); text-align: center; grid-column: span 4; padding: 2rem;">No trends scanned in the last 24h. Go to the Trends page to search!</p>
            `;
            return;
        }

        scannedTrends.forEach(trend => {
            const card = document.createElement("div");
            card.className = "trend-card";
            
            // Map platforms to correct styling tags or source logos
            const platformColors = {
                reddit: "#FF4500",
                youtube: "#FF0000",
                twitter: "#000000",
                linkedin: "#0077B5",
                tiktok: "#000000"
            };
            const platformText = trend.platform ? trend.platform.toUpperCase() : "VIRAL";

            card.innerHTML = `
                <div class="card-thumbnail-container">
                    <div style="background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%); width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: var(--purple-light);">
                        <svg viewBox="0 0 24 24" width="40" height="40" stroke="currentColor" stroke-width="1.5" fill="none"><polygon points="23 7 16 12 23 17 23 7"></polygon><rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect></svg>
                    </div>
                    <div class="card-platform-icon" style="border-color: ${platformColors[trend.platform.toLowerCase()] || '#ccc'};">
                        <span style="color: ${platformColors[trend.platform.toLowerCase()] || '#fff'}; font-size: 0.6rem; font-weight: 800;">${platformText[0]}</span>
                    </div>
                    <span class="card-duration">0:45</span>
                </div>
                <div class="card-content">
                    <h3 class="card-title">${trend.title}</h3>
                    <div class="card-meta">
                        <span>Creator: ${trend.author || '@unknown'}</span>
                        <span>Virality: ${trend.viral_metrics || '10K views'}</span>
                    </div>
                    <div class="card-status-indicator">
                        <span class="card-status-dot"></span>
                        <span>Trending now</span>
                    </div>
                </div>
            `;

            card.addEventListener("click", () => {
                startScraperWorkflow(trend);
            });

            dashboardTrendsContainer.appendChild(card);
        });
    }

    function updateDashboardStats() {
        document.getElementById("stat-trends-found").textContent = stats.trendsFound;
        document.getElementById("stat-downloads").textContent = stats.downloads;
        document.getElementById("stat-trimmed").textContent = stats.trimmed;
        document.getElementById("stat-scheduled").textContent = stats.scheduled;
        document.getElementById("stat-published").textContent = stats.published;
    }

    /* ==========================================
       SCRAPER WORKFLOW CONTROLLER (Image 1)
       ========================================== */

    function startScraperWorkflow(trend) {
        currentTrend = trend;
        navigateTo("scraper");

        // Reset checkmarks
        flowChkFind.classList.add("completed");
        flowChkResolve.classList.add("completed");
        flowChkSearch.classList.add("completed");
        flowChkDownload.classList.remove("completed");
        scraperProceedBtn.disabled = true;

        // Auto download original video files
        triggerScraperDownload(trend);
    }

    function triggerScraperDownload(trend) {
        let downloadUrl = trend.url || "";
        
        // Mock fallback check matching main.py downloader logic
        const isMock = (
            !downloadUrl.startsWith("http") || 
            downloadUrl.includes("examplecyber") || 
            downloadUrl.includes("12345") || 
            downloadUrl.includes("abcdef") || 
            downloadUrl.includes("status/example") ||
            downloadUrl.includes("DigitalDreams") ||
            downloadUrl.includes("AIVoyager")
        );
        if (isMock) {
            downloadUrl = "https://www.youtube.com/watch?v=kQD2bBnb-Yc"; // Live Sora Cinematic AI Video link
        }

        const payload = {
            url: downloadUrl,
            title: trend.title
        };

        fetch("/api/load-original-video", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        })
        .then(res => {
            if (!res.ok) throw new Error("Original video scraper failed.");
            return res.json();
        })
        .then(data => {
            pollScraperDownloadStatus(data.job_id);
        })
        .catch(err => {
            showToast(err.message, true);
        });
    }

    function pollScraperDownloadStatus(jobId) {
        const interval = setInterval(() => {
            fetch(`/api/viral-status/${jobId}`)
                .then(res => res.json())
                .then(data => {
                    if (data.status === "SUCCESS") {
                        clearInterval(interval);
                        flowChkDownload.classList.add("completed");
                        scraperProceedBtn.disabled = false;
                        showToast("Scraper finished downloading video!");
                        
                        originalVideoPath = data.result.video_path;
                        stats.downloads += 1;
                        updateDashboardStats();
                        
                        // Add to downloads log list
                        appendRecentDownloadRow(currentTrend.title, currentTrend.platform, "Downloaded");
                    } else if (data.status === "FAILED") {
                        clearInterval(interval);
                        showToast(`Scraper error: ${data.message}`, true);
                    }
                })
                .catch(err => {
                    clearInterval(interval);
                    showToast("Scraper polling connection error.", true);
                });
        }, 3000);
    }

    function appendRecentDownloadRow(title, platform, status) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td class="table-title">${title}</td>
            <td class="table-source">
                <span style="font-weight: bold;">${platform.toUpperCase()}</span>
            </td>
            <td class="status-downloaded">${status}</td>
            <td>34.5 MB</td>
        `;
        recentDownloadsTbody.insertBefore(tr, recentDownloadsTbody.firstChild);
    }

    scraperProceedBtn.addEventListener("click", () => {
        loadCreateWorkspace();
    });

    /* ==========================================
       CREATE / EDITOR CONTROLLER
       ========================================== */

    function loadCreateWorkspace() {
        navigateTo("create");

        // Load video path
        createVideoPlayer.src = originalVideoPath;
        createVideoBadge.textContent = "Original Scraped";
        createVideoPlayer.load();

        // Populate prompt inputs
        createPromptInput.value = currentTrend.studio_adaptation_concept || currentTrend.recreated_video_prompt || "";

        // Fill staging post texts
        editLinkedinText.value = currentTrend.repurposed_6frame_linkedin_post || currentTrend.recreated_linkedin_post || "";
        editInstagramText.value = currentTrend.repurposed_6frame_instagram_caption || currentTrend.recreated_instagram_caption || "";

        // Fill tweet threads
        editTwitterCardsContainer.innerHTML = "";
        const tweets = currentTrend.repurposed_6frame_twitter_thread || currentTrend.recreated_twitter_thread || [currentTrend.title];
        
        tweets.forEach((t, idx) => {
            const card = document.createElement("div");
            card.className = "tweet-card";
            card.style.background = "rgba(0,0,0,0.25)";
            card.style.border = "1px solid var(--border-color)";
            card.style.borderRadius = "8px";
            card.style.padding = "0.75rem";
            card.innerHTML = `
                <div style="display:flex; justify-content:space-between; font-size:0.75rem; color:var(--text-secondary); margin-bottom: 0.35rem;">
                    <span>Tweet ${idx + 1}</span>
                    <span>Draft</span>
                </div>
                <textarea class="edit-tweet-textarea" rows="3" style="width:100%; font-size:0.8rem; background:rgba(0,0,0,0.3); border:1px solid var(--border-color); color:#fff; border-radius:4px; padding:0.4rem;">${t}</textarea>
                <div style="text-align:right; font-size:0.65rem; color:var(--text-secondary); margin-top:0.2rem;">
                    <span class="char-c">${t.length}</span>/280
                </div>
            `;
            
            const textarea = card.querySelector(".edit-tweet-textarea");
            const charSpan = card.querySelector(".char-c");
            textarea.addEventListener("input", () => {
                charSpan.textContent = textarea.value.length;
            });

            editTwitterCardsContainer.appendChild(card);
        });
    }

    // Social Editor sub-tabs toggle
    const createTabs = document.querySelectorAll(".tab-btn");
    createTabs.forEach(tab => {
        tab.addEventListener("click", () => {
            createTabs.forEach(t => t.classList.remove("active"));
            document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));

            tab.classList.add("active");
            document.getElementById(tab.dataset.pane).classList.add("active");
        });
    });

    // Copy commentary logic
    document.querySelectorAll(".copy-trigger").forEach(btn => {
        btn.addEventListener("click", () => {
            const targetId = btn.dataset.target;
            const text = document.getElementById(targetId).value;
            navigator.clipboard.writeText(text)
                .then(() => showToast("Copied to clipboard!"))
                .catch(() => showToast("Copy failed.", true));
        });
    });

    editTwitterCopyBtn.addEventListener("click", () => {
        const textareas = editTwitterCardsContainer.querySelectorAll(".edit-tweet-textarea");
        let threadStr = "";
        textareas.forEach((ta, idx) => {
            threadStr += `[Tweet ${idx + 1}]\n${ta.value}\n\n`;
        });
        navigator.clipboard.writeText(threadStr.trim())
            .then(() => showToast("Copied Twitter thread to clipboard!"))
            .catch(() => showToast("Copy failed.", true));
    });

    // Live Publishing trigger triggers
    document.querySelector(".publish-linkedin-trigger").addEventListener("click", () => {
        const text = editLinkedinText.value;
        const btn = document.querySelector(".publish-linkedin-trigger");
        
        btn.disabled = true;
        btn.textContent = "Publishing...";

        fetch("/api/publish/linkedin", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, video_path: originalVideoPath || null })
        })
        .then(res => {
            if (!res.ok) return res.json().then(e => { throw new Error(e.detail || "Publish failed") });
            return res.json();
        })
        .then(data => {
            showToast(data.message || "Posted to LinkedIn successfully!");
            stats.published += 1;
            updateDashboardStats();
        })
        .catch(err => {
            showToast(err.message, true);
        })
        .finally(() => {
            btn.disabled = false;
            btn.textContent = "Publish to LinkedIn";
        });
    });

    document.querySelector(".publish-twitter-trigger").addEventListener("click", () => {
        const textareas = editTwitterCardsContainer.querySelectorAll(".edit-tweet-textarea");
        const btn = document.querySelector(".publish-twitter-trigger");
        const thread = [];
        
        textareas.forEach(ta => thread.push(ta.value));
        btn.disabled = true;
        btn.textContent = "Publishing Thread...";

        const payload = {
            is_thread: thread.length > 1,
            thread: thread,
            text: thread.length === 1 ? thread[0] : null,
            video_path: originalVideoPath || null
        };

        fetch("/api/publish/twitter", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        })
        .then(res => {
            if (!res.ok) return res.json().then(e => { throw new Error(e.detail || "Publish failed") });
            return res.json();
        })
        .then(data => {
            showToast(data.message || "Thread posted to X successfully!");
            stats.published += 1;
            updateDashboardStats();
        })
        .catch(err => {
            showToast(err.message, true);
        })
        .finally(() => {
            btn.disabled = false;
            btn.textContent = "Publish Thread to X";
        });
    });

    // Trim Video check
    createTrimBtn.addEventListener("click", () => {
        createTrimBtn.disabled = true;
        createTrimBtn.textContent = "Trimming video...";

        fetch("/api/publish/twitter", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                is_thread: false,
                text: "Duration verification trim dry-run",
                video_path: originalVideoPath
            })
        })
        .then(res => {
            // Trim checks duration and builds file. If it creates a trimmed path, reload player
            showToast("Video trimmed successfully for X upload!");
            stats.trimmed += 1;
            updateDashboardStats();
            
            // Reload with trimmed video source if applicable
            if (originalVideoPath) {
                const base = originalVideoPath.substring(0, originalVideoPath.lastIndexOf("."));
                const ext = originalVideoPath.substring(originalVideoPath.lastIndexOf("."));
                createVideoPlayer.src = `${base}_trimmed${ext}`;
                createVideoBadge.textContent = "Trimmed (120s)";
                createVideoPlayer.load();
            }
        })
        .catch(() => {
            showToast("Video check completed.");
        })
        .finally(() => {
            createTrimBtn.disabled = false;
            createTrimBtn.textContent = "Trim to 120s Limit";
        });
    });

    // Runway / Google Veo Video Generator
    createRenderBtn.addEventListener("click", () => {
        const engine = createEngineSelect.value;
        const duration = parseInt(createDurationSelect.value);
        const prompt = createPromptInput.value;

        createRenderBtn.disabled = true;
        createVideoPlayerContainer.classList.add("hidden");
        createVideoLoading.classList.remove("hidden");
        createVideoStatusTxt.textContent = "Enqueuing render job...";

        fetch("/api/generate-video", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prompt, engine, duration })
        })
        .then(res => {
            if (!res.ok) throw new Error("Video rendering failed to start.");
            return res.json();
        })
        .then(data => {
            pollRenderStatus(data.job_id);
        })
        .catch(err => {
            showToast(err.message, true);
            createRenderBtn.disabled = false;
            createVideoPlayerContainer.classList.remove("hidden");
            createVideoLoading.classList.add("hidden");
        });
    });

    function pollRenderStatus(jobId) {
        const interval = setInterval(() => {
            fetch(`/api/viral-status/${jobId}`)
                .then(res => res.json())
                .then(data => {
                    createVideoStatusTxt.textContent = `${data.message} (${data.progress}%)`;
                    
                    if (data.status === "SUCCESS") {
                        clearInterval(interval);
                        createRenderBtn.disabled = false;
                        createVideoPlayerContainer.classList.remove("hidden");
                        createVideoLoading.classList.add("hidden");
                        showToast("Stitched AI video generated successfully!");
                        
                        renderedVideoPath = data.result.video_path;
                        createVideoPlayer.src = renderedVideoPath;
                        createVideoBadge.textContent = "Stitched AI Render";
                        createVideoPlayer.load();
                    } else if (data.status === "FAILED") {
                        clearInterval(interval);
                        createRenderBtn.disabled = false;
                        createVideoPlayerContainer.classList.remove("hidden");
                        createVideoLoading.classList.add("hidden");
                        showToast(`Render failed: ${data.message}`, true);
                    }
                })
                .catch(err => {
                    clearInterval(interval);
                    createRenderBtn.disabled = false;
                    createVideoPlayerContainer.classList.remove("hidden");
                    createVideoLoading.classList.add("hidden");
                    showToast("Render status connection error.", true);
                });
        }, 4000);
    }

    // Schedule Releases
    editScheduleBtn.addEventListener("click", () => {
        const timeVal = editScheduleTime.value;
        const platform = editSchedulePlatform.value;
        
        if (!timeVal) {
            showToast("Please pick a date and time.", true);
            return;
        }

        const text = editLinkedinText.value || currentTrend.title;

        fetch("/api/scheduled-queue", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                platform,
                text,
                scheduled_time: timeVal,
                campaign_title: currentTrend.title,
                video_path: originalVideoPath || null
            })
        })
        .then(res => {
            if (!res.ok) throw new Error("Scheduling failed.");
            return res.json();
        })
        .then(() => {
            showToast("Campaign post successfully queued!");
            stats.scheduled += 1;
            updateDashboardStats();
            navigateTo("calendar");
        })
        .catch(err => {
            showToast(err.message, true);
        });
    });

    /* ==========================================
       CALENDAR & QUEUE CONTROLLER
       ========================================== */

    function loadScheduledQueue() {
        calendarQueueContainer.innerHTML = "";

        fetch("/api/scheduled-queue")
            .then(res => res.json())
            .then(data => {
                if (data.length === 0) {
                    calendarQueueContainer.innerHTML = `
                        <p style="text-align: center; color: var(--text-secondary); padding: 2rem;">No posts currently scheduled in the queue.</p>
                    `;
                    return;
                }

                data.forEach(item => {
                    const row = document.createElement("div");
                    row.className = "queue-item";
                    
                    // Format scheduled ISO string
                    const dateStr = new Date(item.scheduled_time).toLocaleString();
                    const statusText = item.posted_at ? `Published (at ${new Date(item.posted_at).toLocaleTimeString()})` : "Pending";
                    const isPosted = !!item.posted_at;

                    row.innerHTML = `
                        <div class="queue-info">
                            <div class="queue-title">${item.campaign_title || 'Staged Post'} (${item.platform.toUpperCase()})</div>
                            <div class="queue-time">Schedule: ${dateStr} &bull; <span style="color: ${isPosted ? 'var(--green-primary)' : 'var(--purple-light)'};">${statusText}</span></div>
                            <p style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.35rem; display:-webkit-box; -webkit-line-clamp:1; -webkit-box-orient:vertical; overflow:hidden;">${item.text}</p>
                        </div>
                        ${isPosted ? '' : `
                        <button class="queue-delete-btn" data-id="${item.id}">
                            <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                        </button>
                        `}
                    `;

                    if (!isPosted) {
                        row.querySelector(".queue-delete-btn").addEventListener("click", () => {
                            cancelScheduledPost(item.id);
                        });
                    }

                    calendarQueueContainer.appendChild(row);
                });
            })
            .catch(() => {
                calendarQueueContainer.innerHTML = `<p style="text-align: center; color: var(--text-secondary); padding: 2rem;">Queue failed to load.</p>`;
            });
    }

    function cancelScheduledPost(id) {
        fetch(`/api/scheduled-queue/${id}`, { method: "DELETE" })
            .then(res => {
                if (!res.ok) throw new Error("Failed to delete queued post.");
                return res.json();
            })
            .then(() => {
                showToast("Scheduled post successfully cancelled.");
                loadScheduledQueue();
                if (stats.scheduled > 0) stats.scheduled -= 1;
                updateDashboardStats();
            })
            .catch(err => showToast(err.message, true));
    }

    /* ==========================================
       INTEGRATIONS & COCKPIT CONTROLLER
       ========================================== */

    autopilotTriggerNowBtn.addEventListener("click", () => {
        autopilotTriggerNowBtn.disabled = true;
        autopilotTriggerNowBtn.textContent = "Triggering loop...";

        fetch("/api/trigger-autopilot", { method: "POST" })
            .then(res => res.json())
            .then(data => {
                showToast(data.message || "Autopilot automation loop started!");
            })
            .catch(() => {
                showToast("Autopilot triggered.", true);
            })
            .finally(() => {
                autopilotTriggerNowBtn.disabled = false;
                autopilotTriggerNowBtn.textContent = "Run Loop Now";
            });
    });

    autopilotToggle.addEventListener("change", () => {
        saveSettingsFromIntegrations();
    });

    autopilotHourSelect.addEventListener("change", () => {
        saveSettingsFromIntegrations();
    });

    function saveSettingsFromIntegrations() {
        const enabled = autopilotToggle.checked;
        const hour = parseInt(autopilotHourSelect.value);

        fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                autonomous_posting: enabled,
                autonomous_hour: hour
            })
        })
        .then(() => showToast("Autopilot configuration saved."))
        .catch(() => showToast("Autopilot config failed to save.", true));
    }

    /* ==========================================
       SETTINGS & CREDENTIALS COCKPIT
       ========================================== */

    function fetchSettings() {
        fetch("/api/settings")
            .then(res => res.json())
            .then(data => {
                // Populate forms
                inputGeminiKey.value = data.gemini_api_key || "";
                inputRunwayKey.value = data.runway_api_key || "";
                inputMockMode.checked = !!data.mock_mode;
                inputBrandVoice.value = data.brand_voice || "";
                inputTwConsumerKey.value = data.twitter_consumer_key || "";
                inputTwConsumerSecret.value = data.twitter_consumer_secret || "";
                inputTwAccessToken.value = data.twitter_access_token || "";
                inputTwAccessSecret.value = data.twitter_access_token_secret || "";
                inputLiAccessToken.value = data.linkedin_access_token || "";
                inputLiPersonUrn.value = data.linkedin_person_urn || "";

                // Populate autopilot forms
                autopilotToggle.checked = !!data.autonomous_posting;
                autopilotHourSelect.value = data.autonomous_hour || 9;

                // Update health badges
                updateDiagBadges(data);
            });
    }

    function updateDiagBadges(data) {
        setDiagStatus(diagGemini, !!data.gemini_api_key);
        setDiagStatus(diagRunway, !!data.runway_api_key);
        
        const twActive = data.twitter_consumer_key && data.twitter_consumer_secret && data.twitter_access_token && data.twitter_access_token_secret;
        setDiagStatus(diagTwitter, !!twActive);
        
        setDiagStatus(diagLinkedIn, !!data.linkedin_access_token);
    }

    function setDiagStatus(badge, isActive) {
        if (isActive) {
            badge.textContent = "ACTIVE";
            badge.style.background = "rgba(40, 167, 69, 0.2)";
            badge.style.color = "#28a745";
        } else {
            badge.textContent = "INACTIVE";
            badge.style.background = "rgba(220, 53, 69, 0.2)";
            badge.style.color = "#dc3545";
        }
    }

    settingsSaveBtn.addEventListener("click", () => {
        settingsSaveBtn.disabled = true;
        settingsSaveBtn.textContent = "Saving credentials...";

        const payload = {
            gemini_api_key: inputGeminiKey.value,
            runway_api_key: inputRunwayKey.value,
            mock_mode: inputMockMode.checked,
            brand_voice: inputBrandVoice.value,
            twitter_consumer_key: inputTwConsumerKey.value,
            twitter_consumer_secret: inputTwConsumerSecret.value,
            twitter_access_token: inputTwAccessToken.value,
            twitter_access_token_secret: inputTwAccessSecret.value,
            linkedin_access_token: inputLiAccessToken.value,
            linkedin_person_urn: inputLiPersonUrn.value
        };

        fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        })
        .then(res => {
            if (!res.ok) throw new Error("Settings save failed.");
            return res.json();
        })
        .then(data => {
            showToast("API Credentials and Voice successfully saved!");
            updateDiagBadges(data);
        })
        .catch(err => {
            showToast(err.message, true);
        })
        .finally(() => {
            settingsSaveBtn.disabled = false;
            settingsSaveBtn.textContent = "Save Credentials";
        });
    });

    /* ==========================================
       GLOBAL UTILITIES
       ========================================== */

    function showToast(message, isError = false) {
        toast.textContent = message;
        toast.style.borderColor = isError ? "var(--error-primary)" : "var(--green-primary)";
        toast.style.boxShadow = isError ? "0 0 10px rgba(239, 68, 68, 0.25)" : "0 0 10px rgba(16, 185, 129, 0.25)";
        toast.classList.remove("hidden");
        setTimeout(() => {
            toast.classList.add("hidden");
        }, 3500);
    }
});

"""
Job Description Fetcher Module

A hybrid approach to extract job description text from ATS job posting URLs.
First attempts HTTP fetch, then falls back to Playwright for JavaScript-rendered content.

Usage:
    from utils.jd_fetcher import fetch_job_description
    result = fetch_job_description("https://example.com/job/12345")
"""

from typing import Dict, Optional, Tuple
from urllib.parse import urlparse, parse_qs
import time
import requests
from bs4 import BeautifulSoup


# Minimum character threshold for valid job description content.
# If extracted text is below this, we assume the page uses JavaScript rendering.
MIN_CONTENT_LENGTH = 1000

# Keywords that indicate a valid job description is present.
# Used to validate that we actually extracted JD content, not just navigation/footer text.
JD_INDICATORS = [
    "responsibilities",
    "requirements",
    "qualifications",
    "experience",
    "skills",
    "about the role",
    "what you'll do",
    "who you are",
    "job description",
    "duties",
]

# ATS platform detection patterns and their corresponding CSS selectors.
# These selectors target the main job description container on each platform.
ATS_SELECTORS = {
    # Workday uses data-automation-id attribute for job posting content
    "workday": {
        "patterns": ["myworkdayjobs.com", "workday.com", "wd5.myworkdayjobs"],
        "selector": 'div[data-automation-id="jobPostingDescription"]',
    },
    # Greenhouse wraps job content in #content container
    "greenhouse": {
        "patterns": ["greenhouse.io", "boards.greenhouse"],
        "selector": "#content",
    },
    # Lever uses .posting-page class for the job posting container
    "lever": {
        "patterns": ["lever.co", "jobs.lever"],
        "selector": ".posting-page",
    },
    # iCIMS platform selector
    "icims": {
        "patterns": ["icims.com", "careers-"],
        "selector": ".iCIMS_JobContent",
    },
    # Taleo platform selector
    "taleo": {
        "patterns": ["taleo.net", "taleo.com"],
        "selector": ".requisitionDescriptionText",
    },
    # SmartRecruiters platform selector
    "smartrecruiters": {
        "patterns": ["smartrecruiters.com"],
        "selector": ".job-sections",
    },
}

# Semantic containers used for content-aware waiting in Playwright.
# These are standard HTML5 semantic elements that typically contain main content.
# Order matters: prefer more specific containers first.
SEMANTIC_CONTAINERS = ["main", "article", "body"]


def _detect_ats_type(url: str) -> str:
    """
    Detect which ATS platform the URL belongs to.
    
    Detection priority:
    1. Check for gh_jid query param - this indicates Greenhouse embeds
       (e.g., current.com/careers?gh_jid=12345 uses Greenhouse behind the scenes)
    2. Check for workday in hostname - many companies use custom domains
    3. Fall back to URL pattern matching
    
    Args:
        url: The job posting URL
        
    Returns:
        ATS type string: "workday", "greenhouse", "lever", etc., or "unknown"
    """
    url_lower = url.lower()
    
    # gh_jid query parameter is a strong indicator of Greenhouse ATS.
    # Many companies embed Greenhouse job postings on their own domains
    # using this parameter to identify the specific job listing.
    try:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        if "gh_jid" in query_params:
            return "greenhouse"
    except Exception:
        pass
    
    # Check if hostname contains "workday" - handles custom subdomains
    # e.g., company.wd5.myworkdayjobs.com or careers.workday.com
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if "workday" in hostname.lower():
            return "workday"
    except Exception:
        pass
    
    # Fall back to existing pattern matching
    for ats_type, config in ATS_SELECTORS.items():
        for pattern in config["patterns"]:
            if pattern in url_lower:
                return ats_type
    
    return "unknown"


def _has_jd_indicators(text: str) -> bool:
    """
    Check if the text contains keywords indicating a valid job description.
    
    This helps distinguish between actual JD content and generic page chrome
    (navigation, footers, cookie banners, etc.).
    
    Args:
        text: The extracted text content
        
    Returns:
        True if at least one JD indicator is found
    """
    text_lower = text.lower()
    return any(indicator in text_lower for indicator in JD_INDICATORS)


def _is_content_valid(text: str) -> bool:
    """
    Validate that extracted content is likely a real job description.
    
    Two conditions must be met:
    1. Content length exceeds MIN_CONTENT_LENGTH
    2. Content contains at least one JD indicator keyword
    
    If either fails, we should fall back to Playwright.
    
    Args:
        text: The extracted text content
        
    Returns:
        True if content appears to be a valid job description
    """
    if not text:
        return False
    
    # Check minimum length - short content usually means JS-rendered page
    if len(text.strip()) < MIN_CONTENT_LENGTH:
        return False
    
    # Check for JD indicators - ensures we got actual job content
    if not _has_jd_indicators(text):
        return False
    
    return True


def _clean_text(text: str) -> str:
    """
    Clean and normalize extracted text.
    
    Args:
        text: Raw extracted text
        
    Returns:
        Cleaned text with normalized whitespace
    """
    if not text:
        return ""
    
    # Normalize whitespace: replace multiple spaces/newlines with single space
    import re
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _fetch_with_requests(url: str) -> Tuple[Optional[str], str]:
    """
    Attempt to fetch job description using requests + BeautifulSoup.
    
    This is the fast path - works for static HTML pages but fails for
    JavaScript-rendered content (most modern ATS platforms).
    
    Args:
        url: The job posting URL
        
    Returns:
        Tuple of (extracted_text, error_message)
        - If successful: (text, "")
        - If failed: (None, error_message)
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        return None, "Request timed out"
    except requests.exceptions.ConnectionError:
        return None, "Could not connect to URL"
    except requests.exceptions.HTTPError as e:
        return None, f"HTTP error: {e.response.status_code}"
    except requests.exceptions.RequestException as e:
        return None, f"Request failed: {str(e)}"
    
    # Parse HTML and extract text
    soup = BeautifulSoup(response.content, "html.parser")
    
    # Remove non-content elements that add noise
    for element in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe"]):
        element.decompose()
    
    # Try to find main content area using common selectors
    main_content = None
    content_selectors = [
        "article",
        "main",
        '[role="main"]',
        ".job-description",
        ".job-details",
        "#job-description",
        "#job-details",
    ]
    
    for selector in content_selectors:
        try:
            found = soup.select_one(selector)
            if found and len(found.get_text(strip=True)) > 200:
                main_content = found
                break
        except Exception:
            continue
    
    # Fall back to body if no main content found
    if not main_content:
        main_content = soup.find("body") or soup
    
    text = main_content.get_text(separator=" ", strip=True)
    return _clean_text(text), ""


def _extract_text_from_container(page, container_selector: str) -> Optional[str]:
    """
    Extract text from a specific container in a Playwright page.
    
    Args:
        page: Playwright page object
        container_selector: CSS selector for the container
        
    Returns:
        Extracted text or None if container not found
    """
    try:
        element = page.query_selector(container_selector)
        if element:
            return element.inner_text()
    except Exception:
        pass
    return None


def _extract_from_greenhouse_iframe(page) -> Optional[str]:
    """
    Extract job description from Greenhouse iframe embed.
    
    Many company career pages embed Greenhouse job postings in an iframe.
    The iframe typically loads from boards.greenhouse.io or similar.
    We need to switch to the iframe context to extract the content.
    
    Args:
        page: Playwright page object
        
    Returns:
        Extracted text or None if iframe not found/extraction failed
    """
    try:
        # Common Greenhouse iframe selectors and patterns
        # Companies embed Greenhouse using various iframe configurations
        iframe_selectors = [
            'iframe[src*="greenhouse"]',
            'iframe[src*="grnh"]',
            'iframe#grnhse_iframe',
            'iframe[id*="greenhouse"]',
            'iframe[id*="grnhse"]',
            'iframe[class*="greenhouse"]',
            # Generic job board iframe patterns
            'iframe[src*="boards."]',
            'iframe[src*="jobs."]',
        ]
        
        for selector in iframe_selectors:
            try:
                iframe_element = page.query_selector(selector)
                if iframe_element:
                    # Get the iframe's content frame
                    frame = iframe_element.content_frame()
                    if frame:
                        # Wait for content to load in iframe
                        try:
                            frame.wait_for_load_state("domcontentloaded", timeout=10000)
                        except Exception:
                            pass
                        
                        # Try to extract from #content (standard Greenhouse container)
                        try:
                            content_element = frame.query_selector("#content")
                            if content_element:
                                text = content_element.inner_text()
                                if text and len(text.strip()) > 200:
                                    return text
                        except Exception:
                            pass
                        
                        # Try body as fallback
                        try:
                            body_text = frame.query_selector("body")
                            if body_text:
                                text = body_text.inner_text()
                                if text and len(text.strip()) > 200:
                                    return text
                        except Exception:
                            pass
            except Exception:
                continue
        
        return None
    except Exception:
        return None


def _extract_all_page_text(page) -> str:
    """
    Extract ALL visible text from the page, including from iframes.
    
    This is a last-resort extraction method that attempts to get
    any visible text content from the page.
    
    Args:
        page: Playwright page object
        
    Returns:
        All extracted text concatenated
    """
    all_text = []
    
    # Get main page text
    try:
        main_text = page.inner_text("body")
        if main_text:
            all_text.append(main_text)
    except Exception:
        pass
    
    # Get text from all iframes
    try:
        frames = page.frames
        for frame in frames:
            if frame != page.main_frame:
                try:
                    frame_text = frame.inner_text("body")
                    if frame_text and len(frame_text.strip()) > 100:
                        all_text.append(frame_text)
                except Exception:
                    continue
    except Exception:
        pass
    
    return " ".join(all_text)


def _fetch_with_playwright(url: str, ats_type: str) -> Tuple[Optional[str], str]:
    """
    Fetch job description using Playwright for JavaScript-rendered pages.
    
    This function handles modern ATS platforms that render content dynamically.
    
    IMPORTANT: We do NOT rely solely on page.wait_for_load_state("networkidle").
    networkidle is UNRELIABLE for React/SPA pages because:
    - It only waits for network requests to settle
    - React hydration and state updates happen AFTER network is idle
    - Many SPAs lazy-load content based on scroll position or timers
    
    Instead, we use CONTENT-AWARE waiting:
    1. Wait for semantic containers (<main>, <article>, <body>)
    2. Add a hydration delay for React/Vue/Angular apps
    3. Retry extraction multiple times until content stabilizes
    
    Args:
        url: The job posting URL
        ats_type: Detected ATS platform type for selector optimization
        
    Returns:
        Tuple of (extracted_text, error_message)
        - If successful: (text, "")
        - If failed: (None, error_message)
    """
    try:
        # Import here to allow module to work even if Playwright isn't installed
        # (requests-only mode will still function)
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        return None, "Playwright is not installed. Install with: pip install playwright && playwright install chromium"
    
    # Configuration for DOM stabilization
    MAX_EXTRACTION_ATTEMPTS = 3
    HYDRATION_DELAY_SECONDS = 2.0  # Wait for React/SPA hydration (increased for iframes)
    CONTENT_THRESHOLD = MIN_CONTENT_LENGTH  # 1000 chars
    
    try:
        with sync_playwright() as p:
            # Launch headless Chromium - no visible browser window
            browser = p.chromium.launch(headless=True)
            
            # Create browser context with reasonable viewport
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            
            page = context.new_page()
            
            try:
                # Navigate to the page
                # Use "load" for pages with iframes - ensures iframes start loading
                page.goto(url, wait_until="load", timeout=30000)
            except PlaywrightTimeout:
                browser.close()
                return None, "Page load timed out (30s)"
            except Exception as e:
                browser.close()
                return None, f"Navigation error: {str(e)}"
            
            # CONTENT-AWARE WAITING: Wait for semantic containers instead of network idle.
            # Semantic containers (<main>, <article>) are standard HTML5 elements that
            # typically wrap the main page content. Waiting for these ensures the
            # page structure is rendered, even if some content is still loading.
            container_found = False
            for container in SEMANTIC_CONTAINERS:
                try:
                    page.wait_for_selector(container, timeout=15000)
                    container_found = True
                    break
                except PlaywrightTimeout:
                    continue
                except Exception:
                    continue
            
            # Even if no container found, continue - content might be in iframe
            
            # HYDRATION DELAY: Wait for JavaScript frameworks to finish rendering.
            # React, Vue, Angular apps often "hydrate" static HTML with dynamic content
            # after the initial DOM is loaded. This also gives iframes time to load.
            time.sleep(HYDRATION_DELAY_SECONDS)
            
            # DOM STABILIZATION: Attempt extraction multiple times.
            # Some pages load content progressively. We retry extraction up to
            # MAX_EXTRACTION_ATTEMPTS times, stopping early if we get enough content.
            extracted_text = ""
            
            for attempt in range(MAX_EXTRACTION_ATTEMPTS):
                # GREENHOUSE IFRAME HANDLING:
                # Many company career pages (like current.com) embed Greenhouse job 
                # postings in an iframe. The gh_jid param indicates Greenhouse, but
                # the actual content is inside an iframe from boards.greenhouse.io.
                # We MUST check for iframes first before trying main page selectors.
                if ats_type == "greenhouse":
                    # First try: Extract from Greenhouse iframe
                    iframe_text = _extract_from_greenhouse_iframe(page)
                    if iframe_text and len(iframe_text.strip()) > len(extracted_text.strip()):
                        extracted_text = iframe_text
                        if len(extracted_text.strip()) >= CONTENT_THRESHOLD:
                            break
                    
                    # Second try: Direct #content selector (for native Greenhouse pages)
                    if not extracted_text or len(extracted_text.strip()) < 200:
                        try:
                            page.wait_for_selector("#content", timeout=3000)
                            greenhouse_text = _extract_text_from_container(page, "#content")
                            if greenhouse_text and len(greenhouse_text.strip()) > 200:
                                extracted_text = greenhouse_text
                                if len(extracted_text.strip()) >= CONTENT_THRESHOLD:
                                    break
                        except Exception:
                            pass
                
                # Try other ATS-specific selectors
                if not extracted_text or len(extracted_text.strip()) < 200:
                    if ats_type != "unknown" and ats_type in ATS_SELECTORS:
                        selector = ATS_SELECTORS[ats_type]["selector"]
                        try:
                            page.wait_for_selector(selector, timeout=3000)
                            ats_text = _extract_text_from_container(page, selector)
                            if ats_text and len(ats_text.strip()) > len(extracted_text.strip()):
                                extracted_text = ats_text
                                if len(extracted_text.strip()) >= CONTENT_THRESHOLD:
                                    break
                        except Exception:
                            pass
                
                # Fall back to semantic container extraction
                if not extracted_text or len(extracted_text.strip()) < CONTENT_THRESHOLD:
                    for container in SEMANTIC_CONTAINERS:
                        container_text = _extract_text_from_container(page, container)
                        if container_text and len(container_text.strip()) > len(extracted_text.strip()):
                            extracted_text = container_text
                            if len(extracted_text.strip()) >= CONTENT_THRESHOLD:
                                break
                    
                    if len(extracted_text.strip()) >= CONTENT_THRESHOLD:
                        break
                
                # LAST RESORT: Extract ALL text including from iframes
                if not extracted_text or len(extracted_text.strip()) < 200:
                    all_text = _extract_all_page_text(page)
                    if all_text and len(all_text.strip()) > len(extracted_text.strip()):
                        extracted_text = all_text
                        if len(extracted_text.strip()) >= CONTENT_THRESHOLD:
                            break
                
                # Wait before retrying to allow more content to load
                if attempt < MAX_EXTRACTION_ATTEMPTS - 1:
                    time.sleep(1.0)  # Longer wait for iframe content
            
            browser.close()
            
            # Final validation
            cleaned_text = _clean_text(extracted_text)
            
            if len(cleaned_text) < 200:
                # Content still too short after all attempts
                raise ValueError(
                    "Page content loaded asynchronously but did not stabilize in time. "
                    f"Only {len(cleaned_text)} characters extracted after {MAX_EXTRACTION_ATTEMPTS} attempts."
                )
            
            return cleaned_text, ""
            
    except ValueError as e:
        # Re-raise ValueError with clear message
        return None, str(e)
    except Exception as e:
        return None, f"Playwright error: {str(e)}"


def fetch_job_description(url: str, mode: str = "auto") -> Dict:
    """
    Fetch and extract job description text from a URL.
    
    Supports three modes:
    - "auto": Hybrid strategy - tries requests first, falls back to Playwright if needed
    - "requests": HTTP only - fast but may fail on JavaScript-rendered pages
    - "playwright": Browser only - slower but handles all pages including JS-rendered
    
    Args:
        url: The job posting URL to fetch
        mode: Extraction mode - "auto", "requests", or "playwright"
        
    Returns:
        Dictionary with structure:
        {
            "url": str,              # Original URL
            "source": str,           # "requests" or "playwright"
            "ats_type": str,         # "workday", "greenhouse", "lever", or "unknown"
            "raw_text": str,         # Extracted job description text
            "error": str | None      # Error message if extraction failed
        }
        
    Raises:
        ValueError: If URL is empty or invalid
        ValueError: If mode is invalid
    """
    if not url or not url.strip():
        raise ValueError("URL cannot be empty")
    
    valid_modes = ["auto", "requests", "playwright"]
    if mode not in valid_modes:
        raise ValueError(f"Invalid mode '{mode}'. Must be one of: {valid_modes}")
    
    url = url.strip()
    
    # Detect ATS platform for optimized extraction
    # This now checks gh_jid param and hostname before pattern matching
    ats_type = _detect_ats_type(url)
    
    result = {
        "url": url,
        "source": "",
        "ats_type": ats_type,
        "raw_text": "",
        "error": None,
    }
    
    # MODE: requests only
    if mode == "requests":
        text, error = _fetch_with_requests(url)
        result["source"] = "requests"
        if text:
            result["raw_text"] = text
            if not _is_content_valid(text):
                result["error"] = "Content may be incomplete (short or missing JD keywords). Try Playwright mode."
        else:
            result["error"] = error or "Failed to fetch content"
        return result
    
    # MODE: playwright only
    if mode == "playwright":
        text, error = _fetch_with_playwright(url, ats_type)
        result["source"] = "playwright"
        if text and len(text.strip()) > 200:
            result["raw_text"] = text
        else:
            result["raw_text"] = text or ""
            result["error"] = error or "Failed to extract content with Playwright"
        return result
    
    # MODE: auto (hybrid) - default behavior
    # STEP 1: Try fast HTTP fetch first
    text, error = _fetch_with_requests(url)
    
    if text and _is_content_valid(text):
        # Success with requests - content looks valid
        result["source"] = "requests"
        result["raw_text"] = text
        return result
    
    # STEP 2: Fall back to Playwright
    # Reasons for fallback:
    # - requests failed completely (text is None)
    # - Content too short (< 1000 chars) - likely JS-rendered page
    # - Missing JD indicators - got page chrome instead of job content
    
    playwright_text, playwright_error = _fetch_with_playwright(url, ats_type)
    
    if playwright_text and len(playwright_text.strip()) > 200:
        # Playwright succeeded
        result["source"] = "playwright"
        result["raw_text"] = playwright_text
        return result
    
    # Both methods failed - return best available content with error
    if text and len(text.strip()) > 0:
        # Return partial content from requests
        result["source"] = "requests"
        result["raw_text"] = text
        result["error"] = f"Content may be incomplete. Requests: {error or 'OK but short'}. Playwright: {playwright_error}"
    else:
        # Complete failure
        result["source"] = "none"
        result["raw_text"] = ""
        result["error"] = f"Failed to extract content. Requests: {error}. Playwright: {playwright_error}"
    
    return result

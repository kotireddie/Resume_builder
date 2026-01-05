"""
Job Description Fetcher Module

A hybrid approach to extract job description text from ATS job posting URLs.
Uses multiple extraction strategies in priority order:
1. Schema.org JSON-LD structured data (most reliable)
2. HTTP fetch with content cleaning
3. Playwright for JavaScript-rendered content
4. Trafilatura fallback for difficult pages

Usage:
    from utils.jd_fetcher import fetch_job_description
    result = fetch_job_description("https://example.com/job/12345")
"""

from typing import Dict, Optional, Tuple, Any, List, Literal
from urllib.parse import urlparse, parse_qs
from dataclasses import dataclass
import time
import re
import json
import requests
from bs4 import BeautifulSoup, Comment


# =============================================================================
# CONFIGURATION
# =============================================================================

# Minimum character threshold for valid job description content.
MIN_CONTENT_LENGTH = 1000

# Request timeout in seconds
REQUEST_TIMEOUT = 30

# Job source type
JobSource = Literal["greenhouse", "lever", "workday", "icims", "taleo", "smartrecruiters", "generic"]

# Keywords that indicate a valid job description is present.
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
    "benefits",
    "salary",
    "apply",
    "position",
]

# Browser-like headers to avoid bot detection
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Cache-Control': 'max-age=0',
}


# =============================================================================
# SOURCE DETECTION PATTERNS
# =============================================================================

# URL patterns for each platform (using regex for accurate matching)
GREENHOUSE_PATTERNS = [
    r'boards\.greenhouse\.io',
    r'greenhouse\.io/embed',
    r'[?&]gh_jid=\d+',
    r'job_app\.greenhouse\.io',
]

LEVER_PATTERNS = [
    r'jobs\.lever\.co',
    r'lever\.co/[^/]+/[a-f0-9-]+',
]

WORKDAY_PATTERNS = [
    r'myworkdayjobs\.com',
    r'\.workday\.com/.*?/job/',
    r'wd\d+\.myworkdaysite\.com',
]

# ATS platform CSS selectors for content extraction
ATS_SELECTORS = {
    "workday": {
        "patterns": ["myworkdayjobs.com", "workday.com", "wd5.myworkdayjobs"],
        "selector": 'div[data-automation-id="jobPostingDescription"]',
    },
    "greenhouse": {
        "patterns": ["greenhouse.io", "boards.greenhouse"],
        "selector": "#content",
    },
    "lever": {
        "patterns": ["lever.co", "jobs.lever"],
        "selector": ".posting-page",
    },
    "icims": {
        "patterns": ["icims.com", "careers-"],
        "selector": ".iCIMS_JobContent",
    },
    "taleo": {
        "patterns": ["taleo.net", "taleo.com"],
        "selector": ".requisitionDescriptionText",
    },
    "smartrecruiters": {
        "patterns": ["smartrecruiters.com"],
        "selector": ".job-sections",
    },
}

# Semantic containers for content-aware waiting
SEMANTIC_CONTAINERS = ["main", "article", "body"]


# =============================================================================
# BOILERPLATE REMOVAL PATTERNS
# =============================================================================

# Tags to completely remove
REMOVE_TAGS = {
    'script', 'style', 'noscript', 'iframe', 'svg', 'canvas',
    'nav', 'header', 'footer', 'aside', 'form', 'button',
    'input', 'select', 'textarea', 'label',
    'advertisement', 'ads', 'ad'
}

# Classes/IDs indicating boilerplate content
BOILERPLATE_PATTERNS = [
    r'nav(igation)?[-_]?',
    r'header[-_]?',
    r'footer[-_]?',
    r'sidebar[-_]?',
    r'menu[-_]?',
    r'cookie[-_]?',
    r'banner[-_]?',
    r'popup[-_]?',
    r'modal[-_]?',
    r'overlay[-_]?',
    r'advertisement[-_]?',
    r'ads?[-_]?',
    r'promo(tion)?[-_]?',
    r'social[-_]?(share|media|links)?',
    r'share[-_]?(button|link)?s?',
    r'related[-_]?(jobs|posts|articles)?',
    r'similar[-_]?(jobs|positions)?',
    r'recommend(ed|ations)?[-_]?',
    r'newsletter[-_]?',
    r'subscribe[-_]?',
    r'sign[-_]?up',
    r'login[-_]?',
    r'register[-_]?',
    r'legal[-_]?',
    r'privacy[-_]?',
    r'terms[-_]?',
    r'disclaimer[-_]?',
    r'copyright[-_]?',
    r'breadcrumb[-_]?',
    r'pagination[-_]?',
    r'search[-_]?(box|form|bar)?',
]

# Compile patterns for efficiency
BOILERPLATE_REGEX = re.compile('|'.join(BOILERPLATE_PATTERNS), re.IGNORECASE)

# Legal/boilerplate text patterns to remove
LEGAL_TEXT_PATTERNS = [
    r'equal\s+opportunity\s+employer',
    r'we\s+are\s+an?\s+e\.?o\.?e\.?',
    r'affirmative\s+action',
    r'(terms\s+(of\s+)?(use|service)|privacy\s+policy)',
    r'all\s+rights\s+reserved',
    r'cookie\s+(policy|settings|preferences)',
    r'by\s+(clicking|applying|submitting)',
    r'we\s+use\s+cookies',
    r'this\s+site\s+uses\s+cookies',
]

LEGAL_REGEX = re.compile('|'.join(LEGAL_TEXT_PATTERNS), re.IGNORECASE)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class FetchResult:
    """Result of a URL fetch operation."""
    success: bool
    html: Optional[str]
    status_code: Optional[int]
    error_message: Optional[str]
    final_url: str


# =============================================================================
# SOURCE DETECTION
# =============================================================================

def detect_source(url: str) -> JobSource:
    """
    Detect the job posting platform from URL using regex patterns.
    
    Detection priority:
    1. Check for gh_jid query param - indicates Greenhouse embeds
    2. Check regex patterns for each platform
    3. Fall back to "generic"
    
    Args:
        url: The job posting URL
        
    Returns:
        JobSource type string
    """
    url_lower = url.lower()
    
    # Check Greenhouse patterns (including gh_jid param)
    if _detect_greenhouse(url):
        return "greenhouse"
    
    # Check Lever patterns
    if _detect_lever(url):
        return "lever"
    
    # Check Workday patterns
    if _detect_workday(url):
        return "workday"
    
    # Check other ATS platforms by URL pattern
    for ats_type, config in ATS_SELECTORS.items():
        if ats_type in ["greenhouse", "lever", "workday"]:
            continue
        for pattern in config["patterns"]:
            if pattern in url_lower:
                return ats_type
    
    return "generic"


def _detect_greenhouse(url: str) -> bool:
    """Detect if URL is a Greenhouse job posting."""
    url_lower = url.lower()
    
    for pattern in GREENHOUSE_PATTERNS:
        if re.search(pattern, url_lower):
            return True
    
    # Check for gh_jid in query params
    try:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        if 'gh_jid' in query_params:
            return True
    except Exception:
        pass
    
    return False


def _detect_lever(url: str) -> bool:
    """Detect if URL is a Lever job posting."""
    url_lower = url.lower()
    
    for pattern in LEVER_PATTERNS:
        if re.search(pattern, url_lower):
            return True
    
    return False


def _detect_workday(url: str) -> bool:
    """Detect if URL is a Workday job posting."""
    url_lower = url.lower()
    
    for pattern in WORKDAY_PATTERNS:
        if re.search(pattern, url_lower):
            return True
    
    # Check hostname for workday
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if "workday" in hostname.lower():
            return True
    except Exception:
        pass
    
    return False


# =============================================================================
# URL RESOLUTION
# =============================================================================

def resolve_url(url: str, source: JobSource) -> Tuple[str, bool]:
    """
    Resolve URL to canonical form based on detected source.
    
    This is important for Greenhouse embedded jobs where the gh_jid
    parameter needs to be converted to a direct boards.greenhouse.io URL.
    
    Args:
        url: Original job posting URL
        source: Detected job source platform
    
    Returns:
        Tuple of (resolved_url, was_resolved)
    """
    if source == "greenhouse":
        return _resolve_greenhouse_url(url)
    elif source == "lever":
        return _resolve_lever_url(url)
    else:
        return url, False


def _resolve_greenhouse_url(url: str) -> Tuple[str, bool]:
    """
    Resolve Greenhouse job URL to canonical boards.greenhouse.io format.
    
    Handles embedded jobs with gh_jid parameter by converting them to
    the direct embed endpoint which doesn't require company token.
    """
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    
    # Already a direct Greenhouse URL
    if 'boards.greenhouse.io' in parsed.netloc.lower():
        return url, False
    
    # Check for gh_jid parameter (embedded Greenhouse job)
    if 'gh_jid' in query_params:
        job_id = query_params['gh_jid'][0]
        
        # Try to extract company token
        company_token = _extract_greenhouse_company(url, query_params)
        
        if company_token:
            canonical_url = f"https://boards.greenhouse.io/{company_token}/jobs/{job_id}"
        else:
            # Fallback: use embed endpoint which doesn't require company token
            canonical_url = f"https://boards.greenhouse.io/embed/job_app?token={job_id}"
        
        return canonical_url, True
    
    # Check for token parameter
    if 'token' in query_params and 'greenhouse' in url.lower():
        token = query_params['token'][0]
        canonical_url = f"https://boards.greenhouse.io/embed/job_app?token={token}"
        return canonical_url, True
    
    # Try to extract job ID from URL path
    job_id_match = re.search(r'/jobs?/(\d+)', url)
    if job_id_match:
        job_id = job_id_match.group(1)
        company_token = _extract_greenhouse_company(url, query_params)
        
        if company_token:
            canonical_url = f"https://boards.greenhouse.io/{company_token}/jobs/{job_id}"
            return canonical_url, True
    
    return url, False


def _extract_greenhouse_company(url: str, query_params: dict) -> Optional[str]:
    """Try to extract Greenhouse company token from URL or params."""
    if 'for' in query_params:
        return query_params['for'][0]
    
    match = re.search(r'boards\.greenhouse\.io/([^/]+)', url)
    if match:
        return match.group(1)
    
    match = re.search(r'greenhouse\.io/embed/job_board/js\?for=([^&]+)', url)
    if match:
        return match.group(1)
    
    return None


def _resolve_lever_url(url: str) -> Tuple[str, bool]:
    """Resolve Lever job URL - removes trailing /apply if present."""
    parsed = urlparse(url)
    
    if 'lever.co' not in parsed.netloc.lower():
        return url, False
    
    # Remove trailing /apply
    clean_path = re.sub(r'/apply/?$', '', parsed.path)
    
    if clean_path != parsed.path:
        clean_url = f"{parsed.scheme}://{parsed.netloc}{clean_path}"
        return clean_url, True
    
    return url, False


# =============================================================================
# SCHEMA.ORG JSON-LD EXTRACTION
# =============================================================================

def extract_schema_job_posting(html: str) -> Optional[Dict[str, Any]]:
    """
    Extract Schema.org JobPosting JSON-LD from HTML.
    
    This is the most reliable extraction method as it contains structured data
    that the job site explicitly provides for search engines.
    
    Args:
        html: Raw HTML content
    
    Returns:
        Parsed JobPosting data or None if not found
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find all script tags with JSON-LD
    script_tags = soup.find_all('script', type='application/ld+json')
    
    for script in script_tags:
        try:
            content = script.string
            if not content:
                continue
            
            data = json.loads(content)
            
            # Handle array of schemas
            if isinstance(data, list):
                for item in data:
                    if _is_job_posting(item):
                        return _normalize_job_posting(item)
            
            # Handle single schema
            elif isinstance(data, dict):
                if _is_job_posting(data):
                    return _normalize_job_posting(data)
                
                # Check @graph structure
                if '@graph' in data:
                    for item in data['@graph']:
                        if _is_job_posting(item):
                            return _normalize_job_posting(item)
        
        except json.JSONDecodeError:
            continue
        except Exception:
            continue
    
    return None


def _is_job_posting(data: Dict[str, Any]) -> bool:
    """Check if a JSON-LD object is a JobPosting."""
    if not isinstance(data, dict):
        return False
    
    schema_type = data.get('@type', '')
    
    if isinstance(schema_type, str):
        return 'JobPosting' in schema_type
    elif isinstance(schema_type, list):
        return any('JobPosting' in t for t in schema_type)
    
    return False


def _normalize_job_posting(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize JobPosting data to a consistent format."""
    normalized = {
        'title': _extract_schema_value(data, ['title', 'name']),
        'description': _extract_schema_value(data, ['description']),
        'company': _extract_company(data),
        'location': _extract_location(data),
        'employment_type': _extract_schema_value(data, ['employmentType']),
        'date_posted': _extract_schema_value(data, ['datePosted']),
        'salary': _extract_salary(data),
        'experience': _extract_schema_value(data, ['experienceRequirements']),
        'education': _extract_schema_value(data, ['educationRequirements']),
        'skills': _extract_skills(data),
        'industry': _extract_schema_value(data, ['industry']),
    }
    
    return {k: v for k, v in normalized.items() if v}


def _extract_schema_value(data: Dict, keys: List[str]) -> Optional[str]:
    """Extract first matching value from a list of possible keys."""
    for key in keys:
        value = data.get(key)
        if value:
            if isinstance(value, str):
                return value.strip()
            elif isinstance(value, dict):
                for sub_key in ['@value', 'name', 'value']:
                    if sub_key in value:
                        return str(value[sub_key]).strip()
            elif isinstance(value, list):
                return ', '.join(str(v) for v in value if v)
    return None


def _extract_company(data: Dict) -> Optional[str]:
    """Extract company name from hiringOrganization."""
    org = data.get('hiringOrganization')
    if not org:
        return None
    
    if isinstance(org, str):
        return org
    elif isinstance(org, dict):
        return org.get('name') or org.get('legalName')
    
    return None


def _extract_location(data: Dict) -> Optional[str]:
    """Extract job location."""
    location = data.get('jobLocation')
    if not location:
        return None
    
    if isinstance(location, str):
        return location
    
    if isinstance(location, list):
        locations = []
        for loc in location:
            loc_str = _parse_location_object(loc)
            if loc_str:
                locations.append(loc_str)
        return '; '.join(locations) if locations else None
    
    if isinstance(location, dict):
        return _parse_location_object(location)
    
    return None


def _parse_location_object(loc: Dict) -> Optional[str]:
    """Parse a single location object."""
    if not isinstance(loc, dict):
        return str(loc) if loc else None
    
    address = loc.get('address')
    if address:
        if isinstance(address, str):
            return address
        elif isinstance(address, dict):
            parts = []
            for key in ['streetAddress', 'addressLocality', 'addressRegion', 'postalCode', 'addressCountry']:
                val = address.get(key)
                if val:
                    if isinstance(val, dict):
                        val = val.get('name', str(val))
                    parts.append(str(val))
            return ', '.join(parts) if parts else None
    
    return loc.get('name')


def _extract_salary(data: Dict) -> Optional[str]:
    """Extract salary information."""
    salary = data.get('baseSalary') or data.get('estimatedSalary')
    if not salary:
        return None
    
    if isinstance(salary, str):
        return salary
    
    if isinstance(salary, dict):
        value = salary.get('value')
        currency = salary.get('currency', 'USD')
        
        if isinstance(value, dict):
            min_val = value.get('minValue')
            max_val = value.get('maxValue')
            unit = value.get('unitText', 'YEAR')
            
            if min_val and max_val:
                return f"{currency} {min_val:,} - {max_val:,} per {unit}"
            elif min_val:
                return f"{currency} {min_val:,}+ per {unit}"
        elif value:
            return f"{currency} {value}"
    
    return None


def _extract_skills(data: Dict) -> List[str]:
    """Extract required skills."""
    skills = data.get('skills') or data.get('qualifications')
    if not skills:
        return []
    
    if isinstance(skills, str):
        return [skills]
    elif isinstance(skills, list):
        return [str(s) for s in skills if s]
    
    return []


def schema_to_text(schema_data: Dict[str, Any]) -> str:
    """Convert schema data to readable text for LLM analysis."""
    parts = []
    
    if schema_data.get('title'):
        parts.append(f"Job Title: {schema_data['title']}")
    if schema_data.get('company'):
        parts.append(f"Company: {schema_data['company']}")
    if schema_data.get('location'):
        parts.append(f"Location: {schema_data['location']}")
    if schema_data.get('employment_type'):
        parts.append(f"Employment Type: {schema_data['employment_type']}")
    if schema_data.get('salary'):
        parts.append(f"Salary: {schema_data['salary']}")
    if schema_data.get('experience'):
        parts.append(f"Experience Required: {schema_data['experience']}")
    if schema_data.get('description'):
        parts.append(f"\nDescription:\n{schema_data['description']}")
    if schema_data.get('skills'):
        skills = schema_data['skills']
        if isinstance(skills, list):
            parts.append(f"\nSkills: {', '.join(skills)}")
        else:
            parts.append(f"\nSkills: {skills}")
    
    return '\n'.join(parts)


# =============================================================================
# CONTENT CLEANING
# =============================================================================

def clean_html_content(html: str) -> str:
    """
    Clean HTML by removing boilerplate content.
    
    Steps:
    1. Remove unwanted tags (scripts, styles, nav, footer, etc.)
    2. Remove elements with boilerplate class/ID patterns
    3. Remove HTML comments
    4. Extract and clean text
    5. Remove legal/boilerplate text sections
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Step 1: Remove unwanted tags
    for tag in REMOVE_TAGS:
        for element in soup.find_all(tag):
            element.decompose()
    
    # Step 2: Remove elements with boilerplate patterns
    _remove_boilerplate_elements(soup)
    
    # Step 3: Remove HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    
    # Step 4: Extract text
    text = _extract_clean_text(soup)
    
    # Step 5: Remove legal text sections
    text = _remove_legal_sections(text)
    
    # Final cleanup
    text = _final_cleanup(text)
    
    return text


def _remove_boilerplate_elements(soup: BeautifulSoup) -> None:
    """Remove elements that match boilerplate patterns."""
    for element in soup.find_all(True):
        classes = element.get('class', [])
        if isinstance(classes, list):
            class_str = ' '.join(classes)
        else:
            class_str = str(classes)
        
        elem_id = element.get('id', '')
        role = element.get('role', '')
        
        combined = f"{class_str} {elem_id} {role}"
        
        if BOILERPLATE_REGEX.search(combined):
            element.decompose()


def _extract_clean_text(soup: BeautifulSoup) -> str:
    """Extract text while preserving some structure."""
    # Find main content area if possible
    main_content = (
        soup.find('main') or
        soup.find('article') or
        soup.find(attrs={'role': 'main'}) or
        soup.find(class_=re.compile(r'job|content|description', re.I)) or
        soup.find('body') or
        soup
    )
    
    # Extract text with newlines for structure
    text = main_content.get_text(separator='\n', strip=True)
    
    return text


def _remove_legal_sections(text: str) -> str:
    """Remove legal disclaimer sections."""
    lines = text.split('\n')
    cleaned_lines = []
    skip_until_section = False
    
    for line in lines:
        line_stripped = line.strip()
        
        if not line_stripped:
            if cleaned_lines and cleaned_lines[-1] != '':
                cleaned_lines.append('')
            continue
        
        # Check if this line starts a legal section
        if LEGAL_REGEX.search(line_stripped):
            if len(line_stripped) < 100:
                skip_until_section = True
            continue
        
        # Reset skip flag on new apparent section
        if skip_until_section and len(line_stripped) < 60 and line_stripped.endswith(':'):
            skip_until_section = False
        
        if not skip_until_section:
            cleaned_lines.append(line_stripped)
    
    return '\n'.join(cleaned_lines)


def _final_cleanup(text: str) -> str:
    """Final text cleanup."""
    # Remove multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Remove lines that are just punctuation/symbols
    lines = text.split('\n')
    cleaned = []
    
    for line in lines:
        if line and not re.match(r'^[\s\-\u2022\u00b7*|/\\]+$', line):
            if len(line.strip()) > 2 or line.strip() == '':
                cleaned.append(line)
    
    text = '\n'.join(cleaned)
    
    # Remove excessive whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n ', '\n', text)
    
    return text.strip()


# =============================================================================
# VALIDATION
# =============================================================================

def _has_jd_indicators(text: str) -> bool:
    """Check if the text contains keywords indicating a valid job description."""
    text_lower = text.lower()
    return any(indicator in text_lower for indicator in JD_INDICATORS)


def _is_content_valid(text: str) -> bool:
    """Validate that extracted content is likely a real job description."""
    if not text:
        return False
    
    if len(text.strip()) < MIN_CONTENT_LENGTH:
        return False
    
    if not _has_jd_indicators(text):
        return False
    
    return True


def is_meaningful_content(text: str, min_length: int = 200) -> bool:
    """
    Check if extracted content is meaningful.
    
    Args:
        text: Extracted text content
        min_length: Minimum character length for valid content
    
    Returns:
        True if content appears to be a valid job posting
    """
    if len(text) < min_length:
        return False
    
    text_lower = text.lower()
    matches = sum(1 for kw in JD_INDICATORS if kw in text_lower)
    
    return matches >= 2


# =============================================================================
# FETCHING
# =============================================================================

def _fetch_with_requests(url: str) -> FetchResult:
    """
    Fetch HTML content from a URL with browser-like headers.
    
    Returns a FetchResult with success status and content/error.
    """
    # Validate URL
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        response = requests.get(
            url,
            headers=DEFAULT_HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            verify=True
        )
        
        if response.status_code == 200:
            # Detect encoding
            if response.encoding is None or response.encoding == 'ISO-8859-1':
                response.encoding = response.apparent_encoding
            
            return FetchResult(
                success=True,
                html=response.text,
                status_code=response.status_code,
                error_message=None,
                final_url=response.url
            )
        else:
            return FetchResult(
                success=False,
                html=None,
                status_code=response.status_code,
                error_message=f"HTTP {response.status_code}: {response.reason}",
                final_url=response.url
            )
    
    except requests.exceptions.Timeout:
        return FetchResult(False, None, None, f"Request timed out after {REQUEST_TIMEOUT}s", url)
    
    except requests.exceptions.SSLError as e:
        return FetchResult(False, None, None, f"SSL certificate error: {str(e)}", url)
    
    except requests.exceptions.ConnectionError:
        return FetchResult(False, None, None, "Connection error: Could not connect to server", url)
    
    except requests.exceptions.TooManyRedirects:
        return FetchResult(False, None, None, "Too many redirects - URL may be invalid", url)
    
    except requests.exceptions.RequestException as e:
        return FetchResult(False, None, None, f"Request failed: {str(e)}", url)
    
    except Exception as e:
        return FetchResult(False, None, None, f"Unexpected error: {str(e)}", url)


# =============================================================================
# TRAFILATURA FALLBACK
# =============================================================================

def extract_with_trafilatura(html: str, url: str = None) -> str:
    """
    Extract main content using trafilatura (fallback method).
    
    Trafilatura is designed to extract main readable content from web pages,
    removing boilerplate, navigation, and other non-content elements.
    """
    try:
        import trafilatura
        
        extracted = trafilatura.extract(
            html,
            url=url,
            favor_precision=True,
            include_comments=False,
            include_tables=True,
            include_links=False,
            include_images=False,
            deduplicate=True,
            no_fallback=False,
        )
        
        return extracted or ""
    
    except ImportError:
        return ""
    except Exception:
        return ""


# =============================================================================
# PLAYWRIGHT (BROWSER) EXTRACTION
# =============================================================================

def _extract_text_from_container(page, container_selector: str) -> Optional[str]:
    """Extract text from a specific container in a Playwright page."""
    try:
        element = page.query_selector(container_selector)
        if element:
            return element.inner_text()
    except Exception:
        pass
    return None


def _extract_from_greenhouse_iframe(page) -> Optional[str]:
    """Extract job description from Greenhouse iframe embed."""
    try:
        iframe_selectors = [
            'iframe[src*="greenhouse"]',
            'iframe[src*="grnh"]',
            'iframe#grnhse_iframe',
            'iframe[id*="greenhouse"]',
            'iframe[id*="grnhse"]',
            'iframe[class*="greenhouse"]',
            'iframe[src*="boards."]',
            'iframe[src*="jobs."]',
        ]
        
        for selector in iframe_selectors:
            try:
                iframe_element = page.query_selector(selector)
                if iframe_element:
                    frame = iframe_element.content_frame()
                    if frame:
                        try:
                            frame.wait_for_load_state("domcontentloaded", timeout=10000)
                        except Exception:
                            pass
                        
                        # Try #content first
                        try:
                            content_element = frame.query_selector("#content")
                            if content_element:
                                text = content_element.inner_text()
                                if text and len(text.strip()) > 200:
                                    return text
                        except Exception:
                            pass
                        
                        # Fallback to body
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
    """Extract ALL visible text from the page, including from iframes."""
    all_text = []
    
    try:
        main_text = page.inner_text("body")
        if main_text:
            all_text.append(main_text)
    except Exception:
        pass
    
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


def _fetch_with_playwright(url: str, source: JobSource) -> Tuple[Optional[str], str]:
    """
    Fetch job description using Playwright for JavaScript-rendered pages.
    
    Uses content-aware waiting instead of networkidle for better reliability
    with React/SPA pages.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        return None, "Playwright is not installed. Install with: pip install playwright && playwright install chromium"
    
    MAX_EXTRACTION_ATTEMPTS = 3
    HYDRATION_DELAY_SECONDS = 2.0
    CONTENT_THRESHOLD = MIN_CONTENT_LENGTH
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=DEFAULT_HEADERS['User-Agent'],
            )
            
            page = context.new_page()
            
            try:
                page.goto(url, wait_until="load", timeout=30000)
            except PlaywrightTimeout:
                browser.close()
                return None, "Page load timed out (30s)"
            except Exception as e:
                browser.close()
                return None, f"Navigation error: {str(e)}"
            
            # Wait for semantic containers
            for container in SEMANTIC_CONTAINERS:
                try:
                    page.wait_for_selector(container, timeout=15000)
                    break
                except Exception:
                    continue
            
            # Hydration delay for SPAs
            time.sleep(HYDRATION_DELAY_SECONDS)
            
            extracted_text = ""
            
            for attempt in range(MAX_EXTRACTION_ATTEMPTS):
                # Greenhouse iframe handling
                if source == "greenhouse":
                    iframe_text = _extract_from_greenhouse_iframe(page)
                    if iframe_text and len(iframe_text.strip()) > len(extracted_text.strip()):
                        extracted_text = iframe_text
                        if len(extracted_text.strip()) >= CONTENT_THRESHOLD:
                            break
                    
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
                
                # Try ATS-specific selectors
                if not extracted_text or len(extracted_text.strip()) < 200:
                    if source != "generic" and source in ATS_SELECTORS:
                        selector = ATS_SELECTORS[source]["selector"]
                        try:
                            page.wait_for_selector(selector, timeout=3000)
                            ats_text = _extract_text_from_container(page, selector)
                            if ats_text and len(ats_text.strip()) > len(extracted_text.strip()):
                                extracted_text = ats_text
                                if len(extracted_text.strip()) >= CONTENT_THRESHOLD:
                                    break
                        except Exception:
                            pass
                
                # Semantic container extraction
                if not extracted_text or len(extracted_text.strip()) < CONTENT_THRESHOLD:
                    for container in SEMANTIC_CONTAINERS:
                        container_text = _extract_text_from_container(page, container)
                        if container_text and len(container_text.strip()) > len(extracted_text.strip()):
                            extracted_text = container_text
                            if len(extracted_text.strip()) >= CONTENT_THRESHOLD:
                                break
                    
                    if len(extracted_text.strip()) >= CONTENT_THRESHOLD:
                        break
                
                # Last resort: all page text
                if not extracted_text or len(extracted_text.strip()) < 200:
                    all_text = _extract_all_page_text(page)
                    if all_text and len(all_text.strip()) > len(extracted_text.strip()):
                        extracted_text = all_text
                        if len(extracted_text.strip()) >= CONTENT_THRESHOLD:
                            break
                
                if attempt < MAX_EXTRACTION_ATTEMPTS - 1:
                    time.sleep(1.0)
            
            browser.close()
            
            # Clean the extracted text
            cleaned_text = _final_cleanup(extracted_text) if extracted_text else ""
            
            if len(cleaned_text) < 200:
                return None, f"Content too short after {MAX_EXTRACTION_ATTEMPTS} attempts ({len(cleaned_text)} chars)"
            
            return cleaned_text, ""
            
    except Exception as e:
        return None, f"Playwright error: {str(e)}"


# =============================================================================
# MAIN EXTRACTION FUNCTION
# =============================================================================

def fetch_job_description(url: str, mode: str = "auto") -> Dict:
    """
    Fetch and extract job description text from a URL.
    
    Uses a multi-strategy approach:
    1. Schema.org JSON-LD extraction (most reliable for structured data)
    2. HTTP fetch with advanced content cleaning
    3. Playwright for JavaScript-rendered pages
    4. Trafilatura fallback for difficult pages
    
    Supports three modes:
    - "auto": Hybrid strategy - tries all methods intelligently
    - "requests": HTTP only - fast but may fail on JavaScript-rendered pages
    - "playwright": Browser only - slower but handles all pages
    
    Args:
        url: The job posting URL to fetch
        mode: Extraction mode - "auto", "requests", or "playwright"
        
    Returns:
        Dictionary with structure:
        {
            "url": str,
            "source": str,           # "requests", "playwright", or "schema"
            "ats_type": str,         # "workday", "greenhouse", "lever", etc.
            "raw_text": str,
            "schema_data": dict,     # Structured data if found
            "resolved_url": str,     # Canonical URL if resolved
            "error": str | None
        }
    """
    if not url or not url.strip():
        raise ValueError("URL cannot be empty")
    
    valid_modes = ["auto", "requests", "playwright"]
    if mode not in valid_modes:
        raise ValueError(f"Invalid mode '{mode}'. Must be one of: {valid_modes}")
    
    url = url.strip()
    
    # Detect ATS platform
    source = detect_source(url)
    
    # Resolve URL to canonical form
    resolved_url, was_resolved = resolve_url(url, source)
    
    result = {
        "url": url,
        "source": "",
        "ats_type": source,
        "raw_text": "",
        "schema_data": None,
        "resolved_url": resolved_url if was_resolved else url,
        "error": None,
    }
    
    # Use resolved URL for fetching
    fetch_url_to_use = resolved_url if was_resolved else url
    
    # =========================================================================
    # MODE: requests only
    # =========================================================================
    if mode == "requests":
        fetch_result = _fetch_with_requests(fetch_url_to_use)
        result["source"] = "requests"
        
        if not fetch_result.success:
            # Try original URL if resolved URL failed
            if was_resolved:
                fetch_result = _fetch_with_requests(url)
            
            if not fetch_result.success:
                result["error"] = fetch_result.error_message
                return result
        
        # Try Schema.org extraction first
        schema_data = extract_schema_job_posting(fetch_result.html)
        if schema_data and schema_data.get('description'):
            result["schema_data"] = schema_data
            result["raw_text"] = schema_to_text(schema_data)
            result["source"] = "schema"
            return result
        
        # Fall back to content cleaning
        cleaned_text = clean_html_content(fetch_result.html)
        result["raw_text"] = cleaned_text
        
        if not _is_content_valid(cleaned_text):
            # Try trafilatura
            traf_text = extract_with_trafilatura(fetch_result.html, fetch_url_to_use)
            if traf_text and len(traf_text) > len(cleaned_text):
                result["raw_text"] = traf_text
                result["source"] = "trafilatura"
            else:
                result["error"] = "Content may be incomplete. Try Playwright mode."
        
        return result
    
    # =========================================================================
    # MODE: playwright only
    # =========================================================================
    if mode == "playwright":
        text, error = _fetch_with_playwright(fetch_url_to_use, source)
        result["source"] = "playwright"
        
        if text and len(text.strip()) > 200:
            result["raw_text"] = text
        else:
            result["raw_text"] = text or ""
            result["error"] = error or "Failed to extract content with Playwright"
        
        return result
    
    # =========================================================================
    # MODE: auto (hybrid) - default behavior
    # =========================================================================
    
    # STEP 1: Try HTTP fetch
    fetch_result = _fetch_with_requests(fetch_url_to_use)
    
    if not fetch_result.success and was_resolved:
        # Fallback to original URL
        fetch_result = _fetch_with_requests(url)
    
    if fetch_result.success:
        # STEP 2: Try Schema.org extraction (most reliable)
        schema_data = extract_schema_job_posting(fetch_result.html)
        if schema_data and schema_data.get('description'):
            result["schema_data"] = schema_data
            result["raw_text"] = schema_to_text(schema_data)
            result["source"] = "schema"
            return result
        
        # STEP 3: Try content cleaning
        cleaned_text = clean_html_content(fetch_result.html)
        
        if _is_content_valid(cleaned_text):
            result["source"] = "requests"
            result["raw_text"] = cleaned_text
            return result
        
        # STEP 4: Try trafilatura
        traf_text = extract_with_trafilatura(fetch_result.html, fetch_url_to_use)
        if is_meaningful_content(traf_text, 500):
            result["source"] = "trafilatura"
            result["raw_text"] = traf_text
            return result
    
    # STEP 5: Fall back to Playwright
    playwright_text, playwright_error = _fetch_with_playwright(fetch_url_to_use, source)
    
    if playwright_text and len(playwright_text.strip()) > 200:
        result["source"] = "playwright"
        result["raw_text"] = playwright_text
        return result
    
    # Both methods failed - return best available content
    if fetch_result.success:
        cleaned_text = clean_html_content(fetch_result.html)
        traf_text = extract_with_trafilatura(fetch_result.html, fetch_url_to_use)
        
        best_text = cleaned_text if len(cleaned_text) > len(traf_text or "") else (traf_text or cleaned_text)
        
        if best_text:
            result["source"] = "requests"
            result["raw_text"] = best_text
            result["error"] = f"Content may be incomplete. Playwright: {playwright_error}"
            return result
    
    # Complete failure
    result["source"] = "none"
    result["error"] = f"Failed to extract content. HTTP: {fetch_result.error_message if not fetch_result.success else 'OK but short'}. Playwright: {playwright_error}"
    
    return result

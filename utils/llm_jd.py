"""
Job Description Extractor and Analyzer

Uses GPT to extract structured information from job descriptions.
Fetches job descriptions from URLs or processes raw text.
"""

import os
import json
from openai import OpenAI
from typing import Dict, Optional

# Import the hybrid fetcher module
from utils.jd_fetcher import fetch_job_description as fetch_jd


def extract_and_analyze_jd(
    job_url: Optional[str] = None, 
    raw_text: Optional[str] = None,
    fetch_mode: str = "auto"
) -> Dict:
    """
    Extract and analyze job description using GPT.
    
    Fetches job description from URL if provided, otherwise uses raw_text.
    Uses GPT to extract structured information.
    
    Args:
        job_url: URL of the job posting (optional)
        raw_text: Raw job description text (optional)
        fetch_mode: URL fetch mode - "auto", "requests", or "playwright"
        
    Returns:
        Dictionary containing:
        - responsibilities: list of responsibilities
        - required_skills: list of required skills
        - tools_technologies: list of tools and technologies
        - ats_keywords: list of ATS keywords
        - seniority_level: string indicating seniority level
        - _debug: debug information (optional)
        
    Raises:
        ValueError: If neither job_url nor raw_text is provided
        ValueError: If OPENAI_API_KEY is not set
    """
    # Validate inputs
    if not job_url and not raw_text:
        raise ValueError("Either job_url or raw_text must be provided")
    
    debug_info = ""
    jd_text = ""
    
    # Get job description text
    if job_url:
        # Use the fetcher with specified mode
        fetch_result = fetch_jd(job_url, mode=fetch_mode)
        jd_text = fetch_result.get("raw_text", "")
        
        # Build debug info from fetch result
        debug_lines = [
            f"URL: {fetch_result.get('url', job_url)}",
            f"Source: {fetch_result.get('source', 'unknown')}",
            f"ATS Type: {fetch_result.get('ats_type', 'unknown')}",
            f"Content Length: {len(jd_text)} chars",
        ]
        if fetch_result.get("error"):
            debug_lines.append(f"Error: {fetch_result['error']}")
        debug_info = "\n".join(debug_lines)
    else:
        jd_text = raw_text
        debug_info = f"Using provided text ({len(raw_text)} chars)"
    
    # Validate content
    if not jd_text or len(jd_text.strip()) < 50:
        return {
            "responsibilities": [],
            "required_skills": [],
            "tools_technologies": [],
            "ats_keywords": [],
            "seniority_level": "",
            "_debug": debug_info + "\nERROR: Content too short to analyze.",
            "_raw_content": jd_text[:500] if jd_text else "No content"
        }
    
    # Limit content to avoid token limits (approximately 12000 chars ~ 3000 tokens)
    if len(jd_text) > 12000:
        jd_text = jd_text[:12000]
        debug_info += f"\nTruncated content to 12000 chars"
    
    # Get API key from environment
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    
    # Initialize OpenAI client
    client = OpenAI(api_key=api_key)
    
    # Create prompt for GPT
    prompt = f"""Analyze the following job description and extract structured information.

Job Description:
{jd_text}

Extract and return a JSON object with these fields:
- "responsibilities": array of key job responsibilities (at least 3-5 items if present)
- "required_skills": array of required skills mentioned (technical and soft skills)
- "tools_technologies": array of tools, technologies, software, and platforms mentioned
- "ats_keywords": array of important keywords for ATS systems (job-specific terms, acronyms, certifications)
- "seniority_level": one of "junior", "mid-level", "senior", or "executive" based on experience requirements

If certain information is not clearly stated, make reasonable inferences based on the job title and description.
Return ONLY the JSON object."""
    
    try:
        # Call GPT API
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "You are a job description analyzer expert. Extract all relevant information even if it requires inference. Always return valid JSON with non-empty arrays when possible."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
        
        # Extract JSON from response
        content = response.choices[0].message.content.strip()
        debug_info += f"\nGPT response received ({len(content)} chars)"
        
        # Remove markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        # Parse JSON
        result = json.loads(content)
        
        # Ensure all required fields are present and are lists
        required_fields = ["responsibilities", "required_skills", "tools_technologies", "ats_keywords"]
        for field in required_fields:
            if field not in result:
                result[field] = []
            elif not isinstance(result[field], list):
                result[field] = [result[field]] if result[field] else []
        
        if "seniority_level" not in result:
            result["seniority_level"] = ""
        
        # Add debug info
        result["_debug"] = debug_info
        result["_raw_content_preview"] = jd_text[:500] + "..." if len(jd_text) > 500 else jd_text
        
        return result
        
    except json.JSONDecodeError as e:
        return {
            "responsibilities": [],
            "required_skills": [],
            "tools_technologies": [],
            "ats_keywords": [],
            "seniority_level": "",
            "_debug": debug_info + f"\nJSON parse error: {str(e)}",
            "_raw_content_preview": jd_text[:500] if jd_text else "No content"
        }
    except Exception as e:
        raise ValueError(f"Error calling OpenAI API: {str(e)}\n\nDebug info:\n{debug_info}")

"""
Resume Enhancement using GPT

Functions to rewrite bullets and suggest skills based on job description analysis.
GPT outputs plain text only - no LaTeX syntax.
"""

import os
import json
from openai import OpenAI
from typing import List, Dict


def rewrite_bullets(bullets: List[str], jd_analysis: Dict) -> List[Dict]:
    """
    Rewrite resume bullets for ATS optimization using GPT.
    
    GPT rewrites each bullet to better match the job description while
    maintaining accuracy. Outputs plain text only - no LaTeX.
    
    Args:
        bullets: List of original bullet points (plain text)
        jd_analysis: Job description analysis from extract_and_analyze_jd()
        
    Returns:
        List of dictionaries with "original" and "suggested" keys:
        [
            {
                "original": "...",
                "suggested": "..."
            }
        ]
        
    Raises:
        ValueError: If OPENAI_API_KEY is not set
    """
    # Get API key from environment
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    
    # Initialize OpenAI client
    client = OpenAI(api_key=api_key)
    
    # Prepare job description context
    jd_context = f"""Job Description Analysis:
- Required Skills: {', '.join(jd_analysis.get('required_skills', []))}
- Tools/Technologies: {', '.join(jd_analysis.get('tools_technologies', []))}
- ATS Keywords: {', '.join(jd_analysis.get('ats_keywords', []))}
- Seniority Level: {jd_analysis.get('seniority_level', '')}
- Key Responsibilities: {', '.join(jd_analysis.get('responsibilities', [])[:5])}"""
    
    # Create prompt for GPT
    prompt = f"""You are a resume optimization expert. Rewrite each bullet point to be more ATS-friendly and aligned with the job description, while maintaining accuracy and truthfulness.

{jd_context}

Original Bullets:
{chr(10).join(f"{i+1}. {bullet}" for i, bullet in enumerate(bullets))}

Instructions:
- Rewrite each bullet to incorporate relevant ATS keywords naturally
- Use action verbs and quantifiable metrics where possible
- Maintain the original meaning and accuracy
- Do NOT add tools, technologies, or skills that weren't in the original
- Output ONLY plain text - no LaTeX, no markdown, no special formatting
- Keep bullets concise and impactful

Return a JSON array with this exact structure:
[
    {{
        "original": "original bullet text",
        "suggested": "rewritten bullet text"
    }}
]

Return only the JSON array, no markdown code blocks, no explanations."""
    
    try:
        # Call GPT API
        # Note: Not using json_object format since we need an array, not an object
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a resume optimization expert. Return only valid JSON arrays. Do not hallucinate tools or technologies."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )
        
        # Extract JSON from response
        content = response.choices[0].message.content.strip()
        
        # Remove markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        # Parse JSON - should be an array
        parsed = json.loads(content)
        
        # Handle response format
        if isinstance(parsed, list):
            result = parsed
        elif isinstance(parsed, dict):
            # If GPT wrapped it in an object, extract the array
            for value in parsed.values():
                if isinstance(value, list):
                    result = value
                    break
            else:
                result = []
        else:
            result = []
        
        # Validate and ensure structure
        validated_result = []
        for i, item in enumerate(result):
            if isinstance(item, dict):
                original = item.get('original', bullets[i] if i < len(bullets) else '')
                suggested = item.get('suggested', original)
                validated_result.append({
                    "original": original,
                    "suggested": suggested
                })
            elif isinstance(item, str):
                # Fallback: if GPT returns just strings, pair with original
                validated_result.append({
                    "original": bullets[i] if i < len(bullets) else '',
                    "suggested": item
                })
        
        # Ensure we have results for all bullets
        while len(validated_result) < len(bullets):
            idx = len(validated_result)
            validated_result.append({
                "original": bullets[idx],
                "suggested": bullets[idx]
            })
        
        return validated_result[:len(bullets)]
        
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse GPT response as JSON: {str(e)}")
    except Exception as e:
        raise ValueError(f"Error calling OpenAI API: {str(e)}")


def suggest_skills(existing_skills: List[str], jd_skills: List[str]) -> Dict:
    """
    Suggest which skills to add, keep, or mark as optional based on job description.
    
    Uses GPT to intelligently match existing skills with job requirements
    and suggest additions.
    
    Args:
        existing_skills: List of skills currently in the resume
        jd_skills: List of skills from job description analysis
        
    Returns:
        Dictionary with:
        {
            "add": [list of skills to add],
            "keep": [list of skills to keep],
            "optional": [list of skills that are optional/nice-to-have]
        }
        
    Raises:
        ValueError: If OPENAI_API_KEY is not set
    """
    # Get API key from environment
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    
    # Initialize OpenAI client
    client = OpenAI(api_key=api_key)
    
    # Create prompt for GPT
    prompt = f"""Analyze the skills match between a resume and a job description.

Existing Resume Skills:
{', '.join(existing_skills) if existing_skills else 'None'}

Job Description Required Skills:
{', '.join(jd_skills) if jd_skills else 'None'}

Categorize skills into three groups:
1. "add": Skills from JD that are missing from resume (should be added)
2. "keep": Skills that are in both resume and JD (should be kept)
3. "optional": Skills in resume that aren't in JD but are still valuable (optional to keep)

Return a JSON object with this exact structure:
{{
    "add": ["skill1", "skill2"],
    "keep": ["skill1", "skill2"],
    "optional": ["skill1", "skill2"]
}}

Return only the JSON object, no markdown code blocks, no explanations."""
    
    try:
        # Call GPT API
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a skills matching expert. Return only valid JSON objects. Do not hallucinate skills."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
        
        # Extract JSON from response
        content = response.choices[0].message.content.strip()
        
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
        required_fields = ["add", "keep", "optional"]
        for field in required_fields:
            if field not in result:
                result[field] = []
            elif not isinstance(result[field], list):
                result[field] = []
        
        return result
        
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse GPT response as JSON: {str(e)}")
    except Exception as e:
        raise ValueError(f"Error calling OpenAI API: {str(e)}")


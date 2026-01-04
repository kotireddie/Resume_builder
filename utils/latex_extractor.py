"""
LaTeX Resume Extractor

Extracts experience and skills sections from LaTeX resume files.
Uses regex only - no GPT, deterministic, does not modify LaTeX.
"""

import re
from typing import Dict, List, Optional, Tuple


def read_latex_file(file_path: str) -> str:
    """Read LaTeX file as text."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def extract_braced_content(text: str, start_pos: int) -> Tuple[str, int]:
    """
    Extract content between balanced braces starting from start_pos.
    Handles nested braces properly.
    
    Returns (content, end_pos) where end_pos is position after closing brace.
    """
    if start_pos >= len(text) or text[start_pos] != '{':
        return '', start_pos
    
    depth = 0
    content_start = start_pos + 1
    pos = start_pos
    
    while pos < len(text):
        if text[pos] == '{':
            depth += 1
        elif text[pos] == '}':
            depth -= 1
            if depth == 0:
                return text[content_start:pos], pos + 1
        pos += 1
    
    # No closing brace found
    return text[content_start:], len(text)


def find_section(content: str, section_names: List[str]) -> Optional[str]:
    """
    Find section content by section name.
    Returns the content between the section start and next section (or end of file).
    Handles various section command formats.
    """
    for section_name in section_names:
        # Try different patterns for section commands
        patterns = [
            rf'\\section\*?\s*\{{\s*{re.escape(section_name)}\s*\}}',  # \section{Name} or \section*{Name}
            rf'\\section\*?\s*\{{\s*\\textbf\{{\s*{re.escape(section_name)}\s*\}}\s*\}}',  # \section{\textbf{Name}}
            rf'\\resumeSection\s*\{{\s*{re.escape(section_name)}\s*\}}',  # Custom \resumeSection
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                start_pos = match.end()
                # Find next section or end of document
                next_section = re.search(r'\\(?:section|resumeSection)\*?\s*\{', content[start_pos:], re.IGNORECASE)
                if next_section:
                    return content[start_pos:start_pos + next_section.start()].strip()
                else:
                    # Check for \end{document}
                    end_doc = re.search(r'\\end\{document\}', content[start_pos:])
                    if end_doc:
                        return content[start_pos:start_pos + end_doc.start()].strip()
                    return content[start_pos:].strip()
    return None


def extract_experiences(content: str) -> Dict[str, Dict]:
    r"""
    Extract experiences from LaTeX content.
    
    Handles multiple formats:
    - \resumeSubheading{role}{company}{date}{location}
    - \resumeSubheading{role}{date}{company}{location}
    - \resumeProjectHeading{title}{date}
    - \resumeSubHeadingListStart ... \resumeSubHeadingListEnd
    And bullets from \resumeItem{...} or \item ...
    """
    experiences = {}
    exp_idx = 0
    
    # Pattern 1: \resumeSubheading with 4 arguments (most common)
    # Handle nested braces by finding command and then extracting each argument
    subheading_starts = list(re.finditer(r'\\resumeSubheading\s*\{', content))
    
    for match in subheading_starts:
        pos = match.end() - 1  # Position at the opening brace
        
        # Extract 4 arguments
        args = []
        for _ in range(4):
            if pos < len(content) and content[pos] == '{':
                arg, pos = extract_braced_content(content, pos)
                args.append(arg.strip())
            else:
                # Skip whitespace to find next brace
                while pos < len(content) and content[pos] in ' \t\n\r':
                    pos += 1
                if pos < len(content) and content[pos] == '{':
                    arg, pos = extract_braced_content(content, pos)
                    args.append(arg.strip())
                else:
                    args.append('')
        
        if len(args) >= 2:
            exp_idx += 1
            role = args[0] if len(args) > 0 else ''
            company = args[1] if len(args) > 1 else ''
            date = args[2] if len(args) > 2 else ''
            location = args[3] if len(args) > 3 else ''
            
            # Find bullets for this experience
            # Start from current position
            start_pos = pos
            
            # Find end of this experience (next subheading or end of section)
            next_subheading = re.search(r'\\resumeSubheading\s*\{|\\resumeProjectHeading\s*\{|\\resumeSubHeadingListEnd', content[start_pos:])
            if next_subheading:
                end_pos = start_pos + next_subheading.start()
            else:
                end_pos = len(content)
            
            experience_content = content[start_pos:end_pos]
            bullets = extract_bullets(experience_content)
            
            experiences[f"experience_{exp_idx}"] = {
                "role": clean_latex_text(role),
                "company": clean_latex_text(company),
                "date": clean_latex_text(date),
                "location": clean_latex_text(location),
                "bullets": bullets
            }
    
    # Pattern 2: \resumeProjectHeading with 2 arguments
    project_starts = list(re.finditer(r'\\resumeProjectHeading\s*\{', content))
    
    for match in project_starts:
        pos = match.end() - 1
        
        args = []
        for _ in range(2):
            if pos < len(content) and content[pos] == '{':
                arg, pos = extract_braced_content(content, pos)
                args.append(arg.strip())
            else:
                while pos < len(content) and content[pos] in ' \t\n\r':
                    pos += 1
                if pos < len(content) and content[pos] == '{':
                    arg, pos = extract_braced_content(content, pos)
                    args.append(arg.strip())
                else:
                    args.append('')
        
        if len(args) >= 1 and args[0]:
            exp_idx += 1
            
            start_pos = pos
            next_heading = re.search(r'\\resumeSubheading\s*\{|\\resumeProjectHeading\s*\{|\\resumeSubHeadingListEnd|\\resumeItemListEnd', content[start_pos:])
            if next_heading:
                end_pos = start_pos + next_heading.start()
            else:
                end_pos = len(content)
            
            experience_content = content[start_pos:end_pos]
            bullets = extract_bullets(experience_content)
            
            experiences[f"experience_{exp_idx}"] = {
                "role": clean_latex_text(args[0]),
                "company": "",
                "date": clean_latex_text(args[1]) if len(args) > 1 else "",
                "location": "",
                "bullets": bullets
            }
    
    return experiences


def extract_bullets(content: str) -> List[str]:
    r"""
    Extract bullet points from LaTeX content.
    Handles \resumeItem{...} and \item ...
    """
    bullets = []
    
    # Extract from \resumeItem{...} - handle nested braces
    resume_item_starts = list(re.finditer(r'\\resumeItem\s*\{', content))
    
    for match in resume_item_starts:
        pos = match.end() - 1  # Position at opening brace
        bullet_text, _ = extract_braced_content(content, pos)
        cleaned = clean_latex_text(bullet_text)
        if cleaned:
            bullets.append(cleaned)
    
    # If no \resumeItem found, try \item
    if not bullets:
        # Match \item followed by text until next \item, \end, or end of string
        # Handle multi-line items
        item_pattern = r'\\item\s*(.*?)(?=\\item|\\end\{|\\resumeItemListEnd|$)'
        items = re.findall(item_pattern, content, re.DOTALL)
        
        for item in items:
            cleaned = clean_latex_text(item)
            if cleaned:
                bullets.append(cleaned)
    
    return bullets


def clean_latex_text(text: str) -> str:
    """
    Clean LaTeX text by removing common formatting commands
    while preserving the actual text content.
    """
    if not text:
        return ''
    
    # Remove common LaTeX commands while keeping their content
    # \textbf{text} -> text
    text = re.sub(r'\\textbf\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\textit\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\emph\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\underline\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\textsc\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\textsf\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\texttt\{([^}]*)\}', r'\1', text)
    
    # Remove \href{url}{text} -> text
    text = re.sub(r'\\href\{[^}]*\}\{([^}]*)\}', r'\1', text)
    
    # Remove \url{...}
    text = re.sub(r'\\url\{[^}]*\}', '', text)
    
    # Remove common single commands
    text = re.sub(r'\\[a-zA-Z]+\s*', '', text)
    
    # Remove remaining braces
    text = re.sub(r'[{}]', '', text)
    
    # Remove comments
    text = re.sub(r'%.*$', '', text, flags=re.MULTILINE)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def extract_skills(content: str) -> List[str]:
    r"""
    Extract skills from Skills section.
    
    Handles various formats:
    - \resumeItem{skill}
    - \resumeItemListStart \item ... \resumeItemListEnd
    - \item skill
    - \textbf{Category:} skill1, skill2, skill3
    - Plain text with commas
    """
    skills = []
    
    # Extract from \resumeItem{...}
    resume_item_starts = list(re.finditer(r'\\resumeItem\s*\{', content))
    
    for match in resume_item_starts:
        pos = match.end() - 1
        item_text, _ = extract_braced_content(content, pos)
        
        # Check if it's a category: skills format (e.g., "Languages: Python, Java, C++")
        if ':' in item_text:
            parts = item_text.split(':', 1)
            if len(parts) == 2:
                # Extract skills after the colon
                skills_text = parts[1]
                for skill in skills_text.split(','):
                    cleaned = clean_latex_text(skill)
                    if cleaned and len(cleaned) < 50:  # Reasonable skill length
                        skills.append(cleaned)
        else:
            # Single skill or comma-separated
            for skill in item_text.split(','):
                cleaned = clean_latex_text(skill)
                if cleaned and len(cleaned) < 50:
                    skills.append(cleaned)
    
    # Try \item format if no skills found
    if not skills:
        item_pattern = r'\\item\s*(.*?)(?=\\item|\\end\{|\\resumeItemListEnd|$)'
        items = re.findall(item_pattern, content, re.DOTALL)
        
        for item in items:
            # Check for category format
            if ':' in item:
                parts = item.split(':', 1)
                if len(parts) == 2:
                    for skill in parts[1].split(','):
                        cleaned = clean_latex_text(skill)
                        if cleaned and len(cleaned) < 50:
                            skills.append(cleaned)
            else:
                for skill in item.split(','):
                    cleaned = clean_latex_text(skill)
                    if cleaned and len(cleaned) < 50:
                        skills.append(cleaned)
    
    # Try to extract from plain text patterns like "Skills: X, Y, Z"
    if not skills:
        # Look for patterns like \textbf{Category:} X, Y, Z
        pattern = r'\\textbf\{([^}]+)\}\s*:?\s*([^\\]+)'
        matches = re.findall(pattern, content)
        for category, skills_text in matches:
            for skill in skills_text.split(','):
                cleaned = clean_latex_text(skill)
                if cleaned and len(cleaned) < 50:
                    skills.append(cleaned)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_skills = []
    for skill in skills:
        skill_lower = skill.lower().strip()
        if skill_lower and skill_lower not in seen:
            seen.add(skill_lower)
            unique_skills.append(skill.strip())
    
    return unique_skills


def extract_from_latex(file_path: str) -> Dict:
    """
    Main extraction function.
    
    Reads LaTeX file and extracts experiences and skills.
    
    Returns:
    {
        "experiences": {
            "experience_1": {
                "role": "...",
                "company": "...",
                "date": "...",
                "location": "...",
                "bullets": ["...", "..."]
            }
        },
        "skills": ["SQL", "Python", "Power BI"]
    }
    """
    content = read_latex_file(file_path)
    
    # Debug: Print first 500 chars to understand the format
    # print("DEBUG: First 500 chars of file:", content[:500])
    
    # Find Experience section - try multiple names
    experience_section_names = [
        "Professional Experience",
        "Experience",
        "Work Experience",
        "EXPERIENCE",
        "PROFESSIONAL EXPERIENCE",
        "WORK EXPERIENCE",
        "Employment",
        "Work History"
    ]
    experience_section = find_section(content, experience_section_names)
    
    # If no section found, try to extract from entire document
    if not experience_section:
        # Check if there are resumeSubheading commands anywhere
        if re.search(r'\\resumeSubheading\s*\{', content):
            experience_section = content
    
    if not experience_section:
        experiences = {}
    else:
        experiences = extract_experiences(experience_section)
    
    # Find Skills section
    skills_section_names = [
        "Skills",
        "Technical Skills",
        "Core Competencies",
        "SKILLS",
        "TECHNICAL SKILLS",
        "Technologies",
        "Tools & Technologies",
        "Programming Skills"
    ]
    skills_section = find_section(content, skills_section_names)
    
    # If no section found, try to extract from entire document
    if not skills_section:
        # Check for resumeItem or item commands with skills-like content
        if re.search(r'\\resumeItem\s*\{', content) or re.search(r'\\item', content):
            # Try to find a skills-related block
            skills_block_match = re.search(r'(Languages|Tools|Frameworks|Technologies)\s*:', content, re.IGNORECASE)
            if skills_block_match:
                # Extract surrounding content
                start = max(0, skills_block_match.start() - 100)
                end = min(len(content), skills_block_match.end() + 500)
                skills_section = content[start:end]
    
    if not skills_section:
        skills = []
    else:
        skills = extract_skills(skills_section)
    
    return {
        "experiences": experiences,
        "skills": skills
    }


def extract_from_latex_string(content: str) -> Dict:
    """
    Extract from LaTeX content string directly (for testing/debugging).
    """
    experience_section_names = [
        "Professional Experience",
        "Experience",
        "Work Experience",
        "EXPERIENCE",
        "PROFESSIONAL EXPERIENCE"
    ]
    experience_section = find_section(content, experience_section_names)
    
    if not experience_section:
        if re.search(r'\\resumeSubheading\s*\{', content):
            experience_section = content
    
    experiences = extract_experiences(experience_section) if experience_section else {}
    
    skills_section_names = [
        "Skills",
        "Technical Skills",
        "Core Competencies",
        "SKILLS",
        "TECHNICAL SKILLS"
    ]
    skills_section = find_section(content, skills_section_names)
    skills = extract_skills(skills_section) if skills_section else []
    
    return {
        "experiences": experiences,
        "skills": skills
    }

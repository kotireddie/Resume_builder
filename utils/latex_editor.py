"""
LaTeX Resume Editor

Replaces experience bullets and skills in LaTeX resume files.
Uses string replacement only - no LaTeX generation, no GPT.
"""

import re
from typing import Dict, List


def find_experience_section(content: str) -> tuple:
    """
    Find the Experience section boundaries.
    
    Returns:
        (start_pos, end_pos, section_content) or (None, None, None) if not found
    """
    section_names = [
        "Professional Experience",
        "Experience",
        "Work Experience"
    ]
    
    for section_name in section_names:
        escaped_name = re.escape(section_name)
        pattern = rf'\\section\{{{escaped_name}\}}'
        match = re.search(pattern, content)
        if match:
            start_pos = match.start()
            # Find next section or end of document
            next_section = re.search(r'\\section\{', content[match.end():])
            if next_section:
                end_pos = match.end() + next_section.start()
            else:
                end_pos = len(content)
            return (start_pos, end_pos, content[start_pos:end_pos])
    
    return (None, None, None)


def find_skills_section(content: str) -> tuple:
    """
    Find the Skills section boundaries.
    
    Returns:
        (start_pos, end_pos, section_content) or (None, None, None) if not found
    """
    section_names = [
        "Skills",
        "Technical Skills",
        "Core Competencies"
    ]
    
    for section_name in section_names:
        escaped_name = re.escape(section_name)
        pattern = rf'\\section\{{{escaped_name}\}}'
        match = re.search(pattern, content)
        if match:
            start_pos = match.start()
            # Find next section or end of document
            next_section = re.search(r'\\section\{', content[match.end():])
            if next_section:
                end_pos = match.end() + next_section.start()
            else:
                end_pos = len(content)
            return (start_pos, end_pos, content[start_pos:end_pos])
    
    return (None, None, None)


def replace_bullets_in_experience_block(exp_content: str, new_bullets: List[str]) -> str:
    """
    Replace all bullets in an experience block with new bullets.
    
    Args:
        exp_content: Content of a single experience (from subheading to next subheading)
        new_bullets: List of new bullet texts to insert
        
    Returns:
        Updated experience content with new bullets
    """
    if not new_bullets:
        return exp_content
    
    result = exp_content
    
    # Find all \resumeItem{...} in this experience block
    resume_item_pattern = r'\\resumeItem\{[^}]+\}'
    resume_items = list(re.finditer(resume_item_pattern, result))
    
    if resume_items:
        # Replace existing resumeItems
        if len(new_bullets) <= len(resume_items):
            # Replace first N items
            for i, match in enumerate(resume_items[:len(new_bullets)]):
                old_item = match.group(0)
                new_item = f'\\resumeItem{{{new_bullets[i]}}}'
                result = result.replace(old_item, new_item, 1)
            # Remove extra items if we have fewer new bullets
            if len(new_bullets) < len(resume_items):
                for match in resume_items[len(new_bullets):]:
                    old_item = match.group(0)
                    result = result.replace(old_item, '', 1)
        else:
            # Replace all existing and add new ones
            for i, match in enumerate(resume_items):
                old_item = match.group(0)
                new_item = f'\\resumeItem{{{new_bullets[i]}}}'
                result = result.replace(old_item, new_item, 1)
            # Add remaining new bullets after the last one
            last_match = resume_items[-1]
            insert_pos = last_match.end()
            additional_items = '\n'.join([
                f'\\resumeItem{{{bullet}}}'
                for bullet in new_bullets[len(resume_items):]
            ])
            result = result[:insert_pos] + '\n' + additional_items + result[insert_pos:]
    else:
        # Try to find \item entries (for itemize environments)
        item_pattern = r'(\\item\s+)([^\n\\]+?)(?=\\item|\\end\{|$)'
        item_matches = list(re.finditer(item_pattern, result, re.MULTILINE | re.DOTALL))
        
        if item_matches:
            # Replace items
            if len(new_bullets) <= len(item_matches):
                for i, match in enumerate(item_matches[:len(new_bullets)]):
                    old_item = match.group(0)
                    new_item = match.group(1) + new_bullets[i]
                    result = result.replace(old_item, new_item, 1)
                # Remove extra items
                if len(new_bullets) < len(item_matches):
                    for match in item_matches[len(new_bullets):]:
                        old_item = match.group(0)
                        result = result.replace(old_item, '', 1)
            else:
                # Replace all and add new
                for i, match in enumerate(item_matches):
                    old_item = match.group(0)
                    new_item = match.group(1) + new_bullets[i]
                    result = result.replace(old_item, new_item, 1)
                # Add remaining
                last_match = item_matches[-1]
                insert_pos = last_match.end()
                additional_items = '\n'.join([
                    f'\\item {bullet}'
                    for bullet in new_bullets[len(item_matches):]
                ])
                result = result[:insert_pos] + '\n' + additional_items + result[insert_pos:]
        else:
            # No existing bullets found, add new ones after subheading
            # Find where to insert (after any date/location info)
            insert_pos = len(result)
            # Try to find a good insertion point (after first line or after subheading)
            first_newline = result.find('\n')
            if first_newline > 0:
                insert_pos = first_newline + 1
            # Insert resumeItems
            items_text = '\n'.join([f'\\resumeItem{{{bullet}}}' for bullet in new_bullets])
            result = result[:insert_pos] + items_text + '\n' + result[insert_pos:]
    
    return result


def replace_experiences_in_section(
    experience_section: str,
    updated_experiences: Dict
) -> str:
    """
    Replace all experience bullets in the experience section.
    
    Args:
        experience_section: The experience section content
        updated_experiences: Dict with experience keys and updated bullets
            Format: {
                "experience_1": {
                    "role": "...",
                    "company": "...",
                    "bullets": ["...", "..."]  # User-approved bullets
                }
            }
        
    Returns:
        Updated experience section
    """
    result = experience_section
    
    # Process each experience
    for exp_key, exp_data in updated_experiences.items():
        if 'bullets' in exp_data:
            new_bullets = exp_data['bullets']
            
            if new_bullets:
                # Find the subheading for this experience
                role = exp_data.get('role', '')
                company = exp_data.get('company', '')
                
                if role and company:
                    # Find the subheading (escape special regex chars)
                    escaped_role = re.escape(role)
                    escaped_company = re.escape(company)
                    # Match \resumeSubheading{role}{company}{date}{location}
                    subheading_pattern = rf'\\resumeSubheading\{{{escaped_role}\}}\{{{escaped_company}\}}'
                    subheading_match = re.search(subheading_pattern, result)
                    
                    if subheading_match:
                        # Find the content after this subheading until next subheading
                        start_pos = subheading_match.end()
                        next_subheading = re.search(r'\\resumeSubheading\{', result[start_pos:])
                        if next_subheading:
                            end_pos = start_pos + next_subheading.start()
                        else:
                            end_pos = len(result)
                        
                        exp_content = result[start_pos:end_pos]
                        
                        # Replace all bullets in this experience's content
                        updated_exp_content = replace_bullets_in_experience_block(
                            exp_content,
                            new_bullets
                        )
                        
                        # Replace in result
                        result = result[:start_pos] + updated_exp_content + result[end_pos:]
    
    return result


def replace_skills_in_section(skills_section: str, updated_skills: List[str]) -> str:
    """
    Replace skills text in the Skills section.
    
    Args:
        skills_section: The skills section content
        updated_skills: List of new skills
        
    Returns:
        Updated skills section
    """
    if not updated_skills:
        return skills_section
    
    result = skills_section
    
    # Find all \resumeItem{...} in skills section
    resume_item_pattern = r'\\resumeItem\{[^}]+\}'
    resume_items = list(re.finditer(resume_item_pattern, result))
    
    # Replace existing resumeItems with new skills
    if resume_items:
        # Replace each resumeItem with new skills
        replacements = []
        for i, skill in enumerate(updated_skills):
            if i < len(resume_items):
                # Replace the content of this resumeItem
                match = resume_items[i]
                old_item = match.group(0)
                new_item = f'\\resumeItem{{{skill}}}'
                replacements.append((old_item, new_item))
        
        # Apply replacements
        for old, new in replacements:
            result = result.replace(old, new, 1)
        
        # If we have more skills than existing items, add them
        if len(updated_skills) > len(resume_items):
            # Find the last resumeItem or itemize environment
            last_item_match = resume_items[-1] if resume_items else None
            if last_item_match:
                # Add new items after the last one
                insert_pos = last_item_match.end()
                additional_items = '\n'.join([
                    f'\\resumeItem{{{skill}}}'
                    for skill in updated_skills[len(resume_items):]
                ])
                result = result[:insert_pos] + '\n' + additional_items + result[insert_pos:]
    else:
        # No existing resumeItems, try to find itemize environment
        itemize_pattern = r'(\\begin\{itemize\})(.*?)(\\end\{itemize\})'
        itemize_match = re.search(itemize_pattern, result, re.DOTALL)
        
        if itemize_match:
            # Replace items inside itemize
            items_text = '\n'.join([f'\\item {skill}' for skill in updated_skills])
            new_itemize = itemize_match.group(1) + '\n' + items_text + '\n' + itemize_match.group(3)
            result = result[:itemize_match.start()] + new_itemize + result[itemize_match.end():]
        else:
            # No existing structure, add resumeItems after section header
            section_header_match = re.search(r'\\section\{[^}]+\}', result)
            if section_header_match:
                insert_pos = section_header_match.end()
                items_text = '\n'.join([f'\\resumeItem{{{skill}}}' for skill in updated_skills])
                result = result[:insert_pos] + '\n' + items_text + '\n' + result[insert_pos:]
    
    return result


def update_latex_resume(
    original_latex: str,
    updated_experiences: Dict,
    updated_skills: List[str]
) -> str:
    """
    Update LaTeX resume with new experience bullets and skills.
    
    Args:
        original_latex: Original LaTeX resume content
        updated_experiences: Dictionary with experience updates
            Format: {
                "experience_1": {
                    "role": "...",
                    "company": "...",
                    "bullets": ["...", "..."]  # User-approved bullets
                }
            }
        updated_skills: List of updated skills
        
    Returns:
        Updated LaTeX resume content
    """
    result = original_latex
    
    # Update Experience section
    exp_start, exp_end, exp_section = find_experience_section(result)
    if exp_section:
        updated_exp_section = replace_experiences_in_section(exp_section, updated_experiences)
        result = result[:exp_start] + updated_exp_section + result[exp_end:]
    
    # Update Skills section
    skills_start, skills_end, skills_section = find_skills_section(result)
    if skills_section:
        updated_skills_section = replace_skills_in_section(skills_section, updated_skills)
        result = result[:skills_start] + updated_skills_section + result[skills_end:]
    
    return result


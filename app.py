"""
Resume Builder GPT - Streamlit App

Step-by-step resume optimization workflow using GPT.
"""

import os
import streamlit as st
from utils.latex_extractor import extract_from_latex, extract_from_latex_string
from utils.llm_jd import extract_and_analyze_jd
from utils.llm_resume import rewrite_bullets, suggest_skills
from utils.latex_editor import update_latex_resume


# Validate API key at startup
def validate_api_key():
    """Validate OPENAI_API_KEY is set. Stop app if missing."""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        st.error("❌ OPENAI_API_KEY environment variable is not set.")
        st.stop()
    return api_key


# Initialize session state
def init_session_state():
    """Initialize session state variables."""
    if 'step' not in st.session_state:
        st.session_state.step = 1
    if 'latex_content' not in st.session_state:
        st.session_state.latex_content = None
    if 'extracted_data' not in st.session_state:
        st.session_state.extracted_data = None
    if 'jd_analysis' not in st.session_state:
        st.session_state.jd_analysis = None
    if 'bullet_suggestions' not in st.session_state:
        st.session_state.bullet_suggestions = {}
    if 'skill_suggestions' not in st.session_state:
        st.session_state.skill_suggestions = {}
    if 'updated_latex' not in st.session_state:
        st.session_state.updated_latex = None
    if 'jd_url' not in st.session_state:
        st.session_state.jd_url = None
    if 'jd_text' not in st.session_state:
        st.session_state.jd_text = None
    if 'jd_fetch_mode' not in st.session_state:
        st.session_state.jd_fetch_mode = "auto"


# Validate API key at startup
validate_api_key()
init_session_state()


# Page configuration
st.set_page_config(
    page_title="Resume Builder GPT",
    page_icon="📄",
    layout="wide"
)

st.title("📄 Resume Builder GPT")
st.markdown("Optimize your LaTeX resume for ATS using AI")

# Progress indicator
steps = [
    "Upload Resume",
    "Extract Data",
    "Input Job Description",
    "Analyze JD",
    "ATS Dashboard",
    "Review Bullets",
    "Review Skills",
    "Generate LaTeX",
    "Download"
]

progress = st.progress(st.session_state.step / len(steps))
st.caption(f"Step {st.session_state.step} of {len(steps)}: {steps[st.session_state.step - 1]}")


def go_to_step(step_num):
    """Navigate to a specific step."""
    st.session_state.step = step_num
    st.rerun()


def reset_to_home():
    """Reset all session state and go to step 1."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.session_state.step = 1
    st.rerun()


def render_navigation(current_step, show_home=True, show_back=True, back_step=None):
    """Render navigation buttons at the top of each step."""
    if current_step == 1:
        return  # No navigation on first step
    
    cols = st.columns([1, 1, 6])
    
    with cols[0]:
        if show_home:
            if st.button("🏠 Home", key=f"home_{current_step}", help="Start over from the beginning"):
                reset_to_home()
    
    with cols[1]:
        if show_back and current_step > 1:
            prev_step = back_step if back_step else current_step - 1
            if st.button("← Back", key=f"back_{current_step}", help=f"Go back to Step {prev_step}"):
                go_to_step(prev_step)
    
    st.markdown("---")

# Step 1: Upload LaTeX Resume
if st.session_state.step == 1:
    st.header("Step 1: Upload LaTeX Resume")
    st.markdown("Upload your LaTeX resume file (.tex)")
    
    uploaded_file = st.file_uploader(
        "Choose a .tex file",
        type=['tex'],
        help="Upload your LaTeX resume file"
    )
    
    if uploaded_file is not None:
        # Read file content
        latex_content = uploaded_file.read().decode('utf-8')
        st.session_state.latex_content = latex_content
        
        st.success("✅ Resume uploaded successfully!")
        st.code(latex_content[:500] + "..." if len(latex_content) > 500 else latex_content, language='latex')
        
        if st.button("Next: Extract Data", type="primary"):
            st.session_state.step = 2
            st.rerun()

# Step 2: Extract Experience Bullets + Skills
if st.session_state.step == 2:
    render_navigation(2)
    st.header("Step 2: Extract Experience & Skills")
    
    if st.session_state.latex_content is None:
        st.warning("Please upload a resume first.")
    else:
        with st.spinner("Extracting experience bullets and skills..."):
            try:
                # Extract data directly from string content
                extracted_data = extract_from_latex_string(st.session_state.latex_content)
                st.session_state.extracted_data = extracted_data
                
                # Check if extraction was successful
                has_experiences = bool(extracted_data.get('experiences'))
                has_skills = bool(extracted_data.get('skills'))
                
                if has_experiences or has_skills:
                    st.success("✅ Extraction complete!")
                else:
                    st.warning("⚠️ No experiences or skills were extracted. See debugging info below.")
                
                # Display extracted data
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("📋 Experiences")
                    if extracted_data['experiences']:
                        for exp_key, exp_data in extracted_data['experiences'].items():
                            with st.expander(f"{exp_data['role']} at {exp_data['company']}", expanded=True):
                                st.write(f"**Date:** {exp_data.get('date', 'N/A')}")
                                st.write(f"**Location:** {exp_data.get('location', 'N/A')}")
                                st.write(f"**Bullets ({len(exp_data.get('bullets', []))}):**")
                                for bullet in exp_data.get('bullets', []):
                                    st.write(f"- {bullet}")
                    else:
                        st.warning("No experiences found.")
                        st.info("💡 Expected format: `\\resumeSubheading{Role}{Company}{Date}{Location}`")
                
                with col2:
                    st.subheader("🛠️ Skills")
                    if extracted_data['skills']:
                        for skill in extracted_data['skills']:
                            st.write(f"• {skill}")
                    else:
                        st.warning("No skills found.")
                        st.info("💡 Expected format: `\\resumeItem{Skill}` or `\\item Skill`")
                
                # Debug section (collapsible)
                with st.expander("🔧 Debug Information"):
                    st.write("**LaTeX Preview (first 1000 chars):**")
                    st.code(st.session_state.latex_content[:1000], language='latex')
                    
                    st.write("**Looking for these patterns:**")
                    st.write("- Sections: `\\section{Experience}`, `\\section{Professional Experience}`, `\\section{Skills}`")
                    st.write("- Experience: `\\resumeSubheading{...}{...}{...}{...}`")
                    st.write("- Bullets: `\\resumeItem{...}` or `\\item ...`")
                    
                    # Check for common patterns
                    content = st.session_state.latex_content
                    st.write("**Detected patterns:**")
                    if '\\section' in content:
                        import re
                        sections = re.findall(r'\\section\*?\{([^}]+)\}', content)
                        st.write(f"- Sections found: {sections}")
                    else:
                        st.write("- No `\\section` commands found")
                    
                    if '\\resumeSubheading' in content:
                        count = content.count('\\resumeSubheading')
                        st.write(f"- `\\resumeSubheading` found: {count} times")
                    else:
                        st.write("- No `\\resumeSubheading` commands found")
                    
                    if '\\resumeItem' in content:
                        count = content.count('\\resumeItem')
                        st.write(f"- `\\resumeItem` found: {count} times")
                    else:
                        st.write("- No `\\resumeItem` commands found")
                    
                    if '\\item' in content:
                        count = content.count('\\item')
                        st.write(f"- `\\item` found: {count} times")
                
                # Allow proceeding even with partial data
                if st.button("Next: Input Job Description", type="primary"):
                    if not has_experiences:
                        st.warning("⚠️ No experiences extracted. You may need to manually check your LaTeX format.")
                    st.session_state.step = 3
                    st.rerun()
                    
            except Exception as e:
                import traceback
                st.error(f"❌ Error extracting data: {str(e)}")
                with st.expander("🔧 Error Details"):
                    st.code(traceback.format_exc())
                st.info("💡 Tip: Make sure your LaTeX file uses standard resume template commands.")

# Step 3: Input Job Description
if st.session_state.step == 3:
    render_navigation(3)
    st.header("Step 3: Input Job Description")
    
    if st.session_state.extracted_data is None:
        st.warning("Please complete previous steps first.")
    else:
        input_method = st.radio(
            "How would you like to provide the job description?",
            ["URL", "Paste Text"],
            horizontal=True
        )
        
        if input_method == "URL":
            jd_url = st.text_input(
                "Job Description URL",
                value=st.session_state.jd_url or "",
                placeholder="https://..."
            )
            st.session_state.jd_url = jd_url if jd_url else None
            st.session_state.jd_text = None
            
            # Fetch mode selection
            st.markdown("**Select Fetch Mode:**")
            fetch_mode = st.radio(
                "How should we extract content from the URL?",
                options=["auto", "requests", "playwright"],
                index=["auto", "requests", "playwright"].index(st.session_state.jd_fetch_mode),
                horizontal=True,
                help="Auto: Tries HTTP first, falls back to browser. Requests: Fast HTTP only. Playwright: Browser rendering (slower but handles JavaScript)."
            )
            st.session_state.jd_fetch_mode = fetch_mode
            
            # Mode descriptions
            mode_info = {
                "auto": "🔄 **Auto (Recommended)**: Tries fast HTTP fetch first. If content is short or missing, automatically uses browser rendering.",
                "requests": "⚡ **HTTP Requests**: Fast but may fail on JavaScript-heavy sites (LinkedIn, Workday, etc.).",
                "playwright": "🌐 **Playwright Browser**: Slower but handles all sites including JavaScript-rendered pages."
            }
            st.info(mode_info[fetch_mode])
            
            if jd_url:
                st.success("✅ URL entered. Click 'Analyze Job Description' to fetch and analyze.")
        else:
            jd_text = st.text_area(
                "Paste Job Description",
                value=st.session_state.jd_text or "",
                height=300,
                placeholder="Paste the full job description here..."
            )
            st.session_state.jd_text = jd_text if jd_text else None
            st.session_state.jd_url = None
            if jd_text:
                st.info("Click 'Analyze Job Description' to analyze.")
        
        st.markdown("---")
        if st.button("Analyze Job Description →", type="primary", disabled=not (st.session_state.jd_url or st.session_state.jd_text), use_container_width=True):
            st.session_state.step = 4
            st.rerun()

# Step 4: GPT Analyzes JD + ATS Keywords
if st.session_state.step == 4:
    render_navigation(4)
    st.header("Step 4: Analyzing Job Description")
    
    if st.session_state.extracted_data is None:
        st.warning("Please complete previous steps first.")
    elif not st.session_state.jd_url and not st.session_state.jd_text:
        st.warning("Please provide a job description in Step 3.")
    else:
        if st.session_state.jd_analysis is None:
            # Show which mode is being used
            if st.session_state.jd_url:
                mode = st.session_state.jd_fetch_mode
                mode_labels = {"auto": "Auto (HTTP + Playwright fallback)", "requests": "HTTP Requests", "playwright": "Playwright Browser"}
                st.info(f"🔍 Fetching URL using: **{mode_labels.get(mode, mode)}**")
            
            with st.spinner("Fetching and analyzing the job description..."):
                try:
                    jd_analysis = extract_and_analyze_jd(
                        job_url=st.session_state.jd_url,
                        raw_text=st.session_state.jd_text,
                        fetch_mode=st.session_state.jd_fetch_mode
                    )
                    st.session_state.jd_analysis = jd_analysis
                    st.rerun()
                except ValueError as e:
                    error_msg = str(e)
                    if "OPENAI_API_KEY" in error_msg:
                        st.error("❌ OpenAI API key is not set. Please set the OPENAI_API_KEY environment variable.")
                        st.stop()
                    elif "Failed to fetch" in error_msg:
                        st.error(f"❌ Could not fetch job description from URL: {error_msg}")
                        st.info("💡 Tip: Try using 'Playwright' mode for JavaScript-heavy sites.")
                    elif "Playwright" in error_msg:
                        st.error(f"❌ Playwright error: {error_msg}")
                        st.info("💡 Tip: Make sure Playwright is installed: `pip install playwright && playwright install chromium`")
                    else:
                        st.error(f"❌ Error: {error_msg}")
                    if st.button("Go Back"):
                        st.session_state.step = 3
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ Unexpected error analyzing job description: {str(e)}")
                    st.info("💡 Tip: Make sure your job description text is clear and readable.")
                    if st.button("Go Back"):
                        st.session_state.step = 3
                        st.rerun()
        else:
            jd_analysis = st.session_state.jd_analysis
            
            # Check if we got actual results
            total_items = (
                len(jd_analysis.get('required_skills', [])) +
                len(jd_analysis.get('tools_technologies', [])) +
                len(jd_analysis.get('ats_keywords', [])) +
                len(jd_analysis.get('responsibilities', []))
            )
            
            if total_items > 0:
                st.success("✅ Job description analyzed successfully!")
            else:
                st.warning("⚠️ Analysis completed but no data was extracted. See debug info below.")
            
            # Show quick preview
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Seniority Level:** {jd_analysis.get('seniority_level', 'N/A') or 'Not detected'}")
                st.write(f"**Required Skills:** {len(jd_analysis.get('required_skills', []))} found")
                st.write(f"**Tools/Technologies:** {len(jd_analysis.get('tools_technologies', []))} found")
            with col2:
                st.write(f"**ATS Keywords:** {len(jd_analysis.get('ats_keywords', []))} found")
                st.write(f"**Responsibilities:** {len(jd_analysis.get('responsibilities', []))} found")
            
            # Show debug information if available
            if '_debug' in jd_analysis or '_raw_content_preview' in jd_analysis:
                with st.expander("🔧 Debug Information", expanded=(total_items == 0)):
                    if '_debug' in jd_analysis:
                        st.write("**Fetch Log:**")
                        st.code(jd_analysis['_debug'])
                    if '_raw_content_preview' in jd_analysis:
                        st.write("**Content Preview (first 500 chars):**")
                        st.code(jd_analysis['_raw_content_preview'])
                    
                    if total_items == 0:
                        st.warning("""
                        **Why did extraction fail?**
                        
                        Common reasons:
                        1. **JavaScript-rendered site**: Many job sites (LinkedIn, Indeed, etc.) load content with JavaScript, which we can't fetch directly.
                        2. **Login required**: The page may require authentication.
                        3. **Blocked request**: The site may block automated requests.
                        
                        **Solution**: Copy and paste the job description text directly in Step 3.
                        """)
            
            # Offer to retry with text if URL failed
            if total_items == 0 and st.session_state.jd_url:
                st.markdown("---")
                st.info("💡 **Tip:** Try pasting the job description text directly instead of using a URL.")
                if st.button("🔄 Retry with Paste Text", use_container_width=True):
                    st.session_state.jd_analysis = None
                    st.session_state.jd_url = None
                    st.session_state.step = 3
                    st.rerun()
            
            st.markdown("---")
            if total_items > 0:
                if st.button("Next: View ATS Dashboard →", type="primary", use_container_width=True):
                    st.session_state.step = 5
                    st.rerun()
            else:
                if st.button("Continue Anyway →", use_container_width=True):
                    st.session_state.step = 5
                    st.rerun()

# Step 5: Show ATS Analysis Dashboard
if st.session_state.step == 5:
    render_navigation(5)
    st.header("Step 5: ATS Analysis Dashboard")
    
    if st.session_state.jd_analysis is None:
        st.warning("Job description analysis not available.")
    else:
        jd_analysis = st.session_state.jd_analysis
        
        # Display ATS analysis
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 Job Requirements")
            st.write("**Required Skills:**")
            st.write(", ".join(jd_analysis.get('required_skills', [])) or "None found")
            
            st.write("**Tools & Technologies:**")
            st.write(", ".join(jd_analysis.get('tools_technologies', [])) or "None found")
            
            st.write("**Seniority Level:**")
            st.write(jd_analysis.get('seniority_level', 'N/A') or "Not detected")
        
        with col2:
            st.subheader("🔑 ATS Keywords")
            st.write(", ".join(jd_analysis.get('ats_keywords', [])) or "None found")
            
            st.subheader("📝 Key Responsibilities")
            responsibilities = jd_analysis.get('responsibilities', [])[:5]
            if responsibilities:
                for resp in responsibilities:
                    st.write(f"- {resp}")
            else:
                st.write("None found")
        
        st.markdown("---")
        if st.button("Next: Review Bullet Suggestions →", type="primary", use_container_width=True):
            st.session_state.step = 6
            st.rerun()

# Step 6: Show Bullet Suggestions (Editable)
if st.session_state.step == 6:
    render_navigation(6)
    st.header("Step 6: Review & Edit Bullet Suggestions")
    st.markdown("Review GPT's suggestions and edit them as needed. Your edits will be saved.")
    
    if st.session_state.extracted_data is None or st.session_state.jd_analysis is None:
        st.warning("⚠️ Please complete previous steps first.")
    else:
        if not st.session_state.bullet_suggestions:
            st.info("🔄 Generating bullet suggestions...")
            with st.spinner("GPT is rewriting bullets for ATS optimization. This may take a moment..."):
                try:
                    # Get all bullets from all experiences
                    all_bullet_suggestions = {}
                    for exp_key, exp_data in st.session_state.extracted_data['experiences'].items():
                        bullets = exp_data.get('bullets', [])
                        if bullets:
                            try:
                                suggestions = rewrite_bullets(bullets, st.session_state.jd_analysis)
                                all_bullet_suggestions[exp_key] = {
                                    'role': exp_data['role'],
                                    'company': exp_data['company'],
                                    'suggestions': suggestions
                                }
                            except Exception as e:
                                st.error(f"Error processing {exp_data['role']}: {str(e)}")
                                # Use original bullets as fallback
                                all_bullet_suggestions[exp_key] = {
                                    'role': exp_data['role'],
                                    'company': exp_data['company'],
                                    'suggestions': [{'original': b, 'suggested': b} for b in bullets]
                                }
                    
                    if all_bullet_suggestions:
                        st.session_state.bullet_suggestions = all_bullet_suggestions
                        st.rerun()
                    else:
                        st.error("❌ No experiences with bullets found. Please check your resume.")
                except Exception as e:
                    st.error(f"❌ Error generating suggestions: {str(e)}")
                    st.info("💡 Tip: Make sure your resume has experience sections with bullets.")
        else:
            # Display editable bullet suggestions
            if not st.session_state.bullet_suggestions:
                st.warning("No bullet suggestions available.")
            else:
                for exp_key, exp_data in st.session_state.bullet_suggestions.items():
                    with st.expander(f"📋 {exp_data['role']} at {exp_data['company']}", expanded=True):
                        for idx, suggestion in enumerate(exp_data['suggestions']):
                            col1, col2 = st.columns([1, 3])
                            with col1:
                                st.write("**Original:**")
                                st.text_area(
                                    f"Original {idx+1}",
                                    value=suggestion['original'],
                                    height=100,
                                    key=f"orig_{exp_key}_{idx}",
                                    disabled=True,
                                    label_visibility="collapsed"
                                )
                            with col2:
                                st.write("**Suggested (Editable):**")
                                # Get current value from session state or use suggested
                                current_value = suggestion.get('suggested', suggestion.get('original', ''))
                                edited = st.text_area(
                                    f"Edit bullet {idx+1}",
                                    value=current_value,
                                    height=100,
                                    key=f"sugg_{exp_key}_{idx}",
                                    label_visibility="collapsed",
                                    help="Edit this bullet point as needed"
                                )
                                # Update suggestion in session state
                                if exp_key in st.session_state.bullet_suggestions:
                                    if idx < len(st.session_state.bullet_suggestions[exp_key]['suggestions']):
                                        st.session_state.bullet_suggestions[exp_key]['suggestions'][idx]['suggested'] = edited
            
            st.markdown("---")
            if st.button("Next: Review Skills →", type="primary", use_container_width=True):
                st.session_state.step = 7
                st.rerun()

# Step 7: Show Skill Suggestions (Editable)
if st.session_state.step == 7:
    render_navigation(7)
    st.header("Step 7: Review & Edit Skill Suggestions")
    st.markdown("Review and edit which skills to add, keep, or mark as optional.")
    
    if st.session_state.extracted_data is None or st.session_state.jd_analysis is None:
        st.warning("⚠️ Please complete previous steps first.")
    else:
        if not st.session_state.skill_suggestions:
            st.info("🔄 Generating skill suggestions...")
            with st.spinner("GPT is analyzing skill matches. This may take a moment..."):
                try:
                    existing_skills = st.session_state.extracted_data.get('skills', [])
                    jd_skills = st.session_state.jd_analysis.get('required_skills', []) + \
                               st.session_state.jd_analysis.get('tools_technologies', [])
                    if not existing_skills:
                        st.warning("⚠️ No skills found in your resume.")
                    if not jd_skills:
                        st.warning("⚠️ No skills found in job description.")
                    
                    suggestions = suggest_skills(existing_skills, jd_skills)
                    st.session_state.skill_suggestions = suggestions
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error generating suggestions: {str(e)}")
                    st.info("💡 Tip: Make sure your resume and job description have skills listed.")
        else:
            suggestions = st.session_state.skill_suggestions
            
            # Helper function to parse skills
            def parse_skills(text):
                skills = []
                for line in text.split('\n'):
                    line = line.strip()
                    if ',' in line:
                        skills.extend([s.strip() for s in line.split(',') if s.strip()])
                    elif line:
                        skills.append(line)
                return [s for s in skills if s]
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.subheader("➕ Add These Skills")
                st.caption("Skills from JD that are missing from your resume")
                add_skills_text = "\n".join(suggestions.get('add', []))
                add_skills = st.text_area(
                    "Skills to add",
                    value=add_skills_text,
                    height=200,
                    key="add_skills",
                    help="One skill per line or comma-separated",
                    label_visibility="collapsed"
                )
            
            with col2:
                st.subheader("✅ Keep These Skills")
                st.caption("Skills you have that match the JD")
                keep_skills_text = "\n".join(suggestions.get('keep', []))
                keep_skills = st.text_area(
                    "Skills to keep",
                    value=keep_skills_text,
                    height=200,
                    key="keep_skills",
                    help="One skill per line or comma-separated",
                    label_visibility="collapsed"
                )
            
            with col3:
                st.subheader("⚪ Optional Skills")
                st.caption("Skills in your resume but not in JD")
                optional_skills_text = "\n".join(suggestions.get('optional', []))
                optional_skills = st.text_area(
                    "Optional skills",
                    value=optional_skills_text,
                    height=200,
                    key="optional_skills",
                    help="One skill per line or comma-separated",
                    label_visibility="collapsed"
                )
            
            # Update session state with parsed skills
            st.session_state.skill_suggestions = {
                'add': parse_skills(add_skills),
                'keep': parse_skills(keep_skills),
                'optional': parse_skills(optional_skills)
            }
            
            # Show summary
            st.info(f"📊 Summary: {len(st.session_state.skill_suggestions['add'])} to add, "
                   f"{len(st.session_state.skill_suggestions['keep'])} to keep, "
                   f"{len(st.session_state.skill_suggestions['optional'])} optional")
            
            st.markdown("---")
            if st.button("Next: Generate LaTeX →", type="primary", use_container_width=True):
                st.session_state.step = 8
                st.rerun()

# Step 8: Generate Updated LaTeX
if st.session_state.step == 8:
    render_navigation(8)
    st.header("Step 8: Generate Updated LaTeX")
    st.markdown("Generate the final LaTeX resume with your approved edits.")
    
    if (st.session_state.latex_content is None or 
        not st.session_state.bullet_suggestions or
        not st.session_state.skill_suggestions):
        st.warning("⚠️ Please complete previous steps first.")
    else:
        if st.session_state.updated_latex is None:
            with st.spinner("🔄 Generating updated LaTeX resume..."):
                try:
                    # Prepare updated experiences
                    updated_experiences = {}
                    for exp_key, exp_data in st.session_state.bullet_suggestions.items():
                        # Get edited bullets from suggestions
                        edited_bullets = []
                        for suggestion in exp_data.get('suggestions', []):
                            edited_bullets.append(suggestion.get('suggested', suggestion.get('original', '')))
                        
                        updated_experiences[exp_key] = {
                            'role': exp_data['role'],
                            'company': exp_data['company'],
                            'bullets': edited_bullets
                        }
                    
                    # Prepare updated skills (combine keep + add, exclude optional unless user wants them)
                    updated_skills = (
                        st.session_state.skill_suggestions.get('keep', []) +
                        st.session_state.skill_suggestions.get('add', [])
                    )
                    
                    if not updated_skills:
                        st.warning("⚠️ No skills selected. Using original skills.")
                        updated_skills = st.session_state.extracted_data.get('skills', [])
                    
                    # Generate updated LaTeX
                    updated_latex = update_latex_resume(
                        st.session_state.latex_content,
                        updated_experiences,
                        updated_skills
                    )
                    
                    st.session_state.updated_latex = updated_latex
                    st.rerun()
                    
                except KeyError as e:
                    st.error(f"❌ Error: Missing required data - {str(e)}")
                    st.info("💡 Tip: Make sure you've completed all previous steps and edited your bullets/skills.")
                    if st.button("Go Back"):
                        st.session_state.step = 7
                        st.rerun()
                except Exception as e:
                    error_msg = str(e)
                    if "section" in error_msg.lower() or "not found" in error_msg.lower():
                        st.error("❌ Could not find Experience or Skills sections in your LaTeX file.")
                        st.info("💡 Tip: Make sure your LaTeX file contains the expected section structure.")
                    else:
                        st.error(f"❌ Error generating LaTeX: {error_msg}")
        else:
            st.success("✅ Updated LaTeX generated successfully!")
            
            # Show summary of changes
            st.subheader("📊 Summary of Changes")
            col1, col2 = st.columns(2)
            with col1:
                total_bullets = sum(len(exp['suggestions']) for exp in st.session_state.bullet_suggestions.values())
                st.metric("Bullets Updated", total_bullets)
            with col2:
                total_skills = len(st.session_state.skill_suggestions.get('keep', []) + 
                                 st.session_state.skill_suggestions.get('add', []))
                st.metric("Skills in Resume", total_skills)
            
            # Show preview
            with st.expander("📄 Preview Updated LaTeX (first 2000 characters)"):
                preview_text = st.session_state.updated_latex[:2000]
                if len(st.session_state.updated_latex) > 2000:
                    preview_text += "\n\n... (truncated, full file available for download)"
                st.code(preview_text, language='latex')
            
            st.markdown("---")
            if st.button("Next: Download →", type="primary", use_container_width=True):
                st.session_state.step = 9
                st.rerun()

# Step 9: Download .tex File
if st.session_state.step == 9:
    render_navigation(9)
    st.header("Step 9: Download Updated Resume")
    
    if st.session_state.updated_latex is None:
        st.warning("Updated LaTeX not available.")
    else:
        st.success("🎉 Your optimized resume is ready for download!")
        
        st.markdown("---")
        
        # Download button
        st.download_button(
            label="📥 Download Updated Resume (.tex)",
            data=st.session_state.updated_latex,
            file_name="resume_optimized.tex",
            mime="text/plain",
            type="primary",
            use_container_width=True
        )
        
        # Show final preview
        with st.expander("📄 Final LaTeX Preview"):
            st.code(st.session_state.updated_latex, language='latex')
        
        st.markdown("---")
        st.markdown("### What's next?")
        st.markdown("""
        1. **Compile your LaTeX** - Use a LaTeX editor (Overleaf, TeXstudio, etc.) to generate PDF
        2. **Review the output** - Check formatting and make any final adjustments
        3. **Start a new optimization** - Click the button below to start over with a new job description
        """)
        
        if st.button("🔄 Start Over with New Job", use_container_width=True):
            reset_to_home()


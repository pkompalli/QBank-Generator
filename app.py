"""
QBank Generator - Flask Backend
Generates MCQs for NEET PG and USMLE using Claude API
"""

import json
import os
import re
import requests
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from anthropic import Anthropic
from dotenv import load_dotenv
from google import genai
from PIL import Image

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('qbank_generator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Load subject/topic data
def load_subjects_data():
    with open('NEET PG Subjects-Topics-Chapters.json', 'r') as f:
        neet_data = json.load(f)
    with open('USMLE Subjects-Topics-Chapters.json', 'r') as f:
        usmle_data = json.load(f)
    return neet_data, usmle_data

# Load example questions for reference
def load_examples():
    with open('NEET PG Example.json', 'r') as f:
        neet_example = json.load(f)
    with open('USMLE Example.json', 'r') as f:
        usmle_example = json.load(f)
    return neet_example[:5], usmle_example[:5]  # First 5 as examples

NEET_DATA, USMLE_DATA = load_subjects_data()
NEET_EXAMPLES, USMLE_EXAMPLES = load_examples()

# Initialize Anthropic client
client = Anthropic()

# Initialize Gemini client for image generation
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
gemini_client = None
if GOOGLE_API_KEY and GOOGLE_API_KEY != 'your_gemini_api_key_here':
    try:
        gemini_client = genai.Client(api_key=GOOGLE_API_KEY)
        logger.info("Google Gemini API initialized for image generation")
    except Exception as e:
        logger.warning(f"Failed to initialize Gemini API: {e}")
        gemini_client = None
else:
    logger.warning("Google Gemini API key not configured - image generation will be disabled")

# Image cache configuration
IMAGE_CACHE_FILE = 'image_cache.json'

def load_image_cache():
    """Load the image cache from disk."""
    if os.path.exists(IMAGE_CACHE_FILE):
        try:
            with open(IMAGE_CACHE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading image cache: {e}")
            return {}
    return {}

def save_image_cache(cache):
    """Save the image cache to disk."""
    try:
        with open(IMAGE_CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving image cache: {e}")

def get_cache_key(search_terms, image_type):
    """Generate a unique cache key for image search."""
    key_string = f"{image_type}:{','.join(sorted(search_terms[:3]))}"
    return hashlib.md5(key_string.encode()).hexdigest()

def get_cached_image(search_terms, image_type):
    """Check if we have a cached image for these search parameters."""
    cache = load_image_cache()
    cache_key = get_cache_key(search_terms, image_type or '')
    if cache_key in cache:
        print(f"✓ Using cached image for: {search_terms[:2]}")
        return cache[cache_key]
    return None

def cache_image(search_terms, image_type, image_data):
    """Cache a successfully found image."""
    cache = load_image_cache()
    cache_key = get_cache_key(search_terms, image_type or '')
    cache[cache_key] = image_data
    save_image_cache(cache)
    print(f"✓ Cached image for: {search_terms[:2]}")

# =============================================================================
# MODULAR ARCHITECTURE - REUSABLE COMPONENTS
# =============================================================================

def generate_course_structure(course_name, reference_docs=None):
    """
    MODULE 1: Course Structure Generator

    Intelligently generates hierarchical course structure:
    Course → Subjects → Topics → Chapters

    This module is reusable for both QBank and Lesson generation.

    Args:
        course_name: Name of the course/exam (e.g., "NEET PG", "USMLE", "FE Exam")
        reference_docs: Optional uploaded reference documents

    Returns:
        {
            'course': str,
            'exam_type': str,
            'subjects': [
                {
                    'name': str,
                    'topics': [
                        {
                            'name': str,
                            'chapters': [
                                {'name': str, 'nice_refs': [...]}
                            ]
                        }
                    ]
                }
            ]
        }
    """
    logger.info(f"Generating course structure for: {course_name}")

    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    ref_doc_context = ""
    if reference_docs:
        ref_doc_context = f"\n\nREFERENCE DOCUMENTS PROVIDED:\n{reference_docs}\n\nUse these documents to inform the structure."

    structure_prompt = f"""You are an expert educational curriculum designer with access to official exam syllabi and curriculum guidelines.

📚 FIRST: Research and reference the OFFICIAL curriculum for: {course_name}

For each exam/course, base your structure on the authoritative sources:
- UKMLA AKT: GMC (General Medical Council) curriculum, UKMLA syllabus, UK Foundation Programme curriculum
- USMLE: NBME content outline, USMLE Step specifications
- NEET PG: NMC (National Medical Commission) syllabus, MCI guidelines
- Engineering exams (FE, PE): NCEES exam specifications
- Other certifications: Official exam board syllabi

🎯 Use the EXACT subject names, topic divisions, and terminology from the official curriculum.
🎯 Ensure weightage and coverage matches what's actually tested in the exam.
🎯 Reference the most current version of the curriculum/syllabus.

🚨 CRITICAL WARNING: You MUST generate AT LEAST 10 subjects! 🚨
   - Generating only 2-3 subjects is COMPLETELY UNACCEPTABLE
   - Medical/Professional exams require 10-12 subjects based on official curriculum
   - This is a professional educational platform - comprehensive coverage is MANDATORY

Analyze the official curriculum and create a full hierarchical structure with:

1. **Course identification** (type: medical/engineering/business/certification/other)

2. **Subjects** (major divisions):
   🔴 CRITICAL: Generate AT LEAST 10 subjects - THIS IS MANDATORY!

   - Medical exams (UKMLA, USMLE, NEET PG): EXACTLY 10-12 subjects required

     🔴 HIERARCHY FOR MEDICAL COURSES:
     Subject → Topic → Chapter

     Example for "Internal Medicine - Adult":
     - SUBJECT: Internal Medicine - Adult
       - TOPIC: Cardiology
         - CHAPTER: Hypertension
         - CHAPTER: Heart Failure
         - CHAPTER: Arrhythmias
       - TOPIC: Respiratory Medicine
         - CHAPTER: Asthma
         - CHAPTER: COPD
         - CHAPTER: Pneumonia

     FOR UKMLA AKT - Base structure on GMC/UKMLA official curriculum:
     Reference: GMC "Outcomes for graduates" and UKMLA syllabus domains

     SUGGESTED SUBJECTS (use official terminology where possible):
     1. Internal Medicine - Adult (system-based topics: Cardiology, Respiratory, Gastroenterology, Nephrology, Endocrinology, Rheumatology, Neurology)
     2. Surgery (subspecialties: General Surgery, Trauma & Orthopedics, Urology, ENT, Ophthalmology)
     3. Pediatrics & Child Health (including neonatology, growth & development)
     4. Obstetrics & Gynecology (including maternal medicine, reproductive health)
     5. Psychiatry & Mental Health (including liaison psychiatry, substance misuse)
     6. General Practice & Primary Care (including chronic disease management, preventive care)
     7. Emergency Medicine & Acute Care (including resuscitation, trauma)
     8. Ethics, Law & Communication (including consent, capacity, professionalism)
     9. Public Health & Epidemiology (including screening, health promotion)
     10. Clinical Pharmacology & Therapeutics (including prescribing, adverse effects)
     11. Pathology & Laboratory Medicine (including interpretation of results)
     12. Microbiology & Infectious Diseases (including antimicrobial stewardship)

     ⚠️ If official curriculum uses different terminology or groupings, PREFER the official structure.

   - Engineering exams (FE, PE): EXACTLY 10-12 subjects required
     Examples: Mathematics, Physics, Chemistry, Statics, Dynamics, Mechanics of Materials,
     Thermodynamics, Fluid Mechanics, Electrical Circuits, Materials Science, etc.

   - Business exams (CPA, CFA): EXACTLY 8-10 subjects required
     Examples: Financial Accounting, Auditing, Tax, Business Law, Ethics, Financial Management, etc.

3. **Topics** (under each subject):
   - 8-12 topics per subject (comprehensive coverage)
   - Each topic represents a system-based or area-based division
   - Medical Example: Under "Internal Medicine - Adult" → Cardiology, Respiratory, Gastroenterology, Nephrology, etc.
   - Engineering Example: Under "Mechanical Engineering" → Thermodynamics, Fluid Mechanics, Heat Transfer, etc.

4. **Chapters** (under each topic):
   - Leave chapters as EMPTY ARRAYS initially: "chapters": []
   - Chapters will be generated dynamically when lessons are requested for specific topics
   - This keeps structure generation fast and efficient
   - When needed, chapters will be: specific conditions, concepts, procedures, or subtopics (8-12 per topic)

{ref_doc_context}

🔴 MANDATORY REQUIREMENTS:
✓ Generate AT LEAST 10 subjects for medical/professional exams, 8 for technical exams
✓ NEVER generate less than 6 subjects - that's insufficient for any comprehensive course
✓ Each subject must have at least 6 topics
✓ Each topic must have at least 4 chapters
✓ Use standard, recognized terminology for the domain
✓ Cover the FULL breadth of the exam/course - don't summarize or abbreviate

DOMAIN-SPECIFIC GUIDELINES:

**Medical Courses (UKMLA, USMLE, NEET PG, MRCP)**:
HIERARCHY: Subject → Topic → Chapter

SUBJECTS (Major Specialties - 10-12 total):
- Core Clinical: Internal Medicine - Adult, Surgery, Pediatrics, OB/GYN, Psychiatry
- Foundation: Pathology, Pharmacology, Microbiology
- Professional: Ethics/Law/Communication, Public Health, General Practice

TOPICS (System-based divisions under each subject - 8-12 per subject):
- Under "Internal Medicine - Adult": Cardiology, Respiratory, Gastroenterology, Nephrology, Endocrinology, Rheumatology, Neurology
- Under "Surgery": General Surgery, Trauma & Orthopedics, Urology, ENT, Ophthalmology
- Under "Pediatrics": Neonatology, Growth & Development, Pediatric Cardiology, etc.

CHAPTERS (Specific conditions - 8-15 per topic):
- Under "Cardiology": Hypertension, Heart Failure, Arrhythmias, Ischemic Heart Disease, Valvular Disease, etc.
- Under "Respiratory": Asthma, COPD, Pneumonia, Tuberculosis, Lung Cancer, etc.

**Engineering Courses (FE, PE)**:
- Include: Core sciences (Math, Physics, Chemistry)
- Include: Engineering fundamentals (Statics, Dynamics, Thermodynamics)
- Include: Discipline-specific topics (Electrical, Mechanical, Civil, etc.)

**Business/Finance Courses (CPA, CFA, MBA)**:
- Include: Functional areas (Accounting, Finance, Marketing, Operations)
- Include: Specializations (Auditing, Tax, Investment, Strategy)

OUTPUT FORMAT (strict JSON):
{{
    "course": "{course_name}",
    "exam_type": "medical|engineering|business|certification|academic",
    "domain_characteristics": "detailed description of learning patterns and exam focus",
    "subjects": [
        {{
            "name": "Subject Name",
            "description": "Brief 1-line description of what this subject covers",
            "topics": [
                {{
                    "name": "Topic Name",
                    "chapters": []
                }}
            ]
        }}
    ]
}}

🔴 IMPORTANT: Generate a COMPLETE structure - minimum 10 subjects for professional exams!

Generate ONLY the JSON, no other text."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=8000,  # Sufficient for subjects + topics (chapters generated on-demand)
            temperature=0.7,
            timeout=120.0,  # 2 minute timeout for fast structure generation
            messages=[{"role": "user", "content": structure_prompt}]
        )

        response_text = message.content[0].text.strip()

        # Extract JSON if wrapped in markdown
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()

        # Try to parse JSON
        try:
            structure = json.loads(response_text)
        except json.JSONDecodeError as json_err:
            logger.error(f"JSON parsing error: {json_err}")
            logger.error(f"Response length: {len(response_text)} chars")

            # Try to fix common JSON issues
            # Remove any trailing incomplete content
            last_brace = response_text.rfind('}')
            if last_brace > 0:
                truncated = response_text[:last_brace + 1]
                logger.info("Attempting to parse truncated JSON...")
                try:
                    structure = json.loads(truncated)
                    logger.info("✓ Successfully parsed truncated JSON")
                except:
                    # If still fails, retry with simpler request (just subjects and topics, fewer chapters)
                    logger.warning("JSON still invalid, retrying with simplified structure request...")
                    raise json_err
            else:
                raise json_err

        # Validate structure completeness
        num_subjects = len(structure.get('subjects', []))
        if num_subjects < 6:
            logger.warning(f"⚠️ Generated structure has only {num_subjects} subjects - attempting retry with stronger prompt")

            # Retry with even more explicit prompt
            retry_prompt = f"""CRITICAL: The previous attempt generated only {num_subjects} subjects, which is INSUFFICIENT.

For {course_name}, generate a COMPLETE course structure with AT LEAST 10 subjects.

This is a professional educational platform - we need COMPREHENSIVE coverage.

{structure_prompt}

REMEMBER: Minimum 10 subjects for medical/professional exams, 8 for technical exams!"""

            message = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=8000,
                temperature=0.5,  # Lower temperature for more focused output
                timeout=120.0,  # 2 minute timeout
                messages=[{"role": "user", "content": retry_prompt}]
            )

            response_text = message.content[0].text.strip()
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0].strip()
            elif '```' in response_text:
                response_text = response_text.split('```')[1].split('```')[0].strip()

            structure = json.loads(response_text)
            num_subjects = len(structure.get('subjects', []))

        logger.info(f"✓ Generated structure with {num_subjects} subjects")

        # Log summary statistics
        total_topics = sum(len(subj.get('topics', [])) for subj in structure.get('subjects', []))
        logger.info(f"  - Total topics: {total_topics}")
        logger.info(f"  - Avg topics per subject: {total_topics / num_subjects if num_subjects > 0 else 0:.1f}")

        return structure

    except Exception as e:
        logger.error(f"Error generating course structure: {e}")
        raise


def analyze_exam_format(course_name, course_structure):
    """
    MODULE 2: Exam Format Analyzer (for QBank)

    Analyzes and determines:
    - Question format (MCQ type, number of options)
    - Bloom's level distribution strategy
    - Difficulty distribution
    - Domain-specific question characteristics

    Args:
        course_name: Name of course/exam
        course_structure: Output from generate_course_structure()

    Returns:
        {
            'question_format': {...},
            'blooms_distribution': {...},
            'difficulty_distribution': {...},
            'domain_characteristics': {...}
        }
    """
    logger.info(f"Analyzing exam format for: {course_name}")

    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    exam_type = course_structure.get('exam_type', 'general')
    domain_chars = course_structure.get('domain_characteristics', '')

    # Extract subjects from course structure for subject-specific analysis
    subjects_list = [s['name'] for s in course_structure.get('subjects', [])]
    subjects_str = ', '.join(subjects_list[:10]) if subjects_list else 'various subjects'

    format_prompt = f"""You are an assessment design expert with access to official exam data. Analyze the exam format for: {course_name}

COURSE TYPE: {exam_type}
DOMAIN CHARACTERISTICS: {domain_chars}
SUBJECTS IN COURSE: {subjects_str}

🔍 MANDATORY RESEARCH REQUIREMENT: Use OFFICIAL published exam specifications and statistics for {course_name}:

**For UKMLA AKT (UK Medical Licensing Assessment Applied Knowledge Test):**
- Source: GMC (General Medical Council), UKMLA blueprint
- Number of options: 5 (A, B, C, D, E) - CONFIRMED from official GMC specification
- Image questions: ~30-40% overall (ECGs, radiology, dermatology, ophthalmology images)
- Question style: Single best answer, clinical scenario-based
- Avg stem: 60-80 words per question

**For NEET PG (National Eligibility cum Entrance Test - Postgraduate):**
- Source: NBE (National Board of Examinations), NEET PG information bulletin
- Number of options: 4 (A, B, C, D) - CONFIRMED from official specification
- Image questions: ~40% overall (varies 10-75% by subject)
- Question style: Single best answer, clinically oriented

**For USMLE (United States Medical Licensing Examination):**
- Source: NBME, USMLE content outline
- Number of options: 4-5 (varies by step)
- Image questions: ~20-30% (anatomical, pathological, radiological images)
- Question style: Clinical vignettes, single best answer

Use the OFFICIAL specification for number of options - this is critical and must be accurate.

Determine the optimal question bank format including:

1. **Question Format**:
   - MCQ type (single best answer, multiple correct, true/false, assertion-reason, etc.)
   - Number of options (typically 4-5)
   - Clinical vignette length (for medical exams)
   - Stem complexity
   - **CRITICAL**: image_questions_percentage - the TYPICAL percentage of image-based questions in this exam overall

2. **Bloom's Taxonomy Distribution**:
   - Level 1 (Remember/Recall): X%
   - Level 2 (Understand): X%
   - Level 3 (Apply): X%
   - Level 4 (Analyze): X%
   - Level 5 (Evaluate): X%
   - Level 6 (Create): X%
   - Level 7 (Integrate/Synthesize): X%

   Consider:
   - Medical exams: Higher emphasis on Apply/Analyze (clinical reasoning)
   - Engineering exams: Balance of Understand/Apply/Analyze
   - Certification exams: Focus on Apply/Evaluate

3. **Difficulty Distribution**:
   - Easy: X%
   - Medium: X%
   - Hard: X%

4. **Image-Based Questions by Subject** (CRITICAL FOR MEDICAL EXAMS):
   Research typical image percentages for each subject. Examples:
   - NEET PG: Radiology ~75%, Ophthalmology ~60%, Medicine ~40%, Biochemistry ~10%
   - USMLE Step 1: Pathology ~30%, Anatomy ~50%, Physiology ~15%

   Provide subject-specific percentages as a map.

5. **Domain-Specific Characteristics**:
   - Medical: Case-based scenarios, image-based questions
   - Engineering: Calculation-based, diagram interpretation
   - Business: Case studies, scenario analysis

OUTPUT FORMAT (strict JSON):
{{
    "question_format": {{
        "type": "single_best_answer",
        "num_options": 4,
        "avg_stem_words": 50,
        "uses_vignettes": true,
        "image_questions_percentage": 40
    }},
    "blooms_distribution": {{
        "1_remember": 15,
        "2_understand": 15,
        "3_apply": 30,
        "4_analyze": 25,
        "5_evaluate": 10,
        "6_create": 5,
        "7_integrate": 0
    }},
    "difficulty_distribution": {{
        "easy": 20,
        "medium": 50,
        "hard": 30
    }},
    "image_percentage_by_subject": {{
        "Radiology": 75,
        "Internal Medicine": 40,
        "Biochemistry": 10,
        "Surgery": 45
    }},
    "domain_characteristics": {{
        "key_features": ["feature1", "feature2"],
        "memory_aids": "mnemonics|formulas|frameworks|acronyms",
        "visual_elements": "high|medium|low"
    }}
}}

Generate ONLY the JSON, no other text."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=3000,
            temperature=0.7,
            messages=[{"role": "user", "content": format_prompt}]
        )

        response_text = message.content[0].text.strip()
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()

        format_spec = json.loads(response_text)
        logger.info(f"✓ Analyzed exam format")
        return format_spec

    except Exception as e:
        logger.error(f"Error analyzing exam format: {e}")
        raise


def design_lesson_flow(course_name, subject, topic, chapters, course_structure):
    """
    MODULE 3: Lesson Flow Architect (for Lessons)

    Designs intelligent lesson structure with:
    - Bloom's level progression
    - Optimal content length (7-8 pages topic, 1-2 pages chapter)
    - Strategic placement of tables, flowcharts, images
    - Domain-specific memory aids (mnemonics for medical, equivalents for others)

    Args:
        course_name: Name of course
        subject: Subject name
        topic: Topic name
        chapters: List of chapter names
        course_structure: Output from generate_course_structure()

    Returns:
        {
            'topic_lesson_plan': {...},
            'chapter_lesson_plan': {...},
            'visual_strategy': {...}
        }
    """
    logger.info(f"Designing lesson flow for: {topic}")

    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    exam_type = course_structure.get('exam_type', 'general')
    domain_chars = course_structure.get('domain_characteristics', '')

    flow_prompt = f"""You are an instructional design expert. Design the optimal lesson flow for:

COURSE: {course_name}
SUBJECT: {subject}
TOPIC: {topic}
CHAPTERS: {', '.join([ch if isinstance(ch, str) else ch['name'] for ch in chapters])}

COURSE TYPE: {exam_type}
DOMAIN: {domain_chars}

Design a comprehensive learning experience with:

1. **TOPIC LESSON STRUCTURE** (7-8 pages, ~1200 words):
   - Bloom's progression: Foundation → Understanding → Application → Analysis → Evaluation → Synthesis → Integration
   - 7 main sections mapping to Bloom's levels
   - Content type per section (text/table/flowchart/image)
   - Estimated word count per section

2. **CHAPTER LESSON STRUCTURE** (1-2 pages, ~300-500 words):
   - Rapid revision format
   - Key facts, problem-solving approaches, quick reference
   - Visual aid strategy (1-2 elements max)

3. **VISUAL ELEMENT STRATEGY**:
   Topic lesson:
   - Minimum images: X (based on subject visual intensity)
   - Tables: X (for classifications, comparisons)
   - Flowcharts: X (for algorithms, processes)
   - Placement: Strategic distribution across Bloom's levels

   Chapter lesson:
   - Images: 0-2
   - Tables/flowcharts: 1-2
   - Focus: Most critical visual

4. **MEMORY AIDS STRATEGY**:
   - Medical: Mnemonics, clinical pearls
   - Engineering: Key formulas, design patterns
   - Business: Frameworks, case examples
   - General: Acronyms, visual analogies

OUTPUT FORMAT (strict JSON):
{{
    "topic_lesson_plan": {{
        "total_words": 1200,
        "sections": [
            {{
                "blooms_level": 1,
                "title_pattern": "Foundation/Remember",
                "content_focus": "core knowledge, definitions, classifications",
                "word_count": 150,
                "visual_elements": {{
                    "images": 1,
                    "tables": 1,
                    "flowcharts": 0
                }},
                "memory_aids": true
            }}
        ]
    }},
    "chapter_lesson_plan": {{
        "total_words": 400,
        "sections": ["Quick Overview", "Core Facts", "Problem-Solving", "Analysis Framework", "Visual Aid", "Key Points"],
        "visual_elements": {{
            "images": 1,
            "tables_or_flowcharts": 1
        }}
    }},
    "memory_aids_strategy": {{
        "type": "mnemonics|formulas|frameworks|acronyms",
        "frequency": "per_section|end_of_topic",
        "examples": ["SAMPLE", "EXAMPLE"]
    }}
}}

Generate ONLY the JSON, no other text."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=3000,
            temperature=0.7,
            messages=[{"role": "user", "content": flow_prompt}]
        )

        response_text = message.content[0].text.strip()
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()

        flow_design = json.loads(response_text)
        logger.info(f"✓ Designed lesson flow")
        return flow_design

    except Exception as e:
        logger.error(f"Error designing lesson flow: {e}")
        raise


# =============================================================================
# END OF MODULAR ARCHITECTURE
# =============================================================================

def get_neet_prompt(subject, topic, num_questions, chapters=None):
    """Generate prompt for NEET PG questions with equal Bloom's level distribution."""
    
    # Calculate distribution: equal numbers of Bloom's levels 1,2,3,4,5
    per_level = num_questions // 5
    remainder = num_questions % 5
    
    distribution = {
        1: per_level + (1 if remainder > 0 else 0),
        2: per_level + (1 if remainder > 1 else 0),
        3: per_level + (1 if remainder > 2 else 0),
        4: per_level + (1 if remainder > 3 else 0),
        5: per_level + (1 if remainder > 4 else 0),
    }
    
    examples_json = json.dumps(NEET_EXAMPLES[:3], indent=2)
    
    chapter_info = f"\nChapters to focus on: {', '.join(chapters)}" if chapters else ""
    
    return f"""You are an expert medical educator creating MCQs for NEET PG (National Eligibility cum Entrance Test - Postgraduate) examination in India.

Generate exactly {num_questions} unique MCQs following NEET PG exam pattern.

SUBJECT: {subject}
TOPIC: {topic}{chapter_info}

BLOOM'S LEVEL DISTRIBUTION (MANDATORY - must follow exactly):
- Bloom's Level 1 (Remember/Recall): {distribution[1]} questions
- Bloom's Level 2 (Understand): {distribution[2]} questions
- Bloom's Level 3 (Apply): {distribution[3]} questions
- Bloom's Level 4 (Analyze): {distribution[4]} questions
- Bloom's Level 5 (Evaluate/Synthesize): {distribution[5]} questions

DIFFICULTY LEVELS:
- 1 = Medium
- 2 = Hard  
- 3 = Very Hard

Mix difficulties across all Bloom's levels.

STRICT FORMAT REQUIREMENTS:
1. Each question MUST have exactly 4 options
2. correct_option must be the exact text of the correct answer
3. Questions must follow NEET PG clinical vignette style for higher Bloom's levels
4. No duplicate questions
5. Tags must be ["NEET-PG", "INICET"]

EXAMPLE FORMAT:
{examples_json}

Generate {num_questions} questions in valid JSON array format. Output ONLY the JSON array, no other text."""


def get_usmle_prompt(subject, topic, num_questions, chapters=None):
    """Generate prompt for USMLE questions with equal Bloom's level distribution (3,4,5 only)."""
    
    # Calculate distribution: equal numbers of Bloom's levels 3,4,5
    per_level = num_questions // 3
    remainder = num_questions % 3
    
    distribution = {
        3: per_level + (1 if remainder > 0 else 0),
        4: per_level + (1 if remainder > 1 else 0),
        5: per_level + (1 if remainder > 2 else 0),
    }
    
    examples_json = json.dumps(USMLE_EXAMPLES[:3], indent=2)
    
    chapter_info = f"\nChapters to focus on: {', '.join(chapters)}" if chapters else ""
    
    return f"""You are an expert medical educator creating MCQs for USMLE (United States Medical Licensing Examination) Steps 1, 2, and 3.

Generate exactly {num_questions} unique MCQs following USMLE exam pattern.

SUBJECT: {subject}
TOPIC: {topic}{chapter_info}

BLOOM'S LEVEL DISTRIBUTION (MANDATORY - must follow exactly):
- Bloom's Level 3 (Apply): {distribution[3]} questions
- Bloom's Level 4 (Analyze): {distribution[4]} questions
- Bloom's Level 5 (Evaluate/Synthesize): {distribution[5]} questions

DIFFICULTY LEVELS:
- 1 = Medium
- 2 = Hard
- 3 = Very Hard

Mix difficulties across all Bloom's levels.

STRICT FORMAT REQUIREMENTS:
1. Each question MUST have exactly 5 options
2. correct_option must be the exact text of the correct answer
3. Questions must follow USMLE clinical vignette style with patient presentations
4. No duplicate questions
5. Tags must include "USMLE" plus relevant steps like "USMLE - Step 1", "USMLE - Step 2", "USMLE - Step 3"
6. Each question MUST include "course": "US Medical PG" field

EXAMPLE FORMAT:
{examples_json}

Generate {num_questions} questions in valid JSON array format. Output ONLY the JSON array, no other text."""


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/subjects/<course>')
def get_subjects(course):
    """Return subjects for the selected course (alphabetically sorted)."""
    if course == 'NEET PG':
        subjects = sorted([item['Subject'] for item in NEET_DATA])
    elif course == 'USMLE':
        subjects = sorted([item['subject'] for item in USMLE_DATA])
    else:
        subjects = []
    return jsonify(subjects)


@app.route('/api/topics/<course>/<subject>')
def get_topics(course, subject):
    """Return topics for the selected subject (alphabetically sorted)."""
    topics = []
    if course == 'NEET PG':
        for item in NEET_DATA:
            if item['Subject'] == subject:
                topics = sorted([t['Topic'] for t in item['Topics']])
                break
    elif course == 'USMLE':
        for item in USMLE_DATA:
            if item['subject'] == subject:
                topics = sorted([t['name'] for t in item['topics']])
                break
    return jsonify(topics)


@app.route('/api/chapters/<course>/<subject>/<topic>')
def get_chapters(course, subject, topic):
    """Return chapters for the selected topic."""
    chapters = []
    if course == 'NEET PG':
        for item in NEET_DATA:
            if item['Subject'] == subject:
                for t in item['Topics']:
                    if t['Topic'] == topic:
                        chapters = t['Chapters']
                        break
                break
    elif course == 'USMLE':
        for item in USMLE_DATA:
            if item['subject'] == subject:
                for t in item['topics']:
                    if t['name'] == topic:
                        chapters = t['chapters']
                        break
                break
    return jsonify(chapters)


def validate_image_with_claude(image_url, question_data):
    """Validate image relevance using Claude Vision. Returns score 0-100."""
    try:
        question = question_data.get('question', '')
        image_desc = question_data.get('image_description', '')
        image_type = question_data.get('image_type', '')
        key_finding = question_data.get('key_finding', '')

        finding_context = f"\n\nKEY DIAGNOSTIC FINDING that must be visible: {key_finding}" if key_finding else ""

        validation_prompt = f"""You are a medical imaging specialist validating images for board examination questions. Analyze this image with clinical precision.

QUESTION: {question}

EXPECTED IMAGE:
- Modality: {image_type}
- Description: {image_desc}{finding_context}

VALIDATION CRITERIA (score 0-100):

1. MODALITY MATCH (20 points): Is this the exact type of medical image specified? (e.g., if "Chest X-ray PA view" is requested, is it actually a chest X-ray and not a CT?)

2. DIAGNOSTIC FINDING PRESENT (40 points): Does the image clearly show the specific pathologic finding or characteristic feature described? This is CRITICAL - the key diagnostic element must be visible and identifiable.

3. CLINICAL QUALITY (20 points):
   - Is this a real medical image (not a diagram, flowchart, illustration, or labeled schematic)?
   - Is the image quality sufficient for diagnostic interpretation?
   - **CRITICAL**: Are there NO text labels, annotations, or arrows that reveal the answer or diagnosis?
   - **CRITICAL**: Medical images for exam questions must be UNLABELED - any visible text revealing the diagnosis should result in automatic failure (score 0-30)

4. EDUCATIONAL VALUE (20 points):
   - Would this image help a medical student identify the diagnosis?
   - Is the finding prominent enough to be clinically useful?
   - Does it match board examination image standards?

SCORING GUIDE:
- 90-100: Perfect match - correct modality, diagnostic finding clearly visible, clinical quality, NO text labels
- 80-89: Very good match - correct type, finding clearly visible, minor quality issues, NO text labels
- 70-79: Good match - correct type, finding visible but not ideal quality, NO text labels
- 50-69: Partial match - correct type but finding unclear or poor quality
- 30-49: Wrong finding or very poor quality
- 0-29: Wrong modality, diagram/illustration, or **ANY visible text revealing the diagnosis/answer**

**AUTOMATIC DISQUALIFICATION (score 0-30)**: If the image contains ANY text, labels, annotations, or arrows that reveal or hint at the diagnosis/answer. For example:
- "Mitochondrial inheritance" on a pedigree → score 0-20
- "Pneumonia" labeled on chest X-ray → score 0-20
- "STEMI" or diagnosis text on ECG → score 0-20
- Educational diagrams with labeled pathology → score 0-20

Respond with ONLY a JSON object:
{{"score": <number 0-100>, "reason": "<specific explanation of what you see and why score was given>"}}"""

        # Download image to base64
        img_response = requests.get(image_url, timeout=10)
        if img_response.status_code != 200:
            return {'score': 0, 'reason': 'Failed to download image'}

        import base64
        img_base64 = base64.b64encode(img_response.content).decode('utf-8')

        # Determine media type
        content_type = img_response.headers.get('content-type', 'image/jpeg')

        # Call Claude Vision
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": content_type,
                            "data": img_base64
                        }
                    },
                    {
                        "type": "text",
                        "text": validation_prompt
                    }
                ]
            }]
        )

        # Parse response
        response_text = message.content[0].text
        result = json.loads(response_text)
        return result

    except Exception as e:
        logger.error(f"Validation error: {e}")
        return {'score': 0, 'reason': str(e)}


def collect_candidate_images(image_search_terms, image_type, max_candidates=10):
    """Collect candidate images from multiple sources. Try harder to find images from internet sources."""
    candidates = []

    logger.info(f"🔍 Starting image search with terms: {image_search_terms[:3]}, type: {image_type}")

    # Try Open-i (NIH) - more aggressive search
    try:
        url = "https://openi.nlm.nih.gov/api/search"
        image_type_map = {
            'X-ray': 'xg', 'CT scan': 'ct', 'CT': 'ct', 'MRI': 'mri', 'Ultrasound': 'us',
            'Microscopy': 'mi', 'Gram stain': 'mi', 'Histopathology': 'mi',
            'Culture plate': 'mi', 'Microscopy stain': 'mi'
        }
        it_param = image_type_map.get(image_type, 'xg,ct,mri,us,mi')

        logger.info(f"  → Trying Open-i NIH with image type param: {it_param}")

        # Try ALL search terms (not just first 2)
        for idx, search_term in enumerate(image_search_terms[:5]):
            params = {'query': search_term, 'it': it_param, 'm': 1, 'n': 15}
            logger.info(f"  → Open-i search #{idx+1}: '{search_term}'")

            response = requests.get(url, params=params, timeout=15)
            logger.info(f"    Status: {response.status_code}")

            data = response.json()
            logger.info(f"    Response keys: {list(data.keys())}")

            if 'list' in data:
                logger.info(f"    Found {len(data['list'])} results in list")
                for item in data['list'][:3]:  # Take top 3 from each search (increased from 2)
                    if 'imgLarge' in item:
                        candidates.append({
                            'url': f"https://openi.nlm.nih.gov{item['imgLarge']}",
                            'source': 'Open-i (NIH)',
                            'title': item.get('title', '')[:100]
                        })
                        logger.info(f"    ✓ Added candidate: {item.get('title', '')[:50]}")
                        if len(candidates) >= max_candidates:
                            logger.info(f"  ✓ Reached max candidates ({max_candidates}), returning")
                            return candidates
                    else:
                        logger.info(f"    ✗ Item missing 'imgLarge' key: {list(item.keys())}")
            else:
                logger.info(f"    ✗ No 'list' in response")
    except Exception as e:
        logger.error(f"Open-i collection error: {e}")
        import traceback
        logger.error(traceback.format_exc())

    # Try Wikimedia Commons - more aggressive search
    try:
        url = "https://commons.wikimedia.org/w/api.php"
        logger.info(f"  → Trying Wikimedia Commons")

        # Add proper User-Agent to avoid 403 errors
        headers = {
            'User-Agent': 'QBankGenerator/1.0 (Educational Medical Image Search; contact@example.com)'
        }

        for idx, search_term in enumerate(image_search_terms[:5]):  # Increased from 2 to 5
            params = {
                'action': 'query', 'format': 'json', 'generator': 'search',
                'gsrnamespace': 6, 'gsrsearch': f"{search_term} medical",
                'gsrlimit': 15, 'prop': 'imageinfo', 'iiprop': 'url|mime', 'iiurlwidth': 600
            }
            logger.info(f"  → Wikimedia search #{idx+1}: '{search_term} medical'")

            response = requests.get(url, params=params, headers=headers, timeout=20)
            logger.info(f"    Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                logger.info(f"    Response keys: {list(data.keys())}")

                if 'query' in data and 'pages' in data['query']:
                    pages = data['query']['pages']
                    logger.info(f"    Found {len(pages)} pages")

                    for page_id, page in list(pages.items())[:3]:  # Increased from 2 to 3
                        if 'imageinfo' in page and len(page['imageinfo']) > 0:
                            img_info = page['imageinfo'][0]
                            mime = img_info.get('mime', '')
                            logger.info(f"    Page: {page.get('title', '')[:30]}, mime: {mime}")

                            if mime.startswith('image/') and 'svg' not in mime.lower():
                                candidates.append({
                                    'url': img_info.get('thumburl', img_info.get('url')),
                                    'source': 'Wikimedia Commons',
                                    'title': page.get('title', '').replace('File:', '')
                                })
                                logger.info(f"    ✓ Added candidate: {page.get('title', '')[:50]}")
                                if len(candidates) >= max_candidates:
                                    logger.info(f"  ✓ Reached max candidates ({max_candidates}), returning")
                                    return candidates
                            else:
                                logger.info(f"    ✗ Skipped (SVG or non-image mime type)")
                        else:
                            logger.info(f"    ✗ Page missing imageinfo")
                else:
                    logger.info(f"    ✗ No 'query' or 'pages' in response")
            else:
                logger.info(f"    ✗ Bad response status: {response.status_code}")
    except Exception as e:
        logger.error(f"Wikimedia collection error: {e}")
        import traceback
        logger.error(traceback.format_exc())

    logger.info(f"Collected {len(candidates)} candidate images from internet sources")
    return candidates


def add_visual_markers_to_image(image_path, question_text, image_description):
    """Add visual markers (arrows, circles, highlights) to an image based on question references."""
    try:
        logger.info(f"add_visual_markers_to_image called with:")
        logger.info(f"  - image_path: {image_path}")
        logger.info(f"  - question_text length: {len(question_text) if question_text else 0}")
        logger.info(f"  - question_text: '{question_text[:100]}...'")
        logger.info(f"  - image_description: '{image_description[:50]}...'")

        # Detect if question has spatial references
        # Use word boundary matching to avoid false positives like "markedly" triggering "marked"
        import re
        spatial_keywords = [
            r'\barrow\b', r'\barrows\b', r'\bpointing to\b', r'\bpoints to\b', r'\bindicated by\b',
            r'\bcircle\b', r'\bcircled\b', r'\bencircled\b', r'\bmarked\b', r'\bhighlighted\b', r'\bshown by\b',
            r'\bboxed\b', r'\boutlined\b', r'\blabeled\b', r'\basterisk\b', r'\bstar\b'
        ]

        question_lower = question_text.lower() if question_text else ""
        has_spatial_reference = any(re.search(keyword, question_lower) for keyword in spatial_keywords)

        logger.info(f"Spatial reference detected: {has_spatial_reference}")

        if not has_spatial_reference:
            logger.info("No spatial keywords found in question, skipping markers")
            return None

        logger.info("✓ Question has spatial references - proceeding to add visual markers")

        # Step 1: Use Claude Vision to locate the diagnostic finding
        import base64
        with open(image_path, 'rb') as f:
            image_data = f.read()
            img_base64 = base64.b64encode(image_data).decode('utf-8')

        # Determine media type
        from PIL import Image
        img = Image.open(image_path)
        img_format = img.format.lower()
        media_type = f"image/{img_format}" if img_format in ['jpeg', 'jpg', 'png'] else 'image/jpeg'

        location_prompt = f"""Analyze this medical image and locate the key diagnostic finding.

IMAGE DESCRIPTION: {image_description}

QUESTION: {question_text}

Identify the location of the main diagnostic feature that the question refers to. Provide coordinates as percentages of image dimensions (0-100%).

Respond with ONLY a JSON object:
{{
  "center_x": <percentage 0-100>,
  "center_y": <percentage 0-100>,
  "radius_percent": <percentage 5-15 for circle size>,
  "marker_type": "circle" or "arrow" or "box",
  "description": "brief description of what you're marking"
}}

For example: {{"center_x": 45, "center_y": 60, "radius_percent": 10, "marker_type": "circle", "description": "fractured tooth fragment"}}"""

        # Call Claude Vision
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": img_base64
                        }
                    },
                    {
                        "type": "text",
                        "text": location_prompt
                    }
                ]
            }]
        )

        # Parse location response
        response_text = message.content[0].text
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0]
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0]

        location_data = json.loads(response_text.strip())

        # Step 2: Draw the marker using PIL
        from PIL import ImageDraw
        img = Image.open(image_path)
        draw = ImageDraw.Draw(img)

        width, height = img.size
        center_x = int(location_data['center_x'] * width / 100)
        center_y = int(location_data['center_y'] * height / 100)
        radius = int(location_data.get('radius_percent', 10) * min(width, height) / 100)

        # Choose color based on marker type
        color = 'red'
        line_width = max(3, int(min(width, height) / 200))

        marker_type = location_data.get('marker_type', 'circle')

        if marker_type == 'circle' or re.search(r'\bcircle\b', question_lower) or re.search(r'\bencircle', question_lower):
            # Draw circle
            draw.ellipse(
                [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
                outline=color,
                width=line_width
            )
            logger.info(f"Drew circle at ({center_x}, {center_y}) with radius {radius}")

        elif marker_type == 'arrow':
            # Draw arrow pointing to the location
            arrow_length = radius * 2
            draw.line(
                [center_x - arrow_length, center_y - arrow_length, center_x, center_y],
                fill=color,
                width=line_width
            )
            # Arrow head
            head_size = radius // 2
            draw.polygon(
                [
                    (center_x, center_y),
                    (center_x - head_size, center_y - head_size),
                    (center_x + head_size, center_y - head_size)
                ],
                fill=color
            )
            logger.info(f"Drew arrow pointing to ({center_x}, {center_y})")

        elif marker_type == 'box':
            # Draw rectangle
            draw.rectangle(
                [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
                outline=color,
                width=line_width
            )
            logger.info(f"Drew box at ({center_x}, {center_y})")

        # Save the marked image
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png', dir='static') as f:
            marked_img_path = f.name

        img.save(marked_img_path, format='PNG')
        logger.info(f"✓ Added {marker_type} marker to image: {location_data.get('description', '')}")

        return marked_img_path

    except Exception as e:
        logger.error(f"Error adding visual markers: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def generate_image_with_gemini(question_data):
    """Generate image with Gemini Nano Banana Pro."""
    try:
        image_desc = question_data.get('image_description', '')
        image_type = question_data.get('image_type', '')
        key_finding = question_data.get('key_finding', '')

        # Build context about what must be visible
        finding_emphasis = f"\n\nCRITICAL DIAGNOSTIC FINDING that MUST be clearly visible: {key_finding}" if key_finding else ""

        # Universal restriction: NO text labels that reveal the answer
        no_answer_text = "\n\n**CRITICAL RESTRICTION**: The image must be COMPLETELY UNLABELED. NO text, NO annotations, NO labels, NO arrows with text, NO diagnosis names written on the image. Students must interpret the raw clinical image without any textual hints or answers visible."

        # Create very specific prompt based on image type
        if 'gram stain' in image_type.lower() or 'microscopy' in image_type.lower() and 'histopathology' not in image_type.lower():
            prompt = f"""Create a realistic high-resolution microscopy photograph: {image_desc}.{finding_emphasis}{no_answer_text}

REQUIREMENTS:
- Must be an actual microscope photograph showing the exact morphology described
- Show individual cells/organisms with proper staining characteristics (Gram stain: purple for Gram+, pink for Gram-)
- High magnification (1000x oil immersion) clinical microscopy view
- Clear focus on the diagnostic morphology
- NO diagrams, NO flowcharts, NO tables, NO illustrations, NO labels, NO text annotations
- Realistic medical laboratory quality photograph as seen through microscope eyepiece"""

        elif 'histopathology' in image_type.lower() or 'h&e' in image_type.lower() or 'biopsy' in image_type.lower():
            prompt = f"""Create a realistic histopathology microscopy image: {image_desc}.{finding_emphasis}{no_answer_text}

REQUIREMENTS:
- Must be actual tissue histology showing the specific pathologic cells/patterns described
- Show characteristic cellular architecture and pathognomonic features
- Proper H&E staining (or specified stain): nuclei blue/purple, cytoplasm pink
- Medium to high magnification showing cellular detail
- NO diagrams, NO illustrations, NO schematic drawings, NO labels, NO text annotations
- Realistic pathology slide photograph suitable for board examination"""

        elif 'culture' in image_type.lower() or 'agar' in image_type.lower():
            prompt = f"""Create a realistic photograph of a culture plate: {image_desc}.{finding_emphasis}{no_answer_text}

REQUIREMENTS:
- Must be an actual photograph of a petri dish with bacterial/fungal colonies
- Show the exact colony morphology, color, and hemolysis pattern described
- Clear view of growth characteristics on agar medium
- NO diagrams, NO flowcharts, NO tables, NO illustrations, NO text labels
- Realistic medical microbiology laboratory photograph"""

        elif 'ecg' in image_type.lower() or 'ekg' in image_type.lower():
            prompt = f"""Create a realistic 12-lead ECG tracing: {image_desc}.{finding_emphasis}{no_answer_text}

REQUIREMENTS:
- Must be an actual ECG printout showing the specific abnormality described
- Show clear waveforms with proper lead labels (I, II, III, aVR, aVL, aVF, V1-V6)
- Standard calibration (10mm/mV, 25mm/s) and grid paper background
- The diagnostic finding must be clearly visible in the appropriate leads
- NO diagnosis text, NO annotations pointing to findings - only standard lead labels allowed
- NO illustrations, NO diagrams - actual ECG machine printout appearance
- High contrast and clinically readable quality"""

        elif 'x-ray' in image_type.lower() or 'radiograph' in image_type.lower():
            prompt = f"""Create a realistic medical X-ray radiograph: {image_desc}.{finding_emphasis}{no_answer_text}

REQUIREMENTS:
- Must be an actual X-ray image showing the specific pathologic finding described
- Proper radiographic contrast (white bones, black air, gray soft tissue)
- Show anatomical landmarks and the diagnostic abnormality clearly
- Correct patient positioning and view as specified (PA, AP, lateral, etc.)
- NO diagrams, NO illustrations, NO arrows, NO labels, NO text annotations
- High-quality diagnostic radiology image suitable for interpretation"""

        elif 'ct' in image_type.lower() or 'computed tomography' in image_type.lower():
            prompt = f"""Create a realistic CT scan image: {image_desc}.{finding_emphasis}{no_answer_text}

REQUIREMENTS:
- Must be an actual CT cross-sectional image showing the specific pathology described
- Proper Hounsfield unit contrast (bone white, air black, soft tissue gray)
- Show anatomical structures and the diagnostic abnormality clearly
- Axial/coronal/sagittal slice as appropriate
- NO diagrams, NO illustrations, NO annotations, NO text labels
- High-resolution diagnostic CT quality"""

        elif 'mri' in image_type.lower():
            prompt = f"""Create a realistic MRI scan: {image_desc}.{finding_emphasis}{no_answer_text}

REQUIREMENTS:
- Must be an actual MRI image showing the specific pathologic finding
- Proper signal characteristics for the specified sequence (T1, T2, FLAIR, etc.)
- Show anatomical detail and the diagnostic abnormality clearly
- Correct tissue contrast for the MRI sequence specified
- NO diagrams, NO illustrations, NO labels, NO text annotations
- High-resolution diagnostic MRI quality"""

        elif 'ultrasound' in image_type.lower() or 'sonography' in image_type.lower():
            prompt = f"""Create a realistic ultrasound image: {image_desc}.{finding_emphasis}{no_answer_text}

REQUIREMENTS:
- Must be an actual ultrasound/sonography image showing the pathologic finding
- Proper grayscale echogenicity (hyperechoic, hypoechoic, anechoic regions)
- Show anatomical structures and diagnostic features clearly
- Typical ultrasound interface with measurement calipers if relevant (but NO text labels of diagnosis)
- NO diagrams, NO illustrations, NO text annotations
- Clinical ultrasound machine output quality"""

        else:
            # Generic medical imaging
            prompt = f"""Create a professional medical {image_type} showing: {image_desc}.{finding_emphasis}{no_answer_text}

REQUIREMENTS:
- Must be realistic medical imaging/photography showing the exact clinical finding described
- The diagnostic feature must be prominently visible and identifiable
- Proper medical imaging characteristics for this modality
- NO diagrams, NO flowcharts, NO tables, NO schematic illustrations, NO labels, NO text annotations
- High-quality clinical photograph suitable for medical board examination
- Actual medical imaging modality output, not educational graphics"""

        response = gemini_client.models.generate_content(
            model='gemini-3-pro-image-preview',
            contents=[prompt],
        )

        for part in response.parts:
            if part.inline_data is not None:
                image = part.as_image()

                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png', dir='static') as f:
                    img_path = f.name

                image.save(img_path)

                return {
                    'url': f"/static/{os.path.basename(img_path)}",
                    'source': 'Nano Banana Pro (AI Generated)',
                    'title': f'Generated: {image_type}'
                }
    except Exception as e:
        logger.error(f"Generation error: {e}")
    return None


def search_and_validate_image(question_data, subject):
    """
    STEP 1: Form good query (done by Claude in question generation)
    STEP 2: Get 3 most promising images from sources
    STEP 3: Validate with Claude Vision, score each
    STEP 4: Pick highest scoring image
    STEP 5: If no image >90%, generate with Nano Banana Pro
    """
    image_search_terms = question_data.get('image_search_terms', [])
    image_type = question_data.get('image_type', '')

    if not image_search_terms:
        return None

    # Check cache first
    cached = get_cached_image(image_search_terms, image_type)
    if cached:
        print(f"✓ Cached image for: {image_search_terms[:2]}")
        return cached

    print(f"\n🔍 Searching image: {image_type}")

    # STEP 2: Collect candidate images (try harder - up to 10 candidates)
    print(f"  → Collecting candidates from internet sources...")
    candidates = collect_candidate_images(image_search_terms, image_type, max_candidates=10)

    if not candidates:
        print(f"  → No candidates found, generating with Nano Banana Pro...")
        if gemini_client:
            result = generate_image_with_gemini(question_data)
            if result:
                cache_image(image_search_terms, image_type, result)
                print(f"✓ Generated image")
                return result
        print(f"✗ No image available")
        return None

    print(f"  → Found {len(candidates)} candidates, validating with Claude Vision...")

    # STEP 3 & 4: Validate and score each candidate
    scored_candidates = []
    for idx, candidate in enumerate(candidates):
        print(f"    • Validating candidate {idx+1}/{len(candidates)}...")
        logger.info(f"Validating candidate {idx+1}: {candidate['source']}")
        validation = validate_image_with_claude(candidate['url'], question_data)
        scored_candidates.append({
            **candidate,
            'score': validation['score'],
            'reason': validation['reason']
        })
        logger.info(f"Score: {validation['score']}/100 - {validation['reason']}")
        print(f"      Score: {validation['score']}/100 - {validation['reason']}")

    # Pick best candidate
    best_candidate = max(scored_candidates, key=lambda x: x['score'])

    # STEP 5: Use best if >=80%, otherwise generate
    if best_candidate['score'] >= 80:
        print(f"✓ Using internet image (score: {best_candidate['score']}/100)")
        result = {
            'url': best_candidate['url'],
            'source': best_candidate['source'],
            'title': best_candidate['title']
        }
        cache_image(image_search_terms, image_type, result)

        # STEP 6: Add visual markers if question references specific parts
        question_text = question_data.get('question', '')
        image_description = question_data.get('image_description', '')

        logger.info(f"Checking for spatial references in question: {question_text[:50]}...")

        if question_text and image_description:
            # Download the image locally first
            try:
                import tempfile
                img_response = requests.get(result['url'], timeout=10)
                if img_response.status_code == 200:
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png', dir='static') as f:
                        f.write(img_response.content)
                        temp_path = f.name

                    logger.info(f"Attempting to add markers to internet image: {temp_path}")
                    marked_path = add_visual_markers_to_image(temp_path, question_text, image_description)

                    if marked_path:
                        result['url'] = f"/static/{os.path.basename(marked_path)}"
                        result['source'] = f"{result['source']} (with markers)"
                        logger.info(f"Successfully added markers, new URL: {result['url']}")
                    else:
                        logger.info("No markers added (no spatial reference or error)")
            except Exception as e:
                logger.error(f"Error adding markers to internet image: {e}")
                import traceback
                logger.error(traceback.format_exc())

        return result
    else:
        print(f"  → Best internet image score only {best_candidate['score']}/100, generating with Nano Banana Pro...")
        if gemini_client:
            result = generate_image_with_gemini(question_data)
            if result:
                # STEP 6: Add visual markers to generated image if needed
                question_text = question_data.get('question', '')
                image_description = question_data.get('image_description', '')

                logger.info(f"Checking for spatial references in question: {question_text[:50]}...")

                if question_text and image_description and result.get('url'):
                    # Convert URL to absolute local path
                    import os
                    if result['url'].startswith('/static/'):
                        local_path = os.path.join(os.getcwd(), result['url'][1:])  # Remove leading /
                    else:
                        local_path = result['url']

                    logger.info(f"Attempting to add markers to: {local_path}")
                    marked_path = add_visual_markers_to_image(local_path, question_text, image_description)

                    if marked_path:
                        result['url'] = f"/static/{os.path.basename(marked_path)}"
                        result['source'] = f"{result['source']} (with markers)"
                        logger.info(f"Successfully added markers, new URL: {result['url']}")
                    else:
                        logger.info("No markers added (no spatial reference or error)")

                cache_image(image_search_terms, image_type, result)
                print(f"✓ Generated image")
                return result

    # Fallback to best candidate if generation fails
    print(f"✓ Using best available (score: {best_candidate['score']}/100)")
    result = {
        'url': best_candidate['url'],
        'source': best_candidate['source'],
        'title': best_candidate['title']
    }
    cache_image(image_search_terms, image_type, result)
    return result


def save_generation_review(questions, course, subject, topics):
    """Save generation to a markdown file for easy review."""
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"review_{timestamp}.md"

    with open(filename, 'w') as f:
        f.write(f"# QBank Generation Review\n\n")
        f.write(f"**Course:** {course}\n")
        f.write(f"**Subject:** {subject}\n")
        f.write(f"**Topics:** {', '.join(topics)}\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Total Questions:** {len(questions)}\n\n")
        f.write("---\n\n")

        for idx, q in enumerate(questions, 1):
            f.write(f"## Q{idx}\n\n")
            f.write(f"**Bloom's Level:** {q.get('blooms_level')}\n")
            f.write(f"**Difficulty:** {['', 'Medium', 'Hard', 'Very Hard'][q.get('difficulty', 1)]}\n")
            f.write(f"**Tags:** {', '.join(q.get('tags', []))}\n\n")

            if q.get('image_url'):
                f.write(f"**Image:** {q['image_url']}\n")
                f.write(f"**Source:** {q.get('image_source', 'N/A')}\n")
                if q.get('image_description'):
                    f.write(f"**Expected:** {q['image_description']}\n")
                f.write(f"\n")

            f.write(f"**Question:**\n{q['question']}\n\n")

            f.write(f"**Options:**\n")
            for opt_idx, opt in enumerate(q['options'], 1):
                marker = "✓ " if opt == q['correct_option'] else "  "
                f.write(f"{marker}{opt_idx}. {opt}\n")
            f.write(f"\n")

            f.write(f"**Explanation:**\n{q['explanation']}\n\n")
            f.write("---\n\n")

    logger.info(f"Review file saved: {filename}")
    return filename


def get_generic_prompt(course, subject, topic, num_questions, exam_format=None):
    """Generate course-specific prompt using exam format metadata."""

    # Get Bloom's distribution from exam_format or use equal distribution as fallback
    if exam_format and 'blooms_distribution' in exam_format:
        # Use course-specific percentages
        blooms_percentages = exam_format['blooms_distribution']
        bloom_distribution = {}

        # Convert percentages to question counts
        total_assigned = 0
        for level in range(1, 6):
            percentage = blooms_percentages.get(str(level), 20)  # Default 20% if missing
            count = round(num_questions * percentage / 100)
            bloom_distribution[level] = count
            total_assigned += count

        # Adjust for rounding errors (add/subtract from highest percentage level)
        if total_assigned != num_questions:
            # Find level with highest percentage and adjust it
            max_level = max(blooms_percentages.items(), key=lambda x: x[1])[0]
            bloom_distribution[int(max_level)] += (num_questions - total_assigned)
    else:
        # Fallback: Equal Bloom's distribution across levels 1-5
        per_level = num_questions // 5
        remainder = num_questions % 5

        bloom_distribution = {
            1: per_level + (1 if remainder > 0 else 0),
            2: per_level + (1 if remainder > 1 else 0),
            3: per_level + (1 if remainder > 2 else 0),
            4: per_level + (1 if remainder > 3 else 0),
            5: per_level + (1 if remainder > 4 else 0),
        }

    # Equal difficulty distribution across 1, 2, 3 (Medium, Hard, Very Hard)
    per_difficulty = num_questions // 3
    diff_remainder = num_questions % 3

    difficulty_distribution = {
        1: per_difficulty + (1 if diff_remainder > 0 else 0),
        2: per_difficulty + (1 if diff_remainder > 1 else 0),
        3: per_difficulty + (1 if diff_remainder > 2 else 0),
    }

    # Use exam format if provided, otherwise infer
    if exam_format:
        # Handle both old format (flat) and new format (nested in question_format)
        question_format = exam_format.get('question_format', {})
        num_options = question_format.get('num_options') or exam_format.get('num_options', 4)
        question_style = question_format.get('type', exam_format.get('question_style', 'Single best answer'))
        typical_length = question_format.get('avg_stem_words', exam_format.get('typical_length', 'Medium length scenarios'))
        emphasis = exam_format.get('emphasis', [])
        domain_context = exam_format.get('domain_characteristics', {}).get('domain', exam_format.get('domain', 'professional examination'))

        logger.info(f"📝 Using exam format: {num_options} options, style={question_style}")
    else:
        # Fallback defaults
        num_options = 4
        question_style = 'Single best answer'
        typical_length = 'Medium length scenarios'
        emphasis = []
        domain_context = 'professional examination'

        # Detect medical for fallback
        is_medical = any(keyword in course.lower() for keyword in ['ukmla', 'neet', 'usmle', 'medical', 'mbbs', 'md', 'clinical'])
        if is_medical:
            domain_context = "medical/clinical examination"

    # Generate option labels (A, B, C, D, E, etc.)
    option_labels = [chr(65 + i) for i in range(num_options)]  # A, B, C, D, E...

    # Format emphasis points
    emphasis_text = "\n   - " + "\n   - ".join(emphasis) if emphasis else ""

    return f"""You are an expert educator creating MCQs for {course} ({domain_context}).

EXAM FORMAT REQUIREMENTS FOR {course}:
- Number of options: {num_options} ({', '.join(option_labels)})
- Question style: {question_style}
- Typical length: {typical_length}
- Key emphasis areas: {emphasis_text if emphasis_text else "Professional standards"}

Generate exactly {num_questions} unique, high-quality MCQs following {course} examination standards.

SUBJECT: {subject}
TOPIC: {topic}

BLOOM'S LEVEL DISTRIBUTION (MANDATORY - must follow exactly):
- Bloom's Level 1 (Remember): {bloom_distribution[1]} questions
- Bloom's Level 2 (Understand): {bloom_distribution[2]} questions
- Bloom's Level 3 (Apply): {bloom_distribution[3]} questions
- Bloom's Level 4 (Analyze): {bloom_distribution[4]} questions
- Bloom's Level 5 (Evaluate): {bloom_distribution[5]} questions

DIFFICULTY DISTRIBUTION (MANDATORY - must follow exactly):
- Difficulty 1 (Medium): {difficulty_distribution[1]} questions
- Difficulty 2 (Hard): {difficulty_distribution[2]} questions
- Difficulty 3 (Very Hard): {difficulty_distribution[3]} questions

QUESTION REQUIREMENTS:
1. Each question must have:
   - Clear, unambiguous stem following {course} style
   - EXACTLY {num_options} options ({', '.join(option_labels)})
   - Only ONE correct answer
   - Detailed explanation for correct answer
   - Bloom's level and difficulty specified

2. Question quality standards:
   - Professional examination level matching {course}
   - Test understanding and application, not just recall
   - Avoid trick questions or ambiguous wording
   - All {num_options} options should be plausible distractors
   - Explanations should be educational and comprehensive

3. Content requirements:
   - Cover different aspects of {topic}
   - Match {course} typical question length and style
   - Use appropriate terminology and conventions for {course}
   - Ensure accuracy and current best practices

OUTPUT FORMAT (JSON array):
[
  {{
    "question": "Question text here",
    "options": [{', '.join([f'"Option {label}"' for label in option_labels])}],
    "correct_option": "{option_labels[0]}",
    "explanation": "Detailed explanation of correct answer",
    "blooms_level": 3,
    "difficulty": 2,
    "course": "{course}",
    "subject": "{subject}",
    "topic": "{topic}",
    "tags": ["{course}"]
  }}
]

CRITICAL REQUIREMENTS:
- MUST have EXACTLY {num_options} options per question (not more, not less)
- "blooms_level": Must be 1, 2, 3, 4, or 5 (Remember, Understand, Apply, Analyze, Evaluate)
- "difficulty": Must be 1 (Medium), 2 (Hard), or 3 (Very Hard)
- Follow the distribution requirements above for both Bloom's levels and difficulty
- "course", "subject", and "topic" are separate fields
- "tags": Array containing ONLY the course name (e.g., ["{course}"])
- "tags" array should be empty or contain domain-specific tags (NOT course/subject/topic)
- correct_option must be one of: {', '.join(option_labels)}

Generate ONLY the JSON array, no additional text."""


def generate_for_topic(course, subject, topic, num_questions, include_images=False, exam_format=None):
    """Generate questions for a single topic."""
    # Get base prompt - using course-specific exam format
    prompt = get_generic_prompt(course, subject, topic, num_questions, exam_format)

    # Determine how many image-based questions to include based on exam format
    num_image_questions = 0
    if include_images and exam_format:
        # Get subject-specific image percentage
        image_by_subject = exam_format.get('image_percentage_by_subject', {})

        # Get overall percentage (can be nested in question_format or at top level)
        overall_image_pct = exam_format.get('question_format', {}).get('image_questions_percentage', 0)
        if overall_image_pct == 0:
            overall_image_pct = exam_format.get('image_questions_percentage', 0)

        # Try to find exact subject match or partial match
        subject_image_pct = None
        for subj_name, pct in image_by_subject.items():
            if subj_name.lower() in subject.lower() or subject.lower() in subj_name.lower():
                subject_image_pct = pct
                logger.info(f"Found subject-specific image percentage: {pct}% for {subject} (matched with {subj_name})")
                break

        # Fall back to overall percentage if no subject-specific match found
        if subject_image_pct is None:
            subject_image_pct = overall_image_pct
            logger.info(f"Using overall image percentage: {subject_image_pct}% (no subject-specific data for {subject})")

        # Calculate number of image questions
        num_image_questions = round(num_questions * subject_image_pct / 100)
        logger.info(f"Including {num_image_questions}/{num_questions} image-based questions ({subject_image_pct}% for {subject})")

    # Add image requirements if requested
    if num_image_questions > 0:
        image_instructions = f"""

IMPORTANT: Out of {num_questions} questions, EXACTLY {num_image_questions} must be IMAGE-BASED questions (the rest should be text-only). This reflects the typical distribution for {subject} in {course}.

For the {num_image_questions} IMAGE-BASED questions, you MUST analyze what the KEY DIAGNOSTIC FINDING is that needs to be visualized.

Think step-by-step:
1. What is the clinical diagnosis or pathology in this question?
2. What specific imaging finding or visual feature would help a student make this diagnosis?
3. What exact medical terminology describes this visual finding?

Then add these fields:
- "image_description": PRECISE description of the KEY diagnostic finding visible in the image. Be specific about pathology, anatomy, and visual characteristics. Examples:
  * "Chest X-ray showing dense right lower lobe consolidation with air bronchograms, consistent with lobar pneumonia"
  * "Brain MRI T2-weighted showing hyperintense periventricular white matter lesions perpendicular to ventricles (Dawson fingers), characteristic of multiple sclerosis"
  * "ECG showing ST-segment elevation >1mm in leads II, III, aVF indicating inferior wall myocardial infarction"
  * "Light microscopy of Gram stain showing gram-positive cocci in grape-like clusters (Staphylococcus aureus)"
  * "Histopathology showing Reed-Sternberg cells (large cells with bilobed 'owl-eye' nuclei) in background of inflammatory cells"

- "image_search_terms": Array of 3-5 medical search queries using SIMPLE, DATABASE-FRIENDLY terms. **IMPORTANT: Use SHORT queries with standard medical terminology that actually exists in NIH/medical databases. DO NOT add "unlabeled", "no text", or "no annotations" - these terms don't exist in databases and will return zero results**. Include:
  * Primary: [condition] + [modality] (2-3 words max)
  * Secondary: [specific finding] + [anatomy] (2-3 words max)
  * Tertiary: [key pathologic term] alone (1-2 words)
  Examples:
  * ["pneumonia chest xray", "lobar consolidation", "air bronchogram"]
  * ["multiple sclerosis MRI", "dawson fingers", "demyelinating plaques"]
  * ["inferior STEMI", "ST elevation ECG", "myocardial infarction"]
  * ["hypertrophic cardiomyopathy", "septal hypertrophy echo", "SAM mitral valve"]

- "image_type": Specific imaging modality (e.g., "Chest X-ray PA view", "Brain MRI T2-weighted", "12-lead ECG", "Gram stain microscopy", "H&E histopathology", "CT abdomen with contrast")

- "key_finding": Single sentence describing what the student should identify (e.g., "Air bronchograms within consolidation", "Dawson fingers pattern", "ST elevation in inferior leads")

CRITICAL: The image should show the PATHOGNOMONIC or CHARACTERISTIC finding that distinguishes this diagnosis. Avoid generic images - be specific about what clinical feature is visible.

**ABSOLUTELY CRITICAL - NO ANSWER TEXT IN IMAGES**: The image MUST be completely unlabeled with NO text, NO annotations, NO arrows with labels, NO diagnosis names visible. Students must interpret the raw clinical image. Any text revealing the answer makes the question invalid. Search terms should include "unlabeled", "no text", "clinical image" to find appropriate images.

**SPATIAL REFERENCES IN QUESTIONS**: When appropriate, use spatial references in the question text to help students focus on the relevant diagnostic area. Examples:
- "The arrow points to which structure?"
- "The circled area shows what pathology?"
- "What diagnosis is indicated by the highlighted region?"
- "The marked area represents which finding?"
These references will trigger automatic visual marker addition (arrows, circles, highlights) to the image. Use them when the diagnostic finding needs to be localized in a specific area of the image.

The question text should reference "the image shown" or "based on the image"."""
        prompt = prompt.replace("Generate ONLY the JSON array, no additional text.", image_instructions + "\n\nGenerate ONLY the JSON array, no additional text.")

    # Call Claude API
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=8192,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    # Parse response
    response_text = message.content[0].text

    # Try to extract JSON from response
    if '```json' in response_text:
        response_text = response_text.split('```json')[1].split('```')[0]
    elif '```' in response_text:
        response_text = response_text.split('```')[1].split('```')[0]

    questions = json.loads(response_text.strip())

    if not isinstance(questions, list):
        raise ValueError('Invalid response format from AI')

    # Fetch images if requested
    if include_images:
        logger.info(f"Fetching images for {len(questions)} questions...")
        images_found = 0
        for idx, q in enumerate(questions, 1):
            if 'image_search_terms' in q or 'image_type' in q:
                logger.info(f"  Question {idx}/{len(questions)}: {q.get('image_type', 'Unknown')}")
                # Note: q already contains 'question' field, so it can be passed directly
                image_result = search_and_validate_image(q, subject)
                if image_result:
                    q['image_url'] = image_result['url']
                    q['image_source'] = image_result['source']
                    images_found += 1
                else:
                    q['image_url'] = None
                    q['needs_image'] = True
        logger.info(f"Image fetch complete: {images_found}/{len(questions)} found")

    return questions


@app.route('/api/generate', methods=['POST'])
def generate_questions():
    """Generate MCQs using Claude API for multiple topics."""
    # Check for API key first
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({'error': 'ANTHROPIC_API_KEY not set. Please set it in your environment.'}), 500
    
    data = request.json
    course = data.get('course')
    subject = data.get('subject')
    topics = data.get('topics', [])  # Now expects array of topics
    num_questions = data.get('num_questions', 10)  # Questions per topic
    include_images = data.get('include_images', False)  # Image-based questions
    exam_format = data.get('exam_format')  # Exam format metadata from course structure

    # Debug logging
    logger.info(f"Received exam_format: {exam_format}")
    if exam_format:
        logger.info(f"  num_options in exam_format: {exam_format.get('num_options', 'NOT FOUND')}")

    # Validate
    if not all([course, subject]) or not topics:
        return jsonify({'error': 'Missing required fields'}), 400

    if num_questions < 5 or num_questions > 50:
        return jsonify({'error': 'Number of questions must be between 5 and 50'}), 400

    # Course validation removed - now accepts any course

    try:
        all_questions = []
        num_options = exam_format.get('num_options', 4) if exam_format else 4
        logger.info(f"Generating {num_questions} questions per topic for {len(topics)} topics")
        logger.info(f"  Format: {num_options} options, images={include_images}")

        # Generate questions for each topic
        for topic in topics:
            topic_questions = generate_for_topic(course, subject, topic, num_questions, include_images, exam_format)
            all_questions.extend(topic_questions)

        # Calculate image statistics if images were requested
        image_stats = None
        if include_images:
            # Count questions designated as image-based (have image metadata)
            image_based_questions = sum(1 for q in all_questions if q.get('image_description') or q.get('image_type'))
            images_with_url = sum(1 for q in all_questions if q.get('image_url'))
            images_missing = sum(1 for q in all_questions if q.get('needs_image'))

            image_stats = {
                'total_questions': len(all_questions),
                'image_based_count': image_based_questions,
                'images_found': images_with_url,
                'images_missing': images_missing,
                'image_percentage': f"{(image_based_questions/len(all_questions)*100):.0f}%" if all_questions else "0%",
                'success_rate': f"{(images_with_url/image_based_questions*100):.1f}%" if image_based_questions else "0%"
            }
            logger.info(f"Image statistics: {image_stats}")

        # Save review file for easy validation
        review_file = save_generation_review(all_questions, course, subject, topics)
        print(f"\n📄 Review file saved: {review_file}")

        response_data = {
            'success': True,
            'questions': all_questions,
            'count': len(all_questions),
            'topics_count': len(topics),
            'review_file': review_file
        }

        if image_stats:
            response_data['image_stats'] = image_stats

        return jsonify(response_data)
        
    except json.JSONDecodeError as e:
        return jsonify({'error': f'Failed to parse AI response as JSON: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': f'API error: {str(e)}'}), 500


@app.route('/api/download', methods=['POST'])
def download_questions():
    """Return questions as downloadable JSON."""
    data = request.json
    questions = data.get('questions', [])

    return jsonify(questions)


@app.route('/api/add-image', methods=['POST'])
def add_image_to_question():
    """Analyze questions (single or batch) and add appropriate medical images."""
    # Check for API key first
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({'error': 'ANTHROPIC_API_KEY not set. Please set it in your environment.'}), 500

    data = request.json
    questions = data.get('questions', [])
    course = data.get('course', '')

    # Handle both single question object and array of questions
    if not isinstance(questions, list):
        questions = [questions]

    # Validate
    if not questions or len(questions) == 0:
        return jsonify({'error': 'At least one question is required'}), 400

    try:
        results = []
        stats = {
            'total': len(questions),
            'images_added': 0,
            'no_image_needed': 0,
            'failed': 0,
            'explanations_generated': 0
        }

        logger.info(f"Processing {len(questions)} question(s) for image addition...")

        for idx, q in enumerate(questions, 1):
            question_text = q.get('question', '')
            options = q.get('options', [])
            correct_option = q.get('correct_option', '')
            explanation = (q.get('explanation') or '').strip()
            subject = q.get('subject', '')

            # Auto-detect course from tags if not provided
            if not course:
                tags = q.get('tags', [])
                if any('NEET' in tag.upper() for tag in tags):
                    q_course = 'NEET PG'
                elif any('USMLE' in tag.upper() for tag in tags):
                    q_course = 'USMLE'
                else:
                    q_course = 'NEET PG'
            else:
                q_course = course

            if not question_text:
                logger.warning(f"Question {idx}: Missing question text, skipping")
                results.append({**q, 'image_status': 'error', 'image_error': 'Missing question text'})
                stats['failed'] += 1
                continue

            logger.info(f"Question {idx}/{len(questions)}: Analyzing...")

            # Generate explanation if missing
            if not explanation:
                logger.info(f"Question {idx}: No explanation found, generating...")
                try:
                    explanation_prompt = f"""You are a medical educator. Generate a clear, educational explanation for this medical question.

QUESTION: {question_text}

OPTIONS:
{chr(10).join([f"{i+1}. {opt}" for i, opt in enumerate(options)])}

CORRECT ANSWER: {correct_option}

SUBJECT: {subject or 'General Medicine'}
COURSE: {q_course}

Generate a comprehensive explanation that:
1. Explains why the correct answer is correct
2. Briefly explains why other options are incorrect (if relevant)
3. Provides relevant clinical context or teaching points
4. Is 2-4 sentences long
5. Uses appropriate medical terminology for {q_course} level

Respond with ONLY the explanation text, no other content."""

                    expl_message = client.messages.create(
                        model="claude-sonnet-4-5",
                        max_tokens=1000,
                        messages=[
                            {"role": "user", "content": explanation_prompt}
                        ]
                    )

                    explanation = expl_message.content[0].text.strip()
                    q['explanation'] = explanation
                    stats['explanations_generated'] += 1
                    logger.info(f"Question {idx}: ✓ Explanation generated")

                except Exception as e:
                    logger.error(f"Question {idx}: Failed to generate explanation - {e}")
                    explanation = ""

            # Step 1: Use Claude to analyze the question and generate image metadata
            analysis_prompt = f"""You are a medical imaging specialist. Analyze this medical question and determine what diagnostic image would be most helpful.

QUESTION: {question_text}

OPTIONS:
{chr(10).join([f"{i+1}. {opt}" for i, opt in enumerate(options)])}

CORRECT ANSWER: {correct_option}

EXPLANATION: {explanation}

Your task: Identify the KEY DIAGNOSTIC FINDING that should be visualized in an image to help students answer this question.

Think step-by-step:
1. What is the clinical diagnosis or pathology in this question?
2. What specific imaging finding or visual feature would help make this diagnosis?
3. What exact medical terminology describes this visual finding?

Return a JSON object with these fields:
{{
  "needs_image": true/false,
  "image_type": "Specific imaging modality (e.g., 'Chest X-ray PA view', 'Brain MRI T2-weighted', '12-lead ECG', 'Gram stain microscopy', 'H&E histopathology')",
  "image_description": "PRECISE description of the KEY diagnostic finding visible in the image. Be specific about pathology, anatomy, and visual characteristics.",
  "image_search_terms": ["array of 3-5 HIGHLY SPECIFIC medical search queries using precise clinical terminology"],
  "key_finding": "Single sentence describing what the student should identify",
  "reasoning": "Brief explanation of why this image would help"
}}

If this question does NOT need an image (e.g., pure clinical reasoning, no visual diagnosis), set needs_image to false.

CRITICAL: Focus on PATHOGNOMONIC or CHARACTERISTIC findings that distinguish this diagnosis.

Respond with ONLY the JSON object, no other text."""

            try:
                # Call Claude API
                message = client.messages.create(
                    model="claude-sonnet-4-5",
                    max_tokens=2000,
                    messages=[
                        {"role": "user", "content": analysis_prompt}
                    ]
                )

                # Parse response
                response_text = message.content[0].text

                # Try to extract JSON from response
                if '```json' in response_text:
                    response_text = response_text.split('```json')[1].split('```')[0]
                elif '```' in response_text:
                    response_text = response_text.split('```')[1].split('```')[0]

                image_metadata = json.loads(response_text.strip())

                # Check if image is needed
                if not image_metadata.get('needs_image', False):
                    logger.info(f"Question {idx}: No image needed - {image_metadata.get('reasoning', 'N/A')}")
                    results.append({
                        **q,
                        'image_status': 'no_image_needed',
                        'image_reasoning': image_metadata.get('reasoning', 'No visual diagnosis required')
                    })
                    stats['no_image_needed'] += 1
                    continue

                # Step 2: Search and validate image using existing pipeline
                # Add the actual question text to image_metadata so markers can be added
                image_metadata['question'] = question_text

                logger.info(f"Question {idx}: Searching for {image_metadata.get('image_type')}...")
                image_result = search_and_validate_image(image_metadata, subject)

                if image_result:
                    # Step 3: Add image metadata to question (only user-facing fields)
                    result_q = {
                        **q,
                        'image_url': image_result['url'],
                        'image_source': image_result['source'],
                        'image_type': image_metadata.get('image_type'),
                        'image_description': image_metadata.get('image_description'),
                        'image_status': 'success'
                    }
                    results.append(result_q)
                    stats['images_added'] += 1
                    logger.info(f"Question {idx}: ✓ Image added from {image_result['source']}")
                else:
                    logger.warning(f"Question {idx}: Could not find suitable image")
                    results.append({
                        **q,
                        'image_status': 'failed',
                        'image_error': 'Could not find or generate suitable image'
                    })
                    stats['failed'] += 1

            except Exception as e:
                logger.error(f"Question {idx}: Error - {e}")
                results.append({
                    **q,
                    'image_status': 'error',
                    'image_error': str(e)
                })
                stats['failed'] += 1

        logger.info(f"Batch complete: {stats['images_added']}/{stats['total']} images added")

        return jsonify({
            'success': True,
            'questions': results,
            'stats': stats
        })

    except Exception as e:
        logger.error(f"Batch processing error: {e}")
        return jsonify({'error': f'Error: {str(e)}'}), 500


def integrate_images_into_lesson(lesson_content, subject, topic):
    """Parse lesson content and integrate actual images where placeholders exist.
    All image searches run in parallel to minimise latency."""
    import re
    from concurrent.futures import ThreadPoolExecutor as _ImgTP

    vague_terms = [
        'pathway', 'flowchart', 'algorithm', 'diagram', 'mechanism', 'cascade',
        'process', 'cycle', 'overview', 'summary', 'treatment plan', 'management',
        'approach', 'strategy', 'decision tree', 'flow', 'schematic'
    ]
    specific_terms = [
        # ECG / cardiac monitoring
        'ecg', 'ekg', 'rhythm strip', 'holter',
        # Radiology
        'x-ray', 'xray', 'chest radiograph', 'radiograph',
        'ct', 'computed tomography',
        'mri', 'magnetic resonance',
        'pet', 'spect', 'nuclear',
        'fluoroscopy', 'angiography', 'angiogram',
        # Ultrasound / echo
        'ultrasound', 'echocardiogram', 'echocardiograph', 'echo ',
        'transthoracic', 'transoesophageal', 'transesophageal',
        'doppler', 'sonograph',
        # Pathology / microscopy
        'histology', 'histopathology', 'microscopy', 'biopsy',
        'blood film', 'blood smear', 'smear', 'cytology',
        'stain', 'haematoxylin', 'hematoxylin',
        # Endoscopy
        'endoscopy', 'colonoscopy', 'bronchoscopy', 'gastroscopy',
        'fundoscopy', 'funduscopy', 'ophthalmoscopy', 'slit lamp',
        # Clinical photos / specimens
        'photograph', 'photo', 'clinical image', 'clinical photo',
        'anatomical', 'specimen',
        # Specific modalities
        'spirometry', 'peak flow', 'capillary', 'dermatoscopy', 'dermoscopy',
    ]

    image_pattern = r'\*\*Figure (\d+):\s*\[Image:\s*([^\]]+)\]\*\*'

    # Collect all searchable figures first
    candidates = []
    for match in re.finditer(image_pattern, lesson_content):
        figure_num = match.group(1)
        description = match.group(2).strip()
        full_placeholder = match.group(0)
        desc_lower = description.lower()

        if any(t in desc_lower for t in vague_terms):
            logger.warning(f"⚠️ Figure {figure_num} too vague: '{description}' — skipping")
            continue
        if not any(t in desc_lower for t in specific_terms):
            logger.warning(f"⚠️ Figure {figure_num} not specific enough: '{description}' — skipping")
            continue
        candidates.append((figure_num, description, full_placeholder))

    if not candidates:
        return lesson_content

    def _fetch_image(figure_num, description, full_placeholder):
        metadata = {
            'image_description': description,
            'image_type': 'Medical illustration',
            'image_search_terms': [
                f"{subject} {topic} {description}",
                f"{description} medical image",
                f"{topic} {description}"
            ],
            'question': f"Medical illustration showing {description} in the context of {topic}"
        }
        logger.info(f"Searching for Figure {figure_num}: {description}")
        try:
            result = search_and_validate_image(metadata, subject)
            return full_placeholder, result, figure_num, description
        except Exception as e:
            logger.error(f"Error searching for image '{description}': {e}")
            return full_placeholder, None, figure_num, description

    # Search all images in parallel
    with _ImgTP(max_workers=len(candidates)) as pool:
        futures = [pool.submit(_fetch_image, fn, desc, ph) for fn, desc, ph in candidates]
        for fut in futures:
            placeholder, result, figure_num, description = fut.result()
            if result:
                markdown = f"![{description}]({result['url']})\n*Figure {figure_num}: {description}*"
                lesson_content = lesson_content.replace(placeholder, markdown)
                logger.info(f"✓ Found image for Figure {figure_num}")
            else:
                logger.warning(f"✗ No image found for Figure {figure_num}")

    return lesson_content


def _get_image_requirements(subject, lesson_type='topic'):
    """Determine minimum image requirements based on subject and lesson type."""
    subject_lower = subject.lower()

    # Define subject categories by visual intensity
    highly_visual = ['cardiology', 'anatomy', 'surgery', 'radiology', 'pathology',
                     'dermatology', 'ophthalmology', 'orthopedics', 'neurology',
                     'ent', 'obstetrics', 'gynecology', 'pediatrics', 'histology',
                     'microbiology']

    moderately_visual = ['medicine', 'physiology', 'pharmacology', 'psychiatry',
                         'emergency', 'critical care', 'anesthesia', 'immunology']

    less_visual = ['biochemistry', 'biostatistics', 'epidemiology', 'ethics',
                   'forensic', 'community medicine', 'preventive']

    # Determine category
    if any(keyword in subject_lower for keyword in highly_visual):
        if lesson_type == 'topic':
            return {
                'min_images': 5,
                'max_images': 8,
                'guidance': 'HIGHLY VISUAL SUBJECT: Include diagnostic images (X-rays, CT/MRI, histology, clinical photos, ECGs, etc.)'
            }
        else:  # chapter
            return {
                'min_images': 1,
                'max_images': 2,
                'guidance': 'Include 1-2 key diagnostic images'
            }

    elif any(keyword in subject_lower for keyword in moderately_visual):
        if lesson_type == 'topic':
            return {
                'min_images': 3,
                'max_images': 5,
                'guidance': 'MODERATELY VISUAL: Include clinical presentations, key investigations, anatomical correlations'
            }
        else:  # chapter
            return {
                'min_images': 1,
                'max_images': 1,
                'guidance': 'Include 1 key clinical image if relevant'
            }

    else:  # less visual or unknown
        if lesson_type == 'topic':
            return {
                'min_images': 2,
                'max_images': 3,
                'guidance': 'Include relevant diagrams, molecular structures, or key concepts (can use tables/mermaid for some)'
            }
        else:  # chapter
            return {
                'min_images': 0,
                'max_images': 1,
                'guidance': 'Images optional - use tables/flowcharts if more appropriate'
            }


def _get_domain_specific_requirements(course, is_medical, chapter_list):
    """Generate domain-specific requirements based on course type."""
    if is_medical:
        # Check if chapters have NICE refs
        has_nice_refs = any('nice_refs' in ch for ch in chapter_list if isinstance(ch, dict))

        requirements = """===========  DOMAIN-SPECIFIC: MEDICAL/CLINICAL  ===========
✓ Include evidence-based medicine with specific clinical guidelines (NICE, ESC, AHA where applicable)
✓ Specific drug dosages, timing, monitoring parameters, contraindications
✓ Diagnostic thresholds with sensitivity/specificity where relevant
✓ Clinical decision-making with patient safety considerations
✓ Red flags, complications, and when to escalate/refer
✓ Medicolegal considerations where relevant (consent, capacity)
"""
        if has_nice_refs:
            requirements += """✓ When chapters have 'nice_refs', cite specific guideline numbers (e.g., "NICE NG136 recommends...")
✓ Include guideline-specific thresholds, algorithms, and recommendations
"""
        return requirements

    elif 'engineering' in course.lower() or 'cs' in course.lower() or 'computer' in course.lower():
        return """===========  DOMAIN-SPECIFIC: ENGINEERING/CS  ===========
✓ Include design patterns, algorithms, and industry best practices
✓ Specific time/space complexity, Big-O notation where relevant
✓ Code examples and pseudocode for key algorithms
✓ Trade-offs between different approaches (performance vs maintainability)
✓ Common bugs, edge cases, and debugging strategies
✓ Standards and specifications (IEEE, ISO, RFC where applicable)
"""

    elif 'law' in course.lower() or 'legal' in course.lower():
        return """===========  DOMAIN-SPECIFIC: LAW/LEGAL  ===========
✓ Cite specific statutes, cases, and legal precedents
✓ Jurisdiction-specific considerations
✓ Legal tests, standards of proof, and burden allocation
✓ Exceptions, defenses, and procedural nuances
✓ Recent developments and ongoing controversies
✓ Practical application to hypothetical fact patterns
"""

    elif 'business' in course.lower() or 'mba' in course.lower() or 'finance' in course.lower():
        return """===========  DOMAIN-SPECIFIC: BUSINESS/FINANCE  ===========
✓ Include specific formulas, ratios, and financial metrics
✓ Real-world case studies and industry examples
✓ Regulatory frameworks and compliance requirements
✓ Risk analysis and mitigation strategies
✓ Quantitative models and their assumptions
✓ Market context and macroeconomic considerations
"""

    else:
        # Generic for any other course
        return """===========  DOMAIN-SPECIFIC: GENERAL  ===========
✓ Include authoritative sources and established frameworks in this field
✓ Specific formulas, equations, or key quantitative relationships
✓ Domain standards, conventions, and best practices
✓ Real-world applications and practical examples
✓ Common mistakes and how to avoid them
✓ Current developments and recent research where relevant
"""


def generate_chapters_for_topic(course_name, subject_name, topic_name):
    """
    Dynamically generate chapter names for a topic when they're missing.

    Args:
        course_name: Name of the course (e.g., "UKMLA AKT")
        subject_name: Name of the subject (e.g., "Internal Medicine - Adult")
        topic_name: Name of the topic (e.g., "Cardiology")

    Returns:
        List of chapter dictionaries: [{"name": "Chapter Name"}, ...]
    """
    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    prompt = f"""Generate 8-12 specific chapter names for a lesson on: {topic_name}

Context:
- Course: {course_name}
- Subject: {subject_name}
- Topic: {topic_name}

Generate focused, specific chapter names that cover the key subtopics, conditions, or concepts.

For medical topics, include specific conditions, diseases, or procedures.
For engineering topics, include specific principles, theorems, or applications.

OUTPUT FORMAT (strict JSON array):
[
    {{"name": "Chapter 1 Name"}},
    {{"name": "Chapter 2 Name"}},
    ...
]

Generate ONLY the JSON array, no other text."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1000,
            temperature=0.7,
            timeout=30.0,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text.strip()

        # Clean up response
        if response_text.startswith('```'):
            response_text = response_text.split('```')[1]
            if response_text.startswith('json'):
                response_text = response_text[4:]
        response_text = response_text.strip()

        chapters = json.loads(response_text)
        return chapters

    except Exception as e:
        logger.error(f"Error generating chapters: {e}")
        # Return default chapters if generation fails
        return [
            {"name": f"{topic_name} - Part 1"},
            {"name": f"{topic_name} - Part 2"},
            {"name": f"{topic_name} - Part 3"}
        ]


@app.route('/api/generate-lessons', methods=['POST'])
def generate_lessons():
    """Generate review lessons for topics and chapters."""
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({'error': 'ANTHROPIC_API_KEY not set'}), 500

    data = request.json
    course = data.get('course')
    uploaded_json = data.get('uploaded_json')
    generate_all = data.get('generate_all', False)
    selected_subject_idx = data.get('selected_subject_idx')
    selected_topic_indices = data.get('selected_topic_indices')
    selected_chapters = data.get('selected_chapters')

    if not course:
        return jsonify({'error': 'Course is required'}), 400

    if not uploaded_json:
        return jsonify({'error': 'Course structure is required'}), 400

    try:
        course = uploaded_json.get('Course', course)
        subjects = uploaded_json.get('subjects', [])

        if not subjects:
            return jsonify({'error': 'No subjects found in structure'}), 400

        # Process based on selection
        subjects_to_process = []

        if generate_all:
            # Generate for all subjects
            logger.info(f"Generating lessons for entire course: {course}")
            subjects_to_process = subjects
        else:
            # Generate for selected subject/topics/chapters
            if selected_subject_idx is None:
                return jsonify({'error': 'Subject selection required'}), 400

            subject_data = subjects[selected_subject_idx]
            logger.info(f"Generating lessons for subject: {subject_data.get('name')}")

            # Filter topics if specific ones are selected
            if selected_topic_indices:
                filtered_topics = [subject_data['topics'][i] for i in selected_topic_indices]
                subject_data = {**subject_data, 'topics': filtered_topics}

            # Filter chapters if specific ones are selected
            if selected_chapters:
                # Parse chapter selections (format: "topicIdx-chapterIdx")
                chapter_selections = {}
                for ch in selected_chapters:
                    topic_idx, ch_idx = map(int, ch.split('-'))
                    if topic_idx not in chapter_selections:
                        chapter_selections[topic_idx] = []
                    chapter_selections[topic_idx].append(ch_idx)

                # Filter topics and chapters
                filtered_topics = []
                for topic_idx, topic in enumerate(subject_data['topics']):
                    if topic_idx in chapter_selections:
                        filtered_chapters = [topic['chapters'][i] for i in chapter_selections[topic_idx]]
                        filtered_topics.append({**topic, 'chapters': filtered_chapters})

                subject_data = {**subject_data, 'topics': filtered_topics}

            subjects_to_process = [subject_data]

        # Parse structure for lesson generation
        all_lessons = []
        subject = None

        from concurrent.futures import ThreadPoolExecutor as _TP

        def _gen_and_integrate(client_ref, prompt, max_tok, subj, name):
            """Generate a lesson via Claude then integrate images. Thread-safe."""
            try:
                msg = client_ref.messages.create(
                    model="claude-sonnet-4-5",
                    max_tokens=max_tok,
                    temperature=0.7,
                    messages=[{"role": "user", "content": prompt}]
                )
                text = msg.content[0].text.strip()
                logger.info(f"✓ Generated lesson for {name} ({len(text)} chars)")
                return integrate_images_into_lesson(text, subj, name)
            except Exception as e:
                logger.error(f"Error generating lesson for {name}: {e}")
                return f"Error generating lesson: {str(e)}"

        for subject_data in subjects_to_process:
            subject = subject_data.get('name')
            structure = []

            for topic_data in subject_data.get('topics', []):
                topic_entry = {
                    'topic': topic_data.get('name'),
                    'chapters': []
                }

                # Include optional fields if present
                if 'high_yield' in topic_data:
                    topic_entry['high_yield'] = topic_data['high_yield']

                # If chapters are empty, generate them dynamically
                chapters_list = topic_data.get('chapters', [])
                if not chapters_list or len(chapters_list) == 0:
                    logger.info(f"  Generating chapters for topic: {topic_data.get('name')}")
                    chapters_list = generate_chapters_for_topic(
                        course,
                        subject_data.get('name'),
                        topic_data.get('name')
                    )
                    logger.info(f"  Generated {len(chapters_list)} chapters")

                # Parse chapters (can be strings or objects)
                for chapter in chapters_list:
                    if isinstance(chapter, str):
                        topic_entry['chapters'].append({'name': chapter})
                    elif isinstance(chapter, dict):
                        chapter_entry = {'name': chapter.get('name')}
                        # Preserve optional fields like nice_refs
                        if 'nice_refs' in chapter:
                            chapter_entry['nice_refs'] = chapter['nice_refs']
                        topic_entry['chapters'].append(chapter_entry)

                structure.append(topic_entry)

            # Compute per-subject invariants once (don't repeat inside the topic loop)
            is_medical = any(kw in course.lower() for kw in ['ukmla', 'neet', 'usmle', 'medical', 'mbbs', 'md', 'clinical'])
            if is_medical:
                audience_desc = "Medical licensing exam candidates"
                depth_desc = "Clinical practitioner level - assume medical school foundation knowledge"
            else:
                audience_desc = f"{course} exam candidates or advanced learners"
                depth_desc = "Advanced professional level - assume foundational knowledge"
            image_reqs        = _get_image_requirements(subject, 'topic')
            chapter_image_reqs = _get_image_requirements(subject, 'chapter')

            def _process_topic(topic_data):
                """Build prompts and generate (topic + chapters) in parallel. Returns lesson dict."""
                topic_name = topic_data.get('topic')
                chapters   = topic_data.get('chapters', [])
                high_yield = topic_data.get('high_yield', False)

                chapter_list = []
                for chapter in chapters:
                    if isinstance(chapter, dict):
                        entry = {'name': chapter.get('name')}
                        if 'nice_refs' in chapter:
                            entry['nice_refs'] = chapter['nice_refs']
                        chapter_list.append(entry)
                    else:
                        chapter_list.append({'name': chapter})

                chapter_list_json = json.dumps(chapter_list, indent=2)
                logger.info(f"Generating lesson for {course} > {subject} > {topic_name}")

                lesson_prompt = f"""====================  LESSON GENERATOR (COURSE-AGNOSTIC)  ====================
- Course       : {course}
- Subject      : {subject}
- Topic        : {topic_name}
- ChaptersJSON : {chapter_list_json}
- WordTarget   : 1000-1200 words max | 7 pages max
- Audience     : {audience_desc}
- Depth Level  : {depth_desc}
==========================================================================

🔴 CRITICAL MANDATORY REQUIREMENTS (NON-NEGOTIABLE):
1. MUST end with "### High Yield Summary" section (Key Take-Aways, Essential Numbers/Formulas, Key Principles, Quick Reference)
2. 🔴 CHAPTER REFERENCES (CRITICAL FORMAT - MUST USE EXACT SYNTAX):
   🚨 MANDATORY: Reference ALL chapters from the chapters list using this EXACT format:

   Format: (see **Chapter Name**)

   ✅ EXAMPLES OF CORRECT FORMAT:
   - "Ischemic heart disease (see **Acute Coronary Syndromes: STEMI and NSTEMI**) accounts for..."
   - "Management of arrhythmias (see **Atrial Fibrillation, Flutter and Supraventricular Tachycardias**) requires..."
   - "Hypertensive crisis (see **Hypertension: Assessment and Treatment Strategies**) demands..."
   - "Systolic dysfunction (see **Heart Failure: Acute and Chronic Management**) is characterized by..."

   ❌ WRONG FORMATS (DO NOT USE):
   - "(see Acute Coronary Syndromes)" - MISSING bold markers **
   - "see **Chapter Name**" - MISSING parentheses ()
   - "[Chapter Name]" - WRONG brackets
   - "Related chapters: ..." - WRONG approach

   → Reference EVERY chapter from the list at least once throughout the lesson
   → Use exact chapter names as provided in ChaptersJSON
   → Bold markers (**) are REQUIRED for automatic linking to work
3. 🔴 IMAGES (CRITICAL): MINIMUM {image_reqs['min_images']} images required, up to {image_reqs['max_images']} recommended
   {image_reqs['guidance']}
   - Format: **Figure N: [Image: SPECIFIC modality + exact finding/structure]**
   - Examples of SPECIFIC descriptions:
     ✅ "Chest X-ray PA view showing cardiomegaly with increased cardiothoracic ratio"
     ✅ "ECG showing ST elevation in leads V1-V4 indicating anterior STEMI"
     ✅ "Histology section showing non-caseating granulomas with multinucleated giant cells"
     ❌ "Heart anatomy diagram" (too vague - use Mermaid instead)
     ❌ "Treatment flowchart" (use Mermaid flowchart, not image)
   - Include image numbers sequentially (Figure 1, Figure 2, etc.)
   - Place images strategically throughout lesson, not clustered
4. MUST include 2-3 ```mermaid flowcharts for algorithms/workflows/processes
   IMPORTANT: Use SIMPLE mermaid syntax only. Example:
   ```mermaid
   flowchart TD
       A[Start] --> B{{Decision}}
       B -->|Yes| C[Action 1]
       B -->|No| D[Action 2]
   ```
   Rules: Use TD (top-down) or LR (left-right). Shapes: [] rectangles, {{}} diamonds, () rounded.
   Keep it simple - max 8 nodes. Use basic punctuation only in labels.
==========================================================================

===========  DEPTH & RIGOR REQUIREMENTS  ===========
✓ Write for advanced learners preparing for professional exams - NOT beginners
✓ Assume foundational knowledge - focus on ADVANCED APPLICATION
✓ Include domain-specific standards, best practices, and authoritative sources where applicable
✓ Specific numbers, formulas, thresholds, parameters, and quantitative details
✓ Decision-making frameworks with real-world trade-offs and nuances
✓ Common pitfalls, edge cases, and when to escalate/consult experts
✓ Depth over breadth - better to cover fewer concepts thoroughly than many superficially
==========================================================================

{_get_domain_specific_requirements(course, is_medical, chapter_list)}

===========  WRITING VOICE & STYLE  ===========
✓ Professional yet engaging - authoritative voice with narrative flow
✓ Conversational but sophisticated
✓ Evidence-based explanations with mechanistic depth
✓ Concrete scenarios over abstract theory
✓ Specific numbers, formulas, thresholds, timings throughout
✓ Confidence-building through mastery of nuance
✓ NO explicit mentions of "exams", "examiners", "toppers", "candidates", "test", "assessment"
✓ Capture excellence through depth and precision, not exam rhetoric

===========  FORMATTING REQUIREMENTS (CRITICAL)  ===========
🔴 PARAGRAPH BREAKS (MANDATORY):
✓ MAXIMUM 3-4 sentences per paragraph - then MUST add blank line
✓ Use DOUBLE newlines (blank lines) between ALL paragraphs
✓ Never write more than 5 lines without a blank line break
✓ Each major point should be a separate paragraph with blank line before and after

VISUAL MARKERS:
✓ Use emojis sparingly for visual markers (🎯 for key points, 🚩 for red flags, 💎 for clinical pearls, ⚠️ for warnings)
✓ Bold key terms and concepts: **term**
✓ Use bullet points (• or *) for lists with proper line breaks

SPECIAL SECTIONS:
  - **Key Points:** at the end (will be highlighted in blue box)
  - **Mnemonic:** for memory aids (will be highlighted in purple box)
  - **Red Flags:** for urgent warnings (will be highlighted in red box)
  - **Clinical Pearl:** for expert tips (will be highlighted in green box)
✓ Use markdown tables with | separators for comparisons
✓ Ensure each section has clear spacing - double newlines between major elements

===========  LESSON FLOW STRUCTURE  ===========
CRITICAL RULES FOR SECTION HEADERS:
✗ NO section numbers ("1 —", "2 —", "Section 1", etc.)
✗ NO Bloom's labels ("Remember", "Understand", "Apply", "Analyze", "Level 1", etc.)
✗ NO "Page 1", "Page 2" etc.
✓ ONLY use short, topic-specific memorable titles that read naturally to a learner

OPENING PARAGRAPH (MANDATORY — appears BEFORE the first ### header):
Write a single paragraph of exactly 25-30 words — a vivid scenario, clinical moment,
or compelling question that immediately anchors WHY this topic matters. No heading.
This is the reader's entry point into the lesson. Make it memorable.
Example style: "A 52-year-old arrives breathless at 3am. The next 20 minutes of decisions
hinge on one skill: reading this topic fluently. Here is how you build it."

### [Short Topic-Specific Title — Foundation]
**Core Knowledge Building**
* Essential classifications with clinical significance (not just lists)
* Evidence-based definitions and diagnostic criteria with specific thresholds
* Epidemiology with absolute numbers (incidence, prevalence, mortality where relevant)
* Must-know mnemonics linked to clinical decision-making
* TABLE with key classifications or criteria
* 🔴 IMAGES: Include 1-2 diagnostic images in this section:
  → **Figure 1: [Image: specific investigation + exact visible findings]**
  → Examples: "ECG showing sinus rhythm with normal axis", "Chest X-ray PA view showing normal heart size and clear lung fields"
  → Be ULTRA-SPECIFIC - mention modality, view, and visible features
* 🔴 MANDATORY: Integrate 1-2 chapter names NATURALLY IN SENTENCES (not at section end):
  → "Acute coronary syndromes (see Acute coronary syndrome management) present with..."
  → "Hypertension diagnosis (see Hypertension diagnosis and management) requires BP >140/90..."

### [Short Topic-Specific Title — Mechanisms]
**Pathophysiology & Clinical Mechanisms**
* Mechanistic understanding that explains clinical presentations
* Molecular/cellular basis linked to macroscopic clinical findings
* WHY certain investigations work, WHY certain treatments target specific pathways
* Pharmacodynamics and pharmacokinetics with clinical implications
* Quantitative relationships (e.g., Starling forces, oxygen delivery equations)
* ```mermaid flowchart showing pathophysiological pathway/cascade (MANDATORY - use simple syntax, max 8 nodes)
* Table linking mechanisms to clinical manifestations
* 🔴 IMAGES: Include anatomical/histological images if relevant to mechanism:
  → Examples: "Histology showing specific cellular changes", "Anatomical diagram showing affected structures"
* 🔴 Integrate 1-3 chapter names INSIDE sentences (e.g., "RAAS activation in heart failure (see Heart failure pathophysiology) leads to...")

### [Short Topic-Specific Title — Clinical Application]
**Clinical Presentations & Diagnostic Approach**
* Real clinical scenarios with presenting complaints and examination findings
* Diagnostic approach with pre-test probability considerations
* Investigation sequence with sensitivity/specificity/PPV/NPV where relevant
* Interpretation of results in clinical context (not just normal ranges)
* When to investigate further vs when to act on clinical diagnosis
* ```mermaid flowchart for diagnostic algorithm (MANDATORY - use simple syntax, max 8 nodes)
* Table with likelihood ratios and diagnostic accuracy
* Red flags requiring urgent action
* 🔴 IMAGES: Include 2-3 diagnostic investigation images (CRITICAL for clinical diagnosis):
  → Examples: "ECG showing specific abnormality", "CT scan showing characteristic finding", "Blood film showing specific cells"
  → **Figure 2-4: [Image: modality + view + specific visible diagnostic feature]**
  → These are essential for pattern recognition in exams and clinical practice
* 🔴 Integrate 2-3 chapter names INSIDE sentences (e.g., "Acute coronary syndromes (see ACS diagnosis and risk stratification) present with...")

### [Short Topic-Specific Title — Differential Thinking]
**Differential Diagnosis & Clinical Reasoning**
* Systematic approach to distinguishing between similar presentations
* Key discriminating features with clinical significance (not just lists of differences)
* Likelihood ratios, Bayesian reasoning, or clinical prediction rules where applicable
* Time course, age, comorbidities, and other contextual factors
* Common diagnostic errors and cognitive biases to avoid
* When similar conditions require different urgent interventions
* COMPARISON TABLE showing key differentiators (MANDATORY)
* ```mermaid decision tree for differentiation if algorithm-based (OPTIONAL)
* Quantitative differentiators with specific thresholds
* 🔴 NO images needed in this section - tables are clearer for differentials
* 🔴 Integrate 2-3 chapter names INSIDE sentences (e.g., "Unlike stable angina (see Stable angina management), ACS presents...")

### [Short Topic-Specific Title — Management]
**Evidence-Based Management & Treatment**
* Evidence-based treatment algorithms with NICE/guideline references
* Specific drug names, dosages, routes, frequencies, durations
* Monitoring requirements (what to check, when, and why)
* Treatment targets and when to escalate/switch therapy
* Contraindications, drug interactions, and adverse effects requiring action
* Non-pharmacological interventions with evidence level
* When to refer and to which specialty (primary vs secondary care)
* ```mermaid flowchart for treatment algorithm (MANDATORY)
* Evidence-based treatment table with specific dosing (MANDATORY)
* Cost-effectiveness and NHS formulary considerations
* 🔴 NO images needed - use mermaid flowcharts and tables only
* 🔴 Integrate 2-3 chapter names INSIDE sentences with NICE refs (e.g., "Heart failure pharmacotherapy (see Heart failure drug therapy - NICE NG106) includes...")

### [Short Topic-Specific Title — Advanced Integration]
**Advanced Clinical Integration & Special Scenarios**
* Pick one clinically important but less emphasized chapter from ChaptersJSON
* Complex cases: multimorbidity, atypical presentations, special populations
* Pregnancy, elderly, renal/hepatic impairment considerations where relevant
* Emerging evidence or recent guideline changes
* Complications, long-term sequelae, and follow-up requirements
* Integration with other conditions/systems (holistic clinical thinking)
* ADVANCED TABLE for complex data (MANDATORY)
* Mnemonic for complex decisions (≤10 words with clinical context)
* 🔴 OPTIONAL: Include 1 specialist investigation ONLY if truly essential
  → Examples: "MRI brain showing MS plaques", "Bone marrow biopsy showing leukaemia"
  → Most topics won't need an image here
* 🔴 Integrate 1-2 chapter names INSIDE sentences with NICE refs (e.g., "In pregnancy (see Hypertension in pregnancy), target BP is lower...")

### High Yield Summary
🔴🔴🔴 ABSOLUTELY MANDATORY FINAL SECTION - DO NOT SKIP THIS! 🔴🔴🔴

**Key Take-Aways:**
* 5-7 bullet points with the most critical concepts for this topic
* Include specific numbers, formulas, thresholds, and key parameters
* Critical points that cannot be missed
* Domain-specific recommendations and best practices

**Essential {topic_name} Numbers/Formulas:**
* Critical values, thresholds, or key equations (table format)
* Most commonly used formulas or parameters
* Key quantitative relationships and their significance

**Key Principles/Pearls:**
* 3-5 practical insights from expert practice
* Common mistakes and how to avoid them
* Pattern recognition tips and heuristics

**Quick Reference:**
* SUMMARY TABLE with key numbers/formulas/thresholds (MANDATORY)
* ```mermaid flowchart for quick reference algorithm if needed (OPTIONAL)
* Decision rules, frameworks, or scoring systems
* Critical points and important caveats
* 🔴 NO images needed in summary - tables and mermaid only

**Related Chapters:**
* ONLY list chapters from ChaptersJSON that were NOT already integrated into the text above
* If all chapters were already mentioned in the lesson, write "All chapters covered above"
* Do NOT repeat chapters that were already woven into the narrative
* Note: "For rapid revision of individual chapters, refer to the dedicated chapter-level notes included with this topic."

===========  ESSENTIAL FOR EXAM PREPAREDNESS (STEALTH MODE)  ===========
✓ High-yield concept prioritization (without labeling as "high-yield")
✓ Pattern recognition frameworks ("Master X, and you unlock...")
✓ Memory aids naturally embedded (mnemonics, decision trees)
✓ Quick recall formats (calculation tables, criteria lists)
✓ Common pitfall identification ("Don't confuse X with Y")
✓ Essential numbers for memorization ("Critical thresholds")
✓ Rapid problem-solving approaches (decision algorithms)
✓ Integration points between concepts (connects to clinical thinking)

===========  MANDATORY ELEMENTS  ===========
✓ IMAGES (Topic-dependent - use strategic judgment):
  → Format: **Figure N: [Image: highly specific description with visible features]**
  → Include 0-3 images based on what's visually essential for THIS topic
  → If topic has key visual elements (domain-specific diagrams, patterns, structures) → Include them
  → If topic is theoretical/conceptual without essential images → Skip images, use mermaid/tables
  → Quality over quantity - only essential visual aids

✓ 2-3 ```mermaid flowcharts for algorithms/workflows/processes (MANDATORY)
✓ Tables with quantitative data in every section (MANDATORY)
✓ Concrete numbers, formulas, parameters, thresholds throughout (MANDATORY)
✓ Engaging, confidence-building language
✓ Memory hooks and mnemonics with quantitative elements

🔴🔴🔴 CHAPTER INTEGRATION RULES (CRITICAL - DO NOT VIOLATE): 🔴🔴🔴
✓ All chapter names must use EXACT names from ChaptersJSON - no variations
✓ Integrate chapter names INSIDE sentences when discussing each concept
✓ Format: "Concept/topic (see Chapter Name) explanation continues..."
  - Example: "Topic X (see Related Chapter Name) demonstrates..."
  - Example: "Concept Y (see Chapter on Y Details) involves..."
  - Example: "Process Z (see Advanced Z Techniques) requires..."
✓ Each section MUST integrate 1-3 chapter names naturally in flowing text
✓ NEVER create separate "Related Chapters:" lists within sections
✓ NEVER list chapters as bullet points at section ends
✓ Chapters should feel like natural cross-references, not forced insertions
✓ Visual elements should enhance understanding, not just fill space
✓ For images: Use format [Image: specific description] - be precise about what structures, patterns, features, or relationships are shown
✓ End lesson with "High Yield Summary" section containing most important concepts
✓ Prioritize clear, informative visuals over decorative images

===========  IMAGE STRATEGY (COURSE-AGNOSTIC PRINCIPLE-BASED)  ===========

STEP 1: Strategic Image Identification
Before writing, ask yourself these questions about THIS SPECIFIC TOPIC:

1. "What are the KEY VISUAL ELEMENTS that define or illustrate this concept?"
   → Medical: ECGs, X-rays, scans, histology, clinical photos
   → Engineering: Circuit diagrams, waveforms, stress-strain curves, system architectures
   → Science: Molecular structures, experimental setups, microscopy images, spectra
   → Mathematics: Graphs of functions, geometric constructions, visual proofs
   → Other fields: Domain-specific diagrams, photographs, visualizations

2. "Are there CHARACTERISTIC visual patterns/features that learners MUST recognize?"
   → If YES and the visual is diagnostic/definitional → Include it

3. "Would a learner be unable to understand/apply this concept without seeing certain images?"
   → If YES → That image is essential, include it
   → If NO → Skip the image, use table/mermaid instead

STEP 2: Apply Domain-Specific Rules

✅ INCLUDE images for (adapt to your course domain):
- **Medical**: Diagnostic imaging (ECG, X-ray, CT/MRI), histopathology, clinical photos, lab results
- **Engineering**: Circuit diagrams, oscilloscope traces, CAD drawings, system diagrams, equipment photos
- **Science**: Molecular structures, experimental apparatus, microscopy, chromatograms, spectra
- **Mathematics**: Graphs of key functions, geometric diagrams, visual proofs
- **Law**: Flowcharts of legal processes (but use mermaid instead)
- **Business**: Real charts/data (not generic icons), organizational structures
- **Other**: Domain-appropriate visualizations that aid understanding

❌ NEVER include images for (universal across all courses):
- Calculators, interfaces, software screenshots (unless demonstrating specific UI functionality)
- Generic charts, graphs, or icon-based visualizations
- Flowcharts, algorithms, process diagrams (use ```mermaid instead)
- Conceptual illustrations that don't show specific detail
- Decorative or motivational graphics

STEP 3: Image Count Decision (Topic-Dependent)
- If topic has 2-3 essential visual elements → Include 2-3 images
- If topic has 1 key visual element → Include 1 image
- If topic is primarily conceptual/theoretical with no essential images → 0 images, use mermaid/tables

STEP 4: Image Format - Be ULTRA-SPECIFIC about visible features:
**Figure N: [Image: Type + specific visible features/details]**

GOOD examples (highly specific, domain-adapted):
- Medical: "12-lead ECG showing atrial fibrillation with absent P waves and irregularly irregular RR intervals"
- Engineering: "Bode plot showing -20dB/decade roll-off with phase margin of 45° at unity gain frequency"
- Chemistry: "Mass spectrum showing molecular ion peak at m/z 180 with base peak at m/z 107"
- Physics: "Double-slit interference pattern showing bright fringes at d·sinθ = nλ intervals"

BAD examples (will be rejected, universal):
- "System overview diagram" (too vague, use mermaid)
- "Calculator interface" (not useful)
- "Concept illustration" (use mermaid/table)

✓ ALSO MANDATORY: Include 2-3 ```mermaid flowcharts for algorithms/workflows/processes

===========  WRITING STYLE REQUIREMENTS  ===========
✓ Storytelling hooks that paint visual scenarios
✓ Conversational tone ("Here's the thing...", "Think of it this way...")
✓ Concrete examples over abstract concepts
✓ Strategic use of formatting (bold, bullets, tables)
✓ Smooth transitions between Bloom's levels
✓ Make learning exciting through discovery, not pressure
✓ Stealth preparation through strategic content organization

🔴 1. IMAGES: Use strategic judgment - include 0-3 images based on topic
     → Ask: "What investigations would a clinician NEED to see to diagnose/manage this?"
     → Format: **Figure N: [Image: Investigation + specific visible diagnostic features]**
     → Example: **Figure 1: [Image: 12-lead ECG showing atrial fibrillation with absent P waves and irregularly irregular RR intervals]**
     → Topics with key investigations (ECG, X-ray, histology, endoscopy) → Include them (1-3 images)
     → Topics that are clinical/theoretical without essential images → Skip images (0 images)
     → Quality over quantity - only truly essential diagnostic images
     → NO calculators, NO generic charts, NO concept diagrams
     → YES actual medical investigations showing pathology

🔴 2. FLOWCHARTS: Include 2-3 ```mermaid code blocks (MANDATORY)
     → Use for: diagnostic algorithms, treatment pathways, decision trees
     → NOT images - actual mermaid code blocks

🔴 3. TABLES: Include tables in EVERY section (MANDATORY)
     → Classifications, differentials, dosing, thresholds, criteria

🔴 4. CHAPTERS: Weave chapter names NATURALLY INTO SENTENCES throughout ALL sections
     ✅ DO: "Heart failure (see Heart failure pharmacological therapy) management involves..."
     ❌ DON'T: Separate "Related Chapters:" lists

🔴 5. HIGH YIELD SUMMARY: MUST end with "### High Yield Summary" with all subsections

🔴 6. WORD COUNT: 1000-1200 words total

🔴 7. NO PAGE NUMBERS in headers - use topic-specific memorable titles

===========  OUTPUT FORMAT  ===========
Markdown only. No meta commentary. No apologies. No "here's the lesson".
Start directly with first section header."""

                # Build chapter prompts up-front so we can fire all in parallel
                chapter_specs = []  # (chapter_name, nice_refs, chapter_prompt)
                for chapter in chapter_list:
                    chapter_name = chapter.get('name') if isinstance(chapter, dict) else chapter
                    nice_refs = chapter.get('nice_refs', []) if isinstance(chapter, dict) else []

                    chapter_prompt = f"""====================  CHAPTER RAPID REVISION GENERATOR  ====================
- Course   : {course}
- Subject  : {subject}
- Topic    : {topic_name}
- Chapter  : {chapter_name}
- Target   : 1-2 pages | 300-500 words | RAPID REVISION FORMAT
- Audience : {audience_desc} preparing for rapid review
==========================================================================

🎯 PURPOSE: Create a concise, high-density rapid revision note for this chapter.
Think of this as a "cheat sheet" or "quick reference card" for rapid review before exams.

🔴 MANDATORY STRUCTURE:

### {chapter_name}

**Quick Overview** (2-3 sentences max)
Brief context and why this chapter matters clinically/practically.

**Core Facts & Concepts**
• Key definitions with specific thresholds/values
• Essential classifications (use table if >3 items)
• Critical formulas, equations, or calculations
• Must-know numbers, percentages, timeframes

**Problem-Solving Approach**
• Step-by-step clinical/analytical framework (numbered list)
• Decision points with specific criteria
• "When to..." and "How to..." guidelines
• Red flags or warning signs

**Analysis Framework**
• Differential diagnosis approach OR comparison framework
• Key discriminating features (table format)
• Quick decision rules or scoring systems

**Visual Aid** (REQUIRED: {chapter_image_reqs['min_images']}-{chapter_image_reqs['max_images']} visual elements):
{chapter_image_reqs['guidance']}
- ```mermaid flowchart for algorithm/workflow (if chapter has process/algorithm)
  IMPORTANT: Use simple mermaid syntax only. Valid examples:
  ```mermaid
  flowchart TD
      A[Start] --> B{{Decision}}
      B -->|Yes| C[Action 1]
      B -->|No| D[Action 2]
  ```
  Common syntax rules: Use TD for top-down, LR for left-right. Node shapes: [] for rectangles, {{}} for diamonds, () for rounded.
  Keep it simple - max 6-8 nodes. Avoid special characters in labels except basic punctuation.
- TABLE for classifications/differentials/comparisons (if chapter has categories)
- **Figure: [Image: specific modality + exact visible finding]** (for key diagnostic/clinical visuals)
  Examples: "ECG showing specific pattern", "X-ray showing characteristic feature", "Histology showing specific cells"

**Key Points Summary** (MANDATORY - End section)
✓ Top 5-7 bullet points capturing absolute essentials
✓ Include specific numbers, ranges, thresholds
✓ Mnemonics if helpful (≤10 words with context)
✓ "Can't miss" clinical pearls or concepts
✓ Common pitfalls to avoid

==========================================================================

🔴 STYLE REQUIREMENTS:
✓ Bullet points and tables - NOT paragraphs
✓ Specific numbers, not vague terms ("60%" not "most")
✓ Action-oriented language ("Measure X when...", "Consider Y if...")
✓ NO fluff - every word must add value
✓ Clinical pearls and memory aids embedded naturally
✓ Professional but concise - assume advanced learner
✓ Use emojis for visual clarity (🎯 key points, 🚩 red flags, 💊 drugs, 📊 numbers)
✓ DOUBLE newlines between sections for proper spacing
✓ Bold important terms and thresholds

🔴 LENGTH: 300-500 words total (strict limit for rapid review)
🔴 FORMAT: Markdown only. Start directly with "### {chapter_name}"
🔴 MUST END WITH: "**Key Points Summary**" section
"""
                    chapter_specs.append((chapter_name, nice_refs, chapter_prompt))

                # ---- Parallel generation: topic lesson + all chapters at once ----
                logger.info(f"🚀 Generating topic lesson + {len(chapter_specs)} chapter(s) in parallel for '{topic_name}'...")
                max_workers = 1 + len(chapter_specs)

                with _TP(max_workers=max_workers) as pool:
                    topic_future = pool.submit(
                        _gen_and_integrate, client, lesson_prompt, 8000, subject, topic_name
                    )
                    ch_futures = [
                        (ch_name, nice_refs,
                         pool.submit(_gen_and_integrate, client, ch_prompt, 2000, subject, ch_name))
                        for ch_name, nice_refs, ch_prompt in chapter_specs
                    ]

                    topic_lesson = topic_future.result()
                    chapter_lessons = []
                    for ch_name, nice_refs, fut in ch_futures:
                        chapter_lessons.append({
                            'name': ch_name,
                            'nice_refs': nice_refs,
                            'lesson': fut.result()
                        })

                return {
                    'topic': topic_name,
                    'high_yield': high_yield,
                    'topic_lesson': topic_lesson,
                    'chapters': chapter_lessons,
                    'subject': subject
                }

            # Run all topics for this subject in parallel
            logger.info(f"🚀 Generating {len(structure)} topic(s) in parallel for subject '{subject}'...")
            if len(structure) == 1:
                all_lessons.append(_process_topic(structure[0]))
            else:
                with _TP(max_workers=len(structure)) as topic_pool:
                    for result in topic_pool.map(_process_topic, structure):
                        all_lessons.append(result)

        return jsonify({
            'course': course,
            'subject': subject if len(subjects_to_process) == 1 else 'Multiple Subjects',
            'lessons': all_lessons
        })

    except Exception as e:
        logger.error(f"Lesson generation error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Error: {str(e)}'}), 500


@app.route('/api/analyze-course', methods=['POST'])
def analyze_course():
    """
    NEW MODULAR ENDPOINT: Comprehensive course analysis using all three modules

    Uses:
    1. generate_course_structure() - Get hierarchical structure
    2. analyze_exam_format() - Determine question/exam characteristics
    3. design_lesson_flow() - Plan optimal lesson structure

    This provides a complete analysis for both QBank and Lesson generation.
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({'error': 'ANTHROPIC_API_KEY not set'}), 500

    data = request.json
    course = data.get('course')
    analysis_type = data.get('type', 'full')  # 'structure', 'exam', 'lesson', 'full'

    if not course:
        return jsonify({'error': 'Course is required'}), 400

    try:
        result = {'course': course}

        # MODULE 1: Generate course structure (always needed)
        logger.info(f"📚 Running MODULE 1: Course Structure Generation")
        structure = generate_course_structure(course)
        result['structure'] = structure

        if analysis_type in ['exam', 'full']:
            # MODULE 2: Analyze exam format (for QBank)
            logger.info(f"📝 Running MODULE 2: Exam Format Analysis")
            exam_format = analyze_exam_format(course, structure)
            result['exam_format'] = exam_format

        if analysis_type in ['lesson', 'full']:
            # MODULE 3: Design lesson flow (for Lessons)
            # Use first subject/topic as example
            if structure['subjects'] and structure['subjects'][0]['topics']:
                first_subject = structure['subjects'][0]
                first_topic = first_subject['topics'][0]
                logger.info(f"📖 Running MODULE 3: Lesson Flow Design")

                lesson_flow = design_lesson_flow(
                    course,
                    first_subject['name'],
                    first_topic['name'],
                    first_topic.get('chapters', []),
                    structure
                )
                result['lesson_flow_template'] = lesson_flow

        logger.info(f"✓ Complete course analysis generated")
        return jsonify(result)

    except Exception as e:
        logger.error(f"Course analysis error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Error: {str(e)}'}), 500


@app.route('/api/generate-subjects', methods=['POST'])
def generate_subjects():
    """
    Generate comprehensive course structure using the new modular architecture.

    Now uses:
    - MODULE 1: generate_course_structure() for 10-15 subjects
    - MODULE 2: analyze_exam_format() for question characteristics
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({'error': 'ANTHROPIC_API_KEY not set'}), 500

    data = request.json
    course = data.get('course')

    if not course:
        return jsonify({'error': 'Course is required'}), 400

    try:
        logger.info(f"📚 Generating comprehensive structure for: {course}")

        # Use MODULE 1: Generate course structure (10-15 subjects minimum)
        structure = generate_course_structure(course)

        # Use MODULE 2: Analyze exam format
        logger.info(f"📝 Analyzing exam format for: {course}")
        exam_format_analysis = analyze_exam_format(course, structure)

        # Combine into response format expected by frontend
        response = {
            'Course': course,
            'exam_format': exam_format_analysis,  # Include FULL exam format analysis (not just question_format)
            'blooms_distribution': exam_format_analysis.get('blooms_distribution', {}),
            'content_characteristics': {
                'domain': structure.get('exam_type', 'general'),
                'domain_description': structure.get('domain_characteristics', ''),
                'key_features': exam_format_analysis.get('domain_characteristics', {}).get('key_features', [])
            },
            'question_requirements': {
                'format_notes': f"Standard format for {structure.get('exam_type', 'general')} exams",
                'visual_elements': exam_format_analysis.get('domain_characteristics', {}).get('visual_elements', 'medium')
            },
            'subjects': structure.get('subjects', [])
        }

        num_subjects = len(response['subjects'])
        logger.info(f"✓ Generated comprehensive structure:")
        logger.info(f"  - Subjects: {num_subjects}")
        logger.info(f"  - Exam Type: {structure.get('exam_type', 'unknown')}")

        # Debug: Log subject names being returned
        subject_names = [s.get('name', 'UNNAMED') for s in response['subjects'][:5]]
        logger.info(f"  - First 5 subjects: {subject_names}")

        # DEBUG: Save structure to file for testing
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_filename = f"debug_structure_{course.replace(' ', '_')}_{timestamp}.json"
        debug_filepath = os.path.join(os.path.dirname(__file__), debug_filename)

        try:
            with open(debug_filepath, 'w', encoding='utf-8') as f:
                json.dump(response, f, indent=2, ensure_ascii=False)
            logger.info(f"  - 💾 Saved structure to: {debug_filename}")
            logger.info(f"  - 💾 File contains {len(response['subjects'])} subjects")

            # Also log the size of the JSON string
            json_str = json.dumps(response, ensure_ascii=False)
            logger.info(f"  - 💾 JSON string size: {len(json_str)} characters")
        except Exception as e:
            logger.error(f"  - ❌ Failed to save debug file: {e}")

        # Debug: Log response size
        import sys
        response_json = jsonify(response)
        response_data = response_json.get_json()
        logger.info(f"  - Response contains {len(response_data.get('subjects', []))} subjects")
        logger.info(f"  - Total response keys: {list(response_data.keys())}")

        if num_subjects < 8:
            logger.warning(f"⚠️ Only {num_subjects} subjects generated - this may be insufficient")

        return response_json

    except Exception as e:
        logger.error(f"Subject generation error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Error: {str(e)}'}), 500


@app.route('/api/debug-structure/<course>', methods=['GET'])
def debug_structure(course):
    """Debug endpoint to check response structure"""
    try:
        structure = generate_course_structure(course)
        response = {
            'debug_info': {
                'backend_subject_count': len(structure.get('subjects', [])),
                'backend_subject_names': [s.get('name') for s in structure.get('subjects', [])[:10]],
                'has_topics': all(s.get('topics') for s in structure.get('subjects', [])),
                'response_type': type(structure).__name__
            },
            'structure': structure
        }
        return jsonify(response)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/refine-structure', methods=['POST'])
def refine_structure():
    """Refine course structure based on user chat input and optional reference documents."""
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({'error': 'ANTHROPIC_API_KEY not set'}), 500

    try:
        course = request.form.get('course', '')
        user_message = request.form.get('message', '')
        current_structure_json = request.form.get('current_structure', '{}')
        current_structure = json.loads(current_structure_json)

        # Handle reference document if uploaded
        ref_doc_content = ""
        if 'reference_doc' in request.files:
            ref_doc = request.files['reference_doc']
            if ref_doc.filename:
                logger.info(f"Processing reference document: {ref_doc.filename}")

                # Read file content based on type
                filename = ref_doc.filename.lower()
                if filename.endswith('.txt'):
                    ref_doc_content = ref_doc.read().decode('utf-8', errors='ignore')
                elif filename.endswith('.json'):
                    ref_doc_content = ref_doc.read().decode('utf-8', errors='ignore')
                elif filename.endswith('.pdf'):
                    # For PDF, use basic text extraction or just note it's a PDF
                    ref_doc_content = f"[PDF document uploaded: {ref_doc.filename}. User expects structure aligned with this curriculum.]"
                else:
                    ref_doc_content = ref_doc.read().decode('utf-8', errors='ignore')[:5000]  # Limit size

        # Build prompt for Claude to understand the request and refine structure
        refine_prompt = f"""You are helping to refine a course structure for "{course}".

CURRENT STRUCTURE:
{json.dumps(current_structure, indent=2)}

USER REQUEST:
{user_message}

{f'''REFERENCE DOCUMENT CONTENT:
{ref_doc_content[:3000]}
''' if ref_doc_content else ''}

Your task:
1. Understand what the user wants to change (add subjects/topics, remove items, modify exam format, etc.)
2. If a reference document is provided, extract relevant subjects/topics from it
3. Modify the structure accordingly
4. Respond with:
   - A friendly message explaining what you changed
   - The updated structure in the same JSON format

Output format:
{{
  "response": "I've added the Pharmacology subject with 5 topics as requested...",
  "updated_structure": {{
    "Course": "{course}",
    "exam_format": {{ ... }},
    "subjects": [ ... ]
  }},
  "modified": true
}}

If no changes are needed (e.g., user just asking a question), set "modified": false and don't include "updated_structure".

IMPORTANT: Maintain the exact JSON structure format with "Course", "exam_format", and "subjects" fields.
Output ONLY the JSON, no additional text.
"""

        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=4000,
            temperature=0.7,
            messages=[{
                "role": "user",
                "content": refine_prompt
            }]
        )

        response_text = message.content[0].text.strip()

        # Extract JSON from response
        import re
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            response_text = json_match.group(0)

        result = json.loads(response_text)

        logger.info(f"Structure refinement: modified={result.get('modified', False)}")

        return jsonify(result)

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in refine_structure: {e}")
        return jsonify({
            'response': "I understood your request, but encountered an error updating the structure. Please try rephrasing.",
            'modified': False
        })
    except Exception as e:
        logger.error(f"Error in refine_structure: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'response': f"Error processing request: {str(e)}",
            'modified': False
        }), 500


# ============================================================================
# COUNCIL OF MODELS VALIDATION SYSTEM
# ============================================================================

def get_batch_validator_prompt(content_type, domain="medical education"):
    """
    Generate domain-agnostic batch validator prompt — evaluates all items at once.
    Returns a JSON array, one entry per item.
    """
    if content_type == 'lesson':
        return f"""You are a senior {domain} content validation and learning design agent.

You will receive multiple lesson sections numbered SECTION 1, SECTION 2, etc.
Each section may contain text, tables, flowcharts (Mermaid), and embedded images.
Evaluate ALL content types — text accuracy, image relevance, table correctness, and flowchart logic.

For EACH section evaluate:
1. Factual correctness (text, tables, image captions)
2. Alignment with current standard {domain} understanding
3. Internal logical consistency
4. Missing critical contraindications or exceptions
5. Safety implications
6. Conceptual clarity and learning flow
7. Over-simplification that may mislead learners
8. LEARNING GAPS — major concepts a learner would need but are absent
9. Missing prerequisites not explained before being used
10. Missing high-yield exam/clinical pearls for this topic
11. Missing common pitfalls or misconceptions learners typically encounter
12. Image/asset relevance — if an image is embedded, does it match and support the text?
13. Missing memory aids (mnemonics, frameworks) where they would significantly help retention

Do NOT attempt adversarial breaking.
Do NOT rewrite unless needed to show a correction.

Scoring guidance:
• 9–10 → accurate, complete, and pedagogically sound
• 7–8 → minor gaps or refinements needed
• ≤6 → material factual error or significant learning gap

If any major_error OR significant learning gap exists → needs_revision = true

Return a JSON ARRAY — one object per section — with this structure:
[
  {{
    "section_number": 1,
    "section_title": "<title of the section>",
    "overall_accuracy_score": <number 0-10>,
    "needs_revision": <boolean>,
    "factual_errors": [<list of errors, empty if none>],
    "missing_critical_info": [<list, empty if none>],
    "safety_concerns": [<list, empty if none>],
    "clarity_issues": [<list, empty if none>],
    "learning_gaps": [<list of major missing concepts a learner needs>],
    "missing_high_yield": [<list of missing high-yield points or pearls>],
    "missing_pitfalls": [<list of common misconceptions/traps not addressed>],
    "asset_issues": [<list of image/table/flowchart problems, empty if none>],
    "recommendations": [<list, empty if none>],
    "summary": "<1-2 sentence summary>"
  }},
  ...
]

Output ONLY the JSON array. No preamble, no trailing text."""

    elif content_type == 'qbank':
        return f"""You are a senior {domain} exam item validation agent.

You will receive multiple questions numbered Q1, Q2, etc.

For EACH question independently verify:
1. The marked correct answer is truly correct
2. All distractors are clearly incorrect
3. The explanation logically proves the correct answer
4. The vignette contains sufficient data to reach the answer
5. No factual inaccuracies
6. Lab values and details are realistic
7. The question tests the stated learning objective

Reason through each case independently before judging it.
Do NOT attempt adversarial ambiguity testing.

Scoring per question:
• ≥8 AND correct_answer_verified = true → acceptable
• Any factual_error OR incorrect answer → needs_revision = true

Return a JSON ARRAY — one object per question — with this structure:
[
  {{
    "question_number": 1,
    "question_preview": "<first 80 chars of the question stem>",
    "overall_accuracy_score": <number 0-10>,
    "correct_answer_verified": <boolean>,
    "needs_revision": <boolean>,
    "factual_errors": [<list, empty if none>],
    "distractor_issues": [<list, empty if none>],
    "vignette_issues": [<list, empty if none>],
    "explanation_issues": [<list, empty if none>],
    "recommendations": [<list, empty if none>],
    "summary": "<1-2 sentence summary>"
  }},
  ...
]

Output ONLY the JSON array. No preamble, no trailing text."""


def get_batch_adversarial_prompt(content_type, domain="medical education"):
    """
    Generate domain-agnostic batch adversarial review prompt — reviews all items at once.
    Returns a JSON array, one entry per item.
    """
    if content_type == 'lesson':
        return f"""You are an adversarial {domain} content and learning design reviewer.

You will receive multiple lesson sections numbered SECTION 1, SECTION 2, etc.
Each section may contain text, tables, flowcharts, and embedded images.

For EACH section, aggressively identify weaknesses across:
• Factual inaccuracies or outdated guidance
• Overgeneralizations or dangerous simplifications
• Missing contraindications or exceptions
• Internal contradictions
• Cognitive overload or unclear learning flow
• Potential misinterpretation by a learner
• Images/tables/flowcharts that are misleading, irrelevant, or inconsistent with the text
• Concepts presented without sufficient context for a learner to understand them
• Critical learning steps that a student would fail at due to a gap in this content

Assume the content may be flawed and the learner may be harmed by acting on it.

Scoring per section:
0 = unbreakable, pedagogically sound
10 = fundamentally unsafe, misleading, or a significant learning failure

Return a JSON ARRAY — one object per section — with this structure:
[
  {{
    "section_number": 1,
    "adversarial_score": <number 0-10>,
    "breakability_rating": "<unbreakable|minor issues|moderate issues|severely flawed>",
    "identified_weaknesses": [<list, empty if none>],
    "ambiguities": [<list, empty if none>],
    "overgeneralizations": [<list, empty if none>],
    "logical_gaps": [<list, empty if none>],
    "safety_risks": [<list, empty if none>],
    "learning_traps": [<list of ways a learner could be misled or left with wrong mental model>],
    "asset_issues": [<list of image/table/flowchart concerns>],
    "recommendations": [<list, empty if none>],
    "summary": "<1-2 sentence summary>"
  }},
  ...
]

Output ONLY the JSON array. No preamble, no trailing text."""

    elif content_type == 'qbank':
        return f"""You are an adversarial {domain} exam item reviewer.

You will receive multiple questions numbered Q1, Q2, etc.

For EACH question, aggressively test for:
1. More than one defensible correct answer
2. Missing critical data in vignette
3. Ambiguous phrasing
4. Lab values inconsistent with diagnosis
5. Distractors that are not truly incorrect
6. Explanation that does not logically prove the answer
7. Clues that make the question trivial
8. Unrealistic scenario
9. Misalignment between learning objective and tested concept

If you can construct a reasonable argument for an alternative answer, you must report it.

Scoring per question:
0 = airtight
10 = easily broken

Return a JSON ARRAY — one object per question — with this structure:
[
  {{
    "question_number": 1,
    "adversarial_score": <number 0-10>,
    "breakability_rating": "<airtight|minor flaws|moderate flaws|easily broken>",
    "alternative_answers": [<list, empty if none>],
    "ambiguities": [<list, empty if none>],
    "distractor_defenses": [<list, empty if none>],
    "explanation_contradictions": [<list, empty if none>],
    "triviality_clues": [<list, empty if none>],
    "recommendations": [<list, empty if none>],
    "summary": "<1-2 sentence summary>"
  }},
  ...
]

Output ONLY the JSON array. No preamble, no trailing text."""


# Keep old single-item prompts for reference (unused)
def get_validator_prompt(content_type, domain="medical education"):
    return get_batch_validator_prompt(content_type, domain)


def get_adversarial_prompt(content_type, domain="medical education"):
    return get_batch_adversarial_prompt(content_type, domain)


def _image_available(image_url):
    """Return True if image_url points to an accessible file or a valid http URL."""
    if not image_url:
        return False
    if image_url.startswith('http'):
        return True  # external URLs assumed reachable; we won't make an HTTP call here
    # local path like /static/tmpXXXX.png
    local = image_url.lstrip('/')
    return os.path.isfile(local)


_MD_IMG_RE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
_HTML_IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)


def _extract_image_urls_from_lesson(text):
    """
    Parse markdown/HTML lesson content and return a list of (url, alt_text) tuples
    for all embedded images, in order of appearance.
    """
    results = []
    for alt, url in _MD_IMG_RE.findall(text or ''):
        results.append((url.strip(), alt.strip()))
    for url in _HTML_IMG_RE.findall(text or ''):
        results.append((url.strip(), ''))
    return results


def _sniff_media_type(raw_bytes):
    """Detect actual image format from magic bytes — ignores file extension."""
    if raw_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if raw_bytes[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if raw_bytes[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if raw_bytes[:4] == b'RIFF' and raw_bytes[8:12] == b'WEBP':
        return 'image/webp'
    return 'image/jpeg'  # safe fallback


def _load_image_as_base64(image_url):
    """
    Load an image from a local path or URL and return (base64_data, media_type).
    Media type is detected from actual file bytes, not the extension.
    Returns (None, None) on failure.
    """
    import base64 as _b64
    try:
        if image_url.startswith('http'):
            import requests as _req
            resp = _req.get(image_url, timeout=10)
            if resp.status_code == 200:
                raw = resp.content
                data = _b64.b64encode(raw).decode('utf-8')
                media_type = _sniff_media_type(raw)
                return data, media_type
        else:
            local = image_url.lstrip('/')
            if os.path.isfile(local):
                with open(local, 'rb') as f:
                    raw = f.read()
                data = _b64.b64encode(raw).decode('utf-8')
                media_type = _sniff_media_type(raw)
                return data, media_type
    except Exception as e:
        logger.warning(f"Could not load image {image_url}: {e}")
    return None, None


_IMAGE_REF_RE = re.compile(
    r'shown\s+(?:below|above|here)'
    r'|in\s+the\s+(?:image|figure|photo|picture|scan|x-?ray|ct|mri)'
    r'|as\s+seen\s+in'
    r'|refer\s+to\s+the\s+(?:image|figure)'
    r'|\[image\]'
    r'|based\s+on\s+the\s+(?:image|figure|scan|x-?ray|photograph)'
    r'|(?:chest|abdominal|pelvic|brain|head)\s+(?:x-?ray|ct|mri)\s+shown',
    re.IGNORECASE
)


def _make_structural_failure(index, question_text, reason):
    """Return a pre-scored result for a question that cannot be content-validated."""
    return {
        "index": index,
        "structural_failure": True,
        "validator": {
            "question_number": index,
            "question_preview": question_text[:80],
            "overall_accuracy_score": 2,
            "correct_answer_verified": False,
            "needs_revision": True,
            "factual_errors": [reason],
            "distractor_issues": [],
            "vignette_issues": [reason],
            "explanation_issues": [],
            "recommendations": ["Fix the structural issue before content review"],
            "summary": f"Structural failure: {reason}. Content review skipped."
        },
        "adversarial": {
            "question_number": index,
            "adversarial_score": 0,
            "breakability_rating": "N/A — structural failure, adversarial review skipped",
            "alternative_answers": [],
            "ambiguities": [],
            "distractor_defenses": [],
            "explanation_contradictions": [],
            "triviality_clues": [],
            "recommendations": [],
            "summary": "Adversarial review skipped — structural failure detected by Validator."
        },
        "overall_assessment": {
            "status": "❌ Structural Failure",
            "quality_score": 1.0,
            "validator_score": 2,
            "adversarial_score": 0,
            "needs_revision": True,
            "recommendation": f"Cannot review content: {reason}"
        }
    }


def _extract_json_array(text, expected_count):
    """
    Robustly extract a JSON array of results from a model response.
    Uses json.JSONDecoder.raw_decode() to find the first complete JSON value
    starting at the first '[' or '{', ignoring surrounding markdown/text.
    """
    if not text:
        return []

    decoder = json.JSONDecoder()

    def _try_parse(s, start_char):
        """Find the first occurrence of start_char and raw_decode from there."""
        idx = s.find(start_char)
        while idx != -1:
            try:
                parsed, _ = decoder.raw_decode(s, idx)
                return parsed
            except json.JSONDecodeError:
                idx = s.find(start_char, idx + 1)
        return None

    def _normalise(parsed):
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for key in ('sections', 'items', 'questions', 'results', 'data'):
                if isinstance(parsed.get(key), list):
                    return parsed[key]
            return [parsed]
        return None

    # 1. Try to find a JSON array first (most common case)
    result = _normalise(_try_parse(text, '['))
    if result is not None:
        return result

    # 2. Fall back to finding a JSON object
    result = _normalise(_try_parse(text, '{'))
    if result is not None:
        return result

    logger.warning(f"Could not parse JSON from model response (expected {expected_count} items). "
                   f"Response preview: {text[:300]}")
    return []


@app.route('/api/validate-content', methods=['POST'])
def validate_content():
    """
    Council of Models validation: Sequential batch Validator → Adversarial Reviewer
    Accepts an array of items and returns per-item results.
    Image-based questions with missing images are pre-screened as structural failures
    and bypass the adversarial review entirely.
    """
    try:
        data = request.json
        content_type = data.get('content_type')
        items = data.get('items', [])
        domain = data.get('domain', 'medical education')
        course = data.get('course', 'Unknown')

        if not items:
            return jsonify({'error': 'No items provided'}), 400

        logger.info(f"🔍 Council of Models batch validation: {len(items)} {content_type}(s)")
        logger.info(f"   Domain: {domain}, Course: {course}")

        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

        import re as _re

        # ---- Pre-screen QBank for structural failures (missing images) ----
        pre_scored = {}   # original_index → result dict
        valid_indices = list(range(len(items)))  # indices to actually send to models

        if content_type == 'qbank':
            valid_indices = []
            for i, q in enumerate(items):
                question_text = q.get('question', '')
                image_url = q.get('image_url', '')
                needs_image = bool(image_url) or bool(_IMAGE_REF_RE.search(question_text))

                if needs_image and image_url and not _image_available(image_url):
                    reason = "Image file referenced in question is missing or unavailable"
                    pre_scored[i] = _make_structural_failure(i + 1, question_text, reason)
                    logger.info(f"   ⚠️  Q{i+1}: structural failure — {reason}")
                elif needs_image and not image_url:
                    reason = "Question references an image but no image is attached"
                    pre_scored[i] = _make_structural_failure(i + 1, question_text, reason)
                    logger.info(f"   ⚠️  Q{i+1}: structural failure — {reason}")
                else:
                    valid_indices.append(i)

        valid_items = [items[i] for i in valid_indices]

        # ---- Format valid items as content blocks (multimodal for both types) ----
        # section_block_ranges[i] = (start_block_idx, end_block_idx) for valid_items[i]
        section_block_ranges = []

        if content_type == 'lesson':
            lesson_blocks = []
            images_embedded = 0

            for pos, lesson in enumerate(valid_items, start=1):
                orig_idx = valid_indices[pos - 1]
                block_start = len(lesson_blocks)
                title = lesson.get('topic', f'Section {orig_idx + 1}')
                body = lesson.get('topic_lesson', '')
                if isinstance(body, dict):
                    body = json.dumps(body, indent=2)
                body_str = str(body)

                # Collect all image URLs from topic body + all chapters
                all_texts = [body_str]
                chapters_text = ""
                if lesson.get('chapters'):
                    for ch in lesson['chapters']:
                        ch_title = ch.get('chapter', '')
                        ch_body = ch.get('lesson', '') or ''
                        chapters_text += f"\n  Chapter: {ch_title}\n  {ch_body[:1500]}\n"
                        all_texts.append(ch_body)

                section_header = f"\n\n--- SECTION {pos}: {title} ---\n{body_str[:8000]}{chapters_text}"
                lesson_blocks.append({"type": "text", "text": section_header})

                # Extract and embed all images found in this section
                seen_urls = set()
                for text_chunk in all_texts:
                    for url, alt in _extract_image_urls_from_lesson(text_chunk):
                        if url in seen_urls:
                            continue
                        seen_urls.add(url)
                        if not _image_available(url):
                            lesson_blocks.append({"type": "text",
                                "text": f"[IMAGE MISSING: '{alt or url}' — referenced in section but file not found]\n"})
                            continue
                        img_data, media_type = _load_image_as_base64(url)
                        if img_data:
                            lesson_blocks.append({"type": "text",
                                "text": f"[IMAGE: '{alt or os.path.basename(url)}' embedded below]\n"})
                            lesson_blocks.append({
                                "type": "image",
                                "source": {"type": "base64", "media_type": media_type, "data": img_data}
                            })
                            images_embedded += 1
                        else:
                            lesson_blocks.append({"type": "text",
                                "text": f"[IMAGE LOAD FAILED: '{alt or url}']\n"})

                section_block_ranges.append((block_start, len(lesson_blocks)))

            logger.info(f"   📸 {images_embedded} lesson image(s) embedded across {len(valid_items)} section(s)")
            content_payload = lesson_blocks

        elif content_type == 'qbank':
            q_blocks = []
            images_embedded = 0
            for pos, q in enumerate(valid_items, start=1):
                block_start = len(q_blocks)
                opts = '\n'.join([f"  {chr(65+j)}. {opt}" for j, opt in enumerate(q.get('options', []))])
                image_url = q.get('image_url', '')
                has_image = image_url and _image_available(image_url)

                image_marker = "[IMAGE FOR THIS QUESTION IS EMBEDDED BELOW — evaluate it as part of the question]\n" if has_image else ""
                q_text = f"""
--- Q{pos} ---
{image_marker}Question: {q.get('question', '')}
Options:
{opts}
Correct Answer: {q.get('correct_option', '')}
Explanation: {q.get('explanation', '')}
Tags: {', '.join(q.get('tags', []))}
"""
                q_blocks.append({"type": "text", "text": q_text})

                if has_image:
                    img_data, media_type = _load_image_as_base64(image_url)
                    if img_data:
                        q_blocks.append({
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": img_data}
                        })
                        images_embedded += 1
                        logger.info(f"   🖼️  Q{pos}: embedded image ({media_type})")
                    else:
                        q_blocks.append({"type": "text", "text": "[IMAGE LOAD FAILED — treat question as having a missing image]\n"})
                        logger.warning(f"   ⚠️  Q{pos}: image present but failed to load")

                section_block_ranges.append((block_start, len(q_blocks)))

            logger.info(f"   📸 {images_embedded}/{len(valid_items)} questions have embedded images")
            content_payload = q_blocks
        else:
            return jsonify({'error': 'Invalid content_type. Must be "lesson" or "qbank"'}), 400

        validator_results = []
        adversarial_results = []

        # Lessons: batch 2 — smaller batches finish faster, all run fully in parallel.
        # QBank: batch 10 — still parallelised, keeps response well within token limits.
        BATCH_SIZE = 2 if content_type == 'lesson' else 10

        if valid_items:
            # Helper to build user message content (string or list)
            def _make_user_content(prompt_text, payload):
                if isinstance(payload, list):
                    return [{"type": "text", "text": f"{prompt_text}\n\nContent to validate:\n"}] + payload
                else:
                    return f"{prompt_text}\n\nContent to validate:\n{payload}"

            def _call_agent(prompt, payload, temperature, label):
                response = client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=8000,
                    temperature=temperature,
                    messages=[{"role": "user", "content": _make_user_content(prompt, payload)}]
                )
                return response.content[0].text.strip()

            validator_prompt = get_batch_validator_prompt(content_type, domain)
            adversarial_prompt = get_batch_adversarial_prompt(content_type, domain)

            # Pre-compute all batch specs
            batch_specs = []
            for b_start in range(0, len(valid_items), BATCH_SIZE):
                b_end = min(b_start + BATCH_SIZE, len(valid_items))
                batch_count = b_end - b_start
                first_block = section_block_ranges[b_start][0]
                last_block  = section_block_ranges[b_end - 1][1]
                batch_payload = content_payload[first_block:last_block]
                batch_specs.append((b_start, b_end, batch_count, batch_payload))

            num_batches = len(batch_specs)
            logger.info(f"   🚀 Running {num_batches} validator + {num_batches} adversarial batches in parallel "
                        f"({len(valid_items)} item(s), batch size {BATCH_SIZE})...")

            from concurrent.futures import ThreadPoolExecutor, as_completed

            # Slot results by position so order is preserved regardless of completion order
            v_slots = [None] * len(valid_items)
            a_slots = [None] * len(valid_items)

            def _run_validator_batch(b_start, b_end, batch_count, payload):
                batch_num = b_start // BATCH_SIZE + 1
                logger.info(f"      [V{batch_num}] Validator sections {b_start+1}–{b_end}...")
                text = _call_agent(validator_prompt, payload, 0.3, 'validator')
                results = _extract_json_array(text, batch_count)[:batch_count]
                logger.info(f"      [V{batch_num}] → Parsed {len(results)}/{batch_count}")
                return 'validator', b_start, b_end, results

            def _run_adversarial_batch(b_start, b_end, batch_count, payload):
                batch_num = b_start // BATCH_SIZE + 1
                logger.info(f"      [A{batch_num}] Adversarial sections {b_start+1}–{b_end}...")
                text = _call_agent(adversarial_prompt, payload, 0.5, 'adversarial')
                results = _extract_json_array(text, batch_count)[:batch_count]
                logger.info(f"      [A{batch_num}] → Parsed {len(results)}/{batch_count}")
                return 'adversarial', b_start, b_end, results

            with ThreadPoolExecutor(max_workers=num_batches * 2) as executor:
                futures = []
                for b_start, b_end, batch_count, payload in batch_specs:
                    futures.append(executor.submit(_run_validator_batch,   b_start, b_end, batch_count, payload))
                    futures.append(executor.submit(_run_adversarial_batch, b_start, b_end, batch_count, payload))

                for future in as_completed(futures):
                    try:
                        role, b_start, b_end, results = future.result()
                        slots = v_slots if role == 'validator' else a_slots
                        for j, r in enumerate(results):
                            if b_start + j < len(slots):
                                slots[b_start + j] = r if isinstance(r, dict) else {}
                    except Exception as e:
                        logger.error(f"Batch future error: {e}")

            validator_results  = [r or {} for r in v_slots]
            adversarial_results = [r or {} for r in a_slots]
            logger.info(f"   ✓ All batches done: {len(validator_results)} validator, {len(adversarial_results)} adversarial")

        # ---- Merge results back in original order ----
        merged_items = []
        valid_pos = 0
        for i in range(len(items)):
            if i in pre_scored:
                merged_items.append(pre_scored[i])
            else:
                v = validator_results[valid_pos] if valid_pos < len(validator_results) else {}
                a = adversarial_results[valid_pos] if valid_pos < len(adversarial_results) else {}
                # Guard: ensure v and a are dicts (model may occasionally return strings)
                if not isinstance(v, dict): v = {}
                if not isinstance(a, dict): a = {}
                assessment = generate_overall_assessment(v, a, content_type)
                merged_items.append({
                    "index": i + 1,
                    "validator": v,
                    "adversarial": a,
                    "overall_assessment": assessment
                })
                valid_pos += 1

        # ---- Summary ----
        total = len(merged_items)
        needs_revision_count = sum(1 for item in merged_items if item["overall_assessment"].get("needs_revision"))
        structural_count = sum(1 for item in merged_items if item.get("structural_failure"))
        approved_count = total - needs_revision_count
        avg_quality = round(
            sum(item["overall_assessment"].get("quality_score", 0) for item in merged_items) / total, 2
        ) if total > 0 else 0

        report = {
            "timestamp": datetime.now().isoformat(),
            "content_type": content_type,
            "domain": domain,
            "course": course,
            "items": merged_items,
            "summary": {
                "total": total,
                "approved": approved_count,
                "needs_revision": needs_revision_count,
                "structural_failures": structural_count,
                "avg_quality_score": avg_quality
            }
        }

        logger.info(f"   ✅ Done — {approved_count}/{total} approved, {structural_count} structural failures, avg {avg_quality}")
        return jsonify(report)

    except Exception as e:
        logger.error(f"Error in validate_content: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


def generate_overall_assessment(validator_result, adversarial_result, content_type):
    """Generate a combined assessment from both agents"""

    validator_score = validator_result.get('overall_accuracy_score', 0)
    adversarial_score = adversarial_result.get('adversarial_score', 0)
    needs_revision = validator_result.get('needs_revision', False)

    # Calculate overall quality score (inverse of adversarial score)
    quality_score = (validator_score + (10 - adversarial_score)) / 2

    if quality_score >= 8 and not needs_revision:
        status = "✅ Approved"
        recommendation = "Content is of high quality and safe to use."
    elif quality_score >= 6:
        status = "⚠️ Conditional"
        recommendation = "Content has minor issues. Review recommendations and consider revisions."
    else:
        status = "❌ Needs Revision"
        recommendation = "Content has significant issues and requires revision before use."

    return {
        "status": status,
        "quality_score": round(quality_score, 2),
        "validator_score": validator_score,
        "adversarial_score": adversarial_score,
        "needs_revision": needs_revision,
        "recommendation": recommendation
    }


if __name__ == '__main__':
    app.run(debug=True, port=5001)

"""
QBank Generator - Flask Backend
Generates MCQs for NEET PG and USMLE using OpenRouter
"""

import json
import math
import os
import re
import secrets
import requests
import hashlib
import logging
import concurrent.futures
from pathlib import Path
from datetime import datetime
import threading
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from openai import OpenAI
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

# ── OpenRouter — single unified LLM gateway ───────────────────────────────────
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
or_client = OpenAI(
    api_key=OPENROUTER_API_KEY or 'missing',
    base_url='https://openrouter.ai/api/v1',
)
if not OPENROUTER_API_KEY:
    logger.warning("OPENROUTER_API_KEY not set — all LLM calls will fail")
else:
    logger.info("OpenRouter client initialised")

# Model aliases (override via env vars)
OR_MAIN_MODEL       = os.environ.get('OR_MAIN_MODEL',       'anthropic/claude-sonnet-4-6')
OR_WEB_MODEL        = os.environ.get('OR_WEB_MODEL',        'anthropic/claude-sonnet-4-6')
OR_VALIDATOR_MODEL  = os.environ.get('OR_VALIDATOR_MODEL',  'openai/gpt-5.4')
OR_ADVERSARIAL_MODEL= os.environ.get('OR_ADVERSARIAL_MODEL','openai/gpt-5.4')
OR_IMAGE_MODEL      = os.environ.get('OR_IMAGE_MODEL',      'gpt-image-2')

logger.info(f"Models — main:{OR_MAIN_MODEL}  web:{OR_WEB_MODEL}  "
            f"validator:{OR_VALIDATOR_MODEL}  adversarial:{OR_ADVERSARIAL_MODEL}  "
            f"image:{OR_IMAGE_MODEL}")

# ── Direct OpenAI client — used ONLY for image generation (images API not on OpenRouter) ──
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
openai_image_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
if openai_image_client:
    logger.info(f"OpenAI image client initialised (model: {OR_IMAGE_MODEL})")
else:
    logger.warning("OPENAI_API_KEY not set — OpenAI image generation unavailable; Gemini will be used as fallback")

# ── Google Gemini — kept ONLY for image generation (not available on OpenRouter) ─
# Uses GEMINI_API_KEY (dedicated). GOOGLE_API_KEY is reserved for Custom Search only.
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
gemini_client = None
if GEMINI_API_KEY:
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("Google Gemini API initialised (image generation only)")
    except Exception as e:
        logger.warning(f"Failed to initialise Gemini API: {e}")
else:
    logger.warning("GEMINI_API_KEY not set — AI image generation will be disabled")

# ── Google Custom Search (image search) ──────────────────────────────────────
# Uses GOOGLE_CSE_API_KEY (separate from GEMINI_API_KEY to avoid library conflicts).
# Create a CSE at https://cse.google.com/ — enable Image Search, search the whole web.
GOOGLE_API_KEY = os.environ.get('GOOGLE_CSE_API_KEY')  # dedicated CSE key
GOOGLE_CSE_ID = os.environ.get('GOOGLE_CSE_ID')
if GOOGLE_CSE_ID and GOOGLE_API_KEY:
    logger.info("Google Custom Search (image) enabled")
else:
    logger.info("GOOGLE_CSE_API_KEY/GOOGLE_CSE_ID not set — Google Image Search disabled (optional)")

# ── Image source strategy constants ──────────────────────────────────────────
IMAGE_SOURCE_WIKIMEDIA = 'wikimedia'   # Wikimedia Commons API — histology, gross path, anatomy
IMAGE_SOURCE_OPENNI    = 'openni'      # OpenI NIH API — radiology (CT, X-ray, MRI)
IMAGE_SOURCE_WIKIPEDIA = 'wikipedia'   # Wikipedia lead image — instruments, organisms, named findings
IMAGE_SOURCE_GENERATE  = 'generate'   # Gemini directly — schematics, graphs, ECGs, flow diagrams
IMAGE_SOURCE_GOOGLE    = 'google'      # Google Custom Search — general fallback

# ── Unified LLM helper ────────────────────────────────────────────────────────
def _or_call(prompt, model=None, max_tokens=8000, temperature=0.2, messages=None, timeout=180):
    """Call OpenRouter and return the response text."""
    if messages is None:
        messages = [{"role": "user", "content": prompt}]
    resp = or_client.chat.completions.create(
        model=model or OR_MAIN_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=messages,
        extra_headers={"X-Title": "QBank Generator"},
        timeout=timeout,
    )
    choices = resp.choices or []
    if not choices:
        return ''
    return choices[0].message.content or ''

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

def _call_with_web_search(client_unused, user_prompt, max_tokens=8000, max_rounds=5):
    """Call Perplexity Sonar (web-search capable) via OpenRouter. Returns text response."""
    return _or_call(user_prompt, model=OR_WEB_MODEL, max_tokens=max_tokens, temperature=0.2)


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
   - Tag each topic with "high_yield": true/false based on exam frequency and importance for THIS specific exam.
     High-yield = consistently heavily tested, high question density in real exams (typically 40-60% of topics per subject).

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
                    "high_yield": true,
                    "chapters": []
                }}
            ]
        }}
    ]
}}

⭐ HIGH-YIELD TAGGING (MANDATORY):
   - Set "high_yield": true for topics that are HEAVILY and CONSISTENTLY tested in real {course_name} exams.
   - Use your knowledge of past exam patterns, question banks, and official blueprints.
   - Aim for 40-60% of topics per subject to be high-yield — not all, not too few.
   - Examples for NEET PG: Cardiology (HY), General Surgery (HY), Pharmacology of Antibiotics (HY), Embryology (not HY)
   - Examples for USMLE Step 1: Cell Biology (HY), Cardiac Physiology (HY), Rare Genetic Disorders (not HY)

🔴 IMPORTANT: Generate a COMPLETE structure - minimum 10 subjects for professional exams!

Generate ONLY the JSON, no other text."""

    try:
        web_prompt = (
            f"Using your knowledge of the official syllabus and curriculum for '{course_name}', "
            f"including official exam body guidelines, accreditation documents, and published blueprints, "
            f"produce the complete structure.\n\n"
            + structure_prompt
        )
        response_text = _call_with_web_search(None, web_prompt, max_tokens=8000).strip()

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

            response_text = _or_call(retry_prompt, max_tokens=8000, temperature=0.5).strip()
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
        web_format_prompt = (
            f"Using your knowledge of the official question format and exam specifications for '{course_name}', "
            f"including official exam board guidelines, published blueprints, and candidate handbooks, "
            f"answer the following:\n\n"
            + format_prompt
        )
        response_text = _call_with_web_search(None, web_format_prompt, max_tokens=4000).strip()
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


def fetch_mock_exam_specs(course_name, subjects):
    """
    Fetch official mock exam specs via web search:
    total questions, time, scoring, subject-wise distribution.
    subjects: list of subject names from the course structure.
    """
    logger.info(f"Fetching mock exam specs for: {course_name}")

    subjects_json = json.dumps(subjects[:25])

    prompt = f"""You are an expert on official medical exam blueprints and question patterns.

EXAM: {course_name}
OUR SUBJECT LIST: {subjects_json}

Return EXACTLY this JSON and nothing else:

{{
    "total_questions": <integer — exact total MCQs in one sitting>,
    "time_minutes": <integer — total exam duration in minutes>,
    "num_options": <integer — options per question, e.g. 4 or 5>,
    "negative_marking": "<string — e.g. '-1 for wrong, +4 correct' or 'None'",
    "scoring_note": "<one-line summary of marking scheme>",
    "subject_distribution": {{
        "<use EXACT subject name from our list>": {{
            "questions": <integer>,
            "percentage": <number>,
            "image_pct": <integer — % of THIS subject's questions that are image-based>
        }}
    }},
    "image_questions_total": <integer — REQUIRED, see rules below>,
    "exam_notes": "<one or two sentences on format/pattern>"
}}

CRITICAL RULES:
- Use EXACT subject names from our list above. Skip any subjects with 0 questions.
- The sum of all "questions" values MUST equal total_questions.
- If a subject in our list is not normally tested, omit it.
- If two subjects overlap (e.g., "Internal Medicine" and "Medicine"), merge into the closest match.
- Percentages must sum to 100.
- image_pct per subject: use your knowledge of this exam's subject-specific image question rates.
  NEET PG / INICET examples: Radiology 80, Ophthalmology 65, Dermatology 55, Pathology 45,
  Surgery 45, ENT 40, Medicine 35, Orthopaedics 40, Anatomy 30, Microbiology 25,
  Physiology 15, Pharmacology 10, Biochemistry 8, PSM/Community Medicine 10, Psychiatry 5.
  Adapt to the actual exam — USMLE, UKMLA etc. have different subject image rates.
- Output ONLY the JSON block.

IMAGE QUESTIONS RULE — this field is REQUIRED and must NEVER be 0 for any real medical exam:
Use your knowledge of each exam's typical image-based question proportion:
  - NEET PG / INICET: ~20-25% image-based (NBE pattern — pathology slides, X-rays, clinical photos)
  - USMLE Step 1: ~30-35% image-based (histology, radiology, clinical images)
  - USMLE Step 2 CK: ~20-25% image-based (clinical photos, ECGs, imaging)
  - USMLE Step 3: ~15-20% image-based
  - UKMLA AKT: ~15-20% image-based
  - MRCP Part 1: ~10-15% image-based
  - MRCP Part 2 (PACES): clinical exam, not applicable
  - If you are unsure of the exact figure, estimate at 20% of total_questions.
Compute: image_questions_total = round(total_questions * estimated_image_percentage / 100)
This must be a positive integer."""

    search_prompt = (
        f"Using your detailed knowledge of the official {course_name} exam pattern — total questions, "
        f"subject-wise distribution, duration, scoring scheme, and the proportion of image-based questions — "
        f"answer this:\n\n{prompt}"
    )

    try:
        response_text = _call_with_web_search(None, search_prompt, max_tokens=3000).strip()
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()
        specs = json.loads(response_text)
        # Safety net: ensure image_questions_total is a positive integer (floor at 20%)
        total_q = specs.get('total_questions', 0)
        if not specs.get('image_questions_total') and total_q:
            specs['image_questions_total'] = round(total_q * 0.20)
            logger.warning(f"image_questions_total was missing/zero — defaulted to 20% ({specs['image_questions_total']} Qs)")
        logger.info(f"✓ Mock exam specs fetched: {total_q} Qs, {len(specs.get('subject_distribution', {}))} subjects, {specs.get('image_questions_total')} image Qs")
        return specs
    except Exception as e:
        logger.error(f"Error fetching mock exam specs: {e}")
        raise


@app.route('/api/mock-exam-specs', methods=['POST'])
def get_mock_exam_specs():
    """Return official exam specs for mock paper generation."""
    data = request.json
    course = data.get('course')
    subjects = data.get('subjects', [])  # subject names from courseStructure

    if not course:
        return jsonify({'error': 'course is required'}), 400

    try:
        specs = fetch_mock_exam_specs(course, subjects)
        return jsonify(specs)
    except Exception as e:
        logger.error(f"mock-exam-specs error: {e}")
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# MOCK PAPER — PARALLEL PROFESSOR MODEL
# ─────────────────────────────────────────────────────────────────────────────

def generate_subject_profile(subject_name, course_name, hyt_topics):
    """
    LLM call that returns a subject-specific profile used to enrich the professor
    prompt. Called once per subject before question generation begins.
    """
    topics_str = ', '.join(hyt_topics[:20]) if hyt_topics else subject_name
    prompt = f"""You are an expert curriculum designer for {course_name} postgraduate medical entrance examinations.

Generate a subject-specific examiner profile for: {subject_name}

High-yield topics: {topics_str}

Return ONLY a JSON object with these exact keys:

{{
  "question_style": "<2-3 sentences: how questions in THIS subject typically work — e.g. clinical vignette vs. direct recall vs. image interpretation vs. data interpretation; what makes distractors hard in this subject>",
  "image_types": [
    "<modality 1 specific to {subject_name} — e.g. 'PA chest X-ray' not just 'X-ray'>",
    "<modality 2>",
    "<modality 3>",
    "<modality 4>",
    "<modality 5>"
  ],
  "image_question_focus": "<what students must identify from images in {subject_name} exams — e.g. 'ECG rhythm diagnosis', 'histological pattern recognition', 'radiological finding localisation'>",
  "distractor_archetypes": [
    "<archetype 1: a category of plausible wrong answer used repeatedly in this subject — e.g. 'related drug from the same class but wrong indication'>",
    "<archetype 2>",
    "<archetype 3>",
    "<archetype 4>"
  ],
  "bloom_guidance": "<1-2 sentences: which Bloom's levels dominate in {subject_name} and why — e.g. 'Apply and Analyse dominate because questions present novel clinical scenarios requiring diagnosis'>",
  "special_instructions": "<2-3 subject-specific rules for this examiner — e.g. drug dose ranges, classification systems to use, eponymous findings to test, common confusables to exploit>"
}}

Be specific to {subject_name} as a distinct medical discipline. Do not give generic medical exam advice."""

    try:
        raw = _or_call(prompt, model=OR_MAIN_MODEL, max_tokens=1200, temperature=0.2)
        raw = raw.split('```json')[-1].split('```')[0] if '```' in raw else raw
        profile = json.loads(raw.strip())
        if not isinstance(profile, dict):
            raise ValueError('non-dict')
        logger.info(f"  Subject profile generated for {subject_name}")
        return profile
    except Exception as e:
        logger.warning(f"generate_subject_profile failed for {subject_name}: {e} — using defaults")
        return {
            'question_style': f'Clinical vignette-based questions requiring application and analysis specific to {subject_name}.',
            'image_types': [f'{subject_name} clinical photograph', f'{subject_name} diagnostic image', 'histology slide', 'radiograph', 'diagram'],
            'image_question_focus': f'Identifying key diagnostic findings in {subject_name}',
            'distractor_archetypes': ['related condition with similar presentation', 'correct diagnosis wrong management', 'partial knowledge trap', 'common misconception'],
            'bloom_guidance': 'Apply and Analyse levels dominate; recall-only questions are rare.',
            'special_instructions': f'Use current standard guidelines. Test high-yield differentials and management decision points in {subject_name}.',
        }


def build_subject_tasks(mock_specs, course_structure, exam_format, course_name=''):
    """Builds one SubjectTask per subject. Generates subject profiles in parallel via LLM."""
    total_q = mock_specs.get('total_questions', 200)

    # Bloom's distribution: filter L2–L5 from exam_format, renormalize
    blooms_raw = {}
    if exam_format:
        blooms_raw = exam_format.get('blooms_distribution', {})
    l2_to_l5 = {k: v for k, v in blooms_raw.items()
                 if any(k.startswith(f'{i}') for i in ['2', '3', '4', '5'])}
    if not l2_to_l5:
        l2_to_l5 = {'2_understand': 1, '3_apply': 1, '4_analyze': 1, '5_evaluate': 1}
    total_bloom = sum(l2_to_l5.values()) or 1
    bloom_ratios = {k: v / total_bloom for k, v in l2_to_l5.items()}

    # HYT topic map: normalised subject name → [topic, ...]
    hyt_map = {}
    for subj in (course_structure.get('subjects') or []):
        name = subj.get('name', '').strip()
        topics = subj.get('topics') or []
        hyt = [t.get('name', '') for t in topics if t.get('high_yield') or t.get('is_high_yield')]
        if not hyt:
            hyt = [t.get('name', '') for t in topics if t.get('name')][:15]
        hyt_map[name.lower()] = {'name': name, 'topics': hyt}

    def _find_hyt(subject_name):
        key = subject_name.strip().lower()
        if key in hyt_map:
            return hyt_map[key]['topics']
        for k, v in hyt_map.items():
            if k in key or key in k:
                return v['topics']
        return []

    qf = exam_format.get('question_format', {}) if exam_format else {}
    exam_params = {
        'style':       qf.get('type') or (exam_format.get('question_style', 'single_best_answer') if exam_format else 'single_best_answer'),
        'num_options': qf.get('num_options') or (exam_format.get('num_options', 4) if exam_format else 4),
        'marking':     (exam_format.get('negative_marking') if exam_format else None) or mock_specs.get('negative_marking', ''),
    }

    tasks = []
    for subj_name, dist in (mock_specs.get('subject_distribution') or {}).items():
        num_q = int(dist.get('questions', 0))
        if num_q <= 0:
            continue
        img_pct = int(dist.get('image_pct', 0))
        num_image_q = round(num_q * img_pct / 100)

        # Bloom counts: proportional from ratios, remainder to highest level
        bloom_counts = {}
        remainder = num_q
        sorted_levels = sorted(bloom_ratios.items(), key=lambda x: x[1], reverse=True)
        for i, (level, ratio) in enumerate(sorted_levels):
            if i == len(sorted_levels) - 1:
                bloom_counts[level] = max(0, remainder)
            else:
                c = round(num_q * ratio)
                bloom_counts[level] = c
                remainder -= c

        tasks.append({
            'subject':        subj_name,
            'num_questions':  num_q,
            'num_image_qs':   num_image_q,
            'bloom_counts':   bloom_counts,
            'hyt_topics':     _find_hyt(subj_name),
            'exam_params':    exam_params,
        })

    logger.info(f"build_subject_tasks: {len(tasks)} subjects — generating subject profiles in parallel…")

    # Generate subject profiles in parallel (one LLM call per subject)
    _course_name = course_name or course_structure.get('course_name', '')
    def _gen_profile(task):
        return task['subject'], generate_subject_profile(task['subject'], _course_name, task['hyt_topics'])

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(tasks), 6)) as pool:
        for subj_name, profile in pool.map(_gen_profile, tasks):
            for t in tasks:
                if t['subject'] == subj_name:
                    t['subject_profile'] = profile
                    break

    logger.info(f"build_subject_tasks: {len(tasks)} subjects, {sum(t['num_questions'] for t in tasks)} total Qs — profiles ready")
    return tasks


def professor_plan_images(subject_task, course_name):
    """Phase A — Professor declares what images they need (one LLM call)."""
    n = subject_task['num_image_qs']
    if n <= 0:
        return []
    subject    = subject_task['subject']
    topics_str = ', '.join(subject_task.get('hyt_topics', [])[:20]) or subject
    profile    = subject_task.get('subject_profile') or {}

    # Build image-type guidance from profile (subject-specific modalities)
    profile_image_types = profile.get('image_types', [])
    profile_img_focus   = profile.get('image_question_focus', '')
    img_type_guidance   = ''
    if profile_image_types:
        img_type_guidance = (
            f"\nSUBJECT-SPECIFIC IMAGE MODALITIES FOR {subject.upper()}\n"
            f"Use these modalities (in order of relevance for this subject):\n"
            + '\n'.join(f'  • {t}' for t in profile_image_types)
        )
    if profile_img_focus:
        img_type_guidance += f"\n\nIMAGE QUESTION FOCUS: {profile_img_focus}"

    prompt = f"""You are a Professor of {subject} setting image-based questions for the {course_name} examination.
You must plan exactly {n} image-based questions. Each question will require a real image — the image IS the question.

HIGH-YIELD TOPICS:
{topics_str}
{img_type_guidance}

For each image slot, specify what you need. Return ONLY a JSON array of exactly {n} items:
[
  {{
    "topic": "<specific topic being tested>",
    "image_type": "<precise description using the subject-specific modalities above — e.g. 'PA chest X-ray showing right upper lobe cavitation'>",
    "clinical_context": "<brief patient scenario for the stem — do NOT describe the image finding>",
    "diagnosis": "<what the image shows — the correct answer>",
    "source_strategy": "<openni|wikimedia|wikipedia|generate|google>",
    "gemini_ok": true,
    "query_hint": "<3-6 word search string>"
  }}
]

SOURCE STRATEGY:
- openni: real radiology — X-ray, CT, MRI, ultrasound
- wikimedia: histology slides, gross specimens, clinical photographs, anatomy, blood smears, Gram stains, culture plates, peripheral blood films, microscopy specimens
- wikipedia: named instruments, named organisms, named syndromes with classic photo
- generate: ONLY purely synthetic content — ECG tracings, spirometry graphs, dose-response curves, action potential graphs, pedigree charts, flowcharts, mechanism diagrams, anatomy schematics. NEVER use generate for real specimen types (blood smear, Gram stain, histology, culture plate, peripheral blood film, clinical photograph, microscopy slide).
- google: last resort for anything that doesn't fit above

RULES:
- Spread across different topics from the HYT list
- Use image modalities that are authentic and high-yield for {subject} specifically
- Be specific in image_type — not "X-ray" but "Lateral skull X-ray showing button sequestrum"
- clinical_context must NOT reveal the diagnosis or image finding
- gemini_ok is always true — AI image generation is used as fallback for ALL image types when search fails"""

    try:
        raw = _or_call(prompt, model=OR_MAIN_MODEL, max_tokens=2500, temperature=0.1)
        raw = raw.split('```json')[-1].split('```')[0] if '```' in raw else raw
        specs = json.loads(raw.strip())
        if not isinstance(specs, list):
            raise ValueError('non-list')
        valid = {IMAGE_SOURCE_WIKIMEDIA, IMAGE_SOURCE_OPENNI, IMAGE_SOURCE_WIKIPEDIA,
                 IMAGE_SOURCE_GENERATE, IMAGE_SOURCE_GOOGLE}
        for s in specs:
            if s.get('source_strategy') not in valid:
                s['source_strategy'] = IMAGE_SOURCE_GOOGLE
        return specs[:n]
    except Exception as e:
        logger.warning(f"professor_plan_images failed for {subject}: {e} — falling back to plan_image_questions")
        return plan_image_questions(course_name, subject, subject_task.get('hyt_topics', []), n)


def _download_and_cache_image(img_dict):
    """
    If img_dict['url'] is an external http URL, download it to /static/ and
    replace 'url' with the local path. Returns img_dict (mutated in place).
    This ensures validation can embed the image even if the external host blocks hotlinking.
    """
    if not img_dict or not img_dict.get('url'):
        return img_dict
    url = img_dict['url']
    if not url.startswith('http'):
        return img_dict  # already local
    try:
        _HDR = {
            'User-Agent': 'Mozilla/5.0 (compatible; QBankGenerator/1.0)',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Referer': '/'.join(url.split('/')[:3]) + '/',
        }
        resp = requests.get(url, timeout=15, headers=_HDR)
        if resp.status_code == 200:
            ext = '.jpg'
            ct = resp.headers.get('content-type', '')
            if 'png' in ct:
                ext = '.png'
            elif 'gif' in ct:
                ext = '.gif'
            elif 'webp' in ct:
                ext = '.webp'
            fname = f"img_{hashlib.md5(url.encode()).hexdigest()[:12]}{ext}"
            local_path = os.path.join('static', fname)
            with open(local_path, 'wb') as f:
                f.write(resp.content)
            img_dict['url'] = f'/static/{fname}'
            img_dict['original_url'] = url
            logger.info(f"  Cached external image → {local_path}")
    except Exception as e:
        logger.warning(f"  Could not cache {url}: {e}")
    return img_dict


def _short_image_query(image_type, max_words=5):
    """
    Derive a short fallback search query from a verbose image_type string.
    Finds the *earliest* describing clause and truncates there, then caps at max_words.

    Examples:
      "CTPA axial slice at the level of the main pulmonary artery…" → "CTPA axial slice"
      "PA chest X-ray showing cardiomegaly, bilateral…"             → "PA chest X-ray"
      "12-lead ECG showing ST-segment elevation in leads II…"       → "12-lead ECG"
      "Peripheral blood smear (Leishman stain…) showing…"          → "Peripheral blood smear"
      "Tabulated arterial blood gas and biochemistry panel showing…" → "arterial blood gas panel"
    """
    import re
    text = image_type
    # Strip parenthetical qualifiers first: "(Leishman stain, high power)"
    text = re.sub(r'\s*\([^)]*\)', '', text).strip()
    # Find the earliest split point across all stop-clause patterns
    earliest = len(text)
    for pattern in [r'\s+showing\s+', r'\s+demonstrating\s+', r'\s+at\s+the\s+',
                    r'\s+of\s+the\s+', r'\s+with\s+', r',\s+']:
        m = re.search(pattern, text, re.IGNORECASE)
        if m and m.start() < earliest:
            earliest = m.start()
    text = text[:earliest].strip()
    words = text.split()
    # Drop generic openers like "Tabulated" that add no search value
    skip_first = {'tabulated', 'labelled', 'labeled', 'annotated', 'schematic'}
    if words and words[0].lower() in skip_first:
        words = words[1:]
    return ' '.join(words[:max_words])


def run_image_pipeline_for_subject(image_specs, subject_task):
    """Phase B — Fetch + validate images in parallel. Returns [{spec, image}]."""
    if not image_specs:
        return []

    def _fetch_one(spec):
        query_hint   = spec.get('query_hint', '')
        image_type   = spec.get('image_type', '')
        # Build two distinct, usable search terms:
        # [0] query_hint  — the professor's concise 3-6 word search string (primary)
        # [1] modality shortform — first meaningful words of image_type, no verbose description (fallback)
        fallback_query = _short_image_query(image_type)
        # deduplicate while preserving order
        seen = set()
        image_search_terms = []
        for t in [query_hint, fallback_query]:
            if t and t not in seen:
                seen.add(t)
                image_search_terms.append(t)

        source_strategy = spec.get('source_strategy', IMAGE_SOURCE_GOOGLE)
        q_data = {
            'image_type':         image_type,
            'image_description':  spec.get('clinical_context', ''),
            'question':           spec.get('topic', ''),
            'image_search_terms': image_search_terms,
            '_gemini_ok':         spec.get('gemini_ok', False),
            'key_finding':        spec.get('diagnosis', ''),  # what the image must show — drives the 40-pt scoring criterion
        }

        # Always run the full search+validate pipeline during generation so we capture
        # exactly what happened: query used, every candidate seen, scores, winner, Gemini prompt.
        # return_debug=True gives us all of that. The debug button just reads this stored data.
        img, candidates, raw_count, google_error, gemini_error = search_and_validate_image(
            q_data, subject_task['subject'],
            source_strategy=source_strategy,
            return_debug=True,
        )
        if img:
            _download_and_cache_image(img)
        debug_info = {
            'search_terms':     image_search_terms,
            'source_strategy':  source_strategy,
            'image_type':       image_type,
            'candidates':       candidates or [],
            'selected_url':     img.get('url') if img else None,
            'google_raw_count': raw_count,
            'google_error':     google_error,
            'gemini_error':     gemini_error,
        }
        return {'spec': spec, 'image': img, '_debug': debug_info}

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(_fetch_one, s) for s in image_specs]
        for fut in concurrent.futures.as_completed(futures, timeout=240):
            try:
                results.append(fut.result(timeout=15))
            except Exception as e:
                logger.warning(f"Image fetch error: {e}")
    return results


def _build_professor_prompt(subject_task, course_name, confirmed_images):
    """Build the fully-specified, subject-aware professor prompt."""
    subject     = subject_task['subject']
    num_q       = subject_task['num_questions']
    num_img_q   = subject_task['num_image_qs']
    bloom       = subject_task['bloom_counts']
    hyt         = subject_task.get('hyt_topics', [])
    ep          = subject_task['exam_params']
    profile     = subject_task.get('subject_profile') or {}

    hyt_str   = '\n'.join(f'  • {t}' for t in hyt[:25]) or '  (Full subject syllabus)'
    bloom_str = '\n'.join(
        f'  {k}: {v} question{"s" if v != 1 else ""}'
        for k, v in sorted(bloom.items())
    )

    # Build profile sections (only if profile was generated)
    profile_section = ''
    if profile:
        q_style      = profile.get('question_style', '')
        distractor_archetypes = profile.get('distractor_archetypes', [])
        bloom_guidance        = profile.get('bloom_guidance', '')
        special_instructions  = profile.get('special_instructions', '')
        img_q_focus           = profile.get('image_question_focus', '')

        distractor_str = '\n'.join(f'  • {d}' for d in distractor_archetypes) if distractor_archetypes else ''

        profile_section = f"""
SUBJECT PROFILE — {subject.upper()}
{"─" * 40}"""
        if q_style:
            profile_section += f"\nQuestion style: {q_style}"
        if bloom_guidance:
            profile_section += f"\nBloom's guidance: {bloom_guidance}"
        if distractor_str:
            profile_section += f"\nDistractor archetypes to exploit:\n{distractor_str}"
        if img_q_focus and num_img_q > 0:
            profile_section += f"\nImage question focus: {img_q_focus}"
        if special_instructions:
            profile_section += f"\nSpecial instructions: {special_instructions}"
        profile_section += "\n"

    batch_label = subject_task.get('_batch', '')

    # Confirmed images section — listed in order; _enrich() attaches them positionally
    img_lines = []
    for i, item in enumerate(confirmed_images, 1):
        spec = item['spec']
        img  = item.get('image')
        if img and img.get('url'):
            img_lines.append(
                f'  Slot {i}: {spec["image_type"]} | '
                f'Shows: {spec.get("diagnosis","")} | '
                f'Stem context: {spec.get("clinical_context","")}'
            )
        else:
            img_lines.append(
                f'  Slot {i}: [NOT FOUND] {spec["image_type"]} | '
                f'Shows: {spec.get("diagnosis","")} — write as text-only question'
            )

    img_section = ''
    if img_lines:
        img_section = f"""
CONFIRMED IMAGES FOR YOUR IMAGE-BASED QUESTIONS (in order)
────────────────────────────────────────────────────────────
{chr(10).join(img_lines)}

Write your {num_img_q} image question(s) in the same order as the slots above.
- The stem provides ONLY clinical context — never describe what the image shows
- The student must look at the image to select the correct answer
- [NOT FOUND] slots: write a text-only clinical question on the same topic instead
"""

    batch_note = f' (batch {batch_label})' if batch_label else ''

    return f"""You are a Professor of {subject} and a senior NBE examiner for the {course_name} examination.
You are now setting your department's contribution to this year's question paper{batch_note}.

EXAMINATION BRIEF
─────────────────
Exam:             {course_name}
Your allocation:  {num_q} questions
Format:           {ep['style'].replace('_', ' ').title()}, {ep['num_options']} options per question
Marking scheme:   {ep['marking'] or 'Standard positive marking'}
Image-based Qs:   {num_img_q} of your {num_q} questions must use the confirmed images listed below

BLOOM'S TAXONOMY — YOU MUST HIT THESE COUNTS EXACTLY
──────────────────────────────────────────────────────
{bloom_str}

HIGH-YIELD TOPICS FROM THIS YEAR'S SYLLABUS
────────────────────────────────────────────
{hyt_str}
{profile_section}{img_section}
YOUR RESPONSIBILITIES AS EXAMINER
──────────────────────────────────
- Every question must reflect authentic {course_name} standard and clinical depth for {subject}
- Follow the question style and distractor archetypes described in the Subject Profile above
- Question stems may be short or long — the key discriminating information for image questions
  must be visible only in the image, not revealed in the text
- Wrong options must be genuinely plausible to a well-prepared {subject} candidate
- Exploit the distractor archetypes listed above — these are the traps that distinguish
  the well-prepared from the partially-prepared in {subject}
- No two questions should test the same clinical fact
- Distribute your questions across the HYT topics listed above
- Each question must be tagged with its exact Bloom's level

ANSWER INTEGRITY — MANDATORY RULES
────────────────────────────────────
These rules are non-negotiable. A question that violates them is invalid.

1. STEM MUST NOT NAME THE DIAGNOSIS
   The stem presents a clinical scenario. It must NOT contain the name of the disease,
   the drug of choice, the procedure, or any term that is itself the correct answer.
   ✗ BAD:  "A patient with inferior STEMI presents with hypotension. What do you do next?"
   ✓ GOOD: "A 58-year-old man presents with crushing chest pain, ST elevation in II/III/aVF,
            and BP 80/50. His JVP is elevated. What is the next step?"

2. FOR IMAGE QUESTIONS — STEM MUST NOT DESCRIBE THE IMAGE FINDING
   The stem provides patient context only. The diagnostic finding lives in the image.
   The student must look at the image to get the key information.
   Image references: write ONLY "(Image N)" or "shown in Image N" — NEVER add a qualifier like "— schematic diagram", "— photograph", or "— illustration" after the number.
   ✗ BAD:  "The ECG shows ST elevation in leads II, III and aVF. What is the diagnosis?"
   ✗ BAD:  "…peripheral blood smear (Image 1 — schematic diagram) shows…"
   ✓ GOOD: "A 55-year-old man presents with chest pain radiating to the jaw. The ECG is shown in Image 1.
            What is the most likely diagnosis?"
   ✓ GOOD: "A 28-year-old man presents with fever. A peripheral blood smear is shown (Image 1).
            What species is identified?"

3. OPTIONS MUST NOT BETRAY THE ANSWER
   - All options must be plausible — no option should be obviously absurd
   - Options must be grammatically parallel and similar in length/detail
   - The correct answer must NOT be the only long, detailed, or qualified option
   - Do NOT use "All of the above" or "None of the above"
   ✗ BAD:  A. Inferior STEMI with RV involvement   B. Pericarditis   C. Anxiety   D. GERD
   ✓ GOOD: A. Inferior STEMI with RV involvement   B. Anterior STEMI   C. NSTEMI   D. Type 2 MI

4. NO ANSWER CLUES IN STEM WORDING
   The stem must not use phrases that implicitly point to one option:
   ✗ "which finding is pathognomonic for X" (when X is an option)
   ✗ "the classic triad of Y includes all EXCEPT" (when Y is the answer)

Return EXACTLY {num_q} questions as a JSON array. Schema for each question:
{{
  "question":       "<stem>",
  "options":        ["A. ...", "B. ...", "C. ...", "D. ..."],
  "correct_answer": "A",
  "explanation":    "<2-3 sentences max: why correct answer is right and key distractor traps>",
  "topic":          "<specific topic from HYT list>",
  "bloom_level":    "<2_understand|3_apply|4_analyze|5_evaluate>",
  "is_image_question": <true|false>,
  "image_type":         "<modality string if image question — copied from the slot description, else null>",
  "image_search_terms": ["<3-5 specific search terms if image question, else empty array>"]
}}

Return ONLY the JSON array. No preamble, no commentary, no markdown."""


_PROFESSOR_BATCH_SIZE = 6   # max questions per LLM call — 10 with full explanations hits 6k token ceiling

def professor_generate_questions(subject_task, confirmed_images, course_name):
    """Phase C — Professor generates questions in batches of ≤10 to avoid truncation."""
    subject = subject_task['subject']
    num_q   = subject_task['num_questions']

    # Flat list of confirmed image data in slot order; _enrich assigns positionally
    img_data_list = [
        {
            **(item.get('image') or {}),
            'image_search_terms': [item['spec'].get('query_hint', ''), _short_image_query(item['spec'].get('image_type', ''))],
            'image_type':         item['spec'].get('image_type', ''),
            'image_description':  item['spec'].get('clinical_context', ''),
            '_debug':             item.get('_debug'),   # generation-time search debug
        }
        for item in confirmed_images
    ]

    def _enrich(qs, batch_img_data):
        """Attach metadata and assign images positionally to is_image_question=true questions."""
        img_idx = 0
        for q in qs:
            q['subject'] = subject
            q['course']  = course_name
            # Normalise correct answer
            if 'correct_answer' in q and not q.get('correct_option'):
                q['correct_option'] = q.pop('correct_answer')
            # Normalise bloom field
            if 'bloom_level' in q and 'blooms_level' not in q:
                q['blooms_level'] = q.pop('bloom_level')
            bl = q.get('blooms_level', '')
            q['blooms_level'] = bl[0] if bl and bl[0].isdigit() else bl
            # Normalise difficulty to numeric (UI expects 1=Medium, 2=Hard, 3=Very Hard)
            _diff_map = {'easy': 1, 'medium': 1, 'hard': 2, 'very hard': 3, 'very_hard': 3}
            d = q.get('difficulty')
            if not d:
                q['difficulty'] = 1
            elif isinstance(d, str):
                q['difficulty'] = _diff_map.get(d.lower().strip(), 1)
            # Positional image assignment
            if q.get('is_image_question') and img_idx < len(batch_img_data):
                img = batch_img_data[img_idx]
                img_idx += 1
                q['image_url']    = img.get('url')
                q['image_source'] = img.get('source')
                if not q.get('image_search_terms'):
                    q['image_search_terms'] = [t for t in img.get('image_search_terms', []) if t]
                if not q.get('image_type'):
                    q['image_type'] = img.get('image_type', '')
                if not q.get('image_description'):
                    q['image_description'] = img.get('image_description', '')
                # Store generation-time debug data so the debug button never needs to re-run
                if img.get('_debug'):
                    q['_image_debug'] = img['_debug']
            elif q.get('is_image_question') and not q.get('image_url'):
                # Image was planned but fetch failed — mark so the UI can warn the user.
                # Do NOT alter the stem: the question is broken without its image and
                # should surface as "Needs Revision" in validation.
                q['image_missing'] = True
        return qs

    def _parse(raw):
        raw = raw.split('```json')[-1].split('```')[0] if '```' in raw else raw
        qs  = json.loads(raw.strip())
        if not isinstance(qs, list):
            raise ValueError('non-list')
        return qs

    def _call_batch(batch_task, batch_imgs, batch_img_data):
        prompt = _build_professor_prompt(batch_task, course_name, batch_imgs)
        raw    = _or_call(prompt, model=OR_MAIN_MODEL, max_tokens=8000, temperature=0.7)
        qs     = _parse(raw)
        if len(qs) < batch_task['num_questions']:
            raw2 = _or_call(prompt, model=OR_MAIN_MODEL, max_tokens=8000, temperature=0.5)
            qs2  = _parse(raw2)
            if len(qs2) > len(qs):
                qs = qs2
        _enrich(qs, batch_img_data)
        return qs

    # Split into batches, distributing image slots and bloom counts proportionally
    all_questions = []
    num_batches   = math.ceil(num_q / _PROFESSOR_BATCH_SIZE)

    # Distribute bloom counts across batches proportionally
    bloom_remaining = dict(subject_task['bloom_counts'])

    # Distribute confirmed_images across batches by index
    img_per_batch = math.ceil(len(confirmed_images) / num_batches) if confirmed_images else 0

    for b in range(num_batches):
        batch_size = min(_PROFESSOR_BATCH_SIZE, num_q - len(all_questions))
        if batch_size <= 0:
            break

        # Bloom counts for this batch: proportional slice
        batch_bloom = {}
        remaining_batches = num_batches - b
        for level, total_count in bloom_remaining.items():
            if remaining_batches == 1:
                batch_bloom[level] = total_count
            else:
                c = round(total_count / remaining_batches)
                batch_bloom[level] = c

        # Image slots for this batch — both the spec+image pairs (for the prompt) and
        # the resolved image data (for positional assignment in _enrich)
        img_start      = b * img_per_batch
        batch_images   = confirmed_images[img_start: img_start + img_per_batch]
        batch_img_data = img_data_list[img_start: img_start + img_per_batch]
        batch_img_q    = len(batch_images)

        batch_task = {
            **subject_task,
            'num_questions': batch_size,
            'num_image_qs':  batch_img_q,
            'bloom_counts':  batch_bloom,
            '_batch':        f'{b+1}/{num_batches}',
        }

        try:
            qs = _call_batch(batch_task, batch_images, batch_img_data)
            all_questions.extend(qs)
            # Subtract from bloom_remaining
            for level in bloom_remaining:
                bloom_remaining[level] = max(0, bloom_remaining[level] - batch_bloom.get(level, 0))
            logger.info(f"  {subject} batch {b+1}/{num_batches}: {len(qs)}/{batch_size} Qs")
        except Exception as e:
            logger.error(f"professor batch {b+1} failed for {subject}: {e}")

    logger.info(f"Professor {subject}: {len(all_questions)}/{num_q} questions generated")
    return all_questions


def generate_subject_paper(subject_task, course_name):
    """Orchestrate Phase A → B → C for one subject. Returns list of questions."""
    subject = subject_task['subject']
    logger.info(f"▶ Professor of {subject}: {subject_task['num_questions']} Qs, {subject_task['num_image_qs']} image Qs")

    # Phase A: plan images
    confirmed_images = []
    if subject_task['num_image_qs'] > 0:
        specs = professor_plan_images(subject_task, course_name)
        logger.info(f"  {subject}: planned {len(specs)} image specs")
        # Phase B: fetch images
        if specs:
            confirmed_images = run_image_pipeline_for_subject(specs, subject_task)
            found = sum(1 for c in confirmed_images if c.get('image'))
            logger.info(f"  {subject}: {found}/{len(specs)} images confirmed")

    # Phase C: generate questions
    return professor_generate_questions(subject_task, confirmed_images, course_name)


def assemble_mock_paper(subject_results_ordered, total_q):
    """Round-robin interleave subject question lists, trim to total_q."""
    lists = [qs for qs in subject_results_ordered if qs]
    if not lists:
        return []
    assembled, max_len = [], max(len(lst) for lst in lists)
    for i in range(max_len):
        for lst in lists:
            if i < len(lst):
                assembled.append(lst[i])
    for i, q in enumerate(assembled, 1):
        q['question_number'] = i
    return assembled[:total_q]


@app.route('/api/generate-mock-paper', methods=['POST'])
def generate_mock_paper():
    """Generate a full mock exam paper — parallel professor agents, SSE streaming."""
    data          = request.json or {}
    mock_specs    = data.get('mock_specs')
    course_struct = data.get('course_structure') or {}
    exam_format   = data.get('exam_format') or {}
    course_name   = data.get('course_name', '')

    if not mock_specs:
        return jsonify({'error': 'mock_specs required'}), 400
    if not course_name:
        return jsonify({'error': 'course_name required'}), 400

    def _stream():
        try:
            # Step 1: build tasks + generate subject profiles
            yield f"data: {json.dumps({'type':'status','message':'Building subject profiles…'})}\n\n"
            tasks    = build_subject_tasks(mock_specs, course_struct, exam_format, course_name)
            total_q  = mock_specs.get('total_questions') or sum(t['num_questions'] for t in tasks)
            subjects = [t['subject'] for t in tasks]
            yield f"data: {json.dumps({'type':'tasks_ready','subjects':subjects,'total_questions':total_q,'task_count':len(tasks)})}\n\n"

            # Step 2: parallel professor agents
            subject_results = {}  # subject → [questions]
            lock = threading.Lock()
            completed = [0]

            def _run(task):
                qs = generate_subject_paper(task, course_name)
                with lock:
                    subject_results[task['subject']] = qs
                    completed[0] += 1
                return task['subject'], len(qs)

            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(tasks), 6)) as pool:
                futures = {pool.submit(_run, t): t for t in tasks}
                for fut in concurrent.futures.as_completed(futures, timeout=3600):
                    task = futures[fut]
                    try:
                        subj, count = fut.result(timeout=15)
                        yield f"data: {json.dumps({'type':'subject_done','subject':subj,'count':count,'completed':completed[0],'total_subjects':len(tasks)})}\n\n"
                    except Exception as e:
                        logger.error(f"Subject {task['subject']} failed: {e}", exc_info=True)
                        yield f"data: {json.dumps({'type':'subject_error','subject':task['subject'],'error':str(e)})}\n\n"

            # Step 3: assemble
            yield f"data: {json.dumps({'type':'status','message':'Assembling final paper…'})}\n\n"
            ordered = [subject_results.get(t['subject'], []) for t in tasks]
            final   = assemble_mock_paper(ordered, total_q)

            yield f"data: {json.dumps({'type':'complete','questions':final,'count':len(final)})}\n\n"

        except Exception as e:
            logger.error(f"generate_mock_paper stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type':'error','message':str(e)})}\n\n"

    return Response(
        stream_with_context(_stream()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


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
        response_text = _or_call(flow_prompt, max_tokens=3000, temperature=0.7).strip()
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
   - **CRITICAL — PHOTOREALISM**: For modalities that must be real photographs or scans (X-ray, CT, MRI, ultrasound, microscopy, histopathology, blood smear, Gram stain, culture plate, ECG, fundoscopy, endoscopy, clinical photograph) — does the image look like a genuine clinical image? Plasticky textures, over-saturated colors, CGI-rendered anatomy, 3D-illustration style, or any "computer-generated" appearance counts as automatic failure for these modalities.
   - Is the image quality sufficient for diagnostic interpretation?
   - **CRITICAL**: Are there NO text labels, annotations, or arrows that reveal the answer or diagnosis?
   - **CRITICAL**: Medical images for exam questions must be UNLABELED - any visible text revealing the diagnosis should result in automatic failure (score 0-30)

4. EDUCATIONAL VALUE (20 points):
   - Would this image help a medical student identify the diagnosis?
   - Is the finding prominent enough to be clinically useful?
   - Does it match board examination image standards?

SCORING GUIDE:
- 90-100: Perfect match - correct modality, diagnostic finding clearly visible, photorealistic clinical quality, NO text labels
- 80-89: Very good match - correct type, finding clearly visible, minor quality issues, NO text labels
- 70-79: Good match - correct type, finding visible but not ideal quality, NO text labels
- 50-69: Partial match - correct type but finding unclear or poor quality
- 30-49: Wrong finding, very poor quality, or mildly schematic appearance
- 0-29: Wrong modality, diagram/illustration, plasticky/CGI/schematic when realism required, or ANY visible text revealing the diagnosis/answer

**AUTOMATIC DISQUALIFICATION (score 0-30)**:
- Image contains ANY text, labels, annotations, or arrows that reveal or hint at the diagnosis/answer:
  - "Mitochondrial inheritance" on a pedigree → score 0-20
  - "Pneumonia" labeled on chest X-ray → score 0-20
  - "STEMI" or diagnosis text on ECG → score 0-20
  - Educational diagrams with labeled pathology → score 0-20
- Image looks plasticky, CGI-rendered, illustrated, or schematic for a modality that requires a real photograph/scan:
  - Plasticky 3D-rendered "X-ray" instead of a real radiograph → score 0-20
  - Illustrated microscopy cartoon instead of a real blood smear photo → score 0-20
  - CGI anatomy render instead of a real CT/MRI slice → score 0-20
  - Schematic ECG diagram instead of a real tracing printout → score 0-20

Respond with ONLY a JSON object:
{{"score": <number 0-100>, "reason": "<specific explanation of what you see and why score was given — explicitly call out if image is plasticky/schematic/CGI when realism was required>"}}"""

        # Download image
        img_response = requests.get(image_url, timeout=10)
        if img_response.status_code != 200:
            return {'score': 0, 'reason': f'Failed to download image (HTTP {img_response.status_code})'}

        # Reject non-image responses (HTML error pages, redirects, etc.)
        raw_ct = img_response.headers.get('content-type', '')
        content_type = raw_ct.split(';')[0].strip()
        if not content_type.startswith('image/'):
            return {'score': 0, 'reason': f'URL returned non-image content ({content_type or "unknown type"}) — skipping'}

        # Reject implausibly small files (< 500 bytes can't be a real image)
        if len(img_response.content) < 500:
            return {'score': 0, 'reason': f'Downloaded file too small ({len(img_response.content)} bytes) — not a valid image'}

        import base64
        img_base64 = base64.b64encode(img_response.content).decode('utf-8')

        # Call vision model via OpenRouter — short timeout (scoring only, not generation)
        response_text = _or_call(
            None,
            max_tokens=500,
            timeout=45,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{content_type};base64,{img_base64}"}
                    },
                    {
                        "type": "text",
                        "text": validation_prompt
                    }
                ]
            }]
        )

        # Guard against empty / None response from the API
        if not response_text:
            return {'score': 0, 'reason': 'Vision model returned empty response — image may be unprocessable'}

        # Parse response
        result = json.loads(response_text)
        if not isinstance(result, dict):
            return {'score': 0, 'reason': f'Unexpected API response type: {type(result).__name__}'}
        return result

    except Exception as e:
        logger.error(f"Validation error: {e}")
        return {'score': 0, 'reason': str(e)[:200]}


_TERM_BLOCKLIST = re.compile(
    r'\b(wikimedia\s*commons?|wikimedia|open[\s\-]?i|pubmed|radiopaedia|medscape'
    r'|annotated|labeled|labelled|unlabeled|diagram|illustration|schematic)\b',
    re.IGNORECASE
)
# Same blocklist applied to image_type before using it in Gemini prompts
_TYPE_BLOCKLIST = re.compile(
    r'\b(labeled|labelled|annotated|unlabeled|diagram|illustration|schematic'
    r'|image|picture|photo(?:graph)?)\b',
    re.IGNORECASE
)

def _sanitize_search_terms(terms):
    """Strip site names and diagram qualifiers that pollute Google queries."""
    cleaned = []
    for t in terms:
        t2 = _TERM_BLOCKLIST.sub('', t).strip()
        t2 = ' '.join(t2.split())  # normalise whitespace
        if t2:
            cleaned.append(t2)
    return cleaned or terms  # fall back to originals if everything got wiped

def _sanitize_image_type(image_type):
    """Remove misleading qualifiers (Labeled, Annotated, etc.) from the image_type string."""
    cleaned = _TYPE_BLOCKLIST.sub('', image_type).strip()
    cleaned = ' '.join(cleaned.split())
    return cleaned or image_type


def collect_candidate_images(image_search_terms, image_type, max_candidates=8):
    """Collect candidate images from Google Custom Search only.
    Tries each sanitized query in order until we have enough candidates.
    No imgType/rights filters — Claude Vision scorer handles quality control.
    Returns (candidates, google_raw_count, google_error) where:
      google_raw_count = total raw items Google returned across all queries
      google_error     = error string if Google returned an API error, else None
    """
    candidates = []
    google_raw_count = 0
    google_error = None

    image_search_terms = _sanitize_search_terms(image_search_terms)
    if not image_search_terms:
        return candidates, google_raw_count, 'No search terms after sanitization'

    if not (GOOGLE_CSE_ID and GOOGLE_API_KEY):
        logger.warning("  ✗ Google CSE not configured — skipping web search")
        return candidates, google_raw_count, 'Google CSE not configured'

    cse_url = "https://www.googleapis.com/customsearch/v1"

    for attempt, query in enumerate(image_search_terms):
        if len(candidates) >= max_candidates:
            break
        logger.info(f"  → Google search #{attempt+1}: '{query}'")
        try:
            params = {
                'key': GOOGLE_API_KEY, 'cx': GOOGLE_CSE_ID,
                'q': query, 'searchType': 'image', 'num': 10, 'safe': 'active',
            }
            resp = requests.get(cse_url, params=params, timeout=15)
            body = resp.json()

            if resp.status_code == 200:
                items = body.get('items', [])
                google_raw_count += len(items)
                logger.info(f"    Google returned {len(items)} raw result(s) (cumulative: {google_raw_count})")
                if not items:
                    # Log search information for diagnosis
                    search_info = body.get('searchInformation', {})
                    logger.info(f"    searchInformation: {search_info}")
                for item in items:
                    link = item.get('link', '')
                    if not link or link.lower().endswith('.svg'):
                        continue
                    if not link.startswith(('http://', 'https://')):
                        continue  # skip x-raw-image:// and other non-http URLs
                    mime = item.get('mime', '')
                    if mime and not mime.startswith('image/'):
                        continue
                    candidates.append({'url': link, 'source': 'Google Images',
                                       'title': item.get('title', '')[:100]})
                    logger.info(f"    ✓ {item.get('title','')[:60]}")
                    if len(candidates) >= max_candidates:
                        break
            elif resp.status_code == 429:
                google_error = 'Google CSE daily quota exceeded (429)'
                logger.warning(f"  ✗ {google_error}")
                break
            else:
                err = body.get('error', {})
                google_error = f"HTTP {resp.status_code}: {err.get('message', resp.text[:200])}"
                logger.warning(f"  ✗ Google error: {google_error}")
                break  # no point retrying on auth/config errors
        except Exception as e:
            google_error = str(e)
            logger.error(f"  ✗ Google request exception: {e}")
            break

    logger.info(f"  Collected {len(candidates)} candidate(s) from Google (raw total: {google_raw_count})")
    return candidates, google_raw_count, google_error


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
        # Call vision model via OpenRouter
        response_text = _or_call(
            None,
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{img_base64}"}
                    },
                    {
                        "type": "text",
                        "text": location_prompt
                    }
                ]
            }]
        )

        # Parse location response
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


def build_gemini_prompt(question_data):
    """Build the Gemini image-generation prompt for the given question. Returns the prompt string."""
    image_desc = question_data.get('image_description', '')
    image_type = _sanitize_image_type(question_data.get('image_type', ''))
    key_finding = question_data.get('key_finding', '')

    kf_line = f"\n\nKEY FINDING — must be unmistakably visible and visually dominant: {key_finding}" if key_finding else ""

    # Appended to imaging/specimen branches only — demands a real photograph, not a schematic
    realism_note = """
- PHOTOREALISTIC — must look exactly like a genuine clinical image captured in real life: natural grain, authentic optical artifacts, real tissue colors and textures; do NOT produce a plasticky, CGI-rendered, over-saturated, or illustrated look; a viewer must be unable to distinguish it from an actual photograph or scan"""

    # Appended to every branch — universal quality gate
    universal_quality = f"""

EDUCATIONAL QUALITY REQUIREMENTS (mandatory for every image):
- Textbook-quality accuracy: proportions, colors, spatial relationships, and morphology must match what appears in authoritative medical textbooks
- Every structure and detail mentioned in the description must be present and clearly identifiable
- The key finding ({key_finding or image_desc[:80]}) must be the most visually salient feature — a student must immediately notice it
- No detail omitted that is necessary to understand or answer a board-style question about this image
- Medically accurate and educationally valuable — suitable for use in a USMLE/NBME-style examination
- COMPLETELY UNLABELED: NO text, NO structure names, NO arrows with text, NO annotations, NO diagnosis names anywhere on the image"""

    if 'gram stain' in image_type.lower() or ('microscopy' in image_type.lower() and 'histopathology' not in image_type.lower()):
        return f"""Create a realistic high-resolution microscopy photograph for a medical board examination question.

WHAT TO SHOW: {image_desc}.{kf_line}

ACCURACY REQUIREMENTS:
- Authentic microscope photograph — NOT a diagram or illustration
- Individual cells/organisms rendered with precise staining morphology:
  Gram stain → Gram-positive organisms purple/violet, Gram-negative organisms pink/red
  Other stains → exact color characteristics as specified in the description
- Magnification appropriate to the organism/finding (typically 400x–1000x oil immersion)
- Background field populated realistically (RBCs, WBCs, debris as appropriate)
- Depth of field, slight optical blur at edges — looks like a real microscope image
- Colony/cell arrangement (clusters, chains, pairs, singly) exactly as described{realism_note}{universal_quality}"""

    if 'histopathology' in image_type.lower() or 'h&e' in image_type.lower() or 'biopsy' in image_type.lower():
        return f"""Create a realistic histopathology microscopy image for a medical board examination question.

WHAT TO SHOW: {image_desc}.{kf_line}

ACCURACY REQUIREMENTS:
- Authentic H&E-stained tissue section — NOT a diagram or illustration
- Nuclei: blue/purple (hematoxylin); cytoplasm and extracellular matrix: pink (eosin)
- Tissue architecture preserved: glandular, stromal, vascular structures correctly arranged
- Pathognomonic cellular features prominently represented (e.g., Reed-Sternberg cells, granulomas, dysplasia, necrosis)
- Magnification appropriate to show both tissue architecture and cellular detail
- Looks like a real glass slide scanned on a digital pathology system{realism_note}{universal_quality}"""

    if 'culture' in image_type.lower() or 'agar' in image_type.lower():
        return f"""Create a realistic photograph of a microbiology culture plate for a medical board examination question.

WHAT TO SHOW: {image_desc}.{kf_line}

ACCURACY REQUIREMENTS:
- Authentic petri dish photograph — NOT a diagram or illustration
- Colony morphology exactly as described: size, color, texture, surface characteristics, hemolysis pattern (alpha/beta/gamma on blood agar)
- Correct agar color for the medium specified (blood agar: dark red; MacConkey: pink; chocolate agar: brown)
- Realistic colony density and distribution
- Petri dish edge, lid reflection, and agar surface texture visible for realism{realism_note}{universal_quality}"""

    if 'ecg' in image_type.lower() or 'ekg' in image_type.lower():
        return f"""Create a realistic 12-lead ECG tracing for a medical board examination question.

WHAT TO SHOW: {image_desc}.{kf_line}

ACCURACY REQUIREMENTS:
- Authentic ECG printout appearance with standard pink/red grid paper background
- All 12 leads clearly arranged: limb leads (I, II, III, aVR, aVL, aVF) and precordial leads (V1–V6)
- Standard calibration: 10 mm/mV amplitude, 25 mm/s paper speed — calibration box visible
- Waveform morphology precisely matching the described abnormality in the correct leads
  (e.g., ST elevation in inferior leads for inferior MI; delta waves in WPW; p-wave absence in AF)
- Rhythm strip (lead II or V1) at the bottom
- No diagnosis text — only standard lead labels (I, II, aVR, V1, etc.) are permitted{realism_note}{universal_quality}"""

    if 'x-ray' in image_type.lower() or 'radiograph' in image_type.lower():
        return f"""Create a realistic medical X-ray radiograph for a medical board examination question.

WHAT TO SHOW: {image_desc}.{kf_line}

ACCURACY REQUIREMENTS:
- Authentic radiograph appearance: white bone, black air/lung, gray soft tissue on dark background
- Correct projection and positioning: PA chest, AP abdomen, lateral, oblique — as specified
- Anatomical landmarks correctly positioned and proportioned
- The pathologic finding rendered with accurate radiographic density and location
  (e.g., consolidation opacifies lung field; pneumothorax shows sharp pleural line with absent lung markings;
   fracture shows cortical break; air under diaphragm is crescentic lucency)
- Film grain/noise appropriate to a real diagnostic radiograph{realism_note}{universal_quality}"""

    if re.search(r'\bct\b', image_type.lower()) or 'computed tomography' in image_type.lower() or 'ct scan' in image_type.lower():
        return f"""Create a realistic CT scan image for a medical board examination question.

WHAT TO SHOW: {image_desc}.{kf_line}

ACCURACY REQUIREMENTS:
- Authentic CT image: black background, Hounsfield unit-based grayscale
  (bone: bright white; air: black; fat: dark gray; soft tissue: intermediate gray; contrast-enhancing structures: bright)
- Correct slice plane: axial, coronal, or sagittal as specified
- Anatomical structures correctly positioned and shaped for the level of the scan
- Pathology rendered at correct HU density and location
  (e.g., acute hemorrhage bright white; ischemic stroke dark hypoattenuation; PE: filling defect in pulmonary artery)
- Scan window/level appearance appropriate to the region (brain window vs. lung window vs. soft tissue window){realism_note}{universal_quality}"""

    if 'mri' in image_type.lower():
        return f"""Create a realistic MRI scan image for a medical board examination question.

WHAT TO SHOW: {image_desc}.{kf_line}

ACCURACY REQUIREMENTS:
- Authentic MRI appearance for the specified sequence:
  T1: fat bright, water dark, good anatomical detail
  T2: water/CSF bright, fat intermediate, pathology often bright
  FLAIR: CSF suppressed (dark), periventricular lesions bright
  DWI: restricted diffusion (acute infarct/abscess) bright
- Black background with correct signal intensities for every tissue type
- Correct slice plane and anatomical level
- Pathologic finding renders with the signal characteristics appropriate to the sequence and diagnosis
- MRI appearance: smooth gradient, no film grain (unlike X-ray){realism_note}{universal_quality}"""

    if 'ultrasound' in image_type.lower() or 'sonography' in image_type.lower():
        return f"""Create a realistic ultrasound/sonography image for a medical board examination question.

WHAT TO SHOW: {image_desc}.{kf_line}

ACCURACY REQUIREMENTS:
- Authentic ultrasound appearance: sector or linear probe fan-shape, black background
- Correct echogenicity for each structure:
  Fluid/cysts: anechoic (black) with posterior acoustic enhancement
  Solid tissue: echogenic (gray-white)
  Bone/gas: bright white with posterior shadowing
- Speckle artifact and slight graininess typical of real ultrasound
- Anatomical structures correctly positioned in the scan plane
- Pathologic finding rendered with correct echogenicity and location{realism_note}{universal_quality}"""

    # Clinical photograph modalities — realistic photo is the RIGHT format
    _photo_keywords = ('dermatology', 'skin', 'rash', 'lesion', 'wound', 'fundoscopy', 'fundus',
                       'ophthalmoscopy', 'retina', 'slit lamp', 'clinical photograph', 'clinical photo',
                       'physical examination', 'bedside', 'operative', 'surgical', 'endoscopy',
                       'colonoscopy', 'colposcopy')
    if any(kw in image_type.lower() for kw in _photo_keywords):
        return f"""Create a realistic, unlabeled clinical medical photograph for a medical board examination question.

WHAT TO SHOW: {image_desc}.{kf_line}

ACCURACY REQUIREMENTS:
- Authentic clinical photograph quality — looks like a real patient photograph taken in clinic or OR
- Lighting, color, and tissue appearance consistent with the described setting
- The diagnostic finding is prominently visible, centered, and well-lit — exactly as described
- Surrounding context (skin, mucosa, background tissue) anatomically accurate
- Skin lesions: accurate color, border, surface texture for the described condition
- Fundoscopy: correct optic disc, vessel, and retinal appearance
- Endoscopy: correct mucosal color and luminal appearance{realism_note}{universal_quality}"""

    # Everything else — use medical illustration style (Netter/Gray's quality)
    # Covers: anatomy, cross-sections, nerve/vessel courses, pedigrees,
    # pathophysiology/mechanism diagrams, pharmacology, and any unrecognized type.
    return f"""Create a high-quality, unlabeled medical illustration for a medical board examination question.

WHAT TO SHOW: {image_desc}.{kf_line}

STYLE — choose whichever best fits the content:
- Anatomy / cross-section / nerve or vessel course: Netter's Atlas / Gray's Anatomy quality —
  color-coded structures (red arteries, blue veins, yellow nerves, cream/white bone, pink muscle),
  realistic tissue shading, clean light background
- Pathophysiology / mechanism / pharmacology: clean schematic with distinct shapes and directional arrows
  (NO text labels — shapes and spatial layout convey the mechanism visually)
- Pedigree: ACMG-standard symbols (squares = male, circles = female, filled = affected),
  correct generational lines and carrier notation
- Clinical sign / physical finding: textbook-quality illustration of the finding on an anatomical figure

ACCURACY REQUIREMENTS:
- Spatial relationships between structures exactly as in authoritative anatomy atlases
- Proportions and relative sizes anatomically correct
- Every structure described must be present and distinguishable
- Key pathology or variant clearly differentiated from normal surrounding tissue
- Clean, uncluttered composition on a white or light neutral background
- Do NOT generate a cadaver photograph, a dissection photograph, or any MRI/CT/X-ray image{universal_quality}"""


def generate_image_with_gemini(question_data):
    """Generate image with Gemini Nano Banana Pro (gemini-3-pro-image-preview).
    Returns (result_dict, error_str). On success error_str is None; on failure result_dict is None."""
    try:
        image_type = question_data.get('image_type', '')
        prompt = build_gemini_prompt(question_data)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _executor:
            _future = _executor.submit(
                gemini_client.models.generate_content,
                model='gemini-3-pro-image-preview',
                contents=[prompt],
            )
            try:
                response = _future.result(timeout=120)
            except concurrent.futures.TimeoutError:
                msg = 'Gemini timed out after 120s'
                logger.warning(msg)
                return None, msg

        for part in (response.parts or []):
            if part.inline_data is not None and part.inline_data.data:
                image = part.as_image()

                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png', dir='static') as f:
                    img_path = f.name

                image.save(img_path)

                # Validate the saved file is non-empty (Gemini can return corrupt/zero-byte data)
                file_size = os.path.getsize(img_path)
                if file_size < 1000:
                    msg = f'Gemini returned near-empty image ({file_size} bytes)'
                    logger.warning(msg + ', discarding')
                    try:
                        os.remove(img_path)
                    except Exception:
                        pass
                    return None, msg

                return {
                    'url': f"/static/{os.path.basename(img_path)}",
                    'source': 'Nano Banana Pro (AI Generated)',
                    'title': f'Generated: {image_type}'
                }, None

        return None, 'Gemini returned no image parts in response'
    except Exception as e:
        raw = str(e)
        if '<html' in raw.lower() or '<!doctype' in raw.lower():
            msg = 'Gemini API returned an HTML error page (auth/quota issue)'
        else:
            msg = raw.split('\n')[0][:200]
        logger.error(f"Generation error: {e}")
        return None, msg


def generate_image_with_openrouter(question_data):
    """Generate image via direct OpenAI API using OR_IMAGE_MODEL (default: gpt-image-2).
    Requires OPENAI_API_KEY — OpenRouter does not expose the /v1/images/generations endpoint.
    Returns (result_dict, error_str). On success error_str is None; on failure result_dict is None."""
    if not openai_image_client:
        return None, 'OPENAI_API_KEY not set — direct OpenAI image generation unavailable'
    if not OR_IMAGE_MODEL:
        return None, 'OR_IMAGE_MODEL not configured'
    try:
        import base64 as _b64
        image_type = question_data.get('image_type', '')
        prompt = build_gemini_prompt(question_data)

        logger.info(f"  [openai-img] Generating with {OR_IMAGE_MODEL}: {image_type}")
        response = openai_image_client.images.generate(
            model=OR_IMAGE_MODEL,
            prompt=prompt,
            n=1,
            size='1024x1024',
            response_format='b64_json',
        )
        b64_data = (response.data or [{}])[0].b64_json if response.data else None
        if not b64_data:
            return None, f'{OR_IMAGE_MODEL} returned empty image data'

        img_bytes = _b64.b64decode(b64_data)
        if len(img_bytes) < 1000:
            return None, f'{OR_IMAGE_MODEL} returned near-empty image ({len(img_bytes)} bytes)'

        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png', dir='static') as f:
            f.write(img_bytes)
            img_path = f.name

        logger.info(f"  [openai-img] Image saved: {os.path.basename(img_path)}")
        return {
            'url':    f"/static/{os.path.basename(img_path)}",
            'source': f'AI Generated ({OR_IMAGE_MODEL})',
            'title':  f'Generated: {image_type}',
        }, None

    except Exception as e:
        msg = str(e).split('\n')[0][:200]
        logger.error(f"OpenRouter image generation error: {e}")
        return None, msg


# ─────────────────────────────────────────────────────────────────────────────
# IMAGE PLANNING
# ─────────────────────────────────────────────────────────────────────────────

def plan_image_questions(course, subject, topics, total_img_count):
    """
    LLM-powered planning step: given the exam name, subject, topics, and how many image
    questions we need, return a list of ImageSlot dicts describing WHAT to generate and
    HOW to source each image.  Works generically for any exam (NEET PG, USMLE, FMGE, …).

    Returns a list of dicts:
      {
        "image_type": "H&E histopathology slide",
        "image_category": "histology",
        "source_strategy": "wikimedia",   # one of IMAGE_SOURCE_* constants
        "gemini_ok": False,               # True = Gemini can make a clean image here
        "query_hint": "glomerulonephritis H&E stain",
        "topic_hint": "Glomerulonephritis"
      }
    Length == total_img_count.
    """
    if total_img_count <= 0:
        return []

    topics_str = ', '.join(str(t) for t in topics[:20])
    prompt = f"""You are an expert medical educator planning image-based MCQs for {course}.

SUBJECT: {subject}
TOPICS COVERED: {topics_str}
NUMBER OF IMAGE QUESTIONS TO PLAN: {total_img_count}

Your task: produce a JSON array of exactly {total_img_count} image-question slots.
Use your knowledge of {course} exam patterns to decide:
  - Which topics/subtopics within {subject} most commonly appear as image questions in {course}
  - What SPECIFIC image type is tested (e.g., "H&E histopathology slide", "Chest X-ray PA view",
    "Gram stain microscopy", "Surgical instrument photo", etc.)
  - The best SOURCE STRATEGY for finding that image:
      "wikimedia"  → Wikimedia Commons: use for histology slides, gross pathology specimens,
                     anatomy cross-sections, organism microscopy, physical-finding clinical photos
      "openni"     → OpenI NIH: use for radiology — CT, X-ray, MRI, ultrasound
      "wikipedia"  → Wikipedia lead image: use for named surgical instruments, named organisms,
                     named syndromes with a classic photo, named ECG patterns
      "generate"   → Gemini AI generation: use for schematic diagrams, graphs (spirometry,
                     dose-response, action potential), flow charts, pedigree charts, ECG tracings,
                     government/NGO program logos/posters, mechanism diagrams
      "google"     → Google Custom Search: last resort only — use when none of the above fit
  - "gemini_ok": true ONLY if the image type is a clean schematic/graph/diagram that AI can
    render well (ECG, flow chart, dose-response curve, anatomy schematic). false for clinical
    photos, histology slides, real radiology images.
  - A short "query_hint": 3-6 word search string that would find this image on the chosen source
  - "topic_hint": the specific subtopic this image question should be about

IMPORTANT RULES:
- Spread image slots across different topics proportionally — do not cluster all slots on one topic
- Reflect {course} exam pattern knowledge: e.g., for NEET PG Surgery → surgical instruments are
  very common; NEET PG PSM → govt program logos/posters; NEET PG Radiology → CT/X-ray heavy;
  NEET PG Psychiatry → almost no image questions (return empty if subject is psychiatry)
- For USMLE: histology and pathology slides are very common; radiology less so than NEET PG
- Be specific: not "X-ray" but "Chest X-ray PA view showing RLL consolidation"
- query_hint must be searchable: 3-6 words, no site names, no adjectives like "labeled/annotated"

Return ONLY a JSON array, no commentary:
[
  {{
    "image_type": "H&E histopathology slide",
    "image_category": "histology",
    "source_strategy": "wikimedia",
    "gemini_ok": false,
    "query_hint": "glomerulonephritis mesangial proliferation H&E",
    "topic_hint": "Glomerulonephritis"
  }},
  ...
]"""

    try:
        raw = _or_call(prompt, model=OR_MAIN_MODEL, max_tokens=2000, temperature=0.1)
        if '```json' in raw:
            raw = raw.split('```json')[1].split('```')[0]
        elif '```' in raw:
            raw = raw.split('```')[1].split('```')[0]
        slots = json.loads(raw.strip())
        if not isinstance(slots, list):
            raise ValueError('planner returned non-list')
        # Trim/pad to exact count
        while len(slots) < total_img_count:
            slots.append({
                'image_type': 'clinical photograph',
                'image_category': 'clinical',
                'source_strategy': IMAGE_SOURCE_GOOGLE,
                'gemini_ok': False,
                'query_hint': f'{subject} clinical finding',
                'topic_hint': topics[0] if topics else subject,
            })
        slots = slots[:total_img_count]
        # Normalise source_strategy values
        valid_strategies = {IMAGE_SOURCE_WIKIMEDIA, IMAGE_SOURCE_OPENNI, IMAGE_SOURCE_WIKIPEDIA,
                            IMAGE_SOURCE_GENERATE, IMAGE_SOURCE_GOOGLE}
        for s in slots:
            if s.get('source_strategy') not in valid_strategies:
                s['source_strategy'] = IMAGE_SOURCE_GOOGLE
        logger.info(f"Image plan for {subject} ({total_img_count} slots): "
                    + ', '.join(s['source_strategy'] for s in slots))
        return slots
    except Exception as e:
        logger.warning(f"Image planner failed ({e}), falling back to google for all slots")
        return [{
            'image_type': 'clinical image',
            'image_category': 'clinical',
            'source_strategy': IMAGE_SOURCE_GOOGLE,
            'gemini_ok': False,
            'query_hint': f'{subject} clinical image',
            'topic_hint': t,
        } for t in (topics * total_img_count)[:total_img_count]]


# ─────────────────────────────────────────────────────────────────────────────
# ALTERNATIVE IMAGE SOURCES
# ─────────────────────────────────────────────────────────────────────────────

def search_wikimedia_commons(query, max_candidates=8):
    """Search Wikimedia Commons for images. Returns list of candidate dicts (url, source, title)."""
    try:
        search_url = 'https://commons.wikimedia.org/w/api.php'
        search_params = {
            'action': 'query', 'list': 'search', 'srsearch': query,
            'srnamespace': 6, 'srlimit': min(max_candidates, 15), 'format': 'json',
        }
        r = requests.get(search_url, params=search_params, timeout=15)
        r.raise_for_status()
        results = r.json().get('query', {}).get('search', [])
        if not results:
            return []

        titles = [res['title'] for res in results]
        info_params = {
            'action': 'query', 'titles': '|'.join(titles[:max_candidates]),
            'prop': 'imageinfo', 'iiprop': 'url|mediatype|extmetadata',
            'iiurlwidth': 900, 'format': 'json',
        }
        r2 = requests.get(search_url, params=info_params, timeout=15)
        r2.raise_for_status()
        pages = r2.json().get('query', {}).get('pages', {})

        candidates = []
        for page in pages.values():
            ii = (page.get('imageinfo') or [{}])[0]
            url = ii.get('url', '')
            mediatype = ii.get('mediatype', '')
            if not url or mediatype == 'DRAWING':
                continue
            ext = url.lower().split('?')[0].rsplit('.', 1)[-1]
            if ext not in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
                continue
            title = page.get('title', '').replace('File:', '')
            candidates.append({'url': url, 'source': 'Wikimedia Commons', 'title': title})
            if len(candidates) >= max_candidates:
                break
        return candidates
    except Exception as e:
        logger.warning(f"Wikimedia Commons search failed: {e}")
        return []


def search_openni_nih(query, max_candidates=8):
    """Search OpenI NIH for medical images. Returns list of candidate dicts."""
    try:
        r = requests.get(
            'https://openi.nlm.nih.gov/api/search',
            params={'query': query, 'm': 1, 'n': max_candidates, 'it': 'x,ct,mri,photo'},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        items = data.get('list', [])
        candidates = []
        for item in items:
            img_url = item.get('imgLarge') or item.get('imgThumb') or item.get('imgUrl', '')
            if not img_url:
                continue
            if img_url.startswith('/'):
                img_url = 'https://openi.nlm.nih.gov' + img_url
            title = item.get('title', query)
            candidates.append({'url': img_url, 'source': 'OpenI NIH', 'title': title})
        return candidates
    except Exception as e:
        logger.warning(f"OpenI NIH search failed: {e}")
        return []


def get_wikipedia_lead_image(article_title):
    """Return a single candidate dict for the Wikipedia article's lead image, or None."""
    try:
        r = requests.get(
            f'https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(article_title)}',
            timeout=10, headers={'User-Agent': 'QBankGenerator/1.0'},
        )
        if r.status_code != 200:
            return None
        data = r.json()
        img = data.get('originalimage') or data.get('thumbnail')
        if not img or not img.get('source'):
            return None
        return {'url': img['source'], 'source': 'Wikipedia', 'title': article_title}
    except Exception as e:
        logger.warning(f"Wikipedia lead image failed for '{article_title}': {e}")
        return None


def _collect_candidates_for_strategy(source_strategy, image_search_terms, image_type, max_candidates=8):
    """
    Dispatch to the right image source based on source_strategy.
    Returns (candidates, raw_count, error_msg).
    """
    query = image_search_terms[0] if image_search_terms else image_type

    if source_strategy == IMAGE_SOURCE_WIKIMEDIA:
        candidates = search_wikimedia_commons(query, max_candidates)
        if not candidates and len(image_search_terms) > 1:
            candidates = search_wikimedia_commons(image_search_terms[1], max_candidates)
        return candidates, len(candidates), None

    elif source_strategy == IMAGE_SOURCE_OPENNI:
        candidates = search_openni_nih(query, max_candidates)
        if not candidates and len(image_search_terms) > 1:
            candidates = search_openni_nih(image_search_terms[1], max_candidates)
        return candidates, len(candidates), None

    elif source_strategy == IMAGE_SOURCE_WIKIPEDIA:
        # Try the first search term as an article title
        result = get_wikipedia_lead_image(query)
        if not result and len(image_search_terms) > 1:
            result = get_wikipedia_lead_image(image_search_terms[1])
        candidates = [result] if result else []
        return candidates, len(candidates), None

    else:  # IMAGE_SOURCE_GOOGLE or IMAGE_SOURCE_GENERATE or unknown
        return collect_candidate_images(image_search_terms, image_type, max_candidates=max_candidates)


def search_and_validate_image(question_data, subject, return_debug=False, source_strategy=None, skip_ai_fallback=False):
    """
    STEP 1: Sanitize search terms
    STEP 2: Collect candidates from the planned source (Wikimedia / OpenI / Wikipedia / Google)
    STEP 3: Validate candidates with Claude Vision (score 0–100 each)
    STEP 4: Use best if ≥80; otherwise generate with Gemini (only when gemini_ok or fallback)
    source_strategy: one of IMAGE_SOURCE_* constants (from the image plan); None → google.
    If return_debug=True, skips cache and returns (result, candidates, google_raw_count, google_error, gemini_error) tuple.
    """
    image_search_terms = question_data.get('image_search_terms', [])
    image_type = question_data.get('image_type', '')
    effective_strategy = source_strategy or question_data.get('_source_strategy') or IMAGE_SOURCE_GOOGLE
    gemini_ok = question_data.get('_gemini_ok', True)  # True = Gemini is an acceptable fallback here

    if not image_search_terms:
        return (None, []) if return_debug else None

    # For 'generate' strategy: skip search entirely, go straight to AI generation
    if effective_strategy == IMAGE_SOURCE_GENERATE:
        if not return_debug:
            cached = get_cached_image(image_search_terms, image_type)
            if cached:
                return cached
        # In fix flow (skip_ai_fallback=True) return None so the caller can use OpenRouter instead
        if skip_ai_fallback:
            return (None, [], 0, None, None) if return_debug else None
        print(f"\n🎨 Generating image (planned): {image_type}")
        gen_result, gemini_error = generate_image_with_gemini(question_data) if gemini_client else (None, 'Gemini not configured')
        if gen_result:
            cache_image(image_search_terms, image_type, gen_result)
            debug_candidates = [{'url': gen_result.get('url',''), 'source': 'Gemini (AI generated)',
                                  'title': 'AI-generated image', 'score': 100,
                                  'reason': 'Planned generate strategy.', 'selected': True}]
            return (gen_result, debug_candidates, 0, None, gemini_error) if return_debug else gen_result
        return (None, [], 0, None, gemini_error) if return_debug else None

    # Check cache first (skip cache when return_debug=True so user sees live candidates)
    if not return_debug:
        cached = get_cached_image(image_search_terms, image_type)
        if cached:
            print(f"✓ Cached image for: {image_search_terms[:2]}")
            return cached

    print(f"\n🔍 Searching image [{effective_strategy}]: {image_type}")

    # STEP 2: Collect candidates from the planned source
    print(f"  → Searching {effective_strategy}...")
    candidates, google_raw_count, google_error = _collect_candidates_for_strategy(
        effective_strategy, image_search_terms, image_type, max_candidates=6)

    # If planned source found nothing, fall back to Google (except when strategy was already google)
    if not candidates and effective_strategy != IMAGE_SOURCE_GOOGLE:
        print(f"  → {effective_strategy} returned nothing, trying Google fallback...")
        candidates, google_raw_count, google_error = collect_candidate_images(
            image_search_terms, image_type, max_candidates=6)

    if not candidates:
        reason_msg = (
            f'{effective_strategy} error: {google_error}' if google_error
            else f'{effective_strategy} returned {google_raw_count} raw result(s) but all unusable'
            if google_raw_count else f'{effective_strategy} returned 0 results'
        )
        gemini_error = None
        if not skip_ai_fallback and gemini_client:
            print(f"  → No candidates found ({reason_msg}), generating with Nano Banana Pro...")
            result, gemini_error = generate_image_with_gemini(question_data)
            if result:
                cache_image(image_search_terms, image_type, result)
                print(f"✓ Generated image")
                debug_candidates = [{'url': result.get('url',''), 'source': 'Gemini (AI generated)',
                                      'title': 'AI-generated image', 'score': 100,
                                      'reason': f'{reason_msg}. Fell back to Gemini generation.',
                                      'selected': True}]
                return (result, debug_candidates, google_raw_count, google_error, gemini_error) if return_debug else result
        else:
            print(f"  → No candidates found ({reason_msg}) and AI fallback not appropriate — skipping")
        return (None, [], google_raw_count, google_error, gemini_error) if return_debug else None

    source_label = candidates[0].get('source', effective_strategy) if candidates else effective_strategy
    print(f"  → Found {len(candidates)} candidate(s) from {source_label}, validating with Claude Vision (parallel, early-exit ≥80)...")

    # STEP 3 & 4: Validate candidates in parallel; stop as soon as one scores ≥ 80
    # Cap at 6 candidates — beyond that we'd just be burning time for marginal gain
    candidates = candidates[:6]
    scored_candidates = []
    _VALIDATION_SCORE_THRESHOLD = 80

    def _validate_one(args):
        idx, candidate = args
        logger.info(f"Validating candidate {idx+1}: {candidate['source']}")
        validation = validate_image_with_claude(candidate['url'], question_data)
        return {**candidate, 'score': validation['score'], 'reason': validation['reason']}

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as vpool:
        futures_map = {vpool.submit(_validate_one, (i, c)): i for i, c in enumerate(candidates)}
        try:
            for fut in concurrent.futures.as_completed(futures_map, timeout=120):
                try:
                    result = fut.result(timeout=5)
                    scored_candidates.append(result)
                    logger.info(f"Score: {result['score']}/100 - {result['reason'][:120]}")
                    print(f"      Score: {result['score']}/100")
                    if result['score'] >= _VALIDATION_SCORE_THRESHOLD:
                        # Cancel remaining — we have a good enough image
                        for pending in futures_map:
                            pending.cancel()
                        break
                except Exception as e:
                    logger.warning(f"Validation future error: {e}")
        except concurrent.futures.TimeoutError:
            logger.warning("Validation pool timed out — using best scored so far")

    if not scored_candidates:
        scored_candidates = [{'score': 0, 'reason': 'all validations failed', **candidates[0]}]

    # Pick best candidate
    best_candidate = max(scored_candidates, key=lambda x: x['score'])
    for c in scored_candidates:
        c['selected'] = False
    scored_candidates_sorted = sorted(scored_candidates, key=lambda x: x['score'], reverse=True)

    def _add_markers(result, question_data):
        """Optionally overlay visual markers on the image."""
        question_text = question_data.get('question', '')
        image_description = question_data.get('image_description', '')
        if not (question_text and image_description):
            return result
        try:
            url = result['url']
            if url.startswith('http'):
                import tempfile
                img_response = requests.get(url, timeout=10)
                if img_response.status_code == 200:
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png', dir='static') as f:
                        f.write(img_response.content)
                        temp_path = f.name
                    marked = add_visual_markers_to_image(temp_path, question_text, image_description)
                    if marked:
                        result['url'] = f"/static/{os.path.basename(marked)}"
                        result['source'] = f"{result['source']} (with markers)"
            elif url.startswith('/static/'):
                local = os.path.join(os.getcwd(), url[1:])
                marked = add_visual_markers_to_image(local, question_text, image_description)
                if marked:
                    result['url'] = f"/static/{os.path.basename(marked)}"
                    result['source'] = f"{result['source']} (with markers)"
        except Exception as e:
            logger.error(f"Marker overlay error: {e}")
        return result

    # STEP 5: Use best if >=80%, otherwise generate with Gemini
    if best_candidate['score'] >= 80:
        print(f"✓ Using internet image (score: {best_candidate['score']}/100)")
        result = {'url': best_candidate['url'], 'source': best_candidate['source'],
                  'title': best_candidate['title']}
        cache_image(image_search_terms, image_type, result)
        result = _add_markers(result, question_data)
        for c in scored_candidates_sorted:
            c['selected'] = (c['url'] == best_candidate['url'])
        if return_debug:
            return result, scored_candidates_sorted, google_raw_count, google_error, None
        return result
    else:
        gemini_error = None
        ai_label = OR_IMAGE_MODEL if skip_ai_fallback else 'Nano Banana Pro'
        print(f"  → Best score only {best_candidate['score']}/100, generating with {ai_label}...")
        if not skip_ai_fallback and gemini_client:
            gen_result, gemini_error = generate_image_with_gemini(question_data)
            if gen_result:
                gen_result = _add_markers(gen_result, question_data)
                cache_image(image_search_terms, image_type, gen_result)
                print(f"✓ Generated image")
                if return_debug:
                    ai_entry = {'url': gen_result.get('url',''), 'source': 'Gemini (AI generated)',
                                'title': 'AI-generated image', 'score': 100,
                                'reason': f'Best Google result scored only {best_candidate["score"]}/100 (threshold: 80). Generated by Gemini instead.',
                                'selected': True}
                    return gen_result, [ai_entry] + scored_candidates_sorted, google_raw_count, google_error, gemini_error
                return gen_result

    # Gemini unavailable or failed — nothing suitable, return no image
    print(f"✗ No suitable image found (best Google score: {best_candidate['score']}/100, Gemini unavailable/failed)")
    if return_debug:
        return None, scored_candidates_sorted, google_raw_count, google_error, gemini_error
    return None


SESSIONS_DIR     = 'sessions'
COURSES_DIR      = 'courses'
EXAM_FORMATS_DIR = 'exam_formats'

def _embed_question_images(questions):
    """
    For each question with a local image_url, read the file and store base64 + media_type
    directly in the question dict so the session JSON is fully self-contained.
    Skips questions that already have embedded data or have no local image.
    """
    import base64 as _b64
    for q in questions:
        url = q.get('image_url', '')
        if not url or url.startswith('http') or q.get('_img_b64'):
            continue
        local = url.lstrip('/')
        try:
            if os.path.isfile(local):
                with open(local, 'rb') as f:
                    raw = f.read()
                q['_img_b64'] = _b64.b64encode(raw).decode('utf-8')
                q['_img_media_type'] = _sniff_media_type(raw)
        except Exception as e:
            logger.warning(f"Could not embed image {local}: {e}")
    return questions


def _restore_question_images(questions):
    """
    On session load: for questions with embedded _img_b64, restore the local file
    if it no longer exists, then clear the b64 from the returned payload (keep on disk only).
    """
    import base64 as _b64
    for q in questions:
        b64 = q.get('_img_b64')
        url = q.get('image_url', '')
        if not b64 or not url or url.startswith('http'):
            continue
        local = url.lstrip('/')
        if not os.path.isfile(local):
            try:
                os.makedirs(os.path.dirname(local) or '.', exist_ok=True)
                with open(local, 'wb') as f:
                    f.write(_b64.b64decode(b64))
                logger.info(f"Restored image from session: {local}")
            except Exception as e:
                logger.warning(f"Could not restore image {local}: {e}")
    return questions


def save_qbank_session(questions, course, subject, topics, image_stats=None, session_id=None):
    """Persist a QBank generation to sessions/ as a JSON file and return the session id."""
    import copy
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    existing_created = None
    if session_id:
        existing_path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
        if os.path.isfile(existing_path):
            try:
                with open(existing_path) as f:
                    existing_created = json.load(f).get('created_at')
            except Exception:
                pass
    else:
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    # Deep-copy so we don't mutate in-flight question objects
    questions_to_save = copy.deepcopy(questions)
    _embed_question_images(questions_to_save)

    filename = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    session = {
        'session_id': session_id,
        'created_at': existing_created or datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat(),
        'type': 'qbank',
        'course': course,
        'subject': subject,
        'topics': topics,
        'question_count': len(questions_to_save),
        'image_stats': image_stats,
        'questions': questions_to_save,
    }
    try:
        with open(filename, 'w') as f:
            json.dump(session, f, indent=2)
        embedded = sum(1 for q in questions_to_save if q.get('_img_b64'))
        logger.info(f"Session {'updated' if existing_created else 'saved'}: {filename} ({embedded} images embedded)")
    except Exception as e:
        logger.error(f"Failed to save session: {e}")
    return session_id


def _embed_lesson_images(lessons_data):
    """
    Walk lesson markdown/HTML, find local /static/ image URLs, and embed them as base64
    in a top-level _images dict keyed by path. Lessons stay text-only; images are
    restored on load via _restore_lesson_images.
    """
    import base64 as _b64
    images = {}
    for lesson in lessons_data.get('lessons', []):
        texts = [lesson.get('topic_lesson', '')]
        for ch in lesson.get('chapters', []):
            texts.append(ch.get('lesson', '') or '')
        for text in texts:
            for url, _ in _extract_image_urls_from_lesson(str(text)):
                if url and not url.startswith('http') and url not in images:
                    local = url.lstrip('/')
                    try:
                        if os.path.isfile(local):
                            with open(local, 'rb') as f:
                                raw = f.read()
                            images[url] = {
                                'b64': _b64.b64encode(raw).decode('utf-8'),
                                'media_type': _sniff_media_type(raw),
                            }
                    except Exception as e:
                        logger.warning(f"Could not embed lesson image {local}: {e}")
    return images


def _restore_lesson_images(images_dict):
    """Restore local /static/ image files from the embedded dict if they're missing."""
    import base64 as _b64
    for url, data in (images_dict or {}).items():
        local = url.lstrip('/')
        if not os.path.isfile(local):
            try:
                os.makedirs(os.path.dirname(local) or '.', exist_ok=True)
                with open(local, 'wb') as f:
                    f.write(_b64.b64decode(data['b64']))
                logger.info(f"Restored lesson image: {local}")
            except Exception as e:
                logger.warning(f"Could not restore lesson image {local}: {e}")


def save_lesson_session(lessons_data, course, subject, session_id=None):
    """Persist a Lessons generation to sessions/ as a JSON file and return the session id."""
    import copy
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    existing_created = None
    if session_id:
        existing_path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
        if os.path.isfile(existing_path):
            try:
                with open(existing_path) as f:
                    existing_created = json.load(f).get('created_at')
            except Exception:
                pass
    else:
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    topics = [l.get('topic', '') for l in lessons_data.get('lessons', [])]
    embedded_images = _embed_lesson_images(lessons_data)
    session = {
        'session_id': session_id,
        'created_at': existing_created or datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat(),
        'type': 'lessons',
        'course': course,
        'subject': subject,
        'topics': topics,
        'lesson_count': len(topics),
        'question_count': 0,
        'lessons_data': lessons_data,
        '_images': embedded_images,
    }
    try:
        with open(filename, 'w') as f:
            json.dump(session, f, indent=2)
        logger.info(f"Lesson session {'updated' if existing_created else 'saved'}: {filename} ({len(embedded_images)} images embedded)")
    except Exception as e:
        logger.error(f"Failed to save lesson session: {e}")
    return session_id


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
    def _norm_blooms_keys(raw):
        out = {}
        for k, v in raw.items():
            try:
                out[int(str(k).split('_')[0])] = v
            except (ValueError, IndexError):
                pass
        return out

    if exam_format and 'blooms_distribution' in exam_format:
        blooms_raw = _norm_blooms_keys(exam_format['blooms_distribution'])
        blooms_percentages = {l: blooms_raw.get(l, 0) for l in range(1, 6)}
        total_pct = sum(blooms_percentages.values()) or 100
        bloom_distribution = {}
        total_assigned = 0
        for level in range(1, 6):
            pct = blooms_percentages[level] / total_pct * 100
            count = round(num_questions * pct / 100)
            bloom_distribution[level] = max(count, 0)
            total_assigned += bloom_distribution[level]
        if total_assigned != num_questions:
            best = max(range(1, 6), key=lambda l: blooms_percentages[l])
            bloom_distribution[best] += num_questions - total_assigned
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

4. CLINICAL VIGNETTE STRUCTURE (for Bloom's L3/L4/L5 questions):
   Use this exact format for the question stem:
   "A [age]-year-old [male/female] presents with [complaint]. [1-2 sentences of relevant
   history and examination findings]. [1 investigation result if relevant].
   [Single specific question ending in '?']"
   Bloom's L1/L2 may use direct knowledge questions without a full vignette.

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


# ── QBank parallel batch helpers ──────────────────────────────────────────────

def _compute_qbank_batches(bloom_distribution, difficulty_distribution, num_image_questions, num_questions):
    """
    Split question generation into per-Bloom's-level parallel batches (max 8 each).
    Returns list of dicts: {bloom_level, count, img_count, diff_dist}
    """
    MAX_BATCH = 8
    batches = []

    # Build one batch per active Bloom's level (split if >MAX_BATCH)
    for level in range(1, 6):
        remaining = bloom_distribution.get(level, 0)
        while remaining > 0:
            batch_n = min(remaining, MAX_BATCH)
            batches.append({'bloom_level': level, 'count': batch_n, 'img_count': 0, 'diff_dist': {}})
            remaining -= batch_n

    if not batches:
        return []

    # Concentrate image slots in L3/L4/L5 batches (clinical vignette levels)
    # Images make no sense on L1/L2 recall batches
    visual_batches = [b for b in batches if b['bloom_level'] >= 3]
    non_visual_batches = [b for b in batches if b['bloom_level'] < 3]
    if not visual_batches:
        visual_batches = batches  # fallback: distribute across all

    visual_total = sum(b['count'] for b in visual_batches)
    img_assigned = 0
    for b in visual_batches[:-1]:
        img_n = min(round(num_image_questions * b['count'] / visual_total), b['count'])
        b['img_count'] = img_n
        img_assigned += img_n
    visual_batches[-1]['img_count'] = max(0, min(num_image_questions - img_assigned, visual_batches[-1]['count']))
    for b in non_visual_batches:
        b['img_count'] = 0

    # Difficulty sub-distribution proportional to batch count
    for b in batches:
        n = b['count']
        diff = {}
        d_total = 0
        for d in [1, 2, 3]:
            cnt = max(0, round(difficulty_distribution.get(d, 0) * n / num_questions))
            diff[d] = cnt
            d_total += cnt
        adj = n - d_total
        if adj > 0:
            diff[2] += adj
        elif adj < 0:
            for d in [3, 2, 1]:
                dec = min(abs(adj), diff[d])
                diff[d] -= dec
                adj += dec
                if adj == 0:
                    break
        b['diff_dist'] = diff

    return batches


def _run_single_qbank_batch(course, subject, topic, batch_spec, exam_format, include_images, existing_summaries=None, reference_examples=None, image_slots=None):
    """
    Call Claude for one Bloom's-level batch. Returns list of question dicts (no images yet).
    """
    bloom_level = batch_spec['bloom_level']
    count       = batch_spec['count']
    img_count   = batch_spec['img_count']
    diff_dist   = batch_spec['diff_dist']
    bloom_labels = {1: 'Remember', 2: 'Understand', 3: 'Apply', 4: 'Analyze', 5: 'Evaluate'}
    bloom_name  = bloom_labels.get(bloom_level, 'Apply')

    if exam_format:
        qf = exam_format.get('question_format', {})
        num_options    = qf.get('num_options') or exam_format.get('num_options') or 4
        question_style = qf.get('type') or exam_format.get('question_style') or 'Single best answer'
        typical_length = qf.get('avg_stem_words') or exam_format.get('typical_length') or 'Medium length scenarios'
        emphasis       = exam_format.get('emphasis') or exam_format.get('domain_characteristics', {}).get('key_features') or []
        dc             = exam_format.get('domain_characteristics', {})
        domain_context = dc.get('domain') or exam_format.get('domain') or 'professional examination'
    else:
        num_options    = 4
        question_style = 'Single best answer'
        typical_length = 'Medium length scenarios'
        emphasis       = []
        domain_context = 'professional examination'

    option_labels  = [chr(65 + i) for i in range(num_options)]
    emphasis_text  = "\n   - " + "\n   - ".join(emphasis) if emphasis else ""
    diff_lines     = (
        f"- Difficulty 1 (Medium): {diff_dist.get(1, 0)} questions\n"
        f"- Difficulty 2 (Hard):   {diff_dist.get(2, 0)} questions\n"
        f"- Difficulty 3 (Very Hard): {diff_dist.get(3, 0)} questions"
    )

    prompt = f"""You are an expert educator creating MCQs for {course} ({domain_context}).

EXAM FORMAT REQUIREMENTS FOR {course}:
- Number of options: {num_options} ({', '.join(option_labels)})
- Question style: {question_style}
- Typical length: {typical_length}
- Key emphasis areas: {emphasis_text if emphasis_text else "Professional standards"}

Generate exactly {count} unique, high-quality MCQs following {course} examination standards.

SUBJECT: {subject}
TOPIC: {topic}

BLOOM'S LEVEL — ALL {count} questions in this batch MUST be Bloom's Level {bloom_level} ({bloom_name}):
- Bloom's Level {bloom_level} ({bloom_name}): {count} questions

DIFFICULTY DISTRIBUTION (MANDATORY - must follow exactly):
{diff_lines}

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

4. CLINICAL VIGNETTE STRUCTURE (for Bloom's L3/L4/L5 questions):
   Use this exact format for the question stem:
   "A [age]-year-old [male/female] presents with [complaint]. [1-2 sentences of relevant
   history and examination findings]. [1 investigation result if relevant].
   [Single specific question ending in '?']"
   Bloom's L1/L2 may use direct knowledge questions without a full vignette.

OUTPUT FORMAT (JSON array):
[
  {{
    "question": "Question text here",
    "options": [{', '.join([f'"Option {label}"' for label in option_labels])}],
    "correct_option": "{option_labels[0]}",
    "explanation": "Detailed explanation of correct answer",
    "blooms_level": {bloom_level},
    "difficulty": 1,
    "course": "{course}",
    "subject": "{subject}",
    "topic": "{topic}",
    "tags": ["{course}"]
  }}
]

CRITICAL REQUIREMENTS:
- MUST have EXACTLY {num_options} options per question (not more, not less)
- "blooms_level": MUST be {bloom_level} for ALL questions in this batch
- "difficulty": Must be 1 (Medium), 2 (Hard), or 3 (Very Hard)
- Follow the difficulty distribution requirements above
- "course", "subject", and "topic" are separate fields
- "tags": Array containing ONLY the course name (e.g., ["{course}"])
- correct_option must be one of: {', '.join(option_labels)}
{"AVOID DUPLICATES — the following questions have ALREADY been generated for this topic. Do NOT repeat the same clinical scenario, drug, condition, investigation, or core concept tested:" + chr(10) + chr(10).join("- " + s for s in existing_summaries) + chr(10) + "Each new question MUST test a DIFFERENT aspect or scenario." if existing_summaries else ""}
Generate ONLY the JSON array, no additional text."""

    # Inject reference examples (PYQs) if provided
    if reference_examples:
        ref_block = "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        ref_block += "REFERENCE: PREVIOUS YEAR / SAMPLE QUESTIONS\n"
        ref_block += "Study these carefully. Match their EXACT style — question length, clinical scenario depth, distractor quality, terminology, and level of detail.\n\n"
        for i, ex in enumerate(reference_examples[:6], 1):
            if isinstance(ex, dict):
                q = ex.get('question', '')[:300]
                opts = ex.get('options', [])
                ans = ex.get('correct_option', '')
                opts_str = '  '.join(f"{chr(64+j+1)}) {o}" for j, o in enumerate(opts[:5]))
                ref_block += f"Example {i}:\nQ: {q}\n{opts_str}\nAnswer: {ans}\n\n"
            elif isinstance(ex, str):
                ref_block += f"Example {i}:\n{ex[:400]}\n\n"
        ref_block += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        prompt = prompt.replace(
            "Generate ONLY the JSON array, no additional text.",
            ref_block + "\nGenerate ONLY the JSON array, no additional text."
        )

    # Append image instructions if this batch has image questions
    if include_images and img_count > 0:
        # Build slot-specific instructions when a plan exists; fall back to generic otherwise
        if image_slots and len(image_slots) >= img_count:
            batch_slots = image_slots[:img_count]
            slot_lines = '\n'.join(
                f"  • Image Q{i+1}: {s['image_type']} — topic: {s.get('topic_hint', topic)} — search hint: {s.get('query_hint', '')}"
                for i, s in enumerate(batch_slots)
            )
            image_instructions = f"""

IMPORTANT: Out of {count} questions, EXACTLY {img_count} must be IMAGE-BASED questions (the rest text-only).
The image types are PRE-PLANNED — you MUST write questions that require exactly these images:

{slot_lines}

Write each image question so that identifying the specific visual finding in the planned image type is REQUIRED to answer it correctly.

━━━ STRICT IMAGE NECESSITY RULE ━━━
An image-based question is ONLY valid if the image is ABSOLUTELY NECESSARY to answer it.
→ If the question is answerable from text alone → it MUST be text-only. Do NOT add image fields.

For the {img_count} IMAGE-BASED questions, add these fields:
- "image_description": PRECISE description of the KEY diagnostic finding visible in the image
- "image_search_terms": Array of 1-3 search queries. Rules: (a) 2-5 words only, (b) anatomy/pathology terms, (c) NO site names, (d) NO "annotated/labeled/diagram/unlabeled". Best query first.
- "image_type": Use EXACTLY the planned image type string listed above
- "key_finding": Single sentence — the specific visual finding the student must identify

For image-based question stems:
• Reference the image as "(Image N)" or "shown in Image N" — NEVER add a qualifier after the number such as "— schematic diagram", "— photograph", "— illustration", or any other descriptor
• Name the modality in natural prose: "A peripheral blood smear is shown (Image 1)", "The ECG tracing (Image 1) demonstrates…", "This H&E slide (Image 1) is from…"
• Do NOT describe the finding in the stem — the finding must be read FROM the image
• The stem should present clinical context; the IMAGE provides the diagnostic finding"""
        else:
            image_instructions = f"""

IMPORTANT: Out of {count} questions, EXACTLY {img_count} must be IMAGE-BASED questions (the rest text-only).

━━━ STRICT IMAGE NECESSITY RULE ━━━
An image-based question is ONLY valid if the image is ABSOLUTELY NECESSARY to answer it.
Ask yourself: "Could a student answer this question correctly without seeing any image?"
→ If YES → it MUST be a text-only question. Do NOT add image fields.
→ If NO (the answer requires identifying a specific visual finding) → it qualifies as image-based.

VALID image-based scenarios (answer requires the image):
• "Identify the pathology in this H&E slide" (answer depends on which cells/pattern are visible)
• "What does this ECG show?" (answer depends on the rhythm/morphology in the tracing)
• "What is the diagnosis based on this chest X-ray?" (answer depends on the specific opacity/pattern)
• "Identify the structure indicated in this cross-sectional anatomy image"
INVALID (decorative — the question is answerable from text alone):
• A clinical vignette that fully describes findings in text and then says "see image" (image adds nothing)
• "A patient has fever, cough, and RLL consolidation on CXR — what is the diagnosis?" (text already tells the answer)
• Any question where removing the image does not change the answer

For the {img_count} IMAGE-BASED questions, add these fields:
- "image_description": PRECISE description of the KEY diagnostic finding visible in the image
- "image_search_terms": Array of 1-3 search queries. Rules: (a) 2-5 words only, (b) anatomy/pathology terms only, (c) NEVER include site names like "Wikimedia Commons", "Open-i", "PubMed", "Radiopaedia", (d) NEVER include "annotated", "labeled", "diagram", "unlabeled". Put the single best query first.
- "image_type": Imaging modality only (e.g., "Chest X-ray PA view", "Brain MRI T2", "12-lead ECG", "H&E histopathology slide", "CT abdomen axial", "Gross anatomy cross-section"). NEVER include "Labeled", "Annotated", or "Unlabeled".
- "key_finding": Single sentence — the specific visual finding the student must identify to answer correctly

For image-based question stems:
• Reference the image as "(Image N)" or "shown in Image N" — NEVER add a qualifier after the number such as "— schematic diagram", "— photograph", "— illustration", or any other descriptor
• Name the modality in natural prose: "A peripheral blood smear is shown (Image 1)", "The ECG tracing (Image 1) demonstrates…", "This H&E slide (Image 1) is from…"
• Do NOT describe the finding in the stem — the finding must be read FROM the image
• The stem should present the clinical context; the IMAGE provides the diagnostic finding
• Do NOT say "based on the image shown" generically — specify the modality"""

        prompt = prompt.replace(
            "Generate ONLY the JSON array, no additional text.",
            image_instructions + "\n\nGenerate ONLY the JSON array, no additional text."
        )

    # Each question ~1000 tokens output (long stems + 5 options + explanation), floor 6000
    tokens_needed = max(6000, count * 1200 + (len(existing_summaries) * 30 if existing_summaries else 0))
    response_text = _or_call(prompt, max_tokens=min(tokens_needed, 16000), temperature=0.2)
    if '```json' in response_text:
        response_text = response_text.split('```json')[1].split('```')[0]
    elif '```' in response_text:
        response_text = response_text.split('```')[1].split('```')[0]

    questions = json.loads(response_text.strip())
    if not isinstance(questions, list):
        raise ValueError(f'Invalid response format for Bloom level {bloom_level}')
    return questions


# ─────────────────────────────────────────────────────────────────────────────

def generate_for_topic(course, subject, topic, num_questions, include_images=False, exam_format=None, existing_questions=None, reference_examples=None, image_count_override=None, image_plan=None):
    """Generate questions for a single topic using parallel Bloom's-level batches."""
    from concurrent.futures import ThreadPoolExecutor as _QTP, as_completed as _QAC

    # ── Bloom's distribution ──────────────────────────────────────────────────
    # Normalise keys: "1_remember" → 1, "1" → 1
    def _normalise_blooms(raw):
        out = {}
        for k, v in raw.items():
            try:
                out[int(str(k).split('_')[0])] = v
            except (ValueError, IndexError):
                pass
        return out

    if exam_format and 'blooms_distribution' in exam_format:
        blooms_raw = _normalise_blooms(exam_format['blooms_distribution'])
        # Only use levels 1-5
        blooms_pct = {l: blooms_raw.get(l, 0) for l in range(1, 6)}
        total_pct = sum(blooms_pct.values()) or 100
        bloom_distribution = {}
        total_assigned = 0
        for level in range(1, 6):
            pct = blooms_pct[level] / total_pct * 100
            cnt = round(num_questions * pct / 100)
            bloom_distribution[level] = max(cnt, 0)
            total_assigned += bloom_distribution[level]
        # Fix rounding: adjust the level with highest percentage
        if total_assigned != num_questions:
            best = max(range(1, 6), key=lambda l: blooms_pct[l])
            bloom_distribution[best] += num_questions - total_assigned
    else:
        per_level = num_questions // 5
        rem = num_questions % 5
        bloom_distribution = {l: per_level + (1 if rem > l - 1 else 0) for l in range(1, 6)}

    # ── Difficulty distribution ───────────────────────────────────────────────
    per_diff  = num_questions // 3
    diff_rem  = num_questions % 3
    difficulty_distribution = {
        1: per_diff + (1 if diff_rem > 0 else 0),
        2: per_diff + (1 if diff_rem > 1 else 0),
        3: per_diff,
    }

    # ── Image count ───────────────────────────────────────────────────────────
    num_image_questions = 0
    if include_images:
        if image_count_override is not None:
            # Caller computed the exact count at subject level — use it directly
            num_image_questions = min(num_questions, image_count_override)
            logger.info(f"Including {num_image_questions}/{num_questions} image-based questions (subject-level override for {subject})")
        else:
            ef = exam_format or {}
            overall_pct = (
                ef.get('question_format', {}).get('image_questions_percentage')
                or ef.get('image_questions_percentage')
                or ef.get('image_percentage')
                or 0
            )
            image_by_subject = ef.get('image_percentage_by_subject', {})
            subject_pct = overall_pct
            for subj, pct in image_by_subject.items():
                if subj.lower() in subject.lower() or subject.lower() in subj.lower():
                    subject_pct = pct
                    break
            if subject_pct == 0 and include_images:
                subject_pct = 20
            num_image_questions = min(num_questions, math.ceil(num_questions * subject_pct / 100))
            logger.info(f"Including {num_image_questions}/{num_questions} image-based questions ({subject_pct}% for {subject})")

    # ── Summarise existing questions for duplicate avoidance ─────────────────
    # Use the 25 most-recent questions across all subjects/topics. This is
    # enough context to catch nearby duplicates without bloating the prompt
    # (which causes the LLM to generate fewer questions for later subjects).
    # A post-generation Jaccard dedup pass handles any stragglers.
    existing_summaries = None
    if existing_questions:
        recent = existing_questions[-25:]  # last 25 across all subjects
        existing_summaries = [
            q['question'][:100].replace('\n', ' ')
            for q in recent
            if q.get('question')
        ] or None

    # ── Build parallel batch specs ────────────────────────────────────────────
    batch_specs = _compute_qbank_batches(bloom_distribution, difficulty_distribution, num_image_questions, num_questions)
    logger.info(
        f"   📦 {len(batch_specs)} parallel batch(es) for '{topic}': "
        + ", ".join(f"L{b['bloom_level']}×{b['count']}" for b in batch_specs)
    )

    # ── Distribute image_plan slots across bloom batches (by img_count order) ─
    plan_slots = list(image_plan) if image_plan else []
    slot_cursor = 0
    spec_slots = {}  # spec bloom_level → list of slots
    for spec in sorted(batch_specs, key=lambda s: s['bloom_level']):
        n = spec.get('img_count', 0)
        spec_slots[spec['bloom_level']] = plan_slots[slot_cursor:slot_cursor + n]
        slot_cursor += n

    # ── Fire all Bloom's-level batches in parallel ────────────────────────────
    _BATCH_TIMEOUT = 240  # 4 min per Bloom's batch — hard ceiling
    all_questions = []
    with _QTP(max_workers=len(batch_specs)) as pool:
        future_to_spec = {
            pool.submit(
                _run_single_qbank_batch,
                course, subject, topic, spec, exam_format, include_images,
                existing_summaries, reference_examples,
                spec_slots.get(spec['bloom_level'], [])
            ): spec
            for spec in batch_specs
        }
        for future in _QAC(future_to_spec, timeout=_BATCH_TIMEOUT):
            spec = future_to_spec[future]
            try:
                qs = future.result(timeout=10)  # result already computed by as_completed
                logger.info(f"   ✓ L{spec['bloom_level']} batch returned {len(qs)} question(s)")
                all_questions.extend(qs)
            except concurrent.futures.TimeoutError:
                logger.error(f"   ✗ L{spec['bloom_level']} batch timed out after {_BATCH_TIMEOUT}s — skipping")
            except Exception as e:
                logger.error(f"   ✗ L{spec['bloom_level']} batch failed: {e}")

    # ── Tag image questions with source_strategy from the plan ───────────────
    if include_images and plan_slots:
        img_q_indices = [i for i, q in enumerate(all_questions) if q.get('image_search_terms')]
        for slot_i, q_idx in enumerate(img_q_indices):
            if slot_i < len(plan_slots):
                slot = plan_slots[slot_i]
                all_questions[q_idx]['_source_strategy'] = slot.get('source_strategy', IMAGE_SOURCE_GOOGLE)
                all_questions[q_idx]['_gemini_ok'] = slot.get('gemini_ok', True)

    # ── Fetch images in parallel for all image-tagged questions ──────────────
    if include_images:
        image_candidates = [
            (idx, q) for idx, q in enumerate(all_questions)
            if q.get('image_search_terms') and len(q.get('image_search_terms', [])) > 0
        ]
        logger.info(f"Fetching images for {len(image_candidates)} image-tagged question(s)...")

        def _fetch_q_image(args):
            idx, q = args
            result = search_and_validate_image(q, subject)
            if result:
                _download_and_cache_image(result)  # ensure local /static/ copy
                q['image_url']    = result['url']
                q['image_source'] = result['source']
            else:
                q['image_url']   = None
                q['needs_image'] = True
            return idx, q

        if image_candidates:
            _IMG_TIMEOUT = 180  # 3 min per image question (Google + up to 10 Claude scores + Gemini)
            with _QTP(max_workers=min(len(image_candidates), 4)) as img_pool:
                futures = {img_pool.submit(_fetch_q_image, arg): arg for arg in image_candidates}
                for future in concurrent.futures.as_completed(futures, timeout=_IMG_TIMEOUT * len(image_candidates)):
                    try:
                        idx, q = future.result(timeout=10)
                        all_questions[idx] = q
                    except concurrent.futures.TimeoutError:
                        logger.warning("Image fetch timed out for a question — skipping image")
                    except Exception as e:
                        logger.warning(f"Image fetch failed: {e}")

        images_found = sum(1 for q in all_questions if q.get('image_url'))
        logger.info(f"Image fetch complete: {images_found}/{len(image_candidates)} found")

    return all_questions


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
    topics = data.get('topics', [])
    num_questions = data.get('num_questions', 20)  # Default 20 per topic
    include_images = data.get('include_images', False)
    subject_image_count = data.get('subject_image_count')  # Total image Qs for the whole subject
    exam_format = data.get('exam_format')
    existing_questions = data.get('existing_questions', [])  # For append mode
    reference_examples = data.get('reference_examples', [])  # PYQ / sample questions

    logger.info(f"Received exam_format: {exam_format}")
    if exam_format:
        logger.info(f"  num_options in exam_format: {exam_format.get('num_options', 'NOT FOUND')}")
    if reference_examples:
        logger.info(f"  Reference examples provided: {len(reference_examples)}")

    if not all([course, subject]) or not topics:
        return jsonify({'error': 'Missing required fields'}), 400

    if num_questions < 1:
        return jsonify({'error': 'num_questions must be at least 1'}), 400

    try:
        all_questions = []
        num_options = exam_format.get('num_options', 4) if exam_format else 4
        num_topics = len(topics)
        logger.info(f"Generating {num_questions} questions per topic for {num_topics} topics (existing: {len(existing_questions)})")
        logger.info(f"  Format: {num_options} options, images={include_images}, subject_image_count={subject_image_count}")

        # ── Image planning step ───────────────────────────────────────────────
        # Compute total image count first so we can plan before generation.
        total_image_count = 0
        if include_images:
            if subject_image_count is not None:
                total_image_count = subject_image_count
            else:
                ef = exam_format or {}
                overall_pct = (
                    ef.get('question_format', {}).get('image_questions_percentage')
                    or ef.get('image_questions_percentage')
                    or ef.get('image_percentage')
                    or 20
                )
                total_image_count = min(
                    num_questions * num_topics,
                    math.ceil(num_questions * num_topics * overall_pct / 100)
                )

        subject_image_plan = []
        if include_images and total_image_count > 0:
            logger.info(f"  🗂  Running image planner for {subject} ({total_image_count} image slots)...")
            subject_image_plan = plan_image_questions(course, subject, topics, total_image_count)
            logger.info(f"  🗂  Image plan complete: {len(subject_image_plan)} slots")

        # ── Distribute subject-level image quota and plan slots across topics ─
        def _image_count_for_topic(topic_idx):
            if not include_images:
                return 0
            if subject_image_count is not None:
                base = subject_image_count // num_topics
                extra = 1 if topic_idx < (subject_image_count % num_topics) else 0
                return min(num_questions, base + extra)
            return None  # None = let generate_for_topic calculate from exam_format

        def _plan_for_topic(topic_idx):
            """Slice the subject-level image plan for this topic."""
            if not subject_image_plan:
                return []
            slots_per_topic = len(subject_image_plan) // num_topics
            extra = 1 if topic_idx < (len(subject_image_plan) % num_topics) else 0
            start = topic_idx * slots_per_topic + min(topic_idx, len(subject_image_plan) % num_topics)
            count = slots_per_topic + extra
            return subject_image_plan[start:start + count]

        from concurrent.futures import ThreadPoolExecutor as _TQP, as_completed as _TAC
        def _gen_topic(args):
            topic_idx, t = args
            img_override = _image_count_for_topic(topic_idx)
            topic_plan = _plan_for_topic(topic_idx)
            return generate_for_topic(course, subject, t, num_questions, include_images, exam_format, existing_questions, reference_examples, img_override, topic_plan)

        _TOPIC_TIMEOUT = 300  # 5 min per topic — hard ceiling
        indexed_topics = list(enumerate(topics))
        if len(topics) == 1:
            all_questions = _gen_topic(indexed_topics[0])
        else:
            logger.info(f"  🚀 Running {len(topics)} topics in parallel...")
            with _TQP(max_workers=min(len(topics), 8)) as topic_pool:
                futures = {topic_pool.submit(_gen_topic, arg): arg for arg in indexed_topics}
                try:
                    for future in _TAC(futures, timeout=_TOPIC_TIMEOUT * len(topics)):
                        try:
                            all_questions.extend(future.result(timeout=10))
                        except concurrent.futures.TimeoutError:
                            logger.error(f"  ✗ Topic timed out — skipping")
                        except Exception as e:
                            logger.error(f"  ✗ Topic failed: {e}")
                except concurrent.futures.TimeoutError:
                    logger.error(f"  ✗ Topic pool overall timeout ({_TOPIC_TIMEOUT * len(topics)}s) — returning partial results")

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

        # Session is saved manually by user via the Save button — no auto-save here
        session_id = None

        response_data = {
            'success': True,
            'questions': all_questions,
            'count': len(all_questions),
            'topics_count': len(topics),
            'review_file': review_file,
            'session_id': session_id,
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


@app.route('/api/sessions', methods=['GET'])
def list_sessions():
    """List all saved QBank sessions (metadata only, no questions)."""
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    sessions = []
    try:
        for fname in sorted(os.listdir(SESSIONS_DIR), reverse=True):
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(SESSIONS_DIR, fname)
            try:
                with open(fpath, 'r') as f:
                    data = json.load(f)
                sessions.append({
                    'session_id': data.get('session_id', fname[:-5]),
                    'created_at': data.get('created_at'),
                    'course': data.get('course'),
                    'subject': data.get('subject'),
                    'topics': data.get('topics', []),
                    'question_count': data.get('question_count', 0),
                })
            except Exception:
                continue
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify(sessions)


# ── Saved course structures ───────────────────────────────────────────────────

@app.route('/api/courses', methods=['GET'])
def list_courses():
    """Return metadata for all saved course structures, newest first."""
    os.makedirs(COURSES_DIR, exist_ok=True)
    courses = []
    for fname in sorted(os.listdir(COURSES_DIR), reverse=True):
        if not fname.endswith('.json'):
            continue
        fpath = os.path.join(COURSES_DIR, fname)
        try:
            with open(fpath, 'r') as f:
                data = json.load(f)
            subjects = data.get('structure', {}).get('subjects', [])
            topic_count = sum(len(s.get('topics', [])) for s in subjects)
            courses.append({
                'id':           data['id'],
                'course_name':  data['course_name'],
                'saved_at':     data['saved_at'],
                'subject_count': len(subjects),
                'topic_count':  topic_count,
            })
        except Exception:
            continue
    return jsonify(courses)


@app.route('/api/courses/save', methods=['POST'])
def save_course():
    """Persist a course structure — one record per course name (upsert by course name)."""
    os.makedirs(COURSES_DIR, exist_ok=True)
    body = request.json or {}
    structure = body.get('structure')
    course_name = (body.get('course_name', (structure or {}).get('Course', 'Unknown')) or 'Unknown').strip()
    if not structure:
        return jsonify({'error': 'structure required'}), 400

    # Upsert: overwrite existing record for this course name
    existing_path = None
    existing_id = None
    for fname in os.listdir(COURSES_DIR):
        if not fname.endswith('.json'):
            continue
        try:
            with open(os.path.join(COURSES_DIR, fname)) as f:
                d = json.load(f)
            if d.get('course_name', '').strip().lower() == course_name.lower():
                existing_path = os.path.join(COURSES_DIR, fname)
                existing_id = d['id']
                break
        except Exception:
            continue

    course_id = existing_id or f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}"
    fpath = existing_path or os.path.join(COURSES_DIR, f'{course_id}.json')
    record = {
        'id':          course_id,
        'course_name': course_name,
        'saved_at':    datetime.now().isoformat(),
        'structure':   structure,
    }
    with open(fpath, 'w') as f:
        json.dump(record, f, indent=2)
    logger.info(f"{'Updated' if existing_path else 'Saved'} course structure: {course_name} → {fpath}")
    return jsonify({'id': course_id, 'course_name': course_name})


@app.route('/api/courses/<course_id>', methods=['GET'])
def get_course(course_id):
    """Load a saved course structure by id."""
    fpath = os.path.join(COURSES_DIR, f'{course_id}.json')
    if not os.path.exists(fpath):
        return jsonify({'error': 'Not found'}), 404
    with open(fpath, 'r') as f:
        data = json.load(f)
    return jsonify(data)


@app.route('/api/courses/<course_id>', methods=['DELETE'])
def delete_course(course_id):
    """Delete a saved course structure."""
    fpath = os.path.join(COURSES_DIR, f'{course_id}.json')
    if not os.path.exists(fpath):
        return jsonify({'error': 'Not found'}), 404
    os.remove(fpath)
    return jsonify({'ok': True})


# ── Saved exam formats ────────────────────────────────────────────────────────

@app.route('/api/exam-formats', methods=['GET'])
def list_exam_formats():
    """Return metadata for all saved exam formats, newest first."""
    os.makedirs(EXAM_FORMATS_DIR, exist_ok=True)
    formats = []
    for fname in sorted(os.listdir(EXAM_FORMATS_DIR), reverse=True):
        if not fname.endswith('.json'):
            continue
        try:
            with open(os.path.join(EXAM_FORMATS_DIR, fname)) as f:
                data = json.load(f)
            ef = data.get('exam_format', {})
            qf = ef.get('question_format', {})
            formats.append({
                'id':          data['id'],
                'course_name': data['course_name'],
                'saved_at':    data['saved_at'],
                'num_options': qf.get('num_options', ef.get('num_options', 4)),
                'question_style': qf.get('type', ef.get('question_style', '')),
                'image_pct':   qf.get('image_questions_percentage', ef.get('image_questions_percentage', 0)),
            })
        except Exception:
            continue
    return jsonify(formats)


@app.route('/api/exam-formats/save', methods=['POST'])
def save_exam_format_api():
    """Persist an exam format — one record per course name (upsert by course name)."""
    os.makedirs(EXAM_FORMATS_DIR, exist_ok=True)
    body = request.json or {}
    exam_format = body.get('exam_format')
    course_name = (body.get('course_name', 'Unknown') or 'Unknown').strip()
    if not exam_format:
        return jsonify({'error': 'exam_format required'}), 400

    # Check if a record for this course already exists — if so, overwrite it
    existing_path = None
    existing_id = None
    for fname in os.listdir(EXAM_FORMATS_DIR):
        if not fname.endswith('.json'):
            continue
        try:
            with open(os.path.join(EXAM_FORMATS_DIR, fname)) as f:
                d = json.load(f)
            if d.get('course_name', '').strip().lower() == course_name.lower():
                existing_path = os.path.join(EXAM_FORMATS_DIR, fname)
                existing_id = d['id']
                break
        except Exception:
            continue

    fmt_id   = existing_id or f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}"
    out_path = existing_path or os.path.join(EXAM_FORMATS_DIR, f'{fmt_id}.json')
    record = {
        'id':          fmt_id,
        'course_name': course_name,
        'saved_at':    datetime.now().isoformat(),
        'exam_format': exam_format,
    }
    with open(out_path, 'w') as f:
        json.dump(record, f, indent=2)
    logger.info(f"{'Updated' if existing_path else 'Saved'} exam format: {course_name} → {fmt_id}")
    return jsonify({'id': fmt_id, 'course_name': course_name})


@app.route('/api/exam-formats/<fmt_id>', methods=['GET'])
def get_exam_format(fmt_id):
    fpath = os.path.join(EXAM_FORMATS_DIR, f'{fmt_id}.json')
    if not os.path.exists(fpath):
        return jsonify({'error': 'Not found'}), 404
    with open(fpath) as f:
        return jsonify(json.load(f))


@app.route('/api/exam-formats/<fmt_id>', methods=['DELETE'])
def delete_exam_format(fmt_id):
    fpath = os.path.join(EXAM_FORMATS_DIR, f'{fmt_id}.json')
    if not os.path.exists(fpath):
        return jsonify({'error': 'Not found'}), 404
    os.remove(fpath)
    return jsonify({'ok': True})


@app.route('/api/sessions/save', methods=['POST'])
def save_session_api():
    """Save or update a QBank or Lessons session. Pass session_id to update in place."""
    data = request.json
    session_type = data.get('type', 'qbank')
    course = data.get('course', '')
    existing_id = data.get('session_id') or None  # if set → update that entry

    if session_type == 'lessons':
        lessons_data = data.get('lessons_data', {})
        subject = data.get('subject', '')
        if not lessons_data or not lessons_data.get('lessons'):
            return jsonify({'error': 'No lessons data provided'}), 400
        session_id = save_lesson_session(lessons_data, course, subject, session_id=existing_id)
    else:
        questions = data.get('questions', [])
        subject = data.get('subject', '')
        topics = data.get('topics', [])
        if not questions:
            return jsonify({'error': 'No questions provided'}), 400
        session_id = save_qbank_session(questions, course, subject, topics, session_id=existing_id)

    return jsonify({'session_id': session_id})


@app.route('/api/parse-reference-doc', methods=['POST'])
def parse_reference_doc():
    """
    Parse an uploaded PYQ / reference document (JSON, MD, DOCX) and return
    a list of extracted question objects plus raw text for use as generation context.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    filename = file.filename or ''
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    questions = []
    raw_text = ''

    try:
        if ext == 'json':
            content = file.read().decode('utf-8')
            raw_json = json.loads(content)
            # Accept: array of question dicts OR {questions: [...]} wrapper
            if isinstance(raw_json, list):
                candidates = raw_json
            elif isinstance(raw_json, dict):
                candidates = raw_json.get('questions', raw_json.get('items', []))
                if not candidates:
                    # could be {subject: [...]} structure — flatten
                    for v in raw_json.values():
                        if isinstance(v, list):
                            candidates.extend(v)
            else:
                candidates = []
            # Keep only items that look like questions
            for item in candidates:
                if isinstance(item, dict) and ('question' in item or 'stem' in item or 'Q' in item):
                    q_text = item.get('question') or item.get('stem') or item.get('Q', '')
                    options = item.get('options') or item.get('choices') or []
                    correct = item.get('correct_option') or item.get('answer') or item.get('correct') or ''
                    explanation = item.get('explanation') or item.get('rationale') or ''
                    questions.append({
                        'question': q_text,
                        'options': options,
                        'correct_option': correct,
                        'explanation': explanation,
                        'subject': item.get('subject', ''),
                        'topic': item.get('topic', ''),
                    })
            raw_text = '\n\n'.join(
                f"Q: {q['question']}\nOptions: {', '.join(q['options'])}\nAnswer: {q['correct_option']}"
                for q in questions[:20]
            )

        elif ext == 'md':
            raw_text = file.read().decode('utf-8')
            # Parse markdown question blocks: lines starting with Q: or ## Q or numbered 1.
            import re
            blocks = re.split(r'\n(?=(?:\d+\.|##\s*Q|Q:|---\n))', raw_text)
            for block in blocks:
                lines = block.strip().split('\n')
                if not lines:
                    continue
                q_line = lines[0].lstrip('#0123456789. Q:').strip()
                if len(q_line) < 10:
                    continue
                opts, correct, expl = [], '', ''
                for ln in lines[1:]:
                    ln = ln.strip()
                    m = re.match(r'^([A-Ea-e])[.)]\s*(.+)', ln)
                    if m:
                        opts.append(m.group(2))
                    elif ln.lower().startswith(('answer:', 'correct:', 'ans:')):
                        correct = ln.split(':', 1)[-1].strip()
                    elif ln.lower().startswith(('explanation:', 'rationale:', 'reason:')):
                        expl = ln.split(':', 1)[-1].strip()
                if q_line:
                    questions.append({'question': q_line, 'options': opts, 'correct_option': correct, 'explanation': expl, 'subject': '', 'topic': ''})

        elif ext in ('docx', 'doc'):
            try:
                from docx import Document
                import io
                doc = Document(io.BytesIO(file.read()))
                raw_text = '\n'.join(para.text for para in doc.paragraphs if para.text.strip())
                # Parse numbered questions from plain text
                import re
                segments = re.split(r'\n(?=\d{1,3}[.)]\s)', raw_text)
                for seg in segments:
                    seg = seg.strip()
                    if len(seg) < 20:
                        continue
                    lines = seg.split('\n')
                    q_text = re.sub(r'^\d{1,3}[.)]\s*', '', lines[0]).strip()
                    opts, correct = [], ''
                    for ln in lines[1:]:
                        ln = ln.strip()
                        m = re.match(r'^([A-Ea-e])[.)]\s*(.+)', ln)
                        if m:
                            opts.append(m.group(2))
                        elif ln.lower().startswith(('answer:', 'ans:', 'correct:')):
                            correct = ln.split(':', 1)[-1].strip()
                    if q_text:
                        questions.append({'question': q_text, 'options': opts, 'correct_option': correct, 'explanation': '', 'subject': '', 'topic': ''})
            except Exception as e:
                logger.error(f"DOCX parse error: {e}")
                return jsonify({'error': f'Could not read DOCX file: {e}'}), 400

        else:
            # Plain text fallback
            raw_text = file.read().decode('utf-8', errors='ignore')

    except Exception as e:
        logger.error(f"parse-reference-doc error: {e}")
        return jsonify({'error': str(e)}), 500

    # Build a compact reference_text for prompt injection (cap at ~4000 chars)
    if not raw_text and questions:
        raw_text = '\n\n'.join(
            f"Q: {q['question']}\nOptions: {', '.join(q['options'])}\nAnswer: {q['correct_option']}"
            for q in questions[:20]
        )
    reference_text = raw_text[:4000] if raw_text else ''

    logger.info(f"Parsed reference doc '{filename}': {len(questions)} questions, {len(raw_text)} chars")
    return jsonify({
        'questions': questions[:100],   # cap at 100 for transfer
        'count': len(questions),
        'reference_text': reference_text,
        'filename': filename,
    })


@app.route('/api/sessions/<session_id>', methods=['GET'])
def get_session(session_id):
    """Load a full saved QBank session including questions."""
    fpath = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if not os.path.exists(fpath):
        return jsonify({'error': 'Session not found'}), 404
    try:
        with open(fpath, 'r') as f:
            data = json.load(f)
        # Restore any images whose local file has gone missing, then strip bulk data
        if data.get('questions'):
            _restore_question_images(data['questions'])
            for q in data['questions']:
                q.pop('_img_b64', None)
                q.pop('_img_media_type', None)
        if data.get('_images'):
            _restore_lesson_images(data['_images'])
            data.pop('_images', None)  # don't send MB of base64 to browser
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    """Delete a saved QBank session."""
    fpath = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if not os.path.exists(fpath):
        return jsonify({'error': 'Session not found'}), 404
    try:
        os.remove(fpath)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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

                    explanation = _or_call(explanation_prompt, max_tokens=1000).strip()
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
  "image_search_terms": ["1-3 Google Image Search queries, 2-5 words each, best query first — anatomy/pathology terms only, NO site names, NO 'annotated'/'labeled'/'diagram' qualifiers"],
  "key_finding": "Single sentence describing what the student should identify",
  "reasoning": "Brief explanation of why this image would help"
}}

If this question does NOT need an image (e.g., pure clinical reasoning, no visual diagnosis), set needs_image to false.

CRITICAL: Focus on PATHOGNOMONIC or CHARACTERISTIC findings that distinguish this diagnosis.

Respond with ONLY the JSON object, no other text."""

            try:
                # Call LLM API
                response_text = _or_call(analysis_prompt, max_tokens=2000)

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


def _get_lesson_flow_structure(course, is_medical):
    """Return the LESSON FLOW STRUCTURE block with domain-appropriate section headers,
    opening paragraph template, and per-section RHYTHM/bullet descriptions."""

    # ── SHARED: High Yield Summary is identical across all domains ──────────────
    high_yield_block = """### High Yield Summary
🔴🔴🔴 ABSOLUTELY MANDATORY FINAL SECTION - DO NOT SKIP THIS! 🔴🔴🔴

**Key Take-Aways:**
* 5-7 bullet points with the most critical concepts for this topic
* Include specific numbers, formulas, thresholds, and key parameters
* Critical points that cannot be missed
* Domain-specific recommendations and best practices

**Essential Numbers/Formulas:**
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
* 🔴 DO NOT add a "Red Flag" column to any table here — **Red Flags:** is a standalone callout box (already placed in earlier sections above)

**Related Chapters:**
* ONLY list chapters from ChaptersJSON that were NOT already integrated into the text above
* If all chapters were already mentioned in the lesson, write "All chapters covered above"
* Do NOT repeat chapters that were already woven into the narrative
* Note: "For rapid revision of individual chapters, refer to the dedicated chapter-level notes included with this topic."
"""

    # ── MEDICAL ─────────────────────────────────────────────────────────────────
    if is_medical:
        return f"""===========  LESSON FLOW STRUCTURE  ===========
CRITICAL RULES FOR SECTION HEADERS:
✗ NO section numbers ("1 —", "2 —", "Section 1", etc.)
✗ NO Bloom's labels ("Remember", "Understand", "Apply", "Analyze", "Level 1", etc.)
✗ NO "Page 1", "Page 2" etc.
✓ Use EXACTLY these section headers, in this order — do not rename, reorder, or add sections

OPENING PARAGRAPH (MANDATORY — appears BEFORE the first ### header):
Write EXACTLY 3 sentences using this template:
  Sentence 1: "A [age]-year-old [male/female] [presents/arrives/collapses] with [specific complaint + urgency detail]."
  Sentence 2: "[The specific decision/skill/action] is what [determines outcome / the next X minutes hinge on / separates a good clinician from a great one]."
  Sentence 3: "This lesson builds exactly that." (use this phrase or a close equivalent)

EXAMPLE — write a version for THIS topic, using the same 3-sentence structure (do not copy this example):
  "A 58-year-old man collapses in triage with crushing central chest pain and ST elevation across V1–V4. The next 90 minutes — and your ability to read this ECG and activate the right pathway — determine whether his myocardium survives. This lesson builds exactly that."

The opening must begin with a patient. Do not begin with a statistic, a definition, or a disease overview.

### Overview & Foundations
RHYTHM: 1 intro sentence → bullet list (key facts/classifications) → classification table → [image if a characteristic finding defines this topic] → **Mnemonic:** box
* Core definition with the diagnostic threshold or key criterion (e.g., "EF <40% defines HFrEF")
* Essential subtypes/classifications — each with its clinical implication, not just the label
* 2-3 key epidemiology facts only if they directly change clinical suspicion (e.g., "PE: 60-70/100,000 — always consider in breathless patients post-surgery")
* Diagnostic criteria with specific numbers (not "elevated markers" — name the marker and cut-off)
* TABLE: key classification or criteria table (MANDATORY)
* IMAGE (if applicable): place AFTER the table — a characteristic finding or hallmark image for this topic
* **Mnemonic:** [a specific, memorable aid for THIS topic — ≤12 words] (MANDATORY)
* 🔴 Integrate 1-2 chapter names NATURALLY IN SENTENCES

### Pathophysiology & Mechanisms
RHYTHM: 1 paragraph (core mechanism) → mermaid flowchart (cascade) → [image if anatomy/histology illuminates the mechanism] → table (mechanism → clinical manifestation) → **Key Points:** box
* Explain the central mechanism in 2-3 sentences with specific molecular/cellular detail
* Link each pathophysiological step to a clinical sign, symptom, or investigation finding
* WHY specific investigations are diagnostic (what they detect mechanistically)
* WHY specific treatments work (their mechanism, not just their name)
* Quantitative relationships where they exist (e.g., Starling curve, V/Q ratio, Fick equation)
* ```mermaid flowchart: pathophysiological cascade, max 8 nodes (MANDATORY)
* IMAGE (if applicable): place AFTER the mermaid — anatomical or histological image that makes the mechanism visible
* TABLE: mechanism → clinical manifestation (MANDATORY)
* **Key Points:** 3-5 mechanism-to-clinical-feature links a student must know (MANDATORY)
* 🔴 Integrate 1-3 chapter names INSIDE sentences

### Clinical Presentation & Diagnosis
RHYTHM: 1 clinical scenario sentence → bullet list (symptoms/signs with discriminating features) → investigation table → [diagnostic images here — ECG, X-ray, CT, histology, blood film, etc.] → mermaid (diagnostic algorithm) → **Red Flags:** box
* Open with a concrete clinical scenario: "A [age]-year-old [sex] presents with..." — specific to THIS topic
* Key symptoms with their sensitivity/specificity where known (e.g., "pleuritic chest pain: 66% sensitive for PE")
* Examination findings that change management — not exhaustive lists, only discriminating signs
* First-line investigations with expected findings and diagnostic thresholds
* TABLE: investigation → what it shows → sensitivity/specificity or clinical utility (MANDATORY)
* IMAGE (if applicable): place AFTER the investigation table — the key diagnostic image for this topic (ECG printout, chest X-ray, CT/MRI slice, histology slide, blood film, fundoscopy photo, dermatology photo). This is the highest-priority section for images. 🔴 DO NOT use this slot for spirometry traces, graphs, flow-volume curves, or any plotted data — use mermaid for those.
* ```mermaid flowchart: diagnostic algorithm from presentation to diagnosis (MANDATORY)
* **Red Flags:** symptoms/signs requiring immediate action for THIS specific topic (MANDATORY)
* 🔴 Integrate 2-3 chapter names INSIDE sentences

### Differential Diagnosis
RHYTHM: 1 paragraph (the key discriminating theme — what makes THIS diagnosis vs the mimics) → comparison table → bullet list (common pitfalls/cognitive traps) → **Clinical Pearl:** box
* State the 3-4 most important differentials for THIS topic and the single best discriminating feature for each
* Focus on features that CHANGE MANAGEMENT — not just academic differences
* Clinical prediction rules or scoring systems with their thresholds (e.g., Wells score, CURB-65)
* Common diagnostic errors: what gets missed and why
* TABLE: differential → key discriminating feature → investigation to confirm/exclude (MANDATORY)
* **Clinical Pearl:** one expert insight that prevents a common diagnostic error (MANDATORY)
* 🔴 Integrate 2-3 chapter names INSIDE sentences

### Management
RHYTHM: mermaid (treatment algorithm — first, sets the structure) → dosing table → bullet list (monitoring, targets, escalation) → **Red Flags:** box (when to escalate urgently)
* ```mermaid flowchart: treatment algorithm from diagnosis to step-up therapy (MANDATORY — place FIRST in this section)
* TABLE: drug/intervention → dose → frequency → monitoring → key contraindication (MANDATORY)
* Treatment targets with specific numbers (e.g., "target SBP <130 mmHg in high cardiovascular risk")
* When to escalate: specific thresholds, not vague "if not responding"
* Key drug interactions and adverse effects that require monitoring or dose adjustment
* Non-pharmacological interventions with evidence level (e.g., "CPAP reduces AHI by 50% — NICE NG202")
* Referral criteria: which specialty, when, and what triggers urgent vs routine referral
* **Red Flags:** specific findings that demand immediate escalation of care (MANDATORY)
* 🔴 Integrate 2-3 chapter names INSIDE sentences with guideline references

### Special Situations & Complications
RHYTHM: 1 paragraph (the highest-stakes special scenario for THIS topic) → table (special populations or complications with specific management differences) → [image only if a complication has a characteristic appearance] → bullet list (follow-up, long-term sequelae) → **Clinical Pearl:** box
* Focus on 2-3 genuinely important special scenarios — not a generic list of populations
* Pregnancy, elderly, renal/hepatic impairment ONLY if there are specific dose/management changes for THIS topic
* Complications: name them, state their incidence where known, and how to detect early
* Follow-up: what to monitor, at what interval, and what triggers re-referral
* TABLE: special population/complication → specific management change or threshold (MANDATORY)
* IMAGE (if applicable): place AFTER the table — only if a complication has a highly specific visual appearance worth recognising
* **Clinical Pearl:** one high-value nuance that a generalist commonly misses (MANDATORY)
* 🔴 Integrate 1-2 chapter names INSIDE sentences with guideline refs

{high_yield_block}"""

    # ── ENGINEERING / CS ────────────────────────────────────────────────────────
    elif any(kw in course.lower() for kw in ['engineering', 'cs', 'computer', 'software', 'data science']):
        return f"""===========  LESSON FLOW STRUCTURE  ===========
CRITICAL RULES FOR SECTION HEADERS:
✗ NO section numbers ("1 —", "2 —", "Section 1", etc.)
✗ NO "Page 1", "Page 2" etc.
✓ Use EXACTLY these section headers, in this order — do not rename, reorder, or add sections

OPENING PARAGRAPH (MANDATORY — appears BEFORE the first ### header):
Write EXACTLY 3 sentences using this template:
  Sentence 1: Describe a specific, high-stakes technical problem or scenario directly relevant to THIS topic.
  Sentence 2: State the specific skill, decision, or knowledge that determines the outcome.
  Sentence 3: "This lesson builds exactly that." (use this phrase or a close equivalent)

EXAMPLE — write a version for THIS topic (do not copy this example):
  "A distributed service is dropping requests under peak load and the on-call engineer has 5 minutes to decide: scale horizontally, increase cache TTL, or roll back the last deploy. Understanding concurrency limits, backpressure, and thread-pool exhaustion is what separates a correct diagnosis from an expensive guess. This lesson builds exactly that."

### Overview & Foundations
RHYTHM: 1 intro sentence → bullet list (key concepts/variants) → classification table → [diagram if a structure defines this topic] → **Mnemonic:** box
* Core definition with the key invariant or criterion (e.g., "O(log n) lookup defines a balanced BST")
* Essential variants/subtypes — each with its primary use case, not just the label
* 2-3 key performance or design constraints that directly change implementation choices
* Formal specifications with specific values (not "efficient" — state exact complexity or bounds)
* TABLE: key classification or comparison table (MANDATORY)
* IMAGE (if applicable): place AFTER the table — a characteristic architecture or structure diagram
* **Mnemonic:** [a specific, memorable aid for THIS topic — ≤12 words] (MANDATORY)
* 🔴 Integrate 1-2 chapter names NATURALLY IN SENTENCES

### Theory & Mechanisms
RHYTHM: 1 paragraph (core algorithm/principle) → mermaid flowchart (process flow) → [diagram if structure illuminates the mechanism] → table (operation → complexity/behaviour) → **Key Points:** box
* Explain the core algorithm or mechanism in 2-3 sentences with specific step-by-step logic
* Link each step to its observable outcome or performance characteristic
* WHY specific data structures or patterns are used (what property they exploit)
* WHY specific algorithms are correct (their invariant or proof sketch)
* Quantitative relationships where they exist (e.g., master theorem, Amdahl's law)
* ```mermaid flowchart: algorithmic or process flow, max 8 nodes (MANDATORY)
* IMAGE (if applicable): place AFTER the mermaid — structural diagram that makes the mechanism visible
* TABLE: operation → time complexity → space complexity → notes (MANDATORY)
* **Key Points:** 3-5 mechanism-to-behaviour links a student must know (MANDATORY)
* 🔴 Integrate 1-3 chapter names INSIDE sentences

### Implementation & Analysis
RHYTHM: 1 problem scenario sentence → bullet list (key factors with discriminating features) → analysis table → [structural diagram if applicable] → mermaid (decision/analysis algorithm) → **Red Flags:** box
* Open with a concrete implementation or analysis scenario specific to THIS topic
* Key indicators or signals with their precision/utility where known
* Implementation details that change outcomes — not exhaustive lists, only discriminating factors
* Primary analysis or measurement methods with expected results and decision thresholds
* TABLE: method/tool → what it reveals → complexity or utility (MANDATORY)
* IMAGE (if applicable): place AFTER the analysis table — a key architectural or structural diagram
* ```mermaid flowchart: decision or analysis algorithm (MANDATORY)
* **Red Flags:** anti-patterns or failure modes requiring immediate attention (MANDATORY)
* 🔴 Integrate 2-3 chapter names INSIDE sentences

### Trade-offs & Alternatives
RHYTHM: 1 paragraph (the key discriminating theme — what makes THIS approach vs alternatives) → comparison table → bullet list (common pitfalls/misconceptions) → **Clinical Pearl:** box
* State the 3-4 most important alternatives and the single best discriminating criterion for each
* Focus on trade-offs that CHANGE THE DESIGN DECISION — not just academic differences
* Decision heuristics with their applicability criteria
* Common implementation errors: what breaks and why
* TABLE: alternative → key discriminating criterion → scenario to prefer it (MANDATORY)
* **Clinical Pearl:** one expert insight that prevents a common design mistake (MANDATORY)
* 🔴 Integrate 2-3 chapter names INSIDE sentences

### Optimization & Best Practices
RHYTHM: mermaid (decision algorithm — first, sets the structure) → specification table → bullet list (tuning, targets, escalation) → **Red Flags:** box (failure conditions)
* ```mermaid flowchart: optimisation decision from problem to solution (MANDATORY — place FIRST in this section)
* TABLE: technique → parameters → constraints → monitoring (MANDATORY)
* Performance targets with specific numbers (e.g., "target p99 latency <10ms")
* When to escalate: specific thresholds, not vague "if slow"
* Key parameter interactions and side effects requiring monitoring or adjustment
* Non-algorithmic optimisations with evidence or benchmark data
* Escalation criteria: when to choose a different approach
* **Red Flags:** specific conditions that demand immediate architectural change (MANDATORY)
* 🔴 Integrate 2-3 chapter names INSIDE sentences with standards or RFC references

### Edge Cases & Advanced Scenarios
RHYTHM: 1 paragraph (the highest-stakes edge case for THIS topic) → table (special scenarios with specific handling) → [diagram only if a variant has a characteristic structure] → bullet list (maintenance, long-term considerations) → **Clinical Pearl:** box
* Focus on 2-3 genuinely important edge cases — not a generic list of scenarios
* Concurrency, distributed, or resource-constraint scenarios ONLY if there are specific handling changes
* Failure modes: name them, state their frequency, and how to detect early
* Maintenance: what to monitor and what triggers redesign
* TABLE: edge case → specific handling change or threshold (MANDATORY)
* IMAGE (if applicable): place AFTER the table — only if a variant has a highly specific structural appearance
* **Clinical Pearl:** one high-value nuance that a practitioner commonly misses (MANDATORY)
* 🔴 Integrate 1-2 chapter names INSIDE sentences with standards references

{high_yield_block}"""

    # ── GENERIC (Law, Business, Finance, and all other domains) ─────────────────
    else:
        return f"""===========  LESSON FLOW STRUCTURE  ===========
CRITICAL RULES FOR SECTION HEADERS:
✗ NO section numbers ("1 —", "2 —", "Section 1", etc.)
✗ NO "Page 1", "Page 2" etc.
✓ Use EXACTLY these section headers, in this order — do not rename, reorder, or add sections

OPENING PARAGRAPH (MANDATORY — appears BEFORE the first ### header):
Write EXACTLY 3 sentences using this template:
  Sentence 1: Describe a specific, high-stakes real-world scenario or situation directly relevant to THIS topic.
  Sentence 2: State the specific skill, decision, or knowledge that determines the outcome.
  Sentence 3: "This lesson builds exactly that." (use this phrase or a close equivalent)

EXAMPLE — write a version for THIS topic (do not copy this example):
  "A company is hours away from signing a major acquisition agreement when due diligence reveals an undisclosed liability that could void the deal. Knowing exactly which representations and warranties apply — and which contractual remedies are available — is what separates a prepared adviser from a costly mistake. This lesson builds exactly that."

### Overview & Foundations
RHYTHM: 1 intro sentence → bullet list (key concepts/categories) → classification table → [image/diagram if a characteristic feature defines this topic] → **Mnemonic:** box
* Core definition with the key criterion or distinguishing feature
* Essential subtypes/variants — each with its primary implication, not just the label
* 2-3 key contextual facts that directly change how this topic is applied
* Formal criteria or thresholds with specific values
* TABLE: key classification or criteria table (MANDATORY)
* IMAGE (if applicable): place AFTER the table — a characteristic image or diagram for this topic
* **Mnemonic:** [a specific, memorable aid for THIS topic — ≤12 words] (MANDATORY)
* 🔴 Integrate 1-2 chapter names NATURALLY IN SENTENCES

### Theory & Core Principles
RHYTHM: 1 paragraph (core theory/principle) → mermaid flowchart (causal or logical flow) → [image/diagram if it illuminates the principle] → table (principle → practical implication) → **Key Points:** box
* Explain the core theory or principle in 2-3 sentences with specific conceptual detail
* Link each theoretical step to a real-world outcome or observable implication
* WHY specific tools, methods, or frameworks are used (what property they exploit)
* WHY specific approaches work (their underlying rationale)
* Quantitative or formal relationships where they exist
* ```mermaid flowchart: causal or logical process chain, max 8 nodes (MANDATORY)
* IMAGE (if applicable): place AFTER the mermaid — diagram that makes the principle visible
* TABLE: principle → practical implication (MANDATORY)
* **Key Points:** 3-5 theory-to-practice links a student must know (MANDATORY)
* 🔴 Integrate 1-3 chapter names INSIDE sentences

### Application & Analysis
RHYTHM: 1 scenario sentence → bullet list (key indicators with discriminating features) → evidence/analysis table → [relevant image/diagram if applicable] → mermaid (decision/analysis algorithm) → **Red Flags:** box
* Open with a concrete applied scenario specific to THIS topic
* Key indicators or signals with their utility/reliability where known
* Factors that change the analysis — not exhaustive lists, only discriminating elements
* Primary methods or tools with expected outcomes and decision thresholds
* TABLE: method/tool → what it reveals → utility or reliability (MANDATORY)
* IMAGE (if applicable): place AFTER the analysis table — a key illustrative image or diagram
* ```mermaid flowchart: decision or analysis algorithm from scenario to conclusion (MANDATORY)
* **Red Flags:** critical warning signs requiring immediate attention (MANDATORY)
* 🔴 Integrate 2-3 chapter names INSIDE sentences

### Comparative Analysis
RHYTHM: 1 paragraph (the key discriminating theme — what makes THIS approach vs alternatives) → comparison table → bullet list (common pitfalls/misconceptions) → **Clinical Pearl:** box
* State the 3-4 most important alternatives and the single best discriminating criterion for each
* Focus on differences that CHANGE THE DECISION — not just academic distinctions
* Decision frameworks or heuristics with their applicability criteria
* Common errors: what gets confused and why
* TABLE: alternative → key discriminating criterion → evidence to prefer it (MANDATORY)
* **Clinical Pearl:** one expert insight that prevents a common error (MANDATORY)
* 🔴 Integrate 2-3 chapter names INSIDE sentences

### Implementation & Practice
RHYTHM: mermaid (process/decision algorithm — first, sets the structure) → specification table → bullet list (monitoring, targets, escalation) → **Red Flags:** box (critical failure conditions)
* ```mermaid flowchart: implementation or decision process (MANDATORY — place FIRST in this section)
* TABLE: approach/action → parameters → constraints → monitoring (MANDATORY)
* Outcome targets with specific numbers or thresholds
* When to escalate: specific triggers, not vague "if not working"
* Key interactions and side effects requiring monitoring
* Supporting approaches with evidence level where available
* Escalation criteria: when and what triggers re-evaluation
* **Red Flags:** specific findings demanding immediate escalation (MANDATORY)
* 🔴 Integrate 2-3 chapter names INSIDE sentences with authoritative references

### Special Cases & Advanced Scenarios
RHYTHM: 1 paragraph (the highest-stakes special case for THIS topic) → table (special scenarios with specific handling differences) → [image only if a variant has a characteristic appearance] → bullet list (follow-up, long-term implications) → **Clinical Pearl:** box
* Focus on 2-3 genuinely important special cases — not a generic list of scenarios
* Edge cases or special contexts ONLY if there are specific handling changes for THIS topic
* Failure modes or exceptions: name them and how to detect them
* Ongoing considerations: what to monitor and what triggers re-evaluation
* TABLE: special case → specific handling change or threshold (MANDATORY)
* IMAGE (if applicable): place AFTER the table — only if a variant has a highly specific visual appearance
* **Clinical Pearl:** one high-value nuance that a practitioner commonly misses (MANDATORY)
* 🔴 Integrate 1-2 chapter names INSIDE sentences with authoritative references

{high_yield_block}"""


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
        response_text = _or_call(prompt, max_tokens=1000, temperature=0.7).strip()

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

        def _gen_and_integrate(prompt, max_tok, subj, name):
            """Generate a lesson via OpenRouter then integrate images. Thread-safe."""
            try:
                text = _or_call(prompt, max_tokens=max_tok, temperature=0.1).strip()
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
- WordTarget   : 3500-4500 words | 7-8 A4 pages
- Audience     : {audience_desc}
- Depth Level  : {depth_desc}
==========================================================================

🔴 CRITICAL MANDATORY REQUIREMENTS (NON-NEGOTIABLE):
1. MUST end with "### High Yield Summary" section (Key Take-Aways, Essential Numbers/Formulas, Key Principles, Quick Reference)
2. 🔴 CHAPTER REFERENCES (CRITICAL FORMAT - MUST USE EXACT SYNTAX):
   🚨 MANDATORY: Reference ALL chapters from the chapters list using this EXACT format:

   Format: (see **Chapter Name**)

   ✅ EXAMPLES OF CORRECT FORMAT (substitute your actual chapter names from ChaptersJSON):
   - "[Key concept from this topic] (see **[Exact Chapter Name]**) accounts for..."
   - "Management of [X] (see **[Exact Chapter Name]**) requires understanding that..."
   - "The mechanism of [Y] (see **[Exact Chapter Name]**) explains why..."
   - "As described in (see **[Exact Chapter Name]**), [specific implication relevant here]..."

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
   - Examples of SPECIFIC descriptions (adapt to the modalities relevant to {course}):
     ✅ "[Imaging/photography modality] showing [specific finding with anatomical or structural detail]"
        e.g. "Chest X-ray PA view showing cardiomegaly with increased cardiothoracic ratio"
        e.g. "Histology slide showing [cell type] with [specific morphological feature]"
        e.g. "Photograph of [tissue/surface] demonstrating [named sign or finding]"
     ❌ "[Topic] anatomy/structure diagram" (too vague — use Mermaid instead)
     ❌ "[Topic] flowchart or algorithm" (use Mermaid flowchart, not image)
     ❌ "Spirometry trace" / "Flow-volume curve" / "V/Q graph" — graphs, function plots, and physiological curves CANNOT be embedded as images — use Mermaid instead
     ❌ Any waveform, trace, or plotted curve (spirometry, ECG waveform schematic, dose-response) — use Mermaid for diagrams, only use [Image:...] for real photographic modalities (X-ray, CT, MRI, histology, ECG printout, blood film, fundoscopy, dermatology photo)
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
✓ MAXIMUM 3 sentences per paragraph - then MUST add blank line
✓ Use DOUBLE newlines (blank lines) between ALL paragraphs

🔴 ANTI-WALL-OF-TEXT RULE (MANDATORY):
✗ Never write more than 2 consecutive prose paragraphs without a visual break
✓ Strict rhythm: prose → visual element → prose → visual element
✓ Visual elements = bullet list, table, callout box, or mermaid flowchart
✓ If you have written 2 paragraphs in a row, the next element MUST be visual

🔴 NO FILLER RULE (MANDATORY):
Every prose paragraph must contain at least ONE of:
- A specific number, threshold, parameter, or formula
- A named mechanism, process, or causal relationship
- A named technique, tool, concept, or domain-specific entity
- A key decision point or discriminating feature
❌ Cut any paragraph that only restates what the section header says
❌ Cut any paragraph that could apply to ANY medical topic (not specific to THIS one)

VISUAL MARKERS:
✓ Use emojis sparingly (🎯 key points, 🚩 red flags, 💎 clinical pearls, ⚠️ warnings)
✓ Bold key terms and concepts: **term**
✓ Use bullet points for lists with proper line breaks

CALLOUT BOXES (rendered as highlighted boxes in the app):
  - **Key Points:** → highlighted blue box
  - **Mnemonic:** → highlighted purple box
  - **Red Flags:** → highlighted red box
  - **Clinical Pearl:** → highlighted green box
🔴 Callout boxes MUST be STANDALONE blocks — NEVER embed them inside table cells or as table columns.
   ❌ WRONG: a markdown table with a "Red Flag" column
   ✅ RIGHT: a **Red Flags:** block placed AFTER the table, on its own line
✓ Use markdown tables with | separators for comparisons
✓ Ensure each section has clear spacing - double newlines between major elements

{_get_lesson_flow_structure(course, is_medical)}

===========  MANDATORY ELEMENTS  ===========
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
✓ End lesson with "### High Yield Summary" section containing most important concepts

===========  OUTPUT FORMAT  ===========
Markdown only. No meta commentary. No apologies. No "here's the lesson".
Start directly with the opening paragraph (no header before it).
🔴 WORD COUNT: 3500-4500 words total | 7-8 A4 pages"""

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
                        _gen_and_integrate, lesson_prompt, 16000, subject, topic_name
                    )
                    ch_futures = [
                        (ch_name, nice_refs,
                         pool.submit(_gen_and_integrate, ch_prompt, 2000, subject, ch_name))
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
    uploaded_structure = data.get('uploaded_structure')  # Optional pre-parsed structure
    saved_exam_format  = data.get('exam_format')         # Optional pre-saved exam format (skip analyze_exam_format)

    if not course:
        return jsonify({'error': 'Course is required'}), 400

    try:
        if uploaded_structure:
            # Use uploaded structure — skip AI structure generation
            logger.info(f"📚 Using uploaded structure for: {course} ({len(uploaded_structure.get('subjects', []))} subjects)")
            structure = {
                'course': course,
                'exam_type': uploaded_structure.get('exam_type', 'general'),
                'domain_characteristics': uploaded_structure.get('domain_characteristics', ''),
                'subjects': uploaded_structure.get('subjects', [])
            }
        else:
            # Use MODULE 1: Generate course structure via web search
            logger.info(f"📚 Generating structure from web for: {course}")
            structure = generate_course_structure(course)

        # MODULE 2: Use saved exam format if provided, otherwise fetch from web
        if saved_exam_format:
            logger.info(f"📋 Using saved exam format for: {course} (skipping web analysis)")
            exam_format_analysis = saved_exam_format
        else:
            logger.info(f"📝 Fetching exam format from web for: {course}")
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

        response_text = _or_call(refine_prompt, max_tokens=4000, temperature=0.7).strip()

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
        return f"""You are a senior {domain} content validator. Fix what is genuinely wrong — do not over-correct content that is already accurate and appropriate.

You will receive multiple lesson sections numbered SECTION 1, SECTION 2, etc. in two formats:

• TOPIC LESSON (~800-1200 words): evaluate completeness, depth, factual accuracy, and learning flow.
• RAPID REVISION NOTE (~300-500 words, cheat-sheet): evaluate ACCURACY only — do NOT penalise for brevity, missing depth, or omitting prerequisites. A dense, accurate cheat-sheet scores 8-9.

For EACH section check ONLY:
1. Factual correctness — wrong numbers, outdated thresholds, incorrect statements
2. Dangerous omissions — missing critical safety warnings or contraindications that could cause harm
3. Active misinformation — oversimplifications that would leave a learner with a wrong mental model
4. Image relevance — embedded images that are clearly wrong modality or irrelevant to the text
5. Absent high-value images — flag only if the absence makes a key concept significantly harder to understand (e.g., "No ECG for atrial fibrillation identification", "No histology image for this pathology section")

Do NOT flag content for style preferences, incomplete coverage of tangential topics, or missing depth in rapid revision notes.
needs_revision = true ONLY for: factual error, dangerous omission, or actively misleading content.

Scoring:
• 9–10 → accurate and appropriate for its format
• 7–8 → minor factual gap or imprecision, no safety risk
• 5–6 → notable inaccuracy or missing critical safety info
• ≤4  → material factual errors or dangerous content

Each issue or recommendation must be ONE specific, actionable sentence. No padding.

Return a JSON ARRAY — one object per section:
[
  {{
    "section_number": 1,
    "section_title": "<title>",
    "overall_accuracy_score": <0-10>,
    "needs_revision": <boolean>,
    "factual_errors": [<only confirmed wrong facts — empty if none>],
    "missing_critical_info": [<dangerous omissions only — empty if none>],
    "safety_concerns": [<empty if none>],
    "clarity_issues": [<only where ambiguity causes real confusion — empty if none>],
    "learning_gaps": [<only truly essential missing concepts — empty if none>],
    "missing_high_yield": [<empty if none>],
    "missing_pitfalls": [<empty if none>],
    "asset_issues": [<image/table wrong modality or clearly irrelevant — empty if none>],
    "missing_images": [<high-value absent images only, each as a specific 1-sentence description — empty if none>],
    "recommendations": [<specific, actionable fixes only — empty if none>],
    "summary": "<1 sentence: what is wrong, or 'No issues found' if clean>"
  }},
  ...
]

Output ONLY the JSON array. No preamble, no trailing text."""

    elif content_type == 'qbank':
        return f"""You are a senior {domain} exam item validator.

YOUR ROLE — accuracy and relevance: Is everything in this question factually correct? Is the content relevant to what the question is testing?
You are NOT here to improve, expand, or polish. Only flag what is wrong or irrelevant.

You will receive multiple questions numbered Q1, Q2, etc.

For EACH question ask only:
1. Is the marked correct answer factually correct? If yes, score it high and move on.
2. Are the distractors factually wrong? Minor edge cases that don't change the answer are NOT issues.
3. Is the explanation factually accurate and does it correctly justify the answer?
4. Does the vignette contain the minimum data needed to reach the correct answer?
5. Is the clinical content free of factual inaccuracies?
6. IMAGE — relevance only:
   a. Image absent but the stem explicitly references it (e.g. "shown below", "image 1", "radiograph shown") → score ≤ 4 and set needs_revision true. The question is UNUSABLE without its image regardless of how good the text is.
   b. Image present but wrong modality or clearly irrelevant → flag and suggest replacement.
   c. Image that is imperfect but clinically appropriate → do NOT flag.

Scoring (10 = nothing to fix, 1 = unacceptable):
• 9–10 → factually correct and relevant — do not change
• 7–8 → minor imprecision, correct answer not in doubt
• 5–6 → genuine factual or relevance issue worth fixing
• 1–4  → wrong answer, dangerous error, broken question, OR image explicitly referenced but absent

Each issue must be ONE specific sentence: what is wrong AND the preferred fix. No vague commentary.
If nothing is wrong, leave all issue arrays empty and score 9–10.

Return a JSON ARRAY — one object per question:
[
  {{
    "question_number": 1,
    "question_preview": "<first 80 chars of stem>",
    "overall_accuracy_score": <1-10>,
    "correct_answer_verified": <boolean>,
    "needs_revision": <boolean — true if score ≤ 5 OR if image is explicitly referenced but absent>,
    "factual_errors": [<confirmed wrong clinical facts only — empty if none>],
    "distractor_issues": [<only if a distractor is genuinely defensible as correct — empty if none>],
    "vignette_issues": [<only if key data is missing to reach the answer — empty if none>],
    "explanation_issues": [<only if explanation contradicts or fails to justify the answer — empty if none>],
    "asset_issues": [<image mismatch — replace image only — empty if none>],
    "missing_images": [<image absent but explicitly required — empty if none>],
    "recommendations": [<empty if none>],
    "changes_required": [<NUMBERED list of concrete changes needed. Empty if score > 7.
      Each entry is a complete, self-contained instruction.
      Examples:
        "1. Replace attached image with a CT abdomen showing appendiceal wall thickening",
        "2. Fix correct answer from B to A — adenosine is first-line for SVT not metoprolol"
      Empty array if no real changes needed.>],
    "summary": "<1 sentence: what is wrong, or 'No issues found' if clean>"
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
        return f"""You are an adversarial {domain} content reviewer. Your role is to find real defects that would mislead learners or cause harm — not to invent problems where none exist.

You will receive multiple lesson sections in two formats:
• TOPIC LESSON (~800-1200 words): check for factual errors, dangerous gaps, and misleading statements.
• RAPID REVISION NOTE (~300-500 words cheat-sheet): check ONLY factual accuracy and dangerous omissions. A concise, accurate note scores 0-2. Do NOT penalise for brevity.

For EACH section, report ONLY genuine defects:
• Confirmed factual inaccuracies (wrong drug dose, wrong diagnostic threshold, wrong mechanism)
• Dangerous simplifications that could lead to patient harm or wrong clinical decisions
• Missing critical contraindications or safety warnings
• Internal contradictions within the content
• Images that actively mislead (wrong pathology, wrong anatomy shown)
• Wrong imaging modality for the topic (e.g., CXR shown when the topic is CT diagnosis)
• High-value image clearly absent that would make a key concept significantly clearer

Do NOT flag: brevity, style choices, tangential omissions, or content that is accurate but could theoretically be more detailed.
Do NOT manufacture ambiguity where the content is clear and correct.

Scoring (10 = no defects at all, 1 = seriously misleading or unsafe):
• 9–10 → no real defects for this format
• 7–8 → very minor inaccuracy, no safety risk
• 5–6 → notable inaccuracy or potentially misleading
• 1–4  → significant error, dangerous gap, or unsafe content
If no genuine defects exist, score 9–10 and leave all issue arrays empty.

Each item in any list must be ONE specific sentence. No vague filler.

Return a JSON ARRAY — one object per section:
[
  {{
    "section_number": 1,
    "adversarial_score": <0-10>,
    "breakability_rating": "<unbreakable|minor issues|moderate issues|severely flawed>",
    "identified_weaknesses": [<confirmed factual errors or dangerous statements only — empty if none>],
    "ambiguities": [<genuine ambiguities that would confuse a learner — empty if none>],
    "overgeneralizations": [<dangerous oversimplifications only — empty if none>],
    "logical_gaps": [<internal contradictions or missing logic — empty if none>],
    "safety_risks": [<missing contraindications or safety warnings — empty if none>],
    "learning_traps": [<ways content could actively mislead into wrong mental model — empty if none>],
    "asset_issues": [<images with wrong modality or actively misleading content — empty if none>],
    "missing_images": [<high-value absent image with specific 1-sentence description — empty if none>],
    "recommendations": [<specific, actionable — empty if no real issues>],
    "summary": "<1 sentence: what is genuinely wrong, or 'No significant defects found'>"
  }},
  ...
]

Output ONLY the JSON array. No preamble, no trailing text."""

    elif content_type == 'qbank':
        return f"""You are an adversarial {domain} exam item reviewer.

YOUR ROLE — missing or misleading content: Does this question have anything absent or misleading that would cause confusion, reinforce a wrong mental model, or reduce its educational value?
You are NOT a fact-checker (the validator handles accuracy). Your lens is: could a student come away from this question more confused or with a worse understanding than before?

You will receive multiple questions numbered Q1, Q2, etc.

Flag only if one of these is true:
1. Something critical is missing from the vignette or explanation such that a student can't build the right clinical reasoning — not just "could be more complete"
2. The question is misleading in a way that would teach a wrong mental model (e.g., explanation implies a false rule, distractor wording implies wrong pathophysiology)
3. An alternative answer is so defensible that a well-prepared student would reasonably choose it — not a far-fetched edge case
4. A triviality clue bypasses clinical reasoning entirely, making the question educationally worthless
5. IMAGE: actively misleading (wrong pathology/anatomy shown) OR absent when the stem explicitly references it — a question that says "shown below" or "Image 1" with no image present is educationally broken and scores ≤ 4

Do NOT flag:
• Omissions that don't affect clinical reasoning for this question
• Style, phrasing, or formatting preferences
• Content a student could reasonably infer
• Wanting the question to cover more ground than it needs to

Scoring (10 = high educational value, no confusion risk; 1 = misleading or educationally harmful):
• 9–10 → clear, sound, good learning value — no changes needed
• 7–8 → trivial gap or very minor risk of confusion
• 5–6 → genuine concern — something missing or misleading that affects learning
• 1–4  → seriously misleading, reinforces wrong reasoning, educationally counterproductive, OR image explicitly referenced in stem but absent

If nothing meets the bar above, score 9–10, leave all arrays empty, and say "No significant defects found."

Each issue must be ONE specific sentence: what is missing/misleading AND what would fix it.

Return a JSON ARRAY — one object per question:
[
  {{
    "question_number": 1,
    "adversarial_score": <1-10>,
    "breakability_rating": "<airtight|minor flaws|moderate flaws|easily broken>",
    "alternative_answers": [<only if genuinely defensible — empty if answer is clear>],
    "ambiguities": [<genuine confusion that would lead most candidates astray — empty if none>],
    "distractor_defenses": [<only if a distractor is actually defensible as correct — empty if none>],
    "explanation_contradictions": [<only if explanation logically fails to justify the answer — empty if none>],
    "triviality_clues": [<only if answer is obvious without clinical reasoning — empty if none>],
    "asset_issues": [<clear mismatch only — empty if image is appropriate even if imperfect>],
    "missing_images": [<image explicitly required but absent — empty if none>],
    "recommendations": [<empty if none>],
    "changes_required": [<NUMBERED list of changes NOT already captured by the validator. Empty if none.>],
    "summary": "<1 sentence: what is genuinely wrong, or 'No significant defects found'>"
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
            _HDR = {
                'User-Agent': 'Mozilla/5.0 (compatible; QBankGenerator/1.0; +https://github.com/pkompalli/QBank-Generator)',
                'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                'Referer': '/'.join(image_url.split('/')[:3]) + '/',
            }
            resp = _req.get(image_url, timeout=15, headers=_HDR)
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


def _make_parse_miss(index):
    """Return a result for a question whose batch slot came back empty (model returned fewer items than sent)."""
    return {
        "index": index,
        "parse_miss": True,
        "validator": {
            "question_number": index,
            "overall_accuracy_score": None,
            "correct_answer_verified": None,
            "needs_revision": False,
            "factual_errors": [], "distractor_issues": [], "vignette_issues": [],
            "explanation_issues": [], "recommendations": [],
            "summary": "Could not validate — model did not return a result for this question."
        },
        "adversarial": {
            "question_number": index,
            "adversarial_score": None,
            "breakability_rating": "N/A",
            "alternative_answers": [], "ambiguities": [], "distractor_defenses": [],
            "explanation_contradictions": [], "triviality_clues": [],
            "recommendations": [],
            "summary": "Could not validate — model did not return a result for this question."
        },
        "overall_assessment": {
            "status": "⚠️ Not Validated",
            "quality_score": None,
            "validator_score": None,
            "adversarial_score": None,
            "needs_revision": False,
            "recommendation": "Validation model did not return a result for this question. Re-run validation."
        }
    }


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


def _dedup_sim(s1, s2, threshold=0.6):
    """Return True if two change strings are similar enough to be duplicates."""
    w1 = set(s1.lower().split())
    w2 = set(s2.lower().split())
    if not w1 or not w2:
        return False
    return len(w1 & w2) / min(len(w1), len(w2)) >= threshold


def _validate_one_qbank_question(q_obj, course, domain="medical education"):
    """
    Run validator + adversarial on a single QBank question and return
    (v_result, a_result, overall_assessment).  Used post-fix to confirm score ≥ 8.
    """
    from concurrent.futures import ThreadPoolExecutor

    # Build content payload (text + optional embedded image)
    opts = '\n'.join([f"  {chr(65+j)}. {opt}" for j, opt in enumerate(q_obj.get('options', []))])
    image_url = q_obj.get('image_url', '')
    has_image = bool(image_url) and _image_available(image_url)

    image_marker = "[IMAGE FOR THIS QUESTION IS EMBEDDED BELOW — evaluate it as part of the question]\n" if has_image else ""
    q_text = f"""
--- Q1 ---
{image_marker}Question: {q_obj.get('question', '')}
Options:
{opts}
Correct Answer: {q_obj.get('correct_option', '')}
Explanation: {q_obj.get('explanation', '')}
Tags: {', '.join(q_obj.get('tags', []))}
"""
    blocks = [{"type": "text", "text": q_text}]
    if has_image:
        img_data, media_type = _load_image_as_base64(image_url)
        if not img_data and image_url.startswith('http'):
            cached = _download_and_cache_image({'url': image_url})
            local_url = cached.get('url', image_url)
            if local_url != image_url:
                img_data, media_type = _load_image_as_base64(local_url)
                if img_data:
                    q_obj['image_url'] = local_url
        if img_data:
            blocks.append({"type": "image",
                           "source": {"type": "base64", "media_type": media_type, "data": img_data}})
        else:
            blocks.append({"type": "text", "text": "[IMAGE ATTACHED — could not be embedded; assume image exists]\n"})

    # Convert blocks → OpenAI-format content list
    def _to_oai(blk_list, prompt_text):
        oai = [{"type": "text", "text": f"{prompt_text}\n\nContent to validate:\n"}]
        for b in blk_list:
            if b.get('type') == 'text':
                oai.append({"type": "text", "text": b['text']})
            elif b.get('type') == 'image':
                src = b.get('source', {})
                if src.get('type') == 'base64':
                    oai.append({"type": "image_url",
                                "image_url": {"url": f"data:{src['media_type']};base64,{src['data']}"}})
        return oai

    vp = get_batch_validator_prompt('qbank', domain)
    ap = get_batch_adversarial_prompt('qbank', domain)

    def _run_v():
        return _or_call(None, model=OR_VALIDATOR_MODEL, max_tokens=4000, temperature=0.2,
                        messages=[{"role": "user", "content": _to_oai(blocks, vp)}]).strip()

    def _run_a():
        return _or_call(None, model=OR_ADVERSARIAL_MODEL, max_tokens=4000, temperature=0.3,
                        messages=[{"role": "user", "content": _to_oai(blocks, ap)}]).strip()

    with ThreadPoolExecutor(max_workers=2) as ex:
        vf = ex.submit(_run_v)
        af = ex.submit(_run_a)
        v_text = vf.result()
        a_text = af.result()

    v_arr = _extract_json_array(v_text, 1)
    a_arr = _extract_json_array(a_text, 1)
    v_result = v_arr[0] if v_arr else {}
    a_result = a_arr[0] if a_arr else {}

    # Inline _enforce_needs_revision logic (same as in validate_content)
    _v_score = v_result.get('overall_accuracy_score', 10)
    hard_failure = (
        bool(v_result.get('factual_errors')) or
        v_result.get('correct_answer_verified') is False or
        bool(v_result.get('asset_issues')) or
        bool(v_result.get('missing_images')) or
        (bool(a_result.get('asset_issues')) and _v_score < 8) or
        bool(a_result.get('alternative_answers')) or
        bool(a_result.get('explanation_contradictions')) or
        _v_score <= 4
    )
    if hard_failure:
        v_result['needs_revision'] = True
    else:
        v_result['needs_revision'] = False
        a_result.pop('needs_revision', None)

    oa = generate_overall_assessment(v_result, a_result, 'qbank')
    return v_result, a_result, oa


@app.route('/api/fix-content', methods=['POST'])
def fix_content():
    """
    Fix selected validation items using Claude.
    Reads original content + aggregated issues + recommendations + missing_images,
    rewrites to address them, then fetches/embeds real images where needed.
    All items are fixed in parallel.
    """
    data = request.json
    content_type  = data.get('content_type', 'lesson')   # 'lesson' | 'qbank'
    items_to_fix  = data.get('items', [])
    course        = data.get('course', '')
    subject       = data.get('subject', '')

    if not items_to_fix:
        return jsonify({'error': 'No items to fix'}), 400

    def fix_one(item):
        idx              = item.get('index', 0)
        content          = item.get('content', '')
        title            = item.get('title', f'Item {idx}')
        issues           = item.get('issues', [])
        recommendations  = item.get('recommendations', [])
        missing_images   = item.get('missing_images', [])
        changes_required = item.get('changes_required', [])   # numbered list from validation
        topic            = item.get('topic', title)
        search_subject   = subject or course

        issues_text = '\n'.join(f'  • {i}' for i in issues) if issues else '  (none specified)'
        recs_text   = '\n'.join(f'  • {r}' for r in recommendations) if recommendations else '  (none specified)'

        # ── LESSONS: search images FIRST, pass real URLs to Claude ─────────────
        if content_type == 'lesson':
            found_images = []
            if missing_images:
                from concurrent.futures import ThreadPoolExecutor as _ITP

                def _fetch_missing(desc):
                    q_data = {
                        'image_description': desc,
                        'image_type': 'Medical illustration',
                        'image_search_terms': [
                            desc,
                            f"{topic} {desc}",
                            f"{search_subject} {desc}",
                        ],
                        'question': f"Medical educational image: {desc}",
                    }
                    try:
                        result = search_and_validate_image(q_data, search_subject)
                        if result:
                            return {'description': desc, 'url': result['url']}
                    except Exception as e:
                        logger.warning(f"  [fix] Image search failed for '{desc}': {e}")
                    return None

                with _ITP(max_workers=max(1, len(missing_images))) as pool:
                    for r in pool.map(_fetch_missing, missing_images):
                        if r:
                            found_images.append(r)
                logger.info(f"  [fix] Found {len(found_images)}/{len(missing_images)} images for '{title}'")

            # Build image embed section with real URLs so Claude can insert ![alt](url) directly
            img_section = ''
            if found_images:
                lines = '\n'.join(
                    f"  • {img['description']} → {img['url']}"
                    for img in found_images
                )
                img_section = f"""
─── IMAGES TO EMBED ───
These images were found — insert each one IMMEDIATELY AFTER the paragraph or heading that
discusses that topic (not all at the end). Use this exact markdown format:

![Description](url)
*Figure N: Description*

(N = next sequential figure number after any already in the content)

{lines}
"""
            elif missing_images:
                # Nothing found — ask Claude to compensate with rich descriptive text
                img_section = f"""
─── IMAGES UNAVAILABLE ───
These images were flagged as needed but could not be found in our library:
{chr(10).join(f"  • {i}" for i in missing_images)}
Where each image would appear, add a rich descriptive sentence conveying the key visual
finding in words (e.g. "The ECG classically shows ...", "On histology one sees ...").
"""

            prompt = f"""You are a medical education content editor. Revise the lesson section below to fix every identified issue.

SECTION: {title}
COURSE: {course}

─── ORIGINAL CONTENT ───
{content}

─── IDENTIFIED ISSUES ───
{issues_text}

─── RECOMMENDATIONS ───
{recs_text}
{img_section}
INSTRUCTIONS:
- Fix EVERY issue and implement EVERY recommendation listed above
- If images are provided above, embed each one using ![Description](url) + *Figure N: Description*
  caption, placed immediately after the most relevant paragraph
- Preserve the existing structure (### headers, clinical pearls, mnemonics, tables, flowcharts)
- Maintain the progressive learning flow and approximate length
- Do NOT add a preamble or closing note — return ONLY the revised markdown content"""

            fixed = _or_call(prompt, max_tokens=4000).strip()
            return {
                'index': idx, 'fixed_content': fixed, 'title': title,
                'images_added': len(found_images),
            }

        # ── QBANK ──────────────────────────────────────────────────────────────
        else:
            # Build the required-changes list: prefer changes_required (numbered, precise),
            # fall back to issues + recommendations if not present
            all_changes = changes_required if changes_required else (
                [f'{i+1}. {x}' for i, x in enumerate(issues + recommendations) if x]
            )
            changes_text = '\n'.join(f'  {c}' for c in all_changes) if all_changes else '  (none — question is correct as-is)'

            # Detect if any change involves an image
            _img_keywords = ('image', 'modality', 'ecg', 'x-ray', 'xray', 'ct ', 'mri', 'histol',
                             'ultrasound', 'dermat', 'scan', 'radiograph', 'replace image', 'replace attached')
            has_image_change = bool(missing_images) or any(
                any(kw in str(c).lower() for kw in _img_keywords) for c in all_changes
            )

            img_fix_rules = ''
            if has_image_change:
                img_fix_rules = """

─── IMAGE FIX RULES ───
The STEM is the source of truth. When an image fix is required:
• ALWAYS replace the image to match what the stem describes — never change the stem to match the image.
• UPDATE: requires_image=true, image_type (exact modality stated in stem), image_description (exact
  finding described in stem), image_search_terms (3-5 specific queries matching the stem's clinical scenario).
• If no image is needed: set requires_image=false and remove the image reference from the stem.
"""

            prompt = f"""You are a medical education question editor. Apply EXACTLY the required changes below to the MCQ — nothing more, nothing less.

COURSE: {course}

─── ORIGINAL QUESTION (JSON) ───
{content}

─── REQUIRED CHANGES (apply every one, in order) ───
{changes_text}
{img_fix_rules}
Return a JSON object with TWO fields:
1. "question" — the complete fixed question JSON (same structure as original)
2. "changes_applied" — array of strings, one per required change above, each prefixed with
   "✅ " if applied, "⚠️ " if partially applied (explain why), or "❌ " if not applicable / could not apply (explain why)

Example output format:
{{
  "question": {{ ...fixed question fields... }},
  "changes_applied": [
    "✅ 1. Changed 'CT scan' to 'MRI' in question stem",
    "✅ 2. Updated explanation to state adenosine is first-line for SVT",
    "⚠️ 3. Image replacement triggered — new search terms set, image will be fetched automatically"
  ]
}}

Return ONLY valid JSON. No preamble, no markdown fences."""

            raw = _or_call(prompt, max_tokens=4000).strip()

            # Strip markdown fences if model wraps in ```
            if '```json' in raw:
                raw = raw.split('```json')[1].split('```')[0].strip()
            elif '```' in raw:
                raw = raw.split('```')[1].split('```')[0].strip()

            # Parse wrapper — extract "question" and "changes_applied"
            changes_applied = []
            try:
                wrapper = json.loads(raw)
                if isinstance(wrapper, dict) and 'question' in wrapper:
                    fixed = json.dumps(wrapper['question'], ensure_ascii=False)
                    changes_applied = wrapper.get('changes_applied', [])
                else:
                    # Model returned the question directly (old format fallback)
                    fixed = raw
            except (json.JSONDecodeError, Exception):
                fixed = raw

            # If the fixed question needs an image (new or replacement), fetch one.
            # Triggers when requires_image is true (or search terms exist) AND any of:
            #   1. No image_url yet (new image needed)
            #   2. missing_images was flagged (existing image was wrong/missing)
            #   3. LLM updated image_search_terms (wants a different image for asset_issues)
            try:
                q_obj = json.loads(fixed)
                needs_image = q_obj.get('requires_image') or bool(q_obj.get('image_search_terms'))

                # Detect if LLM changed search terms (signals it wants a different image)
                terms_changed = False
                try:
                    orig_obj = json.loads(content)
                    orig_terms = set(orig_obj.get('image_search_terms') or [])
                    new_terms  = set(q_obj.get('image_search_terms') or [])
                    terms_changed = bool(new_terms) and orig_terms != new_terms
                except Exception:
                    pass

                needs_new_image = needs_image and (
                    not q_obj.get('image_url') or bool(missing_images) or terms_changed
                )
                image_debug = None
                if needs_new_image:
                    # Clear stale image so the new one fully replaces it
                    q_obj.pop('image_url', None)
                    q_obj.pop('image_source', None)
                    q_obj.pop('image_title', None)
                    logger.info(f"  [fix] Fetching image for Q{idx}: {q_obj.get('image_description','')}")
                    # skip_ai_fallback=True so Gemini is bypassed; OpenRouter is tried explicitly below
                    img_result, img_candidates, img_raw, img_err, img_gemini_err = search_and_validate_image(
                        q_obj, search_subject, return_debug=True, skip_ai_fallback=bool(openai_image_client))

                    # If search/validation couldn't find a good image, try OpenRouter image generation
                    or_img_err = None
                    if not img_result and OR_IMAGE_MODEL:
                        logger.info(f"  [fix] Search returned nothing — trying {OR_IMAGE_MODEL} for Q{idx}")
                        img_result, or_img_err = generate_image_with_openrouter(q_obj)
                        if img_result:
                            best_score = max((c.get('score', 0) for c in (img_candidates or [])), default=0)
                            img_candidates = (img_candidates or []) + [{
                                'url':      img_result.get('url', ''),
                                'source':   img_result.get('source', ''),
                                'title':    'AI-generated image',
                                'score':    100,
                                'reason':   f'Best search result scored {best_score}/100 (threshold: 80). Generated by {OR_IMAGE_MODEL} instead.',
                                'selected': True,
                            }]

                    if img_result:
                        q_obj['image_url']    = img_result['url']
                        q_obj['image_source'] = img_result.get('source', '')
                        q_obj['image_title']  = img_result.get('title', '')
                        logger.info(f"  [fix] Image found for Q{idx} via {img_result.get('source','')}")
                    else:
                        logger.warning(f"  [fix] No image found for Q{idx} (search err={img_err}, or_img_err={or_img_err})")
                    sanitized_terms = _sanitize_search_terms(q_obj.get('image_search_terms', []))
                    image_debug = {
                        'used_query': sanitized_terms[0] if sanitized_terms else '',
                        'search_terms': sanitized_terms,
                        'image_type': q_obj.get('image_type', ''),
                        'candidates': img_candidates,
                        'google_raw_count': img_raw,
                        'google_error': img_err,
                        'gemini_error': (f'OpenAI ({OR_IMAGE_MODEL}): {or_img_err}' if or_img_err
                                        else (f'Gemini: {img_gemini_err}' if img_gemini_err else None)),
                        'selected_url': img_result['url'] if img_result else None,
                        'threshold': 80,
                        'gemini_prompt': build_gemini_prompt(q_obj),
                    }
                fixed = json.dumps(q_obj, ensure_ascii=False)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"  [fix] QBank image fetch skipped: {e}")
                image_debug = None

            ret = {'index': idx, 'fixed_content': fixed, 'title': title,
                   'changes_applied': changes_applied, 'changes_required': all_changes}
            if image_debug is not None:
                ret['image_debug'] = image_debug
            return ret

    try:
        from concurrent.futures import ThreadPoolExecutor as _FTP
        with _FTP(max_workers=len(items_to_fix)) as pool:
            fixed_items = list(pool.map(fix_one, items_to_fix))
        logger.info(f"Fixed {len(fixed_items)} item(s) via /api/fix-content")
        return jsonify({'success': True, 'fixed_items': fixed_items})
    except Exception as e:
        logger.error(f"fix_content error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/image-search-debug', methods=['POST'])
def image_search_debug():
    """
    Run image search+scoring pipeline for a single question and return full debug info:
    search terms, candidate images with scores, which one was selected.
    Skips cache so the caller always sees live candidates.
    """
    try:
        data = request.json or {}
        question_data = data.get('question_data', {})
        subject = data.get('subject', '')

        # If generation stored debug data, return it directly — no re-run needed
        stored = question_data.get('_image_debug')
        if stored:
            image_type = question_data.get('image_type', '')
            gemini_prompt_text = build_gemini_prompt(question_data) if question_data else ''
            return jsonify({
                'used_query':       (stored.get('search_terms') or [''])[0],
                'search_terms':     stored.get('search_terms', []),
                'source_strategy':  stored.get('source_strategy', ''),
                'image_type':       stored.get('image_type', image_type),
                'google_raw_count': stored.get('google_raw_count'),
                'google_error':     stored.get('google_error'),
                'gemini_error':     stored.get('gemini_error'),
                'candidates':       stored.get('candidates', []),
                'selected_url':     stored.get('selected_url'),
                'threshold':        80,
                'gemini_prompt':    gemini_prompt_text,
            })

        image_search_terms = question_data.get('image_search_terms', [])
        image_type = question_data.get('image_type', '')

        if not image_search_terms:
            # Reconstruct fallback terms from whatever is available on the question
            parts = []
            if image_type:
                parts.append(image_type)
            desc = question_data.get('image_description', '')
            if desc:
                parts.append(desc[:60])
            if subject:
                parts.append(subject)
            if parts:
                image_search_terms = parts
                question_data = {**question_data, 'image_search_terms': image_search_terms}
                logger.info(f"image_search_debug: reconstructed terms from metadata: {image_search_terms}")
            else:
                return jsonify({
                    'search_terms': [], 'image_type': image_type,
                    'candidates': [], 'selected_url': None, 'threshold': 80,
                    'message': 'No image_search_terms on this question and no metadata to reconstruct from'
                })

        result, candidates, google_raw_count, google_error, gemini_error = search_and_validate_image(question_data, subject, return_debug=True)

        sanitized = _sanitize_search_terms(image_search_terms)
        used_query = sanitized[0] if sanitized else ''
        gemini_prompt_text = build_gemini_prompt(question_data) if question_data else ''

        return jsonify({
            'used_query': used_query,
            'search_terms': sanitized,
            'image_type': image_type,
            'google_raw_count': google_raw_count,
            'google_error': google_error,
            'gemini_error': gemini_error,
            'candidates': candidates,
            'selected_url': result['url'] if result else None,
            'threshold': 80,
            'gemini_prompt': gemini_prompt_text,
        })
    except Exception as e:
        logger.error(f"image_search_debug error: {e}")
        return jsonify({'error': str(e)}), 500


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

        # Normalise field names for questions generated by the professor pipeline
        if content_type == 'qbank':
            for q in items:
                if 'correct_answer' in q and not q.get('correct_option'):
                    q['correct_option'] = q.pop('correct_answer')
                if 'bloom_level' in q and not q.get('blooms_level'):
                    q['blooms_level'] = q.pop('bloom_level')
                bl = q.get('blooms_level', '')
                if bl and bl[0].isdigit() and len(bl) > 1:
                    q['blooms_level'] = bl[0]

        logger.info(f"🔍 Council of Models batch validation: {len(items)} {content_type}(s)")
        logger.info(f"   Domain: {domain}, Course: {course}")

        import re as _re

        # ---- Pre-screen QBank for structural failures (missing images) ----
        pre_scored = {}   # original_index → result dict
        valid_indices = list(range(len(items)))  # indices to actually send to models

        if content_type == 'qbank':
            valid_indices = []
            for i, q in enumerate(items):
                question_text = q.get('question', '').strip()
                image_url = q.get('image_url', '')
                needs_image = bool(image_url) or bool(_IMAGE_REF_RE.search(question_text))

                if not question_text:
                    reason = "Question text is empty — cannot validate"
                    pre_scored[i] = _make_structural_failure(i + 1, '', reason)
                    logger.info(f"   ⚠️  Q{i+1}: structural failure — {reason}")
                elif not q.get('correct_option') and not q.get('correct_answer'):
                    reason = "No correct answer specified — cannot validate"
                    pre_scored[i] = _make_structural_failure(i + 1, question_text, reason)
                    logger.info(f"   ⚠️  Q{i+1}: structural failure — {reason}")
                elif needs_image and image_url and not _image_available(image_url):
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
                    # Try to load; if external URL fails, cache locally and retry once
                    img_data, media_type = _load_image_as_base64(image_url)
                    if not img_data and image_url.startswith('http'):
                        cached = _download_and_cache_image({'url': image_url})
                        local_url = cached.get('url', image_url)
                        if local_url != image_url:
                            img_data, media_type = _load_image_as_base64(local_url)
                            if img_data:
                                q['image_url'] = local_url  # update for future calls
                    if img_data:
                        q_blocks.append({
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": img_data}
                        })
                        images_embedded += 1
                        logger.info(f"   🖼️  Q{pos}: embedded image ({media_type})")
                    else:
                        # Don't tell the LLM to treat as missing — it IS attached, just temporarily unloadable
                        q_blocks.append({"type": "text", "text": "[IMAGE ATTACHED — could not be embedded for validation; assume the image exists and evaluate accordingly]\n"})
                        logger.warning(f"   ⚠️  Q{pos}: image present but failed to load from {image_url}")

                section_block_ranges.append((block_start, len(q_blocks)))

            logger.info(f"   📸 {images_embedded}/{len(valid_items)} questions have embedded images")
            content_payload = q_blocks
        else:
            return jsonify({'error': 'Invalid content_type. Must be "lesson" or "qbank"'}), 400

        validator_results = []
        adversarial_results = []

        # Lessons: batch 4 — enough context for the model to calibrate scores across sections,
        # still fast because all batches run in parallel.
        # Lesson: 4 sections/batch. QBank: 1 question/call — guarantees exactly 1 result per call,
        # eliminating all "model returned fewer items" batch-alignment bugs.
        BATCH_SIZE = 4 if content_type == 'lesson' else 1

        validator_results   = []
        adversarial_results = []

        if valid_items:
            # Helper to build user message content (string or list)
            def _make_user_content(prompt_text, payload):
                if isinstance(payload, list):
                    return [{"type": "text", "text": f"{prompt_text}\n\nContent to validate:\n"}] + payload
                else:
                    return f"{prompt_text}\n\nContent to validate:\n{payload}"

            def _call_validator(prompt, payload, temperature):
                """OpenRouter validator agent (OR_VALIDATOR_MODEL)."""
                content = _make_user_content(prompt, payload)
                # Convert Anthropic-style content list to OpenAI format if needed
                if isinstance(content, list):
                    oai_content = []
                    for block in content:
                        if block.get('type') == 'text':
                            oai_content.append({"type": "text", "text": block['text']})
                        elif block.get('type') == 'image':
                            src = block.get('source', {})
                            if src.get('type') == 'base64':
                                oai_content.append({
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{src['media_type']};base64,{src['data']}"}
                                })
                else:
                    oai_content = content
                resp_text = _or_call(None, model=OR_VALIDATOR_MODEL, max_tokens=8000, temperature=temperature,
                                     messages=[{"role": "user", "content": oai_content}])
                return resp_text.strip()

            def _call_adversarial(prompt, payload, temperature):
                """OpenRouter adversarial agent (OR_ADVERSARIAL_MODEL) — multimodal, same as validator."""
                content = _make_user_content(prompt, payload)
                if isinstance(content, list):
                    oai_content = []
                    for block in content:
                        if block.get('type') == 'text':
                            oai_content.append({"type": "text", "text": block['text']})
                        elif block.get('type') == 'image':
                            src = block.get('source', {})
                            if src.get('type') == 'base64':
                                oai_content.append({
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{src['media_type']};base64,{src['data']}"}
                                })
                else:
                    oai_content = content
                return _or_call(None, model=OR_ADVERSARIAL_MODEL, max_tokens=8000, temperature=temperature,
                                messages=[{"role": "user", "content": oai_content}])

            validator_prompt = get_batch_validator_prompt(content_type, domain)
            adversarial_prompt = get_batch_adversarial_prompt(content_type, domain)

            # Pre-compute all batch specs
            # Re-number questions Q1..N within each batch so the model always uses
            # 1-based question_number regardless of global position.
            batch_specs = []
            for b_start in range(0, len(valid_items), BATCH_SIZE):
                b_end = min(b_start + BATCH_SIZE, len(valid_items))
                batch_count = b_end - b_start
                first_block = section_block_ranges[b_start][0]
                last_block  = section_block_ranges[b_end - 1][1]
                raw_payload = content_payload[first_block:last_block]
                # Re-number text blocks: replace "--- Q{global} ---" with "--- Q{local} ---"
                renumbered = []
                local_q = 0
                for block in raw_payload:
                    if block.get('type') == 'text' and block['text'].lstrip().startswith('--- Q'):
                        local_q += 1
                        renumbered.append({**block, 'text': block['text'].replace(
                            f'--- Q{b_start + local_q} ---', f'--- Q{local_q} ---', 1)})
                    else:
                        renumbered.append(block)
                batch_specs.append((b_start, b_end, batch_count, renumbered))

            num_batches = len(batch_specs)
            MAX_CONCURRENT = 8 if content_type == 'qbank' else 3
            logger.info(f"   🔍 Phase 1 — Validator: {len(valid_items)} item(s), {num_batches} call(s), {MAX_CONCURRENT} concurrent...")

            from concurrent.futures import ThreadPoolExecutor, as_completed

            v_slots = [None] * len(valid_items)
            a_slots = [None] * len(valid_items)

            def _run_one_validator_batch(b_start, b_end, batch_count, payload):
                batch_num = b_start // BATCH_SIZE + 1
                logger.info(f"      [V{batch_num}] items {b_start+1}–{b_end}...")
                text = _call_validator(validator_prompt, payload, 0.3)
                results = _extract_json_array(text, batch_count)[:batch_count]
                if len(results) < batch_count:
                    logger.warning(f"      [V{batch_num}] short ({len(results)}/{batch_count}), retrying...")
                    text2 = _call_validator(validator_prompt, payload, 0.1)
                    results2 = _extract_json_array(text2, batch_count)[:batch_count]
                    if len(results2) > len(results):
                        results = results2
                logger.info(f"      [V{batch_num}] → {len(results)}/{batch_count}")
                return b_start, b_end, results

            def _run_one_adversarial_batch(b_start, b_end, batch_count, payload):
                batch_num = b_start // BATCH_SIZE + 1
                logger.info(f"      [A{batch_num}] items {b_start+1}–{b_end}...")
                text = _call_adversarial(adversarial_prompt, payload, 0.5)
                results = _extract_json_array(text, batch_count)[:batch_count]
                if len(results) < batch_count:
                    logger.warning(f"      [A{batch_num}] short ({len(results)}/{batch_count}), retrying...")
                    text2 = _call_adversarial(adversarial_prompt, payload, 0.3)
                    results2 = _extract_json_array(text2, batch_count)[:batch_count]
                    if len(results2) > len(results):
                        results = results2
                logger.info(f"      [A{batch_num}] → {len(results)}/{batch_count}")
                return b_start, b_end, results

            def _fill_slots(slots, b_start, batch_count, results):
                """Fill result slots using question_number/section_number from response (1-based within batch)."""
                for j, r in enumerate(results):
                    if not isinstance(r, dict):
                        continue
                    q_num = r.get('question_number') or r.get('section_number')
                    if isinstance(q_num, int) and 1 <= q_num <= batch_count:
                        slot = b_start + q_num - 1
                    else:
                        slot = b_start + j  # fallback: positional
                    if 0 <= slot < len(slots):
                        slots[slot] = r

            # Phase 1: all validator batches (max MAX_CONCURRENT concurrent)
            with ThreadPoolExecutor(max_workers=min(num_batches, MAX_CONCURRENT)) as executor:
                futures = [executor.submit(_run_one_validator_batch, *spec) for spec in batch_specs]
                for future in as_completed(futures):
                    try:
                        b_start, b_end, results = future.result()
                        _fill_slots(v_slots, b_start, b_end - b_start, results)
                    except Exception as e:
                        logger.error(f"Validator batch error: {e}")

            logger.info(f"   ✓ Validator complete — {sum(1 for r in v_slots if r is not None)}/{len(v_slots)} results")
            logger.info(f"   ⚔️  Phase 2 — Adversarial: {num_batches} batch(es)...")

            # Phase 2: all adversarial batches (max 3 concurrent)
            with ThreadPoolExecutor(max_workers=min(num_batches, MAX_CONCURRENT)) as executor:
                futures = [executor.submit(_run_one_adversarial_batch, *spec) for spec in batch_specs]
                for future in as_completed(futures):
                    try:
                        b_start, b_end, results = future.result()
                        _fill_slots(a_slots, b_start, b_end - b_start, results)
                    except Exception as e:
                        logger.error(f"Adversarial batch error: {e}")

            validator_results   = v_slots
            adversarial_results = a_slots
            logger.info(f"   ✓ Adversarial complete — {sum(1 for r in a_slots if r is not None)}/{len(a_slots)} results")

        def _enforce_needs_revision(v, a, ctype):
            # needs_revision is now driven purely by combined score in generate_overall_assessment.
            # Clear any model-set boolean flags so they don't interfere.
            v.pop('needs_revision', None)
            a.pop('needs_revision', None)
            return v, a

        # ---- Merge results back in original order ----
        merged_items = []
        valid_pos = 0
        for i in range(len(items)):
            if i in pre_scored:
                merged_items.append(pre_scored[i])
            else:
                v = validator_results[valid_pos] if valid_pos < len(validator_results) else None
                a = adversarial_results[valid_pos] if valid_pos < len(adversarial_results) else None
                # If the batch slot came back empty, record as parse miss (not "Needs Revision")
                if not v and not a:
                    merged_items.append(_make_parse_miss(i + 1))
                else:
                    if not isinstance(v, dict): v = {}
                    if not isinstance(a, dict): a = {}
                    v, a = _enforce_needs_revision(v, a, content_type)
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
            sum(item["overall_assessment"].get("quality_score") or 0 for item in merged_items) / total, 2
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
    """
    Combined score = validator (1-10) + adversarial (1-10) = max 20.
    Both models rate 10 as best (nothing to fix), 1 as unacceptable.
    Thresholds:
      ≤ 10 : Needs Revision
      11–15: Conditional — worth a look
      ≥ 16 : All Good
    """
    validator_score   = validator_result.get('overall_accuracy_score')
    adversarial_score = adversarial_result.get('adversarial_score')

    # If either score is missing (parse miss or structural failure), fall back to 5 per model
    if validator_score is None:   validator_score   = 5
    if adversarial_score is None: adversarial_score = 5

    combined = validator_score + adversarial_score  # 2–20

    if combined <= 10:
        status        = "❌ Needs Revision"
        needs_revision = True
        recommendation = "Genuine errors detected — review changes required."
    elif combined <= 15:
        status        = "⚠️ Conditional"
        needs_revision = False
        recommendation = "No critical errors, but reviewers flagged areas worth a quick look."
    else:
        status        = "✅ All Good"
        needs_revision = False
        recommendation = "Both reviewers found no significant issues."

    return {
        "status": status,
        "quality_score": combined,
        "validator_score": validator_score,
        "adversarial_score": adversarial_score,
        "needs_revision": needs_revision,
        "recommendation": recommendation
    }


@app.route('/api/deduplicate-mock', methods=['POST'])
def deduplicate_mock():
    """
    Post-generation duplicate removal for mock exam questions.
    Uses word-level Jaccard similarity on question stems (stopwords excluded).
    Questions with similarity >= threshold are considered near-duplicates;
    the later one is dropped (first occurrence kept).
    Returns { kept: [...], removed_count: N, removed_indices: [...] }
    """
    try:
        data = request.json or {}
        questions = data.get('questions', [])
        threshold = float(data.get('threshold', 0.70))  # 70% word overlap = near-duplicate

        if not questions:
            return jsonify({'kept': [], 'removed_count': 0, 'removed_indices': []})

        _STOPWORDS = {
            'a','an','the','is','are','was','were','be','been','being','have','has','had',
            'do','does','did','will','would','could','should','may','might','shall','can',
            'of','in','on','at','to','for','with','by','from','about','as','into','through',
            'during','including','until','against','among','throughout','despite','towards',
            'upon','concerning','and','but','or','nor','so','yet','both','either','neither',
            'not','no','this','that','these','those','which','who','whom','what','whose',
            'he','she','it','they','we','you','i','his','her','its','their','our','your',
            'patient','presents','year','old','man','woman','history','following','most',
            'likely','diagnosis','next','best','step','management','which','associated',
        }

        def _stem_tokens(text):
            words = re.findall(r'[a-z]+', text.lower())
            return set(w for w in words if w not in _STOPWORDS and len(w) > 2)

        def _jaccard(a, b):
            if not a or not b:
                return 0.0
            inter = len(a & b)
            union = len(a | b)
            return inter / union if union else 0.0

        token_sets = [_stem_tokens(q.get('question', '')) for q in questions]

        kept_indices = []
        removed_indices = []

        for i in range(len(questions)):
            is_dup = False
            for j in kept_indices:
                sim = _jaccard(token_sets[i], token_sets[j])
                if sim >= threshold:
                    is_dup = True
                    logger.info(
                        f"  Dedup: Q{i+1} is near-duplicate of Q{j+1} (Jaccard={sim:.2f}) — removing Q{i+1}"
                    )
                    break
            if is_dup:
                removed_indices.append(i)
            else:
                kept_indices.append(i)

        kept = [questions[i] for i in kept_indices]
        logger.info(f"Dedup: {len(questions)} → {len(kept)} questions ({len(removed_indices)} removed)")
        return jsonify({
            'kept': kept,
            'removed_count': len(removed_indices),
            'removed_indices': removed_indices,
        })
    except Exception as e:
        logger.error(f"deduplicate_mock error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/adjust-mock-specs', methods=['POST'])
def adjust_mock_specs():
    """Adjust mock exam specs based on a free-text user request."""
    try:
        data = request.json
        specs = data.get('specs', {})
        message = data.get('message', '').strip()
        if not message:
            return jsonify({'error': 'No message provided'}), 400

        prompt = f"""You are adjusting official mock exam specifications based on a user request.

Current specs (JSON):
{json.dumps(specs, indent=2)}

User request: {message}

Apply the requested change and return the updated specs as a JSON object with the same structure, plus a plain-English "response" field (1-2 sentences) describing what you changed.

Rules:
- subject_distribution question counts must still sum to total_questions
- If image_questions_total is changed, keep it ≤ total_questions
- Preserve any fields the user did not ask to change
- Return ONLY valid JSON, no markdown fences"""

        result_text = _or_call(prompt, model=OR_VALIDATOR_MODEL, max_tokens=4000, temperature=0.1)

        if '```json' in result_text:
            result_text = result_text.split('```json')[1].split('```')[0].strip()
        elif '```' in result_text:
            result_text = result_text.split('```')[1].split('```')[0].strip()

        updated = json.loads(result_text)
        return jsonify(updated)
    except Exception as e:
        logger.error(f"adjust-mock-specs error: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5001)

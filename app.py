"""
QBank Generator - Flask Backend
Generates MCQs for NEET PG and USMLE using Claude API
"""

import json
import os
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

    # Try Open-i (NIH) - more aggressive search
    try:
        url = "https://openi.nlm.nih.gov/api/search"
        image_type_map = {
            'X-ray': 'xg', 'CT scan': 'ct', 'CT': 'ct', 'MRI': 'mri', 'Ultrasound': 'us',
            'Microscopy': 'mi', 'Gram stain': 'mi', 'Histopathology': 'mi',
            'Culture plate': 'mi', 'Microscopy stain': 'mi'
        }
        it_param = image_type_map.get(image_type, 'xg,ct,mri,us,mi')

        # Try ALL search terms (not just first 2)
        for search_term in image_search_terms[:5]:
            params = {'query': search_term, 'it': it_param, 'm': 1, 'n': 15}
            response = requests.get(url, params=params, timeout=15)
            data = response.json()

            if 'list' in data:
                for item in data['list'][:3]:  # Take top 3 from each search (increased from 2)
                    if 'imgLarge' in item:
                        candidates.append({
                            'url': f"https://openi.nlm.nih.gov{item['imgLarge']}",
                            'source': 'Open-i (NIH)',
                            'title': item.get('title', '')[:100]
                        })
                        if len(candidates) >= max_candidates:
                            return candidates
    except Exception as e:
        logger.error(f"Open-i collection error: {e}")

    # Try Wikimedia Commons - more aggressive search
    try:
        url = "https://commons.wikimedia.org/w/api.php"
        for search_term in image_search_terms[:5]:  # Increased from 2 to 5
            params = {
                'action': 'query', 'format': 'json', 'generator': 'search',
                'gsrnamespace': 6, 'gsrsearch': f"{search_term} medical",
                'gsrlimit': 15, 'prop': 'imageinfo', 'iiprop': 'url|mime', 'iiurlwidth': 600
            }
            response = requests.get(url, params=params, timeout=20)
            if response.status_code == 200:
                data = response.json()
                if 'query' in data and 'pages' in data['query']:
                    for page_id, page in list(data['query']['pages'].items())[:3]:  # Increased from 2 to 3
                        if 'imageinfo' in page and len(page['imageinfo']) > 0:
                            img_info = page['imageinfo'][0]
                            mime = img_info.get('mime', '')
                            if mime.startswith('image/') and 'svg' not in mime.lower():
                                candidates.append({
                                    'url': img_info.get('thumburl', img_info.get('url')),
                                    'source': 'Wikimedia Commons',
                                    'title': page.get('title', '').replace('File:', '')
                                })
                                if len(candidates) >= max_candidates:
                                    return candidates
    except Exception as e:
        logger.error(f"Wikimedia collection error: {e}")

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


def generate_for_topic(course, subject, topic, num_questions, include_images=False):
    """Generate questions for a single topic."""
    # Get base prompt
    if course == 'NEET PG':
        prompt = get_neet_prompt(subject, topic, num_questions)
    elif course == 'USMLE':
        prompt = get_usmle_prompt(subject, topic, num_questions)
    else:
        raise ValueError('Invalid course')

    # Add image requirements if requested
    if include_images:
        image_instructions = """

IMPORTANT: These must be IMAGE-BASED questions. For each question, you MUST analyze what the KEY DIAGNOSTIC FINDING is that needs to be visualized.

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

- "image_search_terms": Array of 3-5 HIGHLY SPECIFIC medical search queries using precise clinical terminology. **IMPORTANT: Add "unlabeled" or "no text" to search terms to avoid finding images with answer text visible**. Include:
  * Primary: [condition] + [modality] + [key finding] + "unlabeled"
  * Secondary: [specific pathologic sign/pattern] + [medical term] + "no text"
  * Tertiary: [differential diagnosis term] + "clinical image"
  Examples:
  * ["lobar pneumonia chest x-ray air bronchogram unlabeled", "right lower lobe consolidation radiology no annotations", "pneumococcal pneumonia imaging clinical"]
  * ["multiple sclerosis MRI dawson fingers unlabeled", "periventricular white matter lesions T2 no text", "demyelinating plaques brain clinical"]
  * ["inferior STEMI ECG unlabeled", "ST elevation leads II III aVF no diagnosis text", "inferior wall myocardial infarction EKG clinical"]

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
        prompt = prompt.replace("Output ONLY the JSON array, no other text.", image_instructions + "\n\nOutput ONLY the JSON array, no other text.")

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

    # Validate
    if not all([course, subject]) or not topics:
        return jsonify({'error': 'Missing required fields'}), 400

    if num_questions < 5 or num_questions > 50:
        return jsonify({'error': 'Number of questions must be between 5 and 50'}), 400

    if course not in ['NEET PG', 'USMLE']:
        return jsonify({'error': 'Invalid course'}), 400

    try:
        all_questions = []
        logger.info(f"Generating {num_questions} questions per topic for {len(topics)} topics (images={include_images})")

        # Generate questions for each topic
        for topic in topics:
            topic_questions = generate_for_topic(course, subject, topic, num_questions, include_images)
            all_questions.extend(topic_questions)

        # Calculate image statistics if images were requested
        image_stats = None
        if include_images:
            images_with_url = sum(1 for q in all_questions if q.get('image_url'))
            images_missing = sum(1 for q in all_questions if q.get('needs_image'))
            image_stats = {
                'total_image_questions': len(all_questions),
                'images_found': images_with_url,
                'images_missing': images_missing,
                'success_rate': f"{(images_with_url/len(all_questions)*100):.1f}%" if all_questions else "0%"
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
    """Parse lesson content and integrate actual images where placeholders exist."""
    import re

    # Vague terms that should use Mermaid/tables instead of images
    vague_terms = [
        'pathway', 'flowchart', 'algorithm', 'diagram', 'mechanism', 'cascade',
        'process', 'cycle', 'overview', 'summary', 'treatment plan', 'management',
        'approach', 'strategy', 'decision tree', 'flow', 'schematic'
    ]

    # Find all image placeholders with Figure numbers: **Figure N: [Image: description]**
    # Pattern captures: Figure number and description
    image_pattern = r'\*\*Figure (\d+):\s*\[Image:\s*([^\]]+)\]\*\*'
    matches = re.finditer(image_pattern, lesson_content)

    replacements = []
    for match in matches:
        figure_num = match.group(1)
        description = match.group(2).strip()
        full_placeholder = match.group(0)

        # Check if description is too vague (should use Mermaid instead)
        description_lower = description.lower()
        is_vague = any(term in description_lower for term in vague_terms)

        if is_vague:
            logger.warning(f"⚠️ Figure {figure_num} description is too vague: '{description}' - keeping placeholder (should use Mermaid/table instead)")
            continue  # Skip this image, keep placeholder

        # Check if it's a specific medical investigation type
        specific_terms = ['ecg', 'x-ray', 'ct', 'mri', 'ultrasound', 'histology',
                         'histopathology', 'microscopy', 'endoscopy', 'photograph',
                         'blood film', 'smear', 'angiography', 'anatomical']
        is_specific = any(term in description_lower for term in specific_terms)

        if not is_specific:
            logger.warning(f"⚠️ Figure {figure_num} not specific enough: '{description}' - skipping")
            continue

        # Create image metadata for search
        image_metadata = {
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
            # Use existing image search function
            image_result = search_and_validate_image(image_metadata, subject)

            if image_result:
                # Replace with markdown image + caption below
                image_url = image_result['url']
                image_alt = description
                markdown_with_caption = f"![{image_alt}]({image_url})\n*Figure {figure_num}: {description}*"
                replacements.append((full_placeholder, markdown_with_caption))
                logger.info(f"✓ Found image for Figure {figure_num}")
            else:
                logger.warning(f"✗ No image found for Figure {figure_num}")
                # Keep the placeholder if no image found

        except Exception as e:
            logger.error(f"Error searching for image '{description}': {e}")

    # Apply all replacements
    for old, new in replacements:
        lesson_content = lesson_content.replace(old, new)

    return lesson_content


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

                # Parse chapters (can be strings or objects)
                for chapter in topic_data.get('chapters', []):
                    if isinstance(chapter, str):
                        topic_entry['chapters'].append({'name': chapter})
                    elif isinstance(chapter, dict):
                        chapter_entry = {'name': chapter.get('name')}
                        # Preserve optional fields like nice_refs
                        if 'nice_refs' in chapter:
                            chapter_entry['nice_refs'] = chapter['nice_refs']
                        topic_entry['chapters'].append(chapter_entry)

                structure.append(topic_entry)

            # Generate lessons using OnCourse prompt
            for topic_data in structure:
                topic_name = topic_data.get('topic')
                chapters = topic_data.get('chapters', [])
                high_yield = topic_data.get('high_yield', False)

                # Prepare chapter list for prompt
                chapter_list = []
                for chapter in chapters:
                    if isinstance(chapter, dict):
                        chapter_entry = {'name': chapter.get('name')}
                        if 'nice_refs' in chapter:
                            chapter_entry['nice_refs'] = chapter['nice_refs']
                        chapter_list.append(chapter_entry)
                    else:
                        chapter_list.append({'name': chapter})

                chapter_list_json = json.dumps(chapter_list, indent=2)

                # Generate topic-level lesson using Claude
                logger.info(f"Generating lesson for {subject} > {topic_name}")

                lesson_prompt = f"""====================  ONCOURSE LESSON PROMPT  ====================
- Subject      : {subject}
- Topic        : {topic_name}
- ChaptersJSON : {chapter_list_json}
- WordTarget   : 1000-1200 words max | 7 pages max
- Audience     : Medical licensing exam candidates (UKMLA/NEET PG/USMLE level)
- Depth Level  : Clinical practitioner level - assume medical school foundation knowledge
==========================================================================

🔴 CRITICAL MANDATORY REQUIREMENTS (NON-NEGOTIABLE):
1. MUST end with "### High Yield Summary" section (Key Take-Aways, Essential Numbers, Clinical Pearls, Quick Reference)
2. MUST integrate chapter names INSIDE sentences throughout ALL sections - NOT as a list at the end!
   ✅ CORRECT: "Acute coronary syndromes (see Acute coronary syndrome management) present with chest pain..."
   ❌ WRONG: Having a "Related Chapters:" list at the end of sections
   → Weave chapter names naturally when discussing each clinical concept
3. MUST use [Image: description] format: **Figure 1: [Image: ECG showing STEMI]**
4. MUST include 2-3 ```mermaid flowcharts for algorithms/pathways
==========================================================================

===========  CLINICAL RIGOR REQUIREMENTS  ===========
✓ Write for qualified doctors preparing for licensing exams - NOT medical students
✓ Assume foundational anatomy/physiology/pathology knowledge - focus on CLINICAL APPLICATION
✓ Include evidence-based medicine with specific guidelines (NICE, ESC, AHA where applicable)
✓ Specific drug dosages, timing, monitoring parameters, contraindications
✓ Specific diagnostic thresholds with sensitivity/specificity where relevant
✓ Clinical decision-making with real-world trade-offs and nuances
✓ Red flags, complications, and when to escalate/refer
✓ Medicolegal considerations where relevant (consent, capacity, safeguarding)
✓ Cost-effectiveness and resource allocation awareness (especially for UK candidates)
✓ Depth over breadth - better to cover fewer concepts thoroughly than many superficially

===========  NICE GUIDELINE & EVIDENCE INTEGRATION  ===========
✓ When chapters have 'nice_refs' in ChaptersJSON, reference these guidelines naturally
✓ Cite specific guideline numbers (e.g., "NICE NG136 recommends clinic BP <140/90 for treatment")
✓ Include guideline-specific thresholds, algorithms, and recommendations
✓ Mention updates or controversies in guidelines where clinically important
✓ Reference other evidence (landmark trials, meta-analyses) where relevant for depth
✓ UK-specific practice points for UKMLA (e.g., NHS pathways, formulary restrictions)

===========  ONCOURSE BRAND VOICE  ===========
✓ Professional yet engaging - authoritative clinical voice with narrative flow
✓ Conversational but clinically sophisticated
✓ Evidence-based explanations with mechanistic depth
✓ Concrete clinical scenarios over abstract theory
✓ Specific numbers, thresholds, dosages, timings throughout
✓ Confidence-building through mastery of clinical nuance
✓ NO explicit mentions of "exams", "examiners", "toppers", "candidates", "test", "assessment"
✓ Capture clinical excellence through depth and precision, not exam rhetoric

===========  BLOOM'S PROGRESSION STRUCTURE (Levels 1-7)  ===========
IMPORTANT: Do NOT include "Page 1", "Page 2" etc. in section headers - use only the topic-specific titles.

### [Topic-Specific Memorable Title for Foundation/Remember]
**Core Knowledge Building**
* Engaging clinical vignette or scenario hook ≤25 words
* Essential classifications with clinical significance (not just lists)
* Evidence-based definitions and diagnostic criteria with specific thresholds
* Epidemiology with absolute numbers (incidence, prevalence, mortality where relevant)
* Must-know mnemonics linked to clinical decision-making
* TABLE with key classifications or criteria
* 🔴 OPTIONAL: Include 1 essential clinical image ONLY if truly necessary
  → Examples: "ECG showing STEMI in leads II, III, aVF", "Chest X-ray showing tension pneumothorax"
  → Most topics won't need an image here - use table instead
* 🔴 MANDATORY: Integrate 1-2 chapter names NATURALLY IN SENTENCES (not at section end):
  → "Acute coronary syndromes (see Acute coronary syndrome management) present with..."
  → "Hypertension diagnosis (see Hypertension diagnosis and management) requires BP >140/90..."

### 2 — [Topic-Specific Title for Mechanisms/Understand]
**Pathophysiology & Clinical Mechanisms**
* Mechanistic understanding that explains clinical presentations
* Molecular/cellular basis linked to macroscopic clinical findings
* WHY certain investigations work, WHY certain treatments target specific pathways
* Pharmacodynamics and pharmacokinetics with clinical implications
* Quantitative relationships (e.g., Starling forces, oxygen delivery equations)
* ```mermaid flowchart showing pathophysiological pathway/cascade (MANDATORY)
* Table linking mechanisms to clinical manifestations
* 🔴 OPTIONAL: Include anatomical image ONLY if essential for understanding mechanism
* 🔴 Integrate 1-3 chapter names INSIDE sentences (e.g., "RAAS activation in heart failure (see Heart failure pathophysiology) leads to...")

### 3 — [Topic-Specific Title for Clinical Application/Apply]
**Clinical Presentations & Diagnostic Approach**
* Real clinical scenarios with presenting complaints and examination findings
* Diagnostic approach with pre-test probability considerations
* Investigation sequence with sensitivity/specificity/PPV/NPV where relevant
* Interpretation of results in clinical context (not just normal ranges)
* When to investigate further vs when to act on clinical diagnosis
* ```mermaid flowchart for diagnostic algorithm (MANDATORY)
* Table with likelihood ratios and diagnostic accuracy
* Red flags requiring urgent action
* 🔴 OPTIONAL: Include 1 diagnostic investigation image if pathognomonic/essential
  → Examples: "ECG showing AF with absent P waves", "Chest X-ray showing lobar pneumonia"
  → Only if the visual finding is critical for diagnosis
* 🔴 Integrate 2-3 chapter names INSIDE sentences (e.g., "Acute coronary syndromes (see ACS diagnosis and risk stratification) present with...")

### 4 — [Topic-Specific Title for Analysis/Analyze]
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

### 5 — [Topic-Specific Title for Evaluation/Evaluate]
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

### 6 — [Topic-Specific Title for Advanced Integration/Synthesize]
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
* 5-7 bullet points with the most critical clinical concepts
* Include specific numbers, thresholds, and dosages
* Red flags that cannot be missed
* Evidence-based recommendations with NICE refs

**Essential {topic_name} Numbers:**
* Critical thresholds for diagnosis and treatment (table format)
* Most commonly used drug dosages
* Key timing parameters (when to treat, monitor, refer)

**Clinical Pearls:**
* 3-5 practical pearls from clinical experience
* Common pitfalls and how to avoid them
* Pattern recognition tips

**Quick Reference:**
* SUMMARY TABLE with key numbers/thresholds (MANDATORY)
* ```mermaid flowchart for quick reference algorithm if needed (OPTIONAL)
* Decision rules and clinical scores
* Safety-critical points and medicolegal considerations
* 🔴 NO images needed in summary - tables and mermaid only

**Related Chapters:**
* ONLY list chapters from ChaptersJSON that were NOT already integrated into the text above
* If all chapters were already mentioned in the lesson, write "All chapters covered above"
* Do NOT repeat chapters that were already woven into the narrative

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
✓ 2-3 ```mermaid flowcharts for algorithms/decision trees (MANDATORY)
✓ Tables with quantitative data in every section (MANDATORY)
✓ Concrete numbers, dosages, thresholds, percentages throughout (MANDATORY)
✓ 1-3 [Image: ...] ONLY if truly essential clinical images (OPTIONAL - be selective!)
  → Most topics should have 0-2 images maximum
  → Only include if the image is absolutely necessary for understanding
  → When in doubt, use a table or mermaid instead
✓ Engaging, confidence-building language
✓ Memory hooks and mnemonics with quantitative elements

🔴🔴🔴 CHAPTER INTEGRATION RULES (CRITICAL - DO NOT VIOLATE): 🔴🔴🔴
✓ All chapter names must use EXACT names from ChaptersJSON - no variations
✓ Integrate chapter names INSIDE sentences when discussing each concept
✓ Format: "Clinical concept (see Chapter Name) explanation continues..."
  - Example: "Hypertension diagnosis (see Hypertension diagnosis and management) requires..."
  - Example: "Risk stratification (see Cardiovascular risk assessment) uses QRISK3..."
  - Example: "Atrial fibrillation (see Atrial fibrillation and anticoagulation) management depends on..."
✓ Each section MUST integrate 1-3 chapter names naturally in flowing text
✓ NEVER create separate "Related Chapters:" lists within sections
✓ NEVER list chapters as bullet points at section ends
✓ Chapters should feel like natural cross-references, not forced insertions
✓ Visual elements should enhance understanding, not just fill space
✓ For images: Use format [Image: specific medical visual description] - be precise about what anatomical structure, pathology, chart type, or diagram is needed
✓ End lesson with "High Yield Summary" section containing most testable concepts
✓ Prioritize diagrams, anatomical illustrations, flowcharts, and reference wheels over decorative images

===========  IMAGE STRATEGY (CRITICAL - READ CAREFULLY)  ===========
🔴 IMAGES ARE EXPENSIVE AND OFTEN FAIL - BE EXTREMELY SELECTIVE! 🔴

STEP 1: Before writing, identify 2-3 ESSENTIAL medical images for this topic
→ Ask yourself: "What would a doctor MUST see to understand this clinically?"
→ NOT decorative, NOT conceptual, NOT flowcharts - ONLY essential clinical images

STEP 2: Only include images that are:
✅ Actual medical investigations (ECG, X-ray, CT, histology, endoscopy)
✅ Critical anatomy that's hard to explain in words
✅ Pathognomonic clinical signs (rashes, physical findings)
✅ Lab results that are diagnostic (blood films, cultures)

❌ NEVER include:
❌ Calculators or interfaces (like QRISK3 calculator)
❌ Generic charts or graphs
❌ Flowcharts or algorithms (use ```mermaid instead)
❌ "Overview" or "summary" diagrams
❌ Conceptual illustrations

STEP 3: Image format when essential image identified:
**Figure N: [Image: HIGHLY SPECIFIC description]**
Examples of GOOD descriptions:
- "12-lead ECG showing atrial fibrillation with absent P waves and irregular RR intervals"
- "Chest X-ray PA view showing right upper lobe consolidation with air bronchograms"
- "Fundoscopy photograph showing papilloedema with blurred disc margins"
- "Histopathology H&E stain showing Reed-Sternberg cells in Hodgkin lymphoma"

Examples of BAD descriptions (will be rejected):
- "QRISK3 calculator showing risk assessment"
- "Heart failure risk stratification chart"
- "Treatment pathway overview"
- "Summary of cardiovascular risk factors"

RECOMMENDED IMAGE COUNTS:
- Visual topics (Dermatology, Radiology): 2-3 images
- Clinical topics (Cardiology, Respiratory): 1-2 images
- Theoretical topics (Pharmacology): 0-1 images

✓ MANDATORY: Include 2-3 ```mermaid flowcharts for algorithms/pathways (NOT images)

===========  WRITING STYLE REQUIREMENTS  ===========
✓ Storytelling hooks that paint visual scenarios
✓ Conversational tone ("Here's the thing...", "Think of it this way...")
✓ Concrete examples over abstract concepts
✓ Strategic use of formatting (bold, bullets, tables)
✓ Smooth transitions between Bloom's levels
✓ Make learning exciting through discovery, not pressure
✓ Stealth preparation through strategic content organization

===========  CRITICAL OUTPUT REQUIREMENTS (CHECK BEFORE SUBMITTING)  ===========
🔴 1. IMAGES: Include 0-2 images maximum - ONLY if absolutely essential!
     → Format: **Figure N: [Image: HIGHLY specific description]**
     → Example: **Figure 1: [Image: 12-lead ECG showing atrial fibrillation with absent P waves and irregularly irregular RR intervals]**
     → Ask: "Would a doctor NEED to see this to understand clinically?"
     → When in doubt, use table or mermaid instead
     → NO calculators, NO generic charts, NO concept diagrams

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

                try:
                    # Call Claude API with increased tokens for complete lesson
                    message = client.messages.create(
                        model="claude-sonnet-4-5",
                        max_tokens=8000,  # Increased to ensure complete lesson with all sections
                        temperature=0.7,
                        messages=[{
                            "role": "user",
                            "content": lesson_prompt
                        }]
                    )

                    topic_lesson = message.content[0].text.strip()
                    logger.info(f"✓ Generated lesson for {topic_name} ({len(topic_lesson)} chars)")

                    # Integrate images into the lesson
                    logger.info(f"Integrating images for {topic_name}...")
                    topic_lesson = integrate_images_into_lesson(topic_lesson, subject, topic_name)
                    logger.info(f"✓ Images integrated for {topic_name}")

                except Exception as e:
                    logger.error(f"Error generating lesson for {topic_name}: {e}")
                    topic_lesson = f"Error generating lesson: {str(e)}"

                # Store lesson with metadata
                all_lessons.append({
                    'topic': topic_name,
                    'high_yield': high_yield,
                    'topic_lesson': topic_lesson,
                    'chapters': [{'name': ch.get('name') if isinstance(ch, dict) else ch,
                                  'nice_refs': ch.get('nice_refs', []) if isinstance(ch, dict) else []}
                                 for ch in chapters],
                    'subject': subject
                })

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


if __name__ == '__main__':
    app.run(debug=True, port=5000)

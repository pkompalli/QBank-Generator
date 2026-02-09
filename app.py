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


def search_and_validate_image(question_data, subject):
    """Search for image, validate with Claude Vision, or generate with Nano Banana Pro."""
    image_search_terms = question_data.get('image_search_terms', [])
    image_type = question_data.get('image_type', '')

    if not image_search_terms:
        return None

    # Check cache first
    cached = get_cached_image(image_search_terms, image_type)
    if cached:
        return cached

    print(f"\n🔍 Searching image: {image_type}")

    # Try Open-i (NIH) for radiology
    if image_type in ['X-ray', 'CT scan', 'CT', 'MRI', 'Ultrasound']:
        try:
            url = "https://openi.nlm.nih.gov/api/search"
            params = {'query': image_search_terms[0], 'it': 'xg,ct,mri,us', 'm': 1, 'n': 5}
            response = requests.get(url, params=params, timeout=15)
            data = response.json()
            if 'list' in data and len(data['list']) > 0:
                for item in data['list']:
                    if 'imgLarge' in item:
                        result = {
                            'url': f"https://openi.nlm.nih.gov{item['imgLarge']}",
                            'source': 'Open-i (NIH)',
                            'title': item.get('title', '')[:100]
                        }
                        cache_image(image_search_terms, image_type, result)
                        print(f"✓ Found Open-i image")
                        return result
        except Exception as e:
            logger.error(f"Open-i error: {e}")

    # Try Wikimedia Commons
    try:
        url = "https://commons.wikimedia.org/w/api.php"
        params = {
            'action': 'query', 'format': 'json', 'generator': 'search',
            'gsrnamespace': 6, 'gsrsearch': f"{image_search_terms[0]} medical",
            'gsrlimit': 10, 'prop': 'imageinfo', 'iiprop': 'url|mime', 'iiurlwidth': 600
        }
        response = requests.get(url, params=params, timeout=20)
        if response.status_code == 200:
            data = response.json()
            if 'query' in data and 'pages' in data['query']:
                for page_id, page in data['query']['pages'].items():
                    if 'imageinfo' in page and len(page['imageinfo']) > 0:
                        img_info = page['imageinfo'][0]
                        mime = img_info.get('mime', '')
                        if mime.startswith('image/') and 'svg' not in mime.lower():
                            result = {
                                'url': img_info.get('thumburl', img_info.get('url')),
                                'source': 'Wikimedia Commons',
                                'title': page.get('title', '').replace('File:', '')
                            }
                            cache_image(image_search_terms, image_type, result)
                            print(f"✓ Found Wikimedia image")
                            return result
    except Exception as e:
        logger.error(f"Wikimedia error: {e}")

    # Generate with Nano Banana Pro if nothing found
    if gemini_client:
        try:
            print(f"  → Generating with Nano Banana Pro...")
            image_desc = question_data.get('image_description', '')
            prompt = f"Generate medical {image_type} image: {image_desc}. Professional clinical quality."

            response = gemini_client.models.generate_images(
                model='imagen-3.0-generate-001',
                prompt=prompt,
                config={'number_of_images': 1, 'aspect_ratio': '1:1'}
            )

            if response.images and len(response.images) > 0:
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png', dir='static') as f:
                    f.write(response.images[0].image_bytes)
                    img_path = f.name

                result = {
                    'url': f"/static/{os.path.basename(img_path)}",
                    'source': 'Nano Banana Pro (AI Generated)',
                    'title': f'Generated: {image_type}'
                }
                cache_image(image_search_terms, image_type, result)
                print(f"✓ Generated image")
                return result
        except Exception as e:
            logger.error(f"Generation error: {e}")

    print(f"✗ No image found")
    return None


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

IMPORTANT: These must be IMAGE-BASED questions. For each question, add these fields:
- "image_description": Detailed description of the medical image (e.g., "Chest X-ray showing right lower lobe consolidation with air bronchograms")
- "image_search_terms": Array of 3-5 specific search terms (e.g., ["pneumonia chest X-ray lower lobe", "air bronchogram consolidation", "lobar pneumonia radiology"])
- "image_type": Type of image (e.g., "X-ray", "CT scan", "Gram stain", "Culture plate", "Histopathology slide", "ECG")

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

        response_data = {
            'success': True,
            'questions': all_questions,
            'count': len(all_questions),
            'topics_count': len(topics)
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


if __name__ == '__main__':
    app.run(debug=True, port=5000)

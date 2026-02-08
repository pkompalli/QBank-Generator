"""
QBank Generator - Flask Backend
Generates MCQs for NEET PG and USMLE using Claude API
"""

import json
import os
from flask import Flask, render_template, request, jsonify
from anthropic import Anthropic
from dotenv import load_dotenv

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


def generate_for_topic(course, subject, topic, num_questions):
    """Generate questions for a single topic."""
    # Generate prompt based on course
    if course == 'NEET PG':
        prompt = get_neet_prompt(subject, topic, num_questions)
    elif course == 'USMLE':
        prompt = get_usmle_prompt(subject, topic, num_questions)
    else:
        raise ValueError('Invalid course')
    
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
    
    # Validate
    if not all([course, subject]) or not topics:
        return jsonify({'error': 'Missing required fields'}), 400
    
    if num_questions < 5 or num_questions > 50:
        return jsonify({'error': 'Number of questions must be between 5 and 50'}), 400
    
    if course not in ['NEET PG', 'USMLE']:
        return jsonify({'error': 'Invalid course'}), 400
    
    try:
        all_questions = []
        
        # Generate questions for each topic
        for topic in topics:
            topic_questions = generate_for_topic(course, subject, topic, num_questions)
            all_questions.extend(topic_questions)
        
        return jsonify({
            'success': True,
            'questions': all_questions,
            'count': len(all_questions),
            'topics_count': len(topics)
        })
        
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

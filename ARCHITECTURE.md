# QBank Generator - Modular Architecture

## Overview

The QBank Generator now features a **modular, domain-agnostic architecture** that intelligently generates educational content for any course or exam. The system is built on three core reusable modules that work together to create comprehensive learning materials.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     USER INPUT: Course Name                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  MODULE 1: Course Structure Generator                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Input: Course name, optional reference docs        │   │
│  │  Process: AI-powered hierarchical analysis          │   │
│  │  Output: Course → Subjects → Topics → Chapters      │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
┌───────────────────┐   ┌──────────────────────┐
│  MODULE 2:        │   │  MODULE 3:           │
│  Exam Format      │   │  Lesson Flow         │
│  Analyzer         │   │  Architect           │
│  (for QBank)      │   │  (for Lessons)       │
│                   │   │                      │
│  ├─ Question      │   │  ├─ Bloom's          │
│  │  Format        │   │  │  Progression       │
│  ├─ Bloom's       │   │  ├─ Content          │
│  │  Distribution  │   │  │  Strategy          │
│  ├─ Difficulty    │   │  ├─ Visual           │
│  └─ Domain        │   │  │  Placement         │
│     Characteristics│   │  └─ Memory Aids      │
└────────┬──────────┘   └──────────┬───────────┘
         │                         │
         ▼                         ▼
┌──────────────────┐   ┌─────────────────────┐
│  QBank           │   │  Lesson             │
│  Generation      │   │  Generation         │
└──────────────────┘   └─────────────────────┘
```

## Core Modules

### Module 1: Course Structure Generator

**Purpose**: Generate hierarchical course structure for ANY course/exam

**Function**: `generate_course_structure(course_name, reference_docs=None)`

**Features**:
- ✅ **Domain-agnostic**: Works for medical, engineering, business, certifications
- ✅ **Intelligent hierarchy**: Creates logical Course → Subjects → Topics → Chapters
- ✅ **Reference document support**: Can incorporate uploaded curriculum docs
- ✅ **Reusable**: Single source of truth for both QBank and Lessons

**Output Structure**:
```json
{
  "course": "NEET PG",
  "exam_type": "medical",
  "domain_characteristics": "Clinical medical licensing exam...",
  "subjects": [
    {
      "name": "Cardiology",
      "description": "Cardiovascular diseases and management",
      "topics": [
        {
          "name": "Heart Failure",
          "chapters": [
            {"name": "Acute Heart Failure", "nice_refs": []},
            {"name": "Chronic Heart Failure", "nice_refs": []}
          ]
        }
      ]
    }
  ]
}
```

**Usage Example**:
```python
# Generate structure for any course
structure = generate_course_structure("AWS Solutions Architect")
# Now use this structure for both QBank and Lessons
```

---

### Module 2: Exam Format Analyzer (QBank Specific)

**Purpose**: Determine optimal question format and Bloom's distribution

**Function**: `analyze_exam_format(course_name, course_structure)`

**Features**:
- ✅ **Question format analysis**: MCQ type, number of options, stem complexity
- ✅ **Bloom's distribution**: Intelligent cognitive level percentages
- ✅ **Difficulty distribution**: Easy/Medium/Hard ratios
- ✅ **Domain-specific characteristics**: Clinical vignettes for medical, calculations for engineering

**Output Structure**:
```json
{
  "question_format": {
    "type": "single_best_answer",
    "num_options": 5,
    "avg_stem_words": 50,
    "uses_vignettes": true,
    "image_questions_percentage": 20
  },
  "blooms_distribution": {
    "1_remember": 10,
    "2_understand": 15,
    "3_apply": 35,
    "4_analyze": 25,
    "5_evaluate": 10,
    "6_create": 5,
    "7_integrate": 0
  },
  "difficulty_distribution": {
    "easy": 20,
    "medium": 50,
    "hard": 30
  },
  "domain_characteristics": {
    "key_features": ["clinical_reasoning", "evidence_based"],
    "memory_aids": "mnemonics",
    "visual_elements": "high"
  }
}
```

**Intelligent Bloom's Distribution Examples**:

| Exam Type | Remember | Understand | Apply | Analyze | Evaluate | Create |
|-----------|----------|------------|-------|---------|----------|--------|
| Medical Licensing (USMLE/NEET) | 10% | 15% | 35% | 25% | 10% | 5% |
| Engineering (FE Exam) | 15% | 20% | 30% | 20% | 10% | 5% |
| Business (CPA) | 10% | 20% | 30% | 25% | 10% | 5% |
| Academic Course | 20% | 20% | 25% | 20% | 10% | 5% |

---

### Module 3: Lesson Flow Architect (Lesson Specific)

**Purpose**: Design optimal lesson structure with strategic content placement

**Function**: `design_lesson_flow(course_name, subject, topic, chapters, course_structure)`

**Features**:
- ✅ **Bloom's progression**: Foundation → Integration (7 levels)
- ✅ **Length optimization**: 7-8 pages for topics, 1-2 for chapters
- ✅ **Visual strategy**: Images, tables, flowcharts placement
- ✅ **Domain-specific memory aids**: Mnemonics (medical), formulas (engineering), frameworks (business)

**Output Structure**:
```json
{
  "topic_lesson_plan": {
    "total_words": 1200,
    "sections": [
      {
        "blooms_level": 1,
        "title_pattern": "Foundation/Remember",
        "content_focus": "core knowledge, definitions",
        "word_count": 150,
        "visual_elements": {
          "images": 2,
          "tables": 1,
          "flowcharts": 0
        },
        "memory_aids": true
      }
      // ... 6 more sections for Bloom's 2-7
    ]
  },
  "chapter_lesson_plan": {
    "total_words": 400,
    "sections": ["Quick Overview", "Core Facts", "Problem-Solving",
                 "Analysis Framework", "Visual Aid", "Key Points"],
    "visual_elements": {
      "images": 1,
      "tables_or_flowcharts": 1
    }
  },
  "memory_aids_strategy": {
    "type": "mnemonics",  // or "formulas", "frameworks", "acronyms"
    "frequency": "per_section",
    "examples": ["SAMPLE", "ACRONYM"]
  }
}
```

**Domain-Specific Memory Aids**:
- **Medical**: Mnemonics (HEART FACTS), Clinical Pearls
- **Engineering**: Key Formulas, Design Patterns
- **Business**: Frameworks (SWOT, 4Ps), Case Examples
- **General**: Acronyms, Visual Analogies

**Visual Element Strategy** (Subject-based):

| Subject Type | Topic Images | Chapter Images | Tables | Flowcharts |
|--------------|--------------|----------------|--------|------------|
| Highly Visual (Cardiology, Anatomy) | 5-8 | 1-2 | 2-3 | 2-3 |
| Moderately Visual (Physiology) | 3-5 | 1 | 2-3 | 2-3 |
| Less Visual (Biochemistry) | 2-3 | 0-1 | 2-3 | 1-2 |

---

## API Endpoints

### Comprehensive Analysis Endpoint

```http
POST /api/analyze-course
Content-Type: application/json

{
  "course": "AWS Solutions Architect",
  "type": "full"  // Options: "structure", "exam", "lesson", "full"
}
```

**Response**:
```json
{
  "course": "AWS Solutions Architect",
  "structure": { /* Module 1 output */ },
  "exam_format": { /* Module 2 output */ },
  "lesson_flow_template": { /* Module 3 output */ }
}
```

### Legacy Endpoints (Being Migrated)

```http
POST /api/generate-subjects  // Will be updated to use Module 1
POST /api/generate-questions  // Will be updated to use Modules 1 + 2
POST /api/generate-lessons    // Will be updated to use Modules 1 + 3
```

---

## Integration Flow

### For QBank Generation:

```python
# Step 1: Get course structure (Module 1)
structure = generate_course_structure(course_name)

# Step 2: Analyze exam format (Module 2)
exam_format = analyze_exam_format(course_name, structure)

# Step 3: Generate questions using the analysis
questions = generate_questions(
    subject=subject,
    topic=topic,
    num_questions=num_questions,
    format_spec=exam_format,
    structure=structure
)
```

### For Lesson Generation:

```python
# Step 1: Get course structure (Module 1)
structure = generate_course_structure(course_name)

# Step 2: Design lesson flow (Module 3)
flow = design_lesson_flow(course_name, subject, topic, chapters, structure)

# Step 3: Generate lessons following the flow
topic_lesson = generate_topic_lesson(
    topic=topic,
    flow_plan=flow['topic_lesson_plan'],
    structure=structure
)

chapter_lessons = [
    generate_chapter_lesson(
        chapter=ch,
        flow_plan=flow['chapter_lesson_plan']
    )
    for ch in chapters
]
```

---

## Benefits of Modular Architecture

### 1. **Reusability**
- Single course structure used by both QBank and Lessons
- Exam format analysis reusable across different question types
- Lesson flow design applicable to any subject

### 2. **Domain Agnostic**
- Works for medical, engineering, business, certification exams
- Automatically adapts to domain characteristics
- Intelligent content strategy per domain

### 3. **Maintainability**
- Clean separation of concerns
- Each module has single responsibility
- Easy to update and test independently

### 4. **Scalability**
- Add new exam types without changing core logic
- Extend with new modules (e.g., assessment module, progress tracking)
- Support for multiple languages and regions

### 5. **Intelligence**
- AI-powered analysis at each stage
- Context-aware decision making
- Adaptive to user needs and course requirements

---

## Future Enhancements

### Planned Modules:

**Module 4: Progress Tracker**
- Track user learning progress
- Identify weak areas
- Recommend focus topics

**Module 5: Adaptive Difficulty**
- Adjust question difficulty based on performance
- Personalized learning paths
- Spaced repetition scheduling

**Module 6: Multi-Modal Content**
- Video integration
- Interactive simulations
- AR/VR for complex concepts

---

## Usage Guidelines

### For Developers:

1. **Always use Module 1 first**: Course structure is the foundation
2. **Cache structure results**: Avoid regenerating for same course
3. **Pass context forward**: Each module builds on previous outputs
4. **Handle errors gracefully**: AI modules may need retries

### For Content Creators:

1. **Provide reference docs**: Improves structure accuracy
2. **Review generated structure**: Validate before content generation
3. **Customize as needed**: Modules provide templates, not rigid rules
4. **Iterate and refine**: Use chat interface to improve structure

---

## Technical Implementation

### Dependencies:
- **Claude API (Anthropic)**: Core AI processing
- **Python 3.9+**: Backend runtime
- **Flask**: Web framework
- **Google Gemini**: Image generation (optional)

### Performance:
- Module 1: ~10-15 seconds (cached after first run)
- Module 2: ~5-8 seconds
- Module 3: ~5-8 seconds
- Total analysis: ~20-30 seconds for full course

### Error Handling:
- Automatic retry on API failures
- Fallback to default structures
- Comprehensive logging
- User-friendly error messages

---

## Conclusion

This modular architecture transforms the QBank Generator from a domain-specific tool into a **universal educational content platform**. It combines AI intelligence with educational best practices to create high-quality, personalized learning materials for any subject or exam.

**Key Takeaway**: Three modules, infinite possibilities! 🚀

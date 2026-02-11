// DOM Elements - Question Bank
const qbankCourseInput = document.getElementById('qbank-course');
const qbankGenerateSubjectsBtn = document.getElementById('qbank-generate-subjects-btn');
const qbankUploadStructureBtn = document.getElementById('qbank-upload-structure-btn');
const qbankJsonFile = document.getElementById('qbank-json-file');
const qbankStructureStatus = document.getElementById('qbank-structure-status');
const qbankSubjectsContainer = document.getElementById('qbank-subjects-container');
const subjectSelect = document.getElementById('subject');
const topicsSelect = document.getElementById('topics');
const includeImagesCheckbox = document.getElementById('include-images');
const numQuestionsInput = document.getElementById('num-questions');
const numDisplay = document.getElementById('num-display');
const bloomInfo = document.getElementById('bloom-distribution');
const totalQuestionsInfo = document.getElementById('total-questions-info');
const perTopicLabel = document.getElementById('per-topic-label');
const generateBtn = document.getElementById('generate-btn');
const resultsSection = document.getElementById('results');
const questionsContainer = document.getElementById('questions-container');
const statsContainer = document.getElementById('stats');
const downloadBtn = document.getElementById('download-btn');
const copyBtn = document.getElementById('copy-btn');
const loading = document.getElementById('loading');
const toast = document.getElementById('toast');

let generatedQuestions = [];
let qbankCourseStructure = null;

// Update Bloom's level distribution display
function updateBloomDistribution() {
    const course = qbankCourseInput.value;
    const numQuestions = parseInt(numQuestionsInput.value);
    const selectedTopics = Array.from(topicsSelect.selectedOptions).map(opt => opt.value);
    const numTopics = selectedTopics.length || 1;

    if (!course || !qbankCourseStructure) {
        bloomInfo.innerHTML = '<p>Load course structure to see distribution</p>';
        totalQuestionsInfo.innerHTML = '';
        perTopicLabel.style.display = 'none';
        return;
    }

    perTopicLabel.style.display = 'inline';

    // Equal Bloom's distribution (1-5 levels for all courses)
    let levels = [1, 2, 3, 4, 5];
    let perLevel = Math.floor(numQuestions / 5);
    let remainder = numQuestions % 5;

    const levelNames = {
        1: 'Remember',
        2: 'Understand',
        3: 'Apply',
        4: 'Analyze',
        5: 'Evaluate'
    };

    let html = '';
    levels.forEach((level, idx) => {
        const count = perLevel + (idx < remainder ? 1 : 0);
        html += `<div><span>Level ${level} (${levelNames[level]})</span><span>${count} questions</span></div>`;
    });

    bloomInfo.innerHTML = html;

    // Show total questions info
    const totalQuestions = numQuestions * numTopics;
    if (numTopics > 1) {
        totalQuestionsInfo.innerHTML = `<div class="total-info"><strong>Total: ${totalQuestions} questions</strong> (${numQuestions} × ${numTopics} topics)</div>`;
    } else if (numTopics === 1) {
        totalQuestionsInfo.innerHTML = `<div class="total-info"><strong>Total: ${totalQuestions} questions</strong></div>`;
    } else {
        totalQuestionsInfo.innerHTML = '';
    }
}

// Show toast message
function showToast(message, type = 'info') {
    toast.textContent = message;
    toast.className = 'toast ' + type;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
}

// Question Bank - Generate Subjects button
qbankGenerateSubjectsBtn.addEventListener('click', async () => {
    const course = qbankCourseInput.value.trim();
    if (!course) {
        showToast('Please enter a course name', 'error');
        return;
    }

    qbankGenerateSubjectsBtn.disabled = true;
    qbankGenerateSubjectsBtn.textContent = '⏳ Generating...';

    try {
        const response = await fetch('/api/generate-subjects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ course })
        });

        if (!response.ok) throw new Error('Failed to generate subjects');

        qbankCourseStructure = await response.json();
        populateQBankSubjects();
        qbankStructureStatus.textContent = `✓ Loaded structure for ${course}`;
        qbankStructureStatus.style.color = 'var(--success)';
        showToast('Course structure generated successfully', 'success');
    } catch (error) {
        showToast(error.message || 'Error generating subjects', 'error');
        qbankStructureStatus.textContent = '✗ Failed to generate structure';
        qbankStructureStatus.style.color = 'var(--error)';
    } finally {
        qbankGenerateSubjectsBtn.disabled = false;
        qbankGenerateSubjectsBtn.textContent = '🤖 Generate Subjects';
    }
});

// Question Bank - Upload JSON button
qbankUploadStructureBtn.addEventListener('click', () => {
    qbankJsonFile.click();
});

qbankJsonFile.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
        try {
            qbankCourseStructure = JSON.parse(event.target.result);
            populateQBankSubjects();
            qbankStructureStatus.textContent = `✓ Loaded structure from ${file.name}`;
            qbankStructureStatus.style.color = 'var(--success)';
            showToast('Course structure uploaded successfully', 'success');
        } catch (error) {
            showToast('Invalid JSON file', 'error');
            qbankStructureStatus.textContent = '✗ Failed to parse JSON';
            qbankStructureStatus.style.color = 'var(--error)';
        }
    };
    reader.readAsText(file);
});

// Populate subjects dropdown from loaded structure
function populateQBankSubjects() {
    if (!qbankCourseStructure || !qbankCourseStructure.subjects) return;

    qbankSubjectsContainer.style.display = 'block';
    subjectSelect.innerHTML = '<option value="">Select a subject...</option>';
    topicsSelect.innerHTML = '';

    qbankCourseStructure.subjects.forEach((subject, idx) => {
        const option = document.createElement('option');
        option.value = idx;
        option.textContent = subject.name;
        subjectSelect.appendChild(option);
    });
}

// Subject change handler - populate topics from structure
subjectSelect.addEventListener('change', () => {
    const subjectIdx = subjectSelect.value;
    topicsSelect.innerHTML = '';
    generateBtn.disabled = true;

    if (!subjectIdx || !qbankCourseStructure) return;

    const subject = qbankCourseStructure.subjects[subjectIdx];
    if (!subject || !subject.topics) return;

    subject.topics.forEach((topic, idx) => {
        const option = document.createElement('option');
        option.value = topic.name;
        option.textContent = topic.name;
        topicsSelect.appendChild(option);
    });

    updateBloomDistribution();
});

// Topics change handler (multi-select)
topicsSelect.addEventListener('change', () => {
    const selectedTopics = Array.from(topicsSelect.selectedOptions).map(opt => opt.value);
    generateBtn.disabled = selectedTopics.length === 0;
    updateBloomDistribution();
});

// Number of questions slider
numQuestionsInput.addEventListener('input', () => {
    numDisplay.textContent = numQuestionsInput.value;
    updateBloomDistribution();
});

// Generate button handler
generateBtn.addEventListener('click', async () => {
    const course = qbankCourseInput.value.trim();
    const subjectIdx = subjectSelect.value;
    const topics = Array.from(topicsSelect.selectedOptions).map(opt => opt.value);
    const numQuestions = parseInt(numQuestionsInput.value);
    const includeImages = includeImagesCheckbox.checked;

    if (!qbankCourseStructure || !subjectIdx) {
        showToast('Please load course structure and select a subject', 'error');
        return;
    }

    const subject = qbankCourseStructure.subjects[subjectIdx].name;

    loading.style.display = 'flex';
    generateBtn.disabled = true;

    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                course,
                subject,
                topics,
                num_questions: numQuestions,
                include_images: includeImages
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        generatedQuestions = data.questions;
        displayResults(data.questions, course, data.image_stats);

        let message = `Generated ${data.count} questions across ${topics.length} topic(s)!`;
        if (data.image_stats) {
            message += ` | Images: ${data.image_stats.images_found}/${data.image_stats.total_image_questions} (${data.image_stats.success_rate})`;
        }
        showToast(message, 'success');
        
    } catch (error) {
        showToast(error.message || 'Error generating questions', 'error');
    } finally {
        loading.style.display = 'none';
        generateBtn.disabled = false;
    }
});

// Display results
function displayResults(questions, course, imageStats = null) {
    resultsSection.style.display = 'block';

    // Scroll to results section
    setTimeout(() => {
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);

    // Calculate stats
    const bloomCounts = {};
    const difficultyCounts = { 1: 0, 2: 0, 3: 0 };

    questions.forEach(q => {
        bloomCounts[q.blooms_level] = (bloomCounts[q.blooms_level] || 0) + 1;
        difficultyCounts[q.difficulty] = (difficultyCounts[q.difficulty] || 0) + 1;
    });

    const difficultyLabels = { 1: 'Medium', 2: 'Hard', 3: 'Very Hard' };

    statsContainer.innerHTML = `
        <div class="stat-item">
            <div class="label">Total Questions</div>
            <div class="value">${questions.length}</div>
        </div>
        <div class="stat-item">
            <div class="label">Course</div>
            <div class="value">${course}</div>
        </div>
        ${imageStats ? `
            <div class="stat-item">
                <div class="label">Images Found</div>
                <div class="value">${imageStats.images_found}/${imageStats.total_image_questions}</div>
            </div>
            <div class="stat-item">
                <div class="label">Image Success</div>
                <div class="value">${imageStats.success_rate}</div>
            </div>
        ` : ''}
        ${Object.entries(bloomCounts).map(([level, count]) => `
            <div class="stat-item">
                <div class="label">Bloom's L${level}</div>
                <div class="value">${count}</div>
            </div>
        `).join('')}
        ${Object.entries(difficultyCounts).filter(([_, count]) => count > 0).map(([diff, count]) => `
            <div class="stat-item">
                <div class="label">${difficultyLabels[diff]}</div>
                <div class="value">${count}</div>
            </div>
        `).join('')}
    `;
    
    questionsContainer.innerHTML = questions.map((q, idx) => `
        <div class="question-card">
            <div class="question-header">
                <span class="question-number">Q${idx + 1}</span>
                <div class="question-tags">
                    <span class="tag tag-bloom">Bloom's L${q.blooms_level}</span>
                    <span class="tag tag-difficulty">${difficultyLabels[q.difficulty]}</span>
                    ${(q.image_url || q.image_description) ? '<span class="tag tag-image">Image</span>' : ''}
                    ${q.tags.map(tag => `<span class="tag tag-exam">${tag}</span>`).join('')}
                </div>
            </div>
            ${q.image_url ? `
                <div class="question-image">
                    <img src="${q.image_url}" alt="${q.image_description || 'Medical image'}" loading="lazy" onerror="this.onerror=null; this.style.display='none'; this.nextElementSibling.style.display='block';">
                    <div class="image-fallback" style="display:none;">
                        <p class="image-placeholder">${q.image_type ? `[${q.image_type}]` : '[Image]'} ${q.image_description || ''}</p>
                    </div>
                    ${q.image_source ? `<small class="image-source">Source: ${q.image_source}</small>` : ''}
                </div>
            ` : (q.image_description ? `
                <div class="question-image">
                    <div class="image-placeholder-box">
                        <div class="placeholder-icon">🖼️</div>
                        <p class="image-placeholder"><strong>${q.image_type || 'Image'}:</strong> ${q.image_description}</p>
                        ${q.image_search_terms ? `<small>Search: ${q.image_search_terms.slice(0,2).join(', ')}</small>` : ''}
                    </div>
                </div>
            ` : '')}
            <p class="question-text">${q.question}</p>
            <ul class="options-list">
                ${q.options.map(opt => `
                    <li class="${opt === q.correct_option ? 'correct' : ''}">${opt}</li>
                `).join('')}
            </ul>
            <div class="explanation">
                <strong>Explanation:</strong> ${q.explanation}
            </div>
        </div>
    `).join('');
    
    resultsSection.scrollIntoView({ behavior: 'smooth' });
}

// Download button
downloadBtn.addEventListener('click', () => {
    if (!generatedQuestions.length) return;

    const course = qbankCourseInput.value.trim() || 'questions';
    const blob = new Blob([JSON.stringify(generatedQuestions, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `qbank_${course.replace(/\s+/g, '_')}_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);

    showToast('Downloaded successfully!', 'success');
});

// Convert image URL to base64
async function urlToBase64(url) {
    try {
        const response = await fetch(url);
        const blob = await response.blob();
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onloadend = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });
    } catch (error) {
        console.error('Error converting image to base64:', error);
        return null;
    }
}

// Download Markdown button
copyBtn.addEventListener('click', async () => {
    if (!generatedQuestions.length) return;

    try {
        showToast('Generating markdown with embedded images...', 'info');

        const course = qbankCourseInput.value.trim() || 'Unknown Course';
        const subjectIdx = subjectSelect.value;
        const subject = qbankCourseStructure && subjectIdx ? qbankCourseStructure.subjects[subjectIdx].name : 'Unknown Subject';
        const topics = Array.from(topicsSelect.selectedOptions).map(opt => opt.value);
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);

        let markdown = `# QBank Generation Review\n\n`;
        markdown += `**Course:** ${course}\n`;
        markdown += `**Subject:** ${subject}\n`;
        markdown += `**Topics:** ${topics.join(', ')}\n`;
        markdown += `**Generated:** ${new Date().toLocaleString()}\n`;
        markdown += `**Total Questions:** ${generatedQuestions.length}\n\n`;
        markdown += `---\n\n`;

        for (let i = 0; i < generatedQuestions.length; i++) {
            const q = generatedQuestions[i];
            const diffLabels = { 1: 'Medium', 2: 'Hard', 3: 'Very Hard' };

            markdown += `## Q${i + 1}\n\n`;
            markdown += `**Bloom's Level:** ${q.blooms_level}\n`;
            markdown += `**Difficulty:** ${diffLabels[q.difficulty] || 'Medium'}\n`;
            markdown += `**Tags:** ${q.tags.join(', ')}\n\n`;

            // Embed image if present
            if (q.image_url) {
                const base64 = await urlToBase64(q.image_url);
                if (base64) {
                    markdown += `![${q.image_type || 'Medical Image'}](${base64})\n\n`;
                }
                markdown += `**Source:** ${q.image_source || 'N/A'}\n\n`;
            }

            markdown += `**Question:**\n${q.question}\n\n`;

            markdown += `**Options:**\n`;
            q.options.forEach((opt, idx) => {
                const marker = opt === q.correct_option ? '✓' : ' ';
                markdown += `${marker} ${idx + 1}. ${opt}\n`;
            });
            markdown += `\n`;

            markdown += `**Explanation:**\n${q.explanation}\n\n`;
            markdown += `---\n\n`;
        }

        // Download markdown file
        const blob = new Blob([markdown], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `qbank_${course.replace(' ', '_')}_${timestamp}.md`;
        a.click();
        URL.revokeObjectURL(url);

        showToast('Markdown downloaded with embedded images!', 'success');
    } catch (error) {
        console.error('Error generating markdown:', error);
        showToast('Failed to generate markdown', 'error');
    }
});

// Initialize
updateBloomDistribution();

// ============================================
// TAB SWITCHING FUNCTIONALITY
// ============================================

const tabButtons = document.querySelectorAll('.tab-button');
const tabContents = document.querySelectorAll('.tab-content');

tabButtons.forEach(button => {
    button.addEventListener('click', () => {
        const tabName = button.getAttribute('data-tab');

        // Remove active class from all tabs and contents
        tabButtons.forEach(btn => btn.classList.remove('active'));
        tabContents.forEach(content => content.classList.remove('active'));

        // Add active class to clicked tab and corresponding content
        button.classList.add('active');
        document.getElementById(`${tabName}-tab`).classList.add('active');

        // Hide results sections when switching tabs
        resultsSection.style.display = 'none';
        document.getElementById('image-result').style.display = 'none';
        document.getElementById('lessons-result').style.display = 'none';
    });
});

// ============================================
// ADD IMAGE TO QUESTION FUNCTIONALITY
// ============================================

const addImageBtn = document.getElementById('add-image-btn');
const jsonInput = document.getElementById('json-input');
const jsonFileInput = document.getElementById('json-file-input');
const uploadJsonBtn = document.getElementById('upload-json-btn');
const fileNameDisplay = document.getElementById('file-name');
const batchCourse = document.getElementById('batch-course');
const imageResultSection = document.getElementById('image-result');
const imageResultContainer = document.getElementById('image-result-container');
const imageStatsContainer = document.getElementById('image-stats');
const downloadImageResultBtn = document.getElementById('download-image-result-btn');
const downloadImageMdBtn = document.getElementById('download-image-md-btn');

let imageResultData = null;

// File upload button handler
uploadJsonBtn.addEventListener('click', () => {
    jsonFileInput.click();
});

// File selection handler
jsonFileInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    fileNameDisplay.textContent = file.name;

    try {
        const text = await file.text();
        jsonInput.value = text;
        showToast('File loaded successfully!', 'success');
    } catch (error) {
        showToast('Error reading file', 'error');
    }
});

// Add image button handler
addImageBtn.addEventListener('click', async () => {
    const jsonText = jsonInput.value.trim();
    const course = batchCourse.value;

    // Validation
    if (!jsonText) {
        showToast('Please paste JSON or upload a file', 'error');
        return;
    }

    let questions;
    try {
        const parsed = JSON.parse(jsonText);
        // Handle both single object and array
        questions = Array.isArray(parsed) ? parsed : [parsed];
    } catch (error) {
        showToast('Invalid JSON format. Please check your input.', 'error');
        return;
    }

    if (questions.length === 0) {
        showToast('No questions found in JSON', 'error');
        return;
    }

    loading.style.display = 'flex';
    const loadingText = loading.querySelector('p');
    loadingText.textContent = `Processing ${questions.length} question(s)...`;
    addImageBtn.disabled = true;

    try {
        const response = await fetch('/api/add-image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                questions,
                course
            })
        });

        const data = await response.json();

        if (!data.success) {
            showToast(data.error || 'Error processing questions', 'error');
            return;
        }

        imageResultData = data.questions;
        displayBatchImageResult(data.questions, data.stats);

        const stats = data.stats;
        let message = `Processed ${stats.total} questions: ${stats.images_added} images added`;
        if (stats.explanations_generated > 0) {
            message += `, ${stats.explanations_generated} explanations generated`;
        }
        if (stats.no_image_needed > 0) {
            message += `, ${stats.no_image_needed} didn't need images`;
        }
        showToast(message, 'success');

    } catch (error) {
        showToast(error.message || 'Error adding images', 'error');
    } finally {
        loading.style.display = 'none';
        loadingText.textContent = 'Generating questions with Claude...';
        addImageBtn.disabled = false;
    }
});

function displayBatchImageResult(questions, stats) {
    imageResultSection.style.display = 'block';

    const diffLabels = { 1: 'Medium', 2: 'Hard', 3: 'Very Hard' };

    // Display stats
    imageStatsContainer.innerHTML = `
        <div class="stat-item">
            <div class="label">Total Questions</div>
            <div class="value">${stats.total}</div>
        </div>
        <div class="stat-item">
            <div class="label">Images Added</div>
            <div class="value">${stats.images_added}</div>
        </div>
        ${stats.explanations_generated > 0 ? `
        <div class="stat-item">
            <div class="label">Explanations Generated</div>
            <div class="value">${stats.explanations_generated}</div>
        </div>
        ` : ''}
        ${stats.no_image_needed > 0 ? `
        <div class="stat-item">
            <div class="label">No Image Needed</div>
            <div class="value">${stats.no_image_needed}</div>
        </div>
        ` : ''}
        ${stats.failed > 0 ? `
        <div class="stat-item">
            <div class="label">Failed</div>
            <div class="value">${stats.failed}</div>
        </div>
        ` : ''}
    `;

    // Display questions - same format as main generation tab
    imageResultContainer.innerHTML = questions.map((q, idx) => {
        const status = q.image_status || 'unknown';

        return `
        <div class="question-card">
            <div class="question-header">
                <span class="question-number">Q${idx + 1}</span>
                <div class="question-tags">
                    ${q.blooms_level ? `<span class="tag tag-bloom">Bloom's L${q.blooms_level}</span>` : ''}
                    ${q.difficulty ? `<span class="tag tag-difficulty">${diffLabels[q.difficulty]}</span>` : ''}
                    ${q.image_url ? '<span class="tag tag-image">Image</span>' : ''}
                    ${q.tags ? q.tags.map(tag => `<span class="tag tag-exam">${tag}</span>`).join('') : ''}
                </div>
            </div>

            ${q.image_url ? `
                <div class="question-image">
                    <img src="${q.image_url}" alt="${q.image_description || 'Medical image'}" loading="lazy" onerror="this.onerror=null; this.style.display='none'; this.nextElementSibling.style.display='block';">
                    <div class="image-fallback" style="display:none;">
                        <p class="image-placeholder">${q.image_type ? `[${q.image_type}]` : '[Image]'} ${q.image_description || ''}</p>
                    </div>
                    ${q.image_source ? `<small class="image-source">Source: ${q.image_source}</small>` : ''}
                </div>
            ` : (q.image_description && status === 'failed' ? `
                <div class="question-image">
                    <div class="image-placeholder-box">
                        <div class="placeholder-icon">⚠️</div>
                        <p class="image-placeholder"><strong>Image not found:</strong> ${q.image_type || 'Image'}</p>
                        <small style="color: var(--text-muted);">${q.image_error || 'Could not find suitable image'}</small>
                    </div>
                </div>
            ` : '')}

            <p class="question-text">${q.question}</p>
            <ul class="options-list">
                ${q.options.map(opt => `
                    <li class="${opt === q.correct_option ? 'correct' : ''}">${opt}</li>
                `).join('')}
            </ul>
            ${q.explanation ? `
                <div class="explanation">
                    <strong>Explanation:</strong> ${q.explanation}
                </div>
            ` : ''}
        </div>
    `}).join('');

    imageResultSection.scrollIntoView({ behavior: 'smooth' });
}

// Download image results as JSON
downloadImageResultBtn.addEventListener('click', () => {
    if (!imageResultData) return;

    // Clean up internal metadata fields before download
    const cleanedData = imageResultData.map(q => {
        const cleaned = { ...q };
        // Remove internal fields
        delete cleaned.image_status;
        delete cleaned.image_error;
        delete cleaned.image_reasoning;
        delete cleaned.key_finding;
        delete cleaned.image_search_terms;
        delete cleaned.image_title;
        return cleaned;
    });

    const blob = new Blob([JSON.stringify(cleanedData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `questions_with_images_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);

    showToast('Downloaded successfully!', 'success');
});

// Download as Markdown
downloadImageMdBtn.addEventListener('click', async () => {
    if (!imageResultData) return;

    try {
        showToast('Generating markdown with embedded images...', 'info');

        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
        const diffLabels = { 1: 'Medium', 2: 'Hard', 3: 'Very Hard' };

        let markdown = `# Questions with Added Images\n\n`;
        markdown += `**Generated:** ${new Date().toLocaleString()}\n`;
        markdown += `**Total Questions:** ${imageResultData.length}\n\n`;
        markdown += `---\n\n`;

        for (let i = 0; i < imageResultData.length; i++) {
            const q = imageResultData[i];

            markdown += `## Q${i + 1}\n\n`;

            if (q.blooms_level) markdown += `**Bloom's Level:** ${q.blooms_level}\n`;
            if (q.difficulty) markdown += `**Difficulty:** ${diffLabels[q.difficulty] || 'Medium'}\n`;
            if (q.tags) markdown += `**Tags:** ${q.tags.join(', ')}\n`;
            markdown += `**Image Status:** ${q.image_status || 'unknown'}\n\n`;

            // Embed image if present
            if (q.image_url) {
                const base64 = await urlToBase64(q.image_url);
                if (base64) {
                    markdown += `![${q.image_type || 'Medical Image'}](${base64})\n\n`;
                }
                markdown += `**Image Source:** ${q.image_source || 'N/A'}\n`;
                if (q.key_finding) markdown += `**Key Finding:** ${q.key_finding}\n`;
                markdown += `\n`;
            }

            markdown += `**Question:**\n${q.question}\n\n`;

            markdown += `**Options:**\n`;
            q.options.forEach((opt, idx) => {
                const marker = opt === q.correct_option ? '✓' : ' ';
                markdown += `${marker} ${idx + 1}. ${opt}\n`;
            });
            markdown += `\n`;

            if (q.explanation) {
                markdown += `**Explanation:**\n${q.explanation}\n\n`;
            }

            markdown += `---\n\n`;
        }

        // Download markdown file
        const blob = new Blob([markdown], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `questions_with_images_${timestamp}.md`;
        a.click();
        URL.revokeObjectURL(url);

        showToast('Markdown downloaded!', 'success');
    } catch (error) {
        console.error('Error generating markdown:', error);
        showToast('Failed to generate markdown', 'error');
    }
});

// ============================================
// LESSON GENERATION FUNCTIONALITY
// ============================================

const generateLessonsBtn = document.getElementById('generate-lessons-btn');
const lessonCourse = document.getElementById('lesson-course');
const lessonJsonFile = document.getElementById('lesson-json-file');
const generateSubjectsBtn = document.getElementById('generate-subjects-btn');
const uploadStructureBtn = document.getElementById('upload-structure-btn');
const structureStatus = document.getElementById('structure-status');
const lessonSubjectsContainer = document.getElementById('subjects-container');
const lessonSubjectSelect = document.getElementById('subject-select');
const lessonTopicsSelect = document.getElementById('topics-select');
const lessonChaptersSelect = document.getElementById('chapters-select');
const generateAllCheckbox = document.getElementById('generate-all-checkbox');
const lessonsResultSection = document.getElementById('lessons-result');
const lessonsContainer = document.getElementById('lessons-container');
const lessonsStatsContainer = document.getElementById('lessons-stats');
const downloadLessonsJsonBtn = document.getElementById('download-lessons-json-btn');
const downloadLessonsMdBtn = document.getElementById('download-lessons-md-btn');

let lessonsData = null;
let courseStructure = null;  // Stores the full course structure

// Generate Subjects button handler
generateSubjectsBtn.addEventListener('click', async () => {
    const course = lessonCourse.value.trim();
    if (!course) {
        showToast('Please enter a course/exam name', 'error');
        lessonCourse.focus();
        return;
    }

    structureStatus.textContent = '⏳ Generating course structure...';
    generateSubjectsBtn.disabled = true;

    try {
        // TODO: This will call Claude to generate structure
        // For now, show placeholder
        await new Promise(resolve => setTimeout(resolve, 1000));

        // Placeholder structure
        courseStructure = {
            Course: course,
            subjects: [
                {
                    name: "Core Medicine",
                    topics: [
                        { name: "Cardiology", high_yield: true, chapters: [{ name: "Heart Failure" }, { name: "Arrhythmias" }] },
                        { name: "Respiratory", chapters: [{ name: "Asthma" }, { name: "COPD" }] }
                    ]
                },
                {
                    name: "Surgery",
                    topics: [
                        { name: "General Surgery", chapters: [{ name: "Appendicitis" }] }
                    ]
                }
            ]
        };

        populateSubjects(courseStructure);
        structureStatus.textContent = `✓ Generated ${courseStructure.subjects.length} subjects`;
        showToast('Course structure generated!', 'success');
    } catch (error) {
        structureStatus.textContent = '✗ Failed to generate structure';
        showToast('Failed to generate structure', 'error');
    } finally {
        generateSubjectsBtn.disabled = false;
    }
});

// Upload JSON button handler
uploadStructureBtn.addEventListener('click', () => {
    lessonJsonFile.click();
});

// File selection handler for lessons
lessonJsonFile.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    try {
        const text = await file.text();
        const json = JSON.parse(text);

        // Store the full JSON
        courseStructure = json;

        // Auto-fill course field
        if (json.Course) {
            lessonCourse.value = json.Course;
        }

        // Populate subjects dropdown
        populateSubjects(json);

        // Display info
        if (json.subjects) {
            const totalTopics = json.subjects.reduce((sum, subj) =>
                sum + (subj.topics?.length || 0), 0);
            structureStatus.textContent = `✓ Loaded: ${json.subjects.length} subjects, ${totalTopics} topics`;
            showToast(`JSON loaded: ${file.name}`, 'success');
        } else {
            showToast('JSON file loaded successfully', 'success');
        }
    } catch (error) {
        console.error('Error parsing JSON:', error);
        showToast('Invalid JSON file', 'error');
        structureStatus.textContent = '✗ Invalid JSON file';
        courseStructure = null;
    }
});

function populateSubjects(structure) {
    if (!structure || !structure.subjects) return;

    lessonSubjectsContainer.style.display = 'block';
    lessonSubjectSelect.innerHTML = '<option value="">Select a subject...</option>';
    lessonTopicsSelect.innerHTML = '';
    lessonChaptersSelect.innerHTML = '';

    // Populate subjects
    structure.subjects.forEach((subject, idx) => {
        const option = document.createElement('option');
        option.value = idx;
        option.textContent = subject.name;
        lessonSubjectSelect.appendChild(option);
    });

    // Enable generate button
    generateLessonsBtn.disabled = false;
    console.log('✓ Generate Lessons button enabled');
    console.log('Course structure loaded:', structure);
}

function updateTopics() {
    if (!courseStructure || !courseStructure.subjects) return;

    const selectedSubjectIdx = lessonSubjectSelect.value;
    lessonTopicsSelect.innerHTML = '';
    lessonChaptersSelect.innerHTML = '';

    if (selectedSubjectIdx === '') return;

    const subject = courseStructure.subjects[selectedSubjectIdx];

    subject.topics.forEach((topic, idx) => {
        const option = document.createElement('option');
        option.value = idx;
        const highYieldMarker = topic.high_yield ? ' ⭐' : '';
        option.textContent = `${topic.name}${highYieldMarker}`;
        lessonTopicsSelect.appendChild(option);
    });
}

function updateChapters() {
    if (!courseStructure || !courseStructure.subjects) return;

    const selectedSubjectIdx = lessonSubjectSelect.value;
    if (selectedSubjectIdx === '') return;

    const subject = courseStructure.subjects[selectedSubjectIdx];
    const selectedTopicIndices = Array.from(lessonTopicsSelect.selectedOptions).map(opt => parseInt(opt.value));

    lessonChaptersSelect.innerHTML = '';

    // If no topics selected, don't show chapters
    if (selectedTopicIndices.length === 0) return;

    // Collect chapters from selected topics
    selectedTopicIndices.forEach(topicIdx => {
        const topic = subject.topics[topicIdx];
        if (topic.chapters && topic.chapters.length > 0) {
            topic.chapters.forEach((chapter, chIdx) => {
                const option = document.createElement('option');
                option.value = `${topicIdx}-${chIdx}`;
                const chapterName = typeof chapter === 'string' ? chapter : chapter.name;
                option.textContent = `${topic.name} > ${chapterName}`;
                lessonChaptersSelect.appendChild(option);
            });
        }
    });
}

// Update topics when subject changes
lessonSubjectSelect.addEventListener('change', updateTopics);

// Update chapters when topics change
lessonTopicsSelect.addEventListener('change', updateChapters);

// Handle "Generate All" checkbox
generateAllCheckbox.addEventListener('change', (e) => {
    const isChecked = e.target.checked;
    lessonSubjectSelect.disabled = isChecked;
    lessonTopicsSelect.disabled = isChecked;
    lessonChaptersSelect.disabled = isChecked;

    if (isChecked) {
        structureStatus.textContent = '✓ Will generate lessons for entire course';
    } else {
        structureStatus.textContent = structureStatus.textContent.replace('Will generate lessons for entire course', '');
    }
});

// Generate lessons button handler
generateLessonsBtn.addEventListener('click', async () => {
    console.log('Generate Lessons button clicked');

    const course = lessonCourse.value.trim();

    // Validation
    if (!course) {
        showToast('Please enter a course name', 'error');
        lessonCourse.focus();
        return;
    }

    if (!courseStructure) {
        showToast('Please click "Generate Subjects" or "Upload JSON" first!', 'error');
        return;
    }

    const generateAll = generateAllCheckbox.checked;

    // Prepare request data
    const requestData = {
        course: course,
        uploaded_json: courseStructure,
        generate_all: generateAll
    };

    if (!generateAll) {
        const selectedSubjectIdx = lessonSubjectSelect.value;
        if (selectedSubjectIdx === '') {
            showToast('Please select a subject', 'error');
            return;
        }

        requestData.selected_subject_idx = parseInt(selectedSubjectIdx);

        // Get selected topics (empty means all topics in subject)
        const selectedTopicIndices = Array.from(lessonTopicsSelect.selectedOptions).map(opt => parseInt(opt.value));
        if (selectedTopicIndices.length > 0) {
            requestData.selected_topic_indices = selectedTopicIndices;
        }

        // Get selected chapters (optional)
        const selectedChapters = Array.from(lessonChaptersSelect.selectedOptions).map(opt => opt.value);
        if (selectedChapters.length > 0) {
            requestData.selected_chapters = selectedChapters;
        }
    }

    console.log('Request data:', requestData);

    // Show loading with enhanced messages
    loading.style.display = 'flex';
    const loadingText = loading.querySelector('p');
    loadingText.textContent = '🔄 Initializing lesson generation...';
    generateLessonsBtn.disabled = true;

    // Update loading messages periodically
    let messageIndex = 0;
    const messages = [
        '📝 Generating lesson content with Claude...',
        '🔍 Searching for medical images...',
        '🎨 Integrating visuals and flowcharts...',
        '✨ Finalizing lesson format...'
    ];
    const messageInterval = setInterval(() => {
        messageIndex = (messageIndex + 1) % messages.length;
        loadingText.textContent = messages[messageIndex];
    }, 3000);

    try {
        console.log('Sending request to /api/generate-lessons...');
        const response = await fetch('/api/generate-lessons', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        });

        console.log('Response status:', response.status);

        if (!response.ok) {
            const error = await response.json();
            console.error('Server error:', error);
            throw new Error(error.error || 'Failed to generate lessons');
        }

        const data = await response.json();
        console.log('Lessons data received:', data);
        lessonsData = data;

        // Display results
        displayLessons(data);
        lessonsResultSection.style.display = 'block';

        showToast(`✓ Generated ${data.lessons.length} lessons!`, 'success');
    } catch (error) {
        console.error('Error generating lessons:', error);
        showToast(error.message || 'Failed to generate lessons', 'error');
    } finally {
        clearInterval(messageInterval);
        loading.style.display = 'none';
        generateLessonsBtn.disabled = false;
    }
});

function displayLessons(data) {
    // Display stats
    const stats = {
        'Course': data.course,
        'Subject': data.subject,
        'Total Topics': data.lessons.length,
        'Total Chapters': data.lessons.reduce((sum, lesson) => sum + (lesson.chapters?.length || 0), 0)
    };

    lessonsStatsContainer.innerHTML = Object.entries(stats)
        .map(([label, value]) => `
            <div class="stat-item">
                <div class="label">${label}</div>
                <div class="value">${value}</div>
            </div>
        `).join('');

    // Display lessons
    lessonsContainer.innerHTML = data.lessons.map((lesson, idx) => `
        <div class="lesson-card">
            <div class="lesson-header">
                <h3>Topic ${idx + 1}: ${lesson.topic}</h3>
                <div class="lesson-tags">
                    ${lesson.high_yield ? '<span class="tag tag-success">High Yield</span>' : ''}
                    <span class="tag tag-info">${lesson.chapters?.length || 0} Chapters</span>
                </div>
            </div>

            <div class="lesson-content">
                <h4>📖 Topic-Level Lesson (Detailed)</h4>
                <div class="lesson-text">${formatLessonContent(lesson.topic_lesson)}</div>
            </div>

            ${lesson.chapters && lesson.chapters.length > 0 ? `
                <div class="chapters-section">
                    <h4>📝 Chapter-Level Lessons (Rapid Revision)</h4>
                    ${lesson.chapters.map((chapter, chIdx) => `
                        <div class="chapter-card">
                            <div class="chapter-header">
                                <h5>Chapter ${chIdx + 1}: ${chapter.name}</h5>
                                ${chapter.nice_refs && chapter.nice_refs.length > 0 ? `
                                    <span class="chapter-refs">📋 ${chapter.nice_refs.join(', ')}</span>
                                ` : ''}
                            </div>
                            <div class="lesson-text">${formatLessonContent(chapter.lesson)}</div>
                        </div>
                    `).join('')}
                </div>
            ` : ''}
        </div>
    `).join('');
}

function formatLessonContent(content) {
    if (!content) return '<p class="text-muted">No content available</p>';

    let html = content;

    // Extract and process Mermaid code blocks
    const mermaidBlocks = [];
    html = html.replace(/```mermaid\n([\s\S]*?)```/g, (match, code) => {
        const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
        mermaidBlocks.push({ id, code: code.trim() });
        return `<div class="mermaid-container"><pre class="mermaid" id="${id}">${code.trim()}</pre></div>`;
    });

    // Convert markdown headings
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

    // Convert markdown images
    html = html.replace(/!\[([^\]]*)\]\(([^\)]+)\)/g, '<img src="$2" alt="$1" style="max-width: 100%; border-radius: 8px; margin: 1rem 0;">');

    // Convert bold and italic
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // Convert bullet lists
    html = html.replace(/^\* (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');

    // Convert tables (simple markdown tables)
    const tableRegex = /(\|.+\|\n)+/g;
    html = html.replace(tableRegex, (table) => {
        const rows = table.trim().split('\n');
        let tableHtml = '<table class="lesson-table">';
        rows.forEach((row, idx) => {
            if (idx === 1 && row.includes('---')) return; // Skip separator row
            const cells = row.split('|').filter(c => c.trim());
            const tag = idx === 0 ? 'th' : 'td';
            tableHtml += `<tr>${cells.map(c => `<${tag}>${c.trim()}</${tag}>`).join('')}</tr>`;
        });
        tableHtml += '</table>';
        return tableHtml;
    });

    // Convert paragraphs
    html = html.split('\n\n').map(para => {
        if (para.startsWith('<')) return para; // Already HTML
        return `<p>${para.replace(/\n/g, '<br>')}</p>`;
    }).join('');

    // Initialize Mermaid rendering after content is added to DOM
    setTimeout(() => {
        if (window.mermaid) {
            window.mermaid.run({
                querySelector: '.mermaid'
            });
        }
    }, 100);

    return html;
}

// Download lessons as JSON
downloadLessonsJsonBtn.addEventListener('click', () => {
    if (!lessonsData) {
        showToast('No lessons to download', 'error');
        return;
    }

    const timestamp = new Date().toISOString().slice(0, 10);
    const blob = new Blob([JSON.stringify(lessonsData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `lessons_${lessonsData.course}_${timestamp}.json`;
    a.click();
    URL.revokeObjectURL(url);

    showToast('Lessons downloaded!', 'success');
});

// Download lessons as Markdown
downloadLessonsMdBtn.addEventListener('click', () => {
    if (!lessonsData) {
        showToast('No lessons to download', 'error');
        return;
    }

    try {
        const timestamp = new Date().toISOString().slice(0, 10);
        let markdown = `# ${lessonsData.course} - ${lessonsData.subject}\n\n`;
        markdown += `Generated on: ${new Date().toLocaleDateString()}\n\n`;
        markdown += `---\n\n`;

        lessonsData.lessons.forEach((lesson, idx) => {
            markdown += `## Topic ${idx + 1}: ${lesson.topic}\n\n`;

            markdown += `### 📖 Detailed Lesson\n\n`;
            markdown += `${lesson.topic_lesson}\n\n`;

            if (lesson.chapters && lesson.chapters.length > 0) {
                markdown += `### 📝 Chapter-Level Rapid Revision\n\n`;
                lesson.chapters.forEach((chapter, chIdx) => {
                    markdown += `#### ${chIdx + 1}. ${chapter.name}\n\n`;
                    markdown += `${chapter.lesson}\n\n`;
                });
            }

            markdown += `---\n\n`;
        });

        const blob = new Blob([markdown], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `lessons_${lessonsData.course}_${timestamp}.md`;
        a.click();
        URL.revokeObjectURL(url);

        showToast('Markdown downloaded!', 'success');
    } catch (error) {
        console.error('Error generating markdown:', error);
        showToast('Failed to generate markdown', 'error');
    }
});

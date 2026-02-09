// DOM Elements
const courseSelect = document.getElementById('course');
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

// Update Bloom's level distribution display
function updateBloomDistribution() {
    const course = courseSelect.value;
    const numQuestions = parseInt(numQuestionsInput.value);
    const selectedTopics = Array.from(topicsSelect.selectedOptions).map(opt => opt.value);
    const numTopics = selectedTopics.length || 1;
    
    if (!course) {
        bloomInfo.innerHTML = '<p>Select a course to see distribution</p>';
        totalQuestionsInfo.innerHTML = '';
        perTopicLabel.style.display = 'none';
        return;
    }
    
    perTopicLabel.style.display = 'inline';
    
    let levels, perLevel, remainder;
    
    if (course === 'NEET PG') {
        levels = [1, 2, 3, 4, 5];
        perLevel = Math.floor(numQuestions / 5);
        remainder = numQuestions % 5;
    } else {
        levels = [3, 4, 5];
        perLevel = Math.floor(numQuestions / 3);
        remainder = numQuestions % 3;
    }
    
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

// Course change handler
courseSelect.addEventListener('change', async () => {
    const course = courseSelect.value;
    
    // Reset dependent selects
    subjectSelect.innerHTML = '<option value="">Select Subject</option>';
    topicsSelect.innerHTML = '';
    
    subjectSelect.disabled = !course;
    topicsSelect.disabled = true;
    generateBtn.disabled = true;
    
    updateBloomDistribution();
    
    if (!course) return;
    
    try {
        const response = await fetch(`/api/subjects/${encodeURIComponent(course)}`);
        const subjects = await response.json();
        
        subjects.forEach(subject => {
            const option = document.createElement('option');
            option.value = subject;
            option.textContent = subject;
            subjectSelect.appendChild(option);
        });
    } catch (error) {
        showToast('Error loading subjects', 'error');
    }
});

// Subject change handler
subjectSelect.addEventListener('change', async () => {
    const course = courseSelect.value;
    const subject = subjectSelect.value;
    
    topicsSelect.innerHTML = '';
    topicsSelect.disabled = !subject;
    generateBtn.disabled = true;
    
    updateBloomDistribution();
    
    if (!subject) return;
    
    try {
        const response = await fetch(`/api/topics/${encodeURIComponent(course)}/${encodeURIComponent(subject)}`);
        const topics = await response.json();
        
        topics.forEach(topic => {
            const option = document.createElement('option');
            option.value = topic;
            option.textContent = topic;
            topicsSelect.appendChild(option);
        });
    } catch (error) {
        showToast('Error loading topics', 'error');
    }
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
    const course = courseSelect.value;
    const subject = subjectSelect.value;
    const topics = Array.from(topicsSelect.selectedOptions).map(opt => opt.value);
    const numQuestions = parseInt(numQuestionsInput.value);
    const includeImages = includeImagesCheckbox.checked;
    
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
    
    const blob = new Blob([JSON.stringify(generatedQuestions, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `qbank_${courseSelect.value.replace(' ', '_')}_${Date.now()}.json`;
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

        const course = courseSelect.value;
        const subject = subjectSelect.value;
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

// DOM Elements
const courseSelect = document.getElementById('course');
const subjectSelect = document.getElementById('subject');
const topicsSelect = document.getElementById('topics');
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
                num_questions: numQuestions
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        generatedQuestions = data.questions;
        displayResults(data.questions, course);
        showToast(`Generated ${data.count} questions across ${topics.length} topic(s)!`, 'success');
        
    } catch (error) {
        showToast(error.message || 'Error generating questions', 'error');
    } finally {
        loading.style.display = 'none';
        generateBtn.disabled = false;
    }
});

// Display results
function displayResults(questions, course) {
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
                    ${q.tags.map(tag => `<span class="tag tag-exam">${tag}</span>`).join('')}
                </div>
            </div>
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

// Copy button
copyBtn.addEventListener('click', async () => {
    if (!generatedQuestions.length) return;
    
    try {
        await navigator.clipboard.writeText(JSON.stringify(generatedQuestions, null, 2));
        showToast('Copied to clipboard!', 'success');
    } catch (error) {
        showToast('Failed to copy', 'error');
    }
});

// Initialize
updateBloomDistribution();

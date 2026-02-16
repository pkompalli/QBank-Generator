// ============================================
// QBank Generator - Single Page Workflow
// ============================================

// Global state
let courseStructure = null;
let generatedContent = null;

// ============================================
// TAB SWITCHING
// ============================================

document.querySelectorAll('.tab-button').forEach(button => {
    button.addEventListener('click', () => {
        const targetTab = button.dataset.tab;

        // Update button styles
        document.querySelectorAll('.tab-button').forEach(btn => {
            btn.style.borderBottom = '3px solid transparent';
            btn.style.color = 'var(--text-muted)';
            btn.style.fontWeight = 'normal';
        });
        button.style.borderBottom = '3px solid var(--primary)';
        button.style.color = 'inherit';
        button.style.fontWeight = '600';

        // Update tab content
        document.querySelectorAll('.tab-content').forEach(content => {
            content.style.display = 'none';
        });
        document.getElementById(`${targetTab}-tab`).style.display = 'block';
    });
});

// ============================================
// DOM ELEMENTS
// ============================================

// DOM Elements
const courseInput = document.getElementById('course-input');
const analyzeCourseBtn = document.getElementById('analyze-course-btn');
const structureSection = document.getElementById('structure-section');
const examFormatDetails = document.getElementById('exam-format-details');
const structureTree = document.getElementById('structure-tree');
const approveStructureBtn = document.getElementById('approve-structure-btn');
const generateSection = document.getElementById('generate-section');
const mainSubjectSelect = document.getElementById('main-subject-select');
const mainTopicsSelect = document.getElementById('main-topics-select');
const generateAllCheckbox = document.getElementById('generate-all-checkbox');
const numQuestionsInput = document.getElementById('num-questions');
const numDisplay = document.getElementById('num-display');
const totalQuestionsInfo = document.getElementById('total-questions-info');
const generateLessonBtn = document.getElementById('generate-lesson-btn');
const generateQbankBtn = document.getElementById('generate-qbank-btn');
const resultsSection = document.getElementById('results-section');
const resultsTitle = document.getElementById('results-title');
const resultsActions = document.getElementById('results-actions');
const resultsStats = document.getElementById('results-stats');
const resultsContainer = document.getElementById('results-container');
const loading = document.getElementById('loading');
const loadingMessage = document.getElementById('loading-message');
const toast = document.getElementById('toast');

// Chat elements
const structureChatMessages = document.getElementById('structure-chat-messages');
const structureChatInput = document.getElementById('structure-chat-input');
const sendStructureChatBtn = document.getElementById('send-structure-chat-btn');
const attachStructureDocBtn = document.getElementById('attach-structure-doc-btn');
const structureDocUpload = document.getElementById('structure-doc-upload');
const attachedStructureFile = document.getElementById('attached-structure-file');

// ============================================
// UTILITY FUNCTIONS
// ============================================

function escapeRegex(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function renderMarkdown(markdown, chapters = null) {
    if (!markdown) return '';

    let html = markdown;

    // Convert chapter references to clickable links if chapters are provided
    if (chapters && chapters.length > 0) {
        // Sort chapters by name length (longest first) to match specific names first
        const sortedChapters = [...chapters].sort((a, b) => b.name.length - a.name.length);

        sortedChapters.forEach((chapter, idx) => {
            const chapterName = chapter.name;
            const anchorId = `chapter-${idx}`;

            // Match patterns like: (see **Chapter Name**)
            const patterns = [
                new RegExp(`\\(see\\s+\\*\\*${escapeRegex(chapterName)}\\*\\*\\)`, 'gi'),
                new RegExp(`\\(see\\s+${escapeRegex(chapterName)}\\)`, 'gi'),
                new RegExp(`\\*\\*${escapeRegex(chapterName)}\\*\\*`, 'g')
            ];

            patterns.forEach(pattern => {
                html = html.replace(pattern, (match) => {
                    return `<a href="#${anchorId}" class="chapter-link" style="color: var(--primary); font-weight: 600; text-decoration: none; border-bottom: 2px solid var(--primary);">${match}</a>`;
                });
            });
        });
    }

    // Extract and preserve mermaid diagrams
    const mermaidBlocks = [];
    html = html.replace(/```mermaid\n([\s\S]*?)```/g, (match, code) => {
        const id = `mermaid-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        mermaidBlocks.push({ id, code: code.trim() });
        return `<div class="mermaid" id="${id}"></div>`;
    });

    // Code blocks (non-mermaid)
    html = html.replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');

    // Headers
    html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

    // Bold and Italic
    html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // Images
    html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" style="max-width: 100%; border-radius: 8px; margin: 1rem 0;">');

    // Links
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

    // Tables
    html = html.replace(/\|(.+)\|\n\|[-:\s|]+\|\n((?:\|.+\|\n?)+)/g, (match, header, rows) => {
        const headers = header.split('|').filter(h => h.trim()).map(h => `<th>${h.trim()}</th>`).join('');
        const rowsHtml = rows.trim().split('\n').map(row => {
            const cells = row.split('|').filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`).join('');
            return `<tr>${cells}</tr>`;
        }).join('');
        return `<table class="markdown-table" style="width: 100%; border-collapse: collapse; margin: 1rem 0;"><thead><tr>${headers}</tr></thead><tbody>${rowsHtml}</tbody></table>`;
    });

    // Unordered lists
    html = html.replace(/^\* (.+)$/gim, '<li>$1</li>');
    html = html.replace(/^- (.+)$/gim, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');

    // Ordered lists
    html = html.replace(/^\d+\. (.+)$/gim, '<li>$1</li>');

    // Line breaks (double newline = paragraph)
    html = html.replace(/\n\n/g, '</p><p>');
    html = '<p>' + html + '</p>';

    // Clean up empty paragraphs
    html = html.replace(/<p>\s*<\/p>/g, '');
    html = html.replace(/<p>(<h[1-6]>)/g, '$1');
    html = html.replace(/(<\/h[1-6]>)<\/p>/g, '$1');
    html = html.replace(/<p>(<table)/g, '$1');
    html = html.replace(/(<\/table>)<\/p>/g, '$1');
    html = html.replace(/<p>(<ul>)/g, '$1');
    html = html.replace(/(<\/ul>)<\/p>/g, '$1');
    html = html.replace(/<p>(<div)/g, '$1');
    html = html.replace(/(<\/div>)<\/p>/g, '$1');

    // Render mermaid diagrams after DOM insertion
    if (mermaidBlocks.length > 0) {
        setTimeout(() => {
            mermaidBlocks.forEach(({ id, code }) => {
                const element = document.getElementById(id);
                if (element && window.mermaid) {
                    element.textContent = code;
                    window.mermaid.init(undefined, element);
                }
            });
        }, 100);
    }

    return html;
}

function showToast(message, type = 'info') {
    toast.textContent = message;
    toast.className = 'toast ' + type;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
}

function showLoading(message = 'Processing...') {
    loadingMessage.textContent = message;
    loading.style.display = 'flex';
}

function hideLoading() {
    loading.style.display = 'none';
}

function scrollToElement(element) {
    setTimeout(() => {
        element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
}

// ============================================
// STEP 1: COURSE ANALYSIS
// ============================================

analyzeCourseBtn.addEventListener('click', async () => {
    const course = courseInput.value.trim();

    if (!course) {
        showToast('Please enter a course/exam name', 'error');
        return;
    }

    showLoading('Analyzing course structure & exam format...');
    analyzeCourseBtn.disabled = true;

    try {
        const response = await fetch('/api/generate-subjects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ course })
        });

        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        courseStructure = data;
        displayCourseStructure();

        structureSection.style.display = 'block';
        scrollToElement(structureSection);
        showToast('Course structure generated successfully!', 'success');

    } catch (error) {
        showToast(error.message || 'Failed to generate structure', 'error');
    } finally {
        hideLoading();
        analyzeCourseBtn.disabled = false;
    }
});

// ============================================
// STEP 2: DISPLAY & REFINE STRUCTURE
// ============================================

function displayCourseStructure() {
    // Display exam format
    const examFormat = courseStructure.exam_format || {};
    const questionFormat = examFormat.question_format || {};
    const bloomsDist = examFormat.blooms_distribution || courseStructure.blooms_distribution || {};
    const diffDist = examFormat.difficulty_distribution || {};
    const imageBySubject = examFormat.image_percentage_by_subject || {};

    let formatHTML = '<div style="display: grid; gap: 1.5rem;">';

    // Basic Format
    formatHTML += `
        <div class="format-section">
            <h4 style="margin: 0 0 0.5rem 0; color: var(--primary);">Question Format</h4>
            <div class="format-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 0.75rem;">
                <div class="format-item" style="padding: 0.5rem; background: var(--bg); border-radius: 4px;">
                    <small style="color: var(--text-muted);">Type</small><br>
                    <strong>${questionFormat.type || examFormat.type || 'Single best answer'}</strong>
                </div>
                <div class="format-item" style="padding: 0.5rem; background: var(--bg); border-radius: 4px;">
                    <small style="color: var(--text-muted);">Options</small><br>
                    <strong>${questionFormat.num_options || examFormat.num_options || 4}</strong>
                </div>
                <div class="format-item" style="padding: 0.5rem; background: var(--bg); border-radius: 4px;">
                    <small style="color: var(--text-muted);">Images</small><br>
                    <strong>~${questionFormat.image_questions_percentage || examFormat.image_questions_percentage || 0}%</strong>
                </div>
                <div class="format-item" style="padding: 0.5rem; background: var(--bg); border-radius: 4px;">
                    <small style="color: var(--text-muted);">Vignettes</small><br>
                    <strong>${questionFormat.uses_vignettes ? 'Yes' : 'No'}</strong>
                </div>
            </div>
        </div>
    `;

    // Bloom's Distribution
    const bloomLevels = {
        '1_remember': 'Remember', '2_understand': 'Understand', '3_apply': 'Apply',
        '4_analyze': 'Analyze', '5_evaluate': 'Evaluate'
    };

    formatHTML += `
        <div class="format-section">
            <h4 style="margin: 0 0 0.5rem 0; color: var(--primary);">Bloom's Level Distribution</h4>
            <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
    `;

    Object.entries(bloomLevels).forEach(([key, name]) => {
        const percentage = bloomsDist[key] || bloomsDist[key.split('_')[0]] || 0;
        if (percentage > 0) {
            formatHTML += `
                <div style="padding: 0.4rem 0.8rem; background: var(--bg); border-radius: 4px; font-size: 0.9rem;">
                    <small style="color: var(--text-muted);">${name}</small>
                    <strong style="margin-left: 0.5rem;">${percentage}%</strong>
                </div>
            `;
        }
    });

    formatHTML += `</div></div>`;

    // Difficulty Distribution
    if (diffDist.easy || diffDist.medium || diffDist.hard) {
        formatHTML += `
            <div class="format-section">
                <h4 style="margin: 0 0 0.5rem 0; color: var(--primary);">Difficulty Distribution</h4>
                <div style="display: flex; gap: 0.5rem;">
        `;

        const difficulties = {
            'easy': 'Easy', 'medium': 'Medium', 'hard': 'Hard'
        };

        Object.entries(difficulties).forEach(([key, name]) => {
            const percentage = diffDist[key] || 0;
            if (percentage > 0) {
                formatHTML += `
                    <div style="padding: 0.4rem 0.8rem; background: var(--bg); border-radius: 4px; font-size: 0.9rem;">
                        <small style="color: var(--text-muted);">${name}</small>
                        <strong style="margin-left: 0.5rem;">${percentage}%</strong>
                    </div>
                `;
            }
        });

        formatHTML += `</div></div>`;
    }

    formatHTML += '</div>';
    examFormatDetails.innerHTML = formatHTML;

    // Display subjects & topics tree
    let treeHTML = '<div class="subjects-tree" style="max-height: 400px; overflow-y: auto;">';

    courseStructure.subjects.forEach((subject, idx) => {
        const imagePercentage = imageBySubject[subject.name] || questionFormat.image_questions_percentage || 0;

        treeHTML += `
            <div class="subject-item" style="margin-bottom: 1rem; padding: 1rem; background: var(--bg-secondary); border-radius: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <strong style="font-size: 1.1rem;">${idx + 1}. ${subject.name}</strong>
                    <span style="color: var(--text-muted); font-size: 0.9rem;">~${imagePercentage}% images</span>
                </div>
                <div style="margin-top: 0.5rem; padding-left: 1rem;">
                    <small style="color: var(--text-muted);">${subject.topics.length} topics</small>
                    <div style="margin-top: 0.25rem; display: flex; flex-wrap: wrap; gap: 0.5rem;">
                        ${subject.topics.slice(0, 5).map(t => `<span style="background: var(--bg); padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.85rem;">${t.name}</span>`).join('')}
                        ${subject.topics.length > 5 ? `<span style="color: var(--text-muted); font-size: 0.85rem;">+${subject.topics.length - 5} more</span>` : ''}
                    </div>
                </div>
            </div>
        `;
    });

    treeHTML += '</div>';
    structureTree.innerHTML = treeHTML;
}

// Chat interface for structure refinement
attachStructureDocBtn.addEventListener('click', () => {
    structureDocUpload.click();
});

structureDocUpload.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        attachedStructureFile.textContent = file.name;
    }
});

sendStructureChatBtn.addEventListener('click', async () => {
    const message = structureChatInput.value.trim();
    const file = structureDocUpload.files[0];

    if (!message && !file) return;

    // Show chat messages area
    structureChatMessages.style.display = 'block';

    // Add user message to chat
    if (message) {
        const userMsgHTML = `<div class="chat-message user" style="margin-bottom: 0.5rem;"><strong>You:</strong> ${message}</div>`;
        structureChatMessages.insertAdjacentHTML('beforeend', userMsgHTML);
        structureChatInput.value = '';
    }

    showLoading('Refining structure...');

    try {
        const formData = new FormData();
        formData.append('message', message);
        formData.append('course', courseStructure.Course);
        formData.append('current_structure', JSON.stringify(courseStructure));
        if (file) {
            formData.append('document', file);
        }

        const response = await fetch('/api/refine-structure', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        // Update structure and display
        if (data.modified) {
            courseStructure = data.structure;
            displayCourseStructure();
        }

        // Add assistant response to chat
        const assistantMsgHTML = `<div class="chat-message assistant" style="margin-bottom: 0.5rem;"><strong>Assistant:</strong> ${data.response}</div>`;
        structureChatMessages.insertAdjacentHTML('beforeend', assistantMsgHTML);

        structureChatMessages.style.display = 'block';
        structureChatMessages.scrollTop = structureChatMessages.scrollHeight;

    } catch (error) {
        showToast(error.message || 'Failed to refine structure', 'error');
    } finally {
        hideLoading();
        structureDocUpload.value = '';
        attachedStructureFile.textContent = '';
    }
});

// ============================================
// STEP 3: APPROVE & GENERATE
// ============================================

approveStructureBtn.addEventListener('click', () => {
    // Populate subject selector
    mainSubjectSelect.innerHTML = '<option value="">Choose a subject...</option>';
    courseStructure.subjects.forEach((subject, idx) => {
        const option = document.createElement('option');
        option.value = idx;
        option.textContent = subject.name;
        mainSubjectSelect.appendChild(option);
    });

    generateSection.style.display = 'block';
    scrollToElement(generateSection);
    showToast('Structure approved! Select subject/topics to generate content.', 'success');
});

// Subject selection - populate topics
mainSubjectSelect.addEventListener('change', () => {
    const subjectIdx = mainSubjectSelect.value;
    mainTopicsSelect.innerHTML = '';

    generateLessonBtn.disabled = true;
    generateQbankBtn.disabled = true;

    if (!subjectIdx || !courseStructure) return;

    const subject = courseStructure.subjects[subjectIdx];
    if (!subject || !subject.topics) return;

    subject.topics.forEach(topic => {
        const option = document.createElement('option');
        option.value = topic.name;
        option.textContent = topic.name;
        mainTopicsSelect.appendChild(option);
    });

    updateQuestionDistribution();
});

// Topics selection
mainTopicsSelect.addEventListener('change', () => {
    const selectedTopics = Array.from(mainTopicsSelect.selectedOptions);
    const hasSelection = selectedTopics.length > 0 || generateAllCheckbox.checked;

    generateLessonBtn.disabled = !hasSelection;
    generateQbankBtn.disabled = !hasSelection;

    updateQuestionDistribution();
});

// Generate all checkbox
generateAllCheckbox.addEventListener('change', () => {
    const hasSelection = generateAllCheckbox.checked || Array.from(mainTopicsSelect.selectedOptions).length > 0;
    generateLessonBtn.disabled = !hasSelection;
    generateQbankBtn.disabled = !hasSelection;

    updateQuestionDistribution();
});

// Number of questions slider
numQuestionsInput.addEventListener('input', () => {
    numDisplay.textContent = numQuestionsInput.value;
    updateQuestionDistribution();
});

// ============================================
// UPDATE TOTAL QUESTIONS
// ============================================

function updateQuestionDistribution() {
    const numQuestions = parseInt(numQuestionsInput.value);
    const selectedTopics = Array.from(mainTopicsSelect.selectedOptions);
    const numTopics = generateAllCheckbox.checked && courseStructure ?
        courseStructure.subjects.reduce((sum, s) => sum + s.topics.length, 0) :
        selectedTopics.length || 0;

    // Just show total questions
    if (numTopics > 1) {
        const totalQuestions = numQuestions * numTopics;
        totalQuestionsInfo.innerHTML = `Total: <strong>${totalQuestions} questions</strong> (${numQuestions} per topic × ${numTopics} topics)`;
    } else if (numTopics === 1) {
        totalQuestionsInfo.innerHTML = `Total: <strong>${numQuestions} questions</strong>`;
    } else {
        totalQuestionsInfo.innerHTML = '';
    }
}

// ============================================
// GENERATE LESSONS
// ============================================

generateLessonBtn.addEventListener('click', async () => {
    const course = courseStructure.Course;
    const subjectIdx = mainSubjectSelect.value;
    const selectedTopics = Array.from(mainTopicsSelect.selectedOptions).map(opt => opt.value);
    const generateAll = generateAllCheckbox.checked;

    if (!generateAll && !subjectIdx) {
        showToast('Please select a subject', 'error');
        return;
    }

    showLoading('Generating lessons...');
    generateLessonBtn.disabled = true;

    try {
        const requestData = {
            course,
            uploaded_json: courseStructure,  // Send full structure
            generate_all: generateAll
        };

        if (!generateAll) {
            // Find subject index
            requestData.selected_subject_idx = parseInt(subjectIdx);

            // Find topic indices
            const subject = courseStructure.subjects[subjectIdx];
            requestData.selected_topic_indices = selectedTopics.map(topicName =>
                subject.topics.findIndex(t => t.name === topicName)
            ).filter(idx => idx !== -1);
        }

        const response = await fetch('/api/generate-lessons', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        });

        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        generatedContent = data.lessons;
        displayLessonsResults(data.lessons, course);
        showToast(`Generated ${data.lessons.length} lessons!`, 'success');

    } catch (error) {
        showToast(error.message || 'Failed to generate lessons', 'error');
    } finally {
        hideLoading();
        generateLessonBtn.disabled = false;
    }
});

// ============================================
// GENERATE QBANK
// ============================================

generateQbankBtn.addEventListener('click', async () => {
    const course = courseStructure.Course;
    const subjectIdx = mainSubjectSelect.value;
    const selectedTopics = Array.from(mainTopicsSelect.selectedOptions).map(opt => opt.value);
    const numQuestions = parseInt(numQuestionsInput.value);

    if (!subjectIdx) {
        showToast('Please select a subject', 'error');
        return;
    }

    if (selectedTopics.length === 0) {
        showToast('Please select at least one topic', 'error');
        return;
    }

    const subject = courseStructure.subjects[subjectIdx].name;

    showLoading('Generating questions...');
    generateQbankBtn.disabled = true;

    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                course,
                subject,
                topics: selectedTopics,
                num_questions: numQuestions,
                include_images: true, // Always include based on exam format
                exam_format: courseStructure.exam_format
            })
        });

        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        generatedContent = data.questions;
        displayQBankResults(data.questions, course, data.image_stats);

        let message = `Generated ${data.count} questions!`;
        if (data.image_stats) {
            message += ` | ${data.image_stats.image_based_count} image-based (${data.image_stats.image_percentage})`;
        }
        showToast(message, 'success');

    } catch (error) {
        showToast(error.message || 'Failed to generate questions', 'error');
    } finally {
        hideLoading();
        generateQbankBtn.disabled = false;
    }
});

// ============================================
// DISPLAY RESULTS
// ============================================

function displayLessonsResults(lessons, course) {
    resultsTitle.textContent = 'Generated Lessons';

    // Action buttons
    resultsActions.innerHTML = `
        <button id="download-lessons-json" class="btn-secondary">Download JSON</button>
        <button id="download-lessons-md" class="btn-secondary">📄 Download Markdown</button>
    `;

    // Stats
    const totalChapters = lessons.reduce((sum, l) => sum + (l.chapters?.length || 0), 0);

    resultsStats.innerHTML = `
        <div class="stat-item">
            <div class="label">TOTAL LESSONS</div>
            <div class="value">${lessons.length}</div>
        </div>
        <div class="stat-item">
            <div class="label">COURSE</div>
            <div class="value">${course}</div>
        </div>
        ${totalChapters > 0 ? `
            <div class="stat-item">
                <div class="label">CHAPTERS</div>
                <div class="value">${totalChapters}</div>
            </div>
        ` : ''}
    `;

    // Lessons content
    let html = '';
    lessons.forEach((lesson, idx) => {
        html += `
            <div class="lesson-card" style="margin-bottom: 3rem; padding: 1.5rem; background: var(--bg-secondary); border-radius: 8px;">
                <div style="display: flex; align-items: center; margin-bottom: 1rem;">
                    <h2 style="margin: 0;">${idx + 1}. ${lesson.subject} - ${lesson.topic}</h2>
                    ${lesson.high_yield ? '<span style="background: var(--primary); color: white; padding: 0.4rem 0.8rem; border-radius: 4px; font-size: 0.9rem; margin-left: 1rem;">⭐ High Yield</span>' : ''}
                </div>

                <div class="lesson-content markdown-content" style="margin-top: 1rem; line-height: 1.6;">
                    ${renderMarkdown(lesson.topic_lesson || 'No content', lesson.chapters)}
                </div>

                ${lesson.chapters && lesson.chapters.length > 0 ? `
                    <div class="deep-dive-section" style="margin-top: 2.5rem; padding-top: 2rem; border-top: 3px solid var(--primary);">
                        <h3 style="color: var(--primary); margin-bottom: 1.5rem;">
                            📚 Deep Dive - Chapter Lessons
                        </h3>
                        <div>
                            ${lesson.chapters.map((chapter, cIdx) => `
                                <div id="chapter-${cIdx}" class="chapter-deep-dive" style="margin-bottom: 2.5rem; padding: 1.5rem; background: var(--bg); border-left: 4px solid var(--primary); border-radius: 8px; scroll-margin-top: 100px;">
                                    <h4 style="margin: 0 0 1rem 0; color: var(--primary); font-size: 1.3rem;">
                                        ${cIdx + 1}. ${chapter.name}
                                    </h4>
                                    <div class="markdown-content" style="line-height: 1.6;">
                                        ${renderMarkdown(chapter.lesson || 'No content')}
                                    </div>
                                    <a href="#top" style="display: inline-block; margin-top: 1rem; color: var(--primary); text-decoration: none; font-size: 0.9rem;">
                                        ↑ Back to top
                                    </a>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                ` : ''}
            </div>
        `;
    });

    resultsContainer.innerHTML = html;

    resultsSection.style.display = 'block';
    scrollToElement(resultsSection);

    // Download handlers
    document.getElementById('download-lessons-json').addEventListener('click', () => {
        downloadJSON(lessons, `lessons_${course}_${Date.now()}.json`);
    });

    document.getElementById('download-lessons-md').addEventListener('click', () => {
        downloadLessonsMarkdown(lessons, course);
    });
}

function displayQBankResults(questions, course, imageStats) {
    resultsTitle.textContent = 'Generated Questions';

    // Action buttons
    resultsActions.innerHTML = `
        <button id="download-qbank-json" class="btn-secondary">Download JSON</button>
        <button id="download-qbank-md" class="btn-secondary">📄 Download Markdown</button>
    `;

    // Stats
    let statsHTML = `
        <div class="stat-item">
            <div class="label">Total Questions</div>
            <div class="value">${questions.length}</div>
        </div>
        <div class="stat-item">
            <div class="label">Course</div>
            <div class="value">${course}</div>
        </div>
    `;

    if (imageStats) {
        statsHTML += `
            <div class="stat-item">
                <div class="label">Image-Based</div>
                <div class="value">${imageStats.image_based_count} (${imageStats.image_percentage})</div>
            </div>
            <div class="stat-item">
                <div class="label">Images Found</div>
                <div class="value">${imageStats.images_found}/${imageStats.image_based_count}</div>
            </div>
        `;
    }

    resultsStats.innerHTML = statsHTML;

    // Questions content
    const difficultyLabels = { 1: 'Medium', 2: 'Hard', 3: 'Very Hard' };

    let html = '';
    questions.forEach((q, idx) => {
        html += `
            <div class="question-card" style="margin-bottom: 2rem; padding: 1.5rem; background: var(--bg-secondary); border-radius: 8px;">
                <div class="question-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                    <span class="question-number" style="font-weight: 600; font-size: 1.1rem;">Q${idx + 1}</span>
                    <div class="question-tags">
                        <span class="tag" style="background: var(--primary); color: white; padding: 0.25rem 0.5rem; border-radius: 4px; margin-left: 0.5rem; font-size: 0.85rem;">Bloom's L${q.blooms_level}</span>
                        <span class="tag" style="background: var(--bg); padding: 0.25rem 0.5rem; border-radius: 4px; margin-left: 0.5rem; font-size: 0.85rem;">${difficultyLabels[q.difficulty]}</span>
                        ${q.image_url || q.image_description ? '<span class="tag" style="background: var(--primary); color: white; padding: 0.25rem 0.5rem; border-radius: 4px; margin-left: 0.5rem; font-size: 0.85rem;">📷 Image</span>' : ''}
                    </div>
                </div>

                ${q.image_url ? `
                    <div class="question-image" style="margin-bottom: 1rem;">
                        <img src="${q.image_url}" alt="${q.image_description || 'Medical image'}" style="max-width: 100%; border-radius: 8px;">
                        ${q.image_source ? `<small style="color: var(--text-muted);">Source: ${q.image_source}</small>` : ''}
                    </div>
                ` : (q.image_description ? `
                    <div class="image-placeholder" style="margin-bottom: 1rem; padding: 1rem; background: var(--bg); border-radius: 8px; border: 2px dashed var(--border);">
                        <div style="text-align: center; color: var(--text-muted);">🖼️</div>
                        <p style="margin: 0.5rem 0 0 0; font-size: 0.9rem;"><strong>${q.image_type || 'Image'}:</strong> ${q.image_description}</p>
                    </div>
                ` : '')}

                <p class="question-text" style="font-size: 1.05rem; line-height: 1.6; margin-bottom: 1rem;">${q.question}</p>

                <ul class="options-list" style="list-style: none; padding: 0;">
                    ${q.options.map((opt, i) => `
                        <li style="padding: 0.75rem; margin: 0.5rem 0; background: ${opt === q.correct_option ? 'var(--primary)' : 'var(--bg)'}; color: ${opt === q.correct_option ? 'white' : 'inherit'}; border-radius: 8px; font-weight: ${opt === q.correct_option ? '600' : 'normal'};">
                            ${String.fromCharCode(65 + i)}. ${opt}
                        </li>
                    `).join('')}
                </ul>

                <div class="explanation" style="margin-top: 1rem; padding: 1rem; background: var(--bg); border-left: 4px solid var(--primary); border-radius: 4px;">
                    <strong>Explanation:</strong> ${q.explanation}
                </div>
            </div>
        `;
    });

    resultsContainer.innerHTML = html;

    resultsSection.style.display = 'block';
    scrollToElement(resultsSection);

    // Download handlers
    document.getElementById('download-qbank-json').addEventListener('click', () => {
        downloadJSON(questions, `qbank_${course}_${Date.now()}.json`);
    });

    document.getElementById('download-qbank-md').addEventListener('click', async () => {
        await downloadQBankMarkdown(questions, course);
    });
}

// ============================================
// DOWNLOAD FUNCTIONS
// ============================================

function downloadJSON(data, filename) {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Downloaded successfully!', 'success');
}

function downloadLessonsMarkdown(lessons, course) {
    let markdown = `# Lessons - ${course}\n\n`;
    markdown += `**Generated:** ${new Date().toLocaleString()}\n\n`;
    markdown += `---\n\n`;

    lessons.forEach((lesson, idx) => {
        markdown += `# ${idx + 1}. ${lesson.subject} - ${lesson.topic}\n\n`;
        if (lesson.high_yield) {
            markdown += `**⭐ High Yield Topic**\n\n`;
        }
        markdown += lesson.topic_lesson + '\n\n';

        if (lesson.chapters && lesson.chapters.length > 0) {
            markdown += `## Chapter Deep Dives\n\n`;
            lesson.chapters.forEach((chapter, cIdx) => {
                markdown += `### ${cIdx + 1}. ${chapter.name}\n\n`;
                markdown += chapter.lesson + '\n\n';
            });
        }

        markdown += `---\n\n`;
    });

    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `lessons_${course.replace(/\s+/g, '_')}_${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Markdown downloaded!', 'success');
}

async function downloadQBankMarkdown(questions, course) {
    showToast('Generating markdown...', 'info');

    let markdown = `# QBank - ${course}\n\n`;
    markdown += `**Generated:** ${new Date().toLocaleString()}\n`;
    markdown += `**Total Questions:** ${questions.length}\n\n`;
    markdown += `---\n\n`;

    for (let i = 0; i < questions.length; i++) {
        const q = questions[i];
        const diffLabels = { 1: 'Medium', 2: 'Hard', 3: 'Very Hard' };

        markdown += `## Q${i + 1}\n\n`;
        markdown += `**Bloom's Level:** ${q.blooms_level} | **Difficulty:** ${diffLabels[q.difficulty]}\n\n`;

        if (q.image_url) {
            // Try to embed image as base64
            try {
                const response = await fetch(q.image_url);
                const blob = await response.blob();
                const base64 = await new Promise((resolve) => {
                    const reader = new FileReader();
                    reader.onloadend = () => resolve(reader.result);
                    reader.readAsDataURL(blob);
                });
                markdown += `![${q.image_type || 'Image'}](${base64})\n\n`;
            } catch (e) {
                markdown += `![${q.image_type || 'Image'}](${q.image_url})\n\n`;
            }
        }

        markdown += `**Question:**\n${q.question}\n\n`;
        markdown += `**Options:**\n`;
        q.options.forEach((opt, idx) => {
            const marker = opt === q.correct_option ? '✓' : ' ';
            markdown += `${marker} ${String.fromCharCode(65 + idx)}. ${opt}\n`;
        });
        markdown += `\n**Explanation:**\n${q.explanation}\n\n`;
        markdown += `---\n\n`;
    }

    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `qbank_${course.replace(' ', '_')}_${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Markdown downloaded!', 'success');
}

// ============================================
// IMAGE UTILITY - Single Click Experience
// ============================================

const addImagesBtn = document.getElementById('add-images-btn');
const jsonFileInput = document.getElementById('json-file-input');
const processingStatus = document.getElementById('processing-status');

// Single button - opens file dialog and auto-processes
addImagesBtn.addEventListener('click', () => {
    jsonFileInput.click();
});

// Auto-process when file is selected
jsonFileInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    processingStatus.textContent = `Selected: ${file.name}`;
    showLoading('Adding images to questions...');

    try {
        const text = await file.text();
        const questions = JSON.parse(text);

        processingStatus.textContent = `Processing ${questions.length} questions...`;

        const response = await fetch('/api/add-image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ questions })
        });

        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        // Display results
        const imageStats = {
            total_questions: data.questions.length,
            image_based_count: data.questions.filter(q => q.image_description || q.image_type).length,
            images_found: data.questions.filter(q => q.image_url).length
        };

        document.getElementById('image-result').style.display = 'block';
        document.getElementById('image-stats').innerHTML = `
            <div class="stat-item">
                <div class="label">Total Questions</div>
                <div class="value">${imageStats.total_questions}</div>
            </div>
            <div class="stat-item">
                <div class="label">Image-Based</div>
                <div class="value">${imageStats.image_based_count}</div>
            </div>
            <div class="stat-item">
                <div class="label">Images Found</div>
                <div class="value">${imageStats.images_found}</div>
            </div>
        `;

        // Display questions with images
        displayQBankResults(data.questions, 'Image Enhancement', imageStats);

        processingStatus.textContent = `✓ Processed ${data.questions.length} questions - ${imageStats.images_found} images added`;
        processingStatus.style.color = 'var(--primary)';
        showToast(`Successfully added images to ${imageStats.images_found} questions!`, 'success');

        // Update download handlers for utility tab
        document.getElementById('download-image-result-btn').addEventListener('click', () => {
            downloadJSON(data.questions, `questions_with_images_${Date.now()}.json`);
        });

        document.getElementById('download-image-md-btn').addEventListener('click', async () => {
            await downloadQBankMarkdown(data.questions, 'Image Enhancement');
        });

    } catch (error) {
        processingStatus.textContent = `✗ Error: ${error.message}`;
        processingStatus.style.color = 'red';
        showToast(error.message || 'Failed to add images', 'error');
    } finally {
        hideLoading();
        jsonFileInput.value = ''; // Reset for next use
    }
});

// Initialize
updateQuestionDistribution();

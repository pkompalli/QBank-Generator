console.log('🚀 app.js is loading...');

// DOM Elements - Question Bank
const qbankCourseInput = document.getElementById('qbank-course');
const qbankGenerateSubjectsBtn = document.getElementById('qbank-generate-subjects-btn');
const qbankUploadStructureBtn = document.getElementById('qbank-upload-structure-btn');
const qbankJsonFile = document.getElementById('qbank-json-file');
const qbankStructureStatus = document.getElementById('qbank-structure-status');
const qbankSubjectsContainer = document.getElementById('qbank-subjects-container');
const subjectSelect = document.getElementById('subject-select');
const topicsSelect = document.getElementById('topics-select');
const includeImagesCheckbox = document.getElementById('include-images');
const numQuestionsInput = null; // slider removed
const numDisplay = null;
const bloomInfo = document.getElementById('bloom-distribution');
const totalQuestionsInfo = document.getElementById('total-questions-info');
const perTopicLabel = null;
const generateBtn = document.getElementById('generate-btn');
const resultsSection = document.getElementById('results');
const questionsContainer = document.getElementById('questions-container');
const statsContainer = document.getElementById('stats');
const downloadBtn = document.getElementById('download-btn');
const copyBtn = document.getElementById('copy-btn');
const loading = document.getElementById('loading');
const toast = document.getElementById('toast');

// New Structure Review Elements
const structureSection = document.getElementById('structure-section');
const examFormatDetails = document.getElementById('exam-format-details');
const structureTree = document.getElementById('structure-tree');
const approveStructureBtn = document.getElementById('approve-structure-btn');
const structureChatMessages = document.getElementById('structure-chat-messages');
const structureChatInput = document.getElementById('structure-chat-input');
const sendStructureChatBtn = document.getElementById('send-structure-chat-btn');
const attachStructureDocBtn = document.getElementById('attach-structure-doc-btn');
const structureDocUpload = document.getElementById('structure-doc-upload');
const attachedStructureFile = document.getElementById('attached-structure-file');

let generatedQuestions = [];
let courseStructure = null; // Shared structure for both Lessons and QBank tabs
let uploadedStructureData = null; // Holds normalized structure from uploaded JSON file
let selectedExamFormat = null; // Pre-loaded exam format — skips analyze_exam_format on generate-subjects

let attachedFile = null;
let _validationState = null; // Stores report + original content for Fix Selected
let _fixedItemIndices = new Set(); // Tracks indices that have been fixed this session

// Save / Regenerate state — QBank
let lastSaveMeta = null;    // { questions, course, subject, topics }
let lastRegenerateFn = null; // () => void — re-runs the last generation
let currentQBankSessionId = null; // set after first explicit save; reused for updates

// Save / Regenerate state — Lessons
let lastLessonsSaveMeta = null;    // { lessons_data, course, subject }
let lastLessonsRegenerateFn = null; // () => void
let currentLessonsSessionId = null; // set after first explicit save; reused for updates

function escapeHtml(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Update Bloom's level distribution display
function updateBloomDistribution() {
    // Disabled - user doesn't want to see the distribution table
    return;

    // Check if QBank elements exist (they may not if on different tab)
    if (!numQuestionsInput || !topicsSelect || !bloomInfo) {
        return; // Skip if elements don't exist
    }

    const course = courseStructure?.Course || '';
    const numQuestions = parseInt(numQuestionsInput.value);
    const selectedTopics = Array.from(topicsSelect.selectedOptions).map(opt => opt.value);
    const numTopics = selectedTopics.length || 1;

    if (!course || !courseStructure) {
        bloomInfo.innerHTML = '<p>Load course structure to see distribution</p>';
        if (totalQuestionsInfo) totalQuestionsInfo.innerHTML = '';
        if (perTopicLabel) perTopicLabel.style.display = 'none';
        return;
    }

    if (perTopicLabel) perTopicLabel.style.display = 'inline';

    const levelNames = {
        1: 'Remember',
        2: 'Understand',
        3: 'Apply',
        4: 'Analyze',
        5: 'Evaluate'
    };

    const difficultyNames = {
        'medium': 'Medium',
        'hard': 'Hard',
        'very_hard': 'Very Hard'
    };

    let html = '';
    let levels = [1, 2, 3, 4, 5];
    let difficulties = ['medium', 'hard', 'very_hard'];

    // Use course-specific distributions if available
    if (courseStructure?.exam_format?.blooms_distribution && courseStructure?.exam_format?.difficulty_distribution) {
        const bloomsPercentages = courseStructure.exam_format.blooms_distribution;
        const difficultyPercentages = courseStructure.exam_format.difficulty_distribution;

        // Convert backend format (easy, medium, hard) to our format (medium, hard, very_hard)
        const adjustedDifficultyPercentages = {
            'medium': difficultyPercentages.easy || 0 + (difficultyPercentages.medium || 0) * 0.5,
            'hard': (difficultyPercentages.medium || 0) * 0.5 + (difficultyPercentages.hard || 0) * 0.5,
            'very_hard': (difficultyPercentages.hard || 0) * 0.5
        };

        // Normalize percentages
        const totalDiffPercentage = adjustedDifficultyPercentages.medium + adjustedDifficultyPercentages.hard + adjustedDifficultyPercentages.very_hard;
        if (totalDiffPercentage > 0) {
            difficulties.forEach(diff => {
                adjustedDifficultyPercentages[diff] = (adjustedDifficultyPercentages[diff] / totalDiffPercentage) * 100;
            });
        }

        // Get Bloom's percentages (sum 1-5 levels, ignoring 6-7)
        const bloomsMap = {
            1: bloomsPercentages['1_remember'] || bloomsPercentages['1'] || 0,
            2: bloomsPercentages['2_understand'] || bloomsPercentages['2'] || 0,
            3: bloomsPercentages['3_apply'] || bloomsPercentages['3'] || 0,
            4: bloomsPercentages['4_analyze'] || bloomsPercentages['4'] || 0,
            5: bloomsPercentages['5_evaluate'] || bloomsPercentages['5'] || 0
        };

        // Normalize Bloom's percentages to 100% (ignore levels 6-7)
        const totalBloomPercentage = Object.values(bloomsMap).reduce((a, b) => a + b, 0);
        if (totalBloomPercentage > 0) {
            levels.forEach(level => {
                bloomsMap[level] = (bloomsMap[level] / totalBloomPercentage) * 100;
            });
        }

        // Create matrix
        html = '<div style="overflow-x: auto;"><table class="distribution-matrix" style="width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: 0.9rem;">';

        // Header row
        html += '<thead><tr><th style="border: 1px solid var(--border); padding: 0.5rem; background: var(--bg-secondary); text-align: left;">Bloom\'s Level</th>';
        difficulties.forEach(diff => {
            html += `<th style="border: 1px solid var(--border); padding: 0.5rem; background: var(--bg-secondary); text-align: center;">${difficultyNames[diff]}</th>`;
        });
        html += '<th style="border: 1px solid var(--border); padding: 0.5rem; background: var(--primary); color: white; text-align: center;">Total</th></tr></thead>';

        // Data rows
        html += '<tbody>';
        let difficultyTotals = { medium: 0, hard: 0, very_hard: 0 };
        let grandTotal = 0;

        levels.forEach(level => {
            html += `<tr><td style="border: 1px solid var(--border); padding: 0.5rem; font-weight: 500;">${level}. ${levelNames[level]}</td>`;
            let rowTotal = 0;

            difficulties.forEach(diff => {
                // Calculate count: (Bloom's %) × (Difficulty %) × numQuestions / 100
                const percentage = (bloomsMap[level] / 100) * (adjustedDifficultyPercentages[diff] / 100) * 100;
                const count = Math.round(numQuestions * percentage / 100);
                rowTotal += count;
                difficultyTotals[diff] += count;
                grandTotal += count;

                html += `<td style="border: 1px solid var(--border); padding: 0.5rem; text-align: center;">${count} <span style="color: var(--text-muted); font-size: 0.85rem;">(${percentage.toFixed(0)}%)</span></td>`;
            });

            html += `<td style="border: 1px solid var(--border); padding: 0.5rem; text-align: center; font-weight: 600; background: var(--bg-secondary);">${rowTotal}</td></tr>`;
        });

        // Footer row with totals
        html += '<tr style="font-weight: 600; background: var(--bg-secondary);"><td style="border: 1px solid var(--border); padding: 0.5rem;">Total</td>';
        difficulties.forEach(diff => {
            html += `<td style="border: 1px solid var(--border); padding: 0.5rem; text-align: center;">${difficultyTotals[diff]}</td>`;
        });
        html += `<td style="border: 1px solid var(--border); padding: 0.5rem; text-align: center; background: var(--primary); color: white;">${grandTotal}</td></tr>`;
        html += '</tbody></table></div>';

        // Adjust if total doesn't match numQuestions (due to rounding)
        if (grandTotal !== numQuestions) {
            html += `<p style="margin-top: 0.5rem; font-size: 0.85rem; color: var(--text-muted);">Note: Total adjusted to ${numQuestions} questions (rounding differences)</p>`;
        }

    } else {
        // Fallback: Equal distribution across Bloom's levels and difficulties
        const perCell = Math.floor(numQuestions / (levels.length * difficulties.length));
        const remainder = numQuestions % (levels.length * difficulties.length);

        html = '<div style="overflow-x: auto;"><table class="distribution-matrix" style="width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: 0.9rem;">';

        html += '<thead><tr><th style="border: 1px solid var(--border); padding: 0.5rem; background: var(--bg-secondary);">Bloom\'s Level</th>';
        difficulties.forEach(diff => {
            html += `<th style="border: 1px solid var(--border); padding: 0.5rem; background: var(--bg-secondary); text-align: center;">${difficultyNames[diff]}</th>`;
        });
        html += '</tr></thead><tbody>';

        let cellIdx = 0;
        levels.forEach(level => {
            html += `<tr><td style="border: 1px solid var(--border); padding: 0.5rem;">${level}. ${levelNames[level]}</td>`;
            difficulties.forEach(diff => {
                const count = perCell + (cellIdx < remainder ? 1 : 0);
                html += `<td style="border: 1px solid var(--border); padding: 0.5rem; text-align: center;">${count}</td>`;
                cellIdx++;
            });
            html += '</tr>';
        });

        html += '</tbody></table></div>';
    }

    bloomInfo.innerHTML = html;

    // Show total questions info
    if (totalQuestionsInfo) {
        const totalQuestions = numQuestions * numTopics;
        if (numTopics > 1) {
            totalQuestionsInfo.innerHTML = `<div class="total-info"><strong>Total: ${totalQuestions} questions</strong> (${numQuestions} × ${numTopics} topics)</div>`;
        } else if (numTopics === 1) {
            totalQuestionsInfo.innerHTML = `<div class="total-info"><strong>Total: ${totalQuestions} questions</strong></div>`;
        } else {
            totalQuestionsInfo.innerHTML = '';
        }
    }
}

// Show toast message
function showToast(message, type = 'info') {
    toast.textContent = message;
    toast.className = 'toast ' + type;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
}

// Display Structure Review Panel
function displayStructureReview() {
    console.log('🎯 displayStructureReview() called');

    if (!courseStructure) {
        console.error('❌ courseStructure is null in displayStructureReview()');
        return;
    }

    console.log('✅ courseStructure exists:', {
        hasCourse: !!courseStructure.Course,
        hasSubjects: !!courseStructure.subjects,
        subjectsLength: courseStructure.subjects?.length,
        hasExamFormat: !!courseStructure.exam_format
    });

    // Show structure section, hide course input
    const courseInputSection = document.getElementById('course-input-section');
    if (courseInputSection) courseInputSection.style.display = 'none';
    if (structureSection) structureSection.style.display = 'block';

    // Display Exam Format
    const examFormat = courseStructure.exam_format || {};
    const bloomsDist = examFormat.blooms_distribution || {};

    if (examFormatDetails) {
        examFormatDetails.innerHTML = `
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;">
                <div>
                    <strong>MCQ Options:</strong> ${examFormat.num_options || 4} options
                </div>
                <div>
                    <strong>Question Style:</strong> ${examFormat.question_style || 'Single best answer'}
                </div>
                ${examFormat.emphasis ? `
                <div style="grid-column: 1 / -1;">
                    <strong>Key Emphasis Areas:</strong> ${examFormat.emphasis.join(', ')}
                </div>
                ` : ''}
            </div>
        `;
    }

    // Display Subjects & Topics Tree
    const subjects = courseStructure.subjects || [];
    console.log(`📊 Displaying ${subjects.length} subjects in review panel`);

    if (structureTree) {
        structureTree.innerHTML = subjects.map((subject, idx) => {
            const topics = subject.topics || [];
            console.log(`  Subject ${idx + 1}: ${subject.name} (${topics.length} topics)`);

            return `
            <details style="margin-bottom: 1rem; padding: 0.75rem; background: var(--bg-secondary); border-radius: 8px; border: 1px solid var(--border);">
                <summary style="cursor: pointer; font-weight: 600; color: var(--primary); user-select: none;">
                    📚 ${subject.name} (${topics.length} topics)
                </summary>
                <div style="margin-top: 0.75rem; display: flex; flex-wrap: wrap; gap: 0.5rem;">
                    ${topics.map(topic => `
                        <span style="padding: 0.4rem 0.8rem; background: white; border: 1px solid var(--border); border-radius: 6px; font-size: 0.9rem;">
                            ${topic.name}${topic.high_yield ? ' ⭐' : ''}
                        </span>
                    `).join('')}
                </div>
            </details>
            `;
        }).join('');
    }

    // Clear chat messages
    if (structureChatMessages) {
        structureChatMessages.innerHTML = '';
        structureChatMessages.style.display = 'none';
    }

    // Scroll to review panel
    setTimeout(() => {
        if (structureSection) {
            structureSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }, 100);
}

// Add message to chat
function addChatMessage(content, sender = 'user') {
    if (!structureChatMessages) return;

    // Show chat messages container if hidden
    structureChatMessages.style.display = 'block';

    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${sender}`;
    messageDiv.innerHTML = `
        <div style="font-weight: 600; margin-bottom: 0.25rem; color: ${sender === 'user' ? 'var(--primary)' : 'var(--success)'};">
            ${sender === 'user' ? '👤 You' : '🤖 AI Assistant'}
        </div>
        <div>${content}</div>
    `;
    structureChatMessages.appendChild(messageDiv);
    structureChatMessages.scrollTop = structureChatMessages.scrollHeight;
}

// Approve structure and show subject selection
function approveStructure() {
    // Auto-save this course structure + exam format so they appear in saved lists next time
    if (courseStructure) {
        const courseName = courseStructure.Course || lessonCourse?.value?.trim() || 'Unknown';
        fetch('/api/courses/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ structure: courseStructure, course_name: courseName })
        }).then(() => loadSavedCourses()).catch(() => {});

        if (courseStructure.exam_format) {
            fetch('/api/exam-formats/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ exam_format: courseStructure.exam_format, course_name: courseName })
            }).then(() => loadSavedExamFormats()).catch(() => {});
        }
    }

    // Hide structure review section
    if (structureSection) {
        structureSection.style.display = 'none';
    }

    // Show generate section
    const generateSection = document.getElementById('generate-section');
    if (generateSection) {
        generateSection.style.display = 'block';
    }

    // Show saved exam patterns in the generate section
    loadSavedExamFormats();

    // Populate dropdowns for both lessons and QBank
    populateSubjects(courseStructure);

    // Scroll to generate section
    setTimeout(() => {
        if (generateSection) {
            generateSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }, 100);

    showToast('Structure approved! Select subjects and topics to generate lessons or questions.', 'success');
}

// ── Saved Courses ─────────────────────────────────────────────────────────────

async function loadSavedCourses() {
    const panel = document.getElementById('saved-courses-panel');
    const list  = document.getElementById('saved-courses-list');
    if (!panel || !list) return;
    try {
        const res = await fetch('/api/courses');
        if (!res.ok) return;
        const courses = await res.json();
        if (!courses.length) { panel.style.display = 'none'; return; }
        panel.style.display = 'block';
        list.innerHTML = courses.map(c => {
            const date = c.saved_at ? new Date(c.saved_at).toLocaleDateString('en-GB', { day:'numeric', month:'short', year:'2-digit' }) : '';
            return `
            <div class="saved-course-row" data-id="${escapeHtml(c.id)}" style="
                display:flex;align-items:center;gap:0.75rem;padding:0.6rem 0.9rem;
                background:var(--bg-secondary);border:1px solid var(--border);
                border-radius:8px;cursor:pointer;transition:border-color 0.15s,background 0.15s;">
                <span style="font-size:1.1rem;">🎓</span>
                <div style="flex:1;min-width:0;">
                    <div style="font-weight:600;font-size:0.95rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(c.course_name)}</div>
                    <div style="font-size:0.78rem;color:var(--text-muted);">${c.subject_count} subjects · ${c.topic_count} topics · ${date}</div>
                </div>
                <button type="button" class="delete-course-btn" data-id="${escapeHtml(c.id)}" title="Delete"
                    style="background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:1rem;padding:0.2rem 0.4rem;border-radius:4px;flex-shrink:0;line-height:1;">✕</button>
            </div>`;
        }).join('');

        // Single delegated listener on the container
        list.onclick = async (e) => {
            const deleteBtn = e.target.closest('.delete-course-btn');
            if (deleteBtn) {
                e.stopPropagation();
                e.preventDefault();
                const id = deleteBtn.dataset.id;
                try {
                    const dr = await fetch(`/api/courses/${id}`, { method: 'DELETE' });
                    if (!dr.ok) throw new Error(`Server returned ${dr.status}`);
                    showToast('Course deleted', 'success');
                } catch (err) {
                    showToast('Delete failed: ' + err.message, 'error');
                }
                loadSavedCourses();
                return;
            }
            const row = e.target.closest('.saved-course-row');
            if (row) {
                const res = await fetch(`/api/courses/${row.dataset.id}`);
                if (!res.ok) { showToast('Failed to load saved course', 'error'); return; }
                const data = await res.json();
                courseStructure = data.structure;
                const courseInput = document.getElementById('lesson-course');
                if (courseInput) courseInput.value = data.course_name || courseStructure.Course || '';
                displayStructureReview();
                showToast(`Loaded: ${data.course_name}`, 'success');
            }
        };

        list.onmouseover = (e) => {
            const row = e.target.closest('.saved-course-row');
            if (row) { row.style.borderColor = 'var(--primary)'; row.style.background = 'var(--bg)'; }
        };
        list.onmouseout = (e) => {
            const row = e.target.closest('.saved-course-row');
            if (row) { row.style.borderColor = 'var(--border)'; row.style.background = 'var(--bg-secondary)'; }
        };
    } catch (e) {
        panel.style.display = 'none';
    }
}

// Load saved courses on page init
loadSavedCourses();

// ── Saved Exam Formats ────────────────────────────────────────────────────────

function _updateFormatBadge(name) {
    const badge = document.getElementById('active-format-badge');
    if (!badge) return;
    if (name) { badge.textContent = name; badge.style.display = 'inline'; }
    else { badge.style.display = 'none'; }
}

async function _loadExamFormatIntoMockPanel(ef, courseName) {
    if (!ef) return;

    // Switch to mock exam mode immediately
    document.querySelector('.gen-mode-btn[data-mode="mock"]')?.click();

    const mockSpecsStatus = document.getElementById('mock-specs-status');
    const adjustSection   = document.getElementById('mock-adjust-section');
    const genMockBtn      = document.getElementById('generate-mock-btn');

    if (mockSpecsStatus) mockSpecsStatus.textContent = '⏳ Fetching exam pattern details…';
    if (mockSpecsPanel)  mockSpecsPanel.style.display = 'none';
    if (genMockBtn)      genMockBtn.disabled = true;

    const course   = courseName || courseStructure?.Course || '';
    const subjects = (courseStructure?.subjects || []).map(s => s.name);

    try {
        const res = await fetch('/api/mock-exam-specs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ course, subjects })
        });
        if (!res.ok) throw new Error(await res.text());
        mockExamSpecs = await res.json();
        renderMockSpecs(mockExamSpecs);
        if (mockSpecsStatus) mockSpecsStatus.textContent = `✓ Exam pattern loaded: ${course}`;
        if (adjustSection)   adjustSection.style.display = 'block';
        if (genMockBtn)      genMockBtn.disabled = false;
    } catch (err) {
        if (mockSpecsStatus) mockSpecsStatus.textContent = '✗ Could not fetch pattern details';
        showToast('Failed to load exam pattern details', 'error');
        console.error(err);
    }
}

async function loadSavedExamFormats() {
    const panel = document.getElementById('saved-formats-panel');
    const list  = document.getElementById('saved-formats-list');
    if (!panel || !list) return;
    try {
        const res = await fetch('/api/exam-formats');
        if (!res.ok) return;
        const formats = await res.json();
        const inGenerateSection = !!document.getElementById('generate-section')?.offsetParent;
        if (!formats.length) { if (!inGenerateSection) panel.style.display = 'none'; return; }
        panel.style.display = 'block';
        list.innerHTML = formats.map(f => {
            const date = f.saved_at ? new Date(f.saved_at).toLocaleDateString('en-GB', { day:'numeric', month:'short', year:'2-digit' }) : '';
            const imgBadge = f.image_pct ? ` · ${f.image_pct}% img` : '';
            const isActive = selectedExamFormat && selectedExamFormat._id === f.id;
            return `
            <div class="saved-format-row" data-id="${escapeHtml(f.id)}" style="
                display:flex;align-items:center;gap:0.75rem;padding:0.5rem 0.9rem;
                background:${isActive ? '#e8f4fd' : 'var(--bg-secondary)'};
                border:1.5px solid ${isActive ? 'var(--primary)' : 'var(--border)'};
                border-radius:8px;cursor:pointer;transition:border-color 0.15s,background 0.15s;">
                <span style="font-size:1rem;">📋</span>
                <div style="flex:1;min-width:0;">
                    <div style="font-weight:600;font-size:0.9rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(f.course_name)}</div>
                    <div style="font-size:0.75rem;color:var(--text-muted);">${escapeHtml(f.question_style || '')} · ${f.num_options} options${imgBadge} · ${date}</div>
                </div>
                ${isActive ? '<span style="font-size:0.75rem;color:var(--primary);font-weight:600;flex-shrink:0;">✓ active</span>' : ''}
                <button type="button" class="delete-format-btn" data-id="${escapeHtml(f.id)}" title="Delete"
                    style="background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:1rem;padding:0.2rem 0.4rem;border-radius:4px;flex-shrink:0;line-height:1;">✕</button>
            </div>`;
        }).join('');

        // Single delegated listener
        list.onclick = async (e) => {
            const deleteBtn = e.target.closest('.delete-format-btn');
            if (deleteBtn) {
                e.stopPropagation();
                e.preventDefault();
                const id = deleteBtn.dataset.id;
                try {
                    const dr = await fetch(`/api/exam-formats/${id}`, { method: 'DELETE' });
                    if (!dr.ok) throw new Error(`Server returned ${dr.status}`);
                    if (selectedExamFormat?._id === id) { selectedExamFormat = null; _updateFormatBadge(null); }
                    showToast('Exam pattern deleted', 'success');
                } catch (err) {
                    showToast('Delete failed: ' + err.message, 'error');
                }
                loadSavedExamFormats();
                return;
            }
            const row = e.target.closest('.saved-format-row');
            if (!row) return;
            const fmtId = row.dataset.id;
            // Toggle off if already active
            if (selectedExamFormat?._id === fmtId) {
                selectedExamFormat = null;
                _updateFormatBadge(null);
                showToast('Exam pattern deselected', 'info');
                loadSavedExamFormats();
                return;
            }
            const res = await fetch(`/api/exam-formats/${fmtId}`);
            if (!res.ok) { showToast('Failed to load exam pattern', 'error'); return; }
            const data = await res.json();
            selectedExamFormat = { ...data.exam_format, _id: fmtId };
            const courseInput = document.getElementById('lesson-course');
            if (courseInput && !courseInput.value.trim()) courseInput.value = data.course_name || '';
            _updateFormatBadge(data.course_name);
            _loadExamFormatIntoMockPanel(data.exam_format, data.course_name);
            showToast(`Exam pattern selected: ${data.course_name}`, 'success');
            loadSavedExamFormats();
        };
    } catch (e) {
        panel.style.display = 'none';
    }
}

// loadSavedExamFormats() is called from approveStructure() when Step 3 becomes visible

// Question Bank - Generate Subjects button (removed from UI, kept for compatibility)
if (qbankGenerateSubjectsBtn) {
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

        courseStructure = await response.json();

        // Debug logging
        console.log('📥 Received course structure:', courseStructure);
        console.log('📊 Number of subjects received:', courseStructure.subjects?.length || 0);
        console.log('📋 exam_format in structure:', courseStructure.exam_format);

        if (courseStructure.subjects) {
            console.log('📚 Subject names:', courseStructure.subjects.map(s => s.name));
        }

        // Show review panel instead of directly populating
        displayStructureReview();
        qbankStructureStatus.textContent = `✓ Loaded structure for ${course}`;
        qbankStructureStatus.style.color = 'var(--success)';
        showToast('Course structure generated - please review', 'success');
    } catch (error) {
        showToast(error.message || 'Error generating subjects', 'error');
        qbankStructureStatus.textContent = '✗ Failed to generate structure';
        qbankStructureStatus.style.color = 'var(--error)';
    } finally {
        qbankGenerateSubjectsBtn.disabled = false;
        qbankGenerateSubjectsBtn.textContent = '🤖 Generate Subjects';
    }
    });
}

// Question Bank - Upload JSON button (removed from UI, kept for compatibility)
if (qbankUploadStructureBtn) {
    qbankUploadStructureBtn.addEventListener('click', () => {
        qbankJsonFile.click();
    });
}

if (qbankJsonFile) {
    qbankJsonFile.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = async (event) => {
        try {
            const raw = JSON.parse(event.target.result);
            const uploadedStructure = normalizeStructureJson(raw, '');

            // If exam_format is missing, research it based on course name
            if (!uploadedStructure.exam_format) {
                const courseName = uploadedStructure.Course || 'Unknown';

                if (courseName && courseName !== 'Unknown') {
                    showToast('Researching exam format...', 'info');

                    try {
                        const response = await fetch('/api/generate-subjects', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ course: courseName })
                        });

                        if (response.ok) {
                            const researchData = await response.json();
                            // Merge exam_format from research into uploaded structure
                            uploadedStructure.exam_format = researchData.exam_format;
                            uploadedStructure.Course = courseName;
                            console.log('Added exam_format to uploaded structure:', uploadedStructure.exam_format);
                        }
                    } catch (err) {
                        console.error('Failed to research exam format:', err);
                        showToast('Warning: Could not research exam format, using defaults', 'warning');
                    }
                }
            }

            courseStructure = uploadedStructure;
            displayStructureReview();
            qbankStructureStatus.textContent = `✓ Loaded structure from ${file.name}`;
            qbankStructureStatus.style.color = 'var(--success)';
            showToast('Course structure uploaded - please review', 'success');
        } catch (error) {
            showToast('Invalid JSON file', 'error');
            qbankStructureStatus.textContent = '✗ Failed to parse JSON';
            qbankStructureStatus.style.color = 'var(--error)';
        }
    };
    reader.readAsText(file);
    });
}

// Populate subjects dropdown from loaded structure
function populateQBankSubjects() {
    console.log('🔄 populateQBankSubjects() called');
    console.log('courseStructure:', courseStructure);

    if (!courseStructure) {
        console.error('❌ courseStructure is null or undefined');
        return;
    }

    if (!courseStructure.subjects) {
        console.error('❌ courseStructure.subjects is null or undefined');
        console.log('Structure keys:', Object.keys(courseStructure));
        return;
    }

    console.log(`✅ Populating ${courseStructure.subjects.length} subjects into dropdown`);

    qbankSubjectsContainer.style.display = 'block';
    subjectSelect.innerHTML = '<option value="">Select a subject...</option>';
    topicsSelect.innerHTML = '';

    courseStructure.subjects.forEach((subject, idx) => {
        console.log(`  Adding subject ${idx}: ${subject.name}`);
        const option = document.createElement('option');
        option.value = idx;
        option.textContent = subject.name;
        subjectSelect.appendChild(option);
    });

    console.log(`✅ Dropdown populated with ${subjectSelect.options.length - 1} subjects`);
}

// Update image percentage info based on selected subject
function updateImagePercentageInfo(subjectName) {
    const imagePercentageInfo = document.getElementById('image-percentage-info');
    if (!imagePercentageInfo || !courseStructure) return;

    const examFormat = courseStructure.exam_format;
    if (!examFormat) return;

    const imageBySubject = examFormat.image_percentage_by_subject || {};
    // Handle both old format (nested) and new format (at top level)
    const overallPct = examFormat.question_format?.image_questions_percentage ||
                       examFormat.image_questions_percentage || 0;

    // Try to find subject-specific percentage
    let subjectPct = overallPct;
    for (const [subjName, pct] of Object.entries(imageBySubject)) {
        if (subjName.toLowerCase().includes(subjectName.toLowerCase()) ||
            subjectName.toLowerCase().includes(subjName.toLowerCase())) {
            subjectPct = pct;
            break;
        }
    }

    const courseName = courseStructure.Course || 'this exam';
    imagePercentageInfo.textContent = `Includes ~${subjectPct}% image-based questions (typical for ${subjectName} in ${courseName}). Images fetched from NIH/Wikimedia or generated with AI.`;
}

// Subject change handler - populate topics from structure
if (subjectSelect) {
    subjectSelect.addEventListener('change', () => {
        const subjectIdx = subjectSelect.value;
        if (topicsSelect) topicsSelect.innerHTML = '';
        if (generateBtn) generateBtn.disabled = true;

        if (!subjectIdx || !courseStructure) return;

        const subject = courseStructure.subjects[subjectIdx];
        if (!subject || !subject.topics) return;

        subject.topics.forEach((topic, idx) => {
            const option = document.createElement('option');
            option.value = topic.name;
            option.textContent = topic.name;
            if (topicsSelect) topicsSelect.appendChild(option);
        });

        // Update image percentage info for this subject
        updateImagePercentageInfo(subject.name);

        updateBloomDistribution();
    });
}

// Topics change handler (multi-select)
if (topicsSelect) {
    topicsSelect.addEventListener('change', () => {
        const selectedTopics = Array.from(topicsSelect.selectedOptions).map(opt => opt.value);
        const hasSelection = selectedTopics.length > 0;

        // Enable/disable both generate buttons
        if (generateBtn) generateBtn.disabled = !hasSelection;
        if (generateLessonsBtn) generateLessonsBtn.disabled = !hasSelection;

        updateTotalCount();
        updateBloomDistribution();
    });
}

function updateTotalCount() {
    if (!totalQuestionsInfo) return;
    const num = numQuestionsInput ? parseInt(numQuestionsInput.value) : 10;
    const selected = topicsSelect ? Array.from(topicsSelect.selectedOptions).length : 0;
    if (selected > 0) {
        totalQuestionsInfo.innerHTML = `<strong>Total: ${num * selected} questions</strong> (${num} per topic × ${selected} topic${selected !== 1 ? 's' : ''})`;
    } else {
        totalQuestionsInfo.innerHTML = '';
    }
}

// ─── Shared QBank generate helper ────────────────────────────────────────────
async function runQBankGenerate(numQuestionsPerTopic, isAppend) {
    if (!courseStructure) {
        showToast('Please generate course structure first', 'error');
        return;
    }
    const course = courseStructure.Course || 'Unknown Course';
    const generateAll = generateAllCheckbox?.checked || false;

    // Auto-enable images based on exam format
    const examImagePct = courseStructure?.exam_format?.question_format?.image_questions_percentage
        ?? courseStructure?.exam_format?.image_questions_percentage
        ?? 0;
    const includeImages = examImagePct > 0;

    if (generateAll) {
        // Generate for every subject and all its topics
        if (!courseStructure.subjects?.length) {
            showToast('No subjects in course structure', 'error');
            return;
        }
        if (generateBtn) generateBtn.disabled = true;
        loading.style.display = 'flex';
        document.getElementById('loading-message').textContent = 'Generating questions for all subjects…';

        let allQuestions = isAppend ? [...generatedQuestions] : [];
        let totalGenerated = 0;
        try {
            for (const subjectObj of courseStructure.subjects) {
                const allT = (subjectObj.topics || []).filter(t => t.name);
                const hyT = allT.filter(t => t.high_yield);
                const topics = (hyT.length > 0 ? hyT : allT).map(t => t.name);
                if (!topics.length) continue;
                document.getElementById('loading-message').textContent =
                    `Generating: ${subjectObj.name} (${topics.length} topics)…`;
                const response = await fetch('/api/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        course, subject: subjectObj.name, topics,
                        num_questions: numQuestionsPerTopic,
                        include_images: includeImages,
                        exam_format: selectedExamFormat || courseStructure?.exam_format,
                        existing_questions: allQuestions
                    })
                });
                const data = await response.json();
                if (data.error) { showToast(`Error on ${subjectObj.name}: ${data.error}`, 'error'); continue; }
                allQuestions = [...allQuestions, ...data.questions];
                totalGenerated += data.count;
            }
            generatedQuestions = allQuestions;
            displayResults(allQuestions, course);
            showResultTab('qbank');
            showToast(`Generated ${totalGenerated} questions across all subjects`, 'success');
            lastSaveMeta = { course, subject: 'All Subjects', topics: courseStructure.subjects.map(s => s.name) };
            currentQBankSessionId = null;
            lastRegenerateFn = () => runQBankGenerate(numQuestionsPerTopic, false);
        } catch (error) {
            showToast(error.message || 'Error generating questions', 'error');
        } finally {
            loading.style.display = 'none';
            if (generateBtn) generateBtn.disabled = false;
        }
        return;
    }

    const subjectIdx = subjectSelect ? subjectSelect.value : '';
    const topics = topicsSelect ? Array.from(topicsSelect.selectedOptions).map(opt => opt.value) : [];

    if (!subjectIdx) { showToast('Please select a subject', 'error'); return; }
    if (topics.length === 0) { showToast('Please select at least one topic', 'error'); return; }

    const subject = courseStructure.subjects[subjectIdx].name;

    // Disable all generate buttons
    if (generateBtn) generateBtn.disabled = true;
    document.querySelectorAll('.btn-more-questions').forEach(b => b.disabled = true);
    if (isAppend) {
        const statusEl = document.getElementById('generate-more-status');
        if (statusEl) statusEl.textContent = `⏳ Generating ${numQuestionsPerTopic} more per topic…`;
    }
    loading.style.display = 'flex';
    document.getElementById('loading-message').textContent =
        isAppend ? `Adding ${numQuestionsPerTopic * topics.length} more questions…` : 'Generating questions…';

    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                course,
                subject,
                topics,
                num_questions: numQuestionsPerTopic,
                include_images: includeImages,
                exam_format: selectedExamFormat || courseStructure?.exam_format,
                existing_questions: isAppend ? generatedQuestions : [],
                reference_examples: getPyqExamples(subject, 8),
            })
        });

        const data = await response.json();
        if (data.error) throw new Error(data.error);

        if (isAppend) {
            generatedQuestions = [...generatedQuestions, ...data.questions];
            appendResults(data.questions, course, data.image_stats);
            showToast(`Added ${data.count} questions — total: ${generatedQuestions.length}`, 'success');
            const statusEl = document.getElementById('generate-more-status');
            if (statusEl) statusEl.textContent = `✓ Added ${data.count} questions. Total: ${generatedQuestions.length}`;
        } else {
            generatedQuestions = data.questions;
            displayResults(data.questions, course, data.image_stats);
            showResultTab('qbank');
            showToast(`Generated ${data.count} questions across ${topics.length} topic(s)`, 'success');
            lastSaveMeta = { course, subject, topics };
            currentQBankSessionId = null;
            lastRegenerateFn = () => runQBankGenerate(numQuestionsPerTopic * topics.length, false);
        }


        // Show "generate more" bar
        const moreBar = document.getElementById('generate-more-bar');
        if (moreBar) moreBar.style.display = 'block';

    } catch (error) {
        showToast(error.message || 'Error generating questions', 'error');
        const statusEl = document.getElementById('generate-more-status');
        if (statusEl) statusEl.textContent = '';
    } finally {
        loading.style.display = 'none';
        if (generateBtn) generateBtn.disabled = false;
        document.querySelectorAll('.btn-more-questions').forEach(b => b.disabled = false);
    }
}

// Generate button — reads count from dropdown
const numQuestionsSelect = document.getElementById('num-questions-select');

function getNumQuestions() {
    return numQuestionsSelect ? parseInt(numQuestionsSelect.value) || 20 : 20;
}

function updateGenerateBtnLabel() {
    if (!generateBtn) return;
    const n = getNumQuestions();
    const allChecked = document.getElementById('generate-all-checkbox')?.checked;
    generateBtn.textContent = allChecked
        ? `📝 Generate ${n} Qs / Topic (All)`
        : `📝 Generate ${n} Questions`;
}

if (numQuestionsSelect) {
    numQuestionsSelect.addEventListener('change', updateGenerateBtnLabel);
}

if (generateBtn) {
    generateBtn.addEventListener('click', () => runQBankGenerate(getNumQuestions(), false));
}

// Generate More buttons (+20, +40, +60, +80)
document.querySelectorAll('.btn-more-questions').forEach(btn => {
    btn.addEventListener('click', () => {
        const count = parseInt(btn.dataset.count);
        runQBankGenerate(count, true);
    });
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
                <div class="label">Image-Based</div>
                <div class="value">${imageStats.image_based_count} (${imageStats.image_percentage})</div>
            </div>
            <div class="stat-item">
                <div class="label">Images Found</div>
                <div class="value">${imageStats.images_found}/${imageStats.image_based_count}</div>
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
    
    questionsContainer.innerHTML = questions.map((q, idx) => renderQuestionCard(q, idx)).join('');
    resultsSection.scrollIntoView({ behavior: 'smooth' });

    // Enable Save / Regenerate buttons now that results exist
    const saveQbankBtn = document.getElementById('save-qbank-btn');
    const regenQbankBtn = document.getElementById('regenerate-qbank-btn');
    if (saveQbankBtn) {
        saveQbankBtn.disabled = false;
        saveQbankBtn.textContent = currentQBankSessionId ? '💾 Update History' : '💾 Save to History';
    }
    if (regenQbankBtn) regenQbankBtn.disabled = false;
}

function renderQuestionCard(q, idx) {
    const difficultyLabels = { 1: 'Medium', 2: 'Hard', 3: 'Very Hard', 'medium': 'Medium', 'easy': 'Medium', 'hard': 'Hard', 'very hard': 'Very Hard' };
    const hasImage = q.image_url || q.image_description;
    const imageHtml = q.image_url ? `
        <div class="question-image">
            <img src="${q.image_url}" alt="${q.image_description || 'Medical image'}" loading="lazy"
                 onerror="this.onerror=null; this.style.display='none'; this.nextElementSibling.style.display='block';"
                 onload="if(this.naturalWidth<10||this.naturalHeight<10){this.onerror=null;this.style.display='none';this.nextElementSibling.style.display='block';}">
            <div class="image-fallback" style="display:none;">
                <p class="image-placeholder">${q.image_type ? `[${q.image_type}]` : '[Image]'} ${q.image_description || ''}</p>
            </div>
            ${q.image_source ? `<small class="image-source">Source: ${q.image_source}</small>` : ''}
        </div>
    ` : (q.is_image_question ? `
        <div class="question-image" style="border:2px dashed #dc3545;border-radius:8px;padding:1rem;background:#fff5f5;">
            <div style="text-align:center;color:#dc3545;font-weight:600;margin-bottom:0.4rem;">⚠️ Image required but not found</div>
            <p style="font-size:0.85rem;color:#555;text-align:center;margin:0;">
                <strong>${q.image_type || 'Image'}:</strong> ${q.image_description || ''}
            </p>
            <p style="font-size:0.78rem;color:#dc3545;text-align:center;margin:0.4rem 0 0;">This question needs revision — it was written assuming an image would be present.</p>
        </div>
    ` : '');

    const debugBtn = hasImage ? `
        <button onclick="showImageDebugPanel(${idx + 1}, this, 'qbank')"
            title="View image search debug — see queries, candidates and selected image"
            style="background:none;border:1.5px solid #7b5ea7;color:#7b5ea7;border-radius:6px;padding:2px 9px;font-size:0.78rem;cursor:pointer;font-weight:600;line-height:1.5;white-space:nowrap;"
            data-debug-loading="false">🔍 Image Search</button>` : '';

    return `
        <div class="question-card" data-q-index="${idx + 1}">
            <div class="question-header">
                <span class="question-number">Q${idx + 1}</span>
                <div class="question-tags">
                    <span class="tag tag-bloom">Bloom's L${q.blooms_level}</span>
                    <span class="tag tag-difficulty">${difficultyLabels[q.difficulty]}</span>
                    ${hasImage ? '<span class="tag tag-image">Image</span>' : ''}
                    ${(q.tags || []).map(tag => `<span class="tag tag-exam">${tag}</span>`).join('')}
                    ${debugBtn}
                </div>
            </div>
            ${imageHtml}
            <p class="question-text">${q.question}</p>
            <ul class="options-list">
                ${q.options.map(opt => `<li class="${opt === q.correct_option ? 'correct' : ''}">${opt}</li>`).join('')}
            </ul>
            <div class="explanation"><strong>Explanation:</strong> ${q.explanation}</div>
        </div>
    `;
}

// Append new questions to existing results without re-rendering everything
function appendResults(newQuestions, course, imageStats = null) {
    const difficultyLabels = { 1: 'Medium', 2: 'Hard', 3: 'Very Hard', 'medium': 'Medium', 'easy': 'Medium', 'hard': 'Hard', 'very hard': 'Very Hard' };
    const startIdx = generatedQuestions.length - newQuestions.length; // offset into full array

    // Add a separator
    const separator = document.createElement('div');
    separator.style.cssText = 'margin: 2rem 0 1rem; padding: 0.5rem 1rem; background: var(--primary); color: white; border-radius: 6px; font-weight: 600; font-size: 0.9rem;';
    separator.textContent = `➕ ${newQuestions.length} new questions added (Q${startIdx + 1}–Q${generatedQuestions.length})`;
    questionsContainer.appendChild(separator);

    newQuestions.forEach((q, i) => {
        const idx = startIdx + i;
        const wrapper = document.createElement('div');
        wrapper.innerHTML = renderQuestionCard(q, idx);
        questionsContainer.appendChild(wrapper.firstElementChild);
    });

    // Update stats header
    updateQBankStats(generatedQuestions);

    separator.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function updateQBankStats(questions) {
    if (!statsContainer) return;
    const bloomCounts = {};
    const difficultyCounts = { 1: 0, 2: 0, 3: 0 };
    questions.forEach(q => {
        bloomCounts[q.blooms_level] = (bloomCounts[q.blooms_level] || 0) + 1;
        difficultyCounts[q.difficulty] = (difficultyCounts[q.difficulty] || 0) + 1;
    });
    const difficultyLabels = { 1: 'Medium', 2: 'Hard', 3: 'Very Hard' };
    const course = courseStructure?.Course || '';
    statsContainer.innerHTML = `
        <div class="stat-item"><div class="label">Total Questions</div><div class="value">${questions.length}</div></div>
        <div class="stat-item"><div class="label">Course</div><div class="value">${course}</div></div>
        ${Object.entries(bloomCounts).map(([l, c]) => `
            <div class="stat-item"><div class="label">Bloom's L${l}</div><div class="value">${c}</div></div>
        `).join('')}
        ${Object.entries(difficultyCounts).filter(([,c]) => c > 0).map(([d, c]) => `
            <div class="stat-item"><div class="label">${difficultyLabels[d]}</div><div class="value">${c}</div></div>
        `).join('')}
    `;
}

// Download button
if (downloadBtn) {
    downloadBtn.addEventListener('click', async () => {
    if (!generatedQuestions.length) return;

    showToast('Embedding images, please wait…', 'info');

    // Deep-copy questions and replace image_url with base64 data URIs
    const questionsWithEmbeddedImages = await Promise.all(generatedQuestions.map(async (q) => {
        const qCopy = { ...q };
        if (qCopy.image_url && qCopy.image_url.startsWith('/')) {
            const b64 = await urlToBase64(qCopy.image_url);
            if (b64) qCopy.image_url = b64;
        }
        return qCopy;
    }));

    const course = courseStructure?.Course || 'questions';
    const blob = new Blob([JSON.stringify(questionsWithEmbeddedImages, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `qbank_${course.replace(/\s+/g, '_')}_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);

    showToast('Downloaded with embedded images!', 'success');
    });
}

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
if (copyBtn) {
    copyBtn.addEventListener('click', async () => {
    if (!generatedQuestions.length) return;

    try {
        showToast('Generating markdown with embedded images...', 'info');

        const course = courseStructure?.Course || 'Unknown Course';
        const subjectIdx = subjectSelect.value;
        const subject = courseStructure && subjectIdx ? courseStructure.subjects[subjectIdx].name : 'Unknown Subject';
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
}

// ── Save to History button ───────────────────────────────────────────────────
const saveQbankBtn = document.getElementById('save-qbank-btn');
if (saveQbankBtn) {
    saveQbankBtn.addEventListener('click', async () => {
        if (!generatedQuestions.length) return;
        const meta = lastSaveMeta || { course: courseStructure?.Course || 'Unknown', subject: '', topics: [] };
        const isUpdate = !!currentQBankSessionId;
        saveQbankBtn.disabled = true;
        saveQbankBtn.textContent = isUpdate ? 'Updating…' : 'Saving…';
        try {
            const res = await fetch('/api/sessions/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    questions: generatedQuestions,
                    course: meta.course,
                    subject: meta.subject,
                    topics: meta.topics,
                    session_id: currentQBankSessionId || undefined,
                })
            });
            const data = await res.json();
            if (data.session_id) {
                currentQBankSessionId = data.session_id;
                showToast(isUpdate ? 'History updated ✓' : 'Saved to History ✓', 'success');
                saveQbankBtn.textContent = '✓ Saved';
                saveQbankBtn.disabled = false;
            } else {
                throw new Error(data.error || 'Save failed');
            }
        } catch (err) {
            showToast(err.message || 'Save failed', 'error');
            saveQbankBtn.disabled = false;
            saveQbankBtn.textContent = currentQBankSessionId ? '💾 Update History' : '💾 Save to History';
        }
    });
}

// ── Regenerate button ────────────────────────────────────────────────────────
const regenerateQbankBtn = document.getElementById('regenerate-qbank-btn');
if (regenerateQbankBtn) {
    regenerateQbankBtn.addEventListener('click', () => {
        if (typeof lastRegenerateFn === 'function') {
            // Reset Save button so user can save the new result
            if (saveQbankBtn) {
                saveQbankBtn.disabled = true;
                saveQbankBtn.textContent = '💾 Save to History';
            }
            lastRegenerateFn();
        } else {
            showToast('No previous generation to repeat', 'error');
        }
    });
}

// ── Lessons: Save to History button ─────────────────────────────────────────
const saveLessonsBtn = document.getElementById('save-lessons-btn');
if (saveLessonsBtn) {
    saveLessonsBtn.addEventListener('click', async () => {
        if (!lastLessonsSaveMeta) return;
        const isUpdate = !!currentLessonsSessionId;
        saveLessonsBtn.disabled = true;
        saveLessonsBtn.textContent = isUpdate ? 'Updating…' : 'Saving…';
        try {
            const res = await fetch('/api/sessions/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    type: 'lessons',
                    lessons_data: lastLessonsSaveMeta.lessons_data,
                    course: lastLessonsSaveMeta.course,
                    subject: lastLessonsSaveMeta.subject,
                    session_id: currentLessonsSessionId || undefined,
                })
            });
            const data = await res.json();
            if (data.session_id) {
                currentLessonsSessionId = data.session_id;
                showToast(isUpdate ? 'History updated ✓' : 'Lessons saved to History ✓', 'success');
                saveLessonsBtn.textContent = '✓ Saved';
                saveLessonsBtn.disabled = false;
            } else {
                throw new Error(data.error || 'Save failed');
            }
        } catch (err) {
            showToast(err.message || 'Save failed', 'error');
            saveLessonsBtn.disabled = false;
            saveLessonsBtn.textContent = currentLessonsSessionId ? '💾 Update History' : '💾 Save to History';
        }
    });
}

// ── Lessons: Regenerate button ───────────────────────────────────────────────
const regenerateLessonsBtn = document.getElementById('regenerate-lessons-btn');
if (regenerateLessonsBtn) {
    regenerateLessonsBtn.addEventListener('click', () => {
        if (typeof lastLessonsRegenerateFn === 'function') {
            if (saveLessonsBtn) {
                saveLessonsBtn.disabled = true;
                saveLessonsBtn.textContent = '💾 Save to History';
            }
            lastLessonsRegenerateFn();
        } else {
            showToast('No previous lesson generation to repeat', 'error');
        }
    });
}

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

        // Check if switching to QBank tab - update status based on structure
        if (tabName === 'generate') {
            const qbankStructureInfo = document.getElementById('qbank-structure-info');
            if (courseStructure && courseStructure.subjects && courseStructure.subjects.length > 0) {
                // Structure exists - hide info box, show subjects container, populate dropdowns
                if (qbankStructureInfo) qbankStructureInfo.style.display = 'none';
                populateQBankSubjects();
                qbankStructureStatus.textContent = `✓ Structure loaded: ${courseStructure.Course || 'Unknown'} (${courseStructure.subjects.length} subjects)`;
                qbankStructureStatus.style.color = 'var(--success)';
            } else {
                // No structure - show info box
                if (qbankStructureInfo) qbankStructureInfo.style.display = 'block';
                qbankSubjectsContainer.style.display = 'none';
                qbankStructureStatus.textContent = 'No structure loaded - generate one in the Lessons tab first';
                qbankStructureStatus.style.color = 'var(--error)';
            }
        }

        // Show/hide results based on active tab (don't hide all - keep each tab's results)
        // This allows users to iterate on generation separately
        if (tabName === 'generate') {
            // QBank tab - show QBank results if they exist, hide others
            if (resultsSection) resultsSection.style.display = resultsSection.innerHTML.trim() ? 'block' : 'none';
            if (document.getElementById('lessons-result')) document.getElementById('lessons-result').style.display = 'none';
            if (document.getElementById('image-result')) document.getElementById('image-result').style.display = 'none';
        } else if (tabName === 'lessons') {
            // Lessons tab - show lesson results if they exist, hide others
            if (document.getElementById('lessons-result')) {
                const lessonsResult = document.getElementById('lessons-result');
                lessonsResult.style.display = lessonsResult.innerHTML.trim() ? 'block' : 'none';
            }
            if (resultsSection) resultsSection.style.display = 'none';
            if (document.getElementById('image-result')) document.getElementById('image-result').style.display = 'none';
        } else if (tabName === 'history') {
            if (resultsSection) resultsSection.style.display = 'none';
            if (document.getElementById('lessons-result')) document.getElementById('lessons-result').style.display = 'none';
            if (document.getElementById('image-result')) document.getElementById('image-result').style.display = 'none';
            loadSessionHistory();
        } else if (tabName === 'utility') {
            // Utility tab - show image results if they exist, hide others
            if (document.getElementById('image-result')) {
                const imageResult = document.getElementById('image-result');
                imageResult.style.display = imageResult.innerHTML.trim() ? 'block' : 'none';
            }
            if (resultsSection) resultsSection.style.display = 'none';
            if (document.getElementById('lessons-result')) document.getElementById('lessons-result').style.display = 'none';
        }
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
if (uploadJsonBtn) {
    uploadJsonBtn.addEventListener('click', () => {
        if (jsonFileInput) jsonFileInput.click();
    });
}

// File selection handler
if (jsonFileInput) {
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
}

// Add image button handler
if (addImageBtn) {
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

        // Add indicator badge to Utility tab
        const utilityTab = document.querySelector('[data-tab="utility"]');
        if (utilityTab && !utilityTab.textContent.includes('●')) {
            utilityTab.textContent = '● ' + utilityTab.textContent.trim();
            utilityTab.style.color = 'var(--success)';
        }

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
}

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
if (downloadImageResultBtn) {
    downloadImageResultBtn.addEventListener('click', async () => {
    if (!imageResultData) return;

    showToast('Embedding images, please wait…', 'info');

    // Clean up internal metadata fields and embed images
    const cleanedData = await Promise.all(imageResultData.map(async q => {
        const cleaned = { ...q };
        delete cleaned.image_status;
        delete cleaned.image_error;
        delete cleaned.image_reasoning;
        delete cleaned.key_finding;
        delete cleaned.image_search_terms;
        delete cleaned.image_title;
        if (cleaned.image_url && cleaned.image_url.startsWith('/')) {
            const b64 = await urlToBase64(cleaned.image_url);
            if (b64) cleaned.image_url = b64;
        }
        return cleaned;
    }));

    const blob = new Blob([JSON.stringify(cleanedData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `questions_with_images_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);

    showToast('Downloaded with embedded images!', 'success');
    });
}

// Download as Markdown
if (downloadImageMdBtn) {
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
}

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
// courseStructure is declared globally at the top and shared between tabs

// Debug: Check if button exists
console.log('🔍 Lessons button element:', generateSubjectsBtn);
console.log('🔍 Lessons course input:', lessonCourse);
if (!generateSubjectsBtn) {
    console.error('❌ Generate Subjects button NOT FOUND in DOM!');
} else {
    console.log('✅ Generate Subjects button FOUND! Attaching event listener...');
}

// Generate Subjects button handler
if (generateSubjectsBtn) {
    console.log('📌 About to attach click event listener to generateSubjectsBtn');
    generateSubjectsBtn.addEventListener('click', async () => {
    console.log('🎯 BUTTON CLICKED! Starting handler...');
    const course = lessonCourse.value.trim();
    if (!course) {
        showToast('Please enter a course/exam name', 'error');
        lessonCourse.focus();
        return;
    }

    structureStatus.textContent = uploadedStructureData
        ? '⏳ Using uploaded structure, fetching question format from web...'
        : selectedExamFormat
        ? '⏳ Generating course structure (using saved exam pattern — skipping format analysis)...'
        : '⏳ Searching web for official curriculum and question format...';
    generateSubjectsBtn.disabled = true;

    try {
        // Call backend to generate comprehensive structure
        console.log('🎓 Lessons: Calling API to generate structure for:', course);

        const payload = { course };
        if (uploadedStructureData) {
            payload.uploaded_structure = uploadedStructureData;
        }
        if (selectedExamFormat) {
            payload.exam_format = selectedExamFormat;
        }
        const response = await fetch('/api/generate-subjects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            throw new Error('Failed to generate course structure');
        }

        courseStructure = await response.json();

        console.log('🎓 Lessons: Received structure:', courseStructure);
        console.log('🎓 Lessons: Number of subjects:', courseStructure.subjects?.length || 0);
        if (courseStructure.subjects) {
            console.log('🎓 Lessons: Subject names:', courseStructure.subjects.map(s => s.name));
        }

        // Show structure review panel
        displayStructureReview();

        structureStatus.textContent = `✓ Generated ${courseStructure.subjects.length} subjects`;
        showToast('Structure generated! Please review and approve.', 'success');
    } catch (error) {
        console.error('🎓 Lessons: Error generating structure:', error);
        structureStatus.textContent = '✗ Failed to generate structure';
        showToast('Failed to generate structure', 'error');
    } finally {
        generateSubjectsBtn.disabled = false;
    }
    });
} else {
    console.error('❌ Cannot attach event listener - button not found');
}

// Upload JSON button handler
if (uploadStructureBtn) {
    uploadStructureBtn.addEventListener('click', () => {
        lessonJsonFile.click();
    });
}

// Normalize any uploaded JSON into the expected { Course, subjects, exam_format } shape
function normalizeStructureJson(json, fallbackCourseName) {
    // Helper: case-insensitive key lookup on a plain object
    function getKey(obj, ...keys) {
        for (const k of keys) {
            if (obj[k] !== undefined) return obj[k];
            // Try capitalized variant
            const cap = k.charAt(0).toUpperCase() + k.slice(1);
            if (obj[cap] !== undefined) return obj[cap];
        }
        return undefined;
    }

    function normalizeTopic(t) {
        if (typeof t === 'string') return { name: t, chapters: [] };
        const name = getKey(t, 'name', 'topic', 'Topic') || 'Unknown';
        const chapters = (getKey(t, 'chapters', 'Chapters') || []).map(c =>
            typeof c === 'string' ? c : (getKey(c, 'name', 'chapter') || String(c))
        );
        return { name, chapters, high_yield: t.high_yield || t.High_yield || false };
    }

    function normalizeSubject(s) {
        const name = getKey(s, 'name', 'subject', 'Subject') || 'Unknown';
        const description = getKey(s, 'description', 'Description') || '';
        const rawTopics = getKey(s, 'topics', 'Topics') || [];
        return { name, description, topics: rawTopics.map(normalizeTopic) };
    }

    // Format 1: flat array of subjects
    if (Array.isArray(json)) {
        return {
            Course: fallbackCourseName || '',
            subjects: json.map(normalizeSubject),
            exam_format: null
        };
    }

    // Format 2: object with a subjects/Subjects array
    const rawSubjects = getKey(json, 'subjects', 'Subjects');
    if (rawSubjects && Array.isArray(rawSubjects) && rawSubjects.length > 0) {
        return {
            ...json,
            Course: json.Course || json.course || fallbackCourseName || '',
            subjects: rawSubjects.map(normalizeSubject)
        };
    }

    // Format 3: unrecognized — pass through with Course filled in
    return {
        ...json,
        Course: json.Course || json.course || fallbackCourseName || ''
    };
}

// File selection handler for lessons
if (lessonJsonFile) {
    lessonJsonFile.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    try {
        const text = await file.text();
        const raw = JSON.parse(text);
        const fallbackName = lessonCourse ? lessonCourse.value.trim() : '';
        uploadedStructureData = normalizeStructureJson(raw, fallbackName);

        // Auto-fill course name from JSON if not already typed
        if (uploadedStructureData.Course && lessonCourse && !lessonCourse.value.trim()) {
            lessonCourse.value = uploadedStructureData.Course;
        }

        // Show the attached file indicator
        const infoDiv = document.getElementById('uploaded-structure-info');
        const nameSpan = document.getElementById('uploaded-filename');
        if (infoDiv) infoDiv.style.display = 'flex';
        if (nameSpan) nameSpan.textContent = `${file.name} (${uploadedStructureData.subjects?.length || 0} subjects)`;

        showToast(`Structure attached: ${file.name}`, 'success');
    } catch (error) {
        console.error('Error parsing JSON:', error);
        showToast('Invalid JSON file', 'error');
        uploadedStructureData = null;
    }
    // Reset file input so same file can be re-selected
    lessonJsonFile.value = '';
    });
}

// Clear attached structure
const clearStructureBtn = document.getElementById('clear-structure-btn');
if (clearStructureBtn) {
    clearStructureBtn.addEventListener('click', () => {
        uploadedStructureData = null;
        const infoDiv = document.getElementById('uploaded-structure-info');
        if (infoDiv) infoDiv.style.display = 'none';
    });
}

function populateSubjects(structure) {
    if (!structure || !structure.subjects) return;

    // Populate lesson subject select
    if (lessonSubjectSelect) {
        lessonSubjectSelect.innerHTML = '<option value="">Select a subject...</option>';
        structure.subjects.forEach((subject, idx) => {
            const option = document.createElement('option');
            option.value = idx;
            option.textContent = subject.name;
            lessonSubjectSelect.appendChild(option);
        });
    }

    // Populate QBank subject select (same dropdown in unified UI)
    if (subjectSelect) {
        subjectSelect.innerHTML = '<option value="">Select a subject...</option>';
        structure.subjects.forEach((subject, idx) => {
            const option = document.createElement('option');
            option.value = idx;
            option.textContent = subject.name;
            subjectSelect.appendChild(option);
        });
    }

    // Clear topics and chapters
    if (lessonTopicsSelect) lessonTopicsSelect.innerHTML = '';
    if (lessonChaptersSelect) lessonChaptersSelect.innerHTML = '';
    if (topicsSelect) topicsSelect.innerHTML = '';

    // Show subjects container
    if (lessonSubjectsContainer) lessonSubjectsContainer.style.display = 'block';

    // Initially buttons are disabled - they get enabled when user selects topics
    // Don't enable them here, let the topic selection handler enable them
    console.log('✓ Subjects populated - select topics to enable generate buttons');
    console.log('Course structure loaded:', structure);
}

function updateTopics() {
    if (!courseStructure || !courseStructure.subjects) return;

    const selectedSubjectIdx = lessonSubjectSelect?.value;
    if (lessonTopicsSelect) lessonTopicsSelect.innerHTML = '';
    if (lessonChaptersSelect) lessonChaptersSelect.innerHTML = '';

    if (!selectedSubjectIdx || selectedSubjectIdx === '') return;

    const subject = courseStructure.subjects[selectedSubjectIdx];
    if (!subject || !subject.topics) return;

    subject.topics.forEach((topic, idx) => {
        const option = document.createElement('option');
        option.value = topic.name;
        option.dataset.idx = idx;
        const highYieldMarker = topic.high_yield ? ' ⭐' : '';
        option.textContent = `${topic.name}${highYieldMarker}`;
        if (lessonTopicsSelect) lessonTopicsSelect.appendChild(option);
    });
}

function updateChapters() {
    if (!courseStructure || !courseStructure.subjects || !lessonChaptersSelect) return;

    const selectedSubjectIdx = lessonSubjectSelect?.value;
    if (!selectedSubjectIdx || selectedSubjectIdx === '') return;

    const subject = courseStructure.subjects[selectedSubjectIdx];
    if (!subject || !subject.topics) return;

    const selectedTopicNames = lessonTopicsSelect
        ? Array.from(lessonTopicsSelect.selectedOptions).map(opt => opt.value)
        : [];

    lessonChaptersSelect.innerHTML = '';

    // If no topics selected, don't show chapters
    if (selectedTopicNames.length === 0) return;

    // Collect chapters from selected topics
    selectedTopicNames.forEach(topicName => {
        const topicIdx = subject.topics.findIndex(t => t.name === topicName);
        const topic = topicIdx >= 0 ? subject.topics[topicIdx] : null;
        if (topic && topic.chapters && topic.chapters.length > 0) {
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
if (lessonSubjectSelect) {
    lessonSubjectSelect.addEventListener('change', updateTopics);
}

// Update chapters when topics change
if (lessonTopicsSelect) {
    lessonTopicsSelect.addEventListener('change', updateChapters);
}

// Handle "Generate All" checkbox
if (generateAllCheckbox) {
    generateAllCheckbox.addEventListener('change', (e) => {
        const isChecked = e.target.checked;
        if (lessonSubjectSelect) lessonSubjectSelect.disabled = isChecked;
        if (lessonTopicsSelect) lessonTopicsSelect.disabled = isChecked;
        if (lessonChaptersSelect) lessonChaptersSelect.disabled = isChecked;

        // Enable both generate buttons when "generate all" is checked
        if (generateBtn) generateBtn.disabled = !isChecked && topicsSelect
            ? Array.from(topicsSelect.selectedOptions).length === 0
            : false;
        if (generateLessonsBtn) generateLessonsBtn.disabled = !isChecked && lessonTopicsSelect
            ? Array.from(lessonTopicsSelect.selectedOptions).length === 0
            : false;

        if (isChecked && structureStatus) {
            structureStatus.textContent = '✓ Will generate for entire course';
        } else if (structureStatus) {
            structureStatus.textContent = '';
        }

        updateGenerateBtnLabel();
    });
}

// Generate lessons button handler
if (generateLessonsBtn) {
    generateLessonsBtn.addEventListener('click', async () => {
        console.log('Generate Lessons button clicked');

        const course = lessonCourse?.value.trim() || '';

        // Validation
        if (!course) {
            showToast('Please enter a course name', 'error');
            if (lessonCourse) lessonCourse.focus();
            return;
        }

        if (!courseStructure) {
            showToast('Please click "Generate Subjects" or "Upload JSON" first!', 'error');
            return;
        }

        const generateAll = generateAllCheckbox?.checked || false;

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
        const selectedTopicNames = Array.from(lessonTopicsSelect.selectedOptions).map(opt => opt.value);
        if (selectedTopicNames.length > 0) {
            const subjectData = courseStructure.subjects[parseInt(selectedSubjectIdx)];
            requestData.selected_topic_indices = selectedTopicNames.map(name =>
                subjectData.topics.findIndex(t => t.name === name)
            ).filter(idx => idx >= 0);
        }

        // Get selected chapters (optional)
        if (lessonChaptersSelect) {
            const selectedChapters = Array.from(lessonChaptersSelect.selectedOptions).map(opt => opt.value);
            if (selectedChapters.length > 0) {
                requestData.selected_chapters = selectedChapters;
            }
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

        // Track state for Save / Regenerate buttons
        lastLessonsSaveMeta = { lessons_data: data, course: data.course || course, subject: data.subject || '' };
        currentLessonsSessionId = null;
        lastLessonsRegenerateFn = () => generateLessonsBtn.click();

        // Show results section and switch to lessons tab
        showResultTab('lessons');

        // Scroll to results after a brief delay to ensure rendering
        setTimeout(() => {
            const resultsSection = document.getElementById('results-section');
            if (resultsSection) {
                resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }, 300);

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
}

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

    // Display lessons with tabbed interface
    lessonsContainer.innerHTML = data.lessons.map((lesson, lessonIdx) => {
        const topicId = `topic-${lessonIdx}`;
        const hasChapters = lesson.chapters && lesson.chapters.length > 0;

        return `
        <div class="lesson-card">
            <div class="lesson-header">
                <h3>${lesson.topic}</h3>
                <div class="lesson-tags">
                    ${lesson.high_yield ? '<span class="tag tag-success">High Yield</span>' : ''}
                    <span class="tag tag-info">${lesson.chapters?.length || 0} Chapters</span>
                </div>
            </div>

            <!-- Lesson Tabs -->
            <div class="lesson-tabs">
                <button class="lesson-tab-btn active" data-lesson="${topicId}" data-tab="topic">
                    📖 ${lesson.topic}
                </button>
                ${hasChapters ? `
                <button class="lesson-tab-btn" data-lesson="${topicId}" data-tab="chapters">
                    🎯 Deep Dive
                </button>
                ` : ''}
            </div>

            <!-- Topic Tab Content -->
            <div class="lesson-tab-content active" id="${topicId}-topic">
                <div class="lesson-text">${formatLessonContent(lesson.topic_lesson, lesson.chapters, topicId)}</div>
            </div>

            <!-- Chapters Tab Content -->
            ${hasChapters ? `
            <div class="lesson-tab-content" id="${topicId}-chapters">
                <!-- Chapter Links (Horizontal) -->
                <div class="chapter-links">
                    ${lesson.chapters.map((chapter, chIdx) => `
                        <button class="chapter-link-btn ${chIdx === 0 ? 'active' : ''}"
                                data-lesson="${topicId}"
                                data-chapter="${chIdx}">
                            ${chapter.name}
                        </button>
                    `).join('')}
                </div>

                <!-- Chapter Content -->
                <div class="chapter-content-area">
                    ${lesson.chapters.map((chapter, chIdx) => `
                        <div class="chapter-content ${chIdx === 0 ? 'active' : ''}"
                             id="${topicId}-chapter-${chIdx}">
                            <h4>${chapter.name}</h4>
                            ${chapter.nice_refs && chapter.nice_refs.length > 0 ? `
                                <p class="chapter-refs">📋 NICE References: ${chapter.nice_refs.join(', ')}</p>
                            ` : ''}
                            <div class="lesson-text">${formatLessonContent(chapter.chapter_lesson || chapter.lesson)}</div>
                        </div>
                    `).join('')}
                </div>
            </div>
            ` : ''}
        </div>
        `;
    }).join('');

    // Add event listeners for lesson tabs
    document.querySelectorAll('.lesson-tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const lessonId = e.target.dataset.lesson;
            const tabName = e.target.dataset.tab;

            // Update tab buttons
            document.querySelectorAll(`[data-lesson="${lessonId}"]`).forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');

            // Update tab content
            document.querySelectorAll(`[id^="${lessonId}-"]`).forEach(content => {
                if (!content.id.includes('chapter-')) {
                    content.classList.remove('active');
                }
            });
            document.getElementById(`${lessonId}-${tabName}`).classList.add('active');
        });
    });

    // Add event listeners for chapter links
    document.querySelectorAll('.chapter-link-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const lessonId = e.target.dataset.lesson;
            const chapterIdx = e.target.dataset.chapter;

            // Update chapter link buttons
            document.querySelectorAll(`.chapter-link-btn[data-lesson="${lessonId}"]`).forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');

            // Update chapter content
            document.querySelectorAll(`.chapter-content[id^="${lessonId}-chapter-"]`).forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById(`${lessonId}-chapter-${chapterIdx}`).classList.add('active');
        });
    });

    // Enable Save / Regenerate buttons now that lessons exist
    const saveLessonsBtn = document.getElementById('save-lessons-btn');
    const regenLessonsBtn = document.getElementById('regenerate-lessons-btn');
    if (saveLessonsBtn) {
        saveLessonsBtn.disabled = false;
        saveLessonsBtn.textContent = currentLessonsSessionId ? '💾 Update History' : '💾 Save to History';
    }
    if (regenLessonsBtn) regenLessonsBtn.disabled = false;
}

// Helper function to escape special characters in regex
function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Navigate to a specific chapter in the Deep Dive tab
function navigateToChapter(topicId, chapterIdx) {
    // Switch to chapters tab
    const lessonTabBtns = document.querySelectorAll(`[data-lesson="${topicId}"]`);
    lessonTabBtns.forEach(btn => btn.classList.remove('active'));

    const chaptersTabBtn = document.querySelector(`[data-lesson="${topicId}"][data-tab="chapters"]`);
    if (chaptersTabBtn) {
        chaptersTabBtn.classList.add('active');
    }

    // Show chapters tab content
    document.querySelectorAll(`[id^="${topicId}-"]`).forEach(content => {
        if (!content.id.includes('chapter-')) {
            content.classList.remove('active');
        }
    });
    const chaptersTabContent = document.getElementById(`${topicId}-chapters`);
    if (chaptersTabContent) {
        chaptersTabContent.classList.add('active');
    }

    // Activate the specific chapter
    document.querySelectorAll(`.chapter-link-btn[data-lesson="${topicId}"]`).forEach(btn => {
        btn.classList.remove('active');
    });
    const chapterBtn = document.querySelector(`.chapter-link-btn[data-lesson="${topicId}"][data-chapter="${chapterIdx}"]`);
    if (chapterBtn) {
        chapterBtn.classList.add('active');
    }

    // Show the specific chapter content
    document.querySelectorAll(`.chapter-content[id^="${topicId}-chapter-"]`).forEach(content => {
        content.classList.remove('active');
    });
    const chapterContent = document.getElementById(`${topicId}-chapter-${chapterIdx}`);
    if (chapterContent) {
        chapterContent.classList.add('active');

        // Smooth scroll to the chapter content
        setTimeout(() => {
            chapterContent.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 100);
    }
}

function formatLessonContent(content, chapters = null, topicId = null) {
    if (!content) return '<p class="text-muted">No content available</p>';

    let html = content;

    // Create chapter links if chapters are provided
    if (chapters && topicId) {
        // Sort chapters by name length (longest first) to match more specific names first
        const sortedChapters = chapters.map((ch, idx) => ({ chapter: ch, index: idx }))
            .sort((a, b) => b.chapter.name.length - a.chapter.name.length);

        sortedChapters.forEach(({ chapter, index: chIdx }) => {
            const chapterName = chapter.name;

            // Try multiple variations of the chapter name for better matching
            const variations = [
                chapterName, // Full name
                chapterName.split(':')[0].trim(), // Name before colon
                chapterName.split('-')[0].trim(), // Name before dash
            ];

            variations.forEach(namePart => {
                if (!namePart || namePart.length < 3) return; // Skip very short names

                const escapedName = escapeRegExp(namePart);

                // Multiple patterns to catch different formats
                const patterns = [
                    // (see **Chapter Name**)
                    new RegExp(`\\(see\\s+\\*\\*([^*]*${escapedName}[^*]*)\\*\\*\\)`, 'gi'),
                    // (see Chapter Name)
                    new RegExp(`\\(see\\s+(${escapedName}[^)]*)\\)`, 'gi'),
                    // **Chapter Name** standalone
                    new RegExp(`\\*\\*(${escapedName}[^*]*)\\*\\*(?![^<]*</)`, 'gi'),
                ];

                patterns.forEach(pattern => {
                    html = html.replace(pattern, (match, captured) => {
                        // Don't replace if already has a link
                        if (match.includes('href=') || match.includes('chapter-link')) {
                            return match;
                        }
                        return `<a href="#" class="chapter-link" data-topic="${topicId}" data-chapter="${chIdx}" onclick="navigateToChapter('${topicId}', ${chIdx}); return false;">${match}</a>`;
                    });
                });
            });
        });
    }

    // Handle "Visual Aid" sections - convert to proper heading BEFORE mermaid extraction
    html = html.replace(/(\*\*)?Visual Aid[s]?(\*\*)?:?\s*(\(.*?\))?/gi, '\n<h4 class="visual-aid-heading">📊 Visual Aid</h4>\n');

    // Extract and process Mermaid code blocks first (preserve spacing)
    const mermaidBlocks = [];
    html = html.replace(/```mermaid\s*\n([\s\S]*?)```/g, (match, code) => {
        const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
        mermaidBlocks.push({ id, code: code.trim() });
        return `\n\n<div class="mermaid-container" id="container-${id}"><pre class="mermaid" id="${id}">${code.trim()}</pre></div>\n\n`;
    });

    // Remove empty Visual Aid sections (heading with no content after it)
    html = html.replace(/<h4 class="visual-aid-heading">📊 Visual Aid<\/h4>\s*\n\s*\n(?=<h|$)/g, '');

    // Identify and highlight special sections FIRST (before any markdown conversion)
    // Key Points Summary
    html = html.replace(/(\*\*)?Key Points Summary(\*\*)?/gi, () => {
        return '\n<div class="highlight-box key-points">\n<h4>🎯 Key Points Summary</h4>\n';
    });

    // Look for the next heading after Key Points and close the box
    html = html.replace(/(<div class="highlight-box key-points">[\s\S]*?)(\n#{1,3}\s)/g, '$1\n</div>$2');

    // If no next heading found, close at end
    if (html.includes('<div class="highlight-box key-points">') && !html.includes('</div>\n#')) {
        html = html.replace(/(<div class="highlight-box key-points">[\s\S]*$)/, '$1\n</div>');
    }

    // Mnemonics (with or without bold markers)
    html = html.replace(/(\*\*)?Mnemonic[s]?:?\s*(\*\*)?\s*([A-Z\s]+)\s+for\s+(.+?)(?=\n\n|\n[A-Z#]|$)/gis, (match, b1, b2, acronym, explanation) => {
        return `\n<div class="highlight-box mnemonic">
            <h4>🧠 Mnemonic: ${acronym.trim()}</h4>
            <p>for ${explanation.trim()}</p>
        </div>\n`;
    });

    // Simpler mnemonic pattern
    html = html.replace(/(\*\*)?Mnemonic[s]?:?\s*(\*\*)?\s*(.+?)(?=\n\n|\n[A-Z#]|$)/gis, (match, b1, b2, content) => {
        if (content.trim() && !content.includes('<div')) {
            return `\n<div class="highlight-box mnemonic">
                <h4>🧠 Mnemonic</h4>
                <p>${content.trim()}</p>
            </div>\n`;
        }
        return match;
    });

    // Red Flags
    html = html.replace(/(\*\*)?Red Flag[s]?:?\s*(\*\*)?\s*(.+?)(?=\n\n|\n[A-Z#]|$)/gis, (match, b1, b2, content) => {
        if (content.trim() && !content.includes('<div')) {
            return `\n<div class="highlight-box red-flag">
                <h4>🚩 Red Flags</h4>
                <p>${content.trim()}</p>
            </div>\n`;
        }
        return match;
    });

    // Clinical Pearls
    html = html.replace(/(\*\*)?Clinical Pearl[s]?:?\s*(\*\*)?\s*(.+?)(?=\n\n|\n[A-Z#]|$)/gis, (match, b1, b2, content) => {
        if (content.trim() && !content.includes('<div')) {
            return `\n<div class="highlight-box clinical-pearl">
                <h4>💎 Clinical Pearl</h4>
                <p>${content.trim()}</p>
            </div>\n`;
        }
        return match;
    });

    // Convert tables (do this early to avoid conflicts)
    const tableRegex = /(\|.+\|\n)+/g;
    html = html.replace(tableRegex, (table) => {
        const rows = table.trim().split('\n');
        let tableHtml = '\n<table class="lesson-table">\n';
        rows.forEach((row, idx) => {
            if (idx === 1 && row.includes('---')) return; // Skip separator row
            const cells = row.split('|').filter(c => c.trim());
            const tag = idx === 0 ? 'th' : 'td';
            tableHtml += `<tr>${cells.map(c => `<${tag}>${c.trim()}</${tag}>`).join('')}</tr>\n`;
        });
        tableHtml += '</table>\n';
        return tableHtml;
    });

    // Convert markdown images
    html = html.replace(/!\[([^\]]*)\]\(([^\)]+)\)/g, '\n<img src="$2" alt="$1" class="lesson-image">\n');

    // Convert bold and italic (before lists to handle bold in lists)
    html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // Convert bullet points (• or * or ✓ or -)
    html = html.replace(/^[•\*✓\-]\s+(.+)$/gm, '<li>$1</li>');

    // Wrap consecutive <li> in <ul>
    html = html.replace(/(<li>.*?<\/li>\n?)+/g, (match) => {
        return '\n<ul class="lesson-list">\n' + match + '</ul>\n';
    });

    // Convert numbered lists
    html = html.replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*?<\/li>\n?)+/g, (match) => {
        if (!match.includes('<ul')) {
            return '\n<ol class="lesson-list">\n' + match + '</ol>\n';
        }
        return match;
    });

    // Convert markdown headings
    html = html.replace(/^### (.+)$/gm, '\n<h3 class="lesson-h3">$1</h3>\n');
    html = html.replace(/^## (.+)$/gm, '\n<h2 class="lesson-h2">$1</h2>\n');
    html = html.replace(/^# (.+)$/gm, '\n<h1 class="lesson-h1">$1</h1>\n');

    // Convert paragraphs (split by double newlines, but preserve existing HTML)
    const blocks = html.split(/\n\n+/);
    html = blocks.map(block => {
        block = block.trim();
        if (!block) return '';

        // Skip if already HTML
        if (block.startsWith('<')) return block;

        // Skip if it's just a list item
        if (block.startsWith('<li>')) return block;

        // Convert single newlines to <br> within paragraphs
        return `<p class="lesson-para">${block.replace(/\n/g, '<br>')}</p>`;
    }).filter(b => b).join('\n\n');

    // Initialize Mermaid rendering after content is added to DOM with error handling
    setTimeout(() => {
        if (window.mermaid && mermaidBlocks.length > 0) {
            mermaidBlocks.forEach(block => {
                try {
                    const element = document.getElementById(block.id);
                    const container = document.getElementById(`container-${block.id}`);

                    if (element && container) {
                        // Try to render the mermaid diagram
                        window.mermaid.render(`rendered-${block.id}`, block.code)
                            .then(result => {
                                container.innerHTML = result.svg;
                            })
                            .catch(error => {
                                // If mermaid syntax is invalid, show a clean fallback
                                console.warn('Mermaid rendering error:', error);
                                container.innerHTML = `
                                    <div style="padding: 1rem; background: #fff3cd; border: 1px solid #ffc107; border-radius: 8px; margin: 1rem 0;">
                                        <p style="margin: 0; color: #856404;">
                                            <strong>📊 Diagram:</strong> Visual diagram could not be rendered. Content description available in text.
                                        </p>
                                    </div>
                                `;
                            });
                    }
                } catch (error) {
                    console.warn('Error processing mermaid block:', error);
                }
            });
        }
    }, 100);

    return html;
}

// Download lessons as JSON
if (downloadLessonsJsonBtn) {
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
}

// Download lessons as Markdown
if (downloadLessonsMdBtn) {
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
}

// ============================================
// STRUCTURE REVIEW PANEL EVENT HANDLERS
// ============================================

// Approve structure button
if (approveStructureBtn) {
    approveStructureBtn.addEventListener('click', approveStructure);
}

// Attach document button
if (attachStructureDocBtn) {
    attachStructureDocBtn.addEventListener('click', () => {
        structureDocUpload.click();
    });
}

// File upload handler
if (structureDocUpload) {
    structureDocUpload.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            attachedFile = file;
            if (attachedStructureFile) {
                attachedStructureFile.textContent = `📎 ${file.name}`;
            }
            showToast(`Attached: ${file.name}`, 'info');
        }
    });
}

// Send chat message
if (sendStructureChatBtn) {
    sendStructureChatBtn.addEventListener('click', async () => {
        const message = structureChatInput?.value.trim() || '';
        if (!message && !attachedFile) {
            showToast('Please enter a message or attach a document', 'error');
            return;
        }

        // Add user message to chat
        if (message) {
            addChatMessage(message, 'user');
            if (structureChatInput) structureChatInput.value = '';
        }

        // Prepare request
        const formData = new FormData();
        formData.append('course', courseStructure?.Course || '');
        formData.append('message', message);
        formData.append('current_structure', JSON.stringify(courseStructure));

        if (attachedFile) {
            formData.append('reference_doc', attachedFile);
            addChatMessage(`Uploaded: ${attachedFile.name}`, 'user');
        }

        sendStructureChatBtn.disabled = true;
        sendStructureChatBtn.textContent = '⏳';

        try {
            const response = await fetch('/api/refine-structure', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) throw new Error('Failed to process request');

            const data = await response.json();

            // Add AI response to chat
            addChatMessage(data.response, 'assistant');

            // Update structure if modified
            if (data.updated_structure) {
                courseStructure = data.updated_structure;
                displayStructureReview();
                showToast('Structure updated!', 'success');
            }

            // Clear attached file
            attachedFile = null;
            if (attachedStructureFile) attachedStructureFile.textContent = '';
            if (structureDocUpload) structureDocUpload.value = '';

        } catch (error) {
            addChatMessage('Sorry, I encountered an error processing your request. Please try again.', 'assistant');
            showToast(error.message || 'Error processing request', 'error');
        } finally {
            sendStructureChatBtn.disabled = false;
            sendStructureChatBtn.textContent = 'Update';
        }
    });
}

// Allow Enter to send (Shift+Enter for new line)
if (structureChatInput) {
    structureChatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (sendStructureChatBtn) sendStructureChatBtn.click();
        }
    });
}

// ============================================
// RESULT TABS SWITCHING
// ============================================

document.querySelectorAll('.result-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tabName = btn.getAttribute('data-result-tab');
        
        // Remove active class from all result tab buttons
        document.querySelectorAll('.result-tab-btn').forEach(b => b.classList.remove('active'));
        
        // Add active class to clicked button
        btn.classList.add('active');
        
        // Hide all result tab contents
        document.querySelectorAll('.result-tab-content').forEach(content => {
            content.classList.remove('active');
            content.style.display = 'none';
        });
        
        // Show selected result tab content
        if (tabName === 'lessons') {
            const lessonsResult = document.getElementById('lessons-result');
            if (lessonsResult) {
                lessonsResult.classList.add('active');
                lessonsResult.style.display = 'block';
            }
        } else if (tabName === 'qbank') {
            const qbankResult = document.getElementById('results');
            if (qbankResult) {
                qbankResult.classList.add('active');
                qbankResult.style.display = 'block';
            }
        } else if (tabName === 'validation') {
            const valResult = document.getElementById('validation-result');
            if (valResult) {
                valResult.classList.add('active');
                valResult.style.display = 'block';
            }
        }
    });
});

// Helper function to show results section and switch to specific tab
function showResultTab(tabName) {
    const resultsSection = document.getElementById('results-section');
    if (resultsSection) {
        resultsSection.style.display = 'block';
    }

    // Click the appropriate tab
    const tabBtn = document.querySelector(`[data-result-tab="${tabName}"]`);
    if (tabBtn) {
        tabBtn.click();
    }
}

// ============================================
// COUNCIL OF MODELS VALIDATION SYSTEM
// ============================================

// Validate Lessons button handler
// Flatten lessons: topic lesson + each chapter become individual sections
function flattenLessonsToSections(lessons) {
    const sections = [];
    const sectionMap = []; // parallel array: sectionMap[i] → {lessonIndex, type, chapterIndex?}
    lessons.forEach((lesson, li) => {
        if (lesson.topic_lesson) {
            sections.push({ topic: lesson.topic, topic_lesson: lesson.topic_lesson, chapters: [] });
            sectionMap.push({ lessonIndex: li, type: 'topic' });
        }
        if (lesson.chapters && lesson.chapters.length > 0) {
            lesson.chapters.forEach((ch, ci) => {
                if (ch.lesson) {
                    sections.push({ topic: ch.chapter, topic_lesson: ch.lesson, chapters: [] });
                    sectionMap.push({ lessonIndex: li, chapterIndex: ci, type: 'chapter' });
                }
            });
        }
    });
    return { sections, sectionMap };
}

// ── Validation tab helpers ────────────────────────────────────────────────────
function switchToValidationTab() {
    const btn = document.getElementById('validation-tab-btn');
    if (btn) {
        btn.style.display = '';   // make tab visible
        btn.click();              // activate it
    }
}

function switchToContentTab(contentType) {
    const tabName = contentType === 'lesson' ? 'lessons' : 'qbank';
    const btn = document.querySelector(`[data-result-tab="${tabName}"]`);
    if (btn) btn.click();
}

// Filter state: {score, status, type}
let _valFilter = { score: 'all', status: 'all', type: 'all' };

function setValFilter(dim, value) {
    _valFilter[dim] = value;
    // Update button active states
    document.querySelectorAll(`.vfbtn-${dim}`).forEach(b => {
        b.classList.toggle('active', b.dataset.val === value);
    });
    applyValFilters();
}

function applyValFilters() {
    let visible = 0;
    document.querySelectorAll('#val-items-list .val-accordion[data-val-score]').forEach(el => {
        const score  = el.dataset.valScore;
        const status = el.dataset.valStatus;
        const type   = el.dataset.valType;

        const scoreOk  = _valFilter.score  === 'all' || _valFilter.score  === score;
        const statusOk = _valFilter.status === 'all' || _valFilter.status === status;
        const typeOk   = _valFilter.type   === 'all' || _valFilter.type   === type;

        const show = scoreOk && statusOk && typeOk;
        el.style.display = show ? '' : 'none';
        if (show) visible++;
    });

    const countEl = document.getElementById('val-visible-count');
    if (countEl) countEl.textContent = visible;
}

const validateLessonsBtn = document.getElementById('validate-lessons-btn');
if (validateLessonsBtn) {
    validateLessonsBtn.addEventListener('click', async () => {
        if (!lessonsData || !lessonsData.lessons || lessonsData.lessons.length === 0) {
            showToast('No lessons to validate', 'error');
            return;
        }

        const reportContent = document.getElementById('validation-report-content');
        const { sections, sectionMap } = flattenLessonsToSections(lessonsData.lessons);
        const count = sections.length;
        _validationState = { contentType: 'lesson', originalItems: sections, sectionMap, course: lessonsData.course || 'Unknown' };

        reportContent.innerHTML = `
            <div style="text-align:center;padding:3rem;">
                <div class="loading-spinner"></div>
                <p style="color:#999;margin-top:1rem;">Running Council of Models validation on ${count} section(s)...</p>
                <p style="color:#999;font-size:0.9rem;">Validator &amp; Adversarial running in parallel — est. 60–90 sec</p>
            </div>
        `;
        switchToValidationTab();

        try {
            const response = await fetch('/api/validate-content', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    content_type: 'lesson',
                    items: sections,
                    domain: 'medical education',
                    course: lessonsData.course || 'Unknown'
                })
            });

            if (!response.ok) throw new Error('Validation failed');

            const report = await response.json();
            displayBatchValidationReport(report, 'lesson');

        } catch (error) {
            console.error('Validation error:', error);
            reportContent.innerHTML = `
                <div style="text-align:center;padding:2rem;">
                    <h3 style="color:#dc3545;">❌ Validation Error</h3>
                    <p>${error.message || 'Failed to validate content'}</p>
                    <button onclick="switchToContentTab('lesson')" class="btn-secondary" style="margin-top:1rem;">← Back to Lessons</button>
                </div>
            `;
        }
    });
}

// Validate QBank button handler
const validateQBankBtn = document.getElementById('validate-qbank-btn');
if (validateQBankBtn) {
    validateQBankBtn.addEventListener('click', async () => {
        if (!generatedQuestions || generatedQuestions.length === 0) {
            showToast('No questions to validate', 'error');
            return;
        }

        const reportContent = document.getElementById('validation-report-content');
        const course = courseStructure?.Course || 'Unknown';

        _validationState = {
            contentType: 'qbank',
            originalItems: [...generatedQuestions],
            sectionMap: null,
            course
        };

        reportContent.innerHTML = `
            <div style="text-align:center;padding:3rem;">
                <div class="loading-spinner"></div>
                <p style="color:#999;margin-top:1rem;">
                    Running validation on ${generatedQuestions.length} question(s)...
                </p>
                <p style="color:#999;font-size:0.9rem;">Validator &amp; Adversarial running in parallel — est. 30–60 sec</p>
            </div>
        `;
        switchToValidationTab();

        try {
            const response = await fetch('/api/validate-content', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    content_type: 'qbank',
                    items: generatedQuestions,
                    domain: 'medical education',
                    course
                })
            });
            if (!response.ok) throw new Error('Validation failed');
            const report = await response.json();

            displayBatchValidationReport(report, 'qbank');

        } catch (error) {
            console.error('Validation error:', error);
            reportContent.innerHTML = `
                <div style="text-align:center;padding:2rem;">
                    <h3 style="color:#dc3545;">❌ Validation Error</h3>
                    <p>${error.message || 'Failed to validate content'}</p>
                    <button onclick="switchToContentTab('qbank')" class="btn-secondary" style="margin-top:1rem;">← Back to QBank</button>
                </div>
            `;
        }
    });
}

function displayBatchValidationReport(report, contentType) {
    const reportContent = document.getElementById('validation-report-content');
    const items = report.items || [];
    const summary = report.summary || {};

    // Reset filters and fixed-item tracking for new report
    _valFilter = { score: 'all', status: 'all', type: 'all' };
    _fixedItemIndices.clear();

    // Combined score is out of 20; individual scores out of 10
    const getScoreClass = (score, outOf = 10) => {
        const pct = score / outOf;
        if (pct >= 0.8) return 'score-high';
        if (pct >= 0.55) return 'score-medium';
        return 'score-low';
    };

    const statusBadge = (assessment) => {
        const s = assessment.status || '';
        const color = s.includes('All Good') ? '#28a745' : s.includes('Conditional') ? '#e67e00' : '#dc3545';
        return `<span style="background:${color};color:#fff;padding:2px 10px;border-radius:12px;font-size:0.85rem;">${s}</span>`;
    };

    // Store report in validation state for fix
    if (_validationState) _validationState.report = report;

    // ---- Back button ----
    const backLabel = contentType === 'lesson' ? '← Back to Lessons' : '← Back to QBank';
    const backHtml = `
        <div style="margin-bottom:1rem;">
            <button onclick="switchToContentTab('${contentType}')"
                style="background:none;border:1.5px solid var(--border);border-radius:6px;padding:0.35rem 0.9rem;font-size:0.88rem;cursor:pointer;color:var(--text);font-weight:500;">
                ${backLabel}
            </button>
        </div>`;

    // ---- Summary bar ----
    const structuralCount = summary.structural_failures || 0;
    const needsRevCount = summary.needs_revision || 0;
    const approvedCount = summary.approved || 0;
    const conditionalCount = (summary.total || 0) - approvedCount - needsRevCount;

    const summaryHtml = `
        <div class="overall-assessment" style="margin-bottom:1rem;">
            <div style="display:flex;align-items:baseline;gap:1rem;flex-wrap:wrap;">
                <h3 style="margin:0;">📊 ${report.course || 'Validation Report'}</h3>
                <span style="font-size:0.85rem;color:#999;">${new Date(report.timestamp).toLocaleString()}</span>
            </div>
            <div style="display:flex;gap:1.5rem;flex-wrap:wrap;margin-top:0.6rem;font-size:0.95rem;">
                <div><strong>${summary.total || 0}</strong> total</div>
                <div style="color:#28a745;"><strong>✅ ${approvedCount}</strong> approved</div>
                <div style="color:#dc3545;"><strong>❌ ${needsRevCount}</strong> needs revision</div>
                ${conditionalCount > 0 ? `<div style="color:#856404;"><strong>⚠️ ${conditionalCount}</strong> conditional</div>` : ''}
                ${structuralCount ? `<div style="color:#6f42c1;"><strong>🔧 ${structuralCount}</strong> structural failures</div>` : ''}
                <div><strong>Avg:</strong> ${summary.avg_quality_score || 'N/A'}/20</div>
            </div>
        </div>`;

    // ---- Filter bar ----
    const filterHtml = `
        <div class="val-filter-bar" style="border-top:1px solid var(--border);border-bottom:1px solid var(--border);padding:0.6rem 0;margin-bottom:1rem;">
            <span class="val-filter-label">Score:</span>
            <div class="val-filter-group">
                <button class="val-filter-btn vfbtn-score active" data-val="all"     onclick="setValFilter('score','all')">All</button>
                <button class="val-filter-btn vfbtn-score"        data-val="high"    onclick="setValFilter('score','high')">8+ ✅</button>
                <button class="val-filter-btn vfbtn-score"        data-val="medium"  onclick="setValFilter('score','medium')">6–8 ⚠️</button>
                <button class="val-filter-btn vfbtn-score"        data-val="low"     onclick="setValFilter('score','low')">&lt;6 ❌</button>
            </div>
            <span class="val-filter-label" style="margin-left:0.6rem;">Status:</span>
            <div class="val-filter-group">
                <button class="val-filter-btn vfbtn-status active" data-val="all"       onclick="setValFilter('status','all')">All</button>
                <button class="val-filter-btn vfbtn-status"        data-val="approved"  onclick="setValFilter('status','approved')">✅ All Good</button>
                <button class="val-filter-btn vfbtn-status"        data-val="revision"  onclick="setValFilter('status','revision')">❌ Needs Revision</button>
                <button class="val-filter-btn vfbtn-status"        data-val="conditional" onclick="setValFilter('status','conditional')">⚠️ Conditional</button>
            </div>
            ${contentType === 'qbank' ? `
            <span class="val-filter-label" style="margin-left:0.6rem;">Type:</span>
            <div class="val-filter-group">
                <button class="val-filter-btn vfbtn-type active" data-val="all"   onclick="setValFilter('type','all')">All</button>
                <button class="val-filter-btn vfbtn-type"        data-val="image" onclick="setValFilter('type','image')">🖼️ Image</button>
                <button class="val-filter-btn vfbtn-type"        data-val="text"  onclick="setValFilter('type','text')">📝 Text-only</button>
            </div>` : ''}
            <span style="margin-left:auto;font-size:0.82rem;color:var(--text-muted);">Showing <span id="val-visible-count">${items.length}</span> / ${items.length}</span>
        </div>`;

    // ---- Actions bar ----
    const actionsHtml = `
        <div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;margin-bottom:1.25rem;">
            <label style="display:flex;align-items:center;gap:0.4rem;cursor:pointer;font-size:0.9rem;user-select:none;">
                <input type="checkbox" id="select-all-fixes" onchange="toggleSelectAllFixes(this)" style="width:15px;height:15px;cursor:pointer;">
                <span>Select All</span>
            </label>
            <button onclick="selectNeedsRevision()"
                style="background:#dc3545;color:#fff;border:none;border-radius:6px;padding:0.4rem 1rem;cursor:pointer;font-size:0.88rem;font-weight:600;">
                ❌ Select Needs Revision
            </button>
            <button id="fix-selected-btn" onclick="fixSelectedItems()" disabled
                style="background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border:none;border-radius:6px;padding:0.4rem 1.2rem;cursor:pointer;font-size:0.88rem;font-weight:600;opacity:0.45;transition:opacity 0.2s;">
                🔧 Fix Selected (0)
            </button>
            <button id="reval-selected-btn" onclick="revalidateSelected()" disabled
                style="background:linear-gradient(135deg,#f093fb,#f5576c);color:#fff;border:none;border-radius:6px;padding:0.4rem 1.2rem;cursor:pointer;font-size:0.88rem;font-weight:600;opacity:0.45;transition:opacity 0.2s;display:none;">
                🔄 Revalidate Fixed (0)
            </button>
        </div>`;

    // ---- Per-item accordions ----
    const itemLabel = contentType === 'qbank' ? 'Q' : 'Section';
    const itemsHtml = items.map((item, idx) => {
        const v = item.validator || {};
        const a = item.adversarial || {};
        const oa = item.overall_assessment || {};
        const num = item.index || idx + 1;
        const isStructural = item.structural_failure === true;
        const isParseMiss  = item.parse_miss === true;

        // Derive filter data attributes
        const scoreVal = isParseMiss ? 'medium'
            : (oa.quality_score >= 16 ? 'high' : oa.quality_score >= 11 ? 'medium' : 'low');
        const statusStr = (oa.status || '').toLowerCase();
        const statusVal = statusStr.includes('all good') ? 'approved'
            : statusStr.includes('revision') ? 'revision'
            : 'conditional';
        const qObj = contentType === 'qbank' ? (generatedQuestions[num - 1] || {}) : {};
        const isImageQ = !!(qObj.image_url || qObj.requires_image || qObj.is_image_question || qObj.image_missing);
        const typeVal = isImageQ ? 'image' : 'text';

        // Header title
        let headerTitle = `${itemLabel} ${num}`;
        if (contentType === 'qbank' && v.question_preview) {
            headerTitle += ` — ${v.question_preview.substring(0, 70)}${v.question_preview.length > 70 ? '...' : ''}`;
        } else if (contentType === 'lesson' && v.section_title) {
            headerTitle += ` — ${v.section_title}`;
        }

        const accordionId = `val-item-${num}`;
        const headerBg = isStructural ? '#fff0f6' : isParseMiss ? '#fffbf0' : '#f8f9fa';
        const borderColor = isStructural ? '#f5c6cb' : isParseMiss ? '#ffc107' : '#e0e0e0';

        // Build changes list
        const vC = v.changes_required || [];
        const aC = (a.changes_required || []).filter(ac =>
            !vC.some(vc => vc.toLowerCase().includes(ac.toLowerCase().slice(3, 20)) ||
                           ac.toLowerCase().includes(vc.toLowerCase().slice(3, 20)))
        );
        const allChanges = [...vC, ...aC].map((c, i) => c.replace(/^\d+\.\s*/, `${i+1}. `));

        const changesHtml = allChanges.length === 0
            ? '<p style="color:#28a745;font-size:0.88rem;margin:0;">✅ No changes required</p>'
            : `<div style="margin:0.5rem 0;">
                <strong style="font-size:0.88rem;">📋 Changes Required to score above 8:</strong>
                <ol style="margin:0.4rem 0 0 1.2rem;padding:0;font-size:0.88rem;line-height:1.7;">
                    ${allChanges.map(c => `<li style="margin-bottom:0.2rem;">${escapeHtml(c.replace(/^\d+\.\s*/, ''))}</li>`).join('')}
                </ol>
               </div>`;

        const imageTag = isImageQ ? '<span style="font-size:0.75rem;color:#6c757d;background:#f0f0f0;padding:1px 6px;border-radius:10px;margin-left:4px;">🖼️</span>' : '';
        const valDebugBtn = isImageQ ? `
            <button onclick="event.stopPropagation();showImageDebugPanel(${num}, this, 'validation')"
                title="View image search debug"
                style="background:none;border:1.5px solid #7b5ea7;color:#7b5ea7;border-radius:6px;padding:1px 8px;font-size:0.75rem;cursor:pointer;font-weight:600;white-space:nowrap;margin-left:4px;"
                data-debug-loading="false">🔍</button>` : '';

        return `
        <div class="val-accordion" data-val-score="${scoreVal}" data-val-status="${statusVal}" data-val-type="${typeVal}"
             style="border:1px solid ${borderColor};border-radius:8px;margin-bottom:0.6rem;overflow:hidden;">
            <div style="display:flex;align-items:stretch;background:${headerBg};">
                <label style="display:flex;align-items:center;padding:0 0.85rem;cursor:pointer;border-right:1px solid ${borderColor};"
                       onclick="event.stopPropagation()" title="Select for fixing">
                    <input type="checkbox" class="fix-checkbox" data-index="${num}"
                           onchange="updateFixButtonCount()" style="width:15px;height:15px;cursor:pointer;">
                </label>
                <button class="val-acc-header" onclick="toggleValAccordion('${accordionId}')"
                    style="flex:1;text-align:left;padding:0.75rem 1rem;background:transparent;border:none;cursor:pointer;display:flex;align-items:center;gap:0.5rem;font-size:0.9rem;">
                    <span style="font-weight:600;">${headerTitle}</span>${imageTag}${valDebugBtn}
                    <span style="margin-left:auto;display:flex;gap:0.5rem;align-items:center;flex-shrink:0;">
                        ${isStructural ? '<span style="background:#6f42c1;color:#fff;padding:2px 8px;border-radius:12px;font-size:0.78rem;">🔧 Structural</span>' : isParseMiss ? '<span style="background:#ffc107;color:#333;padding:2px 8px;border-radius:12px;font-size:0.78rem;">⚠️ Not Validated</span>' : statusBadge(oa)}
                        <span class="validation-score ${getScoreClass(oa.quality_score != null ? oa.quality_score : 0, 20)}" style="font-size:0.82rem;">${oa.quality_score != null ? oa.quality_score + '/20' : 'N/A'}</span>
                        <span style="font-size:0.78rem;color:#aaa;">▼</span>
                    </span>
                </button>
            </div>
            <div id="${accordionId}" style="display:none;padding:1rem 1.25rem;border-top:1px solid ${borderColor};">
                <!-- Score row -->
                <div style="display:flex;gap:1.25rem;flex-wrap:wrap;margin-bottom:0.6rem;font-size:0.87rem;">
                    <div>✅ <strong>Validator:</strong>
                        <span class="validation-score ${getScoreClass(v.overall_accuracy_score || 0)}" style="font-size:0.78rem;">${v.overall_accuracy_score ?? 'N/A'}/10</span>
                    </div>
                    ${contentType === 'qbank' ? `<div>Answer: <strong>${v.correct_answer_verified === true ? '✅ Verified' : v.correct_answer_verified === false ? '❌ Wrong' : '—'}</strong></div>` : ''}
                    <div>⚔️ <strong>Adversarial:</strong>
                        <span class="validation-score ${getScoreClass(a.adversarial_score || 0)}" style="font-size:0.78rem;">${a.adversarial_score ?? 'N/A'}/10</span>
                        <em style="font-size:0.78rem;color:#888;margin-left:4px;">${a.breakability_rating || ''}</em>
                    </div>
                    <div>Revision: <strong>${oa.needs_revision ? '❌ Yes' : '✅ No'}</strong></div>
                </div>
                <!-- Summaries -->
                <p style="margin-bottom:0.6rem;font-size:0.87rem;color:#555;line-height:1.5;">
                    <strong>V:</strong> ${v.summary || 'N/A'}<br>
                    <strong>A:</strong> ${a.summary || 'N/A'}
                </p>
                ${changesHtml}
                <div style="margin-top:0.6rem;padding:0.4rem 0.6rem;background:#f8f9fa;border-radius:4px;font-size:0.82rem;color:#6c757d;">
                    ${oa.recommendation || ''}
                </div>
                <!-- Image debug panel placeholder (populated on demand or after fix) -->
                <div id="img-debug-${num}" style="display:none;margin-top:0.75rem;"></div>
            </div>
        </div>`;
    }).join('');

    reportContent.innerHTML = backHtml + summaryHtml + filterHtml + actionsHtml + `<div id="val-items-list">${itemsHtml}</div>`;
    showToast(`Validation complete — ${approvedCount}/${summary.total || 0} approved`, 'success');
}

function toggleValAccordion(id) {
    const el = document.getElementById(id);
    if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

// ============================================================
// IMAGE SEARCH DEBUG PANEL
// ============================================================

/**
 * Build HTML for a debug panel from debug data.
 * debugData: { search_terms, image_type, candidates, selected_url, threshold, message? }
 * title: optional header title override
 */
function renderImageDebugPanel(debugData, title) {
    if (!debugData) return '<p style="color:#6c757d;font-size:0.85rem;">No debug data.</p>';

    const headerTitle = title || '🔍 Image Search Debug';
    const { used_query, search_terms = [], image_type = '', google_raw_count, google_error, gemini_error, candidates = [], selected_url, threshold = 80, message, gemini_prompt } = debugData;

    if (message && candidates.length === 0) {
        return `<div style="background:#f0f4ff;border:1px solid #c5d0ff;border-radius:8px;padding:0.75rem 1rem;font-size:0.85rem;color:#444;">
            <strong>${headerTitle}</strong><br><span style="color:#888;">${message}</span>
        </div>`;
    }

    // Only the first (actually used) query chip, bold; rest shown grayed-out as "not used"
    const activeQuery = used_query || search_terms[0] || '';
    const unusedTerms = search_terms.slice(used_query ? (search_terms.indexOf(activeQuery) + 1) : 1);
    const queryHtml = activeQuery
        ? `<span style="background:#5e35b1;color:#fff;border-radius:12px;padding:2px 11px;font-size:0.78rem;white-space:nowrap;font-weight:600;">${escapeHtml(activeQuery)}</span>`
        : '';
    const unusedHtml = unusedTerms.map(t =>
        `<span style="background:#e0e0e0;color:#999;border-radius:12px;padding:2px 9px;font-size:0.75rem;white-space:nowrap;" title="Not sent to Google">${escapeHtml(t)}</span>`
    ).join(' ');

    // Score bar — fills proportionally, color reflects pass/fail vs threshold
    const scoreBar = (score) => {
        const color = score >= threshold ? '#28a745' : score >= 60 ? '#e6a817' : '#dc3545';
        const pct = Math.min(score, 100);
        return `<div style="display:flex;align-items:center;gap:6px;">
            <div style="flex:1;height:6px;background:#e9ecef;border-radius:3px;overflow:hidden;">
                <div style="width:${pct}%;height:100%;background:${color};border-radius:3px;transition:width 0.3s;"></div>
            </div>
            <span style="font-weight:700;color:${color};font-size:0.82rem;min-width:38px;text-align:right;">${score}/100</span>
        </div>`;
    };

    // Scored criterion breakdown — parse out the four criteria scores from the reason if present
    // Reason from Claude: "MODALITY MATCH: X/20. DIAGNOSTIC FINDING: Y/40. ..."
    // We just display the full reason text clearly — no need to re-parse.

    const noCandidates = candidates.length === 0
        ? '<p style="color:#888;font-size:0.85rem;margin:0.3rem 0;">No search candidates found — image was AI-generated by Nano Banana Pro.</p>' : '';

    const candidatesHtml = candidates.map((c, i) => {
        const isSelected = c.selected || (selected_url && c.url === selected_url);
        const scoreColor = c.score >= threshold ? '#28a745' : c.score >= 60 ? '#e6a817' : '#dc3545';
        const rowBg = isSelected ? '#f0eaff' : (i % 2 === 0 ? '#fff' : '#fafafa');
        const borderLeft = isSelected ? '4px solid #7b5ea7' : '4px solid #e0e0e0';

        const hasUrl = c.url && (c.url.startsWith('http') || c.url.startsWith('/'));
        const imgEl = hasUrl
            ? `<img src="${escapeHtml(c.url)}" alt="" loading="lazy"
                style="width:110px;min-width:110px;height:90px;object-fit:cover;border-radius:5px;display:block;"
                onerror="this.style.display='none';this.nextElementSibling.style.display='flex';">
               <div style="display:none;width:110px;min-width:110px;height:90px;align-items:center;justify-content:center;background:#eee;border-radius:5px;font-size:1.5rem;">🖼️</div>`
            : `<div style="width:110px;min-width:110px;height:90px;display:flex;align-items:center;justify-content:center;background:#eee;border-radius:5px;font-size:1.5rem;">🖼️</div>`;

        const selectedBadge = isSelected
            ? `<span style="background:#7b5ea7;color:#fff;border-radius:10px;font-size:0.7rem;padding:1px 7px;font-weight:700;white-space:nowrap;">✓ Selected</span>`
            : `<span style="background:#e0e0e0;color:#888;border-radius:10px;font-size:0.7rem;padding:1px 7px;white-space:nowrap;">Rejected</span>`;

        const passFailLabel = c.score >= threshold
            ? `<span style="color:#28a745;font-size:0.72rem;font-weight:600;">✅ Above threshold (${threshold})</span>`
            : `<span style="color:#dc3545;font-size:0.72rem;font-weight:600;">❌ Below threshold (${threshold})</span>`;

        return `
        <div style="display:flex;gap:10px;align-items:flex-start;padding:10px 12px;background:${rowBg};border-left:${borderLeft};border-bottom:1px solid #ebebeb;">
            ${imgEl}
            <div style="flex:1;min-width:0;">
                <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:4px;">
                    <span style="font-size:0.78rem;color:#555;font-weight:600;">#${i+1}</span>
                    ${selectedBadge}
                    ${passFailLabel}
                    <span style="font-size:0.75rem;color:#888;margin-left:auto;">${escapeHtml(c.source || '')}</span>
                </div>
                ${scoreBar(c.score)}
                ${c.title ? `<div style="font-size:0.75rem;color:#777;margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(c.title)}">${escapeHtml(c.title)}</div>` : ''}
                ${c.reason ? `<div style="font-size:0.8rem;color:#444;margin-top:5px;line-height:1.5;background:#f8f8f8;border-radius:4px;padding:5px 7px;border-left:3px solid ${scoreColor};">${escapeHtml(c.reason)}</div>` : ''}
            </div>
        </div>`;
    }).join('');

    // Final output section — prominently show whichever image was actually used
    const finalOutputSection = (() => {
        if (selected_url) {
            const isAI = candidates.length > 0 && candidates[0].source && candidates[0].source.toLowerCase().includes('gemini');
            const label = isAI ? '🤖 Final Output: Gemini Generated' : '✅ Final Output: Google Image Selected';
            const labelColor = isAI ? '#5e35b1' : '#28a745';
            return `
            <div style="padding:0.6rem 1rem;border-top:1px solid #d0c4f0;background:#f0eaff;">
                <div style="font-size:0.82rem;font-weight:700;color:${labelColor};margin-bottom:0.4rem;">${label}</div>
                <img src="${escapeHtml(selected_url)}" alt="Final output"
                    style="max-width:100%;max-height:320px;border-radius:6px;border:2px solid ${labelColor};display:block;"
                    onerror="this.outerHTML='<div style=\'color:#dc3545;font-size:0.8rem;\'>Image failed to load: ${escapeHtml(selected_url)}</div>'">
            </div>`;
        } else {
            const noImageReason = gemini_error
                ? `No image — all Google results below threshold (${threshold}/100). AI generation failed: ${gemini_error}`
                : `No image — all Google results below threshold (${threshold}/100) and AI generation was skipped or unavailable.`;
            return `
            <div style="padding:0.5rem 1rem;border-top:1px solid #d0c4f0;background:#fff8f8;">
                <span style="font-size:0.8rem;color:#dc3545;font-weight:600;">⚠️ ${escapeHtml(noImageReason)}</span>
            </div>`;
        }
    })();

    const geminiErrorBanner = gemini_error && !selected_url ? '' : (gemini_error ? `
        <div style="padding:0.45rem 1rem;border-bottom:1px solid #f5c6cb;background:#fff0f0;font-size:0.78rem;color:#721c24;">
            ⚠️ <strong>AI generation error:</strong> ${escapeHtml(gemini_error)}
        </div>` : '');

    const geminiSection = gemini_prompt ? `
        <details style="margin-top:0.5rem;">
            <summary style="cursor:pointer;font-size:0.82rem;color:#5e35b1;font-weight:600;user-select:none;padding:4px 0;">
                🤖 Gemini (Nano Banana Pro) Generation Prompt
            </summary>
            <pre style="margin-top:0.4rem;background:#fff;border:1px solid #d0c4f0;border-radius:6px;padding:0.6rem 0.75rem;font-size:0.75rem;white-space:pre-wrap;overflow-x:auto;color:#333;line-height:1.5;">${escapeHtml(gemini_prompt)}</pre>
        </details>` : '';

    return `
        <div style="background:#f7f4ff;border:1.5px solid #d0c4f0;border-radius:8px;overflow:hidden;">
            <!-- Header -->
            <div style="padding:0.65rem 1rem;border-bottom:1px solid #d0c4f0;display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">
                <strong style="font-size:0.88rem;color:#5e35b1;">${headerTitle}</strong>
                ${image_type ? `<span style="background:#ede7f6;color:#5e35b1;border-radius:10px;padding:1px 8px;font-size:0.75rem;">${escapeHtml(image_type)}</span>` : ''}
            </div>
            <!-- Query -->
            ${activeQuery ? `
            <div style="padding:0.5rem 1rem;border-bottom:1px solid #e8e2f8;display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                <span style="font-size:0.75rem;color:#888;white-space:nowrap;">Google query:</span>
                ${queryHtml}
                ${unusedHtml ? `<span style="font-size:0.72rem;color:#bbb;margin-left:4px;">unused:</span>${unusedHtml}` : ''}
            </div>` : ''}
            <!-- Google raw count + error banner -->
            ${google_error ? `
            <div style="padding:0.45rem 1rem;border-bottom:1px solid #f5c6cb;background:#fff0f0;font-size:0.78rem;color:#721c24;">
                ⚠️ <strong>Google CSE error:</strong> ${escapeHtml(google_error)}
            </div>` : ''}
            ${geminiErrorBanner}
            <div style="padding:0.4rem 1rem;border-bottom:1px solid #e8e2f8;font-size:0.75rem;color:#888;display:flex;gap:1.5rem;flex-wrap:wrap;">
                <span>Google raw results: <strong>${google_raw_count ?? '?'}</strong></span>
                ${candidates.length ? `<span>Scored by Claude Vision: <strong>${candidates.filter(c => c.source !== 'Gemini (AI generated)').length}</strong></span>` : ''}
                <span>Auto-select threshold: <strong>${threshold}/100</strong></span>
            </div>
            <!-- Candidates -->
            ${candidates.length ? `
            <div style="border-bottom:1px solid #e8e2f8;">
                ${candidatesHtml}
            </div>` : noCandidates ? `<div style="padding:0.6rem 1rem;">${noCandidates}</div>` : ''}
            <!-- Gemini prompt -->
            ${geminiSection ? `<div style="padding:0.4rem 1rem 0.6rem;">${geminiSection}</div>` : ''}
            <!-- Final output -->
            ${finalOutputSection}
        </div>`;
}

/**
 * Called from QBank card 🔍 button or validation accordion 🔍 button.
 * context: 'qbank' | 'validation'
 * For 'qbank': injects panel just after the button's parent card header.
 * For 'validation': injects panel into #img-debug-{qIdx} placeholder.
 */
async function showImageDebugPanel(qIdx, btn, context) {
    if (btn.dataset.debugLoading === 'true') return;

    // Find the panel container
    let panelContainer;
    if (context === 'validation') {
        panelContainer = document.getElementById(`img-debug-${qIdx}`);
        // Open accordion first so panel is visible
        const accordionId = `val-item-${qIdx}`;
        const acc = document.getElementById(accordionId);
        if (acc) acc.style.display = 'block';
    } else {
        // QBank: look for or create a panel div after the question-card for this index
        const card = document.querySelector(`.question-card[data-q-index="${qIdx}"]`);
        if (!card) return;
        panelContainer = card.querySelector('.img-debug-panel');
        if (!panelContainer) {
            panelContainer = document.createElement('div');
            panelContainer.className = 'img-debug-panel';
            panelContainer.style.cssText = 'margin-top:0.5rem;';
            card.appendChild(panelContainer);
        }
    }

    if (!panelContainer) return;

    // Toggle: if already showing non-empty content, hide it
    if (panelContainer.style.display !== 'none' && panelContainer.innerHTML.trim()) {
        panelContainer.style.display = 'none';
        btn.textContent = '🔍' + (context === 'qbank' ? ' Image Search' : '');
        return;
    }

    // Show loading state
    panelContainer.style.display = 'block';
    panelContainer.innerHTML = `<div style="padding:0.5rem;font-size:0.82rem;color:#7b5ea7;">⏳ Searching images…</div>`;
    btn.dataset.debugLoading = 'true';
    btn.textContent = '⏳' + (context === 'qbank' ? ' Searching…' : '');

    try {
        const q = generatedQuestions[qIdx - 1];
        if (!q) throw new Error('Question not found');

        const subject = lessonsData?.subject || courseStructure?.Subject || '';
        const resp = await fetch('/api/image-search-debug', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question_data: q, subject })
        });
        const data = await resp.json();
        if (data.error) throw new Error(data.error);

        panelContainer.innerHTML = renderImageDebugPanel(data);
    } catch (e) {
        panelContainer.innerHTML = `<div style="color:#dc3545;font-size:0.82rem;padding:0.4rem;">Error: ${escapeHtml(e.message)}</div>`;
    } finally {
        btn.dataset.debugLoading = 'false';
        btn.textContent = '🔍' + (context === 'qbank' ? ' Image Search' : '');
    }
}

// ============================================================
// FIX SELECTED — checkbox helpers + fix dispatch
// ============================================================

function _visibleCheckboxes() {
    return [...document.querySelectorAll('.fix-checkbox')].filter(cb => {
        const acc = cb.closest('.val-accordion');
        return !acc || acc.style.display !== 'none';
    });
}

function updateFixButtonCount() {
    const visibleCbs = _visibleCheckboxes();
    const checked = visibleCbs.filter(cb => cb.checked).length;
    const total   = visibleCbs.length;
    const btn = document.getElementById('fix-selected-btn');
    const selectAll = document.getElementById('select-all-fixes');
    if (!btn) return;
    btn.textContent = `🔧 Fix Selected (${checked})`;
    btn.disabled = checked === 0;
    btn.style.opacity = checked === 0 ? '0.45' : '1';
    btn.style.cursor = checked === 0 ? 'not-allowed' : 'pointer';
    // Sync select-all state
    if (selectAll) {
        selectAll.indeterminate = checked > 0 && checked < total;
        selectAll.checked = total > 0 && checked === total;
    }
    // Revalidate button always reflects all accumulated fixed items
    const revalBtn = document.getElementById('reval-selected-btn');
    if (revalBtn) {
        const revalCount = _fixedItemIndices.size;
        revalBtn.style.display = revalCount > 0 ? '' : 'none';
        revalBtn.textContent = `🔄 Revalidate Fixed (${revalCount})`;
        revalBtn.disabled = revalCount === 0;
        revalBtn.style.opacity = revalCount === 0 ? '0.45' : '1';
        revalBtn.style.cursor = revalCount === 0 ? 'not-allowed' : 'pointer';
    }
}

function toggleSelectAllFixes(selectAllCb) {
    _visibleCheckboxes().forEach(cb => { cb.checked = selectAllCb.checked; });
    updateFixButtonCount();
}

function selectNeedsRevision() {
    const items = _validationState?.report?.items || [];
    const needsRevisionIndices = new Set(
        items.filter(i => i.overall_assessment?.needs_revision).map(i => i.index)
    );
    _visibleCheckboxes().forEach(cb => {
        cb.checked = needsRevisionIndices.has(parseInt(cb.dataset.index));
    });
    updateFixButtonCount();
}

// (auto-save removed — history only updated on explicit "Save to History" click)
function _autosaveClearedState() { /* no-op: kept as stub to avoid call-site errors */ }


async function fixSelectedItems() {
    if (!_validationState) return;
    const checkboxes = _visibleCheckboxes().filter(cb => cb.checked);
    if (checkboxes.length === 0) return;

    const { contentType, originalItems, sectionMap, report, course } = _validationState;
    const reportItems = (report && report.items) ? report.items : [];

    const toFix = checkboxes.map(cb => {
        const num = parseInt(cb.dataset.index); // 1-based
        const reportItem = reportItems.find(i => (i.index ?? (reportItems.indexOf(i) + 1)) === num) || {};
        const origItem = originalItems[num - 1];

        let content = '', title = '';
        if (contentType === 'lesson') {
            content = origItem?.topic_lesson || '';
            title = origItem?.topic || `Section ${num}`;
        } else {
            content = JSON.stringify(origItem || {}, null, 2);
            title = (origItem?.question || `Question ${num}`).substring(0, 80);
        }

        const v = reportItem.validator || {};
        const a = reportItem.adversarial || {};
        const oa = reportItem.overall_assessment || {};

        const issues = [
            ...(v.factual_errors || []), ...(v.missing_critical_info || []),
            ...(v.safety_concerns || []), ...(v.clarity_issues || []),
            ...(v.learning_gaps || []), ...(v.missing_high_yield || []),
            ...(v.missing_pitfalls || []), ...(v.distractor_issues || []),
            ...(v.vignette_issues || []), ...(v.explanation_issues || []),
            ...(v.asset_issues || []),
            ...(a.identified_weaknesses || []), ...(a.ambiguities || []),
            ...(a.safety_risks || []), ...(a.logical_gaps || []),
            ...(a.asset_issues || []),
        ].filter(Boolean);

        const recommendations = [
            ...(v.recommendations || []),
            ...(a.recommendations || []),
            ...(oa.recommendation ? [oa.recommendation] : []),
        ].filter(Boolean);

        // Collect missing images from both validator and adversarial (deduplicated)
        const missingImagesSet = new Set([
            ...(v.missing_images || []),
            ...(a.missing_images || []),
        ]);
        const missing_images = [...missingImagesSet].filter(Boolean);

        // Merge numbered changes_required from validator + adversarial (adversarial adds extra items)
        const vChanges = v.changes_required || [];
        const aChanges = (a.changes_required || []).filter(ac => {
            // Deduplicate: skip adversarial changes that are already covered by validator
            const acLower = ac.toLowerCase();
            return !vChanges.some(vc => {
                const vcLower = vc.toLowerCase();
                // Check for substantial overlap (shared 6+ char substring)
                return vcLower.includes(acLower.slice(3, 20)) || acLower.includes(vcLower.slice(3, 20));
            });
        });
        // Re-number the merged list
        const allChanges = [...vChanges, ...aChanges];
        const changes_required = allChanges.map((c, i) =>
            c.replace(/^\d+\.\s*/, `${i + 1}. `)
        );

        return {
            index: num, content, title, issues, recommendations, missing_images,
            changes_required,
            topic: origItem?.topic || title
        };
    });

    const btn = document.getElementById('fix-selected-btn');
    btn.disabled = true;
    btn.textContent = `⏳ Fixing ${toFix.length} item(s)…`;

    try {
        const resp = await fetch('/api/fix-content', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content_type: contentType,
                items: toFix,
                course,
                subject: lessonsData?.subject || courseStructure?.Subject || ''
            })
        });
        const result = await resp.json();
        if (!result.success) throw new Error(result.error || 'Fix failed');

        // Write fixed content back into memory
        applyFixes(result.fixed_items, contentType);

        // Show tick-off list in each fixed item's accordion
        result.fixed_items.forEach(fixedItem => {
            const { index, changes_applied, images_added } = fixedItem;
            const accordionId = `val-item-${index}`;
            const body = document.getElementById(accordionId);

            // Update accordion header badge to "🔧 Fixed"
            const accHeader = document.querySelector(`button.val-acc-header[onclick="toggleValAccordion('${accordionId}')"]`);
            if (accHeader) {
                const badgeSpan = accHeader.querySelector('span:last-child')?.previousElementSibling
                    || accHeader.querySelector('span[style*="margin-left"]');
                if (badgeSpan) {
                    badgeSpan.innerHTML = `
                        <span style="background:#28a745;color:#fff;padding:2px 10px;border-radius:12px;font-size:0.78rem;">🔧 Fixed</span>
                        <span style="font-size:0.78rem;color:#aaa;">▼</span>`;
                }
            }

            // Tick-off list of what was changed
            const tickList = (changes_applied && changes_applied.length)
                ? changes_applied.map(c => {
                    const color = c.startsWith('✅') ? '#155724' : c.startsWith('⚠️') ? '#856404' : '#721c24';
                    const bg    = c.startsWith('✅') ? '#d4edda'  : c.startsWith('⚠️') ? '#fff3cd'  : '#f8d7da';
                    return `<div style="padding:0.35rem 0.7rem;margin-bottom:0.3rem;border-radius:5px;background:${bg};color:${color};font-size:0.88rem;">${escapeHtml(c)}</div>`;
                }).join('')
                : '<p style="color:#6c757d;font-size:0.88rem;margin:0;">Changes applied.</p>';

            const imgNote = images_added > 0
                ? `<p style="margin-top:0.4rem;font-size:0.83rem;color:#6c757d;">🖼️ ${images_added} image(s) replaced/added</p>` : '';

            // If image_debug is present, show the search results inline
            const imgDebugHtml = fixedItem.image_debug
                ? `<div style="margin-top:0.75rem;">${renderImageDebugPanel(fixedItem.image_debug, '🔍 Image Search Used During Fix')}</div>`
                : '';

            if (body) {
                body.innerHTML = `
                    <div style="background:#d4edda;border:1px solid #c3e6cb;border-radius:6px;padding:0.6rem 0.75rem;margin-bottom:0.6rem;">
                        <strong style="color:#155724;font-size:0.92rem;">🔧 Fix applied — changes made:</strong>
                    </div>
                    ${tickList}${imgNote}${imgDebugHtml}
                    <p style="margin-top:0.6rem;font-size:0.82rem;color:#6c757d;">
                        Click <strong>Validate Generated</strong> to re-score these questions.
                    </p>`;
                body.style.display = 'block';
            }
        });

        const imagesAdded = result.fixed_items.reduce((s, f) => s + (f.images_added || 0), 0);
        const imgNote = imagesAdded > 0 ? ` (+${imagesAdded} image(s) replaced/added)` : '';
        showToast(`✅ Fixed ${result.fixed_items.length} item(s)${imgNote}`, 'success');

        // Track fixed indices, then clear all checkboxes so the Fix button resets
        // to 0. Revalidate uses _fixedItemIndices directly (not checkbox state).
        result.fixed_items.forEach(({ index }) => _fixedItemIndices.add(index));
        document.querySelectorAll('.fix-checkbox').forEach(cb => { cb.checked = false; });
        btn.disabled = false;
        updateFixButtonCount();

    } catch (e) {
        showToast('Fix failed: ' + e.message, 'error');
        btn.disabled = false;
        updateFixButtonCount();
    }
}

// ============================================================
// REVALIDATE SELECTED — runs validation only on checked fixed items
// ============================================================

async function revalidateSelected() {
    const btn = document.getElementById('reval-selected-btn');
    const contentType = _validationState?.contentType || 'qbank';
    const course = _validationState?.course || courseStructure?.Course || 'Unknown';

    // Revalidate all accumulated fixed items (checkboxes are for Fix selection only)
    const checkedFixed = [..._fixedItemIndices].sort((a, b) => a - b);

    if (checkedFixed.length === 0) {
        showToast('No fixed items to revalidate', 'error');
        return;
    }

    btn.disabled = true;
    btn.textContent = `⏳ Revalidating ${checkedFixed.length}…`;

    // Build items array from current in-memory questions
    const items = checkedFixed.map(idx => {
        const q = generatedQuestions[idx - 1];
        return q ? { ...q, _orig_idx: idx } : null;
    }).filter(Boolean);

    try {
        const resp = await fetch('/api/validate-content', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content_type: contentType, items, domain: 'medical education', course })
        });
        if (!resp.ok) throw new Error('Revalidation failed');
        const report = await resp.json();

        const getScoreClass = s => s >= 16 ? 'score-high' : s >= 12 ? 'score-medium' : 'score-low';
        const statusBadge = (oa) => {
            const s = oa.status || '';
            const color = s.includes('All Good') ? '#28a745' : s.includes('Conditional') ? '#ffc107' : '#dc3545';
            return `<span style="background:${color};color:#fff;padding:2px 8px;border-radius:12px;font-size:0.78rem;">${s}</span>`;
        };

        (report.items || []).forEach((item, i) => {
            const origIdx = checkedFixed[i];
            if (!origIdx) return;
            const v = item.validator || {};
            const a = item.adversarial || {};
            const oa = item.overall_assessment || {};
            const accordionId = `val-item-${origIdx}`;
            const body = document.getElementById(accordionId);

            // Update header badge
            const accHeader = document.querySelector(`button.val-acc-header[onclick="toggleValAccordion('${accordionId}')"]`);
            if (accHeader) {
                const badgeSpan = accHeader.querySelector('span[style*="margin-left"]');
                if (badgeSpan) badgeSpan.innerHTML = `
                    ${statusBadge(oa)}
                    <span class="validation-score ${getScoreClass(oa.quality_score||0)}" style="font-size:0.82rem;">${oa.quality_score??'N/A'}/20</span>
                    <span style="font-size:0.78rem;color:#aaa;">▼</span>`;
            }

            // Remove from fixed-indices set if now passing
            if (oa.quality_score >= 16 && !oa.needs_revision) {
                _fixedItemIndices.delete(origIdx);
            }

            // Update _validationState report so Fix Selected gets fresh data
            if (_validationState?.report?.items) {
                const stateItem = _validationState.report.items.find(r => r.index === origIdx);
                if (stateItem) { stateItem.validator = v; stateItem.adversarial = a; stateItem.overall_assessment = oa; }
            }

            // Build changes list
            const vC = v.changes_required || [];
            const aC = (a.changes_required || []).filter(ac =>
                !vC.some(vc => vc.toLowerCase().includes(ac.toLowerCase().slice(3,20)) ||
                               ac.toLowerCase().includes(vc.toLowerCase().slice(3,20)))
            );
            const allC = [...vC, ...aC].map((c,i)=>c.replace(/^\d+\.\s*/,`${i+1}. `));
            const changesHtml = allC.length === 0
                ? '<p style="color:#28a745;font-size:0.88rem;margin:0;">✅ No changes required — question cleared!</p>'
                : `<div style="margin:0.5rem 0;">
                    <strong style="font-size:0.88rem;">📋 Remaining changes to score above 8:</strong>
                    <ol style="margin:0.4rem 0 0 1.2rem;padding:0;font-size:0.88rem;line-height:1.7;">
                        ${allC.map(c=>`<li>${escapeHtml(c.replace(/^\d+\.\s*/,''))}</li>`).join('')}
                    </ol>
                   </div>`;

            if (body) {
                body.innerHTML = `
                    <div style="display:flex;gap:1.25rem;flex-wrap:wrap;margin-bottom:0.6rem;font-size:0.87rem;">
                        <div>✅ <strong>Validator:</strong> <span class="validation-score ${getScoreClass(v.overall_accuracy_score||0)}" style="font-size:0.78rem;">${v.overall_accuracy_score??'N/A'}/10</span></div>
                        <div>⚔️ <strong>Adversarial:</strong> <span class="validation-score ${getScoreClass(10-(a.adversarial_score||0))}" style="font-size:0.78rem;">${a.adversarial_score??'N/A'}/10</span></div>
                        <div>Revision: <strong>${oa.needs_revision ? '❌ Yes' : '✅ No'}</strong></div>
                    </div>
                    <p style="font-size:0.87rem;color:#555;margin-bottom:0.6rem;">
                        <strong>V:</strong> ${v.summary||'N/A'}<br><strong>A:</strong> ${a.summary||'N/A'}
                    </p>
                    ${changesHtml}`;
                body.style.display = 'block';
            }

            // Uncheck if cleared
            if (oa.quality_score >= 16 && !oa.needs_revision) {
                const cb = document.querySelector(`.fix-checkbox[data-index="${origIdx}"]`);
                if (cb) cb.checked = false;
            }
        });

        const passed = (report.items||[]).filter(it => (it.overall_assessment?.quality_score||0) >= 8).length;
        showToast(`Revalidation done — ${passed}/${checkedFixed.length} now 8+`, passed === checkedFixed.length ? 'success' : 'info');

    } catch (e) {
        showToast('Revalidation failed: ' + e.message, 'error');
    } finally {
        updateFixButtonCount();
    }
}

// Diff two rendered HTML strings at block level — returns new HTML with .fix-changed on altered blocks
function _diffHtmlBlocks(oldHtml, newHtml) {
    const scratch = document.createElement('div');

    scratch.innerHTML = oldHtml || '';
    const oldTexts = new Set(
        [...scratch.children].map(el => el.textContent.trim()).filter(Boolean)
    );
    const oldImgSrcs = new Set(
        [...scratch.querySelectorAll('img')].map(img => img.src)
    );

    scratch.innerHTML = newHtml || '';
    for (const el of scratch.children) {
        const text = el.textContent.trim();
        if (!text) continue;
        const imgs = [...el.querySelectorAll('img')];
        const hasNewImg = imgs.some(img => !oldImgSrcs.has(img.src));
        if (hasNewImg) {
            el.classList.add('fix-changed', 'fix-image-added');
        } else if (!oldTexts.has(text)) {
            el.classList.add('fix-changed');
        }
    }
    return scratch.innerHTML;
}

function applyFixes(fixedItems, contentType) {
    const { sectionMap } = _validationState || {};

    for (const { index, fixed_content, title } of fixedItems) {
        // 1. Write back into lessonsData / generatedQuestions
        if (contentType === 'lesson') {
            const map = sectionMap ? sectionMap[index - 1] : null;
            if (map && lessonsData && lessonsData.lessons) {
                const lessonObj = lessonsData.lessons[map.lessonIndex];
                if (map.type === 'topic') {
                    lessonObj.topic_lesson = fixed_content;
                } else {
                    const ch = lessonObj.chapters?.[map.chapterIndex];
                    if (ch) {
                        // handle both property names
                        if ('chapter_lesson' in ch) ch.chapter_lesson = fixed_content;
                        ch.lesson = fixed_content;
                    }
                }
            }
            // Also update _validationState.originalItems so next fix uses latest
            if (_validationState && _validationState.originalItems[index - 1]) {
                _validationState.originalItems[index - 1].topic_lesson = fixed_content;
            }
        } else {
            try {
                const parsed = JSON.parse(fixed_content);
                generatedQuestions[index - 1] = parsed;
                if (_validationState && _validationState.originalItems[index - 1]) {
                    _validationState.originalItems[index - 1] = parsed;
                }
                // Also re-render the card in the QBank tab so it shows the fixed version
                const qbankCard = document.querySelector(`#results .question-card[data-q-index="${index}"]`);
                if (qbankCard) {
                    qbankCard.outerHTML = renderQuestionCard(parsed, index - 1);
                }
            } catch (e) { /* keep original if JSON fails */ }
        }

        // 2. Refresh the live lesson/question DOM, highlighting what changed
        if (contentType === 'lesson') {
            const map = sectionMap ? sectionMap[index - 1] : null;
            if (map) {
                let el, newHtml;
                if (map.type === 'topic') {
                    el = document.querySelector(`#topic-${map.lessonIndex}-topic .lesson-text`);
                    newHtml = formatLessonContent(
                        fixed_content,
                        lessonsData?.lessons?.[map.lessonIndex]?.chapters,
                        `topic-${map.lessonIndex}`
                    );
                } else {
                    el = document.querySelector(`#topic-${map.lessonIndex}-chapter-${map.chapterIndex} .lesson-text`);
                    newHtml = formatLessonContent(fixed_content);
                }
                if (el) {
                    el.innerHTML = _diffHtmlBlocks(el.innerHTML, newHtml);
                }
            }
        } else {
            // QBank: capture old question before overwrite, then highlight changed fields
            const origIdx = index - 1;
            const oldQ = { ...(generatedQuestions[origIdx] || {}) }; // snapshot before write
            const q = _validationState?.originalItems?.[origIdx];
            const card = document.querySelectorAll('.question-card')[origIdx];
            if (card && q) {
                const diffLabels = { 1: 'Medium', 2: 'Hard', 3: 'Very Hard' };
                const ch = (newVal, oldVal) => newVal !== oldVal ? ' fix-changed' : '';
                const optCh = (opt) => !(oldQ.options || []).includes(opt) ? ' fix-changed' : '';
                const imgAdded = q.image_url && !oldQ.image_url;

                card.innerHTML = `
                    <div class="question-header">
                        <span class="question-number">Q${index}</span>
                        <div class="question-tags">
                            <span class="tag tag-bloom">Bloom's L${q.blooms_level}</span>
                            <span class="tag tag-difficulty">${diffLabels[q.difficulty]||''}</span>
                            ${(q.image_url||q.image_description) ? '<span class="tag tag-image">Image</span>' : ''}
                            <span style="background:#28a745;color:#fff;padding:1px 8px;border-radius:10px;font-size:0.75rem;">🔧 Fixed</span>
                            ${(q.tags||[]).map(t => `<span class="tag tag-exam">${t}</span>`).join('')}
                        </div>
                    </div>
                    ${q.image_url
                        ? `<div class="question-image${imgAdded ? ' fix-changed fix-image-added' : ''}"><img src="${q.image_url}" alt="${q.image_description||''}" loading="lazy"></div>`
                        : ''}
                    <p class="question-text${ch(q.question, oldQ.question)}">${q.question}</p>
                    <ul class="options-list">
                        ${(q.options||[]).map(opt =>
                            `<li class="${opt===q.correct_option?'correct':''}${optCh(opt)}">${opt}</li>`
                        ).join('')}
                    </ul>
                    <div class="explanation${ch(q.explanation, oldQ.explanation)}"><strong>Explanation:</strong> ${q.explanation||''}</div>`;
            }
        }

        // 3. Show "re-validating" spinner in validation accordion body
        const accordionId = `val-item-${index}`;
        const body = document.getElementById(accordionId);
        if (body) {
            body.innerHTML = `
                <div style="text-align:center;padding:1.5rem;color:#999;">
                    <div class="loading-spinner" style="margin:0 auto 0.75rem;"></div>
                    <p style="margin:0;font-size:0.9rem;">Re-validating fixed content…</p>
                </div>`;
            body.style.display = 'block';
        }
    }
}

async function revalidateFixed(fixedIndices, contentType, course) {
    // Build mini-batch from the now-updated _validationState.originalItems
    const { originalItems, sectionMap } = _validationState || {};
    if (!originalItems) return;

    // items to send: just the fixed ones, in order
    // We track the mapping: sent position → original accordion index
    const miniItems = [];
    const indexMap  = []; // indexMap[sent-0-based] = original 1-based accordion index

    for (const origIdx of fixedIndices) {         // origIdx is 1-based
        const item = originalItems[origIdx - 1];
        if (!item) continue;
        miniItems.push(item);
        indexMap.push(origIdx);
    }
    if (miniItems.length === 0) return;

    try {
        const resp = await fetch('/api/validate-content', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content_type: contentType,
                items: miniItems,
                domain: 'medical education',
                course
            })
        });
        const report = await resp.json();
        const returnedItems = report.items || [];

        // Patch each fixed accordion with the fresh result
        returnedItems.forEach((item, sentIdx) => {
            const origIdx = indexMap[sentIdx]; // original 1-based
            if (!origIdx) return;

            const v  = item.validator || {};
            const a  = item.adversarial || {};
            const oa = item.overall_assessment || {};
            const accordionId = `val-item-${origIdx}`;
            const body = document.getElementById(accordionId);

            const getScoreClass = s => s >= 16 ? 'score-high' : s >= 12 ? 'score-medium' : 'score-low';
            const formatList = arr => arr && arr.length
                ? `<ul class="validation-list">${arr.map(i => `<li>${i}</li>`).join('')}</ul>`
                : '';
            const status = oa.status || '';
            const badgeColor = status.includes('All Good') ? '#28a745' : status.includes('Conditional') ? '#ffc107' : '#dc3545';

            // Update the header badge + score
            const accBtn = document.querySelector(`[onclick="toggleValAccordion('${accordionId}')"]`);
            if (accBtn) {
                const badgeArea = accBtn.querySelector('span[style*="margin-left"]');
                if (badgeArea) badgeArea.innerHTML = `
                    <span style="background:${badgeColor};color:#fff;padding:2px 10px;border-radius:12px;font-size:0.8rem;">${status}</span>
                    <span class="validation-score ${getScoreClass(oa.quality_score || 0)}" style="font-size:0.85rem;">${oa.quality_score || 'N/A'}/20</span>
                    <span style="font-size:0.8rem;color:#999;">▼</span>`;
            }

            // Update accordion body with fresh results (content-type aware)
            if (body) {
                const allClear = status.includes('All Good');
                const isQBank = contentType === 'qbank';
                body.innerHTML = `
                    <div style="background:${allClear ? '#d4edda' : '#fff3cd'};border:1px solid ${allClear ? '#c3e6cb' : '#ffc107'};border-radius:6px;padding:0.75rem;margin-bottom:0.75rem;">
                        <strong style="color:${allClear ? '#155724' : '#856404'};">${allClear ? '✅ Re-validated — Approved after fix' : '⚠️ Re-validated — still needs attention'}</strong>
                    </div>

                    <!-- Score row -->
                    <div style="display:flex;gap:1.5rem;flex-wrap:wrap;margin-bottom:0.75rem;font-size:0.9rem;">
                        <div>✅ <strong>Validator:</strong>
                            <span class="validation-score ${getScoreClass(v.overall_accuracy_score||0)}" style="font-size:0.8rem;">${v.overall_accuracy_score??'N/A'}/10</span>
                        </div>
                        ${isQBank ? `<div>Answer verified: <strong>${v.correct_answer_verified ? 'Yes ✅' : 'No ❌'}</strong></div>` : ''}
                        <div>⚔️ <strong>Adversarial:</strong>
                            <span class="validation-score ${getScoreClass(10-(a.adversarial_score||0))}" style="font-size:0.8rem;">${a.adversarial_score??'N/A'}/10</span>
                            &nbsp;<em style="font-size:0.8rem;color:#666;">${a.breakability_rating||''}</em>
                        </div>
                        <div>Needs revision: <strong>${oa.needs_revision ? 'Yes ❌' : 'No ✅'}</strong></div>
                    </div>

                    <!-- Validator -->
                    <p style="margin-bottom:0.5rem;"><strong>Validator Summary:</strong> ${v.summary||'N/A'}</p>
                    ${v.factual_errors?.length       ? `<h4 style="color:#dc3545;margin-top:0.5rem;">⚠️ Remaining Factual Errors</h4>${formatList(v.factual_errors)}` : ''}
                    ${v.missing_critical_info?.length? `<h4 style="color:#ffc107;margin-top:0.5rem;">📌 Missing Critical Info</h4>${formatList(v.missing_critical_info)}` : ''}
                    ${v.safety_concerns?.length      ? `<h4 style="color:#dc3545;margin-top:0.5rem;">🚨 Safety Concerns</h4>${formatList(v.safety_concerns)}` : ''}
                    ${v.clarity_issues?.length       ? `<h4 style="color:#17a2b8;margin-top:0.5rem;">💭 Clarity Issues</h4>${formatList(v.clarity_issues)}` : ''}
                    ${!isQBank && v.learning_gaps?.length      ? `<h4 style="color:#e83e8c;margin-top:0.5rem;">🧠 Learning Gaps</h4>${formatList(v.learning_gaps)}` : ''}
                    ${!isQBank && v.missing_high_yield?.length ? `<h4 style="color:#fd7e14;margin-top:0.5rem;">⭐ Missing High-Yield</h4>${formatList(v.missing_high_yield)}` : ''}
                    ${isQBank && v.distractor_issues?.length   ? `<h4 style="color:#ffc107;margin-top:0.5rem;">🎯 Distractor Issues</h4>${formatList(v.distractor_issues)}` : ''}
                    ${isQBank && v.vignette_issues?.length     ? `<h4 style="color:#ffc107;margin-top:0.5rem;">🗒️ Vignette Issues</h4>${formatList(v.vignette_issues)}` : ''}
                    ${isQBank && v.explanation_issues?.length  ? `<h4 style="color:#ffc107;margin-top:0.5rem;">📝 Explanation Issues</h4>${formatList(v.explanation_issues)}` : ''}
                    ${v.asset_issues?.length         ? `<h4 style="color:#6c757d;margin-top:0.5rem;">🖼️ Image / Asset Issues</h4>${formatList(v.asset_issues)}` : ''}
                    ${v.missing_images?.length       ? `<h4 style="color:#8b5cf6;margin-top:0.5rem;">🖼️➕ Missing Images (recommended)</h4>${formatList(v.missing_images)}` : ''}
                    ${v.recommendations?.length      ? `<h4 style="color:#28a745;margin-top:0.5rem;">💡 Validator Recommendations</h4>${formatList(v.recommendations)}` : ''}

                    <!-- Adversarial -->
                    <hr style="margin:0.75rem 0;border-color:#e0e0e0;">
                    <p style="margin-bottom:0.5rem;"><strong>Adversarial Summary:</strong> ${a.summary||'N/A'}</p>
                    ${a.identified_weaknesses?.length ? `<h4 style="color:#dc3545;margin-top:0.5rem;">🔍 Remaining Weaknesses</h4>${formatList(a.identified_weaknesses)}` : ''}
                    ${a.ambiguities?.length           ? `<h4 style="color:#ffc107;margin-top:0.5rem;">❓ Ambiguities</h4>${formatList(a.ambiguities)}` : ''}
                    ${isQBank && a.alternative_answers?.length ? `<h4 style="color:#dc3545;margin-top:0.5rem;">🔀 Alternative Defensible Answers</h4>${formatList(a.alternative_answers)}` : ''}
                    ${a.safety_risks?.length          ? `<h4 style="color:#dc3545;margin-top:0.5rem;">⚠️ Safety Risks</h4>${formatList(a.safety_risks)}` : ''}
                    ${a.asset_issues?.length          ? `<h4 style="color:#6c757d;margin-top:0.5rem;">🖼️ Asset Issues (adversarial)</h4>${formatList(a.asset_issues)}` : ''}
                    ${a.missing_images?.length        ? `<h4 style="color:#8b5cf6;margin-top:0.5rem;">🖼️➕ Missing Images (adversarial)</h4>${formatList(a.missing_images)}` : ''}
                    ${a.recommendations?.length       ? `<h4 style="color:#28a745;margin-top:0.5rem;">💡 Adversarial Recommendations</h4>${formatList(a.recommendations)}` : ''}

                    <div style="margin-top:0.75rem;padding:0.6rem;background:#f8f9fa;border-radius:4px;font-size:0.9rem;">
                        <strong>Assessment:</strong> ${oa.recommendation||'N/A'}
                    </div>`;
                body.style.display = 'block';
            }

            // Remove from fixed-indices set if now passing
            if (oa.quality_score >= 16 && !oa.needs_revision) {
                _fixedItemIndices.delete(origIdx);
            }

            // Also update report in _validationState so future fix uses fresh issues
            if (_validationState && _validationState.report) {
                const ri = (_validationState.report.items || []).findIndex(
                    r => (r.index ?? 0) === origIdx
                );
                if (ri >= 0) _validationState.report.items[ri] = { ...item, index: origIdx };
            }
        });

        const approved = returnedItems.filter(i => (i.overall_assessment?.status || '').includes('All Good')).length;
        showToast(`Re-validation: ${approved}/${returnedItems.length} now Approved`, approved === returnedItems.length ? 'success' : 'info');

    } catch (e) {
        console.error('Re-validation error:', e);
        showToast('Re-validation failed: ' + e.message, 'error');
    }
}

// ============================================================
// UPLOAD & VALIDATE — parse an uploaded JSON or MD file
// ============================================================

async function runUploadValidation(items, contentType, course) {
    const modal = document.getElementById('validation-modal');
    const reportContent = document.getElementById('validation-report-content');

    // For lessons, flatten topic + chapters into individual sections
    let sendItems = items;
    let sectionMap = null;
    if (contentType === 'lesson') {
        const flat = flattenLessonsToSections(items);
        sendItems = flat.sections;
        sectionMap = flat.sectionMap;
    }
    _validationState = { contentType, originalItems: sendItems, sectionMap, course };

    reportContent.innerHTML = `
        <div class="loading-spinner"></div>
        <p style="text-align:center;color:#999;margin-top:1rem;">Running Council of Models validation on ${sendItems.length} ${contentType === 'qbank' ? 'question(s)' : 'section(s)'}...</p>
        <p style="text-align:center;color:#999;font-size:0.9rem;">Validator &amp; Adversarial running in parallel — est. 60–90 sec</p>
    `;
    modal.style.display = 'block';

    try {
        const response = await fetch('/api/validate-content', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content_type: contentType,
                items: sendItems,
                domain: 'medical education',
                course: course || 'Uploaded Document'
            })
        });
        if (!response.ok) throw new Error('Validation request failed');
        const report = await response.json();
        displayBatchValidationReport(report, contentType);
    } catch (err) {
        reportContent.innerHTML = `
            <div style="text-align:center;padding:2rem;">
                <h3 style="color:#dc3545;">❌ Validation Error</h3>
                <p>${err.message}</p>
            </div>`;
    }
}

function parseQBankJSON(data) {
    // Accept: array, { questions: [] }, { items: [] }, { qbank: [] }
    if (Array.isArray(data)) return data;
    if (Array.isArray(data.questions)) return data.questions;
    if (Array.isArray(data.items)) return data.items;
    if (Array.isArray(data.qbank)) return data.qbank;
    return [];
}

function parseLessonsJSON(data) {
    // Accept: { lessons: [] }, array, { topics: [] }
    if (Array.isArray(data)) return data;
    if (Array.isArray(data.lessons)) return data.lessons;
    if (Array.isArray(data.topics)) return data.topics;
    return [];
}

function parseQBankMarkdown(text) {
    // Split on Q-number patterns: "Q1.", "Q1:", "**Q1.**", "## Q1", "Question 1"
    const blocks = text.split(/(?=(?:^|\n)(?:#{1,3}\s*)?(?:Q\d+[\.\:\)]\s*|Question\s+\d+[\.\:\)]\s*))/i).filter(b => b.trim());
    return blocks.map((block, idx) => {
        const lines = block.trim().split('\n').map(l => l.trim()).filter(Boolean);
        // Extract question stem (lines before options)
        const optionLineIdx = lines.findIndex(l => /^[A-E][\.\)]\s+/i.test(l));
        const questionLines = optionLineIdx > 0 ? lines.slice(0, optionLineIdx) : lines.slice(0, 2);
        const question = questionLines.join(' ').replace(/^(?:#{1,3}\s*)?(?:Q\d+[\.\:\)]\s*|Question\s+\d+[\.\:\)]\s*)/i, '').trim();

        // Extract options
        const options = [];
        let correctLine = -1, explLine = -1;
        lines.forEach((l, i) => {
            if (/^[A-E][\.\)]\s+/i.test(l)) options.push(l.replace(/^[A-E][\.\)]\s+/i, '').trim());
            if (/correct\s*(?:answer|option)?[:=\s]/i.test(l)) correctLine = i;
            if (/explanation[:]/i.test(l)) explLine = i;
        });

        const correct_option = correctLine >= 0
            ? lines[correctLine].replace(/correct\s*(?:answer|option)?[:=\s]/i, '').trim()
            : '';
        const explanation = explLine >= 0
            ? lines.slice(explLine).join(' ').replace(/explanation[:]/i, '').trim()
            : '';

        return { question: question || `Question ${idx + 1}`, options, correct_option, explanation, tags: [], blooms_level: '', difficulty: '' };
    }).filter(q => q.question);
}

function parseLessonsMarkdown(text) {
    // Detect our app's structured lesson format (has 📖 / 📝 emoji markers)
    const hasDetailedLesson = text.includes('📖 Detailed Lesson');
    const hasChapterRevision = text.includes('📝 Chapter-Level Rapid Revision');

    if (hasDetailedLesson || hasChapterRevision) {
        // --- Our app's exported lesson format ---
        // Structure: ## Topic N: Name → ### 📖 Detailed Lesson → ... → ### 📝 Chapter-Level Rapid Revision → ### Chapter1 → ...
        const items = [];

        // Topic name from first "## ..." heading
        const topicMatch = text.match(/^##\s+(.+)/m);
        const topicName = topicMatch ? topicMatch[1].trim() : 'Topic Lesson';

        // Locate the lesson-body bounds
        const lessonMarkerIdx  = hasDetailedLesson  ? text.indexOf('📖 Detailed Lesson')           : -1;
        const chapterDividerIdx = hasChapterRevision ? text.indexOf('📝 Chapter-Level Rapid Revision') : -1;

        // Topic lesson body: from the "### 📖" line up to (not including) "### 📝" line
        const lessonLineStart = lessonMarkerIdx !== -1
            ? text.lastIndexOf('\n', lessonMarkerIdx)  // newline before "### 📖"
            : 0;
        const lessonLineEnd = chapterDividerIdx !== -1
            ? text.lastIndexOf('\n', chapterDividerIdx)  // newline before "### 📝"
            : text.length;

        const lessonBody = text.slice(lessonLineStart, lessonLineEnd).trim();
        if (lessonBody) {
            items.push({ topic: topicName, topic_lesson: lessonBody, chapters: [] });
        }

        // Individual chapters: everything after the "### 📝 ..." divider line
        if (chapterDividerIdx !== -1) {
            const dividerLineEnd = text.indexOf('\n', chapterDividerIdx);
            const chaptersText   = dividerLineEnd !== -1 ? text.slice(dividerLineEnd + 1) : '';

            // Split on "### " at the start of a line — each is one chapter
            const chapterSections = chaptersText.split(/(?=^###\s)/m).filter(s => s.trim());

            for (const section of chapterSections) {
                const sectionLines = section.trim().split('\n');
                const title = sectionLines[0].replace(/^###\s*/, '').trim();
                const body  = sectionLines.slice(1).join('\n').trim();
                if (title && body) {
                    items.push({ topic: title, topic_lesson: body, chapters: [] });
                }
            }
        }

        return items;
    }

    // --- Generic markdown: split on the dominant heading level ---
    const h2count = (text.match(/^## /gm)  || []).length;
    const h3count = (text.match(/^### /gm) || []).length;
    const splitOn3 = h3count > 0 && h3count >= h2count;
    const splitPattern = splitOn3 ? /(?=^###\s)/m : /(?=^#{1,2}\s)/m;

    const sections = text.split(splitPattern).filter(s => s.trim());
    return sections.map((section, idx) => {
        const lines = section.trim().split('\n');
        const titleLine = lines[0].replace(/^#{1,3}\s*/, '').trim();
        const body = lines.slice(1).join('\n').trim();
        return { topic: titleLine || `Section ${idx + 1}`, topic_lesson: body, chapters: [] };
    }).filter(s => s.topic_lesson);
}

// Upload & Validate — Lessons
const uploadValidateLessonsBtn = document.getElementById('upload-validate-lessons-btn');
const uploadLessonsFile = document.getElementById('upload-lessons-file');

if (uploadValidateLessonsBtn && uploadLessonsFile) {
    uploadValidateLessonsBtn.addEventListener('click', () => uploadLessonsFile.click());

    uploadLessonsFile.addEventListener('change', async () => {
        const file = uploadLessonsFile.files[0];
        if (!file) return;
        uploadLessonsFile.value = ''; // reset so same file can be re-uploaded

        const text = await file.text();
        let items = [];
        let course = file.name.replace(/\.[^.]+$/, '');

        if (file.name.endsWith('.json')) {
            try {
                const data = JSON.parse(text);
                items = parseLessonsJSON(data);
                if (data.course) course = data.course;
            } catch {
                showToast('Invalid JSON file', 'error');
                return;
            }
        } else if (file.name.endsWith('.md')) {
            items = parseLessonsMarkdown(text);
        }

        if (!items.length) {
            showToast('No lesson sections found in the file', 'error');
            return;
        }

        await runUploadValidation(items, 'lesson', course);
    });
}

// Upload & Validate — QBank
const uploadValidateQBankBtn = document.getElementById('upload-validate-qbank-btn');
const uploadQBankFile = document.getElementById('upload-qbank-file');

if (uploadValidateQBankBtn && uploadQBankFile) {
    uploadValidateQBankBtn.addEventListener('click', () => uploadQBankFile.click());

    uploadQBankFile.addEventListener('change', async () => {
        const file = uploadQBankFile.files[0];
        if (!file) return;
        uploadQBankFile.value = '';

        const text = await file.text();
        let items = [];
        let course = file.name.replace(/\.[^.]+$/, '');

        if (file.name.endsWith('.json')) {
            try {
                const data = JSON.parse(text);
                items = parseQBankJSON(data);
                if (data.course) course = data.course;
            } catch {
                showToast('Invalid JSON file', 'error');
                return;
            }
        } else if (file.name.endsWith('.md')) {
            items = parseQBankMarkdown(text);
        }

        if (!items.length) {
            showToast('No questions found in the file', 'error');
            return;
        }

        await runUploadValidation(items, 'qbank', course);
    });
}

// ── History Tab ─────────────────────────────────────────────────────────────

async function loadSessionHistory() {
    const listEl = document.getElementById('history-list');
    if (!listEl) return;
    listEl.innerHTML = '<p class="empty-state">Loading...</p>';
    try {
        const res = await fetch('/api/sessions');
        if (!res.ok) throw new Error('Failed to fetch sessions');
        const sessions = await res.json();
        renderSessionList(sessions, listEl);
    } catch (e) {
        listEl.innerHTML = '<p class="empty-state">Could not load history.</p>';
    }
}

function renderSessionList(sessions, listEl) {
    if (!sessions || sessions.length === 0) {
        listEl.innerHTML = '<p class="empty-state">No saved generations yet. Generate some questions first!</p>';
        return;
    }
    listEl.innerHTML = '';
    sessions.forEach(s => {
        const date = s.created_at ? new Date(s.created_at).toLocaleString() : s.session_id;
        const topicsStr = (s.topics || []).slice(0, 3).join(', ') + (s.topics && s.topics.length > 3 ? ` +${s.topics.length - 3} more` : '');
        const card = document.createElement('div');
        card.className = 'history-card';
        const isLesson = s.type === 'lessons';
        const icon = isLesson ? '📚' : '📋';
        const badge = isLesson ? `${s.lesson_count || 0} Lessons` : `${s.question_count || 0} Qs`;
        card.innerHTML = `
            <div class="history-card-icon">${icon}</div>
            <div class="history-card-body">
                <div class="history-card-title">${escapeHtml(s.course || 'Unknown')} — ${escapeHtml(s.subject || '')}</div>
                <div class="history-card-meta">${escapeHtml(topicsStr)} &bull; ${date}</div>
            </div>
            <span class="history-card-badge">${badge}</span>
            <button class="history-card-delete" title="Delete session" data-id="${escapeHtml(s.session_id)}">🗑</button>
        `;
        // Load session on card click (not delete button)
        card.addEventListener('click', (e) => {
            if (e.target.closest('.history-card-delete')) return;
            openHistorySession(s.session_id);
        });
        card.querySelector('.history-card-delete').addEventListener('click', async (e) => {
            e.stopPropagation();
            if (!confirm('Delete this session?')) return;
            await deleteHistorySession(s.session_id, card);
        });
        listEl.appendChild(card);
    });
}

async function openHistorySession(sessionId) {
    showToast('Loading session...', 'info');
    try {
        const res = await fetch(`/api/sessions/${sessionId}`);
        if (!res.ok) throw new Error('Session not found');
        const data = await res.json();
        const courseName = data.course || 'Restored';

        // Switch to Generator tab first
        const mainBtn = document.querySelector('[data-tab="main"]');
        if (mainBtn) mainBtn.click();

        if (data.type === 'lessons') {
            const lessonsPayload = data.lessons_data;
            if (!lessonsPayload || !lessonsPayload.lessons?.length) {
                showToast('Session has no lessons', 'error'); return;
            }
            lessonsData = lessonsPayload;
            displayLessons(lessonsPayload);
            lastLessonsSaveMeta = { lessons_data: lessonsPayload, course: courseName, subject: data.subject || '' };
            currentLessonsSessionId = sessionId; // subsequent saves update this entry
            lastLessonsRegenerateFn = null; // Can't replay without original form state
            showResultTab('lessons');
            showToast(`Loaded ${lessonsPayload.lessons.length} lessons from ${courseName}`, 'success');
        } else {
            const questions = data.questions || [];
            if (!questions.length) { showToast('Session has no questions', 'error'); return; }
            generatedQuestions = questions;
            displayResults(questions, courseName);
            lastSaveMeta = { course: courseName, subject: data.subject || '', topics: data.topics || [] };
            currentQBankSessionId = sessionId; // subsequent saves update this entry
            lastRegenerateFn = null; // Can't replay without original form state
            showResultTab('qbank');
            const moreBar = document.getElementById('generate-more-bar');
            if (moreBar) moreBar.style.display = 'block';
            showToast(`Loaded ${questions.length} questions from ${courseName}`, 'success');
        }
    } catch (e) {
        showToast('Failed to load session', 'error');
    }
}

async function deleteHistorySession(sessionId, cardEl) {
    try {
        const res = await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Delete failed');
        cardEl.remove();
        const listEl = document.getElementById('history-list');
        if (listEl && !listEl.querySelector('.history-card')) {
            listEl.innerHTML = '<p class="empty-state">No saved generations yet. Generate some questions first!</p>';
        }
        showToast('Session deleted', 'info');
    } catch (e) {
        showToast('Failed to delete session', 'error');
    }
}

// Wire up the manual Refresh button in the History tab
const historyRefreshBtn = document.getElementById('history-refresh-btn');
if (historyRefreshBtn) {
    historyRefreshBtn.addEventListener('click', loadSessionHistory);
}

// ── Mock Exam Paper ──────────────────────────────────────────────────────────

let mockExamSpecs = null; // cached specs from /api/mock-exam-specs

// Mode toggle: Topic Generator ↔ Mock Exam
document.querySelectorAll('.gen-mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const mode = btn.dataset.mode;
        document.querySelectorAll('.gen-mode-btn').forEach(b => {
            b.style.background = 'var(--bg-secondary)';
            b.style.color = 'var(--text)';
        });
        btn.style.background = 'var(--primary)';
        btn.style.color = 'white';
        document.getElementById('topic-generator-panel').style.display = mode === 'topic' ? '' : 'none';
        document.getElementById('mock-exam-panel').style.display = mode === 'mock' ? '' : 'none';
    });
});

// Fetch official exam pattern
const fetchMockSpecsBtn = document.getElementById('fetch-mock-specs-btn');
const mockSpecsStatus = document.getElementById('mock-specs-status');
const mockSpecsPanel = document.getElementById('mock-specs-panel');
const generateMockBtn = document.getElementById('generate-mock-btn');
const mockProgress = document.getElementById('mock-progress');

if (fetchMockSpecsBtn) {
    fetchMockSpecsBtn.addEventListener('click', async () => {
        if (!courseStructure) {
            showToast('Generate course structure first', 'error');
            return;
        }
        const course = courseStructure.Course || document.getElementById('lesson-course')?.value.trim();
        if (!course) { showToast('No course name found', 'error'); return; }

        const subjects = (courseStructure.subjects || []).map(s => s.name);

        fetchMockSpecsBtn.disabled = true;
        mockSpecsStatus.textContent = '⏳ Searching official blueprints…';
        if (mockSpecsPanel) mockSpecsPanel.style.display = 'none';
        if (generateMockBtn) generateMockBtn.disabled = true;

        try {
            const res = await fetch('/api/mock-exam-specs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ course, subjects })
            });
            if (!res.ok) throw new Error(await res.text());
            mockExamSpecs = await res.json();
            renderMockSpecs(mockExamSpecs);
            mockSpecsStatus.textContent = '✓ Exam pattern loaded';
            if (generateMockBtn) generateMockBtn.disabled = false;
            const adjustSection = document.getElementById('mock-adjust-section');
            if (adjustSection) adjustSection.style.display = 'block';
        } catch (e) {
            mockSpecsStatus.textContent = '✗ Could not fetch specs — check console';
            console.error(e);
            showToast('Failed to fetch exam specs', 'error');
        } finally {
            fetchMockSpecsBtn.disabled = false;
        }
    });
}

function renderMockSpecs(specs) {
    if (!mockSpecsPanel) return;
    mockSpecsPanel.style.display = 'block';

    // Summary stat cards
    const summary = document.getElementById('mock-specs-summary');
    if (summary) {
        summary.innerHTML = [
            { label: 'Total Questions', value: specs.total_questions ?? '—' },
            { label: 'Duration', value: specs.time_minutes ? `${specs.time_minutes} min` : '—' },
            { label: 'Options', value: specs.num_options ? `${specs.num_options} options` : '—' },
            { label: 'Image Qs', value: specs.image_questions_total ? `~${specs.image_questions_total}` : '—' },
            { label: 'Scoring', value: specs.scoring_note || specs.negative_marking || '—' },
        ].map(c => `
            <div class="mock-stat-card">
                <div class="label">${c.label}</div>
                <div class="value">${escapeHtml(String(c.value))}</div>
            </div>
        `).join('');
    }

    // Subject distribution table
    const table = document.getElementById('mock-subject-table');
    if (!table) return;
    const dist = specs.subject_distribution || {};
    const rows = Object.entries(dist)
        .sort((a, b) => b[1].questions - a[1].questions);
    const maxQ = rows[0]?.[1].questions || 1;

    table.innerHTML = rows.map(([subj, d]) => `
        <div class="mock-dist-row">
            <div>
                <div style="font-weight:500;">${escapeHtml(subj)}</div>
                <div class="mock-dist-bar-wrap" style="margin-top:4px; width:100%;">
                    <div class="mock-dist-bar" style="width:${Math.round(d.questions/maxQ*100)}%;"></div>
                </div>
            </div>
            <div style="color:var(--text-muted); font-size:0.82rem;">${d.percentage ?? ''}%</div>
            <div style="font-weight:600; color:var(--primary);">${d.questions} Q</div>
        </div>
    `).join('');

    if (specs.exam_notes) {
        table.insertAdjacentHTML('afterend',
            `<p style="margin-top:0.75rem; font-size:0.82rem; color:var(--text-muted);">${escapeHtml(specs.exam_notes)}</p>`);
    }

}

// Mock specs adjustment chat
(function () {
    const sendBtn = document.getElementById('mock-adjust-send-btn');
    const input = document.getElementById('mock-adjust-input');
    const messages = document.getElementById('mock-adjust-messages');

    function addAdjustMsg(role, text) {
        if (!messages) return;
        messages.style.display = 'block';
        const div = document.createElement('div');
        div.className = 'adjust-msg ' + role;
        div.textContent = text;
        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight;
    }

    async function sendAdjust() {
        const text = input?.value.trim();
        if (!text || !mockExamSpecs) return;
        input.value = '';
        addAdjustMsg('user', text);
        if (sendBtn) { sendBtn.disabled = true; sendBtn.textContent = '⏳'; }

        try {
            const res = await fetch('/api/adjust-mock-specs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ specs: mockExamSpecs, message: text })
            });
            if (!res.ok) throw new Error(await res.text());
            const updated = await res.json();
            const reply = updated.response || 'Done — specs updated.';
            delete updated.response;
            mockExamSpecs = updated;
            renderMockSpecs(mockExamSpecs);
            addAdjustMsg('assistant', reply);
            showToast('Exam pattern updated', 'success');
        } catch (e) {
            addAdjustMsg('assistant', 'Error: ' + e.message);
        } finally {
            if (sendBtn) { sendBtn.disabled = false; sendBtn.textContent = 'Update'; }
            input?.focus();
        }
    }

    if (sendBtn) sendBtn.addEventListener('click', sendAdjust);
    if (input) {
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendAdjust(); }
        });
    }
})();

// Generate the full mock exam paper — parallel professor agents via SSE
if (generateMockBtn) {
    generateMockBtn.addEventListener('click', async () => {
        if (!courseStructure || !mockExamSpecs) {
            showToast('Load exam pattern first', 'error'); return;
        }
        const dist = mockExamSpecs.subject_distribution || {};
        if (!Object.keys(dist).length) { showToast('No subject distribution in specs', 'error'); return; }

        const course = courseStructure.Course || document.getElementById('lesson-course')?.value.trim() || '';

        generateMockBtn.disabled = true;
        if (fetchMockSpecsBtn) fetchMockSpecsBtn.disabled = true;
        loading.style.display = 'flex';

        // Build subject progress tracker
        const subjectStatus = {};  // subject → {done, count}
        const totalSubjects = Object.keys(dist).length;

        function _updateProgress(msg) {
            mockProgress.textContent = msg;
            document.getElementById('loading-message').textContent = msg;
        }
        _updateProgress('Preparing parallel professor agents…');

        let allQuestions = [];

        try {
            const res = await fetch('/api/generate-mock-paper', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    course_name:      course,
                    mock_specs:       mockExamSpecs,
                    course_structure: courseStructure,
                    exam_format:      courseStructure?.exam_format || selectedExamFormat || {},
                })
            });

            if (!res.ok) { throw new Error(await res.text()); }

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buf = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buf += decoder.decode(value, { stream: true });
                const lines = buf.split('\n');
                buf = lines.pop();  // keep incomplete line

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    let evt;
                    try { evt = JSON.parse(line.slice(6)); } catch { continue; }

                    if (evt.type === 'tasks_ready') {
                        _updateProgress(`Starting ${evt.task_count} professor agents in parallel for ${evt.total_questions} questions…`);

                    } else if (evt.type === 'subject_done') {
                        subjectStatus[evt.subject] = { done: true, count: evt.count };
                        const doneCount = Object.values(subjectStatus).filter(s => s.done).length;
                        const totalSoFar = Object.values(subjectStatus).reduce((a, s) => a + s.count, 0);
                        _updateProgress(`[${doneCount}/${evt.total_subjects}] ${evt.subject} done (${evt.count} Qs) — ${totalSoFar} total so far`);

                    } else if (evt.type === 'subject_error') {
                        showToast(`${evt.subject}: ${evt.error}`, 'error');

                    } else if (evt.type === 'status') {
                        _updateProgress(evt.message);

                    } else if (evt.type === 'complete') {
                        allQuestions = evt.questions || [];

                    } else if (evt.type === 'error') {
                        throw new Error(evt.message);
                    }
                }
            }

            if (!allQuestions.length) throw new Error('No questions generated');

            const total = mockExamSpecs.total_questions;
            if (total && allQuestions.length > total) allQuestions = allQuestions.slice(0, total);

            generatedQuestions = allQuestions;
            displayResults(allQuestions, `${course} — Mock Exam`);
            showResultTab('qbank');
            mockProgress.textContent = `✓ Generated ${allQuestions.length} questions`;
            showToast(`Mock exam ready: ${allQuestions.length} questions`, 'success');
            lastSaveMeta = { course, subject: 'Mock Exam', topics: Object.keys(dist) };
            currentQBankSessionId = null;
            lastRegenerateFn = () => generateMockBtn.click();

        } catch (err) {
            showToast(err.message || 'Error generating mock exam', 'error');
            console.error(err);
        } finally {
            loading.style.display = 'none';
            generateMockBtn.disabled = false;
            if (fetchMockSpecsBtn) fetchMockSpecsBtn.disabled = false;
        }
    });
}

// Helper: trigger server-side session save after mock exam generation
async function save_qbank_session_frontend(questions, course, subject, topics) {
    try {
        await fetch('/api/sessions/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ questions, course, subject, topics })
        });
    } catch (_) { /* non-critical */ }
}

// ── PYQ / Reference Document Upload ─────────────────────────────────────────

let pyqReferenceExamples = [];   // parsed question dicts
let pyqReferenceText    = '';    // raw text fallback

const pyqUploadBtn  = document.getElementById('pyq-upload-btn');
const pyqFileInput  = document.getElementById('pyq-file-input');
const pyqStatus     = document.getElementById('pyq-status');
const pyqClearBtn   = document.getElementById('pyq-clear-btn');
const pyqPreview    = document.getElementById('pyq-preview');

if (pyqUploadBtn) {
    pyqUploadBtn.addEventListener('click', () => pyqFileInput && pyqFileInput.click());
}

if (pyqFileInput) {
    pyqFileInput.addEventListener('change', async () => {
        const files = Array.from(pyqFileInput.files);
        if (!files.length) return;
        pyqFileInput.value = '';

        pyqStatus.textContent = `⏳ Parsing ${files.length} file(s)…`;
        let totalQuestions = 0;
        let allExamples = [];
        let previewLines = [];

        for (const file of files) {
            const ext = file.name.split('.').pop().toLowerCase();
            try {
                if (ext === 'json' || ext === 'md' || ext === 'txt') {
                    // Client-side parse for text formats
                    const text = await file.text();
                    if (ext === 'json') {
                        const parsed = JSON.parse(text);
                        const qs = Array.isArray(parsed) ? parsed
                            : (parsed.questions || parsed.items || []);
                        const normalized = qs.filter(q => q && (q.question || q.stem || q.Q))
                            .map(q => ({
                                question: q.question || q.stem || q.Q || '',
                                options: q.options || q.choices || [],
                                correct_option: q.correct_option || q.answer || q.correct || '',
                                explanation: q.explanation || q.rationale || '',
                                subject: q.subject || '',
                                topic: q.topic || '',
                            }));
                        allExamples.push(...normalized);
                        totalQuestions += normalized.length;
                        previewLines.push(`📄 ${file.name}: ${normalized.length} questions (JSON)`);
                    } else {
                        // MD or TXT — send to backend for structured parse
                        const result = await uploadFileToParse(file);
                        allExamples.push(...result.questions);
                        totalQuestions += result.count;
                        previewLines.push(`📄 ${file.name}: ${result.count} questions (${ext.toUpperCase()})`);
                        if (result.reference_text) pyqReferenceText += result.reference_text + '\n\n';
                    }
                } else {
                    // DOCX/DOC — must go to backend
                    const result = await uploadFileToParse(file);
                    allExamples.push(...result.questions);
                    totalQuestions += result.count;
                    previewLines.push(`📄 ${file.name}: ${result.count} questions extracted (DOCX)`);
                    if (result.reference_text) pyqReferenceText += result.reference_text + '\n\n';
                }
            } catch (err) {
                previewLines.push(`⚠️ ${file.name}: parse failed — ${err.message}`);
            }
        }

        pyqReferenceExamples = allExamples;
        pyqStatus.textContent = `✓ ${totalQuestions} reference questions loaded`;
        if (pyqClearBtn) pyqClearBtn.style.display = 'inline';

        // Show preview of first few questions
        if (pyqPreview) {
            pyqPreview.style.display = 'block';
            const sampleLines = [
                ...previewLines,
                '',
                ...allExamples.slice(0, 4).map((q, i) =>
                    `${i + 1}. ${q.question.slice(0, 100)}${q.question.length > 100 ? '…' : ''}`)
            ];
            pyqPreview.innerHTML = sampleLines.map(l => `<div>${escapeHtml(l)}</div>`).join('');
        }
        showToast(`Loaded ${totalQuestions} reference questions`, 'success');
    });
}

async function uploadFileToParse(file) {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch('/api/parse-reference-doc', { method: 'POST', body: form });
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    return res.json();
}

if (pyqClearBtn) {
    pyqClearBtn.addEventListener('click', () => {
        pyqReferenceExamples = [];
        pyqReferenceText = '';
        if (pyqStatus) pyqStatus.textContent = 'No files attached';
        if (pyqClearBtn) pyqClearBtn.style.display = 'none';
        if (pyqPreview) { pyqPreview.style.display = 'none'; pyqPreview.innerHTML = ''; }
    });
}

// Expose for mock exam generation to pick up reference examples
function getPyqExamples(subjectName, maxCount = 8) {
    // Prefer subject-matched examples, fall back to any
    const subjectMatches = pyqReferenceExamples.filter(q =>
        q.subject && subjectName &&
        (q.subject.toLowerCase().includes(subjectName.toLowerCase()) ||
         subjectName.toLowerCase().includes(q.subject.toLowerCase()))
    );
    const pool = subjectMatches.length >= 2 ? subjectMatches : pyqReferenceExamples;
    // Random sample for variety
    const shuffled = [...pool].sort(() => Math.random() - 0.5);
    return shuffled.slice(0, maxCount);
}



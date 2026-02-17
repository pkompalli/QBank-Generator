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
let attachedFile = null;

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
    // Hide structure review section
    if (structureSection) {
        structureSection.style.display = 'none';
    }

    // Show generate section
    const generateSection = document.getElementById('generate-section');
    if (generateSection) {
        generateSection.style.display = 'block';
    }

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
            const uploadedStructure = JSON.parse(event.target.result);

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

        updateBloomDistribution();
    });
}

// Number of questions slider
if (numQuestionsInput) {
    numQuestionsInput.addEventListener('input', () => {
        if (numDisplay) numDisplay.textContent = numQuestionsInput.value;
        updateBloomDistribution();
    });
}

// Generate button handler
if (generateBtn) {
    generateBtn.addEventListener('click', async () => {
    // Get course name from the loaded structure (not from input field)
    if (!courseStructure) {
        showToast('Please generate course structure in Lessons tab first', 'error');
        return;
    }

    const course = courseStructure.Course || 'Unknown Course';
    const subjectIdx = subjectSelect ? subjectSelect.value : '';
    const topics = topicsSelect ? Array.from(topicsSelect.selectedOptions).map(opt => opt.value) : [];
    const numQuestions = numQuestionsInput ? parseInt(numQuestionsInput.value) : 10;
    const includeImages = includeImagesCheckbox ? includeImagesCheckbox.checked : true;

    if (!subjectIdx) {
        showToast('Please select a subject', 'error');
        return;
    }

    if (topics.length === 0) {
        showToast('Please select at least one topic', 'error');
        return;
    }

    const subject = courseStructure.subjects[subjectIdx].name;

    // Debug logging
    console.log('courseStructure:', courseStructure);
    console.log('exam_format being sent:', courseStructure?.exam_format);

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
                include_images: includeImages,
                exam_format: courseStructure?.exam_format
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        generatedQuestions = data.questions;
        displayResults(data.questions, course, data.image_stats);

        // Show results section and switch to qbank tab
        showResultTab('qbank');

        let message = `Generated ${data.count} questions across ${topics.length} topic(s)!`;
        if (data.image_stats) {
            message += ` | ${data.image_stats.image_based_count} image-based (${data.image_stats.image_percentage}), ${data.image_stats.images_found} images found`;
        }
        showToast(message, 'success');
        
    } catch (error) {
        showToast(error.message || 'Error generating questions', 'error');
    } finally {
        loading.style.display = 'none';
        generateBtn.disabled = false;
    }
    });
}

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
if (downloadBtn) {
    downloadBtn.addEventListener('click', () => {
    if (!generatedQuestions.length) return;

    const course = courseStructure?.Course || 'questions';
    const blob = new Blob([JSON.stringify(generatedQuestions, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `qbank_${course.replace(/\s+/g, '_')}_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);

    showToast('Downloaded successfully!', 'success');
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

    structureStatus.textContent = '⏳ Generating course structure...';
    generateSubjectsBtn.disabled = true;

    try {
        // Call backend to generate comprehensive structure
        console.log('🎓 Lessons: Calling API to generate structure for:', course);

        const response = await fetch('/api/generate-subjects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ course })
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

// File selection handler for lessons
if (lessonJsonFile) {
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
        option.value = idx;
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

    const selectedTopicIndices = lessonTopicsSelect
        ? Array.from(lessonTopicsSelect.selectedOptions).map(opt => parseInt(opt.value))
        : [];

    lessonChaptersSelect.innerHTML = '';

    // If no topics selected, don't show chapters
    if (selectedTopicIndices.length === 0) return;

    // Collect chapters from selected topics
    selectedTopicIndices.forEach(topicIdx => {
        const topic = subject.topics[topicIdx];
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

        if (isChecked && structureStatus) {
            structureStatus.textContent = '✓ Will generate lessons for entire course';
        } else if (structureStatus) {
            structureStatus.textContent = structureStatus.textContent.replace('Will generate lessons for entire course', '');
        }
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
        const selectedTopicIndices = Array.from(lessonTopicsSelect.selectedOptions).map(opt => parseInt(opt.value));
        if (selectedTopicIndices.length > 0) {
            requestData.selected_topic_indices = selectedTopicIndices;
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
    for (const lesson of lessons) {
        if (lesson.topic_lesson) {
            sections.push({ topic: lesson.topic, topic_lesson: lesson.topic_lesson, chapters: [] });
        }
        if (lesson.chapters && lesson.chapters.length > 0) {
            for (const ch of lesson.chapters) {
                if (ch.lesson) {
                    sections.push({ topic: ch.chapter, topic_lesson: ch.lesson, chapters: [] });
                }
            }
        }
    }
    return sections;
}

const validateLessonsBtn = document.getElementById('validate-lessons-btn');
if (validateLessonsBtn) {
    validateLessonsBtn.addEventListener('click', async () => {
        if (!lessonsData || !lessonsData.lessons || lessonsData.lessons.length === 0) {
            showToast('No lessons to validate', 'error');
            return;
        }

        const modal = document.getElementById('validation-modal');
        const reportContent = document.getElementById('validation-report-content');
        const sections = flattenLessonsToSections(lessonsData.lessons);
        const count = sections.length;

        reportContent.innerHTML = `
            <div class="loading-spinner"></div>
            <p style="text-align:center;color:#999;margin-top:1rem;">Running Council of Models validation on ${count} section(s)...</p>
            <p style="text-align:center;color:#999;font-size:0.9rem;">Validator &amp; Adversarial running in parallel — est. 2–4 min</p>
        `;
        modal.style.display = 'block';

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

        const modal = document.getElementById('validation-modal');
        const reportContent = document.getElementById('validation-report-content');
        const count = generatedQuestions.length;

        reportContent.innerHTML = `
            <div class="loading-spinner"></div>
            <p style="text-align:center;color:#999;margin-top:1rem;">Running Council of Models validation on ${count} question(s)...</p>
            <p style="text-align:center;color:#999;font-size:0.9rem;">Validator &amp; Adversarial running in parallel — est. 1–3 min</p>
        `;
        modal.style.display = 'block';

        try {
            const response = await fetch('/api/validate-content', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    content_type: 'qbank',
                    items: generatedQuestions,
                    domain: 'medical education',
                    course: courseStructure?.Course || 'Unknown'
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
                </div>
            `;
        }
    });
}

function displayBatchValidationReport(report, contentType) {
    const reportContent = document.getElementById('validation-report-content');
    const items = report.items || [];
    const summary = report.summary || {};

    const getScoreClass = (score) => {
        if (score >= 8) return 'score-high';
        if (score >= 6) return 'score-medium';
        return 'score-low';
    };

    const formatList = (arr) => {
        if (!arr || arr.length === 0) return '<p class="empty-state">None identified</p>';
        return `<ul class="validation-list">${arr.map(i => `<li>${i}</li>`).join('')}</ul>`;
    };

    const statusBadge = (assessment) => {
        const s = assessment.status || '';
        const color = s.includes('Approved') ? '#28a745' : s.includes('Conditional') ? '#ffc107' : '#dc3545';
        return `<span style="background:${color};color:#fff;padding:2px 10px;border-radius:12px;font-size:0.85rem;">${s}</span>`;
    };

    // ---- Summary bar ----
    const structuralCount = summary.structural_failures || 0;
    const summaryHtml = `
        <div class="overall-assessment" style="margin-bottom:1.5rem;">
            <h3>📊 Batch Summary — ${report.course || ''}</h3>
            <div style="display:flex;gap:2rem;flex-wrap:wrap;margin-top:0.75rem;font-size:1rem;">
                <div><strong>Total:</strong> ${summary.total || 0}</div>
                <div style="color:#28a745;"><strong>✅ Approved:</strong> ${summary.approved || 0}</div>
                <div style="color:#dc3545;"><strong>❌ Needs Revision:</strong> ${summary.needs_revision || 0}</div>
                ${structuralCount ? `<div style="color:#6f42c1;"><strong>🔧 Structural Failures:</strong> ${structuralCount}</div>` : ''}
                <div><strong>Avg Quality Score:</strong> ${summary.avg_quality_score || 'N/A'}/10</div>
            </div>
            ${structuralCount ? `<p style="font-size:0.85rem;color:#6f42c1;margin-top:0.5rem;">⚠️ ${structuralCount} question(s) have structural issues (e.g. missing image) and were auto-failed. Adversarial review was skipped for these.</p>` : ''}
            <p style="font-size:0.85rem;color:#999;margin-top:0.25rem;">
                Domain: ${report.domain || 'N/A'} &nbsp;|&nbsp;
                Validated: ${new Date(report.timestamp).toLocaleString()}
            </p>
        </div>
    `;

    // ---- Per-item accordion ----
    const itemLabel = contentType === 'qbank' ? 'Q' : 'Section';
    const itemsHtml = items.map((item, idx) => {
        const v = item.validator || {};
        const a = item.adversarial || {};
        const oa = item.overall_assessment || {};
        const num = item.index || idx + 1;

        // Short label for the accordion header
        let headerTitle = `${itemLabel} ${num}`;
        if (contentType === 'qbank' && v.question_preview) {
            headerTitle += ` — ${v.question_preview.substring(0, 70)}${v.question_preview.length > 70 ? '...' : ''}`;
        } else if (contentType === 'lesson' && v.section_title) {
            headerTitle += ` — ${v.section_title}`;
        }

        const accordionId = `val-item-${num}`;
        const isStructural = item.structural_failure === true;
        const headerBg = isStructural ? '#fff0f6' : '#f8f9fa';

        return `
        <div class="val-accordion" style="border:1px solid ${isStructural ? '#f5c6cb' : '#e0e0e0'};border-radius:8px;margin-bottom:0.75rem;overflow:hidden;">
            <button class="val-acc-header" onclick="toggleValAccordion('${accordionId}')"
                style="width:100%;text-align:left;padding:0.9rem 1rem;background:${headerBg};border:none;cursor:pointer;display:flex;align-items:center;gap:0.75rem;font-size:0.95rem;">
                <span style="font-weight:600;">${headerTitle}</span>
                <span style="margin-left:auto;display:flex;gap:0.5rem;align-items:center;">
                    ${isStructural ? '<span style="background:#6f42c1;color:#fff;padding:2px 10px;border-radius:12px;font-size:0.8rem;">🔧 Structural Failure</span>' : statusBadge(oa)}
                    <span class="validation-score ${getScoreClass(oa.quality_score || 0)}" style="font-size:0.85rem;">
                        ${oa.quality_score || 'N/A'}/10
                    </span>
                    <span style="font-size:0.8rem;color:#999;">▼</span>
                </span>
            </button>
            <div id="${accordionId}" style="display:none;padding:1rem 1.25rem;border-top:1px solid #e0e0e0;">

                <!-- Score row -->
                <div style="display:flex;gap:1.5rem;flex-wrap:wrap;margin-bottom:1rem;font-size:0.9rem;">
                    <div>✅ <strong>Validator:</strong>
                        <span class="validation-score ${getScoreClass(v.overall_accuracy_score || 0)}" style="font-size:0.8rem;">
                            ${v.overall_accuracy_score ?? 'N/A'}/10
                        </span>
                    </div>
                    ${contentType === 'qbank' ? `<div>Answer verified: <strong>${v.correct_answer_verified ? 'Yes ✅' : 'No ❌'}</strong></div>` : ''}
                    <div>⚔️ <strong>Adversarial:</strong>
                        <span class="validation-score ${getScoreClass(10 - (a.adversarial_score || 0))}" style="font-size:0.8rem;">
                            ${a.adversarial_score ?? 'N/A'}/10
                        </span>
                        &nbsp;<em style="font-size:0.8rem;color:#666;">${a.breakability_rating || ''}</em>
                    </div>
                    <div>Needs revision: <strong>${oa.needs_revision ? 'Yes ❌' : 'No ✅'}</strong></div>
                </div>

                <!-- Validator summary -->
                <p style="margin-bottom:0.5rem;"><strong>Validator Summary:</strong> ${v.summary || 'N/A'}</p>

                ${v.factual_errors?.length ? `<h4 style="color:#dc3545;margin-top:0.75rem;">⚠️ Factual Errors</h4>${formatList(v.factual_errors)}` : ''}
                ${v.missing_critical_info?.length ? `<h4 style="color:#ffc107;margin-top:0.75rem;">📌 Missing Critical Info</h4>${formatList(v.missing_critical_info)}` : ''}
                ${v.safety_concerns?.length ? `<h4 style="color:#dc3545;margin-top:0.75rem;">🚨 Safety Concerns</h4>${formatList(v.safety_concerns)}` : ''}
                ${v.clarity_issues?.length ? `<h4 style="color:#17a2b8;margin-top:0.75rem;">💭 Clarity Issues</h4>${formatList(v.clarity_issues)}` : ''}
                ${v.learning_gaps?.length ? `<h4 style="color:#e83e8c;margin-top:0.75rem;">🧠 Learning Gaps (missing concepts)</h4>${formatList(v.learning_gaps)}` : ''}
                ${v.missing_high_yield?.length ? `<h4 style="color:#fd7e14;margin-top:0.75rem;">⭐ Missing High-Yield Points</h4>${formatList(v.missing_high_yield)}` : ''}
                ${v.missing_pitfalls?.length ? `<h4 style="color:#6f42c1;margin-top:0.75rem;">🕳️ Missing Pitfalls / Misconceptions</h4>${formatList(v.missing_pitfalls)}` : ''}
                ${v.asset_issues?.length ? `<h4 style="color:#6c757d;margin-top:0.75rem;">🖼️ Image / Table / Flowchart Issues</h4>${formatList(v.asset_issues)}` : ''}
                ${v.distractor_issues?.length ? `<h4 style="color:#ffc107;margin-top:0.75rem;">🎯 Distractor Issues</h4>${formatList(v.distractor_issues)}` : ''}
                ${v.vignette_issues?.length ? `<h4 style="color:#ffc107;margin-top:0.75rem;">🗒️ Vignette Issues</h4>${formatList(v.vignette_issues)}` : ''}
                ${v.explanation_issues?.length ? `<h4 style="color:#ffc107;margin-top:0.75rem;">📝 Explanation Issues</h4>${formatList(v.explanation_issues)}` : ''}
                ${v.recommendations?.length ? `<h4 style="color:#28a745;margin-top:0.75rem;">💡 Validator Recommendations</h4>${formatList(v.recommendations)}` : ''}

                <!-- Adversarial summary -->
                <hr style="margin:1rem 0;border-color:#f0d0d0;">
                <p style="margin-bottom:0.5rem;"><strong>Adversarial Summary:</strong> ${a.summary || 'N/A'}</p>

                ${a.identified_weaknesses?.length ? `<h4 style="color:#dc3545;margin-top:0.75rem;">🔍 Weaknesses</h4>${formatList(a.identified_weaknesses)}` : ''}
                ${a.ambiguities?.length ? `<h4 style="color:#ffc107;margin-top:0.75rem;">❓ Ambiguities</h4>${formatList(a.ambiguities)}` : ''}
                ${a.alternative_answers?.length ? `<h4 style="color:#dc3545;margin-top:0.75rem;">🔀 Alternative Defensible Answers</h4>${formatList(a.alternative_answers)}` : ''}
                ${a.distractor_defenses?.length ? `<h4 style="color:#ffc107;margin-top:0.75rem;">🛡️ Defensible Distractors</h4>${formatList(a.distractor_defenses)}` : ''}
                ${a.logical_gaps?.length ? `<h4 style="color:#ffc107;margin-top:0.75rem;">🧩 Logical Gaps</h4>${formatList(a.logical_gaps)}` : ''}
                ${a.learning_traps?.length ? `<h4 style="color:#e83e8c;margin-top:0.75rem;">🪤 Learning Traps</h4>${formatList(a.learning_traps)}` : ''}
                ${a.overgeneralizations?.length ? `<h4 style="color:#ffc107;margin-top:0.75rem;">📢 Overgeneralizations</h4>${formatList(a.overgeneralizations)}` : ''}
                ${a.safety_risks?.length ? `<h4 style="color:#dc3545;margin-top:0.75rem;">⚠️ Safety Risks</h4>${formatList(a.safety_risks)}` : ''}
                ${a.asset_issues?.length ? `<h4 style="color:#6c757d;margin-top:0.75rem;">🖼️ Asset Issues (adversarial)</h4>${formatList(a.asset_issues)}` : ''}
                ${a.explanation_contradictions?.length ? `<h4 style="color:#dc3545;margin-top:0.75rem;">💥 Explanation Contradictions</h4>${formatList(a.explanation_contradictions)}` : ''}
                ${a.triviality_clues?.length ? `<h4 style="color:#17a2b8;margin-top:0.75rem;">🔓 Triviality Clues</h4>${formatList(a.triviality_clues)}` : ''}
                ${a.recommendations?.length ? `<h4 style="color:#28a745;margin-top:0.75rem;">💡 Adversarial Recommendations</h4>${formatList(a.recommendations)}` : ''}

                <!-- Recommendation -->
                <div style="margin-top:1rem;padding:0.75rem;background:#f8f9fa;border-radius:6px;font-size:0.9rem;">
                    <strong>Assessment:</strong> ${oa.recommendation || 'N/A'}
                </div>
            </div>
        </div>`;
    }).join('');

    reportContent.innerHTML = summaryHtml + itemsHtml;
    showToast(`Validation complete — ${summary.approved}/${summary.total} approved`, 'success');
}

function toggleValAccordion(id) {
    const el = document.getElementById(id);
    if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

// ============================================================
// UPLOAD & VALIDATE — parse an uploaded JSON or MD file
// ============================================================

async function runUploadValidation(items, contentType, course) {
    const modal = document.getElementById('validation-modal');
    const reportContent = document.getElementById('validation-report-content');

    // For lessons, flatten topic + chapters into individual sections
    const sendItems = (contentType === 'lesson') ? flattenLessonsToSections(items) : items;

    reportContent.innerHTML = `
        <div class="loading-spinner"></div>
        <p style="text-align:center;color:#999;margin-top:1rem;">Running Council of Models validation on ${sendItems.length} ${contentType === 'qbank' ? 'question(s)' : 'section(s)'}...</p>
        <p style="text-align:center;color:#999;font-size:0.9rem;">Validator &amp; Adversarial running in parallel — est. 2–4 min</p>
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


// Global App State
let profileData = {};
let isRunning = false;
let statusInterval = null;
let allLogs = [];
let resumeKeywords = [];
let runStartTime = null;
let currentResumeName = '';

const STANDARD_TITLES = [
  "Python Developer", "Backend Developer", "Frontend Developer", "Full Stack Engineer",
  "Software Engineer", "React Developer", "DevOps Engineer", "Data Scientist",
  "Machine Learning Engineer", "Java Developer", "Node.js Developer", "Cloud Engineer",
  "Android Developer", "iOS Developer", "System Administrator", "Data Engineer",
  "QA Automation Engineer", "Product Manager"
];

// DOM Elements
const navItems = document.querySelectorAll('.nav-item');
const tabContents = document.querySelectorAll('.tab-content');
const pageTitle = document.getElementById('page-title');
const clockEl = document.getElementById('clock');

// Stats Elements
const statTotal = document.getElementById('stat-total');
const statApplied = document.getElementById('stat-applied');
const statNotMatched = document.getElementById('stat-not-matched');

// Runner Controls
const btnStart = document.getElementById('btn-start');
const btnStop = document.getElementById('btn-stop');
const consoleOutput = document.getElementById('console-output');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const activeResumeName = document.getElementById('active-resume-name');

// Logs Table
const logsTbody = document.getElementById('logs-tbody');
const logSearch = document.getElementById('log-search');

// Resume Uploader
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('resume-file-input');
const progressBox = document.getElementById('upload-progress-box');
const progressBar = document.getElementById('upload-bar');
const progressPct = document.getElementById('upload-pct');
const uploadFilename = document.getElementById('upload-filename');
const uploadStatus = document.getElementById('upload-status');

// Profile Form
const profileForm = document.getElementById('profile-form');
const saveStatusMsg = document.getElementById('save-status-msg');

// Modals
const profileNoticeModal = document.getElementById('profile-notice-modal');
const loginRequiredModal = document.getElementById('login-required-modal');
const btnModalConfirm = document.getElementById('btn-modal-confirm');
const btnModalCancel = document.getElementById('btn-modal-cancel');

// -------------------------------------------------------------
// Initialize App
// -------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  initClock();
  initTabs();
  loadProfile();
  loadLogs();
  initRunnerStatus();
  initUploader();
  loadResumeKeywords();
  initAutocomplete();
  initCookieImporter();
  initLoginRemoteControls();
  initLogout();
  initOnboarding();
  initMobileAppDrawer();
  
  // Dashboard portal change listener
  const dbPortal = document.getElementById('dashboard-portal');
  if (dbPortal) {
    dbPortal.addEventListener('change', (e) => {
      if (profileData && profileData.search_preferences) {
        const val = e.target.value;
        profileData.search_preferences.portals = val === 'all' ? ['naukri', 'indeed', 'foundit'] : [val];
        fetch('/api/profile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(profileData)
        });
      }
    });
  }

  // Dashboard freshness change listener
  const dbFreshness = document.getElementById('dashboard-freshness');
  if (dbFreshness) {
    dbFreshness.addEventListener('change', (e) => {
      if (profileData && profileData.search_preferences) {
        profileData.search_preferences.freshness = e.target.value;
        // Save to API
        fetch('/api/profile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(profileData)
        });
      }
    });
  }
  
  // Refresh logs and status periodically
  setInterval(loadLogs, 10000);
});

// Real-time Clock
function initClock() {
  const updateClock = () => {
    const now = new Date();
    clockEl.textContent = now.toLocaleTimeString();
  };
  updateClock();
  setInterval(updateClock, 1000);
}

// -------------------------------------------------------------
// SPA Navigation Tabs
// -------------------------------------------------------------
function initTabs() {
  navItems.forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      
      const tabId = item.getAttribute('data-tab');
      
      // Update sidebar state
      navItems.forEach(n => n.classList.remove('active'));
      item.classList.add('active');
      
      // Switch active tab section
      tabContents.forEach(content => {
        content.classList.remove('active');
      });
      document.getElementById(`tab-${tabId}`).classList.add('active');
      
      // Update page header title
      const tabTitleMap = {
        'overview': 'Dashboard Overview',
        'jobs': 'Job Application History',
        'profile': 'Profile Configuration',
        'resume': 'Resume Repository'
      };
      pageTitle.textContent = tabTitleMap[tabId] || 'Dashboard';
      
      // Hook: load latest data when switching
      if (tabId === 'jobs') {
        loadLogs();
      } else if (tabId === 'profile') {
        loadProfile();
      }
    });
  });
}

// -------------------------------------------------------------
// Runner Controls & Live Log Stream
// -------------------------------------------------------------
function initRunnerStatus() {
  // Check runner status immediately
  checkRunnerStatus();
  
  // Set up polling interval
  statusInterval = setInterval(checkRunnerStatus, 1500);
  
  btnStart.addEventListener('click', () => {
    profileNoticeModal.classList.add('show');
  });
  
  btnModalCancel.addEventListener('click', () => {
    profileNoticeModal.classList.remove('show');
  });
  
  btnModalConfirm.addEventListener('click', () => {
    profileNoticeModal.classList.remove('show');
    startRunner();
  });
  
  btnStop.addEventListener('click', () => {
    btnStop.disabled = true;
    consoleOutput.textContent += "\n[SYSTEM] Stopping process gracefully...\n";
    
    fetch('/api/stop', { method: 'POST' })
      .then(res => res.json())
      .then(data => {
        if (data.error) {
          consoleOutput.textContent += `[ERROR] Failed to stop: ${data.error}\n`;
          btnStop.disabled = false;
        } else {
          isRunning = false;
          updateRunnerUI(false);
        }
      })
      .catch(err => {
        consoleOutput.textContent += `[ERROR] Connection failed: ${err}\n`;
        btnStop.disabled = false;
      });
  });
}

function startRunner() {
  btnStart.disabled = true;
  consoleOutput.textContent = "[SYSTEM] Spawning playwright runner thread...\n";
  runStartTime = new Date();
  
  fetch('/api/run', { method: 'POST' })
    .then(res => res.json())
    .then(data => {
      if (data.error) {
        showConsoleError(data.error);
        btnStart.disabled = false;
      } else {
        isRunning = true;
        updateRunnerUI(true);
      }
    })
    .catch(err => {
      showConsoleError(err);
      btnStart.disabled = false;
    });
}

function checkRunnerStatus() {
  fetch('/api/status')
    .then(res => res.json())
    .then(data => {
      const wasRunning = isRunning;
      const stateChanged = (isRunning !== data.running);
      isRunning = data.running;
      
      updateRunnerUI(isRunning);
      
      // If runner just stopped and we have a start time, show completion summary modal
      if (wasRunning && !isRunning && runStartTime !== null) {
        showCompletionSummary(runStartTime);
        runStartTime = null; // Reset to avoid double triggering
      }
      
      // Update terminal text block
      if (data.logs) {
        const wasScrolledBottom = isConsoleScrolledToBottom();
        consoleOutput.innerHTML = formatLogs(data.logs);
        // Force auto-scrolling if runner is active, or if user was already at the bottom
        if (data.running || wasScrolledBottom || stateChanged) {
          scrollConsoleToBottom();
        }
        
        // 1. Current job target
        const targetMatch = data.logs.match(/Evaluating job card:\s+['"](.*?)['"]/g);
        if (targetMatch && targetMatch.length > 0) {
          const lastTarget = targetMatch[targetMatch.length - 1];
          const cleanTarget = lastTarget.replace(/Evaluating job card:\s+['"]|['"]/g, "").trim();
          document.getElementById('live-current-job').textContent = cleanTarget;
        } else if (!data.running) {
          document.getElementById('live-current-job').textContent = "Idle (Run to begin)";
        }
        
        // 2. Last match score
        const scoreMatch = data.logs.match(/(?:Score:|Job Score:|score|override):?\s+(\d+(?:\.\d+)?)\/100/g);
        if (scoreMatch && scoreMatch.length > 0) {
          const lastScoreText = scoreMatch[scoreMatch.length - 1];
          const digits = lastScoreText.match(/\d+(?:\.\d+)?/);
          if (digits) {
            document.getElementById('live-last-score').textContent = digits[0] + "/100";
          }
        }
        
        // 3. Evaluations count this run (including skipped/matched jobs starting with ==>)
        const evalCount = (data.logs.match(/==> \[/g) || []).length;
        document.getElementById('live-run-evaluated').textContent = evalCount;
        
        // 4. Applications applied this run
        const appliedCount = (data.logs.match(/==> \[APPLIED #/g) || []).length;
        document.getElementById('live-run-applied').textContent = appliedCount;
        
        // B. Handle login action prompt modal overlay
        const needsLogin = data.logs.includes("Please log in manually") && 
                          !data.logs.includes("Manual login detected") && 
                          !data.logs.includes("Session is valid") && 
                          !data.logs.includes("Authentication failed");
                          
        if (data.running && needsLogin) {
          loginRequiredModal.classList.add('show');
          pollLoginHandshake();
        } else {
          loginRequiredModal.classList.remove('show');
        }
      }
      
      // Update active resume
      currentResumeName = data.resume || "None (Drop resume)";
      activeResumeName.textContent = currentResumeName;
      const tabResume = document.getElementById('upload-tab-resume-name');
      if (tabResume) {
        tabResume.textContent = currentResumeName;
      }
      checkOnboardingStatus();
    })
    .catch(err => {
      console.warn("Status poll failed:", err);
    });
}

function updateRunnerUI(running) {
  if (running) {
    if (statusDot) statusDot.className = 'status-dot running';
    if (statusText) statusText.textContent = 'Running';
    btnStart.disabled = true;
    btnStop.disabled = false;
  } else {
    if (statusDot) statusDot.className = 'status-dot idle';
    if (statusText) statusText.textContent = 'Idle';
    btnStart.disabled = false;
    btnStop.disabled = true;
  }
}

function showConsoleError(err) {
  consoleOutput.textContent += `\n[ERROR] Runner failed to start: ${err}\n`;
}

function isConsoleScrolledToBottom() {
  const body = consoleOutput.parentElement;
  return body.scrollHeight - body.clientHeight <= body.scrollTop + 50;
}

function scrollConsoleToBottom() {
  const body = consoleOutput.parentElement;
  setTimeout(() => {
    body.scrollTop = body.scrollHeight;
  }, 10);
}

// -------------------------------------------------------------
// Logs parser & table rendering
// -------------------------------------------------------------
function loadLogs() {
  fetch('/api/logs')
    .then(res => res.json())
    .then(data => {
      allLogs = data;
      renderLogsTable(allLogs);
      updateStatistics(allLogs);
    })
    .catch(err => {
      console.error("Error loading logs:", err);
    });
}

function renderLogsTable(logs) {
  if (logs.length === 0) {
    logsTbody.innerHTML = `<tr><td colspan="7" class="loading-row">No application records found. Run the assistant to generate logs.</td></tr>`;
    return;
  }
  
  let html = '';
  logs.forEach(row => {
    // Format timestamp
    let timeStr = row.timestamp;
    try {
      const dt = new Date(row.timestamp);
      timeStr = dt.toLocaleString();
    } catch(e) {}
    
    // Classify score colors
    const scoreVal = parseFloat(row.score) || 0.0;
    let scoreClass = 'score-text low';
    if (scoreVal >= 60) {
      scoreClass = 'score-text high';
    } else if (scoreVal >= 40) {
      scoreClass = 'score-text mid';
    }
    
    // Applied badge class
    const appliedVal = row.applied.toLowerCase();
    const appliedClass = appliedVal === 'yes' ? 'badge success' : 'badge danger';
    
    // Split reasons by pipe
    const reasonsList = row.reasons.split('|').map(r => `<li>${r.trim()}</li>`).join('');
    
    // Portal badge
    const portalName = row.portal || 'Naukri';

    html += `
      <tr>
        <td style="white-space: nowrap;">${timeStr}</td>
        <td><strong>${escapeHTML(row.company)}</strong></td>
        <td>${escapeHTML(row.title)}</td>
        <td>${escapeHTML(row.location || 'N/A')}</td>
        <td><span class="${scoreClass}">${scoreVal}/100</span></td>
        <td><span class="${appliedClass}">${row.applied}</span></td>
        <td><span class="badge" style="background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.3); color: var(--color-primary);">${escapeHTML(portalName)}</span></td>
        <td>
          <ul style="margin-left: 14px; padding-left: 4px; font-size: 12px; color: var(--text-muted);">
            ${reasonsList}
          </ul>
        </td>
      </tr>
    `;
  });
  
  logsTbody.innerHTML = html;
}

// Statistics card formulas
function updateStatistics(logs) {
  // Filter logs to show only today's metrics
  const todayStr = new Date().toDateString();
  const todayLogs = logs.filter(row => {
    try {
      return new Date(row.timestamp).toDateString() === todayStr;
    } catch(e) {
      return false;
    }
  });

  if (todayLogs.length === 0) {
    statTotal.textContent = '0';
    statApplied.textContent = '0';
    if (statNotMatched) statNotMatched.textContent = '0';
    return;
  }
  
  const total = todayLogs.length;
  const applied = todayLogs.filter(row => row.applied.toLowerCase() === 'yes').length;
  const notMatched = total - applied;
  
  statTotal.textContent = total;
  statApplied.textContent = applied;
  if (statNotMatched) statNotMatched.textContent = notMatched;
}

// ------------------------------------------------------------------
// Job Table Filters — Status pills + text search work together
// ------------------------------------------------------------------
let activeStatusFilter = 'all'; // 'all' | 'yes' | 'no'

function applyLogsFilter() {
  const searchVal = logSearch.value.toLowerCase().trim();
  
  let filtered = allLogs;
  
  // 1. Status filter pill
  if (activeStatusFilter !== 'all') {
    filtered = filtered.filter(row => row.applied.toLowerCase() === activeStatusFilter);
  }
  
  // 2. Text search on top
  if (searchVal) {
    filtered = filtered.filter(row =>
      row.company.toLowerCase().includes(searchVal) ||
      row.title.toLowerCase().includes(searchVal) ||
      (row.location || '').toLowerCase().includes(searchVal) ||
      (row.reasons || '').toLowerCase().includes(searchVal)
    );
  }
  
  renderLogsTable(filtered);
}

// Text search
logSearch.addEventListener('keyup', applyLogsFilter);

// Status filter pills
document.querySelectorAll('.filter-pill').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-pill').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeStatusFilter = btn.dataset.filter;
    applyLogsFilter();
  });
});

// -------------------------------------------------------------
// Profile Config Load / Save Form
// -------------------------------------------------------------
function loadProfile() {
  fetch('/api/profile')
    .then(res => res.json())
    .then(data => {
      profileData = data;
      
      // Populate Personal fields
      document.getElementById('p-name').value = data.personal.full_name || '';
      document.getElementById('p-email').value = data.personal.email || '';
      document.getElementById('p-phone').value = data.personal.phone || '';
      document.getElementById('p-city').value = data.personal.current_city || '';
      document.getElementById('p-relocate').checked = !!data.personal.relocation_willingness;
      
      const fresherCb = document.getElementById('p-fresher');
      if (fresherCb) {
        fresherCb.checked = !!data.experience.is_fresher;
        fresherCb.removeEventListener('change', toggleFresherFields);
        fresherCb.addEventListener('change', toggleFresherFields);
        toggleFresherFields();
      }
      
      // Populate Experience fields
      document.getElementById('exp-total').value = data.experience.total_years || 0.0;
      
      // Populate Search Preferences fields
      document.getElementById('pref-titles').value = (data.search_preferences.target_titles || []).join(', ');
      document.getElementById('pref-locations').value = (data.search_preferences.target_locations || []).join(', ');
      document.getElementById('pref-minexp').value = data.search_preferences.min_experience_years || 0;
      document.getElementById('pref-maxexp').value = data.search_preferences.max_experience_years || 0;
      document.getElementById('pref-ctc').value = data.search_preferences.min_expected_ctc || '';
      document.getElementById('pref-exclude').value = (data.search_preferences.exclude_keywords || []).join(', ');
      
      // Populate dashboard freshness dropdown
      const dbFreshness = document.getElementById('dashboard-freshness');
      if (dbFreshness) {
        dbFreshness.value = data.search_preferences.freshness || 'anytime';
      }
      
      // Populate Match settings fields
      document.getElementById('cfg-keywords').value = data.matcher_settings.target_keyword_matches || 15;
      
      // Populate Auto-Apply settings fields
      document.getElementById('cfg-enabled').checked = !!data.auto_apply_settings.enabled;
      document.getElementById('cfg-threshold').value = data.auto_apply_settings.match_threshold || 60;
      document.getElementById('cfg-maxapps').value = data.auto_apply_settings.max_applications_per_run || 5;
      
      // Populate Screening templates fields
      document.getElementById('qa-why').value = data.screening_answers.why_interested || '';
      document.getElementById('qa-current-ctc').value = data.screening_answers.current_ctc || (data.experience.is_fresher ? '0 (Fresher)' : '');
      document.getElementById('qa-ctc').value = data.screening_answers.expected_ctc || '';
      document.getElementById('qa-join').value = data.screening_answers.earliest_joining_date || '';
      document.getElementById('qa-exp').value = data.screening_answers.years_of_relevant_experience || '';
    })
    .catch(err => {
      console.error("Failed to load profile:", err);
    });
}

function toggleFresherFields() {
  const isFresher = document.getElementById('p-fresher').checked;
  const expContainer = document.getElementById('fresher-exp-container');
  const ctcContainer = document.getElementById('fresher-ctc-container');
  const qaSalaryContainer = document.getElementById('fresher-qa-salary-container');
  const qaExpBox = document.getElementById('fresher-qa-exp-box');
  const totalExpContainer = document.getElementById('fresher-totalexp-container');
  const noticeBadge = document.getElementById('fresher-notice-badge');

  if (isFresher) {
    if (expContainer) expContainer.style.display = 'none';
    if (ctcContainer) ctcContainer.style.display = 'none';
    if (qaSalaryContainer) qaSalaryContainer.style.display = 'none';
    if (qaExpBox) qaExpBox.style.display = 'none';
    if (totalExpContainer) totalExpContainer.style.display = 'none';
    if (noticeBadge) noticeBadge.style.display = 'block';

    document.getElementById('pref-minexp').value = 0;
    document.getElementById('pref-maxexp').value = 1;
    document.getElementById('exp-total').value = 0;
    document.getElementById('qa-exp').value = '0';
    document.getElementById('qa-current-ctc').value = '0 (Fresher)';
  } else {
    if (expContainer) expContainer.style.display = 'grid';
    if (ctcContainer) ctcContainer.style.display = 'block';
    if (qaSalaryContainer) qaSalaryContainer.style.display = 'grid';
    if (qaExpBox) qaExpBox.style.display = 'block';
    if (totalExpContainer) totalExpContainer.style.display = 'block';
    if (noticeBadge) noticeBadge.style.display = 'none';
  }
}

profileForm.addEventListener('submit', (e) => {
  e.preventDefault();
  
  btnSaveProfile = document.getElementById('btn-save-profile');
  btnSaveProfile.disabled = true;
  saveStatusMsg.className = '';
  saveStatusMsg.textContent = 'Saving changes...';
  
  // Bind form values back to our profileData object (preserving other fields like history)
  profileData.personal.full_name = document.getElementById('p-name').value;
  profileData.personal.email = document.getElementById('p-email').value;
  profileData.personal.phone = document.getElementById('p-phone').value;
  profileData.personal.current_city = document.getElementById('p-city').value;
  profileData.personal.relocation_willingness = document.getElementById('p-relocate').checked;
  
  const fresherCb = document.getElementById('p-fresher');
  if (fresherCb) {
    profileData.experience.is_fresher = fresherCb.checked;
  }
  
  profileData.experience.total_years = parseFloat(document.getElementById('exp-total').value);
  
  // Split preference lists by comma
  profileData.search_preferences.target_titles = document.getElementById('pref-titles').value.split(',').map(s => s.trim()).filter(s => s);
  profileData.search_preferences.target_locations = document.getElementById('pref-locations').value.split(',').map(s => s.trim()).filter(s => s);
  profileData.search_preferences.min_experience_years = parseInt(document.getElementById('pref-minexp').value) || 0;
  profileData.search_preferences.max_experience_years = parseInt(document.getElementById('pref-maxexp').value) || 0;
  profileData.search_preferences.min_expected_ctc = document.getElementById('pref-ctc').value;
  profileData.search_preferences.exclude_keywords = document.getElementById('pref-exclude').value.split(',').map(s => s.trim()).filter(s => s);
  
  // Read freshness from dashboard select dropdown
  const dbFreshness = document.getElementById('dashboard-freshness');
  if (dbFreshness) {
    profileData.search_preferences.freshness = dbFreshness.value;
  }
  
  profileData.matcher_settings.target_keyword_matches = parseInt(document.getElementById('cfg-keywords').value) || 15;
  
  profileData.auto_apply_settings.enabled = document.getElementById('cfg-enabled').checked;
  profileData.auto_apply_settings.match_threshold = parseInt(document.getElementById('cfg-threshold').value) || 60;
  profileData.auto_apply_settings.max_applications_per_run = parseInt(document.getElementById('cfg-maxapps').value) || 5;
  
  // Set default safe pacing under the hood
  profileData.auto_apply_settings.delay_between_applications_seconds = [15, 30];
  
  profileData.screening_answers.why_interested = document.getElementById('qa-why').value;
  profileData.screening_answers.current_ctc = document.getElementById('qa-current-ctc').value;
  profileData.screening_answers.expected_ctc = document.getElementById('qa-ctc').value;
  profileData.screening_answers.earliest_joining_date = document.getElementById('qa-join').value;
  profileData.screening_answers.years_of_relevant_experience = document.getElementById('qa-exp').value;
  
  // POST to API
  fetch('/api/profile', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profileData)
  })
    .then(res => res.json())
    .then(data => {
      btnSaveProfile.disabled = false;
      if (data.error) {
        saveStatusMsg.className = 'error';
        saveStatusMsg.textContent = `Error: ${data.error}`;
      } else {
        saveStatusMsg.className = 'success';
        saveStatusMsg.textContent = '💾 Configuration saved successfully!';
        setTimeout(() => { saveStatusMsg.textContent = ''; }, 4000);
      }
    })
    .catch(err => {
      btnSaveProfile.disabled = false;
      saveStatusMsg.className = 'error';
      saveStatusMsg.textContent = `Connection error: ${err}`;
    });
});

// -------------------------------------------------------------
// Drag & Drop Resume File Uploader
// -------------------------------------------------------------
function initUploader() {
  // Click drop zone triggers file selector
  dropZone.addEventListener('click', () => {
    fileInput.click();
  });
  
  fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
      handleFileUpload(fileInput.files[0]);
    }
  });
  
  // Drag over effects
  ['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropZone.classList.add('dragover');
    }, false);
  });
  
  ['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropZone.classList.remove('dragover');
    }, false);
  });
  
  dropZone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length > 0) {
      handleFileUpload(files[0]);
    }
  });
}

function handleFileUpload(file) {
  const name = file.name;
  const size = file.size;
  
  // Basic validation
  const ext = name.split('.').pop().toLowerCase();
  if (ext !== 'pdf' && ext !== 'docx' && ext !== 'doc') {
    alert("Unsupported file format. Please upload PDF or DOCX resume.");
    return;
  }
  
  if (size > 5 * 1024 * 1024) { // 5MB
    alert("File size exceeds 5MB limit.");
    return;
  }
  
  uploadFilename.textContent = name;
  progressBox.style.display = 'block';
  progressBar.style.width = '0%';
  progressPct.textContent = '0%';
  uploadStatus.textContent = 'Uploading...';
  
  const formData = new FormData();
  formData.append('resume', file);
  
  const xhr = new XMLHttpRequest();
  
  // Track progress
  xhr.upload.addEventListener('progress', (e) => {
    if (e.lengthComputable) {
      const pct = Math.round((e.loaded / e.total) * 100);
      progressBar.style.width = `${pct}%`;
      progressPct.textContent = `${pct}%`;
    }
  });
  
  xhr.onreadystatechange = () => {
    if (xhr.readyState === XMLHttpRequest.DONE) {
      if (xhr.status === 200) {
        try {
          const resp = JSON.parse(xhr.responseText);
          uploadStatus.innerHTML = `<span style="color: var(--color-success)">✅ ${resp.message}</span>`;
          // Refresh status and resume keywords to show new data
          checkRunnerStatus();
          loadResumeKeywords();
        } catch(e) {
          uploadStatus.innerHTML = `<span style="color: var(--color-danger)">⚠️ Uploaded, but response error.</span>`;
        }
      } else {
        try {
          const resp = JSON.parse(xhr.responseText);
          uploadStatus.innerHTML = `<span style="color: var(--color-danger)">❌ Upload failed: ${resp.error}</span>`;
        } catch(e) {
          uploadStatus.innerHTML = `<span style="color: var(--color-danger)">❌ Upload failed (HTTP ${xhr.status}).</span>`;
        }
      }
    }
  };
  
  xhr.open('POST', '/api/upload-resume', true);
  xhr.send(formData);
}

// -------------------------------------------------------------
// Helper functions
// -------------------------------------------------------------
function escapeHTML(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function loadResumeKeywords() {
  fetch('/api/resume-keywords')
    .then(res => res.json())
    .then(keywords => {
      resumeKeywords = keywords.map(k => k.toLowerCase());
      console.log("Resume keywords loaded:", resumeKeywords.length);
      const keywordsBadge = document.getElementById('active-resume-keywords');
      if (keywordsBadge) {
        keywordsBadge.textContent = `${resumeKeywords.length} skills loaded`;
      }
    })
    .catch(err => console.warn("Failed to load resume keywords:", err));
}

function initAutocomplete() {
  const titleInput = document.getElementById('pref-titles');
  const suggestionsBox = document.getElementById('title-suggestions');
  
  if (!titleInput || !suggestionsBox) return;
  
  // Close suggestions when clicking outside
  document.addEventListener('click', (e) => {
    if (e.target !== titleInput && e.target !== suggestionsBox) {
      suggestionsBox.style.display = 'none';
    }
  });
  
  titleInput.addEventListener('input', () => {
    const value = titleInput.value;
    const cursorPosition = titleInput.selectionStart;
    
    // Find the segment the user is currently typing
    const segments = value.split(',');
    
    // Determine which segment the cursor is in
    let charCount = 0;
    let activeSegmentIndex = 0;
    
    for (let i = 0; i < segments.length; i++) {
      charCount += segments[i].length + (i > 0 ? 1 : 0); // Include comma in length
      if (cursorPosition <= charCount) {
        activeSegmentIndex = i;
        break;
      }
    }
    
    const currentTypedVal = segments[activeSegmentIndex].trim().toLowerCase();
    
    if (!currentTypedVal) {
      suggestionsBox.style.display = 'none';
      return;
    }
    
    // Filter suggestions based on typed input
    const filtered = STANDARD_TITLES.map(title => {
      const titleLower = title.toLowerCase();
      const isMatch = titleLower.includes(currentTypedVal);
      
      // Check if title words match resume keywords (e.g. 'python' in title matches 'python' in resume)
      const titleWords = titleLower.split(/[^a-z0-9+#./-]+/).filter(w => w.length > 1);
      const matchesResume = titleWords.some(word => resumeKeywords.includes(word));
      
      return {
        title: title,
        isMatch: isMatch,
        matchesResume: matchesResume
      };
    }).filter(item => item.isMatch);
    
    if (filtered.length === 0) {
      suggestionsBox.style.display = 'none';
      return;
    }
    
    // Sort: Resume matches first, then alphabetical
    filtered.sort((a, b) => {
      if (a.matchesResume && !b.matchesResume) return -1;
      if (!a.matchesResume && b.matchesResume) return 1;
      return a.title.localeCompare(b.title);
    });
    
    // Render suggestion items
    suggestionsBox.innerHTML = filtered.map(item => {
      const badgeHtml = item.matchesResume ? '<span class="match-indicator">Resume Match</span>' : '';
      return `<div class="autocomplete-suggestion" data-title="${item.title}">${item.title}${badgeHtml}</div>`;
    }).join('');
    
    suggestionsBox.style.display = 'block';
    
    // Click suggestion handlers
    const suggestionItems = suggestionsBox.querySelectorAll('.autocomplete-suggestion');
    suggestionItems.forEach(item => {
      item.addEventListener('click', () => {
        const selectedTitle = item.getAttribute('data-title');
        
        // Replace only the active segment with the selected title
        segments[activeSegmentIndex] = ` ${selectedTitle}`;
        
        // Reconstruct the value
        titleInput.value = segments.map((s, idx) => {
          let clean = s.trim();
          if (idx > 0) return ` ${clean}`;
          return clean;
        }).join(', ') + ', ';
        
        suggestionsBox.style.display = 'none';
        titleInput.focus();
      });
    });
  });
}

function formatLogs(text) {
  if (!text) return '';
  const lines = text.split('\n');
  return lines.map(line => {
    let escaped = escapeHTML(line);
    // Color code logs based on tags
    if (line.includes('[ERROR]') || line.toLowerCase().includes('error:')) {
      return `<span class="log-error">${escaped}</span>`;
    } else if (line.includes('[APPLIED')) {
      return `<span class="log-success">${escaped}</span>`;
    } else if (line.includes('[SKIPPED') || line.includes('[EXCLUDED')) {
      return `<span class="log-warning">${escaped}</span>`;
    } else if (line.includes('[SYSTEM]')) {
      return `<span class="log-system">${escaped}</span>`;
    }
    return escaped;
  }).join('\n');
}

function initCookieImporter() {
  const btnImport = document.getElementById('btn-import-cookies');
  const input = document.getElementById('cookie-json-input');
  const status = document.getElementById('cookie-import-status');
  
  if (!btnImport || !input || !status) return;
  
  btnImport.addEventListener('click', () => {
    const rawVal = input.value.trim();
    if (!rawVal) {
      status.style.color = '#f87171'; // red
      status.textContent = 'Please paste a valid JSON cookie array.';
      return;
    }
    
    let parsed = null;
    try {
      parsed = JSON.parse(rawVal);
    } catch(e) {
      status.style.color = '#f87171'; // red
      status.textContent = 'Invalid JSON structure: ' + e.message;
      return;
    }
    
    status.style.color = '#94a3b8'; // muted slate
    status.textContent = 'Importing cookies...';
    btnImport.disabled = true;
    
    fetch('/api/import-cookies', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(parsed)
    })
      .then(res => res.json())
      .then(data => {
        btnImport.disabled = false;
        if (data.error) {
          status.style.color = '#f87171'; // red
          status.textContent = 'Error: ' + data.error;
        } else {
          status.style.color = '#34d399'; // emerald
          status.textContent = 'Imported successfully! Restarting assistant...';
          input.value = '';
          
          // Stop current instance and restart
          fetch('/api/stop', { method: 'POST' })
            .then(() => {
              setTimeout(() => {
                loginRequiredModal.classList.remove('show');
                status.textContent = '';
                startRunner();
              }, 2000);
            })
            .catch(err => {
              console.error("Stop error during restart:", err);
              setTimeout(() => {
                loginRequiredModal.classList.remove('show');
                status.textContent = '';
                startRunner();
              }, 2000);
            });
        }
      })
      .catch(err => {
        btnImport.disabled = false;
        status.style.color = '#f87171'; // red
        status.textContent = 'Network connection failed: ' + err;
      });
  });
}

let activeLoginTab = 'otp';
function switchLoginTab(tab) {
  activeLoginTab = tab;
  const tabOtp = document.getElementById('tab-login-otp');
  const tabPwd = document.getElementById('tab-login-pwd');
  const mobileBlock = document.getElementById('login-mobile-block');
  const credsBlock = document.getElementById('login-credentials-block');
  
  if (!tabOtp || !tabPwd || !mobileBlock || !credsBlock) return;
  
  if (tab === 'otp') {
    tabOtp.classList.add('active');
    tabPwd.classList.remove('active');
    mobileBlock.style.display = 'block';
    credsBlock.style.display = 'none';
  } else {
    tabOtp.classList.remove('active');
    tabPwd.classList.add('active');
    mobileBlock.style.display = 'none';
    credsBlock.style.display = 'block';
  }
}

let isPollingHandshake = false;
function pollLoginHandshake() {
  if (isPollingHandshake) return;
  isPollingHandshake = true;
  
  fetch('/api/login-handshake')
    .then(res => res.json())
    .then(handshake => {
      isPollingHandshake = false;
      const spinnerBlock = document.getElementById('login-spinner-block');
      const tabsContainer = document.getElementById('login-tabs-container');
      const mobileBlock = document.getElementById('login-mobile-block');
      const credsBlock = document.getElementById('login-credentials-block');
      const otpBlock = document.getElementById('login-otp-block');
      
      const spinnerText = document.getElementById('login-spinner-text');
      const credsError = document.getElementById('login-credentials-error');
      const mobileError = document.getElementById('login-mobile-error');
      const otpError = document.getElementById('login-otp-error');
      const otpImg = document.getElementById('login-otp-screenshot');
      
      if (handshake.status === 'waiting_for_credentials') {
        spinnerBlock.style.display = 'none';
        otpBlock.style.display = 'none';
        tabsContainer.style.display = 'flex';
        
        // Show correct inputs based on chosen tab
        if (activeLoginTab === 'otp') {
          mobileBlock.style.display = 'block';
          credsBlock.style.display = 'none';
          mobileError.textContent = handshake.error || '';
        } else {
          mobileBlock.style.display = 'none';
          credsBlock.style.display = 'block';
          credsError.textContent = handshake.error || '';
        }
      } else {
        // Hide tabs and input blocks when verification/processing is underway
        tabsContainer.style.display = 'none';
        mobileBlock.style.display = 'none';
        credsBlock.style.display = 'none';
        
        if (handshake.status === 'waiting_for_otp') {
          spinnerBlock.style.display = 'none';
          otpBlock.style.display = 'block';
          otpError.textContent = handshake.error || '';
          
          if (handshake.screenshot) {
            otpImg.src = handshake.screenshot + '?t=' + new Date().getTime();
            otpImg.style.display = 'block';
          } else {
            otpImg.style.display = 'none';
          }
        } else if (handshake.status === 'processing') {
          spinnerBlock.style.display = 'flex';
          otpBlock.style.display = 'none';
          spinnerText.textContent = 'Processing request on Naukri.com...';
        } else if (handshake.status === 'success') {
          spinnerBlock.style.display = 'flex';
          otpBlock.style.display = 'none';
          spinnerText.textContent = 'Login successful! Starting job search...';
          setTimeout(() => {
            loginRequiredModal.classList.remove('show');
          }, 1500);
        } else {
          spinnerBlock.style.display = 'flex';
          otpBlock.style.display = 'none';
          spinnerText.textContent = 'Waiting for browser to load Naukri login...';
        }
      }
    })
    .catch(err => {
      isPollingHandshake = false;
      console.warn("Handshake poll failed:", err);
    });
}

function initLoginRemoteControls() {
  const btnSubmitMobile = document.getElementById('btn-submit-mobile');
  const btnSubmitCreds = document.getElementById('btn-submit-credentials');
  const btnSubmitOtp = document.getElementById('btn-submit-otp');
  
  const tabOtp = document.getElementById('tab-login-otp');
  const tabPwd = document.getElementById('tab-login-pwd');
  
  const mobileInp = document.getElementById('login-mobile');
  const userInp = document.getElementById('login-username');
  const passInp = document.getElementById('login-password');
  const otpInp = document.getElementById('login-otp-code');
  
  const spinnerBlock = document.getElementById('login-spinner-block');
  const tabsContainer = document.getElementById('login-tabs-container');
  const mobileBlock = document.getElementById('login-mobile-block');
  const credsBlock = document.getElementById('login-credentials-block');
  const otpBlock = document.getElementById('login-otp-block');
  const spinnerText = document.getElementById('login-spinner-text');
  
  const mobileError = document.getElementById('login-mobile-error');
  
  // Tab Switch clicks
  if (tabOtp && tabPwd) {
    tabOtp.addEventListener('click', () => switchLoginTab('otp'));
    tabPwd.addEventListener('click', () => switchLoginTab('pwd'));
  }
  
  // Submit Mobile Number for OTP
  if (btnSubmitMobile && mobileInp) {
    mobileInp.addEventListener('input', (e) => {
      e.target.value = e.target.value.replace(/[^0-9]/g, '');
    });
    
    btnSubmitMobile.addEventListener('click', () => {
      const mobile = mobileInp.value.trim();
      const cleanMobile = mobile.replace(/[^0-9]/g, '');
      if (cleanMobile.length !== 10) {
        mobileError.textContent = 'Please enter a valid 10-digit mobile number (numbers only).';
        return;
      }
      mobileError.textContent = '';
      
      mobileBlock.style.display = 'none';
      tabsContainer.style.display = 'none';
      spinnerBlock.style.display = 'flex';
      spinnerText.textContent = 'Requesting OTP via Naukri...';
      
      fetch('/api/submit-mobile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mobile })
      })
        .catch(err => {
          console.error("Mobile submission failed:", err);
        });
    });
  }
  
  // Submit Password Credentials
  if (btnSubmitCreds) {
    btnSubmitCreds.addEventListener('click', () => {
      const username = userInp.value.trim();
      const password = passInp.value.trim();
      if (!username || !password) return;
      
      credsBlock.style.display = 'none';
      tabsContainer.style.display = 'none';
      spinnerBlock.style.display = 'flex';
      spinnerText.textContent = 'Sending login request...';
      
      fetch('/api/submit-credentials', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      })
        .catch(err => {
          console.error("Credentials submission failed:", err);
        });
    });
  }
  
  // Submit OTP Verification Code
  if (btnSubmitOtp) {
    btnSubmitOtp.addEventListener('click', () => {
      const otp = otpInp.value.trim();
      if (!otp) return;
      
      otpBlock.style.display = 'none';
      spinnerBlock.style.display = 'flex';
      spinnerText.textContent = 'Verifying code...';
      
      fetch('/api/submit-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ otp })
      })
        .then(() => {
          otpInp.value = '';
        })
        .catch(err => {
          console.error("OTP submission failed:", err);
        });
    });
  }
}

// Completion Summary Modal Logic
function showCompletionSummary(startTime) {
  fetch('/api/logs')
    .then(res => res.json())
    .then(logs => {
      // Filter logs for this run
      const runLogs = logs.filter(row => {
        const rowTime = new Date(row.timestamp);
        return rowTime >= startTime;
      });
      
      const skippedLogs = runLogs.filter(row => row.applied.toLowerCase() === 'no');
      const mismatchCount = skippedLogs.length;
      
      // Calculate top reason
      const reasonCounts = {};
      skippedLogs.forEach(row => {
        const reasons = row.reasons.split('|').map(r => r.trim()).filter(r => r);
        reasons.forEach(r => {
          let groupKey = r;
          if (r.startsWith("Low composite score") || r.startsWith("Job matching score") || r.toLowerCase().includes("threshold")) {
            groupKey = "Low resume keyword/experience matching score";
          } else if (r.startsWith("Freshness Filter") || r.startsWith("Freshness limit") || r.toLowerCase().includes("posted")) {
            groupKey = "Job posted too long ago (freshness limit)";
          } else if (r.toLowerCase().includes("expired")) {
            groupKey = "Job posting is expired";
          }
          reasonCounts[groupKey] = (reasonCounts[groupKey] || 0) + 1;
        });
      });
      
      let topReason = "None detected";
      let maxCount = 0;
      for (const [reason, count] of Object.entries(reasonCounts)) {
        if (count > maxCount) {
          maxCount = count;
          topReason = reason;
        }
      }
      
      // Populate modal fields
      document.getElementById('summary-mismatch-count').textContent = mismatchCount;
      document.getElementById('summary-top-reason').textContent = topReason;
      
      // Show warning note if mismatch > 120
      const warningEl = document.getElementById('summary-resume-warning');
      if (mismatchCount > 120) {
        warningEl.style.display = 'block';
      } else {
        warningEl.style.display = 'none';
      }
      
      // Open modal overlay
      document.getElementById('completion-modal').classList.add('show');
    })
    .catch(err => console.warn("Failed to generate run summary:", err));
}

// Bind Okay button to close modal
document.getElementById('btn-completion-ok').addEventListener('click', () => {
  document.getElementById('completion-modal').classList.remove('show');
});

// Logout Naukri Session
function initLogout() {
  const btnLogout = document.getElementById('btn-logout');
  if (btnLogout) {
    btnLogout.addEventListener('click', () => {
      if (confirm("Are you sure you want to log out from Naukri? This will delete your cached session cookies and force a new login.")) {
        btnLogout.disabled = true;
        btnLogout.textContent = "Logging out...";
        fetch('/api/logout', { method: 'POST' })
          .then(res => res.json())
          .then(data => {
            alert(data.message || "Logged out successfully!");
            location.reload();
          })
          .catch(err => {
            alert("Logout failed: " + err);
            btnLogout.disabled = false;
            btnLogout.textContent = "Logout from Naukri";
          });
      }
    });
  }
}

// Onboarding Setup Check and Navigation
function initOnboarding() {
  const btnResume = document.getElementById('btn-onboard-resume');
  const btnProfile = document.getElementById('btn-onboard-profile');

  if (btnResume) {
    btnResume.addEventListener('click', () => {
      document.querySelector('.nav-item[data-tab="resume"]').click();
    });
  }

  if (btnProfile) {
    btnProfile.addEventListener('click', () => {
      document.querySelector('.nav-item[data-tab="profile"]').click();
    });
  }
}

function checkOnboardingStatus() {
  const banner = document.getElementById('onboarding-banner');
  const titleEl = document.getElementById('onboarding-status-title');
  const descEl = document.getElementById('onboarding-status-desc');
  const btnResume = document.getElementById('btn-onboard-resume');
  const btnProfile = document.getElementById('btn-onboard-profile');

  if (!banner || !titleEl || !descEl) return;

  const hasResume = currentResumeName && !currentResumeName.toLowerCase().includes('none') && !currentResumeName.toLowerCase().includes('loading');
  const hasProfile = profileData && profileData.personal && profileData.personal.full_name && profileData.personal.full_name.trim().length > 0;
  const hasTitles = profileData && profileData.search_preferences && profileData.search_preferences.target_titles && profileData.search_preferences.target_titles.length > 0;

  if (!hasResume) {
    titleEl.textContent = 'Step 1 of 2: Upload Your Resume';
    titleEl.style.color = '#f87171';
    descEl.textContent = 'No active resume detected. Upload your resume (PDF or DOCX) in the Resume Upload tab so the AI can extract your skill keywords.';
    btnResume.style.borderColor = '#f87171';
    btnResume.style.color = '#f87171';
    btnResume.textContent = '1. Upload Resume';
  } else if (!hasProfile || !hasTitles) {
    titleEl.textContent = 'Step 2 of 2: Complete Profile Details';
    titleEl.style.color = '#fbbf24';
    descEl.textContent = 'Resume loaded! Next, go to Edit Profile to verify your full name, phone number, and target job titles.';
    btnResume.style.borderColor = 'var(--color-success)';
    btnResume.style.color = 'var(--color-success)';
    btnResume.textContent = '✓ Resume Uploaded';
    btnProfile.style.borderColor = '#fbbf24';
    btnProfile.style.color = '#fbbf24';
  } else {
    titleEl.textContent = 'System Ready — Ready to Apply!';
    titleEl.style.color = 'var(--color-success)';
    descEl.textContent = `Resume loaded (${currentResumeName}) and profile details configured. Select your target portal and click "Start Assistant"!`;
    banner.style.borderColor = 'rgba(34, 197, 94, 0.4)';
    banner.style.background = 'linear-gradient(135deg, rgba(34, 197, 94, 0.08) 0%, rgba(16, 185, 129, 0.03) 100%)';
    btnResume.style.borderColor = 'var(--color-success)';
    btnResume.style.color = 'var(--color-success)';
    btnResume.textContent = '✓ Resume Ready';
    btnProfile.style.borderColor = 'var(--color-success)';
    btnProfile.style.color = 'var(--color-success)';
    btnProfile.textContent = '✓ Profile Ready';
  }
}

// Mobile App Drawer Controller
function initMobileAppDrawer() {
  const toggleBtn = document.getElementById('mobile-menu-toggle');
  const closeBtn = document.getElementById('sidebar-close-btn');
  const sidebar = document.querySelector('.sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');
  const navItems = document.querySelectorAll('.nav-item');

  function openDrawer() {
    if (sidebar) sidebar.classList.add('open');
    if (backdrop) backdrop.classList.add('active');
  }

  function closeDrawer() {
    if (sidebar) sidebar.classList.remove('open');
    if (backdrop) backdrop.classList.remove('active');
  }

  if (toggleBtn) toggleBtn.addEventListener('click', openDrawer);
  if (closeBtn) closeBtn.addEventListener('click', closeDrawer);
  if (backdrop) backdrop.addEventListener('click', closeDrawer);

  // Close drawer automatically when any tab option is tapped on mobile
  navItems.forEach(item => {
    item.addEventListener('click', () => {
      if (window.innerWidth <= 768) {
        closeDrawer();
      }
    });
  });
}



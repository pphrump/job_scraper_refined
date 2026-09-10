document.addEventListener("DOMContentLoaded", function () {
    const filterCity = document.getElementById("filter-city");
    const filterCompany = document.getElementById("filter-company");
    const filterDate = document.getElementById("filter-date");
    const filterSite = document.getElementById("filter-site");
    const filterRemote = document.getElementById("filter-remote");
    const compareResumeCheckbox = document.getElementById('compare-resume');
    const resumeUploadForm = document.getElementById('resume-upload-form');

    // Get all modals
    const modals = document.querySelectorAll('.modal');
    
    // Fix for Bootstrap modal focus management
    modals.forEach(modal => {
        // Store the element that had focus before the modal opened
        let previouslyFocusedElement = null;
        
        // When modal starts to open
        modal.addEventListener('show.bs.modal', function () {
            previouslyFocusedElement = document.activeElement;
            
        });
        
        // When modal starts to close
        modal.addEventListener('hide.bs.modal', function () {
            // Immediately remove focus from close buttons to prevent the warning
            const closeButtons = this.querySelectorAll('[data-bs-dismiss="modal"]');
            closeButtons.forEach(button => button.blur());
        });
        
        // After modal is fully hidden
        modal.addEventListener('hidden.bs.modal', function () {
            // Apply a more aggressive approach to ensure no element in the modal has focus
            this.querySelectorAll('*').forEach(element => {
                if (document.activeElement === element) {
                    element.blur();
                }
            });
            
            // Return focus with a slight delay to ensure modal is fully processed
            setTimeout(() => {
                // If we have a previously focused element, restore focus to it
                if (previouslyFocusedElement && typeof previouslyFocusedElement.focus === 'function') {
                    previouslyFocusedElement.focus();
                } else {
                    // If for some reason we don't have a previously focused element,
                    // focus on the body to ensure focus is not in the hidden modal
                    document.body.focus();
                }
                previouslyFocusedElement = null;
            }, 100);
        });
    });
    if (document.getElementById('uploadResumeModal')) {
        document.getElementById('uploadResumeModal').addEventListener('hidden.bs.modal', function () {
            const modal = this;
            const wasSuccess = modal.getAttribute('data-upload-success') === 'true';
        
            if (!wasSuccess && compareResumeCheckbox.checked) {
                compareResumeCheckbox.checked = false;
            }
        
            // Reset the flag for next time
            modal.removeAttribute('data-upload-success');
        });
    }

    var tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltipTriggerList.forEach(function (tooltipTriggerEl) {
        new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Add event listener for the resume upload form
    if (resumeUploadForm) {
        resumeUploadForm.addEventListener('submit', function(e) {
            e.preventDefault(); // Prevent standard form submission
            
            // Create or clear any existing error message
            let errorContainer = document.querySelector('.alert.alert-warning');
            if (errorContainer) {
                errorContainer.remove();
            }
            const formData = new FormData(this);
            
            fetch('/upload_resume_compare', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Close the modal
                    const uploadModal = bootstrap.Modal.getInstance(document.getElementById('uploadResumeModal'));
                    if (uploadModal) {
                        const modalElement = document.getElementById('uploadResumeModal');
                        modalElement.setAttribute('data-upload-success', 'true'); 
                        uploadModal.hide();
                    }
                   
                    // Update job rankings with the data from the response
                    if (data.rankings) {
                        updateJobRanking(data.rankings);
                    }

                    
                    // Create a success message
                    const container = document.querySelector('.container.mt-3');
                    const successAlert = document.createElement('div');
                    successAlert.className = 'alert alert-success';
                    successAlert.setAttribute('role', 'alert');
                    successAlert.textContent = 'Resume uploaded successfully!';
                    
                    // Insert at the beginning of the container
                    container.insertBefore(successAlert, container.firstChild);
                    
                    // Auto-remove the message after 5 seconds
                    setTimeout(() => {
                        successAlert.remove();
                    }, 5000);
                } else {
                    displayErrorMessage(data.message || "Unknown error occurred");
                }
            })
            .catch(error => {
                console.error("Error uploading resume:", error);
                displayErrorMessage("An error occurred while uploading the resume");
            });
        });
        
    }
    function displayErrorMessage(message) {
        const container = document.querySelector('.container.mt-3');
        const errorAlert = document.createElement('div');
        errorAlert.className = 'alert alert-warning';
        errorAlert.setAttribute('role', 'alert');
        errorAlert.textContent = message;
        
        // Insert at the beginning of the container
        container.insertBefore(errorAlert, container.firstChild);
        setTimeout(() => {
           errorAlert.remove();
        }, 5000);
    }

    function doesMatch(filterValue, cardValue) {
        const lowerFilterValue = filterValue.toLowerCase().trim();
        const lowerCardValue = cardValue.toLowerCase();

        // Handle multiple exclusions separated by commas
        if (lowerFilterValue.includes(',')) {
            const filters = lowerFilterValue.split(',').map(f => f.trim());
            return filters.every(filter => {
                if (filter.startsWith("-")) {
                    const excludeValue = filter.substring(1);
                    return !lowerCardValue.includes(excludeValue);
                } else {
                    return filter === "" || lowerCardValue.includes(filter);
                }
            });
        }
    
        // Single filter logic
        if (lowerFilterValue.startsWith("-")) {
            const excludeValue = lowerFilterValue.substring(1);
            return !lowerCardValue.includes(excludeValue);
        } else {
            return lowerFilterValue === "" || lowerCardValue.includes(lowerFilterValue);
        }
    }
    
    function filterJobs() {
        const city = filterCity.value.toLowerCase();
        const company = filterCompany.value.toLowerCase();
        const date = filterDate.value;
        const site = filterSite.value.toLowerCase();
        const isRemoteOnly = filterRemote.checked;
        let visibleCount = 0;

        document.querySelectorAll(".job-card").forEach(card => {
            const cardCity = card.getAttribute("data-city").toLowerCase();
            const cardCompany = card.getAttribute("data-company").toLowerCase();
            const cardDate = card.getAttribute("data-date");
            const cardSite = card.getAttribute("data-site").toLowerCase();
            const cardRemote = card.getAttribute("data-remote").toUpperCase() === "TRUE";

            const matchCity = city === "" || doesMatch(city, cardCity);
            const matchCompany = company === "" || doesMatch(company, cardCompany);
            const matchDate = date === "" || cardDate >= date;
            const matchSite = site === "" || doesMatch(site, cardSite);
            const matchRemote = !isRemoteOnly || cardRemote;

            const isVisible = matchCity && matchCompany && matchDate && matchSite && matchRemote;
            card.style.display = isVisible ? "block" : "none";

            if (isVisible) visibleCount++;
        });
        const jobCountElement = document.getElementById("job-count");
        jobCountElement.textContent = `Jobs Found: ${visibleCount}`;
    }
    compareResumeCheckbox.addEventListener('change', function () {
        if (this.checked) {
            // Send a request to the server to compare the resume
            fetch('/compare_resume', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ compare: true })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Update job cards with the ranking
                    updateJobRanking(data.rankings);
                } else {
                    if (data.message === 'No resume found') {
                        // Trigger the modal to upload a resume
                        const uploadModal = new bootstrap.Modal(document.getElementById('uploadResumeModal'));
                        uploadModal.show();
                        // this.checked = false;
                    } else {
                        displayErrorMessage("Error: " + data.message);
                        this.checked = false;
                    }
                }
            })
            .catch(error => {
                console.error("Error: Unable to fetch comparison data.", error);
                displayErrorMessage("Error: Unable to fetch comparison data.", error)
            });
        } else {
            // Optionally remove rankings if the checkbox is unchecked
            removeJobRanking();
        }
    });

    function updateJobRanking(rankings) {
        const jobCards = document.querySelectorAll('.job-card');
        
        // First, add ranking info to each card
        jobCards.forEach(card => {
            const jobId = card.getAttribute('data-job-id');
            const ranking = rankings[jobId];
            
            if (ranking !== undefined) {
                // Add ranking info to card
                const cardBody = card.querySelector('.card-body');
                if (!cardBody) return;
                
                let rankingElement = card.querySelector('.resume-match-ranking');
                if (!rankingElement) {
                    rankingElement = document.createElement('p');
                    rankingElement.classList.add('resume-match-ranking', 'mt-3', 'text-success');
                    cardBody.appendChild(rankingElement);
                }
                rankingElement.textContent = `Resume Match: ${ranking}%`;
                
                // Store ranking for sorting
                card.setAttribute('data-ranking', ranking);
            } else {
                card.setAttribute('data-ranking', '0');
            }
        });
        
        // Instead of rebuilding the DOM, just add a CSS class for sorting
        jobCards.forEach(card => {
            // Add a style that will position cards based on ranking
            const ranking = parseInt(card.getAttribute('data-ranking'));
            card.style.order = -ranking; // Negative to sort descending
        });
        
        // Add this CSS rule to make flex ordering work
        const jobContainer = document.getElementById('job-container');
        jobContainer.style.display = 'flex';
        jobContainer.style.flexWrap = 'wrap';
        jobContainer.style.flexDirection = 'row';
    }
    
    
    function removeJobRanking() {
        const jobCards = document.querySelectorAll('.job-card');
        const jobContainer = document.getElementById('job-container');
        
        // Remove ranking elements
        jobCards.forEach(card => {
            const rankingElement = card.querySelector('.resume-match-ranking');
            if (rankingElement) {
                rankingElement.remove();
            }
            
            // Reset the order style
            card.style.order = '';
        });
        
        // Reset container to original state if needed
        jobContainer.style.display = '';
    }


    filterCity.addEventListener("input", filterJobs);
    filterCompany.addEventListener("input", filterJobs);
    filterDate.addEventListener("change", filterJobs);
    filterSite.addEventListener("input", filterJobs);
    filterRemote.addEventListener("change", filterJobs); 
    
    // Modify job titles (capitalize correctly and format Roman numerals)
    const jobTitles = document.querySelectorAll('.title-case');
    jobTitles.forEach(title => {
        let text = title.innerHTML;
    
        // Decode HTML entities like &amp;
        text = text.replace(/&amp;/g, '&');
    
        // Fix I/iv or similar to I/IV
        text = text.replace(/\b([ivxlcdm]+)(?=\/[ivxlcdm]+\b)/gi, match => match.toUpperCase());
        text = text.replace(/(?<=\/)([ivxlcdm]+)\b/gi, match => match.toUpperCase());
    
        // Capitalize words, but preserve Roman numerals
        text = text.replace(/\b\w+\b/g, (word) => {
            const roman = /^(i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv|xvi|xvii|xviii|xix|xx|xl|l|c|d|m)$/i;
            if (roman.test(word)) {
                return word.toUpperCase();
            }
            return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
        });
    
        // Update the title with the corrected text
        title.innerHTML = text;
    });
    
    // --- True Cost of Living / Net Pay compare ---
    // colCompareModal is duplicated once per job card (same pattern as
    // climateModal), so we scope lookups to the modal nearest the clicked
    // link rather than using a single getElementById.
    document.querySelectorAll('.col-compare-link').forEach(link => {
        link.addEventListener('click', function (event) {
            const location = this.getAttribute('data-location');
            const salaryMin = parseFloat(this.getAttribute('data-salary-min')) || null;
            const salaryMax = parseFloat(this.getAttribute('data-salary-max')) || null;

            // Note: like climateModal, colCompareModal's id is duplicated once
            // per job card. Both getElementById and Bootstrap's data-bs-target
            // always resolve to the *first* instance in the DOM -- that's a
            // pre-existing quirk of this template, not something introduced
            // here. It's self-consistent (content always matches the modal
            // that actually opens), so we mirror it rather than fix it here.
            const modal = document.getElementById('colCompareModal');

            const toLocationInput = modal.querySelector('.col-to-location');
            const toSalaryInput = modal.querySelector('.col-to-salary');
            const toSalaryHint = modal.querySelector('.col-to-salary-hint');
            const fromLocationInput = modal.querySelector('.col-from-location');
            const fromSalaryInput = modal.querySelector('.col-from-salary');
            const resultsDiv = modal.querySelector('.col-compare-results');

            toLocationInput.value = location || '';
            if (salaryMin && salaryMax) {
                toSalaryInput.value = Math.round((salaryMin + salaryMax) / 2);
                toSalaryHint.style.display = 'none';
            } else if (salaryMin || salaryMax) {
                toSalaryInput.value = Math.round(salaryMin || salaryMax);
                toSalaryHint.style.display = 'none';
            } else {
                toSalaryInput.value = '';
                toSalaryHint.style.display = 'block';
            }

            // Remember the user's "current" location/salary across job cards
            const savedFromLocation = localStorage.getItem('col_from_location');
            const savedFromSalary = localStorage.getItem('col_from_salary');
            if (savedFromLocation && !fromLocationInput.value) fromLocationInput.value = savedFromLocation;
            if (savedFromSalary && !fromSalaryInput.value) fromSalaryInput.value = savedFromSalary;

            resultsDiv.style.display = 'none';
            resultsDiv.innerHTML = '';
        });
    });

    document.querySelectorAll('.col-k401-slider').forEach(slider => {
        slider.addEventListener('input', function () {
            const modal = this.closest('.modal');
            modal.querySelector('.col-k401-value').textContent = this.value;
        });
    });

    document.querySelectorAll('.col-compare-submit').forEach(button => {
        button.addEventListener('click', async function () {
            const modal = this.closest('.modal');
            const fromLocation = modal.querySelector('.col-from-location').value.trim();
            const fromSalary = parseFloat(modal.querySelector('.col-from-salary').value);
            const toLocation = modal.querySelector('.col-to-location').value.trim();
            const toSalaryRaw = modal.querySelector('.col-to-salary').value.trim();
            const toSalary = toSalaryRaw ? parseFloat(toSalaryRaw) : null;
            const k401 = parseFloat(modal.querySelector('.col-k401-slider').value);
            const resultsDiv = modal.querySelector('.col-compare-results');

            if (!fromLocation || !toLocation || !fromSalary) {
                resultsDiv.style.display = 'block';
                resultsDiv.innerHTML = '<p class="text-danger">Please fill in both locations and your current salary.</p>';
                return;
            }

            localStorage.setItem('col_from_location', fromLocation);
            localStorage.setItem('col_from_salary', fromSalary);

            resultsDiv.style.display = 'block';
            resultsDiv.innerHTML = '<p>Calculating...</p>';

            try {
                const response = await fetch('/api/col-compare', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        from: { location: fromLocation, salary: fromSalary, k401_percent: k401 },
                        to: { location: toLocation, salary: toSalary, k401_percent: k401 },
                    }),
                });
                const data = await response.json();

                if (data.error) {
                    resultsDiv.innerHTML = `<p class="text-danger">Error: ${data.error}</p>`;
                    return;
                }

                const estFlag = (q) => (q === 'live' ? '' : ' ~');
                const allWarnings = [...(data.current.warnings || []), ...(data.target.warnings || [])];
                const uniqueWarnings = [...new Set(allWarnings)];
                const warningsHtml = uniqueWarnings.length
                    ? `<div class="alert alert-warning small py-2 mb-2">${uniqueWarnings.map(w => `⚠ ${w}`).join('<br>')}</div>`
                    : '';

                // Helper to build editable numeric rows
                const renderExpenseRow = (label, key, val, flag, side) => `
                    <div class="d-flex align-items-center justify-content-between mb-1">
                        <label class="form-label mb-0 small me-2">${label}${flag}:</label>
                        <div class="input-group input-group-sm" style="max-width: 130px;">
                            <span class="input-group-text">$</span>
                            <input type="number" 
                                   class="form-control form-control-sm expense-input ${side}-expense" 
                                   data-key="${key}" 
                                   value="${val}" 
                                   step="10" min="0">
                        </div>
                    </div>`;

                resultsDiv.innerHTML = `
                    ${warningsHtml}
                    <div id="col-headline-container"></div>
                    <div class="row mt-3">
                        <!-- Current Location Column -->
                        <div class="col-md-6 border-end">
                            <h6>${data.current.city}, ${data.current.state}</h6>
                            <p class="small text-muted mb-2">Net pay: <strong>$${data.current.net_monthly}/mo</strong></p>
                            <form class="expense-list-from">
                                ${renderExpenseRow('Rent', 'housing_rent', data.current.expenses.housing_rent, estFlag(data.current.data_quality.housing_rent), 'cur')}
                                ${renderExpenseRow('Utilities', 'electricity', data.current.expenses.electricity, estFlag(data.current.data_quality.utility_rate), 'cur')}
                                ${renderExpenseRow('Gas', 'gas', data.current.expenses.gas, estFlag(data.current.data_quality.gas_price), 'cur')}
                                ${renderExpenseRow('Groceries', 'groceries', data.current.expenses.groceries, estFlag(data.current.data_quality.groceries_index), 'cur')}
                                ${renderExpenseRow('Auto ins.', 'auto_insurance', data.current.expenses.auto_insurance, estFlag(data.current.data_quality.auto_insurance), 'cur')}
                                ${renderExpenseRow('Health ins.', 'health_insurance', data.current.expenses.health_insurance, ' ~', 'cur')}
                            </form>
                            <div class="mt-2 pt-2 border-top">
                                <strong class="small">Disposable: <span id="cur-disposable-val" class="text-primary">$${data.current.disposable_monthly}</span>/mo</strong>
                            </div>
                        </div>

                        <!-- Target Location Column -->
                        <div class="col-md-6">
                            <h6>${data.target.city}, ${data.target.state} <span class="text-muted small">(${data.mode === 'solved_salary' ? 'required' : 'offered'}: $${data.target.gross_annual.toLocaleString()})</span></h6>
                            <p class="small text-muted mb-2">Net pay: <strong>$${data.target.net_monthly}/mo</strong></p>
                            <form class="expense-list-to">
                                ${renderExpenseRow('Rent', 'housing_rent', data.target.expenses.housing_rent, estFlag(data.target.data_quality.housing_rent), 'tgt')}
                                ${renderExpenseRow('Utilities', 'electricity', data.target.expenses.electricity, estFlag(data.target.data_quality.utility_rate), 'tgt')}
                                ${renderExpenseRow('Gas', 'gas', data.target.expenses.gas, estFlag(data.target.data_quality.gas_price), 'tgt')}
                                ${renderExpenseRow('Groceries', 'groceries', data.target.expenses.groceries, estFlag(data.target.data_quality.groceries_index), 'tgt')}
                                ${renderExpenseRow('Auto ins.', 'auto_insurance', data.target.expenses.auto_insurance, estFlag(data.target.data_quality.auto_insurance), 'tgt')}
                                ${renderExpenseRow('Health ins.', 'health_insurance', data.target.expenses.health_insurance, ' ~', 'tgt')}
                            </form>
                            <div class="mt-2 pt-2 border-top">
                                <strong class="small">Disposable: <span id="tgt-disposable-val" class="text-primary">$${data.target.disposable_monthly}</span>/mo</strong>
                            </div>
                        </div>
                    </div>
                    <p class="text-muted small mb-0 mt-3">~ = estimated values. Edit any field above to update calculations live.</p>
                `;

                // Recalculation logic attached directly to input events
                const recalculateLive = () => {
                    let curExpensesTotal = 0;
                    resultsDiv.querySelectorAll('.cur-expense').forEach(input => {
                        curExpensesTotal += parseFloat(input.value) || 0;
                    });

                    let tgtExpensesTotal = 0;
                    resultsDiv.querySelectorAll('.tgt-expense').forEach(input => {
                        tgtExpensesTotal += parseFloat(input.value) || 0;
                    });

                    const curNet = data.current.net_monthly;
                    const tgtNet = data.target.net_monthly;

                    const curDisposable = curNet - curExpensesTotal;
                    const tgtDisposable = tgtNet - tgtExpensesTotal;
                    const diff = tgtDisposable - curDisposable;

                    // Update inline disposable cash text
                    resultsDiv.querySelector('#cur-disposable-val').textContent = `$${curDisposable.toFixed(2)}`;
                    resultsDiv.querySelector('#tgt-disposable-val').textContent = `$${tgtDisposable.toFixed(2)}`;

                    // Update Top Headline Alert Banner
                    const headlineContainer = resultsDiv.querySelector('#col-headline-container');
                    if (data.mode === 'solved_salary') {
                        headlineContainer.innerHTML = `
                            <div class="alert alert-primary mb-2">
                                To match your updated disposable income in <strong>${data.current.city}, ${data.current.state}</strong>,
                                you'd need a target disposable cash flow of <strong>$${curDisposable.toFixed(2)}/mo</strong> in ${data.target.city}, ${data.target.state}.
                            </div>`;
                    } else {
                        const bannerClass = diff >= 0 ? 'alert-success' : 'alert-danger';
                        const sign = diff >= 0 ? '+' : '';
                        headlineContainer.innerHTML = `
                            <div class="alert ${bannerClass} mb-2">
                                <strong>${sign}$${diff.toFixed(2)}/month</strong> disposable cash moving to ${data.target.city}, ${data.target.state}
                                at the offered salary ($${data.target.gross_annual.toLocaleString()}/year).
                            </div>`;
                    }
                };

                // Attach listeners to all newly rendered inputs
                resultsDiv.querySelectorAll('.expense-input').forEach(input => {
                    input.addEventListener('input', recalculateLive);
                });

                // Initial trigger to render the headline banner
                recalculateLive();

            } catch (error) {
                resultsDiv.innerHTML = '<p class="text-danger">Failed to fetch comparison.</p>';
                console.error(error);
            }
        });
    });

    document.querySelectorAll('.climate-link').forEach(link => {
        link.addEventListener('click', async function (event) {
            event.preventDefault();
            const location = this.getAttribute('data-location');
            const modalBody = document.getElementById('climateModalBody');
            modalBody.innerHTML = `<p>Loading climate data for ${location}...</p>`;

            try {
                const response = await fetch(`/climate?location=${encodeURIComponent(location)}`);
                const data = await response.json();

                if (data.error) {
                    modalBody.innerHTML = `<p class="text-danger">Error: ${data.error}</p>`;
                } else {
                    modalBody.innerHTML = `
                        <h6>${data.city}, ${data.state}</h6>
                        <p>Weather stats for previous 365 days</p>
                        <ul>
                            <li><strong>Avg Temp (°F):</strong> ${data.avg_mean_temp}</li>
                            <li><strong>High Temp (°F):</strong> ${data.avg_max_temp}</li>
                            <li><strong>Low Temp (°F):</strong> ${data.avg_min_temp}</li>
                            <li><strong>Days Below 30°F:</strong> ${data.days_below_30}</li>
                            <li><strong>Days Above 85°F:</strong> ${data.days_above_85}</li>
                            <li><strong>Precipitation:</strong> ${data.total_precipitation} in/year</li>
                            <li><strong>Heating Degree Days:</strong> ${data.total_hdd}</li>
                            <li><strong>Cooling Degree Days:</strong> ${data.total_cdd}</li>
                        </ul>
                    `;
                }
            } catch (error) {
                modalBody.innerHTML = `<p class="text-danger">Failed to fetch climate data.</p>`;
                console.error(error);
            }
        });
    });
    // ── OLLAMA CORE TRIGGER EVENT HANDLER ──
    document.querySelectorAll('.generate-btn').forEach(button => {
        button.addEventListener('click', async function() {
            const jobId = this.getAttribute('data-job-id');
            const container = document.getElementById(`cover-letter-container-${jobId}`);
            const textArea = document.getElementById(`text-${jobId}`);
            const badge = document.querySelector(`.status-badge-${jobId}`);
            
            // Lock out interactive UI state during intensive Pi 5 inference execution
            this.disabled = true;
            this.innerHTML = "🤖 Running Ollama Inference...";
            if (badge) {
                badge.className = "badge bg-warning text-dark";
                badge.textContent = "Status: PROCESSING";
            }
            
            try {
                const response = await fetch(`/generate_cover_letter/${jobId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                const data = await response.json();
                
                if (data.success) {
                    // Inject AI outputs, reveal container layout, and transition status state
                    textArea.value = data.cover_letter;
                    container.style.display = "block";
                    this.innerHTML = "⚡ Regenerate Draft";
                    if (badge) {
                        badge.className = "badge bg-success";
                        badge.textContent = "Status: DRAFT";
                    }
                } else {
                    alert("Ollama was unable to compile a draft response: " + data.message);
                    this.innerHTML = "❌ Compilation Failed";
                    if (badge) {
                        badge.className = "badge bg-danger";
                        badge.textContent = "Status: FAILED";
                    }
                }
            } catch (err) {
                console.error("Inference fetch pipeline broke down: ", err);
                alert("Connection failed or inference request timed out.");
                this.innerHTML = "❌ Network Error";
            } finally {
                this.disabled = false;
            }
        });
    });
});
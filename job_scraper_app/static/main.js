// static/scripts.js

function showLoading() {
    document.getElementById("loading").style.display = "block";
}

// Initialize Bootstrap tooltips
document.addEventListener('DOMContentLoaded', function () {
    var tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltipTriggerList.forEach(function (tooltipTriggerEl) {
        new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Form validation and encoding
    document.querySelector("form").addEventListener("submit", function(event) {
        let siteName = document.getElementById("site_name").value;
        let searchTerm = document.getElementById("search_term").value;
        let location = document.getElementById("location").value;
        let resultsWanted = document.getElementById("results_wanted").value;
        let hoursOld = document.getElementById("hours_old").value;

        // Validate whole number inputs
        if (!Number.isInteger(Number(resultsWanted)) || !Number.isInteger(Number(hoursOld))) {
            alert("Please enter a whole number for 'No Results Wanted' and 'Hours Old'.");
            event.preventDefault(); // Prevent form submission if validation fails
            return;
        }

        // Encode inputs before submission
        document.getElementById("site_name").value = encodeInput(siteName);
        document.getElementById("search_term").value = encodeInput(searchTerm);
        document.getElementById("location").value = encodeInput(location);
    });
});

function encodeInput(input) {
    const textarea = document.createElement('textarea');
    textarea.textContent = input;
    return textarea.innerHTML;
}

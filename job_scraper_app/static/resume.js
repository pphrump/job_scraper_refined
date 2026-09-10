document.addEventListener('DOMContentLoaded', function() {
    const preElement = document.getElementById('resume-content');
    const filename = "{{ filename|default('') }}";
    
    if (preElement && filename && filename.endsWith('.txt')) {
        fetch('{{ url_for("view_resume", filename=filename) if filename else "#" }}')
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to fetch resume file');
            }
            return response.text();
        })
        .then(data => {
            preElement.textContent = data;
        })
        .catch(error => {
            console.error('Error fetching text file:', error);
            preElement.textContent = 'Error loading resume content. Please try uploading again.';
        });
    }

    const uploadResumeForm = document.getElementById('resume-upload-form');
    const uploadErrorMessage = document.getElementById('upload-error-message');
    const uploadSuccessMessage = document.getElementById('upload-success-message');
    
    if (uploadResumeForm) {
        uploadResumeForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            // Clear previous messages
            uploadErrorMessage.style.display = 'none';
            uploadSuccessMessage.style.display = 'none';

            const formData = new FormData(this);

            fetch('/upload_resume', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    uploadSuccessMessage.textContent = 'Resume uploaded successfully!';
                    uploadSuccessMessage.style.display = 'block';
                    
                    // Get the filename from the form input
                    const fileInput = document.getElementById('resume-file');
                    const filename = fileInput.files[0].name;
                    const secureFilename = filename.replace(/[^a-zA-Z0-9_.-]/g, '_'); // Basic sanitization
                    
                    // Update the page content to show the resume
                    const cardBody = document.querySelector('.card-body');
                    if (cardBody) {
                        // Check file type and update content accordingly
                        if (filename.toLowerCase().endsWith('.pdf')) {
                            cardBody.innerHTML = `<iframe src="/view_resume/${secureFilename}" width="100%" height="800px"></iframe>`;
                        } else if (filename.toLowerCase().endsWith('.txt')) {
                            cardBody.innerHTML = `
                                <div class="bg-light p-3 rounded">
                                    <pre id="resume-content" class="mb-0">Loading text content...</pre>
                                </div>`;
                            
                            // Fetch the text content
                            fetch(`/view_resume/${secureFilename}`)
                                .then(response => response.text())
                                .then(text => {
                                    document.getElementById('resume-content').textContent = text;
                                })
                                .catch(error => {
                                    document.getElementById('resume-content').textContent = 'Error loading resume content.';
                                });
                        } else if (filename.toLowerCase().endsWith('.docx')) {
                            cardBody.innerHTML = `
                                <div class="alert alert-info">
                                    <p>To view your DOCX resume, please download it:</p>
                                    <a href="/view_resume/${secureFilename}" class="btn btn-outline-primary" download="${secureFilename}">Download Resume</a>
                                </div>`;
                        } else {
                            cardBody.innerHTML = `<p class="text-danger">Unsupported resume format.</p>`;
                        }
                    }
                    
                    // Close the modal after a short delay
                    setTimeout(() => {
                        const modal = bootstrap.Modal.getInstance(document.getElementById('uploadResumeModal'));
                        if (modal) {
                            modal.hide();
                        }
                    }, 1500);
                } else {
                    uploadErrorMessage.textContent = data.message || "Unknown error occurred";
                    uploadErrorMessage.style.display = 'block';
                }
            })
            .catch(error => {
                console.error("Error uploading resume:", error);
                uploadErrorMessage.textContent = "An error occurred during upload";
                uploadErrorMessage.style.display = 'block';
            });
        });
    }
    
    // Check if filename exists using JavaScript variable
    const hasFilename = Boolean(filename);
    if (!hasFilename) {
        // If no filename, show the upload modal automatically
        const uploadResumeModal = new bootstrap.Modal(document.getElementById('uploadResumeModal'));
        uploadResumeModal.show();
    }
});
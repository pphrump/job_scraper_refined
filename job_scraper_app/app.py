import os
import secrets
from flask import Flask, render_template, request, redirect, url_for, send_file, session, jsonify, send_file
from job_scraper import fetch_jobs, filter_jobs, filter_pay
from utils import get_climate_data, write_to_csv, allowed_file, sanitize_input, read_resume, compare_jobs_to_resume, ensure_nltk_data
import pandas as pd
import logging
from werkzeug.utils import secure_filename
from utils import normalize_location
from utils.col_utils import calculate_takehome_and_expenses, calculate_equivalent_salary, solve_required_salary

ensure_nltk_data()
app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

app.secret_key = secrets.token_hex(16) 
# Folder to store the resume
RESUME_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resume')
app.config['RESUME_FOLDER'] = RESUME_FOLDER
app.config['ALLOWED_EXTENSIONS'] = {'txt', 'pdf', 'docx'}
cached_jobs = []

@app.route('/', methods=['GET', 'POST'])
def index():
    ALLOWED_SITES = {"indeed", "glassdoor", "linkedin"}
    excluded_titles_default = 'Manager, Behavior, Sales, Retail, Temporary, Principal, President, CEO, Nurse, RN, Physician, Dentist'
    warning_message = None  # Initialize warning message
    common_exclusions_path = os.path.join(app.root_path, 'CommonExclusions.txt')

    try:
        if os.path.isfile(common_exclusions_path):
            with open(common_exclusions_path, 'r') as file:
                excluded_titles_default = file.read()
        else:
            # Log the issue if file doesn't exist
            logging.warning(f"Warning: {common_exclusions_path} does not exist. Using default exclusions.")
    except Exception as e:
        # Catch any exceptions (like permission issues) and log them
        logging.error(f"Error reading {common_exclusions_path}: {e}")
        logging.info("Using default exclusions.")  # You can log this as an info message

    if request.method == 'POST':
        # Clear all existing CSV files in the files directory
        files_dir = os.path.join(app.root_path, 'files')
        if os.path.exists(files_dir):
            for file in os.listdir(files_dir):
                if file.endswith('.csv'):
                    try:
                        os.remove(os.path.join(files_dir, file))
                    except PermissionError:
                        warning_message = f"Warning: Unable to delete {file}. The file might be open in another application."

        site_name_string = sanitize_input(request.form["site_name"].strip())
        site_name_list = [site.strip().lower() for site in site_name_string.split(",")] if site_name_string else ["indeed"]

        # Filter out invalid site names
        site_name = [site for site in site_name_list if site in ALLOWED_SITES]

        # Default to "indeed" if no valid site names are provided
        if not site_name:
            site_name = ["indeed"]
        search_term = sanitize_input(request.form['search_term'])
        locations = sanitize_input(request.form['location'])
        location_list = [loc.strip() for loc in locations.split(',')]
        # Create filename location
        if len(location_list) == 1:
            location_for_filename = location_list[0]
        else:
            location_for_filename = "Multiple_Locations"

        is_remote = request.form.get('is_remote') == 'on'
        try:
            results_wanted = int(request.form['results_wanted'])
            hours_old = int(request.form['hours_old'])
        except ValueError:
            session['success'] = False
            session['message'] = "Error: Please enter a whole number for 'No Results Wanted' and 'Hours Old'."
            return redirect(url_for('index'))
        excluded_job_types = sanitize_input(request.form['excluded_job_types'])
        excluded_titles = sanitize_input(request.form['excluded_titles'])

        min_hourly = request.form.get('min_hourly', '').strip()
        min_annual = request.form.get('min_annual', '').strip()
        try:
            min_hourly = float(min_hourly) if min_hourly else None
            min_annual = float(min_annual) if min_annual else None
        except ValueError:
            session['success'] = False
            session['message'] = "Error: Please enter a valid number for 'Min Hourly Rate' and 'Min Annual Salary'."
            return redirect(url_for('index'))

        # Fetch jobs
        try:
            # Fetch jobs
            jobs = fetch_jobs(search_term, locations, results_wanted, hours_old, is_remote, site_name)
            if not jobs.empty and 'location' in jobs.columns:
                jobs['location'] = jobs['location'].apply(normalize_location)

            if jobs.empty:
                # Handle empty DataFrame case
                session['success'] = False
                session['message'] = "No jobs found for the given criteria."
            else:
                # Filter jobs
                filtered_jobs = filter_jobs(jobs, excluded_job_types, excluded_titles)
                # Filter pay
                if (min_hourly is not None or min_annual is not None):
                    filter_by_pay = filter_pay(filtered_jobs, min_hourly, min_annual)
                else:
                    filter_by_pay = filtered_jobs
                # Save to CSV
                csv_filename = write_to_csv(filter_by_pay, search_term, location_for_filename, app.root_path)

                # Store data in session
                session['success'] = True
                session['csv_filename'] = csv_filename
        except Exception as e:
            session['success'] = False
            session['message'] = str(e)
            
        # Redirect to index
        return redirect(url_for('index'))

    # Retrieve data from session
    success = session.pop('success', None)
    csv_filename = session.pop('csv_filename', None)
    message = session.pop('message', None)

    return render_template('index.html' , success=success, csv_filename=csv_filename, message=message, warning_message=warning_message, excluded_titles_default=excluded_titles_default)

def compare_resumes_logic():
    if check_resume():
        # print(f"compare resumes logic check resume: {check_resume()}")
        resume_text = read_resume(app.config['RESUME_FOLDER'], app.config['ALLOWED_EXTENSIONS'])
        # print(f"Resume text is: {resume_text[:200]}")
        job_rankings = compare_jobs_to_resume(cached_jobs, resume_text)
        return {'success': True, 'rankings': job_rankings}
    else:
        return {'success': False, 'message': 'No resume found'}
    
@app.route('/download_csv/<filename>', methods=['GET', 'POST'])
def download_csv(filename):
    file_path = os.path.join(app.root_path, 'files', filename)  # Adjust path as needed
    if not os.path.exists(file_path):
        return "Error: File not found!", 404
    return send_file(file_path,
                     mimetype='text/csv',
                     download_name=filename,
                     as_attachment=True)

@app.route('/resume')
def resume():
    resume_data = get_resume_data()
    return render_template('resume_display.html', 
                          file_exists=resume_data['exists'], 
                          filename=resume_data.get('filename'))

# Check if resume exists in folder and return its name
def get_resume_data():
    for filename in os.listdir(app.config['RESUME_FOLDER']):
        if allowed_file(filename, app.config['ALLOWED_EXTENSIONS']):
            return {'exists': True, 'filename': filename}
    return {'exists': False, 'filename': None}

@app.route('/view_resume/<filename>')
@app.route('/view_resume/<filename>')
def view_resume(filename):
    try:
        # Ensure the file exists
        file_path = os.path.join(os.path.abspath(app.config['RESUME_FOLDER']), filename)
        if not os.path.exists(file_path):
            return f"Error: File {filename} not found", 404
            
        # Determine the correct MIME type
        if filename.endswith('.pdf'):
            mimetype = 'application/pdf'
        elif filename.endswith('.txt'):
            mimetype = 'text/plain'
        elif filename.endswith('.docx'):
            mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        else:
            mimetype = 'application/octet-stream'
            
        return send_file(file_path, mimetype=mimetype)
    except Exception as e:
        return f"Error serving file: {str(e)}", 500

@app.route('/upload_resume_compare', methods=['POST'])
def upload_resume_compare():
    if 'resume' not in request.files:
        return jsonify({'success': False, 'message': 'No file part'}), 400
    
    file = request.files['resume']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file'}), 400

    if file and allowed_file(file.filename, app.config['ALLOWED_EXTENSIONS']):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['RESUME_FOLDER'], filename))
        try:
            # Assuming compare_resume is a function that handles the comparison and ranking
            result = compare_resumes_logic()  # Call the function that updates the rankings

            if result['success']:  # Assuming compare_resume returns a dict with a 'success' key
                return jsonify({
                    'success': True,
                    'message': 'Resume uploaded and rankings updated successfully.',
                    'rankings': result['rankings']  # Pass the rankings data back to the frontend
                }), 200
            else:
                return jsonify({'success': False, 'message': result['message']}), 400

        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    
    else:
        return jsonify({'success': False, 'message': 'Invalid file type'}), 400

@app.route('/upload_resume', methods=['POST'])
def upload_resume():
    """Basic resume upload without comparison"""
    if 'resume' not in request.files:
        return jsonify({'success': False, 'message': 'No file part'}), 400
    
    file = request.files['resume']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file'}), 400

    if file and allowed_file(file.filename, app.config['ALLOWED_EXTENSIONS']):
        # Create the directory if it doesn't exist
        os.makedirs(app.config['RESUME_FOLDER'], exist_ok=True)

        # Remove existing files in the resume folder
        for existing_file in os.listdir(app.config['RESUME_FOLDER']):
            if allowed_file(existing_file, app.config['ALLOWED_EXTENSIONS']):
                os.remove(os.path.join(app.config['RESUME_FOLDER'], existing_file))
        
        # Save the file
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['RESUME_FOLDER'], filename)
        file.save(file_path)
        
        return jsonify({
            'success': True,
            'message': 'Resume uploaded successfully.'
        }), 200
    else:
        return jsonify({'success': False, 'message': 'Invalid file type'}), 400
    
# Check if resume exists in folder
def check_resume():
    for filename in os.listdir(app.config['RESUME_FOLDER']):
        if allowed_file(filename, app.config['ALLOWED_EXTENSIONS']):
            return True
    return False


@app.route('/jobs')
def jobs():
    global cached_jobs
    # This will be the path to your CSV files directory
    files_dir = os.path.join(app.root_path, 'files')
    
    # List all CSV files in the directory (assuming these are your job files)
    csv_files = [f for f in os.listdir(files_dir) if f.endswith('.csv')]
    
    cached_jobs = []
    error_message = None  # Store error message if an exception occurs
    # If you have CSV files, read the most recent one
    if csv_files:
        # Sort by modification time to get the most recent
        csv_files.sort(key=lambda x: os.path.getmtime(os.path.join(files_dir, x)), reverse=True)
        most_recent_file = csv_files[0]
        
        file_path = os.path.join(files_dir, most_recent_file)
        try:
            df = pd.read_csv(file_path)
            df.rename(columns={df.columns[0]: 'id'}, inplace=True)
            # Convert DataFrame to list of lists for template
            cached_jobs = df.to_dict(orient='records')

        except Exception as e:
            error_message = f"Error reading CSV file: {most_recent_file}. It may be open in another application."
    
    return render_template('jobs.html', jobs=cached_jobs, error_message=error_message)

@app.route("/climate")
def get_climate():
    location = request.args.get("location")
    if not location:
        return jsonify({"error": "Location not specified"})
    
    try:
        # Split the location and unpack the first two values
        city, state, *_ = location.split(",")
        city = city.strip()
        state = state.strip()

    except ValueError:
        return jsonify({"error": "Invalid location format. Please use 'city, state'."})
    
    try:
        # Call the climate data function with city and state
        climate_data = get_climate_data(city, state)
        return jsonify(climate_data)

    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/col-compare', methods=['POST'])
def col_compare():
    """True Cost of Living / Net Pay comparison.

    Expects JSON: {
        "from": {"salary": 90000, "location": "Denver, CO", "k401_percent": 10},
        "to":   {"location": "Austin, TX", "salary": 95000 (optional), "k401_percent": 10}
    }

    'to.salary' is optional. If given (e.g. an actual listed salary from a
    job card), the response compares that real offer AND reports the salary
    that would actually be needed to match your current disposable income,
    so you can see the gap. If omitted, the required salary IS the answer --
    no need to guess or manually enter a number for the target job.
    """
    data = request.get_json(silent=True)
    if not data or 'from' not in data or 'to' not in data:
        return jsonify({"error": "Request must include 'from' and 'to' objects."}), 400

    try:
        from_data = data['from']
        to_data = data['to']

        from_salary = float(from_data['salary'])
        from_location = str(from_data['location']).strip()
        k401 = float(from_data.get('k401_percent', 10))
        to_location = str(to_data['location']).strip()

        if from_salary <= 0:
            return jsonify({"error": "'from' salary must be positive."}), 400
        if not from_location:
            return jsonify({"error": "'from' location is required."}), 400
        if not to_location:
            return jsonify({"error": "'to' location is required."}), 400

        current = calculate_takehome_and_expenses(from_salary, from_location, k401)

        to_salary_raw = to_data.get('salary')
        to_salary = float(to_salary_raw) if to_salary_raw not in (None, '') else None

        if to_salary and to_salary > 0:
            # Actual offer given: show it as-is, plus the required-salary
            # figure alongside it so the gap is visible. Reuses target's
            # already-fetched location expenses rather than fetching twice.
            target = calculate_takehome_and_expenses(to_salary, to_location, k401)
            required_salary = solve_required_salary(
                current['disposable_monthly'], target['state'], k401, target['monthly_expenses_total']
            )
            mode = 'actual_salary'
        else:
            # No salary given for the target: solve for it directly.
            current, target = calculate_equivalent_salary(from_salary, from_location, to_location, k401)
            required_salary = target['gross_annual']
            mode = 'solved_salary'

        net_monthly_difference = round(target['disposable_monthly'] - current['disposable_monthly'], 2)

        return jsonify({
            "current": current,
            "target": target,
            "net_monthly_difference": net_monthly_difference,
            "mode": mode,
            "required_salary_to_match": required_salary,
        })
    except (KeyError, ValueError) as e:
        return jsonify({"error": f"Invalid request data: {e}"}), 400
    except Exception as e:
        logging.error(f"Error in /api/col-compare: {e}")
        return jsonify({"error": "Internal error computing comparison."}), 500


@app.route('/compare_resume', methods=['POST'])
def compare_resume():
    try:
        data = request.get_json()
        # print(f"data from json for compare resume {data}")
        if data['compare']:
            result = compare_resumes_logic()
            return jsonify(result)
        else:
            return jsonify({'success': False, 'message': 'No comparison requested'}), 400
    except Exception as e:
        print(f"Error during comparison: {e}")
        return jsonify({'success': False, 'message': 'Internal Server Error'}), 500
    
if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)

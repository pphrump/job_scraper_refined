import hmac
import logging
import os
import secrets
from urllib.parse import urlparse

import pandas as pd
from flask import (
    Flask, Response, abort, jsonify, redirect, render_template, request,
    send_from_directory, session, url_for,
)
from werkzeug.utils import secure_filename

from job_scraper import fetch_jobs, filter_jobs, filter_pay
from utils import (
    allowed_file, compare_jobs_to_resume, ensure_nltk_data, get_climate_data,
    normalize_location, read_resume, sanitize_input, write_to_csv,
)
from utils.col_utils import (
    calculate_equivalent_salary, calculate_takehome_and_expenses,
    solve_required_salary,
)

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())

ensure_nltk_data()
app = Flask(__name__)

# ── Configuration (all secrets come from the environment / .env) ──────────────
_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    logging.warning(
        "SECRET_KEY is not set; using a random key. Sessions will reset on every "
        "restart. Set SECRET_KEY in your .env file."
    )
    _secret_key = secrets.token_hex(32)
app.secret_key = _secret_key

app.config.update(
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,  # reject uploads > 5 MB
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Set SESSION_COOKIE_SECURE=1 once you serve the app over HTTPS.
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "").lower() in ("1", "true", "yes"),
)

RESUME_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resume')
FILES_FOLDER = os.path.join(app.root_path, 'files')
app.config['RESUME_FOLDER'] = RESUME_FOLDER
app.config['ALLOWED_EXTENSIONS'] = {'txt', 'pdf', 'docx'}
os.makedirs(RESUME_FOLDER, exist_ok=True)
os.makedirs(FILES_FOLDER, exist_ok=True)

# NOTE: this is per-process state, so run exactly ONE gunicorn worker
# (the Dockerfile uses --workers 1 --threads 4).
cached_jobs = []

# Optional HTTP Basic auth. Enabled when APP_PASSWORD is set in the environment.
APP_USERNAME = os.environ.get("APP_USERNAME", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD")
if not APP_PASSWORD:
    logging.warning(
        "APP_PASSWORD is not set: the app (including your resume) is "
        "unauthenticated. Only expose it on localhost, or set APP_PASSWORD."
    )

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _authorized():
    auth = request.authorization
    if not auth or auth.username is None:
        return False
    user_ok = hmac.compare_digest(auth.username.encode(), APP_USERNAME.encode())
    pass_ok = hmac.compare_digest((auth.password or "").encode(), APP_PASSWORD.encode())
    return user_ok and pass_ok  # both compared first -> no short-circuit timing leak


@app.before_request
def guard_requests():
    if request.endpoint == "healthz":
        return None
    if APP_PASSWORD and not _authorized():
        return Response(
            "Authentication required", 401,
            {"WWW-Authenticate": 'Basic realm="Job Scraper"'},
        )
    # Basic CSRF defence: refuse state-changing requests that come from another site.
    if request.method in UNSAFE_METHODS:
        fetch_site = request.headers.get("Sec-Fetch-Site")
        if fetch_site is not None:
            # Sent by all modern browsers and unaffected by Referrer-Policy.
            if fetch_site not in ("same-origin", "none"):
                abort(403)
        else:
            # Older browsers / non-browser clients: fall back to the Origin header.
            origin = request.headers.get("Origin")
            if origin and urlparse(origin).netloc != request.host:
                abort(403)
    return None


@app.after_request
def add_security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    # "same-origin" (not "no-referrer"): with "no-referrer", browsers send
    # "Origin: null" on form POSTs, which breaks the same-site check above.
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


@app.errorhandler(413)
def too_large(_e):
    return jsonify({'success': False, 'message': 'File too large (max 5 MB).'}), 413


@app.route('/healthz')
def healthz():
    return "ok", 200


# ── Resume helpers ────────────────────────────────────────────────────────────
def _clear_resumes():
    for existing in os.listdir(RESUME_FOLDER):
        if allowed_file(existing, app.config['ALLOWED_EXTENSIONS']):
            os.remove(os.path.join(RESUME_FOLDER, existing))


def _save_resume(file):
    """Replace any existing resume with the uploaded one. Returns filename or None."""
    filename = secure_filename(file.filename or "")
    if not filename or not allowed_file(filename, app.config['ALLOWED_EXTENSIONS']):
        return None
    _clear_resumes()
    file.save(os.path.join(RESUME_FOLDER, filename))
    return filename


def check_resume():
    return any(
        allowed_file(f, app.config['ALLOWED_EXTENSIONS'])
        for f in os.listdir(RESUME_FOLDER)
    )


def get_resume_data():
    for filename in os.listdir(RESUME_FOLDER):
        if allowed_file(filename, app.config['ALLOWED_EXTENSIONS']):
            return {'exists': True, 'filename': filename}
    return {'exists': False, 'filename': None}


def compare_resumes_logic():
    if check_resume():
        resume_text = read_resume(RESUME_FOLDER, app.config['ALLOWED_EXTENSIONS'])
        job_rankings = compare_jobs_to_resume(cached_jobs, resume_text)
        return {'success': True, 'rankings': job_rankings}
    return {'success': False, 'message': 'No resume found'}


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route('/', methods=['GET', 'POST'])
def index():
    ALLOWED_SITES = {"indeed", "glassdoor", "linkedin"}
    excluded_titles_default = 'Manager, Behavior, Sales, Retail, Temporary, Principal, President, CEO, Nurse, RN, Physician, Dentist'
    warning_message = None
    common_exclusions_path = os.path.join(app.root_path, 'CommonExclusions.txt')

    try:
        if os.path.isfile(common_exclusions_path):
            with open(common_exclusions_path, 'r') as file:
                excluded_titles_default = file.read()
        else:
            logging.warning(f"{common_exclusions_path} does not exist. Using default exclusions.")
    except Exception as e:
        logging.error(f"Error reading {common_exclusions_path}: {e}")
        logging.info("Using default exclusions.")

    if request.method == 'POST':
        # Clear all existing CSV files in the files directory
        for file in os.listdir(FILES_FOLDER):
            if file.endswith('.csv'):
                try:
                    os.remove(os.path.join(FILES_FOLDER, file))
                except PermissionError:
                    warning_message = f"Warning: Unable to delete {file}. The file might be open in another application."

        site_name_string = sanitize_input(request.form["site_name"].strip())
        site_name_list = [site.strip().lower() for site in site_name_string.split(",")] if site_name_string else ["indeed"]
        site_name = [site for site in site_name_list if site in ALLOWED_SITES] or ["indeed"]

        search_term = sanitize_input(request.form['search_term'])
        locations = sanitize_input(request.form['location'])
        location_list = [loc.strip() for loc in locations.split(',')]
        location_for_filename = location_list[0] if len(location_list) == 1 else "Multiple_Locations"

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

        try:
            jobs = fetch_jobs(search_term, locations, results_wanted, hours_old, is_remote, site_name)

            # jobspy >= 1.2 doesn't raise when a site fails; it records the error.
            site_errors = getattr(jobs, "attrs", {}).get("errors")
            if site_errors:
                logging.warning(f"Site errors from jobspy: {site_errors}")

            if not jobs.empty and 'location' in jobs.columns:
                jobs['location'] = jobs['location'].apply(normalize_location)

            if jobs.empty:
                session['success'] = False
                session['message'] = "No jobs found for the given criteria."
                if site_errors:
                    failed = ", ".join(site_errors.keys())
                    session['message'] += f" (These sites reported errors: {failed}.)"
            else:
                filtered_jobs = filter_jobs(jobs, excluded_job_types, excluded_titles)
                if min_hourly is not None or min_annual is not None:
                    filter_by_pay = filter_pay(filtered_jobs, min_hourly, min_annual)
                else:
                    filter_by_pay = filtered_jobs
                csv_filename = write_to_csv(filter_by_pay, search_term, location_for_filename, app.root_path)
                session['success'] = True
                session['csv_filename'] = csv_filename
        except ValueError as e:
            # Input-validation errors (e.g. from jobspy) are safe and useful to show.
            session['success'] = False
            session['message'] = str(e)
        except Exception:
            logging.exception("Job fetch failed")
            session['success'] = False
            session['message'] = "Something went wrong while fetching jobs. Check the server logs."

        return redirect(url_for('index'))

    success = session.pop('success', None)
    csv_filename = session.pop('csv_filename', None)
    message = session.pop('message', None)

    return render_template(
        'index.html', success=success, csv_filename=csv_filename, message=message,
        warning_message=warning_message, excluded_titles_default=excluded_titles_default,
    )


@app.route('/download_csv/<filename>', methods=['GET', 'POST'])
def download_csv(filename):
    if not filename.lower().endswith('.csv'):
        abort(404)
    # send_from_directory refuses anything that escapes FILES_FOLDER.
    return send_from_directory(
        FILES_FOLDER, filename, mimetype='text/csv',
        as_attachment=True, download_name=filename,
    )


@app.route('/resume')
def resume():
    resume_data = get_resume_data()
    return render_template(
        'resume_display.html',
        file_exists=resume_data['exists'],
        filename=resume_data.get('filename'),
    )


@app.route('/view_resume/<filename>')
def view_resume(filename):
    if not allowed_file(filename, app.config['ALLOWED_EXTENSIONS']):
        abort(404)
    return send_from_directory(RESUME_FOLDER, filename)


@app.route('/upload_resume_compare', methods=['POST'])
def upload_resume_compare():
    if 'resume' not in request.files:
        return jsonify({'success': False, 'message': 'No file part'}), 400
    file = request.files['resume']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file'}), 400

    if not _save_resume(file):
        return jsonify({'success': False, 'message': 'Invalid file type'}), 400

    try:
        result = compare_resumes_logic()
        if result['success']:
            return jsonify({
                'success': True,
                'message': 'Resume uploaded and rankings updated successfully.',
                'rankings': result['rankings'],
            }), 200
        return jsonify({'success': False, 'message': result['message']}), 400
    except Exception:
        logging.exception("Resume comparison failed")
        return jsonify({'success': False, 'message': 'Internal error comparing resume.'}), 500


@app.route('/upload_resume', methods=['POST'])
def upload_resume():
    """Basic resume upload without comparison"""
    if 'resume' not in request.files:
        return jsonify({'success': False, 'message': 'No file part'}), 400
    file = request.files['resume']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file'}), 400

    if not _save_resume(file):
        return jsonify({'success': False, 'message': 'Invalid file type'}), 400
    return jsonify({'success': True, 'message': 'Resume uploaded successfully.'}), 200


@app.route('/jobs')
def jobs():
    global cached_jobs
    csv_files = [f for f in os.listdir(FILES_FOLDER) if f.endswith('.csv')]

    cached_jobs = []
    error_message = None
    if csv_files:
        csv_files.sort(key=lambda x: os.path.getmtime(os.path.join(FILES_FOLDER, x)), reverse=True)
        most_recent_file = csv_files[0]
        file_path = os.path.join(FILES_FOLDER, most_recent_file)
        try:
            df = pd.read_csv(file_path)
            df.rename(columns={df.columns[0]: 'id'}, inplace=True)
            cached_jobs = df.to_dict(orient='records')
        except Exception:
            logging.exception(f"Error reading {most_recent_file}")
            error_message = f"Error reading CSV file: {most_recent_file}. It may be open in another application."

    return render_template('jobs.html', jobs=cached_jobs, error_message=error_message)


@app.route("/climate")
def get_climate():
    location = request.args.get("location")
    if not location:
        return jsonify({"error": "Location not specified"})

    try:
        city, state, *_ = location.split(",")
        city = city.strip()
        state = state.strip()
    except ValueError:
        return jsonify({"error": "Invalid location format. Please use 'city, state'."})

    try:
        return jsonify(get_climate_data(city, state))
    except ValueError as e:
        return jsonify({"error": str(e)})
    except Exception:
        logging.exception("Climate lookup failed")
        return jsonify({"error": "Could not retrieve climate data."})


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
            target = calculate_takehome_and_expenses(to_salary, to_location, k401)
            required_salary = solve_required_salary(
                current['disposable_monthly'], target['state'], k401, target['monthly_expenses_total']
            )
            mode = 'actual_salary'
        else:
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
    except Exception:
        logging.exception("Error in /api/col-compare")
        return jsonify({"error": "Internal error computing comparison."}), 500


@app.route('/compare_resume', methods=['POST'])
def compare_resume():
    data = request.get_json(silent=True) or {}
    if not data.get('compare'):
        return jsonify({'success': False, 'message': 'No comparison requested'}), 400
    try:
        return jsonify(compare_resumes_logic())
    except Exception:
        logging.exception("Error during comparison")
        return jsonify({'success': False, 'message': 'Internal Server Error'}), 500


if __name__ == "__main__":
    # Local development ONLY. In Docker the app is served by gunicorn (see Dockerfile).
    debug = os.environ.get("FLASK_DEBUG") == "1"
    host = os.environ.get("HOST", "127.0.0.1")
    if debug and host not in ("127.0.0.1", "localhost"):
        raise SystemExit("Refusing to run the Werkzeug debugger on a non-loopback interface.")
    app.run(debug=debug, host=host, port=5000)

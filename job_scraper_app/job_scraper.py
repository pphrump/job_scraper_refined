from jobspy import scrape_jobs  # Make sure this is the correct package name
import pandas as pd
from requests.exceptions import ReadTimeout, RequestException
from difflib import SequenceMatcher
# import tls_client.exceptions

def deduplicate_jobs_fuzzy(jobs, site_priority=["indeed", "linkedin", "glassdoor"], similarity_threshold=0.85):
    """
    Remove duplicate jobs using fuzzy matching, keeping the highest priority site.
    
    Args:
        jobs: DataFrame of jobs
        site_priority: List of sites in order of preference
        similarity_threshold: How similar two jobs need to be (0-1) to be considered duplicates
    """
    if jobs.empty:
        return jobs
    
    jobs_copy = jobs.copy()
    
    # Normalize
    jobs_copy['title_normalized'] = jobs_copy['title'].str.lower().str.strip()
    jobs_copy['company_normalized'] = jobs_copy['company'].str.lower().str.strip()
    jobs_copy['location_normalized'] = jobs_copy['location'].str.lower().str.strip()
    
    # Site priority
    site_priority_map = {site: idx for idx, site in enumerate(site_priority)}
    jobs_copy['site_priority'] = jobs_copy['site'].str.lower().map(site_priority_map)
    jobs_copy['site_priority'] = jobs_copy['site_priority'].fillna(len(site_priority))
    
    # Sort by priority
    jobs_copy = jobs_copy.sort_values('site_priority')
    
    # Track which jobs to keep
    keep_indices = []
    seen_jobs = []
    
    for idx, row in jobs_copy.iterrows():
        is_duplicate = False
        current_job = f"{row['title_normalized']}|{row['company_normalized']}|{row['location_normalized']}"
        
        for seen_job in seen_jobs:
            similarity = SequenceMatcher(None, current_job, seen_job).ratio()
            if similarity >= similarity_threshold:
                is_duplicate = True
                break
        
        if not is_duplicate:
            keep_indices.append(idx)
            seen_jobs.append(current_job)
    
    jobs_deduped = jobs_copy.loc[keep_indices].drop(
        columns=['title_normalized', 'company_normalized', 'location_normalized', 'site_priority']
    )
    
    print(f"Removed {len(jobs) - len(jobs_deduped)} duplicate jobs (fuzzy matching)")
    
    return jobs_deduped

def fetch_jobs(search_term, locations, results_wanted, hours_old, is_remote=False, site_name=["indeed"]):
    """Fetch jobs from multiple sites and locations, combine results, and remove duplicates."""
    all_jobs = pd.DataFrame()
    errors = []
    
    # Define site priority
    site_priority = ["indeed", "linkedin", "glassdoor"]
    
    # If locations is a string, convert to list
    if isinstance(locations, str):
        locations = [loc.strip() for loc in locations.split(',')]
    
    # Loop through each location
    for location in locations:
        location = location.strip()
        print(f"\n=== Searching in: {location} ===")
        
        for site in site_name:
            try:
                scrape_args = {
                    "site_name": [site],
                    "search_term": search_term,
                    "location": location,
                    "results_wanted": results_wanted,
                    "hours_old": hours_old,
                    # "enforce_annual_salary": True,
                    "is_remote": is_remote
                }
                if site in ("indeed", "glassdoor"):
                    scrape_args["country_indeed"] = "USA"

                if site == "linkedin":
                    scrape_args["linkedin_fetch_description"] = True
                

                print(f"Scraping {site} in {location}...")
                jobs = scrape_jobs(**scrape_args)
                
                if not jobs.empty:
                    print(f"Found {len(jobs)} jobs from {site} in {location}")
                    all_jobs = pd.concat([all_jobs, jobs], ignore_index=True)
                    print(f"Total jobs so far: {len(all_jobs)}") 
                else:
                    print(f"No jobs found from {site} in {location}")
                
            except ReadTimeout:
                print(f"The request to {site} timed out.")
                errors.append(f"{site} ({location}): Request timed out")
                continue
            # except tls_client.exceptions.TLSClientExeption as e:
            #     print(f"TLS client exception occurred for {site}: {e}")
            #     errors.append(f"{site} ({location}): TLS client exception - {str(e)}")
            #     continue
            except RequestException as e:
                print(f"An error occurred while requesting from {site}: {e}")
                errors.append(f"{site} ({location}): Request exception - {str(e)}")
                continue
            except Exception as e:
                print(f"An unexpected error occurred for {site}: {e}")
                errors.append(f"{site} ({location}): Unexpected error - {str(e)}")
                continue
    
    if all_jobs.empty:
        if errors:
            raise Exception("Failed to fetch jobs from all sites. Errors: " + "; ".join(errors))
        else:
            raise Exception("No jobs found for the given criteria.")
    
    # Deduplicate across all locations and sites
    if len(site_name) > 1 or len(locations) > 1:
        all_jobs = deduplicate_jobs_fuzzy(all_jobs, site_priority)
    else:
        print("Single site and location scraped - skipping deduplication")
    
    if errors:
        print("Warning: Some sites/locations failed:", "; ".join(errors))
    
    return all_jobs


def filter_jobs(jobs, excluded_job_types_str, excluded_titles_str):
    # Convert excluded job types and titles to lists
    if not excluded_job_types_str.strip():
        excluded_job_types_list = []
    else:
        excluded_job_types_list = [job_type.strip().lower() for job_type in excluded_job_types_str.split(',')]

    if not excluded_titles_str.strip():
        excluded_titles_list = []
    else:
        excluded_titles_list = [title.strip().lower() for title in excluded_titles_str.split(',')]

    # Ensure jobs is a DataFrame
    if not isinstance(jobs, pd.DataFrame):
        raise ValueError("Jobs must be a Pandas DataFrame.")

    # Convert columns to lowercase for case-insensitive comparison
    jobs['job_type'] = jobs['job_type'].astype(str).str.lower()
    jobs['title'] = jobs['title'].astype(str).str.lower()

        # If there are excluded job types or titles, filter based on them
    if excluded_job_types_list:
        jobs = jobs[~jobs['job_type'].str.contains('|'.join(excluded_job_types_list), na=False)]
    if excluded_titles_list:
        jobs = jobs[~jobs['title'].str.contains('|'.join(excluded_titles_list), na=False)]

    return jobs

def filter_pay(jobs, min_hourly=None, min_annual=None):
    # Ensure jobs is a DataFrame
    if not isinstance(jobs, pd.DataFrame):
        raise ValueError("Jobs must be a Pandas DataFrame.")

    # Copy jobs to avoid modifying the original DataFrame
    filtered_jobs = jobs.copy()

    # Convert salary columns to numeric, handling errors gracefully
    filtered_jobs['min_amount'] = pd.to_numeric(filtered_jobs['min_amount'], errors='coerce')
    filtered_jobs['max_amount'] = pd.to_numeric(filtered_jobs['max_amount'], errors='coerce')

    # Ensure 'interval' column exists and is treated as lowercase
    if 'interval' not in filtered_jobs.columns:
        raise ValueError("Jobs DataFrame must contain an 'interval' column.")
    filtered_jobs['interval'] = filtered_jobs['interval'].astype(str).str.lower()

    # Apply filters
    if min_hourly is not None:
        filtered_jobs = filtered_jobs[
            ~((filtered_jobs['interval'] == 'hourly') & (filtered_jobs['min_amount'] < min_hourly))
        ]

    if min_annual is not None:
        filtered_jobs = filtered_jobs[
            ~((filtered_jobs['interval'] == 'yearly') & (filtered_jobs['min_amount'] < min_annual))
        ]

    return filtered_jobs
import re

filepath = "/app/.venv/lib/python3.11/site-packages/jobspy/glassdoor/__init__.py"

with open(filepath, "r") as f:
    content = f.read()

# Fix 1: Add urllib.parse import
old_import = "import re\nimport json\nimport requests"
new_import = "import re\nimport json\nimport requests\nfrom urllib.parse import quote"
content = content.replace(old_import, new_import)

# Fix 2: URL-encode the location in _get_location
old_url = 'url = f"{self.base_url}/findPopularLocationAjax.htm?maxLocationsToReturn=10&term={location}"'
new_url = 'url = f"{self.base_url}/findPopularLocationAjax.htm?maxLocationsToReturn=10&term={quote(location)}"'
content = content.replace(old_url, new_url)

# Fix 3: Only bail on GraphQL errors when job data is actually missing
old_error = '            if "errors" in res_json:\n                raise ValueError("Error encountered in API response")'
new_error = '            if "errors" in res_json and not res_json.get("data", {}).get("jobListings"):\n                raise ValueError("Error encountered in API response")'
content = content.replace(old_error, new_error)

# Fix 4: CSRF token URL returns 404 - use / instead
old_csrf = 'res = self.session.get(f"{self.base_url}/Job/computer-science-jobs.htm")'
new_csrf = 'res = self.session.get(f"{self.base_url}/")'
content = content.replace(old_csrf, new_csrf)

with open(filepath, "w") as f:
    f.write(content)

print("Patch applied successfully. Verifying changes...")

# Verify
with open(filepath, "r") as f:
    patched = f.read()

checks = [
    ("urllib.parse import", "from urllib.parse import quote" in patched),
    ("URL encoding fix", "quote(location)" in patched),
    ("GraphQL error fix", 'not res_json.get("data", {}).get("jobListings")' in patched),
    ("CSRF token fix", 'self.base_url}/"' in patched),
]

for name, result in checks:
    print(f"  {'OK' if result else 'FAILED'}: {name}")
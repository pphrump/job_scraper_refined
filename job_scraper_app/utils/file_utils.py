import os
from datetime import datetime

def write_to_csv(df, search_term, location, root_path):
    current_date = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    location_cleaned = location.replace(',', '_').replace(' ', '_')
    filename = f"{search_term}_{location_cleaned}_{current_date}.csv"
    save_directory = os.path.join(root_path, 'files')
    os.makedirs(save_directory, exist_ok=True)
    file_path = os.path.join(save_directory, filename)
    df.to_csv(file_path, index=False)
    return filename

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

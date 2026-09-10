import os
import math
import pymupdf
from docx import Document
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# ============================================
# MODULE LEVEL - Load model once when file is imported
# ============================================
sbert_model = SentenceTransformer('all-MiniLM-L6-v2')

def read_resume(folder, allowed_extensions):
    for file_name in os.listdir(folder):
        if any(file_name.endswith(ext) for ext in allowed_extensions):
            resume_path = os.path.join(folder, file_name)
            if os.path.exists(resume_path):
                return extract_text_from_resume(resume_path)
    return ""

def chunk_text(text, max_words=180, overlap=40):
    """
    Split text into overlapping word-based chunks.
    all-MiniLM-L6-v2 has a 256 word-piece limit; 180 words gives comfortable
    headroom for sub-word tokenisation while keeping chunks meaningful.
    Overlap prevents skills that straddle a boundary from being lost.
    """
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += max_words - overlap
    return chunks or [text]


def encode_with_chunking(text, model):
    """
    Encode a (potentially long) text by averaging the embeddings of its chunks.
    This avoids the silent truncation that occurs when the full text exceeds the
    model's token limit.
    """
    chunks = chunk_text(text)
    embeddings = model.encode(chunks, convert_to_tensor=False)
    # Mean-pool across chunks so the final vector represents the whole document
    return embeddings.mean(axis=0)


def compare_jobs_to_resume(jobs, resume_text):
    job_rankings = {}

    # Encode the full resume once using chunked mean-pooling so that no content
    # is silently truncated by the model's 256 word-piece limit.
    resume_embedding = encode_with_chunking(resume_text, sbert_model)

    for job in jobs:
        description = job.get("description")
        if not description or (isinstance(description, float) and math.isnan(description)):
            ranking = 0
        else:
            # Semantic similarity via SBERT (good at understanding meaning)
            sbert_score = calculate_similarity_sbert(resume_embedding, description)

            # Keyword overlap via TF-IDF (good at catching exact skill/tool names)
            tfidf_score = calculate_similarity(resume_text, description)

            # Hybrid score: 60 % semantic + 40 % keyword overlap.
            # SBERT alone is too generous because unrelated texts still share
            # general language patterns; TF-IDF anchors the score on concrete
            # shared terms (technologies, methodologies, role titles, etc.).
            ranking = round(0.6 * sbert_score + 0.4 * tfidf_score, 2)

        job_rankings[job['id']] = ranking
    return job_rankings

def extract_text_from_resume(file_path):
    ext = os.path.splitext(file_path)[-1].lower()

    # Read .txt file
    if ext == ".txt":
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()

    # Read .pdf file
    elif ext == ".pdf":
        doc = pymupdf.open(file_path)
        text = "\n".join(page.get_text() for page in doc)

    # Read .docx file
    elif ext == ".docx":
        doc = Document(file_path)
        text = "\n".join(paragraph.text for paragraph in doc.paragraphs)

    else:
        raise ValueError("Unsupported resume file type: must be .txt, .pdf, or .docx")

    # Remove blank lines
    cleaned_text = "\n".join(line for line in text.split("\n") if line.strip() != "")
    
    cleaned_text = cleaned_text = remove_personal_info(cleaned_text)
    return cleaned_text

def remove_personal_info(text):
    # Replace emails with 'Email: [EMAIL]'
    text = re.sub(
        r'(?i)(Email\s*[:\-]?\s*)?[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}',
        'Email: [EMAIL]', text)

    # Replace phone numbers with 'Phone: [PHONE]'
    text = re.sub(
        r'(?i)(Phone\s*[:\-]?\s*)?(\+?\d[\d\s().-]{7,}\d)',
        'Phone: [PHONE]', text)

    # Replace any URL with 'URL: [URL]'
    text = re.sub(
        r'(?i)(https?://[^\s]+)',
        'URL: [URL]', text)

    # Optional: Remove/replace the name if it's the first line
    lines = text.split('\n')
    if len(lines) > 0 and len(lines[0].split()) <= 5:
        lines[0] = 'Name: [NAME]'

    return "\n".join(lines)

def calculate_similarity_sbert(resume_embedding, job_description):
    """
    Calculate semantic similarity using SBERT embeddings
    
    Args:
        resume_embedding: Pre-computed embedding for resume (numpy array or can be text)
        job_description: Job description text
    
    Returns:
        Similarity score as percentage (0-100)
    """
    # If resume_embedding is raw text, encode it with chunking to avoid truncation
    if isinstance(resume_embedding, str):
        resume_embedding = encode_with_chunking(resume_embedding, sbert_model)

    # Encode job description with chunking for the same reason
    job_embedding = encode_with_chunking(job_description, sbert_model)
    
    # Calculate cosine similarity
    similarity = cosine_similarity(
        resume_embedding.reshape(1, -1), 
        job_embedding.reshape(1, -1)
    )
    # Return as percentage
    return round(similarity[0][0] * 100, 2)

def calculate_similarity(resume_text, job_description):
    # Create a TfidfVectorizer instance
    vectorizer = TfidfVectorizer(stop_words='english')
    
    # Fit and transform the resume and job description
    tfidf_matrix = vectorizer.fit_transform([resume_text, job_description])

    # Debug: Print the shape of the tfidf_matrix
    # print("TF-IDF Matrix Shape:", tfidf_matrix.shape)

    # Calculate the cosine similarity between the resume and job description
    similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])

    # Print similarity matrix for debugging
    # print("Cosine Similarity Matrix:", similarity)

    # Return similarity as a percentage
    return round(similarity[0][0] * 100, 2)



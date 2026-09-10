import nltk

def ensure_nltk_data():
    required_packages = {
        'punkt': 'tokenizers/punkt',
        'stopwords': 'corpora/stopwords',
        'wordnet': 'corpora/wordnet',
    }

    for name, path in required_packages.items():
        try:
            nltk.data.find(path)
        except LookupError:
            nltk.download(name)

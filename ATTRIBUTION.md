# Attribution

This project is built on the open-source libraries below. Versions are those pinned in `pyproject.toml` / `uv.lock` when this file was last updated; license names come from each package's PyPI metadata. This lists the libraries the app uses directly plus the main ones they pull in. `uv.lock` is the complete list (including all other transitive dependencies). Refer to each project's repository for the full license text.

## Web application

* **Flask 3.1.3** — web framework. BSD-3-Clause. <https://github.com/pallets/flask/>
* **Werkzeug 3.1.9** — WSGI utility library. BSD-3-Clause. <https://github.com/pallets/werkzeug/>
* **Jinja2 3.1.6** — templating engine. BSD-3-Clause. <https://github.com/pallets/jinja/>
* **MarkupSafe 2.1.5** — HTML/XML string escaping. BSD-3-Clause. <https://github.com/pallets/markupsafe/>
* **ItsDangerous 2.2.0** — signed data and session cookies. BSD-3-Clause. <https://github.com/pallets/itsdangerous/>
* **Click 8.1.7** — command-line interfaces. BSD-3-Clause. <https://github.com/pallets/click/>
* **Blinker 1.9.0** — in-process signals. MIT. <https://github.com/pallets-eco/blinker/>
* **Gunicorn 26.2.0** — production WSGI server. MIT. <https://gunicorn.org>
* **colorama 0.4.6** — ANSI colour support on Windows. BSD-3-Clause. <https://github.com/tartley/colorama>

## Job scraping and HTTP

* **python-jobspy 1.4.0** — scrapes job postings from multiple boards. MIT. <https://github.com/speedyapply/JobSpy>
* **curl_cffi 0.16.3** — HTTP client used by python-jobspy. MIT. <https://pypi.org/project/curl-cffi/>
* **Beautiful Soup (beautifulsoup4) 4.12.3** — HTML/XML parsing. MIT. <https://www.crummy.com/software/BeautifulSoup/>
* **Soupsieve 2.9.0** — CSS selectors for Beautiful Soup. MIT. <https://github.com/facelessuser/soupsieve>
* **lxml 6.1.3** — XML/HTML processing. BSD-3-Clause. <https://lxml.de/>
* **markdownify 1.2.3** — HTML to Markdown conversion. MIT. <https://github.com/matthewwithanm/python-markdownify>
* **Requests 2.34.2** — HTTP library. Apache-2.0. <https://github.com/psf/requests>
* **urllib3 2.8.0** — HTTP client. MIT. <https://pypi.org/project/urllib3/>
* **certifi 2026.10.19** — CA certificate bundle. MPL-2.0. <https://github.com/certifi/python-certifi>
* **charset-normalizer 3.3.2** — character encoding detection. MIT. <https://github.com/Ousret/charset_normalizer>
* **idna 3.15** — Internationalized Domain Names. BSD-3-Clause. <https://github.com/kjd/idna>

## Data handling

* **pandas 2.2.2** — data analysis. BSD-3-Clause. <https://pandas.pydata.org>
* **NumPy 1.26.3** — numerical computing. BSD-3-Clause. <https://numpy.org>
* **SciPy 1.15.2** — scientific computing. BSD-3-Clause. <https://pypi.org/project/scipy/>
* **python-dateutil 2.9.0.post0** — datetime extensions. Dual-licensed Apache-2.0 / BSD. <https://github.com/dateutil/dateutil>
* **pytz 2024.1** — time zone definitions. MIT. <http://pythonhosted.org/pytz>
* **tzdata 2024.1** — IANA time zone database package. Apache-2.0. <https://github.com/python/tzdata>
* **six 1.16.0** — Python 2/3 compatibility helpers. MIT. <https://github.com/benjaminp/six>
* **joblib 1.4.2** — lightweight pipelining. BSD-3-Clause. <https://joblib.readthedocs.io>
* **threadpoolctl 3.6.0** — thread pool control for native libraries. BSD-3-Clause. <https://github.com/joblib/threadpoolctl>
* **tqdm 4.67.1** — progress bars. MPL-2.0 AND MIT. <https://pypi.org/project/tqdm/>
* **Pydantic 2.7.1** and **pydantic-core 2.18.2** — data validation. MIT. <https://github.com/pydantic/pydantic>
* **annotated-types 0.7.0** — reusable constraint types for type hints. MIT. <https://github.com/annotated-types/annotated-types>
* **typing-extensions 4.12.0** — backported typing features. PSF-2.0. <https://github.com/python/typing_extensions>

## Text analysis and resume matching

* **NLTK 3.10.4** — natural language toolkit. Apache-2.0. <https://www.nltk.org/>
* **regex 2026.9.29** — regular expression library. Apache-2.0 AND CNRI-Python. <https://github.com/mrabarnett/mrab-regex>
* **scikit-learn 1.9.1** — machine learning. BSD-3-Clause. <https://pypi.org/project/scikit-learn/>
* **sentence-transformers 6.2.0** — text embeddings. Apache-2.0. <https://www.SBERT.net>
* **PyTorch (torch) 2.14.1** — tensor/ML library used by sentence-transformers. BSD-style license (see project for details). <https://pytorch.org>
* **Transformers 5.17.0**, **huggingface-hub 1.16.1**, **tokenizers 0.23.3**, **safetensors 0.8.0** — Hugging Face model tooling. Apache-2.0. <https://github.com/huggingface/transformers>

## Resume file handling

* **PyMuPDF 2.0** — PDF text extraction. Dual-licensed: **GNU AGPL-3.0** or an Artifex commercial license. <https://github.com/pymupdf/pymupdf>
* **python-docx 1.2.0** — reading `.docx` files. MIT. <https://github.com/python-openxml/python-docx>
* **Bleach 6.4.0** — HTML sanitizing. Apache-2.0. <https://github.com/mozilla/bleach>
* **webencodings 0.5.1** — WHATWG encoding standard. BSD-3-Clause. <https://github.com/SimonSapin/python-webencodings>

## Data sources

The Cost of Living features use data from the following services, subject to each service's own terms of use:
[API Ninjas](https://api-ninjas.com/), [OpenEI](https://openei.org/services/), [EIA](https://www.eia.gov/opendata/), [HUD Fair Market Rents](https://www.huduser.gov/portal/dataset/fmr-api.html), and [BEA](https://apps.bea.gov/API/signup/).

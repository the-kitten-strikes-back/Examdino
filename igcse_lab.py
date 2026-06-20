from __future__ import annotations

import json
import os
import random
import re
import signal
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
import pdfplumber

try:
    from wordsegment import load as ws_load, segment as ws_segment
    _WORDSEGMENT_AVAILABLE = True
    ws_load()
except Exception:
    _WORDSEGMENT_AVAILABLE = False

try:
    from textblob import TextBlob
    _TEXTBLOB_AVAILABLE = True
except Exception:
    _TEXTBLOB_AVAILABLE = False

try:
    import google.generativeai as genai
    _GENAI_AVAILABLE = True
except Exception:
    _GENAI_AVAILABLE = False


IGCSE_SUBJECT_CODES = {
    "Accounting": "0452",
    "Mathematics": "0606",
    "Afrikaans": "0548",
    "Agriculture": "0600",
    "Art and Design": "0400",
    "Bahasa Indonesia": "0538",
    "Biology": "0610",
    "Business Studies": "0450",
    "Chemistry": "0620",
    "Chinese": "0509",
    "Computer Science": "0478",
    "Economics": "0455",
    "English": "0500",
    "Environmental Management": "0680",
    "French": "0520",
    "Geography": "0460",
    "German": "0525",
    "History": "0470",
    "Latin": "0480",
    "Physics": "0625",
    "Sociology": "0495",
    "Spanish": "0530",
    "Travel and Tourism": "0471",
    "World Literature": "0408",
}

IGCSE_STRUCTURE = {
    "Accounting": [("Section A", "multiple", 35), ("Section B", "text", 5)],
    "Mathematics": [("Paper 1", "text", 20), ("Paper 2", "text", 20)],
    "Afrikaans": [("Reading and Writing", "text", 30)],
    "Agriculture": [("Section 1", "text", 35), ("Section 2", "text", 5)],
    "Art and Design": [("Practical", "text", 100)],
    "Bahasa Indonesia": [("Reading and Writing", "text", 4), ("Listening", "text", 2)],
    "Biology": [("Paper 2 - MCQ", "multiple", 40), ("Paper 4 - Text", "text", 7), ("Paper 6 - Text", "text", 3)],
    "Business Studies": [("Paper 1", "text", 4), ("Paper 2", "text", 4)],
    "Chemistry": [("Paper 2 - MCQ", "multiple", 40), ("Paper 4 - Text", "text", 7), ("Paper 6 - Text", "text", 3)],
    "Chinese": [("Reading and Writing", "text", 4), ("Listening", "multiple", 35)],
    "Computer Science": [("Computer Systems", "text", 12), ("Algorithms, Programming and Logic", "text", 9)],
    "Economics": [("Paper 1", "multiple", 30), ("Paper 2", "text", 13)],
    "English": [("Paper 1 - Reading", "text", 20), ("Paper 2 - Writing", "text", 20)],
    "Environmental Management": [("Paper 1", "text", 40)],
    "French": [("Reading and Writing", "text", 4), ("Listening", "multiple", 35)],
    "Geography": [("Paper 1", "text", 40)],
    "German": [("Reading and Writing", "text", 4), ("Listening", "multiple", 35)],
    "History": [("Paper 1", "text", 40)],
    "Latin": [("Paper 1", "text", 40)],
    "Physics": [("Paper 2 - MCQ", "multiple", 40), ("Paper 4 - Text", "text", 7), ("Paper 6 - Text", "text", 3)],
    "Sociology": [("Paper 1", "text", 40)],
    "Spanish": [("Reading and Writing", "text", 4), ("Listening", "multiple", 35)],
    "Travel and Tourism": [("Paper 1", "text", 40)],
    "World Literature": [("Paper 1", "text", 40)],
}

BASE_URL = "https://pastpapers.papacambridge.com/"


def get_igcse_subject_name(subject_code: str) -> str:
    for name, code in IGCSE_SUBJECT_CODES.items():
        if code == subject_code:
            return name
    return "Code not found"


def fetch_past_papers(subject_code: str, year_range: str | None = None) -> list[str]:
    years = year_range.split("-") if year_range else None
    subject_name = get_igcse_subject_name(subject_code)
    if subject_name == "Code not found":
        return []
    base_url = "https://pastpapers.papacambridge.com/"
    slug = subject_name.lower().replace(" ", "-")
    url = urljoin(base_url, f"papers/caie/igcse-{slug}-{subject_code}")
    response = requests.get(url, timeout=15)
    if response.status_code != 200:
        return []
    ugly_soup = BeautifulSoup(response.content, "html.parser")
    ugly_soup.prettify()
    if years:
        papers = ugly_soup.find_all("a", class_="kt-widget4__title kt-nav__link-text cursor colorgrey stylefont fonthover")
        papers = [p for p in papers if p.text.strip() and any(year in p.text for year in years)]
    else:
        papers = ugly_soup.find_all("a", class_="kt-widget4__title kt-nav__link-text cursor colorgrey stylefont fonthover")
    paper_urls = [urljoin(base_url, paper.get("href", "")) for paper in papers]
    if not paper_urls:
        return []
    download_links = []
    with ProcessPoolExecutor() as executor:
        futures = [executor.submit(_fetch_paper_downloads, url) for url in paper_urls]
        for future in as_completed(futures):
            try:
                download_links.extend(future.result())
            except Exception:
                pass
    if not download_links:
        return []
    if subject_code in {"0500", "0457"}:
        filtered_links = [link for link in download_links if "qp" in link.lower() or "in" in link.lower()]
    else:
        filtered_links = [link for link in download_links if "qp" in link.lower()]
    return filtered_links


def _fetch_paper_downloads(url: str) -> list[str]:
    uglier_soup = BeautifulSoup(requests.get(url, timeout=15).content, "html.parser")
    uglier_soup.prettify()
    return [
        urljoin(BASE_URL, a.get("href", ""))
        for a in uglier_soup.find_all("a", class_="badge badge-info")
    ]


def fetch_session_download_links(page_url: str) -> list[str]:
    return _fetch_paper_downloads(page_url)


def _extract_year_from_text(text: str) -> str | None:
    match = re.search(r"(19|20)\d{2}", text)
    return match.group(0) if match else None


def build_session_catalog(subject_code: str, year_range: str | None = None, limit: int = 40) -> list[dict[str, object]]:
    years = year_range.split("-") if year_range else None
    subject_name = get_igcse_subject_name(subject_code)
    if subject_name == "Code not found":
        return []

    slug = subject_name.lower().replace(" ", "-")
    url = urljoin(BASE_URL, f"papers/caie/igcse-{slug}-{subject_code}")
    response = requests.get(url, timeout=20)
    if response.status_code != 200:
        return []

    soup = BeautifulSoup(response.content, "html.parser")
    paper_links = soup.find_all("a", class_="kt-widget4__title kt-nav__link-text cursor colorgrey stylefont fonthover")
    sessions: list[dict[str, object]] = []
    for paper in paper_links:
        title = paper.get_text(" ", strip=True)
        if not title:
            continue
        if years and not any(year in title for year in years):
            continue
        page_url = urljoin(BASE_URL, paper.get("href", ""))
        session_year = _extract_year_from_text(title)
        sessions.append(
            {
                "title": title,
                "year": session_year or "Unknown",
                "page_url": page_url,
            }
        )
        if len(sessions) >= limit:
            break
    return sessions


def _download_to_file(url: str, filename: str) -> None:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    with open(filename, "wb") as f:
        f.write(response.content)


def _parse_single_pdf(link: str, timeout_seconds: int = 120) -> str:
    def _timeout_handler(signum, frame):
        raise TimeoutError("PDF parse timed out")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.close()
    filename = tmp.name
    try:
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(timeout_seconds)
        _download_to_file(link, filename)
        text_parts = []
        with pdfplumber.open(filename) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if text:
                    text_parts.append(f"--- {os.path.basename(filename)} | Page {page_num} ---\n{text}\n\n")
                try:
                    tables = page.extract_tables()
                except Exception:
                    tables = []
                for t_idx, table in enumerate(tables, start=1):
                    if not table:
                        continue
                    lines = []
                    for row in table:
                        row_vals = [cell if cell is not None else "" for cell in row]
                        lines.append(" | ".join(row_vals))
                    if lines:
                        table_text = "\n".join(lines)
                        text_parts.append(
                            f"--- {os.path.basename(filename)} | Page {page_num} | Table {t_idx} ---\n{table_text}\n\n"
                        )
        return "".join(text_parts)
    except Exception:
        return ""
    finally:
        signal.alarm(0)
        try:
            os.remove(filename)
        except OSError:
            pass


def parse_pdfs(download_links: list[str], max_workers: int | None = None, timeout_seconds: int = 120, max_pdfs: int = 10) -> str:
    if not download_links:
        return ""
    download_links = download_links[:max_pdfs]
    all_text_parts = []
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_parse_single_pdf, link, timeout_seconds) for link in download_links]
        for future in as_completed(futures):
            try:
                all_text_parts.append(future.result())
            except Exception:
                all_text_parts.append("")
    return "".join(all_text_parts)


def parse_pdf_text_from_links(download_links: list[str], max_pdfs: int = 10) -> str:
    return parse_pdfs(download_links, max_pdfs=max_pdfs)


def _clean_text_for_questions(text: str) -> str:
    cleaned = re.sub(r"(?m)^--- .*? ---\s*$", "", text)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    boilerplate_line_patterns = [
        r"^Section\s+[ABC]$",
        r"^Answer\s+Question\s+\d+$",
        r"^Answer\s+any\s+.*questions.*$",
        r"^Answer\s+all\s+parts\s+of\s+Question.*$",
        r"^Read\s+the\s+source\s+material.*$",
        r"^Source\s+material:.*$",
        r"^INSTRUCTIONS$",
        r"^INFORMATION$",
        r"^READ\s+THESE\s+INSTRUCTIONS\s+FIRST$",
        r"^Additional\s+Materials:.*$",
        r"^You\s+must\s+answer.*$",
        r"^You\s+will\s+need:.*$",
        r"^You\s+may\s+use.*$",
        r"^The\s+total\s+mark.*$",
        r"^The\s+number\s+of\s+marks.*$",
        r"^Write\s+your.*$",
        r"^Do\s+not\s+use.*$",
        r"^Choose\s+the\s+one.*$",
        r"^Each\s+correct\s+answer.*$",
        r"^Any\s+rough\s+working.*$",
        r"^Soft\s+clean\s+eraser$",
        r"^Soft\s+pencil.*$",
        r"^\[Turn\s+over.*$",
    ]
    boilerplate_line_re = re.compile("|".join(boilerplate_line_patterns), re.IGNORECASE)
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        if re.fullmatch(r"\d+", stripped):
            continue
        if stripped.upper() == "BLANK PAGE":
            continue
        if stripped.startswith("\u00a9 UCLES"):
            continue
        if boilerplate_line_re.match(stripped):
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


clean_text_for_questions = _clean_text_for_questions


def extract_questions(text: str) -> list[str]:
    cleaned = _clean_text_for_questions(text)
    pattern = re.compile(r"(?m)^(?:Question\s*)?\d{1,2}\s+(?=(?:\(|[A-Z]))")
    matches = list(pattern.finditer(cleaned))
    if not matches:
        return []
    questions = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(cleaned)
        chunk = cleaned[start:end].strip()
        for stop in [
            "Permission to reproduce",
            "Copyright Acknowledgements",
            "This document consists",
            "UNIVERSITY OF CAMBRIDGE INTERNATIONAL EXAMINATIONS",
            "International General Certificate of Secondary Education",
        ]:
            idx = chunk.find(stop)
            if idx != -1:
                chunk = chunk[:idx].strip()
                break
        if chunk:
            questions.append(chunk)
    return questions


def is_multiple_choice(question_text: str) -> bool:
    mcq_pattern = re.compile(r"(?m)^\s*A\s+.+\n^\s*B\s+.+\n^\s*C\s+.+\n^\s*D\s+.+", re.DOTALL)
    if mcq_pattern.search(question_text):
        return True
    option_count = len(re.findall(r"(?m)^\s*[ABCD]\s+", question_text))
    return option_count >= 4


def _segment_joined_words(text: str, enabled: bool = True) -> str:
    if not enabled or not _WORDSEGMENT_AVAILABLE:
        return text

    def segment_run(match):
        words = ws_segment(match.group(0))
        return " ".join(words)

    fixed_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            fixed_lines.append(line)
            continue
        if " " not in line and re.search(r"[A-Za-z]{12,}", line):
            line = re.sub(r"[A-Za-z]{8,}", segment_run, line)
        else:
            line = re.sub(r"[A-Za-z]{12,}", segment_run, line)
        fixed_lines.append(line)
    return "\n".join(fixed_lines)


maybe_segment_joined_words = _segment_joined_words


def generate_paper_json(mcq_questions: list[str], text_questions: list[str], structure_list: list[tuple[str, str, int]]) -> list[dict[str, object]]:
    paper = []
    for section_name, question_type, num_questions in structure_list:
        if question_type == "multiple":
            selected_questions = random.sample(mcq_questions, min(num_questions, len(mcq_questions)))
        elif question_type == "text":
            selected_questions = random.sample(text_questions, min(num_questions, len(text_questions)))
        else:
            raise ValueError(f"Unknown question type: {question_type}")
        paper.append({"section": section_name, "questions": selected_questions})
    return paper


def _clean_sample_text(text: str) -> str:
    cleaned_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue
        if stripped.startswith("\u00a9UCLES"):
            continue
        line = line.replace("\\n", "\n")
        line = re.sub(r"\\+1\b", "", line)
        line = re.sub(r"\b\\1\b", "", line)
        line = re.sub(r"\\\d+\s+\\\d+", "", line)
        if re.fullmatch(r"\(cid:\d+\)+", stripped):
            continue
        line = re.sub(r"\$(\d)", r"$ \1", line)
        line = re.sub(r"([A-Za-z])\$(\d)", r"\1 $\2", line)
        line = re.sub(r"(\d)([A-Za-z])", r"\1 \2", line)
        line = re.sub(r"([A-Za-z])([0-9])", r"\1 \2", line)
        if "|" in line:
            if re.fullmatch(r"(\s*\|\s*){6,}\s*", line):
                continue
            line = re.sub(r"\s*\|\s*", " | ", line)
            line = re.sub(r"\s{2,}", " ", line)
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def gemini_fix_text(text: str, api_key: str = "", model: str = "gemini-2.5-flash") -> str:
    if not _GENAI_AVAILABLE:
        return text
    if not api_key:
        return text
    prompt = (
        "You are a helpful assistant for cleaning up OCR-extracted text from IGCSE papers. "
        "Fix common OCR errors, tidy tables, remove irrelevant boilerplate, remove question numbers, and(if needed/if images/data required are missing) generate images/data that fit the context. Preserve question integrity. Do not write anything except the cleaned text.\n\n"
        "If there is a missing image/diagram, explain what the image/diagram should contain in the text. Example: for a question on Hooke's law you can say: '(The graph(x:spring length, y:force) shows a line that slants upwards.)'\n\n"
        f"Original text:\n{text}\n\nCleaned text:"
    )
    try:
        genai.configure(api_key=api_key)
        model_obj = genai.GenerativeModel(model_name=model)
        response = model_obj.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Gemini API error: {e}"


def generate_sample_paper(paper: list[dict[str, object]], gemini_api_key: str = "") -> str:
    sample_lines = []
    seen = set()
    for section in paper:
        sample_lines.append(f"--- {section['section']} ---\n")
        for question in section["questions"]:
            normalized = re.sub(r"\s+", " ", str(question)).strip().lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            sample_lines.append(str(question) + "\n\n")
    raw = "\n".join(sample_lines)
    text = _clean_sample_text(raw)
    text = gemini_fix_text(text, api_key=gemini_api_key, model="gemini-2.5-flash")
    return text


def save_outputs(all_extracted_text: str, questions: list[str], output_dir: str = ".") -> tuple[list[str], list[str], list[str]]:
    first_1000_questions = questions[:1000]
    mcq_questions = [q for q in first_1000_questions if is_multiple_choice(q)]
    text_questions = [q for q in first_1000_questions if not is_multiple_choice(q)]

    with open(os.path.join(output_dir, "extracted_igcse_papers.txt"), "w", encoding="utf-8") as f:
        f.write(all_extracted_text)
    with open(os.path.join(output_dir, "extracted_igcse_questions_1000.json"), "w", encoding="utf-8") as f:
        json.dump(first_1000_questions, f, ensure_ascii=True, indent=2)
    with open(os.path.join(output_dir, "multiple_choice.json"), "w", encoding="utf-8") as f:
        json.dump(mcq_questions, f, ensure_ascii=True, indent=2)
    with open(os.path.join(output_dir, "text_questions.json"), "w", encoding="utf-8") as f:
        json.dump(text_questions, f, ensure_ascii=True, indent=2)

    return first_1000_questions, mcq_questions, text_questions


def spell_correct_text(text: str, progress_cb=None) -> str:
    if not _TEXTBLOB_AVAILABLE:
        return text
    lines = text.splitlines()
    total = max(len(lines), 1)
    corrected = []
    for i, line in enumerate(lines, start=1):
        if re.search(r"[A-Za-z]", line):
            try:
                line = str(TextBlob(line).correct())
            except Exception:
                pass
        corrected.append(line)
        if progress_cb and i % 50 == 0:
            progress_cb(i / total)
    if progress_cb:
        progress_cb(1.0)
    return "\n".join(corrected)


def gemini_feedback(question: str, answer: str, api_key: str = "", model: str = "gemini-1.5-flash") -> str:
    if not _GENAI_AVAILABLE:
        return "google-generativeai is not installed."
    if not api_key:
        return "GEMINI_API_KEY is not set."
    prompt = (
        "You are an IGCSE examiner. Provide concise feedback (strengths + improvements) "
        "and, if appropriate, a short suggested answer outline.\n\n"
        f"Question:\n{question}\n\nStudent answer:\n{answer}"
    )
    try:
        genai.configure(api_key=api_key)
        model_obj = genai.GenerativeModel(model_name=model)
        response = model_obj.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Gemini API error: {e}"


def gemini_list_models(api_key: str) -> list[str]:
    if not _GENAI_AVAILABLE:
        return []
    if not api_key:
        return []
    try:
        genai.configure(api_key=api_key)
        models = genai.list_models()
        return [m.name for m in models if "generateContent" in getattr(m, "supported_generation_methods", [])]
    except Exception:
        return []


def _format_question_for_display(question: str) -> str:
    if is_multiple_choice(question):
        text = re.sub(r"\s([ABCD])\s", r"\n\1 ", question)
        text = re.sub(r"(\?)\s+(?=[ABCD]\s)", r"\1\n", text)
        return text.strip()
    return question.strip()


def _parse_mcq(question: str) -> tuple[str, list[tuple[str, str]]]:
    text = _format_question_for_display(question)
    lines = text.splitlines()
    stem_lines = []
    options = []
    for line in lines:
        m = re.match(r"^([ABCD])\s+(.*)$", line.strip())
        if m:
            options.append((m.group(1), m.group(2).strip()))
        else:
            stem_lines.append(line)
    stem = "\n".join(stem_lines).strip()
    return stem, options[:4]


def text_to_pdf(text: str, output_path: str, page_width: int = 595, page_height: int = 842, margin: int = 50, font_size: int = 11, leading: int = 14) -> str:
    def _pdf_escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    lines = text.splitlines() or [""]
    pages: list[str] = []
    y = page_height - margin
    content_lines: list[str] = []

    def flush_page():
        if content_lines:
            pages.append("\n".join(content_lines))

    for line in lines:
        if y < margin + leading:
            flush_page()
            content_lines.clear()
            y = page_height - margin
        escaped = _pdf_escape(line)
        content_lines.append(f"1 0 0 1 {margin} {y} Tm ({escaped}) Tj")
        y -= leading

    flush_page()

    objects: list[str] = []
    offsets: list[int] = []

    def add_object(obj_str: str):
        offsets.append(sum(len(o) for o in objects))
        objects.append(obj_str)

    add_object("1 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

    page_ids: list[int] = []
    for page_content in pages:
        content_stream = f"BT\n/F1 {font_size} Tf\n{page_content}\nET"
        content_id = 1 + len(page_ids) * 2 + 1
        add_object(f"{content_id} 0 obj\n<< /Length {len(content_stream)} >>\nstream\n{content_stream}\nendstream\nendobj\n")

        page_id = content_id + 1
        page_ids.append(page_id)
        add_object(
            f"{page_id} 0 obj\n"
            f"<< /Type /Page /Parent {page_id + 1} 0 R "
            f"/Resources << /Font << /F1 1 0 R >> >> "
            f"/MediaBox [0 0 {page_width} {page_height}] "
            f"/Contents {content_id} 0 R >>\n"
            f"endobj\n"
        )

    pages_id = page_ids[-1] + 1 if page_ids else 2
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    add_object(f"{pages_id} 0 obj\n<< /Type /Pages /Count {len(page_ids)} /Kids [ {kids} ] >>\nendobj\n")

    catalog_id = pages_id + 1
    add_object(f"{catalog_id} 0 obj\n<< /Type /Catalog /Pages {pages_id} 0 R >>\nendobj\n")

    header = "%PDF-1.4\n"
    body = "".join(objects)
    xref_offset = len(header) + len(body)
    xref_entries = ["0000000000 65535 f \n"]
    for off in offsets:
        xref_entries.append(f"{off + len(header):010d} 00000 n \n")
    xref = "xref\n0 {0}\n{1}".format(len(xref_entries), "".join(xref_entries))
    trailer = f"trailer\n<< /Size {len(xref_entries)} /Root {catalog_id} 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"

    with open(output_path, "wb") as f:
        f.write(header.encode("utf-8"))
        f.write(body.encode("utf-8"))
        f.write(xref.encode("utf-8"))
        f.write(trailer.encode("utf-8"))
    return output_path


def build_paper_lab_bundle(
    subject_name: str,
    raw_text: str,
    max_questions: int = 1000,
    use_wordsegment: bool = True,
    use_textblob: bool = False,
    gemini_api_key: str = "",
) -> dict[str, object]:
    raw_text = raw_text.replace(".", "")
    raw_text = _segment_joined_words(raw_text, enabled=use_wordsegment)
    if use_textblob:
        raw_text = spell_correct_text(raw_text)
    questions = extract_questions(raw_text)
    first_questions = questions[:max_questions]
    mcq_questions = [q for q in first_questions if is_multiple_choice(q)]
    text_questions = [q for q in first_questions if not is_multiple_choice(q)]
    structure = IGCSE_STRUCTURE.get(subject_name, [])
    paper = generate_paper_json(mcq_questions, text_questions, structure) if structure else []
    sample_text = generate_sample_paper(paper, gemini_api_key=gemini_api_key) if paper else ""
    return {
        "raw_text": raw_text,
        "questions": first_questions,
        "mcq_questions": mcq_questions,
        "text_questions": text_questions,
        "paper": paper,
        "sample_text": sample_text,
    }

from __future__ import annotations

import json
import os
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

try:
    from wordsegment import load as ws_load, segment as ws_segment
    _WORDSEGMENT_AVAILABLE = True
    ws_load()
except Exception:  # pragma: no cover
    _WORDSEGMENT_AVAILABLE = False


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
    "Afrikaans": [("Reading and Writing", "text", 30), ("Listening", "text", 20)],
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

    slug = subject_name.lower().replace(" ", "-")
    url = urljoin(BASE_URL, f"papers/caie/igcse-{slug}-{subject_code}")
    response = requests.get(url, timeout=20)
    if response.status_code != 200:
        return []

    soup = BeautifulSoup(response.content, "html.parser")
    paper_links = soup.find_all("a", class_="kt-widget4__title kt-nav__link-text cursor colorgrey stylefont fonthover")
    if years:
        paper_links = [paper for paper in paper_links if paper.text.strip() and any(year in paper.text for year in years)]

    paper_urls = [urljoin(BASE_URL, paper.get("href", "")) for paper in paper_links]
    if not paper_urls:
        return []

    download_links: list[str] = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(paper_urls)))) as executor:
        futures = [executor.submit(_fetch_paper_downloads, paper_url) for paper_url in paper_urls]
        for future in as_completed(futures):
            try:
                download_links.extend(future.result())
            except Exception:
                pass

    if subject_code in {"0500", "0457"}:
        return [link for link in download_links if "qp" in link.lower() or "in" in link.lower()]
    return [link for link in download_links if "qp" in link.lower()]


def _fetch_paper_downloads(url: str) -> list[str]:
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    return [urljoin(BASE_URL, a.get("href", "")) for a in soup.find_all("a", class_="badge badge-info")]


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
    response = requests.get(url, timeout=45)
    response.raise_for_status()
    with open(filename, "wb") as f:
        f.write(response.content)


def parse_pdf_text_from_links(download_links: list[str], max_pdfs: int = 10) -> str:
    if not download_links or PdfReader is None:
        return ""

    text_parts: list[str] = []
    for index, link in enumerate(download_links[:max_pdfs], start=1):
        tmp_path = Path(os.path.join("/tmp", f"examdino_igcse_{index}.pdf"))
        try:
            _download_to_file(link, str(tmp_path))
            reader = PdfReader(str(tmp_path))
            for page_index, page in enumerate(reader.pages, start=1):
                extracted = page.extract_text() or ""
                if extracted.strip():
                    text_parts.append(f"--- source_{index} | page {page_index} ---\n{extracted}\n\n")
        except Exception:
            continue
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
    return "".join(text_parts)


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


def clean_text_for_questions(text: str) -> str:
    cleaned = re.sub(r"(?m)^--- .*? ---\s*$", "", text)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
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

    lines: list[str] = []
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
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def extract_questions(text: str) -> list[str]:
    cleaned = clean_text_for_questions(text)
    pattern = re.compile(r"(?m)^(?:Question\s*)?\d{1,2}\s+(?=(?:\(|[A-Z]))")
    matches = list(pattern.finditer(cleaned))
    if not matches:
        return []
    questions: list[str] = []
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
    return len(re.findall(r"(?m)^\s*[ABCD]\s+", question_text)) >= 4


def maybe_segment_joined_words(text: str) -> str:
    if not _WORDSEGMENT_AVAILABLE:
        return text

    def segment_run(match):
        return " ".join(ws_segment(match.group(0)))

    fixed_lines: list[str] = []
    for line in text.splitlines():
        if " " not in line and re.search(r"[A-Za-z]{12,}", line):
            line = re.sub(r"[A-Za-z]{8,}", segment_run, line)
        else:
            line = re.sub(r"[A-Za-z]{12,}", segment_run, line)
        fixed_lines.append(line)
    return "\n".join(fixed_lines)


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


def generate_sample_paper(paper: list[dict[str, object]]) -> str:
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
    return "\n".join(sample_lines).strip()


def build_paper_lab_bundle(subject_name: str, raw_text: str, max_questions: int = 1000) -> dict[str, object]:
    raw_text = raw_text.replace(".", "")
    raw_text = maybe_segment_joined_words(raw_text)
    questions = extract_questions(raw_text)
    first_questions = questions[:max_questions]
    mcq_questions = [q for q in first_questions if is_multiple_choice(q)]
    text_questions = [q for q in first_questions if not is_multiple_choice(q)]
    structure = IGCSE_STRUCTURE.get(subject_name, [])
    paper = generate_paper_json(mcq_questions, text_questions, structure) if structure else []
    sample_text = generate_sample_paper(paper) if paper else ""
    return {
        "raw_text": raw_text,
        "questions": first_questions,
        "mcq_questions": mcq_questions,
        "text_questions": text_questions,
        "paper": paper,
        "sample_text": sample_text,
    }

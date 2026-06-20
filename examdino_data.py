from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Subject:
    slug: str
    code: str
    name: str
    board: str
    level: str
    source_url: str
    resource_url: str
    overview: str
    focus: tuple[str, ...]
    common_mistakes: tuple[str, ...]
    chapters: tuple[str, ...]
    checkpoint: str
    paper_lanes: tuple[str, ...]


SUBJECTS: dict[str, Subject] = {
    "maths": Subject(
        slug="maths",
        code="0580",
        name="Cambridge IGCSE Mathematics",
        board="Cambridge International",
        level="Core and Extended",
        source_url="https://www.cambridgeinternational.org/programmes-and-qualifications/cambridge-igcse-mathematics-0580/",
        resource_url="https://www.cambridgeinternational.org/resource-centre/",
        overview="Numbers, algebra, geometry, statistics, and problem solving in one of the most widely taught IGCSE courses.",
        focus=("number sense", "algebra", "graphs", "ratio", "statistics", "proof"),
        common_mistakes=("sign errors", "unit slips", "rounding too early", "misreading scale factors"),
        chapters=("Number", "Algebra", "Geometry", "Trigonometry", "Statistics", "Probability"),
        checkpoint="Quadratic graphs and simultaneous equations",
        paper_lanes=("Paper 1 non-calculator", "Paper 2 calculator", "Extended problem set"),
    ),
    "biology": Subject(
        slug="biology",
        code="0610",
        name="Cambridge IGCSE Biology",
        board="Cambridge International",
        level="Core and Extended",
        source_url="https://www.cambridgeinternational.org/programmes-and-qualifications/cambridge-igcse-biology-0610/",
        resource_url="https://www.cambridgeinternational.org/resource-centre/",
        overview="A content-rich course covering cells, transport, enzymes, genetics, ecology, and human physiology.",
        focus=("cells", "enzymes", "transport", "homeostasis", "inheritance", "ecology"),
        common_mistakes=("missing keywords", "vague explanations", "mixing diffusion and osmosis", "weaker graph interpretation"),
        chapters=("Cells", "Biological molecules", "Enzymes", "Transport", "Genetics", "Ecology"),
        checkpoint="Cell transport and enzyme revision",
        paper_lanes=("Paper 1 factual recall", "Paper 2 data response", "Practical skills"),
    ),
    "chemistry": Subject(
        slug="chemistry",
        code="0620",
        name="Cambridge IGCSE Chemistry",
        board="Cambridge International",
        level="Core and Extended",
        source_url="https://www.cambridgeinternational.org/programmes-and-qualifications/cambridge-igcse-chemistry-0620/",
        resource_url="https://www.cambridgeinternational.org/resource-centre/",
        overview="Build a particle-level understanding of matter, reactions, acids, energetics, and organic chemistry.",
        focus=("bonding", "equations", "moles", "acids", "salts", "organic chemistry"),
        common_mistakes=("equation balancing", "state symbols", "test observations", "molar calculations"),
        chapters=("States of matter", "Atomic structure", "Bonding", "Moles", "Energetics", "Organic chemistry"),
        checkpoint="Acids, salts, and titration vocabulary",
        paper_lanes=("Paper 1 theory", "Paper 2 calculations", "Practical interpretation"),
    ),
    "physics": Subject(
        slug="physics",
        code="0625",
        name="Cambridge IGCSE Physics",
        board="Cambridge International",
        level="Core and Extended",
        source_url="https://www.cambridgeinternational.org/programmes-and-qualifications/cambridge-igcse-physics-0625/",
        resource_url="https://www.cambridgeinternational.org/resource-centre/",
        overview="A highly applied science course built around motion, forces, energy, waves, electricity, and practical skills.",
        focus=("motion", "forces", "energy", "electricity", "waves", "practical reasoning"),
        common_mistakes=("formula confusion", "unit errors", "graph interpretation", "writing weak conclusions"),
        chapters=("Motion", "Forces", "Energy", "Waves", "Electricity", "Space physics"),
        checkpoint="Forces and moments with vectors",
        paper_lanes=("Paper 1 theory", "Paper 2 calculations", "Practical analysis"),
    ),
    "english": Subject(
        slug="english",
        code="0500/0510",
        name="Cambridge IGCSE English",
        board="Cambridge International",
        level="First Language and Second Language",
        source_url="https://www.cambridgeinternational.org/",
        resource_url="https://www.cambridgeinternational.org/resource-centre/",
        overview="A language and composition track focused on reading precision, writing control, vocabulary, and structure.",
        focus=("analysis", "audience", "tone", "structure", "vocabulary", "editing"),
        common_mistakes=("thin analysis", "weak evidence", "overlong introductions", "missed command words"),
        chapters=("Reading", "Directed writing", "Descriptive writing", "Narrative writing", "Summary skills", "Editing"),
        checkpoint="Directed writing under timed conditions",
        paper_lanes=("Reading paper", "Writing paper", "Language accuracy review"),
    ),
    "ict": Subject(
        slug="ict",
        code="0417",
        name="Cambridge IGCSE Information and Communication Technology",
        board="Cambridge International",
        level="Core",
        source_url="https://www.cambridgeinternational.org/",
        resource_url="https://www.cambridgeinternational.org/resource-centre/",
        overview="A practical theory-meets-application course covering hardware, software, data, networks, and digital tools.",
        focus=("hardware", "software", "data", "spreadsheets", "networks", "cybersecurity"),
        common_mistakes=("definition drift", "process order", "incomplete examples", "confusing input/output"),
        chapters=("Systems", "Data", "Networks", "Cybersecurity", "Spreadsheets", "Presentation tools"),
        checkpoint="Spreadsheet validation and formula practice",
        paper_lanes=("Theory paper", "Practical response", "Scenario drills"),
    ),
}

FEATURES = [
    {
        "title": "Course maps",
        "slug": "courses",
        "eyebrow": "Structured learning",
        "summary": "Study by subject, then by chapter, then by question type.",
    },
    {
        "title": "Smart notes",
        "slug": "notes",
        "eyebrow": "Upload or paste",
        "summary": "Turn lessons into summaries, flashcards, and recall prompts.",
    },
    {
        "title": "Past papers",
        "slug": "papers",
        "eyebrow": "Exam practice",
        "summary": "Find paper sets, mark-scheme paths, and timed practice lanes.",
    },
    {
        "title": "Quizzes",
        "slug": "quizzes",
        "eyebrow": "Recall engine",
        "summary": "Generate targeted quizzes from topics, uploads, or chosen courses.",
    },
    {
        "title": "Slide studio",
        "slug": "upload",
        "eyebrow": "File to notes",
        "summary": "Upload PPTX, PDF, or text files and extract study notes automatically.",
    },
    {
        "title": "Revision planner",
        "slug": "planner",
        "eyebrow": "Daily workflow",
        "summary": "Build a week-by-week plan with weak-topic radar and exam-day pacing.",
    },
    {
        "title": "IGCSE Paper Lab",
        "slug": "paper_lab",
        "eyebrow": "Web + OCR",
        "summary": "Scrape past papers, extract questions, classify MCQ/text, and generate sample papers.",
    },
]

RESOURCE_COLLECTIONS = [
    {
        "title": "Syllabus center",
        "description": "Official Cambridge subject pages, quick overviews, and resource-centre entry points.",
        "items": ["Cambridge IGCSE subject pages", "resource-centre link", "course checkpoints"],
    },
    {
        "title": "Recall vault",
        "description": "Generated notes, flashcards, summary bullets, and keyword maps.",
        "items": ["term extraction", "flashcard prompts", "summary bullets"],
    },
    {
        "title": "Paper arena",
        "description": "Practice lanes, filterable paper bundles, and timing drills.",
        "items": ["subject filters", "paper packs", "timed practice"],
    },
    {
        "title": "Planner lab",
        "description": "Scheduling, spaced repetition, and end-of-week progress checks.",
        "items": ["daily tasks", "weak-topic radar", "timed reviews"],
    },
]

PAPER_LIBRARY = [
    {
        "subject": "maths",
        "title": "Mathematics paper sprint",
        "format": "Calculator + non-calculator rotation",
        "difficulty": "Balanced",
        "description": "A mixed practice lane that alternates algebra, graph work, and functional reasoning.",
    },
    {
        "subject": "biology",
        "title": "Biology data-response pack",
        "format": "Long-form explanations",
        "difficulty": "Moderate",
        "description": "Focus on keywords, graph interpretation, and concise scientific explanations.",
    },
    {
        "subject": "chemistry",
        "title": "Chemistry calculations pack",
        "format": "Equation and mole practice",
        "difficulty": "Challenging",
        "description": "A calculation-first route for balancing equations, mole ratios, and reaction logic.",
    },
    {
        "subject": "physics",
        "title": "Physics timed paper pack",
        "format": "Theory + practical mix",
        "difficulty": "Balanced",
        "description": "Train under exam pressure using short-answer reasoning and calculation chains.",
    },
    {
        "subject": "english",
        "title": "English analysis pack",
        "format": "Reading + writing",
        "difficulty": "Flexible",
        "description": "Practice extracting evidence, shaping paragraphs, and controlling tone.",
    },
    {
        "subject": "ict",
        "title": "ICT scenario pack",
        "format": "Theory + applied tasks",
        "difficulty": "Moderate",
        "description": "Apply concepts to practical systems, data rules, and spreadsheet scenarios.",
    },
]

HOME_HIGHLIGHTS = [
    {"title": "Massive subject catalogue", "value": "6 core study tracks", "detail": "Built around Cambridge IGCSE syllabus pages."},
    {"title": "Fast note generation", "value": "Upload or paste", "detail": "Turn slides and notes into revision assets in seconds."},
    {"title": "Past paper lanes", "value": "Searchable packs", "detail": "Filter by subject, difficulty, and question style."},
    {"title": "Revision planner", "value": "Spaced repetition", "detail": "Stay on schedule with daily and weekly study blocks."},
]

NAV_ITEMS = [
    {"label": "Home", "endpoint": "home"},
    {"label": "Courses", "endpoint": "courses"},
    {"label": "Notes", "endpoint": "notes"},
    {"label": "Past Papers", "endpoint": "papers"},
    {"label": "Quizzes", "endpoint": "quizzes"},
    {"label": "Upload", "endpoint": "upload_page"},
    {"label": "Planner", "endpoint": "planner"},
    {"label": "Paper Lab", "endpoint": "paper_lab"},
    {"label": "Library", "endpoint": "library"},
    {"label": "Search", "endpoint": "search"},
    {"label": "About", "endpoint": "about"},
]

SITE_TAGLINE = "A massive IGCSE study framework for courses, notes, past papers, quizzes, uploads, planning, and paper generation."

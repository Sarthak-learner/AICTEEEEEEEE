"""Synthetic PDF Generator for SIH26261 Demo Dataset.

Generates 6 compliant-looking synthetic PDF documents with 8 planted issues
as specified in Blueprint.md Section 19.

ALL DOCUMENTS ARE SYNTHETIC.
Watermark footer: "SYNTHETIC DOCUMENT — FOR DEMONSTRATION ONLY — NOT AN OFFICIAL AICTE DOCUMENT"
"""
from pathlib import Path
import fitz  # PyMuPDF

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FOOTER_TEXT = "SYNTHETIC DOCUMENT — FOR DEMONSTRATION ONLY — NOT AN OFFICIAL AICTE DOCUMENT"


def add_header_footer(page, title: str):
    rect = page.rect
    # Header banner
    page.draw_rect(fitz.Rect(36, 36, rect.width - 36, 70), color=(0.1, 0.2, 0.5), fill=(0.93, 0.95, 0.98))
    page.insert_text(fitz.Point(46, 58), title, fontsize=14, fontname="helv", color=(0.1, 0.2, 0.5))
    # Footer watermark
    page.insert_text(fitz.Point(rect.width / 2 - 200, rect.height - 25), FOOTER_TEXT, fontsize=7.5, fontname="helv", color=(0.6, 0.6, 0.6))
    page.draw_line(fitz.Point(36, rect.height - 35), fitz.Point(rect.width - 36, rect.height - 35), color=(0.8, 0.8, 0.8))


def generate_application_form():
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4
    add_header_footer(page, "AICTE APPROVAL APPLICATION FORM (2026-27)")

    content = [
        ("Application ID:", "APP-2026-0042"),
        ("Academic Year:", "2026-27"),
        ("Application Category:", "Extension of Approval"),
        ("Program Level:", "Under Graduate (UG)"),
        ("Institution Name:", "Sunrise Institute of Technology, Demo City"),
        ("AICTE Institution ID:", "AICTE-DEMO-12345"),
        ("State / UT:", "Demo State"),
        ("Sanctioned Intake:", "1200"),
        ("Total Land Area:", "3.00 acres"),
        ("Total Built-up Area:", "24000 sq m"),
        ("Affiliated University:", "Demo Technical University"),
    ]

    y = 100
    for label, val in content:
        page.insert_text(fitz.Point(50, y), label, fontsize=10, fontname="helv", color=(0.2, 0.2, 0.2))
        page.insert_text(fitz.Point(230, y), val, fontsize=10, fontname="helv", color=(0.0, 0.0, 0.0))
        page.draw_line(fitz.Point(50, y + 6), fitz.Point(545, y + 6), color=(0.9, 0.9, 0.9))
        y += 24

    y += 20
    page.insert_text(fitz.Point(50, y), "CHECKLIST OF MANDATORY UPLOADED DOCUMENTS:", fontsize=10, fontname="helv", color=(0.1, 0.2, 0.5))
    y += 18
    docs_list = [
        "[X] APPLICATION_FORM (Certified application disclosure)",
        "[X] FACULTY_LIST (Teaching cadre distribution)",
        "[X] FINANCIAL_STATEMENT (Audited balance sheet & corpus)",
        "[X] LAND_DEED (Registered ownership deed)",
        "[X] BUILDING_PLAN (Approved structural blueprint)",
        "[X] FACULTY_AFFIDAVIT (Notarized deponent declaration)",
    ]
    for d in docs_list:
        page.insert_text(fitz.Point(60, y), d, fontsize=9, fontname="helv", color=(0.2, 0.4, 0.2))
        y += 18

    out_path = OUTPUT_DIR / "01_APPLICATION_FORM.pdf"
    doc.save(str(out_path))
    print(f"Generated {out_path.name}")


def generate_faculty_list():
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    add_header_footer(page, "TEACHING FACULTY CADRE STATEMENT (UG ENGINEERING)")

    page.insert_text(fitz.Point(50, 95), "Institution: Sunrise Institute of Technology, Demo City", fontsize=10, fontname="helv")
    page.insert_text(fitz.Point(50, 112), "Academic Year: 2026-27 | Sanctioned Intake: 1200", fontsize=9, fontname="helv", color=(0.3, 0.3, 0.3))

    # Table Header
    y = 140
    page.draw_rect(fitz.Rect(50, y, 545, y + 20), color=(0.8, 0.8, 0.8), fill=(0.9, 0.92, 0.95))
    page.insert_text(fitz.Point(55, y + 14), "S.No", fontsize=9, fontname="helv")
    page.insert_text(fitz.Point(90, y + 14), "Faculty Name", fontsize=9, fontname="helv")
    page.insert_text(fitz.Point(260, y + 14), "Designation", fontsize=9, fontname="helv")
    page.insert_text(fitz.Point(400, y + 14), "Department", fontsize=9, fontname="helv")
    y += 20

    sample_faculty = [
        ("1", "Dr. A.B. Sharma", "Professor", "Computer Science"),
        ("2", "Dr. Rajesh Iyer", "Professor", "Mechanical Engg"),
        ("3", "Dr. Sneha Patil", "Professor", "Electronics Engg"),
        ("4", "Dr. K.V. Rao", "Professor", "Electrical Engg"),
        ("5", "Dr. Meera Nambiar", "Professor", "Civil Engg"),
        ("6", "Dr. Arvind Gupta", "Professor", "Information Tech"),
        ("7", "Dr. Suresh Verma", "Associate Professor", "Computer Science"),
        ("8", "Dr. Pooja Kulkarni", "Associate Professor", "Mechanical Engg"),
        ("9", "Prof. R.K. Singh", "Assistant Professor", "Computer Science"),
        ("10", "Prof. Ananya Sen", "Assistant Professor", "Electronics Engg"),
    ]

    for sno, name, desig, dept in sample_faculty:
        page.insert_text(fitz.Point(55, y + 14), sno, fontsize=9, fontname="helv")
        page.insert_text(fitz.Point(90, y + 14), name, fontsize=9, fontname="helv")
        page.insert_text(fitz.Point(260, y + 14), desig, fontsize=9, fontname="helv")
        page.insert_text(fitz.Point(400, y + 14), dept, fontsize=9, fontname="helv")
        page.draw_line(fitz.Point(50, y + 18), fitz.Point(545, y + 18), color=(0.92, 0.92, 0.92))
        y += 20

    y += 30
    # Summary Box with Planted Issue 1: Total Faculty 58 (Intake 1200 -> Ratio 0.0483 < 0.0667)
    page.draw_rect(fitz.Rect(50, y, 545, y + 80), color=(0.2, 0.3, 0.6), fill=(0.98, 0.98, 1.0))
    page.insert_text(fitz.Point(60, y + 20), "CADRE SUMMARY BREAKDOWN:", fontsize=10, fontname="helv", color=(0.1, 0.2, 0.5))
    page.insert_text(fitz.Point(60, y + 40), "Professor: 6", fontsize=9, fontname="helv")
    page.insert_text(fitz.Point(180, y + 40), "Associate Professor: 18", fontsize=9, fontname="helv")
    page.insert_text(fitz.Point(340, y + 40), "Assistant Professor: 34", fontsize=9, fontname="helv")
    page.insert_text(fitz.Point(60, y + 65), "Total Faculty: 58", fontsize=11, fontname="helv", color=(0.7, 0.1, 0.1))
    page.insert_text(fitz.Point(200, y + 65), "(Required FSR 1:15 = 80 faculty for 1200 intake)", fontsize=8.5, fontname="helv", color=(0.4, 0.4, 0.4))

    out_path = OUTPUT_DIR / "02_FACULTY_LIST.pdf"
    doc.save(str(out_path))
    print(f"Generated {out_path.name}")


def generate_financial_statement():
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    add_header_footer(page, "AUDITED FINANCIAL STATEMENT & BALANCE SHEET")

    # Planted issue 3: Institution name abbreviation "Sunrise Inst. of Tech."
    page.insert_text(fitz.Point(50, 95), "Name of College: Sunrise Inst. of Tech.", fontsize=11, fontname="helv", color=(0.1, 0.2, 0.5))
    page.insert_text(fitz.Point(50, 115), "Financial Year: 2025-26 | Academic Audit Cycle: 2026-27", fontsize=9, fontname="helv")

    y = 150
    page.draw_rect(fitz.Rect(50, y, 545, y + 22), color=(0.8, 0.8, 0.8), fill=(0.92, 0.92, 0.92))
    page.insert_text(fitz.Point(60, y + 15), "Particulars / Funds Statement", fontsize=10, fontname="helv")
    page.insert_text(fitz.Point(420, y + 15), "Amount in INR", fontsize=10, fontname="helv")
    y += 22

    financials = [
        ("Institutional Development Fund", "Rs. 2,50,00,000"),
        ("Endowment Fund Fixed Deposit", "Rs. 2,00,00,000"),
        ("Reserve / Capital Fund", "Rs. 1,50,00,000"),
        ("Corpus Fund: Rs. 6.00 crore", "Rs. 6,00,00,000"),
        ("Annual Net Operating Surplus", "Rs. 85,00,000"),
    ]

    for item, amt in financials:
        page.insert_text(fitz.Point(60, y + 16), item, fontsize=9.5, fontname="helv")
        page.insert_text(fitz.Point(420, y + 16), amt, fontsize=9.5, fontname="helv")
        page.draw_line(fitz.Point(50, y + 22), fitz.Point(545, y + 22), color=(0.9, 0.9, 0.9))
        y += 24

    y += 40
    page.insert_text(fitz.Point(50, y), "STATUTORY AUDITOR'S REPORT:", fontsize=10, fontname="helv", color=(0.2, 0.2, 0.2))
    y += 18
    page.insert_text(fitz.Point(50, y), "We have audited the Balance Sheet of Sunrise Inst. of Tech. as of 31st March 2026.", fontsize=8.5, fontname="helv")
    y += 14
    page.insert_text(fitz.Point(50, y), "Total Corpus Fund maintained exceeds statutory norms at Rs. 6.00 crore.", fontsize=8.5, fontname="helv")

    out_path = OUTPUT_DIR / "03_FINANCIAL_STATEMENT.pdf"
    doc.save(str(out_path))
    print(f"Generated {out_path.name}")


def generate_land_deed():
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    add_header_footer(page, "GOVERNMENT OF DEMO STATE - SUB-REGISTRAR OFFICE")

    page.insert_text(fitz.Point(50, 95), "REGISTERED TITLE DEED / CONVEYANCE OF LAND", fontsize=12, fontname="helv", color=(0.5, 0.1, 0.1))
    page.insert_text(fitz.Point(50, 115), "Document No: REG-2019-9481 | Book 1 Volume 412", fontsize=9, fontname="helv")

    y = 150
    # Planted issue 2: Deed says 2.10 acres, application claimed 3.00 acres!
    lines = [
        "THIS DEED OF CONVEYANCE is executed on 15th April 2019 in Demo City.",
        "VENDEE: Sunrise Institute of Technology, represented by its Secretary.",
        "PROPERTY SCHEDULE:",
        "Survey Number: 142/3A, Village Rampur, Demo Taluk, Demo City.",
        "Total Land Area measuring: 2.10 acres (contiguous single plot).",
        "Boundaries: North by PWD Road, South by Survey 142/4, East by Canal, West by Survey 141.",
        "Zoning: Institutional / Educational Use Approved by Competent Authority.",
    ]

    for line in lines:
        page.insert_text(fitz.Point(50, y), line, fontsize=9.5, fontname="helv", color=(0.15, 0.15, 0.15))
        y += 24

    y += 30
    page.draw_rect(fitz.Rect(50, y, 220, y + 60), color=(0.4, 0.4, 0.4))
    page.insert_text(fitz.Point(60, y + 35), "[OFFICIAL SEAL & SIGNATURE]", fontsize=8, fontname="helv", color=(0.5, 0.5, 0.5))
    page.insert_text(fitz.Point(60, y + 50), "Sub-Registrar, Demo City", fontsize=8.5, fontname="helv")

    out_path = OUTPUT_DIR / "04_LAND_DEED.pdf"
    doc.save(str(out_path))
    print(f"Generated {out_path.name}")


def generate_building_plan():
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    add_header_footer(page, "ARCHITECTURAL BLUEPRINT & AREA STATEMENT")

    # Title block
    page.insert_text(fitz.Point(50, 95), "Project: Main Academic Complex (Sunrise Institute of Technology)", fontsize=10, fontname="helv")
    page.insert_text(fitz.Point(50, 110), "Architect: COA Reg. CA/2012/99281 | Scale: 1:100", fontsize=9, fontname="helv", color=(0.3, 0.3, 0.3))

    # Vector CAD drawing mockup
    y = 135
    page.draw_rect(fitz.Rect(50, y, 545, y + 240), color=(0.1, 0.2, 0.4), width=1.5)
    # Rooms
    page.draw_rect(fitz.Rect(60, y + 10, 200, y + 110), color=(0.3, 0.3, 0.3))
    page.insert_text(fitz.Point(70, y + 60), "Classroom 101-104\n(400 sq m)", fontsize=8, fontname="helv")

    page.draw_rect(fitz.Rect(210, y + 10, 370, y + 110), color=(0.3, 0.3, 0.3))
    page.insert_text(fitz.Point(220, y + 60), "Central Library\n(600 sq m)", fontsize=8, fontname="helv")

    page.draw_rect(fitz.Rect(380, y + 10, 535, y + 110), color=(0.3, 0.3, 0.3))
    page.insert_text(fitz.Point(390, y + 60), "Computer Lab 1 & 2\n(450 sq m)", fontsize=8, fontname="helv")

    page.draw_rect(fitz.Rect(60, y + 125, 290, y + 225), color=(0.3, 0.3, 0.3))
    page.insert_text(fitz.Point(70, y + 175), "Administration & Faculty Rooms", fontsize=8, fontname="helv")

    page.draw_rect(fitz.Rect(300, y + 125, 535, y + 225), color=(0.3, 0.3, 0.3))
    page.insert_text(fitz.Point(320, y + 175), "Auditorium & Seminar Hall", fontsize=8, fontname="helv")

    y += 260
    # Planted issue 5: Plan area statement totals 18,000 sq m vs application 24,000 sq m
    page.draw_rect(fitz.Rect(50, y, 545, y + 75), color=(0.2, 0.3, 0.6), fill=(0.95, 0.97, 1.0))
    page.insert_text(fitz.Point(60, y + 18), "CERTIFIED BUILT-UP AREA STATEMENT:", fontsize=9.5, fontname="helv", color=(0.1, 0.2, 0.5))
    page.insert_text(fitz.Point(60, y + 36), "Ground Floor Built-up Area: 9,000 sq m", fontsize=9, fontname="helv")
    page.insert_text(fitz.Point(300, y + 36), "First Floor Built-up Area: 9,000 sq m", fontsize=9, fontname="helv")
    page.insert_text(fitz.Point(60, y + 60), "Total Built-up Area: 18000 sq m", fontsize=10.5, fontname="helv", color=(0.7, 0.1, 0.1))

    out_path = OUTPUT_DIR / "05_BUILDING_PLAN.pdf"
    doc.save(str(out_path))
    print(f"Generated {out_path.name}")


def generate_faculty_affidavit():
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    add_header_footer(page, "NON-JUDICIAL STAMP PAPER - NOTARIZED AFFIDAVIT")

    page.insert_text(fitz.Point(50, 95), "AFFIDAVIT ON FULL-TIME FACULTY APPOINTMENTS", fontsize=11, fontname="helv", color=(0.4, 0.1, 0.1))
    page.insert_text(fitz.Point(50, 115), "Before the Notary Public, Demo City", fontsize=9, fontname="helv")

    y = 150
    text_paras = [
        "I, the Secretary of Sunrise Institute of Technology, solemnly affirm and state as follows:",
        "1. All faculty listed are appointed on a regular full-time basis with AICTE pay scales.",
        "2. The faculty deponents solemnly affirmed include:",
        "   - Dr. A.B. Sharma, Professor",
        "   - Dr. Rajesh Iyer, Professor",
        "   - Dr. Sneha Patil, Professor",
        # Planted issue 4: Dr. Vikram Malhotra is affirmed here but ABSENT from 02_FACULTY_LIST.pdf!
        "   - Dr. Vikram Malhotra, Professor (Affidavit deponent, absent from faculty list)",
        "   - Prof. R.K. Singh, Assistant Professor",
        "3. No faculty member is simultaneously employed at any other institution.",
    ]

    for p in text_paras:
        page.insert_text(fitz.Point(50, y), p, fontsize=9.5, fontname="helv", color=(0.15, 0.15, 0.15))
        y += 24

    y += 40
    page.draw_rect(fitz.Rect(50, y, 200, y + 55), color=(0.4, 0.4, 0.4))
    page.insert_text(fitz.Point(60, y + 30), "[NOTARY SEAL & SIGNATURE]", fontsize=8, fontname="helv", color=(0.5, 0.5, 0.5))
    page.insert_text(fitz.Point(60, y + 45), "Advocate & Notary Public", fontsize=8.5, fontname="helv")

    out_path = OUTPUT_DIR / "06_FACULTY_AFFIDAVIT.pdf"
    doc.save(str(out_path))
    print(f"Generated {out_path.name}")


if __name__ == "__main__":
    generate_application_form()
    generate_faculty_list()
    generate_financial_statement()
    generate_land_deed()
    generate_building_plan()
    generate_faculty_affidavit()
    print("All synthetic demo documents generated successfully!")

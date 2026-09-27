import json
import cv2
import numpy as np

def generate_a4_omr_sheet():
    W, H = 1200, 1600
    canvas = np.ones((H, W, 3), dtype=np.uint8) * 255

    # 1. Anchor Marks 4 มุม (40x40 px)
    margin = 50
    marker_size = 40
    cv2.rectangle(canvas, (margin, margin), (margin + marker_size, margin + marker_size), (0, 0, 0), -1)
    cv2.rectangle(canvas, (W - margin - marker_size, margin), (W - margin, margin + marker_size), (0, 0, 0), -1)
    cv2.rectangle(canvas, (margin, H - margin - marker_size), (margin + marker_size, H - margin), (0, 0, 0), -1)
    cv2.rectangle(canvas, (W - margin - marker_size, H - margin - marker_size), (W - margin, H - margin), (0, 0, 0), -1)

    # 2. หัวกระดาษ
    cv2.putText(canvas, "OMR EXAM ANSWER SHEET", (400, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
    cv2.putText(canvas, "Name: ___________________________________ Subject: __________________", (120, 125), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

    # 3. ส่วนระบายชุดข้อสอบ (Exam Set: 1-4)
    cv2.rectangle(canvas, (120, 150), (420, 440), (0, 0, 0), 1)
    cv2.putText(canvas, "Exam Set", (220, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    
    exam_set_coords = {}
    for i, set_num in enumerate(["1", "2", "3", "4"]):
        x = 180 + (i * 60)
        y = 230
        cv2.circle(canvas, (x, y), 12, (0, 0, 0), 1)
        cv2.putText(canvas, set_num, (x - 4, y + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
        exam_set_coords[set_num] = [x, y]

    # 4. ส่วนรหัสนักเรียน 6 หลัก (Student ID: 0-9)
    cv2.rectangle(canvas, (460, 150), (1080, 440), (0, 0, 0), 1)
    cv2.putText(canvas, "Student ID", (710, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

    student_code_grid = {
        "x_start": 560,
        "y_start": 255,
        "x_spacing": 90,
        "y_spacing": 17,
        "digits": 6
    }

    # กล่องสี่เหลี่ยมเขียนมือ 6 ช่อง
    for digit_idx in range(6):
        box_x = student_code_grid["x_start"] + (digit_idx * student_code_grid["x_spacing"]) - 15
        cv2.rectangle(canvas, (box_x, 195), (box_x + 30, 230), (0, 0, 0), 1)

    # วงกลมตัวเลข 0-9 ทั้ง 6 คอลัมน์
    for digit in range(10):
        y = student_code_grid["y_start"] + (digit * student_code_grid["y_spacing"])
        for col in range(6):
            x = student_code_grid["x_start"] + (col * student_code_grid["x_spacing"])
            cv2.circle(canvas, (x, y), 7, (0, 0, 0), 1)
            cv2.putText(canvas, str(digit), (x - 3, y + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 0), 1)

    # เส้นแบ่ง
    cv2.line(canvas, (120, 465), (1080, 465), (0, 0, 0), 2)

    # 5. ส่วนคำตอบ 60 ข้อ (2 คอลัมน์)
    options = ["A", "B", "C", "D"]
    col1_config = {"x_start": 230, "y_start": 510, "x_spacing": 60, "y_spacing": 33}
    col2_config = {"x_start": 770, "y_start": 510, "x_spacing": 60, "y_spacing": 33}

    for q in range(1, 61):
        col = 0 if q <= 30 else 1
        q_in_col = (q - 1) % 30
        col_cfg = col1_config if col == 0 else col2_config
        y = col_cfg["y_start"] + (q_in_col * col_cfg["y_spacing"])

        cv2.putText(canvas, f"{q:2d}.", (col_cfg["x_start"] - 70, y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)

        for idx, opt in enumerate(options):
            x = col_cfg["x_start"] + (idx * col_cfg["x_spacing"])
            cv2.circle(canvas, (x, y), 11, (0, 0, 0), 1)
            cv2.putText(canvas, opt, (x - 5, y + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)

    # 6. บันทึกไฟล์
    template_data = {
        "paper_size": [W, H],
        "exam_set": exam_set_coords,
        "student_code": {
            "digits": 6,
            "grid": student_code_grid
        },
        "answers": {
            "col1": col1_config,
            "col2": col2_config
        }
    }

    cv2.imwrite("omr_sheet_A4.png", canvas)
    
    with open("omr_template.json", "w", encoding="utf-8") as f:
        json.dump(template_data, f, indent=2)

    print("SUCCESS_NEW_LAYOUT_GENERATED")

if __name__ == "__main__":
    generate_a4_omr_sheet()
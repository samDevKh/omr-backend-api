import cv2
import numpy as np

def four_point_transform(image, pts, target_width=1200, target_height=1600):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]       # Top-Left
    rect[2] = pts[np.argmax(s)]       # Bottom-Right

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]    # Top-Right
    rect[3] = pts[np.argmax(diff)]    # Bottom-Left

    dst = np.array([
        [0, 0],
        [target_width - 1, 0],
        [target_width - 1, target_height - 1],
        [0, target_height - 1]
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, M, (target_width, target_height))

def find_paper_contour(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blurred, 75, 200)

    cnts, _ = cv2.findContours(edged.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)

    for c in cnts:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4:
            return approx.reshape(4, 2)
    return None

def process_omr(image_bytes, template_config):
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Invalid Image File")

    # 1. Perspective Transform หรือ Resize ขนาด 1200x1600
    paper_pts = find_paper_contour(image)
    if paper_pts is not None:
        warped = four_point_transform(image, paper_pts, 1200, 1600)
    else:
        warped = cv2.resize(image, (1200, 1600))

    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 170, 255, cv2.THRESH_BINARY_INV)

    radius = 11
    threshold_pixels = 100

    def check_bubble(cx, cy):
        mask = np.zeros(thresh.shape, dtype="uint8")
        cv2.circle(mask, (int(cx), int(cy)), radius, 255, -1)
        return cv2.countNonZero(cv2.bitwise_and(thresh, thresh, mask=mask))

    # --- A. อ่านชุดข้อสอบ (Exam Set: 1-4) ---
    exam_set_result = "1"
    exam_set_cfg = template_config.get("exam_set", {})
    for set_num, pos in exam_set_cfg.items():
        if check_bubble(pos[0], pos[1]) > threshold_pixels:
            exam_set_result = set_num
            break

    # --- B. อ่านรหัสนักเรียน 6 หลัก ---
    student_code_digits = []
    sc_cfg = template_config.get("student_code", {}).get("grid", {})
    if sc_cfg:
        for col in range(sc_cfg.get("digits", 6)):
            detected_digit = "?"
            max_p = 0
            for digit in range(10):
                x = sc_cfg["x_start"] + (col * sc_cfg["x_spacing"])
                y = sc_cfg["y_start"] + (digit * sc_cfg["y_spacing"])
                p_count = check_bubble(x, y)
                if p_count > threshold_pixels and p_count > max_p:
                    max_p = p_count
                    detected_digit = str(digit)
            student_code_digits.append(detected_digit)
    
    scanned_student_code = "".join(student_code_digits) if student_code_digits else "UNKNOWN"

    # --- C. อ่านคำตอบ 60 ข้อ ---
    answers_result = {}
    options = ["A", "B", "C", "D"]
    ans_cfg = template_config.get("answers", {})
    col1_cfg = ans_cfg.get("col1", {})
    col2_cfg = ans_cfg.get("col2", {})

    for q in range(1, 61):
        col = 0 if q <= 30 else 1
        q_idx = (q - 1) % 30
        col_info = col1_cfg if col == 0 else col2_cfg

        y = col_info["y_start"] + (q_idx * col_info["y_spacing"])
        marked_options = []

        for idx, opt in enumerate(options):
            x = col_info["x_start"] + (idx * col_info["x_spacing"])
            if check_bubble(x, y) > threshold_pixels:
                marked_options.append(opt)

        if len(marked_options) == 1:
            answers_result[str(q)] = marked_options[0]
        elif len(marked_options) > 1:
            answers_result[str(q)] = "MULTIPLE"
        else:
            answers_result[str(q)] = "BLANK"

    return {
        "exam_set": exam_set_result,
        "student_code": scanned_student_code,
        "answers": answers_result
    }
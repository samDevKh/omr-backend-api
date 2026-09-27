import cv2
import numpy as np

def order_points(pts):
    """ จัดเรียงจุด 4 จุดให้อยู่ในลำดับ: [Top-Left, Top-Right, Bottom-Right, Bottom-Left] """
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)] # Top-Left
    rect[2] = pts[np.argmax(s)] # Bottom-Right

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)] # Top-Right
    rect[3] = pts[np.argmax(diff)] # Bottom-Left

    return rect

def four_point_transform(image, pts, target_width=800, target_height=1000):
    """ ดัดภาพเอียงตามจุด 4 จุดให้กลายเป็นภาพตรงขนาดมาตรฐาน """
    rect = order_points(pts)
    dst = np.array([
        [0, 0],
        [target_width - 1, 0],
        [target_width - 1, target_height - 1],
        [0, target_height - 1]
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, M, (target_width, target_height))
    return warped

def find_paper_contour(image):
    """ ค้นหาขอบกระดาษคำตอบจากภาพถ่าย """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blurred, 75, 200)

    # ค้นหา Contours
    cnts, _ = cv2.findContours(edged.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)

    for c in cnts:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)

        # เจอรูปสี่เหลี่ยมที่ใหญ่ที่สุด (ขอบกระดาษ)
        if len(approx) == 4:
            return approx.reshape(4, 2)

    return None

def process_omr(image_bytes, template_config):
    """ 
    รับไฟล์ภาพและโครงร่างพิกัด (Template Config) 
    คืนค่า dict ของคำตอบที่ถูกระบายในแต่ละข้อ
    """
    # 1. แปลงไฟล์ภาพ Bytes เป็น OpenCV Image
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Invalid Image File")

    # 2. Perspective Transform (ดัดภาพให้ตรง)
    paper_pts = find_paper_contour(image)
    if paper_pts is not None:
        warped = four_point_transform(image, paper_pts, 800, 1000)
    else:
        # หากหาขอบกระดาษไม่เจอ ให้ปรับขนาดภาพเป็นขนาดมาตรฐานตรงๆ
        warped = cv2.resize(image, (800, 1000))

    # 3. แปลงเป็นภาพ Gray Scale และ Binarize (Threshold)
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    # Otsu's thresholding สำหรับเเยกพิกเซลขาว-ดำ
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)

    # 4. Bubble Detection ตามพิกัด Grid ใน Template
    # ตัวอย่างโครงสร้างการวัดค่าความเข้มพิกเซลในจุดระบาย
    results = {}
    options = ["A", "B", "C", "D"]
    threshold_pixel_count = 500  # จำนวนพิกเซลสีขาวขั้นต่ำที่ถือว่าฝนตัวเลือก

    # สมมติการคำนวณตำแหน่ง Grid (สามารถใช้พิกัดจาก template_config ได้)
    # สมมติ 60 ข้อ แบ่งเป็น 2 คอลัมน์ (คอลัมน์ละ 30 ข้อ)
    for q in range(1, 61):
        col = 0 if q <= 30 else 1
        q_in_col = (q - 1) % 30
        
        # คำนวณพิกัด Y และ X ในภาพ warped (800x1000)
        start_y = int(150 + (q_in_col * 25))
        start_x_base = 100 if col == 0 else 480

        marked_options = []
        for idx, opt in enumerate(options):
            x = int(start_x_base + (idx * 35))
            y = start_y
            r = 10  # รัศมีวงกลม

            # สร้าง Mask เฉพาะวงกลมบริเวณตัวเลือกนั้น
            mask = np.zeros(thresh.shape, dtype="uint8")
            cv2.circle(mask, (x, y), r, 255, -1)

            # นับพิกเซลที่มีการระบาย (สีขาวใน thresh image)
            total_pixels = cv2.countNonZero(cv2.bitwise_and(thresh, thresh, mask=mask))

            if total_pixels > threshold_pixel_count:
                marked_options.append((opt, total_pixels))

        # ตรวจสอบผลการระบาย
        if len(marked_options) == 1:
            results[str(q)] = marked_options[0][0]  # ระบาย 1 ตัวเลือกถูกต้อง
        elif len(marked_options) > 1:
            results[str(q)] = "MULTIPLE"           # ระบายซ้ำหลายข้อ
        else:
            results[str(q)] = "BLANK"              # ไม่ได้ระบาย

    return results
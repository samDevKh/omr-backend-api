import json
import os
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from supabase import create_client, Client

# 1. นำเข้า Engine ประมวลผลภาพ OMR จาก omr_processor.py
from omr_processor import process_omr

app = FastAPI(title="OMR Processing API")

# --- Set up Supabase Connection ---
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# โหลด OMR Template พิกัด
with open("omr_template.json", "r", encoding="utf-8") as f:
    TEMPLATE_DATA = json.load(f)

@app.get("/")
def read_root():
    return {"status": "online", "message": "OMR Processing Engine Ready"}

@app.post("/api/v1/scan")
async def scan_omr_sheet(
    exam_id: int = Form(...),
    file: UploadFile = File(...)
):
    try:
        # อ่านไฟล์ภาพที่อัปโหลดเข้ามาเป็น Bytes
        contents = await file.read()

        # 2. เรียกใช้ OpenCV OMR Engine อ่านคำตอบจากภาพจริง
        scanned_answers = process_omr(contents, TEMPLATE_DATA)
        
        # สมมติรหัสนักเรียน (หรืออนาคตอ่านจากแถบระบายรหัสบนกระดาษ OMR)
        scanned_student_code = "650123" 

        # 3. ดึงเฉลยข้อสอบจาก Supabase ตาม exam_id
        answer_key = {}
        score_per_q = 1.0

        if supabase:
            res = supabase.table("exams").select("answer_key, score_per_question").eq("id", exam_id).execute()
            if not res.data:
                raise HTTPException(status_code=404, detail=f"Exam ID {exam_id} not found")
            
            answer_key = res.data[0]["answer_key"]
            score_per_q = float(res.data[0].get("score_per_question", 1.0))
        else:
            # เฉลยสำรองกรณีทดสอบ Local แบบไม่ได้ต่อ DB
            answer_key = {"1": "A", "2": "B", "3": "C", "4": "D", "5": "A"}

        # 4. ตรวจคำตอบและคำนวณคะแนน
        correct_count = 0
        details_to_insert = []
        
        for q_num, correct_choice in answer_key.items():
            # ดึงตัวเลือกที่นักเรียนฝนจากผลสแกนจริง (ถ้าฝนไม่ได้ หรือไม่ระบาย จะคืนค่า BLANK)
            st_choice = scanned_answers.get(str(q_num), "BLANK")
            is_corr = (st_choice == correct_choice)
            score = score_per_q if is_corr else 0.0
            
            if is_corr:
                correct_count += 1
                
            details_to_insert.append({
                "question_number": int(q_num),
                "student_choice": st_choice,
                "correct_choice": correct_choice,
                "is_correct": is_corr,
                "score": score
            })

        total_score = correct_count * score_per_q
        max_score = len(answer_key) * score_per_q
        percentage = (total_score / max_score * 100) if max_score > 0 else 0.0

        # 5. บันทึกผลสอบลง Supabase
        if supabase:
            # 5.1 บันทึกสรุปคะแนนรวมลงตาราง submissions
            sub_res = supabase.table("submissions").insert({
                "exam_id": exam_id,
                "student_code": scanned_student_code,
                "total_score": total_score,
                "max_score": max_score,
                "percentage": percentage
            }).execute()

            submission_id = sub_res.data[0]["id"]

            # 5.2 บันทึกรายละเอียดรายข้อลงตาราง submission_details
            for item in details_to_insert:
                item["submission_id"] = submission_id
            
            supabase.table("submission_details").insert(details_to_insert).execute()

        return {
            "status": "success",
            "student_code": scanned_student_code,
            "total_score": total_score,
            "max_score": max_score,
            "percentage": percentage,
            "details": details_to_insert
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
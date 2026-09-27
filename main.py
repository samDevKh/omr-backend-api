import json
import os
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from supabase import create_client, Client
from omr_processor import process_omr

app = FastAPI(title="OMR Processing API")

# ดึงค่าการเชื่อมต่อ Supabase จาก Environment Variables บน Hosting (Render)
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# โหลดไฟล์พิกัดกระดาษ OMR
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
        # [จุดที่ 1]: ตรวจสอบการเชื่อมต่อ Supabase Database
        if not supabase:
            raise HTTPException(
                status_code=500,
                detail="Supabase Connection Failure. Please verify SUPABASE_URL and SUPABASE_KEY on Render Environment Variables."
            )

        contents = await file.read()

        # 1. ให้ OMR Engine (OpenCV) ประมวลผลรูปภาพ
        omr_output = process_omr(contents, TEMPLATE_DATA)
        scanned_answers = omr_output.get("answers", {})
        scanned_student_code = omr_output.get("student_code", "UNKNOWN")
        scanned_exam_set = omr_output.get("exam_set", "1")

        # 2. ดึงเฉลยข้อสอบจาก Supabase
        res = supabase.table("exams").select("answer_key, score_per_question").eq("id", exam_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail=f"Exam ID {exam_id} not found in database")

        answer_key = res.data[0].get("answer_key", {})
        score_per_q = float(res.data[0].get("score_per_question", 1.0))

        # 3. คำนวณคะแนนรายข้อ
        correct_count = 0
        details_to_insert = []

        for q_num, correct_choice in answer_key.items():
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

        # [จุดที่ 2]: เช็กและสร้างข้อมูลนักเรียนในตาราง students อัตโนมัติ ป้องกัน Foreign Key Violation Error 500
        st_check = supabase.table("students").select("student_code").eq("student_code", scanned_student_code).execute()
        if not st_check.data:
            supabase.table("students").insert({
                "student_code": scanned_student_code,
                "full_name": f"นักเรียนรหัส {scanned_student_code}",
                "class_room": "ไม่ระบุ"
            }).execute()

        # [จุดที่ 3]: บันทึกสรุปคะแนนลงตาราง submissions
        sub_res = supabase.table("submissions").insert({
            "exam_id": exam_id,
            "student_code": scanned_student_code,
            "total_score": total_score,
            "max_score": max_score,
            "percentage": percentage
        }).execute()

        submission_id = sub_res.data[0]["id"]

        # [จุดที่ 4]: ผูก submission_id และบันทึกรายละเอียดลงตาราง submission_details
        for item in details_to_insert:
            item["submission_id"] = submission_id

        supabase.table("submission_details").insert(details_to_insert).execute()

        # ตอบกลับผลลัพธ์ผ่าน API
        return {
            "status": "success",
            "submission_id": submission_id,
            "exam_set": scanned_exam_set,
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
import json
import os
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from supabase import create_client, Client
from omr_processor import process_omr

app = FastAPI(title="OMR Processing API")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

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
        contents = await file.read()

        # 1. ประมวลผลภาพ OMR
        omr_output = process_omr(contents, TEMPLATE_DATA)
        scanned_answers = omr_output["answers"]
        scanned_student_code = omr_output["student_code"]
        scanned_exam_set = omr_output["exam_set"]

        # 2. ดึงเฉลยจาก Supabase
        answer_key = {}
        score_per_q = 1.0

        if supabase:
            res = supabase.table("exams").select("answer_key, score_per_question").eq("id", exam_id).execute()
            if not res.data:
                raise HTTPException(status_code=404, detail=f"Exam ID {exam_id} not found")
            
            answer_key = res.data[0]["answer_key"]
            score_per_q = float(res.data[0].get("score_per_question", 1.0))
        else:
            answer_key = {"1": "A", "2": "B", "3": "C", "4": "D"}

        # 3. คำนวณคะแนน
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

        # 4. บันทึกลง Supabase
        if supabase:
            sub_res = supabase.table("submissions").insert({
                "exam_id": exam_id,
                "student_code": scanned_student_code,
                "total_score": total_score,
                "max_score": max_score,
                "percentage": percentage
            }).execute()

            submission_id = sub_res.data[0]["id"]

            for item in details_to_insert:
                item["submission_id"] = submission_id
            
            supabase.table("submission_details").insert(details_to_insert).execute()

        return {
            "status": "success",
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
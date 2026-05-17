from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import os, psycopg2, psycopg2.extras, logging

DATABASE_URL = os.getenv("DATABASE_URL", "")
log = logging.getLogger("meems")

app = FastAPI(title="MEEMS API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

def q(sql, params=None):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

def q1(sql, params=None):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

@app.get("/")
def root():
    return {"app": "MEEMS API", "version": "1.0.0", "status": "running"}

@app.get("/health")
def health():
    try:
        q1("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(503, str(e))

@app.get("/api/dashboard/kpi")
def kpi():
    row = q1("""
        SELECT
            (SELECT COUNT(*) FROM equipment WHERE decom_date IS NULL) AS active_equipment,
            (SELECT COUNT(*) FROM equipment WHERE decom_date IS NOT NULL) AS decom_equipment,
            (SELECT COUNT(*) FROM equipment WHERE ecri_risk='HIGH' AND decom_date IS NULL) AS high_risk,
            (SELECT COALESCE(SUM(price),0) FROM equipment) AS total_value,
            (SELECT COUNT(*) FROM work_orders WHERE EXTRACT(MONTH FROM reported_date)=EXTRACT(MONTH FROM NOW()) AND EXTRACT(YEAR FROM reported_date)=EXTRACT(YEAR FROM NOW())) AS wo_this_month,
            (SELECT COUNT(*) FROM work_orders WHERE (flag_overdue_7d OR flag_overdue_30d) AND close_date IS NULL) AS overdue_count,
            (SELECT COUNT(*) FROM work_orders WHERE flag_close_24h) AS close_24h_count,
            (SELECT COUNT(*) FROM pm_records) AS pm_total,
            (SELECT COUNT(*) FROM pm_records WHERE UPPER(result) IN ('PASS','P')) AS pm_passed
    """)
    return dict(row)

@app.get("/api/dashboard/overdue")
def overdue():
    rows = q("""
        SELECT id, rec_no, dept, ecri_name, reported_date, technician, equipment_id,
               CASE WHEN flag_overdue_30d THEN 30 ELSE 8 END AS overdue_days
        FROM work_orders
        WHERE (flag_overdue_7d OR flag_overdue_30d) AND close_date IS NULL
        ORDER BY overdue_days DESC LIMIT 20
    """)
    return [dict(r) for r in rows]

@app.get("/api/dashboard/recent-wo")
def recent_wo():
    rows = q("""
        SELECT id, rec_no, dept, equipment_id, ecri_name, symptom,
               technician, reported_date, close_date,
               flag_overdue_7d, flag_overdue_30d, flag_wait_parts
        FROM work_orders ORDER BY reported_date DESC, id DESC LIMIT 10
    """)
    return [dict(r) for r in rows]

@app.get("/api/dashboard/pm-completion")
def pm_completion():
    rows = q("SELECT * FROM v_pm_completion ORDER BY total DESC LIMIT 20")
    return [dict(r) for r in rows]

@app.get("/api/equipment")
def list_equipment(
    q_str: str = Query("", alias="q"),
    dept: str = Query(""),
    risk: str = Query(""),
    status: str = Query(""),
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    where = ["1=1"]; params = []
    if q_str:
        where.append("(equipment_id ILIKE %s OR ecri_name ILIKE %s OR brand ILIKE %s)")
        params += [f"%{q_str}%"]*3
    if dept: where.append("dept=%s"); params.append(dept)
    if risk: where.append("ecri_risk=%s"); params.append(risk)
    if status == "active": where.append("decom_date IS NULL")
    elif status == "decom": where.append("decom_date IS NOT NULL")
    sql = f"SELECT equipment_id,dept,ecri_name,brand,model,ecri_risk,price,pm_status,decom_date,inventory_date,(decom_date IS NULL) AS is_active FROM equipment WHERE {' AND '.join(where)} ORDER BY dept,ecri_name LIMIT %s OFFSET %s"
    rows = q(sql, params+[limit, offset])
    count = q1(f"SELECT COUNT(*) AS total FROM equipment WHERE {' AND '.join(where)}", params)
    return {"total": count["total"], "items": [dict(r) for r in rows]}

@app.get("/api/equipment/{equipment_id}")
def get_equipment(equipment_id: str):
    row = q1("SELECT *,(decom_date IS NULL) AS is_active FROM equipment WHERE equipment_id=%s", (equipment_id,))
    if not row: raise HTTPException(404, "ไม่พบ Equipment ID")
    return dict(row)

@app.get("/api/equipment/{equipment_id}/history")
def eq_history(equipment_id: str):
    pm = q("SELECT action_date AS date,'PM' AS type,action_by,result,notes FROM pm_records WHERE equipment_id=%s ORDER BY action_date DESC", (equipment_id,))
    hist = q("SELECT work_date AS date,work_type AS type,symptom,fix_detail,cost_service FROM equipment_history WHERE equipment_id=%s ORDER BY work_date DESC", (equipment_id,))
    wo = q("SELECT reported_date AS date,'REPAIR' AS type,symptom,close_date,rec_no FROM work_orders WHERE equipment_id=%s ORDER BY reported_date DESC", (equipment_id,))
    return {"pm": [dict(r) for r in pm], "history": [dict(r) for r in hist], "work_orders": [dict(r) for r in wo]}

@app.get("/api/work-orders")
def list_wo(
    q_str: str = Query("", alias="q"),
    dept: str = Query(""),
    status: str = Query(""),
    limit: int = Query(100, le=500),
    offset: int = 0,
):
    where = ["1=1"]; params = []
    if q_str:
        where.append("(rec_no ILIKE %s OR dept ILIKE %s OR ecri_name ILIKE %s OR symptom ILIKE %s)")
        params += [f"%{q_str}%"]*4
    if dept: where.append("dept=%s"); params.append(dept)
    if status == "ปิดงาน": where.append("close_date IS NOT NULL")
    elif status == "รออะไหล่": where.append("flag_wait_parts=TRUE AND close_date IS NULL")
    elif status == "ค้างซ่อม": where.append("(flag_overdue_7d OR flag_overdue_30d) AND close_date IS NULL")
    elif status == "กำลังซ่อม": where.append("close_date IS NULL AND NOT flag_overdue_7d AND NOT flag_wait_parts")
    sql = f"""SELECT id,rec_no,dept,equipment_id,ecri_name,symptom,technician,
              reported_date,close_date,flag_overdue_7d,flag_overdue_30d,
              flag_wait_parts,flag_critical,flag_close_24h,flag_done_7d,
              CASE WHEN close_date IS NOT NULL THEN 'ปิดงาน'
                   WHEN flag_overdue_30d OR flag_overdue_7d THEN 'ค้างซ่อม'
                   WHEN flag_wait_parts THEN 'รออะไหล่'
                   ELSE 'กำลังซ่อม' END AS status
              FROM work_orders WHERE {' AND '.join(where)}
              ORDER BY reported_date DESC,id DESC LIMIT %s OFFSET %s"""
    rows = q(sql, params+[limit, offset])
    count = q1(f"SELECT COUNT(*) AS total FROM work_orders WHERE {' AND '.join(where)}", params)
    return {"total": count["total"], "items": [dict(r) for r in rows]}

@app.get("/api/pm")
def list_pm(dept: str = Query(""), limit: int = Query(100, le=500)):
    where = ["1=1"]; params = []
    if dept: where.append("dept=%s"); params.append(dept)
    rows = q(f"SELECT * FROM pm_records WHERE {' AND '.join(where)} ORDER BY action_date DESC NULLS LAST LIMIT %s", params+[limit])
    return [dict(r) for r in rows]

@app.get("/api/reports/wo-summary")
def wo_summary():
    rows = q("""
        SELECT dept, COUNT(*) total,
            COUNT(*) FILTER (WHERE close_date IS NOT NULL) closed,
            COUNT(*) FILTER (WHERE flag_overdue_7d OR flag_overdue_30d) overdue,
            COUNT(*) FILTER (WHERE flag_user_error) user_error,
            COUNT(*) FILTER (WHERE flag_close_24h) close_24h,
            COALESCE(SUM(cost_service+parts_cost),0) total_cost
        FROM work_orders GROUP BY dept ORDER BY total DESC
    """)
    return [dict(r) for r in rows]

@app.get("/api/reports/inventory-summary")
def inv_summary():
    row = q1("""
        SELECT COUNT(*) total,
            COUNT(*) FILTER (WHERE decom_date IS NULL) active,
            COUNT(*) FILTER (WHERE decom_date IS NOT NULL) decom,
            COUNT(*) FILTER (WHERE ecri_risk='HIGH' AND decom_date IS NULL) high_risk,
            COALESCE(SUM(price),0) total_value
        FROM equipment
    """)
    by_dept = q("SELECT dept,COUNT(*) total,COUNT(*) FILTER (WHERE decom_date IS NULL) active,COALESCE(SUM(price),0) total_value FROM equipment GROUP BY dept ORDER BY total DESC")
    return {"summary": dict(row), "by_dept": [dict(r) for r in by_dept]}

@app.get("/api/notifications")
def notifications():
    rows = q("SELECT * FROM notifications WHERE is_read=FALSE ORDER BY created_at DESC LIMIT 50")
    return [dict(r) for r in rows]

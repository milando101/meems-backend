"""
MEEMS — FastAPI Backend v1.0
รัน: uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
import os, psycopg2, psycopg2.extras, logging

# ── Config ───────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://meems_user:password@localhost:5432/meems_db")
log = logging.getLogger("meems")

app = FastAPI(
    title="MEEMS API",
    description="Medical Equipment Management System — โรงพยาบาล SKHY",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # เปลี่ยนเป็น domain จริงเมื่อ deploy
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── DB Helper ────────────────────────────────────────────────────
def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()

def db_fetchall(sql: str, params=None):
    with psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

def db_fetchone(sql: str, params=None):
    with psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

def db_execute(sql: str, params=None):
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()
            try: return cur.fetchone()
            except: return None

# ── Pydantic Models ──────────────────────────────────────────────
class WorkOrderCreate(BaseModel):
    rec_no: Optional[str] = None
    equipment_id: Optional[str] = None
    dept: str
    ecri_name: Optional[str] = None
    reported_date: date
    received_by: Optional[str] = None
    technician: Optional[str] = None
    symptom: Optional[str] = None
    fix_detail: Optional[str] = None
    work_type: Optional[str] = None
    pr_no: Optional[str] = None
    vendor_name: Optional[str] = None
    cost_service: float = 0
    parts_name: Optional[str] = None
    parts_cost: float = 0
    close_date: Optional[date] = None
    flag_send_company: bool = False
    flag_new_install: bool = False
    flag_service_contract: bool = False
    flag_decommission: bool = False
    flag_warranty: bool = False
    flag_wait_parts: bool = False
    flag_done_7d: bool = False
    flag_critical: bool = False
    flag_user_error: bool = False
    flag_overdue_7d: bool = False
    flag_overdue_30d: bool = False
    flag_repair_ext: bool = False
    flag_repair_center: bool = False
    flag_close_24h: bool = False
    flag_itris_r: bool = False

class WorkOrderUpdate(BaseModel):
    technician: Optional[str] = None
    fix_detail: Optional[str] = None
    close_date: Optional[date] = None
    cost_service: Optional[float] = None
    parts_name: Optional[str] = None
    parts_cost: Optional[float] = None
    flag_done_7d: Optional[bool] = None
    flag_close_24h: Optional[bool] = None
    flag_overdue_7d: Optional[bool] = None
    flag_wait_parts: Optional[bool] = None

class PMRecordCreate(BaseModel):
    equipment_id: Optional[str] = None
    dept: Optional[str] = None
    ecri_name: Optional[str] = None
    action_date: Optional[date] = None
    action_type: str = "PM"
    action_by: Optional[str] = None
    result: Optional[str] = None
    notes: Optional[str] = None

class RegistrationCreate(BaseModel):
    equipment_id: str
    ecri_name: str
    dept: str
    brand: Optional[str] = None
    model: Optional[str] = None
    serial_no: Optional[str] = None
    purchase_date: Optional[date] = None
    price: Optional[float] = None
    warranty_expire: Optional[date] = None
    ecri_risk: Optional[str] = None
    life_expectancy_yr: Optional[int] = None
    parent_child: Optional[str] = None
    owner: Optional[str] = None
    vendor: Optional[str] = None
    pm_status: Optional[str] = None
    asset_code: Optional[str] = None
    remarks: Optional[str] = None
    inventory_date: Optional[date] = None
    insp_no: Optional[str] = None
    insp_date: Optional[date] = None
    insp_by: Optional[str] = None
    insp_result: Optional[str] = None
    insp_note: Optional[str] = None
    insp_fail_reason: Optional[str] = None
    insp_checklist: Optional[list] = None
    insp_manual: Optional[str] = None
    insp_vendor_rep: Optional[str] = None
    insp_hosp_rep: Optional[str] = None
    created_by: Optional[str] = None

# ════════════════════════════════════════════════════════════════
# DASHBOARD
# ════════════════════════════════════════════════════════════════

@app.get("/api/dashboard/kpi")
def dashboard_kpi():
    """KPI ภาพรวม Dashboard"""
    row = db_fetchone("""
        SELECT
            (SELECT COUNT(*) FROM equipment WHERE decom_date IS NULL)               AS active_equipment,
            (SELECT COUNT(*) FROM equipment WHERE decom_date IS NOT NULL)            AS decom_equipment,
            (SELECT COUNT(*) FROM equipment WHERE ecri_risk='HIGH' AND decom_date IS NULL) AS high_risk,
            (SELECT COALESCE(SUM(price),0) FROM equipment)                          AS total_value,
            (SELECT COUNT(*) FROM work_orders
             WHERE EXTRACT(MONTH FROM reported_date)=EXTRACT(MONTH FROM NOW())
             AND   EXTRACT(YEAR  FROM reported_date)=EXTRACT(YEAR  FROM NOW()))     AS wo_this_month,
            (SELECT COUNT(*) FROM work_orders
             WHERE (flag_overdue_7d OR flag_overdue_30d) AND close_date IS NULL)    AS overdue_count,
            (SELECT COUNT(*) FROM work_orders WHERE flag_close_24h)                 AS close_24h_count,
            (SELECT COUNT(*) FROM work_orders WHERE flag_done_7d)                   AS done_7d_count,
            (SELECT COUNT(*) FROM pm_records)                                       AS pm_total,
            (SELECT COUNT(*) FROM pm_records WHERE UPPER(result) IN ('PASS','P'))   AS pm_passed
    """)
    return dict(row)

@app.get("/api/dashboard/overdue")
def dashboard_overdue():
    """งานค้างซ่อม"""
    rows = db_fetchall("""
        SELECT wo.id, wo.rec_no, wo.dept, wo.ecri_name, wo.reported_date,
               wo.technician, wo.equipment_id,
               CASE WHEN flag_overdue_30d THEN 30 ELSE 8 END AS overdue_days
        FROM work_orders wo
        WHERE (flag_overdue_7d OR flag_overdue_30d) AND close_date IS NULL
        ORDER BY overdue_days DESC, reported_date
        LIMIT 20
    """)
    return list(rows)

@app.get("/api/dashboard/recent-wo")
def dashboard_recent_wo():
    """งานซ่อมล่าสุด"""
    rows = db_fetchall("""
        SELECT id, rec_no, dept, equipment_id, ecri_name,
               symptom, technician, reported_date, close_date,
               flag_overdue_7d, flag_overdue_30d, flag_wait_parts
        FROM work_orders
        ORDER BY reported_date DESC, id DESC
        LIMIT 10
    """)
    return list(rows)

@app.get("/api/dashboard/pm-completion")
def dashboard_pm_completion():
    """PM completion รายแผนก"""
    rows = db_fetchall("""
        SELECT dept, source_month, total, passed, pct
        FROM v_pm_completion
        ORDER BY total DESC
        LIMIT 20
    """)
    return list(rows)

# ════════════════════════════════════════════════════════════════
# EQUIPMENT
# ════════════════════════════════════════════════════════════════

@app.get("/api/equipment")
def list_equipment(
    q: str = Query("", description="ค้นหา ID/ชื่อ/ยี่ห้อ"),
    dept: str = Query("", description="กรองแผนก"),
    risk: str = Query("", description="HIGH/MEDIUM/LOW"),
    status: str = Query("", description="active/decom"),
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    where = ["1=1"]
    params = []
    if q:
        where.append("(equipment_id ILIKE %s OR ecri_name ILIKE %s OR brand ILIKE %s OR model ILIKE %s)")
        params += [f"%{q}%"] * 4
    if dept:
        where.append("dept = %s"); params.append(dept)
    if risk:
        where.append("ecri_risk = %s"); params.append(risk)
    if status == "active":
        where.append("decom_date IS NULL")
    elif status == "decom":
        where.append("decom_date IS NOT NULL")

    sql = f"""
        SELECT equipment_id, dept, ecri_name, brand, model, serial_no,
               purchase_date, price, ecri_risk, life_expectancy_yr,
               pm_status, decom_date, inventory_date, warranty_expire,
               (decom_date IS NULL) AS is_active
        FROM equipment
        WHERE {' AND '.join(where)}
        ORDER BY dept, ecri_name
        LIMIT %s OFFSET %s
    """
    params += [limit, offset]

    count_sql = f"SELECT COUNT(*) AS total FROM equipment WHERE {' AND '.join(where)}"
    rows = db_fetchall(sql, params[:-2] + [limit, offset])
    count = db_fetchone(count_sql, params[:-2])
    return {"total": count["total"], "items": list(rows)}

@app.get("/api/equipment/{equipment_id}")
def get_equipment(equipment_id: str):
    """ดูข้อมูลเครื่องมือแพทย์ 1 ชิ้น"""
    row = db_fetchone(
        "SELECT *, (decom_date IS NULL) AS is_active FROM equipment WHERE equipment_id = %s",
        (equipment_id,)
    )
    if not row: raise HTTPException(404, "ไม่พบ Equipment ID นี้")
    return dict(row)

@app.get("/api/equipment/{equipment_id}/history")
def get_equipment_history(equipment_id: str):
    """ประวัติเครื่องมือแพทย์ทั้งหมด (PM + CAL + REPAIR)"""
    pm = db_fetchall(
        "SELECT action_date AS date, action_type AS type, action_by, result, notes FROM pm_records WHERE equipment_id=%s ORDER BY action_date DESC",
        (equipment_id,)
    )
    hist = db_fetchall(
        "SELECT work_date AS date, work_type AS type, symptom, fix_detail, cost_service, close_date FROM equipment_history WHERE equipment_id=%s ORDER BY work_date DESC",
        (equipment_id,)
    )
    wo = db_fetchall(
        "SELECT reported_date AS date, 'REPAIR' AS type, symptom, fix_detail, close_date, rec_no FROM work_orders WHERE equipment_id=%s ORDER BY reported_date DESC",
        (equipment_id,)
    )
    return {"pm_records": list(pm), "history": list(hist), "work_orders": list(wo)}

# ════════════════════════════════════════════════════════════════
# WORK ORDERS
# ════════════════════════════════════════════════════════════════

@app.get("/api/work-orders")
def list_work_orders(
    q: str = Query(""),
    dept: str = Query(""),
    status: str = Query(""),
    month: int = Query(0),
    technician: str = Query(""),
    limit: int = Query(100, le=500),
    offset: int = 0,
):
    where = ["1=1"]
    params = []
    if q:
        where.append("(rec_no ILIKE %s OR dept ILIKE %s OR ecri_name ILIKE %s OR symptom ILIKE %s)")
        params += [f"%{q}%"] * 4
    if dept:
        where.append("dept = %s"); params.append(dept)
    if technician:
        where.append("technician ILIKE %s"); params.append(f"%{technician}%")
    if month:
        where.append("EXTRACT(MONTH FROM reported_date) = %s"); params.append(month)
    if status == "ปิดงาน":
        where.append("close_date IS NOT NULL")
    elif status == "กำลังซ่อม":
        where.append("close_date IS NULL AND NOT flag_overdue_7d AND NOT flag_wait_parts")
    elif status == "รออะไหล่":
        where.append("flag_wait_parts = TRUE AND close_date IS NULL")
    elif status == "ค้างซ่อม":
        where.append("(flag_overdue_7d OR flag_overdue_30d) AND close_date IS NULL")

    sql = f"""
        SELECT id, rec_no, dept, equipment_id, ecri_name,
               symptom, technician, received_by,
               reported_date, close_date, source_month,
               flag_overdue_7d, flag_overdue_30d, flag_wait_parts,
               flag_critical, flag_user_error, flag_close_24h,
               flag_done_7d, flag_new_install, flag_decommission,
               CASE
                 WHEN close_date IS NOT NULL         THEN 'ปิดงาน'
                 WHEN flag_overdue_30d OR flag_overdue_7d THEN 'ค้างซ่อม'
                 WHEN flag_wait_parts                THEN 'รออะไหล่'
                 ELSE 'กำลังซ่อม'
               END AS status
        FROM work_orders
        WHERE {' AND '.join(where)}
        ORDER BY reported_date DESC, id DESC
        LIMIT %s OFFSET %s
    """
    params += [limit, offset]
    rows = db_fetchall(sql, params)
    count_sql = f"SELECT COUNT(*) AS total FROM work_orders WHERE {' AND '.join(where[:-0])}"
    count = db_fetchone(f"SELECT COUNT(*) AS total FROM work_orders WHERE {' AND '.join(where)}", params[:-2])
    return {"total": count["total"], "items": list(rows)}

@app.post("/api/work-orders", status_code=201)
def create_work_order(body: WorkOrderCreate):
    """สร้างใบแจ้งซ่อมใหม่"""
    row = db_execute("""
        INSERT INTO work_orders (
            rec_no, equipment_id, dept, ecri_name, reported_date,
            received_by, technician, symptom, work_type,
            pr_no, vendor_name, cost_service, parts_name, parts_cost, close_date,
            flag_send_company, flag_new_install, flag_service_contract,
            flag_decommission, flag_warranty, flag_wait_parts,
            flag_done_7d, flag_critical, flag_user_error,
            flag_overdue_7d, flag_overdue_30d, flag_repair_ext,
            flag_repair_center, flag_close_24h, flag_itris_r
        ) VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
        ) RETURNING id
    """, (
        body.rec_no, body.equipment_id, body.dept, body.ecri_name, body.reported_date,
        body.received_by, body.technician, body.symptom, body.work_type,
        body.pr_no, body.vendor_name, body.cost_service, body.parts_name, body.parts_cost, body.close_date,
        body.flag_send_company, body.flag_new_install, body.flag_service_contract,
        body.flag_decommission, body.flag_warranty, body.flag_wait_parts,
        body.flag_done_7d, body.flag_critical, body.flag_user_error,
        body.flag_overdue_7d, body.flag_overdue_30d, body.flag_repair_ext,
        body.flag_repair_center, body.flag_close_24h, body.flag_itris_r,
    ))
    return {"id": row[0], "message": "บันทึกใบแจ้งซ่อมสำเร็จ"}

@app.patch("/api/work-orders/{wo_id}")
def update_work_order(wo_id: int, body: WorkOrderUpdate):
    """อัปเดตสถานะงานซ่อม"""
    fields, vals = [], []
    for field, val in body.dict(exclude_none=True).items():
        fields.append(f"{field}=%s"); vals.append(val)
    if not fields: raise HTTPException(400, "ไม่มีข้อมูลที่จะอัปเดต")
    vals.append(wo_id)
    db_execute(f"UPDATE work_orders SET {', '.join(fields)}, updated_at=NOW() WHERE id=%s", vals)
    return {"message": "อัปเดตสำเร็จ"}

# ════════════════════════════════════════════════════════════════
# PM & CAL
# ════════════════════════════════════════════════════════════════

@app.get("/api/pm")
def list_pm(
    dept: str = Query(""),
    month_name: str = Query(""),
    result: str = Query(""),
    action_by: str = Query(""),
    limit: int = Query(100, le=500),
    offset: int = 0,
):
    where = ["1=1"]
    params = []
    if dept:
        where.append("dept=%s"); params.append(dept)
    if month_name:
        where.append("source_month=%s"); params.append(month_name)
    if result:
        where.append("UPPER(result)=%s"); params.append(result.upper())
    if action_by:
        where.append("action_by ILIKE %s"); params.append(f"%{action_by}%")

    rows = db_fetchall(
        f"SELECT * FROM pm_records WHERE {' AND '.join(where)} ORDER BY action_date DESC NULLS LAST LIMIT %s OFFSET %s",
        params + [limit, offset]
    )
    count = db_fetchone(f"SELECT COUNT(*) AS total FROM pm_records WHERE {' AND '.join(where)}", params)
    return {"total": count["total"], "items": list(rows)}

@app.post("/api/pm", status_code=201)
def create_pm(body: PMRecordCreate):
    """บันทึกผล PM"""
    row = db_execute("""
        INSERT INTO pm_records (equipment_id, dept, ecri_name, action_date, action_type, action_by, result, notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
    """, (body.equipment_id, body.dept, body.ecri_name, body.action_date,
          body.action_type, body.action_by, body.result, body.notes))
    return {"id": row[0], "message": "บันทึก PM สำเร็จ"}

# ════════════════════════════════════════════════════════════════
# REGISTRATION (ลงทะเบียนเครื่องใหม่)
# ════════════════════════════════════════════════════════════════

@app.post("/api/registrations", status_code=201)
def create_registration(body: RegistrationCreate):
    """ลงทะเบียนเครื่องมือแพทย์ใหม่ + บันทึกลง equipment"""
    import json
    # บันทึก registration
    db_execute("""
        INSERT INTO registrations (
            equipment_id, ecri_name, dept, brand, model, serial_no,
            purchase_date, price, warranty_expire, ecri_risk, life_expectancy_yr,
            parent_child, owner, vendor, pm_status, asset_code, remarks, inventory_date,
            insp_no, insp_date, insp_by, insp_result, insp_note,
            insp_fail_reason, insp_checklist, insp_manual,
            insp_vendor_rep, insp_hosp_rep, created_by
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                  %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (equipment_id) DO UPDATE SET
            insp_result=EXCLUDED.insp_result, insp_date=EXCLUDED.insp_date
    """, (
        body.equipment_id, body.ecri_name, body.dept, body.brand, body.model, body.serial_no,
        body.purchase_date, body.price, body.warranty_expire, body.ecri_risk, body.life_expectancy_yr,
        body.parent_child, body.owner, body.vendor, body.pm_status, body.asset_code,
        body.remarks, body.inventory_date,
        body.insp_no, body.insp_date, body.insp_by, body.insp_result, body.insp_note,
        body.insp_fail_reason,
        json.dumps(body.insp_checklist) if body.insp_checklist else None,
        body.insp_manual, body.insp_vendor_rep, body.insp_hosp_rep, body.created_by,
    ))
    # บันทึกลง equipment ด้วย
    db_execute("""
        INSERT INTO equipment (
            equipment_id, dept, ecri_name, brand, model, serial_no,
            purchase_date, warranty_expire, price, ecri_risk, life_expectancy_yr,
            parent_child, owner, vendor, pm_status, asset_code, remarks, inventory_date
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (equipment_id) DO NOTHING
    """, (
        body.equipment_id, body.dept, body.ecri_name, body.brand, body.model, body.serial_no,
        body.purchase_date, body.warranty_expire, body.price, body.ecri_risk, body.life_expectancy_yr,
        body.parent_child, body.owner, body.vendor, body.pm_status, body.asset_code,
        body.remarks, body.inventory_date,
    ))
    return {"equipment_id": body.equipment_id, "message": "ลงทะเบียนสำเร็จ"}

@app.get("/api/registrations")
def list_registrations(limit: int = 50, offset: int = 0):
    rows = db_fetchall(
        "SELECT * FROM registrations ORDER BY created_at DESC LIMIT %s OFFSET %s",
        (limit, offset)
    )
    return list(rows)

# ════════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ════════════════════════════════════════════════════════════════

@app.get("/api/notifications")
def list_notifications(unread_only: bool = False):
    where = "WHERE is_read=FALSE" if unread_only else ""
    rows = db_fetchall(f"SELECT * FROM notifications {where} ORDER BY created_at DESC LIMIT 50")
    return list(rows)

@app.patch("/api/notifications/{noti_id}/read")
def mark_read(noti_id: int):
    db_execute("UPDATE notifications SET is_read=TRUE WHERE id=%s", (noti_id,))
    return {"message": "อ่านแล้ว"}

@app.patch("/api/notifications/read-all")
def mark_all_read():
    db_execute("UPDATE notifications SET is_read=TRUE WHERE is_read=FALSE")
    return {"message": "อ่านทั้งหมดแล้ว"}

# ════════════════════════════════════════════════════════════════
# REPORTS
# ════════════════════════════════════════════════════════════════

@app.get("/api/reports/wo-summary")
def report_wo_summary(month: int = 0, year: int = 0):
    """สรุปงานซ่อมรายเดือน"""
    where = "1=1"
    params = []
    if month: where += " AND EXTRACT(MONTH FROM reported_date)=%s"; params.append(month)
    if year:  where += " AND EXTRACT(YEAR  FROM reported_date)=%s"; params.append(year)
    rows = db_fetchall(f"""
        SELECT dept,
            COUNT(*) total,
            COUNT(*) FILTER (WHERE close_date IS NOT NULL) closed,
            COUNT(*) FILTER (WHERE flag_overdue_7d OR flag_overdue_30d) overdue,
            COUNT(*) FILTER (WHERE flag_user_error) user_error,
            COUNT(*) FILTER (WHERE flag_critical) critical,
            COUNT(*) FILTER (WHERE flag_close_24h) close_24h,
            COUNT(*) FILTER (WHERE flag_done_7d) done_7d,
            COALESCE(SUM(cost_service+parts_cost),0) total_cost
        FROM work_orders WHERE {where}
        GROUP BY dept ORDER BY total DESC
    """, params)
    return list(rows)

@app.get("/api/reports/pm-summary")
def report_pm_summary():
    """สรุป PM completion"""
    rows = db_fetchall("SELECT * FROM v_pm_completion ORDER BY dept, source_month")
    return list(rows)

@app.get("/api/reports/inventory-summary")
def report_inventory_summary():
    """สรุป Inventory"""
    row = db_fetchone("""
        SELECT
            COUNT(*) total,
            COUNT(*) FILTER (WHERE decom_date IS NULL) active,
            COUNT(*) FILTER (WHERE decom_date IS NOT NULL) decom,
            COUNT(*) FILTER (WHERE ecri_risk='HIGH' AND decom_date IS NULL) high_risk,
            COUNT(*) FILTER (WHERE ecri_risk='MEDIUM' AND decom_date IS NULL) medium_risk,
            COUNT(*) FILTER (WHERE ecri_risk='LOW' AND decom_date IS NULL) low_risk,
            COALESCE(SUM(price),0) total_value
        FROM equipment
    """)
    by_dept = db_fetchall("""
        SELECT dept,
            COUNT(*) total,
            COUNT(*) FILTER (WHERE decom_date IS NULL) active,
            COUNT(*) FILTER (WHERE ecri_risk='HIGH') high_risk,
            COALESCE(SUM(price),0) total_value
        FROM equipment GROUP BY dept ORDER BY total DESC
    """)
    return {"summary": dict(row), "by_dept": list(by_dept)}

# ── Health check ─────────────────────────────────────────────────
@app.get("/")
def root():
    return {"app": "MEEMS API", "version": "1.0.0", "status": "running"}

@app.get("/health")
def health():
    try:
        db_fetchone("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(503, f"Database error: {e}")

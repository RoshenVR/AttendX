from flask import Flask, request, send_file, redirect, url_for, render_template, session, flash, g
import random, time, qrcode, os, csv, io, json, sys
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

app = Flask(__name__, template_folder=resource_path('templates'), static_folder=resource_path('static'))
app.secret_key = os.environ.get("SECRET_KEY", "secret_key_change_this_later")

@app.context_processor
def inject_now():
    return {'now': datetime.now().strftime("%d %b %Y, %I:%M %p")}

# ---------------- CONFIG ----------------
QR_REFRESH_TIME = 15          # seconds
TOKEN_VALID_TIME = 40         # seconds

# Supabase Setup
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("WARNING: Supabase credentials not found. Please set SUPABASE_URL and SUPABASE_KEY environment variables.")
    # For CI/Build process where env vars might be missing, we can default to None, 
    # but app will fail on DB calls.
    supabase: Client = None
else:
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Error connecting to Supabase: {e}")
        supabase = None

SERVER_IP = "127.0.0.1" # Default fallback
try:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('10.255.255.255', 1))
    SERVER_IP = s.getsockname()[0]
    s.close()
except:
    pass

# ---------------- HELPERS ----------------
def generate_token():
    return str(random.randint(100000, 999999))

def generate_qr(token):
    # Dynamic URL: Use current request host (works on Render and Local Automatically)
    # If not in request context, fallback to env or local IP
    server_url = os.environ.get('RENDER_EXTERNAL_URL')
    try:
        from flask import request
        if request:
            server_url = request.host_url.rstrip('/')
    except:
        pass
    
    if not server_url:
        server_url = f"http://{SERVER_IP}:{os.environ.get('PORT', 5000)}"
    
    url = f"{server_url}/student?token={token}"
    img = qrcode.make(url)
    static_dir = resource_path("static")
    os.makedirs(static_dir, exist_ok=True)
    img.save(os.path.join(static_dir, "qr.png"))

def cleanup_tokens():
    if not supabase: return
    # Delete expired tokens
    try:
        # Supabase expects ISO formatted string for timestamps usually
        now_iso = datetime.now().isoformat()
        supabase.table("valid_tokens").delete().lt("expires_at", now_iso).execute()
    except Exception as e:
        print(f"Cleanup error: {e}")

def login_required(role=None):
    if 'user' not in session:
        return False
    if role and session.get('role') != role:
        return False
    return True

# ---------------- AUTH ROUTES ----------------
@app.route("/", methods=["GET"])
def home():
    if 'user' in session:
        role = session.get('role')
        if role == 'teacher':
            return redirect(url_for('teacher_dashboard'))
        elif role == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('student_dashboard'))
    return redirect(url_for('login'))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "").strip() 

        if not supabase:
            flash("Database connection error.", "error")
            return render_template("login.html")

        try:
            response = supabase.table("users").select("*").eq("sid", username).execute()
            user = response.data[0] if response.data else None

            if user and user['password'] == password:
                if user['role'] != role:
                    flash(f"Invalid role. This account is not a {role}.", "error")
                    return redirect(url_for('login'))
                
                # Check Status for Students
                if role == 'student':
                    status = user.get('status', 'approved') # Default to approved to prevent lockout if column missing
                    if status == 'pending':
                        flash("Your account is awaiting approval.", "warning")
                        return redirect(url_for('login'))
                    elif status == 'rejected':
                        flash("Your registration was rejected. Contact admin.", "error")
                        return redirect(url_for('login'))

                session['user'] = user['sid']
                session['role'] = user['role']
                session['name'] = user['name']
                
                flash(f"Welcome, {session['name']}!", "success")
                
                if role == 'teacher':
                    return redirect(url_for('teacher_dashboard'))
                elif role == 'admin':
                    return redirect(url_for('admin_dashboard'))
                else:
                    if 'scanned_token' in session:
                        t = session.pop('scanned_token')
                        return redirect(url_for('student', token=t))
                    return redirect(url_for('student_dashboard'))

            else:
                flash("Invalid username or password", "error")
                return redirect(url_for('login'))
        except Exception as e:
            print(f"Login Error: {e}")
            flash("An error occurred during login.", "error")
            return redirect(url_for('login'))

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        sid = request.form.get("sid")
        password = request.form.get("password")
        department = request.form.get("department", "General")
        semester = request.form.get("semester", "1")
        section = request.form.get("section", "A")

        if not supabase:
             flash("Database connection error.", "error")
             return render_template("register.html")

        try:
            supabase.table("users").insert({
                "sid": sid, 
                "name": name, 
                "password": password, 
                "role": "student",
                "status": "pending",
                "department": department,
                "semester": semester,
                "section": section
            }).execute()
            flash("Registration successful! Please wait for account approval.", "success")
            return redirect(url_for('login'))
        except Exception as e:
            # Check for duplicate key error (23505 is PG error code for unique violation, 
            # but supabase-py might raise a specific exception)
            print(f"Register Error: {e}")
            flash("Student ID already registered or error occurred.", "error")
            return redirect(url_for('register'))

    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('login'))

# ---------------- ADMIN DASHBOARD ----------------
@app.route("/admin_dashboard")
def admin_dashboard():
    if not login_required('admin'):
        return redirect(url_for('login'))
    
    if not supabase: return "DB Error", 500
    
    try:
        # Statistics using count='exact' and head=True to avoid fetching data
        total_teachers = supabase.table("users").select("*", count="exact", head=True).eq("role", "teacher").execute().count
        total_students = supabase.table("users").select("*", count="exact", head=True).eq("role", "student").execute().count
        total_sessions = supabase.table("attendance_sessions").select("*", count="exact", head=True).execute().count
        active_sessions = supabase.table("attendance_sessions").select("*", count="exact", head=True).eq("active", True).execute().count
        
        # Pending Approvals
        pending_students = supabase.table("users").select("*").eq("role", "student").eq("status", "pending").execute().data

    except Exception as e:
        print(f"Stats Error: {e}")
        total_teachers = total_students = total_sessions = active_sessions = 0
        pending_students = []
    
    return render_template("admin_dashboard.html", 
                           total_teachers=total_teachers, 
                           total_students=total_students,
                           total_sessions=total_sessions,
                           active_sessions=active_sessions,
                           pending_students=pending_students)

@app.route("/admin/add_teacher", methods=["POST"])
def add_teacher():
    if not login_required('admin'):
        return redirect(url_for('login'))
        
    name = request.form.get("name")
    sid = request.form.get("sid")
    password = request.form.get("password")
    
    if not supabase: return "DB Error", 500

    try:
        supabase.table("users").insert({
            "sid": sid, 
            "name": name, 
            "password": password, 
            "role": "teacher"
        }).execute()
        flash("Teacher added successfully!", "success")
    except Exception:
        flash("User ID already exists.", "error")
        
    return redirect(url_for('admin_dashboard'))

@app.route("/user/approve/<sid>")
def approve_user(sid):
    if not login_required('admin') and not login_required('teacher'):
        return redirect(url_for('login'))
    
    if not supabase: return "DB Error", 500
    
    try:
        supabase.table("users").update({"status": "approved"}).eq("sid", sid).execute()
        flash(f"User {sid} approved successfully.", "success")
    except Exception as e:
        flash(f"Error approving user: {e}", "error")
        
    # Redirect back to referring page or dashboard
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route("/user/reject/<sid>")
def reject_user(sid):
    if not login_required('admin') and not login_required('teacher'):
        return redirect(url_for('login'))
    
    if not supabase: return "DB Error", 500
    
    try:
        supabase.table("users").update({"status": "rejected"}).eq("sid", sid).execute()
        flash(f"User {sid} rejected.", "warning")
    except Exception as e:
        flash(f"Error rejecting user: {e}", "error")
        
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route("/admin/users")
def admin_users():
    if not login_required('admin'):
        return redirect(url_for('login'))
        
    if not supabase: return "DB Error", 500

    teachers = supabase.table("users").select("*").eq("role", "teacher").execute().data
    students = supabase.table("users").select("*").eq("role", "student").execute().data
    
    return render_template("admin_users.html", teachers=teachers, students=students)

@app.route("/admin/delete_user/<sid>", methods=["POST"])
def delete_user(sid):
    if not login_required('admin'):
        return redirect(url_for('login'))
        
    if sid == 'admin': # Prevent deleting default admin
        flash("Cannot delete the main admin account.", "error")
        return redirect(url_for('admin_users'))

    if not supabase: return "DB Error", 500

    try:
        supabase.table("users").delete().eq("sid", sid).execute()
        flash(f"User {sid} deleted.", "success")
    except Exception as e:
        flash(f"Error deleting user: {e}", "error")

    return redirect(url_for('admin_users'))

# ---------------- ADMIN SUBJECT MANAGEMENT ----------------
@app.route("/admin_subjects", methods=["GET", "POST"])
def admin_subjects():
    if not login_required('admin'):
        return redirect(url_for('login'))
    
    if not supabase: return "DB Error", 500
    
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "add":
            subject_name = request.form.get("subject_name", "").strip()
            class_name = request.form.get("class_name", "").strip()
            department = request.form.get("department", "General").strip()
            semester = request.form.get("semester", "1").strip()
            section = request.form.get("section", "A").strip()
            
            if subject_name and class_name:
                try:
                    supabase.table("subjects").insert({
                        "subject_name": subject_name,
                        "class_name": class_name,
                        "department": department,
                        "semester": semester,
                        "section": section,
                        "added_by": session['user']
                    }).execute()
                    flash(f"Subject '{subject_name}' added successfully!", "success")
                except Exception as e:
                    flash(f"Error adding subject: {e}", "error")
            else:
                flash("Subject name and class are required.", "error")
        
        return redirect(url_for('admin_subjects'))
    
    # GET - List all subjects with Admin Name
    # Using Supabase foreign key select: users!added_by(name)
    try:
        response = supabase.table("subjects").select("*, users!subjects_added_by_fkey(name)").order("created_at", desc=True).execute()
        subjects = response.data
        
        # Flatten structure for template: users['name'] -> admin_name
        # Note: The FK name `subjects_added_by_fkey` assumes the default constraint name. 
        # If it fails, we fall back to manual join or simpler query.
        # Given we just created schema, it might be auto-named user_id or similar.
        # Let's try to just select users(name) and logic handles it.
        # Actually safer to just fetch users names separately or handle logic in jinja if passed as dict.
        # But let's try to map it.
        
        # Simpler approach: Fetch users and map manually to ensure robustness without relying on exact FK names
        all_users = {u['sid']: u['name'] for u in supabase.table("users").select("sid, name").execute().data}
        for s in subjects:
            s['admin_name'] = all_users.get(s['added_by'], 'Unknown')
            
    except Exception as e:
        print(f"Subject List Error: {e}")
        subjects = []
    
    return render_template("admin_subjects.html", subjects=subjects)

@app.route("/admin/edit_subject/<int:subject_id>", methods=["POST"])
def edit_subject(subject_id):
    if not login_required('admin'):
        return redirect(url_for('login'))
    
    subject_name = request.form.get("subject_name", "").strip()
    class_name = request.form.get("class_name", "").strip()
    department = request.form.get("department", "General").strip()
    semester = request.form.get("semester", "1").strip()
    section = request.form.get("section", "A").strip()
    
    if subject_name and class_name:
        if not supabase: return "DB Error", 500
        try:
            supabase.table("subjects").update({
                "subject_name": subject_name, 
                "class_name": class_name,
                "department": department,
                "semester": semester,
                "section": section
            }).eq("subject_id", subject_id).execute()
            flash("Subject updated successfully!", "success")
        except Exception as e:
            flash(f"Error updating subject: {e}", "error")
    else:
        flash("Subject name and class are required.", "error")
    
    return redirect(url_for('admin_subjects'))

@app.route("/admin/delete_subject/<int:subject_id>", methods=["POST"])
def delete_subject(subject_id):
    if not login_required('admin'):
        return redirect(url_for('login'))
    
    if not supabase: return "DB Error", 500
    
    # Check if subject is used in any sessions
    try:
        count = supabase.table("attendance_sessions").select("*", count="exact", head=True).eq("subject_id", subject_id).execute().count
        
        if count > 0:
            flash(f"Cannot delete subject: {count} attendance sessions are linked to it.", "error")
        else:
            supabase.table("subjects").delete().eq("subject_id", subject_id).execute()
            flash("Subject deleted successfully!", "success")
    except Exception as e:
        flash(f"Error deleting subject: {e}", "error")
    
    return redirect(url_for('admin_subjects'))


@app.route("/admin/reports")
def admin_reports():
    if not login_required('admin'):
        return redirect(url_for('login'))

    if not supabase: return "DB Error", 500
    # SQL: SELECT a.*, u.role FROM ...
    # Supabase: we can fetch all records and users, then join.
    try:
        records = supabase.table("attendance_records").select("*").order("record_id", desc=True).execute().data
        all_users = {u['sid']: u for u in supabase.table("users").select("sid, role").execute().data}
        
        for r in records:
            user = all_users.get(r['sid'])
            r['role'] = user['role'] if user else 'Unknown'
            
    except Exception as e:
        print(f"Reports Error: {e}")
        records = []

    return render_template("admin_reports.html", records=records)

# ---------------- TEACHER DASHBOARD ----------------
@app.route("/teacher_dashboard")
def teacher_dashboard():
    if not login_required('teacher'):
        return redirect(url_for('login'))
    
    if not supabase: return "DB Error", 500

    try:
        # Get active session
        response = supabase.table("attendance_sessions").select("*").eq("active", True).execute()
        active_session = response.data[0] if response.data else None
        
        count = 0
        if active_session:
            count = supabase.table("attendance_records").select("*", count="exact", head=True).eq("session_id", active_session['session_id']).execute().count

        subjects = supabase.table("subjects").select("*").order("subject_name").execute().data
        
        # Pending Approvals (Teachers can also approve)
        pending_students = supabase.table("users").select("*").eq("role", "student").eq("status", "pending").execute().data
        
    except Exception as e:
        print(f"Teacher Dashboard Error: {e}")
        active_session = None
        count = 0
        subjects = []
        pending_students = []

    return render_template("teacher_dashboard.html", active_session=active_session, attendance_count=count, subjects=subjects, pending_students=pending_students)

# ---------------- TEACHER ATTENDANCE ACTIONS ----------------
@app.route("/teacher", methods=["GET", "POST"])
def teacher():
    if not login_required('teacher'):
        return redirect(url_for('login'))
    
    if not supabase: return "DB Error", 500

    # Handle Actions
    if request.method == "POST":
        action = request.form.get("action")
        if action == "start":
            subject_id = request.form.get("subject_id")
            session_date = request.form.get("session_date")
            session_name = request.form.get("session_name", "").strip()
            
            if subject_id and session_date:
                try:
                    # Get subject details
                    sub_resp = supabase.table("subjects").select("*").eq("subject_id", subject_id).execute()
                    subject = sub_resp.data[0] if sub_resp.data else None
                    
                    if subject:
                        # Deactivate all others first (Update active=False)
                        # We have to fetch active ones first? Or just update all?
                        # Supabase update allows filtering.
                        # However, update without 'where' on all rows might be restricted by RLS (if enabled). Assuming no RLS for now or using service role.
                        # Safe way: Update all active=True to False
                        supabase.table("attendance_sessions").update({"active": False}).eq("active", True).execute()
                        
                        # Insert new
                        supabase.table("attendance_sessions").insert({
                            "teacher_id": session['user'],
                            "subject_id": subject_id,
                            "subject": subject['subject_name'],
                            "session_date": session_date,
                            "session_name": session_name,
                            "active": True,
                            "start_time": datetime.now().isoformat()
                        }).execute()
                        
                        flash(f"Attendance started for {subject['subject_name']}", "success")
                    else:
                        flash("Selected subject not found", "error")
                except Exception as e:
                     flash(f"Error starting session: {e}", "error")

            else:
                flash("Please select a subject and date", "error")
        elif action == "stop":
            try:
                # 1. Get the currently active session to know which subject we are processing
                active_resp = supabase.table("attendance_sessions").select("*").eq("active", True).execute()
                active_session = active_resp.data[0] if active_resp.data else None
                
                if active_session:
                    # Automatically mark absent students
                    sub_id = active_session['subject_id']
                    sess_id = active_session['session_id']
                    
                    # Fetch subject details to get dept/sem/sec
                    sub_info = supabase.table("subjects").select("*").eq("subject_id", sub_id).execute().data
                    if sub_info:
                        sub = sub_info[0]
                        dept = sub.get('department')
                        sem = sub.get('semester')
                        sec = sub.get('section')
                        
                        # Find all enrolled students for this subject
                        enrolled = supabase.table("users").select("sid, name").eq("role", "student").eq("department", dept).eq("semester", sem).eq("section", sec).execute().data
                        
                        # Find students already marked present
                        present = supabase.table("attendance_records").select("sid").eq("session_id", sess_id).execute().data
                        present_sids = [p['sid'] for p in present]
                        
                        # Identify absentees
                        absentees = [s for s in enrolled if s['sid'] not in present_sids]
                        
                        # Insert absentee records
                        for student in absentees:
                            # Use the session_date if available, else current date
                            rec_date = active_session.get('session_date')
                            if not rec_date: rec_date = datetime.now().strftime("%d-%m-%Y")
                            
                            supabase.table("attendance_records").insert({
                                "session_id": sess_id,
                                "sid": student['sid'],
                                "name": student['name'],
                                "subject_id": sub_id,
                                "subject": active_session['subject'],
                                "date": rec_date,
                                "time": datetime.now().strftime("%H:%M:%S"),
                                "status": "absent",
                                "marked_type": "auto"
                            }).execute()

                supabase.table("attendance_sessions").update({"active": False}).eq("active", True).execute()
                # 3. Cleanup valid_tokens (Safe wrap to prevent crash on permission error)
                try:
                    supabase.table("valid_tokens").delete().neq("token", "dummy").execute() 
                    supabase.table("valid_tokens").delete().gt("expires_at", "2000-01-01").execute() 
                except Exception as te:
                    print(f"Token Cleanup Permission Error: {te}")
                
                flash("Attendance stopped and missing students marked absent.", "success")
                return redirect(url_for('teacher_dashboard'))
            except Exception as e:
                flash(f"Error stopping session: {e}", "error")
        
        return redirect(url_for("teacher"))

    # GET Logic (QR Display)
    try:
        response = supabase.table("attendance_sessions").select("*").eq("active", True).execute()
        active_session = response.data[0] if response.data else None
        
        subjects = supabase.table("subjects").select("*").order("subject_name").execute().data
        
        if active_session:
            cleanup_tokens()
            
            # 2. Update QR Token logic (Safe wrap to prevent crash on permission error)
            try:
                # Check latest token
                tk_resp = supabase.table("valid_tokens").select("created_at").order("created_at", desc=True).limit(1).execute()
                row = tk_resp.data[0] if tk_resp.data else None
                
                generate_new = False
                if not row:
                    generate_new = True
                else:
                    try:
                        # Parse timestamp (Supabase is ISO 8601)
                        last_created = datetime.fromisoformat(row['created_at'].replace('Z', '+00:00')) 
                        if (datetime.now(last_created.tzinfo) - last_created).total_seconds() > QR_REFRESH_TIME:
                            generate_new = True
                    except Exception as e:
                        print(f"Date parse error: {e}")
                        generate_new = True

                if generate_new:
                    token = generate_token()
                    now_iso = datetime.now().isoformat()
                    expires_iso = datetime.fromtimestamp(time.time() + TOKEN_VALID_TIME).isoformat()
                    
                    supabase.table("valid_tokens").insert({
                        "token": token,
                        "created_at": now_iso,
                        "expires_at": expires_iso
                    }).execute()
                    generate_qr(token)
            except Exception as te:
                print(f"Token Refresh Permission Error: {te}")
                # We still try to generate a fallback QR if no token exists, 
                # but it might fail validation later if not in DB.
                # For now, just logging it so the page doesn't crash.
                flash("Warning: Token permission error. Attendance might not be markable.", "warning")
    except Exception as e:
        print(f"Teacher Page Error: {e}")
        # Note: Do not reset active_session to None here if it was already fetched on line 590
        # unless line 590 itself failed. 
        if not active_session: active_session = None
        subjects = []
        
    # Extra data for manual tracking if session is active
    enrolled_students = []
    present_sids = []
    manual_present_sids = []
    absent_sids = []
    
    if active_session:
        try:
            sub_id = active_session['subject_id']
            # Get sub details mapping to department, semester, section
            sub_details = next((s for s in subjects if s['subject_id'] == sub_id), None)
            
            if sub_details:
                # Fetch eligible students
                enrolled_students = supabase.table("users").select("sid, name").eq("role", "student")\
                    .eq("department", sub_details.get("department"))\
                    .eq("semester", sub_details.get("semester"))\
                    .eq("section", sub_details.get("section")).execute().data
                    
            # Fetch existing records
            records = supabase.table("attendance_records").select("sid, status, marked_type").eq("session_id", active_session['session_id']).execute().data
            
            for r in records:
                if r.get('status', 'present') == 'present':
                    present_sids.append(r['sid'])
                    if r.get('marked_type') == 'manual':
                        manual_present_sids.append(r['sid'])
                elif r.get('status') == 'absent':
                    absent_sids.append(r['sid'])
                    
        except Exception as e:
            print(f"Error fetching manual tracking data: {e}")
    
    return render_template("teacher.html", 
                           active=bool(active_session), 
                           current_subject=active_session['subject'] if active_session else "", 
                           session_id=active_session['session_id'] if active_session else 0,
                           session_name=active_session.get('session_name', '') if active_session else "",
                           current_date=active_session.get('session_date', '') if active_session else "",
                           subjects=subjects,
                           enrolled_students=enrolled_students,
                           present_sids=present_sids,
                           manual_present_sids=manual_present_sids,
                           absent_sids=absent_sids)

@app.route("/teacher/manual_mark", methods=["POST"])
def teacher_manual_mark():
    if not login_required('teacher'):
        return redirect(url_for('login'))
        
    student_sid = request.form.get("student_sid")
    student_name = request.form.get("student_name")
    mark_status = request.form.get("mark_status")
    
    if not student_sid or not mark_status:
        flash("Invalid request.", "error")
        return redirect(url_for('teacher'))
        
    if not supabase: return "DB Error", 500
    
    try:
        # Verify active session
        resp = supabase.table("attendance_sessions").select("*").eq("active", True).execute()
        active_session = resp.data[0] if resp.data else None
        
        if not active_session:
            flash("No active session to mark attendance for.", "error")
            return redirect(url_for('teacher'))
            
        sess_id = active_session['session_id']
        sub_id = active_session['subject_id']
        teacher_id = session['user']
        
        # Check if record already exists
        exist_check = supabase.table("attendance_records").select("*").eq("session_id", sess_id).eq("sid", student_sid).execute()
        
        if mark_status == 'clear':
            if exist_check.data:
                supabase.table("attendance_records").delete().eq("session_id", sess_id).eq("sid", student_sid).execute()
                flash(f"Cleared record for {student_name}.", "success")
        else:
            rec_date = active_session.get('session_date')
            if not rec_date: rec_date = datetime.now().strftime("%d-%m-%Y")
                
            if exist_check.data:
                # Update existing record
                supabase.table("attendance_records").update({
                    "status": mark_status,
                    "marked_type": "manual",
                    "marked_by": teacher_id
                }).eq("session_id", sess_id).eq("sid", student_sid).execute()
            else:
                # Insert new record
                supabase.table("attendance_records").insert({
                    "session_id": sess_id,
                    "sid": student_sid,
                    "name": student_name,
                    "subject_id": sub_id,
                    "subject": active_session['subject'],
                    "date": rec_date,
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "status": mark_status,
                    "marked_type": "manual",
                    "marked_by": teacher_id
                }).execute()
                
            flash(f"Marked {student_name} as {mark_status}.", "success")
            
    except Exception as e:
        print(f"Manual Mark Error: {e}")
        flash("An error occurred while marking manually.", "error")
        
    return redirect(url_for('teacher'))

@app.route("/attendance")
def view_attendance():
    if not login_required('teacher'):
        return redirect(url_for('login'))
    
    if not supabase: return "DB Error", 500
    
    subject_filter = request.args.get('subject_id', None)
    
    try:
        subjects = supabase.table("subjects").select("*").order("subject_name").execute().data
        
        query = supabase.table("attendance_records").select("*").order("record_id", desc=True)
        if subject_filter:
            query = query.eq("subject_id", subject_filter)
        
        records = query.execute().data
    except Exception as e:
        print(f"View Attendance Error: {e}")
        records = []
        subjects = []
    
    return render_template("attendance.html", attendance=records, total=len(records), 
                          subjects=subjects, selected_subject=subject_filter)

# ---------------- PROFESSIONAL ATTENDANCE VIEW ----------------
@app.route("/attendance/view")
def attendance_view():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    if not supabase: return "DB Error", 500
    
    role = session.get('role')
    user_id = session.get('user')
    
    # Get filter parameters
    subject_id = request.args.get('subject_id', '')
    from_date = request.args.get('from_date', '')
    to_date = request.args.get('to_date', '')
    search = request.args.get('search', '').strip()
    
    try:
        # Get subjects based on role
        if role == 'student':
            subjects = []
        else:
            subjects = supabase.table("subjects").select("*").order("subject_name").execute().data
        
        # Build query with role-based filtering
        query = supabase.table("attendance_records").select("*")
        
        # Role-based data restriction
        if role == 'student':
            query = query.eq("sid", user_id)
        # For teacher and admin, no restriction on user_id (they can see all students)
        
        # Apply filters
        if subject_id:
            query = query.eq("subject_id", subject_id)
        
        if from_date:
            query = query.gte("date", from_date)
        
        if to_date:
            query = query.lte("date", to_date)
        
        if search and role != 'student':
            # Search by name (case-insensitive partial match)
            query = query.ilike("name", f"%{search}%")
        
        # Execute query
        records = query.order("date", desc=True).order("time", desc=True).execute().data
        
        # Calculate attendance summary per student
        student_summary = {}
        
        for record in records:
            sid = record['sid']
            subject_id_rec = record.get('subject_id')
            
            # Create unique key for student-subject combination
            key = f"{sid}_{subject_id_rec}" if subject_id_rec else sid
            
            if key not in student_summary:
                student_summary[key] = {
                    'sid': sid,
                    'name': record['name'],
                    'subject': record.get('subject', 'N/A'),
                    'subject_id': subject_id_rec,
                    'present': 0,
                    'total': 0,
                    'percentage': 0,
                    'badge_class': 'badge-red'
                }
            
            student_summary[key]['total'] += 1
            student_summary[key]['present'] += 1  # All records in attendance_records are "present"
        
        # Calculate percentages and badge classes
        for key in student_summary:
            summary = student_summary[key]
            if summary['total'] > 0:
                summary['percentage'] = round((summary['present'] / summary['total']) * 100, 2)
                
                # Assign badge class
                if summary['percentage'] >= 75:
                    summary['badge_class'] = 'badge-green'
                elif summary['percentage'] >= 60:
                    summary['badge_class'] = 'badge-yellow'
                else:
                    summary['badge_class'] = 'badge-red'
        
        # Convert to list for template
        summary_list = list(student_summary.values())
        
        # Sort by name
        summary_list.sort(key=lambda x: x['name'])
        
    except Exception as e:
        print(f"Attendance View Error: {e}")
        records = []
        subjects = []
        summary_list = []
    
    return render_template("attendance_view.html", 
                          attendance=records, 
                          summary=summary_list,
                          subjects=subjects,
                          selected_subject=subject_id,
                          from_date=from_date,
                          to_date=to_date,
                          search=search,
                          role=role)

@app.route("/export")
def export():
    if not login_required('teacher'):
        return redirect(url_for('login'))
        
    if not supabase: return "DB Error", 500
    
    try:
        records = supabase.table("attendance_records").select("*").order("record_id").execute().data
    except:
        records = []
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Session", "Name", "ID", "Subject", "Date", "Time"])
    for r in records:
        writer.writerow([r['session_id'], r['name'], r['sid'], r['subject'], r['date'], r['time']])

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype="text/csv",
        as_attachment=True,
        download_name="attendance.csv"
    )

# ---------------- STUDENT DASHBOARD ----------------
@app.route("/student_dashboard")
def student_dashboard():
    if not login_required('student'):
        return redirect(url_for('login'))
    
    if not supabase: return "DB Error", 500
    
    try:
        # Active Session
        resp = supabase.table("attendance_sessions").select("*").eq("active", True).execute()
        active_session = resp.data[0] if resp.data else None
        
        # History
        history = supabase.table("attendance_records").select("*").eq("sid", session['user']).order("record_id", desc=True).limit(10).execute().data
    except Exception as e:
        print(f"Student Dash Error: {e}")
        active_session = None
        history = []
    
    return render_template("student_dashboard.html", 
                           active=bool(active_session), 
                           subject=active_session['subject'] if active_session else "",
                           history=history)

@app.route("/student", methods=["GET", "POST"])
def student():
    token = request.args.get("token") or request.form.get("token")
    
    if 'user' not in session:
        session['scanned_token'] = token
        flash("Please login to mark attendance.", "error")
        return redirect(url_for('login'))

    if session['role'] != 'student':
        flash("Teachers cannot mark attendance.", "error")
        return redirect(url_for('teacher'))
    
    if not supabase: 
        flash("System error.", "error")
        return redirect(url_for('student_dashboard'))
    
    cleanup_tokens()
    
    try:
        resp = supabase.table("attendance_sessions").select("*").eq("active", True).execute()
        active_session = resp.data[0] if resp.data else None
        
        if not active_session:
            flash("Attendance is currently closed.", "error")
            return redirect(url_for('student_dashboard'))

        if request.method == "POST":
            sid = session['user']
            name = session['name']
            token_submitted = request.form.get("token")
            
            # Check duplicate
            dup_check = supabase.table("attendance_records").select("*").eq("session_id", active_session['session_id']).eq("sid", sid).execute()
            if dup_check.data:
                flash("You have already marked attendance for this session.", "error")
                return redirect(url_for('student_dashboard'))
            
            # Validate token (Safe wrap)
            token_valid = None
            try:
                token_resp = supabase.table("valid_tokens").select("*").eq("token", token_submitted).execute()
                token_valid = token_resp.data if token_resp.data else None
            except Exception as te:
                print(f"Token Validation Permission Error: {te}")
            
            if token_valid:
                supabase.table("attendance_records").insert({
                    "session_id": active_session['session_id'],
                    "sid": sid,
                    "name": name,
                    "subject_id": active_session['subject_id'],
                    "subject": active_session['subject'],
                    "date": datetime.now().strftime("%d-%m-%Y"),
                    "time": datetime.now().strftime("%H:%M:%S")
                }).execute()
                
                flash("Attendance marked successfully!", "success")
                return redirect(url_for('student_dashboard'))
            else:
                flash("Invalid or expired QR code. Please scan again.", "error")
                return redirect(url_for('student_dashboard'))

        # GET - Confirmation
        if token:
            token_valid = None
            try:
                token_resp = supabase.table("valid_tokens").select("*").eq("token", token).execute()
                token_valid = token_resp.data if token_resp.data else None
            except Exception as te:
                print(f"Token Confirmation Permission Error: {te}")

            if token_valid:
                return render_template("student.html", active=True, token=token, subject=active_session['subject'])
            else:
                flash("QR code expired or server permission error. Please scan again.", "error")
                return redirect(url_for('student_dashboard'))
    except Exception as e:
        print(f"Student Error: {e}")
        flash("An error occurred.", "error")
        return redirect(url_for('student_dashboard'))
    
    return render_template("scan.html")

# ---------------- STUDENT REPORTS ----------------
@app.route("/student_report")
def student_report():
    if not login_required('student'):
        return redirect(url_for('login'))
    
    if not supabase: return "DB Error", 500
    
    sid = session['user']
    
    # Complex aggregation logic (Python side to avoid complex SQL/RPC for now)
    try:
        # 1. Get all subjects
        subjects = supabase.table("subjects").select("*").execute().data
        
        # 2. Get all distinct session counts per subject
        # Fetch all inactive sessions to count 'total classes held'
        all_sessions = supabase.table("attendance_sessions").select("subject_id, session_id").eq("active", False).execute().data
        
        # Map: subject_id -> set(session_ids)
        subject_session_map = {}
        for s in all_sessions:
            sub_id = s['subject_id']
            if sub_id not in subject_session_map:
                subject_session_map[sub_id] = set()
            subject_session_map[sub_id].add(s['session_id'])
            
        # 3. Get student attendance
        my_records = supabase.table("attendance_records").select("session_id, subject_id").eq("sid", sid).execute().data
        
        # Map: subject_id -> set(attended_session_ids)
        my_attendance_map = {}
        for r in my_records:
            sub_id = r['subject_id']
            if sub_id not in my_attendance_map:
                my_attendance_map[sub_id] = set()
            my_attendance_map[sub_id].add(r['session_id'])
            
        # 4. Build Report
        report = []
        for sub in subjects:
            sub_id = sub['subject_id']
            
            # Total unique completed sessions for this subject
            total_sessions = len(subject_session_map.get(sub_id, []))
            if total_sessions == 0: total_sessions = 1 # Avoid div by zero
            
            # My attended sessions
            attended_sessions = len(my_attendance_map.get(sub_id, []))
            
            percentage = (attended_sessions / total_sessions) * 100
            
            report.append({
                'subject_name': sub['subject_name'],
                'total_classes': total_sessions if total_sessions > 0 and sub_id in subject_session_map else 0, # Display 0 if really 0
                'attended': attended_sessions,
                'percentage': round(percentage, 2)
            })
            
    except Exception as e:
        print(f"Report Generation Error: {e}")
        report = []
    
    return render_template("student_report.html", report=report)

@app.route("/student_report/export")
def export_student_report():
    # Logic similar to above, reuse function or copy... copying for safety & speed
    if not login_required('student'): return redirect(url_for('login'))
    if not supabase: return "DB error", 500
    
    sid = session['user']
    # ... (Re-run logic, omitted for brevity but strictly speaking should duplicate logic or call helper)
    # Re-running logic for CSV:
    try:
        subjects = supabase.table("subjects").select("*").execute().data
        all_sessions = supabase.table("attendance_sessions").select("subject_id, session_id").eq("active", False).execute().data
        subject_session_map = {}
        for s in all_sessions:
            sub_id = s['subject_id']
            if sub_id not in subject_session_map: subject_session_map[sub_id] = set()
            subject_session_map[sub_id].add(s['session_id'])
        my_records = supabase.table("attendance_records").select("session_id, subject_id").eq("sid", sid).execute().data
        my_attendance_map = {}
        for r in my_records:
            sub_id = r['subject_id']
            if sub_id not in my_attendance_map: my_attendance_map[sub_id] = set()
            my_attendance_map[sub_id].add(r['session_id'])
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Subject", "Total Classes", "Attended", "Percentage"])
        
        for sub in subjects:
            sub_id = sub['subject_id']
            total = len(subject_session_map.get(sub_id, []))
            attended = len(my_attendance_map.get(sub_id, []))
            real_total = total if total > 0 else 1
            percentage = (attended / real_total) * 100
            
            writer.writerow([sub['subject_name'], total, attended, f"{round(percentage, 2)}%"])
            
    except Exception as e:
        return f"Error: {e}"

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"attendance_report_{sid}.csv"
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)

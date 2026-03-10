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
    now = datetime.now()
    return {
        'now': now.strftime("%d %b %Y, %I:%M %p"),
        'now_iso': now.strftime("%Y-%m-%d")
    }

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

# ---------------- ADMIN REPORTS ----------------

# ---------------- ADMIN REPORTS ----------------


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

        # Pending Approvals (Teachers can also approve)
        pending_students = supabase.table("users").select("*").eq("role", "student").eq("status", "pending").execute().data
        
    except Exception as e:
        print(f"Teacher Dashboard Error: {e}")
        active_session = None
        count = 0
        pending_students = []

    return render_template("teacher_dashboard.html", active_session=active_session, attendance_count=count, pending_students=pending_students)

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
            subject_name = request.form.get("subject_name", "").strip()
            department = request.form.get("department", "").strip()
            semester = request.form.get("semester", "").strip()
            section = request.form.get("section", "").strip()
            session_date = request.form.get("session_date")
            session_name = request.form.get("session_name", "").strip()
            
            if subject_name and session_date:
                try:
                    # Deactivate all others first
                    supabase.table("attendance_sessions").update({"active": False}).eq("active", True).execute()
                    
                    # Insert new session with manual subject and class metadata
                    supabase.table("attendance_sessions").insert({
                        "teacher_id": session['user'],
                        "subject": subject_name,
                        "department": department,
                        "semester": semester,
                        "section": section,
                        "session_date": session_date,
                        "session_name": session_name,
                        "active": True,
                        "start_time": datetime.now().isoformat()
                    }).execute()
                    
                    flash(f"Attendance started for {subject_name}", "success")
                except Exception as e:
                     flash(f"Error starting session: {e}", "error")

            else:
                flash("Please enter a subject and date", "error")
        elif action == "stop":
            try:
                # 1. Get the currently active session to know which subject we are processing
                active_resp = supabase.table("attendance_sessions").select("*").eq("active", True).execute()
                active_session = active_resp.data[0] if active_resp.data else None
                
                if active_session:
                    # Automatically mark absent students
                    sess_id = active_session['session_id']
                    
                    # Use class metadata directly from active_session
                    dept = active_session.get('department')
                    sem = active_session.get('semester')
                    sec = active_session.get('section')
                        
                    # Find all enrolled students for this subject
                    print(f"DEBUG: Looking for students with Dept: '{dept}', Sem: '{sem}', Sec: '{sec}'")
                    
                    query = supabase.table("users").select("sid, name").eq("role", "student")
                    if dept: query = query.ilike("department", f"{dept.strip()}")
                    if sem: query = query.ilike("semester", f"{sem.strip()}")
                    if sec: query = query.ilike("section", f"{sec.strip()}")
                    
                    enrolled_resp = query.execute()
                    enrolled = enrolled_resp.data if enrolled_resp.data else []
                    
                    # Find students already marked (present or otherwise)
                    marked_resp = supabase.table("attendance_records").select("sid").eq("session_id", sess_id).execute()
                    marked_sids = [str(m['sid']).strip() for m in marked_resp.data] if marked_resp.data else []
                        
                    # Identify absentees
                    absentees = [s for s in enrolled if str(s['sid']).strip() not in marked_sids]
                    
                    print(f"DEBUG: Found {len(enrolled)} enrolled, {len(marked_sids)} marked, resulting in {len(absentees)} absentees.")
                    
                    # Use a consistent date format: %d-%m-%Y
                    rec_date = datetime.now().strftime("%d-%m-%Y")
                    
                    # Insert absentee records
                    for student in absentees:
                        try:
                            supabase.table("attendance_records").insert({
                                "session_id": sess_id,
                                "sid": str(student['sid']).strip(),
                                "name": student['name'],
                                "subject": active_session['subject'],
                                "date": rec_date,
                                "time": datetime.now().strftime("%H:%M:%S"),
                                "status": "absent",
                                "marked_type": "auto"
                            }).execute()
                        except Exception as ie:
                            print(f"Error inserting absentee {student['sid']}: {ie}")

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
        
        if active_session:
            cleanup_tokens()
            
            # 2. Update QR Token logic
            try:
                # Check latest token
                tk_resp = supabase.table("valid_tokens").select("created_at").order("created_at", desc=True).limit(1).execute()
                row = tk_resp.data[0] if tk_resp.data else None
                
                generate_new = False
                if not row:
                    generate_new = True
                else:
                    try:
                        # Parse timestamp
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
                flash("Warning: Token permission error. Attendance might not be markable.", "warning")
        
        if not active_session: active_session = None
        
    except Exception as e:
        print(f"Teacher Page Error: {e}")
        active_session = None
        
    # Extra data for manual tracking if session is active
    enrolled_students = []
    present_sids = []
    manual_present_sids = []
    absent_sids = []
    
    if active_session:
        try:
            dept = active_session.get("department")
            sem = active_session.get("semester")
            sec = active_session.get("section")
            
            # Fetch eligible students with robust filtering
            query = supabase.table("users").select("sid, name").eq("role", "student")
            if dept: query = query.ilike("department", f"{dept.strip()}")
            if sem: query = query.ilike("semester", f"{sem.strip()}")
            if sec: query = query.ilike("section", f"{sec.strip()}")
            
            enrolled_resp = query.execute()
            enrolled_students = enrolled_resp.data if enrolled_resp.data else []
                    
            # Fetch existing records
            records_resp = supabase.table("attendance_records").select("sid, status, marked_type").eq("session_id", active_session['session_id']).execute()
            records = records_resp.data if records_resp.data else []
            
            for r in records:
                sid_str = str(r['sid']).strip()
                if r.get('status', 'present') == 'present':
                    present_sids.append(sid_str)
                    if r.get('marked_type') == 'manual':
                        manual_present_sids.append(sid_str)
                elif r.get('status') == 'absent':
                    absent_sids.append(sid_str)
                    
        except Exception as e:
            print(f"Error fetching manual tracking data: {e}")
    
    return render_template("teacher.html", 
                           active=bool(active_session), 
                           current_subject=active_session['subject'] if active_session else "", 
                           session_id=active_session['session_id'] if active_session else 0,
                           session_name=active_session.get('session_name', '') if active_session else "",
                           current_date=active_session.get('session_date', '') if active_session else "",
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
    
    subject_filter = request.args.get('subject_id', None) # Still using 'subject_id' key for now to keep query param name
    
    try:
        # Get unique subjects from attendance records for filtering
        records_resp = supabase.table("attendance_records").select("subject").execute()
        subjects = list(set(r['subject'] for r in records_resp.data if r.get('subject')))
        subjects.sort()
        
        query = supabase.table("attendance_records").select("*").order("record_id", desc=True)
        if subject_filter:
            query = query.eq("subject", subject_filter)
        
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
    subject_filter = request.args.get('subject_id', '') # Keeping 'subject_id' as param name for compatibility
    from_date = request.args.get('from_date', '')
    to_date = request.args.get('to_date', '')
    search = request.args.get('search', '').strip()
    
    try:
        # Get unique subjects for filter dropdown
        if role == 'student':
            subjects = []
        else:
            # Fetch unique subject names from records
            subj_resp = supabase.table("attendance_records").select("subject").execute()
            subjects = list(set(r['subject'] for r in subj_resp.data if r.get('subject')))
            subjects.sort()
        
        # Build query with role-based filtering
        query = supabase.table("attendance_records").select("*")
        
        # Role-based data restriction
        if role == 'student':
            query = query.eq("sid", user_id)
        
        # Apply filters
        if subject_filter:
            query = query.eq("subject", subject_filter)
        
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
            subject_name = record.get('subject', 'N/A')
            
            # Create unique key for student-subject combination
            key = f"{sid}_{subject_name}"
            
            if key not in student_summary:
                student_summary[key] = {
                    'sid': sid,
                    'name': record['name'],
                    'subject': subject_name,
                    'present': 0,
                    'total': 0,
                    'percentage': 0,
                    'badge_class': 'badge-red'
                }
            
            student_summary[key]['total'] += 1
            if record.get('status', 'present') == 'present':
                student_summary[key]['present'] += 1
        
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
    writer.writerow(["Session", "Name", "ID", "Subject", "Date", "Time", "Status"])
    for r in records:
        writer.writerow([r['session_id'], r['name'], r['sid'], r['subject'], r['date'], r['time'], r.get('status', 'present')])

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
    # Aggregation logic by subject name
    try:
        # 1. Get all distinct session counts per subject name
        # Fetch all inactive sessions to count 'total classes held'
        all_sessions = supabase.table("attendance_sessions").select("subject, session_id").eq("active", False).execute().data
        
        # Map: subject_name -> set(session_ids)
        subject_session_map = {}
        for s in all_sessions:
            sub_name = s['subject']
            if sub_name not in subject_session_map:
                subject_session_map[sub_name] = set()
            subject_session_map[sub_name].add(s['session_id'])
            
        # 2. Get student attendance
        my_records = supabase.table("attendance_records").select("session_id, subject").eq("sid", sid).execute().data
        
        # Map: subject_name -> set(attended_session_ids)
        my_attendance_map = {}
        for r in my_records:
            if r.get('status', 'present') == 'present':
                sub_name = r['subject']
                if sub_name not in my_attendance_map:
                    my_attendance_map[sub_name] = set()
                my_attendance_map[sub_name].add(r['session_id'])
            
        # 3. Build Report
        report = []
        # Use all subject names found in sessions as the base
        all_subject_names = sorted(list(subject_session_map.keys()))
        
        for sub_name in all_subject_names:
            total_sessions = len(subject_session_map.get(sub_name, []))
            if total_sessions == 0: continue
            
            attended_sessions = len(my_attendance_map.get(sub_name, []))
            percentage = (attended_sessions / total_sessions) * 100
            
            report.append({
                'subject_name': sub_name,
                'total_classes': total_sessions,
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
        all_sessions = supabase.table("attendance_sessions").select("subject, session_id").eq("active", False).execute().data
        subject_session_map = {}
        for s in all_sessions:
            sub_name = s['subject']
            if sub_name not in subject_session_map: subject_session_map[sub_name] = set()
            subject_session_map[sub_name].add(s['session_id'])
            
        my_records = supabase.table("attendance_records").select("session_id, subject").eq("sid", sid).execute().data
        my_attendance_map = {}
        for r in my_records:
            sub_name = r['subject']
            if sub_name not in my_attendance_map: my_attendance_map[sub_name] = set()
            my_attendance_map[sub_name].add(r['session_id'])
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Subject", "Total Classes", "Attended", "Percentage"])
        
        all_subject_names = sorted(list(subject_session_map.keys()))
        for sub_name in all_subject_names:
            total = len(subject_session_map.get(sub_name, []))
            attended = len(my_attendance_map.get(sub_name, []))
            real_total = total if total > 0 else 1
            percentage = (attended / real_total) * 100
            
            writer.writerow([sub_name, total, attended, f"{round(percentage, 2)}%"])
            
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

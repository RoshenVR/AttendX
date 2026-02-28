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
    # Dynamic URL: Use Render's external URL if available, else fallback to local IP
    server_url = os.environ.get('RENDER_EXTERNAL_URL')
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

        if not supabase:
             flash("Database connection error.", "error")
             return render_template("register.html")

        try:
            supabase.table("users").insert({
                "sid": sid, 
                "name": name, 
                "password": password, 
                "role": "student",
                "status": "pending"
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
            
            if subject_name and class_name:
                try:
                    supabase.table("subjects").insert({
                        "subject_name": subject_name,
                        "class_name": class_name,
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
    
    if subject_name and class_name:
        if not supabase: return "DB Error", 500
        try:
            supabase.table("subjects").update({
                "subject_name": subject_name, 
                "class_name": class_name
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
            if subject_id:
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
                            "active": True,
                            "start_time": datetime.now().isoformat()
                        }).execute()
                        
                        flash(f"Attendance started for {subject['subject_name']}", "success")
                    else:
                        flash("Selected subject not found", "error")
                except Exception as e:
                     flash(f"Error starting session: {e}", "error")

            else:
                flash("Please select a subject", "error")
        elif action == "stop":
            try:
                supabase.table("attendance_sessions").update({"active": False}).eq("active", True).execute()
                supabase.table("valid_tokens").delete().neq("token", "dummy").execute() # Delete all (hackish neq or just get all IDs?)
                # Delete all tokens:
                # supabase.table("valid_tokens").delete().gt("created_at", "1970-01-01").execute() involves filtering.
                # Simplest is likely just to leave them or delete specifically.
                # Actually we can just leave them, cleanup_tokens deletes expired ones.
                # But to invalidate current QR immediately:
                # We can update expiry of all valid tokens to now?
                supabase.table("valid_tokens").delete().gt("expires_at", "2000-01-01").execute() 
                
                flash("Attendance stopped.", "success")
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
            
            # Check latest token
            # Supabase doesn't support 'limit' with order easily in the same way? yes it does .order().limit()
            tk_resp = supabase.table("valid_tokens").select("created_at").order("created_at", desc=True).limit(1).execute()
            row = tk_resp.data[0] if tk_resp.data else None
            
            generate_new = False
            if not row:
                generate_new = True
            else:
                try:
                    # Parse timestamp (Supabase is ISO 8601)
                    last_created = datetime.fromisoformat(row['created_at'].replace('Z', '+00:00')) 
                    # Note: Naive vs Aware datetime issues might occur.
                    # datetime.now() is naive local. Supabase is UTC aware.
                    # Simple fix: compare timestamps or force utc.
                    # Let's use time.time() for elapsed
                    # Or just rely on string if newly inserted?
                    # Let's try to be robust. 
                    # .timestamp() gives float.
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
    except Exception as e:
        print(f"Teacher Page Error: {e}")
        active_session = None
        subjects = []
    
    return render_template("teacher.html", 
                           active=bool(active_session), 
                           current_subject=active_session['subject'] if active_session else "", 
                           session_id=active_session['session_id'] if active_session else 0,
                           subjects=subjects)

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
            
            # Validate token
            token_valid = supabase.table("valid_tokens").select("*").eq("token", token_submitted).execute()
            
            if token_valid.data:
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
            token_valid = supabase.table("valid_tokens").select("*").eq("token", token).execute()
            if token_valid.data:
                return render_template("student.html", active=True, token=token, subject=active_session['subject'])
            else:
                flash("QR code expired. Please scan again.", "error")
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

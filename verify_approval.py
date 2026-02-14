import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

# Add current dir to path to import app
sys.path.append(os.getcwd())

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def verify_db():
    print("Verifying Database Schema...")
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("FAIL: Supabase credentials missing.")
        return False
    
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Check if 'status' column exists by trying to select it
        try:
            # We select status from users. Limit 1.
            supabase.table("users").select("status").limit(1).execute()
            print("PASS: 'status' column exists in 'users' table.")
            return True
        except Exception as e:
            print(f"FAIL: Could not select 'status' column. It might be missing. Error: {e}")
            print("\n!!! PLEASE RUN THE 'update_approval_schema.sql' SCRIPT IN SUPABASE SQL EDITOR !!!\n")
            return False

    except Exception as e:
        print(f"FAIL: Connection error: {e}")
        return False

def verify_app_syntax():
    print("\nVerifying App Syntax...")
    try:
        import app
        print("PASS: app.py imports successfully (Syntax OK).")
        return True
    except ImportError as e:
        print(f"FAIL: app.py import failed: {e}")
        return False
    except SyntaxError as e:
        print(f"FAIL: Syntax error in app.py: {e}")
        return False
    except Exception as e:
        print(f"FAIL: Error importing app.py (Runtime/Config?): {e}")
        # Might fail due to db connection on import if init logic runs, but app.py seems safe on import
        return False

if __name__ == "__main__":
    db_ok = verify_db()
    app_ok = verify_app_syntax()
    
    if db_ok and app_ok:
        print("\nAll checks PASSED. System is ready.")
    else:
        print("\nVerification FAILED. Please fix issues above.")

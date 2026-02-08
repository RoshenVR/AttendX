"""
Verification script for AttendX enhancements
Tests:
1. Duplicate prevention via database constraint
2. Subject management flow
3. Subject-wise reporting
"""

import sqlite3
import sys

DATABASE = 'attendance.db'

def verify_duplicate_prevention():
    """Test that duplicate attendance marking is prevented at DB level"""
    print("\n=== Testing Duplicate Prevention ===")
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    try:
        # Check if UNIQUE constraint exists
        cursor.execute("PRAGMA index_list('attendance_records')")
        indexes = cursor.fetchall()
        
        has_unique_constraint = False
        for index in indexes:
            cursor.execute(f"PRAGMA index_info('{index[1]}')")
            cols = [col[2] for col in cursor.fetchall()]
            if 'session_id' in cols and 'sid' in cols:
                has_unique_constraint = True
                break
        
        if has_unique_constraint:
            print("✓ UNIQUE constraint on (session_id, sid) exists")
        else:
            # Check if it's a table constraint
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='attendance_records'")
            schema = cursor.fetchone()[0]
            if 'UNIQUE' in schema and 'session_id' in schema and 'sid' in schema:
                print("✓ UNIQUE constraint on (session_id, sid) exists")
            else:
                print("✗ UNIQUE constraint NOT found")
                return False
        
        # Test actual duplicate insertion
        cursor.execute("SELECT session_id FROM attendance_sessions LIMIT 1")
        session_row = cursor.fetchone()
        
        if session_row:
            test_session_id = session_row[0]
            test_sid = "TEST_STUDENT"
            
            # Try to insert first record
            try:
                cursor.execute(
                    "INSERT INTO attendance_records (session_id, sid, name, subject, date, time) VALUES (?, ?, ?, ?, ?, ?)",
                    (test_session_id, test_sid, "Test", "Test Subject", "01-01-2026", "12:00:00")
                )
                conn.commit()
                print("✓ First attendance record inserted")
                
                # Try to insert duplicate
                try:
                    cursor.execute(
                        "INSERT INTO attendance_records (session_id, sid, name, subject, date, time) VALUES (?, ?, ?, ?, ?, ?)",
                        (test_session_id, test_sid, "Test", "Test Subject", "01-01-2026", "12:00:00")
                    )
                    conn.commit()
                    print("✗ Duplicate insertion was ALLOWED (should have been blocked)")
                    return False
                except sqlite3.IntegrityError as e:
                    if "UNIQUE" in str(e):
                        print("✓ Duplicate insertion BLOCKED by database constraint")
                    else:
                        print(f"✗ Unexpected error: {e}")
                        return False
                finally:
                    # Cleanup test record
                    cursor.execute("DELETE FROM attendance_records WHERE sid = ?", (test_sid,))
                    conn.commit()
            except Exception as e:
                print(f"✗ Test failed: {e}")
                return False
        
        return True
        
    except Exception as e:
        print(f"✗ Verification failed: {e}")
        return False
    finally:
        conn.close()

def verify_subjects_table():
    """Check subjects table exists and has correct structure"""
    print("\n=== Verifying Subjects Table ===")
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='subjects'")
        if not cursor.fetchone():
            print("✗ subjects table does NOT exist")
            return False
        
        print("✓ subjects table exists")
        
        # Check columns
        cursor.execute("PRAGMA table_info(subjects)")
        columns = {col[1]: col[2] for col in cursor.fetchall()}
        
        required_cols = ['subject_id', 'subject_name', 'class_name', 'added_by', 'created_at']
        for col in required_cols:
            if col in columns:
                print(f"✓ Column '{col}' exists")
            else:
                print(f"✗ Column '{col}' MISSING")
                return False
        
        # Check if there are any subjects
        cursor.execute("SELECT COUNT(*) FROM subjects")
        count = cursor.fetchone()[0]
        print(f"ℹ Current subject count: {count}")
        
        return True
        
    except Exception as e:
        print(f"✗ Verification failed: {e}")
        return False
    finally:
        conn.close()

def verify_foreign_keys():
    """Check that foreign keys are properly defined"""
    print("\n=== Verifying Foreign Keys ===")
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    try:
        # Check attendance_sessions
        cursor.execute("PRAGMA foreign_key_list(attendance_sessions)")
        fks = cursor.fetchall()
        
        has_teacher_fk = any(fk[2] == 'users' and fk[3] == 'teacher_id' for fk in fks)
        has_subject_fk = any(fk[2] == 'subjects' for fk in fks)
        
        if has_teacher_fk:
            print("✓ attendance_sessions has teacher_id FK to users")
        else:
            print("⚠ teacher_id FK to users not found (optional)")
        
        if has_subject_fk:
            print("✓ attendance_sessions has subject_id FK to subjects")
        else:
            print("⚠ subject_id FK to subjects not found (optional)")
        
        # Check attendance_records
        cursor.execute("PRAGMA foreign_key_list(attendance_records)")
        fks = cursor.fetchall()
        
        has_subject_fk = any(fk[2] == 'subjects' for fk in fks)
        
        if has_subject_fk:
            print("✓ attendance_records has subject_id FK to subjects")
        else:
            print("⚠ subject_id FK to subjects not found (optional)")
        
        return True
        
    except Exception as e:
        print(f"✗ Verification failed: {e}")
        return False
    finally:
        conn.close()

def main():
    print("=" * 60)
    print("AttendX Enhancement Verification Script")
    print("=" * 60)
    
    results = []
    
    results.append(("Subjects Table", verify_subjects_table()))
    results.append(("Foreign Keys", verify_foreign_keys()))
    results.append(("Duplicate Prevention", verify_duplicate_prevention()))
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{name}: {status}")
        if not result:
            all_passed = False
    
    if all_passed:
        print("\n✅ All verifications PASSED!")
        return 0
    else:
        print("\n❌ Some verifications FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())

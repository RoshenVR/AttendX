-- 1. Add Department, Semester, Section to 'users' table
ALTER TABLE users
ADD COLUMN IF NOT EXISTS department TEXT DEFAULT 'General',
ADD COLUMN IF NOT EXISTS semester TEXT DEFAULT '1',
ADD COLUMN IF NOT EXISTS section TEXT DEFAULT 'A';

-- 2. Add Department, Semester, Section to 'subjects' table
ALTER TABLE subjects
ADD COLUMN IF NOT EXISTS department TEXT DEFAULT 'General',
ADD COLUMN IF NOT EXISTS semester TEXT DEFAULT '1',
ADD COLUMN IF NOT EXISTS section TEXT DEFAULT 'A';

-- 3. Add Session Date and Session Name to 'attendance_sessions'
-- We'll allow session_name to be nullable, and default session_date to the date of creation
ALTER TABLE attendance_sessions
ADD COLUMN IF NOT EXISTS session_date DATE DEFAULT CURRENT_DATE,
ADD COLUMN IF NOT EXISTS session_name TEXT;

-- 4. Add Manual Tracking columns to 'attendance_records'
-- Status will default to 'present'. Manual markings might be 'absent' or 'present'.
-- Marked_by relates to the user who marked it manually, marked_type is 'qr' or 'manual'
ALTER TABLE attendance_records
ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'present',
ADD COLUMN IF NOT EXISTS marked_by TEXT,
ADD COLUMN IF NOT EXISTS marked_type TEXT DEFAULT 'qr';

-- Add a foreign key constraint to marked_by (Optional but good for integrity)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE constraint_schema = 'public'
          AND table_name = 'attendance_records'
          AND constraint_name = 'attendance_records_marked_by_fkey'
    ) THEN
        ALTER TABLE attendance_records
        ADD CONSTRAINT attendance_records_marked_by_fkey
        FOREIGN KEY (marked_by) REFERENCES users(sid);
    END IF;
END $$;

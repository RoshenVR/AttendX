-- Add class metadata to attendance_sessions to support manual subject entry
ALTER TABLE attendance_sessions
ADD COLUMN IF NOT EXISTS department TEXT,
ADD COLUMN IF NOT EXISTS semester TEXT,
ADD COLUMN IF NOT EXISTS section TEXT;

-- Update existing sessions to have 'General' defaults if they were null
UPDATE attendance_sessions 
SET department = 'General' 
WHERE department IS NULL;

UPDATE attendance_sessions 
SET semester = '1' 
WHERE semester IS NULL;

UPDATE attendance_sessions 
SET section = 'A' 
WHERE section IS NULL;

-- Drop legacy subjects table
DROP TABLE IF EXISTS subjects CASCADE;

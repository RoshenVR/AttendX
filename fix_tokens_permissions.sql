-- Fix Permission Denied for 'valid_tokens' table
-- Run this in your Supabase SQL Editor

-- Grant permissions to 'anon' and 'authenticated' roles
GRANT ALL ON TABLE public.valid_tokens TO anon;
GRANT ALL ON TABLE public.valid_tokens TO authenticated;
GRANT ALL ON TABLE public.valid_tokens TO service_role;

-- If you are still getting errors, you might need to disable RLS for this specific table:
-- ALTER TABLE public.valid_tokens DISABLE ROW LEVEL SECURITY;

-- Ensure the 'attendance_records' table also has proper permissions for teachers to mark attendance
GRANT ALL ON TABLE public.attendance_records TO anon;
GRANT ALL ON TABLE public.attendance_records TO authenticated;
GRANT ALL ON TABLE public.attendance_records TO service_role;

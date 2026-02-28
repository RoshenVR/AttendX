-- FINAL FIX for Permission Denied (Run this in Supabase SQL Editor)

-- 1. Disable RLS (Fastest fix for prototypes)
ALTER TABLE public.valid_tokens DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.attendance_records DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.attendance_sessions DISABLE ROW LEVEL SECURITY;

-- 2. Grant FULL access to all roles (anon is what the public app uses)
GRANT ALL ON TABLE public.valid_tokens TO anon, authenticated, service_role, postgres;
GRANT ALL ON TABLE public.attendance_records TO anon, authenticated, service_role, postgres;
GRANT ALL ON TABLE public.attendance_sessions TO anon, authenticated, service_role, postgres;

-- 3. Grant access to sequences (Required for ID incrementing)
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated, service_role, postgres;

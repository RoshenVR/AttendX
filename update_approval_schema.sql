-- Add status column to users table with default value 'pending'
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS status text DEFAULT 'pending';

-- Update existing users (admin, teachers, and existing students) to 'approved'
-- This ensures current users don't get locked out.
UPDATE public.users SET status = 'approved' WHERE status IS NULL OR status = 'pending';

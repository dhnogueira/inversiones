-- SCHEMA PARA EL SISTEMA DE INVERSIONES - SUPABASE

-- ==========================================
-- 1. TABLADE PERFILES (Preferencias)
-- ==========================================
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    active_profile TEXT NOT NULL DEFAULT 'moderado' CHECK (active_profile IN ('conservador', 'moderado', 'agresivo')),
    active_horizon TEXT NOT NULL DEFAULT 'medium' CHECK (active_horizon IN ('short', 'medium', 'long')),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Habilitar RLS en profiles
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- Políticas RLS para profiles
CREATE POLICY "Allow users to read their own profile" 
    ON public.profiles FOR SELECT 
    USING (auth.uid() = id);

CREATE POLICY "Allow users to update their own profile" 
    ON public.profiles FOR UPDATE 
    USING (auth.uid() = id);

CREATE POLICY "Allow users to insert their own profile" 
    ON public.profiles FOR INSERT 
    WITH CHECK (auth.uid() = id);

-- ==========================================
-- 2. TABLA DE CARTERAS (Portfolios)
-- ==========================================
CREATE TABLE IF NOT EXISTS public.portfolios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    currency TEXT NOT NULL CHECK (currency IN ('ARS', 'USD')),
    entry_price NUMERIC(15, 4) NOT NULL CHECK (entry_price >= 0),
    quantity NUMERIC(15, 4) NOT NULL CHECK (quantity > 0),
    entry_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Habilitar RLS en portfolios
ALTER TABLE public.portfolios ENABLE ROW LEVEL SECURITY;

-- Políticas RLS para portfolios
CREATE POLICY "Allow users to read their own portfolio positions" 
    ON public.portfolios FOR SELECT 
    USING (auth.uid() = user_id);

CREATE POLICY "Allow users to insert their own portfolio positions" 
    ON public.portfolios FOR INSERT 
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Allow users to update their own portfolio positions" 
    ON public.portfolios FOR UPDATE 
    USING (auth.uid() = user_id);

CREATE POLICY "Allow users to delete their own portfolio positions" 
    ON public.portfolios FOR DELETE 
    USING (auth.uid() = user_id);

-- Indices para portfolios
CREATE INDEX IF NOT EXISTS idx_portfolios_user_id ON public.portfolios(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolios_ticker ON public.portfolios(ticker);

-- ==========================================
-- 3. TABLA DE WATCHLISTS (Alertas Técnicas)
-- ==========================================
CREATE TABLE IF NOT EXISTS public.watchlists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    alert_rules JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    UNIQUE (user_id, ticker)
);

-- Habilitar RLS en watchlists
ALTER TABLE public.watchlists ENABLE ROW LEVEL SECURITY;

-- Políticas RLS para watchlists
CREATE POLICY "Allow users to read their own watchlist items" 
    ON public.watchlists FOR SELECT 
    USING (auth.uid() = user_id);

CREATE POLICY "Allow users to insert their own watchlist items" 
    ON public.watchlists FOR INSERT 
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Allow users to update their own watchlist items" 
    ON public.watchlists FOR UPDATE 
    USING (auth.uid() = user_id);

CREATE POLICY "Allow users to delete their own watchlist items" 
    ON public.watchlists FOR DELETE 
    USING (auth.uid() = user_id);

-- Indices para watchlists
CREATE INDEX IF NOT EXISTS idx_watchlists_user_id ON public.watchlists(user_id);

-- ==========================================
-- 4. DISPARADOR (TRIGGER) PARA CREAR PERFIL AUTOMÁTICO AL REGISTRAR
-- ==========================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, active_profile, active_horizon)
    VALUES (new.id, 'moderado', 'medium');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

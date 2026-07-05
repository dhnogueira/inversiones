// Lee la configuración de Supabase desde window.CONFIG (inyectado por config.js como script clásico)
// Si no está disponible, usa valores de fallback para que la app funcione sin Supabase
const CONFIG = window.CONFIG || {
    SUPABASE_URL: '',
    SUPABASE_ANON_KEY: ''
};

// Init Supabase Client (solo si hay credenciales válidas)
const supabase = (window.supabase && CONFIG.SUPABASE_URL) ? window.supabase.createClient(CONFIG.SUPABASE_URL, CONFIG.SUPABASE_ANON_KEY) : null;
let session = null;
let user = null;

// ===== ASSET METADATA =====
// Nombre completo de la empresa, rubro/sector y año de inicio de cotización
const ASSET_METADATA = {
    // S&P 500
    'AAPL': { company: 'Apple Inc.', sector: 'Tecnología', ipo: 1980 },
    'MSFT': { company: 'Microsoft Corporation', sector: 'Software & Nube', ipo: 1986 },
    'NVDA': { company: 'NVIDIA Corporation', sector: 'Semiconductores', ipo: 1999 },
    'AMZN': { company: 'Amazon.com Inc.', sector: 'E-Commerce & Nube', ipo: 1997 },
    'META': { company: 'Meta Platforms Inc.', sector: 'Redes Sociales', ipo: 2012 },
    'GOOGL': { company: 'Alphabet Inc. (Google)', sector: 'Tecnología & Publicidad', ipo: 2004 },
    'BRK-B': { company: 'Berkshire Hathaway Inc.', sector: 'Holding Financiero', ipo: 1996 },
    'LLY': { company: 'Eli Lilly and Company', sector: 'Farmacéutica', ipo: 1952 },
    'AVGO': { company: 'Broadcom Inc.', sector: 'Semiconductores', ipo: 2009 },
    'JPM': { company: 'JPMorgan Chase & Co.', sector: 'Banca & Servicios Financieros', ipo: 1969 },
    'TSLA': { company: 'Tesla Inc.', sector: 'Automotriz & Energía', ipo: 2010 },
    'XOM': { company: 'ExxonMobil Corporation', sector: 'Petróleo & Gas', ipo: 1920 },
    'UNH': { company: 'UnitedHealth Group Inc.', sector: 'Seguros & Salud', ipo: 1984 },
    'PG': { company: 'Procter & Gamble Co.', sector: 'Consumo Masivo', ipo: 1890 },
    'V': { company: 'Visa Inc.', sector: 'Pagos Digitales', ipo: 2008 },
    'MA': { company: 'Mastercard Incorporated', sector: 'Pagos Digitales', ipo: 2006 },
    'HD': { company: 'The Home Depot Inc.', sector: 'Retail & Construcción', ipo: 1981 },
    'COST': { company: 'Costco Wholesale Corporation', sector: 'Retail Mayorista', ipo: 1985 },
    'MRK': { company: 'Merck & Co. Inc.', sector: 'Farmacéutica', ipo: 1946 },
    'ABBV': { company: 'AbbVie Inc.', sector: 'Biofarmacéutica', ipo: 2013 },
    // CEDEARs (igual ticker sin .BA)
    'AAPL.BA': { company: 'Apple Inc.', sector: 'Tecnología', ipo: 1980 },
    'MSFT.BA': { company: 'Microsoft Corporation', sector: 'Software & Nube', ipo: 1986 },
    'TSLA.BA': { company: 'Tesla Inc.', sector: 'Automotriz & Energía', ipo: 2010 },
    'MELI.BA': { company: 'MercadoLibre Inc.', sector: 'E-Commerce Latinoamérica', ipo: 2007 },
    'KO.BA': { company: 'The Coca-Cola Company', sector: 'Bebidas & Consumo', ipo: 1919 },
    'NVDA.BA': { company: 'NVIDIA Corporation', sector: 'Semiconductores', ipo: 1999 },
    'AMZN.BA': { company: 'Amazon.com Inc.', sector: 'E-Commerce & Nube', ipo: 1997 },
    'META.BA': { company: 'Meta Platforms Inc.', sector: 'Redes Sociales', ipo: 2012 },
    'GOOGL.BA': { company: 'Alphabet Inc. (Google)', sector: 'Tecnología & Publicidad', ipo: 2004 },
    'XOM.BA': { company: 'ExxonMobil Corporation', sector: 'Petróleo & Gas', ipo: 1920 },
    'BABA.BA': { company: 'Alibaba Group Holding Ltd.', sector: 'E-Commerce & Nube China', ipo: 2014 },
    'VALE.BA': { company: 'Vale S.A.', sector: 'Minería & Metales', ipo: 2002 },
    'PBR.BA': { company: 'Petróleo Brasileiro S.A.', sector: 'Petróleo & Gas', ipo: 2001 },
    'GGLD.BA': { company: 'Barrick Gold Corporation', sector: 'Minería de Oro', ipo: 1983 },
    'DESP.BA': { company: 'Despegar.com Corp.', sector: 'Turismo Online', ipo: 2017 },
    // Merval
    'YPFD.BA': { company: 'YPF S.A.', sector: 'Petróleo & Gas', ipo: 1993 },
    'GGAL.BA': { company: 'Grupo Financiero Galicia S.A.', sector: 'Banca', ipo: 2000 },
    'PAMP.BA': { company: 'Pampa Energía S.A.', sector: 'Energía Eléctrica', ipo: 1993 },
    'ALUA.BA': { company: 'Aluar Aluminio Argentino S.A.', sector: 'Aluminio & Metales', ipo: 1993 },
    'TXAR.BA': { company: 'Ternium Argentina S.A.', sector: 'Siderurgia', ipo: 1993 },
    'BMA.BA': { company: 'Banco Macro S.A.', sector: 'Banca', ipo: 1994 },
    'CEPU.BA': { company: 'Central Puerto S.A.', sector: 'Generación Eléctrica', ipo: 1993 },
    'TGSU2.BA': { company: 'Transportadora de Gas del Sur S.A.', sector: 'Gas & Energía', ipo: 1994 },
    'EDN.BA': { company: 'Edenor S.A.', sector: 'Distribución Eléctrica', ipo: 1993 },
    'LOMA.BA': { company: 'Loma Negra Compañía Industrial Argentina S.A.', sector: 'Cemento', ipo: 2017 },
    'CRES.BA': { company: 'Cresud S.A.C.I.F. y A.', sector: 'Agropecuario', ipo: 1997 },
    'TECO2.BA': { company: 'Telecom Argentina S.A.', sector: 'Telecomunicaciones', ipo: 1992 },
    'SUPV.BA': { company: 'Grupo Supervielle S.A.', sector: 'Banca & Finanzas', ipo: 2016 },
    'VALO.BA': { company: 'Grupo Financiero Valores S.A.', sector: 'Finanzas & Inversiones', ipo: 2018 },
    'BYMA.BA': { company: 'Bolsas y Mercados Argentinos S.A.', sector: 'Mercado de Capitales', ipo: 2017 },
    // Crypto
    'BTC-USD': { company: 'Bitcoin', sector: 'Criptomoneda — Reserva de Valor', ipo: 2009 },
    'ETH-USD': { company: 'Ethereum', sector: 'Plataforma de Smart Contracts', ipo: 2015 },
    'BNB-USD': { company: 'BNB (Binance Coin)', sector: 'Token de Exchange', ipo: 2017 },
    'SOL-USD': { company: 'Solana', sector: 'Blockchain L1', ipo: 2020 },
    'XRP-USD': { company: 'Ripple (XRP)', sector: 'Pagos Transfronterizos', ipo: 2013 },
    'ADA-USD': { company: 'Cardano (ADA)', sector: 'Blockchain L1', ipo: 2017 },
    'DOGE-USD': { company: 'Dogecoin', sector: 'Criptomoneda Meme', ipo: 2013 },
    'AVAX-USD': { company: 'Avalanche (AVAX)', sector: 'Blockchain L1', ipo: 2020 },
    'LINK-USD': { company: 'Chainlink (LINK)', sector: 'Oráculos Blockchain', ipo: 2017 },
    'DOT-USD': { company: 'Polkadot (DOT)', sector: 'Interoperabilidad Blockchain', ipo: 2020 },
    // Bonos soberanos argentinos
    'AL30.BA': { company: 'Bono Soberano Argentina AL30', sector: 'Renta Fija Soberana USD', ipo: 2020 },
    'GD30.BA': { company: 'Bono Soberano Argentina GD30', sector: 'Renta Fija Soberana USD', ipo: 2020 },
    'AL29.BA': { company: 'Bono Soberano Argentina AL29', sector: 'Renta Fija Soberana USD', ipo: 2020 },
    'GD29.BA': { company: 'Bono Soberano Argentina GD29', sector: 'Renta Fija Soberana USD', ipo: 2020 },
    'AL35.BA': { company: 'Bono Soberano Argentina AL35', sector: 'Renta Fija Soberana USD', ipo: 2020 },
    'GD35.BA': { company: 'Bono Soberano Argentina GD35', sector: 'Renta Fija Soberana USD', ipo: 2020 },
    'AE38.BA': { company: 'Bono Soberano Argentina AE38', sector: 'Renta Fija Soberana USD', ipo: 2020 },
    'GD38.BA': { company: 'Bono Soberano Argentina GD38', sector: 'Renta Fija Soberana USD', ipo: 2020 },
    'AL41.BA': { company: 'Bono Soberano Argentina AL41', sector: 'Renta Fija Soberana USD', ipo: 2020 },
    'GD41.BA': { company: 'Bono Soberano Argentina GD41', sector: 'Renta Fija Soberana USD', ipo: 2020 },
};

// State Management
let state = {
    activeProfile: 'moderado',
    activeHorizon: 'medium', // 'short', 'medium', 'long'
    activeCategory: 'all',
    searchQuery: '',
    marketData: null,
    updating: false,
    currentView: 'dashboard',
    staticMode: false,         // Si es true, usa JSONs estáticos y localStorage
    apiBase: 'http://localhost:8000',
    portfolioPollingInterval: null  // Referencia para polling en tiempo real de cartera
};


// ApexCharts Instances
let allocationChart = null;
let yieldCurveChart = null;

// DOM Elements
const profileTabs = document.querySelectorAll('.profile-tab');
const horizonTabs = document.querySelectorAll('.horizon-tab');
const categoryFilters = document.querySelectorAll('.category-filter');
const searchInput = document.getElementById('asset-search');
const btnRefresh = document.getElementById('btn-refresh');
const navItems = document.querySelectorAll('.nav-item');
const contentViews = document.querySelectorAll('.content-view');
const updateTimeSpan = document.getElementById('update-time');
const tableBody = document.getElementById('assets-tbody');

// Sidebar and layout toggles
const menuToggle = document.getElementById('menu-toggle');
const sidebar = document.querySelector('.sidebar');
const sidebarOverlay = document.getElementById('sidebar-overlay');

// Initialize Application
document.addEventListener('DOMContentLoaded', async () => {
    setupEventListeners();
    setupAuthListeners();
    await checkHostMode();
    updateSubtitle();
    loadActiveView();
    // Iniciar ticker de chequeo de alertas cada 30 segundos
    setInterval(updateWatchlistAndAlerts, 30000);
});


// Función para actualizar dinámicamente el subtítulo de perfil y horizonte seleccionados
function updateSubtitle() {
    const subtitleEl = document.querySelector('.subtitle');
    if (subtitleEl) {
        const horizonNames = {
            'short': 'Corto plazo (hasta 6 meses)',
            'medium': 'Mediano plazo (6 a 12 meses)',
            'long': 'Largo plazo (más de 1 año)'
        };
        const hName = horizonNames[state.activeHorizon] || 'Mediano plazo';
        const pName = state.activeProfile.charAt(0).toUpperCase() + state.activeProfile.slice(1);
        subtitleEl.innerHTML = `Perfil: <strong style="color: var(--color-${state.activeProfile});">${pName}</strong> · Horizonte: <strong>${hName}</strong>`;
    }
}

// Detectar si el backend FastAPI corre localmente o si estamos en hosting estático
async function checkHostMode() {
    console.log("Detectando disponibilidad de backend FastAPI local...");
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2000);

        const response = await fetch(`${state.apiBase}/api/health`, { signal: controller.signal });
        clearTimeout(timeoutId);

        if (response.ok) {
            state.staticMode = false;
            console.log("Backend local conectado. Operando en modo dinámico.");
            document.querySelector('.update-status').innerHTML = '<i class="fa-solid fa-circle-check text-green"></i> Local API Connected';
        } else {
            throw new Error();
        }
    } catch (e) {
        state.staticMode = true;
        console.warn("Backend local offline o inaccesible. Cambiando a Modo Estático (Cloud / LocalStorage).");
        document.querySelector('.update-status').innerHTML = '<i class="fa-solid fa-cloud text-blue"></i> Cloud Static Offline Mode';

        // Ocultar botón de actualizar manual en modo estático en la nube
        if (btnRefresh) {
            btnRefresh.style.display = 'none';
        }
    }
}

function setupEventListeners() {
    // Mobile navigation side-drawer toggle
    if (menuToggle && sidebar && sidebarOverlay) {
        menuToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            sidebar.classList.toggle('open');
            sidebarOverlay.classList.toggle('active');
        });

        // Close sidebar on overlay click
        sidebarOverlay.addEventListener('click', () => {
            sidebar.classList.remove('open');
            sidebarOverlay.classList.remove('active');
        });
    }

    // Nav menu switching (helper function)
    window.switchView = (viewId) => {
        if (!viewId) return;
        state.currentView = viewId;

        // Quitar 'active' de todos los botones de navegación y dropdown
        document.querySelectorAll('.nav-item, .dropdown-item').forEach(i => i.classList.remove('active'));

        // Poner 'active' en el botón correspondiente si existe
        const targetBtn = document.querySelector(`[data-view="${viewId}"]`);
        if (targetBtn) {
            targetBtn.classList.add('active');
        }

        // Close mobile menu & user dropdown on view switch
        if (sidebar && sidebarOverlay) {
            sidebar.classList.remove('open');
            sidebarOverlay.classList.remove('active');
        }
        const userDropdown = document.getElementById('user-dropdown');
        if (userDropdown) {
            userDropdown.classList.remove('open');
            document.querySelector('.user-menu-container')?.classList.remove('open');
        }

        // Cambiar vista activa
        contentViews.forEach(view => view.classList.remove('active'));
        const targetView = document.getElementById(`view-${viewId}`);
        if (targetView) targetView.classList.add('active');

        loadActiveView();
    };

    // Registrar clicks para botones con data-view
    document.querySelectorAll('[data-view]').forEach(item => {
        item.addEventListener('click', (e) => {
            const viewId = item.getAttribute('data-view');
            switchView(viewId);
        });
    });

    // Horizon selector tabs
    horizonTabs.forEach(tab => {
        tab.addEventListener('click', async () => {
            horizonTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            state.activeHorizon = tab.getAttribute('data-horizon');
            updateSubtitle();
            if (user) {
                await saveUserPreferences(state.activeProfile, state.activeHorizon);
            }
            loadActiveView();
        });
    });

    // Profile selector tabs
    profileTabs.forEach(tab => {
        tab.addEventListener('click', async () => {
            profileTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            state.activeProfile = tab.getAttribute('data-profile');
            updateSubtitle();
            if (user) {
                await saveUserPreferences(state.activeProfile, state.activeHorizon);
            }
            loadActiveView();
        });
    });

    // Category filter buttons
    categoryFilters.forEach(filter => {
        filter.addEventListener('click', () => {
            categoryFilters.forEach(f => f.classList.remove('active'));
            filter.classList.add('active');

            state.activeCategory = filter.getAttribute('data-category');
            renderTable();
        });
    });

    // Search bar indexing
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            state.searchQuery = e.target.value.toLowerCase();
            renderTable();
        });
    }

    // Manual Refresh button
    if (btnRefresh) {
        btnRefresh.addEventListener('click', triggerManualRefresh);
    }

    // Form Submissions
    const posForm = document.getElementById('add-pos-form');
    if (posForm) {
        posForm.addEventListener('submit', handleAddPositionSubmit);
    }
    const watchForm = document.getElementById('add-watch-form');
    if (watchForm) {
        watchForm.addEventListener('submit', handleAddWatchlistSubmit);
    }

    // ===== TICKER AUTOCOMPLETE =====
    setupTickerAutocomplete();

    // Auth account button binding - toggles dropdown or opens modal
    const navAuthBtn = document.getElementById('nav-auth-btn');
    const userDropdown = document.getElementById('user-dropdown');
    const userMenuContainer = document.querySelector('.user-menu-container');

    if (navAuthBtn) {
        navAuthBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (user) {
                userDropdown.classList.toggle('open');
                userMenuContainer.classList.toggle('open');
            } else {
                document.getElementById('auth-modal').style.display = 'flex';
                document.getElementById('login-form').reset();
                document.getElementById('signup-form').reset();
                document.getElementById('login-error').style.display = 'none';
                document.getElementById('signup-error').style.display = 'none';
                document.getElementById('signup-success').style.display = 'none';
                showLoginForm();
            }
        });
    }

    // Cerrar sesión desde el botón del dropdown
    const btnLogout = document.getElementById('btn-logout');
    if (btnLogout) {
        btnLogout.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (confirm(`¿Desea cerrar la sesión de su cuenta (${user ? user.email : ''})?`)) {
                userDropdown.classList.remove('open');
                userMenuContainer?.classList.remove('open');
                await supabase.auth.signOut();
            }
        });
    }

    // Cerrar dropdown al hacer click afuera
    window.addEventListener('click', () => {
        if (userDropdown && userDropdown.classList.contains('open')) {
            userDropdown.classList.remove('open');
            userMenuContainer?.classList.remove('open');
        }
    });

    // Open Modal button bindings
    const addPosBtn = document.getElementById('btn-add-position');
    if (addPosBtn) {
        addPosBtn.addEventListener('click', () => {
            document.getElementById('add-pos-modal').style.display = 'flex';
        });
    }
    const addWatchBtn = document.getElementById('btn-add-watchlist');
    if (addWatchBtn) {
        addWatchBtn.addEventListener('click', () => {
            document.getElementById('add-watch-modal').style.display = 'flex';
        });
    }

}

// ===== SUPABASE AUTH HELPERS =====

function showLoginForm() {
    document.getElementById('auth-modal-title').textContent = 'Iniciar Sesión';
    document.getElementById('login-form').style.display = '';
    document.getElementById('signup-form').style.display = 'none';
}

function showSignupForm() {
    document.getElementById('auth-modal-title').textContent = 'Crear Cuenta';
    document.getElementById('login-form').style.display = 'none';
    document.getElementById('signup-form').style.display = '';
}

function updateAuthUI() {
    const btnText = document.getElementById('auth-btn-text');
    const arrow = document.querySelector('.user-menu-container .dropdown-arrow');
    const container = document.querySelector('.user-menu-container');
    const dropdown = document.getElementById('user-dropdown');

    if (!btnText) return;
    if (user) {
        btnText.textContent = user.email ? user.email.split('@')[0] : 'Mi Cuenta';
        if (arrow) arrow.style.display = 'block';
    } else {
        btnText.textContent = 'Iniciar Sesión';
        if (arrow) arrow.style.display = 'none';
        if (dropdown) dropdown.classList.remove('open');
        if (container) container.classList.remove('open');

        // Redirigir al dashboard si está en una pestaña privada tras desloguearse
        if (state.currentView === 'portfolio' || state.currentView === 'alerts') {
            if (window.switchView) {
                window.switchView('dashboard');
            }
        }
    }
}

function getAuthHeaders() {
    const headers = { 'Content-Type': 'application/json' };
    if (session && session.access_token) {
        headers['Authorization'] = `Bearer ${session.access_token}`;
    }
    return headers;
}

async function saveUserPreferences(profile, horizon) {
    if (!supabase || !user) return;
    try {
        const base = CONFIG.SUPABASE_URL.replace(/\/$/, '');
        const url = `${base}/rest/v1/profiles?user_id=eq.${user.id}`;
        const headers = {
            'apikey': CONFIG.SUPABASE_ANON_KEY,
            'Authorization': `Bearer ${session.access_token}`,
            'Content-Type': 'application/json',
            'Prefer': 'resolution=merge-duplicates'
        };
        await fetch(url, {
            method: 'PATCH',
            headers,
            body: JSON.stringify({ active_profile: profile, active_horizon: horizon })
        });
    } catch (e) {
        console.warn('saveUserPreferences error:', e);
    }
}

async function loadAndApplyUserPreferences() {
    if (!supabase || !user) return;
    try {
        const base = CONFIG.SUPABASE_URL.replace(/\/$/, '');
        const url = `${base}/rest/v1/profiles?user_id=eq.${user.id}&select=active_profile,active_horizon`;
        const headers = {
            'apikey': CONFIG.SUPABASE_ANON_KEY,
            'Authorization': `Bearer ${session.access_token}`
        };
        const res = await fetch(url, { headers });
        if (res.ok) {
            const data = await res.json();
            if (data && data.length > 0) {
                const prefs = data[0];
                if (prefs.active_profile) {
                    state.activeProfile = prefs.active_profile;
                    profileTabs.forEach(t => {
                        t.classList.toggle('active', t.getAttribute('data-profile') === prefs.active_profile);
                    });
                }
                if (prefs.active_horizon) {
                    state.activeHorizon = prefs.active_horizon;
                    horizonTabs.forEach(t => {
                        t.classList.toggle('active', t.getAttribute('data-horizon') === prefs.active_horizon);
                    });
                }
                updateSubtitle();
            }
        }
    } catch (e) {
        console.warn('loadAndApplyUserPreferences error:', e);
    }
}

function setupAuthListeners() {
    if (!supabase) return;

    // Auth state change (login / logout)
    supabase.auth.onAuthStateChange(async (_event, newSession) => {
        session = newSession;
        user = newSession?.user ?? null;
        updateAuthUI();

        if (user) {
            document.getElementById('auth-modal').style.display = 'none';
            await loadAndApplyUserPreferences();
            loadActiveView();
        } else {
            loadActiveView();
        }
    });

    // Modal close button
    const closeBtn = document.getElementById('auth-modal-close');
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            document.getElementById('auth-modal').style.display = 'none';
        });
    }

    // Toggle between login/signup
    document.getElementById('go-to-signup')?.addEventListener('click', (e) => {
        e.preventDefault();
        showSignupForm();
    });
    document.getElementById('go-to-login')?.addEventListener('click', (e) => {
        e.preventDefault();
        showLoginForm();
    });

    // Login form submit
    document.getElementById('login-form')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('login-email').value.trim();
        const password = document.getElementById('login-password').value;
        const errEl = document.getElementById('login-error');
        errEl.style.display = 'none';

        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) {
            errEl.textContent = error.message;
            errEl.style.display = 'block';
        }
        // Success handled by onAuthStateChange
    });

    // Signup form submit
    document.getElementById('signup-form')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('signup-email').value.trim();
        const password = document.getElementById('signup-password').value;
        const errEl = document.getElementById('signup-error');
        const sucEl = document.getElementById('signup-success');
        errEl.style.display = 'none';
        sucEl.style.display = 'none';

        const { error } = await supabase.auth.signUp({ email, password });
        if (error) {
            errEl.textContent = error.message;
            errEl.style.display = 'block';
        } else {
            sucEl.textContent = '¡Cuenta creada! Por favor revisá tu email para confirmar tu registro.';
            sucEl.style.display = 'block';
        }
    });
}

// Controller routing depending on view
function loadActiveView() {
    updateWatchlistAndAlerts(); // mantener alertas actualizadas

    if (state.currentView === 'portfolio') {
        startPortfolioPolling();
        fetchPortfolio();
    } else {
        stopPortfolioPolling();
        if (state.currentView === 'dashboard') {
            fetchRecommendationsAndOptimize(state.activeProfile);
        } else if (state.currentView === 'analysis') {
            fetchYieldCurve();
        } else if (state.currentView === 'alerts') {
            fetchWatchlistOnly();
        }
    }
}

// Fetch recommendation payload AND dynamic Markowitz allocation weights
async function fetchRecommendationsAndOptimize(profile) {
    const horizon = state.activeHorizon || 'medium';
    showTableLoader();
    try {
        // Cargar recomendaciones
        const recUrl = state.staticMode
            ? `api/recommendations/${profile}-${horizon}.json`
            : `${state.apiBase}/api/recommendations?profile=${profile}&horizon=${horizon}`;

        const recResponse = await fetch(recUrl);
        if (!recResponse.ok) throw new Error('Error al cargar recomendaciones.');
        const recData = await recResponse.json();

        if (recData.status === 'success') {
            state.marketData = recData.results;
            state.updating = recData.updating;
            updateMetadata();
            renderTable();
        }

        // Cargar optimizaciones
        const optUrl = state.staticMode
            ? `api/optimize/${profile}-${horizon}.json`
            : `${state.apiBase}/api/optimize?profile=${profile}&horizon=${horizon}`;

        const optResponse = await fetch(optUrl);
        if (optResponse.ok) {
            const optData = await optResponse.json();
            if (optData.status === 'success') {
                renderOptimalDashboard(optData.optimization);
            }
        }
    } catch (e) {
        console.error('Error fetching dashboard details:', e);
        tableBody.innerHTML = `<tr><td colspan="8" class="text-center" style="color: var(--color-agresivo);"><i class="fa-solid fa-triangle-exclamation"></i> Error al conectar con las cotizaciones.</td></tr>`;
    }
}

// Render dynamic optimization metrics & donut
function renderOptimalDashboard(optimization) {
    const expectedReturn = optimization.expected_return;
    const inflationRef = optimization.inflation_reference || 22.0;
    const beatsInflation = optimization.beats_inflation !== undefined ? optimization.beats_inflation : expectedReturn > inflationRef;
    const spread = optimization.spread_vs_inflation !== undefined ? optimization.spread_vs_inflation : (expectedReturn - inflationRef);

    // Retorno óptimo con contexto inflacionario
    const returnEl = document.getElementById('metric-return');
    returnEl.innerText = `${expectedReturn.toFixed(1)}%`;
    returnEl.style.color = beatsInflation ? 'var(--color-conservador)' : '#ef4444';

    // Agregar indicador de inflación debajo de la métrica de retorno
    const metricReturnCard = returnEl.closest('.metric-card') || returnEl.parentElement.parentElement;
    let infBadge = metricReturnCard.querySelector('.inflation-badge');
    if (!infBadge) {
        infBadge = document.createElement('div');
        infBadge.className = 'inflation-badge';
        infBadge.style.cssText = 'font-size: 11px; margin-top: 4px; font-weight: 600;';
        returnEl.parentElement.appendChild(infBadge);
    }
    if (beatsInflation) {
        infBadge.style.color = 'var(--color-conservador)';
        infBadge.innerHTML = `<i class="fa-solid fa-arrow-up"></i> +${spread.toFixed(1)}% sobre inflación (${inflationRef.toFixed(0)}%)`;
    } else {
        infBadge.style.color = '#ef4444';
        infBadge.innerHTML = `<i class="fa-solid fa-arrow-down"></i> ${spread.toFixed(1)}% bajo inflación (${inflationRef.toFixed(0)}%)`;
    }

    document.getElementById('metric-volatility').innerText = `${optimization.expected_volatility.toFixed(1)}%`;

    const sharpe = optimization.sharpe_ratio;
    document.getElementById('metric-sharpe').innerText = sharpe.toFixed(2);

    // Label explicativo del Sharpe según rango
    const sharpeLabel = document.getElementById('metric-sharpe-label');
    if (sharpeLabel) {
        let labelText, labelColor;
        if (sharpe > 1.0) {
            labelText = '✦ Excelente · riesgo muy bien recompensado';
            labelColor = 'var(--color-conservador)';
        } else if (sharpe > 0.5) {
            labelText = '◎ Aceptable · riesgo razonablemente recompensado';
            labelColor = 'var(--color-moderado)';
        } else if (sharpe > 0) {
            labelText = '△ Bajo · el premio por volatilidad es marginal';
            labelColor = '#f59e0b';
        } else {
            labelText = '✕ Negativo · no supera la inflación de referencia';
            labelColor = '#ef4444';
        }
        sharpeLabel.innerText = labelText;
        sharpeLabel.style.color = labelColor;
    }

    const valueEl = document.getElementById('metric-return');
    if (optimization.profile) valueEl.style.color = beatsInflation ? 'var(--color-conservador)' : '#ef4444';

    const listContainer = document.getElementById('allocation-items');
    listContainer.innerHTML = '';

    const series = [];
    const labels = [];

    optimization.weights.forEach(item => {
        const pct = item.weight_pct;
        series.push(pct);
        labels.push(item.name.replace(' Letra', '').replace(' Bono', '').replace(' Accion', ''));

        let priceStr = '';
        if (state.marketData) {
            let foundAsset = null;
            // Look in categories first
            for (const cat of Object.keys(state.marketData.categories)) {
                foundAsset = state.marketData.categories[cat].find(a => a.ticker === item.ticker);
                if (foundAsset) break;
            }
            // Fallback: look in top_10
            if (!foundAsset && state.marketData.top_10) {
                foundAsset = state.marketData.top_10.find(a => a.ticker === item.ticker);
            }
            if (foundAsset && foundAsset.price) {
                const symb = item.currency === 'ARS' ? '$' : 'u$s';
                priceStr = `${symb} ${foundAsset.price.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
                if (foundAsset.resistance || foundAsset.support) {
                    const parts = [];
                    if (foundAsset.resistance) parts.push(`R: ${symb} ${foundAsset.resistance.toLocaleString('es-AR', { maximumFractionDigits: 2 })}`);
                    if (foundAsset.support) parts.push(`S: ${symb} ${foundAsset.support.toLocaleString('es-AR', { maximumFractionDigits: 2 })}`);
                    priceStr += ` (${parts.join(' · ')})`;
                }
            }
        }

        const div = document.createElement('div');
        div.className = 'allocation-item';
        div.style.cssText = 'cursor: pointer; transition: background 0.2s; padding: 4px 8px; border-radius: 6px;';
        div.innerHTML = `
            <div style="flex-grow: 1;">
                <div style="display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap;">
                    <span class="alloc-name">${item.ticker.replace('.BA', '')} <i class="fa-solid fa-circle-info" style="font-size: 10px; opacity: 0.5; margin-left: 2px;"></i></span>
                    ${priceStr ? `<span class="alloc-price-inline">${priceStr}</span>` : ''}
                </div>
                <div class="alloc-category">${item.category} • ${item.currency}</div>
            </div>
            <div class="alloc-weight-container" style="flex-shrink: 0; min-width: 100px;">
                <span class="alloc-weight" style="color: var(--color-${optimization.profile});">${pct}%</span>
                <div class="alloc-progress-bar">
                    <span class="alloc-progress" style="width: ${pct}%; background: var(--color-${optimization.profile});"></span>
                </div>
            </div>
        `;
        div.addEventListener('click', () => openAssetModal(item.ticker));
        listContainer.appendChild(div);
    });

    renderAllocationPizza(series, labels, optimization.profile);
}

function renderAllocationPizza(series, labels, profile) {
    if (allocationChart) {
        allocationChart.destroy();
    }

    if (series.length === 0) {
        document.getElementById('allocation-chart').innerHTML = `<p style="padding: 40px; color: var(--text-muted); text-align:center;">Sin activos asignados.</p>`;
        return;
    }

    const themeColors = {
        conservador: ['#10b981', '#059669', '#34d399', '#34d399', '#6ee7b7', '#a7f3d0'],
        moderado: ['#3b82f6', '#2563eb', '#1d4ed8', '#60a5fa', '#93c5fd', '#bfdbfe'],
        agresivo: ['#ec4899', '#db2777', '#be185d', '#f472b6', '#fbcfe8', '#fce7f3']
    };

    const colors = themeColors[profile] || themeColors.moderado;

    const options = {
        series: series,
        labels: labels,
        chart: {
            type: 'donut',
            height: 320,
            background: 'transparent',
            foreColor: '#9ca3af'
        },
        stroke: { show: true, colors: ['#0f1420'], width: 2 },
        colors: colors,
        legend: { position: 'bottom', labels: { colors: '#f3f4f6' } },
        dataLabels: { enabled: true, formatter: (val) => Math.round(val) + "%" },
        plotOptions: {
            pie: {
                donut: {
                    size: '65%',
                    labels: {
                        show: true,
                        name: { show: true, fontSize: '13px', color: '#9ca3af' },
                        value: { show: true, fontSize: '18px', fontWeight: 'bold', color: '#f3f4f6', formatter: (val) => val + "%" },
                        total: { show: true, label: 'Capital', color: '#9ca3af', formatter: () => "100%" }
                    }
                }
            }
        },
        tooltip: { theme: 'dark' }
    };

    allocationChart = new ApexCharts(document.querySelector("#allocation-chart"), options);
    allocationChart.render();
}

function renderTable() {
    if (!state.marketData) return;

    const results = state.marketData;
    const cat = state.activeCategory;
    const query = state.searchQuery;

    let assets = [];
    if (cat === 'all') {
        const symbolMap = new Set();
        Object.keys(results.categories).forEach(c => {
            results.categories[c].forEach(asset => {
                if (!symbolMap.has(asset.ticker)) {
                    symbolMap.add(asset.ticker);
                    assets.push(asset);
                }
            });
        });
        results.top_10.forEach(asset => {
            if (!symbolMap.has(asset.ticker)) {
                symbolMap.add(asset.ticker);
                assets.push(asset);
            }
        });
    } else {
        assets = results.categories[cat] || [];
    }

    assets.sort((a, b) => b.score - a.score);

    if (query) {
        assets = assets.filter(item =>
            item.ticker.toLowerCase().includes(query) ||
            item.name.toLowerCase().includes(query)
        );
    }

    tableBody.innerHTML = '';

    if (assets.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="8" class="text-center" style="padding: 30px; color: var(--text-secondary);">No se encontraron activos.</td></tr>`;
        return;
    }

    assets.forEach(asset => {
        const row = document.createElement('tr');
        const isFallback = asset.fallback === true;

        if (isFallback) {
            row.style.opacity = '0.72';
        }

        let trendClass = 'trend-stable';
        let trendIcon = 'fa-minus';
        if (asset.trend && asset.trend.includes('Alcista')) {
            trendClass = 'trend-up';
            trendIcon = 'fa-arrow-trend-up';
        } else if (asset.trend && asset.trend.includes('Bajista')) {
            trendClass = 'trend-down';
            trendIcon = 'fa-arrow-trend-down';
        }

        const currencyBadge = asset.currency === 'USD'
            ? `<span class="badge badge-usd">USD</span>`
            : `<span class="badge badge-ars">ARS</span>`;

        const isBonoOrLetra = asset.category === 'bonos' || asset.category === 'letras';
        const rateLabel = isBonoOrLetra
            ? `TNA: ${(asset.tna * 100).toFixed(1)}%`
            : `Rend 6M: ${(asset.ret_6m * 100).toFixed(1)}%`;

        const scoreCell = isFallback
            ? `<span class="font-bold" style="color: #f59e0b; font-size:12px;">
                 <i class="fa-solid fa-triangle-exclamation" title="Alternativa disponible — condicional al mercado"></i>
                 ${asset.score} / 100
               </span>`
            : `<span class="font-bold" style="color: var(--color-${state.activeProfile});">${asset.score} / 100</span>`;

        row.innerHTML = `
            <td><span class="asset-tag">${asset.ticker.replace('.BA', '')}</span></td>
            <td>
                <div>
                    <div>${asset.name}${isFallback ? ' <span style="font-size:10px;color:#f59e0b;font-weight:600;">· alternativa</span>' : ''}</div>
                    <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">${asset.category} • ${rateLabel}</span>
                </div>
            </td>
            <td>${currencyBadge}</td>
            <td>
                <div class="price-cell">
                    <span class="price-amount">${asset.currency === 'ARS' ? '$' : 'u$s'} ${isBonoOrLetra ? asset.price.toLocaleString('es-AR', { minimumFractionDigits: 2 }) : asset.price.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    ${(asset.support || asset.resistance) ? `<span class="price-levels">${asset.resistance ? '<span class="price-r">R: ' + (asset.currency === 'ARS' ? '$' : 'u$s') + ' ' + asset.resistance.toLocaleString('es-AR', { maximumFractionDigits: 2 }) + '</span>' : ''}${asset.support ? ' <span class="price-s">S: ' + (asset.currency === 'ARS' ? '$' : 'u$s') + ' ' + asset.support.toLocaleString('es-AR', { maximumFractionDigits: 2 }) + '</span>' : ''}</span>` : ''}
                </div>
            </td>
            <td>${(asset.volatility * 100).toFixed(1)}%</td>
            <td>${asset.sharpe ? asset.sharpe.toFixed(2) : 'N/A'}</td>
            <td>${scoreCell}</td>
            <td><span class="trend-badge ${trendClass}"><i class="fa-solid ${trendIcon}"></i> ${asset.trend || 'N/A'}</span></td>
        `;
        row.addEventListener('click', () => openAssetModal(asset.ticker));
        tableBody.appendChild(row);
    });
}

// ===== CLIENT-SIDE LOCAL STORAGE PORTFOLIO HELPERS =====
function getLocalPortfolio() {
    const list = localStorage.getItem('inversiones_portfolio');
    return list ? JSON.parse(list) : [];
}

function saveLocalPortfolio(positions) {
    localStorage.setItem('inversiones_portfolio', JSON.stringify(positions));
}

// Obtener un mapeo de precios desde los datos precargados
function getPriceMapFromMarketData() {
    const map = {};
    if (state.marketData) {
        Object.keys(state.marketData.categories).forEach(cat => {
            state.marketData.categories[cat].forEach(a => {
                map[a.ticker] = a.price;
            });
        });
    }
    return map;
}

// ===== SIMULATED PORTFOLIO METHODS =====
// ===== REAL-TIME POLLING HELPERS =====
function startPortfolioPolling() {
    if (state.portfolioPollingInterval) return;
    state.portfolioPollingInterval = setInterval(() => {
        if (state.currentView === 'portfolio') {
            fetchPortfolio(true); // Polling silencioso
        }
    }, 60000);
}

function stopPortfolioPolling() {
    if (state.portfolioPollingInterval) {
        clearInterval(state.portfolioPollingInterval);
        state.portfolioPollingInterval = null;
    }
}

// ===== LOCAL PORTFOLIO REPORT GENERATOR (Fallback) =====
function generateLocalPortfolioReport(positions, profile, horizon) {
    const totalInvested = positions.reduce((acc, p) => acc + p.invested, 0);
    const totalCurrent = positions.reduce((acc, p) => acc + p.current_value, 0);
    const totalPnl = totalCurrent - totalInvested;
    const totalPnlPct = totalInvested > 0 ? (totalPnl / totalInvested * 100) : 0;

    const categoriesInPortfolio = new Set(positions.map(p => p.category));

    const systemicRiskFactors = [
        {
            id: "arg_macro",
            title: "Transición Macroeconómica Argentina",
            icon: "fa-flag",
            severity: "medium",
            categories: ["merval", "cedears", "bonos", "letras"],
            description: "Argentina transita un proceso de estabilización con reducción gradual de la brecha cambiaria y ancla inflacionaria. Cuidado con activos en pesos (ARS) que rindan por debajo de la inflación anual proyectada (~22%). Enfoque selectivo.",
            impact: "Exposición en general en ARS. Los bonos en USD (soberanos hard-dollar) brindan mayor resguardo cambiario."
        },
        {
            id: "fed_policy",
            title: "Política Monetaria de la Reserva Federal (EE.UU.)",
            icon: "fa-university",
            severity: "medium",
            categories: ["sp500", "cedears", "crypto"],
            description: "La Fed sostiene tasas restrictivas prolongadas. Un pivot hacia tasas bajas desataría rallyes en renta variable global y cripto, mientras una demora seguiría presionando valuaciones tecnológicas.",
            impact: "Sensibilidad directa en CEDEARs de empresas de crecimiento y cryptos."
        },
        {
            id: "crypto_regulation",
            title: "Avance Regulatorio Global en Criptomonedas",
            icon: "fa-bitcoin-sign",
            severity: "high",
            categories: ["crypto"],
            description: "Esquemas normativos globales en debate. Los flujos institucionales vía ETFs spot afirman soportes de mediano plazo, pero la volatilidad residual del halving exige estricta gestión del tamaño de posición.",
            impact: "Volatilidad cíclica aguda. Adecuado solo en porción controlada del portafolio agresivo."
        },
        {
            id: "black_swan_concentration",
            title: "Elevada Concentración de Activos",
            icon: "fa-triangle-exclamation",
            severity: "high",
            categories: ["all"],
            description: "Una o más posiciones representan más del 35% del capital total. Exceso de dependencia en el desempeño de poco instrumental corporativo.",
            impact: "Recomendación de reequilibrio de ponderaciones para amortiguar riesgo no sistémico."
        }
    ];

    const priceMap = getPriceMapFromMarketData();
    const positionsAnalysis = positions.map(pos => {
        const weightPct = totalInvested > 0 ? (pos.invested / totalInvested * 100) : 0;

        let assetData = null;
        if (state.marketData) {
            for (let cat of Object.keys(state.marketData.categories)) {
                const found = state.marketData.categories[cat].find(a => a.ticker === pos.ticker);
                if (found) { assetData = found; break; }
            }
        }

        const rsi = assetData ? (assetData.rsi || 50) : 50;
        const sharpe = assetData ? (assetData.sharpe || 0) : 0.5;
        const score = assetData ? (assetData.score || 50) : 50;
        const volatility = assetData ? (assetData.volatility || 0.25) : 0.25;
        const trend = assetData ? (assetData.trend || "Estable") : "Estable";
        const ret1m = assetData ? (assetData.ret_1m || 0) : 0;

        let recommendation = "MANTENER";
        let recommendation_color = "neutral";
        let rationale = "";

        if (score < 25) {
            recommendation = "VENDER TOTAL";
            recommendation_color = "danger";
            rationale = `Score crítico de ${score.toFixed(0)}/100. Fundamentos macro/técnicos deteriorados para tu perfil.`;
        } else if (rsi > 78 && pos.pnl_pct > 20 && sharpe < 0.2) {
            recommendation = "VENDER TOTAL";
            recommendation_color = "danger";
            rationale = `Sobrecompra extrema detectada (RSI: ${rsi.toFixed(0)}) con ganancia de +${pos.pnl_pct.toFixed(1)}%. Conveniente liquidar posición y concretar retornos.`;
        } else if (rsi > 70 && pos.pnl_pct > 12) {
            recommendation = "VENDER PARCIAL";
            recommendation_color = "warning";
            rationale = `RSI de ${rsi.toFixed(0)} en zona de sobrecompra. Recomendable vender una parte para asegurar ganancias y rebalancear.`;
        } else if (rsi < 42 && sharpe > 0.7 && score > 72) {
            recommendation = "INCREMENTAR";
            recommendation_color = "success";
            rationale = `Valuación técnica en sobreventa táctica con sólido Sharpe de ${sharpe.toFixed(2)}. Oportunidad idónea de acumulación.`;
        } else {
            rationale = `Posición con dinamismo balanceado. Score de ${score.toFixed(0)}/100. Perfil del inversor alineado con el activo.`;
        }

        const riskFlags = [];
        if (rsi > 72) riskFlags.push(`⚠ RSI sobrecompra (${rsi.toFixed(0)})`);
        if (rsi < 28) riskFlags.push(`⚠ RSI sobreventa (${rsi.toFixed(0)})`);
        if (volatility > 0.5) riskFlags.push(`🔥 Volatilidad extrema (${(volatility * 100).toFixed(0)}%)`);
        if (sharpe < 0) riskFlags.push("📉 Sharpe negativo");
        if (weightPct > 35) riskFlags.push(`⚡ Alta concentración (${weightPct.toFixed(0)}%)`);

        return {
            ticker: pos.ticker,
            name: pos.name,
            category: pos.category,
            currency: pos.currency,
            entry_price: pos.entry_price,
            current_price: pos.current_price,
            quantity: pos.quantity,
            invested: pos.invested,
            current_value: pos.current_value,
            pnl: pos.pnl,
            pnl_pct: pos.pnl_pct,
            weight_pct: weightPct,
            recommendation,
            recommendation_color,
            rationale,
            risk_flags: riskFlags,
            technical_snapshot: {
                rsi: rsi,
                sharpe: sharpe,
                volatility_pct: volatility * 100,
                trend: trend,
                score: score,
                ret_1m_pct: ret1m * 100
            }
        };
    });

    const activeRisks = systemicRiskFactors.filter(factor => {
        if (factor.id === "black_swan_concentration") {
            return positionsAnalysis.some(p => p.weight_pct > 35);
        }
        return factor.categories.some(c => categoriesInPortfolio.has(c));
    });

    let overall_action = "MANTENER";
    let overall_rationale = `La cartera se encuentra balanceada y acumula rendimiento total neutro/positivo (+${totalPnlPct.toFixed(2)}%).`;

    const sellTotal = positionsAnalysis.filter(p => p.recommendation === "VENDER TOTAL").length;
    const sellPartial = positionsAnalysis.filter(p => p.recommendation === "VENDER PARCIAL").length;
    const increaseCount = positionsAnalysis.filter(p => p.recommendation === "INCREMENTAR").length;

    if (sellTotal >= 2 || (sellTotal + sellPartial) / positions.length > 0.6) {
        overall_action = "REBALANCEAR";
        overall_rationale = "Elevada proporción de activos con alertas de liquidación. Rotar asignaciones hacia activos conservadores o de mayor score.";
    } else if (totalPnlPct > 15 && sellPartial > 0) {
        overall_action = "PROTEGER GANANCIAS";
        overall_rationale = "Retornos globales atractivos. Realizar tomas de ganancias parciales recomendadas y retener liquidez.";
    } else if (increaseCount >= 2) {
        overall_action = "OPORTUNIDAD DE ACUMULACIÓN";
        overall_rationale = "Múltiples activos sólidos y subvaluados presentan señales claras para incrementar ponderación.";
    }

    // Calcular desglose de categorías
    const categoryBreakdown = [];
    const catMapObj = {};
    positions.forEach(pos => {
        if (!catMapObj[pos.category]) catMapObj[pos.category] = { invested: 0, current: 0, count: 0 };
        catMapObj[pos.category].invested += pos.invested;
        catMapObj[pos.category].current += pos.current_value;
        catMapObj[pos.category].count++;
    });

    Object.keys(catMapObj).forEach(cat => {
        const invested = catMapObj[cat].invested;
        const current = catMapObj[cat].current;
        const pnl = current - invested;
        const pnlPct = invested > 0 ? (pnl / invested * 100) : 0;
        categoryBreakdown.push({
            category: cat,
            invested,
            current_value: current,
            pnl,
            pnl_pct: pnlPct,
            count: catMapObj[cat].count
        });
    });

    return {
        generated_at: new Date().toISOString(),
        profile,
        horizon,
        summary: {
            total_invested: totalInvested,
            total_current: totalCurrent,
            total_pnl: totalPnl,
            total_pnl_pct: totalPnlPct,
            positions_count: positions.length
        },
        overall_action,
        overall_rationale,
        positions_analysis: positionsAnalysis,
        category_breakdown: categoryBreakdown,
        market_context: activeRisks
    };
}

// ===== RENDERIZADO VISUAL EXCLUSIVO DE LA CARTERA =====
function renderCategoryBreakdown(positions, categoryBreakdown) {
    const chartContainer = document.getElementById('portfolio-distribution-section');
    if (!positions || positions.length === 0) {
        chartContainer.style.display = 'none';
        return;
    }
    chartContainer.style.display = 'grid';

    // 1. Renderizar Listado de Categorías y P&L
    const listEl = document.getElementById('portfolio-category-list');
    listEl.innerHTML = '';

    categoryBreakdown.forEach(cat => {
        const pnlClass = cat.pnl >= 0 ? 'text-green' : 'text-red';
        const pnlPctClass = cat.pnl >= 0 ? 'trend-up' : 'trend-down';
        const pnlSign = cat.pnl >= 0 ? '+' : '';

        const itemHtml = `
            <div class="allocation-item" style="display: flex; flex-direction: column; gap: 4px; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.04);">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-weight: 500; text-transform: capitalize;">${cat.category} <span style="font-size:11px; color:var(--text-muted);">(${cat.count} act)</span></span>
                    <strong class="${pnlClass}">$ ${cat.current_value.toLocaleString('es-AR', { maximumFractionDigits: 2 })}</strong>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: var(--text-muted);">
                    <span>Invertido: $ ${cat.invested.toLocaleString('es-AR', { maximumFractionDigits: 2 })}</span>
                    <span class="trend-badge ${pnlPctClass}" style="font-size: 11px;">PnL: ${pnlSign}${cat.pnl_pct.toFixed(2)}%</span>
                </div>
            </div>
        `;
        listEl.insertAdjacentHTML('beforeend', itemHtml);
    });

    // 2. Renderizar Donut Chart
    const pieSeries = categoryBreakdown.map(cat => cat.current_value);
    const pieLabels = categoryBreakdown.map(cat => cat.category.toUpperCase());

    if (window.portfolioCategoryChart) {
        window.portfolioCategoryChart.destroy();
    }

    const options = {
        series: pieSeries,
        labels: pieLabels,
        chart: {
            type: 'donut',
            height: 250,
            background: 'transparent',
            foreColor: '#9ca3af'
        },
        dataLabels: { enabled: false },
        stroke: { show: false },
        plotOptions: {
            pie: {
                donut: {
                    size: '72%',
                    background: 'transparent',
                    labels: {
                        show: true,
                        name: { show: true, fontSize: '14px', fontFamily: 'Outfit', color: '#9ca3af' },
                        value: {
                            show: true,
                            fontSize: '18px',
                            fontFamily: 'Outfit',
                            fontWeight: '600',
                            color: '#ffffff',
                            formatter: function (val) {
                                return "$ " + parseFloat(val).toLocaleString('es-AR', { maximumFractionDigits: 0 });
                            }
                        },
                        total: {
                            show: true,
                            label: 'Total Cartera',
                            color: '#9ca3af',
                            formatter: function (w) {
                                const total = w.globals.seriesTotals.reduce((a, b) => a + b, 0);
                                return "$ " + total.toLocaleString('es-AR', { maximumFractionDigits: 0 });
                            }
                        }
                    }
                }
            }
        },
        theme: {
            monochrome: {
                enabled: true,
                color: '#3b82f6',
                shadeTo: 'dark',
                shadeIntensity: 0.65
            }
        },
        legend: {
            position: 'bottom',
            fontFamily: 'Outfit',
            labels: { colors: '#f3f4f6' }
        },
        tooltip: {
            y: {
                formatter: function (val) {
                    return "$ " + val.toLocaleString('es-AR', { maximumFractionDigits: 2 });
                }
            }
        }
    };

    window.portfolioCategoryChart = new ApexCharts(document.querySelector("#portfolio-category-chart"), options);
    window.portfolioCategoryChart.render();
}

function renderAdvisoryReport(report) {
    const reportSection = document.getElementById('portfolio-report-section');
    if (!report || !report.positions_analysis || report.positions_analysis.length === 0) {
        reportSection.style.display = 'none';
        return;
    }
    reportSection.style.display = 'block';

    // Timestamp
    const dateStr = new Date(report.generated_at).toLocaleDateString('es-AR', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });
    document.getElementById('report-timestamp').innerText = `Actualizado: ${dateStr}`;

    // Overall banner color & icon
    const overallPanel = document.getElementById('portfolio-report-overall');
    let bannerColor = 'rgba(255,255,255,0.06)';
    let borderAccent = 'rgba(255,255,255,0.15)';
    let overallIcon = 'fa-scale-balanced';
    let textAccent = 'var(--text-primary)';

    if (report.overall_action === 'REBALANCEAR' || report.overall_action === 'VENDER TOTAL') {
        bannerColor = 'rgba(239, 68, 68, 0.08)';
        borderAccent = 'rgba(239, 68, 68, 0.25)';
        overallIcon = 'fa-triangle-exclamation';
        textAccent = '#ef4444';
    } else if (report.overall_action === 'PROTEGER GANANCIAS') {
        bannerColor = 'rgba(245, 158, 11, 0.08)';
        borderAccent = 'rgba(245, 158, 11, 0.25)';
        overallIcon = 'fa-shield-halved';
        textAccent = '#f59e0b';
    } else if (report.overall_action === 'OPORTUNIDAD DE ACUMULACIÓN') {
        bannerColor = 'rgba(16, 185, 129, 0.08)';
        borderAccent = 'rgba(16, 185, 129, 0.25)';
        overallIcon = 'fa-circle-arrow-up';
        textAccent = '#10b981';
    }

    overallPanel.innerHTML = `
        <div style="background: ${bannerColor}; border: 1px solid ${borderAccent}; border-radius: 12px; padding: 16px 20px; display: flex; gap: 16px; align-items: flex-start;">
            <div style="background: rgba(255,255,255,0.03); border-radius: 10px; width: 44px; height: 44px; display: flex; align-items: center; justify-content: center; font-size: 20px; color: ${textAccent}; flex-shrink: 0;">
                <i class="fa-solid ${overallIcon}"></i>
            </div>
            <div>
                <span style="font-size: 11px; text-transform: uppercase; color: var(--text-muted); font-weight: 600; letter-spacing: 0.5px;">Veredicto de Cartera</span>
                <h4 style="font-size: 16px; font-weight: 700; margin: 2px 0 6px 0; color: ${textAccent};">${report.overall_action}</h4>
                <p style="font-size:13px; color: var(--text-secondary); margin: 0; line-height: 1.5;">${report.overall_rationale}</p>
            </div>
        </div>
    `;

    // Recommendations list
    const activeList = document.getElementById('report-active-list');
    activeList.innerHTML = '';

    report.positions_analysis.forEach(pos => {
        let badgeColor = 'rgba(255,255,255,0.06)';
        let badgeText = '#9ca3af';

        if (pos.recommendation.includes('VENDER TOTAL')) {
            badgeColor = 'rgba(239, 68, 68, 0.12)';
            badgeText = '#ef4444';
        } else if (pos.recommendation.includes('VENDER PARCIAL')) {
            badgeColor = 'rgba(245, 158, 11, 0.12)';
            badgeText = '#f59e0b';
        } else if (pos.recommendation.includes('INCREMENTAR')) {
            badgeColor = 'rgba(16, 185, 129, 0.12)';
            badgeText = '#10b981';
        }

        const riskFlagsHtml = pos.risk_flags.map(f => `<span class="flag-pill">${f}</span>`).join(' ');

        const cardHtml = `
            <div class="report-item-card glass-panel" style="padding: 16px; border: 1px solid rgba(255,255,255,0.03); border-radius: 12px; background: rgba(30, 41, 59, 0.2);">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px;">
                    <div>
                        <span class="asset-tag" style="font-size: 11px;">${pos.ticker.replace('.BA', '')}</span>
                        <span style="font-size: 12px; color: var(--text-muted); text-transform: uppercase; margin-left: 8px;">${pos.category}</span>
                    </div>
                    <span style="font-size: 11px; font-weight: 600; padding: 4px 10px; border-radius: 9999px; background: ${badgeColor}; color: ${badgeText};">${pos.recommendation}</span>
                </div>
                
                <h5 style="margin: 0 0 6px 0; font-size: 14px; font-weight: 600;">${pos.name}</h5>
                <p style="font-size: 13px; color: var(--text-secondary); margin: 0 0 12px 0; line-height: 1.4;">${pos.rationale}</p>
                
                ${pos.risk_flags.length > 0 ? `<div style="display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px;">${riskFlagsHtml}</div>` : ''}
                
                <div style="display: grid; grid-template-columns: repeat(4, 1fr); padding: 8px 10px; background: rgba(0,0,0,0.15); border-radius: 8px; font-size: 11px; color: var(--text-muted); text-align: center; gap: 6px;">
                    <div>RSI: <strong style="color:var(--text-primary); display:block;">${pos.technical_snapshot.rsi.toFixed(1)}</strong></div>
                    <div>Sharpe: <strong style="color:var(--text-primary); display:block;">${pos.technical_snapshot.sharpe.toFixed(2)}</strong></div>
                    <div>Vol: <strong style="color:var(--text-primary); display:block;">${pos.technical_snapshot.volatility_pct.toFixed(0)}%</strong></div>
                    <div>Score: <strong style="color:var(--text-primary); display:block;">${pos.technical_snapshot.score.toFixed(0)}</strong></div>
                </div>
            </div>
        `;
        activeList.insertAdjacentHTML('beforeend', cardHtml);
    });

    // Systemic Risks
    const marketList = document.getElementById('report-market-context');
    marketList.innerHTML = '';

    if (!report.market_context || report.market_context.length === 0) {
        marketList.innerHTML = `<div style="text-align: center; color: var(--text-muted); font-size: 13px; padding: 20px;">Sin riesgos severos ponderados para la cartera actual.</div>`;
        return;
    }

    report.market_context.forEach(risk => {
        let riskColor = '#f59e0b';
        let riskBg = 'rgba(245, 158, 11, 0.06)';
        let riskBorder = 'rgba(245, 158, 11, 0.15)';

        if (risk.severity === 'high') {
            riskColor = '#ef4444';
            riskBg = 'rgba(239, 68, 68, 0.06)';
            riskBorder = 'rgba(239, 68, 68, 0.15)';
        }

        const riskHtml = `
            <div style="background: ${riskBg}; border: 1px solid ${riskBorder}; border-radius: 12px; padding: 14px 16px;">
                <div style="display: flex; align-items: center; gap: 8px; color: ${riskColor}; font-weight: 600; font-size: 13px; margin-bottom: 6px;">
                    <i class="fa-solid ${risk.icon || 'fa-triangle-exclamation'}"></i>
                    <span>${risk.title}</span>
                </div>
                <p style="font-size: 12px; color: var(--text-secondary); margin: 0; line-height: 1.4;">${risk.description}</p>
                <div style="font-size: 11px; color: var(--text-muted); margin-top: 6px; padding-top: 6px; border-top: 1px dashed rgba(255,255,255,0.05);">
                    <strong>Impacto: </strong>${risk.impact}
                </div>
            </div>
        `;
        marketList.insertAdjacentHTML('beforeend', riskHtml);
    });
}

// ===== SIMULATED PORTFOLIO METHODS =====
async function fetchPortfolio(isSilent = false) {
    if (!isSilent) {
        const tbody = document.getElementById('portfolio-tbody');
        tbody.innerHTML = `<tr><td colspan="9" class="text-center" style="padding: 40px;"><i class="fa-solid fa-spinner fa-spin fa-2x"></i><br><br>Cargando posiciones...</td></tr>`;
    }

    if (state.staticMode) {
        if (!state.marketData) {
            try {
                const recRes = await fetch(`api/recommendations/${state.activeProfile}.json`);
                const recD = await recRes.json();
                state.marketData = recD.results;
            } catch (e) {
                console.error("No se pudo precargar tabla de precios para la cartera.");
            }
        }

        const localPos = getLocalPortfolio();
        const priceMap = getPriceMapFromMarketData();

        let totalInvested = 0;
        let totalCurrent = 0;
        const enriched = [];

        localPos.forEach(pos => {
            const current = priceMap[pos.ticker] || pos.entry_price;
            const invested = pos.entry_price * pos.quantity;
            const current_value = current * pos.quantity;
            const pnl = current_value - invested;
            const pnl_pct = invested > 0 ? (pnl / invested * 100) : 0;

            totalInvested += invested;
            totalCurrent += current_value;

            enriched.push({
                ...pos,
                current_price: current,
                invested: invested,
                current_value: current_value,
                pnl: pnl,
                pnl_pct: pnl_pct
            });
        });

        const totalPnl = totalCurrent - totalInvested;
        const totalPnlPct = totalInvested > 0 ? (totalPnl / totalInvested * 100) : 0;

        const mockResponse = {
            positions: enriched,
            summary: {
                total_invested: totalInvested,
                total_current: totalCurrent,
                total_pnl: totalPnl,
                total_pnl_pct: totalPnlPct
            }
        };

        renderPortfolioHTML(mockResponse);

        // Generar informe de cartera local client-side
        if (enriched.length > 0) {
            const localReport = generateLocalPortfolioReport(enriched, state.activeProfile, state.activeHorizon);
            renderAdvisoryReport(localReport);
        } else {
            renderAdvisoryReport(null);
        }
        return;
    }

    try {
        const response = await fetch(`${state.apiBase}/api/portfolio`, {
            headers: getAuthHeaders()
        });
        const data = await response.json();

        if (data.status === 'success') {
            renderPortfolioHTML(data);

            // Consultar endpoint de informe del Backend
            if (data.positions && data.positions.length > 0) {
                try {
                    const repRes = await fetch(`${state.apiBase}/api/portfolio/report?profile=${state.activeProfile}&horizon=${state.activeHorizon}`, {
                        headers: getAuthHeaders()
                    });
                    const repData = await repRes.json();
                    if (repData.status === 'success') {
                        renderAdvisoryReport(repData.report);
                    }
                } catch (errReport) {
                    console.error("Error al cargar informe del backend:", errReport);
                    renderAdvisoryReport(null);
                }
            } else {
                renderAdvisoryReport(null);
            }
        }
    } catch (e) {
        if (!isSilent) {
            const tbody = document.getElementById('portfolio-tbody');
            tbody.innerHTML = `<tr><td colspan="9" class="text-center" style="color: #ef4444;"><i class="fa-solid fa-triangle-exclamation"></i> Error al cargar datos de cartera.</td></tr>`;
        }
    }
}

function renderPortfolioHTML(data) {
    const tbody = document.getElementById('portfolio-tbody');
    document.getElementById('pf-invested').innerText = `$ ${data.summary.total_invested.toLocaleString('es-AR', { maximumFractionDigits: 2 })}`;
    document.getElementById('pf-current').innerText = `$ ${data.summary.total_current.toLocaleString('es-AR', { maximumFractionDigits: 2 })}`;

    const pnl = data.summary.total_pnl;
    const pnlLabel = document.getElementById('pf-pnl');
    pnlLabel.innerText = `${pnl >= 0 ? '+' : ''}$ ${pnl.toLocaleString('es-AR', { maximumFractionDigits: 2 })} (${data.summary.total_pnl_pct.toFixed(2)}%)`;
    pnlLabel.style.color = pnl >= 0 ? '#10b981' : '#ef4444';

    tbody.innerHTML = '';
    if (data.positions.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" class="text-center" style="padding:30px; color:var(--text-secondary);">La cartera está vacía. Agregue posiciones para comenzar a trackear.</td></tr>`;
        renderCategoryBreakdown([], []);
        return;
    }

    data.positions.forEach(pos => {
        const tr = document.createElement('tr');
        const pnlPos = pos.pnl;
        const pnlClass = pnlPos >= 0 ? 'trend-up' : 'trend-down';
        const pnlSign = pnlPos >= 0 ? '+' : '';

        tr.innerHTML = `
            <td><span class="asset-tag">${pos.ticker.replace('.BA', '')}</span></td>
            <td><div>${pos.name}</div><span style="font-size:10px; color:var(--text-muted); text-transform:uppercase;">${pos.category}</span></td>
            <td>${pos.quantity}</td>
            <td>${pos.currency} ${pos.entry_price.toFixed(2)}</td>
            <td>${pos.currency} ${pos.current_price.toFixed(2)}</td>
            <td>$ ${pos.invested.toLocaleString('es-AR', { maximumFractionDigits: 2 })}</td>
            <td>$ ${pos.current_value.toLocaleString('es-AR', { maximumFractionDigits: 2 })}</td>
            <td><span class="trend-badge ${pnlClass}">${pnlSign}${pos.pnl_pct.toFixed(2)}%</span></td>
            <td><button class="delete-btn" data-id="${pos.id}"><i class="fa-solid fa-trash"></i></button></td>
        `;

        tr.addEventListener('click', (e) => {
            if (e.target.closest('.delete-btn')) return;
            openAssetModal(pos.ticker);
        });

        tr.querySelector('.delete-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            handleDeletePosition(pos.id);
        });
        tbody.appendChild(tr);
    });

    // Generar breakdown de categorías
    const catMap = {};
    data.positions.forEach(pos => {
        if (!catMap[pos.category]) {
            catMap[pos.category] = { category: pos.category, count: 0, invested: 0, current_value: 0 };
        }
        catMap[pos.category].count++;
        catMap[pos.category].invested += pos.invested;
        catMap[pos.category].current_value += pos.current_value;
    });

    const categoryBreakdown = Object.values(catMap).map(c => {
        const pnl = c.current_value - c.invested;
        const pnl_pct = c.invested > 0 ? (pnl / c.invested * 100) : 0;
        return {
            ...c,
            pnl,
            pnl_pct
        };
    }).sort((a, b) => b.pnl_pct - a.pnl_pct);

    renderCategoryBreakdown(data.positions, categoryBreakdown);
}

async function handleAddPositionSubmit(e) {
    e.preventDefault();
    const tickerVal = document.getElementById('pos-ticker').value.toUpperCase();
    const payload = {
        ticker: tickerVal,
        name: document.getElementById('pos-name').value,
        category: document.getElementById('pos-category').value,
        currency: document.getElementById('pos-currency').value,
        entry_price: parseFloat(document.getElementById('pos-price').value),
        quantity: parseFloat(document.getElementById('pos-qty').value)
    };

    if (state.staticMode) {
        const localPos = getLocalPortfolio();
        const randId = Math.random().toString(36).substr(2, 9);
        localPos.push({
            id: randId,
            ...payload,
            entry_date: new Date().toISOString().split('T')[0],
            timestamp: Date.now() / 1000
        });
        saveLocalPortfolio(localPos);
        document.getElementById('add-pos-modal').style.display = 'none';
        document.getElementById('add-pos-form').reset();
        fetchPortfolio();
        return;
    }

    try {
        const res = await fetch(`${state.apiBase}/api/portfolio`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.status === 'success') {
            document.getElementById('add-pos-modal').style.display = 'none';
            document.getElementById('add-pos-form').reset();
            fetchPortfolio();
        }
    } catch (er) {
        alert('Error al guardar la posición.');
    }
}

async function handleDeletePosition(id) {
    if (!confirm('¿Desea eliminar esta transacción simulada de su portafolio?')) return;

    if (state.staticMode) {
        const localPos = getLocalPortfolio();
        const filtered = localPos.filter(p => p.id !== id);
        saveLocalPortfolio(filtered);
        fetchPortfolio();
        return;
    }

    try {
        const res = await fetch(`${state.apiBase}/api/portfolio/${id}`, {
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        const data = await res.json();
        if (data.status === 'success') {
            fetchPortfolio();
        }
    } catch (e) {
        alert('Error al borrar la transacción.');
    }
}

// ===== RENTA FIJA INTEREST CURVE METHODS =====
async function fetchYieldCurve() {
    const tbody = document.getElementById('yield-tbody');
    tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 40px;"><i class="fa-solid fa-spinner fa-spin fa-2x"></i><br><br>Cargando rendimientos...</td></tr>`;

    try {
        const url = state.staticMode ? 'api/yield-curve.json' : `${state.apiBase}/api/yield-curve`;
        const response = await fetch(url);
        const data = await response.json();

        if (data.status === 'success') {
            tbody.innerHTML = '';
            const allItems = [...data.letras, ...data.bonos];
            if (allItems.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 20px; color: var(--text-secondary);">No hay cotizaciones de renta fija disponibles.</td></tr>`;
                return;
            }

            allItems.forEach(item => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><span class="asset-tag">${item.ticker}</span></td>
                    <td>${item.name}</td>
                    <td class="font-bold" style="color:var(--color-conservador);">${item.tna_pct}%</td>
                    <td>${item.maturity}</td>
                    <td>${item.days_to_maturity} días</td>
                    <td><span class="badge ${item.currency === 'USD' ? 'badge-usd' : 'badge-ars'}">${item.currency}</span></td>
                    <td>${item.currency === 'ARS' ? '$' : 'u$s'} ${item.price.toLocaleString('es-AR', { maximumFractionDigits: 2 })}</td>
                `;
                tr.addEventListener('click', () => openAssetModal(item.ticker));
                tbody.appendChild(tr);
            });

            renderCurveChart(data.letras, data.bonos);
        }
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="color:#ef4444;"><i class="fa-solid fa-triangle-exclamation"></i> Error de carga en renta fija.</td></tr>`;
    }
}

function renderCurveChart(letras, bonos) {
    if (yieldCurveChart) {
        yieldCurveChart.destroy();
    }

    const dataLetras = letras.map(l => ({ x: l.days_to_maturity, y: l.tna_pct, label: l.ticker }));
    const dataBonos = bonos.map(b => ({ x: b.days_to_maturity, y: b.tna_pct, label: b.ticker }));

    const options = {
        series: [
            { name: 'Letras (LECAPs/Pesos)', data: dataLetras },
            { name: 'Bonos Soberanos', data: dataBonos }
        ],
        chart: {
            type: 'scatter',
            height: 380,
            background: 'transparent',
            foreColor: '#9ca3af',
            toolbar: { show: true }
        },
        colors: ['#10b981', '#3b82f6'],
        xaxis: {
            tickAmount: 10,
            title: { text: 'Días hasta el Vencimiento (Plazo)', style: { color: '#9ca3af' } },
            labels: { formatter: (val) => Math.round(val) + " d" }
        },
        yaxis: {
            title: { text: 'Tasa Nominal Anual (TNA) %', style: { color: '#9ca3af' } },
            labels: { formatter: (val) => val.toFixed(1) + "%" }
        },
        markers: { size: 10, strokeWidth: 1, strokeColors: '#07090e' },
        tooltip: {
            custom: function ({ series, seriesIndex, dataPointIndex, w }) {
                const point = w.config.series[seriesIndex].data[dataPointIndex];
                return `<div class="yield-tooltip" style="padding:10px; background:#0f1420; border:1px solid rgba(255,255,255,0.1); border-radius:6px; font-family: Outfit, sans-serif;">
                    <div style="font-weight:bold; margin-bottom:4px; color:#f3f4f6">${point.label}</div>
                    <div style="font-size:12px; color:var(--text-secondary);">TNA Rend: <strong style="color:#10b981">${point.y}%</strong></div>
                    <div style="font-size:12px; color:var(--text-secondary);">Plazo: <strong>${point.x} días</strong></div>
                </div>`;
            }
        },
        legend: { position: 'top', labels: { colors: '#f3f4f6' } },
        grid: { borderColor: 'rgba(255,255,255,0.04)' }
    };

    yieldCurveChart = new ApexCharts(document.querySelector("#yield-curve-chart"), options);
    yieldCurveChart.render();
}

// ===== CLIENT-SIDE LOCAL STORAGE WATCHLIST HELPERS =====
function getLocalWatchlist() {
    const list = localStorage.getItem('inversiones_watchlist');
    return list ? JSON.parse(list) : [];
}

function saveLocalWatchlist(watchlist) {
    localStorage.setItem('inversiones_watchlist', JSON.stringify(watchlist));
}

// Simular chequeo de alertas técnicas client-side
function checkLocalAlerts(watchlist, marketData) {
    if (!marketData) return [];

    // Crear lookup map de activos
    const map = {};
    Object.keys(marketData.categories).forEach(cat => {
        marketData.categories[cat].forEach(a => {
            map[a.ticker] = a;
        });
    });

    const parsedAlerts = [];

    watchlist.forEach(item => {
        const rules = item.alert_rules || {};
        const asset = map[item.ticker];

        if (!asset || !rules) return;

        const rsi = asset.rsi || 50;
        const price = asset.price || 0;
        const vol = asset.volatility || 0.20;

        if (rules.rsi_below !== undefined && rsi < rules.rsi_below) {
            parsedAlerts.push({
                ticker: item.ticker,
                name: item.name,
                type: "RSI Sobreventa",
                icon: "fa-arrow-down",
                color: "warning",
                message: `El RSI marcó ${rsi.toFixed(1)} (umbral: ${rules.rsi_below}). Oportunidad técnica.`,
                current_value: rsi,
                threshold: rules.rsi_below
            });
        }
        if (rules.rsi_above !== undefined && rsi > rules.rsi_above) {
            parsedAlerts.push({
                ticker: item.ticker,
                name: item.name,
                type: "RSI Sobrecompra",
                icon: "fa-arrow-up",
                color: "danger",
                message: `El RSI marcó ${rsi.toFixed(1)} (umbral: ${rules.rsi_above}). Sobrecompra.`,
                current_value: rsi,
                threshold: rules.rsi_above
            });
        }
        if (rules.price_below !== undefined && price < rules.price_below) {
            parsedAlerts.push({
                ticker: item.ticker,
                name: item.name,
                type: "Precio Bajo Umbral",
                icon: "fa-tag",
                color: "success",
                message: `Precio actual ${price.toFixed(2)} cayó debajo del límite de $${rules.price_below}.`,
                current_value: price,
                threshold: rules.price_below
            });
        }
        if (rules.price_above !== undefined && price > rules.price_above) {
            parsedAlerts.push({
                ticker: item.ticker,
                name: item.name,
                type: "Precio Sobre Umbral",
                icon: "fa-rocket",
                color: "success",
                message: `Precio actual ${price.toFixed(2)} rebasó tu objetivo de $${rules.price_above}.`,
                current_value: price,
                threshold: rules.price_above
            });
        }
        if (rules.volatility_above !== undefined && vol > rules.volatility_above) {
            parsedAlerts.push({
                ticker: item.ticker,
                name: item.name,
                type: "Alta Volatilidad",
                icon: "fa-wave-square",
                color: "warning",
                message: `Volatilidad anualizada en ${(vol * 100).toFixed(1)}% superando el ${(rules.volatility_above * 100).toFixed(1)}% configurado.`,
                current_value: vol,
                threshold: rules.volatility_above
            });
        }
    });

    return parsedAlerts;
}

// ===== WATCHLIST AND ALERTS TRIGGERING =====
async function updateWatchlistAndAlerts() {
    if (state.staticMode) {
        // Cargar recomendaciones si no están cargadas previamente
        if (!state.marketData) {
            try {
                const recRes = await fetch(`api/recommendations/${state.activeProfile}.json`);
                const recD = await recRes.json();
                state.marketData = recD.results;
            } catch (e) {
                console.error("No se pudo precargar data de alertas.");
                return;
            }
        }

        const watchlist = getLocalWatchlist();
        const activeAlerts = checkLocalAlerts(watchlist, state.marketData);

        const badge = document.getElementById('alert-count-badge');
        if (badge) {
            const cnt = activeAlerts.length;
            if (cnt > 0) {
                badge.innerText = cnt;
                badge.style.display = 'inline-block';
            } else {
                badge.style.display = 'none';
            }
        }

        if (state.currentView === 'alerts') {
            renderAlertsView(watchlist, activeAlerts);
        }
        return;
    }

    try {
        const response = await fetch(`${state.apiBase}/api/watchlist`, {
            headers: getAuthHeaders()
        });
        const data = await response.json();

        if (data.status === 'success') {
            const badge = document.getElementById('alert-count-badge');
            if (badge) {
                const cnt = data.alerts.length;
                if (cnt > 0) {
                    badge.innerText = cnt;
                    badge.style.display = 'inline-block';
                } else {
                    badge.style.display = 'none';
                }
            }

            if (state.currentView === 'alerts') {
                renderAlertsView(data.watchlist, data.alerts);
            }
        }
    } catch (e) {
        console.error('Error fetching watchlist data:', e);
    }
}

async function fetchWatchlistOnly() {
    updateWatchlistAndAlerts();
}

function renderAlertsView(watchlist, alerts) {
    const alertDiv = document.getElementById('active-alerts');
    alertDiv.innerHTML = '';

    if (alerts.length === 0) {
        alertDiv.innerHTML = `
            <div class="alert-card alert-success" style="border:1px solid rgba(16, 185, 129, 0.2)">
                <i class="fa-solid fa-circle-check"></i>
                <div>
                    <strong class="alert-card-title">Sin Alertas Disparadas</strong>
                    <p style="margin:0; opacity:0.8;">Todos los instrumentos de la watchlist cotizan dentro de sus rangos normales.</p>
                </div>
            </div>
        `;
    } else {
        alerts.forEach(al => {
            const card = document.createElement('div');
            card.className = `alert-card alert-${al.color}`;
            card.innerHTML = `
                <i class="fa-solid ${al.icon}"></i>
                <div>
                    <strong class="alert-card-title">${al.ticker} – ${al.type}</strong>
                    <p style="margin:0; opacity:0.8;">${al.message}</p>
                </div>
                <span class="alert-card-action alert-${al.color}">ALERTA</span>
            `;
            card.addEventListener('click', () => openAssetModal(al.ticker));
            alertDiv.appendChild(card);
        });
    }

    const tbody = document.getElementById('watchlist-tbody');
    tbody.innerHTML = '';

    if (watchlist.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center" style="padding: 24px; color: var(--text-secondary);">La watchlist está vacía. Configure reglas para activos clave.</td></tr>`;
        return;
    }

    watchlist.forEach(item => {
        const rules = [];
        if (item.alert_rules.rsi_below) rules.push(`RSI < ${item.alert_rules.rsi_below}`);
        if (item.alert_rules.rsi_above) rules.push(`RSI > ${item.alert_rules.rsi_above}`);
        if (item.alert_rules.price_below) rules.push(`Precio < $${item.alert_rules.price_below}`);
        if (item.alert_rules.price_above) rules.push(`Precio > $${item.alert_rules.price_above}`);
        if (item.alert_rules.volatility_above) rules.push(`Vol > ${item.alert_rules.volatility_above * 100}%`);

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><span class="asset-tag">${item.ticker}</span></td>
            <td>${item.name}</td>
            <td style="text-transform:uppercase; font-size:11px;">${item.category}</td>
            <td><span style="font-size:12px; color:var(--text-secondary);">${rules.join(' | ') || 'Monitoreo Base (Sin reglas)'}</span></td>
            <td><button class="delete-btn" data-ticker="${item.ticker}"><i class="fa-solid fa-trash"></i></button></td>
        `;

        tr.addEventListener('click', (e) => {
            if (e.target.closest('.delete-btn')) return;
            openAssetModal(item.ticker);
        });

        tr.querySelector('.delete-btn').addEventListener('click', () => handleDeleteWatchlist(item.ticker));
        tbody.appendChild(tr);
    });
}

async function handleAddWatchlistSubmit(e) {
    e.preventDefault();
    const tickerVal = document.getElementById('watch-ticker').value.toUpperCase();
    const rules = {};
    const rsiBel = document.getElementById('watch-rsi-below').value;
    if (rsiBel) rules.rsi_below = parseFloat(rsiBel);
    const rsiAb = document.getElementById('watch-rsi-above').value;
    if (rsiAb) rules.rsi_above = parseFloat(rsiAb);
    const pBel = document.getElementById('watch-price-below').value;
    if (pBel) rules.price_below = parseFloat(pBel);
    const pAb = document.getElementById('watch-price-above').value;
    if (pAb) rules.price_above = parseFloat(pAb);
    const volAb = document.getElementById('watch-vol-above').value;
    if (volAb) rules.volatility_above = parseFloat(volAb) / 100.0;

    const payload = {
        ticker: tickerVal,
        name: document.getElementById('watch-name').value,
        category: document.getElementById('watch-category').value,
        alert_rules: rules
    };

    if (state.staticMode) {
        const localWatch = getLocalWatchlist();
        const existing = localWatch.findIndex(w => w.ticker === tickerVal);
        if (existing !== -1) {
            localWatch[existing].alert_rules = rules;
        } else {
            localWatch.push(payload);
        }
        saveLocalWatchlist(localWatch);
        document.getElementById('add-watch-modal').style.display = 'none';
        document.getElementById('add-watch-form').reset();
        updateWatchlistAndAlerts();
        return;
    }

    try {
        const res = await fetch(`${state.apiBase}/api/watchlist`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.status === 'success') {
            document.getElementById('add-watch-modal').style.display = 'none';
            document.getElementById('add-watch-form').reset();
            updateWatchlistAndAlerts();
        }
    } catch (er) {
        alert('Error al guardar en la watchlist.');
    }
}

async function handleDeleteWatchlist(ticker) {
    if (!confirm(`¿Eliminar ${ticker} de su lista de alertas?`)) return;

    if (state.staticMode) {
        const localWatch = getLocalWatchlist();
        const filtered = localWatch.filter(w => w.ticker !== ticker);
        saveLocalWatchlist(filtered);
        updateWatchlistAndAlerts();
        return;
    }

    try {
        const res = await fetch(`${state.apiBase}/api/watchlist/${ticker}`, {
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        const data = await res.json();
        if (data.status === 'success') {
            updateWatchlistAndAlerts();
        }
    } catch (e) {
        alert('Error al borrar de la watchlist.');
    }
}

// ===== REFRESH CONTROLLER =====
async function triggerManualRefresh() {
    if (state.updating || state.staticMode) return;

    btnRefresh.disabled = true;
    btnRefresh.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Actualizando...`;

    try {
        await fetch(`${state.apiBase}/api/refresh`, { method: 'POST' });
        checkRefreshStatus();
    } catch (e) {
        console.error('Error triggering refresh:', e);
        btnRefresh.disabled = false;
        btnRefresh.innerHTML = `<i class="fa-solid fa-rotate"></i> Actualizar`;
    }
}

async function checkRefreshStatus() {
    try {
        const res = await fetch(`${state.apiBase}/api/health`);
        const data = await res.json();

        if (data.updating) {
            setTimeout(checkRefreshStatus, 3000);
        } else {
            btnRefresh.disabled = false;
            btnRefresh.innerHTML = `<i class="fa-solid fa-rotate"></i> Actualizar`;
            loadActiveView();
        }
    } catch (e) {
        btnRefresh.disabled = false;
        btnRefresh.innerHTML = `<i class="fa-solid fa-rotate"></i> Actualizar`;
    }
}

function showTableLoader() {
    tableBody.innerHTML = `<tr><td colspan="8" class="text-center" style="padding: 40px;"><i class="fa-solid fa-circle-notch fa-spin fa-2x"></i><br><br>Modelando asignaciones dinámicas óptimas...</td></tr>`;
}

function updateMetadata() {
    const now = new Date();
    updateTimeSpan.innerText = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')} (${now.toLocaleDateString()})`;
}

// ===== DETAIL MODAL DIALOGS =====
const modal = document.getElementById('asset-modal');
const modalClose = document.getElementById('modal-close');
if (modalClose) {
    modalClose.addEventListener('click', closeModal);
}
if (modal) {
    modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
}
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });

function closeModal() {
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = '';
    }
}

async function openAssetModal(ticker) {
    if (!modal) return;
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';

    document.getElementById('modal-body').innerHTML = `
        <div class="modal-loader">
            <i class="fa-solid fa-circle-notch fa-spin fa-2x"></i>
            <p>Generando análisis detallado...</p>
        </div>
    `;

    document.getElementById('modal-ticker').innerText = ticker.replace('.BA', '').replace('-USD', '');
    document.getElementById('modal-name').innerText = '';
    document.getElementById('modal-verdict').style.display = 'none';
    // Reset price badge so it doesn't show stale data or empty box
    const priceBadge = document.getElementById('modal-current-price');
    if (priceBadge) { priceBadge.innerText = ''; priceBadge.style.display = 'none'; }

    try {
        const safeTicker = ticker.replace("/", "_");
        const analysisUrl = state.staticMode
            ? `api/asset-analysis/${state.activeProfile}-${state.activeHorizon}/${safeTicker}.json`
            : `${state.apiBase}/api/asset-analysis?ticker=${encodeURIComponent(ticker)}&profile=${state.activeProfile}&horizon=${state.activeHorizon}`;

        const res = await fetch(analysisUrl);
        const data = await res.json();

        if (data.status === 'success') {
            renderModalContent(data.analysis);
        } else {
            document.getElementById('modal-body').innerHTML = `<p style="color:#ef4444; text-align:center; padding:30px;"><i class="fa-solid fa-triangle-exclamation"></i> ${data.message || 'Error al obtener análisis.'}</p>`;
        }
    } catch (e) {
        document.getElementById('modal-body').innerHTML = `<p style="color:#ef4444; text-align:center; padding:30px;"><i class="fa-solid fa-triangle-exclamation"></i> Error al cargar el análisis estático.</p>`;
    }
}
window.openAssetModal = openAssetModal;

function renderModalContent(analysis) {
    document.getElementById('modal-ticker').innerText = analysis.ticker.replace('.BA', '').replace('-USD', '');
    document.getElementById('modal-name').innerText = analysis.name;

    const catBadge = document.getElementById('modal-category-badge');
    catBadge.innerText = analysis.category.toUpperCase();
    catBadge.className = `badge ${analysis.currency === 'USD' ? 'badge-usd' : 'badge-ars'}`;

    // Poblar metadatos: sector y año de cotización
    const meta = ASSET_METADATA[analysis.ticker] || ASSET_METADATA[analysis.ticker.replace('.BA', '')] || null;
    const sectorEl = document.getElementById('modal-sector-text');
    const ipoEl = document.getElementById('modal-ipo-text');
    const metaRow = document.getElementById('modal-sector')?.parentElement;
    if (meta) {
        if (sectorEl) sectorEl.innerText = meta.sector;
        if (ipoEl) ipoEl.innerText = meta.ipo;
        if (metaRow) metaRow.style.display = 'flex';
    } else {
        if (metaRow) metaRow.style.display = 'none';
    }

    // Mostrar precio actual en el header del modal
    const priceEl = document.getElementById('modal-current-price');
    if (priceEl) {
        if (analysis.price) {
            const sym = analysis.currency === 'ARS' ? '$' : 'u$s';
            priceEl.innerText = `${sym} ${analysis.price.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            priceEl.style.display = 'inline-block';
        } else {
            priceEl.style.display = 'none';
        }
    }

    document.getElementById('modal-profile-name').innerText = analysis.profile;
    document.getElementById('modal-score-value').innerText = `${analysis.score} / 100`;

    const scoreFill = document.getElementById('modal-score-fill');
    scoreFill.style.width = `${analysis.score}%`;
    scoreFill.style.background = `var(--color-${analysis.profile})`;

    const verdict = analysis.verdict;
    const verdictEl = document.getElementById('modal-verdict');
    verdictEl.style.display = 'flex';
    verdictEl.className = `modal-verdict verdict-${verdict.color}`;
    document.getElementById('modal-verdict-icon').className = `fa-solid ${verdict.icon}`;
    document.getElementById('modal-verdict-action').innerText = verdict.action;
    document.getElementById('modal-verdict-summary').innerHTML = formatMarkdownBold(verdict.summary);

    const body = document.getElementById('modal-body');

    // Inyectar Grid de Límites (TP/SL) y Niveles Clave (Soporte/Resistencia/POC)
    const currencySymbol = analysis.currency === 'ARS' ? '$' : 'u$s';
    body.innerHTML = `
        <div class="modal-stats-grid">
            <div class="modal-stat-card">
                <div class="modal-stat-title"><i class="fa-solid fa-crosshairs"></i> Límites Sugeridos</div>
                <div class="modal-stat-row">
                    <span class="modal-stat-label">Take Profit (TP):</span>
                    <span class="modal-stat-value" style="color: var(--color-conservador);">${currencySymbol} ${analysis.take_profit.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (+${analysis.tp_pct}%)</span>
                </div>
                <div class="modal-stat-row">
                    <span class="modal-stat-label">Stop Loss (SL):</span>
                    <span class="modal-stat-value" style="color: #ef4444;">${currencySymbol} ${analysis.stop_loss.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (-${analysis.sl_pct}%)</span>
                </div>
            </div>
            <div class="modal-stat-card">
                <div class="modal-stat-title"><i class="fa-solid fa-layer-group"></i> Estructura de Precios</div>
                <div class="modal-stat-row">
                    <span class="modal-stat-label">Resistencia:</span>
                    <span class="modal-stat-value" style="color: #ef4444;">${currencySymbol} ${analysis.resistance.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                </div>
                <div class="modal-stat-row">
                    <span class="modal-stat-label">Punto de Control (POC):</span>
                    <span class="modal-stat-value" style="color: var(--color-moderado);">${currencySymbol} ${analysis.volume_cluster.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                </div>
                <div class="modal-stat-row">
                    <span class="modal-stat-label">Soporte:</span>
                    <span class="modal-stat-value" style="color: var(--color-conservador);">${currencySymbol} ${analysis.support.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                </div>
            </div>
        </div>
    `;

    if (analysis.technical && analysis.technical.length > 0) {
        body.innerHTML += `<div class="analysis-section-title"><i class="fa-solid fa-chart-line"></i> Análisis Técnico</div>`;
        analysis.technical.forEach(section => { body.innerHTML += renderAnalysisCard(section); });
    }

    if (analysis.fundamental && analysis.fundamental.length > 0) {
        body.innerHTML += `<div class="analysis-section-title"><i class="fa-solid fa-scale-balanced"></i> Análisis Fundamental</div>`;
        analysis.fundamental.forEach(section => { body.innerHTML += renderAnalysisCard(section); });
    }

    if (analysis.macro && analysis.macro.length > 0) {
        body.innerHTML += `<div class="analysis-section-title"><i class="fa-solid fa-globe"></i> Contexto Macroeconómico</div>`;
        analysis.macro.forEach(section => { body.innerHTML += renderAnalysisCard(section); });
    }

    if (analysis.balances) {
        body.innerHTML += renderBalanceSection(analysis.balances);
    }
}

function renderBalanceSection(balances) {
    if (!balances || !balances.snapshots || balances.snapshots.length === 0) return '';

    const snapshots = balances.snapshots;
    const summary = balances.summary;

    // Color de la conclusión del resumen
    const conclusionColorMap = {
        'success': { border: 'var(--color-conservador)', bg: 'rgba(16, 185, 129, 0.08)', icon: 'fa-circle-check', textColor: 'var(--color-conservador)' },
        'neutral': { border: 'var(--color-moderado)', bg: 'rgba(59, 130, 246, 0.08)', icon: 'fa-circle-info', textColor: 'var(--color-moderado)' },
        'warning': { border: '#f59e0b', bg: 'rgba(245, 158, 11, 0.08)', icon: 'fa-triangle-exclamation', textColor: '#f59e0b' }
    };
    const conclusionStyle = conclusionColorMap[summary.conclusion_color] || conclusionColorMap['neutral'];

    // Métricas del resumen
    const avgRevStr = summary.avg_revenue_b !== null ? `$${summary.avg_revenue_b.toFixed(1)}B` : '—';
    const avgMarginStr = summary.avg_net_margin_pct !== null ? `${summary.avg_net_margin_pct.toFixed(1)}%` : '—';
    const avgEpsStr = summary.avg_eps !== null ? `$${summary.avg_eps.toFixed(2)}` : '—';

    const trendArrow = (trend) => {
        if (trend === 'creciente' || trend === 'en expansión') return '<span style="color: var(--color-conservador);">↑</span>';
        if (trend === 'decreciente' || trend === 'en contracción') return '<span style="color: #ef4444;">↓</span>';
        return '<span style="color: var(--text-muted);">→</span>';
    };

    // Renderizar snapshots trimestrales
    let snapshotCards = '';
    snapshots.forEach((snap, idx) => {
        const revStr = snap.revenue_b !== null ? `$${snap.revenue_b.toFixed(1)}B` : '—';
        const niStr = snap.net_income_b !== null ? `$${snap.net_income_b.toFixed(1)}B` : '—';
        const marginStr = snap.net_margin_pct !== null ? `${snap.net_margin_pct.toFixed(1)}%` : '—';
        const epsStr = snap.eps !== null ? `$${snap.eps.toFixed(2)}` : '—';
        const fcfStr = snap.fcf_b !== null ? `$${snap.fcf_b.toFixed(1)}B` : '—';
        const deStr = snap.debt_equity !== null ? snap.debt_equity.toFixed(2) : '—';

        const marginColor = snap.net_margin_pct !== null
            ? (snap.net_margin_pct >= 15 ? 'var(--color-conservador)' : snap.net_margin_pct < 5 ? '#ef4444' : '#f59e0b')
            : 'var(--text-muted)';

        const fcfColor = snap.fcf_b !== null
            ? (snap.fcf_b >= 0 ? 'var(--color-conservador)' : '#ef4444')
            : 'var(--text-muted)';

        const favorableBadges = snap.favorable.map(f =>
            `<span class="balance-badge balance-badge-positive"><i class="fa-solid fa-check"></i> ${f}</span>`
        ).join('');
        const criticalBadges = snap.critical.map(c =>
            `<span class="balance-badge balance-badge-critical"><i class="fa-solid fa-triangle-exclamation"></i> ${c}</span>`
        ).join('');

        const hasBadges = snap.favorable.length > 0 || snap.critical.length > 0;

        snapshotCards += `
        <div class="balance-snapshot-card">
            <div class="balance-snapshot-header">
                <span class="balance-period-label">${snap.period}</span>
                <span class="balance-idx-badge">#${idx + 1}</span>
            </div>
            <div class="balance-metrics-grid">
                <div class="balance-metric-item">
                    <span class="balance-metric-label">Ingresos</span>
                    <span class="balance-metric-value">${revStr}</span>
                </div>
                <div class="balance-metric-item">
                    <span class="balance-metric-label">Utilidad Neta</span>
                    <span class="balance-metric-value">${niStr}</span>
                </div>
                <div class="balance-metric-item">
                    <span class="balance-metric-label">Margen Neto</span>
                    <span class="balance-metric-value" style="color: ${marginColor};">${marginStr}</span>
                </div>
                <div class="balance-metric-item">
                    <span class="balance-metric-label">EPS</span>
                    <span class="balance-metric-value">${epsStr}</span>
                </div>
                <div class="balance-metric-item">
                    <span class="balance-metric-label">FCF</span>
                    <span class="balance-metric-value" style="color: ${fcfColor};">${fcfStr}</span>
                </div>
                <div class="balance-metric-item">
                    <span class="balance-metric-label">Deuda/Equity</span>
                    <span class="balance-metric-value">${deStr}</span>
                </div>
            </div>
            ${hasBadges ? `<div class="balance-badges-row">${favorableBadges}${criticalBadges}</div>` : ''}
        </div>`;
    });

    // Card del resumen final
    const summaryCard = `
    <div class="balance-summary-card" style="border-color: ${conclusionStyle.border}; background: ${conclusionStyle.bg};">
        <div class="balance-summary-header">
            <i class="fa-solid ${conclusionStyle.icon}" style="color: ${conclusionStyle.textColor}; font-size: 18px;"></i>
            <span class="balance-summary-title">Promedio de ${summary.periods_analyzed} Balances:
                <strong style="color: ${conclusionStyle.textColor};">${summary.conclusion}</strong>
            </span>
        </div>
        <div class="balance-summary-metrics">
            <div class="balance-summary-metric">
                <span class="balance-metric-label">Ingresos Promedio</span>
                <span class="balance-metric-value">${avgRevStr} ${trendArrow(summary.revenue_trend)}</span>
                <span class="balance-trend-label">${summary.revenue_trend}</span>
            </div>
            <div class="balance-summary-metric">
                <span class="balance-metric-label">Margen Promedio</span>
                <span class="balance-metric-value">${avgMarginStr} ${trendArrow(summary.margin_trend)}</span>
                <span class="balance-trend-label">${summary.margin_trend}</span>
            </div>
            <div class="balance-summary-metric">
                <span class="balance-metric-label">EPS Promedio</span>
                <span class="balance-metric-value">${avgEpsStr}</span>
            </div>
            <div class="balance-summary-metric">
                <span class="balance-metric-label">Señales ✅ / ⚠️</span>
                <span class="balance-metric-value">
                    <span style="color: var(--color-conservador);">${summary.total_favorable_signals} fav.</span>
                    /
                    <span style="color: #f59e0b;">${summary.total_critical_signals} crít.</span>
                </span>
            </div>
        </div>
        <p class="balance-summary-detail">${summary.conclusion_detail}</p>
    </div>`;

    return `
    <div class="analysis-section-title"><i class="fa-solid fa-file-invoice-dollar"></i> Análisis de Balances (Últimos ${snapshots.length} Trimestres)</div>
    <div class="balance-snapshots-container">
        ${snapshotCards}
    </div>
    ${summaryCard}`;
}


function renderAnalysisCard(section) {
    const statusClass = `analysis-status-${section.status || 'neutral'}`;
    const valueHtml = section.value ? `<span class="analysis-card-value ${statusClass}">${section.value}</span>` : '';

    return `
        <div class="analysis-card">
            <div class="analysis-card-header">
                <div class="analysis-card-title">
                    <i class="fa-solid ${section.icon || 'fa-circle-info'}"></i>
                    ${section.title}
                </div>
                ${valueHtml}
            </div>
            <div class="analysis-card-content">
                ${formatMarkdownBold(section.content)}
            </div>
        </div>
    `;
}

function formatMarkdownBold(text) {
    if (!text) return '';
    return text.replace(/\*\*(.*?)\*\"/g, '<strong>$1</strong>');
}

function setupTickerAutocomplete() {
    const tickerInput = document.getElementById('pos-ticker');
    const nameInput = document.getElementById('pos-name');
    const categorySelect = document.getElementById('pos-category');

    if (!tickerInput) return;

    // Create the dropdown as a child of <body> for portal positioning
    let suggestionsBox = document.getElementById('ticker-suggestions-portal');
    if (!suggestionsBox) {
        suggestionsBox = document.createElement('div');
        suggestionsBox.id = 'ticker-suggestions-portal';
        suggestionsBox.className = 'ticker-suggestions-dropdown';
        document.body.appendChild(suggestionsBox);
    }

    function positionDropdown() {
        const rect = tickerInput.getBoundingClientRect();
        suggestionsBox.style.position = 'fixed';
        suggestionsBox.style.top = (rect.bottom + 4) + 'px';
        suggestionsBox.style.left = rect.left + 'px';
        suggestionsBox.style.width = rect.width + 'px';
        suggestionsBox.style.zIndex = '99999';
    }

    function guessCategory(ticker) {
        if (ticker.endsWith('-USD')) return 'crypto';
        if (/^(AL|GD|AE)\d{2}/.test(ticker) && ticker.endsWith('.BA')) return 'bonos';
        if (/^[sStT]\d{2}[a-zA-Z]\d/.test(ticker)) return 'letras';
        if (ticker.endsWith('.BA')) {
            const merval = ['YPFD', 'GGAL', 'PAMP', 'ALUA', 'TXAR', 'BMA', 'CEPU', 'TGSU2', 'EDN', 'LOMA', 'CRES', 'TECO2', 'SUPV', 'VALO', 'BYMA'];
            return merval.includes(ticker.replace('.BA', '')) ? 'merval' : 'cedears';
        }
        return 'sp500';
    }

    function hideSuggestions() {
        suggestionsBox.style.display = 'none';
        suggestionsBox.innerHTML = '';
    }

    function showSuggestions(query) {
        suggestionsBox.innerHTML = '';
        if (!query || query.length < 1) {
            hideSuggestions();
            return;
        }

        const q = query.toUpperCase();

        const matches = Object.entries(ASSET_METADATA)
            .filter(([ticker, meta]) =>
                ticker.toUpperCase().startsWith(q) ||
                meta.company.toUpperCase().includes(q)
            )
            .slice(0, 8);

        if (matches.length === 0) {
            hideSuggestions();
            return;
        }

        matches.forEach(([ticker, meta]) => {
            const item = document.createElement('div');
            item.className = 'ticker-suggestion-item';
            item.innerHTML = `
                <span class="ticker-suggestion-symbol">${ticker}</span>
                <span class="ticker-suggestion-name">${meta.company}</span>
                <span class="ticker-suggestion-sector">${meta.sector}</span>
            `;
            item.addEventListener('mousedown', (e) => {
                e.preventDefault();
                tickerInput.value = ticker;
                if (nameInput) nameInput.value = meta.company;
                if (categorySelect) categorySelect.value = guessCategory(ticker);
                hideSuggestions();
                if (nameInput) nameInput.focus();
            });
            suggestionsBox.appendChild(item);
        });

        positionDropdown();
        suggestionsBox.style.display = 'block';
    }

    tickerInput.addEventListener('input', () => showSuggestions(tickerInput.value.trim()));
    tickerInput.addEventListener('focus', () => {
        if (tickerInput.value.trim().length > 0) showSuggestions(tickerInput.value.trim());
    });
    tickerInput.addEventListener('blur', () => setTimeout(hideSuggestions, 150));

    // Reposition on scroll/resize
    window.addEventListener('scroll', positionDropdown, true);
    window.addEventListener('resize', () => {
        if (suggestionsBox.style.display === 'block') positionDropdown();
    });

    // Close on outside click
    document.addEventListener('mousedown', (e) => {
        if (!tickerInput.contains(e.target) && !suggestionsBox.contains(e.target)) {
            hideSuggestions();
        }
    });
}

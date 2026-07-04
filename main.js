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
    apiBase: 'http://localhost:8000'
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

    // Nav menu switching
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            navItems.forEach(i => i.classList.remove('active'));
            item.classList.add('active');

            // Close mobile menu on view switch
            if (sidebar && sidebarOverlay) {
                sidebar.classList.remove('open');
                sidebarOverlay.classList.remove('active');
            }

            const viewId = item.getAttribute('data-view');
            state.currentView = viewId;

            contentViews.forEach(view => view.classList.remove('active'));
            document.getElementById(`view-${viewId}`).classList.add('active');

            loadActiveView();
        });
    });

    // Horizon selector tabs
    horizonTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            horizonTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            state.activeHorizon = tab.getAttribute('data-horizon');
            updateSubtitle();
            loadActiveView();
        });
    });

    // Profile selector tabs
    profileTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            profileTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            state.activeProfile = tab.getAttribute('data-profile');
            updateSubtitle();
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

// Controller routing depending on view
function loadActiveView() {
    updateWatchlistAndAlerts(); // mantener alertas actualizadas

    if (state.currentView === 'dashboard') {
        fetchRecommendationsAndOptimize(state.activeProfile);
    } else if (state.currentView === 'portfolio') {
        fetchPortfolio();
    } else if (state.currentView === 'analysis') {
        fetchYieldCurve();
    } else if (state.currentView === 'alerts') {
        fetchWatchlistOnly();
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

        const itemHTML = `
            <div class="allocation-item" onclick="openAssetModal('${item.ticker}')" style="cursor: pointer; transition: background 0.2s; padding: 4px 8px; border-radius: 6px;">
                <div style="flex-grow: 1;">
                    <span class="alloc-name">${item.ticker.replace('.BA', '')} <i class="fa-solid fa-circle-info" style="font-size: 10px; opacity: 0.5; margin-left: 2px;"></i></span>
                    <div class="alloc-category">${item.category} • ${item.currency}</div>
                </div>
                <div class="alloc-weight-container" style="flex-shrink: 0; min-width: 100px;">
                    <span class="alloc-weight" style="color: var(--color-${optimization.profile});">${pct}%</span>
                    <div class="alloc-progress-bar">
                        <span class="alloc-progress" style="width: ${pct}%; background: var(--color-${optimization.profile});"></span>
                    </div>
                </div>
            </div>
        `;
        listContainer.insertAdjacentHTML('beforeend', itemHTML);
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
        let trendClass = 'trend-stable';
        let trendIcon = 'fa-minus';
        if (asset.trend.includes('Alcista')) {
            trendClass = 'trend-up';
            trendIcon = 'fa-arrow-trend-up';
        } else if (asset.trend.includes('Bajista')) {
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

        row.innerHTML = `
            <td><span class="asset-tag">${asset.ticker.replace('.BA', '')}</span></td>
            <td>
                <div>
                    <div>${asset.name}</div>
                    <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">${asset.category} • ${rateLabel}</span>
                </div>
            </td>
            <td>${currencyBadge}</td>
            <td class="font-bold">${isBonoOrLetra ? asset.price.toLocaleString('es-AR', { minimumFractionDigits: 2 }) : asset.price.toFixed(2)}</td>
            <td>${(asset.volatility * 100).toFixed(1)}%</td>
            <td>${asset.sharpe ? asset.sharpe.toFixed(2) : 'N/A'}</td>
            <td><span class="font-bold" style="color: var(--color-${state.activeProfile});">${asset.score} / 100</span></td>
            <td><span class="trend-badge ${trendClass}"><i class="fa-solid ${trendIcon}"></i> ${asset.trend}</span></td>
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
async function fetchPortfolio() {
    const tbody = document.getElementById('portfolio-tbody');
    tbody.innerHTML = `<tr><td colspan="9" class="text-center" style="padding: 40px;"><i class="fa-solid fa-spinner fa-spin fa-2x"></i><br><br>Cargando posiciones...</td></tr>`;

    // Si estamos en modo estático, usar LocalStorage
    if (state.staticMode) {
        // Cargar precios de mercado primero si no están en state
        if (!state.marketData) {
            try {
                const recRes = await fetch(`api/recommendations/${state.activeProfile}.json`);
                const recD = await recRes.json();
                state.marketData = recD.results;
            } catch (e) {
                console.error("No se pudo precargar tabla de precios para cartera estática.");
            }
        }

        const localPos = getLocalPortfolio();
        const priceMap = getPriceMapFromMarketData();

        // Simular cálculo de P&L exactamente como el backend
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

        renderPortfolioHTML({
            positions: enriched,
            summary: {
                total_invested: totalInvested,
                total_current: totalCurrent,
                total_pnl: totalPnl,
                total_pnl_pct: totalPnlPct
            }
        });
        return;
    }

    try {
        const response = await fetch(`${state.apiBase}/api/portfolio`);
        const data = await response.json();

        if (data.status === 'success') {
            renderPortfolioHTML(data);
        }
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="9" class="text-center" style="color: #ef4444;"><i class="fa-solid fa-triangle-exclamation"></i> Error al cargar datos de cartera.</td></tr>`;
    }
}

function renderPortfolioHTML(data) {
    const tbody = document.getElementById('portfolio-tbody');
    document.getElementById('pf-invested').innerText = `$ ${data.summary.total_invested.toLocaleString('es-AR', { maximumFractionDigits: 2 })}`;
    document.getElementById('pf-current').innerText = `$ ${data.summary.total_current.toLocaleString('es-AR', { maximumFractionDigits: 2 })}`;

    const pnl = data.summary.total_pnl;
    const pnlLabel = document.getElementById('pf-pnl');
    pnlLabel.innerText = `${pnl >= 0 ? '+' : ''}$ ${pnl.toLocaleString('es-AR', { maximumFractionDigits: 2 })} (${data.summary.total_pnl_pct.toFixed(2)}%)`;
    pnlLabel.style.color = pnl >= 0 ? 'var(--color-conservador)' : '#ef4444';

    tbody.innerHTML = '';
    if (data.positions.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" class="text-center" style="padding:30px; color:var(--text-secondary);">La cartera está vacía. Agregue posiciones para comenzar a trackear.</td></tr>`;
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

        tr.querySelector('.delete-btn').addEventListener('click', () => handleDeletePosition(pos.id));
        tbody.appendChild(tr);
    });
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
            headers: { 'Content-Type': 'application/json' },
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
        const res = await fetch(`${state.apiBase}/api/portfolio/${id}`, { method: 'DELETE' });
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
        const response = await fetch(`${state.apiBase}/api/watchlist`);
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
            headers: { 'Content-Type': 'application/json' },
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
        const res = await fetch(`${state.apiBase}/api/watchlist/${ticker}`, { method: 'DELETE' });
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

    document.getElementById('modal-ticker').innerText = ticker.replace('.BA', '');
    document.getElementById('modal-name').innerText = '';
    document.getElementById('modal-verdict').style.display = 'none';

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

function renderModalContent(analysis) {
    document.getElementById('modal-ticker').innerText = analysis.ticker.replace('.BA', '');
    document.getElementById('modal-name').innerText = analysis.name;

    const catBadge = document.getElementById('modal-category-badge');
    catBadge.innerText = analysis.category.toUpperCase();
    catBadge.className = `badge ${analysis.currency === 'USD' ? 'badge-usd' : 'badge-ars'}`;

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

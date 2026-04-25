const API_URL = '/api';

// Application State
let isLoginMode = true;
let currentUser = null;
let isAdmin = false;
let editingZoneId = null;

// Map State
let userMap = null;
let adminMap = null;
let userMarker = null;
let userRadiusCircle = null;
let activeIncidentMarkers = [];
let heatmapLayer = null;
let geoZoneLayers = [];
let adminZoneLayers = [];

// Tracking State
let lastKnownLocation = null;
let lastUpdateTime = Date.now();
let currentAlertZone = null; // Prevents alert spam
let watchId = null;

// Timers & Cooldowns
let sosCooldown = false;
let refreshInterval = null;
let timeTrackerInterval = null;
let heatmapInterval = null;

// DOM Elements
const loader = document.getElementById('loader');
const navbar = document.getElementById('navbar');
const roleLabel = document.getElementById('role-label');
const authView = document.getElementById('auth-view');
const userDashboard = document.getElementById('user-dashboard');
const adminDashboard = document.getElementById('admin-dashboard');

const authMsg = document.getElementById('auth-msg');
const dashMsg = document.getElementById('dash-msg');
const adminMsg = document.getElementById('admin-msg');

window.onload = () => {
    const userStr = localStorage.getItem('sv_user');
    const token = localStorage.getItem('sv_token');
    if (userStr && token) {
        currentUser = JSON.parse(userStr);
        isAdmin = currentUser.role === 'admin';
        routeDashboard();
    }
};

/* ================= UTILS ================= */

const showLoader = () => loader.classList.remove('hidden');
const hideLoader = () => loader.classList.add('hidden');

function showMessage(el, text, type) {
    el.textContent = text;
    el.className = `msg ${type}`;
    if (type === 'error') {
        setTimeout(() => { if (el.textContent === text) el.textContent = ''; }, 5000);
    }
}

// Custom Toast Notification System
function showToast(message, type = 'high', icon = '⚠️') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type.toLowerCase()}`;
    toast.innerHTML = `<span class="toast-icon">${icon}</span> <span>${message}</span>`;
    container.appendChild(toast);
    
    // Auto remove after animation finishes (0.3s in + 4.5s wait + 0.5s out)
    setTimeout(() => {
        if(container.contains(toast)) container.removeChild(toast);
    }, 5500);
}

function getDistanceFromLatLonInM(lat1, lon1, lat2, lon2) {
    const R = 6371000;
    const dLat = (lat2-lat1) * Math.PI / 180;
    const dLon = (lon2-lon1) * Math.PI / 180;
    const a = 
        Math.sin(dLat/2) * Math.sin(dLat/2) +
        Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * 
        Math.sin(dLon/2) * Math.sin(dLon/2); 
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a)); 
    return R * c;
}

function getAuthHeaders() {
    const token = localStorage.getItem('sv_token');
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
    };
}

function handleFetchError(res) {
    if (res.status === 401 || res.status === 403) {
        logout();
        showMessage(authMsg, 'Session expired or unauthorized. Please login again.', 'error');
        throw new Error('Unauthorized');
    }
}

function validateApiResponse(data, requiredFields = []) {
    if (!data || data.status !== 'success' || !data.data) return false;
    for (let field of requiredFields) {
        if (data.data[field] === undefined) return false;
    }
    return true;
}

/* ================= AUTHENTICATION ================= */

function switchAuth(mode) {
    isLoginMode = mode === 'login';
    document.getElementById('tab-login').classList.toggle('active', isLoginMode);
    document.getElementById('tab-register').classList.toggle('active', !isLoginMode);
    
    const nameInput = document.getElementById('name');
    if (isLoginMode) {
        nameInput.classList.add('hidden');
        nameInput.removeAttribute('required');
        document.getElementById('auth-submit').textContent = 'Login';
    } else {
        nameInput.classList.remove('hidden');
        nameInput.setAttribute('required', 'true');
        document.getElementById('auth-submit').textContent = 'Register';
    }
    authMsg.textContent = '';
}

async function handleAuth(e) {
    e.preventDefault();
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;
    const name = document.getElementById('name').value.trim();

    const endpoint = isLoginMode ? '/login' : '/register';
    const payload = isLoginMode ? { email, password } : { name, email, password };

    showLoader();
    try {
        const res = await fetch(`${API_URL}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        hideLoader();

        if (data.status === 'success') {
            if (isLoginMode) {
                currentUser = { 
                    id: data.data.user_id, 
                    name: data.data.name, 
                    email: email,
                    role: data.data.role 
                };
                isAdmin = currentUser.role === 'admin';
                localStorage.setItem('sv_user', JSON.stringify(currentUser));
                localStorage.setItem('sv_token', data.data.token);
                routeDashboard();
            } else {
                showMessage(authMsg, 'Registration successful. Please login.', 'success');
                switchAuth('login');
            }
        } else {
            showMessage(authMsg, data.error, 'error');
        }
    } catch (err) {
        hideLoader();
        showMessage(authMsg, 'Network error. Backend down?', 'error');
    }
}

function logout() {
    localStorage.removeItem('sv_user');
    localStorage.removeItem('sv_token');
    currentUser = null;
    isAdmin = false;
    lastKnownLocation = null;
    currentAlertZone = null;
    if (watchId) {
        navigator.geolocation.clearWatch(watchId);
        watchId = null;
    }
    
    if (refreshInterval) clearInterval(refreshInterval);
    if (timeTrackerInterval) clearInterval(timeTrackerInterval);
    if (heatmapInterval) clearInterval(heatmapInterval);
    
    navbar.classList.add('hidden');
    userDashboard.classList.add('hidden');
    adminDashboard.classList.add('hidden');
    authView.classList.remove('hidden');
    
    document.getElementById('email').value = '';
    document.getElementById('password').value = '';
    
    if (userMap) { userMap.remove(); userMap = null; }
    if (adminMap) { 
        if (heatmapLayer) {
            adminMap.removeLayer(heatmapLayer);
            heatmapLayer = null;
        }
        adminMap.remove(); 
        adminMap = null; 
    }
}

function routeDashboard() {
    authView.classList.add('hidden');
    navbar.classList.remove('hidden');
    
    if (isAdmin) {
        roleLabel.textContent = 'AUTHORITY ADMIN';
        roleLabel.style.color = 'var(--danger)';
        adminDashboard.classList.remove('hidden');
        initAdminDashboard();
    } else {
        roleLabel.textContent = 'USER';
        roleLabel.style.color = 'var(--primary)';
        userDashboard.classList.remove('hidden');
        initUserDashboard();
    }
}

/* ================= USER DASHBOARD LOGIC ================= */

function initUserDashboard() {
    document.getElementById('user-name').textContent = currentUser.name;
    if (!userMap) initUserMap();
    
    setTimeout(() => {
        if (userMap) userMap.invalidateSize();
        useCurrentLocation();
    }, 300);
    
    if (refreshInterval) clearInterval(refreshInterval);
    refreshInterval = setInterval(checkRisk, 10000);
    
    if (timeTrackerInterval) clearInterval(timeTrackerInterval);
    timeTrackerInterval = setInterval(() => {
        let diff = Math.floor((Date.now() - lastUpdateTime) / 1000);
        document.getElementById('last-updated').textContent = `Last updated: ${diff}s ago`;
    }, 1000);
}

function initUserMap() {
    userMap = L.map('user-map').setView([17.3850, 78.4867], 12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(userMap);
    
    loadPublicZones();
}

async function loadPublicZones() {
    try {
        const res = await fetch(`${API_URL}/zones/public`, { headers: getAuthHeaders() });
        handleFetchError(res);
        const data = await res.json();
        if(data.status === 'success') {
            geoZoneLayers.forEach(l => userMap.removeLayer(l));
            geoZoneLayers = [];
            
            data.data.zones.forEach(zone => {
                let color = '#2ed573'; // Default safe
                let typeStr = zone.type;
                
                if (zone.type === 'RESTRICTED') color = '#ff0000';
                else if (zone.risk_level === 'HIGH') color = '#ffa500';
                else if (zone.risk_level === 'MEDIUM') color = '#ffff00';
                
                const circle = L.circle([zone.latitude, zone.longitude], {
                    color: color,
                    fillColor: color,
                    fillOpacity: 0.2,
                    weight: 2
                }).addTo(userMap);
                
                circle.bindTooltip(`<b>${zone.name}</b><br>Type: ${zone.type}<br>Risk: ${zone.risk_level}`, { sticky: true });
                geoZoneLayers.push(circle);
            });
        }
    } catch (e) {
        if(e.message !== 'Unauthorized') console.error("Failed to load zones", e);
    }
}

function updateUserMap(lat, lon) {
    if (!userMap) return;
    const pos = [lat, lon];
    
    // Smooth transition
    userMap.flyTo(pos, 15, { animate: true, duration: 1.5 });
    
    if (userMarker) {
        userMarker.setLatLng(pos);
        if(userRadiusCircle) userRadiusCircle.setLatLng(pos);
    } else {
        const userIcon = L.divIcon({
            className: 'custom-div-icon',
            html: `<div style="background:var(--primary); width:15px; height:15px; border-radius:50%; border:2px solid white; box-shadow:0 0 15px var(--primary);"></div>`,
            iconSize: [15, 15]
        });
        userMarker = L.marker(pos, {icon: userIcon}).addTo(userMap);
        userRadiusCircle = L.circle(pos, { radius: 500, color: '#ff4757', weight: 1, fillColor: '#ff4757', fillOpacity: 0.15 }).addTo(userMap);
    }
}

function useCurrentLocation() {
    if (navigator.geolocation) {
        showMessage(dashMsg, 'Acquiring GPS signal...', 'success');
        if (watchId) navigator.geolocation.clearWatch(watchId);
        watchId = navigator.geolocation.watchPosition(
            (pos) => {
                const lat = pos.coords.latitude;
                const lon = pos.coords.longitude;
                document.getElementById('lat').value = lat.toFixed(6);
                document.getElementById('lon').value = lon.toFixed(6);
                showMessage(dashMsg, 'GPS tracking active.', 'success');
                updateUserMap(lat, lon);
                checkRisk();
            },
            (err) => {
                showMessage(dashMsg, 'GPS access denied/failed. Using fallback location.', 'error');
                // Fallback location (Hyderabad Default)
                const fallbackLat = 17.3850;
                const fallbackLon = 78.4867;
                document.getElementById('lat').value = fallbackLat.toFixed(6);
                document.getElementById('lon').value = fallbackLon.toFixed(6);
                updateUserMap(fallbackLat, fallbackLon);
                checkRisk();
            },
            { enableHighAccuracy: true, maximumAge: 10000, timeout: 5000 }
        );
    } else {
        showMessage(dashMsg, 'Geolocation not supported', 'error');
    }
}

async function checkRisk() {
    const lat = parseFloat(document.getElementById('lat').value);
    const lon = parseFloat(document.getElementById('lon').value);
    
    if (isNaN(lat) || isNaN(lon)) return;
    
    try {
        let dist = lastKnownLocation ? getDistanceFromLatLonInM(lastKnownLocation.lat, lastKnownLocation.lon, lat, lon) : Number.MAX_VALUE;
        let timeDiff = lastKnownLocation ? Date.now() - lastKnownLocation.time : Number.MAX_VALUE;
        
        // Update if moved > 20m OR time since last update > 60 seconds
        if (dist > 20 || timeDiff > 60000) {
            const upRes = await fetch(`${API_URL}/location/update`, {
                method: 'POST',
                headers: getAuthHeaders(),
                body: JSON.stringify({ latitude: lat, longitude: lon })
            });
            handleFetchError(upRes);
            const upData = await upRes.json();
            if (!validateApiResponse(upData)) throw new Error("Invalid location update response format");
            lastKnownLocation = { lat, lon, time: Date.now() };
        }

        const res = await fetch(`${API_URL}/risk?latitude=${lat}&longitude=${lon}`, {
            headers: getAuthHeaders()
        });
        handleFetchError(res);
        const data = await res.json();
        
        if (!validateApiResponse(data, ['risk_level', 'score'])) {
            throw new Error("Invalid risk API response format");
        }
        
        lastUpdateTime = Date.now();
        document.getElementById('last-updated').textContent = `Last updated: 0s ago`;

        if (data.status === 'success') {
            const r = data.data;
            const badge = document.getElementById('risk-level-badge');
            
            const levelStr = r.risk_level ? r.risk_level.toUpperCase() : "UNKNOWN";
            const level = ["LOW", "MEDIUM", "HIGH"].includes(levelStr) ? levelStr : "UNKNOWN";
            badge.textContent = level;
            badge.className = `risk-level ${level}`;
            
            document.getElementById('risk-score').textContent = r.score;
            
            // Geofencing Alerts
            const activeZone = r.zone_name;
            const currentRiskLevel = level;
            const alertKey = activeZone ? `${activeZone}_${currentRiskLevel}` : null;
            
            if (alertKey !== currentAlertZone) {
                if (currentAlertZone && !alertKey) {
                    showToast(`✅ You exited the risk zone.`, 'safe', '✅');
                }
                currentAlertZone = alertKey; // Update state with zone + risk level
                if (r.is_restricted) {
                    showToast(`🚫 You entered a RESTRICTED ZONE: ${r.zone_name}`, 'restricted', '⛔');
                } else if (r.zone_type === 'RISK' && level === 'HIGH') {
                    showToast(`⚠️ High Risk Area: ${r.zone_name}`, 'high', '⚠️');
                }
            }
            
            const aiBox = document.getElementById('ai-explanation-box');
            const aiText = document.getElementById('ai-explanation-text');
            aiBox.classList.remove('hidden');
            
            // Enhanced Bullet Points with Emojis
            let parts = r.reason.split('|');
            let analysisHtml = '';
            parts.forEach(p => {
                let text = p.trim();
                let icon = '•';
                if(text.startsWith('Zone:')) icon = '📍';
                else if (text.startsWith('Incidents:')) icon = '🚨';
                else if (text.startsWith('Time:')) icon = '⏰';
                analysisHtml += `${icon} ${text}<br>`;
            });
            
            aiText.innerHTML = `<strong>Hybrid AI Factors:</strong><br>${analysisHtml}`;
            
            // New UI Logic for Proactive AI
            const suggestionsPanel = document.getElementById('safety-suggestions-panel');
            const suggestionsList = document.getElementById('suggestions-list');
            const dashboard = document.getElementById('user-dashboard');
            
            if (r.alert_type === 'warning' || r.alert_type === 'critical') {
                suggestionsPanel.classList.remove('hidden');
                suggestionsList.innerHTML = r.suggestions.map(s => `<li>${s}</li>`).join('');
            } else {
                suggestionsPanel.classList.add('hidden');
            }
            
            if (r.alert_type === 'critical') {
                if (!dashboard.classList.contains('red-alert-mode')) {
                    dashboard.classList.add('red-alert-mode');
                    // Play audio and vibrate on FIRST entering critical mode
                    if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
                    try {
                        const ctx = new (window.AudioContext || window.webkitAudioContext)();
                        const osc = ctx.createOscillator();
                        osc.type = 'square';
                        osc.frequency.setValueAtTime(880, ctx.currentTime);
                        osc.connect(ctx.destination);
                        osc.start();
                        osc.stop(ctx.currentTime + 0.3);
                    } catch(e) { console.warn("Audio not supported"); }
                }
            } else {
                dashboard.classList.remove('red-alert-mode');
            }
            
            if (r.should_auto_sos && r.alert_type === 'critical') {
                showToast("🚨 Auto-SOS Triggered for your safety!", "high", "🚨");
            }
            
            updateUserMap(lat, lon);
        }
    } catch (err) {
        if(err.message !== 'Unauthorized') console.error("Risk update failed:", err);
    }
}

async function triggerSOS() {
    if (sosCooldown) return;
    
    const lat = parseFloat(document.getElementById('lat').value);
    const lon = parseFloat(document.getElementById('lon').value);
    
    if (isNaN(lat) || isNaN(lon)) {
        showMessage(dashMsg, 'Valid location required to send SOS!', 'error');
        return;
    }

    const sosBtn = document.getElementById('sos-btn');
    sosBtn.disabled = true;
    sosBtn.classList.remove('pulse');
    sosBtn.textContent = 'DISPATCHING...';
    
    showLoader();
    try {
        const res = await fetch(`${API_URL}/sos`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ latitude: lat, longitude: lon, type: 'emergency' })
        });
        handleFetchError(res);
        const data = await res.json();
        hideLoader();

        if (data.status === 'success') {
            showMessage(dashMsg, '🚨 EMERGENCY SOS DISPATCHED TO AUTHORITIES 🚨', 'error');
            showToast('🚨 EMERGENCY SOS DISPATCHED!', 'high', '🚨');
            lastKnownLocation = null; // Force absolute latest update
            checkRisk();
        } else {
            showMessage(dashMsg, data.error, 'error');
        }
    } catch (err) {
        hideLoader();
        if(err.message !== 'Unauthorized') showMessage(dashMsg, 'Failed to connect to emergency services.', 'error');
    }
    
    sosCooldown = true;
    let cd = 5;
    const interval = setInterval(() => {
        sosBtn.textContent = `COOLDOWN (${cd}s)`;
        cd--;
        if(cd < 0) {
            clearInterval(interval);
            sosCooldown = false;
            sosBtn.disabled = false;
            sosBtn.textContent = '🚨 SOS / EMERGENCY 🚨';
            sosBtn.classList.add('pulse');
        }
    }, 1000);
}

/* ================= ADMIN DASHBOARD LOGIC ================= */

function initAdminDashboard() {
    if (!adminMap) initAdminMap();
    
    // Give DOM time to settle before rendering map overlays
    setTimeout(() => {
        if (adminMap) adminMap.invalidateSize();
        loadIncidents();
        loadPublicZonesAdmin();
        loadGeozoneList();
        loadSOSHeatmap();
    }, 300);
    
    if (refreshInterval) clearInterval(refreshInterval);
    refreshInterval = setInterval(loadIncidents, 10000);
    
    if (heatmapInterval) clearInterval(heatmapInterval);
    heatmapInterval = setInterval(loadSOSHeatmap, 12000);
}

function initAdminMap() {
    adminMap = L.map('admin-map').setView([17.3850, 78.4867], 12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(adminMap);
}

async function loadIncidents() {
    try {
        const res = await fetch(`${API_URL}/incidents?status=active`, {
            headers: getAuthHeaders()
        });
        handleFetchError(res);
        const data = await res.json();
        
        if(data.status === 'success') {
            renderIncidentFeed(data.data.incidents);
            renderAdminMarkers(data.data.incidents);
        }
    } catch(err) {
        if(err.message !== 'Unauthorized') showMessage(adminMsg, 'Failed to fetch incident feed', 'error');
    }
}

function renderIncidentFeed(incidents) {
    const feed = document.getElementById('incident-feed');
    feed.innerHTML = '';
    
    if(incidents.length === 0) {
        feed.innerHTML = '<p class="text-muted" style="text-align:center; padding: 2rem 0;">No active incidents at the moment. Area secure.</p>';
        return;
    }
    
    incidents.forEach(inc => {
        const timeStr = inc.timestamp ? new Date(inc.timestamp).toLocaleTimeString() : 'Recent';
        const html = `
            <div class="incident-card">
                <div class="incident-header">
                    <span class="incident-type">🚨 ${inc.type}</span>
                    <span class="incident-date">${timeStr}</span>
                </div>
                <div class="incident-body">
                    <strong>User ID:</strong> ${inc.user_id}<br>
                    <strong>Location:</strong> ${inc.latitude.toFixed(5)}, ${inc.longitude.toFixed(5)}
                </div>
                <button class="btn-primary sm-btn w-100" onclick="resolveIncident(${inc.id})">Mark as Resolved</button>
            </div>
        `;
        feed.innerHTML += html;
    });
}

function renderAdminMarkers(incidents) {
    if (!adminMap) return;
    
    activeIncidentMarkers.forEach(m => adminMap.removeLayer(m));
    activeIncidentMarkers = [];
    
    const bounds = L.latLngBounds();
    
    incidents.forEach(inc => {
        const pos = [inc.latitude, inc.longitude];
        
        const dangerIcon = L.divIcon({
            className: 'custom-div-icon',
            html: `<div style="background:var(--danger); width:15px; height:15px; border-radius:50%; border:2px solid white; box-shadow:0 0 15px var(--danger);"></div>`,
            iconSize: [15, 15]
        });
        
        const m = L.marker(pos, {icon: dangerIcon}).addTo(adminMap)
                   .bindPopup(`<b>${inc.type.toUpperCase()}</b><br>Incident #${inc.id}<br>User ID: ${inc.user_id}`);
                   
        activeIncidentMarkers.push(m);
        bounds.extend(pos);
    });
    
    if (incidents.length > 0) {
        adminMap.fitBounds(bounds, {padding: [50, 50], maxZoom: 15});
    } else {
        adminMap.setView([17.3850, 78.4867], 12);
    }
}

async function loadSOSHeatmap() {
    if (!adminMap) return;
    try {
        const res = await fetch(`${API_URL}/sos/heatmap`, { headers: getAuthHeaders() });
        handleFetchError(res);
        const data = await res.json();
        
        if (data.status === 'success') {
            if (heatmapLayer) {
                adminMap.removeLayer(heatmapLayer);
                heatmapLayer = null;
            }
            
            const points = data.data.map(p => [p.latitude, p.longitude, p.intensity]);
            if (points.length === 0) return;

            // Force a size update and verify map is actually visible with non-zero dimensions
            adminMap.invalidateSize();
            const size = adminMap.getSize();
            if (size.x === 0 || size.y === 0) {
                console.warn("Map container dimensions are 0. Retrying heatmap load in 500ms...");
                setTimeout(loadSOSHeatmap, 500);
                return;
            }

            if (heatmapLayer) {
                adminMap.removeLayer(heatmapLayer);
            }

            heatmapLayer = L.heatLayer(points, {
                radius: 25,
                blur: 15,
                maxZoom: 17,
                gradient: {
                    0.2: 'blue',
                    0.4: 'lime',
                    0.6: 'yellow',
                    0.8: 'orange',
                    1.0: 'red'
                }
            }).addTo(adminMap);

            // Center map on the heatmap points
            const bounds = L.latLngBounds(points.map(p => [p[0], p[1]]));
            adminMap.fitBounds(bounds, { padding: [50, 50], maxZoom: 15 });
        }
    } catch (err) {
        if (err.message !== 'Unauthorized') console.error("Heatmap load failed:", err);
    }
}

async function resolveIncident(id) {
    showLoader();
    try {
        const res = await fetch(`${API_URL}/incidents/${id}`, { 
            method: 'PUT',
            headers: getAuthHeaders() 
        });
        handleFetchError(res);
        const data = await res.json();
        
        if (data.status === 'success') {
            showMessage(adminMsg, `Incident #${id} resolved successfully.`, 'success');
            loadIncidents(); 
        } else {
            showMessage(adminMsg, data.error, 'error');
        }
    } catch(err) {
        if(err.message !== 'Unauthorized') showMessage(adminMsg, 'Error resolving incident.', 'error');
    } finally {
        hideLoader();
    }
}


async function loadPublicZonesAdmin() {
    if (!adminMap) return;
    try {
        const res = await fetch(`${API_URL}/zones/public`, { headers: getAuthHeaders() });
        handleFetchError(res);
        const data = await res.json();
        if(data.status === 'success') {
            adminZoneLayers.forEach(l => adminMap.removeLayer(l));
            adminZoneLayers = [];
            
            data.data.zones.forEach(zone => {
                let color = '#2ed573';
                if (zone.type === 'RESTRICTED') color = '#ff0000';
                else if (zone.risk_level === 'HIGH') color = '#ffa500';
                else if (zone.risk_level === 'MEDIUM') color = '#ffff00';
                
                const circle = L.circle([zone.latitude, zone.longitude], {
                    radius: zone.radius,
                    color: color,
                    fillColor: color,
                    fillOpacity: 0.2,
                    weight: 2
                }).addTo(adminMap);
                
                const popupHtml = `
                    <div style="color: black; min-width: 150px;">
                        <b>${zone.name}</b><br>
                        Type: ${zone.type}<br>
                        Risk: ${zone.risk_level}<br>
                        <button class="btn-danger sm-btn mt-2 w-100" style="padding: 5px;" onclick="deleteGeoZone(${zone.id})">Delete Zone</button>
                    </div>
                `;
                circle.bindPopup(popupHtml);
                adminZoneLayers.push(circle);
            });
        }
    } catch (e) {
        if(e.message !== 'Unauthorized') console.error("Failed to load zones for admin", e);
    }
}

async function deleteGeoZone(id) {
    if(!confirm("Are you sure you want to delete this zone?")) return;
    showLoader();
    try {
        const res = await fetch(`${API_URL}/geozones/${id}`, {
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        handleFetchError(res);
        const data = await res.json();
        if(data.status === 'success') {
            showToast(`✅ Zone Deleted`, 'safe', '✅');
            loadPublicZonesAdmin();
            loadGeozoneList();
        } else {
            showMessage(adminMsg, data.error, 'error');
        }
    } catch(err) {
        if(err.message !== 'Unauthorized') showMessage(adminMsg, 'Failed to delete zone', 'error');
    } finally {
        hideLoader();
    }
}

async function loadGeozoneList() {
    const container = document.getElementById('geozone-list');
    if(!container) return;
    
    container.innerHTML = '<p class="text-muted">Loading geozones...</p>';
    try {
        const res = await fetch(`${API_URL}/geozones`, { headers: getAuthHeaders() });
        const data = await res.json();
        if (data.status === 'success') {
            const zones = data.data.geozones;
            if (zones.length === 0) {
                container.innerHTML = '<p class="text-muted" style="text-align: center; margin-top: 1rem;">No geozones available.</p>';
                return;
            }
            container.innerHTML = '';
            zones.forEach(zone => {
                const card = document.createElement('div');
                card.className = 'geozone-card';
                card.innerHTML = `
                    <div class="geozone-header">
                        <div class="geozone-name">${zone.name}</div>
                        <div class="geozone-badge ${zone.type}">${zone.type} - ${zone.risk_level}</div>
                    </div>
                    <div class="geozone-body">
                        Radius: ${zone.radius}m<br>
                        Location: ${zone.latitude.toFixed(4)}, ${zone.longitude.toFixed(4)}
                    </div>
                    <div class="geozone-actions">
                        <button class="btn-icon edit" onclick='editGeozone(${JSON.stringify(zone)})'>✏️ Edit</button>
                        <button class="btn-icon delete" onclick="deleteGeoZone(${zone.id})">🗑️ Delete</button>
                    </div>
                `;
                container.appendChild(card);
            });
        } else {
            container.innerHTML = `<p class="text-muted" style="color: var(--danger);">Error: ${data.error}</p>`;
        }
    } catch (err) {
        console.error("Failed to load geozones list:", err);
        container.innerHTML = '<p class="text-muted" style="color: var(--danger);">Failed to load.</p>';
    }
}

function openGeofenceModal() {
    editingZoneId = null;
    document.getElementById('add-zone-form').reset();
    document.getElementById('geofence-modal-title').textContent = "➕ ADD GEOZONE";
    document.getElementById('geofence-modal').classList.remove('hidden');
}

function closeGeofenceModal() {
    editingZoneId = null;
    document.getElementById('add-zone-form').reset();
    document.getElementById('geofence-modal').classList.add('hidden');
}

function editGeozone(zone) {
    editingZoneId = zone.id;
    document.getElementById('zone-name').value = zone.name;
    document.getElementById('zone-lat').value = zone.latitude;
    document.getElementById('zone-lon').value = zone.longitude;
    document.getElementById('zone-radius').value = zone.radius;
    document.getElementById('zone-risk').value = zone.risk_level;
    document.getElementById('zone-type').value = zone.type || "RISK";
    document.getElementById('zone-place-type').value = zone.place_type || "general";
    document.getElementById('zone-desc').value = zone.description || "";
    document.getElementById('zone-response-time').value = zone.avg_response_time || 15;
    
    document.getElementById('geofence-modal-title').textContent = "✏️ EDIT GEOZONE";
    document.getElementById('geofence-modal').classList.remove('hidden');
}

async function submitGeoZone(e) {
    e.preventDefault();
    
    const payload = {
        name: document.getElementById('zone-name').value,
        latitude: parseFloat(document.getElementById('zone-lat').value),
        longitude: parseFloat(document.getElementById('zone-lon').value),
        radius: parseFloat(document.getElementById('zone-radius').value),
        risk_level: document.getElementById('zone-risk').value,
        type: document.getElementById('zone-type').value,
        place_type: document.getElementById('zone-place-type').value,
        description: document.getElementById('zone-desc').value,
        avg_response_time: document.getElementById('zone-response-time').value
    };
    
    showLoader();
    try {
        const method = editingZoneId ? 'PUT' : 'POST';
        const url = editingZoneId ? `${API_URL}/geozones/${editingZoneId}` : `${API_URL}/geozones`;
        
        const res = await fetch(url, {
            method: method,
            headers: {
                ...getAuthHeaders(),
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        
        handleFetchError(res);
        const data = await res.json();
        
        if(data.status === 'success') {
            showToast(editingZoneId ? `✅ Zone Updated` : `✅ Zone Added`, 'safe', '✅');
            closeGeofenceModal();
            loadPublicZonesAdmin();
            loadGeozoneList();
        } else {
            showMessage(adminMsg, data.error, 'error');
        }
    } catch(err) {
        if(err.message !== 'Unauthorized') showMessage(adminMsg, 'Failed to save zone', 'error');
    } finally {
        hideLoader();
    }
}
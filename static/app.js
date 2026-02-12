// Pokemon TCG Code Monitor — Frontend Application

const API = '/api';
let ws = null;
let wsReconnectTimer = null;
const activityLog = [];

// ─── Initialization ──────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initForms();
    initFilters();
    connectWebSocket();
    loadDashboard();
    loadChannels();
    loadVideos();
    loadCodes();

    // Auto-refresh every 30 seconds
    setInterval(() => {
        loadDashboard();
        loadVideos();
        loadCodes();
    }, 30000);
});

// ─── Tab Navigation ──────────────────────────────────────────────────────────

function initTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.add('hidden'));
            btn.classList.add('active');
            document.getElementById(`tab-${btn.dataset.tab}`).classList.remove('hidden');
        });
    });
}

// ─── Forms ───────────────────────────────────────────────────────────────────

function initForms() {
    document.getElementById('add-channel-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const input = document.getElementById('channel-input');
        const btn = document.getElementById('add-channel-btn');
        const url = input.value.trim();
        if (!url) return;

        btn.disabled = true;
        btn.textContent = 'Adding...';

        try {
            const resp = await fetch(`${API}/channels`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url_or_id: url }),
            });

            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'Failed to add channel');
            }

            const channel = await resp.json();
            input.value = '';
            showToast(`✅ Added: ${channel.channel_name}`, 'success');
            loadChannels();
            loadDashboard();
        } catch (err) {
            showToast(`❌ ${err.message}`, 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = 'Add Channel';
        }
    });
}

function initFilters() {
    document.getElementById('video-status-filter').addEventListener('change', loadVideos);
    document.getElementById('code-filter').addEventListener('change', loadCodes);
}

// ─── Dashboard ───────────────────────────────────────────────────────────────

async function loadDashboard() {
    try {
        const resp = await fetch(`${API}/stats`);
        const stats = await resp.json();

        document.getElementById('stat-channels').textContent = stats.active_channels;
        document.getElementById('stat-videos-today').textContent = stats.videos_today;
        document.getElementById('stat-codes-today').textContent = stats.codes_today;
        document.getElementById('stat-unredeemed').textContent = stats.unredeemed_codes;

        const mode = stats.monitoring_mode === 'api' ? '⚡ YouTube API' : '📡 RSS Feed';
        document.getElementById('monitoring-status').textContent =
            `${mode} • Polling every ${stats.poll_interval}s • ${stats.total_codes} total codes`;

        // Load recent codes for dashboard
        const codesResp = await fetch(`${API}/codes?limit=10`);
        const codes = await codesResp.json();
        renderRecentCodes(codes);

    } catch (err) {
        console.error('Failed to load dashboard:', err);
    }
}

function renderRecentCodes(codes) {
    const container = document.getElementById('recent-codes');
    if (!codes.length) {
        container.innerHTML = '<p class="text-gray-500 text-center py-8">No codes found yet. Add some channels to start monitoring!</p>';
        return;
    }

    container.innerHTML = codes.map(code => `
        <div class="flex items-center justify-between py-2 ${code.is_redeemed ? 'opacity-50' : ''}">
            <div class="flex items-center gap-3">
                <span class="code-text" onclick="copyCode('${code.code_normalized}', this)" title="Click to copy">
                    ${formatCode(code.code_normalized)}
                </span>
                <span class="badge badge-${code.source_type}">${code.source_type.toUpperCase()}</span>
                ${code.is_redeemed ? '<span class="badge bg-gray-700 text-gray-400">Redeemed</span>' : ''}
            </div>
            <div class="text-xs text-gray-500">
                ${code.channel_name} • ${timeAgo(code.discovered_at)}
            </div>
        </div>
    `).join('');
}

// ─── Channels ────────────────────────────────────────────────────────────────

async function loadChannels() {
    try {
        const resp = await fetch(`${API}/channels`);
        const channels = await resp.json();
        renderChannels(channels);
    } catch (err) {
        console.error('Failed to load channels:', err);
    }
}

function renderChannels(channels) {
    const container = document.getElementById('channel-list');
    if (!channels.length) {
        container.innerHTML = '<p class="text-gray-500 text-center py-8">No channels yet. Add one above!</p>';
        return;
    }

    container.innerHTML = channels.map(ch => `
        <div class="flex items-center justify-between py-3 border-b border-gray-700 last:border-0">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-full bg-pokemon-blue flex items-center justify-center text-lg font-bold">
                    ${ch.channel_name.charAt(0).toUpperCase()}
                </div>
                <div>
                    <div class="font-medium">${escapeHtml(ch.channel_name)}</div>
                    <div class="text-xs text-gray-500">
                        ${ch.video_count} videos • ${ch.code_count} codes
                        ${ch.last_checked_at ? '• Checked ' + timeAgo(ch.last_checked_at) : ''}
                    </div>
                </div>
            </div>
            <div class="flex items-center gap-2">
                <button onclick="checkChannelNow(${ch.id})" class="btn-sm bg-pokemon-blue hover:bg-blue-700" title="Check now">
                    🔄 Check
                </button>
                <button onclick="toggleChannel(${ch.id}, ${ch.is_active ? 'false' : 'true'})"
                        class="btn-sm ${ch.is_active ? 'bg-green-700 hover:bg-green-800' : 'bg-gray-600 hover:bg-gray-700'}">
                    ${ch.is_active ? '✅ Active' : '⏸️ Paused'}
                </button>
                <button onclick="deleteChannel(${ch.id}, '${escapeHtml(ch.channel_name)}')"
                        class="btn-sm bg-red-800 hover:bg-red-700" title="Delete">
                    🗑️
                </button>
            </div>
        </div>
    `).join('');
}

async function checkChannelNow(id) {
    try {
        showToast('🔄 Checking for new videos...', 'info');
        const resp = await fetch(`${API}/channels/${id}/check`, { method: 'POST' });
        const data = await resp.json();
        showToast(`Found ${data.new_videos} new video(s)`, data.new_videos > 0 ? 'success' : 'info');
        loadVideos();
        loadDashboard();
    } catch (err) {
        showToast('❌ Check failed', 'error');
    }
}

async function toggleChannel(id, active) {
    try {
        await fetch(`${API}/channels/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: active }),
        });
        loadChannels();
    } catch (err) {
        showToast('❌ Update failed', 'error');
    }
}

async function deleteChannel(id, name) {
    if (!confirm(`Delete channel "${name}" and all its data?`)) return;
    try {
        await fetch(`${API}/channels/${id}`, { method: 'DELETE' });
        showToast(`🗑️ Deleted: ${name}`, 'info');
        loadChannels();
        loadDashboard();
    } catch (err) {
        showToast('❌ Delete failed', 'error');
    }
}

// ─── Videos ──────────────────────────────────────────────────────────────────

async function loadVideos() {
    try {
        const status = document.getElementById('video-status-filter').value;
        const url = `${API}/videos?limit=50${status ? '&status=' + status : ''}`;
        const resp = await fetch(url);
        const videos = await resp.json();
        renderVideos(videos);
    } catch (err) {
        console.error('Failed to load videos:', err);
    }
}

function renderVideos(videos) {
    const container = document.getElementById('video-list');
    if (!videos.length) {
        container.innerHTML = '<p class="text-gray-500 text-center py-8">No videos yet.</p>';
        return;
    }

    container.innerHTML = videos.map(v => `
        <div class="p-4 flex items-center justify-between">
            <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                    <a href="${v.video_url}" target="_blank" class="font-medium text-blue-400 hover:text-blue-300 truncate">
                        ${escapeHtml(v.title)}
                    </a>
                    <span class="badge badge-${v.status}">${v.status}</span>
                </div>
                <div class="text-xs text-gray-500 mt-1">
                    ${escapeHtml(v.channel_name)} • ${timeAgo(v.discovered_at)}
                    ${v.frames_extracted ? '• ' + v.frames_extracted + ' frames' : ''}
                    ${v.code_count ? '• <span class="text-pokemon-yellow">' + v.code_count + ' codes</span>' : ''}
                    ${v.error_message ? '• <span class="text-red-400">' + escapeHtml(v.error_message) + '</span>' : ''}
                </div>
            </div>
            <div class="flex items-center gap-2 ml-3">
                ${v.status === 'failed' ? `<button onclick="reprocessVideo(${v.id})" class="btn-sm bg-pokemon-blue hover:bg-blue-700">🔄 Retry</button>` : ''}
                ${v.status === 'processing' || v.status === 'downloading' ? '<div class="spinner"></div>' : ''}
            </div>
        </div>
    `).join('');
}

async function reprocessVideo(id) {
    try {
        await fetch(`${API}/videos/${id}/reprocess`, { method: 'POST' });
        showToast('🔄 Video queued for reprocessing', 'info');
        loadVideos();
    } catch (err) {
        showToast('❌ Reprocess failed', 'error');
    }
}

// ─── Codes ───────────────────────────────────────────────────────────────────

async function loadCodes() {
    try {
        const filter = document.getElementById('code-filter').value;
        let url = `${API}/codes?limit=100`;
        if (filter === 'unredeemed') url += '&redeemed=false';
        if (filter === 'redeemed') url += '&redeemed=true';

        const resp = await fetch(url);
        const codes = await resp.json();
        renderCodes(codes);
    } catch (err) {
        console.error('Failed to load codes:', err);
    }
}

function renderCodes(codes) {
    const container = document.getElementById('code-list');
    if (!codes.length) {
        container.innerHTML = '<p class="text-gray-500 text-center py-8">No codes found yet.</p>';
        return;
    }

    container.innerHTML = codes.map(code => `
        <div class="p-4 flex items-center justify-between ${code.is_redeemed ? 'opacity-50' : ''}">
            <div class="flex items-center gap-3 flex-1 min-w-0">
                <span class="code-text" onclick="copyCode('${code.code_normalized}', this)" title="Click to copy">
                    ${formatCode(code.code_normalized)}
                </span>
                <span class="badge badge-${code.source_type}">${code.source_type.toUpperCase()}</span>
                <button onclick="copyCode('${code.code_normalized}', this)" class="btn-sm bg-gray-700 hover:bg-gray-600">
                    📋 Copy
                </button>
            </div>
            <div class="flex items-center gap-3 ml-3">
                <div class="text-right text-xs text-gray-500">
                    <div>${escapeHtml(code.video_title || '')}</div>
                    <div>${escapeHtml(code.channel_name || '')} • ${timeAgo(code.discovered_at)}</div>
                </div>
                <button onclick="toggleRedeemed(${code.id}, ${!code.is_redeemed})"
                        class="btn-sm ${code.is_redeemed ? 'bg-gray-600' : 'bg-green-700 hover:bg-green-600'}">
                    ${code.is_redeemed ? '↩️ Unredeem' : '✅ Redeemed'}
                </button>
            </div>
        </div>
    `).join('');
}

async function toggleRedeemed(id, redeemed) {
    try {
        await fetch(`${API}/codes/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_redeemed: redeemed }),
        });
        loadCodes();
        loadDashboard();
    } catch (err) {
        showToast('❌ Update failed', 'error');
    }
}

async function copyAllUnredeemed() {
    try {
        const resp = await fetch(`${API}/codes?redeemed=false&limit=500`);
        const codes = await resp.json();
        if (!codes.length) {
            showToast('No unredeemed codes to copy', 'info');
            return;
        }
        const text = codes.map(c => c.code_normalized).join('\n');
        await navigator.clipboard.writeText(text);
        showToast(`📋 Copied ${codes.length} codes to clipboard`, 'success');
    } catch (err) {
        showToast('❌ Copy failed', 'error');
    }
}

// ─── WebSocket ───────────────────────────────────────────────────────────────

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    try {
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            document.getElementById('ws-dot').className = 'w-2 h-2 rounded-full bg-green-500';
            document.getElementById('ws-label').textContent = 'Connected';
            if (wsReconnectTimer) {
                clearTimeout(wsReconnectTimer);
                wsReconnectTimer = null;
            }
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                handleWSEvent(msg);
            } catch (e) {
                console.error('WS parse error:', e);
            }
        };

        ws.onclose = () => {
            document.getElementById('ws-dot').className = 'w-2 h-2 rounded-full bg-red-500';
            document.getElementById('ws-label').textContent = 'Disconnected';
            // Reconnect after 3 seconds
            wsReconnectTimer = setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = () => {
            ws.close();
        };

        // Keepalive ping every 30 seconds
        setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send('ping');
            }
        }, 30000);

    } catch (e) {
        console.error('WebSocket connection failed:', e);
        wsReconnectTimer = setTimeout(connectWebSocket, 5000);
    }
}

function handleWSEvent(msg) {
    const { event, data, timestamp } = msg;

    switch (event) {
        case 'code_found':
            showToast(`🎯 NEW CODE: ${formatCode(data.code)}\nFrom: ${data.video_title}`, 'code');
            addActivity('🎯', `Code found: <span class="text-pokemon-yellow font-mono">${formatCode(data.code)}</span> in "${data.video_title}"`, timestamp);
            loadCodes();
            loadDashboard();
            playNotificationSound();
            break;

        case 'new_video_detected':
            showToast(`📺 New video: ${data.title}\nBy: ${data.channel}`, 'info');
            addActivity('📺', `New video detected: "${data.title}" by ${data.channel}`, timestamp);
            loadVideos();
            loadDashboard();
            break;

        case 'processing_started':
            addActivity('⚙️', `Processing: "${data.title}" (${data.stage})`, timestamp);
            loadVideos();
            break;

        case 'processing_completed':
            addActivity('✅', `Completed: "${data.title}" — ${data.codes_found} codes found (${data.frames_scanned} frames)`, timestamp);
            loadVideos();
            loadDashboard();
            break;

        case 'processing_failed':
            addActivity('❌', `Failed: "${data.title}" — ${data.error}`, timestamp);
            loadVideos();
            break;

        case 'pong':
            break;

        default:
            console.log('Unknown WS event:', event, data);
    }
}

// ─── Activity Feed ───────────────────────────────────────────────────────────

function addActivity(icon, message, timestamp) {
    activityLog.unshift({ icon, message, timestamp });
    if (activityLog.length > 50) activityLog.pop();
    renderActivityFeed();
}

function renderActivityFeed() {
    const container = document.getElementById('activity-feed');
    if (!activityLog.length) {
        container.innerHTML = '<p class="text-gray-500 text-center py-4">Waiting for activity...</p>';
        return;
    }

    container.innerHTML = activityLog.map(item => `
        <div class="activity-item">
            <span class="activity-icon">${item.icon}</span>
            <span class="flex-1">${item.message}</span>
            <span class="activity-time">${formatTime(item.timestamp)}</span>
        </div>
    `).join('');
}

// ─── Utilities ───────────────────────────────────────────────────────────────

function formatCode(code) {
    // Format as XXX-XXXX-XXX-XXX for readability
    if (code.length === 13) {
        return `${code.slice(0,3)}-${code.slice(3,7)}-${code.slice(7,10)}-${code.slice(10)}`;
    }
    return code;
}

function copyCode(code, element) {
    navigator.clipboard.writeText(code).then(() => {
        if (element) {
            const original = element.textContent;
            element.textContent = '✅ Copied!';
            element.classList.add('copied');
            setTimeout(() => {
                element.textContent = original;
                element.classList.remove('copied');
            }, 1500);
        }
        showToast(`📋 Copied: ${code}`, 'success');
    });
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type === 'code' ? 'toast-code' : ''}`;

    const colors = {
        success: 'text-green-400',
        error: 'text-red-400',
        info: 'text-blue-400',
        code: 'text-pokemon-yellow',
    };

    toast.innerHTML = `
        <div class="${colors[type] || 'text-gray-300'} text-sm whitespace-pre-line">${escapeHtml(message)}</div>
    `;

    container.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
}

function playNotificationSound() {
    // Browser notification
    if ('Notification' in window && Notification.permission === 'granted') {
        new Notification('🎯 Pokemon TCG Code Found!', {
            body: 'A new redemption code was detected!',
            icon: '⚡',
        });
    } else if ('Notification' in window && Notification.permission !== 'denied') {
        Notification.requestPermission();
    }
}

function timeAgo(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);

    if (seconds < 60) return 'just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
}

function formatTime(dateStr) {
    if (!dateStr) return '';
    try {
        return new Date(dateStr).toLocaleTimeString();
    } catch {
        return '';
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

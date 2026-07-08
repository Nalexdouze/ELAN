# ============================================================================
# FILE: /opt/elan/app/elan-webui.py
# VERSION : 1
# ============================================================================

from flask import Flask, render_template_string, jsonify
import subprocess
import logging
from datetime import datetime

app = Flask(__name__)

# Configuration du logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("elan-webui")

# Template HTML avec onglets
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ÉLAN - Logs en temps réel</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(135deg, #2d3748 0%, #1a202c 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .header p {
            opacity: 0.9;
            font-size: 1.1em;
        }
        
        .tabs {
            display: flex;
            background: #f7fafc;
            border-bottom: 2px solid #e2e8f0;
            padding: 0 20px;
        }
        
        .tab {
            padding: 20px 30px;
            cursor: pointer;
            border: none;
            background: none;
            font-size: 1.1em;
            font-weight: 600;
            color: #4a5568;
            transition: all 0.3s ease;
            position: relative;
        }
        
        .tab:hover {
            background: rgba(102, 126, 234, 0.1);
            color: #667eea;
        }
        
        .tab.active {
            color: #667eea;
        }
        
        .tab.active::after {
            content: '';
            position: absolute;
            bottom: -2px;
            left: 0;
            right: 0;
            height: 3px;
            background: #667eea;
        }
        
        .controls {
            padding: 20px 30px;
            background: #f7fafc;
            display: flex;
            gap: 15px;
            align-items: center;
            border-bottom: 1px solid #e2e8f0;
        }
        
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            font-size: 1em;
            cursor: pointer;
            transition: all 0.3s ease;
            font-weight: 600;
        }
        
        .btn-primary {
            background: #667eea;
            color: white;
        }
        
        .btn-primary:hover {
            background: #5a67d8;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }
        
        .btn-secondary {
            background: #e2e8f0;
            color: #2d3748;
        }
        
        .btn-secondary:hover {
            background: #cbd5e0;
        }
        
        .status {
            margin-left: auto;
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.9em;
        }
        
        .status.connected {
            background: #c6f6d5;
            color: #22543d;
        }
        
        .status.loading {
            background: #feebc8;
            color: #7c2d12;
        }
        
        .log-container {
            padding: 20px;
        }
        
        .log-content {
            display: none;
            background: #1a202c;
            color: #e2e8f0;
            font-family: 'Courier New', monospace;
            font-size: 0.95em;
            padding: 20px;
            border-radius: 8px;
            max-height: 600px;
            overflow-y: auto;
            line-height: 1.6;
        }
        
        .log-content.active {
            display: block;
        }
        
        .log-line {
            margin-bottom: 4px;
            word-wrap: break-word;
        }
        
        .log-line.error {
            color: #fc8181;
            font-weight: bold;
        }
        
        .log-line.warning {
            color: #f6ad55;
        }
        
        .log-line.success {
            color: #68d391;
        }
        
        .log-line.info {
            color: #63b3ed;
        }
        
        .timestamp {
            color: #a0aec0;
            margin-right: 10px;
        }
        
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #718096;
        }
        
        .empty-state svg {
            width: 80px;
            height: 80px;
            margin-bottom: 20px;
            opacity: 0.5;
        }
        
        ::-webkit-scrollbar {
            width: 10px;
        }
        
        ::-webkit-scrollbar-track {
            background: #2d3748;
            border-radius: 5px;
        }
        
        ::-webkit-scrollbar-thumb {
            background: #4a5568;
            border-radius: 5px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: #667eea;
        }
        
        .auto-refresh {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .auto-refresh input[type="checkbox"] {
            width: 20px;
            height: 20px;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🖨️ ÉLAN</h1>
            <p>Surveillance des logs en temps réel</p>
        </div>
        
        <div class="tabs">
            <button class="tab active" onclick="switchTab('watchdog')">
                📋 Watchdog
            </button>
            <button class="tab" onclick="switchTab('samba-share')">
                📤 Samba Share
            </button>
            <button class="tab" onclick="switchTab('samba-mnt')">
                📥 Samba Mount
            </button>
        </div>
        
        <div class="controls">
            <button class="btn btn-primary" onclick="refreshLogs()">
                🔄 Rafraîchir
            </button>
            <button class="btn btn-secondary" onclick="clearLogs()">
                🗑️ Effacer
            </button>
            <div class="auto-refresh">
                <input type="checkbox" id="autoRefresh" onchange="toggleAutoRefresh()" checked>
                <label for="autoRefresh">Actualisation auto (30s)</label>
            </div>
            <div class="status connected" id="status">
                ● Connecté
            </div>
        </div>
        
        <div class="log-container">
            <div class="log-content active" id="watchdog-logs">
                <div class="empty-state">
                    <svg fill="currentColor" viewBox="0 0 20 20">
                        <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z"/>
                        <path fill-rule="evenodd" d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm3 4a1 1 0 000 2h.01a1 1 0 100-2H7zm3 0a1 1 0 000 2h3a1 1 0 100-2h-3zm-3 4a1 1 0 100 2h.01a1 1 0 100-2H7zm3 0a1 1 0 100 2h3a1 1 0 100-2h-3z" clip-rule="evenodd"/>
                    </svg>
                    <p>Chargement des logs...</p>
                </div>
            </div>
            <div class="log-content" id="samba-share-logs">
                <div class="empty-state">
                    <p>Chargement des logs...</p>
                </div>
            </div>
            <div class="log-content" id="samba-mnt-logs">
                <div class="empty-state">
                    <p>Chargement des logs...</p>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let currentTab = 'watchdog';
        let autoRefreshInterval = null;
        
        function switchTab(tab) {
            currentTab = tab;
            
            // Update tabs
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            event.target.classList.add('active');
            
            // Update content
            document.querySelectorAll('.log-content').forEach(c => c.classList.remove('active'));
            document.getElementById(tab + '-logs').classList.add('active');
        }
        
        async function refreshLogs() {
            const statusEl = document.getElementById('status');
            statusEl.textContent = '⏳ Chargement...';
            statusEl.className = 'status loading';
            
            try {
                const response = await fetch('/api/logs/' + currentTab);
                const data = await response.json();
                
                const logContainer = document.getElementById(currentTab + '-logs');
                
                if (data.logs.length === 0) {
                    logContainer.innerHTML = '<div class="empty-state"><p>Aucun log disponible</p></div>';
                } else {
                    logContainer.innerHTML = data.logs.map(line => formatLogLine(line)).join('');
                    logContainer.scrollTop = logContainer.scrollHeight;
                }
                
                statusEl.textContent = '● Connecté';
                statusEl.className = 'status connected';
            } catch (error) {
                console.error('Erreur:', error);
                statusEl.textContent = '● Erreur';
                statusEl.className = 'status error';
            }
        }
        
        function formatLogLine(line) {
            let className = 'log-line';
            
            if (line.includes('ERROR') || line.includes('❌') || line.includes('💥')) {
                className += ' error';
            } else if (line.includes('WARNING') || line.includes('⚠️')) {
                className += ' warning';
            } else if (line.includes('✅') || line.includes('🎉')) {
                className += ' success';
            } else if (line.includes('INFO') || line.includes('🆕') || line.includes('📋')) {
                className += ' info';
            }
            
            return `<div class="${className}">${escapeHtml(line)}</div>`;
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        function clearLogs() {
            const logContainer = document.getElementById(currentTab + '-logs');
            logContainer.innerHTML = '<div class="empty-state"><p>Logs effacés</p></div>';
        }
        
        function toggleAutoRefresh() {
            const checkbox = document.getElementById('autoRefresh');
            
            if (checkbox.checked) {
                autoRefreshInterval = setInterval(refreshLogs, 30000); // 30 secondes
            } else {
                if (autoRefreshInterval) {
                    clearInterval(autoRefreshInterval);
                    autoRefreshInterval = null;
                }
            }
        }
        
        // Charger les logs au démarrage
        refreshLogs();
        
        // Démarrer l'auto-refresh
        toggleAutoRefresh();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """Page d'accueil avec les logs"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/logs/<container>')
def get_logs(container):
    """Récupère les logs d'un container via journalctl"""
    
    # Mapping des noms d'onglets vers les noms de containers
    container_map = {
        'watchdog': 'elan-watchdog',
        'samba-share': 'elan-samba-share',
        'samba-mnt': 'elan-samba-mnt'
    }
    
    container_name = container_map.get(container)
    
    if not container_name:
        return jsonify({'error': 'Container inconnu', 'logs': []}), 400
    
    try:
        # Récupérer les 200 dernières lignes de logs
        result = subprocess.run(
            ['journalctl', '-n', '200', '--no-pager', f'CONTAINER_NAME={container_name}'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            logger.error(f"Erreur journalctl pour {container_name}: {result.stderr}")
            return jsonify({'error': 'Erreur lecture logs', 'logs': []})
        
        # Nettoyer et formater les logs
        logs = result.stdout.strip().split('\n')
        logs = [line for line in logs if line]  # Supprimer les lignes vides
        
        return jsonify({
            'container': container_name,
            'logs': logs,
            'count': len(logs)
        })
        
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout lors de la lecture des logs de {container_name}")
        return jsonify({'error': 'Timeout', 'logs': []})
    except Exception as e:
        logger.error(f"Erreur lors de la lecture des logs: {e}")
        return jsonify({'error': str(e), 'logs': []})

@app.route('/health')
def health():
    """Endpoint de santé"""
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    logger.info("🚀 [elan-webui] Démarrage sur le port 80...")
    app.run(host='0.0.0.0', port=80, debug=False)
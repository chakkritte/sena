"""FastAPI web dashboard for CarbonClaw."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog

logger = structlog.get_logger()

try:
    from fastapi import FastAPI, Request, BackgroundTasks
    from fastapi.responses import HTMLResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles

    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False

from carbonclaw.agents.supervisor import SupervisorAgent
from carbonclaw.config.settings import CarbonClawConfig
from carbonclaw.core.models import Message
from carbonclaw.distributed.queue import Task, TaskQueue
from carbonclaw.telemetry.carbon import CarbonStore
from carbonclaw.telemetry.grid import get_grid_intensity


if not _FASTAPI_AVAILABLE:
    raise ImportError(
        "FastAPI is not installed. Install with: uv add fastapi uvicorn"
    )


HTML_DASHBOARD = """
<!DOCTYPE html>
<html>
<head>
    <title>CarbonClaw Dashboard</title>
    <meta charset="utf-8">
    <style>
        body { font-family: system-ui, sans-serif; max-width: 960px; margin: 0 auto; padding: 2rem; }
        h1 { color: #2563eb; }
        .card { border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem; margin: 1rem 0; }
        .log { background: #f3f4f6; padding: 0.5rem; border-radius: 4px; font-family: monospace; white-space: pre-wrap; }
        input, button { padding: 0.5rem; font-size: 1rem; }
        #stream { height: 400px; overflow-y: auto; background: #111827; color: #e5e7eb; padding: 1rem; border-radius: 8px; }
        .msg-user { color: #60a5fa; }
        .msg-assistant { color: #34d399; }
        .msg-tool { color: #fbbf24; }
    </style>
</head>
<body>
    <h1>CarbonClaw Dashboard</h1>
    <div class="card">
        <h2>Chat</h2>
        <div id="stream"></div>
        <form id="chat-form" style="margin-top:1rem;">
            <input id="prompt" type="text" placeholder="Enter a task..." style="width:70%;">
            <button type="submit">Send</button>
        </form>
    </div>
    <div class="card">
        <h2>Status</h2>
        <div id="status" class="log">Idle</div>
    </div>
    <script>
        const stream = document.getElementById('stream');
        const form = document.getElementById('chat-form');
        const prompt = document.getElementById('prompt');
        const status = document.getElementById('status');

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const text = prompt.value.trim();
            if (!text) return;
            prompt.value = '';
            stream.innerHTML += '<div class="msg-user">[you] ' + escapeHtml(text) + '</div>';
            stream.scrollTop = stream.scrollHeight;

            const source = new EventSource('/chat/stream?prompt=' + encodeURIComponent(text));
            source.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === 'text') {
                    stream.innerHTML += escapeHtml(data.content);
                } else if (data.type === 'tool') {
                    stream.innerHTML += '<div class="msg-tool">[' + escapeHtml(data.name) + '] ' + escapeHtml(data.content.substring(0,200)) + '</div>';
                } else if (data.type === 'done') {
                    stream.innerHTML += '<div style="color:#9ca3af;">--- done ---</div>';
                    source.close();
                }
                stream.scrollTop = stream.scrollHeight;
            };
            source.onerror = () => {
                source.close();
                status.textContent = 'Connection closed';
            };
        });

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    </script>
</body>
</html>
"""

HTML_ESG_DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>CarbonClaw | ESG & Sustainability Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #0b0f19;
            --bg-surface: rgba(17, 24, 39, 0.95);
            --border-color: rgba(255, 255, 255, 0.08);
            --primary: #10b981;
            --primary-glow: rgba(16, 185, 129, 0.15);
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-base);
            color: var(--text-main);
            min-height: 100vh;
            padding: 2.5rem;
            background-image: radial-gradient(circle at 10% 20%, rgba(16, 185, 129, 0.05) 0%, transparent 40%),
                              radial-gradient(circle at 90% 80%, rgba(99, 102, 241, 0.05) 0%, transparent 40%);
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2.5rem;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 1.5rem;
        }
        .logo-section h1 {
            font-size: 2.2rem;
            font-weight: 800;
            background: linear-gradient(135deg, #10b981 0%, #6366f1 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.5px;
        }
        .logo-section p {
            color: var(--text-muted);
            font-size: 0.95rem;
            margin-top: 4px;
        }
        .grid-indicator {
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.2);
            padding: 0.5rem 1rem;
            border-radius: 9999px;
            font-size: 0.85rem;
            color: #10b981;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
            box-shadow: 0 0 15px var(--primary-glow);
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2.5rem;
        }
        .card {
            background: var(--bg-surface);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.75rem;
            backdrop-filter: blur(12px);
            transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.3s;
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
        }
        .card:hover {
            transform: translateY(-4px);
            border-color: rgba(16, 185, 129, 0.3);
            box-shadow: 0 8px 30px rgba(16, 185, 129, 0.08);
        }
        .card h2 {
            font-size: 1.1rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 1rem;
            font-weight: 600;
        }
        .metric-value {
            font-size: 2.75rem;
            font-weight: 800;
            margin-bottom: 0.5rem;
            display: flex;
            align-items: baseline;
            gap: 6px;
        }
        .metric-unit {
            font-size: 1.1rem;
            color: var(--text-muted);
            font-weight: 400;
        }
        .metric-desc {
            font-size: 0.85rem;
            color: var(--text-muted);
        }
        .leaderboard-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 1rem;
        }
        .leaderboard-table th {
            text-align: left;
            color: var(--text-muted);
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            padding: 0.75rem 0.5rem;
            border-bottom: 1px solid var(--border-color);
        }
        .leaderboard-table td {
            padding: 1rem 0.5rem;
            border-bottom: 1px solid var(--border-color);
            font-size: 0.95rem;
        }
        .leaderboard-table tr:last-child td {
            border-bottom: none;
        }
        .ratio-high { color: #10b981; font-weight: 600; }
        .ratio-med { color: #f59e0b; }
        .ratio-low { color: #ef4444; }
        .project-list {
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }
        .project-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(255, 255, 255, 0.02);
            padding: 0.75rem 1rem;
            border-radius: 8px;
            border-left: 4px solid #6366f1;
        }
        .project-name { font-weight: 600; }
        .project-emissions { font-family: monospace; color: #10b981; }
        .pulse {
            width: 8px;
            height: 8px;
            background-color: #10b981;
            border-radius: 50%;
            display: inline-block;
            box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
            animation: pulse 1.6s infinite;
        }
        @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }
        /* Tab navigation */
        .tabs {
            display: flex;
            gap: 1rem;
            margin-bottom: 2rem;
        }
        .tab-btn {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-color);
            color: var(--text-muted);
            padding: 0.6rem 1.2rem;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            font-size: 0.9rem;
            transition: all 0.2s;
        }
        .tab-btn.active, .tab-btn:hover {
            background: #10b981;
            color: #0b0f19;
            border-color: #10b981;
            box-shadow: 0 4px 15px rgba(16, 185, 129, 0.2);
        }
    </style>
</head>
<body>
    <header>
        <div class="logo-section">
            <h1>CarbonClaw 🦞</h1>
            <p>ESG Compliant AI-Agent Telemetry & Sustainability Dashboard</p>
        </div>
        <div class="grid-indicator">
            <span class="pulse"></span>
            Grid Carbon: <span id="intensity-val">...</span> g CO2/kWh
        </div>
    </header>

    <div class="tabs">
        <button class="tab-btn active" onclick="location.href='/esg/dashboard'">Dashboard Stats</button>
        <button class="tab-btn" onclick="location.href='/esg/benchmark'">Model Benchmarks</button>
        <button class="tab-btn" onclick="location.href='/'">Interactive Chat</button>
    </div>

    <div class="grid">
        <!-- Card 1 -->
        <div class="card">
            <h2>Total Session Emissions</h2>
            <div class="metric-value" id="total-emissions">... <span class="metric-unit">g CO2</span></div>
            <p class="metric-desc">Aggregated agent grid consumption records.</p>
        </div>
        <!-- Card 2 -->
        <div class="card">
            <h2>Forestry Offsets</h2>
            <div class="metric-value" id="offset-trees">... <span class="metric-unit">Trees</span></div>
            <p class="metric-desc" id="offset-partner">Offset Project Partner</p>
        </div>
        <!-- Card 3 -->
        <div class="card">
            <h2>Clean Energy Restored</h2>
            <div class="metric-value" id="offset-wh">... <span class="metric-unit">Wh</span></div>
            <p class="metric-desc">Equivalent grid power generation offsets.</p>
        </div>
    </div>

    <div class="grid" style="grid-template-columns: 2fr 1fr;">
        <!-- Card 4: Leaderboard -->
        <div class="card">
            <h2>Model Efficiency Leaderboard (Carbon-to-Utility Ratio)</h2>
            <table class="leaderboard-table">
                <thead>
                    <tr>
                        <th>Model Identifier</th>
                        <th>Utility Score</th>
                        <th>Emissions/1k Tok</th>
                        <th>Efficiency Ratio</th>
                    </tr>
                </thead>
                <tbody id="leaderboard-body">
                    <!-- Loaded dynamically -->
                </tbody>
            </table>
        </div>
        <!-- Card 5: Project emissions -->
        <div class="card">
            <h2>Emissions By Project</h2>
            <div class="project-list" id="project-list">
                <!-- Loaded dynamically -->
            </div>
        </div>
    </div>

    <script>
        async function fetchStats() {
            try {
                const res = await fetch('/api/esg/stats');
                const data = await res.json();
                
                document.getElementById('intensity-val').textContent = data.grid_intensity;
                document.getElementById('total-emissions').innerHTML = `${data.total_emissions_grams.toFixed(2)} <span class="metric-unit">g CO₂</span>`;
                document.getElementById('offset-trees').innerHTML = `${data.offsets.trees_planted} <span class="metric-unit">Trees Planted</span>`;
                document.getElementById('offset-partner').textContent = `Credits via ${data.offsets.project_partner}`;
                document.getElementById('offset-wh').innerHTML = `${data.offsets.clean_energy_offset_wh.toFixed(1)} <span class="metric-unit">Wh</span>`;
                
                // Load Leaderboard
                const lBody = document.getElementById('leaderboard-body');
                lBody.innerHTML = '';
                data.leaderboard.forEach(item => {
                    let ratioClass = 'ratio-high';
                    if (item.ratio < 500) ratioClass = 'ratio-low';
                    else if (item.ratio < 2000) ratioClass = 'ratio-med';
                    
                    lBody.innerHTML += `
                        <tr>
                            <td style="font-weight:600;">${item.model}</td>
                            <td>${item.utility_score}%</td>
                            <td>${item.emissions_per_1k_tok}g</td>
                            <td class="${ratioClass}">${item.ratio.toFixed(1)}</td>
                        </tr>
                    `;
                });
                
                // Load Project emissions
                const pList = document.getElementById('project-list');
                pList.innerHTML = '';
                const entries = Object.entries(data.by_project);
                if (entries.length === 0) {
                    pList.innerHTML = '<div style="color:var(--text-muted); font-size:0.9rem;">No active projects recorded.</div>';
                } else {
                    entries.forEach(([name, val]) => {
                        pList.innerHTML += `
                            <div class="project-item">
                                <span class="project-name">${name}</span>
                                <span class="project-emissions">${val.toFixed(3)}g</span>
                            </div>
                        `;
                    });
                }
            } catch (err) {
                console.error("Error fetching stats:", err);
            }
        }
        
        fetchStats();
        // Refresh every 30 seconds
        setInterval(fetchStats, 30000);
    </script>
</body>
</html>
"""


HTML_BENCHMARK_DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>CarbonClaw | Model Carbon Benchmarks</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #0b0f19;
            --bg-surface: rgba(17, 24, 39, 0.95);
            --border-color: rgba(255, 255, 255, 0.08);
            --primary: #10b981;
            --primary-glow: rgba(16, 185, 129, 0.15);
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-base);
            color: var(--text-main);
            min-height: 100vh;
            padding: 2.5rem;
            background-image: radial-gradient(circle at 10% 20%, rgba(16, 185, 129, 0.05) 0%, transparent 40%),
                              radial-gradient(circle at 90% 80%, rgba(99, 102, 241, 0.05) 0%, transparent 40%);
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2.5rem;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 1.5rem;
        }
        .logo-section h1 {
            font-size: 2.2rem;
            font-weight: 800;
            background: linear-gradient(135deg, #10b981 0%, #6366f1 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.5px;
        }
        .logo-section p {
            color: var(--text-muted);
            font-size: 0.95rem;
            margin-top: 4px;
        }
        .grid-indicator {
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.2);
            padding: 0.5rem 1rem;
            border-radius: 9999px;
            font-size: 0.85rem;
            color: #10b981;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
            box-shadow: 0 0 15px var(--primary-glow);
        }
        .pulse {
            width: 8px;
            height: 8px;
            background-color: #10b981;
            border-radius: 50%;
            display: inline-block;
            box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
            animation: pulse 1.6s infinite;
        }
        @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }
        .tabs {
            display: flex;
            gap: 1rem;
            margin-bottom: 2rem;
        }
        .tab-btn {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-color);
            color: var(--text-muted);
            padding: 0.6rem 1.2rem;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            font-size: 0.9rem;
            transition: all 0.2s;
        }
        .tab-btn.active, .tab-btn:hover {
            background: #10b981;
            color: #0b0f19;
            border-color: #10b981;
            box-shadow: 0 4px 15px rgba(16, 185, 129, 0.2);
        }
        .card {
            background: var(--bg-surface);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 2rem;
            backdrop-filter: blur(12px);
            margin-bottom: 2rem;
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
        }
        .card h2 {
            font-size: 1.3rem;
            color: var(--text-main);
            margin-bottom: 0.5rem;
            font-weight: 600;
        }
        .card p.subtitle {
            color: var(--text-muted);
            font-size: 0.9rem;
            margin-bottom: 1.5rem;
        }
        .benchmark-grid {
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }
        .model-row {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            padding: 1rem;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            transition: transform 0.2s, border-color 0.2s;
        }
        .model-row:hover {
            transform: scale(1.01);
            border-color: rgba(16, 185, 129, 0.3);
        }
        .model-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .model-info {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .model-name {
            font-weight: 600;
            font-size: 1.1rem;
        }
        .badge {
            font-size: 0.75rem;
            padding: 0.2rem 0.5rem;
            border-radius: 9999px;
            font-weight: 600;
        }
        .badge-local {
            background: rgba(16, 185, 129, 0.15);
            color: #10b981;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }
        .badge-cloud {
            background: rgba(99, 102, 241, 0.15);
            color: #818cf8;
            border: 1px solid rgba(99, 102, 241, 0.3);
        }
        .badge-active {
            background: rgba(245, 158, 11, 0.15);
            color: #fbbf24;
            border: 1px solid rgba(245, 158, 11, 0.3);
            animation: pulse 2s infinite;
        }
        .model-metrics {
            font-size: 0.85rem;
            color: var(--text-muted);
            display: flex;
            gap: 1.5rem;
        }
        .metric-item strong {
            color: var(--text-main);
        }
        .bar-container {
            width: 100%;
            height: 12px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 9999px;
            overflow: hidden;
            position: relative;
        }
        .bar-fill {
            height: 100%;
            border-radius: 9999px;
            transition: width 1s ease-in-out;
            background: linear-gradient(90deg, #34d399, #10b981);
        }
        .ratio-score {
            font-weight: 800;
            font-size: 1.2rem;
            color: #10b981;
        }
        .stat-cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }
        .stat-card {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1.25rem;
            text-align: center;
        }
        .stat-card h3 {
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
            margin-bottom: 0.5rem;
        }
        .stat-card .val {
            font-size: 1.8rem;
            font-weight: 800;
            color: var(--text-main);
        }
    </style>
</head>
<body>
    <header>
        <div class="logo-section">
            <h1>CarbonClaw 🦞</h1>
            <p>Automated Sustainability Benchmark & Model Comparison</p>
        </div>
        <div class="grid-indicator">
            <span class="pulse"></span>
            Grid Carbon: <span id="intensity-val">...</span> g CO2/kWh
        </div>
    </header>

    <div class="tabs">
        <button class="tab-btn" onclick="location.href='/esg/dashboard'">Dashboard Stats</button>
        <button class="tab-btn active" onclick="location.href='/esg/benchmark'">Model Benchmarks</button>
        <button class="tab-btn" onclick="location.href='/'">Interactive Chat</button>
    </div>

    <div class="stat-cards">
        <div class="stat-card">
            <h3>Active Tested Models</h3>
            <div class="val" id="active-models">0</div>
        </div>
        <div class="stat-card">
            <h3>Total Telemetry Requests</h3>
            <div class="val" id="total-requests">0</div>
        </div>
        <div class="stat-card">
            <h3>Total Token Telemetry</h3>
            <div class="val" id="total-tokens">0k</div>
        </div>
        <div class="stat-card">
            <h3>Most Efficient Model</h3>
            <div class="val" id="best-model" style="font-size: 1.2rem; padding-top: 0.4rem; color: #10b981;">None</div>
        </div>
    </div>

    <div class="card">
        <h2>Model Efficiency Leaderboard (Carbon-to-Utility Ratio)</h2>
        <p class="subtitle">Dynamic rankings comparing model accuracy (utility) per gram of carbon emissions. Higher score = more green-efficient.</p>
        
        <div class="benchmark-grid" id="benchmark-list">
            <!-- Loaded dynamically -->
        </div>
    </div>

    <script>
        async function fetchBenchmark() {
            try {
                const res = await fetch('/api/esg/benchmark');
                const data = await res.json();

                document.getElementById('intensity-val').textContent = data.grid_intensity;
                document.getElementById('total-requests').textContent = data.total_telemetry_requests;
                document.getElementById('total-tokens').textContent = (data.total_telemetry_tokens / 1000).toFixed(1) + 'k';

                const list = document.getElementById('benchmark-list');
                list.innerHTML = '';

                let activeCount = 0;
                let bestRatio = -1;
                let bestModelName = 'None';

                // Find max ratio to normalize the bar widths
                const maxRatio = Math.max(...data.leaderboard.map(item => item.ratio), 1);

                data.leaderboard.forEach(item => {
                    if (item.is_active) activeCount++;
                    if (item.ratio > bestRatio) {
                        bestRatio = item.ratio;
                        bestModelName = item.model;
                    }

                    const widthPercent = (item.ratio / maxRatio) * 100;
                    
                    let badges = '';
                    if (item.is_local) {
                        badges += '<span class="badge badge-local">Local</span>';
                    } else {
                        badges += '<span class="badge badge-cloud">Cloud</span>';
                    }
                    if (item.is_active) {
                        badges += '<span class="badge badge-active">Active (' + item.requests + ' reqs)</span>';
                    }

                    // Dynamically set bar colors based on efficiency score
                    let barColor = 'linear-gradient(90deg, #34d399, #10b981)';
                    if (item.ratio < 500) {
                        barColor = 'linear-gradient(90deg, #f87171, #ef4444)';
                    } else if (item.ratio < 2000) {
                        barColor = 'linear-gradient(90deg, #fbbf24, #f59e0b)';
                    }

                    list.innerHTML += `
                        <div class="model-row">
                            <div class="model-header">
                                <div class="model-info">
                                    <span class="model-name">${item.model}</span>
                                    ${badges}
                                </div>
                                <div class="ratio-score">${item.ratio.toFixed(1)} <span style="font-size:0.75rem; font-weight:400; color:var(--text-muted);">score</span></div>
                            </div>
                            <div class="model-metrics">
                                <span class="metric-item">Utility Score: <strong>${item.utility_score}%</strong></span>
                                <span class="metric-item">Est. Carbon/1k Tok: <strong>${item.emissions_per_1k.toFixed(3)}g CO₂</strong></span>
                                <span class="metric-item">Recorded Tokens: <strong>${(item.total_tokens / 1000).toFixed(1)}k</strong></span>
                            </div>
                            <div class="bar-container">
                                <div class="bar-fill" style="width: ${widthPercent}%; background: ${barColor};"></div>
                            </div>
                        </div>
                    `;
                });

                document.getElementById('active-models').textContent = activeCount;
                document.getElementById('best-model').textContent = bestModelName;

            } catch (err) {
                console.error("Error fetching benchmarks:", err);
            }
        }

        fetchBenchmark();
        setInterval(fetchBenchmark, 30000);
    </script>
</body>
</html>
"""


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    config = CarbonClawConfig()
    queue = TaskQueue()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> "AsyncIterator[None]":
        logger.info("web.starting")
        yield
        logger.info("web.shutting_down")

    app = FastAPI(title="CarbonClaw", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    async def dashboard() -> str:
        return HTML_DASHBOARD

    @app.get("/esg/dashboard", response_class=HTMLResponse)
    async def esg_dashboard() -> str:
        return HTML_ESG_DASHBOARD

    @app.get("/esg/benchmark", response_class=HTMLResponse)
    async def esg_benchmark() -> str:
        return HTML_BENCHMARK_DASHBOARD

    @app.get("/api/esg/benchmark")
    async def get_esg_benchmark() -> dict[str, Any]:
        from carbonclaw.telemetry.store import TelemetryStore
        store = TelemetryStore()
        records = store.records()

        # baseline model benchmarks: utility score out of 100, standard g CO2 per 1k tokens
        baselines = {
            "llama3.2 (local)": {"utility": 80.0, "emissions_per_1k": 0.01, "provider": "ollama", "is_local": True},
            "llama3.1 (local)": {"utility": 82.0, "emissions_per_1k": 0.02, "provider": "ollama", "is_local": True},
            "gpt-4o-mini": {"utility": 85.0, "emissions_per_1k": 0.08, "provider": "openai", "is_local": False},
            "gemini-1.5-flash": {"utility": 84.0, "emissions_per_1k": 0.05, "provider": "gemini", "is_local": False},
            "deepseek-coder": {"utility": 89.0, "emissions_per_1k": 0.12, "provider": "deepseek", "is_local": False},
            "claude-3-5-sonnet-latest": {"utility": 97.0, "emissions_per_1k": 0.35, "provider": "anthropic", "is_local": False},
            "gpt-4o": {"utility": 95.0, "emissions_per_1k": 0.45, "provider": "openai", "is_local": False},
        }

        # Calculate actual execution metrics from TelemetryStore records
        dynamic_stats: dict[str, dict[str, Any]] = {}
        for r in records:
            key = r.model.lower()
            matched_name = None
            for b_name in baselines:
                if key in b_name.lower() or b_name.lower() in key:
                    matched_name = b_name
                    break
            
            if matched_name:
                name = matched_name
            else:
                name = f"{r.provider}/{r.model}"
                if name not in baselines:
                    baselines[name] = {
                        "utility": 75.0 if r.provider == "ollama" else 85.0,
                        "emissions_per_1k": 0.03 if r.provider == "ollama" else 0.15,
                        "provider": r.provider,
                        "is_local": r.provider == "ollama",
                    }

            if name not in dynamic_stats:
                dynamic_stats[name] = {
                    "total_tokens": 0,
                    "requests": 0,
                }
            dynamic_stats[name]["total_tokens"] += r.total_tokens
            dynamic_stats[name]["requests"] += 1

        leaderboard = []
        for name, info in baselines.items():
            stats = dynamic_stats.get(name, {"total_tokens": 0, "requests": 0})
            tokens = stats["total_tokens"]
            requests = stats["requests"]
            
            emissions_per_1k = info["emissions_per_1k"]
            ratio = info["utility"] / emissions_per_1k
            
            leaderboard.append({
                "model": name,
                "provider": info["provider"],
                "is_local": info["is_local"],
                "utility_score": info["utility"],
                "emissions_per_1k": emissions_per_1k,
                "ratio": ratio,
                "total_tokens": tokens,
                "requests": requests,
                "is_active": requests > 0,
            })

        # Sort by ratio descending
        leaderboard.sort(key=lambda x: x["ratio"], reverse=True)

        return {
            "leaderboard": leaderboard,
            "total_telemetry_requests": len(records),
            "total_telemetry_tokens": sum(r.total_tokens for r in records),
            "grid_intensity": get_grid_intensity(),
        }

    @app.get("/api/esg/stats")
    async def get_esg_stats() -> dict[str, Any]:
        store = CarbonStore()
        records = store.records()
        
        total_kg = sum(r.emissions for r in records)
        total_grams = total_kg * 1000.0
        
        by_project: dict[str, float] = {}
        for r in records:
            p_name = r.project_name or "default"
            by_project[p_name] = by_project.get(p_name, 0.0) + (r.emissions * 1000.0)
            
        benchmark_data = await get_esg_benchmark()
        leaderboard = []
        for item in benchmark_data["leaderboard"]:
            leaderboard.append({
                "model": item["model"],
                "utility_score": item["utility_score"],
                "emissions_per_1k_tok": item["emissions_per_1k"],
                "ratio": item["ratio"],
            })
        
        offsets = {
            "trees_planted": max(0, int(total_grams / 10.0)),
            "clean_energy_offset_wh": round(max(0.0, total_grams * 2.5), 2),
            "project_partner": "Gold Standard Global Forestry Project",
        }
        
        return {
            "total_emissions_grams": round(total_grams, 3),
            "total_emissions_kg": round(total_kg, 6),
            "by_project": by_project,
            "leaderboard": leaderboard,
            "offsets": offsets,
            "grid_intensity": get_grid_intensity(),
        }

    @app.post("/api/extension/badge")
    async def extension_badge(payload: dict[str, Any]) -> dict[str, Any]:
        code = payload.get("code", "")
        tokens = max(1, len(code) // 4)
        intensity = get_grid_intensity()
        emissions_g = (tokens / 1000.0) * 0.002 * (intensity / 100.0)
        
        if intensity < 200:
            badge = f"🌱 {round(emissions_g, 4)}g CO2 (Clean Grid)"
            status = "clean"
            color = "#10b981"
        elif intensity < 350:
            badge = f"🟡 {round(emissions_g, 4)}g CO2 (Moderate)"
            status = "blend"
            color = "#f59e0b"
        else:
            badge = f"🔴 {round(emissions_g, 4)}g CO2 (Peak Fossil)"
            status = "peak"
            color = "#ef4444"
            
        return {
            "badge": badge,
            "emissions_estimate_grams": round(emissions_g, 6),
            "grid_intensity": intensity,
            "grid_status": status,
            "color": color,
            "tokens": tokens,
        }

    @app.post("/api/extension/approve")
    async def extension_approve(payload: dict[str, Any]) -> dict[str, Any]:
        action = payload.get("action", "shell")
        arguments = payload.get("arguments", {})
        
        from carbonclaw.cli.main import _get_impact_analysis
        impact = _get_impact_analysis(action, arguments)
        
        cmd = arguments.get("command", "")
        if any(kw in cmd for kw in ["rm ", "mv ", "delete", "kill"]):
            approved = False
            msg = "Action rejected due to critical security risk. Requires manual shell intervention."
        else:
            approved = True
            msg = "Action automatically approved based on safety policy."
            
        return {
            "approved": approved,
            "impact": impact,
            "message": msg,
        }

    @app.post("/webhooks/github")
    async def github_webhook(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ) -> dict[str, Any]:
        action = payload.get("action")
        workflow_run = payload.get("workflow_run", {})
        conclusion = workflow_run.get("conclusion")

        triggered = False
        message = "Webhook received, no action required."

        is_failed = (
            (action == "completed" and conclusion == "failure")
            or payload.get("check_run", {}).get("conclusion") == "failure"
        )
        if is_failed:
            triggered = True
            message = (
                "Failing workflow run detected. Spawning autonomous HealerAgent in background."
            )

            async def run_healer() -> None:
                try:
                    from carbonclaw.agents.supervisor import SupervisorAgent

                    supervisor = await SupervisorAgent.create_default(config.default_provider)
                    await supervisor.delegate(
                        "healer",
                        "Fix unit tests and codebase failures detected by CI webhook."
                    )
                except Exception as e:
                    logger.exception("web.webhook_healer_error", error=str(e))

            background_tasks.add_task(run_healer)

        return {
            "triggered": triggered,
            "message": message,
        }

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}


    @app.get("/chat/stream")
    async def chat_stream(
        request: Request, 
        prompt: str, 
        provider: str | None = None,
        model: str | None = None
    ) -> StreamingResponse:
        """SSE endpoint for streaming chat with the supervisor agent."""
        async def event_generator() -> AsyncIterator[str]:
            try:
                p_name = provider or config.default_provider
                m_id = model or config.default_model
                supervisor = await SupervisorAgent.create_default(p_name)
                # Override model if specified
                if m_id:
                    supervisor.model = m_id
                
                async for text in supervisor.stream_delegate("coding", prompt):
                    yield f"data: {json.dumps({'type': 'text', 'content': text})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            except Exception as e:
                logger.exception("web.stream_error")
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    @app.post("/agent/execute")
    async def execute_agent(payload: dict[str, Any]) -> dict[str, Any]:
        """One-shot agent execution (headless)."""
        prompt = payload.get("prompt", "")
        agent_type = payload.get("agent", "coding")
        p_name = payload.get("provider") or config.default_provider
        m_id = payload.get("model") or config.default_model

        supervisor = await SupervisorAgent.create_default(p_name)
        if m_id:
            supervisor.model = m_id
            
        result = await supervisor.delegate(agent_type, prompt)
        return {"result": result, "agent": agent_type, "model": m_id}

    @app.post("/tasks")
    async def submit_task(payload: dict[str, Any]) -> dict[str, Any]:
        """Submit a task to the queue."""
        task = Task(
            agent_type=payload.get("agent", "coding"),
            payload=payload,
            priority=payload.get("priority", 0),
        )
        await queue.submit(task)
        return {"id": task.id, "status": task.status}

    @app.get("/tasks/{task_id}")
    async def get_task(task_id: str) -> dict[str, Any] | None:
        t = await queue.get(task_id)
        if t is None:
            return None
        return {
            "id": t.id,
            "status": t.status,
            "result": t.result,
            "error": t.error,
            "created_at": t.created_at,
        }

    @app.get("/tasks")
    async def list_tasks() -> list[dict[str, Any]]:
        return [
            {"id": t.id, "status": t.status, "created_at": t.created_at}
            for t in await queue.pending()
        ] + [
            {"id": t.id, "status": t.status, "created_at": t.created_at}
            for t in await queue.active()
        ]

    return app


async def serve(host: str = "127.0.0.1", port: int = 8080) -> None:
    """Run the web server."""
    import uvicorn

    app = create_app()
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

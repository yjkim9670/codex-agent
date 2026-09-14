#!/usr/bin/env node
/* Generates a self-contained KST token-usage report from the deduplicated account ledger. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const input = '/Users/dinya/.codex-workbench/accounts/yangjina-kim/codex_account_token_usage.json';
const usageHistoryInput = '/Users/dinya/.codex-workbench/accounts/yangjina-kim/codex_usage_history.json';
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const output = path.resolve(scriptDir, '../docs/token-usage-last-30-days.html');
const ledger = JSON.parse(fs.readFileSync(input, 'utf8'));
const sessions = Object.values(ledger.by_session);
const kstParts = (date) => Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
}).formatToParts(date).filter(({ type }) => type !== 'literal').map(({ type, value }) => [type, value]));
const dayKey = (date) => {
  const parts = kstParts(date);
  return `${parts.year}-${parts.month}-${parts.day}`;
};
const timestampKst = (date) => {
  const parts = kstParts(date);
  return `${dayKey(date)} ${parts.hour}:${parts.minute}`;
};
const last = new Date(Math.max(...sessions.map((item) => Date.parse(item.updated_at))));
const lastDay = dayKey(last);
const lastKstMidnight = new Date(`${lastDay}T00:00:00+09:00`);
const from = new Date(lastKstMidnight);
from.setUTCDate(from.getUTCDate() - 29);
const included = sessions.filter((item) => new Date(item.updated_at) >= from && new Date(item.updated_at) <= last);
const usageHistory = fs.existsSync(usageHistoryInput)
  ? JSON.parse(fs.readFileSync(usageHistoryInput, 'utf8')) : {};
const limitSamples = Array.isArray(usageHistory.account_limit_samples)
  ? usageHistory.account_limit_samples.slice().sort((a, b) => Date.parse(a.recorded_at) - Date.parse(b.recorded_at)) : [];
const resetDetections = { fiveHour: [], weekly: [] };
for (let index = 1; index < limitSamples.length; index += 1) {
  const previous = limitSamples[index - 1];
  const current = limitSamples[index];
  const observedAt = new Date(current.recorded_at || current.limits_observed_at);
  if (Number.isNaN(observedAt) || observedAt < from || observedAt > last) continue;
  // Keep this identical to the server's reset detector: a timestamp revision
  // alone is not a reset; the observed percentage must actually decline.
  for (const [key, resultKey] of [['five_hour_used_percent', 'fiveHour'], ['weekly_used_percent', 'weekly']]) {
    const before = Number(previous[key]);
    const after = Number(current[key]);
    if (Number.isFinite(before) && Number.isFinite(after) && before > 0.1 && after + 0.1 < before) {
      resetDetections[resultKey].push({ observedAt, before, after });
    }
  }
}
const hours = Array(24).fill(0);
const days = new Map();
for (const item of included) {
  const date = new Date(item.updated_at);
  hours[Number(kstParts(date).hour)] += item.total_tokens;
  const day = dayKey(date);
  days.set(day, (days.get(day) || 0) + item.total_tokens);
}
const dayLabels = [];
for (let date = new Date(from); date <= lastKstMidnight; date.setUTCDate(date.getUTCDate() + 1)) dayLabels.push(dayKey(date));
const daily = dayLabels.map((day) => days.get(day) || 0);
const total = included.reduce((sum, item) => sum + item.total_tokens, 0);
const f = new Intl.NumberFormat('en-US');
const m = (value) => `${(value / 1e6).toFixed(1)}M`;
const maxHour = Math.max(...hours);
const maxDay = Math.max(...daily);
const fiveHour = hours.map((_, start) => Array.from({ length: 5 }, (_, index) => hours[(start + index) % 24]).reduce((sum, value) => sum + value, 0));
const bestWindowStart = fiveHour.indexOf(Math.max(...fiveHour));
const bestWindowEnd = (bestWindowStart + 5) % 24;
const svgBars = (values, labels, max, width, height, labelEvery = 1) => values.map((value, index) => {
  const gap = 7;
  const barWidth = (width - gap * (values.length - 1)) / values.length;
  const barHeight = max ? value / max * height : 0;
  const x = index * (barWidth + gap);
  const y = height - barHeight;
  const label = index % labelEvery === 0 ? `<text x="${x + barWidth / 2}" y="${height + 26}" text-anchor="middle">${labels[index]}</text>` : '';
  return `<g><title>${labels[index]}: ${f.format(value)} tokens</title><rect x="${x}" y="${y}" width="${barWidth}" height="${barHeight}" rx="3"/>${label}</g>`;
}).join('');
const hourBars = svgBars(hours, hours.map((_, i) => String(i).padStart(2, '0')), maxHour, 984, 230, 1);
const dailyBars = svgBars(daily, dayLabels.map((day) => day.slice(5)), maxDay, 984, 180, 3);
const resetMarkerSvg = (items, color, offset) => items.map((item, index) => {
  const dayIndex = dayLabels.indexOf(dayKey(item.observedAt));
  if (dayIndex < 0) return '';
  const gap = 7;
  const barWidth = (984 - gap * (daily.length - 1)) / daily.length;
  const x = dayIndex * (barWidth + gap) + barWidth / 2;
  const y = 14 + ((index + offset) % 3) * 13;
  return `<g><title>${timestampKst(item.observedAt)} KST 감지 · ${item.before}% → ${item.after}%</title><circle cx="${x}" cy="${y}" r="4" fill="${color}"/></g>`;
}).join('');
const fiveHourMarkers = resetMarkerSvg(resetDetections.fiveHour, '#da1e28', 0);
const weeklyMarkers = resetMarkerSvg(resetDetections.weekly, '#8a3ffc', 1);
const resetList = (items, label) => items.slice(-20).reverse().map((item) =>
  `<li><b>${timestampKst(item.observedAt)} KST</b> <span>${label} · ${item.before}% → ${item.after}%</span></li>`
).join('') || '<li><span>이 기간에 감지된 리셋이 없습니다.</span></li>';
const peakHour = hours.indexOf(maxHour);
const range = `${dayKey(from)} 00:00 – ${timestampKst(last)} KST`;
const html = `<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Codex token usage — last 30 days</title><style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
:root{--ink:#161616;--muted:#525252;--line:#d0d0d0;--panel:#f4f4f4;--blue:#0f62fe;--teal:#005d5d;--five:#da1e28;--week:#8a3ffc}*{box-sizing:border-box}body{margin:0;background:#fff;color:var(--ink);font-family:'IBM Plex Sans KR',sans-serif}main{max-width:1120px;margin:40px auto;padding:0 28px}h1{font-size:28px;margin:0 0 8px;font-weight:600}p{color:var(--muted);margin:0}.meta{font-family:'IBM Plex Mono',monospace;font-size:13px;margin:20px 0 32px}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);border:1px solid var(--line);margin-bottom:32px}.stat{background:#fff;padding:18px}.stat b{display:block;font:500 26px 'IBM Plex Mono',monospace;margin-bottom:5px}.stat span{font-size:13px;color:var(--muted)}section{border:1px solid var(--line);padding:24px;margin:18px 0 0}h2{font-size:18px;margin:0 0 6px}section p{font-size:14px;margin-bottom:20px}svg{width:100%;height:auto;overflow:visible}rect{fill:var(--blue)}.daily rect{fill:var(--teal)}text{font:12px 'IBM Plex Mono',monospace;fill:var(--muted)}.rule{stroke:var(--line);stroke-width:1}.legend{display:flex;gap:16px;font-size:13px;color:var(--muted);margin:-6px 0 14px}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px}.five{background:var(--five)}.week{background:var(--week)}.reset-list{columns:2;gap:32px;padding-left:18px;margin:8px 0 0}.reset-list li{break-inside:avoid;font:12px 'IBM Plex Mono',monospace;margin:0 0 9px}.reset-list span{color:var(--muted)}.foot{font-size:12px;margin-top:24px;line-height:1.6}@media(max-width:600px){main{margin:24px auto;padding:0 16px}.stats{grid-template-columns:1fr}section{padding:16px}h1{font-size:24px}.reset-list{columns:1}}</style></head>
<body><main><h1>Codex 토큰 사용량 · 최근 30일</h1><p>계정 공유 원장 기준 · Workbench 간 복제 레코드는 중복 합산하지 않음</p><p class="meta">${range}</p>
<div class="stats"><div class="stat"><b>${m(total)}</b><span>총 토큰</span></div><div class="stat"><b>${included.length}</b><span>완료 세션</span></div><div class="stat"><b>${String(peakHour).padStart(2, '0')}:00</b><span>최대 사용 시각 (KST)</span></div></div>
<section><h2>시간대별 토큰 합계</h2><p>각 세션의 완료 시각을 KST 시간대에 배정했습니다. 막대 위에 올리면 정확한 토큰 수가 보입니다.</p><svg viewBox="0 0 984 270" role="img" aria-label="KST hourly token usage"><line class="rule" x1="0" x2="984" y1="230" y2="230"/>${hourBars}</svg></section>
<section><h2>날짜별 토큰 합계와 리셋 감지</h2><p>원장 관측값에서 사용률이 실제로 하락한 시각을 표시합니다. 예정 시각(<code>resets_at</code>)의 변경만으로는 감지하지 않습니다.</p><div class="legend"><span><i class="dot five"></i>5시간 리셋 (${resetDetections.fiveHour.length})</span><span><i class="dot week"></i>주간 리셋 (${resetDetections.weekly.length})</span></div><svg class="daily" viewBox="0 0 984 220" role="img" aria-label="daily token usage with reset detections"><line class="rule" x1="0" x2="984" y1="180" y2="180"/>${dailyBars}${fiveHourMarkers}${weeklyMarkers}</svg></section>
<section><h2>리셋 감지 시각</h2><p>각 항목은 API를 관측한 시각이며, 실제 서버 경계는 바로 앞 관측과 이 시각 사이에 있었을 수 있습니다. 최근 20건씩 표시합니다.</p><h3>5시간 리셋</h3><ul class="reset-list">${resetList(resetDetections.fiveHour, '5시간')}</ul><h3>주간 리셋</h3><ul class="reset-list">${resetList(resetDetections.weekly, '주간')}</ul></section>
<section><h2>5시간 창 후보</h2><p>시간대 합계가 가장 높은 연속 5시간입니다. 완료 시각 기준 집계이므로, 실제 토큰 생성 시각과는 약간의 차이가 있을 수 있습니다.</p><div class="stats"><div class="stat"><b>${String(bestWindowStart).padStart(2, '0')}:00–${String(bestWindowEnd).padStart(2, '0')}:00</b><span>가장 강한 5시간 (KST)</span></div><div class="stat"><b>${m(fiveHour[bestWindowStart])}</b><span>해당 창의 토큰 합계</span></div></div></section>
<p class="foot">원본: <code>${input}</code><br>토큰은 input + output 기준 <code>total_tokens</code>이며, 캐시 입력도 포함됩니다. 기준 원장의 최신 기록은 ${ledger.updated_at}입니다.</p></main></body></html>`;
fs.writeFileSync(output, html);
console.log(`Wrote ${output}`);

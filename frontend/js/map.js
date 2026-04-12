// ── Map Setup ──────────────────────────────────────────────────
const map = L.map("map", {
    zoomControl: false,
    zoomDelta: 0.5,
    zoomSnap: 0.5,
    wheelDebounceTime: 80,
    wheelPxPerZoomLevel: 120,
}).setView([35.5, -97.5], 7);
L.control.zoom({ position: "topright", zoomInText: "+", zoomOutText: "\u2212" }).addTo(map);

L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://osm.org/copyright">OSM</a>',
    maxZoom: 18,
    subdomains: "abcd",
}).addTo(map);

// ── State ──────────────────────────────────────────────────────
// Foundation layers (always on, independent of HPSAs)
let countyLayer = null;
let countyLabels = null;
let countyData = null;
let tribalLayer = null;
let tribalLoaded = false;
let tribalData = null; // eagerly loaded for Tribal tab lookups
const keyFacLayers = {};

// 3 HPSA type layers — each type uses intersection of checked disciplines
let hpsaGeoLayer = null;
let hpsaPopLayer = null;
let hpsaPopLabels = null;
let hpsaFacLayer = null;

// MUA/MUP overlay
let muaCountyLayer = null;
let muaTractLayer = null;
let muaLoaded = false;

// NHSC site overlay
let nhscLayer = null;
let nhscLoaded = false;

// Data layer state
let activeDataView = null;
let dataLayer = null;

// NPI providers
let providerCluster = null;
let npiLayer = null;
const providerData = {};
const loadedProviders = new Set();

const HPSA_ZOOM_THRESHOLD = 10;
let hpsaVisible = true;

const dataCache = {};

// ── Color Scales ───────────────────────────────────────────────

function hpsaColor(score) {
    if (score == null) return "#888";
    const s = Math.floor(score);
    if (s <= 9)  return "#f59e0b";  // amber
    if (s <= 14) return "#f97316";  // orange
    if (s <= 19) return "#ef4444";  // red
    return "#dc2626";                   // deep red
}

function geoColor() { return "#ff2020"; }

function geoBorderWeight(score) {
    if (score == null) return 2;
    if (score >= 18) return 3;
    if (score >= 13) return 2.5;
    return 2;
}

function popFill(score) {
    if (score == null) return "rgba(100,100,100,0.08)";
    const s = Math.floor(score);
    if (s <= 9)  return "rgba(245, 158, 11, 0.15)";
    if (s <= 14) return "rgba(249, 115, 22, 0.20)";
    if (s <= 19) return "rgba(239, 68, 68, 0.25)";
    return "rgba(220, 38, 38, 0.32)";
}

function popBorder(score) {
    if (score == null) return "rgba(100,100,100,0.2)";
    const s = Math.floor(score);
    if (s <= 9)  return "rgba(245, 158, 11, 0.40)";
    if (s <= 14) return "rgba(249, 115, 22, 0.45)";
    if (s <= 19) return "rgba(239, 68, 68, 0.50)";
    return "rgba(220, 38, 38, 0.55)";
}

function severityLabel(score) {
    if (score >= 20) return { text: "Critical", cls: "badge-critical" };
    if (score >= 15) return { text: "High", cls: "badge-high" };
    if (score >= 10) return { text: "Moderate", cls: "badge-moderate" };
    return { text: "Low", cls: "badge-low" };
}

// ── Utilities ──────────────────────────────────────────────────
function fmt(val) {
    if (val == null || val === "") return "N/A";
    if (typeof val === "number") return val.toLocaleString();
    return val;
}
function pct(val) { return val == null || val === "" ? "N/A" : val + "%"; }
function money(val) { return val == null ? "N/A" : "$" + Number(val).toLocaleString(); }
function insBar(name, count, total, color) {
    const p = total > 0 ? Math.round((count / total) * 100) : 0;
    return `<div class="detail-row" style="flex-direction:column;gap:4px">
        <div style="display:flex;justify-content:space-between;align-items:center">
            <span class="label" style="color:${color}">${name}</span>
            <span class="value">${p}% <span style="color:#667;font-size:0.7rem">(${count.toLocaleString()})</span></span>
        </div>
        <div style="height:4px;background:rgba(255,255,255,0.08);border-radius:2px;overflow:hidden">
            <div style="height:100%;width:${p}%;background:${color};border-radius:2px"></div>
        </div>
    </div>`;
}

function loadData(url) {
    if (dataCache[url]) return Promise.resolve(dataCache[url]);
    return fetch(url).then(r => r.json()).then(data => { dataCache[url] = data; return data; });
}

function interpolate(low, high, t) {
    const l = [parseInt(low.slice(1, 3), 16), parseInt(low.slice(3, 5), 16), parseInt(low.slice(5, 7), 16)];
    const h = [parseInt(high.slice(1, 3), 16), parseInt(high.slice(3, 5), 16), parseInt(high.slice(5, 7), 16)];
    return `rgb(${Math.round(l[0] + (h[0] - l[0]) * t)},${Math.round(l[1] + (h[1] - l[1]) * t)},${Math.round(l[2] + (h[2] - l[2]) * t)})`;
}

// ── Discipline key mapping ─────────────────────────────────────
const DISCIPLINES = {
    pc: "Primary Care",
    dental: "Dental Health",
    mh: "Mental Health",
};

// ── Detail Panel ───────────────────────────────────────────────
const detailEl = document.getElementById("detail-content");

function trendHtml(p) {
    if (!p.has_trend) return "";
    const prev = p.prev_score;
    const curr = p.score;
    if (prev == null) {
        const next = p.new_score;
        if (next == null) return "";
        const dir = next > prev ? "trend-up" : next < prev ? "trend-down" : "trend-same";
        const arrow = next > p.score ? "\u2191" : next < p.score ? "\u2193" : "\u2192";
        return `<div class="detail-row"><span class="label">Incoming Score</span><span class="value ${dir}">${p.score} ${arrow} ${next}</span></div>`;
    }
    const dir = curr > prev ? "trend-up" : curr < prev ? "trend-down" : "trend-same";
    const arrow = curr > prev ? "\u2191" : curr < prev ? "\u2193" : "\u2192";
    return `<div class="detail-row"><span class="label">Previous Score</span><span class="value ${dir}">${prev} ${arrow} ${curr}</span></div>`;
}

// ── Profile Pages ──────────────────────────────────────────────

function phoneLink(phone) {
    if (!phone) return "N/A";
    const digits = String(phone).replace(/\D/g, "");
    const display = digits.replace(/(\d{3})(\d{3})(\d{4})/, "($1) $2-$3");
    return `<a href="tel:${digits}" style="color:#6ab4ff;text-decoration:none">${display}</a>`;
}

function addressBlock(p) {
    let html = "";
    if (p.address) html += `<div style="margin:8px 0;color:#bbc;font-size:0.8rem;line-height:1.5">`;
    if (p.address) html += `${p.address}<br>`;
    if (p.city) html += `${p.city}, ${p.state || "OK"} ${p.zip || ""}`;
    if (p.address) html += `</div>`;
    return html;
}

function mapsLink(p) {
    if (!p.address || !p.city) return "";
    const q = encodeURIComponent(`${p.address}, ${p.city}, ${p.state || "OK"} ${p.zip || ""}`);
    return `<a href="https://www.google.com/maps/search/?api=1&query=${q}" target="_blank" rel="noopener" style="color:#6ab4ff;font-size:0.75rem;text-decoration:none">Open in Google Maps &rarr;</a>`;
}

function hpsaBadge(score) {
    if (score == null) return "";
    const sev = severityLabel(score);
    return `${score}/26 <span class="detail-badge ${sev.cls}">${sev.text}</span>`;
}

function multiCountyNote(p) {
    if (!p.from_multi_county) return "";
    return `<div class="profile-desc" style="margin-top:8px;border-top:1px solid #2a2a3d;padding-top:8px">Part of <strong>${p.multi_county_name}</strong> — a multi-county designation. This score applies to the broader region, not this county specifically.</div>`;
}

function showGeoDetail(p) {
    detailEl.innerHTML = `
        <div class="detail-title">${p.name || "Geographic HPSA"}</div>
        <div class="detail-type">Geographic HPSA</div>
        <div class="profile-desc">This entire area lacks sufficient providers. Everyone in this region — regardless of income or insurance — is underserved.</div>
        ${multiCountyNote(p)}
        <div class="detail-section">
            <div class="detail-section-title">HPSA Designation</div>
            <div class="detail-row"><span class="label">Score</span><span class="value">${hpsaBadge(p.score)}</span></div>
            <div class="detail-row"><span class="label">Status</span><span class="value">${p.status}</span></div>
            ${trendHtml(p)}
            <div class="detail-row"><span class="label">Discipline</span><span class="value">${p.discipline}</span></div>
            <div class="detail-row"><span class="label">Designation Type</span><span class="value">${fmt(p.type)}</span></div>
        </div>
        <div class="detail-section">
            <div class="detail-section-title">Area Profile</div>
            <div class="detail-row"><span class="label">Classification</span><span class="value">${fmt(p.rural)}</span></div>
            <div class="detail-row"><span class="label">Provider Ratio</span><span class="value">${fmt(p.provider_ratio)}</span></div>
            <div class="detail-row"><span class="label">Total Population</span><span class="value">${fmt(p.designation_pop)}</span></div>
            <div class="detail-row"><span class="label">Underserved Pop</span><span class="value">${fmt(p.underserved_pop)}</span></div>
            <div class="detail-row"><span class="label">Poverty Rate</span><span class="value">${pct(p.pct_poverty)}</span></div>
        </div>
    `;
}

function showPopDetail(p) {
    detailEl.innerHTML = `
        <div class="detail-title">${p.name || "Population HPSA"}</div>
        <div class="detail-type">Population HPSA</div>
        <div class="profile-desc">Providers exist in this area, but the low-income population cannot access them due to cost, transportation, or acceptance barriers.</div>
        ${multiCountyNote(p)}
        <div class="detail-section">
            <div class="detail-section-title">HPSA Designation</div>
            <div class="detail-row"><span class="label">Score</span><span class="value">${hpsaBadge(p.score)}</span></div>
            <div class="detail-row"><span class="label">Status</span><span class="value">${p.status}</span></div>
            ${trendHtml(p)}
            <div class="detail-row"><span class="label">Discipline</span><span class="value">${p.discipline}</span></div>
        </div>
        <div class="detail-section">
            <div class="detail-section-title">Underserved Population</div>
            <div class="detail-row"><span class="label">Classification</span><span class="value">${fmt(p.rural)}</span></div>
            <div class="detail-row"><span class="label">Provider Ratio</span><span class="value">${fmt(p.provider_ratio)}</span></div>
            <div class="detail-row"><span class="label">Low-Income Pop</span><span class="value">${fmt(p.designation_pop)}</span></div>
            <div class="detail-row"><span class="label">Underserved Pop</span><span class="value">${fmt(p.underserved_pop)}</span></div>
            <div class="detail-row"><span class="label">Poverty Rate</span><span class="value">${pct(p.pct_poverty)}</span></div>
        </div>
    `;
}

function showFacDetail(p) {
    let facLabel = "Healthcare Facility";
    const t = p.type || "";
    if (t.includes("Federally Qualified")) facLabel = "Federally Qualified Health Center";
    else if (t.includes("Indian") || t.includes("Tribal")) facLabel = "IHS / Tribal Health Facility";
    else if (t.includes("Rural")) facLabel = "Rural Health Clinic";
    else if (t.includes("Correctional")) facLabel = "Correctional Facility";

    const countyHpsa = p.county ? getCountyHpsaHtml(p.county) : "";
    const countyHeader = p.county ? `
        <div style="border-top:2px solid #2a2a3d;margin:12px 0;padding-top:12px">
            <div class="detail-section-title">Area HPSA Designations — ${p.county} County</div>
        </div>
        ${countyHpsa}` : "";

    detailEl.innerHTML = `
        <div class="detail-title">${p.name || "Facility HPSA"}</div>
        <div class="detail-type">${facLabel} &middot; HPSA Facility${p.county ? " &middot; " + p.county + " County" : ""}</div>
        <div class="profile-desc">This facility has been designated as short-staffed by HRSA. It serves a large population relative to its provider capacity.</div>
        <div class="detail-section">
            <div class="detail-section-title">Facility HPSA Designation</div>
            <div class="detail-row"><span class="label">Score</span><span class="value">${hpsaBadge(p.score)}</span></div>
            <div class="detail-row"><span class="label">Status</span><span class="value">${p.status}</span></div>
            <div class="detail-row"><span class="label">Discipline</span><span class="value">${p.discipline}</span></div>
            <div class="detail-row"><span class="label">HPSA ID</span><span class="value">${fmt(p.hpsa_id)}</span></div>
        </div>
        <div class="detail-section">
            <div class="detail-section-title">Service Area</div>
            <div class="detail-row"><span class="label">Classification</span><span class="value">${fmt(p.rural)}</span></div>
            <div class="detail-row"><span class="label">Population Served</span><span class="value">${fmt(p.designation_pop)}</span></div>
            <div class="detail-row"><span class="label">Underserved Pop</span><span class="value">${fmt(p.underserved_pop)}</span></div>
            <div class="detail-row"><span class="label">Poverty Rate</span><span class="value">${pct(p.pct_poverty)}</span></div>
        </div>
        ${countyHeader}
    `;
}

function showHospitalProfile(p) {
    const stars = p.rating && p.rating !== "Not Available" ? "\u2605".repeat(Number(p.rating)) + "\u2606".repeat(5 - Number(p.rating)) : "Not rated";
    detailEl.innerHTML = `
        <div class="detail-title">${p.name}</div>
        <div class="detail-type">Hospital</div>
        ${addressBlock(p)}
        <div style="margin-bottom:8px">${mapsLink(p)}</div>
        <div class="detail-section">
            <div class="detail-section-title">Facility Info</div>
            <div class="detail-row"><span class="label">Type</span><span class="value">${fmt(p.hospital_type)}</span></div>
            <div class="detail-row"><span class="label">Ownership</span><span class="value">${fmt(p.ownership)}</span></div>
            <div class="detail-row"><span class="label">CMS Rating</span><span class="value" style="color:#fbbf24">${stars}</span></div>
            <div class="detail-row"><span class="label">Emergency Services</span><span class="value">${fmt(p.emergency_services)}</span></div>
            <div class="detail-row"><span class="label">Phone</span><span class="value">${phoneLink(p.phone)}</span></div>
        </div>
        <div class="detail-section">
            <div class="detail-section-title">Source</div>
            <div class="detail-row"><span class="label">Data</span><span class="value">${fmt(p.source)}</span></div>
        </div>
    `;
}

function showFqhcProfile(p) {
    detailEl.innerHTML = `
        <div class="detail-title">${p.name}</div>
        <div class="detail-type">Federally Qualified Health Center</div>
        ${addressBlock(p)}
        <div style="margin-bottom:8px">${mapsLink(p)}</div>
        <div class="detail-section">
            <div class="detail-section-title">Facility Info</div>
            <div class="detail-row"><span class="label">Site Type</span><span class="value">${fmt(p.site_type)}</span></div>
            <div class="detail-row"><span class="label">Center Type</span><span class="value">${fmt(p.center_type)}</span></div>
            <div class="detail-row"><span class="label">Phone</span><span class="value">${phoneLink(p.phone)}</span></div>
        </div>
        <div class="detail-section">
            <div class="detail-section-title">About FQHCs</div>
            <div class="profile-desc">FQHCs receive federal funding to provide primary care in underserved areas. They must accept all patients regardless of ability to pay and offer sliding-fee scales.</div>
        </div>
    `;
}

function showIhsProfile(p) {
    detailEl.innerHTML = `
        <div class="detail-title">${p.name}</div>
        <div class="detail-type">IHS / Tribal Health Facility</div>
        ${addressBlock(p)}
        <div style="margin-bottom:8px">${mapsLink(p)}</div>
        <div class="detail-section">
            <div class="detail-section-title">Facility Info</div>
            <div class="detail-row"><span class="label">Facility Type</span><span class="value">${fmt(p.facility_type)}</span></div>
            <div class="detail-row"><span class="label">Tribe / Org</span><span class="value">${fmt(p.tribe)}</span></div>
        </div>
    `;
}

function showRhcProfile(p) {
    detailEl.innerHTML = `
        <div class="detail-title">${p.name}</div>
        <div class="detail-type">Rural Health Clinic</div>
        ${addressBlock(p)}
        <div style="margin-bottom:8px">${mapsLink(p)}</div>
        <div class="detail-section">
            <div class="detail-section-title">Clinic Info</div>
            <div class="detail-row"><span class="label">NPI</span><span class="value">${fmt(p.npi)}</span></div>
            <div class="detail-row"><span class="label">Phone</span><span class="value">${phoneLink(p.phone)}</span></div>
            ${p.county ? `<div class="detail-row"><span class="label">County</span><span class="value">${p.county}</span></div>` : ""}
        </div>
        <div class="detail-section">
            <div class="detail-section-title">About RHCs</div>
            <div class="profile-desc">Rural Health Clinics receive cost-based Medicare reimbursement (typically higher than standard rates). NPs and PAs can serve as the primary provider at RHCs with a physician available for consultation.</div>
        </div>
    `;
}

function showNhscProfile(p) {
    const scoreHtml = [];
    if (p.score_primary_care) scoreHtml.push(`<div class="detail-row"><span class="label">Primary Care</span><span class="value">${hpsaBadge(p.score_primary_care)}</span></div>`);
    if (p.score_dental_health) scoreHtml.push(`<div class="detail-row"><span class="label">Dental</span><span class="value">${hpsaBadge(p.score_dental_health)}</span></div>`);
    if (p.score_mental_health) scoreHtml.push(`<div class="detail-row"><span class="label">Mental Health</span><span class="value">${hpsaBadge(p.score_mental_health)}</span></div>`);

    detailEl.innerHTML = `
        <div class="detail-title">${p.name}</div>
        <div class="detail-type">NHSC Loan Repayment Site</div>
        <div style="margin-bottom:12px;padding:10px;background:rgba(234,179,8,0.08);border:1px solid rgba(234,179,8,0.2);border-radius:8px">
            <div style="font-size:0.82rem;font-weight:600;color:#eab308;margin-bottom:4px">Loan Repayment Eligible</div>
            <div style="font-size:0.75rem;color:#a0a3b5;line-height:1.5">Up to <strong style="color:#fcd34d">$50,000</strong> (LRP) or <strong style="color:#fcd34d">$75,000</strong> (S2S) in student loan repayment for qualifying providers at this site.</div>
        </div>
        <div class="detail-section">
            <div class="detail-section-title">Site Details</div>
            <div class="detail-row"><span class="label">County</span><span class="value">${fmt(p.county)}</span></div>
            <div class="detail-row"><span class="label">Disciplines Needed</span><span class="value">${fmt(p.disciplines_needed)}</span></div>
            <div class="detail-row"><span class="label">Max HPSA Score</span><span class="value">${hpsaBadge(p.max_hpsa_score)}</span></div>
            <div class="detail-row"><span class="label">Auto-HPSA</span><span class="value">${p.is_auto_hpsa ? "Yes" : "No"}</span></div>
        </div>
        ${scoreHtml.length ? `<div class="detail-section">
            <div class="detail-section-title">HPSA Scores by Discipline</div>
            ${scoreHtml.join("")}
        </div>` : ""}
        <div class="detail-section">
            <div class="detail-section-title">About NHSC</div>
            <div class="profile-desc">The National Health Service Corps provides loan repayment and scholarships to healthcare providers who work in underserved areas. Eligible providers include physicians, NPs, PAs, dentists, and behavioral health professionals.</div>
        </div>
    `;
}

function showPharmacyProfile(p) {
    detailEl.innerHTML = `
        <div class="detail-title">${p.name}</div>
        <div class="detail-type">Pharmacy</div>
        ${addressBlock(p)}
        <div style="margin-bottom:8px">${mapsLink(p)}</div>
        <div class="detail-section">
            <div class="detail-section-title">Pharmacy Info</div>
            <div class="detail-row"><span class="label">Specialty</span><span class="value">${fmt(p.specialty)}</span></div>
            <div class="detail-row"><span class="label">NPI</span><span class="value">${fmt(p.npi)}</span></div>
            <div class="detail-row"><span class="label">Phone</span><span class="value">${phoneLink(p.phone)}</span></div>
        </div>
    `;
}

function showClosedProfile(p) {
    detailEl.innerHTML = `
        <div class="detail-title">${p.name}</div>
        <div class="detail-type">Closed Hospital</div>
        ${addressBlock(p)}
        <div class="detail-section">
            <div class="detail-section-title">Closure Info</div>
            <div class="detail-row"><span class="label">Closure Type</span><span class="value">${fmt(p.closure_type)}</span></div>
            <div class="detail-row"><span class="label">Closed</span><span class="value">${p.closure_month || ""} ${p.closure_year}</span></div>
            <div class="detail-row"><span class="label">Beds</span><span class="value">${fmt(p.beds)}</span></div>
            <div class="detail-row"><span class="label">County</span><span class="value">${fmt(p.county)}</span></div>
            <div class="detail-row"><span class="label">Medicare Payment</span><span class="value">${fmt(p.medicare_payment)}</span></div>
        </div>
    `;
}

function showProviderProfile(p) {
    const ins = [];
    if (p.accepts_medicare) ins.push("Medicare");
    if (p.accepts_uhc) ins.push("UHC");

    detailEl.innerHTML = `
        <div class="detail-title">${p.name}</div>
        <div class="detail-type">${p.category || "Provider"}${p.credential ? " &middot; " + p.credential : ""}</div>
        ${addressBlock(p)}
        <div style="margin-bottom:8px">${mapsLink(p)}</div>
        <div class="detail-section">
            <div class="detail-section-title">Provider Info</div>
            <div class="detail-row"><span class="label">Specialty</span><span class="value">${fmt(p.specialty)}</span></div>
            <div class="detail-row"><span class="label">NPI</span><span class="value">${fmt(p.npi)}</span></div>
            <div class="detail-row"><span class="label">Entity</span><span class="value">${fmt(p.entity)}</span></div>
            <div class="detail-row"><span class="label">Phone</span><span class="value">${phoneLink(p.phone)}</span></div>
            <div class="detail-row"><span class="label">Telehealth</span><span class="value">${p.telehealth ? "Yes" : "No"}</span></div>
        </div>
        ${ins.length ? `<div class="detail-section">
            <div class="detail-section-title">Insurance Accepted</div>
            <div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:4px">
                ${ins.map(i => `<span class="detail-badge badge-low">${i}</span>`).join("")}
            </div>
        </div>` : ""}
        ${p.facility_affiliation ? `<div class="detail-section">
            <div class="detail-section-title">Affiliated With</div>
            <div style="font-size:0.78rem;color:#bbc;margin-top:2px">${p.facility_affiliation}</div>
        </div>` : ""}
        ${p.medicare_specialty ? `<div class="detail-section">
            <div class="detail-section-title">Medicare Specialty</div>
            <div style="font-size:0.78rem;color:#bbc;margin-top:2px">${p.medicare_specialty}</div>
        </div>` : ""}
    `;
}

function showTractDetail(p) {
    detailEl.innerHTML = `
        <div class="detail-title">Tract ${p.NAME}</div>
        <div class="detail-type">Census Tract Data</div>
        <div class="detail-section">
            <div class="detail-section-title">Demographics</div>
            <div class="detail-row"><span class="label">Population</span><span class="value">${fmt(p.total_pop)}</span></div>
            <div class="detail-row"><span class="label">Median Age</span><span class="value">${fmt(p.median_age)}</span></div>
            <div class="detail-row"><span class="label">Under 18</span><span class="value">${pct(p.pct_under_18)}</span></div>
            <div class="detail-row"><span class="label">65+</span><span class="value">${pct(p.pct_65_plus)}</span></div>
            <div class="detail-row"><span class="label">Native American</span><span class="value">${pct(p.pct_aian)}</span></div>
            <div class="detail-row"><span class="label">Hispanic</span><span class="value">${pct(p.pct_hispanic)}</span></div>
            <div class="detail-row"><span class="label">Disabled</span><span class="value">${pct(p.pct_disabled)}</span></div>
            <div class="detail-row"><span class="label">No Vehicle</span><span class="value">${pct(p.pct_no_vehicle)}</span></div>
        </div>
        <div class="detail-section">
            <div class="detail-section-title">Insurance & Income</div>
            <div class="detail-row"><span class="label">Uninsured</span><span class="value">${pct(p.pct_uninsured)}</span></div>
            <div class="detail-row"><span class="label">Medicaid</span><span class="value">${pct(p.pct_medicaid)}</span></div>
            <div class="detail-row"><span class="label">Medicare</span><span class="value">${pct(p.pct_medicare)}</span></div>
            <div class="detail-row"><span class="label">Employer</span><span class="value">${pct(p.pct_employer)}</span></div>
            <div class="detail-row"><span class="label">Median Income</span><span class="value">${money(p.median_income)}</span></div>
            <div class="detail-row"><span class="label">Poverty</span><span class="value">${pct(p.pct_poverty)}</span></div>
        </div>
        <div class="detail-section">
            <div class="detail-section-title">Health Conditions</div>
            <div class="detail-row"><span class="label">Diabetes</span><span class="value">${pct(p.diabetes)}</span></div>
            <div class="detail-row"><span class="label">Obesity</span><span class="value">${pct(p.obesity)}</span></div>
            <div class="detail-row"><span class="label">High BP</span><span class="value">${pct(p.bphigh)}</span></div>
            <div class="detail-row"><span class="label">COPD</span><span class="value">${pct(p.copd)}</span></div>
            <div class="detail-row"><span class="label">Heart Disease</span><span class="value">${pct(p.chd)}</span></div>
            <div class="detail-row"><span class="label">Depression</span><span class="value">${pct(p.depression)}</span></div>
            <div class="detail-row"><span class="label">Smoking</span><span class="value">${pct(p.csmoking)}</span></div>
        </div>
    `;
}

function showCountyDetail(p) {
    detailEl.innerHTML = `
        <div class="detail-title">${p.NAME} County</div>
        <div class="detail-type">Market Intelligence</div>
        <div class="detail-section">
            <div class="detail-section-title">Healthcare Economy</div>
            <div class="detail-row"><span class="label">Healthcare Businesses</span><span class="value">${fmt(p.healthcare_establishments)}</span></div>
            <div class="detail-row"><span class="label">Healthcare Employees</span><span class="value">${fmt(p.healthcare_employees)}</span></div>
            <div class="detail-row"><span class="label">Total Businesses</span><span class="value">${fmt(p.total_establishments)}</span></div>
            <div class="detail-row"><span class="label">Healthcare % of Biz</span><span class="value">${pct(p.healthcare_pct_of_biz)}</span></div>
        </div>
        <div class="detail-section">
            <div class="detail-section-title">Infrastructure</div>
            <div class="detail-row"><span class="label">Broadband Access</span><span class="value">${pct(p.pct_broadband)}</span></div>
            <div class="detail-row"><span class="label">No Internet</span><span class="value">${pct(p.pct_no_internet)}</span></div>
        </div>
        <div class="detail-section">
            <div class="detail-section-title">Health Outcomes</div>
            <div class="detail-row"><span class="label">Life Expectancy</span><span class="value">${p.life_expectancy ? p.life_expectancy + " yrs" : "N/A"}</span></div>
            <div class="detail-row"><span class="label">Premature Death Rate</span><span class="value">${fmt(p.premature_death_rate)}</span></div>
            <div class="detail-row"><span class="label">Preventable Hosp.</span><span class="value">${fmt(p.preventable_hosp)}</span></div>
            <div class="detail-row"><span class="label">Poor/Fair Health</span><span class="value">${pct(p.poor_health_pct)}</span></div>
        </div>
    `;
}

// County data element
const countyEl = document.getElementById("county-content");
const tribalEl = document.getElementById("tribal-content");
const networksEl = document.getElementById("networks-content");

// Build compact HPSA listing for a county
function getCountyHpsaHtml(countyName) {
    const geoKey = `${countyName} County`;
    const popKey = `LI - ${countyName} County`;
    let html = "";

    // Helper: render one HPSA type group
    function renderGroup(title, color, desc, hits) {
        if (hits.length === 0) return "";
        let entries = "";
        hits.forEach(f => {
            const p = f.properties;
            const multi = p.from_multi_county ? `<div style="font-size:0.68rem;color:#556;margin-top:2px">Part of ${p.multi_county_name}</div>` : "";
            const status = p.status === "Proposed For Withdrawal" ? `<span style="font-size:0.68rem;color:#667"> (Withdrawal)</span>` : "";
            entries += `
                <div style="margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #1a1a2a">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                        <span style="font-size:0.82rem;font-weight:600;color:#ddd">${p.discipline}${status}</span>
                        <span>${hpsaBadge(p.score)}</span>
                    </div>
                    ${multi}
                    <div class="detail-row"><span class="label">Classification</span><span class="value">${fmt(p.rural)}</span></div>
                    <div class="detail-row"><span class="label">Provider Ratio</span><span class="value">${fmt(p.provider_ratio)}</span></div>
                    ${p.designation_pop ? `<div class="detail-row"><span class="label">Population Served</span><span class="value">${fmt(p.designation_pop)}</span></div>` : ""}
                    ${p.underserved_pop ? `<div class="detail-row"><span class="label">Underserved Pop</span><span class="value">${fmt(p.underserved_pop)}</span></div>` : ""}
                    ${p.pct_poverty ? `<div class="detail-row"><span class="label">Poverty Rate</span><span class="value">${pct(p.pct_poverty)}</span></div>` : ""}
                </div>`;
        });
        return `
            <div class="detail-section">
                <div class="detail-section-title" style="color:${color}">${title}</div>
                <div style="font-size:0.72rem;color:#667;margin-bottom:8px">${desc}</div>
                ${entries}
            </div>`;
    }

    // Geographic
    const geoData = dataCache["../data/processed/ok_hpsa_geographic.geojson"];
    const geoHits = geoData ? geoData.features.filter(f => f.properties.name === geoKey) : [];
    html += renderGroup(
        "Geographic HPSA Designations", "#ff4444",
        "No providers in this area — everyone is underserved regardless of income.",
        geoHits
    );

    // Population
    const popData = dataCache["../data/processed/ok_hpsa_population.geojson"];
    const popHits = popData ? popData.features.filter(f => f.properties.name === popKey) : [];
    html += renderGroup(
        "Population HPSA Designations", "#f97316",
        "Providers exist but low-income residents can't access them.",
        popHits
    );

    // Facility — count facilities in this county
    const facData = dataCache["../data/processed/ok_hpsa_facility.geojson"];
    const facHits = facData ? facData.features.filter(f => f.properties.county === countyName) : [];
    if (facHits.length) {
        // Group by discipline, show count + avg score
        const byDisc = {};
        facHits.forEach(f => {
            const d = f.properties.discipline;
            if (!byDisc[d]) byDisc[d] = [];
            byDisc[d].push(f.properties.score);
        });
        let facRows = "";
        Object.entries(byDisc).forEach(([disc, scores]) => {
            const maxScore = Math.max(...scores);
            facRows += `<div class="detail-row"><span class="label">${disc} (${scores.length} facilities)</span><span class="value">${hpsaBadge(maxScore)}</span></div>`;
        });
        html += `
            <div class="detail-section">
                <div class="detail-section-title" style="color:#fbbf24">Facility HPSA Designations</div>
                <div style="font-size:0.72rem;color:#667;margin-bottom:6px">${facHits.length} facilities designated as short-staffed.</div>
                ${facRows}
            </div>`;
    }

    if (!html) {
        return `<div style="color:#4ade80;font-size:0.8rem;padding:8px 0">No active HPSA designations.</div>`;
    }
    return html;
}

// Populate county data tab
function populateCountyTab(p) {
    const hasSoonerCare = p.ohca_total_enrollment != null;
    const medicaidPctDisplay = p.ohca_medicaid_pct != null
        ? (p.ohca_medicaid_pct * 100).toFixed(0) + "%"
        : "N/A";
    const popTrend = p.pop_pct_change != null
        ? (p.pop_pct_change > 0 ? `<span class="trend-up">+${p.pop_pct_change}% \u2191</span>` :
           p.pop_pct_change < 0 ? `<span class="trend-down">${p.pop_pct_change}% \u2193</span>` :
           `<span class="trend-same">0% \u2192</span>`)
        : "";
    const popTrendRow = popTrend ? `<div class="detail-row"><span class="label">Growth (2020\u20132023)</span><span class="value">${popTrend}</span></div>` : "";

    countyEl.innerHTML = `
        <div class="detail-title">${p.NAME} County</div>
        <div class="detail-type">Demographics & Health Data</div>
        <div class="detail-section">
            <div class="detail-section-title">Demographics</div>
            <div class="detail-row"><span class="label">Population</span><span class="value">${fmt(p.total_pop)}</span></div>
            ${popTrendRow}
            <div class="detail-row"><span class="label">Median Income</span><span class="value">${money(p.median_income)}</span></div>
            <div class="detail-row"><span class="label">Poverty Rate</span><span class="value">${pct(p.pct_poverty)}</span></div>
            <div class="detail-row"><span class="label">Age 65+</span><span class="value">${pct(p.pct_65_plus)}</span></div>
            <div class="detail-row"><span class="label">Under 18</span><span class="value">${pct(p.pct_under_18)}</span></div>
            <div class="detail-row"><span class="label">Native American</span><span class="value">${pct(p.pct_aian)}</span></div>
            <div class="detail-row"><span class="label">Disabled</span><span class="value">${pct(p.pct_disabled)}</span></div>
        </div>
        <div class="detail-section">
            <div class="detail-section-title">Insurance</div>
            <div class="detail-row"><span class="label">Uninsured</span><span class="value">${pct(p.pct_uninsured)}</span></div>
            <div class="detail-row"><span class="label">Medicaid (ACS)</span><span class="value">${pct(p.pct_medicaid)}</span></div>
        </div>
        ${hasSoonerCare ? `
        <div class="detail-section">
            <div class="detail-section-title">SoonerCare (Feb 2026)</div>
            <div class="detail-row"><span class="label">Medicaid Coverage</span><span class="value">${medicaidPctDisplay} <span style="color:#667;font-size:0.7rem">(rank ${fmt(p.ohca_medicaid_rank)})</span></span></div>
            <div class="detail-row"><span class="label">Total Enrollment</span><span class="value">${fmt(p.ohca_total_enrollment)}</span></div>
            <div class="detail-row"><span class="label">Unduplicated Members</span><span class="value">${fmt(p.ohca_unduplicated)}</span></div>
            <div class="detail-row"><span class="label">Expansion Adults</span><span class="value">${fmt(p.ohca_expansion)}</span></div>
            <div class="detail-row"><span class="label">Children/Parents</span><span class="value">${fmt(p.ohca_children_parents)}</span></div>
            <div class="detail-row"><span class="label">Aged/Blind/Disabled</span><span class="value">${fmt(p.ohca_abd)}</span></div>
            <div class="detail-row"><span class="label">Dual Enrollees</span><span class="value">${fmt(p.ohca_dual_enrollees)}</span></div>
            <div class="detail-row"><span class="label">Expenditures</span><span class="value">${money(p.ohca_expenditures)} <span style="color:#667;font-size:0.7rem">(rank ${fmt(p.ohca_expenditures_rank)})</span></span></div>
            <div class="detail-row"><span class="label">Avg Monthly/Member</span><span class="value">${money(p.ohca_avg_monthly_per_member)}</span></div>
            <div class="detail-row"><span class="label">Deliveries (SFY23)</span><span class="value">${fmt(p.ohca_deliveries)}</span></div>
        </div>
        ` : ""}
        <div class="detail-section">
            <div class="detail-section-title">Provider Networks</div>
            <div class="detail-row"><span class="label">Total Providers</span><span class="value">${fmt(p.ins_total_providers)}</span></div>
            <div class="detail-row"><span class="label">Primary Care</span><span class="value">${fmt(p.ins_pcp_total)}</span></div>
            <div class="detail-row"><span class="label">NP / PA</span><span class="value">${fmt(p.ins_np_pa_total)}</span></div>
            <div class="detail-row"><span class="label">Specialists</span><span class="value">${fmt(p.ins_specialist_total)}</span></div>
            <div style="font-size:0.7rem;color:#667;margin-top:4px">See Networks tab for insurer breakdown</div>
        </div>
        <div class="detail-section">
            <div class="detail-section-title">Health Burden</div>
            <div class="detail-row"><span class="label">Diabetes</span><span class="value">${pct(p.diabetes)}</span></div>
            <div class="detail-row"><span class="label">Obesity</span><span class="value">${pct(p.obesity)}</span></div>
            <div class="detail-row"><span class="label">Depression</span><span class="value">${pct(p.depression)}</span></div>
            <div class="detail-row"><span class="label">Heart Disease</span><span class="value">${pct(p.chd)}</span></div>
            <div class="detail-row"><span class="label">COPD</span><span class="value">${pct(p.copd)}</span></div>
            <div class="detail-row"><span class="label">High Blood Pressure</span><span class="value">${pct(p.bphigh)}</span></div>
        </div>
        ${p.gpci_locality ? `
        <div class="detail-section">
            <div class="detail-section-title">Medicare Reimbursement (GPCI)</div>
            <div class="detail-row"><span class="label">Payment Locality</span><span class="value">${p.gpci_locality}</span></div>
            <div class="detail-row"><span class="label">Work GPCI</span><span class="value">${p.gpci_work}</span></div>
            <div class="detail-row"><span class="label">Practice Expense</span><span class="value">${p.gpci_pe}</span></div>
            <div class="detail-row"><span class="label">Malpractice</span><span class="value">${p.gpci_mp}</span></div>
            <div style="font-size:0.68rem;color:#4a4c5a;margin-top:6px;line-height:1.5">Higher PE GPCI = higher practice cost reimbursement. Tulsa metro gets slightly higher rates than rest of OK.</div>
        </div>
        ` : ""}
    `;
}

// Get MUA/MUP info for a county
function getCountyMuaHtml(countyName) {
    const muaData = dataCache["../data/processed/ok_mua.geojson"];
    if (!muaData) return "";

    const hits = muaData.features.filter(f => {
        const n = (f.properties.name || "").toUpperCase();
        return n.includes(countyName.toUpperCase());
    });
    if (hits.length === 0) return "";

    let rows = "";
    hits.forEach(f => {
        const p = f.properties;
        let displayName = p.name || "";
        displayName = displayName.replace(/^LI-/i, "").replace(/ SERVICE AREA$/i, "");
        displayName = displayName.replace(/\w\S*/g, t => t.charAt(0).toUpperCase() + t.slice(1).toLowerCase());
        const isMup = (p.type || "").toUpperCase() === "MUP";
        rows += `<div class="detail-row"><span class="label">${isMup ? "MUP" : "MUA"} — ${displayName}</span><span class="value">${p.score != null ? p.score + "/100" : "N/A"}</span></div>`;
    });

    // Count NHSC sites in this county
    const nhscData = dataCache["../data/processed/ok_nhsc_sites.geojson"];
    let nhscRow = "";
    if (nhscData) {
        const nhscHits = nhscData.features.filter(f =>
            (f.properties.county || "").toUpperCase() === countyName.toUpperCase()
        );
        if (nhscHits.length > 0) {
            nhscRow = `<div class="detail-row"><span class="label">NHSC Loan Repayment Sites</span><span class="value" style="color:#eab308;font-weight:600">${nhscHits.length} sites</span></div>
            <div style="font-size:0.68rem;color:#4a4c5a;margin-top:4px;line-height:1.5">Up to $50k (LRP) or $75k (S2S) in student loan forgiveness. Toggle NHSC overlay to see locations.</div>`;
        }
    }

    return `<div class="detail-section">
        <div class="detail-section-title" style="color:#eab308">Medically Underserved Designations</div>
        <div style="font-size:0.72rem;color:#667;margin-bottom:6px">Providers here may qualify for federal loan repayment.</div>
        ${rows}
        ${nhscRow}
    </div>`;
}

// Show all HPSAs for a county in the Details tab
function showCountyHpsaDetail(countyName) {
    // Eagerly load MUA + NHSC data for the detail panel
    Promise.all([
        loadData("../data/processed/ok_mua.geojson"),
        loadData("../data/processed/ok_nhsc_sites.geojson"),
    ]).then(() => {
        detailEl.innerHTML = `
            <div class="detail-title">${countyName} County</div>
            <div class="detail-type">Designations</div>
            ${getCountyHpsaHtml(countyName)}
            ${getCountyMuaHtml(countyName)}
        `;
    });
}

// Populate Tribal tab for a given county name
const tribalTabBtn = document.querySelector('.tab-btn[data-tab="tribal"]');

function populateTribalTab(countyName) {
    if (!tribalData) {
        tribalTabBtn.style.display = "none";
        return;
    }
    // Find all tribal areas whose counties list includes this county
    const matches = tribalData.features.filter(f => {
        const c = f.properties.counties || "";
        return c.split(",").map(s => s.trim()).includes(countyName);
    });
    if (matches.length === 0) {
        tribalTabBtn.style.display = "none";
        // If tribal tab was active, switch away
        if (tribalTabBtn.classList.contains("active")) switchTab("details");
        return;
    }
    tribalTabBtn.style.display = "";
    let html = `<div class="detail-title">${countyName} County</div>
        <div class="detail-type">${matches.length} Tribal Area${matches.length > 1 ? "s" : ""}</div>`;
    matches.forEach(f => {
        const t = f.properties;
        html += `
            <div class="detail-section">
                <div class="detail-section-title">${t.NAMELSAD || t.NAME}</div>
                <div class="detail-row"><span class="label">Area</span><span class="value">${t.approx_area_sq_mi ? t.approx_area_sq_mi.toLocaleString() + " sq mi" : "N/A"}</span></div>
                <div class="detail-row"><span class="label">Counties</span><span class="value">${fmt(t.county_count)}</span></div>
                <div class="detail-row"><span class="label">IHS Facilities</span><span class="value">${fmt(t.ihs_facilities)}</span></div>
                <div class="detail-row"><span class="label">Area Population</span><span class="value">${t.approx_pop ? t.approx_pop.toLocaleString() : "N/A"}</span></div>
                ${t.counties ? `<div class="detail-row" style="flex-direction:column;gap:4px"><span class="label">All Counties</span><span class="value" style="font-size:0.76rem;color:#bbc;line-height:1.6">${t.counties}</span></div>` : ""}
            </div>`;
    });
    tribalEl.innerHTML = html;
}

// Build a network category block with per-insurer bars
function netCategory(label, prefix, p) {
    const total = p[`${prefix}_total`] || 0;
    if (total === 0) return "";
    const insurers = [
        ["BCBS", "bcbs", "#3b82f6"],
        ["Aetna", "aetna", "#a855f7"],
        ["Cigna", "cigna", "#f97316"],
        ["Centene", "centene", "#22c55e"],
        ["Humana", "humana", "#eab308"],
        ["UHC", "uhc", "#06b6d4"],
    ];
    let bars = "";
    for (const [name, key, color] of insurers) {
        const count = p[`${prefix}_${key}`] || 0;
        if (count === 0) continue;
        bars += insBar(name, count, total, color);
    }
    return `<div class="detail-section">
        <div class="detail-section-title">${label} <span style="color:#99a;font-size:0.7rem;font-weight:400">${total} in county</span></div>
        ${bars}
    </div>`;
}

function populateNetworksTab(p) {
    networksEl.innerHTML = `
        <div class="detail-title">${p.NAME} County</div>
        <div class="detail-type">Insurance Network Coverage</div>
        ${netCategory("Primary Care", "ins_pcp", p)}
        ${netCategory("NP / PA", "ins_np_pa", p)}
        ${netCategory("Specialists", "ins_specialist", p)}
        ${netCategory("Dental", "ins_dental", p)}
        ${netCategory("Behavioral Health", "ins_behavioral", p)}
        ${netCategory("Therapy", "ins_therapy", p)}
        ${netCategory("Hospitals", "ins_hospital", p)}
        ${netCategory("Facilities", "ins_facility", p)}
        ${netCategory("Pharmacy", "ins_pharmacy", p)}
    `;
}

// County click: populate all tabs, show details
function showCountySummary(p) {
    showCountyHpsaDetail(p.NAME);
    populateCountyTab(p);
    populateNetworksTab(p);
    populateTribalTab(p.NAME);
}

// Eagerly load tribal data for the Tribal tab (independent of tribal overlay toggle)
loadData("../data/processed/ok_tribal.geojson").then(data => { tribalData = data; });

// ══════════════════════════════════════════════════════════════════
// FOUNDATION LAYER 1: County Borders (always on, independent)
// ══════════════════════════════════════════════════════════════════

function renderCountyLabels() {
    if (countyLabels) { map.removeLayer(countyLabels); countyLabels = null; }
    if (!countyData || !hpsaVisible) return;

    countyLabels = L.layerGroup();
    countyData.features.forEach(f => {
        const p = f.properties;
        if (!p.label_lat || !p.label_lng) return;
        const icon = L.divIcon({
            className: "county-label",
            html: `<div class="county-name">${p.NAME}</div>`,
            iconSize: [80, 18],
            iconAnchor: [40, 9],
        });
        L.marker([p.label_lat, p.label_lng], { icon, interactive: false }).addTo(countyLabels);
    });
    countyLabels.addTo(map);
}

loadData("../data/processed/ok_counties.geojson").then(data => {
    countyData = data;
    countyLayer = L.geoJSON(data, {
        style: {
            color: "rgba(255,255,255,0.5)",
            weight: 1,
            fillColor: "transparent",
            fillOpacity: 0,
        },
        onEachFeature: (feature, layer) => {
            layer.on("click", (e) => {
                L.DomEvent.stopPropagation(e);
                showCountySummary(feature.properties);
                // Only zoom if at overlay level — don't yank zoomed-in users out
                if (map.getZoom() < HPSA_ZOOM_THRESHOLD) {
                    setTimeout(() => {
                        map.fitBounds(layer.getBounds().pad(0.1), { maxZoom: 11 });
                    }, 50);
                }
            });
            layer.on("mouseover", () => layer.setStyle({ color: "#fff", weight: 1.5 }));
            layer.on("mouseout", () => layer.setStyle({ color: "rgba(255,255,255,0.5)", weight: 1 }));
        },
    });
    countyLayer.addTo(map);
    renderCountyLabels();
    // Now load everything that goes on top
    initHpsaLayers();
    loadKeyFacilities();
    // Dismiss loading overlay
    const overlay = document.getElementById("loading-overlay");
    if (overlay) overlay.classList.add("hidden");
});

// ══════════════════════════════════════════════════════════════════
// FOUNDATION LAYER 2: Key Facility Pins (always visible)
// ══════════════════════════════════════════════════════════════════

const keyFacFiles = {
    pharmacies: { file: "ok_pharmacies.geojson", color: "#06b6d4", label: "Pharmacy" },
    rhc: { file: "ok_rhc.geojson", color: "#14b8a6", label: "RHC" },
    hospitals_cms: { file: "ok_hospitals_cms.geojson", color: "#ef4444", label: "Hospital" },
    fqhc: { file: "ok_fqhc.geojson", color: "#22c55e", label: "FQHC" },
    ihs: { file: "ok_ihs.geojson", color: "#a855f7", label: "IHS/Tribal" },
    closed: { file: "ok_closed_hospitals.geojson", color: "#666", label: "Closed Hospital" },
};

function keyPinRadius() {
    const z = map.getZoom();
    if (z >= 12) return 6;
    if (z >= 10) return 4.5;
    if (z >= 8) return 3.5;
    return 2.5;
}

function loadKeyFacilities() {
    Object.entries(keyFacFiles).forEach(([key, cfg]) => {
        loadData(`../data/processed/${cfg.file}`).then(data => {
            const r = keyPinRadius();
            keyFacLayers[key] = L.geoJSON(data, {
                pointToLayer: (f, ll) => L.circleMarker(ll, {
                    radius: r,
                    fillColor: cfg.color,
                    color: "rgba(255,255,255,0.4)",
                    weight: 1,
                    fillOpacity: 0.85,
                }),
                onEachFeature: (f, layer) => {
                    layer.on("click", () => {
                        const p = f.properties;
                        if (key === "pharmacies") showPharmacyProfile(p);
                        else if (key === "rhc") showRhcProfile(p);
                        else if (key === "hospitals_cms") showHospitalProfile(p);
                        else if (key === "fqhc") showFqhcProfile(p);
                        else if (key === "ihs") showIhsProfile(p);
                        else if (key === "closed") showClosedProfile(p);
                    });
                },
            });
            keyFacLayers[key].addTo(map);
        });
    });
}

// ══════════════════════════════════════════════════════════════════
// HPSA FILTER LAYERS — 9 independent filters
// ══════════════════════════════════════════════════════════════════

// Intersection logic: multiple checked disciplines = narrower results.
// Only show features in areas designated by ALL checked disciplines.

function facPinRadius() {
    const z = map.getZoom();
    if (z >= 12) return 7;
    if (z >= 10) return 5;
    if (z >= 8) return 4;
    return 3;
}

// Get checked disciplines for a given HPSA type
function getCheckedDiscs(type) {
    const discs = [];
    if (document.getElementById(`toggle-${type}-pc`).checked) discs.push("Primary Care");
    if (document.getElementById(`toggle-${type}-dental`).checked) discs.push("Dental Health");
    if (document.getElementById(`toggle-${type}-mh`).checked) discs.push("Mental Health");
    return discs;
}

// Find area names that exist in ALL given disciplines
function intersectNames(features, disciplines) {
    if (disciplines.length === 0) return new Set();
    if (disciplines.length === 1) {
        return new Set(features.filter(f => f.properties.discipline === disciplines[0]).map(f => f.properties.name));
    }
    // Get name sets for each discipline, then intersect
    const sets = disciplines.map(d =>
        new Set(features.filter(f => f.properties.discipline === d).map(f => f.properties.name))
    );
    const result = new Set();
    sets[0].forEach(name => {
        if (sets.every(s => s.has(name))) result.add(name);
    });
    return result;
}

// ── Geographic HPSA rendering (intersection) ───────────────────

function renderGeo() {
    if (hpsaGeoLayer) { map.removeLayer(hpsaGeoLayer); hpsaGeoLayer = null; }
    const discs = getCheckedDiscs("geo");
    if (discs.length === 0 || !hpsaVisible) { enforceLayerOrder(); return; }

    loadData("../data/processed/ok_hpsa_geographic.geojson").then(data => {
        const validNames = intersectNames(data.features, discs);
        // Show features from all checked disciplines that pass intersection
        const features = data.features.filter(f =>
            discs.includes(f.properties.discipline) && validNames.has(f.properties.name)
        );
        // Sort: withdrawal (dashed) first, designated (solid) on top
        features.sort((a, b) => {
            const aW = a.properties.status === "Proposed For Withdrawal" ? 0 : 1;
            const bW = b.properties.status === "Proposed For Withdrawal" ? 0 : 1;
            return aW - bW;
        });
        // Deduplicate by name — keep highest-score feature per area name
        const seen = new Map();
        const deduped = [];
        features.forEach(f => {
            const key = f.properties.name + "|" + f.properties.status;
            const existing = seen.get(key);
            if (!existing || f.properties.score > existing.properties.score) {
                seen.set(key, f);
            }
        });
        seen.forEach(f => deduped.push(f));
        // Re-sort after dedup
        deduped.sort((a, b) => {
            const aW = a.properties.status === "Proposed For Withdrawal" ? 0 : 1;
            const bW = b.properties.status === "Proposed For Withdrawal" ? 0 : 1;
            return aW - bW;
        });

        const group = L.layerGroup();
        deduped.forEach(f => {
            const isWithdrawal = f.properties.status === "Proposed For Withdrawal";
            const layer = L.geoJSON(f, {
                style: () => ({
                    color: geoColor(),
                    weight: geoBorderWeight(f.properties.score),
                    fillColor: "transparent",
                    fillOpacity: 0,
                    opacity: isWithdrawal ? 0.45 : 1,
                }),
            });
            layer.on("click", () => {
                // Extract county name from "Countyname County" format
                const cname = f.properties.name.replace(/ County$/, "");
                showCountyHpsaDetail(cname);
                populateTribalTab(cname);
                if (countyData) {
                    const cf = countyData.features.find(c => c.properties.NAME === cname);
                    if (cf) { populateCountyTab(cf.properties); populateNetworksTab(cf.properties); }
                }
                layer.eachLayer(l => map.fitBounds(l.getBounds().pad(0.1), { maxZoom: 11 }));
            });
            layer.on("mouseover", () => layer.setStyle({ weight: geoBorderWeight(f.properties.score) + 2 }));
            layer.on("mouseout", () => layer.setStyle({ weight: geoBorderWeight(f.properties.score) }));
            layer.addTo(group);
        });

        hpsaGeoLayer = group;
        group.addTo(map);
        enforceLayerOrder();
    });
}

// ── Population HPSA rendering (intersection) ──────────────────

function renderPop() {
    if (hpsaPopLayer) { map.removeLayer(hpsaPopLayer); hpsaPopLayer = null; }
    if (hpsaPopLabels) { map.removeLayer(hpsaPopLabels); hpsaPopLabels = null; }
    const discs = getCheckedDiscs("pop");
    if (discs.length === 0 || !hpsaVisible) { enforceLayerOrder(); return; }

    loadData("../data/processed/ok_hpsa_population.geojson").then(data => {
        const validNames = intersectNames(data.features, discs);
        const allMatching = data.features.filter(f =>
            discs.includes(f.properties.discipline) && validNames.has(f.properties.name)
        );
        // Deduplicate by area name + status — keep highest score
        const seen = new Map();
        allMatching.forEach(f => {
            const key = f.properties.name + "|" + f.properties.status;
            const existing = seen.get(key);
            if (!existing || f.properties.score > existing.properties.score) {
                seen.set(key, f);
            }
        });
        const features = [];
        seen.forEach(f => features.push(f));

        const group = L.layerGroup();

        if (features.length) {
            L.geoJSON({ type: "FeatureCollection", features }, {
                style: feature => ({
                    color: popBorder(feature.properties.score),
                    weight: 1,
                    fillColor: popFill(feature.properties.score),
                    fillOpacity: 1,
                }),
                onEachFeature: (feature, layer) => {
                    layer.on("click", () => {
                        // Extract county from "LI - Countyname County"
                        const m = feature.properties.name.match(/LI\s*-\s*(.+?)\s*County/);
                        const cname = m ? m[1] : feature.properties.name;
                        showCountyHpsaDetail(cname);
                        populateTribalTab(cname);
                        if (countyData) {
                            const cf = countyData.features.find(c => c.properties.NAME === cname);
                            if (cf) { populateCountyTab(cf.properties); populateNetworksTab(cf.properties); }
                        }
                        map.fitBounds(layer.getBounds().pad(0.1), { maxZoom: 11 });
                    });
                },
            }).addTo(group);
        }

        hpsaPopLayer = group;
        group.addTo(map);

        // Score labels — group all discipline scores per county
        const labels = L.layerGroup();
        const discAbbrev = { "Primary Care": "PC", "Dental Health": "DH", "Mental Health": "MH" };
        const checkedDiscs = discs;
        const showAbbrev = checkedDiscs.length > 1;

        // Group ALL matching features by county (before dedup, so we get every discipline)
        const byCounty = new Map();
        allMatching.forEach(f => {
            const p = f.properties;
            const m2 = p.name.match(/LI\s*-?\s*(.+?)\s*County/);
            const cname = m2 ? m2[1] : null;
            if (!cname) return;
            if (!byCounty.has(cname)) byCounty.set(cname, []);
            // Only keep one per discipline (highest score)
            const existing = byCounty.get(cname);
            const prev = existing.find(x => x.properties.discipline === p.discipline);
            if (prev) {
                if (p.score > prev.properties.score) {
                    existing.splice(existing.indexOf(prev), 1);
                    existing.push(f);
                }
            } else {
                existing.push(f);
            }
        });

        byCounty.forEach((feats, cname) => {
            // Get county centroid
            let lat, lng;
            if (countyData) {
                const cf = countyData.features.find(c => c.properties.NAME === cname);
                if (cf && cf.properties.label_lat) {
                    lat = cf.properties.label_lat;
                    lng = cf.properties.label_lng;
                }
            }
            if (!lat || !lng) return;

            // Sort by discipline order: PC, DH, MH
            const order = ["Primary Care", "Dental Health", "Mental Health"];
            feats.sort((a, b) => order.indexOf(a.properties.discipline) - order.indexOf(b.properties.discipline));

            let html;
            if (!showAbbrev) {
                // Single discipline — just show the number
                const p = feats[0].properties;
                const cls = p.status === "Proposed For Withdrawal" ? "pop-score pop-score-withdrawal" : "pop-score";
                html = `<div class="${cls}">${p.score}</div>`;
            } else {
                // Multiple disciplines — compact row with abbreviations
                const parts = feats.map(f => {
                    const p = f.properties;
                    const abbr = discAbbrev[p.discipline] || "?";
                    const dim = p.status === "Proposed For Withdrawal" ? " pop-score-withdrawal" : "";
                    return `<span class="pop-multi-score${dim}"><span class="pop-multi-abbr">${abbr}</span>${p.score}</span>`;
                });
                html = `<div class="pop-multi-row">${parts.join("")}</div>`;
            }

            const height = showAbbrev ? 16 : 16;
            const icon = L.divIcon({
                className: "pop-score-label",
                html,
                iconSize: [100, height],
                iconAnchor: [50, -2],
            });
            L.marker([lat - 0.04, lng], { icon, interactive: false }).addTo(labels);
        });
        hpsaPopLabels = labels;
        labels.addTo(map);

        enforceLayerOrder();
    });
}

// ── Facility HPSA rendering (intersection) ─────────────────────

function renderFac() {
    if (hpsaFacLayer) { map.removeLayer(hpsaFacLayer); hpsaFacLayer = null; }
    const discs = getCheckedDiscs("fac");
    if (discs.length === 0) { enforceLayerOrder(); return; }

    loadData("../data/processed/ok_hpsa_facility.geojson").then(data => {
        const validNames = intersectNames(data.features, discs);
        const features = data.features.filter(f =>
            discs.includes(f.properties.discipline) && validNames.has(f.properties.name)
        );
        // Deduplicate by name — keep highest score
        const seen = new Map();
        features.forEach(f => {
            const key = f.properties.name;
            const existing = seen.get(key);
            if (!existing || f.properties.score > existing.properties.score) {
                seen.set(key, f);
            }
        });
        const deduped = [];
        seen.forEach(f => deduped.push(f));

        hpsaFacLayer = L.geoJSON({ type: "FeatureCollection", features: deduped }, {
            pointToLayer: (feature, latlng) => L.circleMarker(latlng, {
                radius: facPinRadius(),
                fillColor: hpsaColor(feature.properties.score),
                color: "rgba(255,255,255,0.3)",
                weight: 0.5,
                fillOpacity: 0.85,
            }),
            onEachFeature: (feature, layer) => {
                layer.on("click", () => showFacDetail(feature.properties));
            },
        });
        hpsaFacLayer.addTo(map);
        enforceLayerOrder();
    });
}

// ── Layer ordering — foundation below, filters on top ──────────
// Debounced to prevent cascade from async loads

let _layerOrderTimer = null;
function enforceLayerOrder() {
    clearTimeout(_layerOrderTimer);
    _layerOrderTimer = setTimeout(_doEnforceLayerOrder, 50);
}

function _doEnforceLayerOrder() {
    if (dataLayer) dataLayer.bringToBack();

    // MUA fills (behind everything interactive)
    if (muaCountyLayer && map.hasLayer(muaCountyLayer)) muaCountyLayer.bringToFront();
    if (muaTractLayer && map.hasLayer(muaTractLayer)) muaTractLayer.bringToFront();

    // Pop fills behind counties
    if (hpsaPopLayer) hpsaPopLayer.bringToFront();

    // County borders on top of pop fills
    if (countyLayer) countyLayer.bringToFront();

    // Geo HPSA borders on top of county borders
    if (hpsaGeoLayer) hpsaGeoLayer.bringToFront();

    // Tribal on top of borders
    if (tribalLayer && map.hasLayer(tribalLayer)) tribalLayer.bringToFront();

    // Key facilities on top (IHS last so it renders above hospitals/FQHCs)
    Object.entries(keyFacLayers).forEach(([key, l]) => {
        if (key !== "ihs" && l && map.hasLayer(l)) l.bringToFront();
    });
    if (keyFacLayers.ihs && map.hasLayer(keyFacLayers.ihs)) keyFacLayers.ihs.bringToFront();

    // NHSC sites on top of facility pins (gold, high visibility)
    if (nhscLayer && map.hasLayer(nhscLayer)) nhscLayer.bringToFront();

    // Facility HPSA pins on very top
    if (hpsaFacLayer) hpsaFacLayer.bringToFront();
}

// ── Toggle wiring — any change re-renders the whole type ───────

["toggle-geo-pc", "toggle-geo-dental", "toggle-geo-mh"].forEach(id => {
    document.getElementById(id).addEventListener("change", () => {
        renderGeo();
        renderCountyLabels();
    });
});
["toggle-pop-pc", "toggle-pop-dental", "toggle-pop-mh"].forEach(id => {
    document.getElementById(id).addEventListener("change", () => {
        renderPop();
        renderCountyLabels();
    });
});
["toggle-fac-pc", "toggle-fac-dental", "toggle-fac-mh"].forEach(id => {
    document.getElementById(id).addEventListener("change", () => {
        renderFac();
    });
});

// ── Initialize ─────────────────────────────────────────────────

function initHpsaLayers() {
    renderGeo();
    renderPop();
    renderFac();
}

// ══════════════════════════════════════════════════════════════════
// ZOOM BEHAVIOR
// ══════════════════════════════════════════════════════════════════

const toggleProviders = document.getElementById("toggle-providers");
const providerFilter = document.getElementById("provider-filter");

map.on("zoomend", () => {
    const zoom = map.getZoom();
    const shouldShow = zoom < HPSA_ZOOM_THRESHOLD;

    if (shouldShow && !hpsaVisible) {
        hpsaVisible = true;
        renderGeo();
        renderPop();
        renderCountyLabels();
        // Re-show MUA if toggled on
        if (document.getElementById("toggle-mua").checked) renderMua();
    } else if (!shouldShow && hpsaVisible) {
        hpsaVisible = false;
        if (hpsaGeoLayer) { map.removeLayer(hpsaGeoLayer); hpsaGeoLayer = null; }
        if (hpsaPopLayer) { map.removeLayer(hpsaPopLayer); hpsaPopLayer = null; }
        if (hpsaPopLabels) { map.removeLayer(hpsaPopLabels); hpsaPopLabels = null; }
        if (countyLabels) { map.removeLayer(countyLabels); countyLabels = null; }
        // Hide MUA overlays at zoom
        if (muaCountyLayer) { map.removeLayer(muaCountyLayer); muaCountyLayer = null; }
        if (muaTractLayer) { map.removeLayer(muaTractLayer); muaTractLayer = null; }

        if (toggleProviders.checked) {
            renderProviders();
        }
    }

    // Resize facility HPSA pins
    if (hpsaFacLayer) {
        const fr = facPinRadius();
        hpsaFacLayer.eachLayer(layer => { if (layer.setRadius) layer.setRadius(fr); });
    }

    // Resize key facility pins
    const kr = keyPinRadius();
    Object.values(keyFacLayers).forEach(l => {
        if (l) l.eachLayer(layer => { if (layer.setRadius) layer.setRadius(kr); });
    });

    // Resize NPI provider pins
    if (npiLayer) {
        const nr = npiPinRadius();
        npiLayer.eachLayer(layer => { if (layer.setRadius) layer.setRadius(nr); });
    }
});

// ══════════════════════════════════════════════════════════════════
// TRIBAL BOUNDARIES (overlay)
// ══════════════════════════════════════════════════════════════════

document.getElementById("toggle-tribal").addEventListener("change", function () {
    if (this.checked) {
        if (!tribalLoaded) {
            loadData("../data/processed/ok_tribal.geojson").then(data => {
                tribalLayer = L.geoJSON(data, {
                    interactive: false,
                    style: {
                        color: "#a855f7",
                        weight: 1.5,
                        fillColor: "#a855f7",
                        fillOpacity: 0.08,
                    },
                });
                tribalLayer.addTo(map);
                tribalLoaded = true;
                enforceLayerOrder();
            });
        } else {
            tribalLayer.addTo(map);
            enforceLayerOrder();
        }
    } else if (tribalLayer) {
        map.removeLayer(tribalLayer);
    }
});

// ══════════════════════════════════════════════════════════════════
// MUA/MUP OVERLAY
// ══════════════════════════════════════════════════════════════════

function imuColor(score) {
    if (score == null) return "rgba(234,179,8,0.25)";
    // Lower IMU = worse. Range 0-100, threshold for designation is ≤62
    if (score <= 30) return "rgba(220, 38, 38, 0.30)";
    if (score <= 45) return "rgba(249, 115, 22, 0.25)";
    if (score <= 55) return "rgba(234, 179, 8, 0.20)";
    return "rgba(250, 204, 21, 0.15)";
}

function imuBorder(score) {
    if (score == null) return "rgba(234,179,8,0.4)";
    if (score <= 30) return "rgba(220, 38, 38, 0.50)";
    if (score <= 45) return "rgba(249, 115, 22, 0.45)";
    if (score <= 55) return "rgba(234, 179, 8, 0.40)";
    return "rgba(250, 204, 21, 0.35)";
}

function renderMua() {
    if (muaCountyLayer) { map.removeLayer(muaCountyLayer); muaCountyLayer = null; }
    if (muaTractLayer) { map.removeLayer(muaTractLayer); muaTractLayer = null; }

    const toggle = document.getElementById("toggle-mua");
    if (!toggle || !toggle.checked || !hpsaVisible) return;

    // County-level MUA
    loadData("../data/processed/ok_mua.geojson").then(data => {
        if (!toggle.checked) return;
        muaCountyLayer = L.geoJSON(data, {
            interactive: false,
            style: feature => {
                const score = feature.properties.score;
                return {
                    color: imuBorder(score),
                    weight: 1.5,
                    fillColor: imuColor(score),
                    fillOpacity: 0.9,
                };
            },
        });
        muaCountyLayer.addTo(map);
        enforceLayerOrder();
    });

    // Tract-level MUA/MUP
    loadData("../data/processed/ok_mua_tracts.geojson").then(data => {
        if (!toggle.checked) return;
        muaTractLayer = L.geoJSON(data, {
            interactive: false,
            style: feature => {
                const score = feature.properties.imu_score;
                return {
                    color: "rgba(234, 179, 8, 0.7)",
                    weight: 2,
                    fillColor: imuColor(score),
                    fillOpacity: 0.9,
                };
            },
        });
        muaTractLayer.addTo(map);
        enforceLayerOrder();
    });
}

document.getElementById("toggle-mua").addEventListener("change", renderMua);

// ══════════════════════════════════════════════════════════════════
// NHSC LOAN REPAYMENT SITES (overlay)
// ══════════════════════════════════════════════════════════════════

function renderNhsc() {
    if (nhscLayer) { map.removeLayer(nhscLayer); nhscLayer = null; }

    const toggle = document.getElementById("toggle-nhsc");
    if (!toggle || !toggle.checked) return;

    loadData("../data/processed/ok_nhsc_sites.geojson").then(data => {
        if (!toggle.checked) return;
        nhscLayer = L.geoJSON(data, {
            pointToLayer: (f, ll) => {
                const score = f.properties.max_hpsa_score || 0;
                const size = score >= 20 ? 7 : score >= 15 ? 6 : 5;
                return L.circleMarker(ll, {
                    radius: size,
                    fillColor: "#eab308",
                    color: "#fcd34d",
                    weight: 2,
                    fillOpacity: 0.85,
                });
            },
            onEachFeature: (f, layer) => {
                layer.on("click", () => showNhscProfile(f.properties));
            },
        });
        nhscLayer.addTo(map);
        nhscLoaded = true;
        enforceLayerOrder();
    });
}

document.getElementById("toggle-nhsc").addEventListener("change", renderNhsc);

// ══════════════════════════════════════════════════════════════════
// NPI PROVIDERS (zoom 9+, viewport-filtered)
// ══════════════════════════════════════════════════════════════════

const providerFiles = {
    primary_care: { file: "ok_providers_primary_care.geojson", color: "#3b82f6" },
    np_pa: { file: "ok_providers_np_pa.geojson", color: "#06b6d4" },
    specialists: { file: "ok_providers_specialists.geojson", color: "#6366f1" },
    hospitals: { file: "ok_providers_hospitals.geojson", color: "#ef4444" },
    behavioral: { file: "ok_providers_behavioral.geojson", color: "#a855f7" },
    dental: { file: "ok_providers_dental.geojson", color: "#f59e0b" },
    pharmacy: { file: "ok_providers_pharmacy.geojson", color: "#22c55e" },
    therapy: { file: "ok_providers_therapy.geojson", color: "#14b8a6" },
    facilities: { file: "ok_providers_facilities.geojson", color: "#78716c" },
};
const NPI_MIN_ZOOM = 9;
const providerCatSelect = document.getElementById("provider-category");

function loadProviderCategory(key) {
    if (loadedProviders.has(key)) return Promise.resolve();
    return loadData(`../data/processed/${providerFiles[key].file}`).then(data => {
        providerData[key] = data;
        loadedProviders.add(key);
    });
}

function npiPinRadius() {
    const z = map.getZoom();
    if (z >= 13) return 4;
    if (z >= 11) return 3;
    if (z >= 9) return 2;
    return 1.5;
}

function renderProviders() {
    if (npiLayer) { map.removeLayer(npiLayer); npiLayer = null; }
    if (!toggleProviders.checked) return;

    if (map.getZoom() < NPI_MIN_ZOOM) {
        if (!detailEl.querySelector('.detail-title'))
            detailEl.innerHTML = '<p class="placeholder">Zoom in to see individual providers</p>';
        return;
    }

    const cat = providerCatSelect.value;

    loadProviderCategory(cat).then(() => {
        if (!toggleProviders.checked || map.getZoom() < NPI_MIN_ZOOM) return;
        const bounds = map.getBounds();
        const visible = {
            type: "FeatureCollection",
            features: providerData[cat].features.filter(f => {
                const c = f.geometry.coordinates;
                return bounds.contains([c[1], c[0]]);
            }),
        };

        const color = providerFiles[cat].color;
        const r = npiPinRadius();
        npiLayer = L.geoJSON(visible, {
            pointToLayer: (f, ll) => L.circleMarker(ll, {
                radius: r, fillColor: color, color: "transparent", weight: 0, fillOpacity: 0.55,
            }),
            onEachFeature: (f, layer) => {
                layer.on("click", () => showProviderProfile(f.properties));
            },
        });
        npiLayer.addTo(map);
        if (!detailEl.querySelector('.detail-title'))
            detailEl.innerHTML = `<p class="placeholder">${visible.features.length.toLocaleString()} providers in view</p>`;
    });
}

let moveTimer = null;
map.on("moveend", () => {
    if (toggleProviders.checked) {
        clearTimeout(moveTimer);
        moveTimer = setTimeout(renderProviders, 300);
    }
});

toggleProviders.addEventListener("change", function () {
    providerFilter.classList.toggle("hidden", !this.checked);
    if (this.checked) renderProviders();
    else {
        if (npiLayer) { map.removeLayer(npiLayer); npiLayer = null; }
        detailEl.innerHTML = '<p class="placeholder">Click an area on the map to see details</p>';
    }
});
providerCatSelect.addEventListener("change", renderProviders);

// ══════════════════════════════════════════════════════════════════
// DATA LAYER VIEWS (demographics, insurance, disease, market)
// ══════════════════════════════════════════════════════════════════

const dataViews = {
    demographics: {
        file: "../data/processed/ok_tracts_all.geojson",
        metrics: {
            total_pop: { label: "Population", max: 10000, low: "#f0f0f0", high: "#6ab4ff" },
            pct_65_plus: { label: "% Age 65+", max: 40, low: "#f0f0f0", high: "#ff9f43" },
            pct_under_18: { label: "% Under 18", max: 40, low: "#f0f0f0", high: "#4ade80" },
            pct_aian: { label: "% Native American", max: 80, low: "#f0f0f0", high: "#f87171" },
            pct_disabled: { label: "% Disabled", max: 40, low: "#f0f0f0", high: "#c084fc" },
        },
        defaultMetric: "pct_65_plus",
        onClick: showTractDetail,
    },
    insurance: {
        file: "../data/processed/ok_tracts_all.geojson",
        metrics: {
            pct_uninsured: { label: "% Uninsured", max: 35, low: "#f0f0f0", high: "#f87171" },
            pct_medicaid: { label: "% Medicaid", max: 30, low: "#f0f0f0", high: "#4ade80" },
            pct_medicare: { label: "% Medicare", max: 30, low: "#f0f0f0", high: "#ff9f43" },
            median_income: { label: "Median Income ($)", max: 120000, low: "#f87171", high: "#4ade80" },
            pct_poverty: { label: "% Below Poverty", max: 50, low: "#f0f0f0", high: "#f87171" },
        },
        defaultMetric: "pct_uninsured",
        onClick: showTractDetail,
    },
    disease: {
        file: "../data/processed/ok_tracts_all.geojson",
        metrics: {
            diabetes: { label: "Diabetes", max: 25, low: "#f0f0f0", high: "#f87171" },
            obesity: { label: "Obesity", max: 60, low: "#f0f0f0", high: "#fb923c" },
            depression: { label: "Depression", max: 40, low: "#f0f0f0", high: "#a78bfa" },
            copd: { label: "COPD", max: 18, low: "#f0f0f0", high: "#f97316" },
            chd: { label: "Heart Disease", max: 15, low: "#f0f0f0", high: "#dc2626" },
        },
        defaultMetric: "diabetes",
        onClick: showTractDetail,
    },
    market: {
        file: "../data/processed/ok_market.geojson",
        metrics: {
            healthcare_employees: { label: "Healthcare Employees", max: 30000, low: "#f0f0f0", high: "#6ab4ff" },
            pct_broadband: { label: "% Broadband", max: 100, low: "#f87171", high: "#4ade80" },
            life_expectancy: { label: "Life Expectancy", max: 80, low: "#f87171", high: "#4ade80" },
            preventable_hosp: { label: "Preventable Hospitalizations", max: 6000, low: "#f0f0f0", high: "#f87171" },
        },
        defaultMetric: "healthcare_employees",
        onClick: showCountyDetail,
    },
    soonercare: {
        file: "../data/processed/ok_counties.geojson",
        metrics: {
            ohca_medicaid_pct: { label: "Medicaid Coverage %", max: 0.7, low: "#f0f0f0", high: "#4ade80" },
            ohca_total_enrollment: { label: "SoonerCare Enrollment", max: 50000, low: "#f0f0f0", high: "#6ab4ff" },
            ohca_expenditures: { label: "Expenditures ($)", max: 200000000, low: "#f0f0f0", high: "#fb923c" },
            ohca_avg_monthly_per_member: { label: "Avg Monthly/Member ($)", max: 800, low: "#4ade80", high: "#f87171" },
            ins_bcbs: { label: "BCBS Providers", max: 2000, low: "#f0f0f0", high: "#3b82f6" },
            ins_cigna: { label: "Cigna Providers", max: 1500, low: "#f0f0f0", high: "#f97316" },
            ins_aetna: { label: "Aetna Providers", max: 1500, low: "#f0f0f0", high: "#a855f7" },
            ins_centene: { label: "Centene Providers", max: 800, low: "#f0f0f0", high: "#22c55e" },
            ins_total_providers: { label: "Total Providers", max: 5000, low: "#f0f0f0", high: "#6ab4ff" },
        },
        defaultMetric: "ohca_medicaid_pct",
        onClick: showCountyDetail,
    },
};

const viewBtns = document.querySelectorAll(".view-btn");
const metricControls = document.getElementById("metric-controls");
const metricSelect = document.getElementById("metric-select");

function clearDataLayer() {
    if (dataLayer) { map.removeLayer(dataLayer); dataLayer = null; }
    activeDataView = null;
    viewBtns.forEach(b => b.classList.remove("active"));
    metricControls.classList.add("hidden");
}

function renderDataLayer(viewKey, metric) {
    if (dataLayer) { map.removeLayer(dataLayer); dataLayer = null; }
    const view = dataViews[viewKey];
    const cfg = view.metrics[metric];

    loadData(view.file).then(data => {
        dataLayer = L.geoJSON(data, {
            style: feature => {
                const val = feature.properties[metric] || 0;
                const t = Math.min(val / cfg.max, 1);
                return {
                    color: "rgba(255,255,255,0.08)",
                    weight: 0.3,
                    fillColor: interpolate(cfg.low, cfg.high, t),
                    fillOpacity: 0.55,
                };
            },
            onEachFeature: (feature, layer) => {
                layer.on("click", () => view.onClick(feature.properties));
            },
        });
        dataLayer.addTo(map);
        enforceLayerOrder();
    });
}

viewBtns.forEach(btn => {
    btn.addEventListener("click", () => {
        const viewKey = btn.dataset.view;
        if (activeDataView === viewKey) {
            clearDataLayer();
            return;
        }

        activeDataView = viewKey;
        viewBtns.forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        metricControls.classList.remove("hidden");

        metricSelect.innerHTML = "";
        const view = dataViews[viewKey];
        Object.entries(view.metrics).forEach(([key, cfg]) => {
            const opt = document.createElement("option");
            opt.value = key;
            opt.textContent = cfg.label;
            metricSelect.appendChild(opt);
        });
        metricSelect.value = view.defaultMetric;
        renderDataLayer(viewKey, view.defaultMetric);
    });
});

metricSelect.addEventListener("change", () => {
    if (activeDataView) renderDataLayer(activeDataView, metricSelect.value);
});

document.getElementById("clear-data-layer").addEventListener("click", clearDataLayer);

// ══════════════════════════════════════════════════════════════════
// SIDEBAR TABS
// ══════════════════════════════════════════════════════════════════

const tabBtns = document.querySelectorAll(".tab-btn");
const tabContents = document.querySelectorAll(".tab-content");

function switchTab(tabName) {
    tabBtns.forEach(b => b.classList.toggle("active", b.dataset.tab === tabName));
    tabContents.forEach(t => t.classList.toggle("active", t.id === `tab-${tabName}`));
}

tabBtns.forEach(btn => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

// Auto-switch to details tab when detail content is populated
function showDetail() {
    switchTab("details");
}

// Patch all detail-setting functions to auto-switch tab
const _origDetailSetter = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'innerHTML');
const detailContentEl = document.getElementById("detail-content");
// Use MutationObserver to detect when detail content changes to non-placeholder
const detailObserver = new MutationObserver(() => {
    if (detailContentEl.querySelector('.detail-title')) {
        switchTab("details");
    }
});
detailObserver.observe(detailContentEl, { childList: true, subtree: true });

// ── Sidebar collapse toggle (mobile) ────────────────────────────
const sidebarToggle = document.getElementById("sidebar-toggle");
const sidebar = document.getElementById("sidebar");
if (sidebarToggle) {
    // Start collapsed on mobile
    if (window.innerWidth <= 768) sidebar.classList.add("collapsed");
    sidebarToggle.addEventListener("click", () => {
        sidebar.classList.toggle("collapsed");
        setTimeout(() => map.invalidateSize(), 300);
    });
}

/** Shared rendering for recommendation results (résumé + preferences pages). */

function renderRecommendations(data, payload, { gridId, noteId }) {
  const grid = document.getElementById(gridId);
  const note = document.getElementById(noteId);

  grid.innerHTML = "";

  if (data.source === "india_institutes") {
    note.textContent = data.results.length
      ? `${data.results.length} Indian institutes, most competitive first (by 2021 JoSAA closing rank).`
      : `No Indian institute lists a branch matching "${payload.field_of_study}".`;
  } else if (data.source === "us_institutions") {
    if (payload.field_of_study && data.matched_fields.length === 0) {
      note.textContent = `We couldn't match "${payload.field_of_study}" to any field of study on record. Try different wording.`;
    } else if (data.matched_fields.length > 0) {
      const fields = data.matched_fields.map((f) => f.replace(/\.$/, "")).slice(0, 4).join(", ");
      note.textContent = `${data.results.length} US universities, matched to: ${fields}.`;
    } else {
      note.textContent = `${data.results.length} US universities in your tuition range.`;
    }
  } else if (payload.fee_min || payload.fee_max || payload.field_of_study) {
    note.textContent =
      "Tuition and field-of-study data is only available for United States institutions, so these are ranked by academic score and cost of living instead.";
  } else {
    note.textContent = `${data.results.length} universities ranked by academic score and affordability.`;
  }

  if (!data.results.length) {
    grid.innerHTML = `<p class="hint">No universities matched. Try widening your budget or field.</p>`;
    return;
  }

  grid.innerHTML = data.results.map((row) => {
    if (data.source === "us_institutions") return usCard(row);
    if (data.source === "india_institutes") return indiaCard(row);
    return globalCard(row);
  }).join("");
}

/** Small compare affordance shared by every card type. */
function compareLink(key) {
  return `<a class="compare-link" href="compare.html?a=${encodeURIComponent(key)}"
     onclick="event.stopPropagation()">Compare ⇄</a>`;
}

function usCard(row) {
  const tuition = row.tuition_out_state != null
    ? `$${Math.round(row.tuition_out_state).toLocaleString()}/yr`
    : "Tuition not reported";

  const match = row.match && row.match.overall;

  return `
    <a class="result-card" href="university.html?unitid=${row.unitid}">
      ${match != null ? `<span class="match-score" title="${escapeHtml(
        row.match.dimensions.map((d) => d.label + " " + d.score + "%").join(", ")
      )}">${match}% match</span>` : ""}
      <h3>${escapeHtml(row.institution_name)}</h3>
      <p class="result-meta">${escapeHtml(row.city || "")}, ${escapeHtml(row.state || "")}</p>
      <div class="badge-row">
        <span class="badge">${tuition}</span>
        <span class="badge badge-light">${escapeHtml(row.control_label || "")}</span>
      </div>
      ${compareLink("us:" + row.unitid)}
    </a>`;
}

function indiaCard(row) {
  const fee = row.fee_band_usd_min != null
    ? `from $${row.fee_band_usd_min.toLocaleString()}/yr`
    : "Fees vary";

  return `
    <a class="result-card" href="university.html?india=${encodeURIComponent(row.institute)}">
      <h3>${escapeHtml(row.institute)}</h3>
      <p class="result-meta">${escapeHtml(row.institute_type)} · ${row.programmes} branches</p>
      <div class="badge-row">
        <span class="badge">Best closing rank ${Math.round(row.best_closing_rank).toLocaleString()}</span>
        <span class="badge badge-light">${fee}</span>
      </div>
      ${compareLink("india:" + row.institute)}
    </a>`;
}

function globalCard(row) {
  const score = row["EduBridge Score"] != null ? row["EduBridge Score"].toFixed(1) : "—";
  const rank = row["University Rank"] != null ? `Rank #${row["University Rank"]}` : "Rank n/a";
  const name = row["University"] || "";

  const body = `
    <h3>${escapeHtml(name)}</h3>
    <p class="result-meta">${escapeHtml(row["Location"] || "")}</p>
    <div class="badge-row">
      <span class="badge">${rank}</span>
      <span class="badge badge-light">Score ${score}</span>
      ${row.has_detail ? `<span class="badge badge-light">Fees available</span>` : ""}
    </div>
    ${row.has_detail ? compareLink("intl:" + name) : ""}`;

  // Only universities we hold cost data for get a link; the rest would
  // open an empty page.
  return row.has_detail
    ? `<a class="result-card" href="university.html?intl=${encodeURIComponent(name)}">${body}</a>`
    : `<div class="result-card">${body}</div>`;
}

/** Populates the country dropdown and field-of-study autocomplete. */
async function loadFilterOptions(countryId, fieldListId) {
  const data = await api("/api/filters");

  const country = document.getElementById(countryId);
  country.innerHTML = `<option value="">Any country</option>` +
    data.countries.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");

  document.getElementById(fieldListId).innerHTML =
    data.fields_of_study.map((f) => `<option value="${escapeHtml(f)}">`).join("");

  return data;
}

/** Shared rendering for recommendation results (résumé + preferences pages). */

async function renderRecommendations(data, payload, { gridId, noteId }) {
  const grid = document.getElementById(gridId);
  const note = document.getElementById(noteId);

  grid.innerHTML = "";

  const savedKeys = await getSavedKeys();

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
    if (data.source === "us_institutions") return usCard(row, payload, savedKeys);
    if (data.source === "india_institutes") return indiaCard(row, savedKeys);
    return globalCard(row, savedKeys);
  }).join("");

  const existingSummary = document.getElementById(`${gridId}-summary`);
  if (existingSummary) existingSummary.remove();

  if (data.source === "us_institutions") {
    loadSummary(gridId, payload, data.results);
  }
}

/** One grounded paragraph summarizing the top matches, fetched once per
    search right after the list renders — not per card, so it's a single
    LLM call rather than one per result. */
async function loadSummary(gridId, payload, results) {
  const grid = document.getElementById(gridId);

  const box = document.createElement("div");
  box.id = `${gridId}-summary`;
  box.className = "card summary-box";
  box.innerHTML = `<p class="hint">Summarizing your top matches…</p>`;
  grid.parentElement.insertBefore(box, grid);

  try {
    const result = await api("/api/recommendations/summary", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, results: results.slice(0, 8) })
    });
    box.innerHTML = `<p class="summary-label">Overview</p>${renderMarkdown(result.summary)}`;
  } catch (error) {
    box.innerHTML = `<p class="hint">${escapeHtml(error.message)}</p>`;
  }
}

/** "Why this match?" — fetches a grounded explanation for one US result,
    on demand, so a search doesn't trigger up to 30 LLM calls at once. */
async function explainMatch(button) {
  const card = button.closest(".result-card");
  const out = card.querySelector(".explain-text");

  out.hidden = false;
  out.textContent = "Thinking…";
  button.disabled = true;

  try {
    const result = await api("/api/recommendations/explain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        unitid: Number(button.dataset.unitid),
        field_of_study: button.dataset.field || null,
        fee_min: button.dataset.feeMin ? Number(button.dataset.feeMin) : null,
        fee_max: button.dataset.feeMax ? Number(button.dataset.feeMax) : null,
        country: button.dataset.country || null
      })
    });
    out.innerHTML = renderMarkdown(result.explanation);
    button.remove();
  } catch (error) {
    out.textContent = error.message;
    button.disabled = false;
  }
}

function usCard(row, payload = {}, savedKeys) {
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
      <div class="badge-row">
        ${compareLink("us:" + row.unitid)}
        ${saveButton("us:" + row.unitid, savedKeys)}
        <button type="button" class="explain-link"
          data-unitid="${row.unitid}"
          data-field="${escapeHtml(payload.field_of_study || "")}"
          data-fee-min="${payload.fee_min ?? ""}"
          data-fee-max="${payload.fee_max ?? ""}"
          data-country="${escapeHtml(payload.country || "")}"
          onclick="event.preventDefault(); event.stopPropagation(); explainMatch(this);">Why this match?</button>
      </div>
      <div class="explain-text hint" hidden></div>
    </a>`;
}

function indiaCard(row, savedKeys) {
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
      <div class="badge-row">
        ${compareLink("india:" + row.institute)}
        ${saveButton("india:" + row.institute, savedKeys)}
      </div>
    </a>`;
}

function globalCard(row, savedKeys) {
  const score = row["EduBridge Score"] != null ? row["EduBridge Score"].toFixed(1) : "—";
  const rank = row["University Rank"] != null ? `Rank #${row["University Rank"]}` : "Rank n/a";
  const name = row["University"] || "";

  const body = `
    <h3>${escapeHtml(name)}</h3>
    <p class="result-meta">${escapeHtml(row["Location"] || "")}</p>
    <div class="badge-row">
      <span class="badge">${rank}</span>
      <span class="badge badge-light">Score ${score}</span>
      ${row.has_detail
        ? `<span class="badge badge-light">Fees available</span>`
        : `<span class="badge badge-muted">No fee data</span>`}
    </div>
    ${row.has_detail
      ? `<div class="badge-row">${compareLink("intl:" + name)}${saveButton("intl:" + name, savedKeys)}</div>`
      : `<p class="hint">Not enough data for a detail page yet.</p>`}`;

  // Only universities we hold cost data for get a link; the rest would
  // open an empty page. The no-link version is styled as not clickable
  // (muted, no hover lift) instead of looking identical but silently
  // doing nothing.
  return row.has_detail
    ? `<a class="result-card" href="university.html?intl=${encodeURIComponent(name)}">${body}</a>`
    : `<div class="result-card result-card-disabled">${body}</div>`;
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
